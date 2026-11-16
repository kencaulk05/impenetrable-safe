# Finger-counting lock

Hold up fingers under a webcam, and a neural network, written in PyTorch, counts them; three different numbers in the right order open the box. Step 1 is **collecting the pictures** (`capture.py`), step 2 is **training the network** (`train.py`), step 3 is **the lock** on the laptop (`lock_demo.py`). The same network and lock rules run on the UNO Q in `board-lock-box`.

**Six classes: 0, 1, 2, 3, 4 and 5 fingers.** Class 0 is an empty square or a closed fist, so the network can say "nothing here", and the lock only uses 1 to 5.

## Set it up (once)

1. **Fix the camera.** Put the webcam on a stand, looking straight down at the desk, at a distance that never changes (the stand should not be able to slide). Use the same webcam, the same stand and the same lighting as for the lock on the UNO Q.
2. **Mark a square on the desk** with tape or a thick marker line, about a hand and a half wide, so a spread hand fits inside with room to move. Any colour that stands out from the desk works with the automatic finder: red (the default), blue, green or yellow (`--tape blue`). Only the inside of the square is ever used, so every picture has the same size and scale and the network never has to cope with zooming.

   **The tape is only a guide for you.** The square the pictures are cut from is stored in the software (`roi.json`, in pixel coordinates), and you can set it by dragging a box with the mouse, with no tape at all. The tape is still worth having: with your hand under the camera you cannot see an invisible box, and the finished lock will have no screen to show it. If you move the stand, set the square again.
3. **Keep the desk plain** and the light steady (no strong shadows moving across the square, no window light that changes as clouds pass).

## Collect

```
pip install -r requirements.txt
python capture.py --person A --tape blue      # tell it the colour of your tape (default red)
```

A window shows the camera and a small second window shows what the network will actually see.

- **Press `r`** to find the taped square automatically. If it picks the wrong thing (a blue sleeve or jeans can look like blue tape), or you have no tape, **drag a box** with the mouse **just inside** the tape line, so the tape itself is not in the pictures. The square is remembered next time (for the same camera size). After that, **`+` and `-` make the square bigger or smaller and `w a s d` move it** (12 pixels at a time), so you do not have to drag again.
- **How big?** Hold a fully spread hand in the square, with the wrist outside it: the fingertips and palm should be inside with a margin all around. The saved pictures are always resized to the same size (128 x 128), so a bigger square costs nothing, but you must not change the square or move the camera once you start collecting.
- **Press `e` only when the square is EMPTY.** The tool then warns you if a picture labelled 1 to 5 looks empty (a hand that was not really there).
- **Press 0 to 5** to save one picture of that many fingers. **Press `b`** for burst mode: a digit then saves 20 pictures while you move your hand a little, which is the quickest way to get variety. **`u`** undoes the last picture, **`q`** quits.
- **The person is a letter** (A for you, B, C ... for the others), never a name: the pictures show hands, and the repo is public.

**What to collect.** Around 100 pictures of each number from each person, so with three people about 300 per class. What matters most is **variety** and **several different people**:

- Show each number the way you naturally would, and also vary it: slightly different finger positions, left and right hands, the hand moved around the square, tilted, a little further up or down, slightly spread or relaxed.
- Hold the hand the same general way each time (fingers pointing away from you, back of the hand to the camera) unless you also want the network to learn other views.
- Class 0: the empty square, and a closed fist, in different places and tilts.
- **Ask other people** (family, classmates) to give you a few hundred pictures each. A network trained on one person's hands usually does worse on someone else's.
- 3 is usually the hardest number (it is easy to confuse with 2 and 4): take extra of it, in different finger combinations.
- **Light the board from above, close to the camera, not from one side.** A lamp at the side casts a dark shadow of each finger on the white board, and the first network learned to count the shadow as an extra finger: single fingers with a clear shadow were called "2" with about 80% confidence. A lamp right next to or above the camera puts the shadows behind the hand.
- **Decide how the thumb counts, and keep it the same.** The thumb caused most of the network's confusions. Pictures labelled 1 that were thumbs-up were called 0 or 2, and 4 and 5 were swapped between sessions and people, because the thumb was sometimes out and sometimes folded. A simple rule that works: 1 to 4 are shown with the fingers and the thumb folded, and 5 is the open hand with the thumb out. Do not use a thumbs-up for 1.
- **Keep the fingers slightly apart.** Two fingers pressed together look like one thick finger from above, and the network calls them 1.
- **Hold still for a moment before pressing a key**, and move slowly during a burst: blurred pictures are hard for everyone.
- **Take a second session at a different time of day** (and include someone with a lighter skin tone if you can). Pictures taken with more than an hour between them count as a different session, which lets `train.py` measure what happens in different light.

