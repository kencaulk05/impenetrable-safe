"""Tests for the motor test's Python side (python/motortest.py and python/main.py).   python test_motortest.py
It also writes state_samples.json: the real payloads main.py sends to the page, which test_page.js then renders."""
import csv, datetime, importlib.util, json, sys, tempfile, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = HERE.parent / "python"
sys.path.insert(0, str(PY))
from motortest import DEFAULTS, MotorTest, OUTCOMES, clean_settings

problems = 0


def expect(label, cond, detail=""):
    global problems
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    problems += (not cond)


class Clock:
    def __init__(self): self.t = 500.0
    def __call__(self): return self.t


class IO:
    def __init__(self): self.calls = []
    def call(self, name, a=0, b=0): self.calls.append((name, a, b))


def make(tmp=None, **kw):
    c, io = Clock(), IO()
    m = MotorTest(io, (Path(tmp) / "s.json") if tmp else None, (Path(tmp) / "moves.csv") if tmp else None, now=c, clock=lambda: datetime.datetime(2026, 11, 15, 22, 40, 1), **kw)
    return c, io, m


tmp = Path(tempfile.mkdtemp())
print("1. the settings")
expect("the defaults are speed 150, a 250 ms soft start, 600 ms to open and 600 to close, direction +1", DEFAULTS == {"pwm": 150, "ramp_ms": 250, "open_ms": 600, "close_ms": 600, "open_dir": 1})
s = clean_settings({"pwm": 5, "ramp_ms": 9999, "open_ms": "700", "close_ms": 1, "open_dir": -3, "bogus": 1})
expect("every number is kept in a safe range (speed 5 becomes 60, ramp 9999 becomes 1000, '700' is 700, 1 ms becomes 50, direction -3 becomes -1) and unknown keys are ignored", s == {"pwm": 60, "ramp_ms": 1000, "open_ms": 700, "close_ms": 50, "open_dir": -1})
expect("the highest values are allowed but no higher (speed 999 becomes 255, 99999 ms becomes 3000)", clean_settings({"pwm": 999, "open_ms": 99999})["pwm"] == 255 and clean_settings({"pwm": 999, "open_ms": 99999})["open_ms"] == 3000)
bad = []
for k in ("pwm", "open_ms", "ramp_ms", "close_ms", "open_dir"):
    try: clean_settings({k: "fast"}); bad.append(k)
    except ValueError: pass
expect("a setting that is not a number is refused with a clear message", not bad, str(bad))
c, io, m = make(tmp)
m.update_settings({"pwm": 200, "open_ms": 450})
c2, io2, m2 = make(tmp)
expect("the settings are remembered after a restart (speed 200, 450 ms)", m2.settings["pwm"] == 200 and m2.settings["open_ms"] == 450 and m2.settings["close_ms"] == 600)
(tmp / "s.json").write_text("not json at all")
expect("a damaged settings file does not stop it starting: the defaults are used", make(tmp)[2].settings == DEFAULTS)

print("2. the moves")
c, io, m = make()
expect("the door is believed closed and the next move is 'open'", m.snapshot()["door"] == "closed" and m.snapshot()["next"] == "open" and not m.snapshot()["running"])
r = m.move("next")
expect("the first 'next' opens: the speed is set, then motor_run(+1, 600); the door is believed open and the next move is 'close'", io.calls == [("motor_speed", 150, 250), ("motor_run", 1, 600)] and r["action"] == "open" and m.snapshot()["door"] == "open" and m.snapshot()["next"] == "close")
m.on_motor(1, 600); c.t += 1; m.on_motor(0, 0)
r = m.move("next")
expect("the second 'next' closes: motor_run(-1, 600)", io.calls[-1] == ("motor_run", -1, 600) and r["action"] == "close" and m.snapshot()["door"] == "closed")
m.on_motor(0, 0)
r = m.move("open", {"open_ms": 800, "close_ms": 300, "pwm": 120, "ramp_ms": 100})
expect("'open' always opens whatever the belief, with the new settings sent along: motor_speed(120, 100), motor_run(+1, 800)", io.calls[-2:] == [("motor_speed", 120, 100), ("motor_run", 1, 800)] and r["ms"] == 800)
m.on_motor(0, 0); r = m.move("close")
expect("'close' uses the close time (300 ms) and the other direction", io.calls[-1] == ("motor_run", -1, 300))
m.on_motor(0, 0); m.move("open", {"open_dir": -1})
expect("with the direction flipped (open_dir -1) 'open' drives -1 and 'close' drives +1", io.calls[-1][1] == -1); m.on_motor(0, 0); m.move("close"); expect("... 'close' drives +1", io.calls[-1][1] == 1)
m.on_motor(0, 0); m.set_door("open")
expect("the person can correct the belief: after 'the door is open', the next move closes", m.snapshot()["next"] == "close")
try: m.set_door("ajar"); w = False
except ValueError: w = True
expect("any other door state is refused", w)
try: m.move("sideways"); w = False
except ValueError as e: w = "Unknown move" in str(e)
expect("an unknown kind of move is refused", w)

