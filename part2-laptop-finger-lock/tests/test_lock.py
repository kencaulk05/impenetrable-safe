"""Tests for the lock: the rules (fingerlock/lock.py), the LED matrix pictures, the code analysis, the demo and set_code.py.   python tests/test_lock.py"""
import json, random, sys, tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, ROOT.as_posix())
from fingerlock import lock as L
from fingerlock import matrix as M
import lock_analysis as LA
import lock_demo
import set_code

problems = 0


def expect(label, cond, detail=""):
    global problems
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    problems += (not cond)


def P(d, p=0.9):
    v = np.full(6, (1 - p) / 5); v[d] = p
    return v


class Sim:
    """A lock controller on a clock, fed made-up network answers at 15 frames a second."""
    def __init__(self, code="153", policy=None, seed=0):
        self.ctl = L.LockController(L.Verifier.from_code(code, iterations=1000), policy or L.Policy(), rng=random.Random(seed))
        self.t, self.dt, self.events = 0.0, 1 / 15, []

    def frames(self, probs, n):
        for _ in range(n):
            self.t += self.dt; self.events += self.ctl.update(self.t, probs)

    def hold(self, d, n=10): self.frames(P(d), n)
    def rest(self, n=8): self.frames(P(0), n)
    def button(self): self.events += self.ctl.press_button(self.t)
    def wait(self, s): self.t += s; self.events += self.ctl.tick(self.t)
    def show(self, digits):
        for d in digits:
            self.hold(d); self.rest()
    def kinds(self): return [e[0] for e in self.events]
    def last(self, kind): return [e for e in self.events if e[0] == kind][-1]


print("1. the code and the secret")
ok = all(L.check_code(c) == [1, 5, 3] for c in ("153", [1, 5, 3], (1, 5, 3)))
bad = []
for c in ("15", "1534", "155", "150", "156", "abc", None, [1, 2, 2], "", "1 5 3"):
    try: L.check_code(c); bad.append(c)
    except ValueError: pass
expect("'153', [1, 5, 3] and (1, 5, 3) are accepted; too short, too long, repeated digits, 0, 6, letters, nothing and spaces are all refused", ok and not bad, str(bad))
v = L.Verifier.from_code("153", iterations=1000)
expect("the right code passes, the same digits in another order, a different code and a shorter one do not", v.check([1, 5, 3]) and not v.check([1, 3, 5]) and not v.check([2, 4, 1]) and not v.check([1, 5]))
expect("rubbish input is just 'no', never a crash", not v.check(None) and not v.check(["a"]) and not v.check([999, 1, 2]) and not v.check([]))
v2 = L.Verifier.from_code("153", iterations=1000)
expect("two lockers with the same code have different salts and hashes (the same code does not look the same twice)", v.salt != v2.salt and v.digest != v2.digest)
d = v.to_dict()
rt = L.Verifier.from_dict(json.loads(json.dumps(d)))
expect("it can be saved as JSON and loaded back; the file holds an algorithm, iterations, a salt and a hash (64 hex characters) and nothing else", rt.check([1, 5, 3]) and not rt.check([1, 3, 5]) and set(d) == {"algorithm", "iterations", "salt", "hash"} and len(d["hash"]) == 64)
expect("the verifier object holds only bytes and a number: no list of digits anywhere", all(isinstance(x, (bytes, int)) for x in vars(v).values()))
pol = L.Policy.from_dict({"challenge_digits": 2, "max_failures": 5, "nonsense": 1})
expect("a policy is read from a dictionary, ignoring unknown keys, and written back", pol.challenge_digits == 2 and pol.max_failures == 5 and L.Policy.from_dict(pol.to_dict()) == pol and L.Policy.from_dict(None) == L.Policy())

