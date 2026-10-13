"""Pack frame + tube routing — does the plumbing have a path that isn't blocked?

The frame CAD proves the STRUCTURE fits. It says nothing about whether a hose
can actually get from each pump port to where it has to go, and a 1/2" vinyl
line is not a line — it is a 19 mm cylinder that cannot turn tighter than about
50 mm. A route that looks obvious in plan can be impossible in the solid.

So this models the hoses as SOLIDS, with their real OD and their real bend
radius, and runs them through the same interference check as everything else.
`_setbacks` RAISES when a straight is too short to hold the bends at BOTH of its
ends, so a route that cannot physically turn fails loudly instead of being drawn
as a corner no hose can make.

WHAT IS MODELLED AS REFERENCE (not printed, not bought)
-------------------------------------------------------
The pack's back frame (820 x 400) and its shelf (340 x 250), placed against
y=0, because "is the path blocked" has no answer without the thing the whole
assembly is strapped to. These are the user's measurements.

THE PLENUM
----------
There is almost no room INSIDE the frame. The pumps span y=2..208 of a 210 mm
frame and meet each other at x=0, so the only gaps are two 27 mm slots outboard
of the pumps (x=|125|..152, against the posts) and 5 mm over their tops. A
27 mm slot cannot host a 50 mm bend in plan, so routing inside the frame is out.

Everything therefore happens in FRONT: the band at y > FRAME_D, over the shelf
(which is 250 deep against the frame's 210) and clear of the tank (y=0..173).
Hoses are not load-bearing, so they may overhang the shelf in +Y; this is the
one direction where overhang costs nothing but moment.

WHICH PORT IS WHICH
-------------------
Pump B is rotated 180 deg about Z, so the port that is at the pump's local +X
lands at world x=0 on BOTH pumps: the two INLETS are the inner pair and the two
OUTLETS the outer pair. With A running tank->wand and B running wand->tank:

    A inner  = A inlet  = TANK        A outer  = A outlet = GREEN
    B inner  = B inlet  = GREEN       B outer  = B outlet = TANK

so the tank tee lands on +X and the green tee on -X, each joining one inner and
one outer port. That split is a consequence of the flip, not a choice.

Run:  py -3.12 -m src.plumbing
"""
from __future__ import annotations

import math
import pathlib

import cadquery as cq

from . import lumber_frame as L
from . import pump_frame as F

OUT = pathlib.Path(__file__).resolve().parent.parent

# ── The pack, from the user's measurements ──────────────────────────────────
PACK_W, PACK_H = 400.0, 820.0     # back frame, as worn
PACK_T         = 20.0             # frame thickness — ESTIMATE, not measured
SHELF_T        = 8.0              # matches pump_frame._shelf

# ── Tube ────────────────────────────────────────────────────────────────────
# 1/2" ID vinyl is 3/4" OD. BEND_R is from the BOM's own note (1/2" vinyl bends
# to ~50 mm); kink tighter than this and the line closes, which on the SUCTION
# side does not merely restrict flow, it draws the pump dry.
TUBE_ID, TUBE_OD = 12.7, 19.05
BEND_R           = 50.0

# ── Uniseal on the tank ─────────────────────────────────────────────────────
# NOT MEASURED — the panel has not been chosen yet (BOM: "size TBD once a
# Scepter panel is measured"). Modelled on the tank's +Y face, as low as a seal
# can sit, so the route is checked against SOMETHING concrete rather than left
# undrawn. Moving it changes only these three numbers.
UNISEAL_X = 73.0                  # in line with the tank tee, so the drop is straight
# Keyed off the LUMBER deck, not the old printed one. When the frame became
# wood the deck rose from 188 to 208, and the tank line kept its old height and
# ploughed 1343 mm3 through the deck planks — caught by the clearance report,
# which is why the height is derived here rather than written down twice.
UNISEAL_Z = L.DECK_Z + 26.0       # seal needs wall either side of the bore
UNISEAL_Y = F.TANK_D              # 173 — the tank's +Y face

# The X-runs sit 50 mm clear of the frame front because that is exactly what a
# 90 deg bend costs: pump A's legs end at y=206, and a 50 mm radius needs 50 mm
# of straight on BOTH sides of the corner. This is the number that decides how
# deep the pack gets, and it is set by the hose, not by the frame.
# 262, not 256: at 256 the green line's drop clipped the shelf's front edge by
# 290 mm3 (the shelf is 250 deep and a 19 mm hose is 9.5 mm either side). The
# X-runs now clear the shelf entirely rather than resting on its corner.
PLENUM_Y  = 262.0

