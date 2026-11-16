# Door controller

Step 3 of the lock box hardware: the **ultrasonic sensor and the motor working together**. This app opens and closes the door, knows from the distance whether the door is closed, ajar, open or blocked, **checks after every move that it really worked**, and raises a **TAMPER** alarm when the locked door is forced. The Space bar on your laptop is the push-button. It is the door half of the lock: the finger-counting half will tell it when to open.

## What it knows, and how

The sensor faces the inside of the door. The starting values are the ones you measured:

| The door reads | Distance | Measured |
|---|---|---|
| **closed** | 96 to 116 mm (106 plus or minus 10) | the motor closes the door to **106 mm** (5 closes out of 5); closed by hand: 95 to 107, median 96 |
| **ajar** (pushed, or part-way) | 117 to 250 mm | 123 mm (pushed about 1 cm), 136 to 196 mm (about 3 cm) |
| **open** | no echo, or beyond 250 mm | no echo, or 336 mm and beyond (the room behind the open door) |
| **blocked** | nearer than 96 mm | your hand in front of the sensor read 30 to 57 mm |

- A state only changes after **5 readings in a row** agree (about 0.3 s), so one stray reading does nothing.
- A closed door is a **locked** door (the app assumes the door is locked when it sees it closed, and after it has closed it itself).
- **After a move** (the motor time plus 0.8 s to settle), the sensor must show what was asked: closed after a close, open after an open. If not, it **tries once more**, and then reports a **FAULT** and does not claim the door is locked.
- **TAMPER:** the door is locked and then reads anything but closed without being told to move (forced open, swung open, or something held in front of the sensor). The alarm ends when the door reads closed again.
- **Push back** (optional, off to begin with): on tamper the motor tries once to push the door shut (plus its one retry). If someone holds the door open it gives up and shows a FAULT, so it does not push against a person for ever.
- **Sensor lost:** if no distance arrives for over a second it says so (and the matrix shows an X).
- The matrix shows a **closed padlock** (locked), an **open padlock**, an **!** (tamper), an **X** (fault or sensor lost), and an **arrow** while the motor moves.

## Wiring

| Part | Connects to |
|---|---|
| HC-SR04 GND, TRIG, ECHO | **GND, D7, D8** |
| HC-SR04 VCC | **3V3** (your sensor works on 3.3 V, so the echo needs no divider) |
| Cytron Maker Drive M1A, M1B | **D5, D6** |
| Maker Drive GND | **GND** (shared with the UNO Q) |
| The motor | the motor-1 terminals of the Maker Drive |
| Maker Drive power | the UNO Q's **5V** pin (as on your minifig robot: no capacitor was needed there) |

The motor now shares the UNO Q's 5 V / 3 A with the sensor, and later with the webcam. Watch for the warning signs: the board resetting, the webcam dropping out, this page disconnecting. If you see them, lower the speed or lengthen the soft start, and if that is not enough add a capacitor (470 microfarad or more, 10 V or more, + leg to 5V and - leg to GND) or use a second supply.

**Safety:** hold the door the first time and keep fingers out of its swing. **Esc**, or the **Space bar while the door moves**, stops the motor. The sketch ends every move by itself after at most 3 seconds, even if this page goes away.

## Run it

Copy this folder into Arduino App Lab as an app and press Run. Then open **`http://<the board's address>:7000`** in the browser on your laptop.

## Use it

- **Space bar:** the push-button. It opens a closed door and closes any other; pressed while the door moves, it stops it. **Esc** stops the motor at any time.
- **Open / Close:** make that move whatever the door seems to be doing. **Calibrate** reads the closed distance from the sensor (the door closed and still for 3 seconds).
- **Settings:** the closed distance and band, the open limit, the motor's speed, soft start, times and direction. They are kept in `python/door_config.json`. The starting values are the ones that worked on your door (direction -1, 600 ms each way at speed 100, soft start 250, closed distance 106 mm with a band of plus or minus 10), so you do not need to swap or calibrate anything.
- **Events:** every state change, move, check, retry, fault and alarm, also kept in `python/door_log.csv`.