print("2. entering the code")
s = Sim(); s.hold(1, 30); s.rest(10)
expect("while the lock is idle (no button pressed) it does not even look at the hand", s.events == [] and s.ctl.state == L.IDLE)
s = Sim(); s.button()
expect("the button starts an entry: events 'button' and 'session', and the state is entering", s.events == [("button",), ("session", 3)] and s.ctl.state == L.ENTERING)
s.show([1, 5, 3])
expect("the right code, with a rest between digits, reads three digits and UNLOCKS", [e for e in s.events if e[0] in ("digit", "unlocked")] == [("digit", 0, 1), ("digit", 1, 5), ("digit", 2, 3), ("unlocked",)] and s.ctl.state == L.UNLOCKED, str(s.events))
expect("the screen is told the box is open for about 10 more seconds", 9 < s.ctl.display(s.t)["unlocked_left"] <= 10)
s = Sim(); s.button(); s.show([1, 3, 5])
expect("the same digits in the wrong order are DENIED, with 2 tries left, and the lock goes back to idle with nothing remembered", s.last("denied") == ("denied", "code", 2) and s.ctl.state == L.IDLE and s.ctl.entered == [])
s = Sim(); s.button(); s.hold(1, 45)
expect("holding one number up for 3 seconds is ONE digit, not three (the hand must go to rest first)", [e for e in s.events if e[0] == "digit"] == [("digit", 0, 1)])
s = Sim(); s.button(); s.hold(1, 7)
expect("a hold shorter than 8 frames is not a digit ...", s.kinds() == ["button", "session"])
s.hold(1, 3)
expect("... and when it lasts long enough it is", ("digit", 0, 1) in s.events)
s = Sim(); s.button()
for _ in range(10): s.hold(1, 1); s.hold(2, 1)
expect("an answer that flickers between 1 and 2 is never accepted", "digit" not in s.kinds())
s = Sim(); s.button(); s.frames(P(3, 0.45), 40)
expect("an answer the network is not sure about (45%) is never accepted", "digit" not in s.kinds())
s = Sim(); s.button(); s.rest(100)
expect("0 (an empty square or a fist) is never a digit, however long it lasts", "digit" not in s.kinds())
s = Sim(); s.button(); s.hold(1); s.hold(5, 40)
expect("changing straight from 1 to 5 without a rest does not count the 5 (it could be a half-way hand) ...", [e for e in s.events if e[0] == "digit"] == [("digit", 0, 1)])
s.rest(); s.hold(5)
expect("... but after a rest, a 5 does", ("digit", 1, 5) in s.events)
s = Sim(); s.button(); s.hold(1); s.rest(); s.button()
expect("pushing the button in the middle of an entry starts again: the first digit is forgotten", s.ctl.entered == [] and s.ctl.state == L.ENTERING and s.kinds().count("session") == 2)
s = Sim(); s.button(); s.show([1, 5])
a = [e for e in s.events if e[0] == "digit"]
s2 = Sim(); s2.button(); s2.show([1, 4])
expect("the digit events say what was READ, not whether it was RIGHT: a right first digit and a wrong second one look the same until the third digit decides (nothing for the LEDs to leak)", [e[:2] for e in a] == [e[:2] for e in [e for e in s2.events if e[0] == "digit"]] and "denied" not in s.kinds() and "denied" not in s2.kinds())
expect("nothing in the controller or in what the screen is given holds the code", not any(isinstance(x, (list, tuple)) and list(x) == [1, 5, 3] for x in vars(s.ctl).values()) and all(isinstance(x, (int, float, str, list)) for x in s.ctl.display(0).values()))

