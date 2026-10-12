"""This board's parts — the table that was in two places, and the few bodies a box lies about.

Modelled after what bronner did for the pedal steel's boards (that project's
`src/board_geom.py` and `src/optical_pickup.py`): the shared machinery is
cadkit's, the PART FACTS that cadkit does not carry live in ONE project-local
table with a source against each figure, and where a part's F.Fab box is not
what the part looks like, the project DRAWS IT and tells `Boards.solid` to skip
it. "the optical board's plugs as they look: a JST crimp housing, a black
ribbed USB-C lead" is the commit; this is the same move on this board.

WHAT WAS WRONG WITH THE OLD ARRANGEMENT
---------------------------------------
1. TWO TABLES. `pump_frame._PCB_HEIGHT` and `elec/cad_geom_check.py` each had
   their own copy keyed by footprint name, and the first one's own comment says
   what that cost: "renaming the footprint failed the geometry gate from HERE
   after the other one was already fixed -- 'no HEIGHT for ...-PINFIT'. Two
   tables keyed by footprint name is one table too many; whichever is touched
   next should take the other with it." This is that touch.

2. NO TAIL TABLE AT ALL. `Boards(...)` was called with `height=` and nothing
   else, so every through-hole part on this board hung cadkit's DEFAULT 3.4 mm
   of leg below the laminate — the figure cadkit derives from a JST XH post.
   Nothing here is a JST XH. The board sits on 4.0 mm standoffs, so what those
   tails nearly touch is the bay floor, and "nearly" was being decided by a
   part this board does not have.

3. EVERY PART A BOX. Which is right for a shielded module and wrong for a
   screw terminal, an electrolytic can and a buzzer — and the screw terminals
   are both the tallest things on the board and the part JLCPCB wrote in to ask
   about.

WHAT IS STILL A BOX, ON PURPOSE
-------------------------------
F2, the fuse holder. Its declared 21.6 mm is NOT the body: the body is 18.5
above the laminate, and the extra 3.1 is the pin length, carried deliberately
so the figure covers a holder WITH A FUSE IN IT, which the drawing does not
dimension (see HEIGHT below — the argument is preserved there in full). The
bay's depth rests on that number. Drawing the holder "accurately" would mean
drawing a fitted stack nobody has measured and quietly shrinking the bay by
3 mm on the strength of it. A box that is honestly too big beats a shape that
is confidently wrong, and this is the one part where that trade is live.
"""
from __future__ import annotations

import math

import cadquery as cq

from cadkit.board_geom import Boards, fp_name, mask_rgb

# ── BODY HEIGHT above the board face, per footprint ─────────────────────────
# Moved here from src/pump_frame.py with its reasoning intact. A footprint with
# no height RAISES rather than being left out of the drawing.
# Every number says where it came from; an estimate is allowed, an unlabelled
# one is not (PCB_README).
HEIGHT = {
    # from the footprint name, which states the body size
    "Buzzer_12x9.5RM7.6":                    9.5,    # 12 dia x 9.5 high
    "CP_Elec_10x10.5":                      10.5,    # 10 dia x 10.5 high
    # from the maker's drawing / JEDEC outline
    "ESP32-WROOM-32E-FABDRILL":              3.1,    # Espressif datasheet, 18 x 25.5 x 3.1
    "L_Bourns_SRN6045TA":                    4.5,    # Bourns SRN6045, 6.0 x 6.0 x 4.5
    "TO-252-3_TabPin2":                      2.3,    # JEDEC TO-252 (DPAK) body
    "TO-263-2":                              4.6,    # JEDEC TO-263 (D2PAK) body
    # catalogue line
    "PinHeader_1x06_P2.54mm_Vertical":       8.5,    # 2.54 header, pin above board
    "C_0603_1608Metric":                     0.9,    # 0603 MLCC, typical max
    # the buck's real package: HSOIC-8 with PowerPAD. Same 1.75 mm body as the
    # plain SOIC-8 cadkit already lists -- what changed is the land under it.
    "SOIC-8-1EP-FABDRILL": 1.75,
    "R_0805_2012Metric": 0.6,          # VGATE dropper: 0805 for its 0.1 W
    # MEASURED, not estimated: all five terminals are now the SAME part,
    # Ningbo Kangnex WJ500V-5.08-NP, whose customer drawing (LCSC C8465,
    # sheet 1/1) gives 14.07 mm above the board for the whole family. That
    # replaces the 17.0 / 15.0 guesses this table used to carry, and it
    # moves the right way: the PCB shroud needs 2.93 mm LESS standoff than
    # the old MKDS-3 estimate demanded.
    "TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal": 14.07,
    "TerminalBlock_Phoenix_MKDS-3-4-5.08_1x04_P5.08mm_Horizontal": 14.07,
    "TerminalBlock_Phoenix_MKDS-3-5-5.08_1x05_P5.08mm_Horizontal": 14.07,
    # ⚠ THE TALLEST PART ON THE BOARD, AND THE ONE THAT SETS THE BAY DEPTH.
    # Littelfuse 178.6165 FLR, datasheet drawing (LCSC C207060, 1 page, VECTOR
    # not a scan, so these are read dimensions): 20 wide, 6 deep, and 21.6 mm
    # OVERALL from the top of the body to the tips of the pins. The side view
    # breaks that down as 17.5 body + 1 standoff above the board + 3.1 of pin
    # below it, i.e. 18.5 mm above the laminate.
    #
    # 21.6 IS DECLARED HERE, NOT 18.5, AND THE EXTRA 3.1 mm IS DELIBERATE. What
    # has to clear the lid is the holder WITH A FUSE IN IT, and the drawing does
    # not dimension that. The cavity is 20 x 6 and an ATO fuse is 19.1 x 5.1 x
    # 18.6, so it drops in essentially flush -- but "essentially" is an argument
    # and 21.6 is a number off the same drawing that cannot be smaller than the
    # truth, since it already contains 3.1 mm of pin that lives UNDER the board.
    # Nobody has to own a caliper for the housing to be right. A measurement of
    # the fitted stack would recover about 3 mm of bay depth and is the first
    # thing to do if that depth is ever wanted.
    "FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165-PINFIT":         21.6,
}

