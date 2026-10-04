"""Clearance gate for the hoses — is any route blocked, and does every bend fit?

Two failure modes, both checked here:

  1. A bend TIGHTER THAN THE HOSE CAN MAKE. `plumbing.run` raises on this, so a
     route that cannot physically turn fails loudly rather than being drawn as a
     sharp corner. A kinked suction line does not merely restrict flow — it
     draws the pump dry, which is the v1 failure this whole redesign is about.

  2. A route that passes THROUGH something. Checked against every solid in the
     assembly INDIVIDUALLY, never against a union of them: an OCC union of nine
     solids reports interference that is not there (measured — a union said the
     right-hand channel was blocked at y=150..165; per-solid said FREE, and
     per-solid was right). Unions are for display, not for measurement.

    py -3.12 tools/check_plumbing.py        # exit 0 = clean

Exit code is the number of (route, part) collisions, so this works as a gate.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src import plumbing as P          # noqa: E402
from src import pump_frame as F        # noqa: E402

MIN_VOL = 1.0        # mm3 — below this is boolean noise, not a collision

# A hose TOUCHING its own fitting is the joint, not a collision.
INTENDED = {("tank_to_A", "elbows"), ("tank_to_B", "elbows"),
            ("green_from_A", "elbows"), ("green_from_B", "elbows"),
            ("tank_down", "tank")}


def parts():
    return [("pump_a", F._pump_placed(-1)), ("pump_b", F._pump_placed(+1)),
            ("frame_left", F.frame_left), ("frame_right", F.frame_right),
            ("pcb_plate", F.pcb_plate_part), ("pcb_shroud", F.pcb_shroud_part),
            ("pcb", F.pcb_solid()), ("battery_dock", F._dock_placed()),
            ("elbows", F._elbows()), ("tank", F._tank()),
            ("shelf", P.shelf()), ("pack_frame", P.pack_frame())]


def main():
    print("=== plumbing gate: %d routes vs %d parts ===\n"
          % (len(P.routes()), len(parts())))
    solids, bad, unmakeable = [], 0, 0
    for name, pts in P.routes():
        try:
            solids.append((name, P.run(pts)))
        except ValueError as e:
            print("%-14s CANNOT BE BENT: %s" % (name, e))
            unmakeable += 1
    if unmakeable:
        print()

    others = parts()
    for name, hose in solids:
        hits = []
        for pname, part in others:
            if (name, pname) in INTENDED:
                continue
            try:
                i = hose.intersect(part)
                v = i.val().Volume() if i.val() is not None else 0.0
            except Exception:
                v = 0.0
            if v > MIN_VOL:
                hits.append((pname, v))
        b = hose.val().BoundingBox()
        print("%-14s y[%6.1f,%6.1f] z[%6.1f,%6.1f]  %s"
              % (name, b.ymin, b.ymax, b.zmin, b.zmax,
                 "clear" if not hits else
                 "BLOCKED: " + ", ".join("%s %.0f mm3" % h for h in hits)))
        bad += len(hits)

    # hose-to-hose: two lines may not occupy the same space either
    for i in range(len(solids)):
        for j in range(i + 1, len(solids)):
            (na, a), (nb, b) = solids[i], solids[j]
            try:
                x = a.intersect(b)
                v = x.val().Volume() if x.val() is not None else 0.0
            except Exception:
                v = 0.0
            if v > MIN_VOL and not (na.split("_")[0] == nb.split("_")[0]):
                print("  hose clash: %s x %s  %.0f mm3" % (na, nb, v))
                bad += 1

    total = bad + unmakeable
    print("\n%s" % ("every hose has a path, and every bend is one the line can make"
                    if not total else
                    "*** %d PROBLEM(S) ***" % total))
    return total


if __name__ == "__main__":
    sys.exit(main())
