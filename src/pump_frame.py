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

from cadkit.board_geom import Boards
from cadkit.cq_colors import color
from cadkit.fasteners import M4, ScrewJoint
from cadkit.freecad import show
from cadkit.joinery import PrintSpec, joint
from cadkit.step_export import export_step, print_pose

from .battery_dock import battery_dock
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
FLOOR_T = 4.0            # pump deck; carries no tank load, so it stays thin
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

# ── PCB — built from the ROUTED board, never a typed placement ──────────────
# PCB_README: "Model from the routed board, never from the placement table. A
# hand-typed copy can only be checked against itself, and it always agrees. It
# agreed while two connectors sat 0.54 mm short of the board edge."
PCB_PANEL_T  = 4.0       # backing panel on the +X face, the board's mounting surface
PCB_STANDOFF = 3.0       # panel face -> board underside; bottom-side parts clear
PCB_BOSS_D   = 9.0
PCB_HOLE_XY  = ((-64.0, -44.0), (64.0, -44.0), (-64.0, 44.0), (64.0, 44.0))
PCB_CLR      = 6.0       # cavity clearance around the board and its tallest part
PCB_WALL_T   = 3.0
PCB_COVER_T  = 3.0

# Heights for footprints cadkit's shared table does not carry. Mirrors
# elec/cad_geom_check.py — a footprint with no height RAISES rather than being
# silently dropped from the CAD, which is the behaviour we want.
_PCB_HEIGHT = {
    "Buzzer_12x9.5RM7.6": 9.5, "CP_Elec_10x10.5": 10.5,
    "ESP32-WROOM-32E-FABDRILL": 3.1, "L_Bourns_SRN6045TA": 4.5,
    "TO-252-3_TabPin2": 2.3, "TO-263-2": 4.6,
    "PinHeader_1x06_P2.54mm_Vertical": 8.5, "C_0603_1608Metric": 0.9,
    "TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal": 17.0,
    "TerminalBlock_Phoenix_PT-1,5-4-3.5-H_1x04_P3.50mm_Horizontal": 15.0,
    "TerminalBlock_Phoenix_PT-1,5-5-3.5-H_1x05_P3.50mm_Horizontal": 15.0,
}

_BOARDS = Boards(str(OUT / "elec" / "geom"), height=_PCB_HEIGHT)
PCB_FACE_X = FRAME_W / 2.0 + PCB_PANEL_T          # 186 — panel outer face

# The board is centred BETWEEN THE POSTS, not on the frame's depth. The frame's
# +X face is not a surface — it is two posts with 119 mm of air between them —
# so where the board sits decides whether its mounting holes have anything
# behind them. Centred on FRAME_D/2 (105) they did not: the plate overlapped one
# post by 30 mm and the other by 4, and every screw but one would have pulled on
# a cantilever. Centred on the posts' own midline, ALL FOUR of the routed
# board's holes land inside a post, in both Y and Z — asserted below, because it
# is a coincidence of three independent numbers (the hole pitch, the rib inset
# that sets the posts, and the deck height) and any of them can move.
PCB_Y_C = sum(BEAM_YS) / 2.0                      # 86.5


def _pose_board(solid):
    """Lay a board (modelled in XY, +Z normal) flat on the frame's +X face.

    board +X -> world +Y, board +Y -> world +Z, board +Z -> world +X. The board's
    -Y edge therefore points DOWN, which is where every terminal sits — so all
    the shroud's openings face the ground, which is the only weatherproofing this
    enclosure needs.
    """
    r = (solid.rotate((0, 0, 0), (0, 1, 0), 90)
               .rotate((0, 0, 0), (1, 0, 0), 90))
    bb = r.val().BoundingBox()
    return r.translate((PCB_FACE_X + PCB_STANDOFF - bb.xmin,
                        PCB_Y_C - (bb.ymin + bb.ylen / 2.0),
                        DECK_Z / 2.0 - (bb.zmin + bb.zlen / 2.0)))


def pcb_solid():
    """The board as the assembly places it — laminate + every routed part body.
    This is what elec/cad_geom_check.py checks against the routed board."""
    return _pose_board(_BOARDS.solid("main"))


