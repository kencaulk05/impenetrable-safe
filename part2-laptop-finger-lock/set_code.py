#!/usr/bin/env python3
"""Choose the code. It is stored only as a salted hash in lock_config.json (which is kept out of git), never as the digits.

    python set_code.py                 asks for the three digits without showing them
    python set_code.py --challenge 1   also turns on the live challenge (the matrix asks for 1 random digit before the code)

Remember: three different digits from 1 to 5 are only 60 codes, so anyone who can read lock_config.json can find the code in a blink. The hash only keeps it from being read by accident.
"""
import argparse
import getpass
import json
import sys
from pathlib import Path

from fingerlock.lock import Policy, Verifier, check_code


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="lock_config.json")
    ap.add_argument("--code", help="the code, for example 153 (visible on the screen and in the shell history: prefer to type it when asked)")
    ap.add_argument("--challenge", type=int, default=0, help="the extra feature: this many random digits to show before the code (0 = off)")
    ap.add_argument("--challenge-pool", default="12345", help="the digits the challenge may ask for, for example 135 (the ones the network reads best: more reliable, but a recording then works 1 time in 3)")
    a = ap.parse_args(argv)
    code = a.code or getpass.getpass("code (3 different digits, 1 to 5; not shown): ")
    digits = check_code(code)
    pol = Policy(challenge_digits=a.challenge, challenge_pool=tuple(int(c) for c in a.challenge_pool))
    Path(a.config).write_text(json.dumps({"verifier": Verifier.from_code(digits).to_dict(), "policy": pol.to_dict()}, indent=1), encoding="utf-8")
    print("saved %s (a salted hash, not the digits); live challenge: %s" % (a.config, "%d digit(s)" % a.challenge if a.challenge else "off"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
