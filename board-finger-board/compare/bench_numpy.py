"""How fast does THIS computer run one step of the finger-count network?  It uses exactly the code, the network and the made-up picture that the UNO Q app's Benchmark button uses,
so the two machines can be compared fairly (the UNO Q against your computer).

    python bench_numpy.py                 (200 steps, prints the result)
    python bench_numpy.py --csv laptop_speed.csv     (also adds a row to a CSV file, in the same columns as the board's board_speed.csv)

Needs numpy and opencv (pip install numpy opencv-python)."""
import argparse
import csv
import datetime
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
import board_vision as bv


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=200, help="how many steps to time")
    ap.add_argument("--csv", help="add the result to this CSV file")
    args = ap.parse_args()
    pipe = bv.Pipeline(HERE.parent / "python" / "model" / "finger_cnn.npz")
    row = {"time": datetime.datetime.now().strftime("%H:%M:%S"), "what": "made-up picture", "frame": "%dx%d" % bv.TRAINING_FRAME}
    row.update(bv.benchmark(pipe, bv.synthetic_frame(*bv.TRAINING_FRAME), bv.default_roi(bv.TRAINING_FRAME), args.n))
    row.update(bv.machine_info())
    print("One step of the finger-count network on this computer (%d steps, the standard made-up picture):" % row["n"])
    print("  cutting out the square : %6.2f ms (median)" % row["prep_median_ms"])
    print("  the network            : %6.2f ms (median), %.2f ms for the slowest 5%%, %.2f ms worst" % (row["infer_median_ms"], row["infer_p95_ms"], row["infer_max_ms"]))
    print("  one whole step         : %6.2f ms (median), about %s steps a second" % (row["total_median_ms"], row["fps_estimate"]))
    print("  this machine           : %s, Python %s, NumPy %s, OpenCV %s" % (row["machine"], row["python"], row["numpy"], row["opencv"]))
    if args.csv:
        new = not Path(args.csv).exists()
        with open(args.csv, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=bv.BENCH_FIELDS)
            if new:
                w.writeheader()
            w.writerow({k: row.get(k) for k in bv.BENCH_FIELDS})
        print("  added to %s" % args.csv)


if __name__ == "__main__":
    main()
