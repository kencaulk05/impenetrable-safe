#!/usr/bin/env python3
"""Build v_fit.xlsx: gradient descent on m and b for Anna's V, five iterations, every number a live formula.

    python make_v_spreadsheet.py                    Anna's V (the same 120 points as v_fit.py)
    python make_v_spreadsheet.py --data v_data.csv  your own data (x,y)

Sheets:  Read me | Data | Single neuron (5 iterations on m and b, two charts) | Class layout (the same 5 iterations laid out like the class page: one column per point,
         blocks of guess / db / dm rows per epoch) | ReLU neuron (one neuron with a ReLU: 5 iterations on w and c)
Colours: blue text = typed-in numbers, black = formulas, green = a link to another sheet, yellow fill = cells you are meant to change.
"""
import argparse
import subprocess
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference, ScatterChart, Series
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

from v_fit import B0, LR_LINEAR, M0, NOISE, load_data

HERE = Path(__file__).resolve().parent
RECALC = Path("/mnt/skills/public/xlsx/scripts/recalc.py")
RELU_W0, RELU_C0, RELU_LR = 10.0, 0.0, 0.05            # the single ReLU neuron: where it starts and its learning rate (its target is y in y units)
F = "Arial"
BLUE, BLACK, GREEN = "0000FF", "000000", "008000"
HEAD = PatternFill("solid", fgColor="DDE6F3")
YELLOW = PatternFill("solid", fgColor="FFFF00")
THIN = Side(style="thin", color="BBBBBB")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def put(ws, ref, value, color=BLACK, fill=None, fmt=None, bold=False, wrap=False, border=True, italic=False, size=10):
    c = ws[ref]
    c.value = value
    c.font = Font(name=F, size=size, bold=bold, italic=italic, color=color)
    if fill: c.fill = fill
    if fmt: c.number_format = fmt
    c.alignment = Alignment(wrap_text=wrap, vertical="top" if wrap else "center")
    if border: c.border = BOX
    return c


def header(ws, row, labels, col0=1):
    for i, t in enumerate(labels):
        put(ws, "%s%d" % (L(col0 + i), row), t, BLACK, HEAD, bold=True, wrap=True)
    ws.row_dimensions[row].height = 46


