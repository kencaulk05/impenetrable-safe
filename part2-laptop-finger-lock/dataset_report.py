#!/usr/bin/env python3
"""Check the pictures you have collected, before training.

    python dataset_report.py data/raw              counts per class and per person, how sharp and bright the pictures are, duplicates, and what to collect next
    python dataset_report.py data/raw --target 300
"""
import argparse
import hashlib
import random
import sys
from pathlib import Path

import cv2

from fingerlock import capture_lib as cl


def report(root, target=200, sample=60):
    root = Path(root)
    files = {c: sorted((root / str(c)).glob("*.png")) if (root / str(c)).exists() else [] for c in cl.CLASSES}
    people = sorted({f.name.split("__")[0] for fs in files.values() for f in fs})
    counts = {c: len(fs) for c, fs in files.items()}
    per = {p: {c: sum(1 for f in files[c] if f.name.startswith(p + "__")) for c in cl.CLASSES} for p in people}
    rng = random.Random(0)
    qual, dup, seen = {}, 0, set()
    for c, fs in files.items():
        for f in fs:
            h = hashlib.md5(f.read_bytes()).hexdigest()
            dup += h in seen
            seen.add(h)
        picks = rng.sample(fs, min(sample, len(fs)))
        qs = [cl.quality(cv2.imread(str(f))) for f in picks if cv2.imread(str(f)) is not None]
        qual[c] = ({k: sum(q[k] for q in qs) / len(qs) for k in ("brightness", "sharpness", "contrast")}, {"dark": sum(q["brightness"] < 45 for q in qs), "bright": sum(q["brightness"] > 215 for q in qs), "blurry": sum(q["sharpness"] < 8 for q in qs)}) if qs else (None, None)
    total = sum(counts.values())
    todo = []
    for c in cl.CLASSES:
        if counts[c] < target:
            todo.append("class %d: %d more pictures (has %d, target %d)" % (c, target - counts[c], counts[c], target))
    ratio = (max(counts.values()) / max(1, min(counts.values()))) if total else 0
    notes = []
    if total == 0:
        notes.append("no pictures found in %s" % root)
    if len(people) < 3 and total:
        notes.append("only %d %s so far: a network trained on one or two people's hands will probably fail on other people's. Aim for at least 3, and more is better." % (len(people), "person" if len(people) == 1 else "people"))
    if ratio > 2:
        notes.append("the classes are unbalanced (the biggest has %.1f times the smallest): collect more of the small ones." % ratio)
    if dup:
        notes.append("%d exact duplicate files (the same picture saved twice)." % dup)
    for c, (q, f) in qual.items():
        if q and (f["dark"] or f["bright"] or f["blurry"]):
            notes.append("class %d: in a sample, %d dark, %d too bright, %d blurry" % (c, f["dark"], f["bright"], f["blurry"]))
    return {"counts": counts, "people": people, "per_person": per, "total": total, "todo": todo, "notes": notes, "duplicates": dup, "quality": {c: q for c, (q, f) in qual.items()}}


def render(r, target):
    L = ["%d pictures, %d %s (%s)" % (r["total"], len(r["people"]), "person" if len(r["people"]) == 1 else "people", ", ".join(r["people"]) or "none")]
    L.append("%-8s " % "class" + " ".join("%6d" % c for c in cl.CLASSES) + "   total")
    for p in r["people"]:
        L.append("%-8s " % ("person " + p) + " ".join("%6d" % r["per_person"][p][c] for c in cl.CLASSES) + "   %5d" % sum(r["per_person"][p].values()))
    L.append("%-8s " % "all" + " ".join("%6d" % r["counts"][c] for c in cl.CLASSES) + "   %5d" % r["total"])
    L.append("")
    L.append("mean brightness / sharpness per class: " + "  ".join("%d: %.0f / %.0f" % (c, q["brightness"], q["sharpness"]) for c, q in r["quality"].items() if q))
    L.append("")
    L += (["STILL TO COLLECT (target %d per class):" % target] + ["  " + t for t in r["todo"]]) if r["todo"] else ["every class has at least %d pictures" % target]
    L += [""] + ["NOTE: " + n for n in r["notes"]] if r["notes"] else []
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--target", type=int, default=200)
    a = ap.parse_args()
    print(render(report(a.root, a.target), a.target))
