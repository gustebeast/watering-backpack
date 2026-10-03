"""v2 pump frame — the load-bearing table that carries the tank over both pumps.

v2 inverts v1: the TANK sits on top and the pumps sit underneath on the pack's
shelf, instead of the pump hanging above the can. That puts ~21 kg of water on
printed plastic, so this part is a STRUCTURE first and an enclosure second.

  • It is a TABLE, not a box. Two cross-beams run in X under the Scepter's two
    moulded base ribs; eight posts carry them straight down to the shelf. The
    pumps sit between the posts carrying NOTHING — their rubber feet stay
    compliant, which they could not do if load passed through them.

  • The pumps are NOT enclosed. They are water-resistant; only the PCB needs
    shelter (its own open-bottomed shroud, added separately). Open structure
    drains instead of becoming a bucket around electronics.

Why the pumps lie motor-axis-along-Y
------------------------------------
The pump STEP measures 206 (motor axis) x 125 (port tip to tip) x 115 (feet to
top). Laid motor-along-X, two pumps side by side span 250 mm in the PORT axis —
the full depth of the shelf, with nothing left for walls. Turned 90°, the pair
spans 250 in X (which the frame already needs for the 348 mm tank) and only 206
in Y. That drops frame depth from ~256 to 210, which also brings every printed
piece inside the 255 mm bed.

Both ports sit on opposite sides of the head, so two adjacent pumps would have
their inner ports pointing at each other. PUMP B IS FLIPPED END-FOR-END so the
port clusters land at different Y (159 vs 47 from its own rear face, 112 mm
apart) and the elbows interleave instead of colliding.

Fittings are Shurflo 244-3926 — 1/2"-14 NPT(F) x 1/2" barb, 90°, WINGNUT SWIVEL.
The swivel is what lets the bay be this tight: NPT is tapered, so a fixed elbow
lands wherever it seals, and designing for an arbitrary clock angle would have
cost a clearance annulus around every port. The swivel is aimed after tightening,
so only the chosen direction needs room.

Loads
-----
5 gal + can ~= 21 kg ~= 206 N static; design to 3x for setting the pack down.
Split over two beams, ~310 N each, spanning 270 mm between the posts that
straddle the pump bay. A 15 x 40 section sees ~2.6 MPa against PCTG's ~45 MPa
yield and deflects ~0.5 mm. Strength is never the issue at these numbers —
CREEP is, which is why this prints in PCTG (Tg ~85 C) and lives in shade, not
PLA (Tg ~60 C, which a dark part in sun will reach).

Frame:
  • X = width (side to side), centred on 0. Split line at X = 0.
  • Y = depth. Y=0 is the back (against the pack frame), +Y away from the wearer.
  • Z = up. Z=0 is the shelf top = the underside of the frame.

Run:  py -3.12 -m src.pump_frame
"""
from __future__ import annotations

import pathlib

import cadquery as cq

from cadkit.cq_colors import color
from cadkit.freecad import show
from cadkit.step_export import export_step, print_pose

from .dimensions import BOOL_OVERSHOOT, REFERENCES_DIR

OUT = pathlib.Path(__file__).resolve().parent.parent

# ── Pump envelope — measured from references/seaflo_42_pump.step ─────────────
# In the STEP's own frame: X 0..206 (motor axis), Y -62.5..62.5 (port axis),
# Z 0..115 (feet at 0). Ports on the head end, centreline 80 above the feet.
PUMP_MOTOR_L = 206.0
PUMP_PORT_W  = 125.0     # port tip to port tip
PUMP_H       = 115.0
PUMP_PORT_Z  = 80.0      # port centreline above the feet
PUMP_PORT_A  = 159.0     # port axis from the pump's REAR face, along the motor axis

# ── Tank (Scepter 5 gal military) ───────────────────────────────────────────
TANK_W       = 348.0
TANK_D       = 173.0
TANK_H       = 478.0
# It stands on two wide moulded ribs — one at the frame edge, one at the far
# edge — so the load arrives as two LINES, not a face. The beams go under them.
RIB_INSET    = 12.0      # rib centreline in from each base edge
RIB_W        = 28.0      # rib width (conservative; verify with a straightedge)

# ── Pack frame ──────────────────────────────────────────────────────────────
SHELF_W      = 340.0
SHELF_D      = 250.0

