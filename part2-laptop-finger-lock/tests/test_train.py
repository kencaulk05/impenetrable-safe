"""Tests for the training code: loading, the honest splits, augmentation, the network, cross-entropy, the NumPy copy, and the command-line run.   python tests/test_train.py"""
import json, sys, tempfile
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fingerlock import data as D
from fingerlock import infer_numpy as inp
from fingerlock.augment import augment_batch
from fingerlock.model import FingerCNN, n_parameters
from make_synthetic_dataset import write_synthetic
import train as T

problems = 0


def expect(label, cond, detail=""):
    global problems
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    problems += (not cond)


tmp = Path(tempfile.mkdtemp())
write_synthetic(tmp / "ds", ("A", "B"), per_class=40, seed=1)

print("1. loading the pictures the capture tool saved")
expect("file names are read as person, class and time; anything else is rejected", D.parse_name("A__3__1700000000123-007.png") == ("A", 3, 1700000000123) and all(D.parse_name(n) is None for n in ("A__6__1-1.png", "ABCD__3__1-1.png", "A__3__copy.png", "photo.png", "A_3_1-1.png")))
ds = D.load_dataset(tmp / "ds", 64)
expect("480 pictures load as 64 x 64 colour, 80 per class, 240 per person", ds["X"].shape == (480, 64, 64, 3) and ds["X"].dtype == np.uint8 and np.bincount(ds["y"]).tolist() == [80] * 6 and sorted(set(ds["person"])) == ["A", "B"] and (ds["person"] == "A").sum() == 240)
g = D.load_dataset(tmp / "ds", 32, gray=True)
expect("grey loads as one channel at the size asked for", g["X"].shape == (480, 32, 32, 1))
expect("a person can be left out", set(D.load_dataset(tmp / "ds", 32, exclude=("A",))["person"]) == {"B"})
cv2.imwrite(str(tmp / "ds" / "0" / "A__0__copy.png"), np.zeros((128, 128, 3), np.uint8))
cv2.imwrite(str(tmp / "blue.png"), np.dstack([np.full((8, 8), 255, np.uint8), np.zeros((8, 8), np.uint8), np.zeros((8, 8), np.uint8)]))
(tmp / "rgb" / "1").mkdir(parents=True); cv2.imwrite(str(tmp / "rgb" / "1" / "A__1__1700000000000-001.png"), cv2.imread(str(tmp / "blue.png")))
rgb = D.load_dataset(tmp / "rgb", 8)["X"][0, 0, 0]
expect("a stray file in a class folder is skipped and reported, not loaded", D.load_dataset(tmp / "ds", 32)["skipped"] == ["A__0__copy.png"] and len(D.load_dataset(tmp / "ds", 32)["y"]) == 480)
expect("OpenCV's blue-green-red is turned into red-green-blue (a pure blue pixel becomes 0, 0, 255)", rgb.tolist() == [0, 0, 255], str(rgb.tolist()))
a0 = np.where((ds["person"] == "A") & (ds["y"] == 3))[0]
expect("the 20 pictures of one burst share a group, and different bursts are different groups (40 pictures = 2 bursts)", len(set(ds["group"][a0[:20]])) == 1 and len(set(ds["group"][a0])) == 2)

print("2. honest splits")
val = D.split_by_group(ds["group"], ds["y"], 0.2, 0)
leak = set(ds["group"][val]) & set(ds["group"][~val])
expect("no burst is ever split between training and testing (that would leak almost-identical pictures into the test): %d groups held out, %d overlap" % (len(set(ds["group"][val])), len(leak)), not leak)
expect("every class has pictures on both sides, and about a fifth is held out (%.0f%%)" % (100 * val.mean()), all(val[ds["y"] == c].any() and (~val[ds["y"] == c]).any() for c in range(6)) and 0.1 < val.mean() < 0.35)
expect("the split can be repeated with the same seed and differs with another", np.array_equal(val, D.split_by_group(ds["group"], ds["y"], 0.2, 0)) and not np.array_equal(val, D.split_by_group(ds["group"], ds["y"], 0.2, 5)))

