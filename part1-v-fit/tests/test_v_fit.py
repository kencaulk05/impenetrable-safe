#!/usr/bin/env python3
"""Checks that v_fit.py and v_fit.xlsx agree: the same data, and the same five iterations of m and b.

    python tests/test_v_fit.py      (needs openpyxl; the spreadsheet must have been saved by Excel or LibreOffice so its values are stored)
"""
import sys
from pathlib import Path

import numpy as np
import openpyxl

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import v_fit  # noqa: E402

fails = 0


def expect(what, ok):
    global fails
    print(("  ok   " if ok else "  FAIL ") + what)
    fails += not ok


ws = openpyxl.load_workbook(HERE / "v_fit.xlsx", data_only=True).active
x, y = v_fit.anna_v()
expect("the same 120 data points", np.array_equal(x, [ws.cell(r, 1).value for r in range(2, 122)]) and np.array_equal(y, [ws.cell(r, 2).value for r in range(2, 122)]))
expect("the same learning rate and start", ws["M2"].value == v_fit.ALPHA_NEURON and ws["E2"].value == v_fit.M0 and ws["F2"].value == v_fit.B0)

m, b = v_fit.M0, v_fit.B0
for k in range(5):
    row = k + 2
    loss, dm, db = v_fit.neuron_step(x, y, m, b)
    new_m, new_b = m - v_fit.ALPHA_NEURON * dm, b - v_fit.ALPHA_NEURON * db
    sheet = [ws.cell(row, c).value for c in range(5, 12)]          # m, b, de/dm, de/db, new m, new b, loss
    expect("iteration %d: m, b, de/dm, de/db, new m, new b and the loss match the spreadsheet" % (k + 1), np.allclose(sheet, [m, b, dm, db, new_m, new_b, loss], rtol=1e-9, atol=1e-12))
    m, b = new_m, new_b

print("\nALL PASSED" if not fails else "\n%d FAILED" % fails)
sys.exit(1 if fails else 0)
