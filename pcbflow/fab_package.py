"""Fab outputs — gerbers, drill, BOM and CPL, one zip per board.

    "C:/Program Files/KiCad/10.0/bin/python.exe" elec/fab.py              # every board
    "C:/Program Files/KiCad/10.0/bin/python.exe" elec/fab.py controller   # just one

(`elec/fab.py` is your project's entry point -- see pcbflow/example/fab.py.)

THE PROJECT SUPPLIES THE TABLES, this file the machinery. A project's `elec/fab.py` holds
which boards exist and which part number each VALUE is ordered as, hands them to
`configure()`, and calls `main()`. Sourcing is a per-project decision and a per-day fact
(stock moves), so it is deliberately not shared.

RUNS UNDER KiCad's OWN PYTHON: most of it shells out to kicad-cli or reads text, but the
drill check loads the board with pcbnew to count the holes the file must contain.

WHAT THIS IS FOR. The board files are the design; THIS is the handoff. Until it
existed the project had five routed, DRC-clean boards and no way to order any of
them -- which is a pipeline that looks finished and is not. It is deliberately
run BEFORE the last board is designed, so that a problem here (a layer name JLCPCB
rejects, a rotation convention, a missing sourcing decision) is found once rather
than once per board.

⚠ RUN END TO END FROM A CLEAN REGENERATION, 2026-09-19, and this is the claim the
pipeline makes about itself: regenerate every netlist from its generator, route all five
boards, package all five, with nothing carried over from a previous state. Result:

    can_tee       0 unconnected  0 violations                     3 placements
    lever_sensor  0              0            1 silk_overlap     28
    motor_ctrl    0              0                               59
    output_panel  0              0            1 hole_to_hole     60   verify 4/0
    optical       0              0                              156   verify 2/0

Both warnings are recorded as deliberate keeps where they live. Every check in this file
passed silently -- drill hits against holes, poured zones against declared zones, the
In1.Cu plane whole on all four 4-layer boards, paste apertures against pads on the paste
layer, mask openings never short -- and BOM.md agreed with all five packages.

That is the whole point of writing the judgement calls down as CHECKS rather than doing
them by eye: the run above needed no human in it, and the next one will not either.

⚠ ROTATION IS THE CLASSIC WAY TO LOSE A BOARD, and it is NOT fully solvable here.
KiCad's position file gives the footprint's rotation in the KiCad footprint's own
frame; JLCPCB's placement machine wants it in the LCSC part's frame, and for many
parts those differ by 90/180/270. There is no general rule -- it is per part, and
the honest workflow is to CHECK EVERY PART in JLCPCB's online previewer before
paying. This file emits the KiCad convention unmodified and says so in the CPL
header, rather than applying guessed corrections that would be invisible later.

EVERY BOM ROW CARRIES A PART NUMBER, OR THERE IS NO PACKAGE (2026-10-06). This used to
say the opposite: generic passives went out with an EMPTY code cell, "chosen at order
time", on the reasoning that a blank stops the order and a wrong number ships. A dry run
of a real order showed the blank does not stop anything. JLCPCB's matcher fills it in by
itself, from the footprint text, and read `C_0402_1005Metric` as the 01005 that string
also contains: a 100 nF row became a 01005 6.3 V part and a 10 k row a 01005 resistor.
Both are parts the Economic assembly service does not place, so they arrived UNSELECTED
at quantity 0, and pressing Next builds the board without them. Nothing on the page says
so in red.

So a blank is a guess made by somebody else's software, and the rule is now: the project's
table names a part for every row, keyed on (value, footprint) for passives because one
value is several parts ("100nF" is an 0402 on one board and an 0805 on another, and
"4.7uF/50V" comes in two sizes). A row with no code refuses the build. The Footprint
column also carries the plain package ("0402"), not KiCad's name, so the matcher has
nothing to misread.
"""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import zipfile

FLOW = os.path.dirname(os.path.abspath(__file__))
KICAD_CLI = os.environ.get("KICAD_CLI") or r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
KICAD_PY = os.environ.get("KICAD_PYTHON") or os.path.join(os.path.dirname(KICAD_CLI),
                                                          "python.exe")

