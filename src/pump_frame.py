"""v2 pump frame — the load-bearing table that carries the tank over both pumps.

v2 inverts v1: the TANK sits on top and the pumps underneath on the pack's shelf.
That puts ~21 kg of water on printed plastic, so this is a STRUCTURE first and an
enclosure second. The pumps are water-resistant and are NOT enclosed; only the
PCB needs shelter.

FOUR PRINTED PARTS, split for PRINTABILITY — not for bed size
-------------------------------------------------------------
The obvious shape — one table with posts rising into integral cross-beams —
cannot be printed. The beams span the pump bay at z=124 with nothing beneath
them, and no orientation rescues it: posts run in Z and beams run in X, so
whichever you stand on the bed, the other becomes an unsupported bridge. Closing
the opening with 45° chamfers instead would need ~125 mm of rise to span 250 mm,
and the pumps need exactly that volume.

So the table is split along its own load path:

  BASE   (x2)  deck + spine + posts. Prints deck-down: every feature is a
               vertical prism rising off the bed. No overhang anywhere.
  CRADLE (x2)  the two cross-beams plus their end ties, as one flat picture
               frame. Prints lying down: a constant section extruded 40 mm.
               No overhang anywhere.

The cradle DROPS ONTO the post tops, so that joint is loaded in pure compression
— the strong direction for printed plastic, and the direction the tank loads it
anyway. Nothing is glued into a bridge.

Load path: tank ribs -> cradle beams -> posts -> shelf. The pumps sit between the
posts bearing NOTHING, so their rubber feet stay compliant — they could not if
load passed through them.

Why the pumps lie motor-axis-along-Y
------------------------------------
The pump STEP measures 206 (motor axis) x 125 (port tip to tip) x 115 (feet to
top). Laid motor-along-X, two pumps span 250 in the PORT axis — the whole shelf
depth with nothing left for structure. Turned 90° the pair spans 250 in X, which
the frame already needs for the 348 mm tank, and only 206 in Y.

PUMP B IS FLIPPED END-FOR-END. Both ports sit on opposite sides of the head, so
two adjacent pumps would point their inner ports straight at each other; flipping
lands the port clusters 112 mm apart in Y (159 vs 47 from each pump's own rear
face) so the elbows interleave instead of colliding.

Fittings are Shurflo 244-3926 — 1/2"-14 NPT(F) x 1/2" barb, 90°, WINGNUT SWIVEL.
The swivel lets the bay be this tight: NPT is tapered, so a fixed elbow lands
wherever it seals, and designing for an arbitrary clock angle would cost a
clearance annulus around every port. The nut still projects 22 mm beyond each
port along the port axis, and THAT sets the post positions — see POST_X.

Sections
--------
Posts and beams share ONE width (SECT), so a post lands flush under the beam it
carries. The first cut of this file had 18x26 posts under 15-wide beams: the beam
was narrower than the post beneath it, which both read as an error and wasted the
post's section.

Loads
-----
5 gal + can ~= 21 kg ~= 206 N static; design to 3x for setting the pack down.
Split over two beams, ~310 N each. A 30 x 40 section on a 364 mm span sees
~1.7 MPa against PCTG's ~45 MPa yield and deflects ~0.6 mm — a ~26x margin. That
margin is also why the cradle's mid-span splice is sound despite sitting exactly
where bending peaks.

CREEP is the real risk, not strength: hence PCTG (Tg ~85 C) in shade, never PLA
(Tg ~60 C, which a dark part in sun reaches).

Frame:
  • X = width, centred on 0. Both parts split at X = 0.
  • Y = depth. Y=0 is the back (against the pack frame), +Y away from the wearer.
  • Z = up. Z=0 is the shelf top.

Run:  py -3.12 -m src.pump_frame
"""
from __future__ import annotations

import pathlib

import cadquery as cq

from cadkit.cq_colors import color
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
SECT     = 30.0          # post side AND beam width — one number, flush faces
BEAM_H   = 40.0          # beam depth in Z (the bending dimension)
FLOOR_T  = 4.0           # pump deck; carries no tank load, so it stays thin
SPINE_H  = 22.0          # deck spine at X=0 — stiffens it AND hosts the joint
POST_Z0  = FLOOR_T
POST_Z1  = 124.0         # post top = cradle underside; clears PUMP_H + FLOOR_T = 119
DECK_Z   = POST_Z1 + BEAM_H      # 164 — the tank sits here
SOCKET_D = 10.0          # how far a post top enters the cradle

# ── Fitting envelope — Shurflo 244-3926 ─────────────────────────────────────
# Conservative clearance solid, NOT a model of the part. Replace with measured
# numbers once one is in hand.
ELBOW_NUT_D, ELBOW_NUT_L = 34.0, 22.0    # barrel coaxial with the port
ELBOW_LEG_D, ELBOW_LEG_L = 26.0, 45.0    # the turned leg, aimed along +Y

