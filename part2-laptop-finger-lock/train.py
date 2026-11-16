#!/usr/bin/env python3
"""Train the finger-counting network on the pictures the capture tool saved.

    python train.py --data data/raw                       train, test, and write models/ and results/
    python train.py --data data/raw --epochs 5            a quick run to check everything works

It does three things:
  1. NEW-PERSON TESTS (when there are at least two people): for each person, train on everyone else and test on that person. This is the honest number for
     "does it work on someone it has never seen".
  2. trains the final network on everyone, holding out whole 10-second groups of pictures (never single frames of a burst) to pick the best epoch.
  3. writes  models/finger_cnn.pt  (PyTorch)  and  models/finger_cnn.npz  (NumPy, for the UNO Q), plus  results/ : summary.md, confusion matrices, curves, the mistakes.
"""
import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from fingerlock import data as D
from fingerlock.augment import augment_batch
from fingerlock.infer_numpy import NumpyFingerCNN
from fingerlock.model import FingerCNN, n_parameters

CLASS_NAMES = ["0 (empty or fist)", "1", "2", "3", "4", "5"]


def evaluate(model, X, y, batch=256):
    """Accuracy, the confusion matrix (rows: true class, columns: what the network said) and the probabilities. No augmentation."""
    model.eval()
    probs = []
    with torch.no_grad():
        for i in range(0, len(X), batch):
            probs.append(F.softmax(model(X[i:i + batch]), dim=1))
    probs = torch.cat(probs).numpy() if probs else np.zeros((0, 6))
    pred = probs.argmax(axis=1)
    conf = np.zeros((6, 6), dtype=int)
    for t, p in zip(y.numpy(), pred):
        conf[t, p] += 1
    return float((pred == y.numpy()).mean()) if len(y) else float("nan"), conf, probs


def train_model(Xtr, ytr, Xval=None, yval=None, epochs=40, seed=0, lr=2e-3, batch=32, log=None, aug=True, flip_axis="v", center=True, aug_kwargs=None):
    """Train a new network. Returns (model, history). With a validation set, the model of the best epoch is kept."""
    torch.manual_seed(seed)
    gen = torch.Generator().manual_seed(seed)
    model = FingerCNN(in_channels=Xtr.shape[1], center=center)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    hist = {"loss": [], "train_acc": [], "val_acc": []}
    best, best_state = -1.0, None
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(len(Xtr), generator=gen)
        total, correct = 0.0, 0
        for i in range(0, len(perm), batch):
            idx = perm[i:i + batch]
            xb = augment_batch(Xtr[idx], gen, flip_axis=flip_axis, **(aug_kwargs or {})) if aug else Xtr[idx]
            out = model(xb)
            loss = F.cross_entropy(out, ytr[idx])                    # softmax + -ln(probability of the true class)
            opt.zero_grad()
            loss.backward()                                          # backpropagation through all three convolution stages
            opt.step()
            total += loss.item() * len(idx); correct += int((out.argmax(1) == ytr[idx]).sum())
        sched.step()
        hist["loss"].append(total / len(Xtr)); hist["train_acc"].append(correct / len(Xtr))
        if Xval is not None and len(Xval):
            acc = evaluate(model, Xval, yval)[0]
            hist["val_acc"].append(acc)
            if acc > best:
                best, best_state = acc, copy.deepcopy(model.state_dict())
        if log and (ep % 5 == 0 or ep == epochs - 1):
            log("    epoch %2d  loss %.3f  train accuracy %.1f%%%s" % (ep, hist["loss"][-1], 100 * hist["train_acc"][-1], "  validation %.1f%%" % (100 * hist["val_acc"][-1]) if hist["val_acc"] else ""))
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return model, hist


def recall_row(conf):
    return ["%.0f%%" % (100 * conf[c, c] / max(1, conf[c].sum())) for c in range(6)]


