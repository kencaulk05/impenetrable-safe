#!/usr/bin/env python3
"""The lock on the computer: webcam in, network, lock rules, and the LED matrix drawn on the screen. (The box and motors come later, on the UNO Q.)

    python set_code.py --challenge 1 --challenge-pool 135                  once: choose the code (and the live challenge)
    python lock_demo.py --model models/finger_cnn.npz --data data/raw --camera 3

SPACE is the button. Press it, then show your three different digits one after another (go back to a fist or an empty square between digits). q quits.
The dashed box in the picture is where hands were during training: keep your hand in it, with the fingertips inside the square.
    python lock_demo.py --headless-demo 153        no camera: a scripted run (the owner, then an intruder) using the code 153, prints what happens
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from fingerlock import capture_lib as cl
from fingerlock import matrix as M
from fingerlock.lock import IDLE, LOCKOUT, UNLOCKED, LockController, Policy, Verifier, check_code, describe
from fingerlock.predict import Predictor, Smoother

COL = {"idle": (170, 170, 170), "challenge": (0, 190, 255), "entering": (0, 255, 255), "unlocked": (0, 220, 0), "lockout": (60, 60, 255)}
TEXT = {"idle": "LOCKED - press SPACE", "challenge": "CHALLENGE", "entering": "SHOW YOUR CODE", "unlocked": "UNLOCKED", "lockout": "LOCKED OUT"}
PANEL = 380
# where the hand was, as a share of the square, in the pictures the network learned from (80% of the hands: the middle of the hand 40 to 60% of the way down, the fingertips 73 to 95% of the way across)
GUIDE = (0.30, 0.20, 0.96, 0.80)


def ascii_frame(f):
    return "\n".join("    " + "".join("#" if v else "." for v in row) for row in f)


def headless_demo(code, out=print):
    """A scripted run through the whole lock with made-up network answers: the owner gets in, an intruder is locked out, and the lockout grows."""
    P = lambda d: np.where(np.arange(6) == d, 0.9, 0.02)
    ctl = LockController(Verifier.from_code(code, iterations=1000), Policy(), rng=random.Random(0))
    t = [0.0]

    def run(label, events):
        for e in events:
            out("  t=%5.1fs  %-10s %s" % (t[0], label, e))

    def show(digit_list):
        for d in digit_list:
            for _ in range(10): t[0] += 1 / 15; run("", ctl.update(t[0], P(d)))
            for _ in range(8): t[0] += 1 / 15; run("", ctl.update(t[0], P(0)))
    out("THE OWNER, with the right code %s:" % code); run("button", ctl.press_button(t[0])); show([int(c) for c in code]); out("  state: %s" % ctl.state)
    t[0] += 11; run("time", ctl.tick(t[0])); out("  (10 seconds later) state: %s" % ctl.state)
    for k in range(3):
        out("\nAN INTRUDER, wrong code, try %d:" % (k + 1)); t[0] += 1; run("button", ctl.press_button(t[0])); show([2, 4, 1] if code != "241" else [1, 3, 5])
    out("  state: %s; the button now: %s" % (ctl.state, ctl.press_button(t[0] + 1)))
    return ctl.state


def compose(frame, roi, d, pic, probs, reading, log, state, guide=True):
    """The whole window: the camera picture with the square and the guide, and a panel on the right with the status, the LED matrix, the network's answer and a log in words."""
    h, w = frame.shape[:2]
    vis = np.zeros((h, w + PANEL, 3), np.uint8)
    vis[:, :w] = frame
    cv2.rectangle(vis, (roi.x, roi.y), (roi.x + roi.side, roi.y + roi.side), COL[state], 3)
    if guide:
        x0, y0, x1, y1 = [int(v) for v in (roi.x + GUIDE[0] * roi.side, roi.y + GUIDE[1] * roi.side, roi.x + GUIDE[2] * roi.side, roi.y + GUIDE[3] * roi.side)]
        for xs in range(x0, x1, 14):                                       # a dashed box: where hands usually were when the network learned
            cv2.line(vis, (xs, y0), (min(xs + 7, x1), y0), (255, 255, 255), 1); cv2.line(vis, (xs, y1), (min(xs + 7, x1), y1), (255, 255, 255), 1)
        for ys in range(y0, y1, 14):
            cv2.line(vis, (x0, ys), (x0, min(ys + 7, y1)), (255, 255, 255), 1); cv2.line(vis, (x1, ys), (x1, min(ys + 7, y1)), (255, 255, 255), 1)
        cv2.putText(vis, "hand here, fingertips inside", (x0 + 4, y0 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    px = w + 14
    cv2.putText(vis, "FINGER LOCK", (px, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(vis, TEXT[state], (px, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.9, COL[state], 2, cv2.LINE_AA)
    if state == "entering":
        sub = "digit %d of %d" % (min(d["entered"] + 1, d["of"]), d["of"])
    elif state == "challenge":
        sub = "show %d" % d["challenge"][d["challenge_done"]]
    elif state == "lockout":
        sub = "try again in %d s" % round(d["lockout_left"])
    elif state == "unlocked":
        sub = "closes in %d s" % round(d["unlocked_left"])
    else:
        sub = "tries left: %d" % (3 - d["failures"]) if d["failures"] else ""
    cv2.putText(vis, sub, (px, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (230, 230, 230), 1, cv2.LINE_AA)
    led = M.render(pic, 20)
    vis[104:104 + led.shape[0], px:px + led.shape[1]] = led
    cv2.putText(vis, "network sees:", (px, 288), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(vis, str(reading) if reading is not None else "-", (px + 130, 292), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0) if reading is not None else (120, 120, 120), 2, cv2.LINE_AA)
    for c in range(6):
        x0 = px + c * 40
        cv2.rectangle(vis, (x0, 346), (x0 + 28, 346 - int(48 * probs[c])), (255, 255, 255), -1)
        cv2.putText(vis, str(c), (x0 + 9, 364), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    for i, line in enumerate(log[-4:]):
        cv2.putText(vis, line[:44], (px, 392 + i * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (210, 210, 210), 1, cv2.LINE_AA)
    return vis


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="models/finger_cnn.npz")
    ap.add_argument("--data", default="data/raw", help="the folder with roi.json")
    ap.add_argument("--config", default="lock_config.json")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--challenge", type=int, default=None, help="override the live challenge set in the config (0 = off)")
    ap.add_argument("--challenge-pool", default=None, help="override the digits the challenge may ask for, for example 135")
    ap.add_argument("--no-guide", action="store_true", help="do not draw the dashed box where hands usually were")
    ap.add_argument("--headless-demo", metavar="CODE", help="no camera: a scripted run with this code")
    a = ap.parse_args(argv)
    if a.headless_demo:
        headless_demo("".join(map(str, check_code(a.headless_demo)))); return 0
    if not Path(a.config).exists():
        raise SystemExit("no %s yet: run  python set_code.py  first" % a.config)
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    pol = Policy.from_dict(cfg.get("policy"))
    if a.challenge is not None:
        pol.challenge_digits = a.challenge
    if a.challenge_pool is not None:
        pol = Policy.from_dict({**pol.to_dict(), "challenge_pool": [int(c) for c in a.challenge_pool]})
    ctl = LockController(Verifier.from_dict(cfg["verifier"]), pol)
    cam, info = cl.open_camera(a.camera, a.width, a.height)
    roi = cl.load_roi(Path(a.data) / "roi.json", (info["width"], info["height"]))
    if roi is None:
        raise SystemExit("no square for a %dx%d camera in %s/roi.json: run capture.py first" % (info["width"], info["height"], a.data))
    pred, pic, log, reader = Predictor(a.model, roi), M.LOCKED, ["ready: press SPACE (the button)"], Smoother()
    while True:
        ok, frame = cam.read()
        if not ok:
            break
        now = time.monotonic()
        cls, probs = pred.predict(frame)
        reader.add(probs)
        ev = ctl.update(now, probs if ctl.state not in (IDLE, UNLOCKED, LOCKOUT) else None)
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if k == 32:
            ev += ctl.press_button(now)
        d = ctl.display(now)
        for e in ev:
            print(e, flush=True); log.append(describe(e, d["of"]))
        new = M.for_events(ev, d)
        pic = new if new is not None else pic
        cv2.imshow("lock", compose(frame, roi, d, pic, reader.mean(), reader.stable(), log, ctl.state, guide=not a.no_guide))
    cam.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
