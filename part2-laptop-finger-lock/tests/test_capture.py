"""Tests for the capture tool (fingerlock/capture_lib.py, session.py, synth_hand.py, capture.py, dataset_report.py). No camera needed.   python tests/test_capture.py"""
import shutil, sys, tempfile, time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fingerlock import capture_lib as cl
from fingerlock.session import CaptureSession
from fingerlock.synth_hand import SyntheticCamera, make_hand
import capture, dataset_report

problems = 0


def expect(label, cond, detail=""):
    global problems
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    problems += (not cond)


tmp = Path(tempfile.mkdtemp())
rng = np.random.default_rng(0)

print("1. the square (region of interest)")
r = cl.Roi(-5, 10, 5000).clipped(640, 480)
expect("a square that sticks out of the picture is clipped to fit inside it", r.x >= 0 and r.y >= 0 and r.x + r.side <= 640 and r.y + r.side <= 480 and r.side == 480, str(r))
cl.save_roi(cl.Roi(231, 141, 179), tmp / "sub" / "roi.json", (640, 480))
expect("it is saved (even if the folder does not exist yet) and loaded back", cl.load_roi(tmp / "sub" / "roi.json", (640, 480)) == cl.Roi(231, 141, 179))
expect("a square saved for a different camera size is refused, because its pixels would mean something else", cl.load_roi(tmp / "sub" / "roi.json", (1280, 720)) is None)
expect("a missing file gives None", cl.load_roi(tmp / "nothing.json") is None)

print("2. people are letters, not names")
ok = all(cl.check_person(p) == p for p in ("A", "b2", "XYZ"))
bad = []
for p in ("", "Alexander", "A B", "A/B", "A_1", "ab.c"):
    try: cl.check_person(p); bad.append(p)
    except ValueError: pass
expect("A, b2 and XYZ are accepted; an empty string, a name, spaces and slashes are all refused", ok and not bad, str(bad))

print("3. cropping")
frame = np.zeros((480, 640, 3), np.uint8); frame[150:250, 300:400] = (10, 200, 30)
c = cl.crop(frame, cl.Roi(300, 150, 100), 128)
expect("the crop is the chosen square, resized to 128 x 128, and it holds the green patch", c.shape == (128, 128, 3) and c.dtype == np.uint8 and np.all(c[10:-10, 10:-10] == (10, 200, 30)))
expect("a square at the very edge still crops without error", cl.crop(frame, cl.Roi(600, 440, 100)).shape == (128, 128, 3))

print("4. finding the red square")
errs = []
for k, (x, y, s) in enumerate(((220, 130, 200), (40, 40, 150), (400, 250, 180), (150, 60, 260))):
    cam = SyntheticCamera(square=(x, y, s), seed=k); ok_, f = cam.read()
    f = np.clip(f.astype(np.int16) + rng.normal(0, 5, f.shape), 0, 255).astype(np.uint8)
    roi = cl.find_red_square(f)
    if roi is None: errs.append(("none", x, y, s)); continue
    cx, cy = roi.x + roi.side / 2, roi.y + roi.side / 2
    if abs(cx - (x + s / 2)) > 6 or abs(cy - (y + s / 2)) > 6 or not (s * 0.7 < roi.side < s): errs.append((x, y, s, roi))
expect("on four squares of different sizes and places, with noise, it finds the inside of the square (centred within 6 pixels, a bit smaller than the outline so the red line is left out)", not errs, str(errs))
dim = (cv2.cvtColor(SyntheticCamera().read()[1], cv2.COLOR_BGR2HSV) * np.array([1, 1, 0.7])).astype(np.uint8)
expect("it still finds it in dimmer light", cl.find_red_square(cv2.cvtColor(dim, cv2.COLOR_HSV2BGR)) is not None)
empty = np.full((480, 640, 3), (120, 130, 140), np.uint8)
expect("a desk with no red gives None, not a guess", cl.find_red_square(empty) is None)
blue = empty.copy(); cv2.rectangle(blue, (220, 130), (420, 330), (215, 30, 30), 6)
expect("a blue square is not mistaken for the red one", cl.find_red_square(blue) is None)
dots = empty.copy(); cv2.circle(dots, (100, 100), 8, (30, 30, 215), -1); cv2.circle(dots, (500, 400), 6, (30, 30, 215), -1)
expect("small red dots are ignored", cl.find_red_square(dots) is None)
rect = empty.copy(); cv2.rectangle(rect, (100, 100), (500, 250), (30, 30, 215), 6)
expect("a red rectangle that is not square is refused (400 x 150)", cl.find_red_square(rect) is None)
two = empty.copy(); cv2.rectangle(two, (20, 20), (90, 90), (30, 30, 215), 5); cv2.rectangle(two, (250, 100), (450, 300), (30, 30, 215), 6)
rtwo = cl.find_red_square(two)
expect("with two red squares it picks the larger", rtwo is not None and rtwo.x > 240, str(rtwo))

