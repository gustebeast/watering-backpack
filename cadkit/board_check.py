"""Does the CAD actually render the board that was ROUTED?

    from cadkit.board_check import check
    bad = check("controller", my_assembly.controller_pcb(), BOARDS.load("controller"))

`solid` is whatever your project PLACES in its assembly for that board -- in any frame,
at any orientation -- and `geom` is the routed board read back (`cadkit/kicad_geom.py`
writes it, `cadkit.board_geom.Boards.load` reads it). Returns the number of
disagreements; 0 is a pass. Wire it into the board pipeline and the build gate.

WHAT IT CATCHES, and why nothing else does. DRC checks copper against the netlist; an
overlap gate checks solids against solids; neither compares the CAD's board with the
real one. So:

  * for every footprint it takes the centre of the part's F.Fab BODY, just above the
    board face, and asks whether the solid has material there -- a part that is missing,
    moved, or turned so its body lands elsewhere, fails;
  * it then probes just inside each END of that body, along its longer side, and
    reports a part whose body does not reach where the routed one does: SHIFTED or
    drawn SHORT. The centre probe alone passes a part that is anywhere within half its
    own length of the right place (the case: two connectors drawn butted end to end,
    0.5 and 0.8 mm off their pads, where the board has 1.2 mm between them -- "4 / 4
    present"). Reported, and counted only with `strict_ends=True`, because a body drawn
    to its real shape may honestly stop short of its F.Fab rectangle at the board face;
  * it reports a board drawn MIRRORED;
  * it compares the plate's CUTOUTS with the routed board's by count and area -- the
    probe above cannot see a wrong cutout, because a cutout is exactly where no part is.
    (The case that made this necessary: ten sensing slots emitted to Edge.Cuts as ONE
    rectangle spanning all of them, every other check green.)

NO FRAME BOOKKEEPING. Boards live wherever the assembly puts them -- centred on their own
origin, in world coordinates, standing on edge. This FINDS the pose: the plate is the
planar face whose bounding box matches the routed outline, its normal is the board's
down, and of the eight ways the board can lie in that plane it keeps the one where the
most parts land. The plate must be AXIS-ALIGNED: turn a board that stands on a diagonal
square before handing it over (that changes nothing this measures).
"""
from __future__ import annotations

import itertools

import cadquery as cq

from .board_geom import fp_name

# Bare-copper refs: flat pads with no body, nothing above the board to find.
NO_BODY_PREFIX = ("JP", "TP")

_AX = {"x": cq.Vector(1, 0, 0), "y": cq.Vector(0, 1, 0), "z": cq.Vector(0, 0, 1)}


def _plates(solid, w, l):
    """[(centre, outward normal, face)] of every flat face the size of the routed outline.

    PLURAL, because a plate has TWO such faces and only one is its underside; the caller
    tries each and keeps whichever the parts agree with."""
    found = []
    for f in solid.faces().vals():
        if f.geomType() != "PLANE":
            continue
        bb = f.BoundingBox()
        dims = sorted([bb.xlen, bb.ylen, bb.zlen])[1:]      # the two in-plane extents
        err = abs(dims[0] - min(w, l)) + abs(dims[1] - max(w, l))
        if err <= 0.5:
            # the face's BOX centre, not its centre of mass: a board with a mounting ear
            # is an L, and its mass centre sits millimetres off the frame the geom uses
            found.append((cq.Vector((bb.xmin + bb.xmax) / 2, (bb.ymin + bb.ymax) / 2,
                                    (bb.zmin + bb.zmax) / 2), f.normalAt(), f))
    if not found:
        # the CAD's plate is not the routed board's size at all -- report both, because
        # that IS the finding (a board that grew while its CAD did not)
        sizes = sorted({tuple(round(d, 2) for d in sorted([f.BoundingBox().xlen,
                        f.BoundingBox().ylen, f.BoundingBox().zlen])[1:])
                        for f in solid.faces().vals() if f.geomType() == "PLANE"},
                       key=lambda d: -d[0] * d[1])[:3]
        raise RuntimeError("the CAD's board is not the routed board: routed outline %.2f x "
                           "%.2f, largest flat faces in the CAD %s" % (w, l, sizes))
    return found


