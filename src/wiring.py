"""The harness — does every cable have a path, and can it make its bends?

The housing CAD proves the BOX fits and `elec/cad_geom_check.py` proves the board
is where the CAD draws it. Neither says anything about the cables, and that gap
is not theoretical: it is how J5 sat on the wrong edge of the board through five
rounds of review (punchlist 21). **No gate catches a cable that no model draws.**

`src/build.components()` appends these, so `tools/check_overlaps.py` weighs them
against the housing, the lid, the board, the pumps, the timber, the tank and the
hoses -- and against each other -- without being told to.

OCTAGONS, NOT CYLINDERS, AND NOT MY OWN SWEEP
---------------------------------------------
This file first drew cables with `plumbing.run()` -- round segments fused with
ball elbows. That was wrong twice over. cadkit already has `cables.py` for
exactly this, and the reason it is octagonal is written there: a sphere meeting
two cylinders along a shared circle is the tangent case OCCT handles worst, and
it fails SILENTLY -- the fuse returns one valid solid with material missing out
of the middle. A cable is dozens of those joints, and an overlap gate's cost is
mostly cable pairs. `oct_cable` is across-flats = the conductor diameter, so the
real round cable always fits INSIDE the model and every error lands on the side
of clearance.

`bundle_paths` is the other thing not to reinvent. Conductor offsets are taken in
the BUNDLE's own cross-section, so a conductor keeps its place around every
corner. I had written constant WORLD offsets and hit precisely the failure its
docstring warns about: the pack pair's two lanes were offset in Y, the run then
turned ONTO Y, and both conductors slid onto the same centreline -- 1057 mm3 of
cable through cable, which the overlap gate caught.

WHAT IS MODELLED
----------------
All five field cables, END TO END: from the terminal's MOUTH to the thing at the
far end -- the dock's contact block, each pump's motor leads, the wand's
joystick, the tank's level sensor. Every destination is read off a placed model
rather than typed, so a pump or a dock that moves takes its cable with it.

Run:  py -3.12 -m src.wiring
"""
from __future__ import annotations

import json
import pathlib

from cadkit.cables import bundle_paths, oct_cable, path_length

from . import housing as H
from . import lumber_frame as L
from . import plumbing as P
from . import pump_frame as F

OUT = pathlib.Path(__file__).resolve().parent.parent


# ── Conductor sizes, and why these numbers and not catalogue numbers ────────
# 14 AWG for the battery pair and 16 for the pumps is what the design already
# decided; the ODs below are THE SAME NUMBERS THE WIRE SLOT WAS SIZED WITH.
# Punchlist finding 3 sized that slot by laying six conductors side by side and
# getting 17.8 mm, which is 2 x 3.30 + 4 x 2.80 exactly. Re-deriving them from a
# wire table would be a second opinion the slot has never been checked against,
# so the assert at the bottom holds the two together instead.
AWG_OD = {14: 3.30, 16: 2.80, 22: 1.70}     # insulated OD, PVC hookup wire

# ⚠ 22 AWG FOR THE TWO SIGNAL CABLES IS AN ASSUMPTION, not a measurement. The
# joystick and the level sensor carry about 10 mA, so gauge is set by handling
# rather than by current, and 22 AWG is the usual floor for a screw clamp rated
# 22-12 AWG (CIRCUIT.md section 7). Named so a different cable changes one line.
# The level sensor arrives with its OWN moulded lead (finding 20), so that one is
# the vendor's choice and this is our stand-in for it.
SIGNAL_AWG = 22

# Bend radius as a MULTIPLE of conductor OD, and the two numbers differ on
# purpose. 5x OD is the repeated-flex figure, right for a cable that is worn,
# walked past and pulled -- every run OUTSIDE the housing. Inside the sealed bay
# a cable is installed once with a screwdriver and never moves again, and 3x OD
# is the ordinary fixed-installation figure.
BEND_MULT_FIXED = 3.0
BEND_MULT_FLEX  = 5.0