# ── SET BY configure() ───────────────────────────────────────────────────────────────
HERE = None              # the project's generator folder (elec/): <board>.py lives here
OUT_DIR = None           # <HERE>/out -- routed boards, netlists, board.json
FAB_DIR = None           # <OUT_DIR>/fab -- one folder and one zip per board
BOARDS = ()              # every board in the design, by name
# LCSC part number for every BOM row. Two kinds of key in one table:
#   "MPN-as-the-netlist-carries-it"        -> code     (a part chosen by its part number)
#   ("value", "KiCad footprint name")      -> code     (a passive chosen by value AND size)
# The pair is looked up first. ONLY codes a human checked against the catalogue.
LCSC = {}
# A row with no code refuses the package (see the module docstring for what a blank does
# at the fab). False only for a project that is not ordering assembled boards.
REQUIRE_CODES = True
# ⚠ EVERY VALUE STRING MUST BE ACCOUNTED FOR -- IN LCSC, GENERIC, OR HERE. A value that is
# neither sourced nor generic nor declared open FAILS THE BUILD, so changing a part number
# forces you to say so. (The case: a connector kept its OLD part number in `value` after
# its footprint changed, and the BOM reads `value` -- nothing else in the pipeline does.)
OPEN_VALUES = frozenset()
# Order-form choices that apply to every board; none is in a gerber. (key, text) pairs,
# written into each package's ORDER.txt. A board adds its own via BOARD_NOTES
# "order_options".
ORDER_EVERY_BOARD = (
    ("mark", "Remove Mark (the fab's order number). Left on, it is printed wherever the "
             "fab finds room."),
    ("rails", "Edge rails and fiducials: Added by JLCPCB. No board carries its own "
              "fiducials, and small ones are assembled in a panel the fab makes."),
    ("placement", "Confirm Parts Placement: Yes. An engineer checks polarity and rotation "
                  "before the run; ROTATION-CHECK.txt is the list to compare against."),
    ("prod file", "Confirm Production File: Yes. The last look at the panel before it is cut."),
)
AFTER = None             # optional callable(names), run after a build (a BOM-document check)
# Refuse to leave a package behind for a board that is not quality-clean (0 FAIL, 0 OPEN;
# see cadkit/PCB_QUALITY.md). Off by default: the report is always written and printed.
REQUIRE_QUALITY = False


def configure(project_dir, boards, lcsc, open_values=(), order_every_board=None, after=None,
              require_quality=False, require_codes=True):
    """Point this module at a project. `project_dir` is the generator folder (elec/)."""
    global HERE, OUT_DIR, FAB_DIR, BOARDS, LCSC, OPEN_VALUES, ORDER_EVERY_BOARD, AFTER
    global REQUIRE_QUALITY, REQUIRE_CODES
    REQUIRE_QUALITY = bool(require_quality)
    REQUIRE_CODES = bool(require_codes)
    HERE = os.path.abspath(project_dir)
    OUT_DIR = os.path.join(HERE, "out")
    FAB_DIR = os.path.join(OUT_DIR, "fab")
    BOARDS, LCSC, OPEN_VALUES = tuple(boards), dict(lcsc), frozenset(open_values)
    if order_every_board is not None:
        ORDER_EVERY_BOARD = tuple(order_every_board)
    AFTER = after


# Layer sets by copper count. JLCPCB takes the KiCad extensions directly.
L2 = "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"
L4 = ("F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,"
      "F.Mask,B.Mask,Edge.Cuts")

# Generic passives: parts chosen by value and package rather than by a maker's number.
# They still need a code each (REQUIRE_CODES); the pattern only decides how a missing one
# is described and which rows the placeholder rule applies to.
GENERIC = re.compile(r"^(R_|C_|Fuse_|Jumper:|Diode_SMD:D_SOD|Diode_SMD:D_SM[AB]|"
                     r"Inductor_SMD|Crystal:)")
# ⚠ ONLY PASSIVES ARE VALUE-CHOSEN. An 0402 is picked from its value; an LED in an 0805
# land is picked from its part number, and "IR17-21C/TR8" is a perfectly good value that
# simply does not start with a digit. The placeholder rule below applies to this subset.
PASSIVE = re.compile(r"^(R_|C_|L_|Inductor_SMD)")
# Footprint LIBRARIES that hold no orderable part -- see the BOM loop.
# ⚠ Jumper BELONGS HERE AND WAS MISSING. A SolderJumper is a BOARD FEATURE: two pads and
# a mask opening, closed with solder by whoever assembles it. There is nothing to buy and
# nothing to place. It was reaching the BOM as a line reading Comment "TERM", footprint
# "SolderJumper-2_P1.3mm_Open...", and NO part number -- an order asking a fab to source
# a part that does not exist. can_tee carried one, motor_ctrl two.
#
# It slipped past the placeholder guard because that guard only fires on PASSIVES, and a
# jumper is "generic" (the GENERIC pattern lists Jumper:) without being a passive. So
# "TERM" -- a value that cannot pick a part -- was accepted. The CPL was right all along
# and omitted them, which is how the discrepancy showed: BOM designators 4 against CPL 3.
COPPER_ONLY = re.compile(r"^(TestPoint|NetTie|Fiducial|SolderJumper|Jumper)")
# KiCad's chip footprint names carry BOTH codes, imperial then metric: C_0402_1005Metric.
# A matcher that reads the row as text finds "1005" in it, and 01005 is a real, different
# package. The BOM's Footprint column says the one thing a person would: "0402".
_CHIP = re.compile(r"^(?:[A-Z][A-Za-z]*_)+(\d{4})_\d{4}Metric")


def code_for(val, fp):
    """The table's code for a BOM row: (value, footprint name) first, then the value."""
    name = fp.split(":", 1)[-1]
    return LCSC.get((val, name)) or LCSC.get(val, "")


def package_name(fp):
    """What the BOM's Footprint column says: '0402' for a chip, KiCad's name otherwise."""
    name = fp.split(":", 1)[-1]
    m = _CHIP.match(name)
    return m.group(1) if m else name


def _run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("kicad-cli failed:\n  %s\n%s" % (" ".join(args), r.stderr[-800:]))
    return r.stdout


