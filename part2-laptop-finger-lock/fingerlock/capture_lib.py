"""The logic of the capture tool, with no window in it, so it can be tested without a camera.

THE SETUP: the webcam is fixed on a stand at a set distance above the desk, and a red square is drawn on the desk. Only the inside of that square is
saved and used, so every image is the same size and distance, and the network never has to cope with zooming in and out.

CLASSES: six, 0 to 5 fingers (0 = an empty square or a closed fist). Images go to  <out>/<class>/<person>__<class>__<timestamp>.png.
PEOPLE are letters (A, B, C ...), never names: the images show hands and the repo is public.
"""
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

CLASSES = (0, 1, 2, 3, 4, 5)
SAVE_SIZE = 128                                   # crops are saved at 128 x 128; training can shrink them (for example to 64 x 64)
PERSON_RE = re.compile(r"^[A-Za-z0-9]{1,3}$")


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
    """The saved region, or None. If it was saved for a different camera resolution it is refused, because the pixels would mean something else."""
    p = Path(path)
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    if frame_size is not None and (d.get("frame_width"), d.get("frame_height")) != (int(frame_size[0]), int(frame_size[1])):
        return None
    return Roi.from_json(d)


def check_person(person):
    if not PERSON_RE.match(str(person)):
        raise ValueError("the person must be 1 to 3 letters or digits (use a letter such as A, B, C: the images show hands and the repo is public)")
    return str(person)


def crop(frame, roi, size=SAVE_SIZE):
    """The inside of the square, resized to size x size (INTER_AREA, the right way to shrink)."""
    h, w = frame.shape[:2]
    r = roi.clipped(w, h)
    return cv2.resize(frame[r.y:r.y + r.side, r.x:r.x + r.side], (size, size), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------------------------------------------------------------------- finding the square on the desk
TAPE = ("red", "blue", "green", "yellow")
TAPE_HSV = {"red": (((0, 110, 70), (10, 255, 255)), ((170, 110, 70), (180, 255, 255))),        # red wraps around the colour wheel, so it needs two ranges
            "blue": (((95, 90, 60), (130, 255, 255)),), "green": (((40, 80, 60), (85, 255, 255)),), "yellow": (((18, 100, 100), (35, 255, 255)),)}


def find_square(frame, color="red", inset=0.07, min_area_fraction=0.02):
    """Look for a square of tape (red, blue, green or yellow) on the desk. Returns the Roi INSIDE it (inset by a margin so the tape itself is left out), or None.
    It picks out that colour, joins the pieces of the line, and takes the largest outline that is roughly square. Lighting changes colours a lot, and a blue
    sleeve or jeans can look like blue tape: if it picks the wrong thing, drag a box with the mouse instead (the tape is only a guide for you)."""
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
            continue                                             # too small, too big (red wall?), or not roughly square
        if best is None or bw * bh > best[2] * best[3]:
            best = (x, y, bw, bh)
    if best is None:
        return None
    x, y, bw, bh = best
    side = max(bw, bh)
    m = int(round(side * inset))
    return Roi(x + m, y + m, side - 2 * m).clipped(w, h)


# ---------------------------------------------------------------------------------------------------------------------------- quality
def find_red_square(frame, **kw):
    return find_square(frame, "red", **kw)


def quality(img):
    """Brightness (mean grey, 0 to 255), sharpness (variance of the Laplacian: low means blurry) and contrast (spread of the grey levels) of a crop."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return {"brightness": float(g.mean()), "sharpness": float(cv2.Laplacian(g, cv2.CV_64F).var()), "contrast": float(g.std())}


def quality_flags(q, empty_diff=None, label=None):
    """Plain-language warnings about one crop. empty_diff is how much the crop differs from the empty-square picture (0 to 1), if one was taken."""
    flags = []
    if q["brightness"] < 45: flags.append("too dark")
    if q["brightness"] > 215: flags.append("too bright")
    if q["sharpness"] < 8: flags.append("blurry or flat")
    if q["contrast"] < 12: flags.append("low contrast")
    if empty_diff is not None and label in (1, 2, 3, 4, 5) and empty_diff < 0.02:
        flags.append("looks EMPTY but is labelled %d" % label)
    return flags


def difference_from_empty(img, empty, threshold=28):
    """The fraction of pixels that differ clearly from a picture of the empty square (0 = identical, 1 = completely different)."""
    if empty is None:
        return None
    d = cv2.absdiff(cv2.GaussianBlur(img, (5, 5), 0), cv2.GaussianBlur(cv2.resize(empty, (img.shape[1], img.shape[0])), (5, 5), 0))
    return float((d.max(axis=2) > threshold).mean())


# ---------------------------------------------------------------------------------------------------------------------------- the dataset
class Dataset:
    """<out>/<class>/<person>__<class>__<timestamp ms>-<n>.png, and counting what is there."""

    def __init__(self, out):
        self.out = Path(out)
        self._n = 0
        self.undo_stack = []

    def path_for(self, label, person):
        self._n += 1
        d = self.out / str(label)
        d.mkdir(parents=True, exist_ok=True)
        return d / ("%s__%d__%d-%03d.png" % (person, label, int(time.time() * 1000), self._n % 1000))

    def save(self, img, label, person):
        if label not in CLASSES:
            raise ValueError("class must be one of %s" % (CLASSES,))
        p = self.path_for(label, check_person(person))
        if not cv2.imwrite(str(p), img):
            raise IOError("could not write %s" % p)
        self.undo_stack.append(p)
        return p

    def undo(self):
        """Delete the picture saved last. Returns its path, or None."""
        while self.undo_stack:
            p = self.undo_stack.pop()
            if p.exists():
                p.unlink()
                return p
        return None

    def counts(self, person=None):
        """{class: number of images}, for one person or for everyone."""
        out = {c: 0 for c in CLASSES}
        for c in CLASSES:
            d = self.out / str(c)
            if d.exists():
                out[c] = sum(1 for f in d.glob("*.png") if person is None or f.name.startswith(person + "__"))
        return out


class Burst:
    """Capture N pictures over a short time while the hand moves a little: press a digit once, then wiggle the hand and tilt the fingers."""

    def __init__(self, label, n=20, interval=0.1):
        self.label, self.n, self.interval = label, n, interval
        self.taken, self._next = 0, 0.0

    def due(self, now):
        if self.taken >= self.n or now < self._next:
            return False
        self._next = now + self.interval
        self.taken += 1
        return True

    @property
    def done(self):
        return self.taken >= self.n


def open_camera(index=0, width=640, height=480):
    """Open the webcam at a fixed size and, where the camera allows it, switch off autofocus and auto-exposure, which change the picture while you work.
    Returns (camera, what the camera actually accepted). Windows needs the DirectShow backend for this to work reliably."""
    import sys
    cam = cv2.VideoCapture(index, cv2.CAP_DSHOW) if sys.platform.startswith("win") else cv2.VideoCapture(index)
    if not cam.isOpened():
        raise RuntimeError("could not open camera %d: is it plugged in, and is another program using it?" % index)
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, width); cam.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cam.set(cv2.CAP_PROP_AUTOFOCUS, 0)
    info = {"width": int(cam.get(cv2.CAP_PROP_FRAME_WIDTH)), "height": int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT)), "autofocus": cam.get(cv2.CAP_PROP_AUTOFOCUS), "auto_exposure": cam.get(cv2.CAP_PROP_AUTO_EXPOSURE)}
    return cam, info
