"""v2 pump frame — the load-bearing table that carries the tank over both pumps.

v2 inverts v1: the TANK sits on top and the pumps underneath on the pack's shelf.
That puts ~21 kg of water on printed plastic, so this is a STRUCTURE first and an
enclosure second. The pumps are water-resistant and are NOT enclosed; only the
PCB needs shelter.

TWO PRINTED PARTS, BUILT ALONG X
--------------------------------
Printed the obvious way — deck flat on the bed, Z up — the cross-beams span the
pump bay at z=124 with nothing beneath them, and no amount of chamfering saves it
(closing a 250 mm opening at 45° needs ~125 mm of rise, which is the volume the
pumps occupy). An earlier cut of this file split the table into four parts to dodge
that. It does not need to be split at all.

**Build along X instead**, each half standing on its OUTER face. Then almost
everything is a constant Y–Z section extruded along the build direction:

  deck, beams   span the full X -> constant section, no overhang
  posts         sit at |X| = POST_X, the OUTERMOST feature -> they land in the
                FIRST LAYERS, on the bed. (This is why the half must stand on its
                outer face. Stood on the split face instead, the posts would
                appear ~180 mm up the build with nothing beneath them.)
  the joint     sits at X=0, the LAST layers -> the tenon is built on top of the
                layer below it, and the mortise is simply an absence at the final
                face. Both print without support.

So the only features that are not constant-section are at the two ends of the
build, which is exactly where a feature may start or stop for free.

WHY THERE IS NO DECK SPINE
--------------------------
The previous version hosted the left/right joint on a raised spine along X=0.
That cannot work in an X-build: the spine exists only near X=0, so it would start
in mid-air partway up the build, and it cannot be run full-length because the
pumps sit where it would go. Ramping it at 45° fails for the same reason — the
ramp lands under a pump.

The fix is to move the joint into the BEAMS, which cross X=0 at z=124..164 —
clear above the inner swivel nuts (z 67..101) — and have 30 x 40 of section to
host it. With the spine gone the pumps no longer need a gap between them, which
narrows the whole frame from 394 to 364.

Load path: tank ribs -> beams -> posts -> shelf. The pumps sit between the posts
bearing NOTHING, so their rubber feet stay compliant — they could not if load
passed through them.

Why the pumps lie motor-axis-along-Y
------------------------------------
The pump STEP measures 206 (motor axis) x 125 (port tip to tip) x 115 (feet to
top). Laid motor-along-X, two pumps span 250 in the PORT axis — the whole shelf
depth, with nothing left for structure. Turned 90° the pair spans 250 in X, which
the frame already needs for the 348 mm tank, and only 206 in Y.

PUMP B IS FLIPPED END-FOR-END. Both ports sit on opposite sides of the head, so
two adjacent pumps would point their inner ports straight at each other; flipping
lands the port clusters 112 mm apart in Y so the elbows interleave.

Fittings are SEAFLO SFFN1-1220-01 — 1/2"-14 FNPT x 1/2" barb, 90°, PA66, SWIVEL.
The swivel lets the bay be tight: NPT is tapered, so a fixed elbow lands wherever
it seals, and designing for an arbitrary clock angle would cost a clearance
annulus around every port. The nut still projects 22 mm beyond each port, and
THAT sets the post positions — see POST_X.

Sections
--------
Posts and beams share ONE width (SECT) so a post lands flush under the beam it
carries. An early cut had 18x26 posts under 15-wide beams — a beam narrower than
the post beneath it, which read as an error and wasted the post's section.

Loads
-----
5 gal + can ~= 21 kg ~= 206 N static; design to 3x for setting the pack down.
Split over two beams, ~310 N each on a 334 mm span: a 30 x 40 section sees
~1.6 MPa against PCTG's ~45 MPa yield and deflects ~0.5 mm — a ~28x margin.
CREEP is the real risk, not strength: hence PCTG (Tg ~85 C) in shade, never PLA
(Tg ~60 C, which a dark part in sun reaches).

Frame:
  • X = width, centred on 0. Split at X = 0; each half builds along X.
  • Y = depth. Y=0 is the back (against the pack frame), +Y away from the wearer.
  • Z = up. Z=0 is the shelf top.

Run:  py -3.12 -m src.pump_frame
"""
from __future__ import annotations