# ── HOW FAR A THROUGH-HOLE LEG HANGS BELOW THE LAMINATE ─────────────────────
# NEW. Nothing in this project ever passed `tail=`, so every one of these took
# cadkit's 3.4 mm default -- which cadkit derives from a JST XH post, a part
# this board does not carry. The board stands on 4.0 mm standoffs and the gap
# between a tail's tip and the bay floor is 4.0 minus whatever is here, so the
# default was deciding a real clearance by analogy with the wrong component.
#
# 0.0 means SURFACE MOUNT: it is stated rather than left out, because a part
# missing from this table takes the default, and the default is not zero.
TAIL = {
    # The five screw terminals, WJ500V-5.08-NP (LCSC C8465, sheet 1/1): the
    # solder pin is 3.5 mm under the seating plane, so 1.9 shows through a
    # 1.6 mm board.
    "TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal": 1.9,
    "TerminalBlock_Phoenix_MKDS-3-4-5.08_1x04_P5.08mm_Horizontal": 1.9,
    "TerminalBlock_Phoenix_MKDS-3-5-5.08_1x05_P5.08mm_Horizontal": 1.9,
    # READ off the same Littelfuse drawing the HEIGHT argument above cites, and
    # in fact already quoted: "3.1 of pin below it". It was in a comment and
    # nothing used it.
    "FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165-PINFIT": 3.1,
    # The buzzer's leads, and the 1x06 header's. ESTIMATES, and flagged: both
    # are sold with a ~3.0 mm tinned lead, so ~1.4 shows under a 1.6 board.
    # Neither is near anything -- they are the two shortest tails on the board
    # -- which is why an estimate is tolerable here and not on the terminals.
    "Buzzer_12x9.5RM7.6": 1.4,
    "PinHeader_1x06_P2.54mm_Vertical": 1.4,
    # Surface mount, said out loud:
    "ESP32-WROOM-32E-FABDRILL": 0.0,     # castellated, and the FABDRILL holes
                                         # are tooling, not legs
    "CP_Elec_10x10.5": 0.0,              # V-chip can, gull-wing on the board
    "L_Bourns_SRN6045TA": 0.0,
    "TO-263-2": 0.0, "TO-252-3_TabPin2": 0.0,
    "SOIC-8-1EP-FABDRILL": 0.0,
    "R_0805_2012Metric": 0.0, "C_0603_1608Metric": 0.0,
}

# ── THE MASK THE BOARD IS ORDERED IN ────────────────────────────────────────
# elec/main.py's order_options: "mask: Green, white silk. Highest contrast for
# the test-pad and connector lettering." Named here and read by the drawing, so
# the board in the picture is the board in the order rather than a green that
# happens to look about right.
MASK = "green"


