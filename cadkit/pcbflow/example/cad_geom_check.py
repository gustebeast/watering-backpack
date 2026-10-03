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

BOARDS = Boards(os.path.join(HERE, "geom"))


def _cad(board):
    """The solid the assembly places for `board`. REPLACE with your own, e.g.

        from src import electronics
        return {"blinky": electronics.blinky_pcb}[board]()
    """
    return BOARDS.solid(board)


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
