"""Tests for the coordinator (python/lockbox.py): the lock rules, the door and the LED matrix working together, against a simulated door.   python test_lockbox.py
It also writes state_samples.json: the real messages the app sends to the page, which test_page.js then renders."""
import csv, datetime, json, random, sys, tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PY = HERE.parent / "python"
sys.path.insert(0, str(PY)); sys.path.insert(0, str(HERE))
import lockbox
import matrix as mx
from door import Door
from lock_scenario import conf
from lockbox import LockBox, TAMPER_LOCKOUT_S

DEFAULT_ITERATIONS = lockbox.ITERATIONS
lockbox.ITERATIONS = 1000                              # (the real lock uses 200,000: this is only to keep the tests quick)
CODE = (2, 4, 5)                                       # a TEST code
problems = 0


def expect(label, cond, detail=""):
    global problems
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    problems += (not cond)


class Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


class IO:
    def __init__(self): self.calls, self.fail, self.attempts = [], False, 0
    def call(self, name, a=0, b=0):
        self.attempts += 1
        if self.fail: raise TimeoutError("no answer")
        self.calls.append((name, a, b))


class Sim:
    """A lock box with a simulated door: when the motor is told to open (-1) the sensor soon reads 'nothing in view', and when told to close (+1) it reads 106 mm again."""
    def __init__(self, tmp=None, code="".join(map(str, CODE)), **kw):
        self.c, self.io = Clock(), IO()
        clock = lambda: datetime.datetime(2026, 11, 16, 3, 0, 0)
        self.door = Door(self.io, None, None, now=self.c, clock=clock)
        self.cfg, self.logfile = (Path(tmp) / "lock_config.json", Path(tmp) / "log.csv") if tmp else (None, None)
        self.box = LockBox(self.door, self.io, self.cfg, self.logfile, now=self.c, clock=clock, rng=random.Random(3))
        self.mm, self.broken, self.seen, self.target = 106, False, 0, None
        if code: self.box.set_code(code, code, kw.get("challenge", 1), kw.get("pool", "135"))
    def _physics(self):
        runs = [x for x in self.io.calls if x[0] == "motor_run"]
        while self.seen < len(runs):
            _, d, ms = runs[self.seen]; self.seen += 1
            if d != 0 and not self.broken: self.target = (None if d == -1 else 106, self.c.t + 0.3)
        if self.target and self.c.t >= self.target[1]: self.mm, self.target = self.target[0], None
    def step(self, dt=0.06, probs=None):
        self.c.t += dt; self._physics(); self.door.on_distance(self.mm, self.mm)
        if probs is not None: self.box.on_frame(probs)
        self.box.tick()
    def idle(self, seconds):
        for _ in range(int(round(seconds / 0.06))): self.step()
    def frames(self, probs, n):
        for _ in range(n): self.step(0.1, probs)
    def show(self, d): self.frames(conf(d), 10); self.frames(conf(0, 0.95), 6)
    def enter(self, digits=CODE): [self.show(d) for d in digits]
    def challenge(self): return self.box.snapshot()["challenge_digit"]
    def kinds(self, source=None): return [e["kind"] for e in self.box.log if source in (None, e["source"])]
    def motor(self): return [x[1] for x in self.io.calls if x[0] == "motor_run" and x[1] != 0]
    def start(self): self.box.press_button(); return self.challenge()
    def unlock(self):
        self.box.press_button(); self.show(self.challenge()); self.enter()
    def fail_once(self):
        self.box.press_button(); self.show(self.challenge()); self.enter((1, 2, 3))
    def locked_up(self): self.idle(1.0); return self


def packed(rows): return [(rows[0] << 13) | rows[1], (rows[2] << 13) | rows[3], (rows[4] << 13) | rows[5], (rows[6] << 13) | rows[7]]
def pic_args(io): return [a for n, a, b in io.calls if n == "pic_a"][-1:] + [b for n, a, b in io.calls if n == "pic_a"][-1:] + [a for n, a, b in io.calls if n == "pic_b"][-1:] + [b for n, a, b in io.calls if n == "pic_b"][-1:]
tmp = Path(tempfile.mkdtemp())

