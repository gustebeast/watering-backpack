"""cadkit.supports — printability helpers for features protruding SIDEWAYS
out of a wall (feature axis perpendicular to the print direction).

Three helpers, all stated in WORLD coordinates and all taking the part's
`print_up` so they can reason about what actually overhangs:

  * `teardrop_boss_support` — support to UNION with a sideways cylinder/boss.
  * `contact_rib`           — a thin proud RING (thrust/contact face), with
                              that support already fused on when it is needed.
  * `printable_bore`        — a hole CUTTER that is a teardrop when the bore
                              runs sideways and a plain cylinder when it runs
                              along the build direction (where a round hole
                              has no ceiling and a teardrop would be wrong).

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

__all__ = ["teardrop_boss_support", "contact_rib", "printable_bore"]


def teardrop_boss_support(radius, length=None, axis_point=(0.0, 0.0, 0.0),
                          axis_dir=(0.0, 1.0, 0.0), print_up=(0.0, 0.0, 1.0)):
    """Support solid (UNION it with the part) for a cylinder of `radius`
    protruding out of a wall, SIDEWAYS relative to the print direction.
    Everything is stated in WORLD coordinates — the function orients the
    geometry itself; never rotate or mirror its output afterwards (the wall
    ramp is direction-sensitive and post-transforms silently turn it into
    an unprintable shape).

    axis_point — the cylinder's axis at the WALL face.
    axis_dir   — axis direction from the wall toward the FREE end.
    print_up   — the print's build direction ("up"); the teardrop tail
                 hangs opposite it. Must be perpendicular to axis_dir.
    length     — protrusion length; ONLY needed when the boss is SHORTER
                 than radius/√2 (the wall ramp naturally caps the tail at
                 that length, so longer bosses can omit it).

    THE WALL MUST BE REAL: axis_point must lie on a SOLID face of the same
    printed part, spanning the tail's print layers — the tail roots into
    that wall layer by layer (that is what the ramp is shaped around). A
    free plane (open air on the far side, a seat another part rests on) is
    NOT a wall. Orient by the FEATURE'S ROOT, not its surroundings: for a
    ring/rib standing proud of a face, the wall IS that face (plus whatever
    backs it at the tail's layers), axis_dir points along the proudness,
    and length is the proud height — do not point the axis from the free
    end back at the part."""
    ax, ay, az_ = (float(c) for c in axis_dir)
    ux, uy, uz = (float(c) for c in print_up)
    na = math.sqrt(ax * ax + ay * ay + az_ * az_)
    nu = math.sqrt(ux * ux + uy * uy + uz * uz)
    if na < 1e-9 or nu < 1e-9:
        raise ValueError("axis_dir and print_up must be non-zero")
    ax, ay, az_ = ax / na, ay / na, az_ / na
    ux, uy, uz = ux / nu, uy / nu, uz / nu
    if abs(ax * ux + ay * uy + az_ * uz) > 1e-6:
        raise ValueError("axis_dir must be perpendicular to print_up")
    r = float(radius)
    if r <= 0.0:
        raise ValueError("radius must be positive")
    L = float(length) if length is not None else r * math.sqrt(2.0) / 2.0
    if L <= 0.0:
        raise ValueError("length must be positive")

    a = r * math.sqrt(2.0) / 2.0          # 45° tangency half-width
    tip = -r * math.sqrt(2.0)             # tail point (below the axis)

    # canonical frame: wall face at y=0, axis +Y, print-up +Z
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
    # the support only adds material OUTSIDE the supported cylinder: cut the
    # cylinder's own volume from the tail (a solid boss re-absorbs it on
    # union anyway; a RING/annulus feature must not have its opening filled)
    tail = tail.cut(cq.Workplane("XZ").circle(r)
                    .extrude(-(L + 2.0)).translate((0.0, -1.0, 0.0)))

    # rigid map canonical → world via a located plane: normal = print_up
    # (canonical +Z), xDir = axis × up (canonical +X) — the plane's implied
    # yDir = normal × xDir = axis (canonical +Y)
    tx = ay * uz - az_ * uy
    ty = az_ * ux - ax * uz
    tz = ax * uy - ay * ux
    px, py, pz = (float(c) for c in axis_point)
    plane = cq.Plane(origin=cq.Vector(px, py, pz),
                     xDir=cq.Vector(tx, ty, tz),
                     normal=cq.Vector(ux, uy, uz))
    return cq.Workplane(obj=tail.val().moved(cq.Location(plane)))



def _unit(v):
    x, y, z = (float(c) for c in v)
    n = math.sqrt(x * x + y * y + z * z)
    if n < 1e-9:
        raise ValueError("direction vector must be non-zero")
    return x / n, y / n, z / n


def _to_world(wp, axis_point, axis_dir, print_up):
    """Map a solid built in the CANONICAL frame (feature axis +Y, print-up +Z,
    origin on the face) onto a world axis — the same rigid map
    teardrop_boss_support uses. Never post-transform the result."""
    ax, ay, az = _unit(axis_dir)
    ux, uy, uz = _unit(print_up)
    tx, ty, tz = ay * uz - az * uy, az * ux - ax * uz, ax * uy - ay * ux
    px, py, pz = (float(c) for c in axis_point)
    plane = cq.Plane(origin=cq.Vector(px, py, pz),
                     xDir=cq.Vector(tx, ty, tz),
                     normal=cq.Vector(ux, uy, uz))
    return cq.Workplane(obj=wp.val().moved(cq.Location(plane)))


def _axis_case(axis_dir, print_up):
    """'along' (bore/rib runs in the build direction — nothing overhangs),
    'sideways' (perpendicular — the ceiling needs shaping), or raise."""
    ax, ay, az = _unit(axis_dir)
    ux, uy, uz = _unit(print_up)
    d = abs(ax * ux + ay * uy + az * uz)
    if d > 1.0 - 1e-6:
        return "along"
    if d < 1e-6:
        return "sideways"
    raise ValueError(
        "axis_dir must be either parallel or perpendicular to print_up "
        f"(got |cos| = {d:.3f}); an oblique feature needs a hand-built shape")


def printable_bore(diameter, length, axis_point=(0.0, 0.0, 0.0),
                   axis_dir=(0.0, 1.0, 0.0), print_up=(0.0, 0.0, 1.0),
                   overshoot=0.0):
    """CUTTER for a round hole, shaped for the part's PRINT DIRECTION. Cut it;
    do not rotate the result (the teardrop peak is direction-sensitive).

    THE POINT: a hole whose axis runs SIDEWAYS in the print has a circular
    ceiling — the top of the bore is a horizontal overhang that droops into
    the hole and takes it out of round. Adding a 45° peak (a "teardrop") makes
    every layer overhang the one below by ≤45°, so it prints round and to size
    without support. A hole whose axis runs ALONG the build direction has no
    ceiling at all, and a teardrop there would just be a wrong-shaped hole —
    so this returns a plain cylinder for that case.

    Callers therefore do NOT need to know which case they are in: pass the
    part's own print_up and the correct cutter comes back. (Two parts sharing
    one bore — a lever printed on its side and the housing printed upright —
    each get the right shape from the same call site.)

    diameter/length — the bore; length runs from axis_point along axis_dir.
    overshoot       — extra length added at BOTH ends (clean booleans).
    """
    r = float(diameter) / 2.0
    if r <= 0.0:
        raise ValueError("diameter must be positive")
    L = float(length)
    if L <= 0.0:
        raise ValueError("length must be positive")
    o = float(overshoot)
    if o < 0.0:
        raise ValueError("overshoot must be >= 0")
    case = _axis_case(axis_dir, print_up)
    ax, ay, az = _unit(axis_dir)
    px, py, pz = (float(c) for c in axis_point)
    start = cq.Vector(px - ax * o, py - ay * o, pz - az * o)
    total = L + 2.0 * o

    if case == "along":                       # vertical hole: no ceiling
        return cq.Workplane("XY").add(cq.Solid.makeCylinder(
            r, total, start, cq.Vector(ax, ay, az)))

    # sideways: circle + 45° peak, apex r*sqrt(2) above the axis
    a = r * math.sqrt(2.0) / 2.0              # 45° tangency half-width
    body = cq.Workplane("XZ").circle(r).extrude(-total)          # XZ, -L -> +Y
    peak = (cq.Workplane("XZ")
            .polyline([(-a, a), (a, a), (0.0, r * math.sqrt(2.0))])
            .close().extrude(-total))
    return _to_world(body.union(peak), (start.x, start.y, start.z),
                     axis_dir, print_up)


def contact_rib(mean_diameter, proud=0.85, thickness=0.85,
                axis_point=(0.0, 0.0, 0.0), axis_dir=(0.0, 1.0, 0.0),
                print_up=(0.0, 0.0, 1.0)):
    """A thin proud RING standing off a face — a CONTACT/THRUST rib. UNION it.

    Why a ring and not the whole face: when a rotating part has to bottom out
    against a fixed one, seating it on a narrow ring instead of a full annulus
    collapses the friction radius AND the contact area, so the joint locates
    axially (a crisp, repeatable datum — which is the point when the distance
    it sets is something like a sensor air gap) without adding drag. It also
    gives the printer a small, well-defined face to lay down flat instead of a
    wide one that only touches on its high spots.

    Defaults are the house size: 0.85 wide × 0.85 proud — about one nozzle
    each way, the smallest rib that still prints as a solid wall.

    When the ring's axis runs SIDEWAYS in the print (proud of a vertical
    wall), its own underside overhangs, so the teardrop support is fused on
    automatically; when it stands on a horizontal face nothing is needed and
    the bare ring comes back.
    """
    md = float(mean_diameter)
    t = float(thickness)
    h = float(proud)
    if md <= 0.0 or t <= 0.0 or h <= 0.0:
        raise ValueError("mean_diameter, thickness and proud must be positive")
    if t >= md:
        raise ValueError("thickness must be smaller than mean_diameter")
    ro, ri = md / 2.0 + t / 2.0, md / 2.0 - t / 2.0
    case = _axis_case(axis_dir, print_up)
    ax, ay, az = _unit(axis_dir)
    px, py, pz = (float(c) for c in axis_point)

    if case == "along":                       # ring stands on a flat face
        v = cq.Vector(ax, ay, az)
        o = cq.Vector(px, py, pz)
        return (cq.Workplane("XY").add(cq.Solid.makeCylinder(ro, h, o, v))
                .cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(
                    ri, h + 2.0, o - v * 1.0, v))))
    ring = cq.Workplane("XZ").circle(ro).circle(ri).extrude(-h)   # -> +Y
    out = _to_world(ring, axis_point, axis_dir, print_up)
    return out.union(teardrop_boss_support(ro, h, axis_point, axis_dir, print_up))


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

    # nothing INSIDE the supported cylinder (ring features must stay open)
    inside = s.intersect(cq.Workplane("XZ").circle(R - 0.05)
                         .extrude(-(L + 2.0)).translate((0.0, -1.0, 0.0)))
    iv = inside.val().Volume() if inside.val() is not None else 0.0
    print(f"  inside-cylinder vol  {iv:.4f} {'ok' if iv < 1e-6 else 'FAIL'}")
    if iv >= 1e-6:
        fails.append("inside cylinder")

    # transform: axis +X from (10, 5, 2) → tail below that point, spans x 10..11
    t = teardrop_boss_support(R, L, (10.0, 5.0, 2.0), (1.0, 0.0, 0.0))
    tb = t.val().BoundingBox()
    tr_ok = (abs(tb.xmin - 10.0) < 0.01 and abs(tb.xmax - 11.0) < 0.01
             and abs(tb.zmin - (2.0 + tip)) < 0.01
             and abs((tb.ymin + tb.ymax) / 2.0 - 5.0) < 0.01)
    print(f"  transform (+X axis)   {'ok' if tr_ok else 'FAIL'}")
    if not tr_ok:
        fails.append("transform")

    # print_up: a +Y print with the boss running DOWN world −Z from a seat
    # at z=10 (the toothpaste-dispenser mount case) — tail must hang −Y,
    # run z 10−L..10
    p = teardrop_boss_support(R, L, (0.0, 0.0, 10.0), (0.0, 0.0, -1.0),
                              print_up=(0.0, 1.0, 0.0))
    pb = p.val().BoundingBox()
    pu_ok = (abs(pb.ymin - tip) < 0.01 and abs(pb.ymax + a) < 0.01
             and abs(pb.zmax - 10.0) < 0.01 and abs(pb.zmin - (10.0 - L)) < 0.01
             and abs(pb.xmin + a) < 0.01 and abs(pb.xmax - a) < 0.01)
    print(f"  print_up (+Y print)   {'ok' if pu_ok else 'FAIL'}")
    if not pu_ok:
        fails.append("print_up")

    # default length: ramp-capped tail = radius/sqrt(2) deep
    d = teardrop_boss_support(R)
    db = d.val().BoundingBox()
    dl_ok = abs(db.ymax - a) < 0.01 and abs(db.ymin) < 0.01
    print(f"  default length (r/sqrt2) {'ok' if dl_ok else 'FAIL'}")
    if not dl_ok:
        fails.append("default length")

    for args, kw in (({"axis_dir": (0, 0, 1)}, "axis parallel to up"),
                     ({"axis_dir": (0, 0, 0)}, "zero axis"),
                     ({"axis_dir": (0, 1, 0), "print_up": (0, 1, 0)},
                      "up parallel to axis")):
        try:
            teardrop_boss_support(R, L, (0, 0, 0), **args)
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