def _geom():
    with open(str(OUT / "elec" / "geom" / "main.geom.json"), encoding="utf-8") as fh:
        return json.load(fh)


# ── Which cable lands where, and how many conductors ───────────────────────
# From CIRCUIT.md section 7 and the netlist, not from counting ways: J5 has four
# ways but only THREE of the sensor's wires reach a terminal (the yellow OUT
# stops at the inverter's base resistor), and J5's MODE way is deliberately
# empty. The count here is what the CABLE carries, which is what has to fit a
# hole.
CABLES = {
    "J1": dict(name="wire_pack",     n=2, awg=14, flex=False, crosses_plate=True,
               note="the pack pair, 7.5 A, through the plate's wire slot"),
    "J2": dict(name="wire_pump_a",   n=2, awg=16, flex=True, crosses_plate=False,
               note="pump A, chopped low side"),
    "J3": dict(name="wire_pump_b",   n=2, awg=16, flex=True, crosses_plate=False,
               note="pump B, chopped low side"),
    "J4": dict(name="wire_joystick", n=5, awg=SIGNAL_AWG, flex=True,
               crosses_plate=False,
               note="the wand's joystick: +3V3, GND, VRX, VRY, SW"),
    "J5": dict(name="wire_level",    n=4, awg=SIGNAL_AWG, flex=True,
               crosses_plate=False,
               note="the tank's level sensor -- the lead that climbs OUTSIDE"),
}


# ── The mouths, FROM THE ROUTED BOARD ───────────────────────────────────────
# ⚠⚠ THE ENTRY DIRECTION IS DECLARED HERE, AND IT HAS TO BE, BECAUSE THE ONLY
# CANONICAL HELPER THAT ANSWERS THIS QUESTION GETS IT WRONG FOR THESE PARTS AND
# GETS IT WRONG SILENTLY.
#
# `cadkit.board_geom.Boards.lead_exit()` is documented as "the point a cable
# should be drawn from". For all five of these terminals it returns a TOP-ENTRY
# answer -- a point 15.67 mm off the board's FACE, pointing at the lid. Drawn
# from there, five cables would leave perpendicular to the board, miss the chase
# entirely, and this model would have passed.
#
# The cause is a prefix lookup: lead_exit sees "Horizontal" in the fpid so it
# tries the side-entry branch, but keys `side_plug_run` on `name[:7]`, which for
# `TerminalBlock_Phoenix_MKDS-3-...` is the string "Termina". Nothing registers
# that, the lookup returns None, and it FALLS BACK to the top-entry formula
# without a word. See punchlist finding 28.
#
# And the direction cannot simply be measured back. CIRCUIT.md section 7 measured
# material behind each long face at 140 vs 149 mm3 and recorded the verdict as
# **indeterminate**; the body spans 5.35 mm one side of the pad row and 5.95 the
# other, so `_side_mouth`'s "the mouth is the end farther from the origin" rule
# is deciding on 0.6 mm of a simplified block -- and would decide it the WRONG
# WAY ROUND.
#
# What is known is a CONVENTION, which CIRCUIT.md already flags as one:
# BOARD_NOTES is +Y-up and `layout.py` flips to KiCad's +Y-down, so a footprint's
# local +Y points at the board's -Y, and rot 0 aims every entry at world -Z --
# the direction of the bay's only opening, 6.65 mm below. Declared, not inferred,
# and the asserts below check the one thing a convention CAN be held to.
ENTRY_FACE = "board -Y"        # == world -Z; see above. Do not infer this.


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