def mask_tint():
    return mask_rgb(MASK)


# ── THE PARTS THIS FILE DRAWS ITSELF ────────────────────────────────────────
# Keyed by FOOTPRINT, like everything else here. `Boards.solid(skip=...)` leaves
# these out so they can be drawn properly -- the `skip` mechanism, NOT `omit`:
# these parts ARE fitted, somebody else just draws them. (cadkit's own words:
# "Merge them and either a DNP part reappears or a part is drawn twice.")
SHAPED = (
    "TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal",
    "TerminalBlock_Phoenix_MKDS-3-4-5.08_1x04_P5.08mm_Horizontal",
    "TerminalBlock_Phoenix_MKDS-3-5-5.08_1x05_P5.08mm_Horizontal",
    "CP_Elec_10x10.5",
    "Buzzer_12x9.5RM7.6",
)

PITCH = 5.08                 # the terminals' way pitch, in the part number
MOUTH_D = 3.6                # the wire bore, WJ500V: accepts 2.5 mm2
SCREW_D = 3.0                # the clamp screw's head
WALL = 1.2                   # how much plastic a mouth keeps around it


def _terminal(f, t: float, ways: int):
    """A horizontal screw terminal, drawn as one: mouths on the face that takes
    the wire, screw heads on top, the front shoulder cut back.

    ⚠ WHICH FACE THE WIRE GOES IN IS NOT A GUESS AND IT IS NOT NEW. It is the
    board's -Y face, which src/wiring.py declares as ENTRY_FACE with a long note
    on why it cannot be inferred -- cadkit's own `lead_exit` returns a TOP-entry
    answer for these parts, silently, and the body is near enough symmetric
    (5.35 mm one side of the pad row, 5.95 the other) that measuring the block
    decides it the wrong way round. The mouths are drawn on the same face the
    harness is drawn into, from the same declaration, so the two cannot drift.
    """
    x0, x1, y0, y1 = f["fab"]
    h = HEIGHT[fp_name(f["fpid"])]
    body = (cq.Workplane("XY").workplane(offset=t)
            .center((x0 + x1) / 2.0, (y0 + y1) / 2.0)
            .rect(x1 - x0, y1 - y0).extrude(h))
    # the front shoulder: a terminal's mouth face is stepped back at the top
    step = (cq.Workplane("XY").workplane(offset=t + h - 3.0)
            .center((x0 + x1) / 2.0, y0 + 1.6)
            .rect(x1 - x0 + 2.0, 3.2).extrude(3.0 + 1.0))
    body = body.cut(step)
    # the ways, centred on the pad row's own span so they land on the pads
    px0, _px1 = f["tht"][0], f["tht"][1]
    for k in range(ways):
        xc = px0 + 0.645 + k * PITCH if ways > 1 else (x0 + x1) / 2.0
        xc = (f["tht"][0] + f["tht"][1]) / 2.0 + (k - (ways - 1) / 2.0) * PITCH
        # wire bore, into the -Y face, on the axis the wire arrives on
        bore = (cq.Workplane("XZ").workplane(offset=y0 - 0.5)
                .center(xc, t + 4.2).circle(MOUTH_D / 2.0).extrude(-7.0))
        body = body.cut(bore)
        # clamp screw, down from the top
        head = (cq.Workplane("XY").workplane(offset=t + h - 1.4)
                .center(xc, y1 - 3.4).circle(SCREW_D / 2.0).extrude(2.0))
        body = body.cut(head)
    return body


def _can(f, t: float, d: float, h: float):
    """An aluminium electrolytic can: a cylinder with its top edge broken and
    the pressure-relief cross in it. The F.Fab box is square around it."""
    x0, x1, y0, y1 = f["fab"]
    xc, yc = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    s = (cq.Workplane("XY").workplane(offset=t).center(xc, yc)
         .circle(d / 2.0).extrude(h))
    s = s.edges(">Z").fillet(0.8)
    for ang in (0.0, 90.0):
        a = math.radians(ang)
        s = s.cut(cq.Workplane("XY").workplane(offset=t + h - 0.4)
                  .center(xc, yc).rect(d - 2.4, 0.9).extrude(0.6)
                  .rotate((xc, yc, 0), (xc, yc, 1), ang))
    return s