Do these in order:

1. **Close the door with the motor** (Space twice, so it opens and then closes) and wait 3 seconds. It should read about **106 mm**, which is the default. Press **Calibrate** only if yours is different (and note the number).
2. **Open and close ten times** with the Space bar. Each should end with "The door is open" or "The door is closed" in the log. Note any retry or fault.
3. **Leave it locked for 5 minutes** and look at the events: there must be no tamper alarm (a false alarm would be a real problem).
4. **Tamper:** push the locked door open by hand by about 1 cm. How quickly does TAMPER appear? Does the alarm end when it is closed again?
5. **Blocked:** hold your hand a few centimetres in front of the sensor.
6. **Push back:** tick "Push back when forced" and push the door open a little. Does it push it shut? Hold it open: does it give up with a FAULT after one retry?
7. **Power:** watch for resets or a dropped page while the motor runs with the sensor streaming.

## What to send me

| | |
|---|---|
| The closed distance after the motor closes the door (it was 106 mm) | ___ mm |
| Ten opens and closes: how many were checked OK first time, how many needed a retry, any fault | ___ |
| Five minutes locked: any false tamper alarm? | ___ |
| Tamper by pushing about 1 cm: how fast, and did the alarm end by itself? | ___ |
| Blocked with a hand | ___ |
| Push back: did it close the door, and did it give up when held? | ___ |
| Any reset, dropout or page disconnect when the motor ran | ___ |
| With the motor off, how hard is it to push the closed door open? | ___ |
| `python/door_log.csv` | attach it |

## Files

```
app.yaml  sketch/sketch.ino  sketch/sketch.yaml      the App Lab app: the microcontroller side (sensor, motor, LED matrix)
python/main.py                                         connects the board to the page (WebUI brick, port 7000)
python/door.py                                         the logic: the bands, debounce, checking moves, tamper, push back, calibration
assets/index.html  app.js  style.css  libs/            the page (socket.io is included, so it needs no internet)
tests/run_all.py                                       runs every test the computer can run
tests/test_sketch.cpp + tests/stubs/                   the sketch against a simulated sensor, motor and LED matrix (needs g++)
tests/test_door.py                                     the Python side
tests/test_page.js                                     the page in a simulated browser (needs node and: npm install jsdom)
```

## What was tested, and what was not

`python tests/run_all.py` runs 39 checks of the sketch (against a simulated sensor, motor and matrix, including that the distance stream and the motor's timing both stay on time while the other is busy, even when no echo makes each reading wait 25 ms), 87 of the Python side (the bands with your measured distances, the debounce, locking, opening and closing with checks, retries and faults, tamper with and without push back, calibration, a quiet sensor, the log, and the whole main program) and 42 of the page. **None of it has run on the real board or in a real browser.** The sketch has not been compiled with Arduino's own tools.

Limits to know about:

- The bands rest on **a few measurements**. The closed distance (106 mm) is where the *motor* closes the door (5 closes out of 5). A door closed by hand sits about 10 mm further in (96 mm), at the lower edge of the band, so let the motor close it. The band is tight on both sides: closed readings sit 8 mm inside its top edge, and a push of about 1 cm (123 mm) is 7 mm beyond it. If you get false alarms, widen the band a little; if a gentle push is missed, narrow it.
- The motor **does not hold** the door: the yellow TT gearbox is not self-locking, so if the door is easy to push open, this app **detects and reports** that (TAMPER), and can try to push back, but it cannot prevent it.
- The sensor can be **fooled**: an object held in the beam at about 96 mm while the door is pulled open would look like a closed door. A "blocked" reading (nearer than the door) is caught; an exact fake is not.
- The sensor only sees the door while the door is in its beam: **fully open is "no echo or far"**, so the app tells closed, ajar and open apart, but not the angle.
