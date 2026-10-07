"""Pack frame + tube routing — does the plumbing have a path that isn't blocked?

The frame CAD proves the STRUCTURE fits. It says nothing about whether a hose
can actually get from each pump port to where it has to go, and a 1/2" vinyl
line is not a line — it is a 19 mm cylinder that cannot turn tighter than about
50 mm. A route that looks obvious in plan can be impossible in the solid.

So this models the hoses as SOLIDS, with their real OD and their real bend
radius, and runs them through the same interference check as everything else.
`_bend_pts` RAISES when a corner has too little straight either side to hold the
bend, so a route that cannot physically turn fails loudly instead of being drawn
as a sharp corner no hose can make.

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
ARC_SEGS         = 8              # chords per bend; error = R(1-cos(th/2N))

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


def _bend_pts(p_prev, p_corner, p_next, radius, od=None):
    """Chord points approximating a constant-radius bend at `p_corner`.

    Returns (tangent_in, [arc points], tangent_out). Raises when the straight
    either side is too short to hold the bend — which is the whole point: a
    route that cannot physically turn should FAIL here, not be drawn anyway.
    """
    d_in  = _unit([c - p for p, c in zip(p_prev, p_corner)])
    d_out = _unit([n - c for c, n in zip(p_corner, p_next)])
    cosang = max(-1.0, min(1.0, sum(a * b for a, b in zip(d_in, d_out))))
    turn = math.acos(cosang)                       # 0 = straight through
    if turn < 1e-6:
        return p_corner, [], p_corner
    setback = radius * math.tan(turn / 2.0)
    for p, name in ((p_prev, "into"), (p_next, "out of")):
        avail = math.dist(p, p_corner)
        if avail + 1e-6 < setback:
            raise ValueError(
                "bend at %s needs %.1f mm of straight %s it but has %.1f — "
                "a %.1f mm OD line on a %.0f mm radius cannot make this turn"
                % (tuple(round(c, 1) for c in p_corner), setback, name, avail,
                   TUBE_OD if od is None else od, radius))
    t_in  = tuple(c - setback * d for c, d in zip(p_corner, d_in))
    t_out = tuple(c + setback * d for c, d in zip(p_corner, d_out))
    perp = _unit([o - i * cosang for i, o in zip(d_in, d_out)])
    ctr = tuple(t + radius * p for t, p in zip(t_in, perp))
    w = [-p for p in perp]                         # unit: ctr -> t_in
    pts = []
    for k in range(1, ARC_SEGS):
        a = turn * k / ARC_SEGS
        pts.append(tuple(c + radius * (math.cos(a) * wi + math.sin(a) * ti)
                         for c, wi, ti in zip(ctr, w, d_in)))
    return t_in, pts, t_out


def run(points, od=TUBE_OD, radius=BEND_R):
    """A hose along `points`, with real bends. Raises if a bend cannot fit."""
    r = od / 2.0
    path = [points[0]]
    for i in range(1, len(points) - 1):
        t_in, arc, t_out = _bend_pts(points[i - 1], points[i], points[i + 1],
                                     radius, od)
        path += [t_in] + arc + [t_out]
    path.append(points[-1])
    sol = None
    for a, b in zip(path, path[1:]):
        s = _seg(a, b, r)
        if s is None:
            continue
        sol = s if sol is None else sol.union(s)
    for p in path[1:-1]:                            # knuckles at every chord
        sol = sol.union(cq.Workplane(obj=cq.Solid.makeSphere(
            r, cq.Vector(*p))))
    return sol


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
    return [
        # TANK side (+X): Uniseal -> down the front -> tee -> both tank ports
        ("tank_down",    [(UNISEAL_X, UNISEAL_Y, UNISEAL_Z),
                          (UNISEAL_X, PLENUM_Y, UNISEAL_Z),
                          TANK_TEE]),
        ("tank_to_A",    [A_IN,  (A_IN[0],  PLENUM_Y, _ZP), TANK_TEE]),
        ("tank_to_B",    [B_OUT, (B_OUT[0], PLENUM_Y, _ZP), TANK_TEE]),
        # GREEN side (-X): both green ports -> tee -> straight down to the wand
        ("green_from_A", [A_OUT, (A_OUT[0], PLENUM_Y, _ZP), GREEN_TEE]),
        # B's inlet cannot go forward -- pump A is in the way -- so it goes UP,
        # over the pumps, and down again in the plenum.
        ("green_from_B", [B_IN,
                          (B_IN[0], _YB, OVERHEAD_Z),
                          (B_IN[0], PLENUM_Y, OVERHEAD_Z),
                          (B_IN[0], PLENUM_Y, _ZP),
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
