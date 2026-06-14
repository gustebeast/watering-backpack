"""SEAFLO 42-series diaphragm pump (SFDP1-030-055-42) — reference solid.

NON-PRINTED placeholder for designing the pump mounting dock. Captures the
major masses (motor cylinder, pump-head block, in/out ports, pressure-switch
bump, mounting bracket, motor wire leads) so the dock can be laid out around
real port/wiring/bolt positions.

Self-contained on purpose: imports nothing from src/ so it can't collide with
concurrent edits to the battery-dock modules. Run from the project root:

    py -3.12 tools/seaflo_42_pump.py

Writes references/seaflo_42_pump.step (+ .stl for preview).

Dimension sources (best wins):
    USER CALIPERS (authoritative): port height 80 off the feet, port axis
        65 ahead of the front bolt row, cylinder edge 105, head 15..115.
    SHURflo 4008 datasheet (the SEAFLO 42 is a clone): L=206 overall,
        W=124.97, bolt pattern 73 x 83 (front row 22 from the rear),
        port->front-bolt [64] (matches the calipers).
    Ports are modeled at Ø27 = the EFFECTIVE OD with the barb fitting
        installed (bare 1/2" NPT male is 20.95).
Masses not pinned by the above (motor length, head width, switch size,
foot pads F/G/H) are proportioned from the user's photos — close enough
for clearance work, flagged as caliper items in the comments.
"""
from __future__ import annotations

import pathlib
import cadquery as cq

# ============================================================
# PARAMETERS  (mm)
# ============================================================
# --- Overall envelope (EXACT, from drawing) ---
LEN_X   = 206.00          # motor-rear -> head front (SHURflo 4008 sheet: [206] 8.07")
WIDTH_Y = 125.00          # across the port tips
HEIGHT_Z = 115.00         # bottom of feet -> top of head/switch (user-measured)

# --- Mounting bracket / bolt pattern (EXACT, from drawing) ---
BOLT_DX      = 73.00      # lengthwise spacing between the two hole rows
BOLT_DY      = 83.00      # transverse spacing across a pair
BOLT_ROW1_X  = 22.00      # rear row, measured from the rear (X=0) edge
BOLT_HOLE_D  = 4.00       # Ø4 mounting holes
# User photos: the bracket is RAISED between the feet (daylight underneath) —
# only 4 rubber pads touch the mounting plane. CALIPER ITEMS F/G/H to confirm:
PAD_D        = 24.0       # rubber foot pad diameter (F)
PAD_H        = 8.0        # pad height = bracket standoff off the plane (G)
BRACKET_T    = 6.0        # bracket slab thickness above the pads
PLATE_MARGIN = 9.0        # bracket overhang past the bolt holes (H: outer
                          # width across feet = 83 + 2*9 = 101)

# --- Motor body (cylinder; heights from USER MEASUREMENTS of the real unit:
#     cylinder far edge ≈105 above the foot plate, so centre = 105 − 38) ---
MOTOR_D    = 76.0         # est. motor can diameter
MOTOR_X0   = 14.0         # rear face of motor can (wires emerge behind this)
MOTOR_LEN  = 116.0        # est.
MOTOR_Z    = 67.0         # axis height above feet (user: edge at ~105)

# --- Pump head (block; user: near face ~15 off the plate, square end
#     extends to ~115 above the feet) ---
HEAD_W     = 90.0         # body width in Y (ports extend beyond to reach 125)
HEAD_Z0    = 15.0         # user: head sits ~15 off the wall/plate
HEAD_Z1    = 115.0        # user: square end reaches ~115
HEAD_FILLET = 10.0        # rounding on the vertical head edges

# --- Cradle bracket joining the foot plate to the raised body (the real
#     unit's bracket arms hold the motor/head ~23 above the plate) ---
CRADLE_W   = 30.0
CRADLE_Z1  = MOTOR_Z      # reaches the motor centreline

