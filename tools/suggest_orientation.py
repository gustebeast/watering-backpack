# -*- coding: utf-8 -*-
"""Suggest a bed face for a part that has never declared one.

A MIGRATION AID, not an authority. cadkit requires every printed part to
declare a `PrintOrientation` (see cadkit.orientation), and projects that
predate that requirement have parts whose bed face nobody ever wrote down.
This measures the six axis-aligned candidates and ranks them, so the
declaration those projects get is a MEASUREMENT rather than a coin flip.

    from cadkit.tools.suggest_orientation import suggest, report
    print(report({"cup": cup_solid, "lid": lid_solid}))

WHAT IT MEASURES, per candidate, in that candidate's posed frame:

  overhang area   downward-facing material steeper than 45 deg off
                  horizontal. Weighted heaviest: it is the thing that
                  actually fails a print.
  bed area        footprint on the plate. A candidate with essentially NO
                  footprint is DISQUALIFIED, not merely penalised: a part
                  touching the plate over a bead or two cannot print at all.
                  That case is not hypothetical — a sphere laid on its side
                  measures the LEAST overhang area of any orientation while
                  touching the plate at a point, so cost alone ranked an
                  unprintable candidate first (cat-nip ball).
  aspect          height / min(footprint width) — the tipping/wobble risk
                  that made a TPU pin print as a 5.9:1 tower (#1070).

IT TESSELLATES rather than reading face normals. A `normalAt()` with no
argument samples ONE point, which is meaningless on a curved face: the first
version of this tool read each half of a spherical cat-nip ball as a single
flat face with one normal and reported a sphere as having NO overhangs. Every
measurement here is therefore per-triangle.

It also does NOT apply the overhang gate's bridge-span filter (a span over one
bead). That filter decides whether ONE orientation passes; this tool RANKS
six, so counting every unsupported triangle is both symmetric across the
candidates and the more conservative way round. Run the project's own overhang
gate on the orientation you settle on — that is the thing with authority.

WHAT IT CANNOT KNOW, which is exactly why what it produces is
`confirmed=False`: which faces must be cosmetic, which direction the part is
loaded in (layer adhesion is the weak axis), whether a face mates with
something, whether supports are acceptable here, and whether the part is
meant to print alongside others. A human or an agent that has studied the
part settles those and sets `confirmed=True`.

Self-test: ``python -m cadkit.tools.suggest_orientation``.
"""

import math

import cadquery as cq

from ..orientation import PrintOrientation
from ..step_export import print_pose

__all__ = ["CANDIDATES", "measure", "suggest", "report"]

# the six axis-aligned bed faces, in print_pose's own vocabulary
CANDIDATES = (
    (None, "models as printed (modelled -z face on the bed)"),
    ("flip", "modelled TOP face on the bed"),
    (((1, 0, 0), -90), "stands on its +y face"),
    (((1, 0, 0), 90), "stands on its -y face"),
    (((0, 1, 0), 90), "stands on its -x face"),
    (((0, 1, 0), -90), "stands on its +x face"),
)

ANGLE_LIMIT = 46.0      # deg off horizontal — the self-supporting limit
                        # (46 not 45: an exactly-45 face is designed-to, so
                        # the gate's own tolerance is used here too)
BED_MIN_BEADS = 4.0     # a footprint under this many bead-squares is no
                        # footprint: there is nothing for a first layer to be
NO_FOOTPRINT = 1.0e4    # cost for that — a disqualification, not a penalty


TESS_TOL = 0.1          # mm — tessellation chord tolerance
BED_TOL = 0.2           # mm — a triangle this close to z=0 is ON the plate


def _triangles(shape, tol=TESS_TOL):
    """(unit normal z, area, min z, max z) per tessellated triangle.

    Per-triangle, NOT per-face: one `normalAt()` on a sphere or cylinder
    describes a single point of it and nothing else (see the docstring).
    """
    verts, tris = shape.tessellate(tol)
    for ia, ib, ic in tris:
        a, b, c = verts[ia], verts[ib], verts[ic]
        n = (b - a).cross(c - a)
        twice = n.Length
        if twice < 1e-12:                   # degenerate sliver
            continue
        yield n.z / twice, twice / 2.0, min(a.z, b.z, c.z), max(a.z, b.z, c.z)