def _through_wires(plate, others, up):
    """The inner wires of `plate` that are CUTOUTS rather than parts sitting on it.

    The board solid is the laminate FUSED WITH every part body, so a connector standing
    on the plate face leaves its own footprint as an inner wire of that face --
    indistinguishable, by count, from a hole. A cutout goes THROUGH: it appears on BOTH
    plate faces at the same in-plane position AND THE SAME SIZE. Position alone is not
    enough -- a through-hole part's body on one face sits concentric with its tail slab
    on the other -- but a cutout is one prism through the laminate, so its two wires are
    the same shape, and a body and its tails are not.

    `others` may include the plate's own twin (a different Python object wrapping the same
    face): the through-thickness offset test below excludes it geometrically."""
    def _c(wr):
        bb = wr.BoundingBox()
        return cq.Vector((bb.xmin + bb.xmax) / 2, (bb.ymin + bb.ymax) / 2,
                         (bb.zmin + bb.zmax) / 2)

    def _s(wr):
        bb = wr.BoundingBox()
        return sorted((bb.xlen, bb.ylen, bb.zlen))[1:]
    opp = []
    for f in others:
        if abs(f.normalAt().dot(up)) > 0.9:
            opp.extend((_c(wr), _s(wr)) for wr in f.innerWires())
    out = []
    for wr in plate.innerWires():
        c, sz = _c(wr), _s(wr)
        for o, osz in opp:
            d = o - c
            if max(abs(p - q) for p, q in zip(sz, osz)) > 0.10:
                continue
            # in-plane offset ~0 (same hole) AND a real through-thickness offset
            if (d - up * d.dot(up)).Length < 0.20 and abs(d.dot(up)) > 0.5:
                out.append(wr)
                break
    return out


def _hole_check(wires, geom, verbose):
    """Do the plate's through-cutouts match the routed board's, by count and by area?"""
    routed = geom.get("holes", [])

    def _area(pts):
        return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1]
                       - pts[(i + 1) % len(pts)][0] * pts[i][1]
                       for i in range(len(pts)))) / 2.0
    cad_n = len(wires)
    cad_a = sum(abs(cq.Face.makeFromWires(wr).Area()) for wr in wires)
    routed_a = sum(_area(h) for h in routed)
    if cad_n != len(routed):
        if verbose:
            print("      CUTOUTS DISAGREE: the CAD plate has %d hole(s), the routed board "
                  "%d" % (cad_n, len(routed)))
        return 1
    if cad_a > 0 and abs(cad_a - routed_a) / max(cad_a, routed_a) > 0.05:
        if verbose:
            print("      CUTOUT AREA DISAGREES: CAD %.1f mm2, routed %.1f mm2 (%.0f%%)"
                  % (cad_a, routed_a, 100 * abs(cad_a - routed_a) / max(cad_a, routed_a)))
        return 1
    if verbose:
        print("%-13s %3d cutout(s) match, %.1f mm2 vs %.1f" % ("", cad_n, cad_a, routed_a))
    return 0


END_INSET = 0.30           # mm inside each end of a body's longer side: the end probes
END_MIN_LEN = 2.0          # ...on bodies at least this long; a 0603 has no ends to speak of


def _end_misses(shape, parts, c, u, v, up, t):
    """[(ref, name, which end, x, y)]: bodies that have material at their centre but not
    just inside an end of their longer side, in the pose (c, u, v, up) already chosen."""
    out = []
    for f in parts:
        x0, x1, y0, y1 = f["fab"]
        bx, by = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        lift = t + 0.15 if f["side"] == "F" else -0.15
        if not shape.isInside(c + u * bx + v * by + up * lift, 0.01):
            continue                       # already reported as MISSING
        along_x = (x1 - x0) >= (y1 - y0)
        if max(x1 - x0, y1 - y0) < END_MIN_LEN:
            continue
        ends = (((x0 + END_INSET, by), "-x"), ((x1 - END_INSET, by), "+x")) if along_x else (
            ((bx, y0 + END_INSET), "-y"), ((bx, y1 - END_INSET), "+y"))
        for (px, py), which in ends:
            if not shape.isInside(c + u * px + v * py + up * lift, 0.01):
                out.append((f["ref"], fp_name(f["fpid"]), which, px, py))
    return out


