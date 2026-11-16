"""Tests for v_fit.py, make_v_spreadsheet.py and v_fit_torch.py (Anna's V).   python tests/test_v_fit.py   (the PyTorch group is skipped, and says so, if PyTorch is missing)"""
import json, sys, tempfile, zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from v_fit import (B0, EPOCHS, EPOCHS_RELU, LR_LINEAR, LR_RELU, M0, MAX_GRAD, NOISE, ReluNet, Scaler, anna_v, gradient_check, linear_gradients, linear_loss, load_data, lr_sensitivity, on_counts, survey,
                   train_linear, train_relu)

problems = 0


def expect(label, cond, detail=""):
    global problems
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    problems += (not cond)


tmp = Path(tempfile.mkdtemp())
x, y = load_data()
sc = Scaler().fit(x, y)
xn, yn = sc.tx(x), sc.ty(y)
res = json.loads((ROOT / "v_fit_results.json").read_text())

print("1. Anna's V data (AnnaCode: 120 random points, x uniform on 20 to 100, y = 2|x - 60| + noise of sigma 2)")
resid = y - 2 * np.abs(x - 60)
expect("120 points, sorted, with x between 20 and 100, the same every time", len(x) == 120 and np.all(np.diff(x) >= 0) and x.min() >= 20 and x.max() <= 100 and np.allclose(anna_v()[1], y))
expect("the noise around 2|x - 60| has a spread of about 2 (%.2f), and y runs from about 0 to 80" % resid.std(), 1.6 < resid.std() < 2.5 and y.min() < 3 and 70 < y.max() < 90)
expect("it is a V with its bottom near x = 60 (the lowest points lie at x = %.0f to %.0f)" % (x[np.argsort(y)[:3]].min(), x[np.argsort(y)[:3]].max()), 54 < x[np.argmin(y)] < 66)
vx, vy = anna_v(1)
expect("a second draw (the fresh points used for validation) is different points of the same V", not np.allclose(x, vx) and np.abs(vy - 2 * np.abs(vx - 60)).std() < 2.5)
(tmp / "v.csv").write_text("x,y\n-2,2.1\n-1,0.9\n\n0,0.1\n1,1.2\n2,1.9\n", encoding="utf-8")
cx, cy = load_data(tmp / "v.csv")
expect("your own CSV loads (for example one saved from AnnaCode): a header row and blank lines are skipped", list(cx) == [-2, -1, 0, 1, 2] and list(cy) == [2.1, 0.9, 0.1, 1.2, 1.9])
(tmp / "bad.csv").write_text("x,y\n1,2\n", encoding="utf-8")
try:
    load_data(tmp / "bad.csv"); expect("a file with too few points is refused", False)
except ValueError as e:
    expect("a file with too few points is refused, and says how many it needs", "at least 5" in str(e))

print("2. rescaling, as AnnaCode does before every fit")
expect("rescaled x and y have mean 0 and spread 1", abs(xn.mean()) < 1e-12 and abs(xn.std() - 1) < 1e-12 and abs(yn.mean()) < 1e-12 and abs(yn.std() - 1) < 1e-12)
mh, bh = 0.7, -0.3
mr, br = sc.line_to_raw(mh, bh)
expect("a line found in rescaled units, turned back into the original units, makes the same predictions (m = ys m_hat / xs, b = ym + ys b_hat - m xm)", np.allclose(mr * x + br, sc.raw_y(mh * xn + bh)))

