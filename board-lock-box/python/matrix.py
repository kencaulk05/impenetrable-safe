"""Pictures for the UNO Q's LED matrix (8 rows x 13 columns): digits, a closed and an open padlock, a cross, a tick, and a few signals. A picture is a boolean array (8, 13).
frame_rows() turns one into 8 integers (13 bits each, leftmost LED = highest bit): the form the sketch on the board will take. render() draws it in the demo window."""
import cv2
import numpy as np

ROWS, COLS = 8, 13


def _frame(lines):
    assert len(lines) == ROWS and all(len(l) == COLS for l in lines), lines
    return np.array([[c == "#" for c in l] for l in lines], dtype=bool)


_G = {0: [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."], 1: ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
      2: [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"], 3: [".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."],
      4: ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."], 5: ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."]}


def digit(d, done=None, of=3):
    """The digit big in the middle; if done is given, a row of `of` dots underneath with the first `done` lit (progress through the code)."""
    f = np.zeros((ROWS, COLS), dtype=bool)
    f[:7, 4:9] = np.array([[c == "#" for c in row] for row in _G[d]], dtype=bool)
    return f if done is None else with_progress(f, done, of)


def with_progress(f, done, of=3):
    f = f.copy(); f[7, :] = False
    for i in range(of):
        f[7, 3 + i * (7 // max(1, of - 1) if of > 1 else 0)] = i < done if of > 1 else done > 0
    return f


LOCKED = _frame([".....###.....", "....#...#....", "....#...#....", "...#######...", "...#######...", "...###.###...", "...#######...", "...#######..."])
UNLOCKED = _frame([".....###.....", "....#...#....", "........#....", "...#######...", "...#######...", "...###.###...", "...#######...", "...#######..."])
TICK = _frame([".............", ".........#...", "........##...", ".......##....", "..#...##.....", "..##.##......", "...###.......", "....#........"])
CROSS = np.zeros((ROWS, COLS), dtype=bool)
for _i in range(7):
    CROSS[_i, 3 + _i] = CROSS[_i, 9 - _i] = True
READY = np.zeros((ROWS, COLS), dtype=bool); READY[0, :] = READY[7, :] = READY[:, 0] = READY[:, 12] = True        # a frame: "show your hand"
LOCKOUT = CROSS.copy(); LOCKOUT[7, :] = True


def challenge(d):
    """A digit the person must show first: the digit with a dotted line underneath, to tell it from progress."""
    f = digit(d); f[7, ::2] = True
    return f


def frame_rows(f):
    return [int("".join("1" if v else "0" for v in row), 2) for row in f]


def render(f, scale=14):
    """An image of the matrix: dark board, orange LEDs."""
    img = np.full((ROWS * scale, COLS * scale, 3), 25, np.uint8)
    for r in range(ROWS):
        for c in range(COLS):
            cv2.circle(img, (c * scale + scale // 2, r * scale + scale // 2), scale // 2 - 2, (30, 150, 255) if f[r, c] else (50, 50, 50), -1, cv2.LINE_AA)
    return img


def for_events(events, ctl_display):
    """The picture to show after these events (None: leave the picture as it is)."""
    pic = None
    for e in events:
        k = e[0]
        if k == "session": pic = READY
        elif k == "challenge": pic = challenge(e[1][0])
        elif k == "challenge_ok": pic = TICK
        elif k == "enter_code": pic = with_progress(READY, 0, ctl_display["of"])
        elif k == "digit": pic = with_progress(digit(e[2]), e[1] + 1, ctl_display["of"])
        elif k == "unlocked": pic = UNLOCKED
        elif k == "denied": pic = CROSS
        elif k == "lockout": pic = LOCKOUT
        elif k in ("relock", "lockout_over", "timeout"): pic = LOCKED
    return pic
