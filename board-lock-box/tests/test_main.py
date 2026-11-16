"""The whole app through main.py, with a fake camera, a fake board and a simulated door: camera -> network -> lock rules -> door -> LED matrix.   python test_main.py
Needs numpy and opencv (cv2)."""
import datetime, importlib.util, json, sys, tempfile, threading, time, types
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
PY = HERE.parent / "python"
sys.path.insert(0, str(PY)); sys.path.insert(0, str(HERE))
import board_vision as bv
import lockbox
import matrix as mx
from lock_scenario import conf

lockbox.ITERATIONS = 1000
problems = 0


def expect(label, cond, detail=""):
    global problems
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    problems += (not cond)


class Clock:
    def __init__(self): self.t = 500.0
    def __call__(self): return self.t


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


class MainCam:
    def __init__(self, frame): self.frame, self.released = frame, False
    def read(self):
        threading.Event().wait(0.002); return True, self.frame.copy()
    def release(self): self.released = True


class LivePipeline:                                  # stands in for the network: the test says what it "sees"
    size, gray = 64, False
    def __init__(self): self.probs = conf(0, 0.95)
    def preprocess(self, frame, roi): return np.full((64, 64, 3), 50, np.uint8)
    def predict(self, frame, roi): return int(np.argmax(self.probs)), np.array(self.probs), {"prep_ms": 1.0, "infer_ms": 4.0}


tmp = Path(tempfile.mkdtemp())
pre_existing = (PY / "lockbox_log.csv").exists()                  # importing the app writes its "started" line: do not leave that file behind in the app folder
orig_open = bv.open_camera; opened = []
bv.open_camera = lambda w_, h_, **kw: (opened.append(kw) or MainCam(np.full((480, 640, 3), 90, np.uint8)), "/dev/video2", "icspring camera")
spec = importlib.util.spec_from_file_location("lockbox_main", PY / "main.py"); main = importlib.util.module_from_spec(spec); spec.loader.exec_module(main)
clock = Clock(); fixed = lambda: datetime.datetime(2026, 11, 16, 3, 30, 0)
main.door.now = main.box.now = main.board.now = clock
main.door.clock = main.box.clock = main.board.clock = fixed
main.box.config_path, main.box.log_path = tmp / "lock_config.json", tmp / "lockbox_log.csv"
if not pre_existing: (PY / "lockbox_log.csv").unlink()
main.door.settings_path, main.door.log_path = tmp / "door_config.json", tmp / "door_log.csv"
main.board.roi_path, main.board.camera_path = tmp / "roi.json", tmp / "camera.json"
live = LivePipeline(); main.board.pipeline = live
cmd = lambda d: log["handlers"]["cmd"]("sid", d)
last = lambda kind: [m for k, m in log["messages"] if k == kind][-1]
world = {"mm": 106, "seen": 0, "target": None, "broken": False}


def physics():                                       # a working door: told to open (-1) it soon reads "nothing in view", told to close (+1) it reads 106 mm
    runs = [c for c in log["calls"] if c[0] == "motor_run"]
    while world["seen"] < len(runs):
        _, d, ms = runs[world["seen"]]; world["seen"] += 1
        if d != 0 and not world["broken"]: world["target"] = (None if d == -1 else 106, clock.t + 0.3)
    if world["target"] and clock.t >= world["target"][1]: world["mm"], world["target"] = world["target"][0], None


def pump(n, probs=None, dt=0.1):
    """n passes of the app's loop, each with a NEW camera picture (the fake network sees `probs`) and a distance reading from the simulated door."""
    if probs is not None: live.probs = probs
    for _ in range(n):
        got = main.board.camera.read_latest() if main.board.camera else None
        before = got[1] if got else -1
        end = time.time() + 1.0
        while time.time() < end and main.board.camera is not None and (main.board.camera.read_latest() or (None, before))[1] == before: threading.Event().wait(0.002)
        clock.t += dt; physics(); log["provided"]["distance"](world["mm"], world["mm"]); log["loop"]()


def show(d): pump(10, conf(d)); pump(6, conf(0, 0.95))
def state(): return last("lock")["state"]


print("1. wiring")
expect("main.py takes the 'distance' and 'motor' messages from the board, listens for page commands, and hands its loop to the app", "distance" in log["provided"] and "motor" in log["provided"] and "cmd" in log["handlers"] and "connect" in log["handlers"] and callable(log["loop"]))
expect("the network is the real one (64 x 64 colour) and the camera is asked for MJPG at 30 frames a second when it is opened", main.board.pipeline is live and bv.Pipeline(PY / "model" / "finger_cnn.npz").size == 64 and main.board.camera_settings == {"fourcc": "MJPG"})
log["handlers"]["connect"]("sid")
expect("a page that connects is sent the camera view and the lock state at once, and no code is set yet", log["messages"][-2][0] == "view" and log["messages"][-1][0] == "lock" and last("lock")["configured"] is False and last("lock")["state"] == "setup")