import pathlib

import cadquery as cq

from cadkit.cq_colors import color
from cadkit.fasteners import M4, ScrewJoint
from cadkit.freecad import show
from cadkit.joinery import PrintSpec, joint
from cadkit.step_export import export_step, print_pose

from .dimensions import BOOL_OVERSHOOT, REFERENCES_DIR

OUT = pathlib.Path(__file__).resolve().parent.parent

# ── Pump envelope — measured from references/seaflo_42_pump.step ─────────────
PUMP_MOTOR_L = 206.0
PUMP_PORT_W  = 125.0     # port tip to port tip
PUMP_H       = 115.0
PUMP_PORT_Z  = 80.0      # port centreline above the feet
PUMP_PORT_A  = 159.0     # port axis from the pump's REAR face, along the motor axis

# ── Tank (Scepter 5 gal military) ───────────────────────────────────────────
TANK_W, TANK_D, TANK_H = 348.0, 173.0, 478.0
RIB_INSET = 12.0         # ESTIMATE — verify with a straightedge
RIB_W     = 28.0         # ESTIMATE

SHELF_W, SHELF_D = 340.0, 250.0

# ── Sections ────────────────────────────────────────────────────────────────
SECT    = 30.0           # post side AND beam width — one number, flush faces
BEAM_H  = 40.0           # beam depth in Z (the bending dimension)
# The pump SEATING PLANE: the height of the surface the pumps bolt down to.
# This was a printed 4 mm deck that never survived the move to a lumber frame,
# leaving the pumps resting on nothing -- src.lumber_frame now puts real wood
# here, with its TOP face at this z, so the pumps and all the plumbing keep the
# heights they already had. src.build asserts the two agree.
FLOOR_T = 4.0            # carries no tank load, so the floor stays thin
BOLT_HOLE_R = 2.0        # the pump's own mounting bores (D4, exact from drawing)
POST_Z0 = FLOOR_T
# Beam underside. NOT just "clears the pumps" — it also has to clear the HOSE
# that crosses over them. Pump B's inner port sits at x=0 with its nut reaching
# into pump A's half, so that line cannot run forward at port height without
# going through pump A (measured: 8190 mm3). Its only way out is OVER the pumps,
# and a 19 mm line needs its centre at z=134 with 9.5 mm either side. 124 left
# 5 mm of headroom over the 119 mm pumps and blocked the line; 148 leaves 29.
# The alternative was a ~21 mm gap BETWEEN the pumps, which buys the same
# clearance out of WIDTH — and width is the scarce axis here (the posts already
# overhang the 340 mm shelf). Height is not: this costs 24 mm against 820.
POST_Z1 = 148.0
DECK_Z  = POST_Z1 + BEAM_H       # 164 — the tank sits here

# ── Fitting envelope — SEAFLO SFFN1-1220-01 ─────────────────────────────────────
# Conservative clearance solid, NOT a model of the part. Replace with measured
# numbers once one is in hand. These were set for a BRASS fitting, so the PA66
# part should come in UNDER them — POST_X (and so FRAME_W) is derived from
# ELBOW_NUT_L and should shrink, never grow, when the real number lands.
ELBOW_NUT_D, ELBOW_NUT_L = 34.0, 22.0    # barrel coaxial with the port
ELBOW_LEG_D, ELBOW_LEG_L = 26.0, 45.0    # the turned leg, aimed along +Y

# ── Pump bay ────────────────────────────────────────────────────────────────
# The pumps meet at X=0: with the spine gone there is nothing between them.
PUMP_CX    = PUMP_PORT_W / 2.0                     # 62.5 — each pump's centre |X|
PUMP_X_OUT = PUMP_PORT_W                           # 125  — outer port tip
PUMP_Y0    = 2.0

# Post centreline: the outer swivel nut reaches PUMP_X_OUT + ELBOW_NUT_L = 147,
# so the post's INNER face must clear it. Three earlier guesses (135, 150, 160)
# all sat on that nut.
POST_X  = PUMP_X_OUT + ELBOW_NUT_L + 5.0 + SECT / 2.0      # 167
FRAME_W = 2 * (POST_X + SECT / 2.0)                        # 364
FRAME_D = 210.0
BEAM_YS = (RIB_INSET, TANK_D - RIB_INSET)                  # 12 and 161