# ── Frame geometry ──────────────────────────────────────────────────────────
FRAME_W      = 356.0                  # set by the TANK (348), not the pumps
FRAME_D      = 210.0                  # set by the pumps (206) + a little
FLOOR_T      = 4.0                    # pump deck; carries no tank load
POST_Z1      = 124.0                  # post top / beam underside (clears PUMP_H=115)
BEAM_H       = 40.0                   # 15 x 40 section — see Loads above
BEAM_W       = 15.0
DECK_Z       = POST_Z1 + BEAM_H       # 164 — tank sits here

POST_W       = 18.0                   # post section (X)
POST_D       = 26.0                   # post section (Y)
# |X| of the posts. Moved outboard from 135: the outer port of the -X pump lands
# at X=-125, Y=161 — directly under the front beam — and its swivel nut reaches
# X=-147. A post at 135 (spanning 126..144) sat right on it; so did 150
# (141..159). At 160 the post spans 151..169, clearing the nut by 4 mm.
# One pair per beam end, so the beam spans 320 and cantilevers 18 past them:
# deflection ~0.8 mm at 3x load, still well inside comfortable.
POST_XS      = (160.0,)
BEAM_YS      = (RIB_INSET, TANK_D - RIB_INSET)   # 12 and 161: under the two ribs

# ── Pump bay ────────────────────────────────────────────────────────────────
PUMP_BAY_HW  = 125.0                  # half-width: two pumps at 125 port-span each
PUMP_CX      = 62.5                   # |X| of each pump's centre (they meet at X=0)
PUMP_Y0      = 2.0                    # pump rear face, from the frame back

SPLIT_CLR    = 0.20                   # per-side clearance at the X=0 split joint

# ── Fitting envelope — Shurflo 244-3926 (90° wingnut swivel) ────────────────
# Conservative clearance solid, NOT a model of the part: a nut barrel coaxial
# with the port, then the barb leg turned 90°. The leg is aimed along ±Y because
# the swivel lets us choose — pointing it along ±X would drive it into the posts.
# Replace with measured dimensions once one is in hand.
ELBOW_NUT_D  = 34.0
ELBOW_NUT_L  = 22.0      # from the port tip, along the port axis
ELBOW_LEG_D  = 26.0
ELBOW_LEG_L  = 45.0      # the turned leg, along ±Y


def _elbow(x_tip, y, z, x_dir, y_dir):
    """Clearance envelope for one fitting. x_dir = outward along the port axis,
    y_dir = which way the barb leg points once swivelled.

    Built on XY and rotated rather than using an XZ workplane: XZ's normal is
    -Y, so `workplane(offset=y)` there lands the solid at -y, which silently put
    every leg on the wrong side of the frame.
    """
    nut = (cq.Workplane("YZ").workplane(offset=x_tip)
           .circle(ELBOW_NUT_D / 2.0).extrude(x_dir * ELBOW_NUT_L)
           .translate((0, y, z)))
    leg = (cq.Workplane("XY").circle(ELBOW_LEG_D / 2.0).extrude(ELBOW_LEG_L)
           .rotate((0, 0, 0), (1, 0, 0), -90 * y_dir)
           .translate((x_tip + x_dir * ELBOW_NUT_L / 2.0, y, z)))
    return nut.union(leg)


def _elbows():
    """All four fittings. Ports sit PUMP_PORT_A from each pump's own rear face,
    so flipping pump B puts its ports 112 mm away from pump A's along Y — which
    is what lets the two inner elbows pass each other at X≈0."""
    zc = FLOOR_T + PUMP_PORT_Z
    ya = PUMP_Y0 + PUMP_PORT_A                      # -X pump: 161
    yb = PUMP_Y0 + PUMP_MOTOR_L - PUMP_PORT_A       # +X pump: 49
    return (_elbow(-PUMP_BAY_HW, ya, zc, -1, +1)    # A outer, leg forward
            .union(_elbow(0.0, ya, zc, +1, +1))     # A inner
            .union(_elbow(+PUMP_BAY_HW, yb, zc, +1, +1))   # B outer
            .union(_elbow(0.0, yb, zc, -1, +1)))    # B inner


def _pump(flip: bool) -> cq.Workplane:
    """One pump, posed feet-down with the motor axis along Y.

    `flip` turns it end-for-end so its port cluster lands at the opposite end of
    the motor axis — that is what keeps two adjacent pumps' inner elbows clear of
    each other.
    """
    p = cq.importers.importStep(str(REFERENCES_DIR / "seaflo_42_pump.step"))
    # STEP frame: motor along X, ports along Y. Rotate 90 deg about Z so the
    # motor runs along Y and the ports point along X.
    p = p.rotate((0, 0, 0), (0, 0, 1), 90)
    if flip:
        p = p.rotate((0, 0, 0), (0, 0, 1), 180)
    return p


