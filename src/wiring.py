"""The internal harness — does every cable have a path, and can it make its bends?

The housing CAD proves the BOX fits and `elec/cad_geom_check.py` proves the board
is where the CAD draws it. Neither says anything about the cables, and that gap
is not theoretical: it is how J5 sat on the wrong edge of the board through five
rounds of review (punchlist 21). **No gate catches a cable that no model draws.**

So this models the harness as SOLIDS, with real conductor diameters and real bend
radii, and puts them through the same interference check as everything else --
`src/build.components()` appends them, so `tools/check_overlaps.py` weighs them
against the housing, the lid, the board and each other without being told to.

WHAT IS MODELLED HERE, AND WHAT IS NOT
--------------------------------------
Modelled: every field cable from its terminal's MOUTH, down through the cable
chase, to where it leaves the housing -- plus the battery pair's crossing of the
wire slot through the back plate. That is the part with no slack in it, the part
the overlap gate can weigh, and the part finding 21 lived in.

NOT modelled, and said plainly rather than faked: the external runs on to the
pumps, the wand's joystick and the tank's level sensor. Those are in open air
outside the housing, with the whole back of the machine to bend in, and a drawn
centreline there would be a guess dressed as a measurement. The one external
thing that IS pinned is where each cable leaves, which is what the chase gate
needs.

Run:  py -3.12 -m src.wiring
"""
from __future__ import annotations

import json
import pathlib

from . import housing as H
from . import plumbing as P

OUT = pathlib.Path(__file__).resolve().parent.parent


# ── Conductor sizes, and why these numbers and not catalogue numbers ────────
# 14 AWG for the battery pair and 16 AWG for the pumps is what the design already
# decided; the ODs below are not a fresh lookup, they are THE SAME NUMBERS THE
# WIRE SLOT WAS SIZED WITH. Punchlist finding 3 sized that slot by laying six
# conductors side by side and getting 17.8 mm, which is 2 x 3.30 + 4 x 2.80
# exactly. Re-deriving them from a wire table would have been a second opinion
# the slot has never been checked against, so the assert at the bottom of this
# file holds the two together instead.
AWG_OD = {14: 3.30, 16: 2.80, 22: 1.70}     # insulated OD, PVC hookup wire

# ⚠ 22 AWG FOR THE TWO SIGNAL CABLES IS AN ASSUMPTION, not a measurement. The
# joystick and the level sensor carry about 10 mA, so gauge is set by handling
# rather than by current, and 22 AWG is the usual floor for a screw clamp rated
# 22-12 AWG (CIRCUIT.md section 7). It is a named constant so that a different
# cable changes one line. The level sensor arrives with its OWN moulded lead
# (finding 20), so that one is the vendor's choice, not ours.
SIGNAL_AWG = 22

# Bend radius as a MULTIPLE of OD, and the two numbers are different on purpose.
# 5x OD is the repeated-flex figure and it is the right one for a cable that is
# worn, walked past and pulled -- which is every run OUTSIDE the housing.
# Inside the sealed bay a cable is installed once with a screwdriver and never
# moves again, and 3x OD is the ordinary fixed-installation figure. Using the
# flex number inside the box would fail a bend that nothing in service will ever
# make; using the fixed number outside would pass one that gets made daily.
BEND_MULT_FIXED = 3.0
BEND_MULT_FLEX  = 5.0


