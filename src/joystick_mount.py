"""Joystick hose-clamp mount — clips the joystick PCB onto the watering hose.

A flat PCB plate sits on four 3 mm standoffs (to clear the solder on the PCB
underside), carried on a C-clamp that grips the hose (OD 12.3 mm). The PCB long
axis runs ALONG the hose.

PRINT ORIENTATION (no supports): exactly as modelled — Z up, clamp mouth on the
bed. The design is built to print support-free:
  • The hose grip is a ~270° arc (open at the bottom mouth) — its bore is capped
    at the top by the flat plate, so there is NO round bore-ceiling; the plate
    just bridges the ~12 mm opening.
  • The plate edges are carried on 45° gussets whose inner foot lands ON the
    grip's outer face (GUSSET_X is a chord of that circle, not a guess), so the
    plate underside is supported continuously from the bore tangent out to the
    edge — no unsupported strip between gusset and grip.
  • Two screw ears flank the mouth with FLAT bottoms → a stable print base, and
    carry the M2 clamp screw that pulls the mouth shut (PCTG flexes the needed
    couple of mm; the mouth is modelled under-size so it also snaps/grips).
  • Standoffs print as upright posts.

Run:  py -3.12 -m src.joystick_mount     -> writes joystick_mount.step
"""
from __future__ import annotations

import math
import pathlib
import sys

import cadquery as cq

# Shared STEP exporter (vendored cadkit) — names the product after its file.
from cadkit.step_export import export_step
from cadkit.supports import printable_bore

# ── Hose clamp ───────────────────────────────────────────────────────────────
HOSE_OD    = 12.3
HOSE_R     = HOSE_OD / 2.0          # 6.15 — bore matches the hose (snug)
CLAMP_WALL = 2.6                    # grip wall thickness
R_OUT      = HOSE_R + CLAMP_WALL    # 8.75
CLAMP_LIFT = 2.0                    # lift the bore off the bed so the clamp screw
                                    # fits fully BELOW the tube (was clipping it +
                                    # only 0.3 mm under it → bottom layer split)
Z_C        = R_OUT + CLAMP_LIFT     # 10.75 — hose centre height
MOUTH_W    = 10.0                   # bottom opening < OD: grips, but only ~2 mm
                                    # of flex to clip on (PCTG); screw tightens it
# CLAMP_LEN (clamp + gusset span along the hose) is tied to PLATE_Y below, so
# the bottom clamp spans the full plate length (flush at both +y and -y ends).

# ── M2 clamp screw (across the mouth, below the bore) ────────────────────────
EAR_OUT      = R_OUT + 1.0         # 9.75 — ear outer face (screw-head bearing)
M2_CLR       = 2.4                 # M2 clearance bore
SCREW_BOTTOM = 1.0                 # material BELOW the screw hole (was 0.3 → split)
SCREW_Z      = SCREW_BOTTOM + M2_CLR / 2.0   # 2.2 — hole centre: 1 mm to the bed,
                                   # top (3.4) clears the raised bore bottom (4.6)
EAR_TOP      = 7.17                # taller ears (was 4.6) → much more material around
                                   # the lateral screw = stronger. 7.17 ≈ the limit
                                   # where the ear inner edge (mouth wall, x=MOUTH_W/2)
                                   # meets the bore, so it doesn't cut into the tube.

# ── PCB + mounting ───────────────────────────────────────────────────────────
PCB_X, PCB_Y = 26.5, 34.3          # PCB_Y (long) runs along the hose
HOLE_INNER_X, HOLE_INNER_Y = 16.7, 23.2     # gap between hole inner walls
HOLE_D    = 3.0
HOLE_CC_X = HOLE_INNER_X + HOLE_D  # 19.7 — centre-to-centre, across the hose
HOLE_CC_Y = HOLE_INNER_Y + HOLE_D  # 26.2 — centre-to-centre, along the hose
STANDOFF_H = 2.0                   # bottom clearance for PCB solder
STANDOFF_D = 5.5
M2_TAP     = 1.7                   # self-tap pilot for an M2 PCB screw
PILOT_DEEP = 5.0                   # pilot reaches this far BELOW the standoff base
                                   # (into the plate + gusset) so an 8 mm M2 (no
                                   # 6 mm on hand) self-taps fully: 8 - 1.5 PCB
                                   # - 2 standoff = 4.5 mm needed below the base
