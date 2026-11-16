"""Making more training pictures from the ones you took: rotate, shift and zoom a little, mirror, change the brightness and contrast, add a touch of noise.
Every change keeps the number of fingers the same, so the label is still right. Done on whole batches with PyTorch (no extra libraries)."""
import math

import torch
import torch.nn.functional as F


def augment_batch(x, gen, rotate=15.0, shift=0.08, scale=(0.9, 1.1), flip=0.5, flip_axis="v", brightness=0.25, contrast=0.25, noise=0.01, color=0.25, gray=0.2):
    """x: float tensor (B, C, H, W) in [0, 1]. gen: a torch.Generator, so the result can be repeated.
    rotate: degrees either way | shift: fraction of the picture either way | scale: zoom range | flip: chance of mirroring.

    The mirror must be ACROSS the direction the fingers point, so that it turns a left hand into a right hand (and back) WITHOUT changing which way the fingers point.
    Fingers pointing sideways (the arm comes in from the left or right): flip_axis='v' mirrors top-to-bottom. Fingers pointing up or down: flip_axis='h' mirrors left-to-right.
    color: each colour channel is multiplied by a random number between 1 - color and 1 + color (skin tone and the colour of the light vary from person to person);
    gray: the chance that a picture loses its colour completely, so the network cannot rely on skin colour alone.
    The other mirror would turn 'fingers pointing right' into 'fingers pointing left', a pose that is never shown to the lock. flip_axis=None: no mirror."""
    B = x.shape[0]
    u = lambda lo, hi: lo + (hi - lo) * torch.rand(B, generator=gen)
    ang = u(-rotate, rotate) * math.pi / 180.0
    s = u(scale[0], scale[1])
    tx, ty = u(-shift, shift) * 2.0, u(-shift, shift) * 2.0                    # the grid runs from -1 to 1, so a fraction f of the picture is 2 f
    f = (torch.rand(B, generator=gen) < flip).float() * -2.0 + 1.0 if flip_axis else torch.ones(B)       # -1 mirrors, +1 leaves it
    fv, fh = (f, torch.ones(B)) if flip_axis == "v" else ((torch.ones(B), f) if flip_axis == "h" else (torch.ones(B), torch.ones(B)))
    cos, sin = torch.cos(ang) / s, torch.sin(ang) / s
    theta = torch.zeros(B, 2, 3)
    theta[:, 0, 0], theta[:, 0, 1], theta[:, 0, 2] = cos * fh, -sin * fv, tx
    theta[:, 1, 0], theta[:, 1, 1], theta[:, 1, 2] = sin * fh, cos * fv, ty
    grid = F.affine_grid(theta, list(x.shape), align_corners=False)
    out = F.grid_sample(x, grid, mode="bilinear", padding_mode="border", align_corners=False)
    b = u(-brightness, brightness).view(B, 1, 1, 1)
    c = u(-contrast, contrast).view(B, 1, 1, 1)
    if out.shape[1] == 3:
        if color:
            out = out * (1 - color + 2 * color * torch.rand(B, 3, generator=gen)).view(B, 3, 1, 1)
        if gray:
            lum = (0.299 * out[:, 0:1] + 0.587 * out[:, 1:2] + 0.114 * out[:, 2:3]).expand(-1, 3, -1, -1)
            out = torch.where((torch.rand(B, generator=gen) < gray).view(B, 1, 1, 1), lum, out)
    mean = out.mean(dim=(1, 2, 3), keepdim=True)
    out = (out - mean) * (1 + c) + mean * (1 + b)
    if noise:
        out = out + noise * torch.randn(out.shape, generator=gen)
    return out.clamp(0.0, 1.0)
