"""pcbflow -- make a PCB from code: netlist + placements -> a placed, routed, checked board.

READ `cadkit/PCB_README.md` FIRST ("Making a board"); this is the map.

A board is ONE Python file in your project, `elec/<board>.py`, run under your normal CAD
Python. It describes the circuit with SKiDL and the board with a `BOARD_NOTES` dict
(outline, layers, WHERE EVERY PART GOES), and writes two files:

    elec/out/<board>.net          the netlist
    elec/out/<board>.board.json   the notes

Then one command, under KiCad's own Python, does the rest:

    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/finish.py elec/out/<board>

    (fab_package.py   the order package: gerbers, drill, BOM, CPL -- driven by your elec/fab.py)
    layout.py         netlist + notes -> <board>.kicad_pcb, every part placed, planes
                      poured and stitched, declared copper laid
    route.py          freerouting (headless) -> routed board, zones refilled
    repair_planes.py  ...around the post-route copper
    (DRC)             kicad-cli; unconnected count + violations, declared ones excepted
    close_last.py     maze-closes what the router left, kept only if DRC is strictly better
    silk.py           board name + revision, test-pad nets, connector pinouts
    verify.py         length-matched groups inside budget and on one layer set
    quality.py        THE STANDARD VALIDATION PASS, cadkit/PCB_QUALITY.md: supply choke
                      points and drop, bypass capacitors, pairs, pinout citations, and
                      the manual checklist the board's notes must sign
    export_geom.py    -> elec/geom/<board>.geom.json, which the CAD builds the board from
    cad_geom_check.py is the CAD's board the routed one? (your project supplies this)

The result is clean only at `0 unconnected, 0 violation(s)` with no verify FAIL, and
may be ORDERED only at `quality: 0 FAIL, 0 OPEN`.

    gen.py            helpers for the generator side (your CAD Python): begin / part / emit
    netcheck.py       netlist checks nothing else can see (return nets that never meet,
                      orphan pins); also classifies declared DRC violations
    repair_search.py  the obstacle model + maze search the repairs share
    example/blinky.py a complete small board to copy

These files are SCRIPTS that import each other by bare name from this folder; run them by
path. Only `gen` and `netcheck` are meant to be imported (`from cadkit.pcbflow import gen`).

NEEDS, per machine: KiCad 10 (its python.exe and kicad-cli), a Java 25 runtime and
freerouting.jar at %LOCALAPPDATA%\\Programs\\freerouting\\ (or $FREEROUTING_JAR), and
SKiDL in the CAD Python (`pip install skidl`).

PROVENANCE. This pipeline was built on a fourteen-board instrument and its comments keep
the case histories that shaped each rule -- "the optical board", "output_panel",
"lever_sensor" and so on are THAT project's boards, kept because the reason for a rule is
worth more than a tidy comment. Nothing in the code depends on them.
"""
