#!/usr/bin/env python3
"""Write a MADE-UP dataset in exactly the format the capture tool saves, to try the training code without a webcam.

    python make_synthetic_dataset.py data/synth            then:  python train.py --data data/synth --epochs 10

Two or more made-up "people" with different hand sizes and skin tones, in bursts of 20 pictures. The drawings are crude: the accuracy you get says nothing about real hands.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from fingerlock.synth_hand import make_hand

STYLES = {"A": {"skin": ((60, 70, 110), (120, 140, 190)), "palm": 1.0}, "B": {"skin": ((120, 150, 190), (200, 220, 245)), "palm": 0.85}, "C": {"skin": ((90, 110, 150), (170, 190, 225)), "palm": 1.15}}


def write_synthetic(root, people=("A", "B"), per_class=100, seed=0, burst=20, t0=1_700_000_000_000):
    rng = np.random.default_rng(seed)
    root = Path(root)
    t = t0
    for person in people:
        for c in range(6):
            n = 0
            while n < per_class:
                t += 30_000                                              # a new burst, 30 seconds after the last
                (root / str(c)).mkdir(parents=True, exist_ok=True)
                for k in range(min(burst, per_class - n)):
                    cv2.imwrite(str(root / str(c) / ("%s__%d__%d-%03d.png" % (person, c, t + 100 * k, n % 1000))), make_hand(c, rng, style=STYLES.get(person)))
                    n += 1
    return root


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--people", default="AB")
    ap.add_argument("--per-class", type=int, default=100)
    a = ap.parse_args()
    write_synthetic(a.out, tuple(a.people), a.per_class)
    print("wrote", a.out)
