# Finger Lock Box

The finger-counting lock, on the UNO Q. **Press the button** (the Space bar on your laptop), show the digit the LED matrix asks for, then **show your three-digit code with your fingers** under the webcam. A correct code opens the door with the motor, and it closes again after 10 seconds. It puts the pieces together: the finger-counting network on the board, the lock rules from the laptop project, the door controller (sensor and motor), and the LED matrix. Nothing is trained here: the network was trained on the computer.

## What it does

1. **Button** (Space bar on the page): starts a session. The LED matrix shows a digit with a dotted line under it: the **live challenge** (1 digit from 1, 3, 5 to begin with, chosen at random each time). Show that digit first: a recording of someone's hand would only work 1 time in 3.
2. **The code:** show your three different digits one at a time. Hold each number up until the progress dots move on, then rest your hand (a fist, or nothing in the square) before the next. A digit counts when the network has said the same thing, confidently, for 8 pictures in a row.
3. **A correct code unlocks:** the door is asked to open (the motor, with the direction and times in `door_config.json`), and the distance sensor checks that it really opened. After **10 seconds**, or when you press the button, it locks again and the door closes (checked again).
4. **A wrong code** is denied (a cross on the matrix). **Three wrong tries in a row** lock it out for 30 seconds, then 60, 120, and so on up to an hour. A correct code resets the count. **Being too slow** (10 seconds for a digit, 30 for the whole entry) is not counted as a wrong try.
5. **Tamper:** if the locked door is forced (it reads ajar, open, or something is held in front of the sensor), the page says TAMPER, any entry in progress is dropped, and **finger entry is blocked for 15 seconds**. It is written in the log. **It does not count as a wrong try.** With "Push back when forced" on, the motor also tries once to shut the door.
6. **Faults:** a door that does not open or close (after one retry), or a distance sensor that goes quiet, shows an "X" on the matrix and says so on the page.

The page also has a **Measurements** panel (a tally of tries, the times, the speeds, a quiet-time timer): see below. The LED matrix shows what the laptop demo showed: digits with progress dots, the closed and open padlock, a tick, a cross, the lockout bars, plus an "!" for tamper, an "X" for a fault, and an arrow while the motor moves.

## The secret, and the log

The code is stored only as a **salted hash** (PBKDF2, 200,000 rounds) in `python/lock_config.json`, never as digits. **The log never records which digits were shown**, only that "digit number 2 of 3" was read, so `lockbox_log.csv` cannot give the code away. The live challenge digit is not written to the log either.

## Wiring

| Part | Connects to |
|---|---|
| Webcam | the hub (the same webcam as for the finger-count app, fixed and aimed at your tape square) |
| HC-SR04 GND, TRIG, ECHO | **GND, D7, D8** |
| HC-SR04 VCC | **3V3** (the sensor works on 3.3 V, so the echo needs no divider) |
| Cytron Maker Drive M1A, M1B | **D5, D6** |
| Maker Drive GND | **GND** (shared with the UNO Q) |
| The motor | the motor-1 terminals of the Maker Drive |
| Maker Drive power | the UNO Q's **5V** pin |

The board now runs the webcam, the network, the sensor and the motor together on one 5 V / 3 A supply. Watch for resets, a dropped webcam or a dropped page when the motor starts. If you see them, lower the motor speed in `door_config.json` or add a capacitor (470 microfarad or more, 10 V or more, + leg to 5V). **Safety:** hold the door the first time and keep fingers out of its swing. **Esc** stops the motor at any time; the sketch ends every motor move by itself after at most 3 seconds.

## Run it

Copy this folder into Arduino App Lab as an app and press Run. Then open **`http://<the board's address>:7000`** in the browser on your laptop.

## First run, in order

1. **The camera.** The "camera" chip should turn green and name the webcam (MJPG at 640 x 480). Open "Camera and square", press "Find the tape square", check the green square sits just inside your tape, adjust it with the arrow keys, and **Save the square**. The camera must be fixed, as when the training pictures were taken.
2. **Set a code** (three different digits from 1 to 5) in "The code". The live challenge starts as 1 digit from 1, 3, 5.
3. **Wrong code:** press the button, show the challenge digit, then a wrong code. It should be denied (a cross). Do it three times: it locks out for 30 seconds.
4. **Right code:** after the lockout, the right code. The door should open, and close again after 10 seconds. Time how long it takes from the button to the door opening.
5. **Tamper:** with the door locked and closed, push it open by hand about 1 cm. The page should say TAMPER for 15 seconds, the button should be ignored meanwhile, and the log should say it does not count as a wrong try.
6. **Leave it locked for 5 minutes:** the log must show no false tamper.
7. **Different hands:** let someone else try, with the right code and the wrong one.
8. **Power:** watch for resets or dropouts every time the door moves with the camera running (the Measurements panel below counts them).