print("2. the code, and the first pass of the loop")
cmd({"action": "button"}); expect("the button with no code gives a clear warning", last("notice")["level"] == "warn" and "Set a code first" in last("notice")["text"])
for bad in ({"code": "244", "confirm": "244"}, {"code": "245", "confirm": "254"}, {"code": "245", "confirm": "245", "challenge": 5}):
    cmd(dict(action="set_code", **bad)); ok = last("notice")["level"] == "warn"
    expect("a code that is not allowed is a warning and nothing is saved (%s)" % list(bad.values())[:2], ok and not (tmp / "lock_config.json").exists())
cmd({"action": "set_code", "code": "245", "confirm": "245"})
expect("a good code is saved: a notice that says only a hash is kept, the lock message says it is configured, and the file exists", last("notice")["level"] == "ok" and "salted hash" in last("notice")["text"] and last("lock")["configured"] is True and (tmp / "lock_config.json").exists() and "245" not in (tmp / "lock_config.json").read_text())
pump(3)
expect("the loop opens the camera by itself (asking for MJPG at 30 frames a second), the network runs on its pictures, and the LED picture reaches the board in two calls", main.board.last is not None and opened[0] == {"fourcc": "MJPG", "fps": 30} and [c[0] for c in log["calls"] if c[0] in ("pic_a", "pic_b")][:2] == ["pic_a", "pic_b"], str(opened[:1]))
n = len([c for c in log["calls"] if c[0] in ("pic_a", "pic_b")]); pump(3); expect("the picture is only sent again when it changes", len([c for c in log["calls"] if c[0] in ("pic_a", "pic_b")]) == n)
pump(20); expect("the closed door reads closed and counts as locked", state() == "idle" and last("lock")["door"]["mode"] == "locked")

print("3. the whole chain through the loop: button, challenge, code, door opens, locks again, door closes")
cmd({"action": "button"}); d = last("lock")["challenge_digit"]
expect("the button starts the challenge and the page is told the digit to show", state() == "challenge" and d in (1, 3, 5))
show(d); expect("showing it moves on to the code", state() == "entering")
for digit in (2, 4, 5): show(digit)
expect("the right code unlocks, the notice says so, and the door is asked to open the way that worked: speed, then motor -1 for 600 ms", state() == "unlocked" and any(m[0] == "notice" and m[1]["level"] == "ok" for m in log["messages"][-60:]) and ("motor_run", -1, 600) in log["calls"] and ("motor_speed", 100, 250) in log["calls"])
pump(30); expect("the sensor sees the door open and the page is told: unlocked, door open", last("lock")["door"]["state"] == "open" and state() == "unlocked")
pump(120); expect("10 seconds later it locks again by itself and closes the door (motor +1), checked by the sensor", state() == "idle" and last("lock")["door"]["mode"] == "locked" and [c[1] for c in log["calls"] if c[0] == "motor_run" and c[1] != 0] == [-1, 1])

print("4. tamper through the loop")
world["mm"] = 123; pump(8)
expect("forcing the locked door raises the alarm: a warning to the page, the tamper lockout of 15 seconds, and the '!' sent to the LED matrix", last("lock")["door"]["tamper"] and 12 < last("lock")["tamper_left"] <= 15 and any(m[0] == "notice" and "TAMPER" in m[1]["text"] for m in log["messages"][-60:]), str(last("lock")["tamper_left"]))
rows = mx.frame_rows(lockbox.ALERT); pa = [c for c in log["calls"] if c[0] == "pic_a"][-1]; pb = [c for c in log["calls"] if c[0] == "pic_b"][-1]
expect("the '!' is what the board was last sent", pa[1:] == ((rows[0] << 13) | rows[1], (rows[2] << 13) | rows[3]) and pb[1:] == ((rows[4] << 13) | rows[5], (rows[6] << 13) | rows[7]))
cmd({"action": "button"}); expect("the button is ignored during the tamper lockout (and says so)", last("lock")["state"] == "idle" and any(e["kind"] == "ignored" and "tamper" in e["text"] for e in last("lock")["log"]))
world["mm"] = 106; pump(260); cmd({"action": "button"}); expect("after the lockout and with the door closed again, finger entry works again", state() in ("challenge", "entering"))
cmd({"action": "stop"}); pump(2)