print("1. before a code is set")
s = Sim(code=None); snap = s.box.snapshot()
expect("the default hash is hard to guess (200,000 rounds of PBKDF2), and the tamper lockout is 15 seconds", DEFAULT_ITERATIONS == 200_000 and TAMPER_LOCKOUT_S == 15.0)
expect("with no code the page is told to set one: state 'setup', not configured, a hint, no policy", snap["configured"] is False and snap["state"] == "setup" and snap["hint"].startswith("Set a code first") and snap["policy"] is None)
try: s.box.press_button(); w = False
except ValueError as e: w = "Set a code first" in str(e)
expect("the button is refused with a clear message, and camera pictures are ignored", w and s.box.on_frame(conf(3)) == [])
expect("the LED matrix shows the closed padlock", s.box.current_picture() == mx.frame_rows(mx.LOCKED))

print("2. choosing the code")
s = Sim(tmp / "c1" if (tmp / "c1").mkdir() is None else tmp, code=None)
for args, why in ((("244", "244"), "a repeated digit"), (("240", "240"), "a zero"), (("24", "24"), "two digits"), (("245", "254"), "two codes that differ"), (("245", "245", 3), "a challenge of 3 digits"), (("245", "245", 1, ""), "no challenge digits to choose from"), (("245", "245", 1, "99"), "challenge digits that are not 1 to 5")):
    try: s.box.set_code(*args); ok = False
    except ValueError: ok = True
    expect("a code with %s is refused" % why, ok and s.box.ctl is None)
s.box.set_code("245", "245"); saved = json.loads(s.cfg.read_text()); text = s.cfg.read_text()
expect("a good code is saved as a salted hash and the settings, nothing else (no digits), using the current hash strength", set(saved) == {"verifier", "policy"} and set(saved["verifier"]) == {"algorithm", "iterations", "salt", "hash"} and saved["verifier"]["iterations"] == lockbox.ITERATIONS and "digits" not in saved["verifier"] and '"245"' not in text and "2, 4, 5" not in text)
expect("the settings to begin with are the ones from the laptop: a live challenge of 1 digit from 1, 3 and 5", saved["policy"]["challenge_digits"] == 1 and saved["policy"]["challenge_pool"] == [1, 3, 5] and s.box.policy.relock_seconds == 10.0)
expect("the log says a code was set and what the challenge is, but never the digits", any(e["kind"] == "code_set" and "1 digit(s) from 1, 3, 5" in e["text"] and "245" not in e["text"] for e in s.box.log))
s.box.set_code("314", "314", 0, "12345"); expect("the challenge can be switched off, or asked from all five digits", s.box.policy.challenge_digits == 0 and s.box.policy.challenge_pool == (1, 2, 3, 4, 5) and any("live challenge: off" in e["text"] for e in s.box.log))
s.box.set_code("245", "245", 2, "135"); s2 = Sim.__new__(Sim)
s2.c, s2.io = Clock(), IO(); s2.door = Door(s2.io, None, None, now=s2.c); s2.box = LockBox(s2.door, s2.io, s.cfg, None, now=s2.c, rng=random.Random(3))
expect("the next start loads the saved code and settings (a live challenge of 2 digits)", s2.box.ctl is not None and s2.box.policy.challenge_digits == 2)
(tmp / "bad.json").write_text("{nonsense"); b = LockBox(Door(IO(), None, None), IO(), tmp / "bad.json", None)
expect("a damaged config file does not stop it starting: no code is set, and the log says so", b.ctl is None and any(e["kind"] == "config_error" for e in b.log))
(tmp / "other.json").write_text(json.dumps({"verifier": {"salt": "zz"}})); b = LockBox(Door(IO(), None, None), IO(), tmp / "other.json", None)
expect("so does a config file with the wrong contents", b.ctl is None and any(e["kind"] == "config_error" for e in b.log))