def plot_confusion(conf, title, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5.6, 5.0))
    ax.imshow(conf, cmap="Blues")
    for i in range(6):
        for j in range(6):
            ax.text(j, i, conf[i, j], ha="center", va="center", color="white" if conf[i, j] > conf.max() / 2 else "black", fontsize=10)
    ax.set_xticks(range(6)); ax.set_yticks(range(6)); ax.set_xlabel("what the network said"); ax.set_ylabel("how many fingers there really were")
    ax.set_title(title, fontsize=10)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def plot_curves(hist, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a, b) = plt.subplots(1, 2, figsize=(9, 3.6))
    a.plot(hist["loss"], color="#d62728"); a.set_xlabel("epoch"); a.set_ylabel("training loss (cross-entropy)"); a.set_title("The loss falls")
    b.plot([100 * v for v in hist["train_acc"]], label="training pictures (with augmentation)")
    if hist["val_acc"]:
        b.plot([100 * v for v in hist["val_acc"]], label="validation")
    b.set_xlabel("epoch"); b.set_ylabel("accuracy (%)"); b.legend(frameon=False); b.set_title("Accuracy")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def plot_mistakes(X, y, probs, path, limit=16):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    wrong = np.where(probs.argmax(1) != y.numpy())[0][:limit]
    if len(wrong) == 0:
        return False
    cols = 4; rows = (len(wrong) + cols - 1) // cols
    fig, axs = plt.subplots(rows, cols, figsize=(2.3 * cols, 2.5 * rows), squeeze=False)
    for ax in axs.ravel(): ax.axis("off")
    for ax, i in zip(axs.ravel(), wrong):
        img = X[i].permute(1, 2, 0).numpy()
        ax.imshow(img[:, :, 0] if img.shape[2] == 1 else img, cmap="gray" if img.shape[2] == 1 else None)
        ax.set_title("really %d, said %d (%.0f%%)" % (y[i], probs[i].argmax(), 100 * probs[i].max()), fontsize=8)
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)
    return True


def per_person_accuracy(probs, y, person):
    pred = probs.argmax(axis=1)
    return {p: (float((pred[person == p] == y[person == p]).mean()) if (person == p).any() else None) for p in sorted(set(person.tolist()))}