print("3. augmentation (rotate, shift, zoom, mirror, brightness)")
X = D.to_tensor(ds["X"][:16])
none = dict(rotate=0, shift=0, scale=(1, 1), flip=0, brightness=0, contrast=0, noise=0, color=0, gray=0)
gen = lambda s=0: torch.Generator().manual_seed(s)
expect("with every change switched off the picture comes back unchanged", torch.allclose(augment_batch(X, gen(), **none), X, atol=1e-5))
marker = torch.zeros(1, 1, 64, 64); marker[0, 0, 10, 50] = 1.0
vf = augment_batch(marker, gen(), **{**none, "flip": 1.0, "flip_axis": "v"}); hf = augment_batch(marker, gen(), **{**none, "flip": 1.0, "flip_axis": "h"})
pos = lambda t: tuple(int(v) for v in np.unravel_index(int(t[0, 0].argmax()), (64, 64)))
expect("the vertical mirror swaps top and bottom (a marked pixel at row 10, column 50 goes to row %d, column %d: the column must stay at 50)" % pos(vf), pos(vf) == (53, 50) and torch.allclose(augment_batch(X, gen(), **{**none, "flip": 1.0, "flip_axis": "v"}), torch.flip(X, dims=[2]), atol=1e-5))
expect("the horizontal mirror swaps left and right (the row stays at 10, the column goes to 13)", pos(hf) == (10, 13) and torch.allclose(augment_batch(X, gen(), **{**none, "flip": 1.0, "flip_axis": "h"}), torch.flip(X, dims=[3]), atol=1e-5))
expect("with no mirror axis nothing is mirrored, even when asked to", torch.allclose(augment_batch(X, gen(), **{**none, "flip": 1.0, "flip_axis": None}), X, atol=1e-5))
full = augment_batch(X, gen(1))
expect("the full augmentation keeps the size and the 0 to 1 range, changes the pictures, repeats with the same seed and differs with another", full.shape == X.shape and float(full.min()) >= 0 and float(full.max()) <= 1 and not torch.allclose(full, X, atol=1e-3) and torch.equal(full, augment_batch(X, gen(1))) and not torch.equal(full, augment_batch(X, gen(2))))
flat = torch.full((64, 3, 8, 8), 0.5)
cj = augment_batch(flat, gen(), **{**none, "color": 0.25})
gains = cj[:, :, 0, 0] / 0.5
expect("colour jitter multiplies each colour channel by its own random number between 0.75 and 1.25 (seen: %.2f to %.2f), the same over a whole picture" % (float(gains.min()), float(gains.max())), float(gains.min()) >= 0.749 and float(gains.max()) <= 1.251 and float(gains.std()) > 0.05 and torch.allclose(cj, cj[:, :, :1, :1].expand_as(cj)))
gr = augment_batch(torch.rand(16, 3, 8, 8), gen(), **{**none, "gray": 1.0})
mixed = augment_batch(torch.rand(400, 3, 8, 8), gen(), **{**none, "gray": 0.2})
frac = float((mixed[:, 0] == mixed[:, 1]).all(dim=(1, 2)).float().mean())
expect("random loss of colour: with chance 1 every picture comes out grey (equal channels); with chance 0.2 about a fifth do (%.2f)" % frac, torch.allclose(gr[:, 0], gr[:, 1], atol=1e-6) and torch.allclose(gr[:, 1], gr[:, 2], atol=1e-6) and 0.1 < frac < 0.3)
g1 = torch.rand(4, 1, 8, 8)
expect("pictures that are already grey (one channel) are not touched by the colour changes", torch.allclose(augment_batch(g1, gen(), **{**none, "color": 0.5, "gray": 1.0}), augment_batch(g1, gen(), **none), atol=1e-6))
rot = augment_batch(marker, gen(), **{**none, "rotate": 15.0})
expect("rotation moves a marked pixel by at most the angle allows (15 degrees about the centre moves a pixel 40 from the centre by at most 11)", abs(pos(rot)[0] - 10) + abs(pos(rot)[1] - 50) <= 2 * 11 + 2)