print("3. time")
s = Sim(); s.button(); s.rest(10); s.wait(10.5)
expect("no digit for 10 seconds: the entry is dropped, and that is NOT counted as a wrong code", s.last("timeout") == ("timeout", "digit") and s.ctl.state == L.IDLE and s.ctl.failures == 0)
s = Sim(policy=L.Policy(session_timeout=5, digit_timeout=100)); s.button(); s.wait(5.5)
expect("an entry that takes longer than the whole allowance is dropped too", s.last("timeout") == ("timeout", "session"))
s = Sim(policy=L.Policy(digit_timeout=2)); s.button(); s.frames(None, 40)
expect("frames with no usable picture (None) still let time pass, so timeouts work if the camera stops", s.last("timeout") == ("timeout", "digit"))
s = Sim(); s.button(); s.show([1, 5, 3]); s.wait(10.5)
expect("the box closes again by itself after 10 seconds", s.last("relock") == ("relock",) and s.ctl.state == L.IDLE)
s = Sim(); s.button(); s.show([1, 5, 3]); s.button()
expect("pushing the button while it is open closes it at once", s.last("relock") == ("relock",) and s.ctl.state == L.IDLE)

print("4. wrong tries and lockouts")
s = Sim()
for k in range(3):
    s.button(); s.show([2, 4, 1])
expect("three wrong codes in a row: a lockout of 30 seconds", s.last("lockout") == ("lockout", 30.0) and s.ctl.state == L.LOCKOUT and s.ctl.failures == 0)
n = len(s.events); s.button(); s.show([1, 5, 3])
expect("during the lockout the button and the hand are ignored (even the right code)", s.events[n:][-1][0] == "ignored" and s.ctl.state == L.LOCKOUT and "unlocked" not in s.kinds())
s.wait(31)
expect("after 30 seconds the lockout ends", s.last("lockout_over") == ("lockout_over",) and s.ctl.state == L.IDLE)
lengths = [30.0]
for rounds in range(3):
    for k in range(3):
        s.button(); s.show([2, 4, 1])
    lengths.append(s.last("lockout")[1]); s.wait(s.last("lockout")[1] + 1)
expect("each lockout is twice as long as the last (%s seconds), up to the limit (1 hour)" % lengths, lengths == [30.0, 60.0, 120.0, 240.0])
s = Sim(policy=L.Policy(lockout_max=100))
for rounds in range(4):
    for k in range(3):
        s.button(); s.show([2, 4, 1])
    s.wait(1000)
expect("the lockout never grows past the limit (30, 60, then 100 and 100)", [e[1] for e in s.events if e[0] == "lockout"] == [30.0, 60.0, 100.0, 100.0])
s = Sim()
for k in range(2):
    s.button(); s.show([2, 4, 1])
s.button(); s.show([1, 5, 3]); s.wait(11)                          # the box opens, and closes again by itself
for k in range(2):
    s.button(); s.show([2, 4, 1])
expect("a right code clears the count of wrong tries: two wrong, one right, two wrong is no lockout", "lockout" not in s.kinds() and s.ctl.failures == 2)
s = Sim(policy=L.Policy(max_failures=2)); s.button(); s.show([2, 4, 1])
expect("the number of tries before a lockout is a setting (here 2)", s.last("denied")[2] == 1)

print("5. the live challenge (the extra feature)")
pol = L.Policy(challenge_digits=1)
rng = random.Random(1); r1 = rng.choice(L.DIGITS)
s = Sim(policy=pol, seed=1); s.button()
expect("with the challenge on, the button asks for a random digit first (here %d), and the state is 'challenge'" % r1, s.last("challenge") == ("challenge", [r1]) and s.ctl.state == L.CHALLENGE and s.ctl.display(s.t)["challenge"] == [r1])
s.show([r1, 1, 5, 3])
expect("showing the asked digit, then the code, unlocks", s.last("challenge_ok") == ("challenge_ok", 0, r1) and ("enter_code",) in s.events and s.ctl.state == L.UNLOCKED, str(s.kinds()))
wrong = next(d for d in L.DIGITS if d != r1)
s = Sim(policy=pol, seed=1); s.button(); s.show([wrong])
expect("showing a different digit than the one asked is DENIED and counts as a wrong try", s.last("denied") == ("denied", "challenge", 2) and s.ctl.state == L.IDLE and s.ctl.failures == 1)
s = Sim(policy=pol, seed=1); s.button(); s.show([r1, 1, 5, 4])
expect("the right challenge with a wrong code is denied too", s.last("denied") == ("denied", "code", 2))
rng = random.Random(7); seen = []
s = Sim(policy=pol, seed=7)
for k in range(30):
    s.button(); seen.append(s.last("challenge")[1][0])