# ── Joinery — in the beams, at X=0, built in the LAST layers ────────────────
JOINT_W = 18.0           # across the beam's width
JOINT_L = 20.0           # engagement along X
UP = PrintSpec(nozzle=0.4, facing="up")

_PORT_YS = (PUMP_Y0 + PUMP_PORT_A, PUMP_Y0 + PUMP_MOTOR_L - PUMP_PORT_A)   # 161, 49

# ── PCB ────────────────────────────────────────────────
# PCB_BOSS_D / PCB_CLR / PCB_WALL_T / PCB_COVER_T are gone with the rest of the
# dead block below: nothing read them, and PCB_CLR here was 6.0 while the live
# one in src/housing.py is 2.0 — two values behind one name, which is how the
# wrong one gets picked up. The PCB_README warning they carried ("model from
# the routed board, never from the placement table") belongs with the live
# geometry: a typed copy agreed while two connectors sat 0.54 mm short of the
# board edge, and kept drilling bosses at +-64 after the laminate had moved to
# +-41. src/housing.py states it where it sources the board from
# Boards("elec/geom").

# Heights for footprints cadkit's shared table does not carry. Mirrors
# elec/cad_geom_check.py — a footprint with no height RAISES rather than being
# silently dropped from the CAD, which is the behaviour we want.
_PCB_HEIGHT = {
    "Buzzer_12x9.5RM7.6": 9.5, "CP_Elec_10x10.5": 10.5,
    "ESP32-WROOM-32E-FABDRILL": 3.1, "L_Bourns_SRN6045TA": 4.5,
    "TO-252-3_TabPin2": 2.3, "TO-263-2": 4.6,
    "PinHeader_1x06_P2.54mm_Vertical": 8.5, "C_0603_1608Metric": 0.9,
    # the buck's real package: HSOIC-8 with PowerPAD. Same 1.75 mm body as the
    # plain SOIC-8 cadkit already lists -- what changed is the land under it.
    "SOIC-8-1EP-FABDRILL": 1.75,
    "R_0805_2012Metric": 0.6,          # VGATE dropper: 0805 for its 0.1 W
    # MEASURED, not estimated: all five terminals are now the SAME part,
    # Ningbo Kangnex WJ500V-5.08-NP, whose customer drawing (LCSC C8465,
    # sheet 1/1) gives 14.07 mm above the board for the whole family. That
    # replaces the 17.0 / 15.0 guesses this table used to carry, and it
    # moves the right way: the PCB shroud needs 2.93 mm LESS standoff than
    # the old MKDS-3 estimate demanded.
    "TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal": 14.07,
    "TerminalBlock_Phoenix_MKDS-3-4-5.08_1x04_P5.08mm_Horizontal": 14.07,
    "TerminalBlock_Phoenix_MKDS-3-5-5.08_1x05_P5.08mm_Horizontal": 14.07,
}

# The board's own placement lives in src/housing.py, which is what the
# assembly places. It used to live here too -- a second _BOARDS, a second
# pose and a second pcb_solid(), from when the board bolted to the printed
# frame's +X face. Two pcb_solid()s is how elec/cad_geom_check.py came to be
# aimed at the one nothing places; that is why the dead one is gone rather
# than left for reference. _PCB_HEIGHT stays, because housing imports it.

def _pump(flip: bool) -> cq.Workplane:
    p = cq.importers.importStep(str(REFERENCES_DIR / "seaflo_42_pump.step"))
    p = p.rotate((0, 0, 0), (0, 0, 1), 90)       # motor along Y, ports along X
    if flip:
        p = p.rotate((0, 0, 0), (0, 0, 1), 180)
    return p


