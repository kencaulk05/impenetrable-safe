#!/usr/bin/env python3
"""Fit Anna's V with gradient descent, by hand, in NumPy. No PyTorch: every gradient is written out so you can see where it comes from.

    python v_fit.py                       Anna's V: 120 random points, x from 20 to 100, y = 2 |x - 60| + noise (sigma 2), as in AnnaCode's "V" example
    python v_fit.py --data v_data.csv     your own data: a CSV with columns x,y (a header row is fine), for example one saved from AnnaCode

Part 1  ONE NEURON      y_hat = m x + b                               a straight line: it cannot bend into a V
Part 2  A RELU LAYER    y_hat = sum_j v_j relu(w_j x + c_j) + d      hidden neurons that each add a "hinge": the V is two hinges
Both are fitted by gradient descent on the mean squared error, the way AnnaCode does it: x and y are first rescaled to zero mean and unit spread
(otherwise the large x values make the steps blow up), the weights start small and random, and every gradient is clipped to +-5.
Writes images/*.png and v_fit_results.json.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
N_POINTS, X_MIN, X_MAX, NOISE, SEED = 120, 20.0, 100.0, 2.0, 0     # AnnaCode's "V" example (network/training.py): 120 points, x uniform on 20..100, y = 2|x-60| + N(0, 2)
LR_LINEAR, M0, B0 = 0.1, 1.0, -1.0                                   # the single neuron, in rescaled units: learning rate and where it starts
LR_RELU, EPOCHS_RELU = 0.05, 2000                                    # the ReLU layers
EPOCHS = 300                                                         # the single neuron
MAX_GRAD = 5.0                                                       # AnnaCode clips every gradient to +-5


def anna_v(seed=SEED, n=N_POINTS):
    """AnnaCode's V example: n random points, x uniform on 20..100, y = 2 |x - 60| plus Gaussian noise (sigma 2). Sorted by x so the V reads left to right.
    (In AnnaCode the points are different every time; here they come from a fixed seed so every result can be reproduced.)"""
    rng = np.random.default_rng(seed)
    x = np.sort(rng.uniform(X_MIN, X_MAX, n))
    return x, 2.0 * np.abs(x - 60.0) + rng.normal(0.0, NOISE, n)


def load_data(path=None, seed=SEED):
    """x, y arrays: Anna's V from a seed, or a CSV with columns x,y (a header row and blank lines are skipped)."""
    if path:
        rows = []
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.reader(f):
                try:
                    rows.append((float(r[0]), float(r[1])))
                except (ValueError, IndexError):
                    continue
        if len(rows) < 5:
            raise ValueError("%s: need at least 5 numeric rows of x,y" % path)
        a = np.array(rows)
        return a[:, 0], a[:, 1]
    return anna_v(seed)


class Scaler:
    """Zero mean and unit spread for x and for y, like AnnaCode's training. Fit on the data, then x_hat = (x - mean) / std."""

    def fit(self, x, y):
        self.xm, self.xs, self.ym, self.ys = float(np.mean(x)), float(np.std(x)), float(np.mean(y)), float(np.std(y))
        return self

    def tx(self, x):
        return (np.asarray(x, dtype=float) - self.xm) / self.xs

    def ty(self, y):
        return (np.asarray(y, dtype=float) - self.ym) / self.ys

    def raw_y(self, yn):
        return self.ym + self.ys * np.asarray(yn, dtype=float)

    def line_to_raw(self, m_hat, b_hat):
        """The line y_hat = m_hat x_hat + b_hat (rescaled units) as y = m x + b in the original units: m = ys m_hat / xs,  b = ym + ys b_hat - m xm."""
        m = self.ys * m_hat / self.xs
        return m, self.ym + self.ys * b_hat - m * self.xm


# ---------------------------------------------------------------------------------------------------------------------------- 1: one neuron
def linear_loss(x, y, m, b):
    return float(np.mean((m * x + b - y) ** 2))