expect("the digit changes from entry to entry: in 30 entries all of 1 to 5 are asked (%s)" % sorted(set(seen)), set(seen) == set(L.DIGITS))
seed = next(sd for sd in range(100) if (lambda g: (g.choice(L.DIGITS), g.choice(L.DIGITS)))(random.Random(sd))[0] != (lambda g: (g.choice(L.DIGITS), g.choice(L.DIGITS)))(random.Random(sd))[1])
g = random.Random(seed); a1, a2 = g.choice(L.DIGITS), g.choice(L.DIGITS)
s = Sim(policy=pol, seed=seed); s.button(); s.show([a1, 1, 5, 3]); first_ok = s.ctl.state == L.UNLOCKED
s.button(); s.button(); s.show([a1, 1, 5, 3])
expect("REPLAY: a recording of a successful entry (challenge %d, then the code) played back when the lock asks for %d is DENIED" % (a1, a2), first_ok and s.last("denied")[1] == "challenge" and s.ctl.state != L.UNLOCKED)
s = Sim(policy=L.Policy(challenge_digits=2), seed=3); s.button(); ch = s.last("challenge")[1]
s.show(ch + [1, 5, 3])
expect("with a challenge of two digits both must be shown, in order, before the code (%s)" % ch, len(ch) == 2 and s.ctl.state == L.UNLOCKED)
s = Sim(policy=pol, seed=1); s.button(); s.rest(10); s.wait(10.5)
expect("a challenge that is ignored for 10 seconds times out without counting as a wrong try", s.last("timeout") == ("timeout", "digit") and s.ctl.failures == 0)

print("6. the LED matrix pictures")
expect("every picture is 8 rows by 13 columns of on/off, and the digits 0 to 5 are all different", all(f.shape == (8, 13) and f.dtype == bool for f in [M.digit(d) for d in range(6)] + [M.LOCKED, M.UNLOCKED, M.TICK, M.CROSS, M.READY, M.LOCKOUT]) and len({M.digit(d).tobytes() for d in range(6)}) == 6)
expect("the icons (closed padlock, open padlock, tick, cross, ready, lockout) are all different from each other and not empty", len({f.tobytes() for f in (M.LOCKED, M.UNLOCKED, M.TICK, M.CROSS, M.READY, M.LOCKOUT)}) == 6 and all(f.any() for f in (M.LOCKED, M.UNLOCKED, M.TICK, M.CROSS, M.READY, M.LOCKOUT)))
expect("a digit is drawn in the middle (rows 0 to 6, columns 4 to 8), so the bottom row is free for progress dots", all(not M.digit(d)[7].any() and not M.digit(d)[:, :4].any() and not M.digit(d)[:, 9:].any() for d in range(6)))
expect("progress dots: 0, 1, 2 or 3 of the three dots are lit under the digit, at columns 3, 6 and 9", [int(M.with_progress(M.digit(2), k, 3)[7].sum()) for k in range(4)] == [0, 1, 2, 3] and list(np.where(M.with_progress(M.digit(2), 3, 3)[7])[0]) == [3, 6, 9])
expect("the challenge digit has a dotted line underneath, so it cannot be mistaken for progress", M.challenge(4)[7].sum() == 7 and not np.array_equal(M.challenge(4), M.with_progress(M.digit(4), 3, 3)))
rows = M.frame_rows(M.LOCKED)
expect("a picture becomes 8 whole numbers of 13 bits (the leftmost LED the highest bit) for the board, and back again", len(rows) == 8 and all(0 <= r < 2 ** 13 for r in rows) and np.array_equal(np.array([[(r >> (12 - c)) & 1 for c in range(13)] for r in rows], dtype=bool), M.LOCKED))
img = M.render(M.digit(1), 10)
expect("it can be drawn: lit LEDs orange, unlit ones dark grey", img.shape == (80, 130, 3) and tuple(img[5, 65]) == (30, 150, 255) and tuple(img[5, 5]) == (50, 50, 50))
disp = {"of": 3}
expect("events choose the picture: session -> ready, a digit -> the digit with progress, denied -> cross, unlocked -> open padlock, lockout -> lockout, relock -> closed padlock, nothing -> keep the picture",
       np.array_equal(M.for_events([("session", 3)], disp), M.READY) and np.array_equal(M.for_events([("digit", 1, 5)], disp), M.with_progress(M.digit(5), 2, 3)) and np.array_equal(M.for_events([("denied", "code", 2)], disp), M.CROSS)
       and np.array_equal(M.for_events([("unlocked",)], disp), M.UNLOCKED) and np.array_equal(M.for_events([("lockout", 30.0)], disp), M.LOCKOUT) and np.array_equal(M.for_events([("relock",)], disp), M.LOCKED) and M.for_events([], disp) is None)

