"""Tests for the finger-count app's Python side (python/board_vision.py and python/main.py).   python test_vision.py
Needs numpy and opencv (cv2). It also writes state_samples.json: the real messages the app sends to the page, which test_page.js then renders."""
import csv, datetime, importlib.util, json, sys, tempfile, threading, time, types
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
PY = HERE.parent / "python"
MODEL = PY / "model" / "finger_cnn.npz"
sys.path.insert(0, str(PY)); sys.path.insert(0, str(HERE))
import board_vision as bv
from golden_frames import frame_for

problems = 0


def expect(label, cond, detail=""):
    global problems
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    problems += (not cond)


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


class FakeLatest:                                   # stands in for CameraThread
    def __init__(self, frame=None): self.frame, self.seq, self.t, self.lost, self.stopped = frame, 0 if frame is None else 1, 0.0, False, False
    def push(self, frame, t): self.frame, self.seq, self.t = frame, self.seq + 1, t
    def read_latest(self): return (self.frame, self.seq, self.t) if self.frame is not None else None
    def fps(self): return 10.0
    def stop(self): self.stopped = True


class FakePipeline:                                 # a confident, fixed answer, for the steadiness logic
    size, gray = 64, False
    def preprocess(self, frame, roi): return np.full((64, 64, 3), 50, np.uint8)
    def predict(self, frame, roi): return 3, np.array([0, 0, 0, .9, .1, 0]), {"prep_ms": 1.0, "infer_ms": 4.0}


class SeqPipeline:                                  # the n-th call takes n milliseconds, so the statistics can be checked
    calls = 0
    def predict(self, frame, roi):
        i = self.calls; self.calls += 1
        return 0, None, {"prep_ms": 0.5, "infer_ms": float(i)}


def tape_frame(w=640, h=480, color=(255, 0, 0)):
    f = np.full((h, w, 3), 90, np.uint8)
    cv2.rectangle(f, (150, 100), (450, 400), color, 12)
    return f


tmp = Path(tempfile.mkdtemp())
real = bv.Pipeline(MODEL)

print("1. the square")
r = bv.Roi(600, 450, 317).clipped(640, 480)
expect("a square that sticks out of the picture is pulled back inside; one that is too big is cut to the picture; one that is too small is made 8 pixels", (r.x, r.y, r.side) == (323, 163, 317) and bv.Roi(0, 0, 900).clipped(640, 480).side == 480 and bv.Roi(0, 0, 3).clipped(640, 480).side == 8, str(r))
expect("it survives being written as JSON and read back", bv.Roi.from_json(bv.Roi(10, 20, 30).to_json()) == bv.Roi(10, 20, 30))
bv.save_roi(bv.Roi(120, 150, 300), tmp / "roi.json", (640, 480))
expect("a saved square is read back for the same camera size", bv.load_roi(tmp / "roi.json", (640, 480)) == bv.Roi(120, 150, 300))
expect("but is refused for another camera size (the pixels would mean something else), and a missing or damaged file gives None", bv.load_roi(tmp / "roi.json", (320, 240)) is None and bv.load_roi(tmp / "none.json", (640, 480)) is None and (tmp / "bad.json").write_text("{nonsense") is not None and bv.load_roi(tmp / "bad.json", (640, 480)) is None)
expect("the default square is the one the network was trained on: x 108, y 163, side 317 at 640 x 480", bv.default_roi((640, 480)) == bv.Roi(108, 163, 317))
expect("at 320 x 240 (the same shape) it is scaled to half: 54, 82, 158", bv.default_roi((320, 240)) == bv.Roi(54, 82, 158), str(bv.default_roi((320, 240))))
d = bv.default_roi((1280, 720)); expect("for a camera of another shape it is a square in the middle", d.side == 475 and d.x == 402 and d.y == 122, str(d))

print("2. from camera picture to the network's input")
f = bv.synthetic_frame()
expect("the same made-up picture is made on every run, 640 x 480 colour", np.array_equal(f, bv.synthetic_frame()) and f.shape == (480, 640, 3) and f.dtype == np.uint8)
img = real.preprocess(f, bv.default_roi((640, 480)))
ref = cv2.resize(cv2.resize(f[163:163 + 317, 108:108 + 317], (128, 128), interpolation=cv2.INTER_AREA), (64, 64), interpolation=cv2.INTER_AREA)[:, :, ::-1]
expect("the network gets a 64 x 64 colour picture: the square, shrunk to 128 and then to 64 (INTER_AREA), with blue and red swapped", img.shape == (64, 64, 3) and img.dtype == np.uint8 and np.array_equal(img, ref))
red = np.zeros((480, 640, 3), np.uint8); red[:, :] = (0, 0, 255)                           # pure red in OpenCV's BGR
out = real.preprocess(red, bv.default_roi((640, 480)))
expect("red in the camera picture becomes the FIRST channel (R) of the network's input: the colour order is right", out[:, :, 0].mean() > 250 and out[:, :, 2].mean() < 5)
g = json.loads((HERE / "golden.json").read_text(encoding="utf-8"))
worst, same = 0.0, True
for e in g["frames"]:
    digit, probs, t = real.predict(frame_for(e["style"], e["seed"]), bv.default_roi((640, 480)))
    same &= digit == e["digit"]; worst = max(worst, max(abs(a - b) for a, b in zip(probs, e["probs"])))
