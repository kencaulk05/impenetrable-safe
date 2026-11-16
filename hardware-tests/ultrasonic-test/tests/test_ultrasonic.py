"""Tests for the ultrasonic test's Python side (python/ultrasonic.py and python/main.py).   python test_ultrasonic.py
It also writes state_samples.json: the real payloads main.py sends to the page, which test_page.js then renders."""
import csv, datetime, importlib.util, json, sys, tempfile, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = HERE.parent / "python"
sys.path.insert(0, str(PY))
from ultrasonic import SensorMonitor, bar_columns, stats, usable, verdict

problems = 0


def expect(label, cond, detail=""):
    global problems
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    problems += (not cond)


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def make(tmp=None):
    c = Clock(); m = SensorMonitor(log_path=(Path(tmp) / "captures.csv") if tmp else None, now=c, clock=lambda: datetime.datetime(2026, 11, 15, 14, 30, 5))
    return c, m


def feed(c, m, value, n, dt=0.06, raw=None):
    for _ in range(n):
        c.t += dt; m.on_distance(value, value if raw is None else raw)


tmp = Path(tempfile.mkdtemp())
print("1. which readings are usable")
expect("-1 (no echo), too near (19 mm) and too far (4001 mm) are not usable; 20 and 4000 are; None and rubbish are not; 120.7 becomes 120", usable(-1) is None and usable(19) is None and usable(4001) is None and usable(20) == 20 and usable(4000) == 4000 and usable(None) is None and usable("abc") is None and usable(120.7) == 120)
expect("the distance bar: nothing for no reading, 5 of 13 columns at 120 mm, never more than 13", bar_columns(None) == 0 and bar_columns(-1) == 0 and bar_columns(120) == 5 and bar_columns(300) == 13 and bar_columns(9999) == 13)

print("2. the numbers for a capture")
s = stats([100, 102, 98, 100])
expect("four readings 100, 102, 98, 100: mean 100, median 100, range 98 to 102, spread 1.4 mm, all usable", s["n"] == 4 and s["valid"] == 4 and s["mean_mm"] == 100.0 and s["median_mm"] == 100 and s["min_mm"] == 98 and s["max_mm"] == 102 and s["std_mm"] == 1.4 and s["valid_pct"] == 100.0, str(s))
expect("a steady sensor is GOOD (spread 0)", stats([120] * 50)["verdict"].startswith("GOOD"))
expect("a little jumpy is OK, a lot jumpy is POOR", stats([120, 126] * 25)["verdict"].startswith("OK") and stats([100, 120] * 25)["verdict"].startswith("POOR"), "%s | %s" % (stats([120, 126] * 25)["std_mm"], stats([100, 120] * 25)["std_mm"]))
s = stats([120] * 40 + [None] * 10)
expect("80%% usable readings is POOR, and says 80%%", s["valid_pct"] == 80.0 and s["verdict"].startswith("POOR") and "80%" in s["verdict"], s["verdict"][:60])
expect("fewer than half usable, or none at all, is BAD, with advice about the wiring and the power", stats([None] * 20)["verdict"].startswith("BAD") and "5V" in stats([None] * 20)["verdict"] and stats([])["verdict"].startswith("BAD") and stats([120] * 4 + [None] * 6)["verdict"].startswith("BAD"))
s = stats([None] * 5)
expect("with nothing usable the numbers are empty, not zero (no fake average)", s["mean_mm"] is None and s["median_mm"] is None and s["min_mm"] is None and s["std_mm"] is None and s["valid"] == 0)
expect("a single usable reading has a spread of 0", stats([130, None, None])["std_mm"] == 0.0)
v_open = lambda r: stats(r, "open")["verdict"]
expect("for a FULLY OPEN door, no echo is the expected answer, not a fault: 'NOTHING IN VIEW' (and the lock will treat no echo as door open)", v_open([None] * 40).startswith("NOTHING IN VIEW") and "door open" in v_open([None] * 40) and not v_open([None] * 40).startswith("BAD"))
expect("a fully open door that gives a mix of far echoes and no echo is 'MIXED'", v_open([None] * 20 + [900] * 20).startswith("MIXED"))
expect("a fully open door that still sees something far away says what it sees (the median, 1500 mm), so the closed distance can be compared with it", v_open([1500] * 40).startswith("SOMETHING IN VIEW") and "1500 mm" in v_open([1500] * 40))
expect("a fully open capture that received no readings at all is NO DATA, not 'nothing in view'", v_open([]).startswith("NO DATA"))
expect("the same no-echo capture for a CLOSED door, a door pushed open a little, or anything else is still BAD: only 'fully open' expects it", all(stats([None] * 40, k)["verdict"].startswith("BAD") for k in ("closed", "ajar", "other")))