## The Measurements panel

The page counts and times everything, so nothing has to be counted by hand:

- **Tries:** opened the door, wrong code, wrong challenge digit, and too slow (not a wrong try). **Reset the tally** starts a new count.
- **Button to unlocked** and **unlocked to the door open** (the median of the successful tries).
- **Code check:** how long the hash check took, last and slowest.
- **Camera pictures a second / network steps a second.**
- **The app has been running for:** if it goes back to 0:00, the app restarted.
- **Locked with no alarm for:** counts up while the door is locked, and starts again after any alarm or fault.
- **Download the whole log (CSV)** gives the board's `lockbox_log.csv` (the list on the page keeps the last 60 events).

## Which code to choose

The network reads **1, 3 and 5** best (from the laptop tests on new sessions: about 73% per try for any order of 1, 3, 5, and 98% within three tries; a code with 2 and 4 was much worse: about 27% per try). **But a code made of 1, 3 and 5 has only 6 possible orders**, so it is weak against someone who knows the digits and guesses. Three different digits from 1 to 5 are 60 codes in all. This is a trade-off between reliability for the owner and strength against guessing. Those percentages were measured on the laptop, not on the board.

## Files

```
app.yaml  sketch/sketch.ino  sketch/sketch.yaml      the App Lab app: the microcontroller side (sensor, motor, LED matrix pictures)
python/main.py                                         connects everything to the board and the page (WebUI brick, port 7000)
python/lockbox.py                                      joins the lock rules, the door and the LED matrix (unlock, relock, tamper, the log)
python/lock.py                                         the lock rules, from the finger-lock project (one import changed, one method added)
python/door.py                                         the door: bands, checks after every move, tamper (from the door controller)
python/board_vision.py  infer_numpy.py  model/         the camera, the square and the network (from the finger-count app)
python/matrix.py                                       the LED pictures (from the finger-lock project)
assets/index.html  app.js  style.css  libs/            the page (socket.io is included, so it needs no internet)
tests/run_all.py                                       runs every test the computer can run
tests/test_sketch.cpp + tests/stubs/                   the sketch against a simulated sensor, motor and matrix (needs g++)
tests/test_lock_rules.py + golden_lock.json            the lock rules against a recorded session of the ORIGINAL rules
tests/test_vision_core.py + golden.json                the network and camera code against the ORIGINAL code, on 16 pictures
tests/test_lockbox.py                                  the lock, the door and the matrix together, against a simulated door
tests/test_main.py                                     the whole app through main.py (fake camera and board, simulated door)
tests/test_page.js                                     the page in a simulated browser (needs node and: npm install jsdom)
tests/make_golden*.py                                  remake the golden files from the finger-lock project (only if you change the rules or the network)
```

Files the app makes while it runs (all kept out of git): `lock_config.json` (the hash and the settings), `lockbox_log.csv`, `door_config.json`, `door_log.csv`, `roi.json`, `camera.json`.

## Results on the real box

| | Result |
|---|---|
| Camera on the board | about 12 pictures a second (MJPG) |
| The lock rules on the board vs the original rules | identical on a recorded session of 93 events |
| Lockout, relock, door | 30 s, 10 s, closes to 106 mm, 3 of 3 |
| Locked and untouched | 6 min 11 s with no false alarm |
| Forced door | detected 3 of 3 times |

## Tests

`python tests/run_all.py` runs the `app.yaml` check and **313 checks** in six groups: the sketch (44), the lock rules (17), the network and camera code (42), the coordinator (96), the whole app through `main.py` (40) and the page (74).

- **The lock rules are the original ones:** a long recorded session (583 calls, 93 events: success, both ways of being denied, lockouts of 30 and then 60 seconds, a timeout, relocking, ignored presses) gives exactly the same events in the board's copy as in the original. (The session uses a made-up test code.)
- **The network and the picture steps are the original ones:** on 16 made-up pictures the same digits and the same probabilities, to the last decimal.
- **The whole chain is tested against a simulated door**, from the button to the door closing again, including tamper, faults, the button pressed while the door moves, and a door already open or closed. The log is checked never to contain the digits.

## Limits

- Three different digits from 1 to 5 are only 60 codes. The hash keeps the code from being read off the page or out of the repository, not from someone who has the file.
- **Anyone who can reach the page can set a new code without knowing the old one, and the page sends the code to the board without encryption over the local network.** The Maintenance buttons open and close the door without the code.
- The motor does not hold the door shut (the gearbox is not self-locking): a forced door is detected and reported (and can be pushed back), not prevented. A closed door whose sensor is blocked or fooled can look fine.
- The network read digits correctly 71 to 84% of the time on new people and new sessions on the laptop. The finger reading is the weakest part of the lock.