expect("GOLDEN: on %d made-up pictures the app gives the same digits and the same probabilities as the original finger-lock code (largest difference %.1e)" % (len(g["frames"]), worst), same and worst < 1e-9 and len(g["frames"]) >= 16)
expect("the golden pictures cover several different answers, not just one (%s)" % sorted({e["digit"] for e in g["frames"]}), len({e["digit"] for e in g["frames"]}) >= 3)
digit, probs, t = real.predict(f, bv.default_roi((640, 480)))
expect("predict also says how long cutting out the square and running the network took", set(t) == {"prep_ms", "infer_ms"} and t["prep_ms"] > 0 and t["infer_ms"] > 0 and abs(sum(probs) - 1) < 1e-9)

print("3. is the answer steady?")
s = bv.Smoother()
for _ in range(7): s.add([0, 0, 0, .9, .1, 0])
expect("with fewer than 8 answers it is not stable yet", s.stable() is None)
s.add([0, 0, 0, .9, .1, 0]); expect("8 confident answers that agree: stable, and it is 3", s.stable() == 3)
s.reset(); [s.add([.2, .3, .1, .2, .1, .1]) for _ in range(8)]; expect("answers that agree but are not confident (about 0.3) are not stable", s.stable() is None)
s.reset(); [s.add([0, 0, 0, .9, .1, 0] if i % 2 else [0, 0, .9, 0, .1, 0]) for i in range(8)]; expect("answers that keep switching between 2 and 3 are not stable", s.stable() is None)
s.reset(); [s.add([0, 0, 0, .9, .1, 0]) for _ in range(6)]; [s.add([0, 0, .9, 0, .1, 0]) for _ in range(2)]; expect("a couple of stray answers among agreeing ones (6 of 8 = 75%) are tolerated", s.stable() == 3)
s.reset(); expect("reset forgets everything", s.stable() is None and not s.mean().any())

print("4. finding the tape square")
r = bv.find_square(tape_frame(), "blue")
expect("a blue tape square on the table is found, and the square returned is INSIDE it (the tape itself is left out)", r is not None and abs(r.x - 166) <= 4 and abs(r.y - 116) <= 4 and abs(r.side - 269) <= 6, str(r))
expect("no tape gives None; tape of another colour than asked for gives None", bv.find_square(np.full((480, 640, 3), 90, np.uint8), "blue") is None and bv.find_square(tape_frame(), "red") is None)
wide = np.full((480, 640, 3), 90, np.uint8); cv2.rectangle(wide, (100, 100), (500, 250), (255, 0, 0), 12)
expect("a blue rectangle that is not roughly square (blue jeans?) is ignored", bv.find_square(wide, "blue") is None)
try: bv.find_square(tape_frame(), "purple"); w = False
except ValueError: w = True
expect("an unknown tape colour is refused", w)

print("5. finding the webcam (as the sumo app does on this board)")
root = tmp / "v4l"
for n, name in (("video0", "qcom-venus-decoder"), ("video1", "qcom-venus-encoder"), ("video3", "Diccik Webcam: metadata"), ("video2", "Diccik Webcam: Diccik"), ("video10", "USB Camera")):
    (root / n).mkdir(parents=True); (root / n / "name").write_text(name + "\n")
(root / "video11").mkdir()
dev = bv.webcam_devices(str(root))
expect("the board's own video encoder and decoder are skipped, and the rest are in number order (2, 3, 10, 11, not 10 first)", [p for p, n in dev] == ["/dev/video2", "/dev/video3", "/dev/video10", "/dev/video11"] and dev[0][1] == "Diccik Webcam: Diccik" and dev[3][1] == "", str(dev))
expect("with no video devices at all it finds none", bv.webcam_devices(str(tmp / "nothing")) == [])
class Cam:
    def __init__(self, works): self.works, self.set_calls, self.released = works, [], False
    def set(self, prop, val): self.set_calls.append((prop, val))
    def isOpened(self): return True
    def read(self): return (self.works, np.zeros((480, 640, 3), np.uint8) if self.works else None)
    def release(self): self.released = True