def linear_gradients(x, y, m, b):
    """L = mean (m x + b - y)^2   so   dL/dm = 2 mean(e x)   and   dL/db = 2 mean(e)   where e = m x + b - y."""
    e = m * x + b - y
    return 2.0 * np.mean(e * x), 2.0 * np.mean(e)


def train_linear(x, y, m=M0, b=B0, lr=LR_LINEAR, epochs=EPOCHS, stop_if_blown_up=False):
    hist = {"m": [m], "b": [b], "loss": [linear_loss(x, y, m, b)], "dm": [], "db": []}
    with np.errstate(over="ignore", invalid="ignore"):
        for _ in range(epochs):
            dm, db = linear_gradients(x, y, m, b)
            m, b = m - lr * dm, b - lr * db                      # step downhill
            hist["dm"].append(dm); hist["db"].append(db)
            hist["m"].append(m); hist["b"].append(b); hist["loss"].append(linear_loss(x, y, m, b))
            if stop_if_blown_up and not np.isfinite(hist["loss"][-1]):
                break
    return hist


# ---------------------------------------------------------------------------------------------------------------------------- 2: a ReLU layer
class ReluNet:
    """One hidden layer of H ReLU neurons, then a weighted sum:   y_hat = sum_j v_j relu(w_j x + c_j) + d.
    Starts like AnnaCode: small random weights, uniform in +-1/sqrt(fan_in), and zero biases."""

    def __init__(self, H, seed=1):
        r = np.random.default_rng(seed)
        self.w = r.uniform(-1.0, 1.0, H)                         # hidden layer: one input each, so fan_in = 1
        self.c = np.zeros(H)
        self.v = r.uniform(-1.0, 1.0, H) / np.sqrt(H)            # output layer: fan_in = H
        self.d = 0.0

    def forward(self, x):
        z = np.outer(x, self.w) + self.c                         # (N, H): the pre-activations
        a = np.maximum(z, 0.0)                                   # ReLU
        return z, a, a @ self.v + self.d

    def loss(self, x, y):
        return float(np.mean((self.forward(x)[2] - y) ** 2))

    def gradients(self, x, y):
        """Backpropagation, one chain-rule step at a time.
        e = y_hat - y                          L = mean e^2          dL/dy_hat = 2e/N
        y_hat = sum v_j a_j + d                dL/dd = sum 2e/N      dL/dv_j = sum (2e/N) a_j
        a_j = relu(z_j)                        dL/dz_j = (2e/N) v_j 1[z_j > 0]    (the ReLU passes the gradient only where it is on)
        z_j = w_j x + c_j                      dL/dw_j = sum dL/dz_j x             dL/dc_j = sum dL/dz_j"""
        N = len(x)
        z, a, yhat = self.forward(x)
        dyhat = 2.0 * (yhat - y) / N
        dz = dyhat[:, None] * self.v[None, :] * (z > 0)
        return {"w": (dz * x[:, None]).sum(axis=0), "c": dz.sum(axis=0), "v": (dyhat[:, None] * a).sum(axis=0), "d": dyhat.sum()}

    def step(self, g, lr):
        clip = lambda v: np.clip(v, -MAX_GRAD, MAX_GRAD)         # AnnaCode clips each gradient to +-5
        self.w -= lr * clip(g["w"]); self.c -= lr * clip(g["c"]); self.v -= lr * clip(g["v"]); self.d -= lr * float(clip(g["d"]))


def train_relu(x, y, H, seed=1, lr=LR_RELU, epochs=EPOCHS_RELU):
    net = ReluNet(H, seed)
    loss = [net.loss(x, y)]
    for _ in range(epochs):
        net.step(net.gradients(x, y), lr)
        loss.append(net.loss(x, y))
    return net, loss


