# Midterm: a lock you open with your fingers

> **BEFORE YOU PUBLISH (delete this box).** Search the page for `[FILL` and replace each one. There are 8 kinds (the video table has one for each row):
> 1. the GitHub link  2. the video links (table below)  3. owner's 10 honest tries  4. another person's 10 tries
> 5. code check time (ms)  6. camera / network steps per second while the lock runs  7. the reflection answers  8. the laptop camera speed (or delete that row)
> Everything else on this page was measured or computed, and the source of each number is written next to it.

## Intro

I built a box that opens only when you show it the right three digits **with your fingers**. A webcam looks at my hand, a small neural network that I trained from scratch counts the fingers (0 to 5), and an Arduino UNO Q runs the lock: it checks the code, opens the door with a motor, and raises an alarm if somebody forces the door open.

The network is a **convolutional neural network (CNN)** written and trained in PyTorch on my laptop. The UNO Q does not train anything: it only runs the finished network (as a plain NumPy copy that gives the same answers as the PyTorch one). Everything about the box (the code, the door, the alarm, the log) is on the board.

**GitHub:** [FILL: link to the repository]

## Demo videos

| # | What you see | Video |
|---|---|---|
| 1 | Setting up: the camera view, the tape square, choosing the password | [FILL] |
| 2 | Opening the box: the live challenge first (the LED matrix shows a digit), then the code | [FILL] |
| 3 | Failing the challenge (the wrong digit) | [FILL] |
| 4 | Failing the code (a wrong code, three times, then the lockout) | [FILL] |
| 5 | Opening with the code 1-3-5 | [FILL] |
| 6 | Opening with another code (2-4-3) | [FILL] |
| 7 | Forcing the locked door: the tamper alarm, and the motor pushes it shut | [FILL] |
| 8 | Close-ups of the LED matrix (digit, padlock, cross, lockout, "!") | [FILL] |
| 9 | Stop-action explainer: how the CNN counts fingers (my voice) | [FILL] |

## Part 1: fitting Anna's "V" (the math of one neuron)

I fitted the V-shaped data from Anna's neural-network page with one neuron and then with a small ReLU layer: the gradient-descent math written out, five iterations in Excel (m and b), and Python plots. A single neuron can only draw a line (it ends up flat across the V); two ReLU neurons can make the V, but from random starting values they only found it in 5 of 10 tries (three neurons: 6 of 10); with four or more neurons it worked from every one of 10 random starts. That is what the network in Part 2 relies on: many simple neurons together. The full write-up with the Excel file and the plots is in the section "V-fit" (`v-fit/` in the repository).

## Part 2: the finger-counting network

**Data.** 2,400 pictures of a hand inside a taped square, taken by a fixed webcam: 200 pictures for each of the 6 classes (0 = empty square or fist, 1 to 5 fingers), from two people (A and B), in two sessions about ten hours apart. The thumb is folded for 1 to 4 and open for 5.

**Honest tests** (nothing was chosen using the test pictures):

| Test | Accuracy |
|---|---|
| Trained on one person, tested on the other: A as the new person | 73.9% |
| Trained on one person, tested on the other: B as the new person | 71.4% |
| Trained on the first session, tested on the second (new session, both people) | 81.3% |
| (The final network on its own training pictures: 96.5%. This is **not** a test.) | |

92% of the mistakes are off by exactly one finger. The digits the network reads best on a new session are 0, 1 and 5 (98%, 94%, 99%), then 3 (78%), 2 (66%), and worst 4 (52%): this is why a code made of 1, 3 and 5 works best.

## The lock box

- **Webcam + the network** (on the UNO Q, plain NumPy) read the digits.
- **Lock rules** decide whether the code is right (same rules as on the laptop; checked to give exactly the same answers on a recorded session of 93 events).
- **Ultrasonic sensor + DC motor** are the door: the motor swings the door, and the sensor checks after every move that the door really opened or closed (closed = 106 mm; open = nothing in view; pushed = 119 to 123 mm).
- **LED matrix** shows what is going on (the challenge digit, the digits read, a padlock, a cross, the lockout, "!" for tamper).
- **A web page** (on my laptop, served by the board) shows the camera, the door and the log. The Space bar on the laptop is the push-button.

---

## 1. Lock policy

**The code.** Three **different** digits, each from 1 to 5 (60 possible codes). A fist or an empty square (class 0) means "rest": it separates the digits and is never part of the code.

**Reading a digit.** The network gives six probabilities for every camera picture. A digit is accepted only when the last **8 pictures agree** (at least 75% name the same digit) and the average probability is at least 0.6. Then the hand must rest (a fist or nothing in the square for 5 pictures) before the next digit counts. So holding one number up for four seconds is **one** digit, not three.

**The live challenge.** After the button, the LED matrix shows a random digit with a dotted line under it. That digit must be shown **before** the code. A video or a recording of someone's earlier correct entry would only work 1 time in 3 (the challenge draws from 1, 3, 5) or 1 in 5.

**Time.** 10 seconds for each digit and 30 for a whole entry. Being too slow just ends the session: it is **not** a wrong try.

