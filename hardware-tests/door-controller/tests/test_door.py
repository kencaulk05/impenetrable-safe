"""Tests for the door controller's Python side (python/door.py and python/main.py).   python test_door.py
It also writes state_samples.json: the real payloads main.py sends to the page, which test_page.js then renders."""
import csv, datetime, importlib.util, json, sys, tempfile, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = HERE.parent / "python"
sys.path.insert(0, str(PY))
from door import DEFAULTS, Door, band, clean_settings

problems = 0


def expect(label, cond, detail=""):
    global problems
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    problems += (not cond)


CLOSED = 106                                  # where the motor closes the door (5 closes out of 5 on the real door)


class Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


class IO:
    def __init__(self): self.calls = []
    def call(self, name, a=0, b=0): self.calls.append((name, a, b))


def make(tmp=None, **cfg):
    c, io = Clock(), IO()
    d = Door(io, (Path(tmp) / "cfg.json") if tmp else None, (Path(tmp) / "log.csv") if tmp else None, now=c, clock=lambda: datetime.datetime(2026, 11, 15, 23, 50, 7))
    if cfg: d.update_settings(cfg)
    return c, io, d


def feed(c, d, mm, n, dt=0.06):
    evs = []
    for _ in range(n):
        c.t += dt; d.on_distance(mm, mm); evs += d.tick()
    return evs


kinds = lambda evs: [e["kind"] for e in evs]
tmp = Path(tempfile.mkdtemp())

print("1. the settings")
expect("the defaults are the values measured and verified on the real door: direction -1, 600 ms each way at speed 100, soft start 250, closed 106 mm (where the motor closes it) plus or minus 10, open beyond 250 mm", DEFAULTS == {"open_dir": -1, "open_ms": 600, "close_ms": 600, "pwm": 100, "ramp_ms": 250, "closed_mm": 106, "closed_tol_mm": 10, "open_mm": 250, "debounce": 5, "push_back": False})
s = clean_settings({"pwm": 5, "ramp_ms": 9999, "open_ms": "700", "close_ms": 1, "open_dir": 3, "debounce": 99, "closed_tol_mm": 1, "push_back": 1, "bogus": 1})
expect("every number is kept in a safe range (speed 5 becomes 60, ramp 9999 becomes 1000, '700' is 700, 1 ms becomes 50, debounce 99 becomes 20, tolerance 1 becomes 5), the direction is +1 or -1, unknown keys are ignored", s["pwm"] == 60 and s["ramp_ms"] == 1000 and s["open_ms"] == 700 and s["close_ms"] == 50 and s["debounce"] == 20 and s["closed_tol_mm"] == 5 and s["open_dir"] == 1 and s["push_back"] is True and "bogus" not in s)
bad = []
for k in ("pwm", "open_ms", "closed_mm", "open_mm", "debounce", "open_dir"):
    try: clean_settings({k: "fast"}); bad.append(k)
    except ValueError: pass
expect("a setting that is not a number is refused with a clear message", not bad, str(bad))
for new in ({"open_mm": 100}, {"closed_mm": 300}):
    try: clean_settings(new); w = False
    except ValueError as e: w = "at least 20 mm beyond" in str(e)
    expect("an 'open' distance that is not beyond the closed band is refused: %s" % new, w)
c, io, d = make(tmp); d.update_settings({"pwm": 140, "closed_mm": 101})
d2 = Door(IO(), tmp / "cfg.json")
expect("the settings are remembered after a restart (speed 140, closed 101 mm)", d2.cfg["pwm"] == 140 and d2.cfg["closed_mm"] == 101 and d2.cfg["open_dir"] == -1)
(tmp / "cfg.json").write_text("{nonsense"); expect("a damaged settings file does not stop it starting: the defaults are used", Door(IO(), tmp / "cfg.json").cfg == DEFAULTS)

