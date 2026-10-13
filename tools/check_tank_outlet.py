# -*- coding: utf-8 -*-
"""The tank outlet: does the hose start where the fittings leave off, and does
it get to the tee without being bent by one of them?

WHAT THIS EXISTS FOR. `WORK_V2_PUNCHLIST` findings 16 and 19 both end on the
same sentence: nothing in this model knew that an inline fitting occupies
length, so "both will keep passing either layout". `src/tank_outlet.py` draws
the four rigid parts and `src/tees.py` the tee at the other end; this reads
what they cost between them.

WHAT CHANGED WHEN THE TEE WAS DRAWN. The route used to run from the elbow's
barb to the tee's CENTRE POINT, with a bend in the middle of it placed by
`plumbing.TANK_SLOPE_Z`, and this file measured that bend's two consequences
against declared ceilings. Both of those figures have gone, because the bend
has: the elbow's corner only sat 32.8 mm behind the tee's axis because the PVC
stub holding it out from the wall was 25 mm, and the stub is a piece of pipe
CUT WITH A HACKSAW. Cut it 57.8 and the corner lands on the tee's axis, and the
tank line is one dead-straight drop. So what is declared below is no longer a
bend's price -- it is the cut length that buys the straightness, two-sided, so
that the straightness cannot quietly come back as a slope.

FIVE CLAIMS, each FAILING rather than warning:

1. The hose begins ON the elbow's barb (not at its tip: the vinyl swallows it)
   and ends at the tee's BRANCH tip, not at the tee's centre.
2. The drop is STRAIGHT: one segment, and it leaves the fitting along the
   fitting's own axis. This is the claim that fails if `FITTING` is flipped to
   the straight 62017, which points +Y and would need a 90 degree turn in the
   8 mm it has.
3. The stub is cut to the length that makes claim 2 true, and that length is
   the one `bom_consolidated.md` has to say out loud.
4. The stack's reach past the plenum line is what the elbow's own body is, and
   nothing more.
5. On the four plenum runs the bend begins PAST the tee's barb and the hose
   arrives along it. !! THIS ONE IS RED, and is meant to be: finding 68.

!! WHAT IT DOES NOT CHECK is the drawing's dimension letters. `tank_outlet`
says plainly that TE 2088's A and C are matched to the two legs by value and
not by reading the geometry. A caliper settles that in two minutes, and this
gate is built so the CONSEQUENCE fails if the inference is wrong: the legs set
where the corner lands, and claim 3 is two-sided about that.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import plumbing as P          # noqa: E402
from src import tank_outlet as TO      # noqa: E402
from src import tees as TEE            # noqa: E402

# ── What the as-built stack is signed for ──────────────────────────────────
# !! EVERY ONE OF THESE IS TWO-SIDED, AND THAT IS NOT STYLE. The first version
# of this gate did not catch its own headline case: its two bounds were floors,
# so making the elbow's thread leg LONGER -- a 20 mm error in exactly the
# letter mapping the docstring warns about -- improved both of them and the
# gate passed. A figure that can only fail in one direction is not measured, it
# is bounded.
STUB_CUT          = 57.8      # mm of PVC proud of the tank wall. THE OWNER CUTS
STUB_TOL          = 0.3       # this one with a saw; it is in the BOM.
CORNER_TOL        = 0.05      # the corner lands ON PLENUM_Y, or it does not
MAX_OFF_AXIS      = 0.5       # deg between the hose's first run and the
                              # fitting's own outlet axis -- i.e. straight
DROP_FREE_VINYL   = 87.5      # mm from the barb's tip to the branch's tip
DROP_TOL          = 1.0
STACK_REACH_TOL   = 0.1


def _twosided(label, got, want, tol, note=""):
    """Returns 1 and says so if `got` has moved either way off `want`."""
    if abs(got - want) <= tol:
        print("  %-46s %8.2f  (declared %.2f%s)" % (label, got, want,
                                                    ", +-%.2f" % tol))
        return 0
    print("  *** %s IS %.2f, DECLARED %.2f (%+.2f) ***" % (label.upper(), got,
                                                           want, got - want))
    if note:
        print("      %s" % note)
    print("      Re-measure the part and re-sign the figure; do not widen the "
          "tolerance to make it pass.")
    return 1


def _angle(v, axis):
    n = math.sqrt(sum(c * c for c in v))
    return math.degrees(math.acos(min(1.0, abs(v[axis]) / n))) if n else 0.0


def main():
    bad = 0
    routes = dict(P.routes())
    print("=== tank outlet: four rigid parts, a tee, and one straight drop ===")
    print("  the wall is at y %.1f; the FNPT face the fitting screws to is at "
          "y %.1f" % (TO.WALL_Y, TO.FNPT_FACE_Y))

    # ── 1. the hose begins on the barb and ends on the branch ───────────────
    print("\n  -- 1. where the vinyl starts and stops --")
    drop = routes["tank_down"]
    start, end = TO.hose_start(), TEE.branch_end("tee_tank")
    for what, got, want in (("starts", drop[0], start), ("ends", drop[-1], end)):
        if tuple(round(c, 3) for c in got) != tuple(round(c, 3) for c in want):
            print("  *** tank_down %s AT %s, NOT AT %s ***"
                  % (what, tuple(round(c, 1) for c in got),
                     tuple(round(c, 1) for c in want)))
            bad += 1
    if not bad:
        print("  tank_down runs (%.1f, %.1f, %.1f) -> (%.1f, %.1f, %.1f)"
              % (start + end))
        print("    the top %.1f mm of that is over the elbow's barb, which "
              "holds it straight" % TO.BARB_SWALLOW)
        print("    the bottom of it is the tee's BRANCH tip, not the tee: the "
              "branch is male NPT")
        print("    and carries a strainer, so no vinyl touches the tee there "
              "at all.")

    # ── 2. the drop is straight, and leaves the fitting on its own axis ─────
    print("\n  -- 2. the drop has no bend in it --")
    if len(drop) != 2:
        print("  *** tank_down HAS %d POINTS, SO IT HAS %d BEND(S) ***"
              % (len(drop), len(drop) - 2))
        bad += 1
    v = [drop[1][i] - drop[0][i] for i in range(3)]
    # the elbow's barb points -Z; the straight's points +Y
    axis = 2 if TO.FITTING == "elbow" else 1
    off = _angle(v, axis)
    bad += _twosided("the line leaves the %s on its own axis, deg"
                     % TO.FITTING, off, 0.0, MAX_OFF_AXIS,
                     "A hose leaves a barb along the barb. Anything else is "
                     "the FITTING being bent,")
    bad += _twosided("free vinyl, barb tip to branch tip, mm",
                     TO.barb_tip()[2] - end[2], DROP_FREE_VINYL, DROP_TOL)

    # ── 3. the cut that buys it ─────────────────────────────────────────────
    print("\n  -- 3. the stub is cut to the length that makes 2 true --")
    bad += _twosided("the elbow's corner lands on PLENUM_Y, y",
                     TO.ELBOW_CORNER_Y, P.PLENUM_Y, CORNER_TOL,
                     "This is the hose's whole vertical axis moving off the "
                     "tee's.")
    bad += _twosided("PVC stub, cut proud of the tank wall, mm",
                     TO.STUB_PROUD, STUB_CUT, STUB_TOL,
                     "bom_consolidated.md states this cut length. If it moves, "
                     "the BOM is wrong too.")

    # ── 4. what the stack sticks out past the plenum ────────────────────────
    print("\n  -- 4. how far the stack reaches --")
    reach = TO.ELBOW_CORNER_Y + TO.ELBOW_HEX / 2.0
    bad += _twosided("the elbow's +Y face, y", reach,
                     P.PLENUM_Y + TO.ELBOW_HEX / 2.0, STACK_REACH_TOL)
    print("    %.1f mm past the plenum line, against the %.1f the hoses on it "
          "already stand proud" % (reach - P.PLENUM_Y, P.TUBE_OD / 2.0))
    print("    (the shelf is 250 deep and everything here is in front of it; "
          "overhang in +Y costs")
    print("     moment and nothing else -- src/plumbing.py's own rule for the "
          "plenum.)")

    # ── 5. the plenum runs: is the bend ON the barb? ────────────────────────
    # !! THE FIRST VERSION OF THIS CLAIM PASSED A HOSE THAT CANNOT EXIST. It
    # measured the straight from the corner to the tee's flats and asked for
    # BEND_R of it -- and got 51.1 against 50, "spare +1.08". But the last
    # 20 mm of that straight is not free vinyl, it is vinyl with a rigid barb
    # inside it. A bend that starts 1 mm off the flats is a bend with a
    # straight barb through it, and the viewer drew exactly that: the barb's
    # tip standing out of the outside of every curve. The owner's words were
    # "the tubes don't fit into the tees properly", and they do not.
    #
    # What a run needs is the barb's own length of DEAD STRAIGHT hose past the
    # flats before the bend begins, and to arrive along the barb's axis.
    barb = TEE.TEE_RUN_HALF - TEE.TEE_HEX / 2.0
    print("\n  -- 5. the four plenum runs: where the bend begins, against "
          "the barb --")
    print("    a run barb is %.1f mm long; the hose over it cannot bend, and "
          "cannot arrive askew" % barb)
    print("    run             straight past the flats   needs   short by   "
          "off the barb's axis")
    for name in ("tank_to_A", "tank_to_B", "green_from_A", "green_from_B"):
        pts = routes[name]
        try:
            sb = P._setbacks(pts, P.BEND_R, P.TUBE_OD)
        except ValueError as exc:
            print("    %-15s NO ROUTE: %s" % (name, str(exc)[:70]))
            bad += 1
            continue
        free = math.dist(pts[-2], pts[-1]) - sb[-2] - sb[-1]
        v = [pts[-1][i] - pts[-2][i] for i in range(3)]
        off = _angle(v, 0)
        short = barb - free
        ok = short <= 0.0 and off <= MAX_OFF_AXIS
        print("    %-15s %10.1f mm          %5.1f   %7.1f     %5.1f deg   %s"
              % (name, free, barb, max(short, 0.0), off,
                 "" if ok else "*** DOES NOT FIT ***"))
        bad += 0 if ok else 1
    print("    WHY, IN ONE SUM: the pumps' legs stand 125 mm apart and each "
          "tee joins one inner")
    print("    and one outer. A run along X needs, per side, half a body "
          "(%.1f) + a barb (%.1f)" % (TEE.TEE_HEX / 2.0, barb))
    print("    + a bend (%.0f) = %.0f mm, twice: %.0f. There are 125. It was "
          "never a drawing fault;" % (P.BEND_R, TEE.TEE_HEX / 2.0 + barb
                                      + P.BEND_R,
                                      2 * (TEE.TEE_HEX / 2.0 + barb + P.BEND_R)))
    print("    the layout was chosen while the tee was a point. "
          "WORK_V2_PUNCHLIST finding 68, OPEN.")

    # ── what finding 16's strainer has to fit in ────────────────────────────
    print("\n  the tank leg, between the two things now drawn at its ends:")
    print("    %.1f mm of free vinyl, and a strainer somewhere in it."
          % (TO.barb_tip()[2] - end[2]))
    print("    finding 16 called this leg ~100 mm. Neither the tee's own "
          "branch (%.1f mm) nor the" % TEE.TEE_BRANCH)
    print("    outlet stack was in that sum. THE STRAINER IS STILL NOT DRAWN "
          "AND ITS LENGTH IS STILL")
    print("    NOT MEASURED -- finding 16 stays open, and this is the budget "
          "it has to come in under.")

    # ── the correction to finding 19 ───────────────────────────────────────
    print("\n  !! FINDING 19 SAID THE ELBOW LEAVES 51 mm ON THE BOTTOM LEG AND "
          "'FITS, AND ONLY JUST'.")
    print("     It measured from the FNPT face, and the hose's vertical axis "
          "is not there -- the")
    print("     elbow's own thread leg (%.1f mm) carries the corner out past "
          "it. With the stub at" % TO.ELBOW_LEG_THREAD)
    print("     25 mm that landed at y 229.2 and the drop had to slope. The "
          "stub is cut, not bought,")
    print("     so it is %.1f now and the leg is straight. Finding 19 read the "
          "arithmetic right and" % TO.STUB_PROUD)
    print("     the free variable wrong.")

    print("\n%s" % ("the hose starts where the fittings leave off, stops where "
                    "the next one starts, and"
                    "\nruns straight between them"
                    if not bad else "*** THE TANK OUTLET DOES NOT ADD UP ***"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
