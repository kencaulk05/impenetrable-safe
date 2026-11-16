"""The lock: the rules that turn the network's answers into "open" or "stay shut". No camera, no motor and no window in here, so every rule can be tested.

THE FLOW (as in the assignment): walk to the safe, PUSH THE BUTTON, the LEDs light, show three DIFFERENT numbers (1 to 5) one after another under the camera, and it unlocks or stays locked.

  IDLE ---button---> [CHALLENGE: show the random digit(s) the matrix asks for, if the live challenge is on] ---> ENTERING: show the code digits ---> UNLOCKED (closes by itself
  after a few seconds, or when the button is pressed) or DENIED (back to IDLE). Too many wrong tries in a row -> LOCKOUT, which gets longer each time.

HOW A DIGIT IS READ. The network answers every camera frame. A digit counts only when (1) the answer has been the same, and sure enough, for several frames in a row (so a blur or a hand on its
way in does not count), and (2) the hand went to REST (a fist or an empty square, the network's class 0) since the last digit, so that holding one number up is one digit, not three.
The digit 0 is never part of a code.

THE SECRET. The code is stored only as a salted hash (PBKDF2), never as the digits. HONEST LIMIT: three different digits from 1 to 5 are only 60 codes, so anyone who can read the file can
try all 60 in a blink. The hash keeps the code from being read off the screen or out of the repository by accident, not from someone who has the file.
"""
import hashlib
import hmac
import os
import secrets
from dataclasses import asdict, dataclass, fields

import numpy as np

from fingerlock.predict import Smoother

DIGITS = (1, 2, 3, 4, 5)
IDLE, CHALLENGE, ENTERING, UNLOCKED, LOCKOUT = "idle", "challenge", "entering", "unlocked", "lockout"


def check_code(code, n=3):
    """The code as a list of digits, or ValueError. A code is n DIFFERENT digits from 1 to 5, given as '153' or [1, 5, 3]."""
    try:
        digits = [int(c) for c in code]
    except (TypeError, ValueError):
        raise ValueError("a code is %d digits, for example 153" % n)
    if len(digits) != n or any(d not in DIGITS for d in digits) or len(set(digits)) != n:
        raise ValueError("a code is %d DIFFERENT digits, each from 1 to 5 (for example 153)" % n)
    return digits


class Verifier:
    """Checks a code without keeping it: only a salt and a PBKDF2-SHA256 hash are stored."""

    def __init__(self, salt, iterations, digest):
        self.salt, self.iterations, self.digest = bytes(salt), int(iterations), bytes(digest)

    @staticmethod
    def _hash(digits, salt, iterations):
        return hashlib.pbkdf2_hmac("sha256", bytes(digits), salt, iterations)

    @classmethod
    def from_code(cls, code, n=3, iterations=200_000, salt=None):
        digits = check_code(code, n)
        salt = salt if salt is not None else os.urandom(16)
        return cls(salt, iterations, cls._hash(digits, salt, iterations))

    def check(self, digits):
        try:
            h = self._hash([int(d) for d in digits], self.salt, self.iterations)
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(h, self.digest)                       # takes the same time whether it is nearly right or not at all

    def to_dict(self):
        return {"algorithm": "pbkdf2-sha256", "iterations": self.iterations, "salt": self.salt.hex(), "hash": self.digest.hex()}

    @classmethod
    def from_dict(cls, d):
        return cls(bytes.fromhex(d["salt"]), d["iterations"], bytes.fromhex(d["hash"]))