print("3. one neuron: the gradient, by hand")
hx, hy = np.array([0.0, 1.0, 2.0]), np.array([1.0, 3.0, 5.0])
dm, db = linear_gradients(hx, hy, 0.0, 0.0)
expect("on three points (0,1) (1,3) (2,5) with m = b = 0: dL/dm = 2 mean(e x) = -26/3 and dL/db = 2 mean(e) = -6", abs(dm + 26 / 3) < 1e-12 and abs(db + 6) < 1e-12, "%.4f, %.4f" % (dm, db))
expect("that loss is mean(1, 9, 25) = 35/3", abs(linear_loss(hx, hy, 0.0, 0.0) - 35 / 3) < 1e-12)
eps = 1e-6
g = linear_gradients(xn, yn, M0, B0)
num_m = (linear_loss(xn, yn, M0 + eps, B0) - linear_loss(xn, yn, M0 - eps, B0)) / (2 * eps); num_b = (linear_loss(xn, yn, M0, B0 + eps) - linear_loss(xn, yn, M0, B0 - eps)) / (2 * eps)
expect("the formulas match finite differences on the V data", abs(g[0] - num_m) < 1e-6 and abs(g[1] - num_b) < 1e-6, "%.5f vs %.5f, %.5f vs %.5f" % (g[0], num_m, g[1], num_b))
lin = train_linear(xn, yn)
best = np.polyfit(x, y, 1)
m_end, b_end = sc.line_to_raw(lin["m"][-1], lin["b"][-1])
expect("gradient descent reaches the closed-form best line in the original units (m %.4f, b %.3f)" % tuple(best), abs(m_end - best[0]) < 1e-3 and abs(b_end - best[1]) < 1e-2)
expect("the loss falls at every one of the %d epochs" % EPOCHS, all(b < a for a, b in zip(lin["loss"][:60], lin["loss"][1:61])))
r_xy = float(np.mean(xn * yn))
expect("with rescaled data the steps follow a simple rule: b_hat shrinks by exactly 1 - 2 alpha = %.1f each step (b_hat after 5 steps = %.5f), and the gap between m_hat and its final value %.4f shrinks by that same factor each step" % (1 - 2 * LR_LINEAR, B0 * (1 - 2 * LR_LINEAR) ** 5, r_xy),
       all(abs(lin["b"][k] - B0 * (1 - 2 * LR_LINEAR) ** k) < 1e-12 for k in range(6)) and all(abs((lin["m"][k + 1] - r_xy) - (1 - 2 * LR_LINEAR) * (lin["m"][k] - r_xy)) < 1e-12 for k in range(5)))
for label, xx, yy, should_blow in (("the raw x and y", x, y, True), ("x with its mean taken off", x - sc.xm, y, True), ("x and y rescaled", xn, yn, False)):
    h = train_linear(xx, yy, m=1.0, b=0.0, lr=0.05, epochs=40, stop_if_blown_up=True)
    blown = (not np.isfinite(h["loss"][-1])) or h["loss"][-1] > 1e6
    expect("at learning rate 0.05, %s %s (loss after %d epochs: %.2e)" % (label, "BLOWS UP" if should_blow else "settles", len(h["loss"]) - 1, h["loss"][-1]), blown == should_blow)
expect("a straight line cannot fit the V: it ends flat (m = %.3f), and its typical miss (%.1f) is as big as the V is tall, against noise of %g" % (m_end, sc.ys * np.sqrt(lin["loss"][-1]), NOISE), abs(m_end) < 0.2 and sc.ys * np.sqrt(lin["loss"][-1]) > 10 * NOISE)
expect("the five steps saved in v_fit_results.json are the ones the code produces now", all(abs(res["steps"][k]["m"] - lin["m"][k]) < 1e-12 and abs(res["steps"][k]["loss"] - lin["loss"][k]) < 1e-12 for k in range(6)))

