"""A complete small board, to copy: power in, one LED, a test pad, one mounting hole.

COPY THIS FILE TO YOUR PROJECT AS `elec/blinky.py` (it writes beside itself), then:

    py -3.12 elec/blinky.py
    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/finish.py elec/out/blinky

The first line writes elec/out/blinky.net and elec/out/blinky.board.json. The second
places, routes, checks and labels the board (elec/out/blinky.kicad_pcb -- open it in
KiCad) and writes elec/geom/blinky.geom.json, which the CAD builds the board from:

    from cadkit.board_geom import Boards
    pcb = Boards("elec/geom").solid("blinky")

A board file has four parts, in this order: the CIRCUIT, the BOARD, the checks that tie
the board to the CAD it has to fit, and the QUALITY record (cadkit/PCB_QUALITY.md) --
what `finish.py` holds the board to before it may be ordered: `0 FAIL, 0 OPEN`.
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
    # power arrives down a cable: a capacitor beside the connector (quality rule A2)
    c1 = gen.part("C1", "100n", "Capacitor_SMD:C_0603_1608Metric", 2, "input bypass, 50 V X7R")
    gnd += j1["GND"], d1["K"], tp1[1], c1[2]
    vin += j1["VIN"], r1[1], c1[1]
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
        "C1": (-3.0, -2.0, 90.0),
        "R1": (2.0, 4.0, 0.0),
        "D1": (8.0, 4.0, 0.0),
        "TP1": (0.0, -5.0, 0.0),
    },
    # a ground pour on the back, pulled 0.3 in from the edge; GND pads stitch down to it
    "zones": [("GND", "B.Cu", 0.3)],
    "stitch_nets": ("GND",),
    "single_sided": True,                # every part on the front: one assembly setup
}

# ── 4. THE QUALITY RECORD ────────────────────────────────────────────────────────────
# cadkit/PCB_QUALITY.md is the rule list; `pcbflow/quality.py` (run by finish.py) holds
# the board to it. The automated rules read what is declared here; each manual rule is
# signed with WHAT WAS CHECKED AGAINST -- "checked" is not a sign-off.
BOARD_NOTES["quality"] = {
    # A1: every supply net -- where it enters, where it goes, how many amps
    "power_paths": [{"net": "VIN", "from": "J1.2", "to": "R1.1", "amps": LED_MA / 1000.0}],
    # A4: where each part with three or more pads had its pinout read (none here: J1 has
    # two, and its order is M1's business)
    "pinouts": {},
    "manual": {
        "M1": "J1 B2B-XH-A, JST drawing: pin 1 at the polarising slot = GND, pin 2 = VIN; "
              "the harness XHP-2 is crimped 1:1 and the housing is keyed",
        "M2": "D1 pad 1 = K in LED_0805_2012Metric and in the part's pin list ['K', 'A']",
        "M3": "GND returns on the B.Cu pour, unbroken under the VIN track",
        "M4": "C1 100 nF 50 V on a 5 V rail; no regulator and no stepping load",
        "M5": "5 V in; LED at 5 mA of 20 mA rated; R1 15 mW of 100 mW",
        "M6": "no high-speed nets",
        "M7": "no ICs",
        "M8": "no configuration pins",
        "M9": "TP1 is ground for a clip; VIN is reachable at J1",
        "M10": "bench-supplied indicator inside the enclosure: no ESD or reverse protection "
               "by decision; a reversed plug only leaves the LED dark (5 V = its max reverse)",
        "M11": "elec/cad_geom_check.py passes; J1 plugs from +Z with the board installed",
        "M12": "example board: not ordered",
        # M13 onward are each about one kind of circuit: sign the ones that do not apply
        # with the reason, in a line
        **{m: "no switching or linear regulator, inductor or ferrite on this board"
           for m in ("M13", "M14", "M15", "M17")},
        "M16": "5 V bench supply into 100 nF: 2 x 5 V = 10 V, under C1's 50 V and the "
               "LED's path is current-limited by R1",
        **{m: "no ICs, transistors, buses, converters, op-amps, USB or crystal"
           for m in ("M18", "M19", "M20", "M21", "M22", "M23", "M24", "M25", "M26",
                     "M27")},
        "M28": "no part with a variant pin order: two-pad parts and a 2-way header",
        "M29": "board rules are pcbflow's defaults = the fab's standard 2-layer limits; "
               "no via in a pad; R1/D1/C1 pads are track-fed, none in a pour",
        "M30": "example board: not ordered",
        "M31": "name + revision in silk (kicad_silk); D1's cathode mark is outside its body",
        "M32": "footprint pitch 2.50 = XH; 5 mA against XH's 3 A contacts",
        "M33": "one rail, one load: 5 mA from the bench supply",
        "M34": "no logic signals; D1 anode to R1, cathode to ground",
        "M35": "no parts with errata",
        "M36": "no power leaves the board",
        "M37": "example board: not ordered",
        "M38": "C1 is 12 mm from the nearest edge and 13 mm from the screw; J1 plugs from "
               "+Z with nothing above it",
    },
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
