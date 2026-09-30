# -*- coding: utf-8 -*-
"""CABLES, drawn as OCTAGONAL prisms rather than cylinders.

`oct_cable(pts, d)` is the one entry point: a cable through a polyline, section
an octagon ACROSS-FLATS = `d`, ends left exactly where they are (they are
connector contacts), interior corners filled with no elbow solid at all.

WHY NOT CYLINDERS AND BALL ELBOWS, which is what every one of these models
started with. A sphere meeting two cylinders along a shared circle is the
tangent case OCCT handles worst, and a cable is dozens of them in one fuse.
Measured on a 24 V head (36 points, one loop): the cylinders alone fused
whole, but with the elbow spheres every tolerance came back with 0.19-0.31 of
the cable, or in loose pieces. Worse, the failure is SILENT -- the fuse
returns ONE valid solid with material missing out of the middle (645 of
1776 mm3, once), so nothing raises and only the volume says so. Every boolean
an overlap gate runs against a curved face also costs more than one against
planes, and a model's cables are most of its part pairs.

So: one octagonal prism per segment, ACROSS-FLATS = the cable's diameter, so
the real round cable always fits INSIDE the model and any error lands on the
side of clearance (the corners stand 8 % proud). Bends get no elbow: each
segment runs past an interior corner by half its width, and the overlapping
ends fill the outside of the bend with flat faces. Nothing in the fuse is
tangent to anything.

The prisms are rolled 22.5 degrees so a FLAT, not a corner, faces each
principal direction: stacked lanes then sit flat against each other and
against the floor of a trough.

THE FUSE IS CHECKED BY VOLUME against the section times the path length,
because of the silent loss above. A cable that cannot be fused whole at any
tolerance RAISES rather than returning a cable with holes in it.
"""

from __future__ import annotations

import math as _math

import cadquery as cq

_OCT_R = 1.0 / _math.cos(_math.pi / 8)          # circumradius per unit half-across-flats


def oct_area(d: float) -> float:
    """Section area of a regular octagon, across-flats `d`."""
    return 2.0 * d * d * (_math.sqrt(2.0) - 1.0)


def oct_prism(s0, u, length: float, d: float):
    """One octagonal prism from point `s0` along unit vector `u`, across-flats `d`."""
    ref = cq.Vector(0, 0, 1) if abs(u.z) < 0.9 else cq.Vector(1, 0, 0)
    x = ref.cross(u).normalized()
    plane = cq.Plane(origin=s0, xDir=x, normal=u)
    return (cq.Workplane(plane).transformed(rotate=(0, 0, 22.5))
            .polygon(8, 2 * (d / 2) * _OCT_R).extrude(length).val())


def oct_cable(pts, d: float) -> cq.Workplane:
    """A cable through `pts` (a polyline of (x, y, z)), octagonal section,
    across-flats `d`. See the module docstring for why it is not round."""
    segs = []
    for a, b in zip(pts, pts[1:]):
        va, vb = cq.Vector(*a), cq.Vector(*b)
        if (vb - va).Length > 1e-6:
            segs.append((va, vb))
    if not segs:
        return cq.Workplane("XY")
    r = d / 2.0
    parts = []
    for i, (va, vb) in enumerate(segs):
        u = (vb - va).normalized()
        s0 = va - u * r if i > 0 else va
        s1 = vb + u * r if i < len(segs) - 1 else vb
        parts.append(oct_prism(s0, u, (s1 - s0).Length, d))
    if len(parts) == 1:
        return cq.Workplane("XY").add(parts[0])
    want = oct_area(d) * sum((vb - va).Length for va, vb in segs)
    for tol in (None, 1e-5, 1e-4):
        try:
            fused = parts[0].fuse(*parts[1:], tol=tol) if tol else parts[0].fuse(*parts[1:])
        except Exception:
            continue
        if fused.Solids() and fused.Volume() >= 0.9 * want:
            return cq.Workplane("XY").add(fused.clean())
    raise RuntimeError("oct_cable: no fuse tolerance returned a whole cable "
                       "(%d segments, wanted >= %.1f mm3)" % (len(segs), want))


def _segments(pts):
    """[(va, vb)] the polyline's real segments, zero-length ones dropped."""
    segs = []
    for a, b in zip(pts, pts[1:]):
        va, vb = cq.Vector(*a), cq.Vector(*b)
        if (vb - va).Length > 1e-6:
            segs.append((va, vb))
    return segs