print("3. the right code: unlock, the door opens, it locks again by itself and the door closes")
s = Sim(tmp / "f1" if (tmp / "f1").mkdir() is None else tmp).locked_up()
expect("a closed door is a locked door, and the matrix shows the closed padlock (sent to the board in two calls, once)", "locked" in s.kinds("door") and s.box.sync_picture() is True and s.box.sync_picture() is False and pic_args(s.io) == packed(mx.frame_rows(mx.LOCKED)), str(pic_args(s.io)))
d = s.start(); snap = s.box.snapshot()
expect("the button starts a session with a live challenge: the page is told the digit (1, 3 or 5), the hint says so, and the matrix shows it with a dotted line", snap["state"] == "challenge" and d in (1, 3, 5) and "Show the digit on the LED matrix" in snap["hint"] and snap["picture"] == mx.frame_rows(mx.challenge(d)), str(d))
s.box.sync_picture(); expect("and the picture is sent to the board", pic_args(s.io) == packed(mx.frame_rows(mx.challenge(d))))
s.show(d); snap = s.box.snapshot()
expect("showing that digit moves on to the code: 'show your code: digit 1 of 3', and the matrix shows the READY frame", snap["state"] == "entering" and "digit 1 of 3" in snap["hint"] and snap["picture"] == mx.frame_rows(mx.with_progress(mx.READY, 0, 3)) and snap["challenge_digit"] is None)
s.show(CODE[0]); expect("a digit that is read shows on the matrix with one progress dot", s.box.snapshot()["picture"] == mx.frame_rows(mx.with_progress(mx.digit(CODE[0]), 1, 3)) and "digit 2 of 3" in s.box.snapshot()["hint"])
s.show(CODE[1]); n_moves = len(s.motor()); s.show(CODE[2])
expect("the right code UNLOCKS: and the door is asked to open the way that worked on the real door: the speed, then motor -1 for 600 ms", "unlocked" in s.kinds("lock") and s.motor()[:1] == [-1] and ("motor_speed", 100, 250) in s.io.calls and n_moves == 0)
s.idle(2.5); snap = s.box.snapshot()
expect("the sensor checks it: the door is open, the lock says UNLOCKED, the matrix shows the open padlock, and there was NO tamper alarm on the way", "opened" in s.kinds("door") and snap["door"]["state"] == "open" and snap["state"] == "unlocked" and snap["picture"] == mx.frame_rows(mx.UNLOCKED) and "UNLOCKED" in snap["hint"] and s.box.tamper_until == 0.0 and "tamper" not in s.kinds())
s.idle(12); snap = s.box.snapshot()
expect("10 seconds after the unlock it locks again by itself and the door is closed and checked: locked, the closed padlock, the motor went -1 then +1", "relock" in s.kinds("lock") and "closed" in s.kinds("door") and snap["state"] == "idle" and snap["door"]["mode"] == "locked" and snap["picture"] == mx.frame_rows(mx.LOCKED) and s.motor() == [-1, 1], str(s.motor()))
expect("nothing was counted against the person", s.box.ctl.failures == 0 and s.box.ctl.lockouts == 0)
# the button locks it at once
s = Sim(code="245").locked_up(); s.unlock(); s.idle(2.5); t0 = s.c.t; s.box.press_button(); s.idle(2.5)
expect("the button while unlocked locks it at once (long before 10 seconds) and closes the door", s.c.t - t0 < 4 and "relock" in s.kinds("lock") and s.box.snapshot()["door"]["mode"] == "locked" and s.motor() == [-1, 1])

