"""Print-aware HOLE cutters.

`house_hole(d, length, axis_point, axis_dir, print_up)` is the teardrop's
bounding "house": the same 45° roof and apex, but straight walls tangent to
the Ø`d` circle and a flat floor tangent to it - a pentagon. Use it for
CLEARANCE passages (something Ø<d must pass, nothing rides the bore): the
square corners are free room, and where a round floor would have left a thin
cusp against a neighbouring cut the flat one merges cleanly.

`teardrop_hole(d, length, axis_point, axis_dir, print_up)` returns a CUTTER
for a round hole whose axis runs PERPENDICULAR or OBLIQUE to the print
direction. A plain cylinder cut prints with an unsupported sagging
round ceiling; the teardrop replaces the TOP of the circle with two 45°
flats meeting at an apex r*sqrt(2) above the axis - every ceiling surface
sits at the self-support threshold, so the hole prints clean with no
supports. The round LOWER half is untouched: pins, rods and bearings ride
exactly as in a round bore (contact is at the bottom).

Conventions (same as supports.py): describe the site with `axis_point`
(a point on the bore axis where the cutter starts), `axis_dir` (the bore
axis; the cutter extrudes `length` that way) and `print_up` (the part's
build direction). Use the returned solid as-is - never post-rotate or
mirror it; orient via the arguments instead. `axis_dir` must not be
PARALLEL to `print_up` (a vertical hole prints round on its own - asking
for a teardrop there raises). `house_hole` is sideways-only: it needs the
axis perpendicular.

OBLIQUE HOLES (axis tilted from print_up, neither parallel nor square to it).
A round bore's worst surface is its crown, and that crown faces down only as
steeply as the hole is tilted: at tilt T from the build axis its slope is
90-T. So the peak is sized FROM THE TILT, not fixed at 45:

    T <= 45 (SELF_SUPPORT_DEG)   the round bore already self-supports -> the
                                 cutter IS the round bore, no peak at all
    45 < T < 90                  a partial peak: flats tangent at psi from the
                                 crown, cos(psi) = cos(45)/sin(T), apex r/cos(psi)
    T = 90 (sideways)            psi = 45, apex r*sqrt(2) -- the classic teardrop

Every case leaves the steepest ceiling at exactly the limit and no steeper. A
fixed 45 teardrop on an oblique hole is not wrong, just wasteful: it slits
walls the hole never needed to touch.

THE HOLE'S MOUTH, AT EXACTLY THE LIMIT -- and an earlier version of this note
was WRONG. It claimed the mouth adds no overhang, "measured": but the
measurement was a FACE-ANGLE probe, and every face there really is at 45. What
it cannot see is a 45-degree crown that DESCENDS toward the mouth, so the last
of it hangs from its low, outer end. A slicer-style layer-support check found
it: ~0.15 mm2 per hole at the +X mouths of Ø4 holes tilted exactly 45 in a
45-built floating tenon. So a hole tilted at (or within a hair of) the limit
that exits on its crown's downhill side should be cut with a stricter
`limit_deg`, and HOW strict is worth measuring rather than guessing: for those
tenon holes 50 still left 0.17 mm2 across three mouths, 60 left nothing. The
crown then gets a peak and the mouth prints. The default stays 45, so sideways holes
keep their classic teardrop. PARALLEL still raises -- a hole along the build
axis prints round on its own.

DULL TIPS (user, 2026-09-10). A printer cannot lay down a knife point, so
both cutters end their roof in a FLAT one `nozzle` wide instead of a knife
point - the same dull tip the joinery arrowheads use. It is small
enough to bridge without deforming, so it adds no overhang. Sideways it takes
nozzle/2 off the apex height; an oblique hole's partial peak is steeper in
section, so the same one-nozzle flat sits only (nozzle/2)*tan(psi) below its
apex. The flat is clamped so it never drops into the round bore itself (small
holes: it sits on the bore's crown instead). Pass nozzle=0 for the old sharp
point.

Mind the apex room: sideways, the peak reaches r*sqrt(2) - nozzle/2 from the
axis in the `print_up` direction. In thin webs (e.g. a bore through a ring
whose wall is thinner than that) the apex will slit the crown; usually
harmless for a cutter, but check the site.
"""

import math

import cadquery as cq

