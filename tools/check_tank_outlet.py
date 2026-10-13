# -*- coding: utf-8 -*-
"""The tank outlet: does the hose start where the fittings leave off, and can it
get from there to the tee?

WHAT THIS EXISTS FOR. `WORK_V2_PUNCHLIST` findings 16 and 19 both end on the
same sentence: nothing in this model knew that an inline fitting occupies
length, so "both will keep passing either layout". `src/tank_outlet.py` draws
the four rigid parts; this reads what they cost.

THREE CLAIMS, each FAILING rather than warning:

1. The hose starts at the FITTED fitting's barb tip. If `plumbing.tank_down`
   ever goes back to leaving the tank wall, this says so.
2. The route the hose is asked to make is one a hose can make — which is
   `plumbing._setbacks`' own judgement, re-asked here against the fitting's
   tip rather than against a point on the wall.
3. Both bought fittings are reported, not just the fitted one, because the
   owner has both and the choice is settled at the tank with the parts in hand.

⚠ WHAT IT DOES NOT CHECK is the drawing's dimension letters. `tank_outlet` says
plainly that TE 2088's A and C are matched to the two legs by value and not by
reading the geometry. A caliper settles that in two minutes, and this gate is
built so the CONSEQUENCE fails if the inference is wrong: get the legs wrong by
more than a few mm and the straight off the barb, or the arrival angle, moves
past what is declared below.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import plumbing as P          # noqa: E402
from src import tank_outlet as TO      # noqa: E402

# What the as-built route is signed for. Measured, so a change is visible.
MIN_STRAIGHT_OFF_BARB = 45.0      # mm of dead-straight vinyl before any bend
MAX_TEE_ANGLE         = 38.9      # deg off the tee's axis -- green_from_B's
                                  # accepted figure, and this must not be worse

# ⚠ AND A TWO-SIDED ONE, BECAUSE THE FIRST VERSION OF THIS GATE DID NOT CATCH
# ITS OWN HEADLINE CASE. The two bounds above are one-sided, so making the
# elbow's thread leg LONGER improves both of them: a 20 mm error in the
# drawing's letter mapping -- the exact thing this file warns about -- moved the
# corner from y 229.2 to 249.3 and the arrival from 30.3 to 12.8 deg, and the
# gate passed. A figure that can only fail in one direction is not measured, it
# is bounded. The corner's own position is declared instead, to the drawing's
# own X.XX tolerance doubled, and it is the figure that matters: it is where
# the hose's vertical axis sits, and how much of PLENUM_Y the stack has eaten.
ELBOW_CORNER_Y    = 229.2
CORNER_Y_TOL      = 2.0


def _angle_at_tee(pts):
    """How far off the tee's own axis the hose arrives, in degrees."""
    a, b = pts[-2], pts[-1]
    v = [b[i] - a[i] for i in range(3)]
    n = math.sqrt(sum(c * c for c in v))
    return math.degrees(math.acos(abs(v[2]) / n)) if n else 0.0


def _route_for(tip):
    return [tip, (P.UNISEAL_X, tip[1], P.TANK_SLOPE_Z), P.TANK_TEE]