print("2. the bands, with the distances measured on the real door")
b = lambda mm: band(mm, DEFAULTS)
expect("closed: 106 (where the motor closes the door, 5 out of 5), 104 to 108, and the edges 96 and 116", all(b(x) == "closed" for x in (106, 104, 108, 96, 116)))
expect("ajar: 117, and the measured 123 (pushed about 1 cm, twice), 136 to 196 (about 3 cm), up to 250", all(b(x) == "ajar" for x in (117, 123, 136, 140, 196, 250)))
expect("open: no echo, the measured 336 to 382 (the room behind the open door), 455 and 3564, and 251", all(b(x) == "open" for x in (None, 336, 357, 382, 455, 3564, 251)))
expect("blocked: nearer than the closed band: 95 mm, and the measured 57, 43, 30 (a hand in front of the sensor), and 25", all(b(x) == "blocked" for x in (95, 57, 43, 30, 25)))
expect("the margins: closed readings (104 to 108) are 8 mm inside the top edge of the closed band, and a push of 1 cm (123 mm or more) is 7 mm beyond it", band(108, DEFAULTS) == "closed" and band(116, DEFAULTS) == "closed" and band(123, DEFAULTS) == "ajar" and 116 - 108 == 8 and 123 - 116 == 7)
expect("the door closed BY HAND (95 to 107 mm measured, median 96) is at the lower edge of the band: the motor's 106 is the position that counts", band(96, DEFAULTS) == "closed" and band(95, DEFAULTS) == "blocked")

print("3. what the door is doing: debounce and locking")
c, io, d = make()
expect("before any reading the state is unknown and the sensor is 'waiting'", d.snapshot()["state"] is None and d.snapshot()["sensor"] == "waiting" and d.snapshot()["mode"] == "unknown")
d.on_distance(CLOSED, CLOSED); d.on_distance(CLOSED, CLOSED)
expect("a reading from the board changes nothing until tick() has looked at it (the board's thread only stores)", d.state is None and d.last_f is None)
c, io, d = make(); evs = feed(c, d, CLOSED, 4)
expect("4 readings in a row are not enough to decide (the debounce is 5)", d.state is None and kinds(evs) == [])
evs = feed(c, d, CLOSED, 1)
expect("the 5th reading in a row decides: the door reads closed, and a closed door is a LOCKED door", d.state == "closed" and kinds(evs) == ["state", "locked"] and d.snapshot()["mode"] == "locked", str(kinds(evs)))
evs = feed(c, d, 150, 1); evs += feed(c, d, CLOSED, 3)
expect("one stray reading (150 mm) among closed ones changes nothing", d.state == "closed" and kinds(evs) == [])
evs = feed(c, d, 150, 4); expect("four readings in a row are not enough to change the state", d.state == "closed")
evs = feed(c, d, 150, 1); expect("but five are: the door reads ajar (and, because it was locked, that is TAMPER)", d.state == "ajar" and "state" in kinds(evs) and "tamper" in kinds(evs), str(kinds(evs)))