def _parts(stem):
    """[(ref, value, footprint)] from the netlist -- the same file the board was
    laid out from, so the BOM cannot describe a different build than the gerbers."""
    t = open(stem + ".net", encoding="utf-8").read()
    out = []
    for m in re.finditer(r'\(comp\s*\(ref "([^"]+)"\)\s*\(value "([^"]*)"\).*?'
                         r'\(footprint "([^"]+)"\)', t, re.S):
        out.append(m.groups())
    return sorted(out)


def _layers(stem):
    return L4 if json.load(open(stem + ".board.json", encoding="utf-8"))["layers"] == 4 else L2


def fab(board):
    stem = os.path.join(OUT_DIR, board)
    pcb = stem + ".kicad_pcb"
    if not os.path.isfile(pcb):
        raise SystemExit("no routed board at %s -- run layout.py and route.py first" % pcb)
    # ⚠ A PLACED BOARD IS NOT A FINISHED BOARD, and gerbers do not say so. The board
    # file exists as soon as layout.py runs; export it before route.py has been through
    # and you get a clean-looking package with no tracks in it -- which is precisely the
    # "pipeline that looks finished and is not" this file was written against. DRC is
    # what knows the difference, so ask it rather than trusting that the step was run.
    r = subprocess.run([KICAD_CLI, "pcb", "drc", "--exit-code-violations", pcb],
                       capture_output=True, text=True)
    unrouted = re.search(r"Found (\d+) unconnected", r.stdout or "")
    if unrouted and int(unrouted.group(1)):
        n = int(unrouted.group(1))
        tracks = sum(1 for ln in open(pcb, encoding="utf-8") if ln.lstrip().startswith("(segment"))
        # ⚠ SAY WHICH OF THE TWO FAILURES THIS IS. They need opposite responses and
        # the message used to assert the first one flatly: a board that was never routed
        # arrives as bare copper and wants route.py; a board that WAS routed and has
        # three nets left wants a look at those three nets, and being told to "run
        # route.py first" sends you to re-run a step that already ran. Track count is
        # what distinguishes them, and it costs one pass over a file already on disk.
        # ⚠ AND TAKE THE OLD PACKAGE WITH IT. Refusing to WRITE a zip leaves any
        # previous one sitting in fab/ looking exactly like a current one -- which is
        # the same "looks complete and arrives incomplete" failure this refusal exists
        # to prevent, arriving by the back door. lever_sensor.zip survived here from
        # 2026-09-17, two days and a BOOT0 rework out of date, describing a board that
        # no longer exists. A board that cannot be packaged must not appear packaged.
        _stale = os.path.join(FAB_DIR, "%s.zip" % board)
        if os.path.isfile(_stale):
            os.remove(_stale)
            print("  removed the previous %s.zip -- it describes an older board and "
                  "this one cannot be packaged" % board)
        raise SystemExit(
            "%s: %d unconnected item(s) -- %s. A fab package built from it would look "
            "complete and arrive incomplete."
            % (board, n,
               "this board has NO routing at all; run elec/route.py on it first"
               if tracks == 0 else
               "the board IS routed (%d segments) but the router could not finish "
               "these nets. Re-running route.py will not help -- it is deterministic "
               "now and will make the same choices. Look at the nets themselves"
               % tracks))

    # ⚠ AND DRC IS NOT THE WHOLE TEST EITHER. It answers "is this manufacturable",
    # not "is this correct": a router can hand back a DRC-perfect board on which the
    # USB pair is split across two layers and took two unrelated paths. elec/verify.py
    # is where the checks a PERSON would otherwise make by eye are written down, and
    # running it HERE is what stops it being a script nobody remembers to run. Boards
    # that declare no budgets pass it trivially, so this costs them nothing.
    v = subprocess.run([KICAD_PY, os.path.join(FLOW, "verify.py"), stem],
                       capture_output=True, text=True)
    if v.returncode:
        # ⚠ AND THE STALE ZIP GOES HERE TOO. The unconnected-items refusal above
        # deletes it, on the principle that a board which cannot be packaged must not
        # appear packaged -- and this refusal, added later, did not. Found by making a
        # budget fail on purpose to check the gate bites: it does, and it left the
        # previous output_panel.zip in the fab directory, described by nothing. A
        # refusal that leaves the artefact behind is the weaker half of a gate.
        _stale = os.path.join(FAB_DIR, "%s.zip" % board)
        if os.path.isfile(_stale):
            os.remove(_stale)
            print("  removed the previous %s.zip -- it describes an older board and "
                  "this one cannot be packaged" % board)
        raise SystemExit("%s: FAILED its declared high-speed budgets --\n%s"
                         % (board, (v.stdout or "") + (v.stderr or "")[-400:]))

    d = os.path.join(FAB_DIR, board)
    os.makedirs(d, exist_ok=True)

    _run([KICAD_CLI, "pcb", "export", "gerbers", "-o", d + os.sep,
          "--layers", _layers(stem), "--no-x2", "--subtract-soldermask", pcb])
    # Excellon, mm, 2:4, PTH and NPTH in ONE file: JLCPCB accepts merged and it
    # removes the commonest upload mistake, which is forgetting the NPTH file and
    # getting a board with no mounting holes.
    _run([KICAD_CLI, "pcb", "export", "drill", "-o", d + os.sep, "--format", "excellon",
          "--drill-origin", "absolute", "--excellon-units", "mm", pcb])
    # (--excellon-separate-th and --generate-map are FLAGS, not options taking a
    #  value; passing "false" makes kicad-cli read it as the input file and fail.
    #  Omitting them is what gives one merged drill file and no map.)

    _check_drill(pcb, d, board)
    _check_gerbers(d, json.load(open(stem + ".board.json", encoding="utf-8")),
                   board, pcb)

    # ---- CPL, converted to JLCPCB's column names ----
    raw = os.path.join(d, "_pos.csv")
    _run([KICAD_CLI, "pcb", "export", "pos", "-o", raw, "--format", "csv",
          "--units", "mm", "--side", "both", pcb])
    cpl = os.path.join(d, "%s-cpl.csv" % board)
    with open(raw, newline="", encoding="utf-8") as f, \
            open(cpl, "w", newline="", encoding="utf-8") as g:
        r = csv.DictReader(f)
        w = csv.writer(g)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        n = 0
        for row in r:
            w.writerow([row["Ref"], row["PosX"], row["PosY"],
                        "top" if row["Side"].lower() == "top" else "bottom", row["Rot"]])
            n += 1
    os.remove(raw)

    # ---- BOM, grouped by (value, footprint) the way JLCPCB reads it ----
    groups, open_real, open_generic, uncoded = {}, set(), set(), []
    for ref, val, fp in _parts(stem):
        groups.setdefault((val, fp), []).append(ref)
    bom = os.path.join(d, "%s-bom.csv" % board)
    with open(bom, "w", newline="", encoding="utf-8") as g:
        w = csv.writer(g)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (val, fp), refs in sorted(groups.items()):
            # ⚠ BARE COPPER IS NOT A BOM LINE. Test points, net ties and fiducials are
            # footprints with no part behind them: nothing is placed, nothing is
            # soldered, and asking JLCPCB to source one would be asking for a part that
            # does not exist. The footprints carry exclude_from_bom themselves, but the
            # BOM here is built from the NETLIST rather than the board, so that
            # attribute never reaches it.
            if COPPER_ONLY.search(fp.split(":", 1)[0]):
                continue
            code = code_for(val, fp)
            if not code:
                uncoded.append((val, fp.split(":", 1)[1], sorted(refs)))
                generic = bool(GENERIC.search(fp.split(":", 1)[1]) or GENERIC.search(fp))
                # ⚠ A GENERIC PASSIVE STILL NEEDS A VALUE, and "generic" was letting
                # placeholders through. JLCPCB picks an 0402 100nF from the value field;
                # it cannot pick an 0402 "Rf". The optical board carried FIFTY-THREE
                # parts whose value was a note to self -- "Rf", "Cf C0G", "ballast",
                # "mid-rail top", "load C0G", "preset" -- and every one was counted as a
                # sourced generic and would have reached a quote as a blank line.
                # A real value starts with a digit. That is the whole rule, and it
                # accepts every value this project actually uses (100nF, 8k06 1%,
                # 22uF/16V, 600R@100MHz, 18uH) while rejecting every placeholder.
                if generic and PASSIVE.search(fp.split(":", 1)[1]) \
                        and not re.match(r"\d", val.strip()):
                    raise SystemExit(
                        "%s: %s (%s) has value %r, which is a placeholder rather than a "
                        "value -- the fab cannot choose a part from it. Give it a real "
                        "value, or if it is genuinely undecided put it in "
                        "fab.OPEN_VALUES so it is COUNTED as undecided."
                        % (board, ",".join(sorted(refs)), fp.split(":", 1)[1], val))
                if not generic and val not in OPEN_VALUES:
                    raise SystemExit(
                        "%s: value %r (%s) is neither sourced, generic, nor "
                        "declared OPEN. Nothing but the BOM reads the value "
                        "field, so an unrecognised one is how a wrong part "
                        "gets ordered. Add it to fab.LCSC if you know the "
                        "part number, or to fab.OPEN_VALUES if you do not."
                        % (board, val, fp.split(":", 1)[1]))
                (open_generic if generic else open_real).add(val)
            w.writerow([val, ",".join(sorted(refs)), package_name(fp), code])
    if uncoded and REQUIRE_CODES:
        os.remove(bom)
        raise SystemExit(
            "%s: %d BOM row(s) have no LCSC code, so there is no package:\n%s\n"
            "A blank is not left for the order page: JLCPCB's matcher fills it from the "
            "footprint text and has turned an 0402 into an 01005 that Economic assembly "
            "does not place (qty 0, silently). Add each row to the project's table as "
            "(value, footprint) -> code, read off the catalogue with the voltage, "
            "dielectric and tolerance the board needs."
            % (board, len(uncoded), "\n".join(
                "   %-18s %-28s %s" % (v, f, ",".join(r[:6]) + (" ..." if len(r) > 6 else ""))
                for v, f, r in uncoded)))

    # ⚠ WHAT THE GERBERS CANNOT SAY. Mask colour, board thickness, surface finish and
    # copper weight are chosen in the ORDER FORM, not in any generated file, so a board
    # whose design depends on one of them has no way to carry that to the person paying
    # -- and "I remember it should be black" is not a design record. A board declaring
    # order_options gets them written into its own zip, next to the gerbers, where
    # whoever opens it to place the order will see them.
    opts = json.load(open(stem + ".board.json", encoding="utf-8")).get("order_options")
    # EVERY package gets an ORDER.txt now: the four settings in ORDER_EVERY_BOARD apply to
    # all of them, and a board with none of its own used to ship with no note at all.
    with open(os.path.join(d, "ORDER.txt"), "w", encoding="utf-8") as f:
        f.write("%s -- order form settings that are NOT in the gerbers\n\n" % board)
        for k in sorted(opts or {}):
            f.write("  %-12s %s\n" % (k + ":", opts[k]))
        f.write("\n  on every board:\n")
        for k, v in ORDER_EVERY_BOARD:
            f.write("  %-12s %s\n" % (k + ":", v))
    crit, _total = _rotation_critical(pcb)
    with open(os.path.join(d, "ROTATION-CHECK.txt"), "w", encoding="utf-8") as f:
        f.write("%s -- the placements a rotation difference can DAMAGE\n\n" % board)
        f.write("The CPL carries KiCad's convention unmodified. JLCPCB's placement "
                "machine wants\nthe LCSC part's frame, and for many parts those differ "
                "by 90/180/270. Check these\nin the previewer before paying:\n\n")
        for _ref, _rot, _fpn in crit:
            f.write("  %-8s %3d deg   %s\n" % (_ref, _rot, _fpn))
        f.write("\n%d of %d placements. The rest are two-pad chip passives, which both\n"
                "conventions align along the pad axis -- symmetric, so a 0/180 "
                "difference\ncannot change them.\n" % (len(crit), _total))
    z = os.path.join(FAB_DIR, "%s.zip" % board)
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn in sorted(os.listdir(d)):
            zf.write(os.path.join(d, fn), fn)
    return n, len(groups), sorted(open_real), sorted(open_generic), z, opts or {}


