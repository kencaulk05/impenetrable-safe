"""The lock rules on the board (python/lock.py) against the ORIGINAL rules from the finger-lock project: a long recorded session must give exactly the same events.   python test_lock_rules.py"""
import json, random, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python")); sys.path.insert(0, str(HERE))
import board_vision
import lock
from lock import CHALLENGE, ENTERING, IDLE, LockController, Policy, Verifier, check_code
from lock_scenario import ITERATIONS, POLICY, RNG_SEED, SALT, TEST_CODE, conf, jsonable

problems = 0


def expect(label, cond, detail=""):
    global problems
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    problems += (not cond)


def controller(**kw):
    pol = Policy(**{**POLICY, "challenge_pool": tuple(POLICY["challenge_pool"]), **kw})
    return LockController(Verifier.from_code(TEST_CODE, iterations=ITERATIONS, salt=SALT), pol, rng=random.Random(RNG_SEED))


print("1. the recorded session")
g = json.loads((HERE / "golden_lock.json").read_text(encoding="utf-8"))
ctl = controller(); got = []
for op in g["ops"]:
    if op["op"] == "button": ev = ctl.press_button(op["t"])
    elif op["op"] == "update": ev = ctl.update(op["t"], op["probs"])
    else: ev = ctl.tick(op["t"])
    got.append(jsonable(ev))
n_events = sum(len(e) for e in g["events"]); kinds = sorted({e[0] for evs in g["events"] for e in evs})
expect("GOLDEN: all %d calls of a long session (%d events) give EXACTLY the events the original rules gave, in the same order" % (len(g["ops"]), n_events), got == g["events"] and len(got) == len(g["ops"]))
expect("and the lock ends in the same state as the original", ctl.display(g["final_time"]) == g["final_display"], str(ctl.display(g["final_time"])))
expect("the session covers success, both ways of being denied, the lockouts (30 s, then 60 s), the timeout, relocking, and presses that are ignored (%s)" % ", ".join(kinds), {"unlocked", "denied", "lockout", "lockout_over", "timeout", "relock", "ignored", "challenge_ok", "digit"} <= set(kinds) and [e[1] for evs in g["events"] for e in evs if e[0] == "lockout"] == [30.0, 60.0])
expect("it uses the same steadiness check as the camera page (Smoother from board_vision)", lock.Smoother is board_vision.Smoother)

print("2. aborting an entry (new on the board: used when the box is tampered with)")
ctl = controller(); ctl.press_button(0.0); ctl.update(0.1, conf(ctl.display(0.1)["challenge"][0]))
ctl.abort(); d = ctl.display(0.2)
expect("an entry in progress is dropped: back to idle, nothing entered, and NO failure is counted against the person", ctl.state == IDLE and d["entered"] == 0 and d["challenge"] == [] and ctl.failures == 0 and ctl.lockouts == 0)
ev = ctl.press_button(1.0)
expect("afterwards the button starts a fresh session as usual", ctl.state == CHALLENGE and ("session", 3) in ev)
for _ in range(1): pass
ctl.abort(); ctl2 = controller(challenge_digits=0); ctl2.press_button(0.0)
for d in TEST_CODE: [ctl2.update(0.1, conf(d)) for _ in range(10)]; [ctl2.update(0.2, conf(0, .95)) for _ in range(6)]
st = ctl2.state; ctl2.abort(); expect("aborting an UNLOCKED box (or an idle one) changes nothing", st == "unlocked" and ctl2.state == "unlocked")
ctl3 = controller(); ctl3.failures = 2; ctl3.press_button(0.0); ctl3.abort(); expect("failures already counted are kept when an entry is aborted", ctl3.failures == 2)

print("3. the code check, the secret and the settings")
expect("a code is 3 different digits from 1 to 5, given as text or a list", check_code("245") == [2, 4, 5] and check_code([2, 4, 5]) == [2, 4, 5])
bad = []
for c in ("244", "240", "246", "24", "2456", "abc", "", None):
    try: check_code(c); bad.append(c)
    except ValueError: pass
expect("repeated digits, a 0, a 6, the wrong length, letters and nothing are all refused", not bad, str(bad))
v = Verifier.from_code("245", iterations=1000, salt=SALT); d = v.to_dict()
expect("only a salt and a hash are stored: the file says how it was made, not the digits", set(d) == {"algorithm", "iterations", "salt", "hash"} and d["algorithm"] == "pbkdf2-sha256" and len(d["hash"]) == 64 and "digits" not in d)
expect("the right digits check out, wrong ones and rubbish do not, and it survives being written and read back", v.check([2, 4, 5]) and not v.check([2, 5, 4]) and not v.check([2, 4]) and not v.check("x") and Verifier.from_dict(json.loads(json.dumps(d))).check([2, 4, 5]))
p = Policy(challenge_digits=2, challenge_pool=(1, 3, 5))
expect("the settings (policy) survive being written and read back, and unknown keys are ignored", Policy.from_dict(json.loads(json.dumps(p.to_dict()))) == p and Policy.from_dict({"relock_seconds": 5, "nonsense": 1}).relock_seconds == 5 and Policy.from_dict(None) == Policy())
for pool in ((), (0, 1), (6,)):
    try: Policy(challenge_pool=pool); ok = False
    except ValueError: ok = True
    expect("a challenge pool of %s is refused" % (pool,), ok)
dp = Policy()
expect("the defaults are the rules of the laptop lock: 3 digits, 8 steady frames, 3 tries, a first lockout of 30 s that doubles up to an hour, the door closes after 10 s", (dp.n_digits, dp.hold_frames, dp.max_failures, dp.lockout_seconds, dp.lockout_growth, dp.lockout_max, dp.relock_seconds) == (3, 8, 3, 30.0, 2.0, 3600.0, 10.0))

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
