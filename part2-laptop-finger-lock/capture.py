#!/usr/bin/env python3
"""Collect pictures of hands for the finger-counting lock, with the webcam on its stand and the red square on the desk.

    python capture.py --person A                     live window; press 0-5 to save a picture of that many fingers
    python capture.py --person B --camera 1          a different webcam
    python capture.py --person A --simulate          a made-up camera, to try the tool without a webcam

Keys: 0-5 save a picture (0 = empty square or closed fist) | b burst mode (a digit saves 20 pictures while you move the hand a little) |
r find the taped square (colour with --tape) | drag with the mouse to choose the square yourself | + - bigger or smaller | w a s d move it | e record the EMPTY square | u undo | q quit.
Use the SAME camera, the same stand and the same light as you will use for the lock, and take pictures from several different people (a letter each: A, B, C).
"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from fingerlock import capture_lib as cl
from fingerlock.session import CaptureSession
from fingerlock.synth_hand import SyntheticCamera

WINDOW, VIEW = "capture", "what the network sees"


def draw(frame, s, drag=None):
    vis = frame.copy()
    if s.roi is not None:
        cv2.rectangle(vis, (s.roi.x, s.roi.y), (s.roi.x + s.roi.side, s.roi.y + s.roi.side), (0, 220, 0), 2)
    if drag:
        cv2.rectangle(vis, drag[0], drag[1], (0, 200, 255), 1)
    mine, total = s.counts()
    lines = ["person %s    burst mode %s    %s" % (s.person, "ON" if s.burst_mode else "off", "square set" if s.roi else "NO SQUARE: press r or drag a box"),
             "this person:  " + "  ".join("%d:%d" % (c, mine[c]) for c in cl.CLASSES), "everyone:     " + "  ".join("%d:%d" % (c, total[c]) for c in cl.CLASSES)]
    msg = s.message
    while msg:
        lines.append(msg[:95]); msg = msg[95:]
    cv2.rectangle(vis, (0, 0), (vis.shape[1], 18 * len(lines) + 8), (0, 0, 0), -1)
    for i, t in enumerate(lines):
        cv2.putText(vis, t, (8, 18 * (i + 1)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255) if "WARNING" in t else (255, 255, 255), 1, cv2.LINE_AA)
    return vis


def headless_demo(session, cam):
    """No window: find the square, then save 3 pictures of every class from the (simulated) camera. Used by the tests."""
    ok, frame = cam.read()
    session.on_key("r", frame)
    session.on_key("e", frame)
    for c in cl.CLASSES:
        if hasattr(cam, "set_label"):
            cam.set_label(c)
        for _ in range(3):
            ok, frame = cam.read()
            session.on_key(str(c), frame)
    return session.counts()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--person", required=True, help="a letter (A, B, C ...): not a name")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--roi-file", default=None, help="where the square is remembered (default: next to the pictures)")
    ap.add_argument("--tape", default="red", choices=cl.TAPE, help="the colour of the tape square on the desk, for the 'r' key (any colour works for dragging a box)")
    ap.add_argument("--simulate", action="store_true", help="use a made-up camera")
    ap.add_argument("--headless-demo", action="store_true", help="no window: save 3 pictures of every class from the simulated camera, then stop")
    a = ap.parse_args(argv)
    cl.check_person(a.person)
    if a.simulate or a.headless_demo:
        cam, info = SyntheticCamera(a.width, a.height, tape=a.tape), {"width": a.width, "height": a.height, "autofocus": "n/a", "auto_exposure": "n/a"}
    else:
        cam, info = cl.open_camera(a.camera, a.width, a.height)
    print("camera: %s x %s, autofocus %s, auto exposure %s (what the camera accepted)" % (info["width"], info["height"], info["autofocus"], info["auto_exposure"]))
    out = Path(a.out)
    session = CaptureSession(out, a.person, roi_path=a.roi_file or (out / "roi.json"), frame_size=(info["width"], info["height"]), tape=a.tape)
    if a.headless_demo:
        print("saved:", headless_demo(session, cam))
        return 0
    drag = {"start": None, "now": None}

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            drag["start"], drag["now"] = (x, y), (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and drag["start"]:
            drag["now"] = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and drag["start"]:
            (x0, y0), (x1, y1) = drag["start"], (x, y)
            side = max(abs(x1 - x0), abs(y1 - y0))
            if side >= 24:
                session.set_roi(cl.Roi(min(x0, x1) if x1 >= x0 else x0 - side, min(y0, y1) if y1 >= y0 else y0 - side, side))
            drag["start"] = drag["now"] = None

    cv2.namedWindow(WINDOW)
    cv2.setMouseCallback(WINDOW, on_mouse)
    while not session.quit:
        ok, frame = cam.read()
        if not ok:
            print("the camera stopped giving pictures"); break
        session.on_frame(frame)
        cv2.imshow(WINDOW, draw(frame, session, (drag["start"], drag["now"]) if drag["start"] else None))
        if session.roi is not None:
            view = cl.crop(frame, session.roi, session.save_size)
            small = cv2.resize(cv2.resize(view, (64, 64), interpolation=cv2.INTER_AREA), (session.save_size, session.save_size), interpolation=cv2.INTER_NEAREST)
            cv2.imshow(VIEW, np.hstack([view, small]))
        k = cv2.waitKey(1) & 0xFF
        if k != 255:
            session.on_key("\x1b" if k == 27 else chr(k), frame)
    cam.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
