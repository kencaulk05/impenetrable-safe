"""Turning a camera frame into a finger count, the same way the training pictures were made, and steadying the answer over a few frames.

The network was trained on pictures that went: camera frame -> cut out the square -> resize to 128 x 128 (the capture tool) -> shrink to the network's size (train.py). Here the
same two steps are done on the live frame, with the same resizing, so the network sees the same kind of picture it learned from.
"""
from collections import deque

import cv2
import numpy as np

from fingerlock import capture_lib as cl
from fingerlock.infer_numpy import NumpyFingerCNN


class Predictor:
    def __init__(self, model_path, roi):
        self.net = NumpyFingerCNN.load(model_path)
        self.size, self.gray, self.roi = int(self.net.meta["size"]), bool(self.net.meta["gray"]), roi

    def preprocess(self, frame):
        crop = cl.crop(frame, self.roi, cl.SAVE_SIZE)                                   # the picture the capture tool would have saved
        if self.gray:                                                                   # data.load_dataset reads grey pictures as grey BEFORE shrinking them
            crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        img = cv2.resize(crop, (self.size, self.size), interpolation=cv2.INTER_AREA)
        return np.ascontiguousarray(img[:, :, None] if self.gray else img[:, :, ::-1])

    def predict(self, frame):
        """(the most likely number of fingers, the six probabilities) for one camera frame."""
        return self.net.predict(self.preprocess(frame))


class Smoother:
    """The last few answers, averaged. One frame can be wrong (a blur, a hand on its way in); a number is called STABLE only when the average probability is high
    enough and most of the recent frames agree."""

    def __init__(self, n=8, min_prob=0.6, min_agree=0.75):
        self.n, self.min_prob, self.min_agree = n, min_prob, min_agree
        self.buf = deque(maxlen=n)

    def add(self, probs):
        self.buf.append(np.asarray(probs, dtype=float))

    def mean(self):
        return np.mean(self.buf, axis=0) if self.buf else np.zeros(6)

    def stable(self):
        """The number if the answer is steady, else None."""
        if len(self.buf) < self.n:
            return None
        m = self.mean()
        cls = int(m.argmax())
        agree = float(np.mean([int(p.argmax()) == cls for p in self.buf]))
        return cls if m[cls] >= self.min_prob and agree >= self.min_agree else None

    def reset(self):
        self.buf.clear()