def main():
    bad = 0
    print("=== tank outlet: four rigid parts, then the hose ===")
    print("  the wall is at y %.1f; the FNPT face the fitting screws to is at y %.1f"
          % (TO.WALL_Y, TO.FNPT_FACE_Y))

    # ── 1. the hose starts at the barb ──────────────────────────────────────
    tank_down = dict(P.routes())["tank_down"]
    tip = TO.hose_start()
    if tuple(round(c, 3) for c in tank_down[0]) != tuple(round(c, 3) for c in tip):
        print("  *** tank_down STARTS AT %s, NOT AT THE BARB %s ***"
              % (tuple(round(c, 1) for c in tank_down[0]),
                 tuple(round(c, 1) for c in tip)))
        bad += 1
    else:
        print("  tank_down starts at the barb tip (%.1f, %.1f, %.1f), %.1f mm "
              "out from the wall" % (tip + (tip[1] - TO.WALL_Y,)))

    # ── 2 and 3. what each bought fitting leaves ────────────────────────────
    print("\n  fitting                 barb tip        straight off   arrives at")
    print("                          (y, z)          the barb       the tee")
    for name, tip_of in (("62043 elbow   TE2088/P",
                          (TO.AXIS_X, TO.ELBOW_CORNER_Y, TO.ELBOW_TIP_Z)),
                         ("62017 straight TA1088/P",
                          (TO.AXIS_X, TO.STRAIGHT_TIP_Y, TO.AXIS_Z))):
        pts = _route_for(tip_of)
        try:
            sb = P._setbacks(pts, P.BEND_R, P.TUBE_OD)
        except ValueError as exc:
            print("  %-23s (%.1f, %.1f)   NO ROUTE: %s"
                  % (name, tip_of[1], tip_of[2], str(exc)[:60]))
            if TO.FITTING in name:
                bad += 1
            continue
        first = math.dist(pts[0], pts[1]) - sb[1]
        ang = _angle_at_tee(pts)
        fitted = ("elbow" if "elbow" in name else "straight") == TO.FITTING
        print("  %-23s (%6.1f, %5.1f)  %6.1f mm      %5.1f deg %s"
              % (name, tip_of[1], tip_of[2], first, ang,
                 "   <- FITTED" if fitted else ""))
        if not fitted:
            continue
        if first < MIN_STRAIGHT_OFF_BARB:
            print("  *** only %.1f mm of straight off the barb, against %.1f "
                  "declared ***" % (first, MIN_STRAIGHT_OFF_BARB))
            bad += 1
        if ang > MAX_TEE_ANGLE + 1e-6:
            print("  *** arrives %.1f deg off the tee axis, against %.1f "
                  "declared ***" % (ang, MAX_TEE_ANGLE))
            bad += 1

    # ── the corner's own position, both ways ───────────────────────────────
    dy = TO.ELBOW_CORNER_Y - ELBOW_CORNER_Y
    if abs(dy) > CORNER_Y_TOL:
        print("\n  *** THE ELBOW'S CORNER IS AT y %.1f, DECLARED %.1f (%+.1f) ***"
              % (TO.ELBOW_CORNER_Y, ELBOW_CORNER_Y, dy))
        print("      That is the hose's vertical axis moving. Re-measure the "
              "part and re-sign this figure;")
        print("      do not widen the tolerance to make it pass.")
        bad += 1
    else:
        print("\n  the elbow's corner is at y %.1f, declared %.1f (%+.1f mm)"
              % (TO.ELBOW_CORNER_Y, ELBOW_CORNER_Y, dy))
    reach = TO.ELBOW_CORNER_Y + P.TUBE_OD / 2.0
    if reach > P.PLENUM_Y:
        print("  *** THE STACK REACHES y %.1f, PAST THE PLENUM AT %.1f ***"
              % (reach, P.PLENUM_Y))
        bad += 1

    # ── the correction to finding 19, measured rather than asserted ─────────
    sq = P.TANK_TEE[1] - TO.ELBOW_CORNER_Y
    print("\n  !! FINDING 19 SAID THE ELBOW LEAVES 51 mm ON THE BOTTOM LEG "
          "AND 'FITS, AND ONLY JUST'.")
    print("     It measured from the FNPT face at y %.0f. The hose's vertical "
          "axis is not there:" % TO.FNPT_FACE_Y)
    print("     the elbow's own thread leg (%.1f mm) carries the corner out to "
          "y %.1f, which leaves" % (TO.ELBOW_LEG_THREAD, TO.ELBOW_CORNER_Y))
    print("     %.1f mm against the %.0f a square bend needs -- short by %.1f, "
          "not spare by 1." % (sq, P.BEND_R, P.BEND_R - sq))
    print("     So the line is SLOPED into the tee instead of turned square, "
          "which is what the")
    print("     hose does anyway and what green_from_B was already accepted "
          "for.")

    # ── what finding 16's strainer actually has to fit in ──────────────────
    # That finding measured the tank leg at "~100 mm" between TANK_TEE and the
    # Uniseal and sized a strainer against it. Two things were not in that sum,
    # and both are drawn now: the tee's own branch at one end and the whole
    # fitting stack at the other. What is left is what the tape measure has to
    # beat.
    from src import tees as TEE                                    # noqa: E402
    leg_top = TO.hose_start()[2]
    leg_bot = TEE.branch_end("tee_tank")[2]
    print("\n  the tank leg, between the two things now drawn at its ends:")
    print("    the tee's branch ends at z %.1f, the elbow's barb at z %.1f "
          "-- %.1f mm of hose" % (leg_bot, leg_top, leg_top - leg_bot))
    print("    finding 16 called this leg ~100 mm. Neither the tee's own branch"
          " (%.1f mm) nor the" % TEE.TEE_BRANCH)
    print("    outlet stack was in that sum. THE STRAINER IS STILL NOT DRAWN "
          "AND ITS LENGTH IS STILL")
    print("    NOT MEASURED -- finding 16 stays open, and this is the budget "
          "it has to come in under.")

    print("\n%s" % ("the hose starts where the fittings leave off, and the "
                    "route is one it can make" if not bad
                    else "*** THE TANK OUTLET DOES NOT ADD UP ***"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
