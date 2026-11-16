"""The lock box: the finger-reading lock (lock.py), the door (door.py) and the LED matrix, joined together. No camera, no board library and no web page in here, so every rule can be tested.

WHAT HAPPENS
  button (the SPACE bar) -> the lock rules (lock.py, the same as on the laptop) read the digits the network sees -> a correct code UNLOCKS: the door is asked to open ->
  after 10 seconds, or when the button is pressed, the lock LOCKS again: the door is asked to close. The door (door.py) checks every move with the distance sensor.
  If the locked door is FORCED the door logic raises TAMPER: any entry in progress is dropped and finger entry is blocked for 15 seconds. That is written in the log, and it does NOT count as a wrong try.

THE LOG never contains the digits that were shown (only that a digit was read), so the log file cannot give the code away.
THE LED MATRIX shows the same pictures as the laptop demo (digits with progress dots, padlocks, a tick, a cross), and an "!" for tamper or an "X" for a fault of the door or its sensor.
"""
import csv
import datetime
import json
import math
import secrets
import statistics
import threading
import time
from pathlib import Path

import matrix as mx
from lock import CHALLENGE, ENTERING, IDLE, LOCKOUT, UNLOCKED, LockController, Policy, Verifier, check_code, describe

ITERATIONS = 200_000                        # how hard the stored hash is to guess (PBKDF2 rounds)
TAMPER_LOCKOUT_S = 15.0                     # finger entry is blocked this long after the locked door is forced
LOG_FIELDS = ["time", "source", "kind", "text"]
POOLS = {"135": (1, 3, 5), "12345": (1, 2, 3, 4, 5)}          # the digits the live challenge may ask for: the ones the network reads best, or all of them
ALERT = mx._frame(["......#......", "......#......", "......#......", "......#......", "......#......", ".............", "......#......", "............."])           # "!"
FAULT = mx._frame(["..#.......#..", "...#.....#...", "....#...#....", ".....#.#.....", ".....#.#.....", "....#...#....", "...#.....#...", "..#.......#.."])           # "X"
DOOR_LOGGED = {"opened", "closed", "tamper", "tamper_over", "fault", "retry", "push_back", "stopped", "sensor_lost", "sensor_back", "calibrated", "locked", "move"}      # ("state" changes are too chatty for the log)
NOTICE_LEVEL = {"unlocked": "ok", "denied": "warn", "lockout": "warn", "lockout_over": "info", "timeout": "info", "relock": "info", "tamper_lockout": "warn", "tamper": "warn", "fault": "warn", "ignored": "info"}