# ── The mouths, FROM THE ROUTED BOARD ───────────────────────────────────────
# ⚠⚠ THE ENTRY DIRECTION IS DECLARED HERE, AND IT HAS TO BE, BECAUSE THE ONLY
# CANONICAL HELPER THAT ANSWERS THIS QUESTION GETS IT WRONG FOR THESE PARTS AND
# GETS IT WRONG SILENTLY.
#
# `cadkit.board_geom.Boards.lead_exit()` is documented as "the point a cable
# should be drawn from". For all five of these terminals it returns
# (pad centre, body centre y, board top + body height) -- a TOP-ENTRY answer,
# a point 15.67 mm off the board's FACE, pointing at the lid. Drawn from there,
# five cables would leave perpendicular to the board, miss the chase entirely,
# and the model would have passed.
#
# The cause is a prefix lookup: lead_exit sees "Horizontal" in the fpid, so it
# tries the side-entry branch, but keys `side_plug_run` on `name[:7]`, which for
# `TerminalBlock_Phoenix_MKDS-3-...` is the string "Termina". Nothing registers
# that, the lookup returns None, and the function FALLS BACK to the top-entry
# formula without a word. See punchlist finding 28.
#
# And the direction cannot simply be measured back, which is the second half of
# the problem. CIRCUIT.md section 7 measured material behind each long face at
# 140 vs 149 mm3 and recorded the verdict as **indeterminate**; the body spans
# 5.35 mm one side of the pad row and 5.95 the other, so `_side_mouth`'s "the
# mouth is the end farther from the origin" heuristic is deciding a direction on
# 0.6 mm of a simplified block -- and it would decide it the WRONG WAY ROUND.
#
# What is actually known is a CONVENTION, and CIRCUIT.md already flags it as one:
# BOARD_NOTES is +Y-up and `layout.py` flips to KiCad's +Y-down, so a footprint's
# local +Y points at the board's -Y, and rot 0 therefore aims every entry at
# world -Z. That is the direction of the bay's only opening, 6.65 mm below. So
# the convention is declared, not inferred, and the assert below checks the one
# thing a convention CAN be checked against: that the mouth actually faces the
# chase.
ENTRY_FACE = "board -Y"        # == world -Z; see above. Do not infer this.

# Which cable lands on which terminal, and how many conductors. From CIRCUIT.md
# section 7 and the netlist, not from counting ways: J5 has four ways but only
# THREE of the sensor's wires reach a terminal (the yellow OUT stops at the
# inverter's base resistor), and J5's MODE way is deliberately empty.
CABLES = {
    "J1": dict(name="wire_pack",     n=2, awg=14, flex=False,
               note="the pack pair, 7.5 A, through the plate's wire slot"),
    "J2": dict(name="wire_pump_a",   n=2, awg=16, flex=True,
               note="pump A, chopped low side"),
    "J3": dict(name="wire_pump_b",   n=2, awg=16, flex=True,
               note="pump B, chopped low side"),
    "J4": dict(name="wire_joystick", n=5, awg=SIGNAL_AWG, flex=True,
               note="the wand's joystick: +3V3, GND, VRX, VRY, SW"),
    "J5": dict(name="wire_level",    n=4, awg=SIGNAL_AWG, flex=True,
               note="the tank's level sensor -- the lead that climbs OUTSIDE"),
}


def _geom():
    with open(str(OUT / "elec" / "geom" / "main.geom.json"), encoding="utf-8") as fh:
        return json.load(fh)


def mouths():
    """{ref: (x, y, z)} in WORLD -- where each cable meets its clamp.

    FROM THE ROUTED BOARD (PCB_README: never a typed placement). The mouth is
    the body's board -Y face at the pad span's centre, mid-body in the standoff
    direction, because that is where a clamp's throat is."""
    from cadkit.board_geom import fp_name
    g = _geom()
    t = g["thickness_mm"]
    out = {}
    for f in g["footprints"]:
        ref = f["ref"]
        if ref not in CABLES:
            continue
        _x0, _x1, y0, _y1 = f["fab"]
        h = H._BOARDS.HEIGHT[fp_name(f["fpid"])]
        out[ref] = (H.BOARD_X1 - (t + h / 2.0),      # board +Z -> world -X
                    H.PCB_Y_C - f["pads_xy"][0],     # board +X -> world -Y
                    H.PCB_Z_C + y0)                  # board +Y -> world +Z
    missing = set(CABLES) - set(out)
    assert not missing, (
        "no routed footprint for %s: this file names a terminal the board does "
        "not have" % sorted(missing))
    return out


MOUTHS = mouths()

