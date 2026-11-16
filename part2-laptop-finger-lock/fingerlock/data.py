"""Loading the pictures the capture tool saved, and splitting them HONESTLY.

A burst saves 20 near-identical pictures in two seconds. If those were split at random between training and testing, the network would be tested on pictures that are
almost copies of ones it trained on, and the score would be far too good. So pictures are grouped by (person, class, 10-second window) and a whole group goes to one side.
The most honest test of all is a NEW PERSON: train on everyone else, test on the person who was left out.
"""
import re
from pathlib import Path

import cv2
import numpy as np

NAME_RE = re.compile(r"^(?P<person>[A-Za-z0-9]{1,3})__(?P<label>[0-5])__(?P<ts>\d+)-(?P<n>\d+)\.png$")
GROUP_SECONDS = 10


def parse_name(name):
    """(person, class, time in ms) from a file name made by the capture tool, or None for any other file."""
    m = NAME_RE.match(name)
    return (m["person"], int(m["label"]), int(m["ts"])) if m else None


def load_dataset(root, size=64, gray=False, exclude=()):
    """Returns a dict: X uint8 (N, size, size, C), y, person (array of letters), group (array of ints), skipped (file names that were not pictures of this tool)."""
    X, y, person, keys, skipped, times, files = [], [], [], [], [], [], []
    for c in range(6):
        for f in sorted((Path(root) / str(c)).glob("*.png")) if (Path(root) / str(c)).exists() else []:
            parsed = parse_name(f.name)
            if parsed is None or parsed[1] != c:
                skipped.append(f.name)
                continue
            if parsed[0] in exclude:
                continue
            img = cv2.imread(str(f), cv2.IMREAD_COLOR)
            if img is None:
                skipped.append(f.name)
                continue
            if gray:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)               # the same conversion the live code uses, before shrinking
            img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
            X.append(img[:, :, None] if gray else img[:, :, ::-1])             # OpenCV reads BGR; the network sees RGB
            y.append(c); person.append(parsed[0]); times.append(parsed[2]); files.append(str(f)); keys.append((parsed[0], c, parsed[2] // (GROUP_SECONDS * 1000)))
    ids = {k: i for i, k in enumerate(sorted(set(keys)))}
    return {"X": np.stack(X) if X else np.zeros((0, size, size, 1 if gray else 3), np.uint8), "y": np.array(y, dtype=np.int64), "person": np.array(person), "ts": np.array(times, dtype=np.int64), "files": files,
            "group": np.array([ids[k] for k in keys], dtype=np.int64), "skipped": skipped}


def sessions(ts, gap_minutes=60):
    """Which session each picture belongs to (0 = the earliest): a new session starts after a gap of more than gap_minutes with no pictures taken. A session is a stretch
    of collecting in one light and one setup, so training on the earlier sessions and testing on the last one measures what happens on a different day or in different light."""
    ts = np.asarray(ts, dtype=np.int64)
    if len(ts) == 0:
        return np.zeros(0, dtype=np.int64)
    order = np.argsort(ts, kind="stable")
    s = np.zeros(len(ts), dtype=np.int64)
    s[order] = np.concatenate([[0], np.cumsum(np.diff(ts[order]) > gap_minutes * 60 * 1000)])
    return s


def split_by_group(group, y, val_fraction=0.2, seed=0):
    """A boolean mask of the pictures to hold out. Whole groups go to the held-out side, every class gets some, and no group is ever on both sides."""
    rng = np.random.default_rng(seed)
    val = np.zeros(len(y), dtype=bool)
    for c in np.unique(y):
        groups = np.unique(group[y == c])
        rng.shuffle(groups)
        k = max(1, int(round(len(groups) * val_fraction))) if len(groups) > 1 else 0
        val |= np.isin(group, groups[:k]) & (y == c)
    return val


def to_tensor(X):
    """uint8 (N, H, W, C) -> float32 (N, C, H, W) in [0, 1]."""
    import torch
    return torch.from_numpy(X).float().div(255.0).permute(0, 3, 1, 2).contiguous()