def check(board, solid, geom, verbose=True, no_body_prefix=NO_BODY_PREFIX,
          strict_ends=False, ends_ok=None):
    """Number of disagreements between `solid` (the CAD's board, any pose) and `geom`
    (the routed board): missing parts + 1 if mirrored + cutout mismatches (+ bodies that
    stop short of a routed end, with `strict_ends`). Raises RuntimeError if no face of
    the solid is the routed outline's size.

    `ends_ok` is {ref: reason} for the bodies drawn to their real shape that honestly do
    not reach the board face at an end of their fab rectangle (a jack's round bushing).
    Their end probes are printed with the reason and not counted. A ref named there that
    no longer misses an end IS counted: a stale declaration."""
    w, l = geom["outline_mm"]
    t = geom["thickness_mm"]
    shape = solid.val() if hasattr(solid, "val") else solid
    wp = cq.Workplane(obj=shape)
    parts = [f for f in geom["footprints"]
             if f["fab"] and not f["ref"].startswith(tuple(no_body_prefix))]
    plates = _plates(wp, w, l)
    best = None
    for c, down, plate in plates:
        up = cq.Vector(-down.x, -down.y, -down.z)
        inplane = [q for q in _AX.values() if abs(q.dot(up)) < 0.5]
        for a, b in itertools.permutations(inplane, 2):
            for sa, sb in itertools.product((1, -1), (1, -1)):
                u, v = a * sa, b * sb
                mirrored = u.cross(v).dot(up) < 0
                misses = []
                for f in parts:
                    x0, x1, y0, y1 = f["fab"]
                    bx, by = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                    lift = t + 0.15 if f["side"] == "F" else -0.15
                    if not shape.isInside(c + u * bx + v * by + up * lift, 0.01):
                        misses.append((f["ref"], fp_name(f["fpid"]), bx, by))
                # fewest misses wins; on a tie the UNmirrored pose does, or a board that
                # renders perfectly could be reported mirrored because that pose came first
                key = (len(misses), mirrored)
                if best is None or key < (len(best[0]), best[1]):
                    best = (misses, mirrored, plate, (c, u, v, up))
    misses, mirrored, plate, pose = best
    short = _end_misses(shape, parts, *pose, t)
    ends_ok = dict(ends_ok or {})
    declared = [s for s in short if s[0] in ends_ok]
    short = [s for s in short if s[0] not in ends_ok]
    stale = sorted(set(ends_ok) - {s[0] for s in declared})
    faces = [pl for _c, _d, pl in plates]
    holes = _hole_check(_through_wires(plate, faces, plate.normalAt()), geom, verbose)
    if verbose:
        print("%-13s %3d / %3d routed parts present in the CAD%s"
              % (board, len(parts) - len(misses), len(parts),
                 "   !! MIRRORED" if mirrored else ""))
        for ref, name, bx, by in misses:
            print("      MISSING %-6s %-44s routed at (%.2f, %.2f)"
                  % (ref, name[:44], bx, by))
        for ref, name, which, px, py in short:
            print("      SHORT OR SHIFTED %-6s %-36s no body %.2f mm inside its %s end "
                  "(%.2f, %.2f)" % (ref, name[:36], END_INSET, which, px, py))
        for ref, name, which, px, py in declared:
            print("      declared: %-6s stops short of its %s end -- %s"
                  % (ref, which, ends_ok[ref]))
        for ref in stale:
            print("      STALE ends_ok: %-6s reaches both its ends, or is not on the board"
                  % ref)
        if short and not strict_ends:
            print("      (%d end probe(s) found no body: reported, not counted)" % len(short))
    return (len(misses) + (1 if mirrored else 0) + holes + len(stale)
            + (len(short) if strict_ends else 0))