print("4. opening and closing, and checking that it worked")
c, io, d = make(); feed(c, d, CLOSED, 10)
ev = d.request_open()
expect("'open' sets the speed and starts the motor the way that opens this door: motor_speed(100, 250), motor_run(-1, 600)", io.calls == [("motor_speed", 100, 250), ("motor_run", -1, 600)] and kinds(ev) == ["move"])
expect("while it moves the mode is 'moving', the lock is not claimed, and there is no tamper alarm", d.snapshot()["mode"] == "moving" and d.snapshot()["moving"] == "open" and d.commanded is None)
try: d.request_close(); w = False
except ValueError as e: w = "already moving" in str(e)
expect("another move while it moves is refused", w and len(io.calls) == 2)
evs = feed(c, d, None, 24)
expect("when the door leaves the sensor's view (no echo) and the move and the settling time are over, the door is checked and found OPEN: unlocked, no tamper", "opened" in kinds(evs) and d.snapshot()["mode"] == "unlocked" and not d.tamper and d.state == "open", str(kinds(evs)))
ev = d.request_close(); expect("'close' drives the other way: motor_run(+1, 600)", io.calls[-1] == ("motor_run", 1, 600))
evs = feed(c, d, CLOSED, 25)
expect("when the distance is back in the closed band after the move, the door is CLOSED and locked", "closed" in kinds(evs) and d.snapshot()["mode"] == "locked" and d.fault is None, str(kinds(evs)))
c, io, d = make(); feed(c, d, CLOSED, 10); d.request_open(); n = len(io.calls); evs = feed(c, d, CLOSED, 24)
expect("if the door did NOT open (still reads closed), it tries once more", "retry" in kinds(evs) and io.calls[-1] == ("motor_run", -1, 600) and len(io.calls) == n + 2, str(kinds(evs)))
evs = feed(c, d, CLOSED, 24)
expect("and if it still does not, it reports a FAULT (with what it reads), is not locked, and does not call the door open", "fault" in kinds(evs) and d.fault and "did not open" in d.fault and "106 mm" in d.fault and d.snapshot()["mode"] == "unknown", str(d.fault))
n = len(io.calls); feed(c, d, CLOSED, 10)
expect("no third attempt on its own (a fault waits for a person), and a closed-reading door with a fault is not silently called locked", len(io.calls) == n and d.snapshot()["mode"] == "unknown")
d.request_close(); expect("a new command clears the fault", d.fault is None)
c, io, d = make(); feed(c, d, None, 10); d.request_close(); evs = feed(c, d, 150, 24); evs += feed(c, d, 150, 24)
expect("a close that leaves the door ajar (part-way) is retried and then a fault too", "retry" in kinds(evs) and "fault" in kinds(evs) and "did not close" in d.fault and "150 mm" in d.fault)
c, io, d = make(); feed(c, d, CLOSED, 10); d.request_open(); evs = feed(c, d, 150, 24)
expect("an open that only gets as far as ajar is not good enough: it retries", "retry" in kinds(evs))
c, io, d = make(); feed(c, d, CLOSED, 10); d.request_open(); feed(c, d, CLOSED, 3); evs = d.stop()
expect("STOP sends motor_run(0, 0) at once, cancels the move and the check, and says so", io.calls[-1] == ("motor_run", 0, 0) and d.move is None and kinds(evs) == ["stopped"] and d.commanded is None)
n = len(io.calls); evs = d.stop(); expect("STOP when nothing is moving is harmless (still sent, no event)", io.calls[-1] == ("motor_run", 0, 0) and kinds(evs) == [])
c, io, d = make(); feed(c, d, CLOSED, 10); evs = d.toggle()
expect("the push-button (toggle) opens a closed door", io.calls[-1] == ("motor_run", -1, 600))
feed(c, d, None, 24); d.toggle(); expect("and closes an open one", io.calls[-1] == ("motor_run", 1, 600))
feed(c, d, 150, 24); feed(c, d, 150, 24); d.fault = None; d.move = None; d.toggle(); expect("and closes one that is ajar", io.calls[-1] == ("motor_run", 1, 600))
c, io, d = make()
try: d.toggle(); w = False
except ValueError as e: w = "not seen the door" in str(e)
expect("the push-button before the sensor has seen anything is refused", w)

