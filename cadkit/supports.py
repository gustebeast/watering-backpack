"""cadkit.supports — printability helpers for features protruding SIDEWAYS
out of a wall (feature axis perpendicular to the print direction).

`teardrop_boss_support(radius, length, axis_point, axis_dir)` returns the
support solid to UNION with a short horizontal cylinder/boss so its
underside prints support-free in a −Z→+Z print. Two elements, and BOTH are
required:

  * TEARDROP TAIL — two 45° flats tangent to the cylinder, meeting at a
    point radius·√2 below the axis. Every layer of the cylinder's underside
    then rests on the layer below (≤45° stepover in plan).
  * WALL RAMP — the tail's bottom recedes toward the wall at 45°: without
    it the tail's lowest layers are thin lines cantilevered off the wall
    ALONG THE AXIS with nothing under them (the classic failure when this
    shape is rebuilt by hand — the flats fix the cross-section but not the
    axis direction). Depth grows with height at 45° from the tip, so every
    layer roots on the wall or on the layer below.

Intended for SHORT protrusions (a few mm — thrust bosses, pin seats,
stand-off pads): the cylinder's own underside spans its length as a
supported perimeter and the tail handles the taper to a point. A long
side-sticking shaft needs a different strategy (separate part, or printed
on its side).

Self-test: `python -m cadkit.supports` (or run this file) — gates geometry
(tip depth, ramp recede, transform correctness) and argument validation.
"""

import math

import cadquery as cq

__all__ = ["teardrop_boss_support"]


def teardrop_boss_support(radius, length, axis_point=(0.0, 0.0, 0.0),
                          axis_dir=(0.0, 1.0, 0.0)):
    """Support solid (UNION it with the part) for a horizontal cylinder of
    `radius` protruding `length` out of a wall.

    axis_point — the cylinder's axis at the WALL face (world coords).
    axis_dir   — axis direction from the wall toward the FREE end; must be
                 horizontal (perpendicular to print +Z), any plan azimuth.

    The returned solid spans the full `length`; its free-end bottom is the
    45° wall ramp. Print direction is −Z→+Z (cadkit convention)."""
    dxa, dya, dza = (float(c) for c in axis_dir)
    n = math.sqrt(dxa * dxa + dya * dya + dza * dza)
    if n < 1e-9:
        raise ValueError("axis_dir must be non-zero")
    if abs(dza) > 1e-6 * n:
        raise ValueError(
            "axis_dir must be horizontal (perpendicular to the print Z)")
    r, L = float(radius), float(length)
    if r <= 0.0 or L <= 0.0:
        raise ValueError("radius and length must be positive")

    a = r * math.sqrt(2.0) / 2.0          # 45° tangency half-width
    tip = -r * math.sqrt(2.0)             # tail point (below the axis)

    # local frame: wall face at y=0, axis along +Y, axis through the origin
    tail = (cq.Workplane("XZ")
            .polyline([(-a, -a), (a, -a), (0.0, tip)])
            .close().extrude(-L))                     # XZ extrude(−L) → +Y
    # wall ramp: cut everything below the 45° line z = y + tip, so the tail
    # only reaches depth y where height (z − tip) has caught up
    ramp = (cq.Workplane("YZ").workplane(offset=-a - 1.0)
            .polyline([(0.0, tip - 1.0), (L + 1.0, tip - 1.0),
                       (L + 1.0, tip + L + 1.0), (0.0, tip)])
            .close().extrude(2.0 * a + 2.0))
    tail = tail.cut(ramp)

    az = math.degrees(math.atan2(dya, dxa)) - 90.0    # rotate +Y → axis_dir
    px, py, pz = (float(c) for c in axis_point)
    return (tail.rotate((0, 0, 0), (0, 0, 1), az)
            .translate((px, py, pz)))


if __name__ == "__main__":
    import sys

    fails = []
    R, L = 3.45, 1.0                      # the retractable-spool thrust boss
    s = teardrop_boss_support(R, L)
    a = R * math.sqrt(2.0) / 2.0
    tip = -R * math.sqrt(2.0)

    v = s.val().Volume()
    print(f"  volume               {v:.3f} mm^3 {'ok' if v > 0.1 else 'FAIL'}")
    if v <= 0.1:
        fails.append("volume")

    bb = s.val().BoundingBox()
    geo_ok = (abs(bb.zmin - tip) < 0.01 and abs(bb.zmax - (-a)) < 0.01
              and abs(bb.ymin - 0.0) < 0.01 and abs(bb.ymax - L) < 0.01
              and abs(bb.xmin + a) < 0.01 and abs(bb.xmax - a) < 0.01)
    print(f"  bbox (tip r*sqrt2, chord, wall..L) {'ok' if geo_ok else 'FAIL'}")
    if not geo_ok:
        fails.append("bbox")

    # ramp recede: within 0.4 above the tip, depth off the wall stays <= 0.45
    sl = s.intersect(cq.Workplane("XY").workplane(offset=tip)
                     .rect(20, 20).extrude(0.4))
    ymax = sl.val().BoundingBox().ymax if sl.val().Volume() > 1e-9 else 0.0
    print(f"  tip recede y<= {ymax:.2f}      {'ok' if ymax <= 0.45 else 'FAIL'}")
    if ymax > 0.45:
        fails.append("ramp recede")

    # transform: axis +X from (10, 5, 2) → tail below that point, spans x 10..11
    t = teardrop_boss_support(R, L, (10.0, 5.0, 2.0), (1.0, 0.0, 0.0))
    tb = t.val().BoundingBox()
    tr_ok = (abs(tb.xmin - 10.0) < 0.01 and abs(tb.xmax - 11.0) < 0.01
             and abs(tb.zmin - (2.0 + tip)) < 0.01
             and abs((tb.ymin + tb.ymax) / 2.0 - 5.0) < 0.01)
    print(f"  transform (+X axis)   {'ok' if tr_ok else 'FAIL'}")
    if not tr_ok:
        fails.append("transform")

    for bad, kw in ((((0, 0, 1),), "vertical axis"),
                    (((0, 0, 0),), "zero axis")):
        try:
            teardrop_boss_support(R, L, (0, 0, 0), bad[0])
            print(f"  {kw:<20}  did NOT raise  <-- FAIL")
            fails.append(kw)
        except ValueError:
            print(f"  {kw:<20}  raises (ok)")
    try:
        teardrop_boss_support(R, 0.0)
        print("  zero length           did NOT raise  <-- FAIL")
        fails.append("zero length")
    except ValueError:
        print("  zero length           raises (ok)")

    if fails:
        print("FAIL:", *fails, sep="\n  ")
    else:
        print("OK -- teardrop tail tangent at 45, tip at r*sqrt2, wall ramp "
              "recedes at 45, transforms and validation behave.")
    sys.exit(len(fails))