class LockBox:
    """io needs one method, io.call(name, a, b), which asks the board to do something (here: pic_a and pic_b, the LED matrix picture)."""

    def __init__(self, door, io, config_path=None, log_path=None, now=time.monotonic, clock=datetime.datetime.now, rng=None):
        self.door, self.io, self.config_path, self.log_path, self.now, self.clock = door, io, config_path, log_path, now, clock
        self.rng = rng or secrets.SystemRandom()
        self._lock = threading.RLock()
        self.ctl, self.policy = None, None
        self.log, self._notices = [], []
        self.base = mx.LOCKED                # the picture of the lock's own state
        self.tamper_until, self.tamper_noted = 0.0, False
        self.want_door = None                # "open" or "close": waits here while the door is busy moving
        self.pic_sent, self._pic_try = None, -1e9
        self.started, self.perf = self.now(), time.perf_counter           # (perf is replaced by a fake clock in the tests)
        self.stats = self._new_stats()
        self._session_at = self._unlocked_at = self._locked_since = None
        self._load()
        self._log("system", "started", "The app started.")

    # ---- the measurements (the tally, the times, how long it has been locked quietly)
    @staticmethod
    def _new_stats():
        return {"sessions": 0, "unlocked": 0, "denied_code": 0, "denied_challenge": 0, "timeouts": 0, "lockouts": 0, "tamper": 0, "faults": 0, "unlock_times": [], "open_times": [], "check_ms": []}

    def reset_stats(self):
        """Start a new tally (for example before another person tries). The log is kept."""
        with self._lock:
            self.stats = self._new_stats()
            self._session_at = self._unlocked_at = None
            self._log("system", "tally_reset", "The measurements were reset.")

    def _stats_view(self, now, door_mode):
        s = self.stats
        def times(v): return {"n": len(v), "last": v[-1] if v else None, "median": round(statistics.median(v), 2) if v else None}
        locked_for = now - self._locked_since if (self._locked_since is not None and door_mode == "locked" and not self._tamper_active(now)) else 0.0
        return {"sessions": s["sessions"], "unlocked": s["unlocked"], "denied_code": s["denied_code"], "denied_challenge": s["denied_challenge"], "timeouts": s["timeouts"], "lockouts": s["lockouts"],
                "tamper": s["tamper"], "faults": s["faults"], "unlock_s": times(s["unlock_times"]), "open_s": times(s["open_times"]),
                "check_ms": {"n": len(s["check_ms"]), "last": s["check_ms"][-1] if s["check_ms"] else None, "slowest": max(s["check_ms"]) if s["check_ms"] else None},
                "locked_for_s": round(locked_for, 1), "uptime_s": round(now - self.started, 1)}

    def read_log_file(self, limit=3000):
        """Every entry in lockbox_log.csv (the page only gets the last 60), or what is in memory if there is no file."""
        try:
            with open(self.log_path, newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))[-limit:]
        except (OSError, TypeError):
            return list(self.log)

    # ---- the secret code and the rules
    def _load(self):
        self.ctl = self.policy = None
        if not self.config_path or not Path(self.config_path).exists():
            return
        try:
            d = json.loads(Path(self.config_path).read_text(encoding="utf-8"))
            verifier, policy = Verifier.from_dict(d["verifier"]), Policy.from_dict(d.get("policy"))
        except (ValueError, KeyError, TypeError, OSError):
            self._log("system", "config_error", "lock_config.json could not be read: set a code again.")
            return
        self.policy, self.ctl = policy, LockController(verifier, policy, rng=self.rng)

    def set_code(self, code, confirm, challenge_digits=1, pool="135"):
        """Choose the code (3 different digits from 1 to 5). Only a salted hash is stored, never the digits, and the digits are never written to the log."""
        digits = check_code(code)
        if str(confirm) != str(code):
            raise ValueError("The two codes are not the same.")
        try:
            k = int(challenge_digits)
        except (TypeError, ValueError):
            k = -1
        if k not in (0, 1, 2):
            raise ValueError("The live challenge asks for 0, 1 or 2 digits before the code.")
        digits_in_pool = POOLS.get(str(pool)) or tuple(sorted({int(c) for c in str(pool) if c in "12345"}))
        if not digits_in_pool:
            raise ValueError("The challenge digits are some of 1 to 5.")
        with self._lock:
            verifier, policy = Verifier.from_code(digits, iterations=ITERATIONS), Policy(challenge_digits=k, challenge_pool=digits_in_pool)
            if self.config_path:
                Path(self.config_path).write_text(json.dumps({"verifier": verifier.to_dict(), "policy": policy.to_dict()}, indent=1), encoding="utf-8")
            self.policy, self.ctl = policy, LockController(verifier, policy, rng=self.rng)
            self.base = mx.LOCKED
            self._log("lock", "code_set", "A new code was set (live challenge: %s). Only a salted hash is stored, never the digits." % ("%d digit(s) from %s" % (k, ", ".join(str(d) for d in digits_in_pool)) if k else "off"))

    # ---- the log
    def _log(self, source, kind, text):
        e = {"time": self.clock().strftime("%H:%M:%S"), "source": source, "kind": kind, "text": text}
        self.log.append(e)
        del self.log[:-200]
        if kind in NOTICE_LEVEL:
            self._notices.append((NOTICE_LEVEL[kind], text))
        if self.log_path:
            try:
                new = not Path(self.log_path).exists()
                with open(self.log_path, "a", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
                    if new:
                        w.writeheader()
                    w.writerow(e)
            except OSError:
                pass

    def drain_notices(self):
        with self._lock:
            n, self._notices = self._notices, []
            return n

    def clear_log(self):
        with self._lock:
            self.log = []

    def _text(self, e):
        """An event in words for the log: like the events themselves it says neither whether a digit was right NOR which digit was shown (the log is a file)."""
        k, of = e[0], self.policy.n_digits if self.policy else 3
        if k == "digit": return "read digit number %d of %d" % (e[1] + 1, of)
        if k == "challenge": return "live challenge: show the digit on the LED matrix first"
        if k == "challenge_ok": return "challenge digit accepted"
        return describe(e, of)

    # ---- what the person does, and what the camera sees
    def _tamper_active(self, now):
        return now < self.tamper_until

    def press_button(self):
        with self._lock:
            now = self.now()
            if self.ctl is None:
                raise ValueError("Set a code first (the Code section).")
            if self._tamper_active(now):
                left = self.tamper_until - now
                self._log("lock", "ignored", "Button ignored: finger entry is blocked for %d more seconds after the tamper alarm." % math.ceil(left))
                return [("ignored", "tamper", round(left, 1))]
            ev = self.ctl.press_button(now)
            self._handle(ev, now)
            return ev

    def on_frame(self, probs):
        """Call once for every camera picture the network has looked at (probs: the six probabilities)."""
        with self._lock:
            if self.ctl is None:
                return []
            now = self.now()
            if self._tamper_active(now):                 # no finger entry while it is blocked
                return []
            t0 = self.perf()
            ev = self.ctl.update(now, probs)
            ms = (self.perf() - t0) * 1000.0
            if any(e[0] == "unlocked" or (e[0] == "denied" and e[1] == "code") for e in ev):      # the code was checked (the slow hash): how long that took is how long the page may pause
                self.stats["check_ms"] = (self.stats["check_ms"] + [round(ms, 1)])[-200:]
            self._handle(ev, now)
            return ev

    def _handle(self, events, now):
        if not events:
            return
        for e in events:
            self._log("lock", e[0], self._text(e))
            if e[0] == "session":
                self.stats["sessions"] += 1
                self._session_at = now
            elif e[0] == "unlocked":
                self.want_door = "open"
                self.stats["unlocked"] += 1
                self._locked_since, self._unlocked_at = None, now
                if self._session_at is not None:
                    self.stats["unlock_times"] = (self.stats["unlock_times"] + [round(now - self._session_at, 2)])[-200:]
            elif e[0] == "relock":
                self.want_door = "close"
            elif e[0] == "denied":
                self.stats["denied_challenge" if e[1] == "challenge" else "denied_code"] += 1
            elif e[0] == "timeout":
                self.stats["timeouts"] += 1
            elif e[0] == "lockout":
                self.stats["lockouts"] += 1
        pic = mx.for_events(events, self.ctl.display(now))
        if pic is not None:
            self.base = pic

    # ---- time passing, and the door
    def tick(self):
        """Call often: the door thinks, the lock's timers run, and the door is told what the lock wants."""
        with self._lock:
            now = self.now()
            self._door_events(self.door.tick(), now)
            if self.ctl is not None:
                self._handle(self.ctl.tick(now), now)
            if self.tamper_noted and now >= self.tamper_until:
                self.tamper_noted = False
                self._log("lock", "tamper_lockout_over", "The tamper lockout is over: finger entry works again.")
            self._run_door_wants()

    def _door_events(self, events, now=None):
        now = self.now() if now is None else now
        for e in events or []:
            if e["kind"] in DOOR_LOGGED:
                self._log("door", e["kind"], e["text"])
            if e["kind"] == "tamper":
                self._tamper(now)
            elif e["kind"] in ("fault", "sensor_lost"):
                self.stats["faults"] += 1
                self._locked_since = None
            elif e["kind"] == "opened" and self._unlocked_at is not None:
                self.stats["open_times"] = (self.stats["open_times"] + [round(now - self._unlocked_at, 2)])[-200:]
                self._unlocked_at = None
            elif e["kind"] in ("locked", "closed", "tamper_over"):          # (after a forced door is closed again there is no new "locked" event: the quiet time starts again here)
                self._locked_since = now

    def _tamper(self, now):
        """The locked door was forced: drop any entry in progress and block finger entry for a while. NOT a wrong try: the failure counters are not touched."""
        self.tamper_until, self.tamper_noted = now + TAMPER_LOCKOUT_S, True
        self.stats["tamper"] += 1
        self._locked_since = None
        if self.ctl is not None:
            self.ctl.abort()
        self._log("lock", "tamper_lockout", "TAMPER: finger entry is blocked for %d seconds. This is noted here and does not count as a wrong try." % round(TAMPER_LOCKOUT_S))

    def _run_door_wants(self):
        if self.want_door is None or self.door.move:
            return
        want, self.want_door = self.want_door, None
        try:
            if want == "open" and self.door.state == "open":
                self.door.commanded, self.door.fault = "open", None             # the door and the lock agree: an old fault (a close that did not work) is over
                self._log("door", "info", "The door is already open: no need to move it.")
            elif want == "close" and self.door.state == "closed":
                self.door.commanded, self.door.fault = "closed", None           # the door and the lock agree: an old fault (an open that did not work) is over
                self._log("door", "info", "The door is already closed: no need to move it.")
            else:
                self._door_events(self.door.request_open() if want == "open" else self.door.request_close())
        except Exception as e:
            self._log("door", "fault", "The door could not be moved: %s" % str(e)[:100])

    # ---- the door by hand (this bypasses the code: for testing and for putting things right)
    def door_command(self, what):
        with self._lock:
            if what == "stop":
                self.want_door = None
                self._door_events(self.door.stop())
            elif what == "calibrate":
                self._door_events(self.door.calibrate())
            elif what in ("open", "close"):
                self._log("lock", "maintenance", "Door %s with the maintenance button: this bypasses the code." % ("opened" if what == "open" else "closed"))
                self._door_events(self.door.request_open() if what == "open" else self.door.request_close())
            else:
                raise ValueError("Unknown door command.")

    def set_push_back(self, on):
        with self._lock:
            self.door.update_settings({"push_back": bool(on)})
            self._log("door", "info", "Push back when forced: %s." % ("on" if on else "off"))

    # ---- the LED matrix
    def current_picture(self):
        """The 8 rows (13 bits each) the matrix should show now: a fault or tamper picture takes over from the lock's own picture."""
        d = self.door
        if d.fault or d.sensor_lost:
            pic = FAULT
        elif self._tamper_active(self.now()) or d.tamper:
            pic = ALERT
        else:
            pic = self.base
        return mx.frame_rows(pic)

    def sync_picture(self):
        """Send the picture to the board if it changed (two calls, and the picture appears only when both have arrived). A failed call is tried again after a second."""
        with self._lock:
            rows = self.current_picture()
            now = self.now()
            if rows == self.pic_sent or now - self._pic_try < 1.0:
                return False
            try:
                self.io.call("pic_a", (rows[0] << 13) | rows[1], (rows[2] << 13) | rows[3])
                self.io.call("pic_b", (rows[4] << 13) | rows[5], (rows[6] << 13) | rows[7])
                self.pic_sent = rows
                return True
            except Exception:
                self._pic_try = now
                return False

    # ---- what the page shows
    def _hint(self, state, d, tamper_left):
        door = self.door
        if state == "setup":
            return "Set a code first (the Code section below)."
        if tamper_left > 0:
            return "TAMPER: finger entry is blocked for %d more seconds." % math.ceil(tamper_left)
        if door.fault:
            return "The door has a problem: %s" % door.fault
        if state == LOCKOUT:
            return "Locked out for %d more seconds after too many wrong tries." % math.ceil(d["lockout_left"])
        if state == CHALLENGE:
            return "Show the digit on the LED matrix first (it is also shown here)."
        if state == ENTERING:
            return "Show your code: digit %d of %d. Hold each number up until it is read, then rest your hand (a fist) before the next." % (d["entered"] + 1, d["of"])
        if state == UNLOCKED:
            return "UNLOCKED. The door locks again in %d seconds, or press the button." % math.ceil(d["unlocked_left"])
        if door.state in ("open", "ajar") and door.commanded in (None, "open") and not door.move:
            return "The door is open but the lock is locked (it was opened by hand?). Close it with the Close button in the Door section."
        return "Locked. Press the button (the Space bar), then show your hand."

    def snapshot(self):
        with self._lock:
            now = self.now()
            d = self.ctl.display(now) if self.ctl else None
            state = "setup" if self.ctl is None else self.ctl.state
            left = max(0.0, self.tamper_until - now)
            cd = d["challenge"][d["challenge_done"]] if d and state == CHALLENGE and d["challenge_done"] < len(d["challenge"]) else None
            door = self.door.snapshot()
            door.pop("history", None)
            door.pop("events", None)
            p = self.policy
            return {"configured": self.ctl is not None, "state": state, "display": d, "challenge_digit": cd, "tamper_left": round(left, 1), "hint": self._hint(state, d, left),
                    "policy": None if p is None else {"n_digits": p.n_digits, "hold_frames": p.hold_frames, "challenge_digits": p.challenge_digits, "challenge_pool": list(p.challenge_pool), "max_failures": p.max_failures,
                                                      "lockout_seconds": p.lockout_seconds, "relock_seconds": p.relock_seconds, "tamper_lockout_s": TAMPER_LOCKOUT_S},
                    "door": door, "picture": self.current_picture(), "log": list(self.log[-60:]), "log_file": "lockbox_log.csv", "want_door": self.want_door, "stats": self._stats_view(now, door["mode"])}