# ⚠ THIS LIST CANNOT BE THE ONLY THING THAT DECIDES, and the fail harness proved
# it. The slot-fit asserts were first written `for ref in LAID_FLAT:`, so
# emptying the tuple did not trip them -- it SKIPPED them, and a gathered bundle
# went back through a 5.00 mm slot with the gate silent. A check that only
# inspects the cases it is told about cannot catch the case somebody forgot to
# tell it about. So crossing is a property of the CABLE and this is derived.
LAID_FLAT = tuple(sorted(r for r, sp in CABLES.items() if sp["crosses_plate"]))
assert LAID_FLAT, (
    "no cable crosses the back plate, but the housing cuts a wire slot for one: "
    "either a cable lost its crosses_plate flag or the slot is now dead geometry")

# THE MOUTH MUST FACE THE CHASE. The one check the declared convention can be
# held to, and the gate finding 21 never had: a terminal whose mouth is not over
# the opening has no way out, whichever way its entry faces.
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


# ── Where each cable is going, read off the placed models ───────────────────
def _pump_lead_tips(side):
    """[(x, y, z)] of a pump's two motor lead tips, FROM THE PLACED PUMP.

    Found by geometry the way `pump_frame._pump_bores` finds its bolt holes --
    cylinders of the lead radius whose axis runs along the motor axis -- so a
    pump that moves takes its cable with it instead of leaving it pointing at
    where the pump used to be."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    import tools.seaflo_42_pump as S
    r = S.LEAD_D / 2.0
    seen = set()
    for f in F._pump_placed(side).faces().vals():
        if f.geomType() != "CYLINDER":
            continue
        c = BRepAdaptor_Surface(f.wrapped).Cylinder()
        if abs(c.Radius() - r) > 0.01:
            continue
        if abs(c.Axis().Direction().Y()) < 0.9:      # the motor axis, not a bore
            continue
        p = c.Location()
        seen.add((round(p.X(), 2), round(p.Y(), 2), round(p.Z(), 2)))
    assert len(seen) == 2, (
        "pump %+d: found %d motor lead(s), expected 2 -- the pump model changed "
        "and its cable no longer knows where to land" % (side, len(seen)))
    return sorted(seen)


# ── The band the cables fan out in, below the bay and outboard of the plate ──
# Everything leaving the chase arrives here. It is open air: the bay's own floor
# stops at BAY_Z0, the back plate is inboard at x >= FLOOR_X, and the only thing
# in the band is the wire slot the pack pair uses.
# ⚠ A LANE IS THREE NUMBERS, NOT ONE, and the overlap gate is what taught me
# that. Four cables leave the chase into this one band and they do not all go the
# same way: the pumps head for opposite ends of the machine, the joystick heads
# out with the wand line and the level sensor turns straight out past the lid. An
# X lane alone deconflicts the PARALLEL runs and does nothing for the places one
# cable crosses another's path at right angles -- which is most of them. Drawn
# that way the gate found eleven crossings (joystick through level, pump B
# through joystick), each a few mm3 where paths clipped.
#
# So a lane is an X for the run along Y, a Z for the band it crosses in, and its
# own turn-out Y -- all three derived from one index, so adding a cable cannot
# half-assign it a lane. Spacing is the widest conductor plus air at every step.
# THE BAND IS 13.35 mm TALL AND FOUR CABLES WANT IT, so levels are SHARED where
# sharing is safe. Two cables may sit at the same height if their paths never
# cross in plan -- and most do not, because they leave in different directions.
# The level is DECLARED with its reason and the assert below is what holds it:
# it computes which pairs actually cross in plan and requires those to differ.
# Declaring four distinct levels instead would not fit, and hand-checking which
# pairs cross is exactly the thing that was wrong before the gate caught it.
BAND_LEVEL = {
    # J2 heads -Y and J5 turns straight out past the lid at its own mouth's y.
    # J2's lane is INBOARD of J5's run, so the two never meet.
    "J2": 0,
    "J5": 0,
    # J3 and J4 both head +Y, in different X lanes, and turn out at different Y
    # (TURN_Y) so J4's cross-machine run clears J3's climb. They share a level
    # because parallel runs in separate lanes do not need separate heights.
    "J3": 1,
    "J4": 1,
}
# ⚠ THE BAND'S CEILING IS THE LID'S SKIRT, NOT THE BAY FLOOR. The skirt hangs
# down to z 10.55 -- 2.8 mm BELOW the bay floor it closes -- so a lane at 11.0
# was inside it, which the overlap gate found as 9.2 mm3 of lid through the
# joystick. Derived from the lid rather than typed, because the skirt's depth is
# a bead multiple that has already changed once.
BAND_CEIL = H.lid().val().BoundingBox().zmin
assert BAND_CEIL < H.BAY_Z0, (
    "the lid's skirt stops at z %.2f, at or above the bay floor %.2f: this "
    "derivation assumed the skirt hangs below it" % (BAND_CEIL, H.BAY_Z0))
FAN_Z0 = 3.0
FAN_PITCH = max(AWG_OD.values()) + 0.2             # 3.5 -- crossing clearance
BAND_STEP = 5.0                                    # two levels under BAND_CEIL
LANE_PITCH = max(AWG_OD.values()) * 2 + 1.5        # 8.1
FAN_ORDER = ("J2", "J3", "J4", "J5")               # order in the band, inboard -> out
# ⚠ AND EVERY CABLE DROPS ON THE SAME LINE, so no lane may sit on it. All five
# mouths share x = BOARD_X1 - (t + h/2), so each cable's vertical drop from its
# clamp passes through every band level at that one x. A lane within a conductor
# of it clips those drops -- which is what the gate reported as pump B through
# the level sensor, 6.1 mm3 at (-207.4, 181.8, 11.0). Lanes therefore start
# OUTBOARD of the drop line with a full conductor of air.
DROP_X = MOUTHS["J2"][0]
LANE_X0 = DROP_X - (max(AWG_OD.values()) + 2.0)
LANE_X, FAN_Z, TURN_Y = {}, {}, {}
for _i, _r in enumerate(FAN_ORDER):
    LANE_X[_r] = LANE_X0 - _i * LANE_PITCH
    FAN_Z[_r]  = FAN_Z0 + BAND_LEVEL[_r] * BAND_STEP
    TURN_Y[_r] = _i * LANE_PITCH            # pushed out so turns do not coincide
    assert LANE_X[_r] < H.FLOOR_X, "%s's lane is inboard of the plate" % _r
    assert DROP_X - LANE_X[_r] >= max(AWG_OD.values()), (
        "%s's lane at x %.2f is within a conductor of the drop line at %.2f, "
        "where every cable comes down from its clamp"
        % (_r, LANE_X[_r], DROP_X))
    assert 0.0 < FAN_Z[_r] < BAND_CEIL, (
        "%s's fan-out band at z %.2f is not between the ground and the lid "
        "skirt's underside at %.2f -- the band cannot hold this many levels"
        % (_r, FAN_Z[_r], BAND_CEIL))
assert set(BAND_LEVEL) == set(FAN_ORDER), (
    "every cable in the fan-out band needs a declared level: %s"
    % sorted(set(FAN_ORDER) ^ set(BAND_LEVEL)))

# ...and the pack pair shares this band too, crossing the plate at the slot's own
# z. Only its own lane can reach it, so only a cable whose lane lies inside J1's
# x span has to clear it.
for _r, _z in FAN_Z.items():
    if LANE_X[_r] < min(H.BOARD_X1 - (1.6 + 14.07 / 2.0), H.BACK_X + 6.0):
        continue                            # outboard of where J1 ever goes
    assert abs(_z - H.WIRE_SLOT_Z_C) >= FAN_PITCH, (
        "%s's band at z %.2f is within %.2f mm of the pack pair's plate crossing "
        "at z %.2f, and its lane is inside J1's run"
        % (_r, _z, FAN_PITCH, H.WIRE_SLOT_Z_C))


# The timber side: the pack pair crosses the plate and runs to the dock.
# MEASURED, and the run is clear -- probing a 3.30 mm conductor at BACK_X + 2
# along the whole path (y 40..170, z 8..60) finds no timber at all, and sweeping
# +X from the plate's back face at the slot, mid-run and the dock finds none
# within 200 mm. The frame is slender members and the plate meets it only at the
# wood screws, so the leads run in open air between them.
DOCK_RUN_X = H.BACK_X + 6.0
_term = H.terminal_placed()
assert _term is not None, (
    "the Makita contact block is not in the model, so the pack pair has nowhere "
    "to run to -- this file cannot check a destination that is not drawn")
_tb = _term.val().BoundingBox()
DOCK_Y_C = (_tb.ymin + _tb.ymax) / 2.0
DOCK_Z0 = _tb.zmin
# Stop 1.0 mm short of the block rather than inside it. A lead really does enter
# its terminal, but the useful claim is "the pair REACHES the dock with a path",
# and stopping at the envelope makes that claim without asserting anything about
# tabs the bought part does not model.
DOCK_STANDOFF = 1.0

SLOT_Y0 = H.WIRE_SLOT_Y_C - H.WIRE_SLOT_W / 2.0
SLOT_Y1 = H.WIRE_SLOT_Y_C + H.WIRE_SLOT_W / 2.0
SLOT_Z_C = H.WIRE_SLOT_Z_C

# Cross-machine height for the two pump runs. NOT the leads' own z: the hoses
# work the y 210..262 plenum at z 84 and 134, and a pump cable crossing at the
# leads' 71 would pass 13 mm under a 19 mm hose -- 0.7 mm of air once both radii
# are counted. 60 leaves 24 mm, and the cable rises to the lead only once it is
# at the pump.
CROSS_Z = 60.0
# ...and the pump runs pass OUTSIDE the frame in Y, which is where the lead tips
# point anyway: pump A's leads face -Y at y=2, pump B's face +Y at y=208.
FRAME_CLR = 6.0
RUN_Y_LO = -FRAME_CLR                       # outboard of the frame's y=0 face
RUN_Y_HI = L.FRAME_D + FRAME_CLR            # ...and of its y=210 face
# The level sensor's lead climbs the OUTSIDE of the housing (CIRCUIT.md 7), and it
# climbs on ITS OWN LANE rather than at a separately chosen x. Picking one by hand
# put it at WALL_X - 5.0 = -227.9, half a millimetre from the joystick's lane at
# -228.4 -- so the climb passed straight through the joystick's run and the gate
# reported it. Its lane is already deconflicted from every other cable's by
# construction, so using it is both shorter to justify and impossible to get
# wrong when a lane moves.
OUTSIDE_X = LANE_X["J5"]
assert OUTSIDE_X < H.lid().val().BoundingBox().xmin, (
    "the level sensor's lead climbs at x %.2f but the lid reaches out to %.2f: "
    "it is meant to climb the OUTSIDE of the housing"
    % (OUTSIDE_X, H.lid().val().BoundingBox().xmin))
TANK_Z = L.DECK_Z + 7.0                     # just above the deck the tank sits on


def _routes_raw():
    """{ref: (trunk centreline, [per-conductor tail] or None)}.

    A tail is for a cable whose conductors land on SEPARATE things -- a pump's
    two motor leads are 22 mm apart, which is a splay, not a bundle. Everything
    else terminates at one connector and its conductors stay together."""
    out = {}
    for ref, spec in CABLES.items():
        mx, my, mz = MOUTHS[ref]
        if ref == "J1":
            # down past the chase, one turn into the wire slot, then along the
            # back of the plate and up to the dock.
            out[ref] = ([(mx, my, mz), (mx, my, SLOT_Z_C),
                         (DOCK_RUN_X, my, SLOT_Z_C),
                         (DOCK_RUN_X, DOCK_Y_C, SLOT_Z_C),
                         (DOCK_RUN_X, DOCK_Y_C, DOCK_Z0 - DOCK_STANDOFF)], None)
            continue
        lane = LANE_X.get(ref)
        if ref in ("J2", "J3"):
            side = -1 if ref == "J2" else +1
            tips = _pump_lead_tips(side)
            run_y = RUN_Y_LO if side < 0 else RUN_Y_HI
            cx = sum(t[0] for t in tips) / 2.0
            lead_y, lead_z = tips[0][1], tips[0][2]
            fz = FAN_Z[ref]
            run_y = run_y - TURN_Y[ref] if side < 0 else run_y + TURN_Y[ref]
            trunk = [(mx, my, mz), (mx, my, fz),
                     (lane, my, fz),
                     (lane, run_y, fz),
                     (lane, run_y, CROSS_Z),
                     (cx, run_y, CROSS_Z),
                     (cx, run_y, lead_z)]
            out[ref] = (trunk, [[(t[0], run_y, lead_z), (t[0], lead_y, lead_z)]
                                for t in tips])
            continue
        if ref == "J4":
            # out with the wand line. green_out drops at (-73, 262), so this runs
            # parallel to it, offset far enough to clear a 3/4" hose.
            gx, gy, gz = P.GREEN_EXIT
            off = (P.TUBE_OD + AWG_OD[spec["awg"]]) / 2.0 + 4.0
            fz = FAN_Z[ref]
            ry = RUN_Y_HI + TURN_Y[ref]
            out[ref] = ([(mx, my, mz), (mx, my, fz),
                         (lane, my, fz),
                         (lane, ry, fz),
                         (gx - off, ry, fz),
                         (gx - off, gy, fz),
                         (gx - off, gy, gz)], None)
            continue
        # J5: down, out past the lid, up the OUTSIDE of the housing to the tank
        tank = L.tank().val().BoundingBox()
        fz = FAN_Z[ref]
        out[ref] = ([(mx, my, mz), (mx, my, fz),
                     (OUTSIDE_X, my, fz),
                     (OUTSIDE_X, my, TANK_Z),
                     (OUTSIDE_X, tank.ymax - 15.0, TANK_Z),
                     (tank.xmin, tank.ymax - 15.0, TANK_Z)], None)
    return out


def _band_segments():
    """{ref: [((x0,y0),(x1,y1))]} -- each cable's trunk segments that lie IN the
    fan-out band, projected to plan. A segment counts when both ends sit at the
    cable's own band height, which is exactly the run that could meet another
    cable's."""
    out = {}
    for ref, (trunk, _t) in _routes_raw().items():
        if ref not in FAN_Z:
            continue
        z = FAN_Z[ref]
        segs = []
        for a, b in zip(trunk, trunk[1:]):
            if abs(a[2] - z) < 1e-6 and abs(b[2] - z) < 1e-6:
                segs.append(((a[0], a[1]), (b[0], b[1])))
        out[ref] = segs
    return out


