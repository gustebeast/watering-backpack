"""The order packages for this project's boards: gerbers, drill, BOM, CPL, one zip each.

COPY THIS FILE TO YOUR PROJECT AS `elec/fab.py`, then:

    "C:/Program Files/KiCad/10.0/bin/python.exe" elec/fab.py           # every board in BOARDS
    "C:/Program Files/KiCad/10.0/bin/python.exe" elec/fab.py blinky    # just one

(KiCad's own Python: the drill check reads the board with pcbnew.)

It refuses to package a board that is not finished (unconnected items, DRC violations, a
failed length-match), checks the gerbers and drill against the board, and writes
ROTATION-CHECK.txt, ORDER.txt and QUALITY.txt (the quality pass, cadkit/PCB_QUALITY.md)
into each zip. Pass `require_quality=True` to `configure` to refuse a package for a board
that is not at `0 FAIL, 0 OPEN`. See cadkit/pcbflow/fab_package.py.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from cadkit.pcbflow import fab_package as _fab  # noqa: E402

# Every board in the design. A package whose board is not listed here and has no
# generator is deleted as stale.
BOARDS = ("blinky",)

# The LCSC part number for every BOM row. A part chosen by its maker's number is keyed on
# that number as the netlist carries it; a passive is keyed on (value, footprint name),
# because one value is a different part in each package:
#     "B2B-XH-A": "C158012",
#     ("100n", "C_0603_1608Metric"): "C14663",
# Write a number here ONLY when you have read it off the listing yourself -- package,
# value, voltage, dielectric, tolerance -- and check stock the day you order.
LCSC = {
}

# Values that are placed but not yet sourced. A value that is neither in LCSC, nor a
# generic passive, nor listed here FAILS the build -- so a changed part number cannot slip
# through as "just another open item".
OPEN_VALUES = frozenset({
    "B2B-XH-A",          # JST XH 2-way top entry
    "RED",               # the indicator LED: pick a part, put its MPN in the generator
})

# require_codes=False ONLY because this example has not chosen its parts. A project that
# orders assembled boards leaves it at the default: a BOM row with no code is not left for
# the fab's order page to guess (see fab_package's docstring for what that guess did).
_fab.configure(HERE, BOARDS, LCSC, OPEN_VALUES, require_codes=False)

if __name__ == "__main__":
    _fab.main(sys.argv[1:] or list(BOARDS))