# --- Ports (1/2" NPT, EXACT dia) ---
PORT_D     = 27.0         # EFFECTIVE OD with the barb fitting installed
                          # (bare 1/2" NPT male is 20.95; user: model the
                          # final assembled diameter for clearance checks)
PORT_Z     = 80.0         # port centerline above the feet — USER CALIPERED
                          # (the 4008 sheet says 84.6; the SEAFLO differs)
# Port station referenced to the MOUNTING BOLTS (user direction: the feet
# are the known quantity that physically locates the pump — the head face /
# switch are envelope only). CALIPER ITEM B*: front bolt row -> port axis.
PORT_FROM_FRONT_BOLT = 64.0   # 4008 sheet [64], user calipered ~65 - MATCH
                              # (side view ties out: 22+73+64+47 = 206)
PORT_X     = None         # derived below from the bolt row
PORT_LEN_BEYOND = None    # set below so tips land exactly at WIDTH_Y

# --- Pressure switch (on the head END FACE, per user photos: black block
#     centred on the end face with the wire leads exiting it) ---
SW_W  = 40.0              # across the pump width
SW_SPAN_Z = (28.0, 68.0)  # height band above the feet
SW_STICKOUT = 12.0        # protrudes past the head face (within LEN_X)

# --- Motor wire leads (2 stubs out the rear, for routing) ---
LEAD_D   = 4.0
LEAD_LEN = 14.0           # protrude behind the motor rear face
LEAD_DY  = 11.0           # +/- offset of the two leads

# --- Fusion overlap ---
# Adjacent masses must OVERLAP (not just touch) or the boolean union leaves
# them as separate solids in a compound instead of one fused body.
EPS = 8.0                 # mm interpenetration between neighbouring masses

# ============================================================
# DERIVED
# ============================================================
HEAD_X0 = MOTOR_X0 + MOTOR_LEN - EPS   # head reaches back INTO the motor
HEAD_X1 = LEN_X - 12.0                 # head face (switch sticks out to LEN_X)
HEAD_CX = (HEAD_X0 + HEAD_X1) / 2.0    # head center (pressure switch sits here)
PORT_X  = BOLT_ROW1_X + BOLT_DX + PORT_FROM_FRONT_BOLT  # bolts -> port
# port: start EPS inside the head face, run out to exactly +/-WIDTH_Y/2
PORT_INSET = HEAD_W / 2.0 - EPS        # inner end, measured from centre
PORT_LEN   = WIDTH_Y / 2.0 - PORT_INSET
# MOTOR_Z is set in PARAMETERS from user measurements (cylinder raised off
# the plate by the bracket; the CRADLE box below fuses plate <-> body).


def _cyl_x(d, x0, length, y=0.0, z=0.0):
    """Cylinder with its axis along +X, base face at x0."""
    return (cq.Workplane("YZ").workplane(offset=x0)
            .center(y, z).circle(d / 2).extrude(length))


