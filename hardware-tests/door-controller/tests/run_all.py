"""Run every test of this app that the computer can run. Usage: python run_all.py   (from the tests folder)
The page test needs node and the jsdom package:  npm install jsdom   (in this folder)."""
import os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXE = ".exe" if os.name == "nt" else ""
results = []


def run(label, cmd):
    print(f"\n=== {label} ===", flush=True)
    p = subprocess.run(cmd, cwd=HERE)
    results.append((label, "passed" if p.returncode == 0 else "FAILED"))


def skip(label, why):
    print(f"\n=== {label} ===\n  skipped: {why}")
    results.append((label, "skipped (" + why + ")"))


def check_app_yaml():
    """App Lab refuses an app whose app.yaml is not valid YAML (for example an unquoted description that contains a colon and a space)."""
    print("\n=== app.yaml (valid YAML, with the fields App Lab needs) ===", flush=True)
    text = (HERE.parent / "app.yaml").read_text(encoding="utf-8")
    try:
        import yaml
        data = yaml.safe_load(text)
        ok = isinstance(data, dict) and all(k in data for k in ("name", "description", "bricks")) and isinstance(data["description"], str)
        why = "" if ok else "it is missing name, description or bricks"
    except ImportError:                                   # no PyYAML: look for the usual trap by hand
        import re
        bad = [l for l in text.splitlines() if re.match(r"^(name|description|icon):\s+[^\"']", l) and re.search(r":\s| #", l.split(":", 1)[1])]
        ok, why = not bad, ("an unquoted value contains a colon and a space, or ' #': " + bad[0][:70]) if bad else ""
    except Exception as e:
        ok, why = False, str(e).splitlines()[0][:150]
    print("  " + ("ok   app.yaml is valid" if ok else "FAIL app.yaml is not valid: " + why))
    results.append(("app.yaml", "passed" if ok else "FAILED (" + why + ")"))


check_app_yaml()
if shutil.which("g++"):
    built = subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-I", "stubs", "-o", "test_sketch" + EXE, "test_sketch.cpp"], cwd=HERE)
    if built.returncode == 0:
        run("sketch against a simulated sensor, motor and LED matrix", [str(HERE / ("test_sketch" + EXE))])
    else:
        results.append(("sketch", "FAILED (did not compile)"))
else:
    skip("sketch", "g++ is not installed")
run("python (the door logic and main.py)", [sys.executable, "test_door.py"])
node = shutil.which("node")
if node and subprocess.run([node, "-e", "require('jsdom')"], cwd=HERE, capture_output=True).returncode == 0:
    run("web page (in a simulated browser)", [node, "test_page.js"])
else:
    skip("web page", "node or the jsdom package is missing (npm install jsdom)")

print("\n=== summary ===")
for label, outcome in results:
    print(f"  {label:<58} {outcome}")
bad = [r for r in results if r[1].startswith("FAILED")]
print("\n" + ("SOMETHING FAILED" if bad else f"ALL PASSED: {sum(r[1] == 'passed' for r in results)} groups passed, {sum(r[1].startswith('skipped') for r in results)} skipped"))
sys.exit(1 if bad else 0)
