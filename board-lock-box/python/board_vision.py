"""Everything the finger-count app does with a camera picture, with no board library in it, so it can be tested on any computer.

The steps are the ones the network was trained with (copied from the finger-lock project, and checked against it by tests/golden.json):
    camera frame -> cut out the square -> shrink to 128 x 128 -> shrink to 64 x 64 -> swap blue and red (OpenCV is BGR, the network learned RGB) -> the network
The network itself is infer_numpy.py (plain NumPy, no PyTorch on the board).
"""
import base64
import csv
import datetime
import json
import platform
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from infer_numpy import NumpyFingerCNN

SAVE_SIZE = 128                       # crops were saved at 128 x 128 for training, then shrunk to the network's size (64)
TRAINING_FRAME = (640, 480)           # the camera size the 2,400 training pictures were taken at
TRAINING_ROI = (108, 163, 317)        # x, y, side of the blue-tape square at that size
TAPE = ("red", "blue", "green", "yellow")
TAPE_HSV = {"red": (((0, 110, 70), (10, 255, 255)), ((170, 110, 70), (180, 255, 255))),        # red wraps around the colour wheel, so it needs two ranges
            "blue": (((95, 90, 60), (130, 255, 255)),), "green": (((40, 80, 60), (85, 255, 255)),), "yellow": (((18, 100, 100), (35, 255, 255)),)}
FOURCCS = ("MJPG", "YUYV", "")           # the camera formats the page can ask for ("" = whatever the camera chooses)
BENCH_FIELDS = ["time", "what", "frame", "n", "prep_median_ms", "infer_median_ms", "infer_p95_ms", "infer_max_ms", "total_median_ms", "fps_estimate", "machine", "python", "numpy", "opencv"]


# ---------------------------------------------------------------------------------------------------------------------------- the square
@dataclass
class Roi:
    """A square region of the camera image: top-left corner and side, in pixels."""
    x: int
    y: int
    side: int

    def clipped(self, w, h):
        side = max(8, min(self.side, w, h))
        return Roi(int(min(max(self.x, 0), w - side)), int(min(max(self.y, 0), h - side)), int(side))

    def to_json(self):
        return {"x": self.x, "y": self.y, "side": self.side}

    @classmethod
    def from_json(cls, d):
        return cls(int(d["x"]), int(d["y"]), int(d["side"]))


def save_roi(roi, path, frame_size):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({**roi.to_json(), "frame_width": int(frame_size[0]), "frame_height": int(frame_size[1])}), encoding="utf-8")