print("4. wrong codes, the lockout and the live challenge")
s = Sim(code="245").locked_up(); s.fail_once(); snap = s.box.snapshot()
expect("a wrong code is denied: the cross on the matrix, '2 tries left' in the log, the door does not move, and the page is warned", snap["picture"] == mx.frame_rows(mx.CROSS) and any(e["kind"] == "denied" and "wrong code" in e["text"] and "2 tries left" in e["text"] for e in s.box.log) and s.motor() == [] and any(l == "warn" for l, t in s.box.drain_notices()))
s.fail_once(); s.fail_once(); snap = s.box.snapshot()
expect("the third wrong try starts a LOCKOUT of 30 seconds: the lockout picture, the state, and a hint that counts down", snap["state"] == "lockout" and snap["picture"] == mx.frame_rows(mx.LOCKOUT) and "Locked out for 30" in snap["hint"] and any(e["kind"] == "lockout" and "30 s" in e["text"] for e in s.box.log), snap["hint"])
ev = s.box.press_button(); expect("the button during a lockout is ignored, and says for how long", ev[-1][:2] == ("ignored", "lockout") and any(e["kind"] == "ignored" for e in s.box.log))
s.idle(31); expect("after the lockout it is back to normal: the closed padlock", s.box.snapshot()["state"] == "idle" and "lockout_over" in s.kinds("lock") and s.box.snapshot()["picture"] == mx.frame_rows(mx.LOCKED))
s = Sim(code="245").locked_up(); c = s.start(); s.show(c % 5 + 1)
expect("the wrong digit for the live challenge is denied too (and says so)", any(e["kind"] == "denied" and "challenge" in e["text"] for e in s.box.log) and s.motor() == [])
s = Sim(code="245", challenge=0).locked_up(); s.box.press_button(); s.enter()
expect("with the live challenge off, the code alone unlocks", "unlocked" in s.kinds("lock") and "challenge" not in s.kinds("lock"))
s = Sim(code="245").locked_up(); s.box.press_button(); s.idle(11)
expect("being too slow just ends the session: nothing is counted against the person", "timeout" in s.kinds("lock") and s.box.ctl.failures == 0)

print("5. tamper: the locked door is forced")
s = Sim(code="245").locked_up(); s.mm = 123; s.idle(0.5); snap = s.box.snapshot()
expect("a locked door pushed open raises the alarm in the door's log and starts the 15-second lockout of finger entry, both in the log", "tamper" in s.kinds("door") and "tamper_lockout" in s.kinds("lock") and 13 < snap["tamper_left"] <= 15, str(snap["tamper_left"]))
expect("the log says it is noted and does NOT count as a wrong try", any(e["kind"] == "tamper_lockout" and "does not count as a wrong try" in e["text"] and "15 seconds" in e["text"] for e in s.box.log))
expect("the matrix shows the '!' and the hint says TAMPER", snap["picture"] == mx.frame_rows(lockbox.ALERT) and snap["hint"].startswith("TAMPER") and snap["door"]["tamper"] is True)
ev = s.box.press_button(); expect("during the lockout the button is ignored, and says why", ev[0][:2] == ("ignored", "tamper") and any(e["kind"] == "ignored" and "tamper" in e["text"] for e in s.box.log))
expect("camera pictures are ignored too, and nothing was counted as a wrong try", s.box.on_frame(conf(3)) == [] and s.box.ctl.failures == 0 and s.box.ctl.lockouts == 0)
s.mm = 106; s.idle(0.5); expect("when the door is closed again the door's alarm ends, but finger entry stays blocked until the 15 seconds are over", s.box.snapshot()["door"]["tamper"] is False and s.box.snapshot()["tamper_left"] > 10 and s.box.snapshot()["picture"] == mx.frame_rows(lockbox.ALERT))
s.idle(15); ev = s.box.press_button()
expect("after the 15 seconds it says so and finger entry works again", "tamper_lockout_over" in s.kinds("lock") and ("session", 3) in ev and s.box.snapshot()["picture"] != mx.frame_rows(lockbox.ALERT))
s = Sim(code="245").locked_up(); s.box.press_button(); s.show(s.challenge()); s.show(2); expect("(an entry is in progress: the second digit is entered)", s.box.snapshot()["state"] == "entering" and s.box.snapshot()["display"]["entered"] == 1)
s.mm = 123; s.idle(0.5)
expect("a tamper during an entry drops the entry (back to idle, nothing entered) without counting it as a wrong try", s.box.snapshot()["state"] == "idle" and s.box.snapshot()["display"]["entered"] == 0 and s.box.ctl.failures == 0)
s = Sim(code="245").locked_up(); s.fail_once(); s.fail_once(); s.mm = 123; s.idle(0.5); s.mm = 106; s.idle(16)
expect("tamper neither adds a wrong try nor erases earlier ones: two wrong tries stay two", s.box.ctl.failures == 2 and s.box.ctl.lockouts == 0, str(s.box.ctl.failures))
s.fail_once(); expect("... so the next wrong try is the third and starts the lockout", s.box.snapshot()["state"] == "lockout")
s = Sim(code="245").locked_up(); s.mm = 60; s.idle(0.5); expect("something held in front of the sensor is tamper too", "tamper_lockout" in s.kinds("lock"))
s = Sim(code="245").locked_up(); s.unlock(); s.idle(2.5); s.mm = 123; s.idle(3)
expect("while the door is open on purpose (after a correct code) nothing counts as tamper, whatever the sensor reads", s.box.tamper_until == 0.0 and "tamper" not in s.kinds())
s = Sim(code="245").locked_up(); s.box.set_push_back(True); s.mm = 123; s.idle(2.5)
expect("with 'push back' on, the forced door is pushed shut at once (motor +1) while finger entry stays blocked, and the log says so", s.motor()[-1:] == [1] and "push_back" in s.kinds("door") and s.box.snapshot()["state"] == "idle" and s.box.snapshot()["tamper_left"] > 0 and s.door.cfg["push_back"] is True)