print("4. the ReLU layer")
raw = ReluNet(2); raw.w, raw.c, raw.v, raw.d = np.array([1.0, -1.0]), np.array([-60.0, 60.0]), np.array([2.0, 2.0]), 0.0
expect("two hinges make exactly Anna's V: 2 relu(x - 60) + 2 relu(60 - x) = 2|x - 60| at every x", np.allclose(raw.forward(x)[2], 2 * np.abs(x - 60)) and np.allclose(raw.forward(np.linspace(0, 120, 61))[2], 2 * np.abs(np.linspace(0, 120, 61) - 60)))
gc = gradient_check(xn, yn)
expect("backpropagation matches finite differences for every weight (largest relative difference %.1e)" % gc, gc < 1e-6)
off = ReluNet(2); off.w, off.c, off.v, off.d = np.array([1.0, 0.5]), np.array([-1000.0, 0.0]), np.array([2.0, 1.0]), 0.0
g = off.gradients(xn, yn)
expect("a ReLU neuron that is off for every point passes no gradient: its dL/dw and dL/dc are exactly 0 (the dead-ReLU problem)", g["w"][0] == 0.0 and g["c"][0] == 0.0 and g["v"][0] == 0.0 and g["w"][1] != 0.0)
big = ReluNet(1); big.w, big.c, big.v, big.d = np.array([1000.0]), np.zeros(1), np.array([1000.0]), 0.0
before = big.w.copy(); gg = big.gradients(xn, yn); big.step(gg, 1.0)
expect("every gradient is clipped to +-%g before the step, as AnnaCode does (a huge gradient moves a weight by at most alpha x %g)" % (MAX_GRAD, MAX_GRAD), abs(abs(gg["w"][0]) - 0) > MAX_GRAD and abs(before[0] - big.w[0]) <= MAX_GRAD + 1e-12)
init = ReluNet(8, seed=3)
expect("it starts like AnnaCode: zero biases, small weights (hidden: within +-1; output: within +-1/sqrt(8))", np.all(init.c == 0) and np.all(np.abs(init.w) <= 1) and np.all(np.abs(init.v) <= 1 / np.sqrt(8)) and init.d == 0)
sv = survey(xn, yn)
expect("how many of 10 random starts fit the V: 1 neuron %d, 2 neurons %d, 3 neurons %d, 4 neurons %d, 8 neurons %d, the same as v_fit_results.json says" % tuple(sv[H]["worked"] for H in (1, 2, 3, 4, 8)), {str(H): sv[H]["worked"] for H in sv} == {k: v["worked"] for k, v in res["survey"].items()})
expect("one hinge never makes a V (0 of 10), eight always do (10 of 10), and two do not always (%d of 10): the unlucky-start problem is real" % sv[2]["worked"], sv[1]["worked"] == 0 and sv[8]["worked"] == 10 and 0 < sv[2]["worked"] < 10)
stuck = res["relu_runs"]["stuck2"]; good = res["relu_runs"]["good2"]
nst, lst = train_relu(xn, yn, 2, seed=stuck["seed"])
zs = np.outer(xn, nst.w) + nst.c
expect("the unlucky 2-neuron start (seed %d) ends on a half-V (loss %.2f, between the V's 0.007 and the flat line's 1.0) with the neurons switched on for only %s of 120 points: no neuron covers the other arm, so its points send no gradient anywhere" % (stuck["seed"], lst[-1], on_counts(nst, xn)),
       0.05 <= lst[-1] < 0.9 and (zs > 0).any(axis=1).sum() < 70 and on_counts(nst, xn) == stuck["on_counts"])
ngd, lgd = train_relu(xn, yn, 2, seed=good["seed"])
expect("the good 2-neuron start (seed %d) fits the V: its average miss is %.2f, the noise level (sigma %g)" % (good["seed"], sc.ys * np.sqrt(lgd[-1]), NOISE), sc.ys * np.sqrt(lgd[-1]) < 2.4)
tvx, tvy = anna_v(1)
v2 = sc.ys * np.sqrt(ngd.loss(sc.tx(tvx), sc.ty(tvy)))
expect("on 120 fresh points from the same V it misses by %.2f, about what it does on its own training points (%.2f): it learned the V, not the noise" % (v2, sc.ys * np.sqrt(lgd[-1])), v2 < sc.ys * np.sqrt(lgd[-1]) + 0.6)
n8, l8 = train_relu(xn, yn, 8, seed=0)
v8 = sc.ys * np.sqrt(n8.loss(sc.tx(tvx), sc.ty(tvy)))
expect("8 neurons do not overfit either: fresh-point miss %.2f against training %.2f" % (v8, sc.ys * np.sqrt(l8[-1])), v8 < sc.ys * np.sqrt(l8[-1]) + 0.6)
rows = {r["lr"]: r for r in lr_sensitivity(xn, yn, seed=good["seed"])}
expect("learning rate: 0.05 is smooth (the loss rises in %d of %d epochs) and ends at %.4f; 0.1 is unstable (it rises in %d epochs, once by %.0f%%, and ends at %.2f)" % (rows[0.05]["rose"], EPOCHS_RELU, rows[0.05]["final"], rows[0.1]["rose"], 100 * rows[0.1]["largest_relative_rise"], rows[0.1]["final"]),
       rows[0.05]["rose"] < 0.02 * EPOCHS_RELU and rows[0.05]["final"] < 0.01 and rows[0.1]["rose"] > 100 and rows[0.1]["final"] > 0.1 and rows == {r["lr"]: r for r in res["lr_sensitivity"]})

