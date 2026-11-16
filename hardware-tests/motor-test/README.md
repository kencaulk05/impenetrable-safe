# Motor test

Step 2 of testing the lock box hardware, one part at a time. This app tests the **DC motor that swings the door, on its own**, through the Cytron Maker Drive: no sensor, no push-button (the **Space bar on your laptop** replaces the button). A web page on your laptop has big OPEN, CLOSE and STOP controls. Its job is to find out: which way the motor must turn, how long and how fast it must run to open and close the door fully, whether the door stays shut when the motor is off, and whether the shared power copes.

## Wiring

| Part | Connects to |
|---|---|
| Cytron Maker Drive M1A | **D5** |
| Cytron Maker Drive M1B | **D6** |
| Maker Drive GND | **GND** (shared with the UNO Q: needed) |
| The motor's two wires | the motor-1 output terminals of the Maker Drive |
| Maker Drive power (VIN) | the UNO Q's **5V** pin if you have no other supply (a capacitor across it is a precaution, not a requirement: see below); a separate 5 V supply is better |

## Read these before powering anything

**Powering the motor from the 5V pin.** It can work, within limits. What is known: the 5V pin is the board's 5 V system rail, shared with the USB-C input (which the board asks for as a 5 V / 3 A contract; Arduino recommends a supply of at least 15 W); Arduino's datasheet lists the 5V pin as rated "5 V up to 3 A" as an input, but does **not** state how much it may supply as an output, and a forum answer notes that the copper to that pin is thin (fine for about 140 mA, nothing is promised beyond). So keep the motor gentle:

- The sketch has a **soft start**: each move begins at the lowest speed and climbs to the chosen speed over the soft-start time (250 ms to begin with), which spares the rail.
- Keep the speed modest and the moves short. The page starts you at speed 150; **try about 100 and 300 ms first, with a soft start of 500 ms**.
- A **capacitor** is a precaution, **not a requirement**. When a motor starts it draws several times its running current for a few hundredths of a second, and a capacitor is a small local reservoir that supplies that surge, so that the shared rail does not sag. **If you do not have one, try without it** (the soft start already spreads the surge out, and a one-motor door is a lighter load than two motors), and add one only if you see the warning signs below. If you do add one: 470 to 1000 microfarad, rated 10 V or more, across the Maker Drive's power input and close to it, the **+ leg to the 5V side and the - leg (the striped one) to GND**: it is polarised, and backwards it can burst. A 100 nF ceramic capacitor across the motor's two terminals also quiets its electrical noise.
- The UNO Q must be fed by a proper **5 V / 3 A** source (for example a battery through the hub, if it can supply that). The board, the webcam and the motor all share that 3 A; a laptop's USB port is not enough.
- **Warning signs:** the board resets or reboots when the motor starts, the webcam drops out, the LED matrix flickers, this page disconnects. If that happens: lower the speed and the time first, and lengthen the soft start; if it still happens, add a capacitor (any electrolytic of 470 microfarad or more, rated 10 V or more, will do). The clean fix is a second supply: if the battery has a second USB port, a spare USB cable cut open gives 5 V (red) and GND (black) for the Maker Drive, with its GND joined to the UNO Q's GND.

**The motor cannot be left running.** The sketch ends every move by itself after the time asked, never allows more than 3 seconds, and stops at once when told. The motor is off from the moment the board starts. **STOP is Esc, or the Space bar while the motor is moving.**

**Hold the door the first time** you test the motor, and keep fingers out of its swing. Do not hold the door shut against the motor, and do not run it long against the end stop: a stalled TT motor can draw a lot of current. If something jams, unplug the motor's power.

## Run it

Copy this folder into Arduino App Lab as an app and press Run. Then open **`http://<the board's address>:7000`** in the browser on your laptop. While the motor runs, the LED matrix shows an arrow in its direction.

## Use it

- **Space bar:** makes the next move: open, then close, then open ... (the page says which is next). Pressing Space again **while the motor is moving stops it**. **Esc** always stops it.
- **Open / Close:** make that move whatever the page believes. **If the door is really somewhere else**, tell the page with "the door is now closed / open".
- **Settings:** speed (60 to 255), soft start (0 to 1000 ms), the time to open and to close (50 to 3000 ms), and **Swap direction**. They are remembered after a restart, and the page sends them with every move.
- **"Board confirmed"** in the table means the board sent a message back (that the motor started, or stopped) after the command. If it says NOT CONFIRMED the page warns you: the motor may not have moved, or the board's messages are not reaching the page.
- **After every move**, choose how it went in the table: *reached the end*, *stopped short*, *went too far*, or *grinding or jammed*. The table is also in `python/moves.csv`, and the page can download it.

Do these in order:

1. **Direction.** Hold the door, set a low speed (about 100) and a short time (300 ms), and press the Space bar once. Which way did the door go? If it went the wrong way for "open", tick **Swap direction**.
2. **Open and close fully.** Raise the time (and the speed a little if the door barely moves) until it reaches the end without grinding. Rate each move.
3. **The shortest times that work,** for opening and for closing separately, at the lowest speed that moves the door reliably.
4. **Trouble signs:** the board resetting or the webcam dropping out, a hum without movement, grinding at the end.
5. **With the door closed and the motor stopped,** push the door open by hand. How hard is it? (The yellow TT gearbox is not self-locking.)

## Files

```
app.yaml  sketch/sketch.ino  sketch/sketch.yaml      the App Lab app: the microcontroller side (the motor, and an arrow on the LED matrix)
python/main.py                                         connects the board to the page (WebUI brick, port 7000)
python/motortest.py                                    the logic: moves, settings, the door belief, confirmation, ratings, the log
assets/index.html  app.js  style.css  libs/            the page (socket.io is included, so it needs no internet)
tests/run_all.py                                       runs every test the computer can run
tests/test_sketch.cpp + tests/stubs/                   the sketch against simulated motor pins (needs g++)
tests/test_motortest.py                                the Python side
tests/test_page.js                                     the page in a simulated browser (needs node and: npm install jsdom)
```

## Result

The settings that reached the end without grinding on the real door: direction -1, 600 ms to open and 600 ms to close at speed 100, soft start 250 ms. They are the starting values of the door controller.

## Tests

`python tests/run_all.py` runs 39 checks of the sketch (against simulated motor pins: the direction, the timeout, the 3-second cap, the stop, the soft start, the speed limits, the arrow), 62 of the Python side (the settings limits and memory, the moves and directions, refusing a new move while the motor runs, an always-allowed stop, confirmations, including the board's message arriving before the call returns, lost or missing confirmations, a board that does not answer, ratings and the log) and 42 of the page (Space starts a move and stops a moving motor, Esc always stops, Space cannot click a focused button or fire while you type, the settings are cut to their limits and never overwritten by the board's old copy, the table is not rebuilt under a drop-down you are using).
