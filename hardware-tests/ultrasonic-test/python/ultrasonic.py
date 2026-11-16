"""The logic of the ultrasonic sensor test, with no board library in it, so it can be tested.

The sketch sends a distance reading every 60 ms. This module keeps the recent readings (for the live number and the chart) and, when asked, CAPTURES some seconds of them
and works out how good the sensor is: how many readings were usable, and how steady they were. Every capture is added to a table on the page and to captures.csv.
"""
import csv
import datetime
import statistics
import time
from collections import deque
from pathlib import Path

MIN_MM, MAX_MM = 20, 4000                  # the sensor reads 2 cm to 4 m
SUPPLIES = ("3V3", "5V")
KINDS = ("closed", "ajar", "open", "other")      # what a capture is about: the door shut, pushed open a little, fully open (out of the sensor's view), anything else
FIELDS = ["time", "label", "kind", "supply", "seconds", "n", "valid", "valid_pct", "mean_mm", "median_mm", "min_mm", "max_mm", "std_mm", "verdict"]


def usable(mm):
    """The reading as a whole number of millimetres if it is a real one, else None (-1 means no echo; very near or very far is not trusted)."""
    if mm is None:
        return None
    try:
        v = int(mm)
    except (TypeError, ValueError):
        return None
    return v if MIN_MM <= v <= MAX_MM else None


def bar_columns(mm, full_mm=300.0):
    """How many of the matrix's 13 columns a distance fills, so the sensor can be aimed by looking at the LEDs."""
    if mm is None or mm <= 0:
        return 0
    return max(0, min(13, int(round(13 * mm / full_mm))))


def verdict(n, valid_pct, std, kind="other", median=None):
    if kind == "open":                      # with the door out of the way the sensor may see NOTHING: that is the right answer here, not a fault
        if n == 0:
            return "NO DATA: the board sent no readings during the capture. Is the sketch running?"
        if valid_pct <= 20:
            return "NOTHING IN VIEW: almost no echo came back, as expected with the door out of the sensor's way. The lock will treat 'no echo' as 'door open'."
        if valid_pct < 80:
            return "MIXED: some readings are echoes from something far away and some are no echo. The lock will have to treat both as 'door open'."
        return "SOMETHING IN VIEW: with the door open the sensor still reads about %d mm (the wall, or things behind the door?). The closed-door distance must be clearly different from this." % median
    if n == 0 or valid_pct < 50:
        return "BAD: no usable echo most of the time. Check the wiring and the power (try 5V if it is on 3V3), and that the sensor faces a flat surface squarely, 2 cm to 4 m away."
    if valid_pct < 90:
        return "POOR: %d%% of the readings were usable. Something is marginal: the power, a loose wire, or a surface that reflects badly (soft, slanted or tiny)." % round(valid_pct)
    if std <= 2.0:
        return "GOOD: steady to within about 2 mm."
    if std <= 5.0:
        return "OK: a little jumpy (spread %.1f mm). Fine for a door that moves by centimetres." % std
    return "POOR: jumpy (spread %.1f mm). Check the power and the surface it faces." % std


def stats(readings, kind="other"):
    """readings: a list of single readings in mm, with None for the unusable ones. Returns the numbers for one row of the table."""
    n = len(readings)
    good = [r for r in readings if r is not None]
    pct = 100.0 * len(good) / n if n else 0.0
    out = {"n": n, "valid": len(good), "valid_pct": round(pct, 1), "mean_mm": None, "median_mm": None, "min_mm": None, "max_mm": None, "std_mm": None}
    if good:
        out.update(mean_mm=round(statistics.fmean(good), 1), median_mm=statistics.median(good), min_mm=min(good), max_mm=max(good), std_mm=round(statistics.pstdev(good), 1) if len(good) > 1 else 0.0)
    out["verdict"] = verdict(n, pct, out["std_mm"] or 0.0, kind, out["median_mm"])
    return out


class SensorMonitor:
    def __init__(self, log_path=None, now=time.monotonic, clock=datetime.datetime.now, history_s=15.0):
        self.log_path, self.now, self.clock, self.history_s = log_path, now, clock, history_s
        self.readings = deque()            # (time, filtered, raw), newest last
        self.capture = None
        self.rows = []

    # ---- what the board tells us (called on the Bridge's own thread, so it only stores things)
    def on_distance(self, mm, raw):
        t = self.now()
        f, r = usable(mm), usable(raw)
        self.readings.append((t, f, r))
        while self.readings and t - self.readings[0][0] > max(self.history_s, 130.0):
            self.readings.popleft()
        if self.capture is not None:
            self.capture["raw"].append(r)

    # ---- captures
    def start_capture(self, label, supply, seconds, kind="other"):
        if self.capture is not None:
            raise ValueError("A capture is already running: wait until it finishes.")
        try:
            secs = int(float(seconds))
        except (TypeError, ValueError):
            raise ValueError("The capture length must be a number of seconds.")
        secs = max(1, min(60, secs))
        label = (str(label or "").strip() or "unlabelled")[:60]
        if supply not in SUPPLIES:
            raise ValueError("Say whether the sensor is powered from 3V3 or 5V.")
        kind = kind or "other"
        if kind not in KINDS:
            raise ValueError("Unknown kind of capture: " + str(kind)[:30])
        self.capture = {"label": label, "kind": kind, "supply": supply, "seconds": secs, "end": self.now() + secs, "raw": []}
        return secs

    def tick(self):
        """Call often. When a capture has run its time, finishes it and returns the new row (else None)."""
        c = self.capture
        if c is None or self.now() < c["end"]:
            return None
        self.capture = None
        row = {"time": self.clock().strftime("%H:%M:%S"), "label": c["label"], "kind": c["kind"], "supply": c["supply"], "seconds": c["seconds"]}
        row.update(stats(c["raw"], c["kind"]))
        self.rows.append(row)
        self._log(row)
        return row

    def clear(self):
        self.rows = []

    def _log(self, row):
        if not self.log_path:
            return
        new = not Path(self.log_path).exists()
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerow({k: row.get(k) for k in FIELDS})

    # ---- what the page shows
    def snapshot(self):
        t = self.now()
        last = self.readings[-1] if self.readings else None
        recent = [r for (tt, f, r) in self.readings if t - tt <= 3.0]
        hist = [[round(tt - t, 1), f] for (tt, f, r) in self.readings if t - tt <= self.history_s]
        if len(hist) > 150:
            step = -(-len(hist) // 150)
            hist = hist[::step]
        cap = None
        if self.capture is not None:
            cap = {"label": self.capture["label"], "kind": self.capture["kind"], "supply": self.capture["supply"], "seconds": self.capture["seconds"], "remaining_s": max(0.0, round(self.capture["end"] - t, 1))}
        return {"mm": last[1] if last else None, "raw": last[2] if last else None, "age_s": round(t - last[0], 1) if last else None,
                "ok_pct": round(100.0 * sum(r is not None for r in recent) / len(recent), 0) if recent else None, "history": hist, "capturing": cap, "rows": list(self.rows), "csv": "captures.csv"}