errs = []
for color in cl.TAPE:
    cam = SyntheticCamera(square=(180, 100, 220), seed=4, tape=color); _, f = cam.read()
    roi = cl.find_square(f, color)
    others = [c for c in cl.TAPE if c != color and cl.find_square(f, c) is not None]
    if roi is None or abs(roi.x + roi.side / 2 - 290) > 6 or abs(roi.y + roi.side / 2 - 210) > 6: errs.append((color, "not found", roi))
    if others: errs.append((color, "also found as", others))
expect("tape of each colour (red, blue, green, yellow) is found when asked for, and is NOT found when another colour is asked for", not errs, str(errs))
cam = SyntheticCamera(tape="blue", seed=2); cam.set_label(3); _, fb = cam.read()
sb = CaptureSession(tmp / "blue", "A", frame_size=(640, 480), tape="blue"); sb.on_key("r", fb)
sr = CaptureSession(tmp / "blue2", "A", frame_size=(640, 480), tape="red"); sr.on_key("r", fb)
expect("a session told the tape is blue finds a blue square by itself; one told it is red does not, and says which colour it looked for", sb.roi is not None and sr.roi is None and "no red square" in sr.message, sr.message[:60])
sleeve = empty.copy(); cv2.rectangle(sleeve, (0, 200), (300, 330), (170, 110, 60), -1)
expect("a big blue-ish sleeve or jeans patch is not taken for a blue tape square (it is not square)", cl.find_square(sleeve, "blue") is None)
try: cl.find_square(empty, "purple"); w5 = False
except ValueError: w5 = True
expect("an unknown tape colour is refused", w5)
res_b = capture.main(["--person", "A", "--headless-demo", "--tape", "blue", "--out", str(tmp / "demo_blue")])
expect("the headless demo works with blue tape too", res_b == 0 and cl.Dataset(tmp / "demo_blue").counts() == {c: 3 for c in cl.CLASSES})

print("5. quality checks")
flat = np.full((128, 128, 3), 128, np.uint8)
qf = cl.quality(flat)
expect("a flat grey picture has no sharpness and no contrast, and is flagged", qf["sharpness"] < 1e-6 and qf["contrast"] < 1e-6 and {"blurry or flat", "low contrast"} <= set(cl.quality_flags(qf)))
noisy = rng.integers(0, 255, (128, 128, 3)).astype(np.uint8)
expect("a noisy picture is sharp, with contrast, and not flagged", cl.quality(noisy)["sharpness"] > 1000 and not cl.quality_flags(cl.quality(noisy)))
expect("dark and bright pictures are flagged", "too dark" in cl.quality_flags(cl.quality(np.full((8, 8, 3), 10, np.uint8))) and "too bright" in cl.quality_flags(cl.quality(np.full((8, 8, 3), 250, np.uint8))))
hand = make_hand(3, np.random.default_rng(1)); bg = np.full((128, 128, 3), 140, np.uint8)
expect("a picture identical to the empty square differs by 0, and one with a hand in it differs by a lot", cl.difference_from_empty(bg, bg) == 0 and cl.difference_from_empty(hand, np.full_like(hand, hand[2, 2])) > 0.05)
expect("a picture labelled 3 that looks empty is flagged, a picture labelled 0 that looks empty is not", any("EMPTY" in f for f in cl.quality_flags(cl.quality(noisy), 0.0, 3)) and not any("EMPTY" in f for f in cl.quality_flags(cl.quality(noisy), 0.0, 0)))

print("6. the dataset on disk")
d = cl.Dataset(tmp / "ds")
paths = [d.save(make_hand(c % 6, rng), c % 6, "A" if c < 20 else "B") for c in range(50)]
expect("50 pictures saved in the same instant all get different names, in a folder per class, named person__class__time", len({p.name for p in paths}) == 50 and all(p.parent.name == p.name.split("__")[1] for p in paths) and all(p.name.split("__")[0] in ("A", "B") for p in paths))
cnt = d.counts(); cA = d.counts("A")
expect("the counts add up: %s in all, %s for A" % (sum(cnt.values()), sum(cA.values())), sum(cnt.values()) == 50 and sum(cA.values()) == 20 and sum(d.counts("B").values()) == 30)
last = d.undo()
expect("undo deletes the last picture, returns its path, and the count drops", last == paths[-1] and not last.exists() and sum(d.counts().values()) == 49)
try: d.save(hand, 7, "A"); w1 = False
except ValueError: w1 = True
try: d.save(hand, 3, "Alexander"); w2 = False
except ValueError: w2 = True
expect("a class outside 0 to 5 and a person who is a name are refused", w1 and w2)
expect("undo with nothing left returns None", cl.Dataset(tmp / "ds2").undo() is None)

