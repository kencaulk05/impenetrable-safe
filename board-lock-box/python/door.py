"""The door logic, with no board library in it, so it can be tested.

The sketch sends a distance reading every 60 ms and tells us when the motor starts and stops. From the distance this module decides what the door is doing:

    closed   the distance is in the closed band (where the MOTOR closes the door: 106 mm, 5 closes out of 5, plus or minus 10)
    ajar     further than that but still in view (the door has been pushed or is part-way: 123 to 196 mm were measured)
    open     no echo at all, or further than the open limit (the door has left the sensor's view: no echo, or 336 mm and beyond, were measured)
    blocked  nearer than the closed band (something is in front of the sensor)

A state only changes after several readings in a row agree (the debounce, about 0.3 s), so one stray reading does nothing.
It opens and closes the door, and CHECKS afterwards, with the sensor, that the move really worked (it tries once more, then reports a fault).
When the door is locked (commanded closed and seen closed) and then reads anything other than closed without being told to move, that is TAMPER.
"""
import csv
import datetime
import json
import statistics
import threading
import time
from collections import deque
from pathlib import Path

DEFAULTS = {"open_dir": -1, "open_ms": 600, "close_ms": 600, "pwm": 100, "ramp_ms": 250,     # the motor values that reached the end on the real door
            "closed_mm": 106, "closed_tol_mm": 10, "open_mm": 250, "debounce": 5, "push_back": False}
INT_LIMITS = {"open_ms": (50, 3000), "close_ms": (50, 3000), "pwm": (60, 255), "ramp_ms": (0, 1000), "closed_mm": (30, 1000), "closed_tol_mm": (5, 40), "open_mm": (60, 3500), "debounce": (2, 20)}
MIN_MM, MAX_MM = 20, 4000
SETTLE_S = 0.8                 # after a move ends, wait for the door and the sensor to settle before checking it
RETRIES = 1                    # a move that did not work is tried once more
MAX_PUSHES = 1                 # push back at most once per tamper episode
HISTORY_S = 35.0
EVENT_FIELDS = ["time", "kind", "text", "mm"]


def usable(mm):
    try:
        v = int(mm)
    except (TypeError, ValueError):
        return None
    return v if MIN_MM <= v <= MAX_MM else None


def clean_settings(new, base=None):
    """The settings with every number kept in a safe range. Raises ValueError for something that is not a number or does not make sense."""
    s = dict(base or DEFAULTS)
    new = new or {}
    for k, (lo, hi) in INT_LIMITS.items():
        if k in new:
            try:
                s[k] = max(lo, min(hi, int(float(new[k]))))
            except (TypeError, ValueError):
                raise ValueError("The %s must be a number." % k.replace("_", " "))
    if "open_dir" in new:
        try:
            s["open_dir"] = 1 if int(float(new["open_dir"])) >= 0 else -1
        except (TypeError, ValueError):
            raise ValueError("The direction must be +1 or -1.")
    if "push_back" in new:
        s["push_back"] = bool(new["push_back"])
    if s["open_mm"] < s["closed_mm"] + s["closed_tol_mm"] + 20:
        raise ValueError("The 'open' distance (%d mm) must be at least 20 mm beyond the closed band (up to %d mm)." % (s["open_mm"], s["closed_mm"] + s["closed_tol_mm"]))
    return s


def band(mm, cfg):
    """closed, blocked, ajar or open, for one filtered distance (None = no echo)."""
    if mm is None:
        return "open"
    lo, hi = cfg["closed_mm"] - cfg["closed_tol_mm"], cfg["closed_mm"] + cfg["closed_tol_mm"]
    if mm < lo:
        return "blocked"
    if mm <= hi:
        return "closed"
    if mm <= cfg["open_mm"]:
        return "ajar"
    return "open"