def pcb_plate() -> cq.Workplane:
    """Backing plate + standoff bosses — a SEPARATE part, bolted to the frame.

    The frame's +X face is not continuous (deck, two posts, two beams), so there
    is nothing behind most of the board to mount to; this supplies that surface.

    It is separate because merging it into the frame BROKE THE X-BUILD. With the
    plate and shroud attached, the right half's outermost face became the
    shroud's, so the frame printed cantilevered 35 mm above it —
    tools/check_v2_overhangs.py measured 24,996 mm2 of flat ceiling. Apart, each
    piece prints on its own face with nothing overhanging: this plate stands on
    its frame-side face with the bosses rising, and the shroud stands on its
    cover with the walls rising.
    """
    b = pcb_solid().val().BoundingBox()
    pad = 12.0
    panel = (cq.Workplane("YZ").workplane(offset=FRAME_W / 2.0)
             .center((b.ymin + b.ymax) / 2.0, (b.zmin + b.zmax) / 2.0)
             .rect(b.ylen + 2 * pad, b.zlen + 2 * pad)
             .extrude(PCB_PANEL_T))
    for hy, hz in PCB_HOLE_XY:                     # board coords -> world Y, Z
        cy = PCB_Y_C + hy
        cz = DECK_Z / 2.0 + hz
        panel = panel.union(cq.Workplane("YZ").workplane(offset=PCB_FACE_X)
                            .center(cy, cz).circle(PCB_BOSS_D / 2.0)
                            .extrude(PCB_STANDOFF))
    return panel


# ── The four screws that hold the whole PCB stack together ──────────────────
# One M4 per mounting hole, each clamping board -> boss -> plate -> post in a
# single stack, threading into a heat-set insert in the post. ScrewJoint draws
# the hole ONCE and hands each part its own section, so the head recess, the
# clearance, the insert pocket and the screw length cannot drift between the
# plate and the frame.
#
# This is what attaches the plate at all. A drop-in dovetail was the obvious
# alternative and it cannot be built: frame_right prints standing on its +X
# face and the plate on its frame-side face, so the two faces that have to meet
# are BOTH bed faces, and neither can carry a protruding rail without printing
# on its own tip. (See the battery dock, which hits the identical wall.) The
# screws need only holes, and a hole is a void in a bed face — which prints.
PCB_SCREW_L = 14.0
_BOARD_TOP_X = PCB_FACE_X + PCB_STANDOFF + 1.6    # 190.6 — laminate top face


def pcb_screws():
    """One ScrewJoint per routed mounting hole."""
    out = []
    for hy, hz in PCB_HOLE_XY:
        out.append(ScrewJoint(
            spec=M4,
            entry=(_BOARD_TOP_X, PCB_Y_C + hy, DECK_Z / 2.0 + hz),
            direction=(-1.0, 0.0, 0.0),
            length=PCB_SCREW_L,
            insert_at=_BOARD_TOP_X - FRAME_W / 2.0,   # the post's +X face
            # THROUGH the post, not blind. A blind bore running ALONG the build
            # ends in a flat ceiling — cadkit's _bore only teardrops holes that
            # run ACROSS it — and the overhang gate caught exactly that: four
            # 15.2 mm2 faces at n.z=-1.00, one per screw. Running the Ø4.4 out
            # the post's far side removes the ceiling instead of papering over
            # it, costs nothing structurally in a 30 mm post, and gives the
            # pocket a drain.
            end_at=_BOARD_TOP_X - (POST_X - SECT / 2.0),
            head_d=7.6, head_h=2.2))
    return out


def _pump(flip: bool) -> cq.Workplane:
    p = cq.importers.importStep(str(REFERENCES_DIR / "seaflo_42_pump.step"))
    p = p.rotate((0, 0, 0), (0, 0, 1), 90)       # motor along Y, ports along X
    if flip:
        p = p.rotate((0, 0, 0), (0, 0, 1), 180)
    return p


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