print("7. burst capture")
b = cl.Burst(3, n=20, interval=0.1)
times = [i * 0.05 for i in range(200)]
took = [t for t in times if b.due(t)]
expect("a burst takes 20 pictures, about 0.1 s apart, and then stops", len(took) == 20 and b.done and all(abs((y - x) - 0.1) < 0.051 for x, y in zip(took, took[1:])), "%d pictures" % len(took))

print("8. the session: keys, warnings, undo")
cam = SyntheticCamera(seed=3); cam.set_label(2); _, fr = cam.read()
s = CaptureSession(tmp / "s1", "A", roi_path=tmp / "s1" / "roi.json", frame_size=(640, 480))
s.on_key("3", fr)
expect("a digit before the square is set saves nothing and says to set the square first", sum(s.dataset.counts().values()) == 0 and "square" in s.message)
s.on_key("r", fr)
expect("r finds the red square and remembers it in a file", s.roi is not None and (tmp / "s1" / "roi.json").exists())
s.on_key("2", fr)
expect("a digit saves a picture and says how many of that class there are", s.dataset.counts("A")[2] == 1 and "saved 2" in s.message and "1 of this class" in s.message)
s.on_key("e", fr)
cam.set_label(0); cam.rng = np.random.default_rng(99); _, fr_empty = SyntheticCamera(seed=3).read()
s2 = CaptureSession(tmp / "s1b", "A", frame_size=(640, 480)); s2.set_roi(s.roi); s2.record_empty(fr_empty)
s2.on_key("3", fr_empty)
expect("with an empty-square picture recorded, saving an empty square as '3' gives a WARNING", "WARNING" in s2.message and "EMPTY" in s2.message, s2.message[-70:])
s2.on_key("3", fr)
expect("and the same label on a picture that really has a hand in it gives no warning", "WARNING" not in s2.message, s2.message[-70:])
n0 = sum(s.dataset.counts().values()); s.on_key("u")
expect("u undoes the last picture", sum(s.dataset.counts().values()) == n0 - 1 and "deleted" in s.message)
s.on_key("b")
expect("b switches burst mode on, and a digit then starts a burst of 20 instead of saving one", s.burst_mode and (s.on_key("4", fr) or True) and s.burst is not None and s.dataset.counts("A")[4] == 0)
for i in range(120): s.on_frame(fr, now=i * 0.05)
expect("feeding frames saves the 20 pictures of the burst and ends it", s.dataset.counts("A")[4] == 20 and s.burst is None and "burst done" in s.message)
s.on_key("q")
expect("q asks the tool to quit", s.quit)
again = CaptureSession(tmp / "s1", "A", roi_path=tmp / "s1" / "roi.json", frame_size=(640, 480))
other = CaptureSession(tmp / "s1", "A", roi_path=tmp / "s1" / "roi.json", frame_size=(1280, 720))
expect("a new session remembers the square for the same camera size, and forgets it for another size", again.roi == s.roi and other.roi is None)
try: CaptureSession(tmp / "s3", "Alexander"); w3 = False
except ValueError: w3 = True
expect("a session with a name instead of a letter is refused", w3)

print("8b. adjusting the square with the keys")
sa = CaptureSession(tmp / "adj", "A", roi_path=tmp / "adj" / "roi.json", frame_size=(640, 480))
sa.on_key("+"); sa.on_key("w")
expect("with no square set, + and w say to set it first and change nothing", sa.roi is None and "square first" in sa.message)
sa.set_roi(cl.Roi(200, 120, 248)); sa.empty = np.zeros((8, 8, 3), np.uint8)
sa.on_key("+")
expect("+ makes the square bigger by 24 pixels around its centre (the centre stays put), and forgets the empty-square picture, which no longer matches", sa.roi.side == 272 and abs((sa.roi.x + sa.roi.side / 2) - 324) <= 1 and abs((sa.roi.y + sa.roi.side / 2) - 244) <= 1 and sa.empty is None, str(sa.roi))
sa.on_key("-"); sa.on_key("-")
expect("- makes it smaller by 24 pixels each time", sa.roi.side == 224, str(sa.roi))
x0, y0 = sa.roi.x, sa.roi.y
for k in "dds": sa.on_key(k)
sa.on_key("a"); sa.on_key("w")
expect("d moves it right, a left, s down and w up, 12 pixels at a time", (sa.roi.x, sa.roi.y) == (x0 + 12, y0 + 0), str((sa.roi.x - x0, sa.roi.y - y0)))
for _ in range(40): sa.on_key("-")
expect("it never shrinks below 32 pixels", sa.roi.side == 32)
for _ in range(60): sa.on_key("+")
expect("it never grows beyond the picture: the saved square stays inside 640 x 480", sa.roi.side == 480 and sa.roi.x >= 0 and sa.roi.y >= 0 and sa.roi.x + sa.roi.side <= 640)
for _ in range(60): sa.on_key("d")
expect("it never moves outside the picture", sa.roi.x + sa.roi.side <= 640)
back = CaptureSession(tmp / "adj", "A", roi_path=tmp / "adj" / "roi.json", frame_size=(640, 480))
expect("the adjusted square is remembered for next time", back.roi == sa.roi)