def load_roi(path, frame_size=None):
    """The saved square, or None. If it was saved for a different camera size it is refused, because the pixels would mean something else."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if frame_size is not None and (d.get("frame_width"), d.get("frame_height")) != (int(frame_size[0]), int(frame_size[1])):
            return None
        return Roi.from_json(d)
    except (ValueError, KeyError, TypeError, OSError):
        return None


def default_roi(frame_size):
    """The square the network was trained on (at the training camera size), scaled to this camera size if the shape is the same, else a square in the middle."""
    w, h = frame_size
    if (w, h) == TRAINING_FRAME:
        x, y, s = TRAINING_ROI
    elif abs(w / h - 4 / 3) < 0.02:
        k = w / float(TRAINING_FRAME[0])
        x, y, s = (int(round(v * k)) for v in TRAINING_ROI)
    else:
        s = int(min(w, h) * 0.66)
        x, y = (w - s) // 2, (h - s) // 2
    return Roi(x, y, s).clipped(w, h)


def crop(frame, roi, size=SAVE_SIZE):
    """The inside of the square, resized to size x size (INTER_AREA, the right way to shrink)."""
    h, w = frame.shape[:2]
    r = roi.clipped(w, h)
    return cv2.resize(frame[r.y:r.y + r.side, r.x:r.x + r.side], (size, size), interpolation=cv2.INTER_AREA)


def find_square(frame, color="blue", inset=0.07, min_area_fraction=0.02):
    """Look for a square of tape (red, blue, green or yellow). Returns the Roi INSIDE it (inset by a margin so the tape itself is left out), or None."""
    if color not in TAPE_HSV:
        raise ValueError("tape colour must be one of %s" % (TAPE,))
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = np.zeros((h, w), np.uint8)
    for lo, hi in TAPE_HSV[color]:
        mask |= cv2.inRange(hsv, lo, hi)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw * bh < min_area_fraction * w * h or bw * bh > 0.6 * w * h or not 0.8 <= bw / bh <= 1.25:
            continue                                             # too small, too big, or not roughly square
        if best is None or bw * bh > best[2] * best[3]:
            best = (x, y, bw, bh)
    if best is None:
        return None
    x, y, bw, bh = best
    side = max(bw, bh)
    m = int(round(side * inset))
    return Roi(x + m, y + m, side - 2 * m).clipped(w, h)


# ---------------------------------------------------------------------------------------------------------------------------- the network
class Pipeline:
    """A camera frame in, the number of fingers out (the same steps as the training pictures went through)."""

    def __init__(self, model_path):
        self.net = NumpyFingerCNN.load(model_path)
        self.size, self.gray = int(self.net.meta["size"]), bool(self.net.meta["gray"])

    def preprocess(self, frame, roi):
        c = crop(frame, roi, SAVE_SIZE)
        if self.gray:
            c = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY)
        img = cv2.resize(c, (self.size, self.size), interpolation=cv2.INTER_AREA)
        return np.ascontiguousarray(img[:, :, None] if self.gray else img[:, :, ::-1])

    def predict(self, frame, roi):
        """(the most likely number of fingers, the six probabilities, {'prep_ms', 'infer_ms'}): how long cutting the picture out and running the network each took."""
        t0 = time.perf_counter()
        img = self.preprocess(frame, roi)
        t1 = time.perf_counter()
        digit, probs = self.net.predict(img)
        t2 = time.perf_counter()
        return digit, probs, {"prep_ms": (t1 - t0) * 1000.0, "infer_ms": (t2 - t1) * 1000.0}


class Smoother:
    """The last few answers, averaged. A number is called STABLE only when the average probability is high enough and most of the recent frames agree."""

    def __init__(self, n=8, min_prob=0.6, min_agree=0.75):
        self.n, self.min_prob, self.min_agree = n, min_prob, min_agree
        self.buf = deque(maxlen=n)

    def add(self, probs):
        self.buf.append(np.asarray(probs, dtype=float))

    def mean(self):
        buf = list(self.buf)                                  # a copy: another thread may be adding to it
        return np.mean(buf, axis=0) if buf else np.zeros(6)

    def stable(self):
        buf = list(self.buf)
        if len(buf) < self.n:
            return None
        m = np.mean(buf, axis=0)
        cls = int(m.argmax())
        agree = float(np.mean([int(p.argmax()) == cls for p in buf]))
        return cls if m[cls] >= self.min_prob and agree >= self.min_agree else None

    def reset(self):
        self.buf.clear()


def synthetic_frame(w=640, h=480, seed=1):
    """A fixed made-up camera picture (smooth colours and some noise), so that the speed can be measured the same way on every machine, with or without a camera."""
    rs = np.random.RandomState(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    f = np.stack([120 + 80 * np.sin(xx / 97.0), 110 + 70 * np.cos(yy / 71.0), 100 + 60 * np.sin((xx + yy) / 131.0)], axis=2) + rs.normal(0, 8, (h, w, 3))
    return np.clip(f, 0, 255).astype(np.uint8)


def benchmark(pipeline, frame, roi, n=100):
    """How long one step takes (cutting out the square, and running the network), n times over: the median, the 95th percentile and the worst."""
    pipeline.predict(frame, roi)                                  # the first call is slower (it sets things up): not counted
    prep, infer = [], []
    for _ in range(n):
        _, _, t = pipeline.predict(frame, roi)
        prep.append(t["prep_ms"]); infer.append(t["infer_ms"])
    total = [a + b for a, b in zip(prep, infer)]
    s = sorted(infer)
    med = statistics.median(total)
    return {"n": n, "prep_median_ms": round(statistics.median(prep), 2), "infer_median_ms": round(statistics.median(infer), 2),
            "infer_p95_ms": round(s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))], 2), "infer_max_ms": round(max(infer), 2),
            "total_median_ms": round(med, 2), "fps_estimate": round(1000.0 / med, 1) if med > 0 else None}


def machine_info():
    return {"machine": platform.machine() or platform.processor() or "?", "python": platform.python_version(), "numpy": np.__version__, "opencv": cv2.__version__}


# ---------------------------------------------------------------------------------------------------------------------------- the camera
def webcam_devices(root="/sys/class/video4linux"):
    """/dev/videoN paths that aren't the board's built-in qcom-venus encoder/decoder (as in the sumo app, which found the webcam this way on this board)."""
    found = []
    base = Path(root)
    if not base.exists():
        return found
    for d in sorted(base.glob("video*"), key=lambda p: int(p.name[5:]) if p.name[5:].isdigit() else 999):
        name = (d / "name").read_text().strip() if (d / "name").exists() else ""
        if "venus" not in name:
            found.append(("/dev/" + d.name, name))
    return found


def open_camera(width=640, height=480, devices=None, capture=None, fourcc=None, fps=None):
    """Open the first webcam device that actually gives a frame (a USB webcam also makes a metadata device that can't). Returns (camera, path, name) or None.
    fourcc ("MJPG" or "YUYV") asks for that picture format, fps for that frame rate: both are only requests, a camera may refuse them."""
    capture = capture or (lambda path: cv2.VideoCapture(path, cv2.CAP_V4L2))
    for path, name in (devices if devices is not None else webcam_devices()):
        cam = capture(path)
        if fourcc:
            cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))      # the format is asked for BEFORE the size, which is the order V4L2 wants
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)                       # keep only the newest frame, so the picture is never old
        cam.set(cv2.CAP_PROP_AUTOFOCUS, 0)                        # the capture tool switched autofocus off when the training pictures were taken (best effort: not every camera allows it)
        if fps:
            cam.set(cv2.CAP_PROP_FPS, fps)
        if cam.isOpened() and cam.read()[0]:
            return cam, path, name
        cam.release()
    return None


def decode_fourcc(v):
    """The 4 letters of a camera format code (for example MJPG), or "" if it is not letters."""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return ""
    s = "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))
    return s if s.isprintable() and s.strip() else ""


def camera_report(cam):
    """What the camera says it agreed to (format, size, frame rate). This is what the driver REPORTS: the pictures per second really arriving are counted separately."""
    try:
        w, h = int(cam.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT))
        f, code = float(cam.get(cv2.CAP_PROP_FPS)), decode_fourcc(cam.get(cv2.CAP_PROP_FOURCC))
    except Exception:
        return {}
    return {"format": code, "width": w, "height": h, "fps_says": round(f, 1) if f > 0 else None}


def format_text(rep):
    if not rep:
        return ""
    return "%s %dx%d, the camera says %s" % (rep.get("format") or "?", rep.get("width", 0), rep.get("height", 0), "%s fps" % rep["fps_says"] if rep.get("fps_says") else "no frame rate")


class CameraThread:
    """Reads the camera all the time in the background and keeps only the newest frame, so the network always looks at what is in front of the camera NOW."""

    def __init__(self, cam, now=time.monotonic):
        self.cam, self.now = cam, now
        self._lock = threading.Lock()
        self._frame, self._seq, self._t = None, 0, 0.0
        self._stamps = deque(maxlen=90)
        self.failures, self.lost = 0, False
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self):
        while not self._stop.is_set():
            ok, frame = self.cam.read()
            if ok and frame is not None:
                t = self.now()
                with self._lock:
                    self._frame, self._seq, self._t = frame, self._seq + 1, t
                    self._stamps.append(t)
                self.failures = 0
            else:
                self.failures += 1
                if self.failures >= 50:
                    self.lost = True
                time.sleep(0.02)

    def read_latest(self):
        """(the newest frame, its number, when it was taken) or None if there is no frame yet."""
        with self._lock:
            return (self._frame, self._seq, self._t) if self._frame is not None else None

    def report(self):
        return camera_report(self.cam)

    def fps(self, window=3.0):
        with self._lock:
            t = self.now()
            s = [x for x in self._stamps if t - x <= window]
        return round((len(s) - 1) / (s[-1] - s[0]), 1) if len(s) >= 2 and s[-1] > s[0] else 0.0

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        try:
            self.cam.release()
        except Exception:
            pass


def to_jpeg_b64(img_bgr, quality=70):
    ok, jpg = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(jpg.tobytes()).decode("ascii") if ok else None


# ---------------------------------------------------------------------------------------------------------------------------- the app's logic
class FingerBoard:
    """The camera, the square, the network and the steadiness check, and what the web page shows."""
    VIEW_EVERY_S = 0.125                   # the page gets about 8 pictures a second
    REOPEN_EVERY_S = 5.0

    def __init__(self, pipeline, roi_path, csv_path=None, now=time.monotonic, clock=datetime.datetime.now, frame_size=TRAINING_FRAME, camera_path=None):
        self.pipeline, self.roi_path, self.csv_path, self.now, self.clock, self.camera_path = pipeline, roi_path, csv_path, now, clock, camera_path
        self.camera_settings = self._load_camera_settings()
        self.camera, self.camera_info = None, {"ok": False, "path": "", "name": ""}
        self.frame_size = tuple(frame_size)
        self.roi, self.roi_source = None, ""
        self._pick_roi()
        self.smoother = Smoother()
        self.last = None
        self.times = deque(maxlen=90)       # (when, prep_ms, infer_ms) of the steps taken
        self.bench_rows = []
        self.benchmarking = False
        self.paused = False                 # the network is paused: the camera is still read and shown, so its own speed can be seen
        self._seq, self._last_view, self._last_open_try = -1, -1e9, -1e9

    def _load_camera_settings(self):
        """The camera format asked for last time (MJPG to begin with: compressed pictures need less of the USB hub, so the camera can usually go faster)."""
        try:
            f = json.loads(Path(self.camera_path).read_text(encoding="utf-8")).get("fourcc") if self.camera_path else None
        except (ValueError, OSError, AttributeError):
            f = None
        return {"fourcc": f if f in FOURCCS else "MJPG"}

    def set_camera_mode(self, fourcc):
        """Ask for another camera format ('MJPG', 'YUYV' or '' for the camera's own choice): it is remembered, and the camera is closed so that it is reopened at once with it."""
        if fourcc not in FOURCCS:
            raise ValueError("The camera format must be MJPG, YUYV or the camera's default.")
        self.camera_settings = {"fourcc": fourcc}
        if self.camera_path:
            try:
                Path(self.camera_path).write_text(json.dumps(self.camera_settings), encoding="utf-8")
            except OSError:
                pass
        if self.camera is not None:
            self.camera.stop()
        self.camera, self.camera_info = None, {"ok": False, "path": "", "name": "", "format": ""}
        self._last_open_try = -1e9                       # try to open it again on the very next pass, not in 5 seconds
        self.last = None
        self.smoother.reset()

    def set_paused(self, paused):
        """Pause or resume the network. While it is paused the camera is still read and the picture still shown, so the camera's OWN speed can be read off the page."""
        self.paused = bool(paused)
        self.smoother.reset()

    def _pick_roi(self):
        saved = load_roi(self.roi_path, self.frame_size)
        self.roi, self.roi_source = (saved, "saved") if saved else (default_roi(self.frame_size), "the training square")

    # ---- the camera
    def attach_camera(self, camera, path="", name=""):
        rep = camera.report() if hasattr(camera, "report") else {}
        self.camera, self.camera_info = camera, {"ok": True, "path": path, "name": name, "format": format_text(rep)}
        self._seq = -1

    def maintain(self, opener=None):
        """If there is no camera, or it was lost, try to open one again every few seconds (a USB camera can be plugged in later)."""
        t = self.now()
        lost = self.camera is not None and self.camera.lost
        if (self.camera is None or lost) and opener is not None and t - self._last_open_try >= self.REOPEN_EVERY_S:
            self._last_open_try = t
            if lost:
                self.camera.stop()
                self.camera, self.camera_info = None, {"ok": False, "path": "", "name": "", "format": ""}
            found = opener()
            if found:
                cam, path, name = found
                self.attach_camera(CameraThread(cam, now=self.now).start(), path, name)
        if self.camera is None or self.camera.lost:
            self.camera_info = dict(self.camera_info, ok=False)

    # ---- one step
    def step(self):
        """One run of the network on the newest frame, if the camera has made a new one. Returns True if it did."""
        if self.benchmarking or self.camera is None:
            return False
        got = self.camera.read_latest()
        if got is None:
            return False
        frame, seq, t_cap = got
        if seq == self._seq:
            return False
        self._seq = seq
        size = (frame.shape[1], frame.shape[0])
        if size != self.frame_size:                                   # the camera gave another size than expected: use the square that fits it
            self.frame_size = size
            self._pick_roi()
        if self.paused:                                               # keep the newest picture, but do not run the network
            t = self.now()
            self.last = {"frame": frame, "digit": None, "probs": None, "age_ms": max(0.0, (t - t_cap) * 1000.0), "t": t}
            return True
        digit, probs, tm = self.pipeline.predict(frame, self.roi.clipped(*self.frame_size))
        self.smoother.add(probs)
        t = self.now()
        self.times.append((t, tm["prep_ms"], tm["infer_ms"]))
        self.last = {"frame": frame, "digit": digit, "probs": probs, "age_ms": max(0.0, (t - t_cap) * 1000.0), "t": t}
        return True

    # ---- what the page shows
    def view_due(self):
        return self.now() - self._last_view >= self.VIEW_EVERY_S

    def view(self):
        """The message for the page. With no camera picture yet it still says so (no jpg)."""
        t = self.now()
        self._last_view = t
        recent = [x for x in list(self.times) if t - x[0] <= 3.0]        # a copy: the loop thread keeps adding to it
        fps = round((len(recent) - 1) / (recent[-1][0] - recent[0][0]), 1) if len(recent) >= 2 and recent[-1][0] > recent[0][0] else 0.0
        mean = lambda i: round(sum(x[i] for x in recent) / len(recent), 2) if recent else None
        cam = dict(self.camera_info, fps=self.camera.fps() if self.camera else 0.0, lost=bool(self.camera and self.camera.lost), mode=self.camera_settings["fourcc"])
        out = {"jpg": None, "crop": None, "frame": {"w": self.frame_size[0], "h": self.frame_size[1]}, "roi": self.roi.clipped(*self.frame_size).to_json(), "roi_source": self.roi_source,
               "probs": None, "digit": None, "stable": None, "timing": {"prep_ms": mean(1), "infer_ms": mean(2), "age_ms": round(self.last["age_ms"], 1) if self.last else None, "fps": fps},
               "camera": cam, "benchmarking": self.benchmarking, "paused": self.paused}
        if self.last is not None:
            f = self.last["frame"]
            w = min(320, f.shape[1])
            small = cv2.resize(f, (w, int(round(f.shape[0] * w / f.shape[1]))), interpolation=cv2.INTER_AREA)
            img = self.pipeline.preprocess(f, self.roi.clipped(f.shape[1], f.shape[0]))
            out["jpg"] = to_jpeg_b64(small, 70)
            out["crop"] = to_jpeg_b64(np.ascontiguousarray(img[:, :, ::-1]) if img.shape[2] == 3 else img, 90)
            out["jw"], out["jh"] = small.shape[1], small.shape[0]
            if self.last["probs"] is not None:
                out["probs"] = [round(float(p), 4) for p in self.last["probs"]]
                out["digit"] = int(self.last["digit"])
                out["stable"] = self.smoother.stable()
        return out

    # ---- commands from the page
    def nudge(self, dx=0, dy=0, ds=0):
        w, h = self.frame_size
        self.roi = Roi(self.roi.x + int(dx), self.roi.y + int(dy), self.roi.side + int(ds)).clipped(w, h)
        self.roi_source = "moved by you (not saved yet)"
        self.smoother.reset()

    def find_tape(self, color="blue"):
        if self.last is None:
            raise ValueError("There is no camera picture yet.")
        r = find_square(self.last["frame"], color)
        if r is None:
            raise ValueError("No %s square found in the picture. Move the square with the arrow keys instead, or try another tape colour." % color)
        self.roi, self.roi_source = r, "found from the %s tape (not saved yet)" % color
        self.smoother.reset()
        return r

    def save_roi(self):
        save_roi(self.roi, self.roi_path, self.frame_size)
        self.roi_source = "saved"

    def reset_roi(self):
        self.roi, self.roi_source = default_roi(self.frame_size), "the training square"
        self.smoother.reset()

    def benchmark(self, n=100):
        """Time the network, n steps over. The FIRST row is always the same made-up picture (so this machine can be compared with any other); a second row uses the camera
        picture, if there is one. The live steps pause meanwhile, so the numbers are clean. Returns the first (standard) row."""
        self.benchmarking = True
        try:
            jobs = [("made-up picture", synthetic_frame(*TRAINING_FRAME), default_roi(TRAINING_FRAME))]
            if self.last is not None:
                f = self.last["frame"]
                jobs.append(("camera picture", f, self.roi.clipped(f.shape[1], f.shape[0])))
            rows = []
            for what, frame, roi in jobs:
                row = {"time": self.clock().strftime("%H:%M:%S"), "what": what, "frame": "%dx%d" % (frame.shape[1], frame.shape[0])}
                row.update(benchmark(self.pipeline, frame, roi, n))
                row.update(machine_info())
                rows.append(row)
        finally:
            self.benchmarking = False
        for row in rows:
            self.bench_rows.append(row)
            self._log_row(row)
        return rows[0]

    def _log_row(self, row):
        if not self.csv_path:
            return
        new = not Path(self.csv_path).exists()
        try:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=BENCH_FIELDS)
                if new:
                    w.writeheader()
                w.writerow({k: row.get(k) for k in BENCH_FIELDS})
        except OSError:
            pass