def _crosses(p, q, r, t):
    """Do plan segments p-q and r-t properly intersect?"""
    def cr(o, a, b):
        return ((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))
    d1, d2 = cr(r, t, p), cr(r, t, q)
    d3, d4 = cr(p, q, r), cr(p, q, t)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


# ⚠ SHARING A BAND LEVEL IS ONLY SAFE IF THE PATHS DO NOT CROSS, AND THIS IS WHAT
# CHECKS IT. The overlap gate found eleven crossings when the band was one height,
# each a few mm3 where one cable clipped through another. That gate still runs, but
# it is slow and it reports a symptom; this reports the cause, in the file that
# chose the levels. A new cable that crosses an existing one and copies its level
# fails HERE, with both names.
_BS = _band_segments()
for _a in sorted(_BS):
    for _b in sorted(_BS):
        if _a >= _b or BAND_LEVEL[_a] != BAND_LEVEL[_b]:
            continue
        for _s in _BS[_a]:
            for _t2 in _BS[_b]:
                assert not _crosses(_s[0], _s[1], _t2[0], _t2[1]), (
                    "%s and %s share fan-out level %d but their paths cross in "
                    "plan near (%.1f, %.1f): one of them needs its own level"
                    % (_a, _b, BAND_LEVEL[_a], _t2[0][0], _t2[0][1]))