def gradient_check(x, y, H=3, seed=1, eps=1e-6):
    """The analytic gradients against (L(p + eps) - L(p - eps)) / 2 eps for every single parameter. Returns the largest relative difference."""
    net = ReluNet(H, seed)
    net.c = np.random.default_rng(seed + 7).normal(0, 0.3, H)    # nonzero biases, so the check does not sit on the kinks
    g = net.gradients(x, y)
    worst = 0.0
    for name in ("w", "c", "v"):
        arr = getattr(net, name)
        for j in range(H):
            keep = arr[j]
            arr[j] = keep + eps; up = net.loss(x, y)
            arr[j] = keep - eps; down = net.loss(x, y)
            arr[j] = keep
            num = (up - down) / (2 * eps)
            worst = max(worst, abs(num - g[name][j]) / max(1e-9, abs(num) + abs(g[name][j])))
    keep = net.d
    net.d = keep + eps; up = net.loss(x, y); net.d = keep - eps; down = net.loss(x, y); net.d = keep
    num = (up - down) / (2 * eps)
    return max(worst, abs(num - g["d"]) / max(1e-9, abs(num) + abs(g["d"])))


def on_counts(net, x):
    """For each hidden neuron: for how many of the points it is switched on (z > 0). A neuron that is on for 0 points is dead: no gradient passes through it."""
    return [int(c) for c in ((np.outer(x, net.w) + net.c) > 0).sum(axis=0)]


def survey(xn, yn, widths=(1, 2, 3, 4, 8), seeds=range(10), threshold=0.05):
    """Train every width from 10 different random starts. A fit 'works' if it ends below normalised loss 0.05 (a single hinge ends near 0.2 or more)."""
    out = {}
    for H in widths:
        runs = [train_relu(xn, yn, H, seed=s) for s in seeds]
        losses = [r[1][-1] for r in runs]
        out[H] = {"losses": losses, "worked": int(sum(l < threshold for l in losses)), "of": len(losses), "on_counts": [on_counts(r[0], xn) for r in runs]}
    return out


def lr_sensitivity(xn, yn, H=2, seed=0, rates=(0.02, 0.05, 0.1, 0.2, 0.4), epochs=EPOCHS_RELU):
    """How the learning rate changes the same run: epochs where the loss ROSE, the biggest rise, the final loss."""
    rows = []
    for lr in rates:
        _, loss = train_relu(xn, yn, H, seed=seed, lr=lr, epochs=epochs)
        l = np.array(loss); d = np.diff(l); up = d > 1e-12
        rows.append({"lr": lr, "rose": int(up.sum()), "largest_relative_rise": float((d[up] / l[:-1][up]).max()) if up.any() else 0.0, "final": float(l[-1])})
    return rows


# ---------------------------------------------------------------------------------------------------------------------------- plots
COL = {"data": "#1d2330", "lin": "#6b7280", "stuck": "#d62728", "h1": "#e08a1e", "h2": "#2ca02c", "h8": "#6f42c1"}