def build(x, y, anna, out):
    N = len(x)
    last = N + 1                                                       # the last data row on the Data sheet
    X, Y, XH, YH = ("Data!$%s$2:$%s$%d" % (c, c, last) for c in "ABCD")
    wb = Workbook()

    # ---------------------------------------------------------------- Read me
    ws = wb.active; ws.title = "Read me"
    ws.column_dimensions["A"].width = 115
    lines = [("Gradient descent on Anna's V: five iterations on m and b", True),
             ("This workbook fits a straight line to V-shaped data by gradient descent, one step at a time, with every number a live formula. Change a yellow cell and everything recalculates.", False), ("", False),
             ("Sheets", True),
             ("Data: the x and y values (blue = typed in), the same two columns rescaled to zero mean and unit spread (x_hat and y_hat), and the line's prediction after 0 to 5 steps in the original y units (for the chart).", False),
             ("Single neuron: the five iterations. Each row is the state after k steps: the loss, the two gradients, the updated m_hat and b_hat, and the same line in the original units. Two charts show the line moving and the loss falling.", False),
             ("Class layout: the same five iterations laid out like the class page: one column per data point, and for each epoch a block of rows: guess, db (guess - y) and dm (db times x). The averages of those rows give the next m and b. A check cell says it agrees with the Single neuron sheet.", False),
             ("ReLU neuron: one neuron followed by a ReLU, y_hat = relu(w x_hat + c). The ReLU passes gradient only for the points where z = w x_hat + c is above 0, and the 'points on' column counts them.", False), ("", False),
             ("The math in one place (hats mean rescaled)", True),
             ("x_hat = (x - mean of x) / spread of x,  y_hat = (y - mean of y) / spread of y.  Model: y_hat_guess = m_hat x_hat + b_hat.  Loss L = (1/N) * sum of (guess - y_hat)^2.", False),
             ("Gradients: dL/dm = (2/N) * sum of e x_hat,  dL/db = (2/N) * sum of e,  where e = guess - y_hat.  Update: m_new = m - alpha * dL/dm,  b_new = b - alpha * dL/db.", False),
             ("Back to the original units: m = spread_y * m_hat / spread_x,  b = mean_y + spread_y * b_hat - m * mean_x.", False),
             ("For the ReLU neuron: a = max(z, 0), z = w x_hat + c, target y in original units;  dL/dw = (2/N) * sum of e * 1[z > 0] * x_hat,  dL/dc = (2/N) * sum of e * 1[z > 0],  e = a - y.", False), ("", False),
             ("Colour legend", True),
             ("Blue text = a typed-in number (the data, the starting values). Black = a formula. Green = a link to a cell on another sheet. Yellow fill = a cell you are meant to change (learning rate, starting values).", False), ("", False),
             ("Assumptions (all stated here, none hidden)", True),
             ("Data: %s." % ("AnnaCode's V example: %d random points, x uniform on 20 to 100, y = 2 |x - 60| + Gaussian noise (sigma %g). In AnnaCode the points change every time; these come from a fixed seed (0) so the numbers can be reproduced. Rerun make_v_spreadsheet.py --data file.csv to use other points" % (N, NOISE) if anna else "the CSV given to make_v_spreadsheet.py, %d points" % N), False),
             ("Rescaling: x and y are rescaled before the fit, as AnnaCode does. Without it the large x values make the steps blow up (v_fit.py shows this: at learning rate 0.05 the raw fit overflows).", False),
             ("The single neuron starts at m_hat = %g, b_hat = %g with learning rate %g, chosen so the first five steps are easy to see (full-batch gradient descent: every step uses all the points). The ReLU neuron starts at w = %g, c = %g with learning rate %g and fits y in its original units, as AnnaCode does when the last layer has an activation." % (M0, B0, LR_LINEAR, RELU_W0, RELU_C0, RELU_LR), False),
             ("Check: the numbers match v_fit.py to 9 decimals (tests/test_v_fit.py compares them).", False)]
    for i, (t, b) in enumerate(lines, start=1):
        c = ws["A%d" % i]; c.value = t; c.font = Font(name=F, size=12 if i == 1 else 10, bold=b); c.alignment = Alignment(wrap_text=True, vertical="top")

    # ---------------------------------------------------------------- Data
    wd = wb.create_sheet("Data")
    header(wd, 1, ["x", "y", "x_hat = (x - mean) / spread", "y_hat = (y - mean) / spread"] + ["line after %d step%s (y units)" % (k, "" if k == 1 else "s") if k else "line at the start (y units)" for k in range(6)])
    SN = "'Single neuron'!"
    for i in range(N):
        r = i + 2
        put(wd, "A%d" % r, float(x[i]), BLUE, fmt="0.000"); put(wd, "B%d" % r, float(y[i]), BLUE, fmt="0.000")
        put(wd, "C%d" % r, "=(A%d-%s$B$7)/%s$B$8" % (r, SN, SN), GREEN, fmt="0.0000"); put(wd, "D%d" % r, "=(B%d-%s$B$9)/%s$B$10" % (r, SN, SN), GREEN, fmt="0.0000")
        for k in range(6):                                              # the line after k steps, drawn in the original units
            put(wd, "%s%d" % (L(5 + k), r), "=%s$B$9+%s$B$10*(%s$B$%d*$C%d+%s$C$%d)" % (SN, SN, SN, 13 + k, r, SN, 13 + k), GREEN, fmt="0.00")
    for c in range(1, 11): wd.column_dimensions[L(c)].width = 16
    wd.freeze_panes = "A2"

    # ---------------------------------------------------------------- Single neuron
    s = wb.create_sheet("Single neuron")
    put(s, "A1", "One neuron, y_hat = m_hat x_hat + b_hat: five iterations of gradient descent", bold=True, border=False, size=12)
    put(s, "A3", "learning rate alpha"); put(s, "B3", LR_LINEAR, BLUE, YELLOW, "0.0000")
    put(s, "A4", "starting m_hat"); put(s, "B4", M0, BLUE, YELLOW, "0.0000")
    put(s, "A5", "starting b_hat"); put(s, "B5", B0, BLUE, YELLOW, "0.0000")
    put(s, "A6", "number of points N"); put(s, "B6", "=COUNT(%s)" % X, fmt="0")
    put(s, "A7", "mean of x"); put(s, "B7", "=AVERAGE(%s)" % X, fmt="0.0000")
    put(s, "A8", "spread (std) of x"); put(s, "B8", "=STDEVP(%s)" % X, fmt="0.0000")
    put(s, "A9", "mean of y"); put(s, "B9", "=AVERAGE(%s)" % Y, fmt="0.0000")
    put(s, "A10", "spread (std) of y"); put(s, "B10", "=STDEVP(%s)" % Y, fmt="0.0000")
    put(s, "C3", "yellow = change me", border=False); put(s, "C7", "the data is rescaled with these four numbers", border=False)
    put(s, "A11", "Each row is the state after k steps. The new m_hat and b_hat in columns G and H become the next row's m_hat and b_hat.", italic=True, border=False)
    header(s, 12, ["k (steps taken)", "m_hat", "b_hat", "loss = (1/N) sum (m_hat x_hat + b_hat - y_hat)^2", "dL/dm = (2/N) sum e x_hat", "dL/db = (2/N) sum e", "new m_hat = m_hat - alpha dL/dm", "new b_hat = b_hat - alpha dL/db", "the same m in y per x", "the same b in y"])
    for k in range(6):
        r = 13 + k
        put(s, "A%d" % r, k, BLUE, fmt="0")
        put(s, "B%d" % r, "=$B$4" if k == 0 else "=G%d" % (r - 1), fmt="0.0000"); put(s, "C%d" % r, "=$B$5" if k == 0 else "=H%d" % (r - 1), fmt="0.0000")
        put(s, "D%d" % r, "=SUMPRODUCT((B{r}*{XH}+C{r}-{YH})^2)/$B$6".format(r=r, XH=XH, YH=YH), fmt="0.0000")
        if k < 5:
            put(s, "E%d" % r, "=2*SUMPRODUCT((B{r}*{XH}+C{r}-{YH})*{XH})/$B$6".format(r=r, XH=XH, YH=YH), fmt="0.0000")
            put(s, "F%d" % r, "=2*SUMPRODUCT(B{r}*{XH}+C{r}-{YH})/$B$6".format(r=r, XH=XH, YH=YH), fmt="0.0000")
            put(s, "G%d" % r, "=B%d-$B$3*E%d" % (r, r), fmt="0.0000"); put(s, "H%d" % r, "=C%d-$B$3*F%d" % (r, r), fmt="0.0000")
        else:
            for c in "EFGH": put(s, "%s%d" % (c, r), None)
        put(s, "I%d" % r, "=$B$10*B%d/$B$8" % r, fmt="0.0000"); put(s, "J%d" % r, "=$B$9+$B$10*C%d-I%d*$B$7" % (r, r), fmt="0.0000")
    put(s, "A20", "check: the Class layout sheet ends at the same m_hat and b_hat (should be 0)"); put(s, "B20", "=ABS('Class layout'!B34-B18)+ABS('Class layout'!C34-C18)", GREEN, fmt="0.000000000")
    put(s, "A22", "The loss falls every step, but a straight line cannot bend into a V: given many more steps, m goes to about 0 and b to the average of y, the flat line, with a typical miss as big as the V is tall.", border=False)
    for c, w in zip("ABCDEFGHIJ", (34, 12, 12, 24, 18, 18, 20, 20, 16, 14)): s.column_dimensions[c].width = w
    sc = ScatterChart(); sc.title = "The line moves toward the data (then stalls: it cannot bend)"; sc.style = 13; sc.height, sc.width = 9, 15
    sc.x_axis.title, sc.y_axis.title = "x", "y"; sc.x_axis.delete = False; sc.y_axis.delete = False; sc.x_axis.number_format = "0"; sc.y_axis.number_format = "0"
    xr = Reference(wd, min_col=1, min_row=2, max_row=last)
    pts = Series(Reference(wd, min_col=2, min_row=2, max_row=last), xr, title="V data"); pts.marker.symbol = "circle"; pts.marker.size = 5; pts.graphicalProperties.line.noFill = True; sc.series.append(pts)
    for col, name in ((5, "start"), (6, "after 1"), (8, "after 3"), (10, "after 5")):
        sr = Series(Reference(wd, min_col=col, min_row=2, max_row=last), xr, title=name); sr.marker.symbol = "none"; sr.smooth = False; sc.series.append(sr)
    s.add_chart(sc, "L3")
    lc = LineChart(); lc.title = "The loss falls as m and b are adjusted"; lc.style = 12; lc.height, lc.width = 8, 15
    lc.add_data(Reference(s, min_col=4, min_row=12, max_row=18), titles_from_data=True); lc.set_categories(Reference(s, min_col=1, min_row=13, max_row=18))
    lc.x_axis.title, lc.y_axis.title = "steps taken", "loss"; lc.x_axis.delete = False; lc.y_axis.delete = False; lc.legend = None; lc.y_axis.number_format = "0.0"
    s.add_chart(lc, "L22")

    # ---------------------------------------------------------------- Class layout
    c_ = wb.create_sheet("Class layout")
    first, lastc = 5, 4 + N                                             # the data columns: E .. (E + N - 1)
    rng = lambda row: "%s%d:%s%d" % (L(first), row, L(lastc), row)
    put(c_, "A1", "The five iterations laid out like the class page: one column per point", bold=True, border=False, size=12)
    put(c_, "A2", "For each epoch: guess = m_hat x_hat + b_hat;  db = guess - y_hat;  dm = db x_hat.  Then m_hat_new = m_hat - alpha * 2 * average(dm) and b_hat_new = b_hat - alpha * 2 * average(db).", italic=True, border=False)
    for row, label, src, fmt in ((3, "x (original units)", "A", "0.00"), (4, "x_hat", "C", "0.0000"), (5, "y (original units)", "B", "0.00"), (6, "y_hat", "D", "0.0000")):
        put(c_, "A%d" % row, label, bold=True)
        for i in range(N): put(c_, "%s%d" % (L(first + i), row), "=Data!%s%d" % (src, i + 2), GREEN, fmt=fmt)
    put(c_, "A7", "learning rate", bold=True); put(c_, "B7", "='Single neuron'!B3", GREEN, fmt="0.0000")
    put(c_, "A8", "Epoch", bold=True, wrap=True); put(c_, "B8", "m_hat", bold=True); put(c_, "C8", "b_hat", bold=True); put(c_, "D8", "loss", bold=True)
    put(c_, "E8", "one column per data point, from the smallest x to the largest", italic=True, border=False)
    # each epoch's block: its first row holds  Epoch k | m_hat | b_hat | loss ; then the guess, db and dm rows
    for k in range(6):
        h = 9 + 5 * k
        put(c_, "B%d" % h, "='Single neuron'!B4" if k == 0 else "=B%d-$B$7*2*AVERAGE(%s)" % (h - 5, rng(h - 5 + 3)), GREEN if k == 0 else BLACK, fmt="0.0000", bold=True)
        put(c_, "C%d" % h, "='Single neuron'!B5" if k == 0 else "=C%d-$B$7*2*AVERAGE(%s)" % (h - 5, rng(h - 5 + 2)), GREEN if k == 0 else BLACK, fmt="0.0000", bold=True)
        put(c_, "D%d" % h, "=SUMSQ(%s)/COUNT(%s)" % (rng(h + 2), rng(4)), fmt="0.0000", bold=True)
        put(c_, "A%d" % h, "Epoch %d" % k, bold=True)
        put(c_, "A%d" % (h + 1), "guess"); put(c_, "A%d" % (h + 2), "db = guess - y_hat")
        if k < 5: put(c_, "A%d" % (h + 3), "dm = db x_hat")
        for i in range(N):
            col = L(first + i)
            put(c_, "%s%d" % (col, h + 1), "=$B$%d*%s$4+$C$%d" % (h, col, h), fmt="0.000")
            put(c_, "%s%d" % (col, h + 2), "=%s%d-%s$6" % (col, h + 1, col), fmt="0.000")
            if k < 5: put(c_, "%s%d" % (col, h + 3), "=%s%d*%s$4" % (col, h + 2, col), fmt="0.000")
    c_.column_dimensions["A"].width = 22
    for i in range(1, N + 5): c_.column_dimensions[L(i)].width = 10 if i > 4 else (11 if i > 1 else 22)
    c_.freeze_panes = "E8"

    # ---------------------------------------------------------------- ReLU neuron
    r_ = wb.create_sheet("ReLU neuron")
    put(r_, "A1", "One neuron followed by a ReLU, y_hat = relu(w x_hat + c): five iterations", bold=True, border=False, size=12)
    put(r_, "A3", "learning rate alpha"); put(r_, "B3", RELU_LR, BLUE, YELLOW, "0.0000")
    put(r_, "A4", "starting w"); put(r_, "B4", RELU_W0, BLUE, YELLOW, "0.0000")
    put(r_, "A5", "starting c"); put(r_, "B5", RELU_C0, BLUE, YELLOW, "0.0000")
    put(r_, "A6", "number of points N"); put(r_, "B6", "=COUNT(%s)" % X, fmt="0")
    put(r_, "A8", "z = w x_hat + c, the neuron outputs max(z, 0), and it is compared with y in the original units (as AnnaCode does when the last layer has an activation). Where z <= 0 the output is flat, so those points pass NO gradient back: the ReLU's derivative is 1 when z > 0 and 0 otherwise.", italic=True, border=False)
    header(r_, 9, ["k (steps taken)", "w", "c", "loss = (1/N) sum (relu(w x_hat + c) - y)^2", "points on (z > 0)", "dL/dw = (2/N) sum e 1[z>0] x_hat", "dL/dc = (2/N) sum e 1[z>0]", "new w", "new c"])
    for k in range(6):
        r = 10 + k
        z = "(B{r}*{XH}+C{r})".format(r=r, XH=XH)
        put(r_, "A%d" % r, k, BLUE, fmt="0")
        put(r_, "B%d" % r, "=$B$4" if k == 0 else "=H%d" % (r - 1), fmt="0.0000"); put(r_, "C%d" % r, "=$B$5" if k == 0 else "=I%d" % (r - 1), fmt="0.0000")
        put(r_, "D%d" % r, "=SUMPRODUCT((({z}>0)*{z}-{Y})^2)/$B$6".format(z=z, Y=Y), fmt="0.0000")
        put(r_, "E%d" % r, "=SUMPRODUCT(({z}>0)*1)".format(z=z), fmt="0")
        if k < 5:
            put(r_, "F%d" % r, "=2*SUMPRODUCT((({z}>0)*{z}-{Y})*({z}>0)*{XH})/$B$6".format(z=z, XH=XH, Y=Y), fmt="0.0000")
            put(r_, "G%d" % r, "=2*SUMPRODUCT((({z}>0)*{z}-{Y})*({z}>0))/$B$6".format(z=z, Y=Y), fmt="0.0000")
            put(r_, "H%d" % r, "=B%d-$B$3*F%d" % (r, r), fmt="0.0000"); put(r_, "I%d" % r, "=C%d-$B$3*G%d" % (r, r), fmt="0.0000")
        else:
            for c in "FGHI": put(r_, "%s%d" % (c, r), None)
    put(r_, "A17", "One ReLU neuron can only make ONE hinge: at best it can follow one arm of the V and stay flat on the other, so its loss levels off high. Two hidden neurons (one per arm) can make the whole V.", border=False)
    for c, w in zip("ABCDEFGHI", (22, 12, 12, 26, 16, 24, 24, 12, 12)): r_.column_dimensions[c].width = w
    for sheet in wb.worksheets:                                        # print and PDF: landscape, one page wide
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
    wb.save(out)
    return N


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=None)
    ap.add_argument("--out", default=str(HERE / "v_fit.xlsx"))
    a = ap.parse_args()
    x, y = load_data(a.data)
    n = build(x, y, a.data is None, a.out)
    print("wrote %s (%d data points)" % (a.out, n))
    if RECALC.exists():                                                  # Excel computes the formulas when you open the file; this stores the results too
        r = subprocess.run([sys.executable, str(RECALC), a.out, "120"], capture_output=True, text=True)
        print("recalculation:", r.stdout.strip()[:300])
    else:
        print("(recalc.py not found: the formulas will calculate when the file is opened in Excel)")


if __name__ == "__main__":
    main()
