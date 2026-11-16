#!/usr/bin/env python3
"""Fit Anna's V by gradient descent, with every gradient written out (NumPy, no autograd).

    python v_fit.py

Part 1  one neuron with a ReLU:       y_hat = relu(m x + b)                        the same model, data and start as v_fit.xlsx
Part 2  a hidden layer of ReLU neurons: y_hat = sum_j v_j relu(w_j x + c_j) + d    two hidden neurons, two hinges: enough for a V
Writes images/v_fit_data_and_fit.png and images/v_fit_loss.png.
"""
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
EPOCHS = 2000
ALPHA_NEURON, M0, B0 = 0.0001, 0.1, 0.0      # part 1: the same learning rate and start as the spreadsheet
ALPHA_LAYER, H, SEED = 0.05, 2, 2            # part 2: learning rate, number of hidden neurons, random start


def anna_v():
    """AnnaCode's V: 120 points, x uniform on 20..100, y = 2|x - 60| + noise (sigma 2). Fixed seed and 4 decimals, so it is the spreadsheet's data."""
    rng = np.random.default_rng(0)
    x = np.sort(rng.uniform(20, 100, 120))
    y = 2 * np.abs(x - 60) + rng.normal(0, 2, 120)
    return np.round(x, 4), np.round(y, 4)


# ------------------------------------------------------------------ part 1: one neuron with a ReLU
def neuron_step(x, y, m, b):
    """z = m x + b,  a = relu(z),  e = y - a,  r = 1 where z > 0.
    de/dm = -(2/N) sum(e r x),  de/db = -(2/N) sum(e r)."""
    z = m * x + b
    a = np.maximum(z, 0)
    r = (z > 0) * 1.0
    e = y - a
    loss = np.mean(e ** 2)
    dm = -2 * np.mean(e * r * x)
    db = -2 * np.mean(e * r)
    return loss, dm, db


def train_neuron(x, y):
    m, b = M0, B0
    losses = []
    print("Part 1: one neuron, relu(m x + b), alpha = %g" % ALPHA_NEURON)
    print("%9s %9s %9s %12s %10s %9s %9s %10s" % ("iteration", "m", "b", "de/dm", "de/db", "new m", "new b", "loss"))
    for epoch in range(1, EPOCHS + 1):
        loss, dm, db = neuron_step(x, y, m, b)
        new_m, new_b = m - ALPHA_NEURON * dm, b - ALPHA_NEURON * db
        if epoch <= 5:                                        # the five rows of the spreadsheet
            print("%9d %9.4f %9.4f %12.4f %10.4f %9.4f %9.4f %10.2f" % (epoch, m, b, dm, db, new_m, new_b, loss))
        losses.append(loss)
        m, b = new_m, new_b
    print("after %d epochs: m = %.4f, b = %.4f, loss = %.1f\n" % (EPOCHS, m, b, losses[-1]))
    return m, b, losses


# ------------------------------------------------------------------ part 2: a hidden layer of ReLU neurons
def train_layer(x, y):
    """The data is rescaled to mean 0 and spread 1 first (as AnnaCode does), so one learning rate suits every weight."""
    xm, xs, ym, ys = x.mean(), x.std(), y.mean(), y.std()
    xn, yn = (x - xm) / xs, (y - ym) / ys
    rng = np.random.default_rng(SEED)
    w = rng.uniform(-1, 1, H)                 # hidden weights
    c = np.zeros(H)                           # hidden biases
    v = rng.uniform(-1, 1, H) / np.sqrt(H)    # output weights
    d = 0.0                                   # output bias
    N = len(x)
    losses = []
    for epoch in range(EPOCHS):
        # forward pass
        z = np.outer(xn, w) + c               # (N, H)
        a = np.maximum(z, 0)
        y_hat = a @ v + d
        e = y_hat - yn
        losses.append(np.mean(e ** 2) * ys ** 2)              # in y units, so it can be compared with part 1
        # backpropagation, one chain-rule step at a time
        dy = 2 * e / N                         # dL/dy_hat
        dd = dy.sum()                          # dL/dd
        dv = a.T @ dy                          # dL/dv_j = sum dy a_j
        dz = dy[:, None] * v * (z > 0)         # dL/dz_j = dy v_j 1[z_j > 0]
        dw = dz.T @ xn                         # dL/dw_j = sum dz_j x
        dc = dz.sum(axis=0)                    # dL/dc_j = sum dz_j
        # gradient descent
        w, c, v, d = w - ALPHA_LAYER * dw, c - ALPHA_LAYER * dc, v - ALPHA_LAYER * dv, d - ALPHA_LAYER * dd
    print("Part 2: a hidden layer of %d ReLU neurons, alpha = %g (rescaled data)" % (H, ALPHA_LAYER))
    print("after %d epochs: loss = %.2f, typical miss = %.2f (the noise is 2)" % (EPOCHS, losses[-1], np.sqrt(losses[-1])))

    def predict(xx):
        return ym + ys * (np.maximum(np.outer((xx - xm) / xs, w) + c, 0) @ v + d)
    return predict, losses


# ------------------------------------------------------------------ plots
def main():
    x, y = anna_v()
    m, b, loss_neuron = train_neuron(x, y)
    predict, loss_layer = train_layer(x, y)

    out = HERE / "images"
    out.mkdir(exist_ok=True)
    xs = np.linspace(15, 105, 300)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(x, y, s=15, color="#333333", label="the V data")
    ax.plot(xs, np.maximum(m * xs + b, 0), color="#E15759", lw=2, label="one neuron: relu(%.3f x %+.3f)" % (m, b))
    ax.plot(xs, predict(xs), color="#4E79A7", lw=2, label="hidden layer, %d ReLU neurons" % H)
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_title("The data and the fit after %d epochs" % EPOCHS); ax.legend()
    fig.tight_layout(); fig.savefig(out / "v_fit_data_and_fit.png", dpi=120); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(range(1, EPOCHS + 1), loss_neuron, color="#E15759", lw=2, label="one neuron")
    ax.plot(range(1, EPOCHS + 1), loss_layer, color="#4E79A7", lw=2, label="hidden layer, %d ReLU neurons" % H)
    ax.set_yscale("log"); ax.set_xlabel("epoch"); ax.set_ylabel("loss (mean squared error)"); ax.set_title("Loss as a function of epoch"); ax.legend()
    fig.tight_layout(); fig.savefig(out / "v_fit_loss.png", dpi=120); plt.close(fig)
    print("\nwrote images/v_fit_data_and_fit.png and images/v_fit_loss.png")


if __name__ == "__main__":
    main()