def _buzzer(f, t: float, d: float, h: float):
    """A magnetic buzzer: a can with the sound port in its top face."""
    x0, x1, y0, y1 = f["fab"]
    xc, yc = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    s = (cq.Workplane("XY").workplane(offset=t).center(xc, yc)
         .circle(d / 2.0).extrude(h))
    s = s.cut(cq.Workplane("XY").workplane(offset=t + h - 1.0)
              .center(xc, yc).circle(1.1).extrude(2.0))
    return s


def _tails(f, t: float, tail: float):
    """The part's own legs, since `skip` skips those too."""
    if not f.get("tht") or tail <= 0.0:
        return None
    tx0, tx1, ty0, ty1 = f["tht"]
    return (cq.Workplane("XY").workplane(offset=-tail)
            .center((tx0 + tx1) / 2.0, (ty0 + ty1) / 2.0)
            .rect(tx1 - tx0, ty1 - ty0).extrude(tail))


def shaped(board_geom, only=None):
    """The drawn-by-hand bodies for one board, in the BOARD's own frame.

    Returns (solid or None, refs that were drawn) -- the refs go to
    `Boards.solid(skip=...)` so nothing is drawn twice.

    `only` narrows it to those refs, which is how `parts()` gets each material
    group's shaped bodies on their own without cutting a union apart.
    """
    t = board_geom["thickness_mm"]
    out, refs = None, []

    def add(s):
        nonlocal out
        if s is not None:
            out = s if out is None else out.union(s)

    for f in board_geom["footprints"]:
        name = fp_name(f["fpid"])
        if name not in SHAPED or not f["fab"] or f["side"] != "F":
            continue
        if only is not None and f["ref"] not in only:
            continue
        refs.append(f["ref"])
        if name.startswith("TerminalBlock_"):
            ways = int(name.split("MKDS-3-")[1].split("-")[0])
            add(_terminal(f, t, ways))
        elif name == "CP_Elec_10x10.5":
            add(_can(f, t, 10.0, HEIGHT[name]))
        elif name == "Buzzer_12x9.5RM7.6":
            add(_buzzer(f, t, 12.0, HEIGHT[name]))
        add(_tails(f, t, TAIL.get(name, 0.0)))
    return out, tuple(refs)


def boards(geom_dir: str, **kw) -> Boards:
    """This project's `Boards`, with ITS tables on top of cadkit's."""
    return Boards(geom_dir, height=HEIGHT, tail=TAIL, **kw)


# ── WHAT EACH PART IS MADE OF ───────────────────────────────────────────────
# ⚠ A BOARD IS NOT ONE COLOUR, AND DRAWING IT AS ONE SOLID MADE IT ONE. The
# whole board went into the assembly as a single component, so the mask colour
# was painted over every part on it and the owner saw a green ESP32, green
# electrolytics and green screw terminals. Shaping the bodies (finding 62) did
# nothing for that: a correctly shaped terminal block in mask green still reads
# as part of the laminate.
#
# This is the pedal steel's arrangement. That project draws its LEDs with
# `BG.bodies(board, refs)` against `solid(skip=refs)` so they can be lit, and
# gives each board's silkscreen, plugs, screws and inserts their own named
# entry in `_COLORS`. cadkit's own docstring is explicit that this is what the
# pair is for: "skip = the part IS fitted and SOMEONE ELSE DRAWS IT (see
# bodies), so it can be another colour."
#
# Colours are the PART's, not a palette: a steel can is steel, an epoxy package
# is black, an MLCC is its tan ceramic. Each says what it is below.
LAMINATE = "laminate"
LEGS = "legs"