Then check what you have:

```
python dataset_report.py data/raw
```

It shows the counts per class and per person, and tells you what to collect next, and warns about too few people, unbalanced classes, blurry, dark or bright pictures, and duplicates.

## Train the network

```
pip install -r requirements.txt
python train.py --data data/raw                 # fingers pointing sideways (the default mirror is top-to-bottom); 150 epochs
python train.py --data data/raw --flip horizontal    # if your fingers point up instead
python train.py --data data/raw --gray           # grey pictures instead of colour
python train.py --data data/raw --shift 0.18 --zoom 0.15    # a network that is less fussy about where in the square the hand is
python train.py --data data/raw --final-only    # skip the tests: about a quarter of the time, for quick retraining
```

The network (`fingerlock/model.py`) has three convolution stages of different sizes (16, 32 and 64 filters), each followed by ReLU and 2 x 2 max pooling, so the 64 x 64 picture shrinks to 32, 16 and 8 pixels while the feature maps grow. The output of all three stages is squeezed to a 4 x 4 grid, joined (1,792 numbers), and one linear layer turns them into six scores, one per class. It has 35,110 weights and learns with cross-entropy loss (softmax turns the six scores into probabilities, and the loss is -ln of the probability given to the true class). Pictures are made more varied while training by rotating, shifting and zooming them a little, mirroring them, changing the brightness, contrast and colour, and adding a touch of noise. The mirror must be *across* the direction the fingers point (it turns a left hand into a right hand without turning the fingers around), which is why `--flip` exists.

**What it measures** (written to `results/summary.md`). In each test the network is trained **without any picture of what it is tested on**, always for the full number of epochs, so nothing is chosen using the test pictures:

- **A new person:** trained on everyone else, tested on that person. Needs at least two people.
- **A new session:** trained on the earlier sessions, tested on the last one (a different time and light). Needs pictures taken more than an hour apart (`--session-gap` changes the hour). For a lock that will be used by the people who trained it, this is the number that matters most.
- **The final network** is then trained on every picture. Its accuracy on its own training pictures is printed too, but it is **not a test**: it only shows how well the network fits what it was shown.

`confusion_*.png` shows which numbers get mixed up (rows: the truth, columns: what the network said), `curves.png` the loss and accuracy while training, and `mistakes_new_session.png` some of the pictures it got wrong. A burst saves 20 almost identical pictures, which is why pictures are never split frame by frame between training and testing: that would test the network on near-copies of what it learned from.

It writes `models/finger_cnn.pt` (PyTorch) and `models/finger_cnn.npz` (the same network in plain NumPy, which is what the UNO Q runs; `fingerlock/infer_numpy.py` matches PyTorch to about 1e-6).

## Try the network live

```
python predict_live.py --model models/finger_cnn.npz --data data/raw --camera 3
```

It reads the square from `data/raw/roi.json` (so it is exactly the square the network was trained on: do not move the camera or the stand), cuts it out the way the capture tool did, and shows the network's answer on the live picture: six probability bars, the time per picture, and **"sure: N"** only when the answer is steady (the last 8 pictures average above 60% and at least 75% of them agree). **`s` saves the current picture** into `live_saved/`, which is the best way to keep the cases the network gets wrong and add them to the training data. It uses the NumPy copy of the network, the same code that runs on the UNO Q.

## Results (two people, two sessions)