print("7. the analysis of codes and attacks")
R = LA.read_rates(np.array([[10, 0], [5, 5]]))
expect("read rates are the rows of the confusion matrix as shares: each row adds up to 1", np.allclose(R.sum(axis=1), 1) and np.allclose(R[1], [0.5, 0.5]))
perfect = LA.read_rates(np.eye(6) * 100)
st = [LA.code_stats(perfect, c) for c in LA.all_codes()]
expect("there are 60 codes of three different digits; with a perfect network the owner always gets in, and a random guess is right 1 time in 60 for every code", len(st) == 60 and all(abs(o - 1) < 1e-12 and abs(q - 1 / 60) < 1e-12 for o, q in st))
expect("a code is tried a few times: 0.5 per try is 87.5 percent within 3", abs(LA.within(0.5, 3) - 0.875) < 1e-12)
conf = np.eye(6) * 100; conf[4] = [0, 0, 0, 0, 50, 50]; conf[2] = [0, 0, 70, 30, 0, 0]
Rn = LA.read_rates(conf)
o_good, q_good = LA.code_stats(Rn, (1, 3, 5)); o_bad, q_bad = LA.code_stats(Rn, (2, 4, 1))
expect("with 4 read as 5 half the time and 2 as 3 30%% of the time, the code 1-3-5 works for its owner (%.0f%%) far better than 2-4-1 (%.0f%%)" % (100 * o_good, 100 * o_bad), abs(o_good - 1.0) < 1e-12 and abs(o_bad - 0.7 * 0.5) < 1e-12)
rng = np.random.default_rng(0); n_hit = 0; N = 200_000
codes = LA.all_codes()
for _ in range(N):
    x = codes[rng.integers(60)]
    n_hit += all(rng.random() < Rn[xk, sk] for xk, sk in zip(x, (1, 3, 5)))
expect("the intruder figure agrees with a simulation of 200,000 random guesses (%.4f against %.4f)" % (q_good, n_hit / N), abs(q_good - n_hit / N) < 0.002)
e, w = LA.time_to_break(growth=1.0)
expect("guessing against a constant 30 s lockout: 60 tries of 20 s with 19 lockouts is 1770 s at worst, and 895 s on average", abs(w - 1770) < 1e-9 and abs(e - 895) < 1e-9, "%.0f, %.0f" % (e, w))
e2, w2 = LA.time_to_break()
expect("doubling lockouts make it much slower (%s on average against %s)" % (LA.human(e2), LA.human(e)), e2 > 10 * e and w2 > 10 * w)
tmp = Path(tempfile.mkdtemp())
(tmp / "r.json").write_text(json.dumps({"new_session": {"confusion": (np.eye(6, dtype=int) * 100).tolist()}, "holdout": {"A": {"confusion": (np.eye(6, dtype=int) * 100).tolist()}}}))
expect("the command runs on a results file, for the new-session matrix and for a person", LA.main(["--results", str(tmp / "r.json")]) == 0 and LA.main(["--results", str(tmp / "r.json"), "--source", "A", "--code", "153", "--challenge", "2"]) == 0)