@dataclass
class Policy:
    n_digits: int = 3                # digits in the code
    hold_frames: int = 8             # a digit must be the answer for this many frames in a row ...
    min_prob: float = 0.6            # ... with at least this average probability ...
    min_agree: float = 0.75          # ... and at least this share of the frames agreeing
    rest_frames: int = 5             # frames of "nothing" (class 0) needed between two digits
    digit_timeout: float = 10.0      # seconds allowed to show the next digit
    session_timeout: float = 30.0    # seconds for the whole entry
    max_failures: int = 3            # wrong entries in a row before a lockout
    lockout_seconds: float = 30.0    # the first lockout; each next one lasts lockout_growth times longer ...
    lockout_growth: float = 2.0
    lockout_max: float = 3600.0      # ... up to this
    relock_seconds: float = 10.0     # the box closes again by itself after this
    challenge_digits: int = 0        # THE EXTRA FEATURE: 0 = off; k = the matrix asks for k random digits before the code (a live challenge)
    challenge_timeout: float = 10.0
    challenge_pool: tuple = DIGITS   # the digits it may ask for: the ones the network reads best make the demo more reliable (1, 3, 5), but a recording then works 1 time in 3, not 1 in 5

    def __post_init__(self):
        self.challenge_pool = tuple(int(d) for d in self.challenge_pool)
        if not self.challenge_pool or any(d not in DIGITS for d in self.challenge_pool):
            raise ValueError("the challenge pool is some of the digits 1 to 5")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in names})


