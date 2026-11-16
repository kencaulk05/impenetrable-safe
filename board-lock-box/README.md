# Finger Lock Box (version 2: adds a Measurements panel)

The finger-counting lock, on the UNO Q. **Press the button** (the Space bar on your laptop), show the digit the LED matrix asks for, then **show your three-digit code with your fingers** under the webcam. A correct code opens the door with the motor, and it closes again after 10 seconds. This puts the pieces built so far together: the finger-counting network on the board, your lock rules from the laptop, the door controller (sensor and motor), and the LED matrix. Nothing is trained here: the network was trained on the computer.

## What it does

1. **Button** (Space bar on the page): starts a session. The LED matrix shows a digit with a dotted line under it: the **live challenge** (1 digit from 1, 3, 5 to begin with, chosen at random each time). Show that digit first: a recording of someone's hand would only work 1 time in 3.
2. **The code:** show your three different digits one at a time. Hold each number up until the progress dots move on, then rest your hand (a fist, or nothing in the square) before the next. A digit counts when the network has said the same thing, confidently, for 8 pictures in a row.
3. **A correct code unlocks:** the door is asked to open (the motor, the way that worked on your door), and the distance sensor checks that it really opened. After **10 seconds**, or when you press the button, it locks again and the door closes (checked again).
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
| HC-SR04 VCC | **3V3** (your sensor works on 3.3 V, so the echo needs no divider) |
| Cytron Maker Drive M1A, M1B | **D5, D6** |
| Maker Drive GND | **GND** (shared with the UNO Q) |
| The motor | the motor-1 terminals of the Maker Drive |
| Maker Drive power | the UNO Q's **5V** pin (as before) |

The board now runs the webcam, the network, the sensor and the motor together on one 5 V / 3 A supply. Watch for resets, a dropped webcam or a dropped page when the motor starts. If you see them, lower the motor speed in `door_config.json` or add a capacitor (470 microfarad or more, 10 V or more, + leg to 5V) as in the earlier notes. **Safety:** hold the door the first time and keep fingers out of its swing. **Esc** stops the motor at any time; the sketch ends every motor move by itself after at most 3 seconds.

## Run it

Copy this folder into Arduino App Lab as an app and press Run. Then open **`http://<the board's address>:7000`** in the browser on your laptop.

## First run, in order

1. **The camera.** The "camera" chip should turn green and name the webcam (MJPG at 640 x 480). Open "Camera and square", press "Find the tape square", check the green square sits just inside your tape, adjust it with the arrow keys, and **Save the square**. The camera must be fixed, as when the training pictures were taken.
2. **Set a code** (three different digits from 1 to 5) in "The code". The live challenge starts as 1 digit from 1, 3, 5.
3. **Wrong code:** press the button, show the challenge digit, then a wrong code. It should be denied (a cross). Do it three times: it locks out for 30 seconds.
4. **Right code:** after the lockout, the right code. The door should open, and close again after 10 seconds. Time how long it takes from the button to the door opening.
5. **Tamper:** with the door locked and closed, push it open by hand about 1 cm. The page should say TAMPER for 15 seconds, the button should be ignored meanwhile, and the log should say it does not count as a wrong try.
6. **Leave it locked for 5 minutes:** the log must show no false tamper.
7. **Different hands** (midterm rubric item 9): let someone else try, with the right code and the wrong one.
8. **Power:** watch for resets or dropouts every time the door moves with the camera running (the Measurements panel below counts them).

## Measurements for the report (read them off the page)

The **Measurements** panel of the page counts and times everything, so nothing has to be counted by hand or worked out from a file. Do it in this order:

1. **Owner, 10 tries.** Press **Reset the tally**. Then 10 times: press the button, show the challenge digit, show your code; after the door opens, let it close again by itself (about 10 seconds) or press the button. If a lockout starts, wait it out. Read **tries** and **opened the door** (for example 8 of 10), and **wrong code** / **wrong challenge digit** (they say where the misses were). **Too slow** is counted separately: it is not a wrong try.
2. **Another person, 10 tries.** Press **Reset the tally** again, tell them the right code, and repeat. That is your "different people's hands" number (rubric item 9).
3. **Time from the button to the door opening:** the panel shows **button to unlocked** (the median of the successful tries) and **unlocked to the door open**. Add them for the whole wait.
4. **Does the page pause when the third digit is read?** The panel shows **code check**: how long the hash check took, and the slowest. That is how long the page may pause. Over about 0.3 seconds you can see it as a stutter in the camera picture (also check your screen recordings at the moment of the unlock).
5. **Camera pictures per second with everything running:** the panel shows **camera pictures a second / network steps a second**. Read it three times: locked and idle, while a hand is showing digits, and while the door is moving.
6. **Did anything reset when the motor ran?** Watch **the app has been running for**: it must keep counting. If it goes back to 0:00 the app restarted (note when). Also watch the camera chip and **door or sensor faults** (it should stay 0), and the App Lab console.
7. **Five clean minutes locked:** with the door closed and locked, leave it alone. **Locked with no alarm for** counts up and starts again after any alarm or fault. When it reaches 5:00 with **tamper alarms** still 0, you have a clean five minutes.
8. **The log:** press **Download the whole log (CSV)**. It comes from the board's `lockbox_log.csv`, with everything since the app first ran (the list on the page only keeps the last 60).

Then send me the readings (or just the CSV and a note of the numbers from steps 1, 2, 4, 5 and 7):

| | |
|---|---|
| Owner: tries / opened the door / wrong code / wrong challenge / too slow | ___ / ___ / ___ / ___ / ___ |
| Another person: tries / opened the door / wrong code / wrong challenge / too slow | ___ / ___ / ___ / ___ / ___ |
| Button to unlocked, and unlocked to the door open | ___ s and ___ s |
| Code check: last and slowest | ___ ms and ___ ms |
| Camera pictures / network steps a second: idle, showing digits, door moving | ___ , ___ , ___ |
| Did the app running time ever go back to 0:00? Any camera or sensor fault? | ___ |
| Five minutes locked without an alarm? | ___ |
| The whole log (CSV) | attach it |

## Which code to choose

The network reads **1, 3 and 5** best (from the laptop tests on new sessions: about 73% per try for any order of 1, 3, 5, and 98% within three tries; a code with 2 and 4 was much worse: about 27% per try). **But a code made of 1, 3 and 5 has only 6 possible orders**, so it is weak against someone who knows the digits and guesses. Three different digits from 1 to 5 are 60 codes in all. This is a trade-off between reliability for you and strength against guessing. Those percentages were measured on the laptop, not on the board.

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

## What was tested, and what was not

`python tests/run_all.py` runs the `app.yaml` check and **313 checks** in six groups: the sketch (44), the lock rules (17), the network and camera code (42), the coordinator (96), the whole app through `main.py` (40) and the page (74).

- **The lock rules are the original ones:** a long recorded session (583 calls, 93 events: success, both ways of being denied, lockouts of 30 and then 60 seconds, a timeout, relocking, ignored presses) gives exactly the same events in the board's copy as in the original. (The session uses a made-up test code.)
- **The network and the picture steps are the original ones:** on 16 made-up pictures the same digits and the same probabilities, to the last decimal.
- **The whole chain is tested against a simulated door**, from the button to the door closing again, including tamper, faults, the button pressed while the door moves, and a door already open or closed. The log is checked never to contain the digits.

**None of it has run on the real board, with the real webcam and motor together, or in a real browser.** In particular:

- The LED matrix pictures are sent to the board as two numbers per call (a new use of the call that was proven with small numbers); the sketch has not been compiled with Arduino's own tools.
- **The hash check** (200,000 rounds) takes a moment on a computer and probably longer on the board, and it runs each time a code is completed: the page may pause briefly. I do not know for how long.
- Running the webcam, the network, the sensor and the motor on the same 5 V supply is untested (the motor and the camera were each tested alone).

**Limits to know about** (they are honest limits, not bugs):

- Three different digits from 1 to 5 are only 60 codes. The hash keeps the code from being read off the page or out of the repository, not from someone who has the file.
- **Anyone who can reach the page can set a new code without knowing the old one, and the page sends the code to the board without encryption over your local network.** The Maintenance buttons open and close the door without the code.
- The motor does not hold the door shut (the gearbox is not self-locking): a forced door is detected and reported (and can be pushed back), not prevented. A closed door whose sensor is blocked or fooled can look fine.
- The network read digits correctly about 71 to 84% of the time on new people and new sessions on the laptop. The finger reading is the weakest part of the lock.