print("8. the demo and the code setting")
lines = []
final = lock_demo.headless_demo("153", out=lines.append)
text = "\n".join(lines)
expect("the scripted demo unlocks for the owner, closes the box again, denies an intruder three times, and ends locked out", "'unlocked'" in text and "'relock'" in text and text.count("'denied'") == 3 and "'lockout', 30.0" in text and final == L.LOCKOUT)
try: lock_demo.main(["--headless-demo", "155"]); w = False
except ValueError: w = True
expect("the demo refuses a code with a repeated digit", w)
cfg = tmp / "lock_config.json"
set_code.main(["--config", str(cfg), "--code", "153", "--challenge", "1"])
data = json.loads(cfg.read_text())
ctl = L.LockController(L.Verifier.from_dict(data["verifier"]), L.Policy.from_dict(data["policy"]), rng=random.Random(2))
expect("set_code.py writes a config with a salted hash and the policy, and the config opens the lock for the right code only: keys %s, challenge %d" % (sorted(data["verifier"]), data["policy"]["challenge_digits"]), set(data) == {"verifier", "policy"} and data["policy"]["challenge_digits"] == 1 and ctl.v.check([1, 5, 3]) and not ctl.v.check([1, 3, 5]))
for badcode in ("155", "12", "abc"):
    try: set_code.main(["--config", str(tmp / "x.json"), "--code", badcode]); wrong_ok = True
    except ValueError: wrong_ok = False
    if wrong_ok: break
expect("set_code.py refuses bad codes and writes nothing", not wrong_ok and not (tmp / "x.json").exists())
expect("lock_config.json is kept out of git", "lock_config.json" in (ROOT / ".gitignore").read_text() if (ROOT / ".gitignore").exists() else False)

print("9. for the demo: the challenge pool, the words, the window")
import cv2
from fingerlock import capture_lib as cl
from fingerlock.synth_hand import SyntheticCamera
expect("by default the challenge may ask for any digit; a pool is some of the digits 1 to 5, and an empty pool or a 6 is refused", L.Policy().challenge_pool == L.DIGITS and L.Policy(challenge_pool=[1, 3, 5]).challenge_pool == (1, 3, 5))
bad = []
for pool in ([], [6], [0, 1], [1, 7]):
    try: L.Policy(challenge_pool=pool); bad.append(pool)
    except ValueError: pass
expect("... (checked for an empty pool, a 6, a 0 and a 7)", not bad, str(bad))
pp = L.Policy(challenge_digits=1, challenge_pool=(1, 3, 5))
expect("the pool survives being saved as JSON (where it becomes a list) and loaded back", L.Policy.from_dict(json.loads(json.dumps(pp.to_dict()))) == pp)
s = Sim(policy=pp, seed=11); asked = []
for k in range(60):
    s.button(); asked.append(s.last("challenge")[1][0])