def measure(part, rot, nozzle=0.8):
    """`part` posed by `rot`: (overhang_area, bed_area, aspect, height)."""
    posed = print_pose(part, rot)
    bb = posed.val().BoundingBox()
    z_bed = bb.zmin
    over = bed = 0.0
    for nz, area, zmin, zmax in _triangles(posed.val()):
        if nz < -0.999 and zmax - z_bed < BED_TOL:
            bed += area                      # footprint, not an overhang
            continue
        if nz >= 0.0:
            continue
        angle = math.degrees(math.acos(min(1.0, -nz)))       # off horizontal
        if angle < ANGLE_LIMIT:
            over += area
    foot = min(bb.xlen, bb.ylen)
    aspect = bb.zlen / foot if foot > 1e-9 else float("inf")
    return over, bed, aspect, bb.zlen


def suggest(part, nozzle=0.8):
    """[(score, rot, why, overhang, bed, aspect)] best first.

    The score is a cost: overhang area dominates (a failed bridge is a
    failed print), then tipping risk, then a mild preference for a bigger
    footprint. The numbers are in the report so the ranking can be argued
    with — that is the point of printing them.
    """
    rows = []
    bed_min = BED_MIN_BEADS * nozzle * nozzle
    for rot, why in CANDIDATES:
        over, bed, aspect, h = measure(part, rot, nozzle)
        cost = over * 10.0 + max(0.0, aspect - 2.0) ** 2 * 5.0 - bed * 0.05
        if bed < bed_min:
            cost += NO_FOOTPRINT
            why += " [NO FOOTPRINT: %.2f mm2 on the plate]" % bed
        rows.append((cost, rot, why, over, bed, aspect))
    rows.sort(key=lambda r: r[0])
    return rows


def report(parts, nozzle=0.8):
    """A text table plus a paste-ready PRINT_ORIENTATION block.

    `parts` is {name: solid-or-Workplane}. Every suggestion comes out
    `confirmed=False`, because this tool measured the geometry and nothing
    else — see the module docstring for what it cannot know.
    """
    lines, decl = [], []
    for name in sorted(parts):
        rows = suggest(parts[name], nozzle)
        lines.append("%s" % name)
        for i, (cost, rot, why, over, bed, aspect) in enumerate(rows):
            lines.append("  %s %-34s cost %8.1f  overhang %7.2f mm2  "
                         "bed %7.1f mm2  aspect %5.2f"
                         % ("->" if i == 0 else "  ", repr(rot), cost, over,
                            bed, aspect))
        _c, rot, why, over, bed, aspect = rows[0]
        runner = rows[1][0] - rows[0][0]
        decl.append('    %-18s PO(%s,\n%s"%s; %s",\n%sconfirmed=False),'
                    % (('"%s":' % name), repr(rot), " " * 24,
                       why,
                       ("no overhang, aspect %.1f" % aspect) if over < 1e-9
                       else ("%.1f mm2 of unsupported face, aspect %.1f"
                             % (over, aspect)),
                       " " * 24))
        if runner < 1.0:
            decl.append("    # ^ CLOSE CALL: the runner-up %s scores within "
                        "%.2f — this one especially needs a human."
                        % (repr(rows[1][1]), runner))
    out = "\n".join(lines)
    out += ("\n\nPRINT_ORIENTATION = {   # MEASURED, NOT CONFIRMED — see "
            "cadkit.tools.suggest_orientation\n" + "\n".join(decl) + "\n}\n")
    return out


