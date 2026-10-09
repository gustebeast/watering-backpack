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

  overhang area   downward faces steeper than 45 deg off horizontal whose
                  bridge span (2*area/perimeter) exceeds one bead — the
                  project rule the overhang gate enforces. Weighted
                  heaviest: it is the thing that actually fails a print.
  bed area        footprint at z=0. More is better — adhesion, and it is
                  what stops a part walking off the plate.
  aspect          height / min(footprint width) — the tipping/wobble risk
                  that made a TPU pin print as a 5.9:1 tower (#1070).

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


def _span(face):
    per = sum(e.Length() for e in face.Edges())
    return 2.0 * face.Area() / per if per > 1e-9 else 0.0


def measure(part, rot, nozzle=0.8):
    """`part` posed by `rot`: (overhang_area, bed_area, aspect, height)."""
    posed = print_pose(part, rot)
    bb = posed.val().BoundingBox()
    z_bed = bb.zmin
    over = bed = 0.0
    for f in posed.val().Faces():
        try:
            n = f.normalAt()
        except Exception:                                   # noqa: BLE001
            continue
        nz = n.z
        # a face sitting ON the bed is the footprint, not an overhang
        fb = f.BoundingBox()
        if nz < -0.999 and abs(fb.zmax - z_bed) < 1e-6:
            bed += f.Area()
            continue
        if nz >= 0.0:
            continue
        angle = math.degrees(math.acos(min(1.0, -nz)))       # off horizontal
        if angle < ANGLE_LIMIT and _span(f) > nozzle:
            over += f.Area()
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
    for rot, why in CANDIDATES:
        over, bed, aspect, h = measure(part, rot, nozzle)
        cost = over * 10.0 + max(0.0, aspect - 2.0) ** 2 * 5.0 - bed * 0.05
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
    # the OVERHANG must be measured, and measured right: printed as modelled
    # the raised 10x16 block is unsupported except where the 4-wide shelf
    # passes under it, so 160 - 40 = 120 mm2.
    as_modelled = [r for r in rows if r[1] is None][0]
    assert abs(as_modelled[3] - 120.0) < 1e-6, as_modelled
    # 'flip' buries the whole shelf+block underside: it must be the worst
    assert rows[-1][1] == "flip", rows[-1]
    assert rows[0][0] < rows[-1][0]

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