# THE MOUTH MUST FACE THE CHASE. This is the one check the declared convention
# can be held to, and it is the check that would have caught finding 21 before
# it reached a reviewer: a terminal whose mouth is not over the opening has no
# way out, whichever direction its entry faces.
CHASE_Z = H.BAY_Z0 + H.WALL                 # the bay's inner floor level
for _ref, (_mx, _my, _mz) in sorted(MOUTHS.items()):
    assert H.CHASE_Y0 <= _my <= H.CHASE_Y1, (
        "%s's mouth is at y %.2f, outside the cable chase (%.2f..%.2f): its "
        "cable has no way out of the bay" % (_ref, _my, H.CHASE_Y0, H.CHASE_Y1))
    assert _mz > CHASE_Z, (
        "%s's mouth is at z %.2f, at or below the bay floor at %.2f"
        % (_ref, _mz, CHASE_Z))
    _drop = _mz - CHASE_Z
    assert _drop < 20.0, (
        "%s's mouth is %.1f mm above the bay floor: that is not a drop into the "
        "chase, it is a climb down the board -- which is exactly finding 21"
        % (_ref, _drop))

# ── Where the cables leave ──────────────────────────────────────────────────
# Far enough below the housing to be clear of it, so the overlap gate is weighing
# the cable against the chase's WALLS rather than against thin air.
EXIT_Z = H.BAY_Z0 - 12.0

# The wire slot the battery pair crosses, read from the housing rather than
# retyped. It is BELOW the bay (z 5.5..10.5 against the bay floor at 15.75), so
# the pair runs straight down past the chase and turns once.
SLOT_Y0 = H.WIRE_SLOT_Y_C - H.WIRE_SLOT_W / 2.0
SLOT_Y1 = H.WIRE_SLOT_Y_C + H.WIRE_SLOT_W / 2.0
SLOT_Z_C = H.WIRE_SLOT_Z_C


def bundle_od(n, awg):
    """OD of `n` conductors gathered into a round bundle.

    Equal-circle packing, from the published factors: 1 -> 1.00, 2 -> 2.00,
    3 -> 2.155, 4 -> 2.414, 5 -> 2.701, 6 -> 3.00 times the conductor diameter.
    Not an area estimate -- an area estimate under-reads a 2-conductor bundle by
    30 %, and the 2-conductor bundles here are the two carrying 7.5 A."""
    k = {1: 1.0, 2: 2.0, 3: 2.155, 4: 2.414, 5: 2.701, 6: 3.0}
    assert n in k, "no packing factor for %d conductors" % n
    return k[n] * AWG_OD[awg]


def bend_radius(n, awg, flex):
    """Centreline bend radius for a bundle of `n` conductors.

    ⚠ IT IS SET BY THE CONDUCTOR, NOT BY THE BUNDLE, and getting that backwards
    is the first thing this file got wrong. None of these runs is a jacketed
    cable -- they are loose conductors into a screw clamp -- so each wire bends
    on its OWN radius, and multiplying the gathered bundle's diameter instead
    charged the pack pair 19.80 mm where the physics asks 9.90. The bundle's
    diameter is what has to FIT a hole; the conductor's is what has to BEND.

    The one thing the bundle does cost is offset: the conductor on the inside of
    the turn sits (bundle - conductor)/2 nearer the centre than the centreline
    does, so it bends that much tighter than the centreline radius. That is
    added back, which is why this is not simply `mult * conductor`.
    """
    d = AWG_OD[awg]
    own = d * (BEND_MULT_FLEX if flex else BEND_MULT_FIXED)
    return own + (bundle_od(n, awg) - d) / 2.0


def routes():
    """Every modelled cable, as (name, centreline points, od, bend radius)."""
    out = []
    for ref, spec in sorted(CABLES.items()):
        mx, my, mz = MOUTHS[ref]
        od = bundle_od(spec["n"], spec["awg"])
        r = bend_radius(spec["n"], spec["awg"], spec["flex"])
        if ref == "J1":
            # straight down past the chase, then ONE turn into the wire slot.
            # The turn is purely in X-Z: the mouth's y is inside the slot's span,
            # which the assert below checks rather than assumes.
            pts = [(mx, my, mz), (mx, my, SLOT_Z_C), (H.BACK_X + 6.0, my, SLOT_Z_C)]
        else:
            pts = [(mx, my, mz), (mx, my, EXIT_Z)]
        out.append((spec["name"], pts, od, r))
    return out