print("3. the live readings")
c, m = make()
expect("with no readings the snapshot is empty and says so", m.snapshot()["mm"] is None and m.snapshot()["age_s"] is None and m.snapshot()["history"] == [] and m.snapshot()["ok_pct"] is None)
feed(c, m, 143, 30); snap = m.snapshot()
expect("with readings it gives the latest filtered and raw value, how old it is, and how many were usable lately", snap["mm"] == 143 and snap["raw"] == 143 and snap["age_s"] == 0.0 and snap["ok_pct"] == 100.0)
feed(c, m, -1, 10, raw=-1); snap = m.snapshot()
expect("when the echo disappears the readings become None, and the usable share falls (%s%%)" % snap["ok_pct"], snap["mm"] is None and snap["raw"] is None and 60 <= snap["ok_pct"] <= 85)
c.t += 3; expect("a reading 3 seconds old is reported as 3.0 s old", m.snapshot()["age_s"] == 3.0)
c2, m2 = make(); feed(c2, m2, 100, 500); h = m2.snapshot()["history"]
expect("the chart history keeps at most 150 points, all within the last 15 seconds, newest at about 0 (%d points from 500 readings)" % len(h), len(h) <= 150 and min(p[0] for p in h) >= -15.0 and abs(h[-1][0]) <= 0.5)
feed(c2, m2, 100, 3000)
expect("old readings are forgotten (memory does not grow without end): %d kept" % len(m2.readings), len(m2.readings) < 2500)

print("4. captures")
c, m = make(tmp)
for bad, why in ((("door closed", "9V", 5), "an unknown power supply"), (("door closed", "3V3", "abc"), "a length that is not a number")):
    try: m.start_capture(*bad); ok = False
    except ValueError: ok = True
    expect("a capture with %s is refused with a clear message" % why, ok)
expect("a length of 999 s becomes 60, 0 becomes 1, '5' is 5; an empty label becomes 'unlabelled' and a long one is cut to 60 characters",
       m.start_capture("x", "3V3", 999) == 60 and (setattr(m, "capture", None) or True) and m.start_capture("x", "5V", 0) == 1 and (setattr(m, "capture", None) or True) and m.start_capture("", "3V3", "5") == 5 and m.capture["label"] == "unlabelled" and (setattr(m, "capture", None) or True)
       and (m.start_capture("y" * 200, "3V3", 5) and len(m.capture["label"]) == 60))