def _offsets(n, d):
    """Conductor offsets in the bundle's own section: a flat row.

    A row and not a cluster, because the one place a bundle's shape is forced is
    the wire slot -- 5 mm tall and one layer deep, so the conductors lie side by
    side. Keeping that shape everywhere costs nothing and means the slot's own
    arithmetic (finding 3's 17.8 mm) describes the model."""
    a = (n - 1) * d / 2.0
    return [(-a + k * d, 0.0) for k in range(n)]


def routes():
    """[(name, conductor points, od, bend radius)] -- one entry per CONDUCTOR."""
    out = []
    raw = _routes_raw()
    for ref, spec in sorted(CABLES.items()):
        d = AWG_OD[spec["awg"]]
        r = d * (BEND_MULT_FLEX if spec["flex"] else BEND_MULT_FIXED)
        trunk, tails = raw[ref]
        paths = [list(p) for p in bundle_paths(trunk, _offsets(spec["n"], d))]
        if tails is not None:
            # ⚠ PAIR A CONDUCTOR TO ITS NEAREST LEAD, NOT TO tails[k]. Which side
            # of the bundle a conductor comes out on depends on the section
            # frame's handedness at the last segment, so index order is not
            # position order -- and paired by index, pump A's two conductors
            # swapped sides and crossed THROUGH each other for 2.8 mm (36.4 mm3,
            # found by the overlap gate). Nearest-first is order-independent and
            # fixes itself if a lane or a pump moves.
            free = list(range(len(tails)))
            order = []
            for p in paths:
                end = p[-1]
                j = min(free, key=lambda i: sum(
                    (a - b) ** 2 for a, b in zip(end, tails[i][-1])))
                free.remove(j)
                order.append(j)
            # ...and the splay may not cross: a conductor on one side of the
            # bundle has to land on that side's lead.
            for p, j in zip(paths, order):
                for q, j2 in zip(paths, order):
                    if j >= j2:
                        continue
                    assert ((p[-1][0] - q[-1][0])
                            * (tails[j][-1][0] - tails[j2][-1][0])) >= 0, (
                        "%s's splay crosses: a conductor at x %.2f is paired with "
                        "a lead at x %.2f while its neighbour at %.2f takes %.2f"
                        % (ref, p[-1][0], tails[j][-1][0], q[-1][0],
                           tails[j2][-1][0]))
            paths = [p + tails[j] for p, j in zip(paths, order)]
        for k, pts in enumerate(paths):
            out.append(("%s_%d" % (spec["name"], k + 1), pts, d, r))
    return out