print("5. the spreadsheet")
from openpyxl import load_workbook
import make_v_spreadsheet as mv
xl = ROOT / "v_fit.xlsx"
wv, wf = load_workbook(xl, data_only=True), load_workbook(xl)
expect("it has the five sheets, in order", wv.sheetnames == ["Read me", "Data", "Single neuron", "Class layout", "ReLU neuron"], str(wv.sheetnames))
s, sf = wv["Single neuron"], wf["Single neuron"]
block = [c.value for row in sf.iter_rows(min_row=13, max_row=17, min_col=2, max_col=8) for c in row if c.value is not None]
expect("every number in the five-iteration block is a formula, not a typed-in result (%d formulas)" % len(block), all(isinstance(b, str) and b.startswith("=") for b in block) and len(block) >= 25)
expect("the sheet rescales the data with the same four numbers as the code (mean and spread of x and y)", all(abs(s.cell(r, 2).value - v) < 1e-9 for r, v in zip((7, 8, 9, 10), (sc.xm, sc.xs, sc.ym, sc.ys))))
worst = 0.0
for st in res["steps"]:
    r = 13 + st["step"]
    worst = max(worst, abs(s.cell(r, 2).value - st["m"]), abs(s.cell(r, 3).value - st["b"]), abs(s.cell(r, 4).value - st["loss"]), abs(s.cell(r, 9).value - st["m_raw"]), abs(s.cell(r, 10).value - st["b_raw"]))
    if st["step"] < 5: worst = max(worst, abs(s.cell(r, 5).value - st["dm"]), abs(s.cell(r, 6).value - st["db"]))
expect("m_hat, b_hat, the loss, both gradients and the same line in the original units equal the Python run (largest difference %.1e)" % worst, worst < 1e-9)
errs = [(ws.title, c.coordinate, c.value) for ws in wv for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("#")]
expect("no formula error anywhere in the workbook", not errs, str(errs[:3]))
cl = wv["Class layout"]
expect("the Class layout sheet (one column per point, blocks of guess, db and dm) ends at the same m_hat and b_hat as the compact table, and its check cell is 0", abs(cl["B34"].value - lin["m"][5]) < 1e-9 and abs(cl["C34"].value - lin["b"][5]) < 1e-9 and s["B20"].value < 1e-9, "%.6f, %.6f" % (cl["B34"].value, cl["C34"].value))
k_pt = 37; col = 5 + k_pt                                  # spot-check the 38th data point in epochs 0 and 3
g0 = lin["m"][0] * xn[k_pt] + lin["b"][0]; g3 = lin["m"][3] * xn[k_pt] + lin["b"][3]
expect("for one data point the sheet's guess, db and dm in epochs 0 and 3 equal the numbers worked out here", abs(cl.cell(10, col).value - g0) < 1e-9 and abs(cl.cell(11, col).value - (g0 - yn[k_pt])) < 1e-9 and abs(cl.cell(12, col).value - (g0 - yn[k_pt]) * xn[k_pt]) < 1e-9 and abs(cl.cell(25, col).value - g3) < 1e-9 and abs(cl.cell(27, col).value - (g3 - yn[k_pt]) * xn[k_pt]) < 1e-9)
expect("each epoch's loss on that sheet is the loss in the compact table", all(abs(cl.cell(9 + 5 * k, 4).value - lin["loss"][k]) < 1e-9 for k in range(6)))
w_, c_ = mv.RELU_W0, mv.RELU_C0; rl = wv["ReLU neuron"]; rworst = 0.0; ons = []
for k in range(5):
    z = w_ * xn + c_; a = np.maximum(z, 0); e = a - y; on = z > 0; row = 10 + k; ons.append(int(on.sum()))
    rworst = max(rworst, abs(rl.cell(row, 2).value - w_), abs(rl.cell(row, 3).value - c_), abs(rl.cell(row, 4).value - np.mean(e ** 2)), abs(rl.cell(row, 5).value - on.sum()))
    gw, gc_ = 2 * np.mean(e * on * xn), 2 * np.mean(e * on)
    rworst = max(rworst, abs(rl.cell(row, 6).value - gw), abs(rl.cell(row, 7).value - gc_))
    w_, c_ = w_ - mv.RELU_LR * gw, c_ - mv.RELU_LR * gc_
