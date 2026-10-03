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

Fittings are Shurflo 244-3926 — 1/2"-14 NPT(F) x 1/2" barb, 90°, WINGNUT SWIVEL.
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
POST_Z1 = 124.0          # beam underside; clears PUMP_H + FLOOR_T = 119
DECK_Z  = POST_Z1 + BEAM_H       # 164 — the tank sits here

# ── Fitting envelope — Shurflo 244-3926 ─────────────────────────────────────
# Conservative clearance solid, NOT a model of the part. Replace with measured
# numbers once one is in hand.
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
                        FRAME_D / 2.0 - (bb.ymin + bb.ylen / 2.0),
                        DECK_Z / 2.0 - (bb.zmin + bb.zlen / 2.0)))


def pcb_solid():
    """The board as the assembly places it — laminate + every routed part body.
    This is what elec/cad_geom_check.py checks against the routed board."""
    return _pose_board(_BOARDS.solid("main"))


def _pcb_panel() -> cq.Workplane:
    """Backing panel + standoff bosses on the +X face.

    The frame's +X face is NOT continuous — it is deck (z 0..4), two posts and
    two beams — so there is nothing behind most of the board to mount to. This
    panel supplies that surface. It costs nothing in the X-build: it occupies the
    first 4 mm of layers, so it prints flat on the bed and improves adhesion.
    """
    b = pcb_solid().val().BoundingBox()
    pad = 12.0
    panel = (cq.Workplane("YZ").workplane(offset=FRAME_W / 2.0)
             .center((b.ymin + b.ymax) / 2.0, (b.zmin + b.zmax) / 2.0)
             .rect(b.ylen + 2 * pad, b.zlen + 2 * pad)
             .extrude(PCB_PANEL_T))
    for hy, hz in PCB_HOLE_XY:                     # board coords -> world Y, Z
        cy = FRAME_D / 2.0 + hy
        cz = DECK_Z / 2.0 + hz
        panel = panel.union(cq.Workplane("YZ").workplane(offset=PCB_FACE_X)
                            .center(cy, cz).circle(PCB_BOSS_D / 2.0)
                            .extrude(PCB_STANDOFF))
    return panel


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


def _elbow(x_tip, y, z, x_dir, y_dir):
    """Clearance envelope for one fitting.

    Built on XY and rotated, not on an XZ workplane: XZ's normal is -Y, so
    workplane(offset=y) there lands the solid at -y — which silently put every
    leg on the wrong side of the frame in the first cut of this file.
    """
    nut = (cq.Workplane("YZ").workplane(offset=x_tip)
           .circle(ELBOW_NUT_D / 2.0).extrude(x_dir * ELBOW_NUT_L)
           .translate((0, y, z)))
    leg = (cq.Workplane("XY").circle(ELBOW_LEG_D / 2.0).extrude(ELBOW_LEG_L)
           .rotate((0, 0, 0), (1, 0, 0), -90 * y_dir)
           .translate((x_tip + x_dir * ELBOW_NUT_L / 2.0, y, z)))
    return nut.union(leg)


def _elbows() -> cq.Workplane:
    zc = FLOOR_T + PUMP_PORT_Z
    ya, yb = _PORT_YS
    return (_elbow(-PUMP_X_OUT, ya, zc, -1, +1)
            .union(_elbow(0.0, ya, zc, +1, +1))
            .union(_elbow(+PUMP_X_OUT, yb, zc, +1, +1))
            .union(_elbow(0.0, yb, zc, -1, +1)))


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
    return out.union(_pcb_panel())


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

# Each half stands on its OUTER face so the posts land in the first layers.
# Rotating about +Y by -90 maps x -> z (so x=-POST_X goes DOWN); by +90 maps
# x -> -z (so x=+POST_X goes down). print_pose then drops to z=0 and centres.
PRINT_ROT = {
    "v2_frame_left":  ((0, 1, 0), -90),
    "v2_frame_right": ((0, 1, 0), +90),
}


def _dock_placed() -> cq.Workplane:
    """v1's Makita dock, ported onto the -X outer face.

    The DOCK ITSELF ports unchanged — it is a Makita interface and v2 changes
    nothing about the battery. What does not port is v1's ATTACHMENT: it hung the
    dock on printed dovetail rails standing proud of the housing's -X wall. In
    v2's X-build that wall IS the bed face, so an arrowhead rail would print
    starting on its own point — the worst possible first layer. See the note in
    the module docstring.

    Placed here as a fit/width check only; the attachment is unresolved.
    """
    bb = battery_dock.val().BoundingBox()
    # The dock plate is 100.6 x 93.0 x 18.8, modelled flat. Stand it against the
    # -X face: its thickness runs out along -X, its 93 mm axis up in Z.
    d = (battery_dock
         .rotate((0, 0, 0), (0, 1, 0), 90)       # plate normal -> X
         .rotate((0, 0, 0), (1, 0, 0), 90))      # 93 mm axis -> Z
    db = d.val().BoundingBox()
    return d.translate((-FRAME_W / 2.0 - db.xlen - (db.xmin - db.xmin),
                        FRAME_D / 2.0 - (db.ymin + db.ylen / 2.0),
                        FLOOR_T - db.zmin))


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
           .add(_dock_placed(), name="battery_dock", color=color("#d08a3e"))
           .add(_tank(),  name="tank_viz",  color=color("#9fd4e8", alpha=0.35))
           .add(_shelf(), name="shelf_viz", color=color("#808080", alpha=0.5)))

    for nm, part in (("v2_frame_left", frame_left), ("v2_frame_right", frame_right)):
        posed = print_pose(part, PRINT_ROT.get(nm))
        export_step(posed, str(OUT / (nm + ".step")))
        bb = posed.val().BoundingBox()
        print("%-15s print pose %6.1f x %6.1f x %6.1f mm  (bed 255)"
              % (nm, bb.xlen, bb.ylen, bb.zlen))

    asm.save(str(OUT / "assembly.step"), mode="default")
    show(str(OUT / "assembly.step"))


if __name__ == "__main__":
    _build()