# ── A LAID-FLAT CABLE HAS TO FIT THE SLOT IN BOTH DIRECTIONS ───────────────
# Height is one conductor; width is all of them side by side. This is the check
# whose absence let a 6.60 mm round bundle be drawn through a 5.00 mm slot.
for _ref in LAID_FLAT:
    _sp = CABLES[_ref]
    _d = AWG_OD[_sp["awg"]]
    assert _d <= H.WIRE_SLOT_H, (
        "%s lies flat through the wire slot but one %.2f mm conductor is taller "
        "than the %.2f mm slot" % (_ref, _d, H.WIRE_SLOT_H))
    assert _sp["n"] * _d <= H.WIRE_SLOT_W, (
        "%s's %d conductors are %.2f mm laid side by side, into a %.2f mm slot"
        % (_ref, _sp["n"], _sp["n"] * _d, H.WIRE_SLOT_W))

# The pack pair's turn into the slot has to have somewhere to happen. Its
# straight is the drop from the mouth, and a 90 degree bend eats `radius` of it.
_J1 = CABLES["J1"]
_J1_OD = AWG_OD[_J1["awg"]]
_J1_R = _J1_OD * BEND_MULT_FIXED
_J1_DROP = MOUTHS["J1"][2] - SLOT_Z_C
assert _J1_DROP >= _J1_R, (
    "the pack pair drops %.2f mm from its mouth to the wire slot and needs "
    "%.2f mm to turn into it: a %.2f mm conductor on a %.1fx-OD radius cannot "
    "make that corner" % (_J1_DROP, _J1_R, _J1_OD, BEND_MULT_FIXED))
