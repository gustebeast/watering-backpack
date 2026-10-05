"""Does each board's CAD actually render the board that was ROUTED?

COPY THIS FILE TO YOUR PROJECT AS `elec/cad_geom_check.py`. `pcbflow/finish.py` runs it as
its last step (under your CAD Python), and your build gate should too:

    py -3.12 elec/cad_geom_check.py            # every board
    py -3.12 elec/cad_geom_check.py blinky     # one

THE ONE THING TO EDIT is `_cad()`: return the solid YOUR ASSEMBLY places for that board --
the function the build calls, in whatever frame it builds it. As shipped it returns
`Boards.solid(board)`, which proves the geom file loads and every part has a height, but
cannot catch what this check is for: an assembly that draws the board somewhere the
routed board is not (a stale hand-typed plate, a mirrored placement, a missing cutout).
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from cadkit.board_check import check          # noqa: E402
from cadkit.board_geom import Boards          # noqa: E402

# Heights for footprints cadkit's shared table does not carry yet. KiCad has no Z,
# so a footprint with no entry RAISES rather than being silently left out of the
# CAD — which is the behaviour we want. Every number says where it came from;
# an estimate is allowed, an unlabelled one is not (PCB_README).
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
    # MEASURED, not estimated: all five terminals are now the SAME part,
    # Ningbo Kangnex WJ500V-5.08-NP, whose customer drawing (LCSC C8465,
    # sheet 1/1) gives 14.07 mm above the board for the whole family. That
    # replaces the 17.0 / 15.0 guesses this table used to carry, and it
    # moves the right way: the PCB shroud needs 2.93 mm LESS standoff than
    # the old MKDS-3 estimate demanded.
    "TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal": 14.07,
    "TerminalBlock_Phoenix_MKDS-3-4-5.08_1x04_P5.08mm_Horizontal": 14.07,
    "TerminalBlock_Phoenix_MKDS-3-5-5.08_1x05_P5.08mm_Horizontal": 14.07,
    # ⚠ THE TALLEST PART ON THE BOARD, AND THE ONE THAT NOW SETS THE BAY DEPTH.
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
    "FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165":                21.6,
}

BOARDS = Boards(os.path.join(HERE, "geom"), height=HEIGHT)


def _cad(board):
    """The solid THE ASSEMBLY ACTUALLY PLACES for `board`.

    Pointed at src.housing, which is what src/build.py places. It used to point
    at src.pump_frame.pcb_solid, and that is worth spelling out: pump_frame put
    the board on the frame's +X face, from the printed-frame design. The housing
    puts it at x -219..-197 on the OTHER SIDE of the machine. So this check --
    the one whose entire job is catching "an assembly that draws the board
    somewhere the routed board is not" -- was itself aimed at a board that
    nothing places, and it passed.
    """
    from src import housing
    return {"main": housing.pcb_solid}[board]()


def main(names):
    names = names or sorted(os.path.basename(p)[:-len(".geom.json")]
                            for p in glob.glob(os.path.join(HERE, "geom", "*.geom.json")))
    bad = 0
    for b in names:
        try:
            bad += check(b, _cad(b), BOARDS.load(b))
        except Exception as exc:              # a board the check cannot read is a finding
            print("%-13s COULD NOT CHECK: %s" % (b, exc))
            bad += 1
    print("\n%s" % ("every routed part is where the CAD draws it" if not bad
                    else "*** %d DISAGREEMENT(S) BETWEEN THE CAD AND THE ROUTED BOARDS ***"
                    % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