def _frames(dirs, across=None):
    """[(a, b)] one ROTATION-MINIMISING cross-section frame per segment direction.

    `across` aims b at the START of the path; see bundle_paths, which is where this walk
    used to live inline. flat_cable needs the same frames for the same reason -- a ribbon
    and a bundle of conductors are the same section, drawn two ways -- and two copies of
    the walk below would be two places for the near-parallel bug in it to come back."""
    ref = cq.Vector(0, 0, 1) if abs(dirs[0].z) < 0.9 else cq.Vector(1, 0, 0)
    if across is not None:
        want = cq.Vector(*across)
        # a is chosen so that b = u x a comes out along `across`
        cand = want.cross(dirs[0])
        if cand.Length > 1e-6:
            ref = want
            fa = cand.normalized()
        else:
            fa = ref.cross(dirs[0]).normalized()
    else:
        fa = ref.cross(dirs[0]).normalized()
    frames = [(fa, dirs[0].cross(fa).normalized())]
    for u_prev, u in zip(dirs, dirs[1:]):
        a_prev, _ = frames[-1]
        # ROTATE the frame by the rotation that carries u_prev onto u -- Rodrigues about
        # their common normal. It used to PROJECT the old axis onto the new segment's
        # normal plane instead, which is the same thing for a small turn and is not the
        # same thing at all for a big one: when a_prev lies near the NEW direction the
        # projection is nearly zero, and normalising a nearly-zero vector returns noise.
        # The guard below it was set at 1e-9, so it only caught an exact reversal and
        # never fired for the far more common near-parallel case.
        #
        # What that looked like downstream: the whole bundle pinching to a point at one
        # vertex. Offsetting a line ALONG itself does not move it, so once the frame's
        # axis lines up with a segment every conductor's offset line for that segment is
        # the same line, their mitres all land in the same place, and the section has no
        # width there. Measured on three separate cables before it was understood --
        # neighbour gaps reading 0.00 where they should have been the connector's pitch.
        ax = u_prev.cross(u)
        if ax.Length > 1e-9:
            ax = ax.normalized()
            c = max(-1.0, min(1.0, u_prev.dot(u)))
            sn = _math.sqrt(max(0.0, 1.0 - c * c))
            a_new = (a_prev * c + ax.cross(a_prev) * sn
                     + ax * (ax.dot(a_prev) * (1.0 - c)))
        else:                                   # parallel or a full reversal
            a_new = a_prev - u * a_prev.dot(u)
            if a_new.Length < 1e-6:
                a_new = ref.cross(u)
                if a_new.Length < 1e-6:
                    a_new = cq.Vector(1, 0, 0).cross(u)
        a_new = (a_new - u * a_new.dot(u))      # square it up against float drift
        a_new = a_new.normalized()
        frames.append((a_new, u.cross(a_new).normalized()))
    return frames


def flat_bends(pts, across=None):
    """[(vertex, kind, degrees)] every turn in a flat cable's path, kind "bend" or "fold".

    See flat_cable: a BEND is about the ribbon's width and costs nothing, a FOLD is in the
    ribbon's own plane and has to be creased in by hand. Worth having separately from the
    solid because the fold count is an assembly instruction, not a shape."""
    segs = _segments(pts)
    if len(segs) < 2:
        return []
    dirs = [(vb - va).normalized() for va, vb in segs]
    frames = _frames(dirs, across)
    out = []
    for i in range(1, len(segs)):
        ax = dirs[i - 1].cross(dirs[i])
        if ax.Length <= 1e-9:
            continue
        ax = ax.normalized()
        a, b = frames[i - 1]
        deg = _math.degrees(_math.acos(max(-1.0, min(1.0, dirs[i - 1].dot(dirs[i])))))
        if abs(ax.dot(b)) > 0.9:
            out.append((i, "bend", deg))
        elif abs(ax.dot(a)) > 0.9:
            out.append((i, "fold", deg))
        else:
            raise RuntimeError(
                "flat_cable: the turn at vertex %d is neither a bend about the ribbon's "
                "width nor a fold in its own plane (%.0f deg about %.2f of thickness, "
                "%.2f of width) -- real cable would have to fold and twist at once"
                % (i, deg, abs(ax.dot(a)), abs(ax.dot(b))))
    return out