def _pump_placed(side: int) -> cq.Workplane:
    """Pump placed in the frame. side=-1 is the -X pump, +1 the +X pump."""
    p = _pump(flip=(side > 0))
    bb = p.val().BoundingBox()
    # Land it: feet at z=0, motor span starting at PUMP_Y0, centred on PUMP_CX.
    return p.translate((side * PUMP_CX - (bb.xmin + bb.xlen / 2.0),
                        PUMP_Y0 - bb.ymin,
                        FLOOR_T - bb.zmin))


def _posts() -> cq.Workplane:
    """Eight posts, shelf to beam underside. Pure compression — the strong case
    for printed plastic, and the reason nothing spans in bending."""
    out = None
    for sx in (-1, 1):
        for ax in POST_XS:
            for by in BEAM_YS:
                post = (cq.Workplane("XY")
                        .center(sx * ax, by)
                        .rect(POST_W, POST_D)
                        .extrude(POST_Z1))
                out = post if out is None else out.union(post)
    return out


def _beams() -> cq.Workplane:
    """Two cross-beams in X, under the tank's two base ribs."""
    out = None
    for by in BEAM_YS:
        beam = (cq.Workplane("XY").workplane(offset=POST_Z1)
                .center(0, by)
                .rect(FRAME_W, BEAM_W)
                .extrude(BEAM_H))
        out = beam if out is None else out.union(beam)
    return out


def _deck() -> cq.Workplane:
    """Thin floor under the pumps. Locates and bolts them; carries NO tank load
    (that goes posts -> shelf), so it stays thin."""
    return (cq.Workplane("XY")
            .center(0, FRAME_D / 2.0)
            .rect(FRAME_W, FRAME_D)
            .extrude(FLOOR_T))


def _frame_whole() -> cq.Workplane:
    return _deck().union(_posts()).union(_beams())


def frame_half(side: int) -> cq.Workplane:
    """One printed half. Split at X=0 so the seam runs BETWEEN the two pumps and
    each half carries its own four posts — the joint takes no vertical load.

    side=-1 -> the -X half, +1 -> the +X half.
    """
    half = (cq.Workplane("XY")
            .center(side * (FRAME_W / 4.0 + SPLIT_CLR / 2.0), FRAME_D / 2.0)
            .rect(FRAME_W / 2.0 - SPLIT_CLR, FRAME_D + 2 * BOOL_OVERSHOOT)
            .extrude(DECK_Z + BOOL_OVERSHOOT))
    return _frame_whole().intersect(half)


frame_left  = frame_half(-1)
frame_right = frame_half(+1)

PRINT_ROT = {}        # both halves model as printed: deck down, posts up


def _tank() -> cq.Workplane:
    """Viz only — the Scepter, sitting on the beams."""
    return (cq.Workplane("XY").workplane(offset=DECK_Z)
            .center(0, TANK_D / 2.0)
            .rect(TANK_W, TANK_D)
            .extrude(TANK_H))


def _shelf() -> cq.Workplane:
    """Viz only — the pack's shelf, which the posts land on."""
    return (cq.Workplane("XY").workplane(offset=-8.0)
            .center(0, SHELF_D / 2.0)
            .rect(SHELF_W, SHELF_D)
            .extrude(8.0))


def _build() -> None:
    asm = (cq.Assembly()
           .add(frame_left,  name="frame_left",  color=color("#3a7bd5"))
           .add(frame_right, name="frame_right", color=color("#2a5d9f"))
           .add(_pump_placed(-1), name="pump_a", color=color("slategray"))
           .add(_pump_placed(+1), name="pump_b", color=color("#5a6b7a"))
           .add(_elbows(), name="fittings", color=color("#c8a24a"))
           .add(_tank(),  name="tank_viz",  color=color("#9fd4e8", alpha=0.35))
           .add(_shelf(), name="shelf_viz", color=color("#808080", alpha=0.5)))

    export_step(print_pose(frame_left,  PRINT_ROT.get("frame_left")),
                str(OUT / "v2_frame_left.step"))
    export_step(print_pose(frame_right, PRINT_ROT.get("frame_right")),
                str(OUT / "v2_frame_right.step"))
    asm.save(str(OUT / "assembly.step"), mode="default")
    show(str(OUT / "assembly.step"))

    for nm, part in (("frame_left", frame_left), ("frame_right", frame_right)):
        bb = part.val().BoundingBox()
        print("%-12s %6.1f x %6.1f x %6.1f mm" % (nm, bb.xlen, bb.ylen, bb.zlen))


if __name__ == "__main__":
    _build()
