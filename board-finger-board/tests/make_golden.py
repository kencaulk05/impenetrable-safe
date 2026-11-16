"""Makes tests/golden.json: what the ORIGINAL finger-lock code (fingerlock/predict.py) answers for a few made-up pictures, so that the app's copy of the steps can be checked against it.
You only need this if you change the network or the steps. It needs the finger-lock project:  python make_golden.py path/to/finger-lock"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, sys.argv[1])
from golden_frames import frame_for
from fingerlock import capture_lib as cl
from fingerlock.predict import Predictor

model = HERE.parent / "python" / "model" / "finger_cnn.npz"
pred = Predictor(str(model), cl.Roi(108, 163, 317))
out = []
for style, seeds in (("stripes", (1, 2, 3, 4)), ("blob", tuple(range(1, 13)))):
    for seed in seeds:
        digit, probs = pred.predict(frame_for(style, seed))
        out.append({"style": style, "seed": seed, "digit": int(digit), "probs": [float(p) for p in probs]})
        print(style, seed, digit, [round(float(p), 3) for p in probs])
(HERE / "golden.json").write_text(json.dumps({"reference": "fingerlock/predict.py Predictor, roi 108,163,317, model finger_cnn.npz (v2)", "frames": out}), encoding="utf-8")
