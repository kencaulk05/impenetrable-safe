"""Finger Count on the Board, the Python side: see board_vision.py for what it does and the README for how to use it.
The camera is read in the background, the network (plain NumPy) looks at the newest picture, and the web page (port 7000) shows what it sees."""
import time
from pathlib import Path

from arduino.app_utils import *
from arduino.app_bricks.web_ui import WebUI

import board_vision as bv

HERE = Path(__file__).resolve().parent
FRAME_W, FRAME_H = 640, 480        # the camera size the network was trained at (if the board turns out too slow, 320 x 240 can be tried: the square is scaled to fit)

ui = WebUI()
board = bv.FingerBoard(bv.Pipeline(HERE / "model" / "finger_cnn.npz"), HERE / "roi.json", HERE / "board_speed.csv", camera_path=HERE / "camera.json")
print("Finger count on the board: network loaded (%s inputs, %s). %s" % (board.pipeline.size, "grey" if board.pipeline.gray else "colour", bv.machine_info()), flush=True)


def open_cam():
    return bv.open_camera(FRAME_W, FRAME_H, fourcc=board.camera_settings["fourcc"] or None, fps=30)


def notice(level, text):
    ui.send_message("notice", {"level": level, "text": text})


def send_view():
    ui.send_message("view", board.view())


def send_bench():
    ui.send_message("bench", {"rows": board.bench_rows, "csv": "board_speed.csv"})


def on_cmd(sid, data):
    try:
        data = data or {}
        action = data.get("action")
        if action == "nudge":
            board.nudge(data.get("dx", 0), data.get("dy", 0), data.get("ds", 0))
            send_view()
        elif action == "find_tape":
            r = board.find_tape(data.get("color", "blue"))
            notice("ok", "Found a %s square: x %d, y %d, side %d. Check it on the picture, then press Save." % (data.get("color", "blue"), r.x, r.y, r.side))
            send_view()
        elif action == "save_roi":
            board.save_roi()
            notice("ok", "The square is saved (roi.json) and will be used the next time the app starts.")
            send_view()
        elif action == "reset_roi":
            board.reset_roi()
            notice("info", "Back to the square the network was trained on.")
            send_view()
        elif action == "pause":
            board.set_paused(data.get("paused", True))
            notice("info", "The network is paused: the camera pictures per second is now the camera's own speed." if board.paused else "The network is running again.")
            send_view()
        elif action == "camera_mode":
            board.set_camera_mode(data.get("fourcc", ""))
            notice("info", "Reopening the camera with the format %s: the pictures per second show how fast it really goes." % (board.camera_settings["fourcc"] or "the camera chooses"))
            send_view()
        elif action == "benchmark":
            notice("info", "Measuring: the live view pauses for a few seconds.")
            row = board.benchmark(100)
            send_bench()
            notice("ok", "On this board one step takes %.1f ms (cutting out the square %.1f ms + the network %.1f ms): about %.0f steps a second. (Measured on the standard made-up picture, so it can be compared with your laptop.)" % (row["total_median_ms"], row["prep_median_ms"], row["infer_median_ms"], row["fps_estimate"] or 0))
        elif action == "refresh":
            send_view()
            send_bench()
        else:
            notice("warn", "Unknown command.")
    except ValueError as e:
        notice("warn", str(e))
    except Exception as e:                       # never let a bad command kill the app
        notice("warn", "Something went wrong: " + str(e)[:120])


ui.on_message("cmd", on_cmd)
ui.on_connect(lambda sid: (send_view(), send_bench()))


def loop():
    board.maintain(open_cam)
    worked = board.step()
    if board.view_due():
        send_view()
    if not worked:
        time.sleep(0.01)


App.run(user_loop=loop)
