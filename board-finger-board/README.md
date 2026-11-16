# Finger Count on the Board

Step 4 of the lock box: **the trained finger-counting network running on the UNO Q, with the webcam.** This is the "works on the UNO Q" part of the midterm (nothing is trained here: the network was trained on the computer, and its numbers are simply loaded). A web page on your laptop shows the camera view with the square, the number of fingers the network sees, how sure it is, whether the answer is steady, and **how long each step takes on the board**. It also measures the board's speed against your laptop's, which is the "UNO Q vs computer" part of the midterm.

## What it needs

- The **same webcam** you recorded the training pictures with, plugged into the hub, **fixed in place** and aimed at your tape square, in about the same light. The network was trained on exactly that square.
- Nothing to install: it uses NumPy and OpenCV, which the board already has (the sumo app used them). The network is plain NumPy, with no PyTorch.
- The trained network is inside the app (`python/model/finger_cnn.npz`, the "v2" network, 278 KB).

## Run it

Copy this folder into Arduino App Lab as an app and press Run. Then open **`http://<the board's address>:7000`** in the browser on your laptop. The App Lab console prints the NumPy and OpenCV versions it found.

## Use it

The page shows the **camera view with a green square** (what the network looks at), the network's **answer** and six **probability bars**, the **64 x 64 picture** the network really gets, and the **speed**.