def build():
    # --- mounting feet: 4 rubber pads + RAISED bracket slab (user photos:
    #     daylight under the bracket; only the pads touch the wall) ---
    plate_x0 = BOLT_ROW1_X - PLATE_MARGIN
    plate_x1 = BOLT_ROW1_X + BOLT_DX + PLATE_MARGIN
    plate_len = plate_x1 - plate_x0
    plate_w = BOLT_DY + 2 * PLATE_MARGIN
    plate = (cq.Workplane("XY")
             .box(plate_len, plate_w, BRACKET_T, centered=(False, True, False))
             .translate((plate_x0, 0, PAD_H)))

    bolt_xs = [BOLT_ROW1_X, BOLT_ROW1_X + BOLT_DX]
    bolt_ys = [-BOLT_DY / 2, BOLT_DY / 2]
    for bx in bolt_xs:
        for by in bolt_ys:
            pad = (cq.Workplane("XY")
                   .center(bx, by).circle(PAD_D / 2)
                   .extrude(PAD_H + 1.0))           # fuses into the bracket
            plate = plate.union(pad)
            hole = (cq.Workplane("XY").workplane(offset=-1.0)
                    .center(bx, by).circle(BOLT_HOLE_D / 2)
                    .extrude(PAD_H + BRACKET_T + 2.0))
            plate = plate.cut(hole)

    # --- motor can ---
    motor = _cyl_x(MOTOR_D, MOTOR_X0, MOTOR_LEN, y=0.0, z=MOTOR_Z)

    # --- cradle bracket: fuses the feet to the raised body ---
    cradle = (cq.Workplane("XY").workplane(offset=PAD_H + BRACKET_T - 1.0)
              .box(80.0, CRADLE_W, CRADLE_Z1 - PAD_H - BRACKET_T + 1.0,
                   centered=(False, True, False))
              .translate((20.0, 0, 0)))

    # --- pump head block (rounded vertical edges) ---
    head = (cq.Workplane("XY").workplane(offset=HEAD_Z0)
            .box(HEAD_X1 - HEAD_X0, HEAD_W, HEAD_Z1 - HEAD_Z0,
                 centered=(False, True, False))
            .translate((HEAD_X0, 0, 0))
            .edges("|Z").fillet(HEAD_FILLET))

    # --- two ports out the head sides (+/-Y), tips land at +/-WIDTH_Y/2 ---
    # start EPS inside the head wall so the stubs fuse to the head
    port_y = (cq.Workplane("XZ").workplane(offset=-PORT_INSET)
              .center(PORT_X, PORT_Z).circle(PORT_D / 2)
              .extrude(-PORT_LEN))                  # +Y side
    port_y2 = (cq.Workplane("XZ").workplane(offset=PORT_INSET)
               .center(PORT_X, PORT_Z).circle(PORT_D / 2)
               .extrude(PORT_LEN))                  # -Y side

    # --- pressure switch on the head END face (user photos) ---
    # The head face sits at LEN_X - SW_STICKOUT; the switch block occupies
    # the remaining stick-out so the 206 envelope includes it.
    switch = (cq.Workplane("XY").workplane(offset=SW_SPAN_Z[0])
              .box(SW_STICKOUT + EPS, SW_W,
                   SW_SPAN_Z[1] - SW_SPAN_Z[0],
                   centered=(False, True, False))
              .translate((LEN_X - SW_STICKOUT - EPS, 0, 0)))

    # --- wire leads exit at the MOTOR REAR (user: the red + lead originates
    #     at the end-face switch but is factory-routed back along the body to
    #     exit beside the black ground at the rear, equal lengths) ---
    leads = None
    for ly in (-LEAD_DY, LEAD_DY):
        lead = _cyl_x(LEAD_D, MOTOR_X0 - LEAD_LEN, LEAD_LEN + EPS,
                      y=ly, z=MOTOR_Z)
        leads = lead if leads is None else leads.union(lead)

    result = (plate
              .union(cradle)
              .union(motor)
              .union(head)
              .union(port_y).union(port_y2)
              .union(switch)
              .union(leads))
    return result


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    out_dir = root / "references"
    out_dir.mkdir(exist_ok=True)
    result = build()

    n_solids = len(result.val().Solids())
    step_path = out_dir / "seaflo_42_pump.step"
    stl_path = out_dir / "seaflo_42_pump.stl"
    cq.exporters.export(result, str(step_path))
    cq.exporters.export(result, str(stl_path),
                        tolerance=0.01, angularTolerance=0.1)

    bb = result.val().BoundingBox()
    print(f"solids fused into: {n_solids}  (want 1)")
    print(f"bbox  X {bb.xlen:7.2f}  Y {bb.ylen:7.2f}  Z {bb.zlen:7.2f} mm "
          f"| Z range {bb.zmin:.2f}..{bb.zmax:.2f}")
    print(f"target X {LEN_X:7.2f}  Y {WIDTH_Y:7.2f}  Z {HEIGHT_Z:7.2f} mm")
    print(f"wrote {step_path.name} + {stl_path.name}")


if __name__ == "__main__":
    main()
