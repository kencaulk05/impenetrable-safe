# Demo-day guide (software only, box not finished)

## 20 minutes before

1. **Do not move the camera, the stand or the laptop** once you have set up: the network only works on the exact square it was trained on. Check that the green box in the window lines up with your taped square.
2. **Light:** a lamp above or right next to the camera, not at the side (side light makes finger shadows that the network counts as fingers). Same kind of light as when you collected the pictures.
3. **Choose the code** from the digits the network reads best (1, 3 and 5; for example 1 then 5 then 3):
   ```
   python set_code.py --challenge 1 --challenge-pool 135
   ```
   Typed without showing. If recognition is shaky in the room, turn the challenge off for now: `python lock_demo.py ... --challenge 0`.
4. **Start the demo:**
   ```
   python lock_demo.py --model models/finger_cnn.npz --data data/raw --camera 3
   ```
   SPACE is the button. q quits.

## How to show a digit (practise this three times)

- After SPACE, put your hand **inside the dashed box**, fingertips inside the square, the digit clearly visible. Hold it still for **about 1.5 seconds** until the matrix and the log say "read digit".
- Then go back to a **fist** (or take the hand away) for a moment before the next digit: that is what separates one digit from the next.
- Thumb folded for 1 to 4, open hand with the thumb out for 5. No thumbs-up.
- With the challenge on, the matrix first shows a digit: show **that** digit, then your three code digits.
- Practise a wrong code too (it should say "denied", and after 3 wrong tries "locked out for 30 s").

## Record a backup

Before the demo, record one good run with the screen recorder (Windows: Win + Alt + R). If the live demo misbehaves, play the recording and say so.

## Suggested order for the demo (about 5 minutes)

1. **The problem:** a box that opens only for a code of three different numbers (1 to 5) shown with your fingers; button, LEDs, camera.
2. **The network, live:** before pressing the button, hold up numbers and point at "network sees" on the right.
3. **Unlock:** press the button, the challenge, the code, unlocked, closes again.
4. **Wrong code, then the lockout:** denied three times, locked out, the lockouts double.
5. **The honest part:** only 60 codes, how long guessing takes (`python lock_analysis.py --results results/results.json --challenge 1`), why the code uses 1, 3 and 5, the thumb and position findings, what a recording can and cannot do against the challenge.
6. **The box:** not finished; show the plan (Maker Drive on D5/D6 and D9/D10, end-stop switches on D3, D4, D7 and D8, the button on D2, the LED matrix on the board) and say the next step is the UNO Q.

## If something goes wrong

| Problem | What to do |
|---|---|
| The camera does not open | try `--camera 0`, `1` or `2`; close other programs using it; or run `python lock_demo.py --headless-demo 153` for a scripted run |
| It reads the wrong number | check your hand is in the dashed box and the fingertips inside the square; thumb rule; fewer shadows; try again, a wrong digit does not break anything |
| The challenge asks for a digit it cannot read | that is the weak digits 2 and 4: use `--challenge-pool 135`, or `--challenge 0` |
| Locked out | wait 30 seconds, or restart the program (the lockout is not remembered) |
| Anything else | play the backup recording |