expect("with the pool 1, 3, 5 the lock only ever asks for 1, 3 or 5, and asks for all three (%s)" % sorted(set(asked)), set(asked) == {1, 3, 5})
s = Sim(policy=pp, seed=11); s.button(); r = s.last("challenge")[1][0]; s.show([r, 1, 5, 3])
expect("and the challenge, then the code, unlocks as before", s.ctl.state == L.UNLOCKED)
cfg2 = tmp / "cfg2.json"
set_code.main(["--config", str(cfg2), "--code", "135", "--challenge", "1", "--challenge-pool", "135"])
pol2 = L.Policy.from_dict(json.loads(cfg2.read_text())["policy"])
expect("set_code.py --challenge-pool 135 writes the pool into the config", pol2.challenge_pool == (1, 3, 5) and pol2.challenge_digits == 1)
events = [("button",), ("session", 3), ("challenge", [4, 2]), ("challenge_ok", 0, 4), ("enter_code",), ("digit", 1, 5), ("unlocked",), ("denied", "code", 2), ("denied", "challenge", 1), ("lockout", 30.0), ("lockout_over",), ("timeout", "digit"), ("relock",), ("ignored", "lockout", 12.4)]
words = [L.describe(e) for e in events]
expect("every kind of event can be put into plain words (a non-empty sentence each)", all(isinstance(w, str) and len(w) > 5 for w in words), str(words[:3]))
expect("the words are right: 'read digit 5 (2 of 3)', 'denied (wrong code), 2 tries left', '1 try left', 'locked out for 30 s', 'UNLOCKED'", "read digit 5 (2 of 3)" in words and "denied (wrong code), 2 tries left" in words and "denied (wrong challenge digit), 1 try left" in words and "too many wrong tries: locked out for 30 s" in words and "UNLOCKED" in words and "challenge: first show 4 then 2" in words)
expect("the words never say whether a digit was right (no 'right', 'correct' or 'wrong' in the description of a digit being read)", not any(x in L.describe(("digit", 0, 3)).lower() for x in ("right", "correct", "wrong")))
cam = SyntheticCamera(seed=3); cam.set_label(3); _, frame = cam.read(); roi = cl.Roi(220, 130, 200)
probs = np.array([0.02, 0.02, 0.02, 0.9, 0.02, 0.02])
ctl9 = L.LockController(L.Verifier.from_code("135", iterations=1000), L.Policy(), rng=random.Random(0))
img = {}
for st in ("idle", "challenge", "entering", "unlocked", "lockout"):
    disp = {"state": st, "entered": 1, "of": 3, "challenge": [3], "challenge_done": 0, "failures": 1, "lockout_left": 12.0, "unlocked_left": 7.0}
    img[st] = lock_demo.compose(frame, roi, disp, M.LOCKED, probs, 3, ["a", "b"], st)
expect("the window is the camera picture with a panel beside it (%s), and the camera part away from the square is untouched" % (img["idle"].shape,), img["idle"].shape == (480, 640 + lock_demo.PANEL, 3) and np.array_equal(img["idle"][:, :40], frame[:, :40]))
expect("the square is drawn in the colour of the state (grey, orange, yellow, green, red), so the audience can see the state from across the room", all(tuple(img[st][130 + 100, 220]) == lock_demo.COL[st] or tuple(img[st][130 + 100, 221]) == lock_demo.COL[st] for st in img) and len({lock_demo.COL[s] for s in img}) == 5)
g = lock_demo.compose(frame, roi, disp, M.LOCKED, probs, 3, [], "idle", guide=True); ng = lock_demo.compose(frame, roi, disp, M.LOCKED, probs, 3, [], "idle", guide=False)
expect("the dashed guide box is drawn inside the square, and can be turned off", int(np.abs(g.astype(int) - ng.astype(int)).sum()) > 0 and int(np.abs(g[:, 640:].astype(int) - ng[:, 640:].astype(int)).sum()) == 0 and 0 < lock_demo.GUIDE[0] < lock_demo.GUIDE[2] < 1 and 0 < lock_demo.GUIDE[1] < lock_demo.GUIDE[3] < 1)
expect("the panel changes with the state (a different picture for each of the five states)", len({img[st][:, 640:].tobytes() for st in img}) == 5)
try: lock_demo.main(["--config", str(tmp / "missing.json")]); w = False
except SystemExit as e: w = "set_code" in str(e)
expect("without a config the demo says to run set_code.py first", w and lock_demo.main(["--headless-demo", "153"]) == 0)

print()
print("ALL PASSED" if problems == 0 else f"{problems} CHECK(S) FAILED")
sys.exit(1 if problems else 0)
