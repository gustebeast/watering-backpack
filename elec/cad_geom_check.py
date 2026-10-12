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

# ⚠ THE SECOND COPY OF THE HEIGHT TABLE USED TO LIVE HERE, and the first copy's
# own comment is the reason it no longer does: "renaming the footprint failed
# the geometry gate from HERE after the other one was already fixed -- 'no
# HEIGHT for ...-PINFIT'. Two tables keyed by footprint name is one table too
# many; whichever is touched next should take the other with it."
#
# There is one table now, src/board_parts.py, and the SAME object is handed to
# this gate and to the solid the assembly places -- which is the only way this
# gate's answer means anything. It compares the CAD to the routed board; if it
# compared them through a different height table, the two could agree here and
# differ in the assembly, which is exactly what happened.
from src.board_parts import HEIGHT, TAIL     # noqa: E402

BOARDS = Boards(os.path.join(HERE, "geom"), height=HEIGHT, tail=TAIL)


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


def _ink(board):
    """The LETTERING the assembly places for `board`, in the SAME frame as _cad().

    Both faces, because the check asks for every label's ink and this board prints
    on both: the designators and net words on F, the five terminal legends on B
    where a person reads them while screwing a wire down.

    ⚠ THIS HOOK IS WHY THE SILK IS DRAWN AT ALL. The owner's note was "there is
    no silkscreen in cad", and the answer was housing.pcb_silk() -- but a part the
    assembly merely adds is a picture. Passing it HERE is what makes it a claim:
    every label the router printed has to have ink somewhere in this solid, in the
    housing's frame, so silk that is missing, stale or posed wrong is a finding
    rather than something nobody looks at. It found 104 of them the first time it
    ran, which was the whole F-side set -- drawn, but never checked against.
    """
    from src import housing
    return [p for p in (housing.pcb_silk("F"), housing.pcb_silk("B"))
            if p is not None]


def main(names):
    names = names or sorted(os.path.basename(p)[:-len(".geom.json")]
                            for p in glob.glob(os.path.join(HERE, "geom", "*.geom.json")))
    bad = 0
    for b in names:
        try:
            bad += check(b, _cad(b), BOARDS.load(b), ink=_ink(b))
        except Exception as exc:              # a board the check cannot read is a finding
            print("%-13s COULD NOT CHECK: %s" % (b, exc))
            bad += 1
    print("\n%s" % ("every routed part is where the CAD draws it" if not bad
                    else "*** %d DISAGREEMENT(S) BETWEEN THE CAD AND THE ROUTED BOARDS ***"
                    % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