def _check_gerbers(gdir, notes, board, pcb):
    """Did the copper actually reach the gerbers, and is the reference plane whole?

    ⚠ THE EXPORT IS THE LAST PLACE A POUR CAN VANISH, and this project has watched one
    do it: route.py records the optical board's F.Cu ground pour disappearing at a stray
    refill and taking 74 pads with it. DRC ran on the board, not on the files, so a
    package can carry a layer that is missing copper the board had.

    Two things, at opposite severities.

    REFUSES on a declared zone whose layer exports NO region at all. KiCad writes a
    poured zone as a G36/G37 region block, so zero regions on a layer that declares a
    zone means the pour is not in the file. There is no benign reading of that.

    REPORTS, loudly, when a declared PLANE comes out as more than one region. In1.Cu is
    the impedance reference for the USB pair and the ULPI bus, and a plane arrives
    fragmented when something has been routed THROUGH it -- the exact damage the
    plane_layers declaration exists to prevent, which route.py had to be taught after a
    router turned 5729 mm2 of pour into 1043. It is not refused because a board outline
    could legitimately split a plane; it is printed because on these five boards it
    never has, and a change in that number means something moved.

    Measured 2026-09-19: In1.Cu is exactly ONE region on all four 4-layer boards.
    F.Cu and B.Cu fragment freely and are meant to -- optical's F.Cu is 26 islands --
    which is why only the DECLARED plane is held to one.
    """
    zones = {z[1] for z in notes.get("zones", []) or []}
    planes = set(notes.get("plane_layers", ()) or ())
    seen = {}
    for fn in sorted(os.listdir(gdir)):
        m = re.search(r"(F_Cu|In\d_Cu|B_Cu)\.(gtl|gbl|g\d)$", fn)
        if not m:
            continue
        txt = open(os.path.join(gdir, fn), encoding="utf-8", errors="replace").read()
        seen[m.group(1).replace("_", ".")] = len(re.findall(r"G36\*", txt))
    for layer in sorted(zones):
        if layer not in seen:
            raise SystemExit("%s: a zone is declared on %s and no such copper gerber "
                             "was exported" % (board, layer))
        if not seen[layer]:
            raise SystemExit(
                "%s: %s declares a zone and its gerber carries NO poured region. The "
                "pour is not in the file the fab will use." % (board, layer))
    for layer in sorted(planes):
        n = seen.get(layer, 0)
        if n > 1:
            print("  !! %s: the %s PLANE exported as %d separate regions. A reference "
                  "plane arrives fragmented when something is routed through it; check "
                  "plane_layers is being honoured." % (board, layer, n))
    # ⚠ PASTE IS THE LAYER THAT DECIDES WHETHER A PART IS SOLDERED AT ALL, and until now
    # nothing compared it to anything. A stencil aperture missing for a pad is a joint
    # that never forms: the board arrives assembled-looking with a part sitting on dry
    # copper. It is invisible to DRC, to the netlist, and to every check above.
    #
    # Counted as flashes plus regions, against the pads KiCad says are ON that layer --
    # not against "SMD pads", which is a different and wrong question. Measured
    # 2026-09-19: exact on all five boards, and B.Paste is empty on all five because
    # every board here is single-sided.
    #
    # ⚠ AND "SMD PADS" WAS THE FIRST VERSION OF THIS TEST AND IT MISREAD FIVE BOARDS. It
    # called 20 pads on motor_ctrl bottom-side, which would have meant parts with no
    # paste under them; they are the EXPOSED THERMAL PADS of U4 (QFN-68) and U5
    # (SOIC-8), whose copper reaches B.Cu through thermal vias while the part sits on
    # top. Asking IsOnLayer(F_Paste) asks the question the gerber actually answers.
    import pcbnew as _pcb
    _bd = _pcb.LoadBoard(pcb)
    for _lay, _suffix, _name in ((_pcb.F_Paste, "F_Paste.gtp", "F.Paste"),
                                 (_pcb.B_Paste, "B_Paste.gbp", "B.Paste")):
        _want = sum(1 for _fp in _bd.GetFootprints() for _p in _fp.Pads()
                    if _p.IsOnLayer(_lay))
        _f = [x for x in os.listdir(gdir) if x.endswith(_suffix)]
        _got = 0
        if _f:
            _t = open(os.path.join(gdir, _f[0]), encoding="utf-8", errors="replace").read()
            _got = len(re.findall(r"D03\*", _t)) + len(re.findall(r"G36\*", _t))
        if _got != _want:
            raise SystemExit(
                "%s: %s carries %d aperture(s) for %d pad(s) on that layer. A missing "
                "stencil aperture is a part that never gets soldered."
                % (board, _name, _got, _want))

    # ⚠ MASK MAY EXCEED ITS PADS AND MUST NEVER FALL SHORT. An opening fewer than pads
    # means a pad sealed under soldermask, which is unsolderable; an opening MORE is
    # normal and on these boards is exactly the solder jumpers' bridging window --
    # measured, the excess equals the JP count on every board: can_tee 1, lever_sensor
    # 1, motor_ctrl 2, optical 0, output_panel 0. So this is a floor, not an equality.
    _wantm = sum(1 for _fp in _bd.GetFootprints() for _p in _fp.Pads()
                 if _p.IsOnLayer(_pcb.F_Mask))
    _fm = [x for x in os.listdir(gdir) if x.endswith("F_Mask.gts")]
    if _fm:
        _t = open(os.path.join(gdir, _fm[0]), encoding="utf-8", errors="replace").read()
        _gotm = len(re.findall(r"D03\*", _t)) + len(re.findall(r"G36\*", _t))
        if _gotm < _wantm:
            raise SystemExit(
                "%s: F.Mask has %d opening(s) for %d pad(s) -- %d pad(s) would arrive "
                "sealed under soldermask." % (board, _gotm, _wantm, _wantm - _gotm))

    return seen


