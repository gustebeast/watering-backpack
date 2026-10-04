"""Watering Backpack — build entry point.

  py -3.12 -m src.build     # export every printed STEP, build the assembly,
                            # run the gates, refresh the FreeCAD viewer

This builds **v2**. It used to build v1 and overwrite `assembly.step` with it,
which meant the project's own documented command produced the wrong design and
ran none of the gates.

WHAT IS PRINTED NOW
-------------------
Two parts. The frame is lumber (`src/lumber_frame.py` prints its cut list) and
the battery dock is fused into the housing rather than printed separately:

  v2_housing      battery mount + PCB case, one piece
  v2_housing_lid  the cover over the board

`joystick_mount` and the two hose clamps carry over from v1 unchanged.

THE GATES RUN HERE, NOT AFTER
-----------------------------
`cadkit/AGENTS.md`: "fold the scan into the build, which already has the
components in memory ... making a whole-tree gate cost ~+15 s instead of
~+6 min". A standalone `tools.check_overlaps` run pays for a COMPLETE second
model build before it scans anything, so the build does the scan itself.
"""
from __future__ import annotations

import pathlib
import sys

import cadquery as cq

from cadkit.cq_colors import color
from cadkit.freecad import show
from cadkit.step_export import export_step, print_pose

from . import housing as H
from . import lumber_frame as L
from . import plumbing as P
from . import pump_frame as F
from .dual_clamp import dual_clamp_19, dual_clamp_23
from .helpers import bump_build_counter
from .joystick_mount import joystick_mount

OUT = pathlib.Path(__file__).resolve().parent.parent
BED = 255.0

# The Makita pack as an ENVELOPE, not a model — same standing as ELBOW_*. The
# published body is 116 (slide) x 75 x 65.6, it seats with its rails in the
# dock's 7 mm channel, and the slide axis runs vertical. It is here because it
# is the largest unmodelled mass in the design and it hangs off the side; what
# this checks is CLEARANCE, not fit. Fit is the dock's job and v1 validated it.
BATT_L, BATT_W, BATT_D = 116.0, 75.0, 65.6
BATT_CHANNEL = 7.0                       # how deep the rails sit in the dock


def battery_envelope() -> cq.Workplane:
    dock = H._dock_placed().val().BoundingBox()
    x_face = dock.xmin + BATT_CHANNEL     # rails sit this far into the dock
    y_c = (dock.ymin + dock.ymax) / 2.0
    return (cq.Workplane("YZ").workplane(offset=x_face - BATT_D)
            .center(y_c, dock.zmin + BATT_L / 2.0)
            .rect(BATT_W, BATT_L).extrude(BATT_D))


def battery_sweep():
    """The corridor the pack travels to come OFF the dock, and how far.

    The seated envelope is not enough and that is how this was missed: the
    battery was weighed as a static box in its seated position, which says
    nothing about whether you can get it out. The dock's rails are 93 mm long,
    so the pack has to rise its full engagement before it is free, and the deck
    sits directly above it. It hit the deck plank after 43.5 of those 93 mm.

    Only the part ABOVE the seated top is checked. The seated part of the sweep
    overlaps the dock by design -- that is the whole point of a dock.
    """
    dock = H._dock_placed().val().BoundingBox()
    b = battery_envelope().val().BoundingBox()
    travel = dock.zmax + BATT_L - b.zmax
    sweep = (cq.Workplane("XY")
             .center((b.xmin + b.xmax) / 2.0, (b.ymin + b.ymax) / 2.0)
             .rect(b.xlen, b.ylen).extrude(travel).translate((0, 0, b.zmax)))
    return travel, sweep


def printed_parts():
    return (("v2_housing", H.housing(), H.PRINT_ROT["v2_housing"]),
            ("v2_housing_lid", H.lid(), H.PRINT_ROT["v2_housing_lid"]),
            ("joystick_mount", joystick_mount, None),
            ("dual_clamp_23", dual_clamp_23, None),
            ("dual_clamp_19", dual_clamp_19, None))


def components():
    """Everything the overlap gate weighs, in one place so the build and
    `tools/check_overlaps.py` cannot disagree about what the design IS."""
    comps = [("housing", H.housing()), ("housing_lid", H.lid()),
             ("pcb", H.pcb_solid()), ("wood", L.frame()),
             ("battery", battery_envelope()),
             ("pump_a", F._pump_placed(-1)), ("pump_b", F._pump_placed(+1)),
             ("fittings", F._elbows())]
    for name, pts in P.routes():
        comps.append((name, P.run(pts)))
    return comps


