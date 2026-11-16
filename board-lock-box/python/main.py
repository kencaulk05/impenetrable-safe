"""Finger lock box, the Python side: see lockbox.py for what it does and the README for how to use it.
The camera is read in the background, the network (plain NumPy) looks at the newest picture, the lock rules read the digits, the door opens and closes with the motor and is checked by the
distance sensor, the LED matrix shows what is going on, and the web page (port 7000) shows everything and has the button (the Space bar)."""
import time
from pathlib import Path

from arduino.app_utils import *
from arduino.app_bricks.web_ui import WebUI

import board_vision as bv
from door import Door
from lockbox import LockBox

HERE = Path(__file__).resolve().parent
FRAME_W, FRAME_H = 640, 480        # the camera size the network was trained at


class BoardIO:
    @staticmethod
    def call(name, a=0, b=0):
        return Bridge.call(name, a, b, timeout=2)           # the return value is not used: what we need comes by notification


io = BoardIO()
ui = WebUI()
board = bv.FingerBoard(bv.Pipeline(HERE / "model" / "finger_cnn.npz"), HERE / "roi.json", None, camera_path=HERE / "camera.json")
door = Door(io, HERE / "door_config.json", HERE / "door_log.csv")
box = LockBox(door, io, HERE / "lock_config.json", HERE / "lockbox_log.csv")
Bridge.provide("distance", door.on_distance)
Bridge.provide("motor", door.on_motor)
print("Finger lock box: network loaded; code %s. %s" % ("set" if box.ctl else "NOT set yet (use the Code section of the page)", bv.machine_info()), flush=True)
sent = {"lock": 0.0, "errors": 0}


def open_cam():
    return bv.open_camera(FRAME_W, FRAME_H, fourcc=board.camera_settings["fourcc"] or None, fps=30)


def notice(level, text):
    ui.send_message("notice", {"level": level, "text": text})


def send_view():
    ui.send_message("view", board.view())


def send_lock():
    ui.send_message("lock", box.snapshot())
    sent["lock"] = box.now()


def on_cmd(sid, data):
    try:
        data = data or {}
        action = data.get("action")
        if action == "button":
            box.press_button()
        elif action == "stop":
            box.door_command("stop")
            notice("ok", "Stopped.")
        elif action in ("door_open", "door_close"):
            box.door_command("open" if action == "door_open" else "close")
        elif action == "calibrate":
            box.door_command("calibrate")
            notice("ok", "The closed distance was taken from the sensor.")
        elif action == "push_back":
            box.set_push_back(data.get("on"))
        elif action == "set_code":
            box.set_code(data.get("code"), data.get("confirm"), data.get("challenge", 1), data.get("pool", "135"))
            notice("ok", "The code is saved (a salted hash: the digits are not stored).")
        elif action == "clear_log":
            box.clear_log()
        elif action == "reset_stats":
            box.reset_stats()
            notice("info", "The measurements are reset: the tally starts from zero.")
        elif action == "log_full":
            ui.send_message("fulllog", {"rows": box.read_log_file()})
            return
        elif action == "nudge":
            board.nudge(data.get("dx", 0), data.get("dy", 0), data.get("ds", 0))
            send_view()
        elif action == "find_tape":
            r = board.find_tape(data.get("color", "blue"))
            notice("ok", "Found a %s square: x %d, y %d, side %d. Check it on the picture, then press Save." % (data.get("color", "blue"), r.x, r.y, r.side))
            send_view()
        elif action == "save_roi":
            board.save_roi()
            notice("ok", "The square is saved and will be used the next time the app starts.")
            send_view()
        elif action == "reset_roi":
            board.reset_roi()
            notice("info", "Back to the square the network was trained on.")
            send_view()
        elif action == "camera_mode":
            board.set_camera_mode(data.get("fourcc", ""))
            notice("info", "Reopening the camera with the format %s." % (board.camera_settings["fourcc"] or "the camera chooses"))
            send_view()
        elif action == "refresh":
            send_view()
        else:
            notice("warn", "Unknown command.")
            return
        for level, text in box.drain_notices():
            notice(level, text)
        send_lock()
    except ValueError as e:
        notice("warn", str(e))
    except Exception as e:                       # never let a bad command kill the app
        notice("warn", "Something went wrong: " + str(e)[:120])


ui.on_message("cmd", on_cmd)
ui.on_connect(lambda sid: (send_view(), send_lock()))


def loop():
    worked = False
    try:
        board.maintain(open_cam)
        worked = board.step()
        if worked and board.last is not None and board.last["probs"] is not None:
            box.on_frame(board.last["probs"])
        box.tick()
        for level, text in box.drain_notices():
            notice(level, text)
        box.sync_picture()
        if box.now() - sent["lock"] >= 0.2:
            send_lock()
        if board.view_due():
            send_view()
    except Exception as e:                       # one bad pass must not stop the lock
        sent["errors"] += 1
        if sent["errors"] <= 5 or sent["errors"] % 100 == 0:
            print("Finger lock box: a pass of the loop failed (%d so far): %s" % (sent["errors"], str(e)[:150]), flush=True)
    if not worked:
        time.sleep(0.01)


App.run(user_loop=loop)
