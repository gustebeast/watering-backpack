"""The generator side of pcbflow: what every `elec/<board>.py` does, written once.

Runs under your CAD Python (it needs SKiDL, not pcbnew):

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cadkit.pcbflow import gen
    OUT = gen.begin(__file__)              # BEFORE anything imports skidl
    from skidl import Net

    j1 = gen.part("J1", "B2B-XH-A", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
                  ["GND", "VIN"], "power in")
    ...
    gen.emit("blinky", OUT, BOARD_NOTES)

See `example/blinky.py` for a whole board, and cadkit/PCB_README.md for BOARD_NOTES.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netcheck  # noqa: E402

_REFS = []          # every ref part() has made, for emit()'s placement check


def begin(generator_file, out="out"):
    """Make `<generator's folder>/out`, chdir into it, return its path.

    CALL THIS BEFORE THE FIRST `import skidl`. SKiDL names its log, ERC report and
    generated part library after the script and drops them in the CWD -- the log at
    IMPORT time -- and every derived file belongs in the (git-ignored) out folder, not
    beside the source.
    """
    out_dir = os.path.join(os.path.dirname(os.path.abspath(generator_file)), out)
    os.makedirs(out_dir, exist_ok=True)
    os.chdir(out_dir)
    return out_dir


def part(ref, value, footprint, pins, desc=""):
    """One part, defined inline -- no symbol library needed, so a board file is complete
    in itself and a part is exactly the pins you say it has.

    `ref`        "R1", "U3", "J2": prefix + number; also the key in BOARD_NOTES placements
    `value`      what the BOM calls it (a value for passives, the MPN otherwise)
    `footprint`  "Library:Footprint" -- a KiCad library, or `<lib>.pretty` in the project's
                 `elec/footprints/`
    `pins`       a pin COUNT (pins "1".."n"), a list of NAMES (numbered from 1), or a
                 dict {number: name} for packages whose pad names are not 1..n ("A5",
                 "SH"). Index the part by number or by name: `u1[3]`, `j1["VIN"]`.
    """
    from skidl import Part, Pin
    if isinstance(pins, int):
        pin_list = [Pin(num=i + 1, func=Pin.types.PASSIVE) for i in range(pins)]
    elif isinstance(pins, dict):
        pin_list = [Pin(num=k, name=v, func=Pin.types.PASSIVE) for k, v in pins.items()]
    else:
        pin_list = [Pin(num=i + 1, name=n, func=Pin.types.PASSIVE)
                    for i, n in enumerate(pins)]
    prefix = ref.rstrip("0123456789")
    _REFS.append(ref)
    return Part(name=value, ref_prefix=prefix, ref=ref, tag=ref, dest="NETLIST",
                tool="skidl", value=value, description=desc, footprint=footprint,
                pins=pin_list)


def power(*nets):
    """Mark nets as power-driven, so ERC does not report every rail as undriven."""
    from skidl import Pin
    for n in nets:
        n.drive = Pin.drives.POWER
    return nets


def emit(board, out_dir, notes, declared_split=None):
    """Write `<board>.net` and `<board>.board.json`, after the checks that have to pass.

    ERC, then netcheck: every return net must reach the others (two grounds that never
    meet route cleanly and do not work), and no pin may be the only one on its net by
    accident. `declared_split` is netcheck.grounds_meet's -- for a ground split the board
    means and cannot close on its own; it prints on every run.

    Refuses a placement table that does not match the parts made with part(): a part
    with no placement never reaches the board, and a placement with no part is a typo.
    (Parts built with SKiDL's own Part() are not seen by this check.)
    """
    from skidl import ERC, generate_netlist
    refs = set(_REFS)
    placed = set(notes.get("placements", {}))
    if refs and refs - placed:
        raise SystemExit("%s: no placement for %s" % (board, ", ".join(sorted(refs - placed))))
    if refs and placed - refs:
        raise SystemExit("%s: placements for parts that are not in the circuit: %s"
                         % (board, ", ".join(sorted(placed - refs))))
    ERC()
    net = os.path.join(out_dir, board + ".net")
    generate_netlist(file_=net)
    netcheck.grounds_meet(net, declared_split=declared_split)
    netcheck.no_orphan_pins(net)
    with open(os.path.join(out_dir, board + ".board.json"), "w", encoding="utf-8") as fh:
        json.dump(notes, fh, indent=2)
    w, l = notes["outline_mm"]
    print("%s: board %.1f x %.1f mm, %d parts" % (board, w, l, len(placed)))
    return net