print("5. tamper")
c, io, d = make(); feed(c, d, CLOSED, 10); evs = feed(c, d, 123, 5)
expect("a locked door pushed open 1 cm (123 mm) raises TAMPER once, with what it reads", kinds(evs).count("tamper") == 1 and d.tamper and "forced" in [e for e in evs if e["kind"] == "tamper"][0]["text"] and "123 mm" in [e for e in evs if e["kind"] == "tamper"][0]["text"], str(kinds(evs)))
evs = feed(c, d, 123, 30); expect("and not again and again while it stays open", kinds(evs).count("tamper") == 0 and d.tamper)
evs = feed(c, d, CLOSED, 5); expect("when the door is closed again the alarm is over", "tamper_over" in kinds(evs) and not d.tamper and d.snapshot()["mode"] == "locked", str(kinds(evs)))
c, io, d = make(); feed(c, d, CLOSED, 10); evs = feed(c, d, None, 5); expect("the locked door swung fully open (no echo) is TAMPER too", "tamper" in kinds(evs))
c, io, d = make(); feed(c, d, CLOSED, 10); evs = feed(c, d, 60, 5)
expect("something held in front of the sensor (nearer than the door) is TAMPER, and says so", "tamper" in kinds(evs) and "in front of the sensor" in [e for e in evs if e["kind"] == "tamper"][0]["text"])
c, io, d = make(); feed(c, d, None, 10); evs = feed(c, d, 123, 10)
expect("a door that was never locked (it was open) gives no tamper alarm", "tamper" not in kinds(evs) and not d.tamper)
c, io, d = make(); feed(c, d, CLOSED, 10); d.request_open(); evs = feed(c, d, 123, 10); evs += feed(c, d, None, 14)
expect("opening the door on purpose gives no tamper alarm on the way", "tamper" not in kinds(evs) and "opened" in kinds(evs), str(kinds(evs)))
c, io, d = make(push_back=True); feed(c, d, CLOSED, 10); n = len(io.calls); evs = feed(c, d, 123, 5)
expect("with 'push back' on, a forced door raises the alarm and tries to push the door shut: motor_run(+1, 600)", "tamper" in kinds(evs) and "push_back" in kinds(evs) and io.calls[-1] == ("motor_run", 1, 600) and len(io.calls) == n + 2, str(kinds(evs)))
evs = feed(c, d, CLOSED, 25); expect("and if the door then reads closed: closed again, 'pushed back', alarm over, locked", "closed" in kinds(evs) and "tamper_over" in kinds(evs) and "pushed back" in [e for e in evs if e["kind"] == "closed"][0]["text"] and d.snapshot()["mode"] == "locked", str(kinds(evs)))
c, io, d = make(push_back=True); feed(c, d, CLOSED, 10); evs = feed(c, d, 123, 5); n = len(io.calls); evs = feed(c, d, 123, 24); evs += feed(c, d, 123, 24); evs += feed(c, d, 123, 30)
expect("if someone holds the door open, it pushes back once (plus its one retry), then gives a FAULT and leaves the alarm on: it does not push against a person for ever", kinds(evs).count("push_back") == 0 and "fault" in kinds(evs) and d.tamper and len([x for x in io.calls if x[0] == "motor_run" and x[1] == 1]) == 2, str([x for x in io.calls if x[0] == 'motor_run']))
evs = feed(c, d, CLOSED, 5)
expect("when the door is finally closed by hand the alarm ends and the fault clears, and it is locked again", "tamper_over" in kinds(evs) and d.fault is None, str(kinds(evs)))
evs = feed(c, d, CLOSED, 3); expect("... (on the next reading)", "locked" in kinds(evs) or d.snapshot()["mode"] == "locked", str(kinds(evs)))
c, io, d = make(push_back=True); feed(c, d, CLOSED, 10); evs = feed(c, d, 60, 5)
expect("push back is not tried when something is in front of the sensor (there is no door to push)", "push_back" not in kinds(evs))

print("6. calibrating the closed distance")
c, io, d = make(tmp / "cal" if (tmp / "cal").mkdir() is None else tmp); feed(c, d, 108, 40); evs = d.calibrate()
expect("with the door closed and steady the closed distance is taken from what the sensor sees (108 mm), the event says what it was (106), and it is remembered", d.cfg["closed_mm"] == 108 and kinds(evs) == ["calibrated"] and "was 106" in evs[0]["text"] and json.loads((tmp / "cal" / "cfg.json").read_text())["closed_mm"] == 108)
c, io, d = make(); feed(c, d, CLOSED, 5)
try: d.calibrate(); w = False
except ValueError as e: w = "Not enough readings" in str(e)
expect("calibrating with too few readings is refused", w)
c, io, d = make(); evs = []
for i in range(40): evs += feed(c, d, CLOSED if i % 2 else CLOSED + 14, 1)
try: d.calibrate(); w = False
except ValueError as e: w = "not steady" in str(e)
expect("calibrating while the distance jumps about is refused, with how much it varies", w and d.cfg["closed_mm"] == CLOSED)
c, io, d = make(); feed(c, d, CLOSED, 40); d.request_open()
try: d.calibrate(); w = False
except ValueError: w = True
expect("calibrating during a move is refused", w)
c, io, d = make(); feed(c, d, None, 40)
try: d.calibrate(); w = False
except ValueError: w = True
expect("calibrating when the door is out of view (no echo) is refused", w)

print("7. the sensor goes quiet")
c, io, d = make(); feed(c, d, CLOSED, 10); c.t += 1.5; evs = d.tick()
expect("no readings for over a second: 'sensor lost', once, and the snapshot says so", kinds(evs) == ["sensor_lost"] and d.snapshot()["sensor"] == "lost" and d.tick() == [])
evs = feed(c, d, CLOSED, 1); expect("when readings come back: 'sensor back'", "sensor_back" in kinds(evs) and d.snapshot()["sensor"] == "ok")