if __name__ == "__main__":
    # a plate with a deep unsupported shelf: printing it shelf-down must
    # cost more than printing it shelf-up.
    plate = cq.Workplane("XY").box(40.0, 20.0, 4.0, centered=(True, True, False))
    shelf = (plate.faces(">Z").workplane().center(0.0, 0.0)
             .rect(40.0, 4.0).extrude(10.0))
    part = shelf.union(cq.Workplane("XY").workplane(offset=10.0)
                       .center(12.0, 0.0).rect(10.0, 16.0).extrude(4.0))
    rows = suggest(part)
    # the OVERHANG must be measured, and measured right: printed as modelled,
    # the raised 10x16 block is unsupported except where the 4-wide shelf
    # passes under it -> 160 - 40 = 120 mm2.
    as_modelled = [r for r in rows if r[1] is None][0]
    assert abs(as_modelled[3] - 120.0) < 1e-6, as_modelled
    # 'flip' buries the whole shelf+block underside: it must be the worst
    assert rows[-1][1] == "flip", rows[-1]
    assert rows[0][0] < rows[-1][0]

    # A SPHERE HAS NO GOOD SIDE, and every orientation must say so. The
    # face-normal version of this tool reported a ball as overhang-FREE,
    # because one normalAt() on a sphere is one point of it (cat-nip ball).
    ball = cq.Workplane("XY").sphere(10.0)
    brows = suggest(ball)
    # the unsupported region is the cap within ANGLE_LIMIT of straight down:
    # 2*pi*R^2*(1-cos46) = 191.8 mm2. Checked against the closed form, since
    # a number that merely looks plausible is how the sphere bug survived.
    want = 2.0 * math.pi * 100.0 * (1.0 - math.cos(math.radians(ANGLE_LIMIT)))
    for r in brows:
        assert abs(r[3] - want) / want < 0.02,             "sphere cap: got %.2f, want %.2f, for %r" % (r[3], want, r[1])
    spread = max(r[3] for r in brows) - min(r[3] for r in brows)
    assert spread / want < 0.01,         "a sphere is isotropic; %.2f mm2 of spread is more than meshing" % spread
    # and a bare ball touches the plate at a POINT in every orientation, so
    # every candidate must be disqualified rather than one of them winning
    assert all(r[0] > NO_FOOTPRINT for r in brows),         "a ball has no footprint in any orientation; none should look fine"

    # A DOME ON A FLAT RIM must print rim-down, and the thing that says so is
    # the FOOTPRINT: on its side it balances on a point. This is what the
    # cat-nip ball's hollow threaded halves exposed — there, laid on its side
    # measured the LEAST unsupported area of all six candidates, so cost
    # without a footprint rule ranked an unprintable orientation first.
    dome = (cq.Workplane("XY").sphere(15.0)
            .intersect(cq.Workplane("XY").box(40.0, 40.0, 15.0,
                                              centered=(True, True, False))))
    drows = suggest(dome)
    assert drows[0][1] is None, "rim-down must win; %r did" % (drows[0][1],)
    for r in drows:
        if r[1] in (((0, 1, 0), 90), ((0, 1, 0), -90),
                    ((1, 0, 0), 90), ((1, 0, 0), -90)):
            assert r[0] > NO_FOOTPRINT,                 "a dome on its side balances on a point; %r scored %.1f" % (
                    r[1], r[0])
            assert "NO FOOTPRINT" in r[2], r[2]

    # ASPECT, in isolation — a plain slab has no overhang in ANY orientation,
    # so nothing but tipping risk can decide, and standing it on end must lose.
    slab = cq.Workplane("XY").box(40.0, 20.0, 4.0,
                                  centered=(True, True, False))
    srows = suggest(slab)
    assert all(abs(r[3]) < 1e-9 for r in srows), "a slab has no overhangs"
    assert srows[0][1] in (None, "flip"), srows[0]
    assert srows[0][5] < 1.0 and srows[-1][5] > 2.0, (srows[0], srows[-1])

    # a measurement must agree with print_pose: the pose drops to z=0
    for rot, _why in CANDIDATES:
        assert abs(print_pose(part, rot).val().BoundingBox().zmin) < 1e-9

    txt = report({"demo": part})
    assert "confirmed=False" in txt and "PRINT_ORIENTATION" in txt
    print(txt)
    print("cadkit.tools.suggest_orientation self-test OK")