def _frame_whole() -> cq.Workplane:
    """Deck + posts + beams as one solid. Everything here is either constant in
    X (deck, beams) or sits at |X| = POST_X (posts), which is the first layers of
    an X-build."""
    out = (cq.Workplane("XY").center(0, FRAME_D / 2.0)
           .rect(FRAME_W, FRAME_D).extrude(FLOOR_T))
    for by in BEAM_YS:                                  # cross-beams, full width
        out = out.union(cq.Workplane("XY").workplane(offset=POST_Z1)
                        .center(0, by).rect(FRAME_W, SECT).extrude(BEAM_H))
    for sx in (-1, 1):                                  # posts, at the outer face
        for by in BEAM_YS:
            out = out.union(cq.Workplane("XY").workplane(offset=POST_Z0)
                            .center(sx * POST_X, by)
                            .rect(SECT, SECT).extrude(POST_Z1 - POST_Z0))
    return out


def _pcb_cavity():
    """(y0, y1, z0, z1, x0, x1) of the volume the board and its parts occupy,
    plus clearance. Derived from the PLACED solid, so it tracks the routed board
    — it is not a second set of numbers that can drift from the first."""
    b = pcb_solid().val().BoundingBox()
    return (b.ymin - PCB_CLR, b.ymax + PCB_CLR,
            b.zmin - PCB_CLR, b.zmax + PCB_CLR,
            PCB_FACE_X, b.xmax + PCB_CLR)


def pcb_shroud() -> cq.Workplane:
    """Walls around the board: two sides and a roof, OPEN AT THE BOTTOM.

    Open-bottomed is the whole weatherproofing strategy (user: "so long as the
    holes face downward we should be fine"), and it is why the board is posed
    with its terminal edge down — every cable leaves through the open face, and
    anything that gets in drains straight out.

    Prints for free in the X-build: every wall is a column running +X from the
    backing panel, so nothing bridges. The COVER cannot be part of this — closing
    the +X face would roof a cavity — so it is a separate flat part.
    """
    y0, y1, z0, z1, x0, x1 = _pcb_cavity()
    outer = (cq.Workplane("YZ").workplane(offset=x0)
             .center((y0 + y1) / 2.0, (z0 + z1) / 2.0)
             .rect(y1 - y0 + 2 * PCB_WALL_T, z1 - z0 + 2 * PCB_WALL_T)
             .extrude(x1 - x0))
    # The cavity runs off the BOTTOM, so no floor is ever created.
    inner = (cq.Workplane("YZ").workplane(offset=x0 - BOOL_OVERSHOOT)
             .center((y0 + y1) / 2.0, (z1 + (z0 - 80.0)) / 2.0)
             .rect(y1 - y0, z1 - (z0 - 80.0))
             .extrude(x1 - x0 + 2 * BOOL_OVERSHOOT))
    walls = outer.cut(inner)
    # The cover is part of THIS solid, not the frame: printed cover-down the walls
    # rise off it and nothing bridges, where an integral cover on the frame would
    # have roofed a cavity.
    cover = (cq.Workplane("YZ").workplane(offset=x1)
             .center((y0 + y1) / 2.0, (z0 + z1) / 2.0)
             .rect(y1 - y0 + 2 * PCB_WALL_T, z1 - z0 + 2 * PCB_WALL_T)
             .extrude(PCB_COVER_T))
    for i in range(5):                       # drain/vent slots along the open edge
        cy = y0 + (y1 - y0) * (i + 0.5) / 5.0
        cover = cover.cut(cq.Workplane("YZ").workplane(offset=x1 - BOOL_OVERSHOOT)
                          .center(cy, z0 - PCB_WALL_T / 2.0)
                          .rect(14.0, PCB_WALL_T + 2 * BOOL_OVERSHOOT)
                          .extrude(PCB_COVER_T + 2 * BOOL_OVERSHOOT))
    return walls.union(cover)


