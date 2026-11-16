"""Synthetic hands, ONLY to test the software without a webcam (the capture tool's simulator, and the training code's tests). They are crude drawings:
a palm and N finger bars on a desk-coloured square. They say nothing about how the real network will do on real hands.
"""
import cv2
import numpy as np


def make_hand(n, rng, size=128, style=None):
    """A BGR crop (size x size) showing a desk and, if n > 0, a palm with n fingers; n = 0 is an empty desk or a fist (a palm with no fingers)."""
    desk = rng.integers(90, 200, 3).astype(np.uint8)
    img = np.empty((size, size, 3), dtype=np.uint8)
    img[:] = desk
    img = np.clip(img.astype(np.int16) + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    if n == 0 and rng.random() < 0.35:
        return img                                                    # an empty desk
    style = style or {}
    lo, hi = style.get("skin", ((80, 100, 140), (190, 210, 235)))                  # a person's skin tone range (BGR)
    skin = np.array([rng.integers(lo[0], hi[0]), rng.integers(lo[1], hi[1]), rng.integers(lo[2], hi[2])], dtype=np.uint8)
    cx, cy = size * rng.uniform(0.42, 0.58), size * rng.uniform(0.55, 0.7)
    pr = size * rng.uniform(0.17, 0.23) * style.get("palm", 1.0)                   # a person's hand size
    tilt = rng.uniform(-18, 18)
    cv2.ellipse(img, (int(cx), int(cy)), (int(pr), int(pr * 1.05)), tilt, 0, 360, tuple(int(v) for v in skin), -1)
    angles = np.linspace(-38, 38, max(n, 1)) if n > 1 else np.array([0.0])
    for k in range(n):
        a = np.deg2rad(angles[k] + tilt + rng.normal(0, 3))
        length = size * rng.uniform(0.26, 0.34)
        x0, y0 = cx + np.sin(a) * pr * 0.7, cy - np.cos(a) * pr * 0.7
        x1, y1 = x0 + np.sin(a) * length, y0 - np.cos(a) * length
        cv2.line(img, (int(x0), int(y0)), (int(x1), int(y1)), tuple(int(v) for v in skin), max(3, int(size * 0.075)), cv2.LINE_AA)
    return img


TAPE_BGR = {"red": (30, 30, 215), "blue": (215, 70, 30), "green": (40, 170, 40), "yellow": (30, 215, 230)}


class SyntheticCamera:
    """Stands in for a webcam: a desk with a red square outline, and a hand (or nothing) inside it. set_label() chooses what the 'hand' shows."""

    def __init__(self, width=640, height=480, square=(220, 130, 200), seed=0, tape="red"):
        self.w, self.h, self.sq = width, height, square          # square = (x, y, side) of the red outline
        self.rng = np.random.default_rng(seed)
        self.label = 0
        self.base = np.full((height, width, 3), (120, 130, 140), dtype=np.uint8)
        x, y, s = square
        cv2.rectangle(self.base, (x, y), (x + s, y + s), TAPE_BGR[tape], 6)
        self.opened = True

    def set_label(self, n):
        self.label = n

    def read(self):
        frame = self.base.copy()
        x, y, s = self.sq
        inner = int(s * 0.08)
        patch = make_hand(self.label, self.rng, s - 2 * inner)
        frame[y + inner:y + inner + patch.shape[0], x + inner:x + inner + patch.shape[1]] = patch
        return True, frame

    def release(self):
        self.opened = False
