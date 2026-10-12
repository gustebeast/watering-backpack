"""How tall is a CAPITAL in the plotted silkscreen, per unit of KiCad text size?

    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/check_silk_cap.py

RUNS UNDER KiCad's PYTHON, because the only authority on what KiCad plots is
KiCad. It asks each silk label for its EFFECTIVE SHAPE -- the filled outline
that goes on the gerber, not the layout box the geom exporter records -- and
divides the ink's height by the label's declared size.

WHY IT EXISTS. `src/silk_face.py` turns a label's KiCad size into the em the
CadQuery kernel should draw at, and for that it needs two numbers: the FACE's
capital height per em (0.6670, measured through the kernel) and KiCad's own
capital height per unit of size. It assumed the second was 1.0 -- that a KiCad
text size IS its capital height. That is true of KiCad's stroke font and false
of an outline face, and every letter in the CAD stood 7.07 % taller than the
ink for it. Nothing caught it: elec/cad_geom_check.py counts a label by probing
for INK AT ITS PRINTED POSITION, and a label drawn 7 % too tall still has ink
at its position, so it reported 139 / 139 throughout.

0.9340 IS NOW IN THE SOURCE, so it is a figure a gate has to keep true. This is
that gate. A figure no gate reads stops being true.

THE 0.9692 ROWS ARE NOT A SECOND ANSWER. Labels containing O, G, S or C read
0.9692 because round letters OVERSHOOT the cap line in every typeface ever cut.
The capital height is what the FLAT-TOPPED capitals stand at, which is why the
figure is taken from them and why both numbers are printed.
"""
import sys
import os

sys.path.insert(0, r"C:\Program Files\KiCad\10.0\bin\Lib\site-packages")
import pcbnew                                                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ⚠ READ KICAD_CAP OUT OF THE SOURCE, do not import it. src/silk_face.py
# imports cadkit.board_geom, which imports cadquery, which is not in KiCad's
# python -- and KiCad's python is the only interpreter that can answer the
# question this file asks. Same `ast` trick silk_face itself uses to read
# SILK_FACE out of elec/silk.py without importing pcbnew.
import ast                                                      # noqa: E402


def _declared():
    path = os.path.join(HERE, "src", "silk_face.py")
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "KICAD_CAP":
                    return float(ast.literal_eval(node.value))
    raise SystemExit("src/silk_face.py no longer declares KICAD_CAP -- the "
                     "figure this gate exists to keep true is gone")


DECLARED = _declared()

PCB = os.path.join(HERE, "elec", "out", "main.kicad_pcb")
MM = 1e6
TOL = 0.002
# Flat-topped, no overshoot, no descender. Deliberately excludes O G S C Q U J
# and the round digits: those sit a fraction PROUD of the cap line by design.
#
# ⚠ AND IT EXCLUDES "+" AND THE DIGITS 2, 4 AND 7, WHICH THE FIRST DRAFT PUT
# IN. The spread check caught both rather than averaging them into a figure
# that described nothing: "2 PA" and "2 PB" read 0.9496 against every capital's
# 0.9340, because this face cuts the 2 with a rounded top that overshoots like
# an O. "+" is a MATH symbol, set to the arithmetic axis rather than the cap
# line. Being flat-topped says nothing about where the top IS; 4 and 7 are out
# for the same reason, which is that no label on this board proves them.
#
# The digit 1 stays, and it is the only digit that does: it appears in eleven
# labels here and reads 0.9340 in every one.
FLAT = set("ABDEFHIKLMNPRTVWXYZ1")


def main():
    board = pcbnew.LoadBoard(PCB)
    flat, round_ = [], []
    for d in board.GetDrawings():
        if not isinstance(d, pcbnew.PCB_TEXT):
            continue
        s = (d.GetText() or "").strip()
        if not s or d.GetTextAngleDegrees() % 90 != 0:
            continue
        letters = [c for c in s if c != " "]
        if not letters:
            continue
        try:
            bb = d.GetEffectiveShape().BBox()
        except Exception:                                       # noqa: BLE001
            continue
        h = (bb.GetHeight() if d.GetTextAngleDegrees() % 180 == 0
             else bb.GetWidth()) / MM
        size = d.GetTextHeight() / MM
        if size <= 0:
            continue
        (flat if all(c in FLAT for c in letters) else round_).append(
            (s, size, h / size))

    if not flat:
        print("FAIL  no all-flat-capital silk label found on %s -- this gate "
              "cannot measure anything, which is NOT a pass" % PCB)
        return 1

    rs = sorted(r for _s, _z, r in flat)
    lo, hi = rs[0], rs[-1]
    print("%d flat-capital label(s): ink height / KiCad size = %.4f .. %.4f"
          % (len(rs), lo, hi))
    if round_:
        q = sorted(r for _s, _z, r in round_)
        print("%d label(s) with round letters read %.4f .. %.4f -- overshoot, "
              "not a different cap height" % (len(q), q[0], q[-1]))

    if hi - lo > TOL:
        print("FAIL  the flat capitals do not agree with each other (%.4f over "
              "%.4f): something other than the face is varying" % (hi - lo, TOL))
        return 1
    got = (lo + hi) / 2.0
    if abs(got - DECLARED) > TOL:
        print("FAIL  the board plots a capital at %.4f of the text size; "
              "src/silk_face.py declares KICAD_CAP = %.4f (%.2f %% off). The "
              "CAD's lettering is that much the wrong height."
              % (got, DECLARED, abs(got - DECLARED) / got * 100.0))
        return 1
    print("ok    the board plots a capital at %.4f of the text size, which is "
          "the KICAD_CAP src/silk_face.py divides by" % got)
    return 0


if __name__ == "__main__":
    sys.exit(main())
