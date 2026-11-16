#!/usr/bin/env python3
"""Count fingers live with the trained network, on the webcam. Shows what the network says and how sure it is.

    python predict_live.py --model models/finger_cnn.npz --data data/raw --tape blue --camera 3

The square is read from  <data>/roi.json  (where capture.py remembered it), so it is exactly the square the network was trained on: do not move the camera or the stand.
Keys: q quit | s save the current picture of the square into  live_saved/  (to keep a case the network got wrong).
"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from fingerlock import capture_lib as cl
from fingerlock.predict import Predictor, Smoother
from fingerlock.synth_hand import SyntheticCamera


def draw(frame, roi, probs, stable, ms):
    vis = frame.copy()
    cv2.rectangle(vis, (roi.x, roi.y), (roi.x + roi.side, roi.y + roi.side), (0, 220, 0) if stable is not None else (0, 160, 255), 2)
    cv2.rectangle(vis, (0, 0), (vis.shape[1], 60), (0, 0, 0), -1)
    cv2.putText(vis, "sure: %s" % (stable if stable is not None else "?"), (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 0) if stable is not None else (0, 160, 255), 3, cv2.LINE_AA)
    for c in range(6):                                                                  # a bar per class
        x0 = vis.shape[1] - 6 * 38 - 10 + c * 38
        cv2.rectangle(vis, (x0, 52), (x0 + 28, 52 - int(44 * probs[c])), (255, 255, 255), -1)
        cv2.putText(vis, str(c), (x0 + 8, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(vis, "%.0f ms per picture" % ms, (260, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    return vis


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="models/finger_cnn.npz")
    ap.add_argument("--data", default="data/raw", help="the folder with roi.json")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument("--headless-demo", type=int, default=0, metavar="FRAMES", help="no window: run FRAMES frames of the made-up camera and print what it says")
    a = ap.parse_args(argv)
    sim = a.simulate or a.headless_demo
    if sim:
        cam, info = SyntheticCamera(a.width, a.height), {"width": a.width, "height": a.height}
    else:
        cam, info = cl.open_camera(a.camera, a.width, a.height)
    roi = cl.load_roi(Path(a.data) / "roi.json", (info["width"], info["height"]))
    if roi is None and sim:
        ok, f = cam.read(); roi = cl.find_square(f, "red")
    if roi is None:
        raise SystemExit("no square found for a %dx%d camera in %s/roi.json: run capture.py first (the square must be set at the same camera size)" % (info["width"], info["height"], a.data))
    pred, sm = Predictor(a.model, roi), Smoother()
    saved = Path("live_saved")
    last, n = None, 0
    while True:
        ok, frame = cam.read()
        if not ok:
            break
        t = time.perf_counter()
        cls, probs = pred.predict(frame)
        ms = 1000 * (time.perf_counter() - t)
        sm.add(probs)
        st = sm.stable()
        if st != last and st is not None:
            print("stable: %d fingers (probability %.0f%%)" % (st, 100 * sm.mean()[st]), flush=True)
        last = st
        n += 1
        if a.headless_demo:
            if n >= a.headless_demo:
                break
            continue
        cv2.imshow("finger count", draw(frame, roi, sm.mean(), st, ms))
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if k == ord("s"):
            saved.mkdir(exist_ok=True)
            cv2.imwrite(str(saved / ("%d_%d.png" % (int(time.time()), cls))), cl.crop(frame, roi, cl.SAVE_SIZE))
    cam.release()
    if not a.headless_demo:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
