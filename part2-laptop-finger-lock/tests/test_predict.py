"""Tests for the live prediction (fingerlock/predict.py, predict_live.py).   python tests/test_predict.py"""
import sys, tempfile
from pathlib import Path

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fingerlock import capture_lib as cl
from fingerlock import data as D
from fingerlock.infer_numpy import NumpyFingerCNN
from fingerlock.model import FingerCNN
from fingerlock.predict import Predictor, Smoother
from fingerlock.synth_hand import SyntheticCamera, make_hand
from make_synthetic_dataset import write_synthetic
import predict_live

problems = 0


def expect(label, cond, detail=""):
    global problems
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    problems += (not cond)


tmp = Path(tempfile.mkdtemp())
torch.manual_seed(0)
for name, size, ch in (("color64", 64, 3), ("gray32", 32, 1)):
    NumpyFingerCNN.from_torch(FingerCNN(in_channels=ch).eval(), {"size": size, "gray": ch == 1}).save(tmp / (name + ".npz"))

print("1. the live pre-processing is the training pre-processing")
write_synthetic(tmp / "ds", ("A",), per_class=3, seed=1)
f = sorted((tmp / "ds" / "3").glob("*.png"))[0]
pic = cv2.imread(str(f))
frame = np.zeros((480, 640, 3), np.uint8); frame[100:228, 200:328] = pic                      # a camera frame with that picture exactly inside the square
roi = cl.Roi(200, 100, 128)
pc = Predictor(tmp / "color64.npz", roi)
ds = D.load_dataset(tmp / "ds", 64)
ref = ds["X"][[i for i, g in enumerate(ds["y"]) if g == 3][0]]
expect("for a picture saved by the capture tool, the live colour pre-processing gives EXACTLY the array that training loaded (RGB order, 64 x 64)", np.array_equal(pc.preprocess(frame), ref), "%s %s" % (pc.preprocess(frame).shape, pc.preprocess(frame).dtype))
pg = Predictor(tmp / "gray32.npz", roi)
dg = D.load_dataset(tmp / "ds", 32, gray=True)
refg = dg["X"][[i for i, g in enumerate(dg["y"]) if g == 3][0]]
diff = np.abs(pg.preprocess(frame).astype(int) - refg.astype(int)).max()
expect("the grey version gives EXACTLY the same array as training too (largest difference %d), shape %s" % (diff, pg.preprocess(frame).shape), diff == 0 and pg.preprocess(frame).shape == (32, 32, 1))
cls, pr = pc.predict(frame)
expect("predict gives one class from 0 to 5 and six probabilities that add up to 1", 0 <= cls <= 5 and pr.shape == (6,) and abs(pr.sum() - 1) < 1e-9)
big = np.zeros((480, 640, 3), np.uint8); big[100:417, 200:517] = cv2.resize(pic, (317, 317))
expect("it works for a square bigger than 128 pixels too (the frame is cut and shrunk like the capture tool does)", Predictor(tmp / "color64.npz", cl.Roi(200, 100, 317)).preprocess(big).shape == (64, 64, 3))

print("2. steadying the answer")
def feed(sm, seq):
    for c in seq:
        p = np.full(6, 0.02); p[c] = 0.9; sm.add(p / p.sum())
    return sm.stable()
expect("no answer is called stable before enough frames have been seen", Smoother(n=8).stable() is None and feed(Smoother(n=8), [3] * 7) is None)
expect("eight frames in a row saying 3 give a stable 3", feed(Smoother(n=8), [3] * 8) == 3)
expect("one wrong frame among eight does not spoil it (7 of 8 agree)", feed(Smoother(n=8), [3, 3, 3, 4, 3, 3, 3, 3]) == 3)
expect("a flickering answer (3, 4, 3, 4 ...) is NOT stable", feed(Smoother(n=8), [3, 4] * 4) is None)
sm = Smoother(n=8)
for _ in range(8): sm.add(np.full(6, 1 / 6))
expect("an unsure answer (every number equally likely) is NOT stable, even if it never changes", sm.stable() is None)
sm = Smoother(n=4); feed(sm, [2, 2, 2, 2]); sm.reset()
expect("reset forgets everything (a new person puts a new hand in)", sm.stable() is None and len(sm.buf) == 0)
sm = Smoother(n=4); feed(sm, [1, 1, 1, 1]); feed(sm, [5, 5, 5, 5])
expect("old frames drop out: after four 1s and then four 5s the answer is 5", sm.stable() == 5)

