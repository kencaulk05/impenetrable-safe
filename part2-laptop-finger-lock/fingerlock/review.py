"""Finding pictures whose LABEL may be wrong or ambiguous: the ones the trained network confidently disagrees with.

A picture labelled 1 that shows a thumbs-up, or labelled 4 with the thumb out, will be called something else by a network trained on everything else. Looking at those
pictures (and moving the unclear ones out of the training data) often improves a network more than changing the network."""
import shutil
from pathlib import Path

import cv2
import numpy as np


def find_disagreements(files, labels, probs, min_conf=0.8):
    """Rows (file, true label, predicted class, confidence) for every picture where the network's top class is not its label and it is at least min_conf sure,
    most confident first. probs: (N, 6) array."""
    probs = np.asarray(probs)
    pred, conf = probs.argmax(axis=1), probs.max(axis=1)
    rows = [(files[i], int(labels[i]), int(pred[i]), float(conf[i])) for i in range(len(files)) if pred[i] != labels[i] and conf[i] >= min_conf]
    return sorted(rows, key=lambda r: -r[3])


def move_flagged(rows, review_dir):
    """Move the flagged pictures to <review_dir>/<their label>/ (nothing is deleted, and you can move them back). Returns how many were moved."""
    n = 0
    for f, label, pred, conf in rows:
        dest = Path(review_dir) / str(label)
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / Path(f).name
        if Path(f).exists() and not target.exists():
            shutil.move(str(f), str(target)); n += 1
    return n


def contact_sheet(rows, path, per_row=8, thumb=96):
    """One picture of the flagged pictures, each labelled 'really X, said Y (confidence)'."""
    cells = []
    for f, label, pred, conf in rows:
        im = cv2.resize(cv2.imread(str(f)), (thumb, thumb), interpolation=cv2.INTER_AREA)
        cv2.putText(im, "%d>%d %.0f%%" % (label, pred, 100 * conf), (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1, cv2.LINE_AA)
        cells.append(im)
    if not cells:
        return False
    while len(cells) % per_row:
        cells.append(np.full_like(cells[0], 255))
    cv2.imwrite(str(path), np.vstack([np.hstack(cells[i:i + per_row]) for i in range(0, len(cells), per_row)]))
    return True


def load_predictions(path, ds):
    """(probs, files, labels) from the file train.py saved, matched to the pictures in the dataset by file name, so it still works if the folder was moved.
    Pictures that were not in that run are left out."""
    z = np.load(path, allow_pickle=False)
    by_name = {Path(str(f)).name: p for f, p in zip(z["files"], z["probs"])}
    keep = [i for i, f in enumerate(ds["files"]) if Path(f).name in by_name]
    return np.stack([by_name[Path(ds["files"][i]).name] for i in keep]), [ds["files"][i] for i in keep], ds["y"][keep]