m.capture = None
try: m.start_capture("a", "3V3", 5); m.start_capture("b", "3V3", 5); busy = False
except ValueError as e: busy = "already running" in str(e)
expect("a second capture while one is running is refused", busy)
m.capture = None; c, m = make(tmp)
m.start_capture("door closed", "3V3", 5); feed(c, m, 120, 40)
expect("while capturing the snapshot says what, from which supply, and how long is left", m.snapshot()["capturing"] == {"label": "door closed", "kind": "other", "supply": "3V3", "seconds": 5, "remaining_s": round(5 - 40 * 0.06, 1)}, str(m.snapshot()["capturing"]))
expect("tick does nothing before the time is up", m.tick() is None and m.snapshot()["rows"] == [])
feed(c, m, 120, 50); row = m.tick()
expect("when the time is up it finishes: one row with the label, the supply, the time of day and the statistics; the capture ends", row is not None and row["label"] == "door closed" and row["supply"] == "3V3" and row["time"] == "14:30:05" and row["n"] == 90 and row["mean_mm"] == 120.0 and row["verdict"].startswith("GOOD") and m.snapshot()["capturing"] is None and m.snapshot()["rows"] == [row])
c.t += 1; m.start_capture("door open", "5V", 1); feed(c, m, 190, 10); feed(c, m, -1, 10, raw=-1); c.t += 2; row2 = m.tick()
expect("a capture with a gap in the readings counts them honestly (10 of 20 usable, 50%)", row2["n"] == 20 and row2["valid"] == 10 and row2["valid_pct"] == 50.0 and row2["mean_mm"] == 190.0, str(row2["verdict"][:40]))
rows = list(csv.DictReader(open(tmp / "captures.csv", encoding="utf-8")))
expect("both captures are in captures.csv with a header, in order (%d rows)" % len(rows), len(rows) == 2 and rows[0]["label"] == "door closed" and rows[1]["supply"] == "5V" and rows[0]["mean_mm"] == "120.0" and list(rows[0])[0] == "time")
hdr = open(tmp / "captures.csv", encoding="utf-8").readline().strip().split(",")
expect("the CSV has a 'kind' column (closed, ajar, open or other) right after the label", hdr[:4] == ["time", "label", "kind", "supply"] and rows[0]["kind"] == "other")
(tmp / "kinds").mkdir(); c, mk = make(tmp / "kinds")
for bad_kind in ("banana", 5):
    try: mk.start_capture("x", "3V3", 5, bad_kind); ok = False
    except ValueError as e: ok = "Unknown kind" in str(e)
    expect("an unknown kind of capture (%r) is refused" % (bad_kind,), ok)
mk.start_capture("door fully open", "3V3", 2, "open"); feed(c, mk, -1, 40, raw=-1); c.t += 2; rk = mk.tick()
expect("a capture of kind 'open' with no echo gives a row of kind 'open' whose verdict is NOTHING IN VIEW", rk["kind"] == "open" and rk["verdict"].startswith("NOTHING IN VIEW") and rk["valid"] == 0 and rk["mean_mm"] is None)
mk.start_capture("door closed", "3V3", 2, None); expect("a missing kind means 'other'", mk.capture["kind"] == "other"); mk.capture = None
m.clear()
expect("clearing the table empties it but keeps captures.csv", m.snapshot()["rows"] == [] and len(list(csv.DictReader(open(tmp / "captures.csv", encoding="utf-8")))) == 2)