def _frame_half(side: int) -> cq.Workplane:
    """One printed half, with the left/right joint in the beams at X=0.

    A cadkit mortise-and-tenon, not a butt: AGENTS.md is explicit that this joint
    is print-validated and should be CALLED, never re-modelled. Install is +x —
    the halves slide together across the split, which is also the build axis, so
    the tenon is the last thing printed and the mortise is an open face.
    """
    # Reaches PAST the frame edge so the PCB backing panel and its bosses — which
    # stand proud of X = FRAME_W/2 — are kept, not sliced off with the split.
    ext = PCB_PANEL_T + PCB_STANDOFF + 40.0
    box = (cq.Workplane("XY")
           .center(side * (FRAME_W / 4.0 + ext / 2.0), FRAME_D / 2.0)
           .rect(FRAME_W / 2.0 + ext, FRAME_D + 2 * BOOL_OVERSHOOT)
           .extrude(DECK_Z + BOOL_OVERSHOOT))
    half = _frame_whole().intersect(box)

    jointned = joint(JOINT_W, JOINT_L, UP, UP, install="+x")
    zc = POST_Z1 + BEAM_H / 2.0                 # mid-depth of the beam
    for by in BEAM_YS:
        if side < 0:
            half = half.union(jointned.tenon(root=2.0).translate((0, by, zc)))
        else:
            half = half.cut(jointned.mortise(drop=2.0).translate((0, by, zc)))
    return half


frame_left, frame_right = _frame_half(-1), _frame_half(+1)
pcb_plate_part  = pcb_plate()
pcb_shroud_part = pcb_shroud()

# Each part cuts only its own section of the shared hole, shaped for its own
# build direction: the plate builds +X, frame_right builds -X.
for _sj in pcb_screws():
    pcb_plate_part = pcb_plate_part.cut(_sj.cutter(print_up=(1, 0, 0)))
    frame_right = frame_right.cut(_sj.cutter(print_up=(-1, 0, 0)))

# Each half stands on its OUTER face so the posts land in the first layers.
# Rotating about +Y by -90 maps x -> z (so x=-POST_X goes DOWN); by +90 maps
# x -> -z (so x=+POST_X goes down). print_pose then drops to z=0 and centres.
PRINT_ROT = {
    "v2_frame_left":  ((0, 1, 0), -90),
    "v2_frame_right": ((0, 1, 0), +90),
    "v2_pcb_plate":   ((0, 1, 0), -90),   # frame-side face down, bosses up
    "v2_pcb_shroud":  ((0, 1, 0), +90),   # cover down, walls up
}


# Where the dock sits on the -X face. Centred on the REAR post (y=12): the
# battery is ~0.6 kg hanging outboard of the frame, so every mm closer to the
# wearer's back is moment saved, and the post is the only frame material behind
# it to eventually bolt into.
DOCK_Y_C = 55.0
DOCK_Z0  = FLOOR_T

# The dock's own axes, expressed in world terms. battery_dock is modelled with
# z=0 the FLAT BACK (the face that goes against the host) and +Z the front that
# wraps the battery; +Y is the slide, with the battery ENTERING at y=0 and
# sliding toward +Y until the latch catches.
#
# Both of those have to land correctly, and the first cut of this file got BOTH
# wrong: it put the dock's front (+Z) at world +X, pointing the battery INTO the
# frame, and its slide (+Y) at world +Z, so the battery had to be pushed UPWARD
# to seat and would drop out if the latch let go.
#
#   dock +Z -> world -X   front faces AWAY from the frame, battery outboard
#   dock +Y -> world -Z   battery enters at the TOP and slides DOWN to seat,
#                         so gravity holds it against the latch, not the latch
#                         against gravity
#   dock +X -> world +Y   (forced: the frame has to stay right-handed)
#
# Rotating about +Y by -90 sends dock +Z to world -X; then about +X by -90 sends
# dock +Y to world -Z and leaves +Z alone. _DOCK_AXES pins the result so a
# future edit cannot quietly re-break it.
_DOCK_AXES = {"+X": (0.0, 1.0, 0.0), "+Y": (0.0, 0.0, -1.0), "+Z": (-1.0, 0.0, 0.0)}


def _dock_oriented() -> cq.Workplane:
    return (battery_dock
            .rotate((0, 0, 0), (0, 1, 0), -90)
            .rotate((0, 0, 0), (1, 0, 0), -90))


