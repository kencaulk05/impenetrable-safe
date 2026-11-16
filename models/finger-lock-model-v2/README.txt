finger-lock-model-v2: the same network as v1, trained to be less fussy about where in the square the hand is

Trained by:  python train.py --data data/raw --epochs 80 --shift 0.18 --zoom 0.15 --final-only
on the same 2,400 pictures as v1 (two people, A and B, 200 of each number from each, two sessions), 64 x 64 colour, mirror across the fingers (--flip vertical).
The only difference from v1 is the augmentation: the hand is shifted by up to 18% (v1: 8%) and zoomed by up to 15% (v1: 10%) while training.

To try it on the laptop webcam: copy the "models" folder into your finger-lock folder (replace v1's), then
    python predict_live.py --model models/finger_cnn.npz --data data/raw --camera 3
Do not move the camera or the stand: the network was trained on exactly that square.

WHAT IS AND IS NOT MEASURED
- This network itself was trained on every picture, so it has NO held-out test number. It fits its own pictures at 94.2% (v1: 96.5%), which is not a test.
- The evidence for the change is evidence/position_experiment.txt: the same two recipes trained on the SESSION 1 pictures only and tested on the SESSION 2 ones
  (one run each, a few points are noise). Stronger augmentation: 84.1% against 81.3% with the hand where it normally is, and much less loss when the hand is moved:
  moved up 80% against 71%, down 81% against 67%, left 85% against 60%, right (fingertips out of the square) 73% against 56%.
- It has not been tested on a new person.
- This is the network that runs on the UNO Q (board-finger-board and board-lock-box use the same file).