made = {}
def factory(path): made[path] = Cam(path == "/dev/video3"); return made[path]
got = bv.open_camera(640, 480, devices=dev, capture=factory)
expect("it opens the first device that really gives a picture: video2 gives none (a webcam also makes a metadata device), so it is released and video3 is used", got is not None and got[1] == "/dev/video3" and made["/dev/video2"].released and not made["/dev/video3"].released and "/dev/video10" not in made, str(got and got[1:]))
expect("the camera is asked for 640 x 480, to keep only the newest frame, and to switch autofocus off (as the capture tool did for the training pictures)", (cv2.CAP_PROP_FRAME_WIDTH, 640) in made["/dev/video3"].set_calls and (cv2.CAP_PROP_FRAME_HEIGHT, 480) in made["/dev/video3"].set_calls and (cv2.CAP_PROP_BUFFERSIZE, 1) in made["/dev/video3"].set_calls and (cv2.CAP_PROP_AUTOFOCUS, 0) in made["/dev/video3"].set_calls)
expect("if no device gives a picture, or there are none, the answer is None", bv.open_camera(devices=dev, capture=lambda p: Cam(False)) is None and bv.open_camera(devices=[], capture=factory) is None)
props = [c[0] for c in made["/dev/video3"].set_calls]
expect("by default it does NOT ask for a picture format or a frame rate (the camera chooses)", cv2.CAP_PROP_FOURCC not in props and cv2.CAP_PROP_FPS not in props)
made.clear(); bv.open_camera(640, 480, devices=dev, capture=factory, fourcc="MJPG", fps=30); calls = made["/dev/video3"].set_calls; props = [c[0] for c in calls]
expect("asked for MJPG at 30 frames a second, it requests the format FIRST (before the size, which is the order V4L2 wants) and then the frame rate", calls[0] == (cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")) and props.index(cv2.CAP_PROP_FOURCC) < props.index(cv2.CAP_PROP_FRAME_WIDTH) and (cv2.CAP_PROP_FPS, 30) in calls, str(calls[:3]))
class Reporting:
    def get(self, prop): return {cv2.CAP_PROP_FRAME_WIDTH: 640, cv2.CAP_PROP_FRAME_HEIGHT: 480, cv2.CAP_PROP_FPS: 30.0, cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*"MJPG")}[prop]
rep = bv.camera_report(Reporting())
expect("what the camera says it agreed to is read back: format, size and frame rate, as plain words", rep == {"format": "MJPG", "width": 640, "height": 480, "fps_says": 30.0} and bv.format_text(rep) == "MJPG 640x480, the camera says 30.0 fps", bv.format_text(rep))
class NoFps(Reporting):
    def get(self, prop): return 0.0 if prop == cv2.CAP_PROP_FPS else super().get(prop)
expect("a camera that gives no frame rate is reported as that, and one that cannot report at all gives nothing (no crash)", bv.format_text(bv.camera_report(NoFps())).endswith("no frame rate") and bv.camera_report(object()) == {} and bv.format_text({}) == "")
expect("camera format codes are turned into their letters, and rubbish into nothing", bv.decode_fourcc(cv2.VideoWriter_fourcc(*"YUYV")) == "YUYV" and bv.decode_fourcc(0) == "" and bv.decode_fourcc("x") == "")

print("6. reading the camera in the background")
class StreamCam:
    def __init__(self): self.n, self.released = 0, False
    def read(self):
        threading.Event().wait(0.002); self.n += 1
        return True, np.full((48, 64, 3), self.n % 250, np.uint8)
    def release(self): self.released = True
sc = StreamCam(); ct = bv.CameraThread(sc).start(); threading.Event().wait(0.3)
latest = ct.read_latest(); seq1 = latest[1]; threading.Event().wait(0.1); seq2 = ct.read_latest()[1]
expect("it keeps reading: newer frames keep arriving, and it reports about how many a second (%.0f)" % ct.fps(), seq2 > seq1 >= 1 and ct.fps() > 20)
expect("it hands out the NEWEST frame with its number and when it was taken", latest[0].shape == (48, 64, 3) and latest[2] > 0)
ct.stop(); n_after = sc.n; threading.Event().wait(0.1)
expect("stop() ends the reading and releases the camera", sc.released and sc.n == n_after)
class DeadCam:
    released = False
    def read(self): return False, None
    def release(self): self.released = True
real_sleep = time.sleep; time.sleep = lambda s: None
dc = bv.CameraThread(DeadCam()).start(); threading.Event().wait(0.3); time.sleep = real_sleep
expect("a camera that stops giving pictures is declared LOST after 50 failed reads in a row, and there is no frame to hand out", dc.lost and dc.read_latest() is None); dc.stop()

print("7. timing")
b = bv.benchmark(SeqPipeline(), f, bv.default_roi((640, 480)), n=100)
expect("the first call (which sets things up) is not counted; for steps taking 1 to 100 ms: median 50.5, 95th percentile 95, worst 100, total median 51.0, about 19.6 steps a second", b["n"] == 100 and b["infer_median_ms"] == 50.5 and b["infer_p95_ms"] == 95.0 and b["infer_max_ms"] == 100.0 and b["prep_median_ms"] == 0.5 and b["total_median_ms"] == 51.0 and b["fps_estimate"] == 19.6, str(b))
b = bv.benchmark(real, f, bv.default_roi((640, 480)), n=20)
expect("on the real network it gives sensible numbers (median %.2f ms, worst %.2f ms: here, not on the board)" % (b["infer_median_ms"], b["infer_max_ms"]), 0 < b["infer_median_ms"] <= b["infer_p95_ms"] <= b["infer_max_ms"] and b["total_median_ms"] >= b["infer_median_ms"])
mi = bv.machine_info(); expect("it also records what machine, Python, NumPy and OpenCV the numbers are from, so laptop and board can be compared", set(mi) == {"machine", "python", "numpy", "opencv"} and all(mi.values()))

print("8. the app's logic with no camera")
clock = Clock(); fb = bv.FingerBoard(FakePipeline(), tmp / "a_roi.json", csv_path=tmp / "a_speed.csv", now=clock, clock=lambda: datetime.datetime(2026, 11, 16, 1, 40, 0))
v = fb.view()
expect("with no camera the page is told so: no picture, the camera is not ok, and the square is the training square", v["jpg"] is None and v["crop"] is None and v["camera"]["ok"] is False and v["probs"] is None and v["roi"] == {"x": 108, "y": 163, "side": 317} and v["roi_source"] == "the training square")
expect("there is nothing to step on, and no picture to find tape in or to benchmark on", fb.step() is False)
try: fb.find_tape("blue"); w = False
except ValueError as e: w = "no camera picture" in str(e)
expect("looking for the tape with no picture is refused with a clear message", w)
row = fb.benchmark(5)
expect("the speed can still be measured with no camera, on the made-up picture, and the row says so, with the machine details", row["what"] == "made-up picture" and row["frame"] == "640x480" and row["n"] == 5 and row["time"] == "01:40:00" and "numpy" in row and fb.benchmarking is False)
rows = list(csv.DictReader(open(tmp / "a_speed.csv", encoding="utf-8")))
expect("every benchmark is added to board_speed.csv with a header (%d row)" % len(rows), len(rows) == 1 and list(rows[0]) == bv.BENCH_FIELDS and rows[0]["what"] == "made-up picture")

print("9. the app's logic with a camera")
clock = Clock(); cam = FakeLatest(); fb = bv.FingerBoard(FakePipeline(), tmp / "b_roi.json", csv_path=tmp / "b_speed.csv", now=clock, clock=lambda: datetime.datetime(2026, 11, 16, 1, 41, 0))
fb.attach_camera(cam, "/dev/video3", "Diccik Webcam")
expect("with a camera but no frame yet there is still nothing to do", fb.step() is False and fb.view()["camera"]["ok"] is True and fb.view()["camera"]["path"] == "/dev/video3")
frame = frame_for("blob", 5); cam.push(frame, clock.t - 0.05)
expect("a new frame is processed once; the same frame again is not", fb.step() is True and fb.step() is False and fb.last["digit"] == 3)
expect("it knows how old the frame was when it was used (about 50 ms)", 40 <= fb.last["age_ms"] <= 60, "%.1f" % fb.last["age_ms"])
v = fb.view()
expect("the page gets a picture and the 64 x 64 crop the network sees, both real JPEGs, with the answer, the six probabilities and the timing", v["jpg"] and v["crop"] and v["digit"] == 3 and len(v["probs"]) == 6 and abs(sum(v["probs"]) - 1) < 1e-3 and v["timing"]["prep_ms"] == 1.0 and v["timing"]["infer_ms"] == 4.0 and v["stable"] is None)
jp = cv2.imdecode(np.frombuffer(__import__("base64").b64decode(v["jpg"]), np.uint8), cv2.IMREAD_COLOR); cr = cv2.imdecode(np.frombuffer(__import__("base64").b64decode(v["crop"]), np.uint8), cv2.IMREAD_COLOR)
expect("the camera picture is sent at 320 x 240 and the crop at 64 x 64 (the message stays small: %d bytes)" % len(json.dumps(v)), jp.shape == (240, 320, 3) and cr.shape == (64, 64, 3) and (v["jw"], v["jh"]) == (320, 240) and len(json.dumps(v)) < 60000)
for i in range(7):
    clock.t += 0.1; cam.push(frame, clock.t); fb.step()
expect("after 8 frames that all say 3 with confidence, the answer is STABLE: 3", fb.view()["stable"] == 3)
expect("the frames per second are worked out from the steps taken (about 10: one every 0.1 s)", 9.0 <= fb.view()["timing"]["fps"] <= 11.0, str(fb.view()["timing"]["fps"]))
fb._last_view = clock.t; expect("the page is sent a picture about 8 times a second: not yet due", fb.view_due() is False); clock.t += 0.13; expect("... and due after 0.13 s", fb.view_due() is True)
fb.nudge(10, -5, 4)
expect("moving the square works and is kept inside the picture; the answer starts afresh and the page is told the square is not saved yet", fb.roi == bv.Roi(118, 158, 321) and fb.smoother.stable() is None and "not saved" in fb.roi_source, str(fb.roi))
fb.nudge(9999, 9999, 0); expect("moving it far away just stops at the edge of the picture", fb.roi.x + fb.roi.side <= 640 and fb.roi.y + fb.roi.side <= 480)
fb.nudge(0, 0, -9999); expect("making it tiny stops at 8 pixels", fb.roi.side == 8)
fb.reset_roi(); expect("reset goes back to the training square", fb.roi == bv.Roi(108, 163, 317) and fb.roi_source == "the training square")
fb.nudge(-8, 3, 0); fb.save_roi(); saved = json.loads((tmp / "b_roi.json").read_text())      # (the training square already touches the bottom of the picture, so it cannot go down)
expect("saving writes the square with the camera size it belongs to, and the page is told it is saved", saved == {"x": 100, "y": 163, "side": 317, "frame_width": 640, "frame_height": 480} and fb.roi_source == "saved", str(saved))
fb2 = bv.FingerBoard(FakePipeline(), tmp / "b_roi.json", now=clock)
expect("the next start uses the saved square", fb2.roi == bv.Roi(100, 163, 317) and fb2.roi_source == "saved")
fb3 = bv.FingerBoard(FakePipeline(), tmp / "b_roi.json", now=clock, frame_size=(320, 240))
expect("... but not for a camera of another size", fb3.roi == bv.default_roi((320, 240)) and fb3.roi_source == "the training square")
cam.push(tape_frame(), clock.t); fb.step(); r = fb.find_tape("blue")
expect("'find the tape' puts the square inside the blue tape and says where it came from", abs(r.x - 166) <= 4 and fb.roi == r and "blue tape" in fb.roi_source)
cam.push(np.full((480, 640, 3), 90, np.uint8), clock.t); fb.step()
try: fb.find_tape("blue"); w = False
except ValueError as e: w = "arrow keys" in str(e) and "blue" in str(e)
expect("if there is no tape in the picture the message says to move the square by hand instead", w)
cam.push(np.zeros((240, 320, 3), np.uint8), clock.t); fb.reset_roi(); fb.frame_size = (640, 480); fb.step()
expect("if the camera gives another size than expected, the square that fits it is used (54, 82, 158 at 320 x 240) and it keeps working", fb.frame_size == (320, 240) and fb.roi == bv.Roi(54, 82, 158) and fb.last["digit"] == 3, str(fb.roi))
cam.push(frame, clock.t); fb.step(); fb.benchmarking = True; cam.push(frame, clock.t); n_times = len(fb.times)
expect("while a benchmark runs, the live steps pause (so the numbers are clean)", fb.step() is False and len(fb.times) == n_times); fb.benchmarking = False
row = fb.benchmark(5)
expect("with a camera the benchmark gives TWO rows: the standard made-up picture first (comparable between machines), then the camera picture, and the live steps resume afterwards (the frame that arrived meanwhile is processed)", row["what"] == "made-up picture" and [r["what"] for r in fb.bench_rows][-2:] == ["made-up picture", "camera picture"] and fb.benchmarking is False and fb.step() is True)

print("9b. the camera format setting")
fbm = bv.FingerBoard(FakePipeline(), tmp / "e_roi.json", now=Clock(), camera_path=tmp / "cam.json")
expect("the camera format to begin with is MJPG (compressed pictures need less of the USB hub, so the camera can usually go faster)", fbm.camera_settings == {"fourcc": "MJPG"} and fbm.view()["camera"]["mode"] == "MJPG")
cam_a = FakeLatest(frame_for("blob", 5)); fbm.attach_camera(cam_a, "/dev/video3", "X"); fbm._last_open_try = fbm.now()
fbm.set_camera_mode("YUYV")
expect("asking for another format is remembered in camera.json, closes the camera, forgets the old picture, and makes it reopen on the very next pass (not in 5 seconds)", fbm.camera_settings == {"fourcc": "YUYV"} and json.loads((tmp / "cam.json").read_text()) == {"fourcc": "YUYV"} and cam_a.stopped and fbm.camera is None and fbm.last is None and fbm.camera_info["ok"] is False and fbm.now() - fbm._last_open_try > 5.0)
opened = []; fbm.maintain(lambda: opened.append(1) or None)
expect("... the opener is called at once", opened == [1])
expect("the next start uses the remembered format", bv.FingerBoard(FakePipeline(), tmp / "e_roi.json", now=Clock(), camera_path=tmp / "cam.json").camera_settings == {"fourcc": "YUYV"})
(tmp / "cam.json").write_text("{nonsense"); expect("a damaged camera.json gives MJPG again", bv.FingerBoard(FakePipeline(), tmp / "e_roi.json", now=Clock(), camera_path=tmp / "cam.json").camera_settings == {"fourcc": "MJPG"})
(tmp / "cam.json").write_text(json.dumps({"fourcc": "WHAT"})); expect("an unknown format in the file gives MJPG again", bv.FingerBoard(FakePipeline(), tmp / "e_roi.json", now=Clock(), camera_path=tmp / "cam.json").camera_settings == {"fourcc": "MJPG"})
for good in ("MJPG", "YUYV", ""): fbm.set_camera_mode(good)
try: fbm.set_camera_mode("H264"); w = False
except ValueError as e: w = "MJPG, YUYV" in str(e)
expect("MJPG, YUYV and 'the camera chooses' are accepted, anything else is refused with a clear message", w and fbm.camera_settings == {"fourcc": ""})
class Rep(FakeLatest):
    def report(self): return {"format": "MJPG", "width": 640, "height": 480, "fps_says": 30.0}
fbr = bv.FingerBoard(FakePipeline(), tmp / "f_roi.json", now=Clock()); fbr.attach_camera(Rep(frame_for("blob", 5)), "/dev/video2", "icspring camera")
expect("the page is told what format the camera really gave", fbr.view()["camera"]["format"] == "MJPG 640x480, the camera says 30.0 fps")

print("9c. pausing the network (to see the camera's own speed)")
clock = Clock(); cam = FakeLatest(); fbp = bv.FingerBoard(FakePipeline(), tmp / "p_roi.json", now=clock); fbp.attach_camera(cam, "/dev/video2", "X")
for i in range(9):
    cam.push(frame_for("blob", 5), clock.t); fbp.step(); clock.t += 0.1
expect("before pausing: the network runs and the answer is steady", fbp.view()["stable"] == 3 and fbp.view()["paused"] is False and fbp.view()["timing"]["fps"] > 5)
fbp.set_paused(True); n_times = len(fbp.times); cam.push(frame_for("blob", 6), clock.t)
expect("pausing keeps reading the camera (the new picture is taken: step says True) but does NOT run the network (no new timing)", fbp.step() is True and len(fbp.times) == n_times and fbp.last["probs"] is None and fbp.smoother.stable() is None)
clock.t += 4.0; v = fbp.view()
expect("while paused the page still gets the live picture and the crop, but no answer, and the network steps a second fall to 0", v["jpg"] and v["crop"] and v["probs"] is None and v["digit"] is None and v["stable"] is None and v["paused"] is True and v["timing"]["fps"] == 0.0)
row = fbp.benchmark(3); expect("the speed can still be measured while paused (on the standard picture and the newest camera picture)", row["what"] == "made-up picture" and [r["what"] for r in fbp.bench_rows][-1] == "camera picture")
fbp.set_paused(False); cam.push(frame_for("blob", 5), clock.t); expect("resuming runs the network again", fbp.step() is True and fbp.last["probs"] is not None and fbp.view()["paused"] is False)

print("10. a camera that is missing, plugged in later, or lost")
clock = Clock(); fb = bv.FingerBoard(FakePipeline(), tmp / "c_roi.json", now=clock); calls = []
def opener_none(): calls.append(1); return None
fb.maintain(opener_none); fb.maintain(opener_none)
expect("with no camera it tries to open one, but only every 5 seconds, not on every pass", len(calls) == 1 and fb.camera is None and fb.view()["camera"]["ok"] is False)
clock.t += 5.1; fb.maintain(opener_none); expect("... and tries again after 5 seconds", len(calls) == 2)
clock.t += 5.1; fb.maintain(lambda: (StreamCam(), "/dev/video3", "Plugged in later")); threading.Event().wait(0.1)
expect("a camera plugged in later is picked up, and then the live steps start", fb.camera is not None and fb.camera_info["ok"] and fb.camera_info["name"] == "Plugged in later" and fb.camera.read_latest() is not None)
old = fb.camera; old.lost = True; clock.t += 5.1; fb.maintain(lambda: (StreamCam(), "/dev/video4", "Replug"))
expect("a camera that was lost is stopped and replaced when a new one appears", fb.camera is not old and fb.camera_info["path"] == "/dev/video4" and old._stop.is_set()); fb.camera.stop()
fb = bv.FingerBoard(FakePipeline(), tmp / "d_roi.json", now=clock); lostcam = FakeLatest(frame_for("blob", 5)); fb.attach_camera(lostcam, "/dev/video3", "X"); lostcam.lost = True; fb.maintain(None)
expect("when the camera is lost the page is told (so it can say so) while the last picture stays", fb.view()["camera"]["ok"] is False and fb.view()["camera"]["lost"] is True)

print("11. main.py is wired to the page")
log = {"loop": None, "handlers": {}, "messages": []}
class App:
    @staticmethod
    def run(user_loop=None): log["loop"] = user_loop
class WebUI:
    def on_message(self, kind, fn): log["handlers"][kind] = fn
    def on_connect(self, fn): log["handlers"]["connect"] = fn
    def send_message(self, kind, msg, room=None): log["messages"].append((kind, msg))
u = types.ModuleType("arduino.app_utils"); u.App, u.Bridge = App, object()
w = types.ModuleType("arduino.app_bricks.web_ui"); w.WebUI = WebUI
sys.modules.update({"arduino": types.ModuleType("arduino"), "arduino.app_utils": u, "arduino.app_bricks": types.ModuleType("arduino.app_bricks"), "arduino.app_bricks.web_ui": w})
class MainCam:
    def __init__(self, frame): self.frame, self.released = frame, False
    def read(self):
        threading.Event().wait(0.003); return True, self.frame.copy()
    def release(self): self.released = True
current = {"frame": tape_frame()}
orig_open = bv.open_camera; opened_with = []
bv.open_camera = lambda w_, h_, **kw: (opened_with.append(kw) or MainCam(current["frame"]), "/dev/video3", "Fake webcam")
spec = importlib.util.spec_from_file_location("finger_main", PY / "main.py"); main = importlib.util.module_from_spec(spec); spec.loader.exec_module(main)
main.board.roi_path = tmp / "m_roi.json"; main.board.csv_path = tmp / "m_speed.csv"
cmd = lambda d: log["handlers"]["cmd"]("sid", d)
last = lambda kind: [m for k, m in log["messages"] if k == kind][-1]
def run_until(cond, seconds=3.0):
    end = time.time() + seconds
    while time.time() < end:
        log["loop"]()
        if cond(): return True
    return False
expect("main.py loaded the real network, listens for page commands, and hands its loop to the app", main.board.pipeline.size == 64 and "cmd" in log["handlers"] and "connect" in log["handlers"] and callable(log["loop"]))
log["handlers"]["connect"]("sid"); expect("a page that connects is sent the view and the benchmark table at once", log["messages"][-2][0] == "view" and log["messages"][-1][0] == "bench" and last("view")["camera"]["ok"] is False)
ok = run_until(lambda: main.board.last is not None)
expect("the loop opens the camera by itself, then the network runs on its pictures", ok and main.board.camera_info["path"] == "/dev/video3" and main.board.last["digit"] in range(6))
n = len([1 for k, m in log["messages"] if k == "view"]); log["loop"](); log["loop"](); n2 = len([1 for k, m in log["messages"] if k == "view"])
expect("the page is sent pictures at a limited rate, not on every pass of the loop (%d new in 2 quick passes)" % (n2 - n), n2 - n <= 1)
cmd({"action": "nudge", "dx": 10, "dy": 0, "ds": 0}); v = last("view")
expect("'nudge' moves the square and sends the page a new view at once", v["roi"]["x"] == 118 and "not saved" in v["roi_source"])
cmd({"action": "find_tape", "color": "blue"})
expect("'find_tape' puts the square on the tape in the camera picture and says so", last("notice")["level"] == "ok" and "Found a blue square" in last("notice")["text"] and abs(last("view")["roi"]["x"] - 166) <= 4, last("notice")["text"][:70])
cmd({"action": "find_tape", "color": "green"}); expect("no tape of that colour: a warning that says what to do", last("notice")["level"] == "warn" and "arrow keys" in last("notice")["text"])
cmd({"action": "save_roi"}); expect("'save_roi' saves it and says so", last("notice")["level"] == "ok" and (tmp / "m_roi.json").exists() and last("view")["roi_source"] == "saved")
cmd({"action": "reset_roi"}); expect("'reset_roi' goes back to the training square", last("view")["roi"] == {"x": 108, "y": 163, "side": 317})
expect("the camera was opened asking for MJPG at 30 frames a second", opened_with and opened_with[0] == {"fourcc": "MJPG", "fps": 30}, str(opened_with[:1]))
main.board.camera_path = tmp / "m_cam.json"; n_open = len(opened_with); cmd({"action": "camera_mode", "fourcc": "YUYV"})
expect("'camera_mode' switches the format, tells the page what is happening, and the camera is closed to be reopened", last("notice")["level"] == "info" and "YUYV" in last("notice")["text"] and last("view")["camera"]["mode"] == "YUYV" and main.board.camera is None)
ok = run_until(lambda: main.board.last is not None and len(opened_with) > n_open)
expect("the loop reopens it at once, now asking for YUYV, and the pictures flow again", ok and opened_with[-1] == {"fourcc": "YUYV", "fps": 30}, str(opened_with[-1:]))
cmd({"action": "camera_mode", "fourcc": ""}); run_until(lambda: len(opened_with) > n_open + 1)
expect("'the camera chooses' asks for no format at all (but still the frame rate)", opened_with[-1] == {"fourcc": None, "fps": 30}, str(opened_with[-1:]))
cmd({"action": "camera_mode", "fourcc": "H264"}); expect("an unknown format is a warning", last("notice")["level"] == "warn" and "MJPG, YUYV" in last("notice")["text"])
cmd({"action": "camera_mode", "fourcc": "MJPG"}); run_until(lambda: main.board.last is not None)
cmd({"action": "pause", "paused": True}); v = last("view")
expect("'pause' pauses the network and tells the page, with the camera still shown", main.board.paused and v["paused"] is True and last("notice")["level"] == "info" and "camera's own speed" in last("notice")["text"])
run_until(lambda: main.board.last is not None and main.board.last["probs"] is None); expect("the loop keeps taking camera pictures while paused, without answers", main.board.last["probs"] is None and main.board.last["frame"] is not None)
cmd({"action": "pause", "paused": False}); expect("'pause' with false resumes it", not main.board.paused and "running again" in last("notice")["text"])
run_until(lambda: main.board.last is not None and main.board.last["probs"] is not None)
cmd({"action": "benchmark"}); notes = [m["text"] for k, m in log["messages"] if k == "notice"][-2:]
expect("'benchmark' says it is measuring, then gives the numbers in plain words (on the standard picture), and sends the table with the standard row and the camera row", notes[0].startswith("Measuring") and "ms" in notes[1] and "steps a second" in notes[1] and "made-up" in notes[1] and [r["what"] for r in last("bench")["rows"]] == ["made-up picture", "camera picture"], notes[1][:90])
rows = list(csv.DictReader(open(tmp / "m_speed.csv", encoding="utf-8"))); expect("... and both are added to board_speed.csv", len(rows) == 2)
cmd({"action": "refresh"}); expect("'refresh' sends the view and the table", log["messages"][-2][0] == "view" and log["messages"][-1][0] == "bench")
cmd({"action": "dance"}); expect("an unknown command is a warning", last("notice")["level"] == "warn" and "Unknown" in last("notice")["text"])
cmd(None); expect("a command with no data does not crash it", last("notice")["level"] == "warn")
main.board.find_tape = lambda color: (_ for _ in ()).throw(RuntimeError("boom")); cmd({"action": "find_tape"})
expect("an unexpected error becomes a warning, and the app carries on", last("notice")["level"] == "warn" and "went wrong" in last("notice")["text"])
main.board.camera.stop(); bv.open_camera = orig_open

# the real messages, for the page test
clock = Clock(); cam = FakeLatest(); fbs = bv.FingerBoard(real, tmp / "s_roi.json", csv_path=tmp / "s_speed.csv", now=clock, clock=lambda: datetime.datetime(2026, 11, 16, 1, 45, 0))
no_camera = fbs.view()
fbs.attach_camera(cam, "/dev/video3", "Diccik Webcam: Diccik")
for i in range(9):
    cam.push(frame_for("blob", 5), clock.t); fbs.step(); clock.t += 0.1
steady = fbs.view()
unsure = dict(steady, probs=[.2, .3, .1, .2, .1, .1], digit=1, stable=None)
paused = dict(steady, probs=None, digit=None, stable=None, paused=True, timing=dict(steady["timing"], fps=0.0))
lost = dict(steady, camera=dict(steady["camera"], ok=False, lost=True))
benchmarking = dict(steady, benchmarking=True)
fbs.camera = None; fbs.last = None; fbs.benchmark(5); fbs.attach_camera(cam, "/dev/video3", "X"); cam.push(frame_for("blob", 5), clock.t); fbs.step(); fbs.benchmark(5)      # 1 row with no camera, then 2 rows with one
(HERE / "state_samples.json").write_text(json.dumps({"no_camera": no_camera, "steady": steady, "unsure": unsure, "lost": lost, "benchmarking": benchmarking, "paused": paused, "bench_rows": fbs.bench_rows}))
expect("the real messages for the page test are written (steady digit %s, %d benchmark rows)" % (steady["stable"], len(fbs.bench_rows)), steady["stable"] == 5 and steady["jpg"] and len(fbs.bench_rows) == 3 and no_camera["jpg"] is None)

print("12. the laptop benchmark script")
import subprocess
res = subprocess.run([sys.executable, str(HERE.parent / "compare" / "bench_numpy.py"), "--n", "5", "--csv", str(tmp / "laptop.csv")], capture_output=True, text=True)
lines = res.stdout.splitlines()
expect("compare/bench_numpy.py runs and prints the time of cutting out the square, the network and one whole step, and what machine it ran on", res.returncode == 0 and any("the network" in l for l in lines) and any("one whole step" in l and "steps a second" in l for l in lines) and any("Python" in l and "NumPy" in l for l in lines), (res.stderr or "")[:150])
rows = list(csv.DictReader(open(tmp / "laptop.csv", encoding="utf-8")))
expect("it adds a row to a CSV in the same columns as the board's, for the same standard picture, so the two can be compared", len(rows) == 1 and list(rows[0]) == bv.BENCH_FIELDS and rows[0]["what"] == "made-up picture" and rows[0]["frame"] == "640x480" and float(rows[0]["total_median_ms"]) > 0)

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