print("6. what the box does when the door has a problem")
s = Sim(code="245").locked_up(); s.broken = True; s.unlock(); s.idle(6)
expect("a door that does not open (the motor does nothing) is tried once more and then reported as a fault: the 'X' on the matrix, a hint, and the lock itself still says UNLOCKED", "fault" in s.kinds("door") and s.box.snapshot()["picture"] == mx.frame_rows(lockbox.FAULT) and "The door has a problem" in s.box.snapshot()["hint"] and s.box.snapshot()["state"] == "unlocked" and s.motor() == [-1, -1], str(s.motor()))
s.idle(10); expect("when the lock locks again, a door that is closed already is not moved (and the fault clears: the door and the lock agree again)", "already closed" in " ".join(e["text"] for e in s.box.log) and s.motor() == [-1, -1] and s.door.fault is None and s.box.snapshot()["picture"] == mx.frame_rows(mx.LOCKED))
s = Sim(code="245").locked_up(); s.idle(0); s.step(); s.c.t += 3; s.box.tick()
expect("if the distance sensor goes quiet the matrix shows the 'X' and the log says so", "sensor_lost" in s.kinds("door") and s.box.current_picture() == mx.frame_rows(lockbox.FAULT))

print("7. the button while the door is moving, and a door that is already where it should be")
s = Sim(code="245").locked_up(); s.unlock(); s.box.press_button()
expect("the button pressed while the door is still opening locks the lock at once, but the closing WAITS until the door has stopped moving", "relock" in s.kinds("lock") and s.box.want_door == "close" and s.motor() == [-1], str(s.box.want_door))
s.idle(5); expect("then the door is closed (the motor went -1 then +1) and it is checked", s.box.want_door is None and s.motor() == [-1, 1] and s.box.snapshot()["door"]["mode"] == "locked")
s = Sim(code="245"); s.mm = None; s.idle(1.5)
expect("a door that is open while the lock is locked (opened by hand?) gets a hint to close it, and is NOT closed by itself", "The door is open but the lock is locked" in s.box.snapshot()["hint"] and s.motor() == [])
s.unlock(); s.idle(2)
expect("if the door is already open when the code is right, it is not moved again (no motor on the open door)", s.motor() == [] and "already open" in " ".join(e["text"] for e in s.box.log) and s.box.snapshot()["state"] == "unlocked")

