"""The trained finger network in plain NumPy: the same arithmetic as the PyTorch model, with no PyTorch needed (the UNO Q runs this one).

A convolution slides each small filter over the picture and, at every position, multiplies the filter's numbers with the pixels under it and adds them up. Here that is
done with a sliding window and one tensordot. Max pooling keeps the biggest number in every 2 x 2 block. The three pooled stages are squeezed to 4 x 4, joined, and one
linear layer makes six scores.
"""
import json

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def conv2d_same(x, w, b):
    """x (C, H, W), w (O, C, k, k), b (O,) -> (O, H, W): stride 1, zero padding so the size stays the same (as PyTorch's padding=k//2)."""
    p = w.shape[2] // 2
    win = sliding_window_view(np.pad(x, ((0, 0), (p, p), (p, p))), (w.shape[2], w.shape[3]), axis=(1, 2))      # (C, H, W, k, k)
    return np.tensordot(win, w, axes=([0, 3, 4], [1, 2, 3])).transpose(2, 0, 1) + b[:, None, None]


def maxpool2(x):
    C, H, W = x.shape
    return x.reshape(C, H // 2, 2, W // 2, 2).max(axis=(2, 4))


def grid_mean(x, g):
    """Average each (H/g x W/g) block: the same as PyTorch's adaptive average pooling when the size divides evenly."""
    C, H, W = x.shape
    assert H % g == 0 and W % g == 0, "the picture size must divide evenly by the grid"
    return x.reshape(C, g, H // g, g, W // g).mean(axis=(2, 4))


def softmax(z):
    e = np.exp(z - z.max())
    return e / e.sum()


class NumpyFingerCNN:
    def __init__(self, params, meta):
        self.p = {k: np.asarray(v, dtype=np.float64) for k, v in params.items()}
        self.meta = meta
        self.grid = meta["cfg"]["grid"]

    @classmethod
    def from_torch(cls, model, meta):
        p = {}
        for i, conv in enumerate(model.convs):
            p["conv%d_w" % i], p["conv%d_b" % i] = conv.weight.detach().cpu().numpy(), conv.bias.detach().cpu().numpy()
        p["fc_w"], p["fc_b"] = model.fc.weight.detach().cpu().numpy(), model.fc.bias.detach().cpu().numpy()
        return cls(p, {**meta, "cfg": model.cfg})

    def save(self, path):
        np.savez(path, meta=json.dumps(self.meta), **self.p)

    @classmethod
    def load(cls, path):
        z = np.load(path, allow_pickle=False)
        return cls({k: z[k] for k in z.files if k != "meta"}, json.loads(str(z["meta"])))

    def logits(self, img):
        """img: (H, W, C) uint8 RGB (or grey), already the size the network was trained at. Returns six scores."""
        x = np.asarray(img, dtype=np.float64) / 255.0
        if self.meta["cfg"].get("center", False):
            x = (x - 0.5) / 0.25
        x = x.transpose(2, 0, 1) if x.ndim == 3 else x[None]
        feats = []
        for i in range(3):
            x = maxpool2(np.maximum(conv2d_same(x, self.p["conv%d_w" % i], self.p["conv%d_b" % i]), 0.0))
            feats.append(grid_mean(x, self.grid).reshape(-1))
        return self.p["fc_w"] @ np.concatenate(feats) + self.p["fc_b"]

    def predict(self, img):
        """(the class with the highest probability, the six probabilities)."""
        pr = softmax(self.logits(img))
        return int(pr.argmax()), pr