PLATE_T    = 2.5
PLATE_X    = HOLE_CC_X + STANDOFF_D          # 25.2 — standoffs sit FLUSH with the edge
PLATE_Y    = HOLE_CC_Y + STANDOFF_D          # 31.7 — standoffs flush
CLAMP_LEN  = PLATE_Y                          # clamp + gussets span the full plate length

OV = 0.5

PLATE_Z0 = Z_C + HOSE_R            # plate underside tangent to the hose top (low profile)

# Gusset inner foot. This MUST be the x where the grip's outer face actually
# reaches the plate line, which is a chord on the outer circle -- not
# PLATE_X/2 - (PLATE_Z0 - Z_C), which is what it used to be. That older
# expression put the foot at 6.45 while the grip ends at 6.225, so the gusset
# began 0.225 mm OUTBOARD of the grip and the plate underside spanned the gap
# with nothing beneath it: two flat ceilings of 0.225 x 31.7 = 7.1 mm2 at
# n.z = -1.00, one per side. Harmless to a slicer at that width, but the
# docstring claimed 45 degree gussets carrying the plate edges and they did not
# touch the grip. tools/check_v2_overhangs.py now checks this part, which is
# how it surfaced.
GUSSET_X = math.sqrt(R_OUT ** 2 - HOSE_R ** 2)      # 6.225
# ...and the apex drops from there at exactly 45 degrees, so the underside is a
# 45 degree ramp rather than something steeper.
GUSSET_Z0 = PLATE_Z0 - (PLATE_X / 2.0 - GUSSET_X)   # 10.52
assert GUSSET_Z0 > Z_C - math.sqrt(R_OUT ** 2 - GUSSET_X ** 2), (
    "gusset apex hangs below the grip it is supposed to spring from")


def _annulus():
    """Hose grip: an annulus extruded along Y (the hose axis), capped later."""
    return (cq.Workplane("XZ").center(0, Z_C)
            .circle(R_OUT).circle(HOSE_R)
            .extrude(CLAMP_LEN).translate((0, CLAMP_LEN / 2.0, 0)))


def _top_cut():
    """Remove the grip material above the plate line so the plate (not a round
    ceiling) caps the bore — printable as a flat bridge."""
    return (cq.Workplane("XY")
            .box(4 * R_OUT, CLAMP_LEN + 2 * OV, 2 * R_OUT, centered=(True, True, False))
            .translate((0, 0, PLATE_Z0)))


def _mouth():
    """Bottom slot that opens the grip into a C (snap-on mouth)."""
    return (cq.Workplane("XY")
            .box(MOUTH_W, CLAMP_LEN + 2 * OV, Z_C + OV, centered=(True, True, False))
            .translate((0, 0, -OV)))


def _ears():
    """Two blocks flanking the mouth: flat-bottomed (stable base) + screw bosses."""
    ear = (cq.Workplane("XY")
           .box(EAR_OUT - MOUTH_W / 2.0, CLAMP_LEN, EAR_TOP, centered=(False, False, False))
           .translate((MOUTH_W / 2.0, -CLAMP_LEN / 2.0, 0)))
    return ear.union(ear.mirror("YZ"))


def _gussets():
    """45° gussets carrying the plate edges (printable underside, no cantilever)."""
    pts = [(GUSSET_X, GUSSET_Z0), (GUSSET_X, PLATE_Z0), (PLATE_X / 2.0, PLATE_Z0)]
    half = (cq.Workplane("XZ").polyline(pts).close()
            .extrude(CLAMP_LEN).translate((0, CLAMP_LEN / 2.0, 0)))
    return half.union(half.mirror("YZ"))


