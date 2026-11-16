# Finger Count on the Board

Step 4 of the lock box: **the trained finger-counting network running on the UNO Q, with the webcam.** Nothing is trained here: the network was trained on the computer, and its numbers are loaded from a file. A web page on your laptop shows the camera view with the square, the number of fingers the network sees, how sure it is, whether the answer is steady, and **how long each step takes on the board**. It also measures the board's speed against a laptop's, with the same code.

## What it needs

- The **same webcam** the training pictures were taken with, plugged into the hub, **fixed in place** and aimed at your tape square, in about the same light. The network was trained on exactly that square.
- Nothing to install: it uses NumPy and OpenCV, which the board already has. The network is plain NumPy, with no PyTorch.
- The trained network is inside the app (`python/model/finger_cnn.npz`, the "v2" network, 278 KB).

## Run it

Copy this folder into Arduino App Lab as an app and press Run. Then open **`http://<the board's address>:7000`** in the browser on your laptop. The App Lab console prints the NumPy and OpenCV versions it found.

## Use it

The page shows the **camera view with a green square** (what the network looks at), the network's **answer** and six **probability bars**, the **64 x 64 picture** the network really gets, and the **speed**.

1. **Is the camera found?** The "camera" chip at the top should turn green and name the webcam. If it says "no camera found yet", plug the webcam into the hub: the app looks again every 5 seconds. (It skips the board's own video devices.)
2. **Put the square on the tape.** Press "Find the tape square" (blue by default), check that the green square sits just inside your tape, adjust it with the **arrow keys** (4 pixels; Shift = 16) and the **+ and - keys**, then press **Save the square**. For reference, the network was trained on x 108, y 163, side 317 at 640 x 480: the closer you are to that, the better it works. "Back to the training square" goes back to it.
3. **Show your hand** in the square with 1, 2, 3, 4 and 5 fingers (thumb folded for 1 to 4, open hand for 5; a fist or an empty square is 0). The answer and the bars should follow, and the **"steady answer" chip turns green** after about a second (8 pictures that agree). This is the same steadiness rule the lock will use.

   **Camera speed.** "Camera pictures per second" in the speed panel shows how fast the camera delivers pictures. The **Camera format** list asks the camera for **MJPG** (compressed, the default, at 30 frames a second), **YUYV** (uncompressed) or "the camera chooses", and reopens it. The choice is remembered (`python/camera.json`), and the chip names the format the camera agreed to. The button under the speed numbers pauses the network but not the camera.
4. **Benchmark.** Press the button (about 5 seconds, the live view pauses). The table gets two rows: the **standard made-up picture** (identical on every machine, so it can be compared) and, if a camera picture is there, the **camera picture**. Note "one step" and "steps / s".
5. **The same on a laptop.** In a terminal: `python compare/bench_numpy.py` (needs `pip install numpy opencv-python`). It prints the same numbers for the computer, using the same code, network and standard picture. Board against laptop, same test.

## Measured on the real hardware

| | UNO Q (aarch64, Python 3.13, NumPy 2.5, OpenCV 4.13) | Laptop (AMD64, Python 3.12, NumPy 2.5, OpenCV 4.13) | The board is |
|---|---|---|---|
| One whole step (standard made-up picture) | **27.9 ms**, 36 steps a second | 8.3 ms, 120 steps a second | 3.4 times slower |
| The network | 23.8 ms (slowest 5%: 45.5, worst 61.9) | 7.6 ms (slowest 5%: 9.5, worst 11.9) | 3.1 times slower |
| Cutting out the square | 3.9 ms | 0.72 ms | 5.4 times slower |
| The same on a real camera picture | 28.8 ms | | |
| Camera pictures per second (the camera's own format) | 7.5 | | |
| Camera pictures per second (MJPG) | 9.7 | | |

The board runs the network and its finger detection looked just as good as on the laptop. The network is plain NumPy on both machines, so the difference is the processor, not the program. The board's slowest steps are also much slower than its typical ones (62 ms against 24), because the camera, the web page and the system share the same processor. At 7.5 pictures a second the camera, not the network, set the pace of the live view.

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

## Tests

`python tests/run_all.py` runs the `app.yaml` check, 110 checks of the Python side and 55 of the page.

- **The steps from camera picture to the network are checked against the original finger-lock code:** on 16 made-up pictures the app gives the same digits and the same probabilities, to the last decimal (the check also fails if blue and red are swapped, which changes the answers by up to 0.9).
- Also tested, with fake devices and fake cameras: finding the webcam while skipping the board's video devices, a camera plugged in later or lost, the camera format being requested in the right order and remembered, the background reader that always hands out the newest picture, the steadiness rule, the tape finder, moving and saving the square, the timing statistics, the whole main program, and the laptop script.

The speed numbers printed by the tests come from the development computer; the table above is from the real board.
