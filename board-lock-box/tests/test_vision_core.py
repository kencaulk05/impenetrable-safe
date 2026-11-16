"""The vision part of the lock box (python/board_vision.py, the same code as the finger-count app): the network against the original, the square, the tape, the camera.   python test_vision_core.py
Needs numpy and opencv (cv2). It also writes view_samples.json: the real camera messages the app sends to the page, which test_page.js then renders."""
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

print("7. the camera and the answer, as the page gets them (a short check: the finger-count app has the full set for this same code)")
clock = Clock(); cam = FakeLatest(); fb = bv.FingerBoard(real, tmp / "x_roi.json", now=clock, camera_path=tmp / "x_cam.json"); fb.attach_camera(cam, "/dev/video2", "icspring camera")
expect("before any picture the page is told there is none, the camera is ok, and the square is the training square", fb.view()["jpg"] is None and fb.view()["camera"]["ok"] is True and fb.view()["roi"] == {"x": 108, "y": 163, "side": 317})
for i in range(9):
    cam.push(frame_for("blob", 5), clock.t); fb.step(); clock.t += 0.1
v = fb.view()
expect("with pictures it gives the picture, the crop, the answer, the six probabilities and a STEADY answer after 8 pictures that agree", v["jpg"] and v["crop"] and v["digit"] == 5 and v["stable"] == 5 and len(v["probs"]) == 6 and abs(sum(v["probs"]) - 1) < 1e-3)
fb.nudge(-8, 0, 0); fb.save_roi(); fb2 = bv.FingerBoard(real, tmp / "x_roi.json", now=clock)
expect("moving the square and saving it works, and the next start uses it", fb2.roi == bv.Roi(100, 163, 317) and fb2.roi_source == "saved")
fb.set_camera_mode("YUYV"); expect("the camera format can be changed and is remembered, and the camera is closed to be reopened", fb.camera_settings == {"fourcc": "YUYV"} and cam.stopped and fb.camera is None)

# the real camera messages, for the page test
clock = Clock(); cam = FakeLatest(); fbs = bv.FingerBoard(real, tmp / "s_roi.json", now=clock)
no_camera = fbs.view(); fbs.attach_camera(cam, "/dev/video2", "icspring camera: icspring camer")
for i in range(9):
    cam.push(frame_for("blob", 5), clock.t); fbs.step(); clock.t += 0.1
steady = fbs.view(); unsure = dict(steady, probs=[.2, .3, .1, .2, .1, .1], digit=1, stable=None); lost = dict(steady, camera=dict(steady["camera"], ok=False, lost=True))
(HERE / "view_samples.json").write_text(json.dumps({"no_camera": no_camera, "steady": steady, "unsure": unsure, "lost": lost}))
expect("the real camera messages for the page test are written (a steady %s)" % steady["stable"], steady["stable"] == 5 and steady["jpg"] and no_camera["jpg"] is None)

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