2,400 pictures: two people, 200 of each number from each, in two sessions about ten hours apart (a new session starts after a gap of more than an hour with no pictures taken). 64 x 64 colour pictures, 80 epochs (with twice the pictures, 80 epochs is the same number of learning steps as 150 epochs on half of them). Every test trains without any picture of what it is tested on:

| test | accuracy | per class (0 to 5) |
|---|---|---|
| **a new person**: trained without A, tested on A | **73.9%** | 96% 93% 78% 48% 74% 54% |
| **a new person**: trained without B, tested on B | **71.4%** | 100% 66% 70% 66% 52% 75% |
| **a new session**: trained on the session 1 pictures, tested on the session 2 ones | **81.3%** (A 82.8%, B 79.8%) | 98% 94% 66% 78% 52% 99% |
| the final network on its own training pictures (**not a test**) | 96.5% | |

Each test is one training run, so differences of a few points are noise. With about 1,200 pictures and one extra session, the new-person accuracy rose from about 61% to about 72%, so **more varied pictures helped more than any change to the network.** In earlier experiments on the first session alone (an older version of the tests), grey instead of colour pictures, larger pictures (96 x 96) and weaker augmentation made no clear difference.

**What the network gets wrong.** 0, 1 and 5 are reliable (94 to 99% in the new-session test); 2 and 4 are the weak ones. The confusions are almost all about **the thumb and fingers that touch**:

- Pictures labelled 1 that show a **thumbs-up** (or a fist with the thumb at the side) are called 2 or 0 with up to 100% confidence: in the 16 mistakes of the new-session test that are drawn in `mistakes_new_session.png`, 9 are thumb poses labelled 1.
- **4 and 5 are swapped**: in the new-session test 90 of 200 fours were called 5, and in the new-person test on A, 90 of 200 fives were called 4. Whether the thumb is out or folded was not the same in every session and for every person.
- 2 is often called 3 (fingers that touch look like one thick finger from above).

These are problems of the **labels and poses** more than of the network, which is why "What to collect" sets one clear pose per number and `review_labels.py` finds the unclear pictures.

## Does the position of the hand in the square matter?

Yes. In the training pictures the hand sits in a narrow band: for 80% of the pictures of 1 to 5 the vertical middle of the hand is between y = 50 and 77 (the square is 128 tall), the fingertips are at x = 94 to 121, and the hand touches the top or right edge in only 0 to 4% of the pictures. To measure what that does, a network was trained on the session 1 pictures only and tested on the session 2 ones, with the session 2 pictures shifted by hand (6 pixels of 64 is about 10% of the square; one run each, so a few points are noise):

| the hand is moved | usual augmentation (shift up to 8%) | stronger augmentation (`--shift 0.18 --zoom 0.15`) |
|---|---|---|
| not moved | 81.3% | **84.1%** |
| up by 12 px (about 19%) | 71% | 80% |
| down by 12 px | 67% | 81% |
| left by 12 px | 60% | 85% |
| right by 12 px (fingertips leave the square) | 56% | 73% |

So with the usual augmentation a hand pushed 10 to 20% off its normal place loses 10 to 25 points, more when it moves sideways, and the stronger shift and zoom augmentation removes most of that loss without costing accuracy for a hand in its normal place. It is a cheap fix because it needs no new pictures; `train.py` now takes `--shift` and `--zoom` (the defaults are unchanged). The natural variation inside the session 2 pictures points the same way: hands whose fingertips reached farther right were recognised more often (73%, 79% and 81% for the three thirds), and hands held high in the square did worst with the usual augmentation (66%, against 83% and 84%), but this is mixed up with which numbers were being shown.

**For the lock:** mark the spot where the hand should go with tape (hand roughly in the middle, fingertips about three quarters of the way to the right edge), train with `--shift 0.18 --zoom 0.15`, and keep the fingertips inside the square.

## Clean up the labels

```
python train.py --data data/raw                  # saves results/holdout_predictions.npz
python review_labels.py --model models/finger_cnn.npz --data data/raw
```