print("3. the live demo, without a camera")
write_synthetic(tmp / "roi_ds", ("A",), per_class=1, seed=1)
r = predict_live.main(["--model", str(tmp / "color64.npz"), "--data", str(tmp / "nothing"), "--simulate", "--headless-demo", "12"])
expect("the demo runs on the made-up camera, finds its own square, and stops after 12 frames", r == 0)
cl.save_roi(cl.Roi(220, 130, 200), tmp / "roi_ds" / "roi.json", (640, 480))
r2 = predict_live.main(["--model", str(tmp / "color64.npz"), "--data", str(tmp / "roi_ds"), "--simulate", "--headless-demo", "3"])
expect("it uses the square saved by the capture tool when there is one", r2 == 0)
v = predict_live.draw(SyntheticCamera().read()[1], cl.Roi(220, 130, 200), np.array([0.1, 0.1, 0.5, 0.1, 0.1, 0.1]), 2, 3.2)
expect("the window drawing (the number, the six bars, the time per picture) keeps the picture size", v.shape == (480, 640, 3))

print("4. finding pictures whose label may be wrong")
from fingerlock import review
files = ["a/0/p1.png", "a/1/p2.png", "a/2/p3.png", "a/3/p4.png", "a/3/p5.png"]
labels = np.array([0, 1, 2, 3, 3])
pr = np.array([[0.9, .02, .02, .02, .02, .02], [0.05, 0.05, 0.85, 0.02, 0.02, 0.01], [0.1, 0.1, 0.5, 0.1, 0.1, 0.1], [0.02, 0.02, 0.02, 0.1, 0.8, 0.04], [0.03, 0.03, 0.03, 0.2, 0.6, 0.11]])
rows = review.find_disagreements(files, labels, pr, 0.8)
expect("it flags a picture only when the network is sure of a different number: here labelled 1 but 85% sure of 2, and labelled 3 but 80% sure of 4 (the 60% disagreement, the correct answers and the unsure one are not flagged), most confident first", [r[0] for r in rows] == ["a/1/p2.png", "a/3/p4.png"] and rows[0][1:3] == (1, 2) and rows[0][3] > rows[1][3], str(rows))
expect("a lower bar flags more", len(review.find_disagreements(files, labels, pr, 0.5)) == 3)
(tmp / "rv" / "1").mkdir(parents=True)
for n in ("A__1__1700000000001-001.png", "A__1__1700000000002-002.png"): cv2.imwrite(str(tmp / "rv" / "1" / n), np.full((128, 128, 3), 100, np.uint8))
fl = [(str(tmp / "rv" / "1" / "A__1__1700000000001-001.png"), 1, 0, 0.9)]
expect("flagged pictures are MOVED to a review folder by label (never deleted): the other picture stays", review.move_flagged(fl, tmp / "rv" / "_review") == 1 and (tmp / "rv" / "_review" / "1" / "A__1__1700000000001-001.png").exists() and (tmp / "rv" / "1" / "A__1__1700000000002-002.png").exists() and not (tmp / "rv" / "1" / "A__1__1700000000001-001.png").exists())
expect("moving them a second time moves nothing and loses nothing", review.move_flagged(fl, tmp / "rv" / "_review") == 0)
expect("it makes a contact sheet of them, and none when there is nothing to show", review.contact_sheet([(str(tmp / "rv" / "_review" / "1" / "A__1__1700000000001-001.png"), 1, 0, 0.9)], tmp / "sheet.png") and (tmp / "sheet.png").exists() and review.contact_sheet([], tmp / "none.png") is False)
dsr = D.load_dataset(tmp / "ds", 64)
npz = tmp / "hp.npz"; np.savez(npz, files=np.array(dsr["files"][:10]), probs=np.full((10, 6), 1 / 6))
pp, ff, ll = review.load_predictions(npz, dsr)
expect("saved predictions are matched to pictures by file name, and pictures that were not in the run are left out (10 of %d)" % len(dsr["y"]), pp.shape == (10, 6) and len(ff) == 10 and len(ll) == 10 and len(dsr["y"]) == 18)

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
