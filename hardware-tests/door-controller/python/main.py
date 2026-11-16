"""Door controller, the Python side: see door.py for what it does and the README for how to use it.
The sketch streams the distance and the motor's start and stop with Bridge.notify; the web page (port 7000) shows the door and sends the commands."""
import time
from pathlib import Path

from arduino.app_utils import *
from arduino.app_bricks.web_ui import WebUI

from door import Door

HERE = Path(__file__).resolve().parent


class BoardIO:
    @staticmethod
    def call(name, a=0, b=0):
        return Bridge.call(name, a, b, timeout=2)           # the return value is not used: what we need comes by notification


door = Door(BoardIO(), HERE / "door_config.json", HERE / "door_log.csv")
ui = WebUI()
led = {"sent": None, "tick": 0}
Bridge.provide("distance", door.on_distance)
Bridge.provide("motor", door.on_motor)

LEVEL = {"tamper": "warn", "fault": "warn", "sensor_lost": "warn", "retry": "warn", "closed": "ok", "opened": "ok", "locked": "ok", "tamper_over": "ok",
         "calibrated": "ok", "stopped": "info", "move": "info", "push_back": "warn", "sensor_back": "ok"}        # ("state" changes go to the log on the page, not to the message bar)


def notice(level, text):
    ui.send_message("notice", {"level": level, "text": text})


def announce(events):
    for e in events or []:
        if e["kind"] in LEVEL:
            notice(LEVEL[e["kind"]], e["text"])


def icon(snap):
    """Which picture the LED matrix shows when the motor is not moving: 4 X (fault), 3 ! (tamper), 1 closed padlock, 2 open padlock, 0 dark."""
    if snap["fault"] or snap["sensor"] == "lost":
        return 4
    if snap["tamper"]:
        return 3
    return {"locked": 1, "unlocked": 2}.get(snap["mode"], 0)


def on_cmd(sid, data):
    try:
        data = data or {}
        action, ev = data.get("action"), []
        if action == "toggle":
            ev = door.toggle()
        elif action == "open":
            ev = door.request_open()
        elif action == "close":
            ev = door.request_close()
        elif action == "stop":
            ev = door.stop()
            notice("ok", "Stopped.")
        elif action == "calibrate":
            ev = door.calibrate()
        elif action == "settings":
            door.update_settings(data.get("settings"))
            notice("ok", "Settings saved.")
        elif action == "clear_events":
            door.clear_events()
        elif action != "refresh":
            notice("warn", "Unknown command.")
            return
        announce(ev)
        ui.send_message("state", door.snapshot())
    except ValueError as e:
        notice("warn", str(e))
    except Exception as e:                       # never let a bad command kill the app
        notice("warn", "Something went wrong: " + str(e)[:120])


ui.on_message("cmd", on_cmd)
ui.on_connect(lambda sid: ui.send_message("state", door.snapshot()))


def loop():
    time.sleep(0.1)
    announce(door.tick())
    snap = door.snapshot()
    ui.send_message("state", snap)
    want = icon(snap)
    led["tick"] += 1
    if want != led["sent"]:
        try:
            Bridge.call("led", want, 0, timeout=2)
            led["sent"] = want
        except Exception as e:
            if led["tick"] % 100 == 0:
                print("(LED matrix not answering: " + str(e)[:60] + ")", flush=True)


App.run(user_loop=loop)