def _check_drill(pcb, drill_dir, board):
    """Does the drill file describe the holes the board actually has?

    ⚠ THIS CHECKS kicad-cli's OUTPUT, WHICH NOTHING ELSE DOES. Everything upstream
    validates the board; from the export onwards the artefact is whatever the tool
    wrote, and the fab drills from that file, not from the .kicad_pcb. A flag that
    changes meaning between KiCad versions, or an export that silently drops the NPTH
    pass, produces a package that looks complete and arrives as a board with no holes
    where holes were meant to be.

    Two things are compared, and both are cheap:
      * hit count == vias + through-hole pads. Exact, not approximate.
      * every G85 slot's TRAVEL matches an oval pad's (length - width).

    ⚠ A SLOT'S TOOL DIAMETER IS ITS WIDTH, NOT ITS LENGTH, and reading that wrong is
    what made optical's drill file look broken during the first hand check: the tools
    were 0.6 where the pads were 1.7, which looked like a mismatch and was a unit
    confusion. KiCad emits an oval PTH as a routed slot -- tool diameter = the narrow
    dimension, then a G85 move of (length - width). Comparing TRAVEL is what makes the
    two directly comparable.

    This one REFUSES rather than reports, unlike the BOM checks: a wrong drill file is
    a fab error, not a documentation error, and it cannot be caught by looking at the
    board afterwards.
    """
    import math
    import pcbnew
    drl = [f for f in os.listdir(drill_dir) if f.lower().endswith(".drl")]
    if not drl:
        raise SystemExit("%s: the drill export produced no .drl file" % board)
    txt = open(os.path.join(drill_dir, drl[0]), encoding="utf-8").read()
    hits = len(re.findall(r"^X[-\d.]+Y[-\d.]+", txt, re.M))
    slots = sorted(round(math.hypot(float(c) - float(a), float(d) - float(b)), 3)
                   for a, b, c, d in re.findall(
                       r"X(-?[\d.]+)Y(-?[\d.]+)G85X(-?[\d.]+)Y(-?[\d.]+)", txt))
    bd = pcbnew.LoadBoard(pcb)
    vias = sum(1 for t in bd.GetTracks() if isinstance(t, pcbnew.PCB_VIA))
    pth, ovals = 0, []
    for fp in bd.GetFootprints():
        for p in fp.Pads():
            if p.GetAttribute() not in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                continue
            pth += 1
            s = p.GetDrillSize()
            if s.x != s.y:
                ovals.append(round(pcbnew.ToMM(abs(s.x - s.y)), 3))
    if hits != vias + pth:
        raise SystemExit(
            "%s: the drill file has %d hit(s) and the board has %d hole(s) "
            "(%d vias + %d through-hole pads). The fab drills from the FILE."
            % (board, hits, vias + pth, vias, pth))
    if slots != sorted(ovals):
        raise SystemExit(
            "%s: %d routed slot(s) with travels %s, against %d oval pad(s) with "
            "travels %s" % (board, len(slots), slots, len(ovals), sorted(ovals)))
    return hits, len(slots)