print("9. the made-up hands and the made-up camera (used only to test the software)")
frac = []
for n in range(6):
    vals = []
    for k in range(25):
        h = make_hand(n, np.random.default_rng(k * 7 + n))
        vals.append(float((cv2.absdiff(h, cv2.GaussianBlur(h, (31, 31), 0)).max(axis=2) > 30).mean()))
    frac.append(np.mean(vals))
expect("more fingers means more hand in the picture (a rough check that the drawings differ by class)", frac[1] < frac[3] < frac[5], str(["%.3f" % f for f in frac]))
c1, c2 = SyntheticCamera(seed=5), SyntheticCamera(seed=5)
c1.set_label(4); c2.set_label(4)
expect("the made-up camera is repeatable for the same seed", np.array_equal(c1.read()[1], c2.read()[1]))

print("10. the whole tool, without a window")
res = capture.main(["--person", "A", "--headless-demo", "--out", str(tmp / "demo")])
ds = cl.Dataset(tmp / "demo")
expect("the headless demo finds the square by itself and saves 3 pictures of every class", res == 0 and ds.counts() == {c: 3 for c in cl.CLASSES} and (tmp / "demo" / "roi.json").exists())
try: capture.main(["--person", "Alexander", "--headless-demo", "--out", str(tmp / "d2")]); w4 = False
except ValueError: w4 = True
expect("it refuses a name as the person", w4)
vis = capture.draw(SyntheticCamera().read()[1], CaptureSession(tmp / "ui", "A"))
expect("the window's overlay (counts, messages, warnings) draws on the picture without changing its size", vis.shape == (480, 640, 3) and np.abs(vis[:60].astype(int) - SyntheticCamera().read()[1][:60].astype(int)).sum() > 0)

print("11. the dataset report")
rep = dataset_report.report(tmp / "ds", target=10)
expect("it counts pictures per class and per person, and finds the people", rep["total"] == 49 and rep["people"] == ["A", "B"] and sum(rep["per_person"]["A"].values()) == 20)
expect("it says what is still to collect, and notes that two people is too few", any("class" in t for t in rep["todo"]) and any("only 2 people" in n for n in rep["notes"]))
shutil.copy(paths[0], paths[0].parent / "A__0__copy.png")
expect("it detects an exact duplicate file", dataset_report.report(tmp / "ds", 10)["duplicates"] >= 1)
(tmp / "blur" / "1").mkdir(parents=True)
for i in range(5): cv2.imwrite(str(tmp / "blur" / "1" / ("A__1__%d.png" % i)), np.full((128, 128, 3), 120, np.uint8))
rb = dataset_report.report(tmp / "blur", 3)
expect("it warns about flat or blurry pictures", any("blurry" in n for n in rb["notes"]), str(rb["notes"]))
(tmp / "unb" / "0").mkdir(parents=True); (tmp / "unb" / "1").mkdir(parents=True)
for i in range(10): cv2.imwrite(str(tmp / "unb" / "0" / ("A__0__%d.png" % i)), make_hand(0, np.random.default_rng(i)))
for i in range(2): cv2.imwrite(str(tmp / "unb" / "1" / ("A__1__%d.png" % i)), make_hand(1, np.random.default_rng(i)))
expect("it warns when one class has more than twice as many pictures as another (10 against 2)", any("unbalanced" in n for n in dataset_report.report(tmp / "unb", 5)["notes"]))
txt = dataset_report.render(rep, 10)
expect("the printed report has a table with one row per person and a total", "person A" in txt and "person B" in txt and "all " in txt)
expect("an empty folder is reported plainly, not with a crash", dataset_report.report(tmp / "nope", 10)["total"] == 0 and "no pictures" in dataset_report.report(tmp / "nope", 10)["notes"][0])

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