# ── Pump bay ────────────────────────────────────────────────────────────────
PUMP_GAP   = 30.0                                  # channel at X=0 for the spine
PUMP_CX    = PUMP_GAP / 2 + PUMP_PORT_W / 2        # 77.5 — each pump's centre |X|
PUMP_X_OUT = PUMP_GAP / 2 + PUMP_PORT_W            # 140 — outer port tip
PUMP_Y0    = 2.0

# Post centreline: the outer swivel nut reaches PUMP_X_OUT + ELBOW_NUT_L = 162,
# so the post's INNER face must clear it. Three earlier guesses (135, 150, 160)
# all sat on that nut.
POST_X   = PUMP_X_OUT + ELBOW_NUT_L + 5.0 + SECT / 2.0      # 182
FRAME_W  = 2 * (POST_X + SECT / 2.0)                        # 394
FRAME_D  = 210.0
BEAM_YS  = (RIB_INSET, TANK_D - RIB_INSET)                  # 12 and 161

# ── Joinery ─────────────────────────────────────────────────────────────────
JOINT_W = 14.0           # across the spine face
JOINT_L = 16.0           # engagement length
UP = PrintSpec(nozzle=0.4, facing="up")      # both halves print "up"

# The inner swivel nuts cross X=0 at the two port rows, so the spine cannot run
# continuously. These are the Y bands it must skip.
_PORT_YS = (PUMP_Y0 + PUMP_PORT_A, PUMP_Y0 + PUMP_MOTOR_L - PUMP_PORT_A)   # 161, 49
_SKIP = ELBOW_NUT_D + 6.0                    # 40 — band left clear


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
    gh = PUMP_GAP / 2.0
    return (_elbow(-PUMP_X_OUT, ya, zc, -1, +1)
            .union(_elbow(-gh, ya, zc, +1, +1))
            .union(_elbow(+PUMP_X_OUT, yb, zc, +1, +1))
            .union(_elbow(+gh, yb, zc, -1, +1)))


def _spine_bands():
    """Y bands where a spine at X=0 clears the inner swivel nuts."""
    bands, y = [], 0.0
    for py in sorted(_PORT_YS):
        lo, hi = py - _SKIP / 2.0, py + _SKIP / 2.0
        if lo > y:
            bands.append((y, lo))
        y = hi
    if y < FRAME_D:
        bands.append((y, FRAME_D))
    return bands


# ── BASE: deck + spine + posts. Prints deck-down, zero overhang ─────────────
def _base_whole() -> cq.Workplane:
    out = (cq.Workplane("XY").center(0, FRAME_D / 2.0)
           .rect(FRAME_W, FRAME_D).extrude(FLOOR_T))
    for y0, y1 in _spine_bands():
        out = out.union(cq.Workplane("XY").workplane(offset=FLOOR_T)
                        .center(0, (y0 + y1) / 2.0)
                        .rect(SECT, y1 - y0).extrude(SPINE_H - FLOOR_T))
    for sx in (-1, 1):
        for by in BEAM_YS:
            out = out.union(cq.Workplane("XY").workplane(offset=POST_Z0)
                            .center(sx * POST_X, by)
                            .rect(SECT, SECT).extrude(POST_Z1 - POST_Z0))
    return out


# ── CRADLE: two beams + end ties, one flat picture frame ────────────────────
def _cradle_whole() -> cq.Workplane:
    out = None
    for by in BEAM_YS:
        b = (cq.Workplane("XY").workplane(offset=POST_Z1)
             .center(0, by).rect(FRAME_W, SECT).extrude(BEAM_H))
        out = b if out is None else out.union(b)
    for sx in (-1, 1):
        out = out.union(cq.Workplane("XY").workplane(offset=POST_Z1)
                        .center(sx * POST_X, sum(BEAM_YS) / 2.0)
                        .rect(SECT, BEAM_YS[1] - BEAM_YS[0]).extrude(BEAM_H))
    # Post sockets: locate the cradle in X-Y; load passes in compression through
    # the socket floor. Cut upward from the underside.
    for sx in (-1, 1):
        for by in BEAM_YS:
            out = out.cut(cq.Workplane("XY")
                          .workplane(offset=POST_Z1 - BOOL_OVERSHOOT)
                          .center(sx * POST_X, by)
                          .rect(SECT + 0.4, SECT + 0.4)
                          .extrude(SOCKET_D + BOOL_OVERSHOOT))
    return out


def _half_box(side: int) -> cq.Workplane:
    return (cq.Workplane("XY")
            .center(side * (FRAME_W / 4.0), FRAME_D / 2.0)
            .rect(FRAME_W / 2.0, FRAME_D + 2 * BOOL_OVERSHOOT)
            .extrude(DECK_Z + BOOL_OVERSHOOT))