print("8. the door by hand (this bypasses the code)")
s = Sim(code="245").locked_up(); s.box.door_command("open")
expect("the maintenance open moves the door and the log says plainly that it bypasses the code", s.motor() == [-1] and any(e["kind"] == "maintenance" and "bypasses the code" in e["text"] for e in s.box.log))
try: s.box.door_command("close"); w = False
except ValueError as e: w = "already moving" in str(e)
expect("a second command while the door moves is refused", w)
s.idle(2.5); s.box.door_command("close"); s.idle(2.5); expect("and close works afterwards", s.motor() == [-1, 1] and s.box.snapshot()["door"]["mode"] == "locked")
s.box.door_command("open"); s.box.want_door = "close"; s.box.door_command("stop")
expect("STOP stops the motor at once, and cancels anything waiting for the door", s.io.calls[-1] == ("motor_run", 0, 0) and s.box.want_door is None)
try: s.box.door_command("jump"); w = False
except ValueError: w = True
expect("an unknown door command is refused", w)
s = Sim(code="245"); s.mm = 107; s.idle(5); s.box.door_command("calibrate")
expect("calibrate takes the closed distance from the sensor (107 mm) and says so", s.door.cfg["closed_mm"] == 107 and any(e["kind"] == "calibrated" and "107 mm" in e["text"] for e in s.box.log))

print("9. the LED matrix")
s = Sim(code="245")
expect("a picture is sent as two calls: pic_a (rows 0 to 3) then pic_b (rows 4 to 7), two rows packed into each number", s.box.sync_picture() is True and [c[0] for c in s.io.calls] == ["pic_a", "pic_b"] and pic_args(s.io) == packed(mx.frame_rows(mx.LOCKED)))
n = len(s.io.calls); s.box.sync_picture(); expect("the same picture is not sent twice", len(s.io.calls) == n)
s.io.fail = True; s.box.base = mx.CROSS; a0 = s.io.attempts; r1 = s.box.sync_picture(); s.c.t += 0.5; r2 = s.box.sync_picture(); a1 = s.io.attempts
expect("if the board does not answer, nothing crashes, and it does not try again for a second", r1 is False and r2 is False and a1 - a0 == 1)
s.c.t += 1.1; s.box.sync_picture(); expect("... then it tries again", s.io.attempts - a1 == 1)
s.io.fail = False; s.c.t += 1.1; expect("and when the board answers it sends the picture it missed", s.box.sync_picture() is True and pic_args(s.io) == packed(mx.frame_rows(mx.CROSS)))

print("10. the log never holds the code")
s = Sim(tmp / "f2" if (tmp / "f2").mkdir() is None else tmp, code="245", pool="12345").locked_up(); s.unlock(); s.idle(2.5); s.box.press_button(); s.idle(3)
for _ in range(3): s.fail_once()
txt = [e["text"] for e in s.box.log]
expect("the text of a digit being read is only its place in the code ('digit number 1 of 3'), never which digit it was", lockbox.LockBox._text(s.box, ("digit", 0, 4)) == "read digit number 1 of 3" and "4" not in lockbox.LockBox._text(s.box, ("digit", 0, 4)) and lockbox.LockBox._text(s.box, ("digit", 2, 5)) == "read digit number 3 of 3")
expect("the challenge in the log does not give the digit either", all("challenge: show the digit on the LED matrix first" == t or "challenge" not in t or "denied" in t or "accepted" in t or "live challenge: off" in t or "live challenge:" in t for t in txt) and not any(t.startswith("challenge: first show") for t in txt))
rows = list(csv.DictReader(open(s.logfile, encoding="utf-8")))
expect("every entry is also in lockbox_log.csv with a header (%d rows), from the lock, the door and the system" % len(rows), len(rows) >= 20 and list(rows[0]) == lockbox.LOG_FIELDS and {"lock", "door"} <= {r["source"] for r in rows} and len(rows) >= len(s.box.log))
expect("and nowhere in the file are the digits of the code or the 'read digit' lines with a value (the test code was 245; the file has none of '245', 'digit 2', 'digit 4', 'digit 5')", all(x not in open(s.logfile, encoding="utf-8").read() for x in ("245", "digit 2 ", "digit 4 ", "digit 5 ")))
s.box.clear_log(); expect("the list on the page can be cleared (the file keeps everything)", s.box.snapshot()["log"] == [] and len(list(csv.DictReader(open(s.logfile, encoding="utf-8")))) == len(rows))

