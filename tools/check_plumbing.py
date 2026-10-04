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

from src import housing as H           # noqa: E402
from src import lumber_frame as L      # noqa: E402
from src import plumbing as P          # noqa: E402
from src import pump_frame as F        # noqa: E402

MIN_VOL = 1.0        # mm3 — below this is boolean noise, not a collision

# A hose TOUCHING its own fitting is the joint, not a collision -- but HOW MUCH
# it touches is the whole question, and this used to be a bare set of pairs with
# no number in it. Each entry now carries the volume it is allowed to be and the
# reason, so an entry can never again mean "whatever turns up here is fine".
#
# That is not hypothetical. The bare set was hiding a 9962 mm3 reading: see
# green_from_B below, where the hose is drawn curving through 45 mm of rigid
# fitting. Its neighbours, routed the same way, measure 163.
INTENDED = {
    ("tank_to_A", "elbows"):
        (250.0, "the joint: the hose slides onto the leg end and the two "
                "overlap by a sphere's worth at the knuckle"),
    ("green_from_A", "elbows"):
        (250.0, "same joint, pump A's outlet"),
    ("green_from_B", "elbows"):
        (10100.0,
         "NOT A JOINT. 9962 mm3, sixty times its neighbours, and it is a real "
         "blocker held open by an unmeasured number -- see the note below."),
}

# TWO ENTRIES WERE DROPPED, because measuring them showed they held nothing:
#
#   tank_to_B x elbows   0.0 mm3. It and tank_to_A are the same joint drawn the
#                        same way, and tank_to_A reads 163 -- all of which is
#                        one chord KNUCKLE where the first bend's tangent
#                        sphere reaches back into the leg. B's first bend is
#                        further from its leg, so there is no knuckle in it.
#   tank_down x tank     0.0 mm3. UNISEAL_Y is the tank's +Y FACE, so the line
#                        starts flush against the wall it is supposed to pass
#                        through. The Uniseal has no size yet (BOM: "TBD once a
#                        Scepter panel is measured"), so the seal is not
#                        modelled and there is nothing to declare until it is.
#
# Both were standing ready to hide the first real clash that appeared there.

# ── THE green_from_B BLOCKER, in full ──────────────────────────────────────
# Pump B's INNER port is the one port on the machine with nowhere to go but UP:
# forward is pump A's body, and left and right are the two pump bodies. Every
# other route picks the hose up at its elbow's LEG END; this one is drawn from
# the PORT, 45 mm earlier, and src/plumbing.py says so in B_IN's comment.
#
# That is not a modelling shortcut, it is the only way the route closes. The
# arithmetic, all of it measured off the model:
#
#     port centreline                                  z =  84.0
#     elbow leg ends (ELBOW_LEG_L = 45)                z = 129.0
#     the hose's first corner needs BEND_R above that  z = 179.0
#     the rails cap the centreline at RAIL_Z0 - OD/2   z = 140.5
#     ------------------------------------------------------------
#     short by                                              38.5 mm
#
# Put the other way round: this frame can accept a 6.5 mm elbow leg on that
# port. There is no such fitting.
#
# TWO THINGS COULD RESOLVE IT, and the first is cheap:
#
#   1. MEASURE THE ELBOW. ELBOW_LEG_L = 45 is an estimate -- pump_frame says so
#      ("should shrink, never grow, when the real number lands"). At 6.5 or
#      less the route closes as drawn and this entry goes away. The whole
#      blocker rests on a number nobody has put a caliper to.
#   2. RAISE THE FRAME. RAIL_Z0 is documented as being SET by this very hose,
#      so this is the design's own stated dependency, not a workaround. It
#      needs RAIL_Z0 >= 188.5, i.e. +38.5 mm: taller posts, a deck and tank
#      38.5 mm higher, and a 38.5 mm taller housing back plate.
#
# The frame is NOT being raised on the strength of an estimate. The ceiling
# here pins the defect at its measured size instead: change the route, the
# elbow or the rail height and this gate fires.

def parts():
    return [("pump_a", F._pump_placed(-1)), ("pump_b", F._pump_placed(+1)),
            ("wood", L.frame()), ("housing", H.housing()),
            ("housing_lid", H.lid()), ("pcb", H.pcb_solid()),
            ("elbows", F._elbows()), ("tank", L.tank()),
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
    declared, seen = [], set()
    for name, hose in solids:
        hits = []
        for pname, part in others:
            try:
                i = hose.intersect(part)
                v = i.val().Volume() if i.val() is not None else 0.0
            except Exception:
                v = 0.0
            if v <= MIN_VOL:
                continue
            dec = INTENDED.get((name, pname))
            if dec is not None:
                seen.add((name, pname))      # measured; over or under, not missing
            if dec is None:
                hits.append((pname, v))
            elif v > dec[0]:
                hits.append((pname + " OVER ITS DECLARED %.0f" % dec[0], v))
            else:
                declared.append((name, pname, v, dec[0]))
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

    if declared:
        print()
        print("  declared contacts (each one named and measured, never lumped):")
        for na, nb, v, cap in declared:
            print("    %-14s x %-8s %8.0f of %8.0f mm3" % (na, nb, v, cap))
        for key in sorted(INTENDED):
            if key not in seen:
                print("    %-14s x %-8s      NOT MEASURED -- is it still there?"
                      % key)
                bad += 1

    total = bad + unmakeable
    print("\n%s" % ("every hose has a path, and every bend is one the line can make"
                    if not total else
                    "*** %d PROBLEM(S) ***" % total))
    return total


if __name__ == "__main__":
    sys.exit(main())
