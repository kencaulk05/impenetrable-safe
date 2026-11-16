"""The state and the key handling of the capture tool, with no window in it (so the tests can drive it with fake frames and key presses)."""
import time
from pathlib import Path

from fingerlock import capture_lib as cl

HELP = ("0-5 save one picture of that many fingers (0 = empty square or closed fist) | b: burst mode (a digit then saves 20 pictures while you move the hand a little) | "
        "r: find the taped square (colour set with --tape) | drag with the mouse: choose the square yourself | + and -: make the square bigger or smaller | w a s d: move it | e: take a picture of the EMPTY square (lets the tool warn you about empty 'hands') | "
        "u: undo the last picture | q: quit")


class CaptureSession:
    def __init__(self, out, person, roi=None, roi_path=None, frame_size=None, save_size=cl.SAVE_SIZE, tape="red"):
        self.dataset = cl.Dataset(out)
        self.person = cl.check_person(person)
        if tape not in cl.TAPE:
            raise ValueError("tape colour must be one of %s" % (cl.TAPE,))
        self.tape = tape
        self.roi_path = Path(roi_path) if roi_path else None
        self.frame_size = frame_size
        self.save_size = save_size
        self.roi = roi if roi is not None else (cl.load_roi(self.roi_path, frame_size) if self.roi_path else None)
        self.empty = None                                         # a picture of the empty square
        self.burst_mode = False
        self.burst = None
        self.message = HELP
        self.quit = False
        self.last_flags = []

    # ---- the square
    def set_roi(self, roi):
        self.roi = roi.clipped(*self.frame_size) if self.frame_size else roi
        if self.roi_path and self.frame_size:
            cl.save_roi(self.roi, self.roi_path, self.frame_size)
        self.empty = None                                         # a new square needs a new empty picture
        self.message = "square set: %d x %d pixels at (%d, %d)" % (self.roi.side, self.roi.side, self.roi.x, self.roi.y)

    STEP = 12                                                    # pixels per key press

    def resize(self, delta):
        """Make the square bigger or smaller around its centre. The saved pictures are always resized to the same size, so this only changes how much of the scene is in them."""
        if self.roi is None:
            self.message = "set the square first (press r, or drag a box)"
            return
        side = max(32, self.roi.side + delta)
        self.set_roi(cl.Roi(self.roi.x - (side - self.roi.side) // 2, self.roi.y - (side - self.roi.side) // 2, side))

    def nudge(self, dx, dy):
        if self.roi is None:
            self.message = "set the square first (press r, or drag a box)"
            return
        self.set_roi(cl.Roi(self.roi.x + dx, self.roi.y + dy, self.roi.side))

    def auto_roi(self, frame):
        r = cl.find_square(frame, self.tape)
        if r is None:
            self.message = "no %s square found: drag a box with the mouse instead (or improve the light and use a thicker line)" % self.tape
            return False
        self.set_roi(r)
        return True

    def record_empty(self, frame):
        if self.roi is None:
            self.message = "set the square first (press r)"
            return
        self.empty = cl.crop(frame, self.roi, self.save_size)
        self.message = "empty square recorded: pictures labelled 1 to 5 that look empty will be flagged"

    # ---- saving
    def capture(self, frame, label):
        if self.roi is None:
            self.message = "set the square first: press r to find the red square, or drag a box with the mouse"
            return None
        img = cl.crop(frame, self.roi, self.save_size)
        q = cl.quality(img)
        flags = cl.quality_flags(q, cl.difference_from_empty(img, self.empty), label)
        path = self.dataset.save(img, label, self.person)
        self.last_flags = flags
        n = self.dataset.counts(self.person)[label]
        self.message = "saved %d (person %s): %d of this class so far%s" % (label, self.person, n, "  WARNING: " + ", ".join(flags) if flags else "")
        return path

    def on_frame(self, frame, now=None):
        """Called for every camera frame: saves the next picture of a running burst when it is due."""
        if self.burst is not None:
            if self.burst.due(time.monotonic() if now is None else now):
                self.capture(frame, self.burst.label)
            if self.burst.done:
                self.message = "burst done: %d pictures of %d saved" % (self.burst.taken, self.burst.label)
                self.burst = None

    def on_key(self, key, frame=None, now=None):
        """key is a single character. Returns the message to show."""
        if key in ("q", "\x1b"):
            self.quit = True
        elif key in "012345" and key != "":
            label = int(key)
            if self.burst_mode:
                if self.roi is None:
                    self.message = "set the square first: press r"
                else:
                    self.burst = cl.Burst(label)
                    self.message = "burst of %d pictures of %d: move the hand a little" % (self.burst.n, label)
            elif frame is not None:
                self.capture(frame, label)
        elif key == "b":
            self.burst_mode = not self.burst_mode
            self.message = "burst mode %s" % ("ON: a digit saves 20 pictures" if self.burst_mode else "off: a digit saves one picture")
        elif key == "r" and frame is not None:
            self.auto_roi(frame)
        elif key == "e" and frame is not None:
            self.record_empty(frame)
        elif key == "u":
            p = self.dataset.undo()
            self.message = "deleted %s" % p.name if p else "nothing to undo"
        elif key in ("+", "="):
            self.resize(2 * self.STEP)
        elif key in ("-", "_"):
            self.resize(-2 * self.STEP)
        elif key == "w":
            self.nudge(0, -self.STEP)
        elif key == "s":
            self.nudge(0, self.STEP)
        elif key == "a":
            self.nudge(-self.STEP, 0)
        elif key == "d":
            self.nudge(self.STEP, 0)
        elif key == "h":
            self.message = HELP
        return self.message

    def counts(self):
        return self.dataset.counts(self.person), self.dataset.counts()
