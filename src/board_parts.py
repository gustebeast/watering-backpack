"""This board's part facts — the table that was in two places, and the one it never had.

Part FACTS that cadkit cannot know live here, in ONE table, with a source
against every figure. That is the half of bronner's pedal-steel arrangement
that belongs in a project (`src/board_geom.py` there): the machinery is
cadkit's, the numbers are the board's.

The other half of it does NOT belong here, and this file learnt that the
expensive way. It drew five screw terminals, two electrolytic cans and a
buzzer, because their F.Fab boxes are a poor likeness and the render looked
like a green brick with green bumps on it. The render looked like that because
`show()` was never handed `boards=`. With that one argument the viewer draws
67 of this board's 67 footprints from KiCad's own coloured models and keeps no
box at all, so every body this file drew was a worse copy of a model that was
already on the machine. A part with no model anywhere gets a generator in
`cadkit/web/parts.py`, where every project's boards get it -- not here. See
cadkit/PCB_README.md section 6.

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

F2's height is the one entry that is deliberately not the body: see HEIGHT.
"""
from __future__ import annotations

from cadkit.board_geom import Boards, mask_rgb

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


def boards(geom_dir: str, **kw) -> Boards:
    """This project's `Boards`, with ITS tables on top of cadkit's."""
    return Boards(geom_dir, height=HEIGHT, tail=TAIL, **kw)