def _rotation_critical(pcb):
    """Which placements could a rotation convention difference actually DAMAGE?

    ⚠ EVERY PACKAGE ENDS BY TELLING A PERSON TO CHECK EVERY PART IN JLCPCB'S PREVIEWER,
    and across five boards that is 329 placements. A human asked to check 329 things
    checks them carefully the first time. This does not replace that step and corrects
    nothing -- the CPL still carries KiCad's convention unmodified, for the reason at the
    top of this file -- it says WHICH ones can bite, so the attention goes where the
    damage is.

    ⚠ THE RULE IS ABOUT SYMMETRY, NOT PAD COUNT. A two-pad chip resistor or ceramic
    capacitor is rotationally symmetric: KiCad and JLCPCB both align it along its pad
    axis, so the conventions can differ by 0 or 180 and the part is identical either way.
    Everything else -- anything polarized, anything with three or more pads, anything
    whose pin 1 means something -- is at risk.

    ⚠ AND THE FIRST VERSION OF THIS ASKED THE PADS AND GOT DIODES WRONG. A SOD-123 diode
    has pads numbered 1 and 2 exactly like an 0402, and a diode fitted backwards is a
    dead board. Polarity is a property of the PART, not of its pad count, so the test is
    the reference prefix and the footprint name. Measured after fixing it: 108 of 329
    placements, against 56 while diodes were being waved through.

    ⚠ AND THE CATALOGUE CANNOT SETTLE IT EITHER -- CHECKED, so nobody has to check
    again. JLCPCB's own parts API returns 67 fields for a component (the same endpoint
    lcsc_check.py uses) and NOT ONE of them describes the part's frame: no rotation, no
    orientation, no pin-1 reference, nothing in the package or footprint fields that
    would let a script derive the offset. So there is no source here to correct against,
    which makes "narrow the human's work and correct nothing" the only honest answer
    available rather than a cautious preference.
    """
    import pcbnew
    board = pcbnew.LoadBoard(pcb)
    out, total = [], 0
    for fp in board.GetFootprints():
        pads = [q for q in fp.Pads() if q.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]
        if not pads:
            continue
        total += 1
        ref, name = fp.GetReference(), fp.GetFPIDAsString()
        sym = (len({q.GetNumber() for q in pads}) <= 2
               and not re.match(r"^CP", ref)
               and not re.search(r"Polarized|CP_|SOD|SMA|SMB|SMC|LED|Diode|Crystal",
                                 name, re.I)
               and re.match(r"^(R|C|L|FB|TP|JP)[A-Za-z]*[0-9]", ref))
        if not sym:
            out.append((ref, round(fp.GetOrientationDegrees()) % 360,
                        name.split(":")[-1]))
    return sorted(out), total


