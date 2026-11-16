"""The finger-counting network.

Three convolution layers of DIFFERENT SIZES (16, 32 and 64 filters), each followed by ReLU and 2 x 2 max pooling, so the picture shrinks 64 -> 32 -> 16 -> 8 while the number of
feature maps grows. The output of ALL THREE stages is squeezed to a 4 x 4 grid, joined together, and one linear layer turns them into six scores, one per class (0 to 5 fingers).
Training uses cross-entropy loss: softmax turns the six scores into probabilities, and the loss is -ln(probability of the true class).

    picture (3 x 64 x 64)
      conv 5x5, 16 filters + ReLU + max-pool  ->  16 x 32 x 32   -- squeezed to 16 x 4 x 4 --+
      conv 3x3, 32 filters + ReLU + max-pool  ->  32 x 16 x 16   -- squeezed to 32 x 4 x 4 --+--> join (1792 numbers) -> dropout -> linear -> 6 scores
      conv 3x3, 64 filters + ReLU + max-pool  ->  64 x  8 x  8   -- squeezed to 64 x 4 x 4 --+

Why join all three stages: early layers see small details (edges, fingertips), later layers see larger shapes (a whole finger, the palm), and the classifier can use both.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

CLASSES = 6


class FingerCNN(nn.Module):
    def __init__(self, in_channels=3, n_classes=CLASSES, filters=(16, 32, 64), kernels=(5, 3, 3), grid=4, dropout=0.3, center=True):
        super().__init__()
        self.cfg = {"in_channels": in_channels, "n_classes": n_classes, "filters": tuple(filters), "kernels": tuple(kernels), "grid": grid, "dropout": dropout, "center": center}
        chans = (in_channels,) + tuple(filters)
        self.convs = nn.ModuleList([nn.Conv2d(chans[i], chans[i + 1], kernels[i], padding=kernels[i] // 2) for i in range(3)])
        self.grid = grid
        self.center = center
        self.drop = nn.Dropout(dropout)
        self.fc = nn.Linear(grid * grid * sum(filters), n_classes)

    def features(self, x):
        """The three pooled feature maps (what the animation will show)."""
        if self.center:
            x = (x - 0.5) / 0.25                                       # pixel values 0..1 become about -2..2, which makes the learning faster
        outs = []
        for conv in self.convs:
            x = F.max_pool2d(F.relu(conv(x)), 2)
            outs.append(x)
        return outs

    def forward(self, x):
        outs = self.features(x)
        joined = torch.cat([F.adaptive_avg_pool2d(o, self.grid).flatten(1) for o in outs], dim=1)
        return self.fc(self.drop(joined))


def n_parameters(model):
    return sum(p.numel() for p in model.parameters())
