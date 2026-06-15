"""Joinery test coupons — minimal-material samples of each joint at its FULL
slide length, for dialing in friction/clearance before committing to the big
prints.

Four parts (two joints × male/female):
  test_dovetail_tenon  / test_dovetail_mortise  — battery dock ↔ housing
                                                   (arrowhead dovetail, 90 mm)
  test_house_tongue    / test_house_channel     — electronics box ↔ pump
                                                   housing (gabled house, 102 mm)

Each coupon is the real joint profile (shared with the production code, so they
stay in sync) at full length, on just enough backing/wall for handling. Males
have the feature pointing +z; females open −z (downward). All four print FLAT,
feature-up / opening-down, which is self-supporting and matches the real print
orientation for three of them.

ORIENTATION NOTE — the only mismatch: the real housing dovetail RAIL is a
*vertical* extrusion (smooth flanks). This flat coupon puts 45° layer lines on
the rail flanks, so its felt friction may read slightly HIGH vs the real part.
For the most representative dovetail friction, stand the tenon coupon on its
end in the slicer before printing.

Run:  py -3.12 -m src.test_pieces      → writes 4 STEPs + a combined layout.
"""
from __future__ import annotations

import cadquery as cq

from .dimensions import (BOOL_OVERSHOOT, DOVETAIL_ROOT_W, DOVETAIL_TIP_W,
                         DOVETAIL_CLR)
from .helpers import dovetail_arrowhead
from . import backpack_housing as bh

OV   = BOOL_OVERSHOOT
BACK = 5.0      # backing thickness behind a male feature
WALL = 3.5      # minimum wall around a female recess

DOVE_LEN  = bh.RAIL_Z_TOP + bh.FLOOR_T        # 90.0  (full dovetail slide)
HOUSE_LEN = bh.ELEC_XOUT - bh.SHELF_X0        # 102.05 (full shelf run)


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


def _house_tongue_profile():
    """(y, z) gabled house tongue, centred & base at z=0 (same formula as
    backpack_housing._shelf_and_lips)."""
    t0, t1 = bh.HOUSE_T
    tm = (t0 + t1) / 2
    base = bh.SHELF_Z - 0.1
    pts = [(t0, base), (t1, base), (t1, bh.HOUSE_WALL_Z),
           (tm, bh.HOUSE_PEAK_Z), (t0, bh.HOUSE_WALL_Z)]
    return [(y - tm, z - base) for y, z in pts]


def _house_channel_profile():
    """(y, z) matching channel = tongue offset HOUSE_CLR normally, centred &
    base at z=0 (same formula as backpack_housing._build_elec_housing)."""
    ht0, ht1 = bh.HOUSE_T
    htm = (ht0 + ht1) / 2
    g  = bh.HOUSE_CLR
    gv = bh.HOUSE_CLR * 1.414
    peak_c = bh.HOUSE_PEAK_Z + gv
    eave_c = peak_c - (htm - (ht0 - g))
    base = bh.TRAY_SEAT_Z
    pts = [(ht0 - g, base), (ht1 + g, base), (ht1 + g, eave_c),
           (htm, peak_c), (ht0 - g, eave_c)]
    return [(y - htm, z - base) for y, z in pts]


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


def test_house_tongue():
    half_w = (bh.HOUSE_T[1] - bh.HOUSE_T[0]) / 2 + 3.5
    return _male(_house_tongue_profile(), HOUSE_LEN, half_w)


def test_house_channel():
    g = bh.HOUSE_CLR
    half_w = (bh.HOUSE_T[1] - bh.HOUSE_T[0]) / 2 + g + WALL
    return _female(_house_channel_profile(), HOUSE_LEN, half_w)


PARTS = {
    "test_dovetail_tenon":   test_dovetail_tenon,
    "test_dovetail_mortise": test_dovetail_mortise,
    "test_house_tongue":     test_house_tongue,
    "test_house_channel":    test_house_channel,
}


def main():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    combined = None
    y = 0.0
    for name, fn in PARTS.items():
        part = fn()
        cq.exporters.export(part.val(), os.path.join(root, f"{name}.step"))
        b = part.val().BoundingBox()
        print(f"  {name:24s} {b.xlen:5.1f} × {b.ylen:5.1f} × {b.zlen:5.1f} mm")
        spaced = part.translate((0.0, y, BACK + 1.0))   # lift females clear too
        combined = spaced if combined is None else combined.union(spaced)
        y += 35.0
    cq.exporters.export(combined.val(), os.path.join(root, "test_pieces.step"))
    print("Wrote test_pieces.step (combined) + 4 individual STEPs")


if __name__ == "__main__":
    main()