def flat_cable(pts, w: float, t: float, across=None) -> cq.Workplane:
    """A FLAT RIBBON through `pts`: ONE prism of section `w` x `t`, `w` aimed `across`.

    The alternative is what this replaces -- N conductors from `bundle_paths`, one solid
    each. That is the truth about a ribbon and it is the wrong model of it: fourteen
    octagonal sweeps are fourteen solids in every boolean the gate runs, for a part whose
    only interesting property is the rectangle they add up to. A ribbon is a single piece
    of cable and nothing can move relative to anything else inside it, so it gets one
    solid (user, 2026-09-28). `bundle_paths` is still what draws a BUNDLE, where the
    conductors really are separate and really can take different routes.

    Same corner idiom as `oct_cable`: no elbow solid, each segment overrunning an interior
    corner so the overlap fills the outside of the turn with flat faces. HOW FAR it has to
    overrun depends on which way the ribbon turns, which is the one thing a flat cable has
    that a round one does not:

      * a BEND, about the ribbon's width axis, is free -- the cable curves the way it is
        meant to, and the corner is filled by overrunning HALF THE THICKNESS.
      * a FOLD, about the ribbon's thickness axis, is an in-plane change of direction, and
        flat cable can only do it by being creased over at 45 degrees. The folded corner
        occupies the whole square of the turn, so the overrun is HALF THE WIDTH.

    Both are ordinary; a fold is how every ribbon in every instrument turns a corner on a
    flat surface. But a fold is also an ASSEMBLY STEP -- somebody has to crease the cable,
    the right way round -- so `flat_bends` below names them and the caller declares how
    many it expects. Anything in between the two (a turn that would need a fold and a
    twist at once) raises.
    """
    segs = _segments(pts)
    if not segs:
        return cq.Workplane("XY")
    dirs = [(vb - va).normalized() for va, vb in segs]
    frames = _frames(dirs, across)
    kinds = {i: k for i, k, _deg in flat_bends(pts, across)}
    over = [0.0] * (len(segs) + 1)              # how far each vertex's turn reaches
    for i, k in kinds.items():
        over[i] = (w if k == "fold" else t) / 2.0
    parts = []
    for i, (va, vb) in enumerate(segs):
        u = dirs[i]
        a, b = frames[i]
        s0 = va - u * over[i]
        s1 = vb + u * over[i + 1]
        # CENTRED on the path, which is worth saying because the un-centred version of
        # this was wrong: with xDir=b and normal=u the plane's own y comes out as MINUS
        # the thickness axis (b is defined as u x a), so an origin shifted by -a*t/2 put
        # the whole section a full thickness off its centreline.
        plane = cq.Plane(origin=s0, xDir=b, normal=u)
        parts.append(cq.Workplane(plane).rect(w, t, centered=True)
                     .extrude((s1 - s0).Length).val())
    if len(parts) == 1:
        return cq.Workplane("XY").add(parts[0])
    want = w * t * sum((vb - va).Length for va, vb in segs)
    for tol in (None, 1e-5, 1e-4):
        try:
            fused = parts[0].fuse(*parts[1:], tol=tol) if tol else parts[0].fuse(*parts[1:])
        except Exception:
            continue
        if fused.Solids() and fused.Volume() >= 0.9 * want:
            return cq.Workplane("XY").add(fused.clean())
    raise RuntimeError("flat_cable: no fuse tolerance returned a whole ribbon "
                       "(%d segments, wanted >= %.1f mm3)" % (len(segs), want))


def path_length(pts) -> float:
    """Polyline length, which for a cable is the LENGTH YOU HAVE TO BUY."""
    return sum((vb - va).Length for va, vb in _segments(pts))


def bundle_paths(pts, offsets, across=None):
    """Split one bundle centreline into N CONDUCTOR paths, one per (a, b) offset.

    `offsets` are in the bundle's OWN cross-section, so a conductor keeps its place
    in the bundle around every corner. A constant WORLD offset cannot: the moment a
    segment runs parallel to the offset direction, two conductors slide onto the
    same line and become the same cable. (A leg harness has exactly that -- mostly
    vertical, with horizontal jogs at both ends.)

    The frames are ROTATION-MINIMISING: the first is built off whichever world axis
    is least parallel to the run, and each next one is the previous rotated by the
    smallest rotation carrying one segment direction onto the next, so the bundle
    does not spin about its own axis just because the path turned a corner. At a
    vertex the two adjoining frames are averaged, which keeps each conductor a
    single unbroken polyline through the turn.

    `across` AIMS the cross-section: the second offset axis is lined up with it at the
    START of the path. Without it the frame is seeded off whichever world axis is least
    parallel to the run, so which conductor sits on which side of the bundle is
    arbitrary -- and when the bundle then fans out onto a row of connector pins, wires
    cross over each other to reach their own way. Pass the pin row's direction and the
    fan comes out in order.

    Returns a list of point-lists, one per offset, ready for `oct_cable`.
    """
    segs = _segments(pts)
    if not segs:
        return [list(pts) for _ in offsets]
    dirs = [(vb - va).normalized() for va, vb in segs]
    frames = _frames(dirs, across)
    verts = [segs[0][0]] + [vb for _, vb in segs]
    out = []
    for oa, ob in offsets:
        # each SEGMENT offsets as a whole line, and a vertex is where consecutive
        # offset lines meet -- a true polyline offset, the MITRE. Averaging the two
        # frames at the vertex instead lets each conductor cut the corner by a
        # different amount, and neighbours then cross INSIDE the turn (16 overlaps,
        # the worst 17 mm3, all of them at corners).
        org = [v + a * oa + b * ob for v, (a, b) in zip(verts[:-1], frames)]
        path = [(org[0].x, org[0].y, org[0].z)]
        for i in range(1, len(segs)):
            p0, u0 = org[i - 1], dirs[i - 1]
            p1, u1 = org[i], dirs[i]
            w0 = p0 - p1
            b_ = u0.dot(u1)
            den = 1.0 - b_ * b_
            if den < 1e-9:                      # collinear -- no corner to mitre
                m = p1
            else:                               # closest approach of the two lines
                d_, e_ = u0.dot(w0), u1.dot(w0)
                q0 = p0 + u0 * ((b_ * e_ - d_) / den)
                q1 = p1 + u1 * ((e_ - b_ * d_) / den)
                m = (q0 + q1) * 0.5
            path.append((m.x, m.y, m.z))
        end = verts[-1] + frames[-1][0] * oa + frames[-1][1] * ob
        path.append((end.x, end.y, end.z))
        out.append(path)
    return out