print("8. what the page shows, and the log")
c, io, d = make(tmp); feed(c, d, CLOSED, 600); snap = d.snapshot()
expect("the snapshot gives the distance, the state, the mode, the bands and the settings", snap["mm"] == CLOSED and snap["raw"] == CLOSED and snap["state"] == "closed" and snap["mode"] == "locked" and snap["bands"] == {"lo": 96, "hi": 116, "open": 250} and snap["settings"]["open_dir"] == -1 and snap["sensor"] == "ok")
expect("the chart history has at most 200 points, all within 30 seconds, newest at about 0 (%d points from 600 readings)" % len(snap["history"]), len(snap["history"]) <= 200 and min(p[0] for p in snap["history"]) >= -30.0 and abs(snap["history"][-1][0]) <= 0.5)
feed(c, d, 123, 5); feed(c, d, CLOSED, 5); d.request_open(); d.stop()
rows = list(csv.DictReader(open(tmp / "log.csv", encoding="utf-8")))
expect("every event is in door_log.csv (%d rows) with its time, kind, text and the distance" % len(rows), len(rows) >= 6 and list(rows[0]) == ["time", "kind", "text", "mm"] and {"state", "locked", "tamper", "tamper_over", "move", "stopped"} <= {r["kind"] for r in rows} and rows[0]["time"] == "23:50:07")
d.clear_events(); expect("the events on the page can be cleared (the log keeps them)", d.snapshot()["events"] == [] and len(list(csv.DictReader(open(tmp / "log.csv", encoding="utf-8")))) == len(rows))
c, io, d = make(); feed(c, d, CLOSED, 10)
for _ in range(300): d._event([], "state", "x")
expect("only the last 40 events are sent to the page, and only 200 are kept in memory", len(d.snapshot()["events"]) == 40 and len(d.events) == 200)

print("9. main.py is wired to the board and the page")
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
spec = importlib.util.spec_from_file_location("door_main", PY / "main.py"); main = importlib.util.module_from_spec(spec); spec.loader.exec_module(main)
mc = Clock(); main.door.now = mc; main.door.clock = lambda: datetime.datetime(2026, 11, 15, 23, 50, 7); main.door.settings_path = tmp / "m_cfg.json"; main.door.log_path = tmp / "m_log.csv"; main.door.cfg = dict(DEFAULTS)
cmd = lambda dct: log["handlers"]["cmd"]("sid", dct)
last = lambda kind: [m for k, m in log["messages"] if k == kind][-1]
def feed_main(mm, n):
    for _ in range(n):
        mc.t += 0.06; log["provided"]["distance"](mm, mm); log["loop"]()