**Wrong tries.** A wrong code or a wrong challenge digit is a failed try. **Three failed tries in a row lock the box out for 30 seconds**; the next lockout is 60 s, then 120 s, and so on up to one hour. A correct code resets the count. The box never says *which* digit was wrong.

**When the code is right.** The door opens (checked by the sensor, with one retry before it reports a fault). After **10 seconds**, or when the button is pressed, the box locks again and the door closes (checked again).

**Tamper.** If the locked door is forced (it reads ajar or open, or something is held in front of the sensor), the page shows TAMPER, the matrix shows "!", any entry in progress is dropped, and **finger entry is blocked for 15 seconds**. It is written in the log and it is **not** counted as a wrong try. With "push back" on, the motor also tries once to shut the door.

**The secret.** The code is stored only as a **salted hash** (PBKDF2-SHA256, 200,000 rounds), never as digits. The log records that "digit number 2 of 3" was read, but **never which digit** it was, so the log file cannot give the code away.

**Why these choices.** Three different digits and a hash keep the code out of the files; the challenge defeats simple replay; the lockout, doubling each time, makes guessing slow (guessing all 60 codes would take about 4.8 hours on average and 13.4 hours at worst, computed for 20 seconds per try); and the tamper rule keeps a forced door from also being a way to get free tries.