class LockController:
    """Feed it the button and the network's probabilities (six numbers per camera frame, for the classes 0 to 5) and the time; it returns a list of EVENTS to show and act on:

    ("button",) ("session", n_digits) ("challenge", [digits]) ("challenge_ok", index, digit) ("enter_code",) ("digit", index, digit) ("unlocked",) ("denied", reason, tries_left)
    ("lockout", seconds) ("lockout_over",) ("timeout", reason) ("relock",) ("ignored", reason, seconds)

    The events never say whether a digit was RIGHT, only that it was read, so the LEDs cannot leak the code. The time is passed in (seconds), so tests can run a day in a moment."""

    def __init__(self, verifier, policy=None, rng=None):
        self.v, self.p = verifier, policy or Policy()
        self.rng = rng or secrets.SystemRandom()
        self.state = IDLE
        self.failures = self.lockouts = 0
        self.entered, self.challenge, self.challenge_done = [], [], 0
        self.lockout_until = self.unlocked_until = self.session_start = self.last_progress = 0.0
        self._reset_reader()

    def _reset_reader(self):
        self.smoother = Smoother(self.p.hold_frames, self.p.min_prob, self.p.min_agree)
        self.armed, self.rest_run = True, 0

    # ---- what the person does
    def press_button(self, now):
        ev = self.tick(now) + [("button",)]
        if self.state == LOCKOUT:
            return ev + [("ignored", "lockout", round(self.lockout_until - now, 1))]
        if self.state == UNLOCKED:
            self.state = IDLE
            return ev + [("relock",)]
        self.entered, self.challenge_done = [], 0                      # IDLE, or pushed again in the middle of an entry: start afresh
        self.challenge = [self.rng.choice(self.p.challenge_pool) for _ in range(self.p.challenge_digits)]
        self.state = CHALLENGE if self.challenge else ENTERING
        self._reset_reader()
        self.session_start = self.last_progress = now
        ev.append(("session", self.p.n_digits))
        if self.challenge:
            ev.append(("challenge", list(self.challenge)))
        return ev

    def update(self, now, probs):
        """Call for every camera frame (probs: the six probabilities, or None if there was no usable frame)."""
        ev = self.tick(now)
        if self.state in (CHALLENGE, ENTERING) and probs is not None:
            d = self._read(np.asarray(probs, dtype=float))
            if d is not None:
                ev += self._accept(now, d)
        return ev

    def tick(self, now):
        """Time passing: a lockout ends, the box closes again, an entry that takes too long is dropped."""
        ev = []
        if self.state == LOCKOUT and now >= self.lockout_until:
            self.state = IDLE; ev.append(("lockout_over",))
        elif self.state == UNLOCKED and now >= self.unlocked_until:
            self.state = IDLE; ev.append(("relock",))
        elif self.state in (CHALLENGE, ENTERING):
            limit = self.p.challenge_timeout if self.state == CHALLENGE else self.p.digit_timeout
            reason = "session" if now - self.session_start > self.p.session_timeout else ("digit" if now - self.last_progress > limit else None)
            if reason:                                                 # being slow is not a wrong code: nothing is counted against the person
                self.state, self.entered, self.challenge = IDLE, [], []
                ev.append(("timeout", reason))
        return ev

    # ---- reading digits from the frames
    def _read(self, p):
        cls = int(p.argmax())
        self.rest_run = self.rest_run + 1 if (cls == 0 and p[0] >= self.p.min_prob) else 0
        if self.rest_run >= self.p.rest_frames:
            self.armed = True                                          # the hand went to rest: the next digit may be read
        self.smoother.add(p)
        st = self.smoother.stable()
        if st is None or st == 0 or not self.armed:
            return None
        self.armed, self.rest_run = False, 0
        self.smoother.reset()
        return st

    def _accept(self, now, d):
        self.last_progress = now
        if self.state == CHALLENGE:
            if d != self.challenge[self.challenge_done]:
                return self._deny(now, "challenge")
            self.challenge_done += 1
            ev = [("challenge_ok", self.challenge_done - 1, d)]
            if self.challenge_done == len(self.challenge):
                self.state = ENTERING
                ev.append(("enter_code",))
            return ev
        self.entered.append(d)
        ev = [("digit", len(self.entered) - 1, d)]
        if len(self.entered) == self.p.n_digits:
            ev += self._unlock(now) if self.v.check(self.entered) else self._deny(now, "code")
        return ev

    def _unlock(self, now):
        self.state, self.entered, self.challenge = UNLOCKED, [], []
        self.unlocked_until = now + self.p.relock_seconds
        self.failures = self.lockouts = 0
        return [("unlocked",)]

    def _deny(self, now, reason):
        self.failures += 1
        self.state, self.entered, self.challenge = IDLE, [], []
        ev = [("denied", reason, max(0, self.p.max_failures - self.failures))]
        if self.failures >= self.p.max_failures:
            secs = min(self.p.lockout_max, self.p.lockout_seconds * self.p.lockout_growth ** self.lockouts)
            self.lockouts += 1
            self.failures = 0
            self.state, self.lockout_until = LOCKOUT, now + secs
            ev.append(("lockout", secs))
        return ev

    def display(self, now):
        """What a screen or the LEDs need: nothing in it depends on the code."""
        return {"state": self.state, "entered": len(self.entered), "of": self.p.n_digits, "challenge": list(self.challenge), "challenge_done": self.challenge_done,
                "failures": self.failures, "lockout_left": max(0.0, self.lockout_until - now) if self.state == LOCKOUT else 0.0,
                "unlocked_left": max(0.0, self.unlocked_until - now) if self.state == UNLOCKED else 0.0}


def describe(event, of=3):
    """An event in plain words, for a screen or a log. Like the events themselves it never says whether a digit was right."""
    k = event[0]
    if k == "button": return "button pressed"
    if k == "session": return "show %d different digits, one at a time" % event[1]
    if k == "challenge": return "challenge: first show %s" % " then ".join(str(d) for d in event[1])
    if k == "challenge_ok": return "challenge digit %d accepted" % event[2]
    if k == "enter_code": return "now show your code"
    if k == "digit": return "read digit %d (%d of %d)" % (event[2], event[1] + 1, of)
    if k == "unlocked": return "UNLOCKED"
    if k == "denied": return "denied (%s), %d %s left" % ("wrong challenge digit" if event[1] == "challenge" else "wrong code", event[2], "try" if event[2] == 1 else "tries")
    if k == "lockout": return "too many wrong tries: locked out for %d s" % round(event[1])
    if k == "lockout_over": return "lockout over"
    if k == "timeout": return "too slow: press the button to start again"
    if k == "relock": return "locked again"
    if k == "ignored": return "ignored: locked out for %d more s" % round(event[2])
    return str(event)