expect("main.py gets the 'distance' and 'motor' messages, listens for page commands, and hands its loop to the app", "distance" in log["provided"] and "motor" in log["provided"] and "cmd" in log["handlers"] and "connect" in log["handlers"] and callable(log["loop"]))
log["handlers"]["connect"]("sid"); expect("a page that connects is sent the state at once", log["messages"][-1][0] == "state" and log["messages"][-1][1]["sensor"] == "waiting")
log["loop"](); expect("with no door state yet the LED matrix is told 'dark' (led 0)", ("led", 0, 0) in log["calls"])
feed_main(CLOSED, 10); st = last("state")
expect("after readings of a closed door the page is told it is LOCKED, and the matrix gets the closed padlock (led 1)", st["mode"] == "locked" and ("led", 1, 0) in log["calls"] and any(m[0] == "notice" and "locked" in m[1]["text"] for m in log["messages"]))
n_led = len([c for c in log["calls"] if c[0] == "led"]); feed_main(CLOSED, 5); expect("the picture is only sent again when it changes", len([c for c in log["calls"] if c[0] == "led"]) == n_led)
cmd({"action": "toggle"}); expect("'toggle' (the Space bar) opens the closed door: the speed and the move go to the board, with the direction that opens this door", log["calls"][-2:] == [("motor_speed", 100, 250), ("motor_run", -1, 600)] and last("state")["mode"] == "moving")
cmd({"action": "close"}); expect("a command while it moves is a warning, not a crash", last("notice")["level"] == "warn" and "already moving" in last("notice")["text"])
feed_main(None, 25); expect("when it reads open the page says opened and the matrix shows the open padlock (led 2)", last("state")["mode"] == "unlocked" and ("led", 2, 0) in log["calls"] and any("The door is open" in m[1]["text"] for m in log["messages"] if m[0] == "notice"))
cmd({"action": "stop"}); expect("'stop' sends motor_run(0, 0) and says Stopped", log["calls"][-1] == ("motor_run", 0, 0) and last("notice")["text"] == "Stopped.")
cmd({"action": "close"}); feed_main(CLOSED, 25); expect("'close' closes and checks it", last("state")["mode"] == "locked")
feed_main(150, 6); st = last("state")
expect("a forced door gives a warning to the page, TAMPER in the state, and the '!' picture on the matrix (led 3)", st["tamper"] and ("led", 3, 0) in log["calls"] and any(m[0] == "notice" and m[1]["level"] == "warn" and "TAMPER" in m[1]["text"] for m in log["messages"]))
tamper_state = st
feed_main(CLOSED, 6); expect("when the door is closed again: alarm over and the closed padlock comes back", not last("state")["tamper"] and log["calls"][-1] == ("led", 1, 0))
cmd({"action": "settings", "settings": {"closed_tol_mm": 20, "push_back": True}}); expect("'settings' are saved and the state carries them", last("state")["settings"]["closed_tol_mm"] == 20 and last("state")["settings"]["push_back"] is True and last("notice")["text"] == "Settings saved.")
cmd({"action": "settings", "settings": {"open_mm": 100}}); expect("settings that make no sense are a warning and are not saved", last("notice")["level"] == "warn" and last("state")["settings"]["open_mm"] == 250)
cmd({"action": "settings", "settings": {"pwm": "fast"}}); expect("a setting that is not a number is a warning", last("notice")["level"] == "warn" and "must be a number" in last("notice")["text"])
cmd({"action": "settings", "settings": {"push_back": False, "closed_tol_mm": 10}})
feed_main(107, 80); cmd({"action": "calibrate"}); expect("'calibrate' takes the closed distance from the sensor (107 mm)", last("state")["settings"]["closed_mm"] == 107 and any("107 mm" in m[1]["text"] for m in log["messages"] if m[0] == "notice"))
cmd({"action": "clear_events"}); expect("'clear_events' empties the events", last("state")["events"] == [])
cmd({"action": "dance"}); expect("an unknown command is a warning", last("notice")["level"] == "warn" and "Unknown" in last("notice")["text"])
cmd(None); expect("a command with no data does not crash it", last("notice")["level"] == "warn")
cmd({"action": "refresh"}); expect("'refresh' sends the state", log["messages"][-1][0] == "state")
mc.t += 3; log["loop"](); st = last("state")
expect("when the sensor goes quiet the page is warned and the matrix shows the X (led 4)", st["sensor"] == "lost" and ("led", 4, 0) in log["calls"] and any("No distance readings" in m[1]["text"] for m in log["messages"] if m[0] == "notice"))
lost_state = st
log["fail"] = True; main.led["sent"] = None; log["loop"](); expect("if the LED matrix does not answer, the loop carries on", True); log["fail"] = False
log["fail"] = True; cmd({"action": "toggle"}); expect("if the board does not answer a command, the page gets a clear warning and the app carries on", last("notice")["level"] == "warn"); log["fail"] = False
_time.sleep = real_sleep

# the real payloads, for the page test
c, io, d = make(); waiting = d.snapshot()
c, io, d = make(); feed(c, d, CLOSED, 40); locked = d.snapshot()
c, io, d = make(); feed(c, d, CLOSED, 10); d.request_open(); feed(c, d, CLOSED, 3); moving = d.snapshot()
c, io, d = make(); feed(c, d, CLOSED, 10); d.request_open(); feed(c, d, None, 30); unlocked = d.snapshot()
c, io, d = make(); feed(c, d, CLOSED, 10); feed(c, d, 123, 20); tamper = d.snapshot()
c, io, d = make(); feed(c, d, CLOSED, 10); d.request_open(); feed(c, d, CLOSED, 24); feed(c, d, CLOSED, 24); fault = d.snapshot()
c, io, d = make(); feed(c, d, CLOSED, 10); c.t += 3; d.tick(); lost = d.snapshot()
(HERE / "state_samples.json").write_text(json.dumps({"waiting": waiting, "locked": locked, "moving": moving, "unlocked": unlocked, "tamper": tamper, "fault": fault, "lost": lost}))
expect("the real payloads for the page test are written (locked, moving, open, tamper, fault, sensor lost)", locked["mode"] == "locked" and moving["mode"] == "moving" and unlocked["mode"] == "unlocked" and tamper["tamper"] and fault["fault"] and lost["sensor"] == "lost")

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
