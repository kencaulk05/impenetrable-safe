# Ultrasonic sensor test

Step 1 of testing the lock box hardware, one part at a time. This app tests the **HC-SR04 ultrasonic sensor on its own**: no motor, no push-button (the **Space bar on your laptop** replaces the button). A web page on your laptop shows the distance live, and a Space-bar capture records a few seconds of readings and tells you how good they were. Its job is to answer: does the sensor work (on 3.3 V, or does it need 5 V?), and how far is it from the inside of the door when the door is closed, open, or pushed?

## How the sensor should see the door

Mount the sensor so that it faces the **inside of the door squarely** when the door is closed, a few centimetres away. Then the distance means:

- **Door closed:** a steady distance X.
- **Door pushed open a little** (someone forcing it): the distance grows a little, and the door is still in view.
- **Door fully open:** the door has left the sensor's view, so the sensor reads **no echo**, or the distance to the wall or things behind. **That is the correct answer, not a fault.** The lock will treat "no echo, or far away" as "door open", which is why the app has no separate "nothing in front" choice: it is the same situation.

So the door controller can only tell *closed*, *ajar* and *open*, not exactly how far open the door is. Measuring the angle would need a different mounting, where the sensor still sees the door while it swings.

## Wiring

| HC-SR04 | Connects to |
|---|---|
| GND | **GND** |
| TRIG | **D7** |
| ECHO | **D8**, through a divider if the sensor runs from 5V (see below) |
| VCC | **3V3 first**; if its readings are poor, **5V** |

**The sensor's supply.** The classic HC-SR04 is a 5 V part. On 3.3 V it commonly gives short, noisy or missing readings, and some units do not work at all. Variants marked **HC-SR04P**, HC-SR04+ or RCWL-1601 are rated 3 to 5.5 V: look at the back of the sensor's board for a "P" or "3.3V". Either way, **try 3V3 first**: the door is only centimetres away, which is where a weak supply matters least. The page tells you whether it works. (The sensor takes about 15 mA, so the 5V pin is not strained by it.)

**The echo level.** On 5 V the sensor's ECHO is a 5 V signal. Arduino's own pages disagree about whether the UNO Q's digital pins can take that (the datasheet summary says 5 V tolerant except A0 and A1; another Arduino page, as quoted by one site, gives 3.6 V as the absolute maximum on every header pin), so do not gamble the board on it. If the sensor runs from **5V**, put a divider on the ECHO wire: **1 kOhm from ECHO to D8, and 2 kOhm from D8 to GND** (two 1 kOhm in series make the 2 kOhm). If it works from 3V3, the echo is already 3.3 V and needs no divider. Never use A0 or A1.

## Run it

Copy this folder into Arduino App Lab as an app and press Run. Then open **`http://<the board's address>:7000`** in the browser on your laptop (the laptop and the board on the same network). The LED matrix on the board shows the distance as a bar.

## Use it

The page shows a big distance in millimetres, a chart of the last 15 seconds, and a "sensor" chip: **OK**, **no echo** (nothing is coming back), **settling**, or **no data from the board** (is the sketch running?).

To capture: hold the sensor and what it faces **still**, choose what it is looking at (door closed, pushed open about 1 cm or 3 cm, fully open, or "other..." to type your own) and the power supply, and press the **Space bar** (or the button). It records for 5 seconds (you can change that) and adds a row to the table: how many readings were usable, the average, the median, the range and the spread, and a verdict:

| Verdict | Meaning |
|---|---|
| GOOD | steady to within 2 mm |
| OK | spread up to 5 mm: fine for a door that moves by centimetres |
| POOR | jumpy, or fewer than 90% of the readings usable |
| BAD | fewer than half usable: nothing useful is coming back |

For **"door fully open"** the verdict is different, because no echo is expected there: **NOTHING IN VIEW** (almost no echo: as expected), **MIXED** (some far echoes, some none), or **SOMETHING IN VIEW** (it still reads a far distance, which it tells you, so the closed distance can be compared with it).

Do these in order:

1. **Aim.** Point the sensor at the inside of the door and watch the number. It should be steady and make sense.
2. **The power test.** With VCC on **3V3**, capture "door closed" (5 s). Then move VCC to **5V** (add the divider on ECHO), choose 5V on the page, and capture again. Compare "usable readings" and "spread". If 3V3 gives at least 90% usable and a small spread, keep 3V3.
3. **Door closed.** Capture "door closed": this is the distance X the lock will watch for.
4. **Tamper.** With the door closed, push it open by hand about 1 cm and capture; then about 3 cm and capture. The distance should grow, and the sensor should still see the door.
5. **Door fully open.** Open the door all the way and capture. Write down what it reads: no echo, or a far distance (how far?).

The page can download the table as a CSV, and the board also keeps every capture in `python/captures.csv`.

## Files

```
app.yaml  sketch/sketch.ino  sketch/sketch.yaml       the App Lab app: the microcontroller side
python/main.py                                          connects the board to the page (WebUI brick, port 7000)
python/ultrasonic.py                                    the logic: live readings, captures, statistics, verdicts
assets/index.html  app.js  style.css  libs/             the page (socket.io is included, so it needs no internet)
tests/run_all.py                                        runs every test the computer can run
tests/test_sketch.cpp + tests/stubs/                    the sketch against a simulated sensor (needs g++)
tests/test_ultrasonic.py                                the Python side
tests/test_page.js                                      the page in a simulated browser (needs node and: npm install jsdom)
```

## Result

The sensor works on **3V3**, so the echo needs no divider. Measured on the box (the door controller uses these as its bands):

| What the sensor faces | Reading |
|---|---|
| door closed by the motor | 106 mm (5 closes out of 5) |
| door closed by hand | 95 to 107 mm, median 96 |
| door pushed open about 1 cm | 123 mm |
| door pushed open about 3 cm | 136 to 196 mm |
| door fully open | no echo, or 336 mm and beyond (the room behind the door) |
| a hand in front of the sensor | 30 to 57 mm |

## Tests

`python tests/run_all.py` runs 22 checks of the sketch (against a simulated sensor: the distance filter, a wild reading, no echo, out of range, recovery, the LED bar), 51 of the Python side (including the verdicts for a fully open door) and 39 of the page (the Space bar starts a capture but not while you type or choose in a field, and it cannot click a focused Clear button; labels typed into the page cannot inject HTML; the CSV is written safely).