1. **Is the camera found?** The "camera" chip at the top should turn green and name the webcam. If it says "no camera found yet", plug the webcam into the hub: the app looks again every 5 seconds. (It finds the webcam the way the sumo app did: it skips the board's own video devices.)
2. **Put the square on the tape.** Press "Find the tape square" (blue by default), check that the green square sits just inside your tape, adjust it with the **arrow keys** (4 pixels; Shift = 16) and the **+ and - keys**, then press **Save the square**. For reference, the network was trained on x 108, y 163, side 317 at 640 x 480: the closer you are to that, the better it works. "Back to the training square" goes back to it.
3. **Show your hand** in the square with 1, 2, 3, 4 and 5 fingers (thumb folded for 1 to 4, open hand for 5; a fist or an empty square is 0). The answer and the bars should follow, and the **"steady answer" chip turns green** after about a second (8 pictures that agree). This is the same steadiness rule the lock will use.

   **Camera speed.** Look at "camera pictures per second" in the speed panel. The network can do about 36 steps a second on this board, so the camera should be somewhere near that. On the first run it was **7.5** (the camera's own choice of picture format), which makes the live view 5 times slower than it needs to be. The **Camera format** list asks the camera for another format and reopens it: **MJPG** (compressed pictures need less of the USB hub, so the camera can usually go faster; the app now asks for it, at 30 frames a second, to begin with), **YUYV** (uncompressed) or "the camera chooses". Pick one, press Apply, and watch the number for 10 seconds. The choice is remembered (`python/camera.json`), and the chip names the format the camera says it agreed to.

   **Result so far:** with MJPG the camera gave **9.7** pictures a second (7.5 before), and the network steps match it (9.6): the network is waiting for the camera. That is better but far from the 30 the camera reports, so two more experiments:
   1. **Light.** Put a bright lamp on the square and watch the number for 10 seconds. In dim light a camera makes each exposure longer and lowers its own frame rate to match.
   2. **Pause the network.** The button under the speed numbers stops the network but not the camera, so "camera pictures per second" is then the camera's own speed. If it jumps to about 30, the network was starving the camera of processor time (the lock app would then read the camera in a separate process). If it stays near 10, it is the camera, the light or the USB hub.
4. **Benchmark.** Press the button (about 5 seconds, the live view pauses). The table gets two rows: the **standard made-up picture** (identical on every machine, so it can be compared) and, if a camera picture is there, the **camera picture**. Note "one step" and "steps / s".
5. **The same on your laptop.** In a terminal: `python compare/bench_numpy.py` (needs `pip install numpy opencv-python`). It prints the same numbers for your computer, using the same code, network and standard picture. Board against laptop, same test.

## Measured on the real hardware (first run)

| | UNO Q (aarch64, Python 3.13, NumPy 2.5, OpenCV 4.13) | Laptop (AMD64, Python 3.12, NumPy 2.5, OpenCV 4.13) | The board is |
|---|---|---|---|
| One whole step (standard made-up picture) | **27.9 ms**, 36 steps a second | 8.3 ms, 120 steps a second | 3.4 times slower |
| The network | 23.8 ms (slowest 5%: 45.5, worst 61.9) | 7.6 ms (slowest 5%: 9.5, worst 11.9) | 3.1 times slower |
| Cutting out the square | 3.9 ms | 0.72 ms | 5.4 times slower |
| The same on a real camera picture | 28.8 ms | | |
| Camera pictures per second (the camera's own format) | 7.5 | | |
| Camera pictures per second (MJPG) | 9.7 | | |

The board runs the network and its finger detection looked just as good as on the laptop. The network is plain NumPy on both machines, so the difference is the processor, not the program. The board's slowest steps are also much slower than its typical ones (62 ms against 24), because the camera, the web page and the system share the same processor. At 7.5 pictures a second the camera, not the network, set the pace of the live view.

## What to send me

| | |
|---|---|
| Was the camera found by itself? What name and device does the chip show? | ___ |
| Board: one step (ms), network part (ms), steps per second | ___ ms, ___ ms, ___ /s |
| Camera pictures per second with MJPG, with YUYV, and with "the camera chooses" (watch each for 10 seconds), and what the chip says the camera reports | ___ , ___ , ___ /s |
| Camera pictures per second with a bright lamp on the square | ___ /s |
| Camera pictures per second with the network paused (MJPG) | ___ /s |
| Laptop (`bench_numpy.py`): one step (ms), network part (ms), steps per second | ___ ms, ___ ms, ___ /s |
| Does the digit follow your hand for 0 to 5? Does it feel as good as on the laptop? | ___ |
| How long until "steady answer" turns green after you show a number? | ___ s |
| Did the square need moving from the training square? What is it now (shown under the picture)? | x ___ y ___ side ___ |
| Does the picture look different from the laptop's (blurry, darker, flickering)? | ___ |
| Anything in the App Lab console (errors, the library versions) | ___ |
| `python/board_speed.csv` | attach it |

If the board turns out **too slow** (the steps per second are low, or the picture is old), tell me the numbers. A first thing to try is a smaller camera picture: in `python/main.py` change `FRAME_W, FRAME_H` to `320, 240` (the square is scaled to fit; a square saved for 640 x 480 is not used at another size, on purpose).

## Files

```
app.yaml  sketch/sketch.ino  sketch/sketch.yaml      the App Lab app (the sketch is empty: the microcontroller has nothing to do here)
python/main.py                                         connects the camera, the network and the page (WebUI brick, port 7000)
python/camera.json                                     (made by the app) the camera format you last chose
python/board_vision.py                                 the square, the steps from camera picture to the network, tape finding, the camera, the speed test
python/infer_numpy.py                                  the network in plain NumPy (copied unchanged from the finger-lock project)
python/model/finger_cnn.npz                            the trained network (v2)
assets/index.html  app.js  style.css  libs/            the page (socket.io is included, so it needs no internet)
compare/bench_numpy.py                                 the same speed test for your laptop
tests/run_all.py                                       runs every test the computer can run
tests/test_vision.py + golden_frames.py + golden.json  the Python tests, including the check against the original finger-lock code
tests/make_golden.py                                   remakes golden.json from the finger-lock project (only needed if you change the network or the steps)
tests/test_page.js                                     the page in a simulated browser (needs node and: npm install jsdom)
```

## What was tested, and what was not

`python tests/run_all.py` runs the `app.yaml` check, 110 checks of the Python side and 55 of the page.

- **The steps from camera picture to the network are checked against the original finger-lock code:** on 16 made-up pictures the app gives the same digits and the same probabilities, to the last decimal (the check also fails if blue and red are swapped, which changes the answers by up to 0.9).
- Also tested, with fake devices and fake cameras: finding the webcam while skipping the board's video devices, a camera plugged in later or lost, the camera format being requested in the right order and remembered, the background reader that always hands out the newest picture, the steadiness rule, the tape finder, moving and saving the square, the timing statistics, the whole main program, and the laptop script.

**The board's speed, the camera's detection and the page were then tried once on the real hardware (the table above).** What has not been tried on the real board is the camera-format switch (MJPG against YUYV), and none of it has run in a browser other than yours. In particular:

- The numbers printed by the tests are from a development computer and mean nothing for the UNO Q: the table above is from the real board.
- **Why the camera stops at about 10 pictures a second is not known** (MJPG raised it from 7.5 to 9.7, not to 30): light, the USB hub, or the network taking the processor are the suspects, and the two experiments above separate them. MJPG pictures are JPEG-compressed, which could change the network's answers slightly: tell me if the detection gets worse.
- The board's NumPy is 2.5.3 (the network needs 1.20 or newer): fine.
- The training pictures were taken on your laptop with an autofocus-off webcam; this app switches autofocus off too, but does not control the exposure or the white balance, so a difference in how the picture looks is possible.
- The camera on the box is probably not in exactly the training position: expect to move the square, and expect the network to be less accurate if the picture differs (the network was tested at about 71 to 84% on new people and sessions, never on this setup).
- The sketch is empty and was not compiled with Arduino's tools.