# Where the tank line takes its one bend, on the way down from the elbow's
# barb. Chosen, and the two things it trades off are both measured: at 140 the
# hose leaves the barb with 49.7 mm of dead-straight vinyl -- about the 50 mm a
# bend wants on each side, so the fitting is never the thing being bent -- and
# arrives at the tee 30.3 deg off its axis. Lower buys more straight off the
# barb and a steeper arrival; higher does the reverse.
TANK_SLOPE_Z = 140.0


def _seg(p0, p1, r):
    """One straight length of tube as a cylinder from p0 to p1."""
    d = cq.Vector(*[b - a for a, b in zip(p0, p1)])
    L = d.Length
    if L < 1e-9:
        return None
    return cq.Workplane(obj=cq.Solid.makeCylinder(
        r, L, cq.Vector(*p0), d.normalized()))


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def _bend(p_prev, p_corner, p_next, radius):
    """One corner's constant-radius bend: (setback, tangent_in, arc mid, tangent_out).

    NO LENGTH CHECK HAPPENS HERE, and that is the point — see `_setbacks`. A
    corner cannot decide whether it fits, because it does not know how much of
    the straight beside it the NEXT corner is going to spend.
    """
    d_in  = _unit([c - p for p, c in zip(p_prev, p_corner)])
    d_out = _unit([n - c for c, n in zip(p_corner, p_next)])
    cosang = max(-1.0, min(1.0, sum(a * b for a, b in zip(d_in, d_out))))
    turn = math.acos(cosang)                       # 0 = straight through
    if turn < 1e-6:
        return 0.0, p_corner, p_corner, p_corner
    setback = radius * math.tan(turn / 2.0)
    t_in  = tuple(c - setback * d for c, d in zip(p_corner, d_in))
    t_out = tuple(c + setback * d for c, d in zip(p_corner, d_out))
    perp = _unit([o - i * cosang for i, o in zip(d_in, d_out)])
    ctr = tuple(t + radius * p for t, p in zip(t_in, perp))
    w = [-p for p in perp]                         # unit: ctr -> t_in
    half = turn / 2.0
    mid = tuple(c + radius * (math.cos(half) * wi + math.sin(half) * ti)
                for c, wi, ti in zip(ctr, w, d_in))
    return setback, t_in, mid, t_out


def _setbacks(points, radius, od):
    """Every corner's setback, CHECKED AGAINST THE STRAIGHT IT SHARES.

    ⚠ THE CHECK THIS REPLACES ASKED EACH CORNER ON ITS OWN, and the drawing is
    what gave it away. It compared one corner's setback with the whole distance
    to the next CORNER, so two 90 degree bends 50 mm apart on a 50 mm radius
    both passed — each spending the same 50 mm of straight, twice over. What
    came out was `green_from_B` descending z 134 -> 84 and then JUMPING BACK UP
    to 134 to start the second bend: the "down, then up, then down again" the
    owner could see in the viewer. The gate was green the whole time.

    A straight is spent from BOTH ENDS, so the two setbacks either side of it
    have to fit in it TOGETHER. The first and last legs have a free end (a run
    ENDS at a barb, which is not a bend), so their far setback is zero.

    And this is not a drawing nicety: the hose really cannot do it. Two 90
    degree bends on a 50 mm radius need 100 mm between the corners. Where the
    route had 50, no 1/2" vinyl line was ever going to make that descent.
    """
    sb = [0.0] * len(points)
    for i in range(1, len(points) - 1):
        sb[i] = _bend(points[i - 1], points[i], points[i + 1], radius)[0]
    for i in range(len(points) - 1):
        avail = math.dist(points[i], points[i + 1])
        need = sb[i] + sb[i + 1]
        if need > avail + 1e-6:
            raise ValueError(
                "the straight from %s to %s is %.1f mm but the bends at its two "
                "ends want %.1f + %.1f = %.1f mm of it — a %.1f mm OD line on a "
                "%.0f mm radius cannot make both turns that close together"
                % (tuple(round(c, 1) for c in points[i]),
                   tuple(round(c, 1) for c in points[i + 1]),
                   avail, sb[i], sb[i + 1], need, od, radius))
    return sb


