#!/usr/bin/env python3
"""The same fit in PyTorch: autograd finds the gradients we derived by hand.

    python v_fit_torch.py [--data v_data.csv]

It checks three things, in float64 so the comparison is tight (the data is rescaled first, as in v_fit.py):
  1. the single neuron: loss.backward() gives the same dL/dm and dL/db as the formulas  2 mean(e x)  and  2 mean(e)
  2. the ReLU layer: loss.backward() gives the same gradient for every weight as the backpropagation in v_fit.py
  3. training with torch.optim.SGD follows the hand-written gradient descent step for step
"""
import argparse

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from v_fit import B0, EPOCHS_RELU, LR_LINEAR, LR_RELU, M0, ReluNet, Scaler, linear_gradients, load_data, train_linear, train_relu

torch.set_default_dtype(torch.float64)


def autograd_linear(x, y, m, b):
    xt, yt = torch.tensor(x), torch.tensor(y)
    mt, bt = torch.tensor(m, requires_grad=True), torch.tensor(b, requires_grad=True)
    loss = ((mt * xt + bt - yt) ** 2).mean()
    loss.backward()                                    # backpropagation: the chain rule, applied for us
    return mt.grad.item(), bt.grad.item()


def torch_model_from(net):
    """An nn.Sequential with exactly the weights of a ReluNet: Linear(1, H), ReLU, Linear(H, 1)."""
    H = len(net.w)
    m = nn.Sequential(nn.Linear(1, H), nn.ReLU(), nn.Linear(H, 1))
    with torch.no_grad():
        m[0].weight.copy_(torch.tensor(net.w).reshape(H, 1)); m[0].bias.copy_(torch.tensor(net.c))
        m[2].weight.copy_(torch.tensor(net.v).reshape(1, H)); m[2].bias.copy_(torch.tensor([net.d]))
    return m


def autograd_relu(net, x, y):
    m = torch_model_from(net)
    loss = F.mse_loss(m(torch.tensor(x).reshape(-1, 1)).squeeze(1), torch.tensor(y))
    loss.backward()
    return {"w": m[0].weight.grad.reshape(-1).numpy(), "c": m[0].bias.grad.numpy(), "v": m[2].weight.grad.reshape(-1).numpy(), "d": m[2].bias.grad.item()}


def sgd_linear(x, y, steps=5):
    lin = nn.Linear(1, 1)
    with torch.no_grad():
        lin.weight.fill_(M0); lin.bias.fill_(B0)
    opt = torch.optim.SGD(lin.parameters(), lr=LR_LINEAR)
    xt, yt = torch.tensor(x).reshape(-1, 1), torch.tensor(y).reshape(-1, 1)
    out = [(lin.weight.item(), lin.bias.item(), F.mse_loss(lin(xt), yt).item())]
    for _ in range(steps):
        opt.zero_grad(); F.mse_loss(lin(xt), yt).backward(); opt.step()
        out.append((lin.weight.item(), lin.bias.item(), F.mse_loss(lin(xt), yt).item()))
    return out


def sgd_relu(net, x, y, epochs, lr=LR_RELU):
    """torch.optim.SGD with the same +-5 gradient clipping that v_fit.py uses (AnnaCode clips each gradient)."""
    m = torch_model_from(net)
    opt = torch.optim.SGD(m.parameters(), lr=lr)
    xt, yt = torch.tensor(x).reshape(-1, 1), torch.tensor(y)
    losses = [F.mse_loss(m(xt).squeeze(1), yt).item()]
    for _ in range(epochs):
        opt.zero_grad(); F.mse_loss(m(xt).squeeze(1), yt).backward()
        for p in m.parameters():
            p.grad.clamp_(-5.0, 5.0)
        opt.step()
        losses.append(F.mse_loss(m(xt).squeeze(1), yt).item())
    return losses


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=None)
    a = ap.parse_args()
    x, y = load_data(a.data)
    sc = Scaler().fit(x, y)
    xn, yn = sc.tx(x), sc.ty(y)
    gm, gb = linear_gradients(xn, yn, M0, B0)
    am, ab = autograd_linear(xn, yn, M0, B0)
    print("1. single neuron at m_hat = %g, b_hat = %g:\n   by hand   dL/dm = %.10f  dL/db = %.10f\n   autograd  dL/dm = %.10f  dL/db = %.10f   (difference %.1e)" % (M0, B0, gm, gb, am, ab, max(abs(gm - am), abs(gb - ab))))
    net = ReluNet(3, seed=1)
    net.c = np.random.default_rng(8).normal(0, 0.3, 3)
    hand, auto = net.gradients(xn, yn), autograd_relu(net, xn, yn)
    diff = max(float(np.max(np.abs(np.asarray(hand[k]) - np.asarray(auto[k])))) for k in hand)
    print("2. ReLU layer, 3 hidden neurons: largest difference over every weight, by hand against autograd: %.1e" % diff)
    lin = train_linear(xn, yn, epochs=5)
    sgd = sgd_linear(xn, yn, 5)
    d1 = max(max(abs(lin["m"][k] - sgd[k][0]), abs(lin["b"][k] - sgd[k][1]), abs(lin["loss"][k] - sgd[k][2])) for k in range(6))
    print("3. five steps of gradient descent on m and b, by hand against torch.optim.SGD: largest difference %.1e" % d1)
    seed = next(s for s in range(10) if train_relu(xn, yn, 2, seed=s, epochs=300)[1][-1] < 0.5)
    hand_net, hand_loss = train_relu(xn, yn, 2, seed=seed, epochs=EPOCHS_RELU)
    t_loss = sgd_relu(ReluNet(2, seed=seed), xn, yn, EPOCHS_RELU)
    print("   %d epochs on a 2-neuron ReLU layer (seed %d): final loss by hand %.8f, with torch.optim.SGD %.8f" % (EPOCHS_RELU, seed, hand_loss[-1], t_loss[-1]))


if __name__ == "__main__":
    main()
