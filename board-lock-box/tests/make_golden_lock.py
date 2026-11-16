"""Makes tests/golden_lock.json: a long session played through the ORIGINAL lock rules, with every event it gave. Only needed if you change the rules.   python make_golden_lock.py path/to/finger-lock"""
import json, random, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, sys.argv[1])
from fingerlock.lock import LockController, Policy, Verifier
from lock_scenario import ITERATIONS, POLICY, RNG_SEED, SALT, TEST_CODE, Recorder, play

ctl = LockController(Verifier.from_code(TEST_CODE, iterations=ITERATIONS, salt=SALT), Policy(**{**POLICY, "challenge_pool": tuple(POLICY["challenge_pool"])}), rng=random.Random(RNG_SEED))
rec = Recorder(ctl); play(rec)
kinds = sorted({e[0] for evs in rec.events for e in evs})
(HERE / "golden_lock.json").write_text(json.dumps({"reference": "fingerlock/lock.py (finger-lock project)", "ops": rec.ops, "events": rec.events, "final_display": ctl.display(rec.t), "final_time": rec.t}), encoding="utf-8")
print("%d calls, %d events, kinds: %s" % (len(rec.ops), sum(len(e) for e in rec.events), kinds))