def centreline(points, radius=BEND_R, od=TUBE_OD):
    """The route as ONE continuous wire: straights and true circular arcs.

    Arcs, not the chord-and-knuckle chain this used to build. A chord lies
    INSIDE the arc it stands for and the knuckle sphere does not, so every bend
    was drawn as a string of rings standing proud of the tube — the ribbing
    visible on the hoses in the viewer. A swept wire has no facets to show.
    """
    sb = _setbacks(points, radius, od)
    edges, cur = [], points[0]
    for i in range(1, len(points) - 1):
        if sb[i] <= 1e-9:                          # straight through
            continue
        _s, t_in, mid, t_out = _bend(points[i - 1], points[i], points[i + 1],
                                     radius)
        if math.dist(cur, t_in) > 1e-7:
            edges.append(cq.Edge.makeLine(cq.Vector(*cur), cq.Vector(*t_in)))
        edges.append(cq.Edge.makeThreePointArc(
            cq.Vector(*t_in), cq.Vector(*mid), cq.Vector(*t_out)))
        cur = t_out
    if math.dist(cur, points[-1]) > 1e-7:
        edges.append(cq.Edge.makeLine(cq.Vector(*cur), cq.Vector(*points[-1])))
    assert edges, "a run with no length: %r" % (points,)
    return cq.Wire.assembleEdges(edges)


def run(points, od=TUBE_OD, radius=BEND_R, bore=TUBE_ID):
    """A hose along `points`, swept round real bends. Raises if a bend cannot fit.

    ⚠ IT IS A TUBE, NOT A ROD, and that is not cosmetic. This swept a solid
    cylinder of vinyl for as long as it existed -- `TUBE_ID` was declared on the
    same line as `TUBE_OD` and no geometry ever used it -- and a solid rod is
    why the hoses still read as opaque coloured plastic after they were given
    both a see-through alpha and a gloss finish. The material was never the
    problem: at 0.32 you were looking through 19 mm of SOLID vinyl, and no
    alpha low enough to see through that leaves a tube you can see at all. A
    real hose is two 3.2 mm walls with a hole between them, and drawn that way
    it reads as tubing at the same alpha, because that is what makes a clear
    tube look clear.

    Nothing a gate measures moves on the OUTSIDE: the outer surface is the same
    sweep on the same path, and the bounding box is identical to the micron.
    What does move is any volume that was being counted INSIDE the bore -- a
    barb pushed into the hose is in the hose's hole, not in its wall -- and
    that is the more correct answer, not a looser one.
    """
    path = centreline(points, radius, od)
    d0 = _unit([b - a for a, b in zip(points[0], points[1])])

    def swept(d):
        w = cq.Wire.makeCircle(d / 2.0, cq.Vector(*points[0]), cq.Vector(*d0))
        return cq.Workplane(obj=cq.Solid.sweep(w, [], path, makeSolid=True,
                                               isFrenet=True))

    wall = swept(od)
    return wall if not bore else wall.cut(swept(bore))


# ── Where each elbow leg ends — the stub the hose picks up ──────────────────
_ZP = F.FLOOR_T + F.PUMP_PORT_Z                     # 84
_YA, _YB = F._PORT_YS                               # 161 (pump A), 49 (pump B)
_LEGX_IN  = F.ELBOW_NUT_L / 2.0                     # 11 — inner legs
_LEGX_OUT = F.PUMP_X_OUT + F.ELBOW_NUT_L / 2.0      # 136 — outer legs
_LEG_END  = F.ELBOW_LEG_L                           # 45 of +Y leg

A_IN  = (+_LEGX_IN,  _YA + _LEG_END, _ZP)           # A inlet  -> TANK
A_OUT = (-_LEGX_OUT, _YA + _LEG_END, _ZP)           # A outlet -> GREEN
# B's inlet is the odd one. Its elbow is clocked UP (pump_frame.PORT_CLOCK),
# so the route starts at the PORT rather than the leg end: the 45 mm leg IS
# the first straight, and the bend at the top needs all 50 mm of it.
B_IN  = (-_LEGX_IN,  _YB,             _ZP)          # B inlet  -> GREEN, upward

# Centreline of the run that crosses OVER the pumps. Pumps top out at 119 and
# the beam underside is at POST_Z1, so this has to clear both by the hose
# radius. Asserted below rather than trusted.
OVERHEAD_Z = 134.0
_CLR_PUMP = OVERHEAD_Z - TUBE_OD / 2.0 - 119.0
_CLR_BEAM = L.RAIL_Z0 - (OVERHEAD_Z + TUBE_OD / 2.0)
assert _CLR_PUMP > 0 and _CLR_BEAM > 0, (
    "the overhead run does not fit: %.1f mm over the pumps, %.1f mm under the "
    "rails" % (_CLR_PUMP, _CLR_BEAM))