def run(args, log=print):
    t0 = time.time()
    out, res = Path(args.out), Path(args.results)
    out.mkdir(parents=True, exist_ok=True); res.mkdir(parents=True, exist_ok=True)
    flip_axis = {"vertical": "v", "horizontal": "h", "none": None}[args.flip]
    zoom = getattr(args, "zoom", 0.1)
    aug_kw = dict(shift=getattr(args, "shift", 0.08), scale=(1 - zoom, 1 + zoom))
    ds = D.load_dataset(args.data, size=args.size, gray=args.gray)
    if len(ds["y"]) == 0:
        raise SystemExit("no pictures found in %s: collect some with capture.py first" % args.data)
    X, y, person = D.to_tensor(ds["X"]), torch.from_numpy(ds["y"]), ds["person"]
    sess = D.sessions(ds["ts"], getattr(args, "session_gap", 60))
    n_sess = int(sess.max()) + 1
    people = sorted(set(person.tolist()))
    counts = {p: [int(((person == p) & (ds["y"] == c)).sum()) for c in range(6)] for p in people}
    log("%d pictures, %d %s (%s), %d session%s, %dx%d, %s%s" % (len(y), len(people), "person" if len(people) == 1 else "people", ", ".join(people), n_sess, "" if n_sess == 1 else "s", args.size, args.size, "grey" if args.gray else "colour", "; skipped %d files that are not capture-tool pictures" % len(ds["skipped"]) if ds["skipped"] else ""))
    results = {"people": people, "counts": counts, "holdout": {}, "new_session": None, "sessions": n_sess}
    mistakes = None
    held = {}                                                     # picture -> the probabilities from a network that never saw that person
    if getattr(args, "final_only", False):
        log("\n--final-only: the new-person and new-session tests are skipped")
    else:
        if len(people) >= 2:
            for p in people:
                log("\nNEW-PERSON TEST: train on every picture of everyone except %s (the last epoch: nothing is chosen using %s), test on %s" % (p, p, p))
                tr, te = person != p, person == p
                m, _ = train_model(X[tr], y[tr], None, None, args.epochs, args.seed, log=log, flip_axis=flip_axis, aug_kwargs=aug_kw)
                acc, conf, probs = evaluate(m, X[te], y[te])
                for i, pr in zip(np.where(te.numpy() if hasattr(te, "numpy") else te)[0], probs):
                    held[ds["files"][i]] = pr
                results["holdout"][p] = {"accuracy": acc, "confusion": conf.tolist(), "n": int(te.sum())}
                plot_confusion(conf, "trained without %s, tested on %s: %.0f%% right" % (p, p, 100 * acc), res / ("confusion_new_person_%s.png" % p))
                log("  accuracy on %s, a person the network never saw: %.1f%%   (per class: %s)" % (p, 100 * acc, " ".join(recall_row(conf))))
        else:
            log("\nonly one person: there is no new-person test. Collect pictures from at least one more person.")
        if n_sess >= 2:
            tr, te = sess < n_sess - 1, sess == n_sess - 1
            log("\nNEW-SESSION TEST: train on the %d earlier session%s (%d pictures), test on the last session (%d pictures)" % (n_sess - 1, "" if n_sess == 2 else "s", int(tr.sum()), int(te.sum())))
            m, _ = train_model(X[tr], y[tr], None, None, args.epochs, args.seed, log=log, flip_axis=flip_axis, aug_kwargs=aug_kw)
            acc, conf, probs = evaluate(m, X[te], y[te])
            per = per_person_accuracy(probs, y[te].numpy(), person[te])
            results["new_session"] = {"accuracy": acc, "confusion": conf.tolist(), "n": int(te.sum()), "n_train": int(tr.sum()), "per_person": per}
            plot_confusion(conf, "trained on earlier sessions, tested on the last session: %.0f%% right" % (100 * acc), res / "confusion_new_session.png")
            if plot_mistakes(X[te], y[te], probs, res / "mistakes_new_session.png"):
                mistakes = "mistakes_new_session.png"
            log("  accuracy on the last session: %.1f%%   (per person: %s; per class: %s)" % (100 * acc, ", ".join("%s %.1f%%" % (k, 100 * v) for k, v in per.items() if v is not None), " ".join(recall_row(conf))))
        else:
            log("\nonly one session: there is no new-session test (a new session starts after a gap of more than %d minutes with no pictures)." % getattr(args, "session_gap", 60))
    if held:
        fl = sorted(held)
        np.savez(res / "holdout_predictions.npz", files=np.array(fl), probs=np.stack([held[f] for f in fl]))     # for review_labels.py
    log("\nFINAL NETWORK: trained on every picture, the last epoch")
    model, hist = train_model(X, y, None, None, args.epochs, args.seed, log=log, flip_axis=flip_axis, aug_kwargs=aug_kw)
    fit, conf, probs = evaluate(model, X, y)
    results["training_fit"] = fit
    plot_curves(hist, res / "curves.png")
    log("  on its own training pictures (not a test): %.1f%%" % (100 * fit))
    meta = {"size": args.size, "gray": bool(args.gray), "classes": CLASS_NAMES, "trained_on": people, "epochs": args.epochs, "seed": args.seed, "flip": args.flip, "shift": aug_kw["shift"], "zoom": zoom, "pictures": int(len(y)), "sessions": n_sess}
    torch.save({"state": model.state_dict(), "cfg": model.cfg, "meta": meta}, out / "finger_cnn.pt")
    npm = NumpyFingerCNN.from_torch(model, meta)
    npm.save(out / "finger_cnn.npz")
    diff = max(float(np.abs(npm.logits(ds["X"][i]) - model(X[i:i + 1]).detach().numpy()[0]).max()) for i in range(min(20, len(y))))
    log("  the NumPy copy (for the UNO Q) matches PyTorch to %.1e on 20 pictures" % diff)
    json.dump({**results, "hist": hist, "parameters": n_parameters(model), "numpy_diff": diff, "seconds": round(time.time() - t0)}, open(res / "results.json", "w"), indent=1)
    write_summary(res / "summary.md", results, model, args, mistakes)
    log("\ndone in %d s: models in %s, results in %s" % (time.time() - t0, out, res))
    return results