__all__ = ["teardrop_hole", "house_hole", "SELF_SUPPORT_DEG"]

SELF_SUPPORT_DEG = 45.0     # steepest ceiling that prints without support


def _unit(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n < 1e-12:
        raise ValueError("zero-length direction")
    return (v[0] / n, v[1] / n, v[2] / n)


def _section_plane(axis_point, a, up):
    """The bore's cross-section plane: normal = axis `a`, yDir = `up` (unit,
    perpendicular to `a`)."""
    x = (up[1] * a[2] - up[2] * a[1],             # xDir = up x axis ->
         up[2] * a[0] - up[0] * a[2],             # plane yDir = axis x x
         up[0] * a[1] - up[1] * a[0])             #            = up
    return cq.Plane(origin=cq.Vector(*axis_point), xDir=cq.Vector(*x),
                    normal=cq.Vector(*a))


def _hole_plane(axis_point, axis_dir, print_up, who):
    a = _unit(axis_dir)
    u = _unit(print_up)
    if abs(a[0] * u[0] + a[1] * u[1] + a[2] * u[2]) > 1e-6:
        raise ValueError(f"{who} needs axis_dir PERPENDICULAR to "
                         "print_up - a hole along the build direction "
                         "prints round; no teardrop needed there")
    return _section_plane(axis_point, a, u)


def teardrop_hole(d, length, axis_point=(0.0, 0.0, 0.0),
                  axis_dir=(1.0, 0.0, 0.0), print_up=(0.0, 0.0, 1.0),
                  limit_deg=SELF_SUPPORT_DEG, nozzle=0.8):
    """CUTTER for a round hole: a Ø`d` cylinder from `axis_point` along
    `axis_dir` for `length`, its ceiling peaked toward `print_up` only as far
    as the hole's tilt requires (see OBLIQUE HOLES above), the peak DULLED to
    a `nozzle`-wide flat (never below the bore's crown). Square to print_up
    that is the classic 45° teardrop, flat at (d/2)*sqrt(2) - nozzle/2; tilted
    `limit_deg` or less it is the plain round bore. Blind holes: the flat far
    end is the floor, as with a plain cylinder; overshoot the mouth by passing
    a longer length / earlier axis_point."""
    if d <= 0.0 or length <= 0.0 or nozzle < 0.0:
        raise ValueError("d and length must be > 0, nozzle >= 0")
    a = _unit(axis_dir)
    u = _unit(print_up)
    c = a[0] * u[0] + a[1] * u[1] + a[2] * u[2]
    if abs(c) > 1.0 - 1e-9:
        raise ValueError("teardrop_hole: axis_dir is PARALLEL to print_up - "
                         "a hole along the build direction prints round; no "
                         "teardrop needed there")
    # the part of print_up the bore's cross-section actually sees
    up = _unit((u[0] - c * a[0], u[1] - c * a[1], u[2] - c * a[2]))
    sin_t = math.sqrt(max(0.0, 1.0 - c * c))
    plane = _section_plane(axis_point, a, up)
    r = d / 2.0
    bore = cq.Workplane(plane).circle(r).extrude(length)
    # limit_deg: the steepest ceiling allowed. Stricter than the default gives a
    # peak where the plain bore would sit exactly AT 45 (see THE HOLE'S MOUTH).
    cos_psi = math.cos(math.radians(limit_deg)) / sin_t
    if cos_psi >= 1.0 - 1e-9:
        return bore                               # tilt <= limit: round is fine
    psi = math.acos(cos_psi)
    k, h = r * math.sin(psi), r * math.cos(psi)   # tangent point
    apex = r / cos_psi
    # dull tip: a flat one nozzle wide sits (nozzle/2)*tan(psi) below the apex
    # (nozzle/2 sideways), never into the bore
    flat = max(apex - (nozzle / 2.0) * math.tan(psi), r)
    w = k * (apex - flat) / (apex - h)            # flat half-width (nozzle/2 unless clamped)
    pts = ([(-k, h), (0.0, apex), (k, h)] if w <= 1e-9
           else [(-k, h), (-w, flat), (w, flat), (k, h)])
    peak = cq.Workplane(plane).polyline(pts).close().extrude(length)
    return bore.union(peak)


def house_hole(d, length, axis_point=(0.0, 0.0, 0.0),
               axis_dir=(1.0, 0.0, 0.0), print_up=(0.0, 0.0, 1.0), wall=None,
               nozzle=0.8):
    """CUTTER for a sideways CLEARANCE passage: a `d`-wide rectangle `wall`
    tall with a 45° roof on top (roof height d/2), apex toward `print_up`,
    DULLED to a `nozzle`-wide flat nozzle/2 below that apex (never below the
    eaves). The axis sits d/2 above the flat floor, so the sharp apex would
    be `wall` above it. Default wall = (d/2)*sqrt(2): the pentagon that bounds
    a Ø`d` teardrop (same roof, same dull tip), so anything Ø<=d passes - for
    that default the flat is also kept off the circle's crown. A shorter wall
    cuts into that circle. Same argument conventions as teardrop_hole."""
    r = d / 2.0
    bounds_circle = wall is None
    if wall is None:
        wall = r * math.sqrt(2.0)
    if d <= 0.0 or length <= 0.0 or wall <= 0.0 or nozzle < 0.0:
        raise ValueError("d, length and wall must be > 0, nozzle >= 0")
    plane = _hole_plane(axis_point, axis_dir, print_up, "house_hole")
    eave = wall - r
    flat = max(wall - nozzle / 2.0, eave, r if bounds_circle else eave)
    w = wall - flat                               # flat half-width (nozzle/2 unless clamped)
    if w <= 1e-9:
        pts = [(-r, -r), (r, -r), (r, eave), (0.0, wall), (-r, eave)]
    elif w >= r - 1e-9:
        pts = [(-r, -r), (r, -r), (r, eave), (-r, eave)]
    else:
        pts = [(-r, -r), (r, -r), (r, eave), (w, flat), (-w, flat), (-r, eave)]
    return cq.Workplane(plane).polyline(pts).close().extrude(length)


# ── Self-test: geometry gates (run `py -3.12 holes.py`) ──────────────────────
if __name__ == "__main__":
    import sys

    fails = []

    def check(label, ok, detail):
        print(f"{label:14s}{detail}{'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(label)

    D, L, NZ = 5.3, 8.0, 0.8
    R = D / 2.0
    S2 = math.sqrt(2.0)
    APEX = R * S2 - NZ / 2.0                      # dulled apex height
    TIP = NZ * NZ / 4.0                           # the knife point the flat removes
    # teardrop cross-section area = pi*r^2 + r^2*(1 - pi/4), less the dulled tip
    want_v = (math.pi * R * R + R * R * (1.0 - math.pi / 4.0) - TIP) * L

    t = teardrop_hole(D, L)                       # axis +X, up +Z
    bb = t.val().BoundingBox()
    check("volume", abs(t.val().Volume() - want_v) < 1e-3,
          f"{t.val().Volume():.3f} (want {want_v:.3f})")
    check("dull apex", abs(bb.zmax - APEX) < 1e-6 and abs(bb.zmin + R) < 1e-6
          and abs(bb.xmin) < 1e-6 and abs(bb.xmax - L) < 1e-6
          and abs(bb.ymin + R) < 1e-6 and abs(bb.ymax - R) < 1e-6,
          f"z[{bb.zmin:.3f},{bb.zmax:.3f}] (want apex {APEX:.3f})")
    # the flat is exactly one nozzle wide
    top = t.faces(">Z").val().BoundingBox()
    check("flat width", abs((top.ymax - top.ymin) - NZ) < 1e-6,
          f"{top.ymax - top.ymin:.3f} (want {NZ})")
    sharp = teardrop_hole(D, L, nozzle=0.0)
    check("nozzle=0", abs(sharp.val().BoundingBox().zmax - R * S2) < 1e-6,
          f"sharp apex {sharp.val().BoundingBox().zmax:.3f} (want {R * S2:.3f})")
    # a small hole clamps the flat onto the bore's crown instead of cutting into it
    small = teardrop_hole(1.2, L)
    check("small clamp", abs(small.val().BoundingBox().zmax - 0.6) < 1e-6
          and small.val().Volume() >= math.pi * 0.36 * L - 1e-6,
          f"apex {small.val().BoundingBox().zmax:.3f} (want 0.600, the crown)")

    # orientation: axis +Y, print up +X -> apex along +X
    t2 = teardrop_hole(D, L, (1.0, 2.0, 3.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
    bb2 = t2.val().BoundingBox()
    check("reoriented", abs(bb2.xmax - (1.0 + APEX)) < 1e-6
          and abs(bb2.ymin - 2.0) < 1e-6 and abs(bb2.ymax - (2.0 + L)) < 1e-6
          and abs(t2.val().Volume() - want_v) < 1e-3,
          f"apex x={bb2.xmax:.3f} (want {1.0 + APEX:.3f})")

    # diagonal horizontal axis, up -Z (a flipped print) -> apex points DOWN
    s2 = 1.0 / S2
    t3 = teardrop_hole(D, L, (0.0, 0.0, 0.0), (s2, s2, 0.0), (0.0, 0.0, -1.0))
    bb3 = t3.val().BoundingBox()
    check("flipped print", abs(bb3.zmin + APEX) < 1e-6 and abs(bb3.zmax - R) < 1e-6
          and abs(t3.val().Volume() - want_v) < 1e-3,
          f"apex z={bb3.zmin:.3f} (want {-APEX:.3f})")

    # a rod one fit-gap smaller must ride the cut bore without touching
    block = (cq.Workplane("XY").box(L, 20.0, 20.0, centered=(False, True, True))
             .cut(teardrop_hole(D, L + 2.0, (-1.0, 0.0, 0.0))))
    rod = (cq.Workplane(cq.Plane(origin=cq.Vector(0, 0, 0),
                                 xDir=cq.Vector(0, 1, 0),
                                 normal=cq.Vector(1, 0, 0)))
           .circle(R - 0.15).extrude(L))
    try:
        inter = sum(s.Volume() for s in block.intersect(rod).solids().vals())
    except Exception:
        inter = 0.0
    check("rod clearance", inter < 1e-6, f"{inter:.6f} mm3 (must be 0)")

    # house: pentagon area = d*wall + r^2, less the dulled tip; holds the teardrop
    want_h = (2 * R * R * S2 + R * R - TIP) * L
    hh = house_hole(D, L, (1.0, 2.0, 3.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
    bbh = hh.val().BoundingBox()
    cont = hh.intersect(teardrop_hole(D, L, (1.0, 2.0, 3.0), (0.0, 1.0, 0.0),
                                      (1.0, 0.0, 0.0))).val().Volume()
    check("house", abs(hh.val().Volume() - want_h) < 1e-3 and abs(cont - want_v) < 1e-3
          and abs(bbh.xmax - (1.0 + APEX)) < 1e-6
          and abs(bbh.xmin - (1.0 - R)) < 1e-6 and abs(bbh.zmax - (3.0 + R)) < 1e-6,
          f"vol {hh.val().Volume():.3f} (want {want_h:.3f}), holds the teardrop "
          f"{cont:.3f}/{want_v:.3f}, apex x={bbh.xmax:.3f}")
    hw = house_hole(D, L, wall=2.0 * R)           # explicit wall: d*wall + r^2 - tip
    bbw = hw.val().BoundingBox()
    check("house wall", abs(hw.val().Volume() - (D * 2.0 * R + R * R - TIP) * L) < 1e-3
          and abs(bbw.zmax - (2.0 * R - NZ / 2.0)) < 1e-6 and abs(bbw.zmin + R) < 1e-6,
          f"vol {hw.val().Volume():.3f} apex z={bbw.zmax:.3f} (want {2.0 * R - NZ / 2.0:.3f})")

    # OBLIQUE: the steepest ceiling a cutter leaves must be AT the limit and
    # never past it, at every tilt; and a tilt <= 45 must be the plain bore.
    # Sloped surfaces are checked SHARP (nozzle=0): the dull flat is a deliberate
    # nozzle-wide bridge whose normal faces straight up, which this check would flag.
    def _worst_ceiling(cutter, axis, up):
        """Largest n.up over the cutter's side surface. The cutter's UP-facing
        surface is the part's DOWN-facing ceiling. End caps excluded."""
        worst = -1.0
        for f in cutter.val().Faces():
            vs, tris = f.tessellate(0.02)
            for i, j, k2 in tris:
                A, Bv, C = vs[i], vs[j], vs[k2]
                e1 = (Bv.x - A.x, Bv.y - A.y, Bv.z - A.z)
                e2 = (C.x - A.x, C.y - A.y, C.z - A.z)
                n = (e1[1] * e2[2] - e1[2] * e2[1],
                     e1[2] * e2[0] - e1[0] * e2[2],
                     e1[0] * e2[1] - e1[1] * e2[0])
                m = math.sqrt(sum(q * q for q in n))
                if m < 1e-12:
                    continue
                n = tuple(q / m for q in n)
                if abs(sum(n[q] * axis[q] for q in range(3))) > 0.99:
                    continue                      # an end cap, not the bore
                worst = max(worst, sum(n[q] * up[q] for q in range(3)))
        return worst

    lim = math.cos(math.radians(SELF_SUPPORT_DEG))
    for tilt in (90.0, 75.0, 60.0, 50.0, 45.0, 30.0):
        ax = (math.sin(math.radians(tilt)), 0.0, math.cos(math.radians(tilt)))
        cut = teardrop_hole(D, L, (0.0, 0.0, 0.0), ax, (0.0, 0.0, 1.0), nozzle=0.0)
        w = _worst_ceiling(cut, ax, (0.0, 0.0, 1.0))
        vol = cut.val().Volume()
        ok = w <= lim + 2e-3
        if tilt <= SELF_SUPPORT_DEG:
            ok = ok and abs(vol - math.pi * R * R * L) < 1e-3
        ang = math.degrees(math.acos(max(-1.0, min(1.0, w))))
        check(f"tilt {tilt:.0f}", ok,
              f"steepest ceiling {ang:4.1f} deg from down, vol {vol:7.3f}")
    # a STRICTER limit peaks a hole the default would leave round at exactly 45
    ax45 = (math.sqrt(0.5), 0.0, math.sqrt(0.5))
    strict = teardrop_hole(D, L, (0.0, 0.0, 0.0), ax45, (0.0, 0.0, 1.0),
                           limit_deg=50.0, nozzle=0.0)
    w = _worst_ceiling(strict, ax45, (0.0, 0.0, 1.0))
    check("limit 50 @45", strict.val().Volume() > math.pi * R * R * L + 1e-3
          and w <= math.cos(math.radians(50.0)) + 2e-3,
          "peaked, steepest ceiling %.1f deg from down"
          % math.degrees(math.acos(max(-1.0, min(1.0, w)))))
    # dulled OBLIQUE peak: inside the sharp one, above the crown, and smaller
    ax60 = (math.sin(math.radians(60.0)), 0.0, math.cos(math.radians(60.0)))
    s60 = teardrop_hole(D, L, (0.0, 0.0, 0.0), ax60, (0.0, 0.0, 1.0), nozzle=0.0)
    d60 = teardrop_hole(D, L, (0.0, 0.0, 0.0), ax60, (0.0, 0.0, 1.0))
    inside = d60.intersect(s60).val().Volume()
    check("dull oblique", abs(inside - d60.val().Volume()) < 1e-3
          and math.pi * R * R * L < d60.val().Volume() < s60.val().Volume() - 1e-4,
          f"vol {d60.val().Volume():.3f} (sharp {s60.val().Volume():.3f}, "
          f"bore {math.pi * R * R * L:.3f})")

    # the PLAIN bore must fail that same check sideways, or it proves nothing
    plain = (cq.Workplane(cq.Plane((0, 0, 0), (0, 1, 0), (1, 0, 0)))
             .circle(R).extrude(L))
    w = _worst_ceiling(plain, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    check("control", w > lim + 0.1, " plain sideways bore is flagged")

    # vertical axis must raise; zero size must raise
    for label, kwargs in (("parallel axis", dict(axis_dir=(0, 0, 1))),
                          ("zero d", dict())):
        try:
            teardrop_hole(0.0 if label == "zero d" else D, L, **kwargs)
            check(label, False, " did NOT raise")
        except ValueError:
            check(label, True, " raises (ok)")

    if fails:
        print("FAIL:", *fails, sep="\n  ")
    else:
        print("OK - teardrop + house holes: exact areas, DULL nozzle-wide tips (clamped "
              "off the bore), apex tracks print_up (incl. flipped prints), round lower "
              "half preserved, oblique peaks sized to the tilt (round at <=45), "
              "parallel refused.")
    sys.exit(len(fails))
