"""Motor test, the Python side: see motortest.py for what it does and the README for how to use it.
The web page (port 7000) sends the commands; the sketch tells us when the motor starts and stops with Bridge.notify."""
import time
from pathlib import Path

from arduino.app_utils import *
from arduino.app_bricks.web_ui import WebUI

from motortest import MotorTest

HERE = Path(__file__).resolve().parent


class BoardIO:
    @staticmethod
    def call(name, a=0, b=0):
        return Bridge.call(name, a, b, timeout=2)           # the return value is not used: what we need comes by notification


test = MotorTest(BoardIO(), HERE / "motor_settings.json", HERE / "moves.csv")
ui = WebUI()
Bridge.provide("motor", test.on_motor)


def notice(level, text):
    ui.send_message("notice", {"level": level, "text": text})


def on_cmd(sid, data):
    try:
        data = data or {}
        action = data.get("action")
        if action in ("next", "move"):
            row = test.move("next" if action == "next" else data.get("which"), data.get("settings"))
            notice("info", "%s: motor %+d for %d ms at speed %d. Stop it with Esc or the Space bar." % ({"open": "Opening", "close": "Closing"}[row["action"]], row["dir"], row["ms"], row["pwm"]))
        elif action == "stop":
            test.stop()
            notice("ok", "Stopped.")
        elif action == "set_door":
            test.set_door(data.get("door"))
        elif action == "rate":
            test.rate(data.get("id"), data.get("outcome"))
        elif action == "clear":
            test.clear()
            notice("info", "The table is cleared (moves.csv still has every move).")
        elif action != "refresh":
            notice("warn", "Unknown command.")
            return
        ui.send_message("state", test.snapshot())
    except ValueError as e:
        notice("warn", str(e))
    except Exception as e:                       # never let a bad command kill the app
        notice("warn", "Something went wrong: " + str(e)[:120])


ui.on_message("cmd", on_cmd)
ui.on_connect(lambda sid: ui.send_message("state", test.snapshot()))


def loop():
    time.sleep(0.1)
    n = test.tick()
    if n:
        notice(n["level"], n["text"])
    ui.send_message("state", test.snapshot())


App.run(user_loop=loop)
