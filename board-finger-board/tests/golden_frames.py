"""Made-up camera pictures built only from whole-number arithmetic and OpenCV's exact drawing, so that every computer makes the very same picture."""
import cv2
import numpy as np


def golden_frame(seed, w=640, h=480):
    yy, xx = np.mgrid[0:h, 0:w]
    f = np.stack([(xx * 3 + yy * 2 + 40 * seed) % 256, (xx + yy * 5 + 90 * seed) % 256, (xx * 2 + yy + 150 * seed) % 256], axis=2).astype(np.uint8)
    rs = np.random.RandomState(seed)
    for _ in range(4):
        x, y, s = int(rs.randint(100, 380)), int(rs.randint(140, 380)), int(rs.randint(40, 160))
        cv2.rectangle(f, (x, y), (x + s, y + s), tuple(int(c) for c in rs.randint(0, 256, 3)), -1)
    cv2.circle(f, (int(rs.randint(150, 450)), int(rs.randint(200, 420))), int(rs.randint(30, 90)), tuple(int(c) for c in rs.randint(0, 256, 3)), -1)
    return f


def blob_frame(seed, w=640, h=480):
    """A grey background with a skin-coloured palm and a few finger shapes in the square, a different number each time (made only of exact drawing, like the other pictures)."""
    rs = np.random.RandomState(1000 + seed)
    bg = int(rs.randint(40, 90))
    f = np.full((h, w, 3), bg, np.uint8)
    skin = (int(rs.randint(110, 160)), int(rs.randint(140, 185)), int(rs.randint(190, 235)))          # BGR
    cx, cy = int(rs.randint(220, 300)), int(rs.randint(300, 340))
    cv2.ellipse(f, (cx, cy), (70, 55), 0, 0, 360, skin, -1)                                            # the palm
    for i in range(int(rs.randint(0, 6))):                                                              # 0 to 5 fingers pointing up
        fx = cx - 50 + i * 25 + int(rs.randint(-4, 5))
        cv2.ellipse(f, (fx, cy - 85), (11, 60), 0, 0, 360, skin, -1)
    return f


STYLES = {"stripes": golden_frame, "blob": blob_frame}


def frame_for(style, seed):
    return STYLES[style](seed)