print("4. the network: three convolution stages of different sizes, pooling after each, joined, one linear layer")
m = FingerCNN()
x = torch.rand(4, 3, 64, 64)
shapes = [tuple(o.shape[1:]) for o in m.features(x)]
expect("it gives six scores per picture, and the three stages shrink the picture 64 to 32 to 16 to 8 while the filters grow 16, 32, 64: %s" % shapes, m(x).shape == (4, 6) and shapes == [(16, 32, 32), (32, 16, 16), (64, 8, 8)])
expect("the joined features are 16 x 4 x 4 + 32 x 4 x 4 + 64 x 4 x 4 = 1792 numbers, and that is exactly what the linear layer takes in", m.fc.in_features == 1792 and m.fc.out_features == 6)
expect("it has %d weights: 1216 + 4640 + 18496 in the convolutions and 10758 in the linear layer" % n_parameters(m), n_parameters(m) == 35110)
m.train(); F.cross_entropy(m(x), torch.tensor([0, 1, 2, 3])).backward()
expect("backpropagation reaches every one of the three convolution stages (every conv layer gets a non-zero gradient)", all(c.weight.grad.abs().sum() > 0 for c in m.convs))
m.eval()
expect("in evaluation mode the dropout is off, so the same picture gives the same scores every time", torch.equal(m(x), m(x)))
expect("a grey network (one channel in) works too", FingerCNN(in_channels=1)(torch.rand(2, 1, 64, 64)).shape == (2, 6))

print("5. cross-entropy, the loss")
logits = torch.tensor([[0.0, 0.0, 3.0, 0.0, 0.0, 0.0]])
p = F.softmax(logits, dim=1)
l2, l4 = F.cross_entropy(logits, torch.tensor([2])).item(), F.cross_entropy(logits, torch.tensor([4])).item()
expect("scores 0, 0, 3, 0, 0, 0 give the 2 a probability of %.2f and every other class %.2f, and they add up to 1" % (p[0, 2], p[0, 0]), abs(p[0, 2] - 0.8007) < 1e-3 and abs(p[0, 0] - 0.0399) < 1e-3 and abs(float(p.sum()) - 1) < 1e-6)
expect("the loss is -ln(probability of the true class): %.2f if the truth was 2 (right and confident), %.2f if it was 4 (confidently wrong)" % (l2, l4), abs(l2 + np.log(float(p[0, 2]))) < 1e-6 and abs(l4 + np.log(float(p[0, 4]))) < 1e-6 and abs(l2 - 0.2226) < 1e-3 and abs(l4 - 3.2226) < 1e-3)

print("6. the NumPy copy for the UNO Q")
k = np.arange(25, dtype=float).reshape(1, 5, 5)
ident = np.zeros((1, 1, 3, 3)); ident[0, 0, 1, 1] = 1
ones = np.ones((1, 1, 3, 3))
expect("a convolution with a kernel that is 1 in the middle gives the picture back; with a 3 x 3 kernel of ones a flat picture gives 9 inside and 4 in a corner (the zero padding)", np.allclose(inp.conv2d_same(k, ident, np.zeros(1)), k) and inp.conv2d_same(np.ones((1, 6, 6)), ones, np.zeros(1))[0, 3, 3] == 9 and inp.conv2d_same(np.ones((1, 6, 6)), ones, np.zeros(1))[0, 0, 0] == 4)
expect("max pooling keeps the biggest number of each 2 x 2 block, and the grid average takes block means", inp.maxpool2(np.array([[[1., 2.], [3., 4.]]]))[0, 0, 0] == 4 and np.allclose(inp.grid_mean(np.arange(16, dtype=float).reshape(1, 4, 4), 2)[0], [[2.5, 4.5], [10.5, 12.5]]))
imgs = np.random.default_rng(0).integers(0, 255, (10, 64, 64, 3)).astype(np.uint8)
worst = 0.0
for center in (True, False):
    mm = FingerCNN(center=center).eval()
    for q in mm.parameters(): q.data += 0.05 * torch.randn_like(q)
    nm = inp.NumpyFingerCNN.from_torch(mm, {"size": 64})
    for im in imgs:
        t = mm(torch.from_numpy(im).float().div(255).permute(2, 0, 1)[None]).detach().numpy()[0]
        worst = max(worst, float(np.abs(nm.logits(im) - t).max()))