def write_summary(path, r, model, args, mistakes):
    L = ["# How well does it count fingers?\n"]
    L.append("%d %s (%s), %d session%s. Pictures are cut from the marked square, resized to %d x %d (%s). The network has %d weights: three convolution stages (16, 32, 64 filters), each with ReLU and max-pooling, joined, then one linear layer to six classes, trained with cross-entropy for %d epochs with augmentation (rotation, shift, zoom, %s mirror, brightness, colour).\n" % (len(r["people"]), "person" if len(r["people"]) == 1 else "people", ", ".join(r["people"]), r["sessions"], "" if r["sessions"] == 1 else "s", args.size, args.size, "grey" if args.gray else "colour", n_parameters(model), args.epochs, args.flip if args.flip != "none" else "no"))
    L.append("## Pictures per person and class\n")
    L.append("| person | " + " | ".join(str(c) for c in range(6)) + " |\n|---|" + "---|" * 6)
    for p, c in r["counts"].items():
        L.append("| %s | " % p + " | ".join(str(v) for v in c) + " |")
    L.append("\n## Results\n")
    L.append("| test | pictures | accuracy | per class (0 to 5) |\n|---|---|---|---|")
    for p, h in r["holdout"].items():
        L.append("| **a new person**: trained without %s, tested on %s | %d | **%.1f%%** | %s |" % (p, p, h["n"], 100 * h["accuracy"], " ".join(recall_row(np.array(h["confusion"])))))
    ns = r.get("new_session")
    if ns:
        L.append("| **a new session** (a different time and light): trained on the earlier pictures, tested on the last session | %d | **%.1f%%** | %s |" % (ns["n"], 100 * ns["accuracy"], " ".join(recall_row(np.array(ns["confusion"])))))
    L.append("| the final network on its own training pictures (**not a test**) | %d | %.1f%% | |" % (sum(sum(c) for c in r["counts"].values()), 100 * r["training_fit"]))
    if ns:
        L.append("\nIn the new-session test, the accuracy for each person: " + ", ".join("%s %.1f%%" % (k, 100 * v) for k, v in ns["per_person"].items() if v is not None) + ".")
    if r["holdout"] or ns:
        L.append("\nThe new-person and new-session rows are the honest ones: in each, the network is trained without any picture of the person or session it is tested on, and nothing (not even which epoch to keep) is chosen using them. The last row only shows how well the network fits the pictures it was trained on.\n")
    else:
        L.append("\n**No tests were run** (--final-only): the only number above is how well the network fits the pictures it was trained on, which says nothing about new pictures. Run without --final-only to measure it on a new person and a new session.\n")
    L.append("## Limits\n")
    L.append("- Only %d %s, one camera, one setup. A new person, a new hand pose or different light can be worse than these numbers." % (len(r["people"]), "person" if len(r["people"]) == 1 else "people"))
    L.append("- The numbers come from a few hundred pictures per person, and each test is a single training run: differences of a few points are noise.")
    L.append("- Figures: `confusion_*.png` (rows: the truth, columns: what the network said), `curves.png`" + (", `%s` (some of the pictures it got wrong in the new-session test)." % mistakes if mistakes else "."))
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/raw")
    ap.add_argument("--out", default="models")
    ap.add_argument("--results", default="results")
    ap.add_argument("--size", type=int, default=64, help="the pictures are shrunk to size x size (must be a multiple of 32)")
    ap.add_argument("--gray", action="store_true", help="use grey pictures instead of colour")
    ap.add_argument("--epochs", type=int, default=150, help="more epochs helped on real pictures: 60 epochs left the network undertrained (see README)")
    ap.add_argument("--final-only", action="store_true", help="skip the new-person and new-session tests and only train the final network (about a third of the time)")
    ap.add_argument("--shift", type=float, default=0.08, help="augmentation: the hand is moved up, down, left or right by up to this fraction of the picture (a larger number makes the network less fussy about where in the square the hand is)")
    ap.add_argument("--zoom", type=float, default=0.1, help="augmentation: the picture is zoomed in or out by up to this fraction")
    ap.add_argument("--session-gap", type=int, default=60, help="a new session starts after this many minutes with no pictures taken")
    ap.add_argument("--flip", choices=("vertical", "horizontal", "none"), default="vertical", help="the mirror used to make extra hands: it must be ACROSS the direction the fingers point. Fingers pointing sideways (arm in from the left): vertical (the default). Fingers pointing up: horizontal")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    if a.size % 32:
        ap.error("--size must be a multiple of 32 (the picture is halved three times and squeezed to a 4 x 4 grid)")
    run(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