# (group, tint, footprint names). Order matters only for the first match.
MATERIALS = (
    # the ESP32 module's lid is a stamped steel can, and it is the one part on
    # this board big enough to read as a colour from across the room
    ("module", "#b9bdc2", ("ESP32-WROOM-32E-FABDRILL",)),
    # ⚠ THE TERMINALS' COLOUR IS THE LEAST CERTAIN THING HERE. The ordered part
    # is Ningbo Kangnex WJ500V-5.08-NP (LCSC C8465) and that family is moulded
    # in green -- a BRIGHTER green than a solder mask, which is why it is worth
    # drawing at all, but green. If the blocks that arrive are blue, this is
    # the line to change; nothing else reads it.
    ("terminals", "#3f9a46", ("TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal",
                              "TerminalBlock_Phoenix_MKDS-3-4-5.08_1x04_P5.08mm_Horizontal",
                              "TerminalBlock_Phoenix_MKDS-3-5-5.08_1x05_P5.08mm_Horizontal")),
    # aluminium electrolytics: a black sleeve over a bare can
    ("cans", "#1b1b20", ("CP_Elec_10x10.5",)),
    ("buzzer", "#141417", ("Buzzer_12x9.5RM7.6",)),
    # the blade-fuse holder, black nylon (Littelfuse FLR)
    ("fuse_holder", "#1d1d21", ("FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165-PINFIT",)),
    # black plastic strip, gold pins -- the strip is what you see
    ("header", "#202024", ("PinHeader_1x06_P2.54mm_Vertical",)),
    # the buck inductor: a moulded ferrite block, dark grey
    ("inductor", "#3a3a40", ("L_Bourns_SRN6045TA",)),
    # moulded epoxy packages: regulators, FETs, the buck, every diode
    ("packages", "#26262a", ("TO-263-2", "TO-252-3_TabPin2", "SOIC-8-1EP-FABDRILL",
                             "SOT-23", "SOT-23-5", "D_SMA", "D_SMC", "D_SOD-123")),
    # MLCCs are their own ceramic, and it is the one warm colour on the board
    ("ceramics", "#c3b193", ("C_0603_1608Metric", "C_0805_2012Metric",
                             "C_1206_3216Metric")),
    # thick-film chips: a dark body between two tinned ends
    ("chips", "#2d2d31", ("R_0603_1608Metric", "R_0805_2012Metric",
                          "Fuse_1206_3216Metric")),
)
TINT = {LAMINATE: None,            # filled from the order; see mask_tint()
        LEGS: "#9aa0a8"}           # tinned solder, the one metal under the board
TINT.update({g: t for g, t, _n in MATERIALS})
_OF = {n: g for g, _t, names in MATERIALS for n in names}


def group_of(name: str):
    """Which material group a footprint belongs to, or None."""
    return _OF.get(name)


def parts(B, board: str):
    """[(group, tint, solid)] -- the board split by what its parts are MADE OF.

    The union of these IS the board: `housing.pcb_solid()` builds it from
    exactly this list, so the solid the overlap gate weighs and the parts the
    viewer colours cannot be different things. That mattered the moment the
    drawing stopped being one call.
    """
    g = B.load(board)
    t = g["thickness_mm"]
    hand, hand_refs = shaped(g)
    out = [(LAMINATE, "#%02x%02x%02x" % tuple(int(round(255 * c))
                                              for c in mask_tint()[:3]),
            B.plate(board))]

    by_group, legs, missing = {}, None, []
    for f in g["footprints"]:
        if not f["fab"]:
            continue
        name = fp_name(f["fpid"])
        grp = group_of(name)
        if grp is None:
            # ⚠ NOT a default. A part nobody has said what it is made of is a
            # part that would come out the laminate's colour again, which is
            # the whole finding. It is named and the build stops.
            if B.HEIGHT[name] > 0.0:
                missing.append(name)
            continue
        if f["ref"] in hand_refs:
            continue                        # drawn by shaped(), tails and all
        if B.HEIGHT[name] <= 0.0:
            continue                        # bare copper: nothing stands there
        by_group.setdefault(grp, []).append(f["ref"])
        tail = _tails(f, t, TAIL.get(name, 0.0))
        if tail is not None:
            legs = tail if legs is None else legs.union(tail)
    if missing:
        raise KeyError(
            "no material group for %s -- add it to board_parts.MATERIALS "
            "rather than letting it take the laminate's colour"
            % ", ".join(sorted(set(missing))))

    for grp, _tint, _names in MATERIALS:
        refs = by_group.get(grp)
        if refs:
            out.append((grp, TINT[grp], B.bodies(board, refs)))
    # The hand-drawn bodies go back into THEIR OWN groups, so a shaped terminal
    # is still a terminal and not a fourth colour. Drawn one group at a time
    # rather than once and split afterwards: splitting a union by region is a
    # boolean per part and this is a lookup.
    if hand_refs:
        shaped_by_group = {}
        for f in g["footprints"]:
            if f["ref"] in hand_refs:
                shaped_by_group.setdefault(
                    group_of(fp_name(f["fpid"])), []).append(f["ref"])
        for grp, refs in sorted(shaped_by_group.items()):
            piece, _ = shaped(g, only=refs)
            if piece is not None:
                out.append((grp, TINT[grp], piece))
    if legs is not None:
        out.append((LEGS, TINT[LEGS], legs))
    return out