expect("the ReLU-neuron sheet equals a separate NumPy implementation of one neuron with a ReLU (w, c, loss, points on, both gradients: largest difference %.1e)" % rworst, rworst < 1e-9)
expect("and it shows the ReLU at work: the neuron starts with %d of 120 points switched on, and the number climbs to %d as it adapts" % (ons[0], ons[-1]), ons[0] < 80 and ons[-1] > ons[0])
expect("it uses Arial throughout, blue for typed-in numbers and yellow for the cells you may change", {c.font.name for ws in wv for row in ws.iter_rows() for c in row if c.value is not None} == {"Arial"} and sf["B3"].fill.fgColor.rgb.endswith("FFFF00") and sf["B3"].font.color.rgb.endswith("0000FF") and wf["Data"]["A2"].font.color.rgb.endswith("0000FF"))
expect("both charts are in the file (the line moving toward the data, the loss falling)", len([n for n in zipfile.ZipFile(xl).namelist() if n.startswith("xl/charts/chart")]) == 2)
rm = " ".join(str(c.value) for row in wv["Read me"].iter_rows() for c in row if c.value)
expect("the Read me says the data is AnnaCode's V from seed 0, that x and y are rescaled, and why", "AnnaCode's V" in rm and "seed (0)" in rm and "blow up" in rm)

print("6. the plots")
for name in ("v_fit_data_and_fit", "v_fit_loss", "v_fit_two_hinges", "v_fit_first_five_steps"):
    f = ROOT / "images" / (name + ".png")
    expect("%s.png exists and is a real PNG of a sensible size" % name, f.exists() and f.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and 15_000 < f.stat().st_size < 600_000, str(f.stat().st_size if f.exists() else None))

print("7. PyTorch's autograd against the hand-written gradients")
try:
    import torch
    import v_fit_torch as vt
    HAVE = True
except Exception as e:
    HAVE = False; print("  (PyTorch is not installed here: skipped: %s)" % str(e)[:60])
if HAVE:
    am, ab = vt.autograd_linear(xn, yn, M0, B0); gm, gb = linear_gradients(xn, yn, M0, B0)
    expect("loss.backward() gives the same dL/dm and dL/db as the formulas (difference %.1e)" % max(abs(am - gm), abs(ab - gb)), max(abs(am - gm), abs(ab - gb)) < 1e-10)
    net = ReluNet(3, seed=1); net.c = np.random.default_rng(8).normal(0, 0.3, 3); hand, auto = net.gradients(xn, yn), vt.autograd_relu(net, xn, yn)
    d = max(float(np.max(np.abs(np.asarray(hand[k]) - np.asarray(auto[k])))) for k in hand)
    expect("loss.backward() gives the same gradient as my backpropagation for every weight of a 3-neuron ReLU layer (difference %.1e)" % d, d < 1e-10)
    sgd = vt.sgd_linear(xn, yn, 5); dd = max(max(abs(lin["m"][k] - sgd[k][0]), abs(lin["b"][k] - sgd[k][1]), abs(lin["loss"][k] - sgd[k][2])) for k in range(6))
    expect("five steps of torch.optim.SGD follow the hand-written gradient descent (difference %.1e)" % dd, dd < 1e-10)
    tl = vt.sgd_relu(ReluNet(2, seed=good["seed"]), xn, yn, 500)
    expect("500 epochs on the good 2-neuron layer end at the same loss with torch.optim.SGD (and the same +-5 clipping) as by hand (%.8f, %.8f)" % (tl[-1], lgd[500]), abs(tl[-1] - lgd[500]) < 1e-9)

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