B_OUT = (+_LEGX_OUT, _YB + _LEG_END, _ZP)           # B outlet -> TANK

TANK_TEE   = (+73.0, PLENUM_Y, _ZP)   # A_IN from -X, B_OUT from +X, tank from +Z
GREEN_TEE  = (-73.0, PLENUM_Y, _ZP)   # A_OUT from -X, B_IN from +X, wand out -Z
GREEN_EXIT = (-73.0, PLENUM_Y, -40.0)


def routes():
    """Every hose in the system, as (name, centreline points).

    Each run reaches the plenum along its OWN x, turns once, and meets the tee
    head-on. Tee x is picked so both corners keep >= BEND_R of straight on each
    side -- the corners land at x=|11| and x=|136|, so the tee has to sit
    between 61 and 86; 73 centres it.
    """
    # Imported HERE, not at the top: src/tank_outlet.py reads this module's
    # UNISEAL_* to know where the tank wall is, so a module-level import either
    # way round is a cycle. The constants belong to the route and the fittings
    # belong to the outlet; this is the one call that needs both.
    from . import tank_outlet as TO
    return [
        # TANK side (+X): the ELBOW'S BARB -> down -> slope into the tee
        #
        # ⚠ THIS USED TO START AT THE TANK WALL, as if the Uniseal were a hose
        # barb. It is not: there are four rigid parts between the wall and the
        # first millimetre of vinyl (src/tank_outlet.py), and findings 16 and 19
        # say in their own words that neither this module nor check_plumbing
        # knew a fitting has length, so "both will keep passing either layout".
        # The hose now starts where the hose starts.
        #
        # The elbow turns the line down AT the tank, so the route leaves its
        # barb STRAIGHT DOWN -- a barb is the straight part of any hose run --
        # and takes its one bend 63 mm later, sloping into the tee at 30.3 deg
        # off its axis. That is less than the 38.9 deg green_from_B already
        # arrives at and was accepted for, on the same reasoning.
        ("tank_down",    [TO.hose_start(),
                          (UNISEAL_X, TO.hose_start()[1], TANK_SLOPE_Z),
                          TANK_TEE]),
        ("tank_to_A",    [A_IN,  (A_IN[0],  PLENUM_Y, _ZP), TANK_TEE]),
        ("tank_to_B",    [B_OUT, (B_OUT[0], PLENUM_Y, _ZP), TANK_TEE]),
        # GREEN side (-X): both green ports -> tee -> straight down to the wand
        ("green_from_A", [A_OUT, (A_OUT[0], PLENUM_Y, _ZP), GREEN_TEE]),
        # B's inlet cannot go forward -- pump A is in the way -- so it goes UP,
        # over the pumps, and SLOPES down to the tee once it is clear of them.
        #
        # ⚠ IT USED TO DROP VERTICALLY AT x=-11 AND THEN TURN -X, and no hose
        # can do that. The drop was 50 mm (OVERHEAD_Z to the ports' 84) with a
        # 90 degree bend at each end, and two 90 degree bends on a 50 mm radius
        # need 100 mm between their corners. The old per-corner check passed it
        # twice over (see `_setbacks`) and the viewer drew the hose descending
        # to 84, jumping back up to 134, and descending again.
        #
        # There is no all-right-angle route here. The hose has to stay above
        # z=128.5 until y=208 to clear the pumps, which leaves 54 mm of Y to
        # lose 50 mm of Z in -- and the turn into the tee alone wants 50 of
        # those. So the descent is a SLOPE: one bend out of the overhead run,
        # straight down to the barb at 38.9 degrees off the tee's axis. That is
        # what a vinyl line actually does on a barbed fitting -- the barb is the
        # straight part -- and it is one R50 bend, not two.
        ("green_from_B", [B_IN,
                          (B_IN[0], _YB, OVERHEAD_Z),
                          (B_IN[0], PLENUM_Y, OVERHEAD_Z),
                          GREEN_TEE]),
        ("green_out",    [GREEN_TEE, GREEN_EXIT]),
    ]


def pack_frame() -> cq.Workplane:
    """The pack's back frame: a panel behind y=0, as worn. Reference only."""
    return (cq.Workplane("XY").workplane(offset=-SHELF_T)
            .center(0, -PACK_T / 2.0).rect(PACK_W, PACK_T).extrude(PACK_H))


def shelf() -> cq.Workplane:
    return (cq.Workplane("XY").workplane(offset=-SHELF_T)
            .center(0, F.SHELF_D / 2.0).rect(F.SHELF_W, F.SHELF_D)
            .extrude(SHELF_T))
