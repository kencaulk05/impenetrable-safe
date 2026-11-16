#!/usr/bin/env python3
"""Find the pictures the trained network confidently disagrees with: probably unclear or wrong labels.

    python review_labels.py --model models/finger_cnn.npz --data data/raw               list them and make contact sheets in review/
    python review_labels.py --model models/finger_cnn.npz --data data/raw --move        also MOVE them out of the training data into data/raw/_review/<label>/ (nothing is deleted)

Open the sheets in review/ (each picture says 'label > what the network said, confidence'). A picture that really is what its label says is a hard case worth keeping;
a thumbs-up labelled 1, or a hand that is half-way between two numbers, is better out. Then retrain.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

from fingerlock import data as D
from fingerlock.infer_numpy import NumpyFingerCNN
from fingerlock.review import contact_sheet, find_disagreements, load_predictions, move_flagged


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="models/finger_cnn.npz")
    ap.add_argument("--data", default="data/raw")
    ap.add_argument("--predictions", default="results/holdout_predictions.npz", help="predictions made by networks that had NOT seen each picture (saved by train.py): the right thing to use")
    ap.add_argument("--min-conf", type=float, default=0.8, help="only pictures the network is at least this sure about")
    ap.add_argument("--out", default="review")
    ap.add_argument("--move", action="store_true")
    a = ap.parse_args(argv)
    net = NumpyFingerCNN.load(a.model)
    ds = D.load_dataset(a.data, size=net.meta["size"], gray=net.meta["gray"])
    if len(ds["y"]) == 0:
        raise SystemExit("no pictures found in %s" % a.data)
    files, labels, probs = ds["files"], ds["y"], None
    if Path(a.predictions).exists():
        probs, files, labels = load_predictions(a.predictions, ds)
        print("using the predictions of networks that never saw each picture (%s)" % a.predictions)
    else:
        print("WARNING: %s not found, so the final network is used. It was trained on these very pictures and has partly MEMORIZED them, so it will flag far fewer than it should. Run train.py first (it saves the predictions of networks that did not see each picture)." % a.predictions)
        probs = np.stack([net.predict(img)[1] for img in ds["X"]])
    rows = find_disagreements(files, labels, probs, a.min_conf)
    out = Path(a.out); out.mkdir(exist_ok=True)
    print("%d of %d pictures: the network is at least %.0f%% sure of a DIFFERENT number than the label" % (len(rows), len(ds["y"]), 100 * a.min_conf))
    pairs = {}
    for r in rows:
        pairs.setdefault((r[1], r[2]), []).append(r)
    for (t, p), rs in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
        name = out / ("labelled_%d_said_%d.png" % (t, p))
        contact_sheet(rs[:48], name)
        print("  labelled %d, network says %d: %3d pictures  -> %s" % (t, p, len(rs), name))
    if a.move and rows:
        print("moved %d pictures to %s/_review/" % (move_flagged(rows, Path(a.data) / "_review"), a.data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
