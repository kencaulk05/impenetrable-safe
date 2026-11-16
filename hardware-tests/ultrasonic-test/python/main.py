"""Ultrasonic sensor test, the Python side: see ultrasonic.py for what it does and the README for how to use it.
The sketch streams the distance to us with Bridge.notify; the web page (port 7000) shows it and starts captures with the SPACE bar."""
import time
from pathlib import Path

from arduino.app_utils import *
from arduino.app_bricks.web_ui import WebUI

from ultrasonic import SensorMonitor, bar_columns

HERE = Path(__file__).resolve().parent
mon = SensorMonitor(log_path=HERE / "captures.csv")
ui = WebUI()
led = {"sent": None, "tick": 0}

Bridge.provide("distance", mon.on_distance)


def notice(level, text):
    ui.send_message("notice", {"level": level, "text": text})


def on_cmd(sid, data):
    try:
        action = (data or {}).get("action")
        if action == "capture":
            secs = mon.start_capture(data.get("label"), data.get("supply"), data.get("seconds"), data.get("kind"))
            notice("info", "Capturing for %d seconds: hold the sensor and the door still." % secs)
        elif action == "clear":
            mon.clear()
            notice("info", "The table is cleared (captures.csv still has every capture).")
        elif action != "refresh":
            notice("warn", "Unknown command.")
            return
        ui.send_message("state", mon.snapshot())
    except ValueError as e:
        notice("warn", str(e))
    except Exception as e:                       # never let a bad command kill the app
        notice("warn", "Something went wrong: " + str(e)[:120])


ui.on_message("cmd", on_cmd)
ui.on_connect(lambda sid: ui.send_message("state", mon.snapshot()))


def loop():
    time.sleep(0.1)
    row = mon.tick()
    if row:
        notice("ok", "Capture finished. " + row["verdict"])
    snap = mon.snapshot()
    ui.send_message("state", snap)
    want = bar_columns(snap["mm"])
    led["tick"] += 1
    if want != led["sent"]:
        try:
            Bridge.call("led", 5, want, timeout=2)
            led["sent"] = want
        except Exception as e:
            if led["tick"] % 100 == 0:
                print("(LED matrix not answering: " + str(e)[:60] + ")", flush=True)


App.run(user_loop=loop)
