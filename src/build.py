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
from .dual_clamp import dual_clamp_19
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


def _swept(solid, direction, travel, steps=20):
    """The volume a part passes through on its way in or out.

    A seated part proves only that it FITS where it ends up. The battery gate
    below exists because a dock the pack could not be lifted out of passed
    every static check in this file; these two are the same question asked of
    the lid and the contact block.
    """
    dx, dy, dz = direction
    sweep = None
    for i in range(steps + 1):
        f = travel * i / float(steps)
        s = solid.translate((dx * f, dy * f, dz * f))
        sweep = s if sweep is None else sweep.union(s)
    return sweep


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
            # dual_clamp_23 retired: it gripped a 23 mm VALVE body and
            # DESIGN_V2 section 1 has no reversing valve. See src/dual_clamp.py.
            # line_filter_screen retired 2026-10-05: the owner decided the
            # green-line filter is two BOUGHT Seaflo 51S01 strainers at the
            # two tees, not a printed screen -- see DESIGN_V2 section 4 and
            # WORK_V2_PUNCHLIST findings 13/13a. src/line_filter.py and the
            # test_screen_slice coupon went with it; git has them.
            ("dual_clamp_19", dual_clamp_19, None))


def components():
    """Everything the overlap gate weighs, in one place so the build and
    `tools/check_overlaps.py` cannot disagree about what the design IS."""
    comps = [("housing", H.housing()), ("housing_lid", H.lid()),
             ("pcb", H.pcb_solid()), ("wood", L.frame()),
             ("battery", battery_envelope()),
             ("pump_a", F._pump_placed(-1)), ("pump_b", F._pump_placed(+1)),
             ("fittings", F._elbows())]
    # The Makita contact block, seated in the pocket the housing reopens for it.
    # A bought part in a printed pocket is exactly the pair worth weighing: the
    # pocket came from v1 and the back plate that seals it came from v2.
    term = H.terminal_placed()
    if term is not None:
        comps.append(("terminal", term))
    # The screw and its heat-set insert, drawn by the same ScrewJoint that cuts
    # the hole -- cadkit.fasteners.ScrewJoint.dummies(). They were never drawn,
    # so nothing ever checked that the insert fits its pocket or that the screw
    # reaches the insert through the board's own clearance hole. Both are now
    # weighed with everything else.
    for i, sj in enumerate(H.pcb_screws()):
        comps += sj.dummies("pcb_screw_%d" % i, "pcb_insert_%d" % i)
    for name, pts in P.routes():
        comps.append((name, P.run(pts)))
    return comps