expect("the NumPy network gives the same six scores as PyTorch, with and without input centring (largest difference %.1e over 20 pictures)" % worst, worst < 1e-5)
nm.save(tmp / "m.npz"); nm2 = inp.NumpyFingerCNN.load(tmp / "m.npz")
cls, pr = nm2.predict(imgs[0])
expect("it can be saved to one .npz file and loaded back with identical results; predict gives a class and six probabilities that add up to 1", np.allclose(nm2.logits(imgs[0]), nm.logits(imgs[0])) and abs(pr.sum() - 1) < 1e-9 and cls == int(pr.argmax()) and nm2.meta["cfg"]["center"] is False)
mg = FingerCNN(in_channels=1).eval(); ng = inp.NumpyFingerCNN.from_torch(mg, {"size": 64}); gi = imgs[0, :, :, :1]
expect("a grey network works in NumPy too", np.abs(ng.logits(gi) - mg(torch.from_numpy(gi).float().div(255).permute(2, 0, 1)[None]).detach().numpy()[0]).max() < 1e-5)

print("7. evaluation")
class Oracle(nn.Module):
    def forward(self, x):
        return F.one_hot(x.flatten().long(), 6).float() * 10
Xo = torch.tensor([0, 1, 2, 3, 4, 5, 3, 3]).float().view(-1, 1, 1, 1); yo = torch.tensor([0, 1, 2, 3, 4, 5, 3, 2])
acc, conf, probs = T.evaluate(Oracle(), Xo, yo)
expect("accuracy and the confusion matrix are right: 7 of 8 correct, and the one mistake is a true 2 called a 3", abs(acc - 7 / 8) < 1e-9 and conf.sum() == 8 and conf[2, 3] == 1 and np.trace(conf) == 7 and probs.shape == (8, 6))

print("8. training works, and repeats")
write_synthetic(tmp / "ds2", ("A", "B"), per_class=70, seed=2)
d2 = D.load_dataset(tmp / "ds2", 32)
X2, y2 = D.to_tensor(d2["X"]), torch.from_numpy(d2["y"])
v2 = torch.from_numpy(D.split_by_group(d2["group"], d2["y"], 0.2, 0))
model, hist = T.train_model(X2[~v2], y2[~v2], X2[v2], y2[v2], epochs=25, flip_axis="h")
acc2 = T.evaluate(model, X2[v2], y2[v2])[0]
expect("on made-up hands the loss falls (%.2f to %.2f) and it ends well above chance (16.7%%) on held-out groups: %.0f%%" % (hist["loss"][0], hist["loss"][-1], 100 * acc2), hist["loss"][-1] < 0.8 * hist["loss"][0] and acc2 > 0.45)
_, h1 = T.train_model(X2[:120], y2[:120], epochs=2, seed=3, flip_axis="h"); _, h2 = T.train_model(X2[:120], y2[:120], epochs=2, seed=3, flip_axis="h"); _, h3 = T.train_model(X2[:120], y2[:120], epochs=2, seed=4, flip_axis="h")
expect("the same seed gives the identical training history, another seed gives a different one", h1["loss"] == h2["loss"] and h1["loss"] != h3["loss"])