def helix_cable(cx: float, cy: float, z0: float, z1: float, turns: float,
                r: float, d: float) -> cq.Workplane:
    """A slack COIL: a round profile swept along a true helix. THREE faces.

    Round, in a module whose whole point is that cables are not round -- because
    the reason cables are octagonal is that FUSING many round segments loses
    material silently, and a sweep is not a fuse. It is one solid, built from the
    exact helix, in 0.02 s.

    So the rule is about the boolean, not the shape: use this wherever the coil
    can stand as its OWN part, and keep its ends clear of the octagonal run it
    feeds (a tangent round-to-octagon fuse is the case to avoid). Measured on a
    7-turn coil: 3 faces here against ~1200 for `helix_pts` + `oct_cable` at 8
    segments per turn, and ~700 even at 4 -- the cost is the fuse splitting faces
    at every corner, not the segment count, so coarsening barely helps.
    """
    path = cq.Wire.makeHelix((z1 - z0) / turns, z1 - z0, r,
                             cq.Vector(cx, cy, z0), cq.Vector(0, 0, 1))
    prof = cq.Wire.makeCircle(d / 2.0, path.startPoint(), path.tangentAt(0.0))
    return cq.Workplane("XY").add(cq.Solid.sweep(prof, [], path, isFrenet=True))


def helix_pts(cx: float, cy: float, z0: float, z1: float, turns: float,
              r: float, per_turn: int = 8):
    """A helix as a POLYLINE, for feeding to `oct_cable` -- for when the coil must
    be PART OF the same solid as the run. Where it can stand alone, reach for
    `helix_cable` instead: 3 faces against this one's ~1200.

    A swept round profile along a helical wire is one solid and so does not risk
    the fuse above -- but it puts a curved cable in the middle of an octagonal
    run, and the two then meet in exactly the tangent boolean this module exists
    to avoid. Approximating the helix in segments keeps one section for the whole
    cable.

    THE POLYLINE CIRCUMSCRIBES the true helix: its vertices sit at
    r / cos(pi/per_turn), so the chord midpoints land exactly on r and no part of
    the path ever falls INSIDE it. Inscribing instead would have drawn the coil
    up to r*(1 - cos(pi/per_turn)) short of where the cable really runs -- 0.7 mm
    at 8 per turn on a 9 mm coil -- and understating a swept envelope is the one
    error this model cannot afford. Circumscribed, the error lands on the side of
    clearance, exactly as the octagonal section itself does.

    `per_turn` is a face-count knob, and a coarse one is fine BECAUSE of the
    above: a 7-turn coil costs ~900 faces at 6, ~1200 at 8, ~2000 at 16, against
    about 5 for a swept round profile. 8 is the default; raise it only where the
    coil's SHAPE (not its envelope) is what matters.
    """
    n = max(int(round(turns * per_turn)), 1)
    rc = r / _math.cos(_math.pi / per_turn)
    out = []
    for i in range(n + 1):
        f = i / float(n)
        a = 2.0 * _math.pi * turns * f
        out.append((cx + rc * _math.cos(a), cy + rc * _math.sin(a), z0 + (z1 - z0) * f))
    return out
