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
    # ESTIMATE -- replace when a terminal block is in hand and can be measured.
    # These set how far the PCB shroud must stand off the board face, so an
    # estimate here is a real tolerance, not a cosmetic one.
    "TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal":  17.0,  # ESTIMATE
    "TerminalBlock_Phoenix_PT-1,5-4-3.5-H_1x04_P3.50mm_Horizontal": 15.0,  # ESTIMATE
    "TerminalBlock_Phoenix_PT-1,5-5-3.5-H_1x05_P3.50mm_Horizontal": 15.0,  # ESTIMATE
}

BOARDS = Boards(os.path.join(HERE, "geom"), height=HEIGHT)


def _cad(board):
    """The solid THE ASSEMBLY ACTUALLY PLACES for `board`.

    Pointed at src.pump_frame rather than left at the shipped BOARDS.solid(),
    which can only prove the geom loads and every part has a height. This version
    catches what the check exists for: an assembly that draws the board somewhere
    the routed board is not — a mirrored placement, a stale outline, a missing
    cutout.
    """
    from src import pump_frame
    return {"main": pump_frame.pcb_solid}[board]()


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
