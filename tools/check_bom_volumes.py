"""Does the BOM still describe the parts the CAD actually makes?

    py -3.12 tools/check_bom_volumes.py        # exit 0 = the table is current

WHY. bom_consolidated.md section 7b states a volume per printed part and then
buys filament against their total. Nothing connected those numbers to the
models, and they had already drifted: cutting the Makita terminal window took
7 cm3 out of the housing and the lid's retention tab put 2.4 cm3 back, so the
table was over by 5 cm3 and the filament line by ~7 g within a day of both
edits. Neither change announced itself, because a volume is not something you
notice by looking at a part.

It is a small error. It is also the kind that only ever grows, and the fix is
cheap: read the table, measure the models, compare.

The tolerance is deliberately loose (0.5 cm3 or 2%, whichever is larger). The
BOM rounds to whole cm3 on purpose -- it is a shopping list, not a measurement
-- so this is checking that the table still DESCRIBES the part, not that it
matches to three decimals.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src import build as B                      # noqa: E402

BOM = pathlib.Path(__file__).resolve().parents[1] / "bom_consolidated.md"
ABS_TOL = 0.5          # cm3
REL_TOL = 0.02         # 2%
DENSITY = 1.23         # g/cm3, PCTG


def table(text):
    """{part: cm3} from the section 7b rows."""
    out = {}
    for m in re.finditer(r"^\|\s*`([A-Za-z0-9_]+)`\s*\|\s*([\d.]+)\s*cm", text,
                         re.M):
        out[m.group(1)] = float(m.group(2))
    return out


def filament(text):
    """(grams, cm3) from the filament line, or None."""
    m = re.search(r"PCTG filament\D+([\d.]+)\s*g\**\s*for the set\s*\(\s*"
                  r"([\d.]+)\s*cm", text)
    return (float(m.group(1)), float(m.group(2))) if m else None


def main():
    text = BOM.read_text(encoding="utf-8")
    claimed = table(text)
    actual = {n: part.val().Volume() / 1000.0 for n, part, _ in B.printed_parts()}
    bad = 0

    print("=== BOM section 7b vs the models ===")
    print("  %-22s %9s %9s %9s" % ("part", "BOM", "actual", "delta"))
    for n in sorted(actual):
        a = actual[n]
        if n not in claimed:
            print("  %-22s %9s %9.1f %9s  *** NOT IN THE BOM ***"
                  % (n, "-", a, "-"))
            bad += 1
            continue
        c = claimed[n]
        tol = max(ABS_TOL, REL_TOL * a)
        ok = abs(a - c) <= tol
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
        bad += 1
    else:
        g_claim, v_claim = f
        g_actual = total * DENSITY
        tol_v = max(ABS_TOL, REL_TOL * total)
        ok = abs(total - v_claim) <= tol_v and abs(g_actual - g_claim) <= max(
            5.0, REL_TOL * g_actual)
        print("  filament   BOM %.0f g / %.0f cm3   actual %.0f g / %.1f cm3   %s"
              % (g_claim, v_claim, g_actual, total, "ok" if ok else "*** STALE ***"))
        bad += not ok

    print("\n%s" % ("the BOM still describes what the CAD makes" if not bad
                    else "*** %d BOM FIGURE(S) OUT OF DATE ***" % bad))
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