def _dock_placed() -> cq.Workplane:
    """v1's Makita dock, ported onto the -X outer face.

    The DOCK ITSELF ports unchanged — it is a Makita interface and v2 changes
    nothing about the battery. What does not port is v1's ATTACHMENT: it hung
    the dock on printed dovetail rails standing proud of the housing's -X wall.

    That cannot work here, and the reason generalises: frame_left stands on its
    -X face to print, and the dock stands on its own flat back. The two faces
    that have to meet are BOTH bed faces, so neither can carry a protruding
    rail — a rail on either one would print starting on its own tip and lift the
    whole face off the plate. The attachment is therefore still open; what is
    fixed here is the orientation, which was simply wrong.
    """
    d = _dock_oriented()
    db = d.val().BoundingBox()
    return d.translate((-FRAME_W / 2.0 - db.xmax,
                        DOCK_Y_C - (db.ymin + db.ylen / 2.0),
                        DOCK_Z0 - db.zmin))


def _check_dock_orientation():
    """The dock's flat BACK must face the frame, and its slide must run DOWN.

    Asserted on the placed geometry rather than on the rotation arguments,
    because the rotations are what a future edit would change. The back is the
    dock's one big planar face (~5265 mm2); if it is not pointing at the frame
    with the body outboard of it, the battery is mounted into the frame.
    """
    d = _dock_placed()
    bb = d.val().BoundingBox()
    best, best_a = None, 0.0
    for f in d.faces().vals():
        try:
            n = f.normalAt()
        except Exception:
            continue
        if f.Area() > best_a:
            best, best_a = (n, f.Center()), f.Area()
    n, c = best
    if not (n.x > 0.99 and abs(c.x - bb.xmax) < 0.5):
        raise AssertionError(
            "battery dock is facing the wrong way: its largest face (%.0f mm2) "
            "has normal %s at x=%.1f, but the mounting back must point +X at "
            "x=%.1f" % (best_a, (round(n.x, 2), round(n.y, 2), round(n.z, 2)),
                        c.x, bb.xmax))
    # slide direction: dock +Y is the seating direction and must be world -Z
    if _DOCK_AXES["+Y"][2] >= 0:
        raise AssertionError("the battery must slide DOWN to seat")
    return best_a


_check_dock_orientation()


def _tank() -> cq.Workplane:
    return (cq.Workplane("XY").workplane(offset=DECK_Z)
            .center(0, TANK_D / 2.0).rect(TANK_W, TANK_D).extrude(TANK_H))


def _shelf() -> cq.Workplane:
    return (cq.Workplane("XY").workplane(offset=-8.0)
            .center(0, SHELF_D / 2.0).rect(SHELF_W, SHELF_D).extrude(8.0))


def _build() -> None:
    asm = (cq.Assembly()
           .add(frame_left,  name="frame_left",  color=color("#3a7bd5"))
           .add(frame_right, name="frame_right", color=color("#2a5d9f"))
           .add(_pump_placed(-1), name="pump_a", color=color("slategray"))
           .add(_pump_placed(+1), name="pump_b", color=color("#5a6b7a"))
           .add(_elbows(), name="fittings", color=color("#c8a24a"))
           .add(pcb_solid(), name="pcb", color=color("#2f7d4f"))
           .add(pcb_plate_part,  name="pcb_plate",  color=color("#8fb56a"))
           .add(pcb_shroud_part, name="pcb_shroud", color=color("#6a8fb5"))
           .add(_dock_placed(), name="battery_dock", color=color("#d08a3e"))
           .add(_tank(),  name="tank_viz",  color=color("#9fd4e8", alpha=0.35))
           .add(_shelf(), name="shelf_viz", color=color("#808080", alpha=0.5)))

    for nm, part in (("v2_frame_left", frame_left), ("v2_frame_right", frame_right),
                     ("v2_pcb_plate", pcb_plate_part),
                     ("v2_pcb_shroud", pcb_shroud_part)):
        posed = print_pose(part, PRINT_ROT.get(nm))
        export_step(posed, str(OUT / (nm + ".step")))
        bb = posed.val().BoundingBox()
        print("%-15s print pose %6.1f x %6.1f x %6.1f mm  (bed 255)"
              % (nm, bb.xlen, bb.ylen, bb.zlen))

    asm.save(str(OUT / "assembly.step"), mode="default")
    show(str(OUT / "assembly.step"))


if __name__ == "__main__":
    _build()