assert SLOT_Y0 <= MOUTHS["J1"][1] <= SLOT_Y1, (
    "J1's mouth is at y %.2f and the wire slot spans %.2f..%.2f: the pack pair "
    "would have to move sideways under the bay to reach it"
    % (MOUTHS["J1"][1], SLOT_Y0, SLOT_Y1))

# Every conductor that crosses the plate, laid side by side, against the slot.
# Finding 3 sized that slot at 17.8 mm and nothing has held it since.
_CROSSING = ("J1", "J2", "J3")
_LAID_W = sum(CABLES[r]["n"] * AWG_OD[CABLES[r]["awg"]] for r in _CROSSING)
_SLOT_W = SLOT_Y1 - SLOT_Y0
assert _LAID_W <= _SLOT_W, (
    "%.1f mm of conductor laid side by side has to cross a %.1f mm slot"
    % (_LAID_W, _SLOT_W))
assert abs(_LAID_W - 17.8) < 0.05, (
    "the six conductors crossing the plate now measure %.2f mm, not the 17.8 "
    "that punchlist finding 3 sized the %.0f mm slot against -- re-justify the "
    "slot, do not widen this tolerance" % (_LAID_W, _SLOT_W))


# ⚠ ROUTE AT IMPORT. Every assert inside routes() -- the splay-pairing check
# above all -- is only a gate if it RUNS without anybody building a solid.
# Reached from solids() alone it cost nothing until a CAD build, and the fail
# harness, which probes by importing, could not reach it: it reported MISSED on
# the splay case for that reason and not because the assert was wrong. Routing is
# point arithmetic, so running it here is cheap and it fails at the import.
ROUTES = routes()
assert len(ROUTES) == sum(c["n"] for c in CABLES.values()), (
    "%d conductor paths came out of %d declared conductors: a cable lost or "
    "gained one on the way" % (len(ROUTES), sum(c["n"] for c in CABLES.values())))