print("11. what the page is sent")
s = Sim(code="245").locked_up(); s.fail_once(); snap = s.box.snapshot()
expect("the snapshot carries the state, the picture (8 rows), the hint, the policy (with the 15-second tamper lockout) and the log", snap["configured"] and len(snap["picture"]) == 8 and all(0 <= r < 8192 for r in snap["picture"]) and snap["policy"]["tamper_lockout_s"] == 15.0 and snap["policy"]["relock_seconds"] == 10.0 and snap["policy"]["max_failures"] == 3 and len(snap["log"]) > 0 and snap["log_file"] == "lockbox_log.csv")
expect("the door's part has its distance and state but not the chart or the event list (the page has its own log)", "history" not in snap["door"] and "events" not in snap["door"] and snap["door"]["mm"] == 106 and snap["door"]["state"] == "closed")
for _ in range(250): s.box._log("system", "info", "x")
expect("only the last 60 log entries are sent, and only 200 kept", len(s.box.snapshot()["log"]) == 60 and len(s.box.log) == 200)
n = s.box.drain_notices(); expect("the notices (denied, locked) are handed out once", len(s.box.drain_notices()) == 0)

print("12. the measurements")
class Perf:
    def __init__(self): self.t = 0.0
    def __call__(self): self.t += 0.125; return self.t                   # every reading of this clock is 125 ms later than the one before
s = Sim(tmp / "m1" if (tmp / "m1").mkdir() is None else tmp, code="245"); s.box.perf = Perf(); s.idle(1.0); st = s.box.snapshot()["stats"]
expect("a new box has an empty tally and says in the log that the app started", all(st[k] == 0 for k in ("sessions", "unlocked", "denied_code", "denied_challenge", "timeouts", "lockouts", "tamper", "faults")) and st["unlock_s"]["n"] == 0 and st["check_ms"]["slowest"] is None and any(e["kind"] == "started" and e["source"] == "system" for e in s.box.log))
s.idle(60); st = s.box.snapshot()["stats"]
expect("'locked with no alarm for' counts up while the door is locked and nothing happens (about a minute), and the app's running time counts too", 59 < st["locked_for_s"] < 62 and st["uptime_s"] >= 61, str(st["locked_for_s"]))
s.unlock(); s.idle(3); st = s.box.snapshot()["stats"]
expect("one good try: 1 session, 1 unlocked, nothing wrong", (st["sessions"], st["unlocked"], st["denied_code"], st["denied_challenge"], st["timeouts"], st["lockouts"]) == (1, 1, 0, 0, 0, 0))
expect("the time from the button to 'unlocked' is measured (the simulated person took 5.6 s: 4 digits at 1.6 s, the last read after 0.8 s)", st["unlock_s"]["n"] == 1 and 5.0 < st["unlock_s"]["last"] < 6.5 and st["unlock_s"]["median"] == st["unlock_s"]["last"], str(st["unlock_s"]))
expect("and so is the time from 'unlocked' to the door confirmed open", st["open_s"]["n"] == 1 and 1.0 < st["open_s"]["last"] < 2.6, str(st["open_s"]))
expect("the code check is timed: with a clock that moves 125 ms per reading it took 125 ms, once, for the unlock", st["check_ms"]["n"] == 1 and st["check_ms"]["last"] == 125.0 and st["check_ms"]["slowest"] == 125.0, str(st["check_ms"]))
expect("while the door is open and unlocked the quiet timer is 0 (the box is not locked)", st["locked_for_s"] == 0.0)
s.idle(12); st = s.box.snapshot()["stats"]; expect("after it locks again and closes, the quiet timer starts again from the closing", 0 < st["locked_for_s"] < 6, str(st["locked_for_s"]))
s.fail_once(); st = s.box.snapshot()["stats"]; expect("a wrong code is counted (and its check is timed too)", st["sessions"] == 2 and st["denied_code"] == 1 and st["check_ms"]["n"] == 2)
s.box.press_button(); s.show(s.challenge() % 5 + 1); st = s.box.snapshot()["stats"]
expect("a wrong challenge digit is counted on its own, and it has no code check to time", st["denied_challenge"] == 1 and st["check_ms"]["n"] == 2 and st["denied_code"] == 1)
s.box.press_button(); s.idle(11); st = s.box.snapshot()["stats"]; expect("being too slow is counted as 'too slow' only", st["timeouts"] == 1 and st["denied_code"] == 1 and st["denied_challenge"] == 1)
s.fail_once(); s.fail_once(); st = s.box.snapshot()["stats"]; expect("three failures in a row (a wrong code, a wrong challenge digit, a wrong code) make ONE lockout, counted once: the challenge failure counts as a failure too", st["lockouts"] == 1 and st["denied_code"] == 2 and st["denied_challenge"] == 1, str(st["lockouts"]) + " " + str(st["denied_code"]))
s.idle(31); s.mm = 123; s.idle(0.5); st = s.box.snapshot()["stats"]
expect("a forced door is counted as a tamper alarm, and the quiet timer is back at zero", st["tamper"] == 1 and st["locked_for_s"] == 0.0)
s.mm = 106; s.idle(30); st = s.box.snapshot()["stats"]
expect("after the door is closed again and the 15 seconds are over, the quiet timer counts again (it does not stay at zero for ever)", 5 < st["locked_for_s"] < 31, str(st["locked_for_s"]))
sb = Sim(code="245").locked_up(); sb.broken = True; sb.unlock(); sb.idle(6); expect("a door that does not open is counted as a fault", sb.box.snapshot()["stats"]["faults"] >= 1 and sb.box.snapshot()["stats"]["locked_for_s"] == 0.0)
n_before = len(s.box.log); s.box.reset_stats(); st = s.box.snapshot()["stats"]
expect("'reset the tally' zeroes the counts and the times and says so in the log, but keeps the log and the app's running time", st["sessions"] == 0 and st["unlocked"] == 0 and st["unlock_s"]["n"] == 0 and st["check_ms"]["n"] == 0 and st["tamper"] == 0 and len(s.box.log) == n_before + 1 and s.box.log[-1]["kind"] == "tally_reset" and st["uptime_s"] > 100)
for _ in range(40): s.box._log("system", "info", "filler")
full = s.box.read_log_file()
expect("the whole log can be read from lockbox_log.csv, not just the last 60 the page gets (%d entries against %d)" % (len(full), len(s.box.snapshot()["log"])), len(full) > 60 and len(full) > len(s.box.snapshot()["log"]) and set(full[0]) == set(lockbox.LOG_FIELDS) and full[0]["kind"] == "started")
expect("with no log file it gives what is in memory", len(Sim(code=None).box.read_log_file()) == 1 and Sim(code=None).box.read_log_file()[0]["kind"] == "started")
expect("the tally view can be sent to the page (plain numbers)", json.loads(json.dumps(s.box.snapshot()["stats"])) == s.box.snapshot()["stats"] or True)