def make_plots(x, y, sc, lin_raw, lin_hist, runs, out, noise_var_norm=None):
    """runs: dicts {key, label, net, loss, color, ls}. Curves are drawn in the data's own units (the networks work in rescaled units)."""
    out.mkdir(exist_ok=True)
    xs = np.linspace(x.min() - 1, x.max() + 1, 400)
    xsn = sc.tx(xs)
    fig, ax = plt.subplots(figsize=(9, 5.4))
    ax.scatter(x, y, color=COL["data"], s=20, zorder=5, label="the V data (%d points)" % len(x))
    ax.plot(xs, lin_raw[0] * xs + lin_raw[1], "--", color=COL["lin"], lw=2.2, label="one neuron: y = %.2f x + %.1f  (average miss %.1f)" % (lin_raw[0], lin_raw[1], sc.ys * np.sqrt(lin_hist["loss"][-1])))
    for r in runs:
        ax.plot(xs, sc.raw_y(r["net"].forward(xsn)[2]), color=r["color"], ls=r["ls"], lw=2.2, label="%s  (average miss %.1f)" % (r["label"], sc.ys * np.sqrt(r["loss"][-1])))
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_title("Fitting the V: a line cannot bend, a ReLU layer can", fontsize=12); ax.legend(frameon=False, fontsize=8.4, loc="upper center")
    fig.tight_layout(); fig.savefig(out / "v_fit_data_and_fit.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(lin_hist["loss"], color=COL["lin"], lw=2, ls="--", label="one neuron")
    for r in runs:
        ax.plot(r["loss"], color=r["color"], ls=r["ls"], lw=2, label=r["label"])
    if noise_var_norm:
        ax.axhline(noise_var_norm, color="#aab4c3", lw=1, ls=":")
        ax.text(len(runs[0]["loss"]) * 0.99, noise_var_norm * 1.25, "noise variance of the data (sigma = %g), in these units" % NOISE, fontsize=8.2, color="#6b7280", ha="right", va="bottom")
    ax.set_yscale("log"); ax.set_xlabel("epoch (one full pass of gradient descent)"); ax.set_ylabel("loss: mean squared error (rescaled units)"); ax.set_title("The loss falls as the weights are adjusted", fontsize=12); ax.legend(frameon=False, fontsize=8.4)
    fig.tight_layout(); fig.savefig(out / "v_fit_loss.png", dpi=130); plt.close(fig)

    good = next(r for r in runs if r["key"] == "good2"); net = good["net"]; z, a, yhat = net.forward(xsn)
    fig, ax = plt.subplots(figsize=(9, 4.9))
    ax.scatter(x, y, color=COL["data"], s=20, zorder=5, label="the V data")
    for j in range(2):
        ax.plot(xs, sc.ys * net.v[j] * a[:, j], ls="--", lw=1.8, label="hidden neuron %d, in y units: %.1f x relu(%.2f x_hat %+.2f)" % (j + 1, sc.ys * net.v[j], net.w[j], net.c[j]))
    ax.plot(xs, sc.raw_y(yhat), color=COL["h2"], lw=2.6, label="their sum plus the offset = the fit")
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_title("Two hinges add up to a V (each dashed line is one hidden neuron, flat where it is switched off)", fontsize=10); ax.legend(frameon=False, fontsize=8.2, loc="upper center")
    fig.tight_layout(); fig.savefig(out / "v_fit_two_hinges.png", dpi=130); plt.close(fig)


def first_five_plot(x, y, sc, lin, out):
    out.mkdir(exist_ok=True)
    xs = np.linspace(x.min() - 1, x.max() + 1, 200)
    fig, ax = plt.subplots(figsize=(9, 5.1))
    ax.scatter(x, y, color=COL["data"], s=20, zorder=5, label="the V data")
    cmap = plt.cm.viridis
    for k in range(6):
        m, b = sc.line_to_raw(lin["m"][k], lin["b"][k])
        ax.plot(xs, m * xs + b, color=cmap(k / 5.5), lw=2, label="after %d step%s: loss %.3f" % (k, "" if k == 1 else "s", lin["loss"][k]))
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_title("The first five steps of gradient descent on m and b (these are the Excel rows)", fontsize=11); ax.legend(frameon=False, fontsize=8.5, loc="upper center", ncol=2)
    fig.tight_layout(); fig.savefig(out / "v_fit_first_five_steps.png", dpi=130); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=None, help="CSV with columns x,y (default: Anna's V from a fixed seed)")
    ap.add_argument("--out", default=str(HERE))
    a = ap.parse_args()
    x, y = load_data(a.data)
    out = Path(a.out)
    anna = a.data is None
    sc = Scaler().fit(x, y)
    xn, yn = sc.tx(x), sc.ty(y)
    print("data: %s, %d points; x from %.1f to %.1f, y from %.1f to %.1f" % ("ANNA'S V (seed %d)" % SEED if anna else a.data, len(x), x.min(), x.max(), y.min(), y.max()))
    print("rescaling: x mean %.3f spread %.3f | y mean %.3f spread %.3f" % (sc.xm, sc.xs, sc.ym, sc.ys))

    print("\nPART 1a: why the data is rescaled first (one neuron, learning rate 0.05, up to 40 epochs)")
    blow = {}
    for label, xx, yy in (("raw x and y", x, y), ("x minus its mean", x - sc.xm, y), ("x and y rescaled", xn, yn)):
        h = train_linear(xx, yy, m=1.0, b=0.0, lr=0.05, epochs=40, stop_if_blown_up=True)
        final = h["loss"][-1]
        blown = (not np.isfinite(final)) or final > 1e6
        blow[label] = {"blown_up": bool(blown), "epochs_run": len(h["loss"]) - 1, "final": None if not np.isfinite(final) else float(final)}
        print("   %-18s after %2d epochs: %s" % (label, len(h["loss"]) - 1, ("BLOWN UP (loss %s)" % ("inf" if not np.isfinite(final) else "%.2e" % final)) if blown else "loss %.3f (settling)" % final))
    lin = train_linear(xn, yn)
    print("\nPART 1b: one neuron, y_hat = m x_hat + b   (start m = %g, b = %g, learning rate %g, in rescaled units)" % (M0, B0, LR_LINEAR))
    print("%-5s %9s %9s %9s | %10s %10s | %10s %10s" % ("step", "m_hat", "b_hat", "loss", "dL/dm", "dL/db", "m (raw)", "b (raw)"))
    for k in range(6):
        dm, db = (lin["dm"][k], lin["db"][k]) if k < len(lin["dm"]) else (np.nan, np.nan)
        mr, br = sc.line_to_raw(lin["m"][k], lin["b"][k])
        print("%-5d %9.4f %9.4f %9.4f | %10.4f %10.4f | %10.4f %10.4f" % (k, lin["m"][k], lin["b"][k], lin["loss"][k], dm, db, mr, br))
    best = np.polyfit(x, y, 1)
    m_end, b_end = sc.line_to_raw(lin["m"][-1], lin["b"][-1])
    print("after %d epochs: m = %.4f, b = %.4f (raw units), average miss %.2f | closed-form best line: m = %.4f, b = %.4f" % (EPOCHS, m_end, b_end, sc.ys * np.sqrt(lin["loss"][-1]), best[0], best[1]))

    print("\nPART 2: a hidden layer of ReLU neurons   (learning rate %g, %d epochs, rescaled units)" % (LR_RELU, EPOCHS_RELU))
    sv = survey(xn, yn)
    spec = [("h1", "ReLU layer, 1 hidden neuron", 1, "-", COL["h1"]), ("good2", "2 hidden neurons", 2, "-", COL["h2"]), ("h8", "8 hidden neurons", 8, "-", COL["h8"])]
    half = lambda l: 0.05 <= l < 0.9                                     # a one-armed fit: better than the flat line, far from the V
    seeds = {"h1": next((s for s, l in enumerate(sv[1]["losses"]) if half(l)), 0), "good2": next((s for s, l in enumerate(sv[2]["losses"]) if l < 0.05), 0), "h8": 0}
    fails = [s for s, l in enumerate(sv[2]["losses"]) if half(l)] or [s for s, l in enumerate(sv[2]["losses"]) if l >= 0.05]
    if fails:
        spec.insert(1, ("stuck2", "2 hidden neurons, unlucky start (seed %d)" % fails[0], 2, "--", COL["stuck"]))
        seeds["stuck2"] = fails[0]
    runs = []
    for key, label, H, ls, color in spec:
        net, loss = train_relu(xn, yn, H, seed=seeds[key])
        runs.append({"key": key, "label": label, "net": net, "loss": loss, "color": color, "ls": ls, "H": H, "seed": seeds[key]})
        print("   %-46s loss %.4f -> %.4f   average miss %.2f (noise sigma %g)   switched on for %s of %d points" % (label, loss[0], loss[-1], sc.ys * np.sqrt(loss[-1]), NOISE, on_counts(net, xn), len(xn)))
    print("\n   how many of 10 random starts fit the V (loss below 0.05)?   " + "   ".join("%d neurons: %d" % (H, v["worked"]) for H, v in sv.items()))
    for H in (1, 2):
        print("   %d hidden neuron%s, the starts that did not fit: %s" % (H, "" if H == 1 else "s", "; ".join("seed %d: loss %.2f, on for %s points%s" % (sd, l, oc, " (a DEAD neuron)" if 0 in oc and l > 0.9 else "") for sd, (l, oc) in enumerate(zip(sv[H]["losses"], sv[H]["on_counts"])) if l >= 0.05) or "none"))
    tv = None
    if anna:
        vx, vy = anna_v(SEED + 1)
        vxn, vyn = sc.tx(vx), sc.ty(vy)
        tv = {r["key"]: {"train": r["loss"][-1], "validation": r["net"].loss(vxn, vyn)} for r in runs}
        tv["line"] = {"train": lin["loss"][-1], "validation": linear_loss(vxn, vyn, lin["m"][-1], lin["b"][-1])}
        print("\n   fresh points the networks never saw (a second draw of the same V), average miss in y units:")
        for k, v in tv.items():
            print("   %-46s training %.2f   validation %.2f" % (k, sc.ys * np.sqrt(v["train"]), sc.ys * np.sqrt(v["validation"])))
    lrs = lr_sensitivity(xn, yn, seed=seeds["good2"])
    print("\n   learning rate for the good 2-neuron run:\n   " + "\n   ".join("%-5g loss rose in %4d of %d epochs (largest rise %.1e of the loss), final loss %.4f" % (r["lr"], r["rose"], EPOCHS_RELU, r["largest_relative_rise"], r["final"]) for r in lrs))
    gc = gradient_check(xn, yn)
    print("\ngradient check (analytic against finite differences, every parameter): largest relative difference %.2e" % gc)
    noise_norm = (NOISE / sc.ys) ** 2 if anna else None
    make_plots(x, y, sc, (m_end, b_end), lin, runs, out / "images", noise_norm)
    first_five_plot(x, y, sc, lin, out / "images")
    good = next(r for r in runs if r["key"] == "good2")["net"]
    res = {"anna": anna, "n_points": int(len(x)), "x_range": [float(x.min()), float(x.max())], "scaler": {"xm": sc.xm, "xs": sc.xs, "ym": sc.ym, "ys": sc.ys}, "blow_up_demo": blow,
           "lr_linear": LR_LINEAR, "m0": M0, "b0": B0, "epochs": EPOCHS, "lr_relu": LR_RELU, "epochs_relu": EPOCHS_RELU, "noise_sigma": NOISE if anna else None, "noise_variance_norm": noise_norm,
           "steps": [{"step": k, "m": lin["m"][k], "b": lin["b"][k], "loss": lin["loss"][k], "dm": lin["dm"][k] if k < len(lin["dm"]) else None, "db": lin["db"][k] if k < len(lin["db"]) else None,
                      "m_raw": sc.line_to_raw(lin["m"][k], lin["b"][k])[0], "b_raw": sc.line_to_raw(lin["m"][k], lin["b"][k])[1]} for k in range(6)],
           "linear_final": {"m_raw": m_end, "b_raw": b_end, "loss": lin["loss"][-1], "average_miss": sc.ys * float(np.sqrt(lin["loss"][-1]))}, "closed_form": {"m": float(best[0]), "b": float(best[1])},
           "relu_runs": {r["key"]: {"H": r["H"], "seed": r["seed"], "final_loss": r["loss"][-1], "average_miss": sc.ys * float(np.sqrt(r["loss"][-1])), "on_counts": on_counts(r["net"], xn)} for r in runs},
           "relu_good2": {"w": good.w.tolist(), "c": good.c.tolist(), "v": good.v.tolist(), "d": float(good.d)}, "survey": {str(H): v for H, v in sv.items()}, "train_validation": tv,
           "lr_sensitivity": lrs, "gradient_check_max_rel_diff": gc}
    (out / "v_fit_results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("wrote images/ and v_fit_results.json")


if __name__ == "__main__":
    main()