class Door:
    """io needs one method, io.call(name, a, b), which asks the board to do something (motor_run, motor_speed)."""

    def __init__(self, io, settings_path=None, log_path=None, now=time.monotonic, clock=datetime.datetime.now):
        self.io, self.now, self.clock, self.settings_path, self.log_path = io, now, clock, settings_path, log_path
        self.cfg = dict(DEFAULTS)
        if settings_path and Path(settings_path).exists():
            try:
                self.cfg = clean_settings(json.loads(Path(settings_path).read_text(encoding="utf-8")))
            except (ValueError, OSError):
                self.cfg = dict(DEFAULTS)
        self._lock = threading.RLock()
        self._incoming = deque()               # readings from the board, filled on the Bridge's thread and emptied by tick()
        self.history = deque()                 # (time, filtered) for the chart
        self.last_t, self.last_f, self.last_raw = None, None, None
        self.state, self._cand, self._cand_n = None, None, 0
        self.commanded = None                  # "closed" (locked), "open", or None (not known)
        self.move, self.tamper, self.pushes, self.fault = None, False, 0, None
        self.sensor_lost = False
        self.running, self.run_dir = False, 0
        self.events = []

    # ---- what the board tells us (on the Bridge's own thread: only store, tick() does the thinking)
    def on_distance(self, mm, raw):
        self._incoming.append((self.now(), usable(mm), usable(raw)))

    def on_motor(self, direction, ms):
        self.running, self.run_dir = bool(direction), (1 if direction > 0 else -1 if direction < 0 else 0)

    # ---- helpers
    def _event(self, events, kind, text):
        e = {"time": self.clock().strftime("%H:%M:%S"), "kind": kind, "text": text, "mm": self.last_f}
        events.append(e)
        self.events.append(e)
        del self.events[:-200]
        if self.log_path:
            new = not Path(self.log_path).exists()
            try:
                with open(self.log_path, "a", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
                    if new:
                        w.writeheader()
                    w.writerow(e)
            except OSError:
                pass

    def _where(self):
        return "it reads %s" % ("no echo" if self.last_f is None else "%d mm" % self.last_f)

    def _start_move(self, action, attempt=1, reason="command"):
        c = self.cfg
        direction = c["open_dir"] if action == "open" else -c["open_dir"]
        ms = c["open_ms"] if action == "open" else c["close_ms"]
        self.io.call("motor_speed", c["pwm"], c["ramp_ms"])
        self.io.call("motor_run", direction, ms)
        t = self.now()
        self.move = {"action": action, "attempt": attempt, "reason": reason, "ends": t + ms / 1000.0, "verify_at": t + ms / 1000.0 + SETTLE_S}
        return direction, ms

    # ---- commands from the page
    def request_open(self):
        with self._lock:
            ev = []
            if self.move:
                raise ValueError("The door is already moving: wait for it, or press STOP (Esc).")
            self.fault, self.commanded = None, None
            d, ms = self._start_move("open")
            self._event(ev, "move", "Opening: motor %+d for %d ms." % (d, ms))
            return ev

    def request_close(self):
        with self._lock:
            ev = []
            if self.move:
                raise ValueError("The door is already moving: wait for it, or press STOP (Esc).")
            self.fault, self.commanded = None, None
            d, ms = self._start_move("close")
            self._event(ev, "move", "Closing: motor %+d for %d ms." % (d, ms))
            return ev

    def toggle(self):
        """The push-button: open a closed door, close anything else."""
        with self._lock:
            if self.move:
                raise ValueError("The door is already moving: wait for it, or press STOP (Esc).")
            if self.state is None:
                raise ValueError("The sensor has not seen the door yet: wait a moment.")
        return self.request_open() if self.state == "closed" else self.request_close()

    def stop(self):
        with self._lock:
            ev = []
            self.io.call("motor_run", 0, 0)                  # always allowed, whatever the state
            was = self.move is not None or self.running
            self.move, self.commanded = None, None
            self.running, self.run_dir = False, 0
            if was:
                self._event(ev, "stopped", "Stopped by hand: the door state is checked again from the sensor.")
            return ev

    def update_settings(self, new):
        with self._lock:
            self.cfg = clean_settings(new, self.cfg)
            if self.settings_path:
                try:
                    Path(self.settings_path).write_text(json.dumps(self.cfg), encoding="utf-8")
                except OSError:
                    pass
            return self.cfg

    def calibrate(self):
        """Take the closed distance from what the sensor sees now (the door must be closed and still)."""
        with self._lock:
            if self.move:
                raise ValueError("Wait for the move to end first.")
            t = self.now()
            recent = [f for (tt, f) in self.history if t - tt <= 3.0 and f is not None]
            if len(recent) < 20:
                raise ValueError("Not enough readings: the sensor must see the door steadily for 3 seconds (is the door closed?).")
            if max(recent) - min(recent) > 8:
                raise ValueError("The distance is not steady (it varies by %d mm): hold the door still and try again." % (max(recent) - min(recent)))
            med = int(statistics.median(recent))
            old = self.cfg["closed_mm"]
            self.update_settings({"closed_mm": med})
            ev = []
            self._event(ev, "calibrated", "The closed distance is now %d mm (it was %d mm)." % (med, old))
            return ev

    def clear_events(self):
        with self._lock:
            self.events = []

    # ---- the thinking (call often)
    def tick(self):
        """Returns the new events: a list of {'time', 'kind', 'text', 'mm'}."""
        with self._lock:
            ev, t, c = [], self.now(), self.cfg
            while self._incoming:                                         # 1. the readings that arrived
                tt, f, raw = self._incoming.popleft()
                self.last_t, self.last_f, self.last_raw = tt, f, raw
                self.history.append((tt, f))
                while self.history and tt - self.history[0][0] > HISTORY_S:
                    self.history.popleft()
                if self.sensor_lost:
                    self.sensor_lost = False
                    self._event(ev, "sensor_back", "Distance readings are back.")
                b = band(f, c)
                self._cand, self._cand_n = (b, self._cand_n + 1) if b == self._cand else (b, 1)
                if self._cand_n >= c["debounce"] and self.state != b:
                    old, self.state = self.state, b
                    self._event(ev, "state", "The door reads %s (%s)." % (b, "no echo" if f is None else "%d mm" % f))
            if self.last_t is not None and t - self.last_t > 1.0 and not self.sensor_lost:   # 2. the sensor went quiet
                self.sensor_lost = True
                self._event(ev, "sensor_lost", "No distance readings for over a second: is the sketch running?")
            if self.move and t >= self.move["verify_at"]:                  # 3. a move has ended: did it work?
                mv = self.move
                want = "open" if mv["action"] == "open" else "closed"
                if self.state == want:
                    self.move, self.fault, self.commanded = None, None, want
                    self._event(ev, "opened" if want == "open" else "closed", "The door is %s (%s)%s." % (want, "no echo" if self.last_f is None else "%d mm" % self.last_f, ", pushed back" if mv["reason"] == "push_back" else ""))
                elif mv["attempt"] <= RETRIES:
                    self._event(ev, "retry", "The door did not %s (%s): trying once more." % (mv["action"], self._where()))
                    self._start_move(mv["action"], mv["attempt"] + 1, mv["reason"])
                else:
                    self.move, self.commanded = None, None
                    self.fault = "The door did not %s: %s (%s)." % (mv["action"], self._where(), self.state or "unknown")
                    self._event(ev, "fault", self.fault)
            if self.move is None and self.commanded is None and self.state == "closed" and not self.fault and not self.tamper:   # 4. a closed door is a locked door
                self.commanded = "closed"
                self._event(ev, "locked", "The door is closed: locked.")
            if self.move is None and self.commanded == "closed" and self.state in ("ajar", "open", "blocked"):   # 5. a locked door that is not closed: TAMPER
                if not self.tamper:
                    self.tamper, self.pushes = True, 0
                    what = "something is in front of the sensor" if self.state == "blocked" else "the door was forced"
                    self._event(ev, "tamper", "TAMPER: the locked door reads %s (%s): %s." % (self.state, "no echo" if self.last_f is None else "%d mm" % self.last_f, what))
                if c["push_back"] and self.pushes < MAX_PUSHES and self.state != "blocked":
                    self.pushes += 1
                    self._start_move("close", 1, "push_back")
                    self._event(ev, "push_back", "Pushing the door back shut.")
            if self.tamper and self.state == "closed" and self.move is None:
                self.tamper, self.fault = False, None                    # closed again by hand: the alarm and any failed-push-back fault are over, and the next reading locks it again
                self._event(ev, "tamper_over", "The door is closed again.")
            return ev

    # ---- what the page shows
    def snapshot(self):
        with self._lock:
            t = self.now()
            hist = [[round(tt - t, 1), f] for (tt, f) in list(self.history) if t - tt <= 30.0]
            if len(hist) > 200:
                hist = hist[::-(-len(hist) // 200)]
            c = self.cfg
            mode = "moving" if self.move else ("locked" if self.commanded == "closed" else "unlocked" if self.commanded == "open" else "unknown")
            sensor = "waiting" if self.last_t is None else ("lost" if self.sensor_lost else "ok")
            return {"mm": self.last_f, "raw": self.last_raw, "age_s": None if self.last_t is None else round(t - self.last_t, 1), "state": self.state, "mode": mode,
                    "moving": self.move["action"] if self.move else None, "attempt": self.move["attempt"] if self.move else 0, "tamper": self.tamper, "fault": self.fault, "sensor": sensor,
                    "settings": dict(c), "bands": {"lo": c["closed_mm"] - c["closed_tol_mm"], "hi": c["closed_mm"] + c["closed_tol_mm"], "open": c["open_mm"]},
                    "history": hist, "events": list(self.events[-40:]), "motor_running": self.running, "log": "door_log.csv"}