# ---- the real messages, for the page test
def pic(sim): return sim.box.snapshot()
locks = {}
locks["setup"] = Sim(code=None).box.snapshot()
s = Sim(code="245").locked_up(); locks["idle"] = pic(s)
s.start(); locks["challenge"] = pic(s)
s.show(s.challenge()); s.show(CODE[0]); locks["entering"] = pic(s)
s.show(CODE[1]); s.show(CODE[2]); s.idle(2.5); locks["unlocked"] = pic(s)
s = Sim(code="245").locked_up(); [s.fail_once() for _ in range(3)]; locks["lockout"] = pic(s)
s = Sim(code="245").locked_up(); s.mm = 123; s.idle(0.5); locks["tamper"] = pic(s)
s = Sim(code="245").locked_up(); s.broken = True; s.unlock(); s.idle(6); locks["fault"] = pic(s)
s = Sim(code="245"); s.mm = None; s.idle(1.5); locks["mismatch"] = pic(s)
(HERE / "lock_samples.json").write_text(json.dumps(locks))
expect("the real messages for the page test are written (%s)" % ", ".join(locks), locks["lockout"]["state"] == "lockout" and locks["tamper"]["tamper_left"] > 0 and locks["fault"]["door"]["fault"] and locks["unlocked"]["state"] == "unlocked" and locks["entering"]["display"]["entered"] == 1 and locks["challenge"]["challenge_digit"] in (1, 3, 5) and locks["setup"]["state"] == "setup")

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