It lists the pictures that a network which **never saw them** confidently calls a different number (at least 80% sure), and makes contact sheets in `review/` (each picture says `label > what the network said, confidence`). Look at them: a thumbs-up labelled 1 or a hand half-way between two numbers is better out; a picture that really is what its label says is a hard case worth keeping. `--move` moves the flagged pictures into `data/raw/_review/` (nothing is deleted, and you can move them back), then retrain. It deliberately uses the predictions of the new-person tests: the final network was trained on every picture and has partly memorized them, so on its own it flags only about 12 of 2,400.

## The lock

```
python set_code.py                      # choose the code (typed without showing it); --challenge 1 turns on the extra feature below
python set_code.py --challenge 1 --challenge-pool 135    # the challenge only asks for the digits the network reads best
python lock_demo.py --model models/finger_cnn.npz --data data/raw --camera 3
python lock_demo.py --headless-demo 153 # no camera: a scripted run of the owner and then an intruder
python lock_analysis.py --results results/results.json --challenge 1    # how good is each code, and how long does guessing take?
```

SPACE is the button. After pressing it, show three **different** digits from 1 to 5 one after another under the camera. The window shows the camera with the square and a dashed box where hands usually were when the network learned (keep the hand and the fingertips in it), and a panel with the status, the LED matrix drawn big, what the network sees, and a log in words. The lock rules are in `fingerlock/lock.py` (no camera or motor in it, so every rule is tested) and the LED-matrix pictures in `fingerlock/matrix.py`.

**The policy.** Walk to the safe, press the button, the LEDs light, show the digits. A digit is read only when the network's answer has been the same, with at least 60% average probability and at least 75% of the frames agreeing, for 8 frames in a row (so a blur or a hand on its way in does not count), and the hand has gone to rest (a fist or an empty square, class 0) since the last digit (so holding up one number is one digit, not three). Class 0 is never a digit. After the third digit the box unlocks if the code is right and the entry is dropped if not; the box closes again by itself after 10 seconds, or at once when the button is pressed. Three wrong entries in a row cause a lockout of 30 seconds, and each following lockout is twice as long (up to an hour); a right code clears the count. An entry that is too slow (10 seconds for a digit, 30 for all of it) is dropped without counting as a wrong try. The events the lock reports say what was *read*, never whether it was *right*, so the LEDs cannot give the code away. Every number above is a setting (`Policy` in `lock.py`).

**The secret.** The code is stored only as a salted PBKDF2 hash (`lock_config.json`, kept out of git), never as the digits. This keeps the code from being read off the screen or out of the repository by accident, but three different digits from 1 to 5 are only **60 codes**, so anyone who can read the file can try all 60 in a blink.

**The extra feature: a live challenge.** With `--challenge 1` the matrix first shows a random digit, which you must show before your code, so a *recording* of someone entering the code is rejected unless it happens to contain the digit asked for this time (1 time in 5; with `--challenge 2`, 1 in 25). It does not stop someone who watched you and has a photo of each digit, and it does not hide your code from someone looking over your shoulder.

**The challenge pool.** `--challenge-pool 135` makes the challenge ask only for 1, 3 or 5, the digits the network reads best, so the demo is not derailed by a random 4 that is hard to read. The price: a recording then works 1 time in 3 instead of 1 in 5.

**Choosing the code.** `lock_analysis.py` uses the confusion matrix measured in the new-session test (what the network said when the hand showed each number) to score all 60 codes:

| | the owner, one attempt | the owner, within 3 attempts | a random intruder, one attempt |
|---|---|---|---|
| any order of **1, 3 and 5** (the best) | 73% | 98% | 2.6% |
| 3-4-2 and its orders (among the worst) | 27% | 61% | 0.5% |
| a perfect network (for comparison) | 100% | 100% | 1.7% |

The network reads 1 (94%), 5 (99%) and 3 (78%) best and 4 (52%) and 2 (66%) worst, so a code from 1, 3 and 5 is the one that works for its owner. The best codes are also slightly *easier* for a random intruder (2.6% against 1.7%), because wrong digits are read as the code's digits: 4 is read as 5 in 45% of cases and 2 as 3 in 30%. Guessing all 60 codes (20 seconds a try, a guesser who never repeats a code) takes about 15 minutes on average with a constant 30-second lockout, and about **4.8 hours** on average (13 hours at worst) with lockouts that double each time. These figures assume each digit is read independently, that a wrong reading is not corrected by holding longer, and a random guesser; the matrix comes from two people in one setup.

