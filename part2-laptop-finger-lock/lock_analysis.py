#!/usr/bin/env python3
"""How good is a code, and how safe is the lock, given how the network REALLY confuses the digits?

    python lock_analysis.py --results results/results.json                  rank all 60 codes using the new-session confusion matrix
    python lock_analysis.py --results results/results.json --code 153      the numbers for one code

It uses the confusion matrix measured by train.py (what the network said when the hand showed each number) and makes two simplifying assumptions, both stated in the output:
each digit is held up once and read independently of the others, and a mistake on one hold is not undone by holding longer (so the numbers are on the cautious side for the owner).
"""
import argparse
import itertools
import json
import sys

import numpy as np

DIGITS = (1, 2, 3, 4, 5)


def read_rates(confusion):
    """R[i, j] = how often the network says j when the hand shows i."""
    c = np.asarray(confusion, dtype=float)
    return c / c.sum(axis=1, keepdims=True)


def all_codes(n=3):
    return list(itertools.permutations(DIGITS, n))                      # 60 codes of three different digits


def code_stats(R, code):
    """owner: the chance that one honest attempt is read as the code. intruder: the chance that a random code of three different digits is read as THIS code
    (an intruder who knows how the lock works but not the code). Both for one attempt."""
    owner = float(np.prod([R[d, d] for d in code]))
    codes = all_codes(len(code))
    intruder = float(np.mean([np.prod([R[x, s] for x, s in zip(c, code)]) for c in codes]))
    return owner, intruder


def within(p, attempts):
    return 1.0 - (1.0 - p) ** attempts


def time_to_break(max_failures=3, lockout_seconds=30.0, growth=2.0, lockout_max=3600.0, attempt_seconds=20.0, n_codes=60):
    """A guesser who never repeats a code, against a perfect network (so every wrong guess is wrong): the expected and the worst time, in seconds, until the right code is tried.
    After every max_failures wrong tries comes a lockout, each longer than the last."""
    def cost(n):                                                         # the time taken when the right code is the n-th one tried
        locks = (n - 1) // max_failures
        return n * attempt_seconds + sum(min(lockout_max, lockout_seconds * growth ** k) for k in range(locks))
    return float(np.mean([cost(n) for n in range(1, n_codes + 1)])), float(cost(n_codes))


def human(seconds):
    return "%.0f s" % seconds if seconds < 120 else ("%.0f min" % (seconds / 60) if seconds < 7200 else "%.1f hours" % (seconds / 3600))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default="results/results.json")
    ap.add_argument("--source", default="new_session", help="new_session, or a person letter for a new-person test (A, B ...)")
    ap.add_argument("--code")
    ap.add_argument("--challenge", type=int, default=0, help="digits of the live challenge, for the replay numbers")
    a = ap.parse_args(argv)
    r = json.load(open(a.results))
    conf = r["new_session"]["confusion"] if a.source == "new_session" else r["holdout"][a.source]["confusion"]
    R = read_rates(conf)
    print("read rates from the %s test (rows: the number shown, columns: what the network said):" % ("new-session" if a.source == "new_session" else "new-person (%s)" % a.source))
    print("        " + " ".join("%5d" % j for j in range(6)))
    for i in range(6):
        print("shown %d " % i + " ".join("%4.0f%%" % (100 * R[i, j]) for j in range(6)))
    stats = sorted(((code_stats(R, c), c) for c in all_codes()), key=lambda t: (-t[0][0], t[0][1]))
    show = [(s, c) for s, c in stats if a.code is None or "".join(map(str, c)) == a.code] if a.code else stats[:6] + [None] + stats[-3:]
    print("\n%-8s %-22s %-24s %s" % ("code", "owner, one attempt", "owner, within 3 attempts", "a random intruder, one attempt"))
    for t in show:
        if t is None:
            print("   ..."); continue
        (o, q), c = t
        print("%-8s %-22s %-24s %.2f%%  (a perfect network: %.2f%%)" % ("-".join(map(str, c)), "%.0f%%" % (100 * o), "%.0f%%" % (100 * within(o, 3)), 100 * q, 100 / 60))
    e, w = time_to_break()
    e0, w0 = time_to_break(growth=1.0)
    print("\nGUESSING THE CODE (60 codes, a guesser who never repeats one, 20 s per try, 3 wrong tries then a lockout):")
    print("  lockouts of a constant 30 s:           %s on average, %s at worst" % (human(e0), human(w0)))
    print("  lockouts that double each time (30 s, 60 s, 120 s ... up to an hour): %s on average, %s at worst" % (human(e), human(w)))
    k = a.challenge
    print("\nREPLAYING A RECORDING of someone entering the code: it passes about as often as the owner does%s" % ("" if not k else ", times 1 in %d with a live challenge of %d digit%s (the recording must contain the digits the lock asks for this time)" % (5 ** k, k, "" if k == 1 else "s")))
    print("  (without the challenge: the recording is read the same way each time; with 1 digit: 1 in 5; with 2 digits: 1 in 25)")
    print("\nASSUMPTIONS: each digit is held up once and read independently; a wrong reading is not corrected by holding longer; the intruder shows random different digits;")
    print("the confusion matrix comes from two people in one setup, so these are estimates, not guarantees.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