print("3. safety: running, stopping")
c, io, m = make(); m.move("open"); m.on_motor(1, 600)
expect("once the board says the motor runs, the page is told how long is left (600 ms)", m.snapshot()["running"] and m.snapshot()["run_dir"] == 1 and m.snapshot()["remaining_ms"] == 600)
c.t += 0.25; expect("... and the time left counts down (350 ms after 0.25 s)", m.snapshot()["remaining_ms"] == 350)
n = len(io.calls)
try: m.move("next"); refused = False
except ValueError as e: refused = "STOP" in str(e)
expect("a new move while the motor runs is REFUSED (and nothing is sent to the board)", refused and len(io.calls) == n)
m.stop()
expect("STOP is always allowed: motor_run(0, 0) is sent and the state is 'not running'", io.calls[-1] == ("motor_run", 0, 0) and not m.snapshot()["running"])
n = len(io.calls); m.stop(); expect("STOP when nothing is running is harmless", io.calls[-1] == ("motor_run", 0, 0) and not m.snapshot()["running"])
m.on_motor(0, 0); m.move("close"); expect("after the stop a new move is allowed again", io.calls[-1][0] == "motor_run" and io.calls[-1][1] == -1)
c, io, m = make(); m.move("open"); m.on_motor(1, 600); c.t += 0.5; m.tick(); still = m.snapshot()["running"]; c.t += 1.0; m.tick()
expect("if the message that the motor stopped is lost, it does not stay 'running' for ever: it clears 0.7 s after the move should have ended", still and not m.snapshot()["running"])
c, io, m = make(); m.move("open"); c.t += 1.0
expect("a move that the board has not yet confirmed after 1 s is still given time (no warning yet)", m.tick() is None and m.moves[0]["confirmed"] is None)
c.t += 0.6
expect("... and after 1.6 s too: a 600 ms move is given its own time plus 1.5 s (2.1 s) before a warning", m.tick() is None and m.moves[0]["confirmed"] is None)
c.t += 0.6
note = m.tick()
expect("a move the board never confirms gives a warning 1.5 s after it should have ended, and the row says 'not confirmed'", note is not None and note["level"] == "warn" and "did not confirm" in note["text"] and m.moves[0]["confirmed"] is False, str(note))
expect("... but only once", m.tick() is None)
c, io, m = make(); m.move("open"); c.t += 0.2; m.on_motor(1, 600); c.t += 2; n2 = m.tick()
expect("a move the board confirms in time gives no warning, and the row says 'confirmed'", n2 is None and m.moves[0]["confirmed"] is True)
expect("the page can tell whether the board has ever answered", make()[2].snapshot()["heard"] is False and m.snapshot()["heard"] is True)
class Broken:
    def call(self, *a): raise TimeoutError("no answer")
mb = MotorTest(Broken(), now=Clock())
try: mb.move("open"); w = False
except TimeoutError: w = True
expect("if the board does not answer a call, the move fails loudly, no row is added to the table, and nothing is left waiting for a confirmation", w and mb.moves == [] and mb.history == [] and mb.pending is None and mb.snapshot()["door"] == "closed")
class RacyIO(IO):                                    # the board's "motor started" message arrives WHILE the call that started the motor is still running (it did, on the real board)
    m = None
    def call(self, name, a=0, b=0):
        super().call(name, a, b)
        if name == "motor_run" and a != 0 and self.m: self.m.on_motor(a, b)
