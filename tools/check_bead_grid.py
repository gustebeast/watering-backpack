#!/usr/bin/env python3
"""Every printed length in the housing, against the bead grid.

cadkit/AGENTS.md, "The bead GRID":

    Every printed length is either N x BEAD, or another feature +- N x BEAD.

The reason is Arachne. A 3.0 mm wall at a 0.8 mm nozzle is 3.75 beads, and the
slicer resolves that by stretching three beads to 1.0 each or starving in a
fourth -- so the section of a load-bearing wall is chosen by the slicer rather
than by the drawing, and the improvised bead is where the part delaminates.

`src/housing.py` carried 3.0 on every wall, plate, lid and skirt before this
gate existed, and not one of those was a decision: 3.0 is just a round number in
millimetres, which is the one unit the printer does not work in.

WHAT IS EXEMPT, AND WHY IT HAS TO BE DECLARED. AGENTS.md names three kinds of
legitimately off-grid length -- hardware, clearance, and standards -- and says
why they have to carry their reason: *a bare off-grid number is indistinguishable
from an oversight*. So this gate does not skip a constant because of its name. It
skips it because EXEMPT below says which kind it is and why, one line each, and
it fails on an exemption that has gone stale just as it fails on an off-grid wall.

`src/battery_dock.py` is exempt wholesale and that is the clearest case of the
three: its sections match the Makita pack and the adapter that mates with it.
Rounding those to a bead would not print better, it would make the model lie
about what has to fit.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from cadkit.printing import on_grid, snap          # noqa: E402
from src import housing as H                       # noqa: E402

# Printed MATERIAL in src/housing.py: every length that ends up as extruded
# plastic. Add to this list when you add a dimension, not when it breaks.
MATERIAL = [
    "WALL", "BACK_T", "LID_T", "SKIRT_T", "STANDOFF", "BOSS_D",
    "RET_STOP_T", "RET_OVER", "RET_LEN", "RET_TIP_T", "RET_STOP_OVER",
    "SKIRT_D", "LID_CSK_T", "LID_BOSS_W", "LID_BOSS_H",
]

# name -> (kind, why). Kinds are AGENTS.md's own three.
EXEMPT = {
    "BOARD_T": ("hardware", "the laminate is 1.6 mm because a PCB is 1.6 mm"),
    "LID_GAP": ("clearance", "air over the tallest part; no bead crosses a gap"),
    "SKIRT_CLR": ("clearance", "the skirt-to-bay slip fit"),
    "RET_CLR": ("clearance", "air over the laminate at the lip's root"),
    "RET_ROOT_GAP": ("clearance", "lip root to the board's +Y edge"),
    "RET_STOP_CLR": ("clearance", "air between a Z stop and the laminate"),
    "PCB_CLR": ("clearance", "board edge to cavity wall"),
    "BOARD_SLIDE_Y": ("clearance", "how far the board slides to clear the lip"),
    "WOOD_HEAD_D": ("hardware", "the screw head is Ø9.3 whatever the nozzle is"),
    "WOOD_CLR_D": ("clearance", "shaft clearance round a Ø4.0 screw"),
    "WOOD_CSK_D": ("clearance", "a pocket cut for a real head, not a wall"),
    "WOOD_CSK_CLR": ("clearance", "the 0.3 round that head"),
    "LID_BORE_D": ("clearance", "an access bore sized to pass the Ø9.3 head"),
    "WIRE_SLOT_W": ("clearance", "a hole sized by the conductors through it"),
    "WIRE_SLOT_H": ("clearance", "same hole, the other axis"),
    "BOOL_OVERSHOOT": ("standards", "a modelling epsilon, never a printed face"),
}


def main():
    bead = H.BEAD
    print("=== bead grid: src/housing.py printed material, %.1f mm nozzle ==="
          % bead)
    bad, n = [], 0
    for name in MATERIAL:
        if not hasattr(H, name):
            bad.append("%s is on the MATERIAL list but no longer exists in "
                       "src/housing.py -- the list is stale" % name)
            continue
        if name in EXEMPT:
            bad.append("%s is on BOTH the MATERIAL list and the EXEMPT table, "
                       "so the gate cannot say which it is" % name)
            continue
        v = getattr(H, name)
        n += 1
        if on_grid(v, bead):
            print("  %-15s %6.2f  = %4.1f beads" % (name, v, v / bead))
        else:
            bad.append("%s is %.2f mm = %.2f beads. Arachne cannot lay that; "
                       "nearest whole beads are %.2f and %.2f"
                       % (name, v, v / bead, snap(v, bead, "down"),
                          snap(v, bead, "up")))

    print("\n=== declared off-grid, with the reason AGENTS.md asks for ===")
    for name in sorted(EXEMPT):
        kind, why = EXEMPT[name]
        if not hasattr(H, name):
            bad.append("%s is declared exempt (%s: %s) but is not in "
                       "src/housing.py any more -- the excuse outlived the "
                       "number, and a stale excuse hides the next real one"
                       % (name, kind, why))
            continue
        v = getattr(H, name)
        n += 1
        if on_grid(v, bead):
            print("  %-15s %6.2f  %-9s on the grid anyway" % (name, v, kind))
        else:
            print("  %-15s %6.2f  %-9s %s" % (name, v, kind, why))

    # The dock is exempt as a whole, and that is worth printing rather than
    # leaving silent: silence is what an oversight looks like.
    print("\n  src/battery_dock.py  NOT CHECKED -- hardware. Its sections mate "
          "with the\n  Makita pack and its adapter, and a bead-rounded section "
          "would make the\n  model lie about what has to fit.")

    print("\n%d length(s) checked" % n)
    if bad:
        print("\n*** %d OFF THE GRID ***" % len(bad))
        for b in bad:
            print("   " + b)
        return 1
    print("every printed length is a whole number of beads, or says why not")
    return 0


if __name__ == "__main__":
    sys.exit(main())