def _sweep_stale(names):
    """Delete packages for boards that no longer exist, and warn on ones left behind.

    ⚠ THIS FILE REFUSES TO BUILD A PACKAGE FOR A BOARD THAT DOES NOT PASS, AND THAT IS
    ONLY HALF THE GUARANTEE. Refusing to write a new zip does nothing about the OLD one
    sitting beside it, and a stale zip is indistinguishable from a fresh one to whoever
    uploads it -- which is exactly the "looks complete and arrives incomplete" failure
    this file exists to prevent, arriving by the back door.

    Found by listing the directory rather than trusting it: trrs_adapter.zip from
    2026-09-16 and usb_panel.zip from 09-14, both for boards whose GENERATORS HAVE BEEN
    DELETED from the design, and lever_sensor.zip from 09-17, which predates that
    board's BOOT0 rework and describes a board that no longer exists either. All three
    were orderable-looking and none of them were current.

    A package whose generator is gone is deleted outright -- there is no board it could
    describe. A package for a board that still exists but was not rebuilt this run is
    left alone and NAMED, because it may simply not have been asked for.
    """
    import glob
    for z in sorted(glob.glob(os.path.join(FAB_DIR, "*.zip"))):
        board = os.path.splitext(os.path.basename(z))[0]
        gen = os.path.join(HERE, "%s.py" % board)
        # BOARDS first, as the second sweep below already does: leg_pogo.py writes four
        # boards and none is named after it, so this deleted all four packages every run.
        if board not in BOARDS and not os.path.isfile(gen):
            os.remove(z)
            print("  removed %s.zip -- no generator; that board is not in the design"
                  % board)
        elif board not in names:
            # ASCII only in PRINTED text: this console is cp1252 and a warning glyph
            # here raised UnicodeEncodeError, which took the whole tool down. The
            # comments in this file use the glyph freely because they are source, not
            # output.
            print("  !! %s.zip is from an earlier run and was NOT rebuilt now -- check "
                  "its date before ordering" % board)

    # ⚠ THE SAME ARGUMENT REACHES ONE DIRECTORY UP, and the sweep stopped at the zips.
    # Deleting usb_panel.zip left elec/out/usb_panel.kicad_pcb, .net, .dsn and eight more
    # files from 2026-09-14 -- a whole board's intermediates for a generator that is no
    # longer in the design. Nothing distinguishes them from a current board's: finish.py
    # will happily route that .kicad_pcb if somebody names the stem, and it would produce
    # a real-looking result for a board nobody can regenerate.
    #
    # NAMED, NOT DELETED, and the asymmetry with the zips is deliberate. A zip is derived
    # and can always be rebuilt from the board; these intermediates are the ONLY surviving
    # artefact of a design whose source has been removed, so throwing them away is not
    # reversible in the way deleting a package is. Whoever removed the generator gets to
    # decide, and now they get told there is something to decide about.
    # ⚠ ONLY THINGS THAT ARE ACTUALLY BOARDS. The first version of this asked "does
    # a generator exist for every stem in elec/out" and named FIFTY-SEVEN of them --
    # o2, rp7, z9, chk, skidl_REPL and the rest of years of scratch files. A warning
    # channel that cries wolf fifty-seven times is worse than no warning at all, which
    # is the same argument as the DRC warnings this session spent its time on. A board
    # is a stem with a .kicad_pcb; scratch is not.
    for f in sorted(glob.glob(os.path.join(OUT_DIR, "*.kicad_pcb"))):
        board = os.path.basename(f)[:-len(".kicad_pcb")]
        # A tagged snapshot is <board>.<tag>.kicad_pcb -- optical.baseline1,
        # optical.pre_incr, <board>.unrouted. Those belong to a board that DOES exist
        # and are kept on purpose for comparison; only an undotted stem is its own board.
        if "." in board:
            continue
        # ⚠ A BOARD'S GENERATOR NEED NOT BE NAMED AFTER IT. fret_led.py writes BOTH
        # fret_led_mid and fret_led_key -- one design cut to two deck panels -- so the
        # file-name test called them orphans. Being in BOARDS is the real proof that a
        # stem is still in the design, which is what this check is for.
        if board not in BOARDS and not os.path.isfile(os.path.join(HERE, "%s.py" % board)):
            n = len(glob.glob(os.path.join(OUT_DIR, board + ".*")))
            print("  !! elec/out holds %d file(s) for '%s', which has no generator -- a "
                  "board that is not in the design any more. Delete them or restore it."
                  % (n, board))