print("9. the whole command, with files out")
out, res = tmp / "models", tmp / "results"
write_synthetic(tmp / "ds3", ("A", "B"), per_class=30, seed=3)
logs = []
r = T.run(type("A", (), dict(data=str(tmp / "ds3"), out=str(out), results=str(res), size=32, gray=False, epochs=2, seed=0, flip="horizontal"))(), log=logs.append)
files = ["finger_cnn.pt", "finger_cnn.npz"], ["summary.md", "results.json", "confusion_new_person_A.png", "confusion_new_person_B.png", "curves.png"]
expect("it writes the PyTorch model, the NumPy model, the summary, the results, two confusion matrices and the curves", all((out / f).exists() for f in files[0]) and all((res / f).exists() for f in files[1]))
js = json.loads((res / "results.json").read_text())
expect("it ran a new-person test for each of the two people, there is no new-session test (one session only), and the NumPy copy matches PyTorch (%.0e)" % js["numpy_diff"], set(js["holdout"]) == {"A", "B"} and js["new_session"] is None and js["sessions"] == 1 and js["numpy_diff"] < 1e-5 and js["parameters"] == 35110 and 0 <= js["training_fit"] <= 1)
sm = (res / "summary.md").read_text()
expect("the summary states the new-person results, says which rows are the honest ones and that the last row is not a test, and lists the limits", "**a new person**" in sm and "trained without A, tested on A" in sm and "honest ones" in sm and "**not a test**" in sm and "## Limits" in sm)
ck = torch.load(out / "finger_cnn.pt", weights_only=False)
re = FingerCNN(**ck["cfg"]); re.load_state_dict(ck["state"]); re.eval()
nz = inp.NumpyFingerCNN.load(out / "finger_cnn.npz")
d3 = D.load_dataset(tmp / "ds3", 32)
expect("the saved PyTorch file reloads into a network that agrees with the saved NumPy file; the file records the picture size and who it was trained on", np.abs(re(D.to_tensor(d3["X"][:1])).detach().numpy()[0] - nz.logits(d3["X"][0])).max() < 1e-5 and ck["meta"]["size"] == 32 and ck["meta"]["trained_on"] == ["A", "B"])
write_synthetic(tmp / "one", ("A",), per_class=30, seed=4)
logs1 = []
r1 = T.run(type("A", (), dict(data=str(tmp / "one"), out=str(tmp / "m1"), results=str(tmp / "r1"), size=32, gray=False, epochs=1, seed=0, flip="none"))(), log=logs1.append)
expect("with one person there is no new-person test, and it says so plainly", r1["holdout"] == {} and any("only one person" in l for l in logs1))
try: T.run(type("A", (), dict(data=str(tmp / "nothing"), out=str(tmp / "m0"), results=str(tmp / "r0"), size=32, gray=False, epochs=1, seed=0, flip="none"))()); w1 = False
except SystemExit as e: w1 = "no pictures" in str(e)
try: T.main(["--size", "40"]); w2 = False
except SystemExit: w2 = True
expect("an empty folder and a picture size that is not a multiple of 32 are refused with a clear message", w1 and w2)

logs2 = []
r2 = T.run(type("A", (), dict(data=str(tmp / "ds3"), out=str(tmp / "m2"), results=str(tmp / "r2"), size=32, gray=False, epochs=1, seed=0, flip="horizontal", final_only=True))(), log=logs2.append)
expect("--final-only skips the new-person tests, says so, and still writes the model and the summary, which says plainly that no tests were run (it does not claim honest rows it does not have)", r2["holdout"] == {} and any("final-only" in l for l in logs2) and (tmp / "m2" / "finger_cnn.npz").exists() and "No tests were run" in (tmp / "r2" / "summary.md").read_text() and "are the honest ones" not in (tmp / "r2" / "summary.md").read_text())

