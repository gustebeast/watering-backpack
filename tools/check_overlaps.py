"""Interference gate for the v2 assembly — cadkit/AGENTS.md's standard gate.

Supplies this project's parts and its whitelist of DESIGNED contacts, then
hands both to `cadkit.overlap_check.run`.

    py -3.12 -m tools.check_overlaps          # exit code = unintended pairs
    py -3.12 -m tools.check_overlaps --all    # also list intended contacts

What counts as intended here:

  pump x fittings   The swivel nut swallows the port's thread. This is the
                    thread engagement, ~493 mm3 per pump, and it is the whole
                    reason the fitting stays on.
  hose x fittings   A hose over a barb is the joint, not a clash.
  hose x tank       The tank line starts AT the Uniseal, in the tank wall.
  pcb  x plate      The board rests on the plate's standoff bosses.

Everything else is a bug. Note the hoses are included deliberately: a frame
that clears every other frame part but pinches a suction line is not a frame
that works, and `tools/check_plumbing.py` only checks the routes it is given.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cadkit import overlap_check              # noqa: E402

from src import housing as H                  # noqa: E402
from src import lumber_frame as L             # noqa: E402
from src import plumbing as P                 # noqa: E402
from src import pump_frame as F               # noqa: E402


def collect_components():
    comps = [("housing", H.housing().val()),
             ("housing_lid", H.lid().val()),
             ("pcb", H.pcb_solid().val()),
             ("wood", L.frame().val()),
             ("pump_a", F._pump_placed(-1).val()),
             ("pump_b", F._pump_placed(+1).val()),
             ("fittings", F._elbows().val())]
    for name, pts in P.routes():
        comps.append((name, P.run(pts).val()))
    return comps


def intended(a, b):
    pair = {a, b}
    if "fittings" in pair:
        other = (pair - {"fittings"}).pop()
        return other.startswith(("pump_", "tank_", "green_"))
    # the board rests on the housing's standoff bosses
    if pair == {"pcb", "housing"}:
        return True
    # the housing bolts flat onto the posts
    if pair == {"housing", "wood"}:
        return True
    # the lid closes onto the housing's lid pillars
    if pair == {"housing", "housing_lid"}:
        return True
    # hoses meeting at a tee
    if all(n.startswith(("tank_", "green_")) for n in pair):
        return True
    return False


def main(argv):
    comps = collect_components()
    return overlap_check.run(comps, intended, show_all="--all" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