c = Clock(); rio = RacyIO(); mr = MotorTest(rio, now=c, clock=lambda: datetime.datetime(2026, 11, 15, 22, 40, 1)); rio.m = mr
r = mr.move("open"); ok_now = r["confirmed"] is True; c.t += 5
expect("REGRESSION: when the board's 'started' message arrives before the call returns, the move is still confirmed, and no warning follows", ok_now and mr.tick() is None and mr.moves[0]["confirmed"] is True and mr.pending is None)
c, io, m = make(); m.move("open"); c.t += 0.7; m.on_motor(0, 0); c.t += 3
expect("if only the 'stopped' message arrives (the start message was lost), the move still counts as confirmed: only a motor that ran can stop", m.moves[0]["confirmed"] is True and m.tick() is None)
c, io, m = make(); m.on_motor(0, 0)
expect("a stray 'stopped' message with no move waiting changes nothing", m.pending is None and m.moves == [] and m.snapshot()["heard"] is True)

print("4. rating the moves and the log")
c, io, m = make(tmp / "log" if (tmp / "log").mkdir() is None else tmp)
m.move("open"); m.on_motor(1, 600); m.on_motor(0, 0); m.move("close"); m.on_motor(1, 600); m.on_motor(0, 0)
m.rate(1, "reached the end"); m.rate(2, "stopped short")
expect("a move can be rated with one of the four outcomes", [r["outcome"] for r in m.moves] == ["reached the end", "stopped short"] and len(OUTCOMES) == 4)
for bad_args in ((1, "great"), (99, "reached the end")):
    try: m.rate(*bad_args); w = False
    except ValueError: w = True
    expect("rating %r is refused" % (bad_args,), w)
m.rate(1, ""); expect("a rating can be taken back (empty)", m.moves[0]["outcome"] == "")
m.rate(1, "went too far")
rows = list(csv.DictReader(open(tmp / "log" / "moves.csv", encoding="utf-8")))
expect("every move is in moves.csv with its settings and its rating (%d rows)" % len(rows), len(rows) == 2 and rows[0]["action"] == "open" and rows[0]["dir"] == "1" and rows[0]["ms"] == "600" and rows[0]["pwm"] == "150" and rows[0]["outcome"] == "went too far" and rows[1]["outcome"] == "stopped short" and rows[0]["confirmed"] == "True")
expect("the ids count up from 1", [r["id"] for r in rows] == ["1", "2"])
m.clear()
expect("clearing the table empties it, but moves.csv keeps everything, and a move can still be rated afterwards", m.snapshot()["moves"] == [] and len(list(csv.DictReader(open(tmp / "log" / "moves.csv", encoding="utf-8")))) == 2 and (m.rate(2, "reached the end") or True))
expect("the snapshot never carries the internal clock value", all("sent_at" not in r for r in m.snapshot()["moves"]))

print("5. main.py is wired to the board and the page")
log = {"provided": {}, "calls": [], "loop": None, "handlers": {}, "messages": [], "fail": False}
class Bridge:
    @staticmethod
    def provide(name, fn): log["provided"][name] = fn
    @staticmethod
    def call(name, *args, timeout=10):
        if log["fail"]: raise TimeoutError("no answer")
        log["calls"].append((name,) + args)
class App:
    @staticmethod
    def run(user_loop=None): log["loop"] = user_loop
class WebUI:
    def on_message(self, kind, fn): log["handlers"][kind] = fn
    def on_connect(self, fn): log["handlers"]["connect"] = fn
    def send_message(self, kind, msg, room=None): log["messages"].append((kind, msg))