def intended(a, b):
    pair = {a, b}
    if "fittings" in pair:
        # A BLANKET rule, and it is only safe because tools/check_plumbing.py
        # now puts a MEASURED ceiling on every hose-to-fitting pair. It did not,
        # and a hose drawn curving through 45 mm of rigid elbow -- 9962 mm3,
        # sixty times its neighbours -- sat here unremarked. This predicate only
        # gets names, never volumes, so the size has to be checked there.
        other = (pair - {"fittings"}).pop()
        return other.startswith(("pump_", "tank_", "green_"))
    # Measured, so a number that moves is visible rather than absorbed. An entry
    # here is a claim that two solids SHOULD interpenetrate; three former ones
    # were measuring 0.0 mm3, which means they were not whitelisting anything --
    # they were only standing ready to hide the first real clash that appeared.
    # housing<->wood (bolted flat to the posts), housing<->housing_lid and
    # housing<->terminal are all face contact, so they were dropped and the gate
    # now catches them if they ever stop being zero.
    # pcb <-> housing was here, "board on its standoff bosses, 12.5 mm3". It
    # measures 0.00 now: the 12.5 was the board sitting 3.4 mm off those bosses
    # with its lead tails in them, because pose_board was centring a bounding
    # box that included the tails. Seated properly it touches and does not
    # interpenetrate, so the entry is gone and the gate watches it instead.
    if pair == {"battery", "housing"}:      # the pack seated in its dock, 12528
        return True
    if pair == {"battery", "terminal"}:
        # The contact blades engaged in the pack -- the point of the connector,
        # and the same kind of reading as pump x fitting's thread engagement.
        # references/makita_battery.step is a solid ENVELOPE with no contact
        # cavities modelled, so blades that are correctly inside the pack have
        # nowhere to be except inside that solid. Measured 1762.7 mm3 as ten
        # separate bodies at 3.45 mm penetration, spread over the whole contact
        # field -- a body clash would be one lump, not ten.
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
    print("  + " + L.floor_note())

    comps = components()
    asm = cq.Assembly()
    for i, (nm, _len, solid) in enumerate(L.pieces()):
        tint = "#8B5A2B" if nm.startswith("plank") else "#A0724A"
        asm.add(solid, name="%s_%d" % (nm, i), color=color(tint))
    tints = {"housing": "#6a8fb5", "housing_lid": "#8fb56a", "pcb": "#2f7d4f",
             "pcb_screw_0": "#c0c6cc", "pcb_insert_0": "#b08d57",
             "battery": "#d08a3e", "pump_a": "slategray", "pump_b": "#5a6b7a",
             "fittings": "#c8a24a"}
    # ⚠ SEE-THROUGH IS DECLARED, NOT INFERRED FROM THE NAME. The rule here used
    # to be `0.35 if battery else 0.85 if "_" in nm else 1.0`, and an underscore
    # in a name is not a reason to be able to see through something. It caught
    # housing_lid -- so the one part whose whole job is to CLOSE the bay was
    # drawn translucent, and every screenshot of the board was a screenshot
    # taken through it -- along with the pumps, the PCB screw and its insert,
    # none of which anyone had asked to be transparent either.
    #
    # Two things are see-through on purpose, and both are so you can check a
    # fit that is otherwise hidden: the battery against its dock, and the tank
    # against the frame below it. Everything else is solid.
    SEE_THROUGH = {
        "battery": 0.35,        # the dock, the contact block and the lift path
                                # are all behind it
    }
    for nm, solid in comps:
        if nm == "wood":
            continue
        c = tints.get(nm, "#b03030" if nm.startswith("tank") else "#30a050")
        asm.add(solid, name=nm, color=color(c, alpha=SEE_THROUGH.get(nm, 1.0)))
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

    # Same question for the two parts that go in and out along X. The lid is
    # retained by a tab that reaches 28.5 mm inboard to the wood screw, and the
    # contact block seats behind flange lips -- both are shapes that can fit
    # where they end up and still be impossible to get there.
    print("\n=== install/removal gate ===")
    housing_solid = by_name["housing"]
    for nm, solid, direction, travel_mm, what in (
            ("lid", H.lid(), (-1.0, 0.0, 0.0), 60.0, "lifts off outboard"),
            ("terminal", H.terminal_placed(), (1.0, 0.0, 0.0), 40.0,
             "enters from the rear")):
        if solid is None:
            continue
        seated = housing_solid.intersect(solid)
        seated_v = seated.val().Volume() if seated.val() is not None else 0.0
        sw = _swept(solid, direction, travel_mm)
        i = sw.intersect(housing_solid)
        v = i.val().Volume() if i.val() is not None else 0.0
        # the swept volume may not clash any worse than the seated part does
        extra = v - seated_v
        blocked += 0 if extra <= 1.0 else 1
        print("  %-9s %-20s over %2.0f mm: %s"
              % (nm, what, travel_mm,
                 "clear" if extra <= 1.0 else
                 "*** BLOCKED, %.0f mm3 beyond seated ***" % extra))

    # The pumps are the heaviest moving thing on the pack and they hang off
    # eight M4s. Until the floor went in they bolted to nothing at all, so the
    # claim worth re-checking every build is not "a floor exists" but "every
    # bolt still passes through wood, and the feet still land on it".
    print("\n=== pump mount gate ===")
    floor = None
    for nm, _ln, solid in L.pieces():
        if nm == "plank_floor":
            floor = solid if floor is None else floor.union(solid)
    if floor is None:
        print("  *** NO FLOOR: the pumps have nothing to bolt to ***")
        blocked += 1
    else:
        ftop = floor.val().BoundingBox().zmax
        bolts = F.pump_bolt_xy()
        open_holes = seated = 0
        for bx, by in bolts:
            hole = (cq.Workplane("XY").workplane(offset=ftop - L.PLANK_T)
                    .center(bx, by).circle(1.5).extrude(L.PLANK_T))
            ring = (cq.Workplane("XY").workplane(offset=ftop - L.PLANK_T)
                    .center(bx + 4.0, by).circle(1.0).extrude(L.PLANK_T))
            if floor.intersect(hole).val().Volume() < 0.01:
                open_holes += 1
            if floor.intersect(ring).val().Volume() > 1.0:
                seated += 1
        gaps = [F._pump_placed(s).val().BoundingBox().zmin - ftop for s in (-1, 1)]
        ok = (open_holes == len(bolts) and seated == len(bolts)
              and all(abs(g) < 0.01 for g in gaps))
        blocked += 0 if ok else 1
        print("  %d/%d bolt holes open, %d/%d land in wood, feet-to-floor gap "
              "%s mm   %s" % (open_holes, len(bolts), seated, len(bolts),
                              "/".join("%.2f" % g for g in gaps),
                              "" if ok else "*** THE PUMPS ARE NOT MOUNTED ***"))

    # Is the board WHERE ITS OWN MOUNTING HOLES ARE? Nothing asked this, and
    # the answer was no on both axes at once: pose_board centred the solid's
    # BOUNDING BOX, so the ESP32's 4.12 mm antenna overhang pushed the laminate
    # 2.06 mm off the drilled holes in Y, and the 3.4 mm lead tails floated it
    # 3.4 mm clear of the bosses in X. Neither is an overlap -- one is a shift
    # and one is a GAP -- and the routed-board check below compares the solid
    # to the routed board in the BOARD's frame, where both agree perfectly.
    #
    # Two probes per hole, on the two things a seated board must be true of:
    #   THROUGH  a screw-sized bore on the hole's axis must meet no laminate;
    #   SEATED   the same bore 6 mm away, still on the Ø10 boss, must be solid
    #            laminate over the board's thickness starting at BOARD_X0.
    print("")
    print("=== board seating gate ===")
    board = by_name["pcb"]
    probe_d, seat_off = 3.0, 6.0
    full = 3.14159265 * (probe_d / 2.0) ** 2 * H.BOARD_T
    missed = blocked_holes = 0
    for hy, hz in H._hole_points():
        thru = (cq.Workplane("YZ").workplane(offset=H.WALL_X)
                .center(hy, hz).circle(probe_d / 2.0)
                .extrude(abs(H.WALL_X - H.FLOOR_X)))
        v = thru.intersect(board)
        blocked_holes += 0 if (v.val() is None or v.val().Volume() < 1.0) else 1
        # INBOARD of the hole, never outboard: the holes sit 6 mm from the
        # board's edge, so a fixed +Z offset walks the top pair off the
        # laminate and reports a seating failure that is the probe's fault.
        inward = -seat_off if hz > H.PCB_Z_C else seat_off
        seat = (cq.Workplane("YZ").workplane(offset=H.BOARD_X1)
                .center(hy, hz + inward).circle(probe_d / 2.0)
                .extrude(H.BOARD_T))
        v = seat.intersect(board)
        got = v.val().Volume() if v.val() is not None else 0.0
        missed += 0 if got >= 0.95 * full else 1
    ok = not (missed or blocked_holes)
    blocked += 0 if ok else 1
    print("  %d/%d holes clear for a screw, %d/%d seated on their bosses   %s"
          % (len(H._hole_points()) - blocked_holes, len(H._hole_points()),
             len(H._hole_points()) - missed, len(H._hole_points()),
             "" if ok else "*** THE BOARD IS NOT WHERE ITS HOLES ARE ***"))

    # Retention has to be checked BOTH WAYS or it is not checked. A board that
    # cannot be lifted straight off is retained; a board that cannot be got out
    # at all is a board you cut up to reflash. The lip reaches RET_OVER over the
    # +Y edge and the antenna's clearance gives BOARD_SLIDE_Y of travel the
    # other way, and the whole design rests on the first being less than the
    # second.
    print("")
    print("=== board retention gate ===")
    seated = housing_solid.intersect(board)
    seated_v = seated.val().Volume() if seated.val() is not None else 0.0
    straight = _swept(board, (-1.0, 0.0, 0.0), 30.0)
    i = straight.intersect(housing_solid)
    held = (i.val().Volume() if i.val() is not None else 0.0) - seated_v
    slid = board.translate((0.0, -H.BOARD_SLIDE_Y, 0.0))
    s_seat = housing_solid.intersect(slid)
    s_seat_v = s_seat.val().Volume() if s_seat.val() is not None else 0.0
    out = _swept(slid, (-1.0, 0.0, 0.0), 30.0)
    i = out.intersect(housing_solid)
    free = (i.val().Volume() if i.val() is not None else 0.0) - s_seat_v
    ok = held > 1.0 and free <= 1.0
    blocked += 0 if ok else 1
    print("  straight off  %s" % ("HELD, %.0f mm3 of lip in the way" % held
                                  if held > 1.0 else
                                  "*** COMES STRAIGHT OFF: NOTHING RETAINS IT ***"))
    print("  slid %.1f mm toward -Y, then off  %s"
          % (H.BOARD_SLIDE_Y,
             "clear" if free <= 1.0 else
             "*** STILL TRAPPED, %.0f mm3 ***" % free))

    # Does the CAD draw the board that was actually ROUTED? PCB_README lists
    # cad_geom_check under "your build gate should too", and it was not here --
    # which is how it went unnoticed that the check was aimed at the printed
    # frame's board, on the far side of the machine, instead of the housing's.
    print("\n=== routed-board agreement ===")
    sys.path.insert(0, str(OUT / "elec"))
    import cad_geom_check
    board_bad = cad_geom_check.main(["main"])

    b = asm.toCompound().BoundingBox()
    print("\nwhole assembly %.0f x %.0f x %.0f mm"
          % (b.xlen, b.ylen, b.zlen))
    print("Wrote %s  [build #%d]" % (out, build_n))
    show(out)
    return bad + oversize + blocked + board_bad


if __name__ == "__main__":
    sys.exit(main())