**What I measured of this policy on the real box** (from the box's own log):

| Check | Result |
|---|---|
| Lockout after three failures | 30 s exactly (06:35:48 to 06:36:18) |
| Relock after an unlock | 10 s exactly, 3 times out of 3 |
| Door opens after the unlock | 1 to 2 s, 3 of 3 (open readings 408, 534, 563 mm) |
| Door closes again to | 106 mm, 3 of 3 |
| Button to unlocked | 10 to 12 s (digits about 3 s apart) |
| Locked and untouched | 6 min 11 s with no false alarm |
| Forcing the locked door | detected 3 of 3 (119, 119, 120 mm), finger entry blocked for 15 s |

**Owner, 10 honest tries:** [FILL: ___ of 10 opened the door; ___ wrong code; ___ wrong challenge digit; ___ too slow]

**Another person's hand, 10 tries:** [FILL: ___ of 10 opened the door]

---

## 2. Limitations

1. **The code space is small.** Three different digits from 1 to 5 are only 60 codes, and a code made only of 1, 3 and 5 (the digits the network reads best) has just 6 orders. The hash and the lockouts slow guessing down; they cannot make 60 codes strong. It is a classroom lock, not a security product.
2. **Reading fingers is the weakest part.** On new people the network got 71 to 74% of single pictures right, and 81% on a new session; digit 4 is read correctly only about half the time. The 8-picture rule and the three tries make the *code* much more reliable than one picture, but an honest owner can still be refused.
3. **It needs the same setup as the training pictures.** The camera is fixed over a taped square, in similar light. When the hand was shifted by about 19% of the picture the accuracy fell to 56 to 71% depending on the direction (training with stronger shifting and zooming raised that to 73 to 85%), and a lamp casting finger shadows made the network count the shadows as fingers.
4. **Little variety in the training data.** 2,400 pictures from two people, in two sessions: other skin tones, hand sizes, rings, sleeves and lighting were never seen.
5. **The motor does not hold the door.** The gearbox of the yellow TT motor is not self-locking, so a forced door can be opened; the box *detects* it, raises the alarm and can push the door shut again, but it cannot *prevent* it. A real lock needs a mechanical catch.
6. **The distance sensor can be fooled.** An object held in its beam at the closed distance (106 mm) while the door is pulled open would look closed. The sensor also cannot tell *how far* the door is open (fully open reads "no echo or far away"), and the closed band (96 to 116 mm) rests on a few measurements: a 1 cm push reads 119 to 123 mm, so the margin is only 3 to 7 mm.
7. **The control page is not protected.** Anyone on the same network can set a new code without knowing the old one, and the page sends the code to the board unencrypted. The maintenance buttons open the door without the code.
8. **It is slow.** The camera delivers about 12 pictures a second (not the 30 it claims), so each digit needs about 3 seconds and a code takes 10 to 12 seconds from the button to the unlock.
9. **One supply for everything.** The board, the webcam and the motor share one 5 V / 3 A supply; I have not stress-tested what happens in the worst case.

---

## 3. How the neural network works

The network takes a **64 × 64 colour picture** of the taped square (a grid of 64 × 64 pixels, three numbers each: red, green, blue) and gives back **six numbers**, one probability for each of 0, 1, 2, 3, 4, 5 fingers.

**Convolution: sliding a small pattern detector.** A filter is a tiny grid of numbers (for example 5 × 5). I put it on top of a patch of the picture, multiply each pixel by the filter's number above it, and add everything up: one number that says "how much does this patch look like my pattern?". Sliding the filter across the whole picture gives a new, picture-shaped grid of those numbers, a **feature map**. Each filter learns its own pattern during training (an edge, a corner, the side of a finger). The first stage has **16 filters of 5 × 5**.

**ReLU.** Every negative number is turned into zero. It keeps only the "yes, I see it" signals, and it is the bend that lets many simple layers do something that one straight line cannot (in Part 1, it is what lets two neurons make a V).

**Pooling: keep the strongest, shrink the picture.** Max-pooling looks at each 2 × 2 block of a feature map and keeps only the **largest** number. The map becomes half as wide and half as high (64 → 32), so there is less to compute, and the network stops caring about *exactly* where something is: a finger that moves by a pixel or two gives the same answer.

**Three stages, three sizes.** I repeat this three times, with different filter sizes: 16 filters of 5 × 5, then 32 filters of 3 × 3, then 64 filters of 3 × 3, each followed by ReLU and pooling (the picture shrinks 64 → 32 → 16 → 8). Early stages see edges; later stages see combinations of edges, like a fingertip or a gap between fingers.

**Concatenate.** I squeeze the output of each stage down to a 4 × 4 grid per filter (by averaging) and **join the three together** into one long list: 16 × 16 + 32 × 16 + 64 × 16 = **1,792 numbers**, a summary of the hand at three different scales.

**Deciding.** A final linear layer turns those 1,792 numbers into **6 scores**, and softmax turns the scores into probabilities that add up to 1. The biggest one is the answer. (During training 30% of the 1,792 numbers are randomly switched off, "dropout", so the network cannot lean on any single one.)

**Learning.** The network has **35,110 numbers** to learn (1,216 + 4,640 + 18,496 in the three filter stages, 10,758 in the last layer). At the start they are random and the answers are wrong. For each training picture I measure how wrong the answer is with **cross-entropy** (it is large when the network gives a low probability to the true class), and gradient descent (the Adam version) nudges every number a tiny step in the direction that makes it less wrong. It is the same idea as fitting the V in Part 1, with 35,110 numbers instead of two. The pictures are shifted, rotated, zoomed, flipped top to bottom and have their brightness and colours changed every time they are used (**augmentation**), so the network learns what a finger count looks like and not the exact pictures. I trained for 80 passes over the 2,400 pictures.

---

## 4. UNO Q vs computer

Both run **the same network, the same code and the same picture**: the benchmark button on the board and a script on the laptop (`compare/bench_numpy.py`) measure one step: cutting out the square and running the network, on the same made-up picture.

| | UNO Q | Laptop | The board is |
|---|---|---|---|
| Processor | aarch64 (Linux side of the UNO Q) | AMD64 | |
| One whole step | **27.9 ms** (36 steps a second) | 8.3 ms (120 steps a second) | 3.4 × slower |
| The network | 23.8 ms | 7.6 ms | 3.1 × slower |
| Cutting out the square | 3.9 ms | 0.72 ms | 5.4 × slower |
| Slowest 5% of the network steps | 45.5 ms (worst 61.9) | 9.5 ms (worst 11.9) | |
| Camera pictures a second, same MJPG webcam | about 12.5 when only the camera runs, about 10 with the network running | [FILL: laptop camera pictures a second, or delete this row] | |
| Code check (the hash), while the page keeps running | [FILL: ___ ms] | | |
| Camera and network while the whole lock runs | [FILL: ___ pictures/s and ___ steps/s] | | |

**What this means.**
- **Training only on the computer.** The laptop trains the network with PyTorch (minutes). The board has no PyTorch: it runs a plain-NumPy copy of the finished network, which gives the same answers (checked to about 1e-6, and on 16 test pictures to the last decimal).
- **The board is about 3 times slower, and it does not matter.** One step takes 28 ms, so the network could read 36 pictures a second. The **camera** (about 12 pictures a second) is the slow part: the lock needs 8 pictures that agree, which takes under a second.
- **What the board has that the laptop does not.** Its microcontroller reads the distance sensor every 60 ms and times the motor (it stops the motor by itself after 3 seconds at the longest, even if the Linux side freezes), and its pins drive the motor and the LED matrix. The laptop has the power to train; the board has the hardware to *be* the lock.
- **What I had to change for the board.** No PyTorch (the NumPy copy), a camera format that lets the webcam go faster (MJPG: 7.5 → about 12 pictures a second), and one 5 V supply shared by the board, the camera and the motor.

---

## Results at a glance

| | Result | Where it comes from |
|---|---|---|
| Fingers read correctly, new person | 71.4% and 73.9% | laptop, trained on one person, tested on the other |
| Fingers read correctly, new session | 81.3% | laptop |
| Lock rules identical to the laptop's | 93 of 93 events | recorded session replayed on the board's copy |
| Door closes to | 106 mm, 3 of 3 | the box's log |
| Quiet time with no false alarm | 6 min 11 s | the box's log |
| Forced door detected | 3 of 3 | the box's log |
| Network step, board vs laptop | 27.9 ms vs 8.3 ms | benchmark on both |

## Reflection

[FILL: answers to the reflection questions]

## GitHub

[FILL: link]. The repository has the laptop project (capture, training, the lock demo), the V-fit, the board apps (the lock box, the finger-counting test, the door controller, the sensor and motor tests), the trained network, and the explainer-movie script. The 2,400 training pictures are **not** in the repository (they are pictures of people's hands and are kept private; people are called A and B).