print("5. main.py is wired to the board and the page")
log = {"provided": {}, "calls": [], "loop": None, "handlers": {}, "messages": [], "led_fails": False}
class Bridge:
    @staticmethod
    def provide(name, fn): log["provided"][name] = fn
    @staticmethod
    def call(name, *args, timeout=10):
        if log["led_fails"]: raise TimeoutError("no answer")
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
spec = importlib.util.spec_from_file_location("ultra_main", PY / "main.py"); main = importlib.util.module_from_spec(spec); spec.loader.exec_module(main)
main.mon.log_path = tmp / "main_captures.csv"
last = lambda kind: [m for k, m in log["messages"] if k == kind][-1]
expect("main.py gets the 'distance' messages, listens for page commands, and hands its loop to the app", "distance" in log["provided"] and "cmd" in log["handlers"] and "connect" in log["handlers"] and callable(log["loop"]))
log["handlers"]["connect"]("sid"); expect("a page that connects is sent the state at once", log["messages"][-1][0] == "state" and log["messages"][-1][1]["mm"] is None)
for _ in range(20): log["provided"]["distance"](120, 120)
samples = {"no_data": None, "ok": None}
log["loop"](); st = last("state")
expect("the loop sends the state to the page, and draws the distance as a bar on the LED matrix: led(5, 5)", st["mm"] == 120 and ("led", 5, 5) in log["calls"])
n_led = len([c for c in log["calls"] if c[0] == "led"]); log["loop"]()
expect("the bar is only sent again when it changes", len([c for c in log["calls"] if c[0] == "led"]) == n_led)
log["handlers"]["cmd"]("sid", {"action": "capture", "label": "door closed", "supply": "3V3", "seconds": 2})
expect("a 'capture' command starts a capture and tells the page, with the state showing it", last("notice")["level"] == "info" and "2 seconds" in last("notice")["text"] and last("state")["capturing"]["label"] == "door closed")
log["handlers"]["cmd"]("sid", {"action": "capture", "label": "again", "supply": "3V3", "seconds": 2})
expect("a second capture while one runs gives a warning, not a crash", last("notice")["level"] == "warn" and "already running" in last("notice")["text"])
capturing_sample = last("state")
for _ in range(30): log["provided"]["distance"](121, 121)
main.mon.capture["end"] = main.mon.now() - 1; log["loop"]()
expect("when the time is up the loop adds the row and says how it went", last("notice")["level"] == "ok" and "GOOD" in last("notice")["text"] and len(last("state")["rows"]) == 1 and last("state")["capturing"] is None)
log["handlers"]["cmd"]("sid", {"action": "capture", "label": "x", "supply": "9V", "seconds": 2}); expect("a bad power choice is a warning", last("notice")["level"] == "warn")
log["handlers"]["cmd"]("sid", {"action": "capture", "label": "x", "supply": "3V3", "seconds": 2, "kind": "banana"}); expect("an unknown kind of capture is a warning", last("notice")["level"] == "warn" and "Unknown kind" in last("notice")["text"])
log["handlers"]["cmd"]("sid", {"action": "capture", "label": "door closed", "kind": "closed", "supply": "3V3", "seconds": 2}); expect("the kind sent by the page is passed on and shown in the state", last("state")["capturing"]["kind"] == "closed"); main.mon.capture = None
log["handlers"]["cmd"]("sid", {"action": "dance"}); expect("an unknown command is a warning", last("notice")["level"] == "warn" and "Unknown" in last("notice")["text"])
log["handlers"]["cmd"]("sid", None); expect("a command with no data does not crash it", last("notice")["level"] == "warn")
rows_sample = last("state")
log["handlers"]["cmd"]("sid", {"action": "clear"}); expect("'clear' empties the table", last("state")["rows"] == [])
log["handlers"]["cmd"]("sid", {"action": "refresh"}); expect("'refresh' sends the state", log["messages"][-1][0] == "state")
log["led_fails"] = True; main.led["sent"] = None; log["loop"](); expect("if the LED matrix does not answer, the loop carries on", True)
for _ in range(20): log["provided"]["distance"](-1, -1)
no_echo_sample = main.mon.snapshot()
_time.sleep = real_sleep

# the real payloads, for the page test
c, m = make(); no_data = m.snapshot()
c, m = make(); feed(c, m, 143, 250, raw=142); ok = m.snapshot()
c, m = make(); feed(c, m, -1, 60, raw=-1); no_echo = m.snapshot()
c, m = make(); m.start_capture("door closed", "3V3", 5); feed(c, m, 143, 40); capturing = m.snapshot()
c, m = make(); m.start_capture("door closed", "3V3", 5, "closed"); feed(c, m, 143, 90); c.t += 1; m.tick(); m.start_capture("door open <b>x</b>", "5V", 2, "other"); feed(c, m, -1, 40, raw=-1); c.t += 2; m.tick()
m.start_capture("door fully open (nothing in front of the sensor)", "3V3", 2, "open"); feed(c, m, -1, 40, raw=-1); c.t += 2; m.tick(); feed(c, m, 190, 30); with_rows = m.snapshot()
(HERE / "state_samples.json").write_text(json.dumps({"no_data": no_data, "ok": ok, "no_echo": no_echo, "capturing": capturing, "with_rows": with_rows}))
expect("the real payloads for the page test are written (%d rows in the last one)" % len(with_rows["rows"]), len(with_rows["rows"]) == 3 and with_rows["rows"][1]["verdict"].startswith("BAD") and with_rows["rows"][2]["verdict"].startswith("NOTHING IN VIEW"))

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