def _plate():
    return (cq.Workplane("XY")
            .box(PLATE_X, PLATE_Y, PLATE_T, centered=(True, True, False))
            .translate((0, 0, PLATE_Z0)))


def _standoffs():
    """Four posts on the plate top (3 mm solder clearance) with M2 pilots."""
    z0 = PLATE_Z0 + PLATE_T
    posts = pilot = None
    for sx in (-HOLE_CC_X / 2.0, HOLE_CC_X / 2.0):
        for sy in (-HOLE_CC_Y / 2.0, HOLE_CC_Y / 2.0):
            p = (cq.Workplane("XY").workplane(offset=z0)
                 .circle(STANDOFF_D / 2.0).extrude(STANDOFF_H).translate((sx, sy, 0)))
            h = (cq.Workplane("XY").workplane(offset=z0 - PILOT_DEEP)
                 .circle(M2_TAP / 2.0).extrude(STANDOFF_H + PILOT_DEEP).translate((sx, sy, 0)))
            posts = p if posts is None else posts.union(p)
            pilot = h if pilot is None else pilot.union(h)
    return posts, pilot


def _screw_hole():
    """M2 clamp screw across the mouth (below the bore): clearance through the
    +x ear + mouth, self-tap pilot in the -x ear, so the screw pulls the mouth
    shut without a nut."""
    # TEARDROPPED. Both run SIDEWAYS in the print, so a plain cylinder leaves a
    # circular ceiling that droops into the bore: the gate measured 8.8 mm2 on
    # the clearance bore and 6.2 mm2 on the pilot, both at n.z = -1.00.
    # printable_bore adds the 45 deg peak (and returns a plain cylinder if the
    # axis ever becomes the build direction, so the call site stays correct).
    # Apex room is fine here: the clearance peak reaches 1.2*sqrt(2) = 1.70
    # above z=2.2, i.e. 3.9, against EAR_TOP 7.17.
    clr = printable_bore(M2_CLR, EAR_OUT + MOUTH_W / 2.0 + OV,
                         axis_point=(-MOUTH_W / 2.0, 0.0, SCREW_Z),
                         axis_dir=(1.0, 0.0, 0.0), print_up=(0.0, 0.0, 1.0),
                         nozzle=0.4)
    tap = printable_bore(M2_TAP, EAR_OUT - MOUTH_W / 2.0 + OV,
                         axis_point=(-EAR_OUT - OV, 0.0, SCREW_Z),
                         axis_dir=(1.0, 0.0, 0.0), print_up=(0.0, 0.0, 1.0),
                         nozzle=0.4)
    return clr.union(tap)


def _build():
    body = _annulus().cut(_top_cut()).union(_ears()).union(_gussets()).union(_plate())
    body = body.cut(_mouth())
    posts, pilot = _standoffs()
    body = body.union(posts).cut(pilot).cut(_screw_hole())
    return body


joystick_mount = _build()


def main():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "joystick_mount.step")
    export_step(joystick_mount.val(), out)
    b = joystick_mount.val().BoundingBox()
    print("Wrote joystick_mount.step")
    print(f"  envelope   : X {b.xlen:.1f}  Y {b.ylen:.1f}  Z {b.zlen:.1f} mm "
          f"(base z={b.zmin:.1f})")
    print(f"  solids     : {len(joystick_mount.val().Solids())}")
    print(f"  hose bore  : OD {HOSE_OD}  mouth {MOUTH_W} (<OD, grips)")
    print(f"  PCB top    : z={PLATE_Z0 + PLATE_T + STANDOFF_H:.1f}  "
          f"(hose surface z={Z_C + HOSE_R:.1f} -> PCB {PLATE_T + STANDOFF_H:.1f} mm above hose)")
    print(f"  hole c-c   : {HOLE_CC_X:.1f} x {HOLE_CC_Y:.1f} mm, M2 self-tap pilots")


if __name__ == "__main__":
    main()