u = types.ModuleType("arduino.app_utils"); u.Bridge, u.App = Bridge, App
w = types.ModuleType("arduino.app_bricks.web_ui"); w.WebUI = WebUI
sys.modules.update({"arduino": types.ModuleType("arduino"), "arduino.app_utils": u, "arduino.app_bricks": types.ModuleType("arduino.app_bricks"), "arduino.app_bricks.web_ui": w})
import time as _time
real_sleep = _time.sleep; _time.sleep = lambda s: None
spec = importlib.util.spec_from_file_location("motor_main", PY / "main.py"); main = importlib.util.module_from_spec(spec); spec.loader.exec_module(main)
main.test.settings_path = tmp / "main_s.json"; main.test.log_path = tmp / "main_moves.csv"; main.test.settings = dict(DEFAULTS)
cmd = lambda d: log["handlers"]["cmd"]("sid", d)
last = lambda kind: [m for k, m in log["messages"] if k == kind][-1]
expect("main.py gets the 'motor' messages, listens for page commands, and hands its loop to the app", "motor" in log["provided"] and "cmd" in log["handlers"] and "connect" in log["handlers"] and callable(log["loop"]))
log["handlers"]["connect"]("sid"); expect("a page that connects is sent the state at once (door closed, not running)", log["messages"][-1][0] == "state" and log["messages"][-1][1]["door"] == "closed" and not log["messages"][-1][1]["running"])
cmd({"action": "next", "settings": {"pwm": 140, "ramp_ms": 200, "open_ms": 500, "close_ms": 400, "open_dir": 1}})
expect("'next' sends the speed and then the move to the board, tells the page what is happening, and the state shows the new door belief", log["calls"][-2:] == [("motor_speed", 140, 200), ("motor_run", 1, 500)] and "Opening" in last("notice")["text"] and last("state")["door"] == "open")
log["provided"]["motor"](1, 500)
cmd({"action": "next"}); expect("'next' while the motor runs gives a warning, not a crash, and sends nothing", last("notice")["level"] == "warn" and "STOP" in last("notice")["text"] and log["calls"][-1] == ("motor_run", 1, 500))
cmd({"action": "stop"}); expect("'stop' sends motor_run(0, 0) at once and says so", log["calls"][-1] == ("motor_run", 0, 0) and last("notice")["text"] == "Stopped." and not last("state")["running"])
log["provided"]["motor"](0, 0); cmd({"action": "next"}); expect("'next' again closes (the other way, 400 ms) and the message says Closing", log["calls"][-1] == ("motor_run", -1, 400) and "Closing" in last("notice")["text"])
log["provided"]["motor"](0, 0); cmd({"action": "move", "which": "open"}); expect("'move' with 'open' opens", log["calls"][-1] == ("motor_run", 1, 500)); log["provided"]["motor"](0, 0)
cmd({"action": "set_door", "door": "closed"}); expect("'set_door' corrects the belief", last("state")["door"] == "closed")
cmd({"action": "set_door", "door": "sideways"}); expect("a bad door state is a warning", last("notice")["level"] == "warn")
cmd({"action": "rate", "id": 1, "outcome": "reached the end"}); expect("'rate' records the outcome in the table", last("state")["moves"][0]["outcome"] == "reached the end")
cmd({"action": "rate", "id": 1, "outcome": "wow"}); expect("a bad outcome is a warning", last("notice")["level"] == "warn")
cmd({"action": "move", "which": "sideways"}); expect("a bad move is a warning", last("notice")["level"] == "warn")
cmd({"action": "next", "settings": {"pwm": "fast"}}); expect("a settings value that is not a number is a warning, and nothing is sent", last("notice")["level"] == "warn" and "must be a number" in last("notice")["text"])
cmd({"action": "dance"}); expect("an unknown command is a warning", last("notice")["level"] == "warn" and "Unknown" in last("notice")["text"])
cmd(None); expect("a command with no data does not crash it", last("notice")["level"] == "warn")
log["fail"] = True; log["provided"]["motor"](0, 0); cmd({"action": "next"}); expect("if the board does not answer, the page gets a clear warning and the app carries on", last("notice")["level"] == "warn" and "went wrong" in last("notice")["text"]); log["fail"] = False
cmd({"action": "clear"}); expect("'clear' empties the table", last("state")["moves"] == [])
cmd({"action": "refresh"}); expect("'refresh' sends the state", log["messages"][-1][0] == "state")
log["loop"](); expect("the loop sends the state to the page", log["messages"][-1][0] == "state")
main.test.pending = {"sent_at": main.test.now() - 5, "confirmed": None}; log["loop"]()
expect("when a move is never confirmed, the loop tells the page", last("notice")["level"] == "warn" and "did not confirm" in last("notice")["text"])
_time.sleep = real_sleep

# the real payloads, for the page test
c, io, m = make(); idle = m.snapshot()
c, io, m = make(); m.move("open"); m.on_motor(1, 600); c.t += 0.2; running = m.snapshot()
c, io, m = make(); m.move("open"); m.on_motor(1, 600); m.on_motor(0, 0); m.move("close"); m.on_motor(1, 600); m.on_motor(0, 0); m.rate(1, "reached the end"); m.rate(2, "grinding or jammed"); m.set_door("closed"); with_moves = m.snapshot()
c, io, m = make(); m.move("open"); c.t += 5; m.tick(); unconfirmed = m.snapshot()
(HERE / "state_samples.json").write_text(json.dumps({"idle": idle, "running": running, "with_moves": with_moves, "unconfirmed": unconfirmed}))
expect("the real payloads for the page test are written (%d moves in the last two)" % len(with_moves["moves"]), len(with_moves["moves"]) == 2 and unconfirmed["moves"][0]["confirmed"] is False and running["running"] and running["remaining_ms"] == 400)

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
