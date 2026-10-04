"""Does the BOM still describe the parts the CAD actually makes?

    py -3.12 tools/check_bom.py                # exit 0 = the BOM is current

WHY. bom_consolidated.md states two tables of generated fact and then buys
material against their totals: section 7b's printed-part volumes, and the lumber
cut list. Both are written by hand, nothing connected either to the models, and
both had drifted -- within one session, from edits made that same session:

  * cutting the Makita terminal window took 7 cm3 out of the housing and the
    lid's retention tab put 2.4 cm3 back, so the volume table was over by 5 cm3
    and the filament line by ~7 g;
  * adding the pump floor put three more planks in the cut list and shortened
    every post from 150 to 146, while the BOM still said "4 x post 150 mm",
    "1.63 m of beam" and "3 x 210 mm plank".

Neither announced itself. A volume is not something anyone notices by looking at
a part, and a cut list is read once, at the saw.

Small errors, both. Also the kind that only ever grow, and the fix is cheap:
read the tables, measure the models, compare.

Tolerances are deliberately loose -- 0.5 cm3 or 2% on volumes, 20 mm or 2% on
stock lengths -- because the BOM rounds on purpose. It is a shopping list, not a
measurement. This checks that it still DESCRIBES the design, not that it matches
to three decimals. Cut-list quantities and lengths are exact, though: those go
to a saw.

STOCK LENGTHS ARE NOT ON A PERCENTAGE. They were, at 2%, and that is 32 mm on
1.6 m of beam -- wider than the 16 mm that shortening four posts by 4 actually
moved it, so the gate passed the very drift it was written for. The BOM writes
metres to two decimals, so 10 mm is the rounding floor and STOCK_TOL is 15.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src import build as B                      # noqa: E402
from src import lumber_frame as L               # noqa: E402

BOM = pathlib.Path(__file__).resolve().parents[1] / "bom_consolidated.md"
ABS_TOL = 0.5          # cm3
REL_TOL = 0.02         # 2%
DENSITY = 1.23         # g/cm3, PCTG
STOCK_TOL = 15.0       # mm -- just over the BOM's 10 mm rounding floor

# The BOM names pieces for a human; lumber_frame names them for code. One place
# to say so.
CUT_NAMES = {"post": "post", "cross rail": "rail_cross", "side rail": "rail_side"}


def volumes(text):
    """{part: cm3} from the section 7b rows."""
    out = {}
    for m in re.finditer(r"^\|\s*`([A-Za-z0-9_]+)`\s*\|\s*([\d.]+)\s*cm", text, re.M):
        out[m.group(1)] = float(m.group(2))
    return out


def filament(text):
    """(grams, cm3) from the filament line, or None."""
    m = re.search(r"PCTG filament\D+([\d.]+)\s*g\*{0,2}\s*for the set\s*\(\s*"
                  r"([\d.]+)\s*cm", text)
    return (float(m.group(1)), float(m.group(2))) if m else None


def cuts(text):
    """{code_name: (qty, length_mm)} from the cut-list table."""
    out = {}
    # the cut-list table is INDENTED (it sits inside a list item), so the row
    # pattern has to allow leading whitespace -- "^\|" silently matched nothing.
    for m in re.finditer(r"^\s*\|\s*(\d+)\s*\|\s*([a-z ]+?)\s*\|\s*([\d.]+)\s*mm\s*\|",
                         text, re.M):
        name = CUT_NAMES.get(m.group(2))
        if name:
            out[name] = (int(m.group(1)), float(m.group(3)))
    return out


def check_volumes(text):
    claimed = volumes(text)
    actual = {n: part.val().Volume() / 1000.0 for n, part, _ in B.printed_parts()}
    bad = 0
    print("=== BOM section 7b vs the models ===")
    print("  %-22s %9s %9s %9s" % ("part", "BOM", "actual", "delta"))
    for n in sorted(actual):
        a = actual[n]
        if n not in claimed:
            print("  %-22s %9s %9.1f %9s  *** NOT IN THE BOM ***" % (n, "-", a, "-"))
            bad += 1
            continue
        c = claimed[n]
        ok = abs(a - c) <= max(ABS_TOL, REL_TOL * a)
        print("  %-22s %9.1f %9.1f %+9.1f%s"
              % (n, c, a, a - c, "" if ok else "  *** STALE ***"))
        bad += not ok
    for n in sorted(set(claimed) - set(actual)):
        print("  %-22s %9.1f %9s %9s  *** IN THE BOM, NOT BUILT ***"
              % (n, claimed[n], "-", "-"))
        bad += 1

    total = sum(actual.values())
    f = filament(text)
    print()
    if f is None:
        print("  could not read the filament line out of the BOM")
        return bad + 1
    g_claim, v_claim = f
    g_actual = total * DENSITY
    ok = (abs(total - v_claim) <= max(ABS_TOL, REL_TOL * total)
          and abs(g_actual - g_claim) <= max(5.0, REL_TOL * g_actual))
    print("  filament   BOM %.0f g / %.0f cm3   actual %.0f g / %.1f cm3   %s"
          % (g_claim, v_claim, g_actual, total, "ok" if ok else "*** STALE ***"))
    return bad + (not ok)


def check_cuts(text):
    claimed = cuts(text)
    actual = {nm: (n, ln) for (nm, ln), n in L.cut_list()}
    bad = 0
    print()
    print("=== BOM cut list vs src.lumber_frame ===")
    if not claimed:
        print("  could not read the cut-list table out of the BOM")
        return 1
    print("  %-14s %14s %14s" % ("piece", "BOM", "actual"))
    for nm in sorted(claimed):
        c, a = claimed[nm], actual.get(nm)
        if a is None:
            print("  %-14s %14s %14s  *** NOT BUILT ***"
                  % (nm, "%d x %.0f" % c, "-"))
            bad += 1
            continue
        ok = c == a
        print("  %-14s %14s %14s%s"
              % (nm, "%d x %.0f" % c, "%d x %.0f" % a,
                 "" if ok else "  *** STALE ***"))
        bad += not ok
    # a beam piece the BOM never lists at all
    for nm in sorted(set(actual) - set(claimed)):
        if nm.startswith("plank"):
            continue                      # planks are a prose line, checked below
        print("  %-14s %14s %14s  *** MISSING FROM THE CUT LIST ***"
              % (nm, "-", "%d x %.0f" % actual[nm]))
        bad += 1

    beam = sum(n * ln for (nm, ln), n in L.cut_list() if not nm.startswith("plank"))
    plank = sum(n * ln for (nm, ln), n in L.cut_list() if nm.startswith("plank"))
    m = re.search(r"38 \xd7 38 mm beam — ([\d.]+) m", text)
    if m:
        claim = float(m.group(1)) * 1000.0
        ok = abs(claim - beam) <= STOCK_TOL
        print("  %-14s %14s %11.0f mm%s"
              % ("beam stock", "%.2f m" % float(m.group(1)), beam,
                 "" if ok else "  *** STALE ***"))
        bad += not ok
    else:
        print("  could not read the beam stock line")
        bad += 1
    m = re.search(r"137 \xd7 20 mm plank — (\d+) \xd7 210", text)
    if m:
        claim = int(m.group(1)) * 210.0
        ok = abs(claim - plank) <= STOCK_TOL
        print("  %-14s %14s %11.0f mm%s"
              % ("plank stock", "%s x 210" % m.group(1), plank,
                 "" if ok else "  *** STALE ***"))
        bad += not ok
    else:
        print("  could not read the plank stock line")
        bad += 1
    return bad


def main():
    text = BOM.read_text(encoding="utf-8")
    bad = check_volumes(text) + check_cuts(text)
    print()
    print("%s" % ("the BOM still describes what the CAD makes" if not bad
                  else "*** %d BOM FIGURE(S) OUT OF DATE ***" % bad))
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
