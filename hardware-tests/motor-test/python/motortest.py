"""The logic of the motor test, with no board library in it, so it can be tested.

The web page sends commands (the next move, open, close, STOP ...). This module turns them into calls to the board (motor_speed and motor_run), keeps track of what the motor
is doing from the messages the sketch sends back, remembers which way the door is believed to be, and keeps a table of the moves, each of which you rate afterwards
("reached the end", "stopped short", ...) so that the right speed and times can be found. The table is also kept in moves.csv.
"""
import csv
import datetime
import json
import time
from pathlib import Path

DEFAULTS = {"pwm": 150, "ramp_ms": 250, "open_ms": 600, "close_ms": 600, "open_dir": 1}
LIMITS = {"pwm": (60, 255), "ramp_ms": (0, 1000), "open_ms": (50, 3000), "close_ms": (50, 3000)}     # the sketch enforces the same limits
OUTCOMES = ("reached the end", "stopped short", "went too far", "grinding or jammed")
FIELDS = ["id", "time", "action", "dir", "ms", "pwm", "ramp_ms", "confirmed", "outcome"]
CONFIRM_TIMEOUT_S = 1.5                # the sketch tells us within a moment when a move starts; if not, something is wrong


def clean_settings(new, base=None):
    """The settings with every number kept inside a safe range. Raises ValueError for something that is not a number."""
    s = dict(base or DEFAULTS)
    new = new or {}
    for k, (lo, hi) in LIMITS.items():
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
    return s


class MotorTest:
    """io needs one method, io.call(name, a, b), which asks the board to do something (motor_run, motor_speed)."""

    def __init__(self, io, settings_path=None, log_path=None, now=time.monotonic, clock=datetime.datetime.now):
        self.io, self.now, self.clock, self.settings_path, self.log_path = io, now, clock, settings_path, log_path
        self.settings = dict(DEFAULTS)
        if settings_path and Path(settings_path).exists():
            try:
                self.settings = clean_settings(json.loads(Path(settings_path).read_text(encoding="utf-8")))
            except (ValueError, OSError):
                self.settings = dict(DEFAULTS)
        self.door = "closed"                 # what we believe: the person can correct it
        self.running, self.run_dir, self.run_until = False, 0, 0.0
        self.heard = False                   # has the board ever told us about the motor?
        self.moves, self.history, self.pending, self.next_id = [], [], None, 1

    # ---- what the board tells us (called on the Bridge's own thread, so it only stores things)
    def on_motor(self, direction, ms):
        self.heard = True
        if direction:
            self.running, self.run_dir, self.run_until = True, (1 if direction > 0 else -1), self.now() + ms / 1000.0
        else:
            self.running, self.run_dir = False, 0
        if self.pending is not None:                 # a start message, or a stop message (the sketch only sends one after a move it ran): either way the board did it
            self.pending["confirmed"], self.pending = True, None

    # ---- commands from the page
    def update_settings(self, new):
        self.settings = clean_settings(new, self.settings)
        if self.settings_path:
            try:
                Path(self.settings_path).write_text(json.dumps(self.settings), encoding="utf-8")
            except OSError:
                pass
        return self.settings

    def move(self, which="next", settings=None):
        """which: 'next' (the other way from the last move), 'open' or 'close'. Returns the new row."""
        if self.running:
            raise ValueError("The motor is running: press STOP (Esc) first, or wait for the move to end.")
        if which not in ("next", "open", "close"):
            raise ValueError("Unknown move.")
        if settings:
            self.update_settings(settings)
        s = self.settings
        action = ("close" if self.door == "open" else "open") if which == "next" else which
        direction = s["open_dir"] if action == "open" else -s["open_dir"]
        ms = s["open_ms"] if action == "open" else s["close_ms"]
        row = {"id": self.next_id, "time": self.clock().strftime("%H:%M:%S"), "action": action, "dir": direction, "ms": ms, "pwm": s["pwm"], "ramp_ms": s["ramp_ms"], "confirmed": None, "outcome": "", "sent_at": self.now()}
        self.pending = row                           # BEFORE calling the board: its "motor started" message can arrive before the call returns, and must not be lost
        try:
            self.io.call("motor_speed", s["pwm"], s["ramp_ms"])
            self.io.call("motor_run", direction, ms)
        except Exception:
            self.pending = None                      # the call failed: there is no move to wait for, and nothing is added to the table
            raise
        self.next_id += 1
        self.moves.append(row); self.history.append(row)
        self.door = "open" if action == "open" else "closed"
        self._save_log()
        return row

    def stop(self):
        self.io.call("motor_run", 0, 0)          # always allowed, whatever the state
        self.running, self.run_dir = False, 0

    def set_door(self, door):
        if door not in ("closed", "open"):
            raise ValueError("The door is either closed or open.")
        self.door = door

    def rate(self, move_id, outcome):
        row = next((r for r in self.history if r["id"] == move_id), None)
        if row is None:
            raise ValueError("That move is not in the table any more.")
        if outcome not in OUTCOMES and outcome != "":
            raise ValueError("Unknown outcome.")
        row["outcome"] = outcome
        self._save_log()

    def clear(self):
        self.moves = []                          # the table; moves.csv keeps everything

    def tick(self):
        """Call often. Returns a notice {'level', 'text'} when something needs saying, else None."""
        t = self.now()
        if self.running and t > self.run_until + 0.7:
            self.running, self.run_dir = False, 0       # the message that the motor stopped was lost: do not stay 'running' for ever
        if self.pending is not None and t - self.pending["sent_at"] > CONFIRM_TIMEOUT_S + self.pending.get("ms", 0) / 1000.0:      # the stop message ends the wait, so allow for the move itself
            self.pending["confirmed"], self.pending = False, None
            self._save_log()
            return {"level": "warn", "text": "The board did not confirm the move. Is the sketch running? The motor may not have moved."}
        return None

    def _save_log(self):
        if not self.log_path:
            return
        with open(self.log_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            for r in self.history:
                w.writerow({k: r.get(k) for k in FIELDS})

    # ---- what the page shows
    def snapshot(self):
        t = self.now()
        return {"running": self.running, "run_dir": self.run_dir, "remaining_ms": max(0, int(round((self.run_until - t) * 1000))) if self.running else 0,
                "door": self.door, "next": "close" if self.door == "open" else "open", "settings": dict(self.settings), "heard": self.heard,
                "moves": [{k: v for k, v in r.items() if k != "sent_at"} for r in self.moves], "outcomes": list(OUTCOMES), "csv": "moves.csv"}