# The pack pair's single turn has to have somewhere to happen. Its straight is
# the drop from the mouth to the slot's centreline, and a 90 degree bend eats
# `radius` of it (tan(45) = 1).
_J1 = CABLES["J1"]
_J1_OD = bundle_od(_J1["n"], _J1["awg"])
_J1_R = bend_radius(_J1["n"], _J1["awg"], _J1["flex"])
_J1_DROP = MOUTHS["J1"][2] - SLOT_Z_C
assert _J1_DROP >= _J1_R, (
    "the pack pair drops %.2f mm from its mouth to the wire slot and needs "
    "%.2f mm to turn into it: a %.2f mm bundle of %.1fx-OD conductors cannot "
    "make that corner" % (_J1_DROP, _J1_R, _J1_OD, BEND_MULT_FIXED))
assert SLOT_Y0 <= MOUTHS["J1"][1] <= SLOT_Y1, (
    "J1's mouth is at y %.2f and the wire slot spans %.2f..%.2f: the pack pair "
    "would have to move sideways under the bay to reach it"
    % (MOUTHS["J1"][1], SLOT_Y0, SLOT_Y1))

# ── THE SLOT IS NOT A ROUND HOLE, AND A ROUND BUNDLE IS THE WRONG MODEL FOR IT
# The slot is 5 mm tall and 40 wide: one layer deep, so WIDTH is what carries the
# conductors and they lie side by side, not gathered. This is the check finding 3
# did by hand and nothing has held since. Every conductor that crosses the plate
# is counted -- the pack pair AND the two pump pairs, because the chase is the
# bay's only exit and all three cross.
_CROSSING = ("J1", "J2", "J3")
_LAID_W = sum(CABLES[r]["n"] * AWG_OD[CABLES[r]["awg"]] for r in _CROSSING)
_SLOT_W = SLOT_Y1 - SLOT_Y0
assert _LAID_W <= _SLOT_W, (
    "%.1f mm of conductor laid side by side has to cross a %.1f mm slot"
    % (_LAID_W, _SLOT_W))
_TALLEST = max(AWG_OD[CABLES[r]["awg"]] for r in _CROSSING)
assert _TALLEST <= H.WIRE_SLOT_H, (
    "the thickest conductor crossing the plate is %.2f mm and the slot is only "
    "%.2f mm tall" % (_TALLEST, H.WIRE_SLOT_H))

# ...and the numbers above must still be the ones the slot was sized with.
# Finding 3 laid six conductors and got 17.8 mm. If a gauge here is edited, this
# is what says the slot's own width stopped being justified.
assert abs(_LAID_W - 17.8) < 0.05, (
    "the six conductors crossing the plate now measure %.2f mm, not the 17.8 "
    "that punchlist finding 3 sized the %.0f mm slot against -- re-justify the "
    "slot, do not widen this tolerance" % (_LAID_W, _SLOT_W))


def solids():
    """[(name, solid)] for the overlap gate and the viewer."""
    return [(nm, P.run(pts, od=od, radius=r)) for nm, pts, od, r in routes()]


def main() -> int:
    print("internal harness -- %d cables modelled" % len(CABLES))
    for nm, pts, od, r in routes():
        print("  %-14s OD %5.2f  bend R %5.2f  %d point(s)" % (nm, od, r, len(pts)))
    for ref, (x, y, z) in sorted(MOUTHS.items()):
        print("  %-3s mouth (%8.2f, %7.2f, %6.2f)  drop to chase %5.2f mm"
              % (ref, x, y, z, z - CHASE_Z))
    print("  plate crossing: %.1f mm of conductor into a %.0f mm slot"
          % (_LAID_W, _SLOT_W))
    solids()                      # builds every bend, so a bad corner raises
    print("every cable has a path, and every bend is one the cable can make")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
