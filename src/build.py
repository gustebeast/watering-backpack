"""Watering Backpack — build entry point.

  py -3.12 -m src.build     # export every printed STEP, build the assembly,
                            # run the gates, refresh the web viewer

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
from cadkit.web import show
from cadkit.step_export import export_step, export_print, print_pose
from cadkit.orientation import (PrintOrientation as PO,
                                require_declared, unconfirmed)

from . import housing as H
from . import lumber_frame as L
from . import plumbing as P
from . import wiring as W
from . import pump_frame as F
from .dual_clamp import dual_clamp_19
from .helpers import bump_build_counter
from . import battery as BAT
from . import tank as TK
from . import board_parts as BP
from .joystick_mount import joystick_mount

OUT = pathlib.Path(__file__).resolve().parent.parent
BED = 255.0

# ⚠ THE PACK IS THE PACK NOW, not a prism standing in for one. It was
# "116 x 75 x 65.6, an ENVELOPE, not a model" -- which was honest, and three
# literals that happened to equal the GrabCAD model's own bounding box. See
# src/battery.py for the pose and for why the BIG pack is the one drawn.
#
# BATT_L/W/D are still here under their old names because half this file reads
# them, but they are MEASURED off the model now. BATT_CHANNEL stays a declared
# number: it is how deep the rails sit in the dock, which is a fit the dock
# owns and v1 validated, not something this file gets to read off a bbox.
BATT_L, BATT_W, BATT_D = BAT.BATT_L, BAT.BATT_W, BAT.BATT_D
BATT_CHANNEL = 7.0                       # how deep the rails sit in the dock


def _battery_seat():
    """(x_face, y_c, z0) -- where the pack sits, off the PLACED dock."""
    dock = H._dock_placed().val().BoundingBox()
    return (dock.xmin + BATT_CHANNEL,      # rails sit this far into the dock
            (dock.ymin + dock.ymax) / 2.0,
            dock.zmin)


def battery_solid() -> cq.Workplane:
    """The pack as drawn: the imported model, or its prism without the STEP."""
    s = BAT.solid(*_battery_seat())
    return battery_envelope() if s is None else s


def battery_envelope() -> cq.Workplane:
    """The pack's bounding prism. Still here: the lift-out sweep is a prism
    sweep and a swept hull of 599 faces is not worth what it would cost."""
    return BAT.envelope(*_battery_seat())


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


# ── PRINT ORIENTATION — every printed part's bed face, in ONE table, as
# cadkit requires (cadkit/AGENTS.md). The housing pair declare themselves in
# housing.py, beside the geometry whose shape depends on their build
# direction; the other two declare here. All four were already documented in
# prose — this puts the claim where export and the overhang gate read it.
PRINT_ORIENTATION = dict(H.PRINT_ORIENTATION)
PRINT_ORIENTATION.update({
    "joystick_mount": PO(
        None,
        "exactly as modelled — Z up, clamp mouth on the bed "
        "(joystick_mount.py). Built to print support-free: the hose grip is "
        "a ~270 deg arc open at the bottom mouth, so there is no round "
        "bore-ceiling and the plate just BRIDGES the ~12 mm opening; the "
        "plate edges ride 45 deg gussets whose inner foot lands on the "
        "grip's outer face, so the underside is carried continuously; and "
        "two flat-bottomed screw ears flank the mouth as the print base"),
    "dual_clamp_19": PO(
        None,
        "as modelled, no supports (dual_clamp.py) — the pole grip is a "
        "vertical extrusion, and the hose grip's bore is horizontal with its "
        "mouth DOWN so only its crown is a short, bridgeable overhang"),
})


def printed_parts():
    return (("v2_housing", H.housing(), PRINT_ORIENTATION["v2_housing"]),
            ("v2_housing_lid", H.lid(), PRINT_ORIENTATION["v2_housing_lid"]),
            ("joystick_mount", joystick_mount,
             PRINT_ORIENTATION["joystick_mount"]),
            # dual_clamp_23 retired: it gripped a 23 mm VALVE body and
            # DESIGN_V2 section 1 has no reversing valve. See src/dual_clamp.py.
            # line_filter_screen retired 2026-10-05: the owner decided the
            # green-line filter is two BOUGHT Seaflo 51S01 strainers at the
            # two tees, not a printed screen -- see DESIGN_V2 section 4 and
            # WORK_V2_PUNCHLIST findings 13/13a. src/line_filter.py and the
            # test_screen_slice coupon went with it; git has them.
            ("dual_clamp_19", dual_clamp_19,
             PRINT_ORIENTATION["dual_clamp_19"]))


def components():
    """Everything the overlap gate weighs, in one place so the build and
    `tools/check_overlaps.py` cannot disagree about what the design IS."""
    comps = [("housing", H.housing()), ("housing_lid", H.lid()),
             ("pcb", H.pcb_solid()), ("wood", L.frame()),
             ("battery", battery_solid()),
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
    # The internal harness, weighed by the SAME gate as everything else -- a
    # cable that no model draws is how J5 sat on the wrong edge of the board for
    # five rounds of review (punchlist 21).
    comps += W.solids()
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
    if pair == {"battery", "housing"}:
        # The pack's RAILS in the dock's T-slot: 262.4 mm3. It read 12528 while
        # the pack was a prism, because a prism has no rails -- the whole 7 mm
        # of engagement was solid block driven into the dock. The number got
        # fifty times smaller by drawing the part instead of its box.
        return True
    # battery <-> terminal WAS whitelisted here at 1762.7 mm3, and the note
    # explained it: "the STEP is a solid ENVELOPE with no contact cavities
    # modelled, so blades that are correctly inside the pack have nowhere to be
    # except inside that solid". That was true of the PRISM. The model has the
    # cavities, the connector nests in them, and the pair measures 0.00 -- so
    # the entry is gone and the gate watches it. tools/check_battery_pose.py is
    # what makes that zero mean something: end-for-end it reads 1565.4.
    if all(n.startswith(("tank_", "green_")) for n in pair):
        return True
    return False


def add_part(asm, name, solid, tint, alpha=1.0):
    """Put `solid` in the assembly under `name`, in `tint` — ONE NODE PER SOLID.

    ⚠ AND THAT IS NOT TIDINESS, IT IS THE ONLY WAY THE COLOUR SURVIVES. The
    viewer does not read this assembly: `cadkit.web` reads `assembly.step` back
    with `cq.Assembly.importStep`, and a node whose shape is a COMPOUND OF MORE
    THAN ONE SOLID comes back with `color = None`. Six lines reproduce it —
    save a one-solid part and a two-solid part under the same colour, re-import,
    and the two-solid one is colourless. The viewer then falls back to its
    default (0.8, 0.8, 0.8), which is why the imported Makita pack rendered
    WHITE: nine solids in one compound, nine nodes at 0.8 grey, measured
    straight out of the .glb's materials.

    THE RULE IS NARROWER THAN THAT, AND WORSE: a STEP carries a colour on a
    SOLID. A part that is one FACE loses it too — tested, not assumed. That is
    why splitting cannot save the silkscreen (`COLOUR_EXCEPTIONS`): the ink is
    359 flat faces standing 0.02 mm off the laminate, and there is no number of
    nodes that makes a face a solid.

    It is not the battery's problem either. Every part drawn from several
    bodies has it — the board's twenty chip resistors as one coloured group
    would have come back white too, which is the whole point of splitting the
    board by material.

    The viewer already names a multi-solid part's pieces `<name>_0 .. _N`
    (`cadkit.web.export.pieces`), so splitting here changes no name it shows.
    """
    c = color(tint, alpha=alpha)
    try:
        vals = solid.solids().vals()
    except Exception:                                              # noqa: BLE001
        vals = []
    if len(vals) <= 1:
        asm.add(solid, name=name, color=c)
        return
    for i, piece in enumerate(vals):
        asm.add(cq.Workplane(obj=piece), name="%s_%d" % (name, i), color=c)


# ⚠ NAMED AND MEASURED, NOT WAIVED. Same standing as `intended()` below: an
# entry here is a claim that this part CANNOT carry its colour, with the cost
# of that stated, and the gate still catches everything else.
#
# The board's silkscreen is 479 flat FACES (359 front, 120 back) — cadkit
# draws ink as faces standing SILK_T = 0.02 mm off the laminate, not as bodies
# — and a STEP carries a colour on a solid. One face loses its colour exactly
# as a nine-solid compound does.
#
# THE COST, MEASURED: the ink is asked for at #f2f2f2 = (0.949, 0.949, 0.949)
# and draws at the viewer's default (0.8, 0.8, 0.8). Both are near-white on a
# dark green board, which is the only reason this went unnoticed and is NOT a
# reason to leave it: it is the one part on the model where the default
# happens to be close to the intent.
#
# THE FIX IS cadkit's, not this file's — ink drawn as thin solids, or colours
# written so a face can keep one — and by this project's rule that means
# canonical ../cadkit and `propagate.py`, not a hand-edit of the vendored copy.
COLOUR_EXCEPTIONS = {
    "pcb_silk": "flat ink: 479 faces, and a STEP colours solids",
}



# ── WHAT EACH PART IS MADE OF ───────────────────────────────────────────────
# A colour says what a part looks like; a MATERIAL says how light leaves it,
# and the viewer wants both. Without this every part was shaded "plain
# plastic" -- which made the brass fittings and the steel screw as matte as a
# printed wall, and the board's mask as dead as sawn pine. The names are
# cadkit's own (`cadkit.web.finishes`: a filament or a finish), and a filament
# or metal colour is used ONLY where a part has no colour of its own, so
# nothing here overrides the tints above.
#
# The lumber's "wood" is cadkit's now (web/finishes.py, 0.78: matte with the
# sheen that is along the grain). It was missing, and this frame is what
# noticed -- every plank, post and rail was shaded plain plastic. It went
# there rather than here because the pantorouter is made of the same stuff.
MATERIAL = {
    # sawn fir, from L.pieces(): the names are the cut list's
    "plank_deck": "wood", "plank_floor": "wood",
    "post": "wood", "rail_cross": "wood", "rail_side": "wood",
    # printed: the one spool, named where PRINTED_IN_ASSEMBLY is asserted
    "housing": "pctg", "housing_lid": "pctg",
    # the board: its mask is a hard gloss lacquer, its lettering is not
    "pcb": "board", "pcb_silk": "ink",
    "pcb_screw": "steel", "pcb_insert": "brass",
    "fittings": "brass",
    # moulded plastic cases -- a Makita pack, its contact block, the pump
    # bodies, the Scepter can. "painted" is cadkit's non-metal semi-gloss; it
    # is the closest name it has for moulded ABS and HDPE, and that is an
    # approximation, not a measurement.
    "battery": "painted", "terminal": "painted",
    "pump_a": "painted", "pump_b": "painted", "tank_viz": "painted",
}


def material_of(name, hoses=(), wires=()):
    """`name` -> what it is made of, or None. Called with the names the export
    uses, which for a multi-solid part are `<part>_0 .. _N`, so a trailing
    index is dropped when dropping it finds a part. Hose and wire names come
    from the modules that make them (see HOSES / WIRES), not from spelling."""
    for n in (name, name.rsplit("_", 1)[0]):
        if n in MATERIAL:
            return MATERIAL[n]
        if n in hoses or n in wires:
            return "pvc"          # vinyl tube, and wire insulation
    return None

def colour_check(step_path):
    """Every part in the written STEP must come back WITH ITS COLOUR.

    The gate for the above. A part that loses its colour is not a crash and not
    an overlap — it is a part that quietly renders in the viewer's default grey,
    which is exactly how an imported pack sat there white while this file was
    setting it to #2b2e31 and `node.color` read back correctly in memory.
    """
    lost = []
    try:
        back = cq.Assembly.importStep(step_path)
    except Exception as exc:                                       # noqa: BLE001
        print("  could not re-read %s (%s) -- NOT a pass: nothing was checked"
              % (step_path, exc))
        return 1
    n, excused, seen = 0, [], set()
    for nm, node in back.traverse():
        if not getattr(node, "shapes", None):
            continue
        n += 1
        base = nm.split("/")[-1]
        seen.add(base)
        if node.color is None:
            (excused if base in COLOUR_EXCEPTIONS else lost).append(base)
    # ...and an exception that is no longer happening is not a free pass: it is
    # either fixed (drop it) or the part is gone (drop it). Either way, say so.
    stale = sorted(k for k in COLOUR_EXCEPTIONS
                   if k not in excused and k in seen)
    gone = sorted(k for k in COLOUR_EXCEPTIONS if k not in seen)
    for k in stale:
        print("  %s carries its colour now -- drop its COLOUR_EXCEPTIONS entry"
              % k)
    for k in gone:
        print("  %s is not in the assembly any more -- drop its "
              "COLOUR_EXCEPTIONS entry" % k)
    for k in sorted(excused):
        print("  %-14s declared colourless: %s" % (k, COLOUR_EXCEPTIONS[k]))
    if lost:
        print("  *** %d of %d part(s) LOST THEIR COLOUR and will draw in the "
              "viewer's default grey: %s ***"
              % (len(lost), n, ", ".join(sorted(lost)[:8])))
        return 1
    print("  %d part(s), every one with the colour it was given%s"
          % (n, " (%d declared colourless)" % len(excused) if excused else ""))
    return 1 if (stale or gone) else 0


def main() -> int:
    build_n = bump_build_counter()

    print("=== printed parts ===")
    oversize = 0
    require_declared({n for n, _p, _o in printed_parts()}, PRINT_ORIENTATION)
    # 🚩 an UNCONFIRMED bed face is a guess nobody has checked — and the bed
    # face decides which faces are overhangs, so work done on top of a guess
    # can be silently wrong. Say so on every build (cadkit AGENTS.md).
    flagged = unconfirmed(PRINT_ORIENTATION)
    if flagged:
        print("UNCONFIRMED print orientation (confirm with the user BEFORE "
              "working on these parts): " + ", ".join(flagged), flush=True)

    for name, part, orient in printed_parts():
        export_print(part, orient, str(OUT / (name + ".step")))
        posed = print_pose(part, orient)
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
        add_part(asm, "%s_%d" % (nm, i), solid, tint)
    # ⚠ THE BOARD IS DRAWN IN THE MASK IT IS ORDERED IN, read from the order
    # rather than picked to look about right. elec/main.py's order_options say
    # "Green, white silk"; src/board_parts.MASK names it and cadkit turns that
    # into the colour of a MADE board (the laminate under a mask darkens it),
    # so "#2f7d4f" -- a green somebody chose -- becomes #085424, the green that
    # will be in the hand. Change the order and the picture follows.
    tints = {"housing": "#6a8fb5", "housing_lid": "#8fb56a",
             "pcb": "#%02x%02x%02x" % tuple(
                 int(round(255 * c)) for c in BP.mask_tint()[:3]),
             "pcb_screw_0": "#c0c6cc", "pcb_insert_0": "#b08d57",
             # dark grey, as a Makita pack is. It was "#d08a3e", an orange
             # that belonged to the prism era and to nothing in the hand.
             "battery": "#2b2e31", "pump_a": "slategray", "pump_b": "#5a6b7a",
             "fittings": "#c8a24a",
             # the Makita contact block. It used to fall through to the default
             # and come out hose-green, which is what a default picked by name
             # prefix does to a part whose name has no prefix.
             "terminal": "#3b3f44"}
    # ── WHICH SOLIDS ARE HOSES AND WHICH ARE WIRES, FROM THE MODULES THAT MAKE
    # THEM, not from the spelling of a name. The rule underneath used to be
    # `"#b03030" if nm.startswith("tank") else "#30a050"`, so every part with no
    # entry above -- the Makita terminal among them -- was drawn as a green
    # hose. Ask the two modules what they built and nothing can be mistaken for
    # a hose by accident.
    HOSES = {n for n, _pts in P.routes()}
    WIRES = {n for n, _s in W.solids()}
    # The harness is BLACK. Every conductor in it is a black lead in the hand;
    # drawing them in net colours was a schematic, not a model. Which cable is
    # which is a question src/wiring.py answers by name, and the overlap gate
    # reports by name, so nothing is lost by drawing the thing as it looks.
    WIRE_TINT = "#17191c"
    # ...and the hoses are TRANSLUCENT, because the hose is. 1/2" vinyl is a
    # clear tube with a tint, and drawn opaque it hides every line behind it --
    # which on the green side is most of the plenum. The tints stay (tank red,
    # green line green) because they are how the two circuits are told apart in
    # CIRCUIT.md and on the bench, but they are now washes over a see-through
    # wall rather than paint.
    HOSE_ALPHA = 0.45
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
    # ⚠ AND NOTHING IS, NOW. The battery was the last entry -- 0.35, "the dock,
    # the contact block and the lift path are all behind it" -- and that was a
    # reason to see through a PRISM: you could not otherwise tell whether the
    # block was engaged, because a prism is the same solid whichever way round
    # it sits. The pack is the pack now and the question is answered by
    # measurement instead: tools/check_battery_pose.py reads the block nesting
    # in the pack's own interface cavity at 0.00 mm3 and both wrong poses at
    # thousands. So the pack is drawn SOLID, in the dark grey it actually is,
    # and the fit is checked rather than squinted at.
    SEE_THROUGH: dict = {}
    # ── EVERY PRINTED PART IS PCTG, AND PCTG IS ONE COLOUR ──────────────────
    # The housing was "#6a8fb5" and its lid "#8fb56a" -- a blue box with a
    # green lid, which is a diagram of which part is which, not a picture of
    # two parts that come off the same spool. They are printed in PCTG and
    # PCTG is what they look like. Taken from PRINT_ORIENTATION, which is the
    # table that already has to name every printed part (require_declared
    # above fails the build otherwise), so a new printed part cannot be given
    # a colour by forgetting about it.
    PCTG = "#228b22"                                # forest green
    # {assembly name: the printed part it IS}. Two names for one thing is how
    # the wrong one gets coloured, so the mapping is explicit and checked: the
    # right-hand side must be a part PRINT_ORIENTATION declares (and
    # require_declared above has already failed the build if one is missing),
    # and the left must be something the assembly actually places.
    PRINTED_IN_ASSEMBLY = {"housing": "v2_housing",
                           "housing_lid": "v2_housing_lid"}
    _placed = {n for n, _s in comps}
    for _asm_name, _print_name in PRINTED_IN_ASSEMBLY.items():
        assert _print_name in PRINT_ORIENTATION, (
            "%r is not a declared printed part" % _print_name)
        assert _asm_name in _placed, (
            "%r is not in the assembly any more" % _asm_name)
        tints[_asm_name] = PCTG
    # joystick_mount and dual_clamp_19 are printed and EXPORTED but this
    # assembly does not place them (they live on the wand and the pole), so
    # there is nothing here to colour. Said rather than left to be noticed.
    unclassified = sorted(n for n, _s in comps
                          if n != "wood" and n not in tints
                          and n not in HOSES and n not in WIRES)
    assert not unclassified, (
        "no colour for %s -- add it to `tints` rather than letting it take a "
        "default meant for something else" % unclassified)
    for nm, solid in comps:
        if nm == "wood":
            continue
        if nm in HOSES:
            c, a = ("#b03030" if nm.startswith("tank") else "#30a050"), HOSE_ALPHA
        elif nm in WIRES:
            c, a = WIRE_TINT, 1.0
        else:
            c, a = tints[nm], SEE_THROUGH.get(nm, 1.0)
        add_part(asm, nm, solid, c, a)
    # The board's own silkscreen, both faces as ONE part. Not in components():
    # see housing.pcb_silk() for why ink is not an interference -- and
    # housing.pcb_ink() for why the two faces may not go in separately.
    _ink = H.pcb_ink()
    if _ink is not None:
        add_part(asm, "pcb_silk", _ink, "#f2f2f2")
    # The can in the colour it is sold in, and opaque: it was pale blue at
    # 0.35 because it was a brick standing in for a can, and see-through is
    # reserved for fits you cannot otherwise see (SEE_THROUGH above).
    add_part(asm, "tank_viz", L.tank(), TK.BODY, 0.9)
    try:
        counter = (cq.Workplane("XZ").center(0, L.DECK_Z + 520)
                   .text(str(build_n), 30, 6))
        add_part(asm, "build_counter", counter, "#F0A878")
    except Exception:                                              # noqa: BLE001
        pass

    out = str(OUT / "assembly.step")
    asm.save(out, mode="default")

    print("\n=== viewer colour gate ===")
    lost_colour = colour_check(out)

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
    slid_sweep = _swept(slid, (-1.0, 0.0, 0.0), 30.0)
    i = slid_sweep.intersect(housing_solid)
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
    # ⚠ `out` IS THE STEP PATH AND MUST STILL BE A STRING HERE. It was once
    # reused as a scratch Workplane by the board-retention gate above, which
    # cost nothing on disk -- asm.save() already ran -- but handed show() an
    # object. show() never raises by design, so it printed ONE stderr line
    # and returned False, and the viewer silently stopped refreshing on
    # every build. The "Wrote <cadquery.cq.Workplane object>" line was the
    # only tell and it reads like success. Assert instead of trusting it.
    assert isinstance(out, str), (
        "the STEP path was overwritten before show(): got %r. Some gate above "
        "reused the name `out` as a scratch solid." % (out,))
    print("Wrote %s  [build #%d]" % (out, build_n))
    # ⚠ `boards=` IS WHAT PUTS REAL COMPONENTS ON THE BOARD, and leaving it
    # off is why this model showed a green brick with green bumps on it for as
    # long as it had a board. The CAD draws one box per footprint, which is
    # right for the clearance gates and wrong to look at; the viewer swaps each
    # box for KiCad's own model of that footprint (drawn by cadkit.web.parts
    # where the library has none), seats a crimp housing in every JST and puts
    # the lettering on. None of that is this project's to draw -- see
    # cadkit/PCB_README.md s6, and read the "web boards:" line below for any
    # footprint that kept its box, with WEB_BOARDS_WHY=1 to have it named.
    if not show(out, root=OUT, build=build_n, boards=H.BOARDS,
                materials=lambda n: material_of(n, HOSES, WIRES)):
        print("*** THE VIEWER DID NOT REFRESH *** see the [web view] line above")
    return bad + oversize + blocked + board_bad + lost_colour


if __name__ == "__main__":
    sys.exit(main())