print("5. the page's other commands")
cmd({"action": "stop"}); expect("stop says Stopped and sends motor_run(0, 0)", last("notice")["text"] == "Stopped." and ("motor_run", 0, 0) in log["calls"][-3:])
pump(5); cmd({"action": "door_open"}); expect("the maintenance open moves the door and the log says it bypasses the code", ("motor_run", -1, 600) == log["calls"][[i for i, c in enumerate(log["calls"]) if c[0] == "motor_run"][-1]] and any("bypasses the code" in e["text"] for e in last("lock")["log"]))
pump(30); cmd({"action": "door_close"}); pump(30)
world["mm"] = 107; pump(80); cmd({"action": "calibrate"}); expect("calibrate takes the closed distance from the sensor", last("lock")["door"]["settings"]["closed_mm"] == 107 and last("notice")["level"] in ("ok", "info"))
cmd({"action": "push_back", "on": True}); expect("push back can be switched on", last("lock")["door"]["settings"]["push_back"] is True)
cmd({"action": "nudge", "dx": 10, "dy": 0, "ds": 0}); expect("the square can be moved (the page gets a new view at once)", last("view")["roi"]["x"] == 118)
cmd({"action": "find_tape", "color": "blue"}); expect("no tape in the picture: a warning that says what to do", last("notice")["level"] == "warn" and "arrow keys" in last("notice")["text"])
cmd({"action": "save_roi"}); cmd({"action": "reset_roi"}); expect("the square can be saved and reset", (tmp / "roi.json").exists() and last("view")["roi"] == {"x": 108, "y": 163, "side": 317})
n_open = len(opened); cmd({"action": "camera_mode", "fourcc": "YUYV"}); pump(3)
expect("the camera format can be changed: the camera is reopened with it", main.board.camera_settings == {"fourcc": "YUYV"} and len(opened) > n_open and opened[-1] == {"fourcc": "YUYV", "fps": 30}, str(opened[-1:]))
cmd({"action": "camera_mode", "fourcc": "H264"}); expect("an unknown camera format is a warning", last("notice")["level"] == "warn")
cmd({"action": "camera_mode", "fourcc": "MJPG"}); pump(3)
st = last("lock")["stats"]
expect("the tally counted the chain above: a try that opened the door, and a tamper alarm", st["sessions"] >= 1 and st["unlocked"] >= 1 and st["tamper"] >= 1 and st["unlock_s"]["n"] >= 1 and st["check_ms"]["n"] >= 1, str(st["sessions"]) + " " + str(st["unlocked"]))
cmd({"action": "log_full"}); fl = last("fulllog")["rows"]
expect("'log_full' sends the whole log from the file (every entry, from the lock and the door)", len(fl) >= len(last("lock")["log"]) - 1 and len(fl) > 20 and set(fl[0]) == {"time", "source", "kind", "text"} and {"lock", "door"} <= {r["source"] for r in fl}, str(len(fl)))
cmd({"action": "reset_stats"}); expect("'reset_stats' starts a new tally and says so", last("lock")["stats"]["sessions"] == 0 and last("lock")["stats"]["unlocked"] == 0 and last("notice")["level"] == "info" and "tally" in last("notice")["text"])
cmd({"action": "clear_log"}); expect("the log on the page can be cleared", last("lock")["log"] == [])
cmd({"action": "refresh"}); expect("refresh sends the view and the lock state", log["messages"][-2][0] == "view" and log["messages"][-1][0] == "lock")
cmd({"action": "dance"}); expect("an unknown command is a warning", last("notice")["level"] == "warn" and "Unknown" in last("notice")["text"])
cmd(None); expect("a command with no data does not crash it", last("notice")["level"] == "warn")
orig = main.box.press_button; main.box.press_button = lambda: (_ for _ in ()).throw(RuntimeError("boom")); cmd({"action": "button"}); main.box.press_button = orig
expect("an unexpected error becomes a warning and the app carries on", last("notice")["level"] == "warn" and "went wrong" in last("notice")["text"])

print("6. the loop keeps going")
orig_tick = main.box.tick; main.box.tick = lambda: (_ for _ in ()).throw(RuntimeError("boom")); pump(2); errs = main.sent["errors"]; main.box.tick = orig_tick; pump(2)
expect("a pass of the loop that fails is reported and the next one works (the lock does not stop)", errs >= 2 and main.board.last is not None)
n1 = len([1 for k, m in log["messages"] if k == "lock"]); log["loop"](); log["loop"](); n2 = len([1 for k, m in log["messages"] if k == "lock"])
expect("the lock state is sent to the page about 5 times a second, not on every pass (%d new in 2 quick passes)" % (n2 - n1), n2 - n1 <= 1)
log["fail"] = True; main.box.pic_sent = None; main.box._pic_try = -1e9; pump(2)
expect("if the board does not answer, the loop carries on", main.board.last is not None); log["fail"] = False
main.board.camera.stop(); bv.open_camera = orig_open

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
