# A lock you open with your fingers

A box that opens only when you show it the right three digits **with your fingers**. A webcam looks at your hand, a small convolutional neural network (CNN) that I trained from scratch counts the fingers (0 to 5), and an Arduino UNO Q runs the lock: it checks the code, opens the door with a motor, checks with a distance sensor that the door really moved, and raises an alarm if somebody forces the door.

## What is in this repository

| Folder | What it is |
|---|---|
| `part1-v-fit/` | Part 1: fitting the "V" data with one neuron and a ReLU layer: the gradient-descent math, the Excel file (five iterations), the Python plots |
| `part2-laptop-finger-lock/` | Part 2, on the laptop: capturing pictures, training the CNN in PyTorch, honest testing, the live finger counter and the lock demo |
| `models/finger-lock-model-v2/` | the trained network (PyTorch file and the NumPy copy that runs on the board) |
| `board-lock-box/` | **the lock, on the UNO Q** (an Arduino App Lab app): camera, network, lock rules, door, LED matrix, web page |
| `board-finger-board/` | the finger-counting network on the UNO Q on its own, with a speed benchmark (the "UNO Q vs computer" numbers) |
| `hardware-tests/` | the door piece by piece: `ultrasonic-test/`, `motor-test/`, and `door-controller/` (both together) |
| `docs/` | the Notion page text, the script of the stop-action explainer movie, the V-fit write-up, and a study guide of the laptop project |

Each folder has its own README with how to run it, what was tested and what was not.

## How it works, in short

1. **The picture.** A fixed webcam looks at a hand inside a taped square. The square is cut out and shrunk to 64 x 64.
2. **The network.** Three convolution stages (16 filters of 5 x 5, 32 of 3 x 3, 64 of 3 x 3, each with ReLU and max-pooling), joined into 1,792 numbers, then a linear layer: six probabilities, for 0 to 5 fingers. 35,110 numbers learned from 2,400 pictures.
3. **The lock rules.** Three different digits from 1 to 5, each accepted only when 8 pictures in a row agree, with a rest between digits; a live challenge digit first (shown on the LED matrix); three wrong tries lock it out for 30 s, doubling each time; the code is stored only as a salted hash and the log never records which digits were shown.
4. **The door.** A motor swings it; the distance sensor checks every move (closed 106 mm), and a forced door raises a tamper alarm that blocks finger entry for 15 s (and is not counted as a wrong try).

## Results (measured)

| | Result |
|---|---|
| Fingers read correctly, new person | 71.4% and 73.9% (trained on one person, tested on the other) |
| Fingers read correctly, new session | 81.3% |
| Network step, UNO Q vs laptop (same code, same picture) | 27.9 ms vs 8.3 ms (3.4 times slower; 36 vs 120 steps a second) |
| Camera on the board | about 12 pictures a second (MJPG) |
| The lock rules on the board vs the original rules | identical on a recorded session of 93 events |
| On the real box: lockout, relock, door | 30 s, 10 s, closes to 106 mm, 3 of 3 |
| On the real box: locked and untouched | 6 min 11 s with no false alarm; the forced door was detected 3 of 3 times |


## Privacy and security

- **The 2,400 training pictures are not in this repository.** 
- **No real code is stored here.** The box keeps only a salted hash, in `lock_config.json` on the board, which git ignores. **But the examples and tests in this repository use the codes 1-5-3, 2-4-5 and 3-1-4, so do not use those on a real box.** Anyone who has seen the demo videos has also seen the fingers.
- It is a classroom lock: three different digits from 1 to 5 are only 60 codes; the control page can set a new code without the old one and sends it unencrypted over the local network; the maintenance buttons bypass the code; and the motor does not hold the door shut, it only detects and reports a forced one. The limitations are written out in `docs/notion_midterm_page.md`.