**Limits of the lock:**

1. **Only 60 codes**, and the hash cannot protect them: whoever has the config file has the code. Lockouts slow down guessing at the camera, nothing more.
2. **The network makes mistakes.** Even the best code is read right on only 73% of single attempts (98% within three), and the digits 2 and 4 are unreliable.
3. **Two people, one camera, one setup.** The numbers come from two people with similar skin tones; a different hand, a different light or a moved camera or box can be much worse, and the network is tied to the exact square it was trained on.
4. **Photos and recordings.** A photo of a hand showing each digit may fool the camera, and the live challenge only makes a recording work 1 time in 5 (1 in 25 with two digits).
5. **Shoulder surfing:** anyone who sees your fingers learns the code. The challenge does not hide it.
6. **The box is only as strong as its door and walls.** The motor does not hold the door shut; on the UNO Q a distance sensor detects a forced door (see `board-lock-box`).
7. **Frame rate:** the digit must be held for 8 frames; on a slower camera or on the UNO Q that takes longer than on the laptop.

## Try it without a webcam

`python capture.py --person A --simulate` uses a made-up camera that draws crude hands, and `python capture.py --person A --headless-demo --out demo` saves 3 pictures of each class with no window. `python make_synthetic_dataset.py data/synth` writes a made-up dataset in the capture tool's format, and `python train.py --data data/synth --flip horizontal` trains on it (the made-up hands point up). The made-up hands are only for testing the software: the accuracy says nothing about real hands.

## Files

```
capture.py               the window application
dataset_report.py        counts, balance, quality, duplicates
fingerlock/capture_lib.py  the square, cropping, finding the taped square, quality checks, the dataset on disk, burst capture
fingerlock/session.py      the keys and the state of the tool (no window in it, so it can be tested)
fingerlock/synth_hand.py   crude made-up hands and a made-up camera, for tests only
train.py                   trains and tests the network (new-person tests), writes models/ and results/
fingerlock/model.py        the three-stage CNN
fingerlock/augment.py      rotate, shift, zoom, mirror, brightness, colour
fingerlock/data.py         loading the pictures, and splitting them in whole groups (no leaking between bursts)
fingerlock/infer_numpy.py  the trained network in plain NumPy, for the UNO Q
review_labels.py           finds pictures whose label may be wrong or unclear
fingerlock/review.py       the logic of that: flagging, moving, contact sheets
predict_live.py            the live webcam demo of the trained network
fingerlock/predict.py      the same pre-processing as training for a live frame, and the steadying of the answer
make_synthetic_dataset.py  a made-up dataset in the capture tool's format, to try the training without a webcam
tests/test_capture.py      61 checks, no camera needed
tests/test_train.py        51 checks: loading, sessions, the tests' protocol, augmentation, the network, cross-entropy, NumPy against PyTorch, the whole command
tests/test_predict.py      20 checks: live pre-processing identical to training, steadying, the live demo, finding unclear labels
fingerlock/lock.py         the lock rules (digit reading, entry, lockouts, the live challenge, the hashed secret)
fingerlock/matrix.py       the LED-matrix pictures (digits, padlocks, tick, cross) and how to draw them
set_code.py                chooses the code and writes lock_config.json (a salted hash)
lock_demo.py               the lock on the computer: webcam, network, rules, matrix drawn on screen
lock_analysis.py           scores all 60 codes with the measured confusion matrix, and the time to guess
tests/test_lock.py         78 checks: the rules, the challenge and replay, lockouts, the matrix pictures, the analysis against a simulation, the demo window
```

## Limits

- The results above are from **two people** (similar skin tones, one camera, one setup) in two sessions. A new person with a different skin tone, hand size or pose can be worse.
- The camera index and size depend on the computer: use `--camera`, `--width` and `--height`; the tool prints what resolution the camera accepted, and whether it let autofocus be switched off.
- The tape finder depends on colour, so it can fail in odd lighting: drag a box instead.
