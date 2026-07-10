"""Joinery test coupons — minimal-material samples of each joint at its FULL
slide length, for dialing in friction/clearance before committing to the big
prints.

Four parts:
  test_dovetail_tenon  / test_dovetail_mortise  — battery dock ↔ housing
                                                   (arrowhead dovetail, 90 mm)
  test_house_pump      / test_house_elec        — pump housing ↔ electronics
                                                   box (full-profile joint
                                                   slices, 102 mm)

The dovetail coupons are built from the shared production profile
(dovetail_arrowhead). The house coupons are full-cross-section SLICES of the
real pump housing and electronics box at the joint region — so they carry the
complete profile (pump: shelf + gabled tongue + retaining teeth; elec: floor
flange + house channel + a bit of box wall), not just the tongue/channel.

ORIENTATION — the house slices print z-up (the real orientation: tongue/teeth
and the channel are self-supporting; pump slice gets a flat foot for stability).
The dovetail coupons print flat, feature-up / opening-down. The one caveat: the
real housing dovetail RAIL is a *vertical* extrusion (smooth flanks); this flat
coupon lays 45° layer lines on the rail flanks, so its friction may read
slightly HIGH. For the truest dovetail feel, stand the tenon coupon on its end
before slicing.

Run:  py -3.12 -m src.test_pieces      → writes the 4 coupon STEPs.
"""
from __future__ import annotations

import pathlib
import sys

import cadquery as cq

# Shared STEP exporter (vendored cadkit) — names each product after its file.
from cadkit.step_export import export_step

from .dimensions import (BOOL_OVERSHOOT, DOVETAIL_ROOT_W, DOVETAIL_TIP_W,
                         DOVETAIL_CLR)
from .helpers import dovetail_arrowhead
from . import backpack_housing as bh

OV   = BOOL_OVERSHOOT
BACK = 5.0      # backing thickness behind a male feature
WALL = 3.5      # minimum wall around a female recess

DOVE_LEN  = bh.RAIL_Z_TOP + bh.FLOOR_T        # 90.0  (full dovetail slide)
HOUSE_X0  = bh.JOINT_X0                        # joint −x extent (teeth/tongue/shelf cutoff)
HOUSE_LEN = bh.ELEC_XOUT - HOUSE_X0           # the ENGAGED joint run


def _extrude_x(profile, length, x0=0.0):
    """Extrude a (y, z) profile along +x (YZ workplane normal)."""
    return (cq.Workplane("YZ").polyline(profile).close()
            .extrude(length).translate((x0, 0.0, 0.0)))


# ── Joint profiles (centred at y=0, feature base at z=0) ─────────────────────
def _dovetail_profile(clr):
    """(y, z) arrowhead — opening on the bed (z≈0), pointy top up."""
    return [(across, depth)
            for across, depth in dovetail_arrowhead(DOVETAIL_ROOT_W / 2,
                                                     DOVETAIL_TIP_W / 2,
                                                     clr=clr, open_ov=OV)]


# ── Coupons ──────────────────────────────────────────────────────────────────
def _male(profile, length, half_w):
    """Feature (profile, pointing +z, base at z≈0) on a backing slab."""
    back = _extrude_x([(-half_w, -BACK), (half_w, -BACK),
                       (half_w, 0.0), (-half_w, 0.0)], length)
    return back.union(_extrude_x(profile, length))


def _female(profile, length, half_w):
    """Recess (profile, opening on the bed at z≈0) carved up into a block."""
    top = max(z for _, z in profile) + WALL
    block = _extrude_x([(-half_w, 0.0), (half_w, 0.0),
                        (half_w, top), (-half_w, top)], length)
    return block.cut(_extrude_x(profile, length + 2 * OV, -OV))


def test_dovetail_tenon():
    return _male(_dovetail_profile(0.0), DOVE_LEN, DOVETAIL_TIP_W / 2 + 3.0)


def test_dovetail_mortise():
    return _female(_dovetail_profile(DOVETAIL_CLR), DOVE_LEN,
                   DOVETAIL_TIP_W / 2 + DOVETAIL_CLR + WALL)


# House-joint coupons are FULL-PROFILE slices of the real parts at the joint
# region (the simplified tongue/channel missed the teeth and the wall). Both
# parts live in the same assembly frame, so the same y-z-x window cuts the two
# interlocking halves. Window: back-wall (y=0) joint, full shelf run in x.
HOUSE_Y0, HOUSE_Y1 = -bh.WALL, 13.0     # wall outer face .. past the box wall
HOUSE_Z0, HOUSE_Z1 = 113.0, 132.0       # below the shelf corbel .. above teeth
FOOT_T = 4.0                            # flat stability foot under the pump slice


def _join_region():
    return (cq.Workplane("XY")
            .box(HOUSE_LEN, HOUSE_Y1 - HOUSE_Y0, HOUSE_Z1 - HOUSE_Z0,
                 centered=(False, False, False))
            .translate((HOUSE_X0, HOUSE_Y0, HOUSE_Z0)))


def test_house_pump():
    """PUMP side, one piece: back-wall + shelf + gabled tongue (bottom tenon)
    + retaining teeth (top retention), full joint length, on a flat foot for
    print stability. Prints z-up (the real orientation; features self-support)."""
    sl = bh.backpack_housing.intersect(_join_region())
    foot = (cq.Workplane("XY")
            .box(HOUSE_LEN, HOUSE_Y1 - HOUSE_Y0, FOOT_T, centered=(False, False, False))
            .translate((HOUSE_X0, HOUSE_Y0, HOUSE_Z0 - FOOT_T)))
    return sl.union(foot)


def test_house_elec():
    """ELEC side, one piece: floor flange + house CHANNEL (mortise) + a bit of
    the box wall, full joint length. The box floor is the print base; the
    channel opens downward (self-supporting), as in the real box."""
    return bh.elec_housing_part.intersect(_join_region())


PARTS = {
    "test_dovetail_tenon":   test_dovetail_tenon,
    "test_dovetail_mortise": test_dovetail_mortise,
    "test_house_pump":       test_house_pump,
    "test_house_elec":       test_house_elec,
}


def main():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name, fn in PARTS.items():
        part = fn()
        b = part.val().BoundingBox()
        # recenter each coupon's bbox-min to the origin (tidy, on the bed)
        coupon = part.translate((-b.xmin, -b.ymin, -b.zmin))
        export_step(coupon.val(), os.path.join(root, f"{name}.step"))
        print(f"  {name:22s} {b.xlen:6.1f} × {b.ylen:5.1f} × {b.zlen:5.1f} mm")
    print("Wrote 4 individual test-piece STEPs")


if __name__ == "__main__":
    main()
