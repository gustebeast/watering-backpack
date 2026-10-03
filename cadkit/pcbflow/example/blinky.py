"""A complete small board, to copy: power in, one LED, a test pad, one mounting hole.

COPY THIS FILE TO YOUR PROJECT AS `elec/blinky.py` (it writes beside itself), then:

    py -3.12 elec/blinky.py
    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/finish.py elec/out/blinky

The first line writes elec/out/blinky.net and elec/out/blinky.board.json. The second
places, routes, checks and labels the board (elec/out/blinky.kicad_pcb -- open it in
KiCad) and writes elec/geom/blinky.geom.json, which the CAD builds the board from:

    from cadkit.board_geom import Boards
    pcb = Boards("elec/geom").solid("blinky")

A board file has three parts, in this order: the CIRCUIT, the BOARD, and the checks that
tie the board to the CAD it has to fit.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cadkit.pcbflow import gen  # noqa: E402

OUT_DIR = gen.begin(__file__)           # before skidl is imported -- see gen.begin

from skidl import Net  # noqa: E402

# ── 1. THE CIRCUIT ───────────────────────────────────────────────────────────────────
# Parts are defined inline with exactly the pins they have, so the file needs no symbol
# library. Give every figure its reason: a board file is the design record.
LED_MA = 5.0
VIN, V_LED = 5.0, 2.0                    # a red 0805 at 5 mA
R_LED = "%.0fR" % ((VIN - V_LED) / (LED_MA / 1000.0))      # 600R


def circuit():
    gnd, vin, led_a = Net("GND"), Net("VIN"), Net("LED_A")
    gen.power(gnd, vin)
    j1 = gen.part("J1", "B2B-XH-A", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
                  ["GND", "VIN"], "power in, 5 V")
    r1 = gen.part("R1", R_LED, "Resistor_SMD:R_0603_1608Metric", 2, "LED current, 5 mA")
    d1 = gen.part("D1", "RED", "LED_SMD:LED_0805_2012Metric", ["K", "A"], "power indicator")
    tp1 = gen.part("TP1", "TP", "TestPoint:TestPoint_Pad_D1.5mm", 1, "probe ground")
    gnd += j1["GND"], d1["K"], tp1[1]
    vin += j1["VIN"], r1[1]
    led_a += r1[2], d1["A"]


# ── 2. THE BOARD ─────────────────────────────────────────────────────────────────────
# Millimetres, board-centred, +Y UP (the CAD's frame, not KiCad's). In a real project
# these numbers come FROM THE MECHANICAL MODEL -- import your dimensions module here and
# derive the outline and the connector positions from the pocket the board sits in.
BOARD_W, BOARD_L = 30.0, 20.0
HOLE_XY, HOLE_D = (10.0, -5.0), 4.5      # one M4 clearance hole THROUGH the board

BOARD_NOTES = {
    "outline_mm": (BOARD_W, BOARD_L),
    "cutouts": [{"xy": HOLE_XY, "d": HOLE_D}],
    "layers": 2,
    "thickness_mm": 1.6,
    # ref: (x, y, rotation) -- of the part's PAD CENTROID, KiCad rotation in degrees
    "placements": {
        "J1": (-8.0, 2.0, 0.0),
        "R1": (2.0, 4.0, 0.0),
        "D1": (8.0, 4.0, 0.0),
        "TP1": (0.0, -5.0, 0.0),
    },
    # a ground pour on the back, pulled 0.3 in from the edge; GND pads stitch down to it
    "zones": [("GND", "B.Cu", 0.3)],
    "stitch_nets": ("GND",),
    "single_sided": True,                # every part on the front: one assembly setup
}

# ── 3. THE CHECKS ────────────────────────────────────────────────────────────────────
# Anything this board must satisfy that DRC cannot see goes here as an ASSERTION, so a bad
# placement stops the generator instead of surfacing an hour later in the CAD's overlap
# gate: the hole inside the outline with a wall of laminate round it, parts clear of a
# printed wall that comes down onto the board, through-hole tails over the support, the
# outline equal to the pocket the CAD cuts for it.
_EDGE = min(BOARD_W / 2.0 - abs(HOLE_XY[0]), BOARD_L / 2.0 - abs(HOLE_XY[1])) - HOLE_D / 2.0
assert _EDGE >= 1.5, "the mounting hole leaves only %.2f mm of laminate to the edge" % _EDGE


if __name__ == "__main__":
    circuit()
    gen.emit("blinky", OUT_DIR, BOARD_NOTES)