def _quality(board, z):
    """Run the quality pass on `board`, put its report in the package as QUALITY.txt, and
    return (fail, open) -- or None if the pass could not run."""
    stem = os.path.join(OUT_DIR, board)
    r = subprocess.run([KICAD_PY, os.path.join(FLOW, "quality.py"), stem],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = "\n".join(ln for ln in (r.stdout or "").splitlines()
                     if "image handler" not in ln and "memory leak" not in ln)
    m = re.search(r"quality (\d+) FAIL, (\d+) OPEN", text)
    with zipfile.ZipFile(z, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("QUALITY.txt", text + "\n")
    return (int(m.group(1)), int(m.group(2))) if m else None


def main(names=None):
    if HERE is None:
        raise SystemExit("fab: call configure() first")
    names = list(names or BOARDS)
    os.makedirs(FAB_DIR, exist_ok=True)
    _sweep_stale(names)
    blocked, order, dirty = {}, {}, {}
    for b in names:
        n, g, open_real, open_generic, z, opts = fab(b)
        if opts:
            order[b] = opts
        print("%-13s %3d placements, %2d BOM lines, %d generic + %d OPEN  -> %s"
              % (b, n, g, len(open_generic), len(open_real), os.path.basename(z)))
        if open_real:
            blocked[b] = open_real
        dirty[b] = _quality(b, z)
        if REQUIRE_QUALITY and dirty[b] != (0, 0):
            os.remove(z)
    if blocked:
        print("\nSOURCING STILL OPEN -- these cannot be ordered assembled:")
        for b, vals in blocked.items():
            for v in vals:
                print("   %-13s %s" % (b, v))
    if order:
        print("\nORDER FORM SETTINGS (not in the gerbers -- see each zip's ORDER.txt):")
        for b, opts in order.items():
            for k in sorted(opts):
                print("   %-13s %-11s %s" % (b, k, opts[k].split(" -- ")[0]))
    if any(v != (0, 0) for v in dirty.values()):
        print("\nQUALITY NOT CLEAN (cadkit/PCB_QUALITY.md; each zip's QUALITY.txt has the list)%s:"
              % (" -- THESE PACKAGES WERE REMOVED" if REQUIRE_QUALITY else ""))
        for b, v in dirty.items():
            if v != (0, 0):
                print("   %-13s %s" % (b, "the pass did not run" if v is None
                                       else "%d FAIL, %d OPEN manual item(s)" % v))
    if AFTER:
        AFTER(names)
    # ASCII on purpose: this prints to a Windows console whose default
    # codepage is cp1252, and a warning that raises UnicodeEncodeError is
    # worse than no warning at all.
    print("")
    print("!! CHECK THE ROTATIONS in JLCPCB's previewer before paying: the CPL carries")
    print("  KiCad's convention, which differs per part from LCSC's. Each package's")
    print("  ROTATION-CHECK.txt lists ONLY the placements a difference can DAMAGE --")
    print("  polarised, multi-pad, or pin-1-bearing. Two-pad chip passives are")
    print("  symmetric under a 0/180 difference and are deliberately left off it.")


if __name__ == "__main__":
    raise SystemExit("run your project's elec/fab.py -- it supplies the board list and "
                     "the sourcing table (see cadkit/pcbflow/example/fab.py)")