def solids():
    """[(name, solid)] for the overlap gate and the viewer."""
    return [(nm, oct_cable(pts, od)) for nm, pts, od, _r in ROUTES]


def lengths():
    """{cable name: mm of conductor to buy}, summed over its conductors."""
    out = {}
    for nm, pts, _od, _r in ROUTES:
        key = nm.rsplit("_", 1)[0]
        out[key] = out.get(key, 0.0) + path_length(pts)
    return out


def main() -> int:
    print("harness -- %d cables, %d conductors"
          % (len(CABLES), sum(c["n"] for c in CABLES.values())))
    for ref, spec in sorted(CABLES.items()):
        print("  %-3s %-14s %d x %2d AWG (%.2f mm)  %s"
              % (ref, spec["name"], spec["n"], spec["awg"],
                 AWG_OD[spec["awg"]], spec["note"]))
    for ref, (x, y, z) in sorted(MOUTHS.items()):
        print("  %-3s mouth (%8.2f, %7.2f, %6.2f)  drop to chase %5.2f mm"
              % (ref, x, y, z, z - CHASE_Z))
    print("  plate crossing: %.1f mm of conductor into a %.0f mm slot"
          % (_LAID_W, _SLOT_W))
    tot = 0.0
    for nm, mm in sorted(lengths().items()):
        print("  %-14s %7.0f mm of conductor" % (nm, mm))
        tot += mm
    print("  %-14s %7.0f mm total -- what you have to buy" % ("ALL", tot))
    solids()                      # builds every prism, so a bad path raises
    print("every cable has a path, and every bend is one the cable can make")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