def _base_half(side: int) -> cq.Workplane:
    """One printed base half, with the left/right joint in the spine.

    A cadkit mortise-and-tenon, not a butt: AGENTS.md is explicit that this joint
    is print-validated and should be CALLED, never re-modelled. Install is +x —
    the halves slide together across the split.
    """
    half = _base_whole().intersect(_half_box(side))
    j = joint(JOINT_W, JOINT_L, UP, UP, install="+x")
    zc = FLOOR_T + (SPINE_H - FLOOR_T) / 2.0
    tb = j.tenon(root=2.0).val().BoundingBox()
    # The tenon protrudes past X=0 into the other half's space, so without this
    # it would start in mid-air on the bed — a 0 mm^3 footprint, measured. The
    # deck LAPS under it instead: supported print, and a second shear face.
    lap_x, lap_clr = JOINT_L + 2.0, 0.25
    lap_z = zc + tb.zmin
    for y0, y1 in _spine_bands():
        if y1 - y0 < JOINT_L * 2.5:
            continue                           # band too short to host a joint
        yc = (y0 + y1) / 2.0
        if side < 0:
            half = (half
                    .union(cq.Workplane("XY").center(lap_x / 2.0, yc)
                           .rect(lap_x, SECT).extrude(lap_z))
                    .union(j.tenon(root=2.0).translate((0, yc, zc))))
        else:
            half = (half
                    .cut(cq.Workplane("XY")
                         .workplane(offset=-BOOL_OVERSHOOT)
                         .center(lap_x / 2.0, yc)
                         .rect(lap_x + 2 * lap_clr, SECT + 2 * lap_clr)
                         .extrude(lap_z + lap_clr + BOOL_OVERSHOOT))
                    .cut(j.mortise(drop=2.0).translate((0, yc, zc))))
    return half


def _cradle_half(side: int) -> cq.Workplane:
    """One printed cradle half.

    The splice lands at mid-span, where bending peaks — acceptable only because
    the margin there is ~26x. It is an interlocking HALF-LAP, not a butt: the -X
    half carries the top half of the section through the lap and the +X half the
    bottom, so the joint transfers moment in shear across a 36 mm overlap rather
    than relying on a glue line in tension.
    """
    whole = _cradle_whole()
    lap, clr = 36.0, 0.2
    zmid = POST_Z1 + BEAM_H / 2.0
    big = FRAME_W + 100.0
    yc, yd = FRAME_D / 2.0, FRAME_D + 2 * BOOL_OVERSHOOT

    outer = (cq.Workplane("XY")
             .center(side * (lap / 2.0 + big / 2.0), yc)
             .rect(big, yd).extrude(DECK_Z + BOOL_OVERSHOOT))
    if side < 0:                       # -X half keeps the TOP of the lap
        tier = (cq.Workplane("XY").workplane(offset=zmid + clr / 2.0)
                .center(0, yc).rect(lap, yd).extrude(BEAM_H))
    else:                              # +X half keeps the BOTTOM
        tier = (cq.Workplane("XY").center(0, yc)
                .rect(lap, yd).extrude(zmid - clr / 2.0))
    return whole.intersect(outer.union(tier))


base_left,   base_right   = _base_half(-1),   _base_half(+1)
cradle_left, cradle_right = _cradle_half(-1), _cradle_half(+1)

# Bases print deck-down as modelled; cradles print lying as modelled (constant
# section extruded in Z). Neither needs rotating — which is the whole point of
# the split.
PRINT_ROT = {}


def _tank() -> cq.Workplane:
    return (cq.Workplane("XY").workplane(offset=DECK_Z)
            .center(0, TANK_D / 2.0).rect(TANK_W, TANK_D).extrude(TANK_H))


def _shelf() -> cq.Workplane:
    return (cq.Workplane("XY").workplane(offset=-8.0)
            .center(0, SHELF_D / 2.0).rect(SHELF_W, SHELF_D).extrude(8.0))


def _build() -> None:
    asm = (cq.Assembly()
           .add(base_left,    name="base_left",    color=color("#3a7bd5"))
           .add(base_right,   name="base_right",   color=color("#2a5d9f"))
           .add(cradle_left,  name="cradle_left",  color=color("#4fa36b"))
           .add(cradle_right, name="cradle_right", color=color("#357a4c"))
           .add(_pump_placed(-1), name="pump_a", color=color("slategray"))
           .add(_pump_placed(+1), name="pump_b", color=color("#5a6b7a"))
           .add(_elbows(), name="fittings", color=color("#c8a24a"))
           .add(_tank(),  name="tank_viz",  color=color("#9fd4e8", alpha=0.35))
           .add(_shelf(), name="shelf_viz", color=color("#808080", alpha=0.5)))

    for nm, part in (("v2_base_left", base_left), ("v2_base_right", base_right),
                     ("v2_cradle_left", cradle_left),
                     ("v2_cradle_right", cradle_right)):
        export_step(print_pose(part, PRINT_ROT.get(nm)), str(OUT / (nm + ".step")))
        bb = part.val().BoundingBox()
        print("%-17s %6.1f x %6.1f x %6.1f mm" % (nm, bb.xlen, bb.ylen, bb.zlen))

    asm.save(str(OUT / "assembly.step"), mode="default")
    show(str(OUT / "assembly.step"))


if __name__ == "__main__":
    _build()