print("10. sessions, and the new-session test")
m60 = 60_000
expect("a new session starts after a gap of more than an hour: pictures 0, 10 and 20 minutes in are one session, 200 and 210 minutes in another, 500 in a third", D.sessions([0, 10 * m60, 20 * m60, 200 * m60, 210 * m60, 500 * m60]).tolist() == [0, 0, 0, 1, 1, 2] and D.sessions([5 * m60, 0, 3 * m60]).tolist() == [0, 0, 0] and D.sessions([]).tolist() == [])
expect("the order does not matter, a gap of exactly the limit does not split, and the gap can be changed", D.sessions([210 * m60, 0, 200 * m60, 10 * m60]).tolist() == [1, 0, 1, 0] and D.sessions([0, 60 * m60]).tolist() == [0, 0] and D.sessions([0, 61 * m60]).tolist() == [0, 1] and D.sessions([0, 20 * m60], gap_minutes=10).tolist() == [0, 1])
expect("the loader keeps the time each picture was taken", np.array_equal(np.sort(ds["ts"]), np.sort([D.parse_name(f.name)[2] for c in range(6) for f in (tmp / "ds" / str(c)).glob("*.png") if D.parse_name(f.name)])))
write_synthetic(tmp / "two", ("A", "B"), per_class=20, seed=5)
write_synthetic(tmp / "two", ("A", "B"), per_class=20, seed=6, t0=1_700_000_000_000 + 3 * 3600 * 1000)
logs3, calls, kws = [], [], []
orig = T.train_model
def spy(Xtr, ytr, Xval=None, yval=None, *a, **k):
    calls.append((len(Xtr), Xval is None)); kws.append(k.get("aug_kwargs")); return orig(Xtr, ytr, Xval, yval, *a, **k)
T.train_model = spy
try:
    r3 = T.run(type("A", (), dict(data=str(tmp / "two"), out=str(tmp / "m3"), results=str(tmp / "r3"), size=32, gray=False, epochs=1, seed=0, flip="horizontal"))(), log=logs3.append)
finally:
    T.train_model = orig
ns = r3["new_session"]
hp = np.load(tmp / "r3" / "holdout_predictions.npz")
expect("the new-person tests save a prediction for EVERY picture, made by a network that never saw that person (%d pictures), as probabilities that add up to 1" % len(hp["files"]), len(hp["files"]) == 480 and hp["probs"].shape == (480, 6) and np.allclose(hp["probs"].sum(axis=1), 1, atol=1e-4))
expect("with two sessions it finds them (%d), and runs a new-session test: trained on the earlier session's %d pictures, tested on the last session's %d" % (r3["sessions"], ns["n_train"], ns["n"]), r3["sessions"] == 2 and ns["n"] == 240 and ns["n_train"] == 240 and any("NEW-SESSION" in l for l in logs3))
expect("the new-session test reports the accuracy for each person, and writes its confusion matrix", set(ns["per_person"]) == {"A", "B"} and (tmp / "r3" / "confusion_new_session.png").exists() and "a new session" in (tmp / "r3" / "summary.md").read_text())
expect("the default augmentation is a shift of up to 8% and a zoom of 10%, and it reaches every training the tests make", all(k == {"shift": 0.08, "scale": (0.9, 1.1)} for k in kws) and len(kws) == 4, str(kws[:1]))
kws.clear(); T.train_model = spy
try:
    T.run(type("A", (), dict(data=str(tmp / "ds3"), out=str(tmp / "m4"), results=str(tmp / "r4"), size=32, gray=False, epochs=1, seed=0, flip="horizontal", final_only=True, shift=0.2, zoom=0.15))(), log=lambda *_: None)
finally:
    T.train_model = orig
calls.pop()                                                        # the extra run above is not one of the main run's trainings
expect("--shift and --zoom change it (shift 0.2, zoom 0.15 gives a zoom range of 0.85 to 1.15) and are recorded in the model file", len(kws) == 1 and kws[0]["shift"] == 0.2 and abs(kws[0]["scale"][0] - 0.85) < 1e-9 and abs(kws[0]["scale"][1] - 1.15) < 1e-9 and torch.load(tmp / "m4" / "finger_cnn.pt", weights_only=False)["meta"]["shift"] == 0.2)
expect("every test trains on ALL the pictures it is allowed to, with nothing held back to choose an epoch: the two new-person tests on the 240 pictures of the other person each, the new-session test on 240, the final network on all 480", calls == [(240, True), (240, True), (240, True), (480, True)], str(calls))

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