def pump_bolt_xy():
    """The eight M4 bolt positions, MEASURED off the placed pumps.

    Read out of the pump solid (its four vertical 4.0 mm bores) rather than
    re-derived from BOLT_DX/BOLT_DY/BOLT_ROW1_X. The pattern in the drawing is
    stated relative to the pump's own rear edge and its own axes, and the pumps
    are rotated 90 degrees and one of them a further 180 -- so re-deriving it
    here means redoing that transform by hand, which is exactly the kind of sign
    error this project has already paid for twice. Measuring the placed solid
    cannot drift from where the pump actually is.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    out = []
    for side in (-1, 1):
        seen = set()
        for f in _pump_placed(side).faces().vals():
            if f.geomType() != "CYLINDER":
                continue
            c = BRepAdaptor_Surface(f.wrapped).Cylinder()
            if abs(c.Radius() - BOLT_HOLE_R) > 0.01:
                continue
            if abs(c.Axis().Direction().Z()) < 0.9:      # must run up the floor
                continue
            loc = c.Location()
            seen.add((round(loc.X(), 3), round(loc.Y(), 3)))
        if len(seen) != 4:
            raise SystemExit("pump %+d: found %d mounting bores, expected 4 -- "
                             "the pump model changed" % (side, len(seen)))
        out.extend(sorted(seen))
    return out


def _pump_placed(side: int) -> cq.Workplane:
    p = _pump(flip=(side > 0))
    bb = p.val().BoundingBox()
    return p.translate((side * PUMP_CX - (bb.xmin + bb.xlen / 2.0),
                        PUMP_Y0 - bb.ymin,
                        FLOOR_T - bb.zmin))


# Which way each elbow's leg is aimed. The fitting SWIVELS, so the clock angle
# is chosen rather than inherited from the thread taper — but it may only be
# chosen in the plane PERPENDICULAR TO THE PORT AXIS, i.e. the Y-Z plane. A leg
# can point +Y, -Y, +Z or -Z; it can never point along X. src/plumbing.py routes
# from whatever these pick, so the two files must agree: change a clock here and
# the hose model follows it.
ELBOW_CLOCK = {"+y": ((1, 0, 0), -90), "-y": ((1, 0, 0), +90),
               "+z": None,             "-z": ((1, 0, 0), 180)}


def _elbow(x_tip, y, z, x_dir, clock):
    """Clearance envelope for one fitting, with its leg aimed `clock`.

    Built on XY and rotated, not on an XZ workplane: XZ's normal is -Y, so
    workplane(offset=y) there lands the solid at -y — which silently put every
    leg on the wrong side of the frame in the first cut of this file.
    """
    nut = (cq.Workplane("YZ").workplane(offset=x_tip)
           .circle(ELBOW_NUT_D / 2.0).extrude(x_dir * ELBOW_NUT_L)
           .translate((0, y, z)))
    leg = cq.Workplane("XY").circle(ELBOW_LEG_D / 2.0).extrude(ELBOW_LEG_L)
    rot = ELBOW_CLOCK[clock]
    if rot is not None:
        leg = leg.rotate((0, 0, 0), rot[0], rot[1])
    leg = leg.translate((x_tip + x_dir * ELBOW_NUT_L / 2.0, y, z))
    return nut.union(leg)


# port -> (x_tip, y, x_dir, clock). B's INNER leg is the odd one: aimed UP,
# because forward is pump A. Everything else goes out the front.
PORT_CLOCK = {"A_out": "+y", "A_in": "+y", "B_out": "+y", "B_in": "+z"}


def _elbows() -> cq.Workplane:
    zc = FLOOR_T + PUMP_PORT_Z
    ya, yb = _PORT_YS
    return (_elbow(-PUMP_X_OUT, ya, zc, -1, PORT_CLOCK["A_out"])
            .union(_elbow(0.0, ya, zc, +1, PORT_CLOCK["A_in"]))
            .union(_elbow(+PUMP_X_OUT, yb, zc, +1, PORT_CLOCK["B_out"]))
            .union(_elbow(0.0, yb, zc, -1, PORT_CLOCK["B_in"])))


def _tank() -> cq.Workplane:
    return (cq.Workplane("XY").workplane(offset=DECK_Z)
            .center(0, TANK_D / 2.0).rect(TANK_W, TANK_D).extrude(TANK_H))


def _shelf() -> cq.Workplane:
    return (cq.Workplane("XY").workplane(offset=-8.0)
            .center(0, SHELF_D / 2.0).rect(SHELF_W, SHELF_D).extrude(8.0))