def intended(a, b):
    pair = {a, b}
    if "fittings" in pair:
        other = (pair - {"fittings"}).pop()
        return other.startswith(("pump_", "tank_", "green_"))
    if pair == {"pcb", "housing"}:          # board on its standoff bosses
        return True
    if pair == {"housing", "wood"}:         # bolted flat to the posts
        return True
    if pair == {"housing", "housing_lid"}:  # lid closed on its pillars
        return True
    if pair == {"battery", "housing"}:      # the pack seated in its dock
        return True
    if all(n.startswith(("tank_", "green_")) for n in pair):
        return True
    return False


def main() -> int:
    build_n = bump_build_counter()

    print("=== printed parts ===")
    oversize = 0
    for name, part, rot in printed_parts():
        posed = print_pose(part, rot)
        export_step(posed, str(OUT / (name + ".step")))
        bb = posed.val().BoundingBox()
        fits = max(bb.xlen, bb.ylen, bb.zlen) <= BED
        oversize += 0 if fits else 1
        print("  %-16s %6.1f x %6.1f x %6.1f mm  %s"
              % (name, bb.xlen, bb.ylen, bb.zlen,
                 "" if fits else "*** OVER THE %.0f BED ***" % BED))

    print("\n=== lumber cut list (38x38 beam, 137x20 plank) ===")
    for (nm, length), n in L.cut_list():
        print("  %2d x  %-12s %6.1f mm" % (n, nm, length))
    print("  + " + L.notch_note())

    comps = components()
    asm = cq.Assembly()
    for i, (nm, _len, solid) in enumerate(L.pieces()):
        tint = "#8B5A2B" if nm.startswith("plank") else "#A0724A"
        asm.add(solid, name="%s_%d" % (nm, i), color=color(tint))
    tints = {"housing": "#6a8fb5", "housing_lid": "#8fb56a", "pcb": "#2f7d4f",
             "battery": "#d08a3e", "pump_a": "slategray", "pump_b": "#5a6b7a",
             "fittings": "#c8a24a"}
    for nm, solid in comps:
        if nm == "wood":
            continue
        c = tints.get(nm, "#b03030" if nm.startswith("tank") else "#30a050")
        alpha = 0.35 if nm == "battery" else 0.85 if "_" in nm else 1.0
        asm.add(solid, name=nm, color=color(c, alpha=alpha))
    asm.add(L.tank(), name="tank_viz", color=color("#9fd4e8", alpha=0.35))
    try:
        counter = (cq.Workplane("XZ").center(0, L.DECK_Z + 520)
                   .text(str(build_n), 30, 6))
        asm.add(counter, name="build_counter", color=color("#F0A878"))
    except Exception:                                              # noqa: BLE001
        pass

    out = str(OUT / "assembly.step")
    asm.save(out, mode="default")

    print("\n=== overlap gate ===")
    from cadkit import overlap_check
    bad = overlap_check.run([(n, s.val()) for n, s in comps], intended)

    print("\n=== battery access gate ===")
    travel, sweep = battery_sweep()
    by_name = dict(comps)
    blocked = 0
    for nm in ("wood", "housing"):
        i = sweep.intersect(by_name[nm])
        v = i.val().Volume() if i.val() is not None else 0.0
        blocked += 0 if v <= 1.0 else 1
        print("  %-8s %s" % (nm, "clear" if v <= 1.0 else
                             "*** BLOCKS THE PACK, %.0f mm3 ***" % v))
    i = sweep.intersect(L.tank())
    v = i.val().Volume() if i.val() is not None else 0.0
    blocked += 0 if v <= 1.0 else 1
    print("  %-8s %s" % ("tank", "clear" if v <= 1.0 else
                         "*** BLOCKS THE PACK, %.0f mm3 ***" % v))
    print("  the pack needs %.0f mm of lift to clear its rails" % travel)

    b = asm.toCompound().BoundingBox()
    print("\nwhole assembly %.0f x %.0f x %.0f mm"
          % (b.xlen, b.ylen, b.zlen))
    print("Wrote %s  [build #%d]" % (out, build_n))
    show(out)
    return bad + oversize + blocked


if __name__ == "__main__":
    sys.exit(main())
