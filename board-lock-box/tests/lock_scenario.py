"""A long made-up session at the lock, driven the way a person would: used to record what the ORIGINAL lock rules (finger-lock project) do, and to check that the board's copy does the same.
The code used here, 245, is a TEST code and has nothing to do with anyone's real code."""
import random

TEST_CODE = [2, 4, 5]
SALT = bytes(range(16))
ITERATIONS = 1000                          # (the real lock uses 200,000: this is only for the tests)
POLICY = {"challenge_digits": 1, "challenge_pool": [1, 3, 5], "lockout_seconds": 30.0, "relock_seconds": 10.0}
RNG_SEED = 5


def conf(d, p=0.92):
    return [p if i == d else (1 - p) / 5 for i in range(6)]


def jsonable(x):
    return [jsonable(i) for i in x] if isinstance(x, (list, tuple)) else x


class Recorder:
    """Plays a session and writes down every call and every event it gets back."""

    def __init__(self, ctl):
        self.ctl, self.t, self.ops, self.events = ctl, 0.0, [], []

    def button(self):
        self.ops.append({"op": "button", "t": round(self.t, 3)}); self.events.append(jsonable(self.ctl.press_button(self.t)))

    def frames(self, probs, n, dt=0.1):
        for _ in range(n):
            self.t += dt
            self.ops.append({"op": "update", "t": round(self.t, 3), "probs": probs}); self.events.append(jsonable(self.ctl.update(self.t, probs)))

    def wait(self, seconds):
        self.t += seconds
        self.ops.append({"op": "tick", "t": round(self.t, 3)}); self.events.append(jsonable(self.ctl.tick(self.t)))

    def challenge(self):
        return self.ctl.display(self.t)["challenge"][0]


def show(rec, d):
    rec.frames(conf(d), 10); rec.frames(conf(0, 0.95), 6)                    # hold a number up, then rest the hand


def play(rec, code=TEST_CODE):
    wrong = [1, 2, 3]
    rec.button(); show(rec, rec.challenge()); [show(rec, d) for d in code]; rec.wait(5); rec.wait(6)           # 1. the right code: unlocked, then it locks again by itself
    rec.button(); show(rec, rec.challenge()); [show(rec, d) for d in wrong]                                        # 2. a wrong code
    rec.button(); c = rec.challenge(); show(rec, c % 5 + 1)                                                        # 3. the wrong challenge digit
    rec.button(); show(rec, rec.challenge()); [show(rec, d) for d in [3, 1, 2]]                                    # 4. a third failure: the lockout begins (30 s)
    rec.button(); rec.wait(10); rec.button(); rec.wait(25)                                                         #    pressed during the lockout: ignored; then it ends
    for _ in range(3):                                                                                             # 5. three more failures: the second lockout is twice as long (60 s)
        rec.button(); show(rec, rec.challenge()); [show(rec, d) for d in wrong]
    rec.wait(61)
    rec.button(); rec.wait(11)                                                                                     # 6. too slow: nothing counted against the person
    rec.button(); d = rec.challenge(); rec.frames(conf(d), 40); rec.frames(conf(0, 0.95), 6)                       # 7. one number held up for 4 seconds is ONE digit, not three
    rec.button(); show(rec, rec.challenge()); show(rec, 2); rec.button()                                          # 8. the button in the middle of an entry starts again
    show(rec, rec.challenge()); [show(rec, d) for d in code]                                                       #    ... and the right code unlocks (and resets the failures)
    rec.button()                                                                                                   # 9. the button while unlocked locks it again at once
    rec.frames([0.25, 0.25, 0.1, 0.1, 0.1, 0.2], 20)                                                               # 10. frames the network is unsure about do nothing
    rec.ctl.update(rec.t + 0.1, None); rec.wait(1)                                                                 # 11. a missing frame is harmless
