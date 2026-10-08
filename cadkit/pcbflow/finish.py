"""Route a board, then hand the router's own failures back to the generator.

    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/finish.py elec/out/optical

⚠ THIS EXISTS BECAUSE PRE-LAYING COPPER IS A TRADE, NOT AN IMPROVEMENT, and the trade
only pays on the nets the router cannot do. Measured on three boards, freezing every
short net in advance took lever_sensor from 4 unconnected to 7 and output_panel from 2 to
5, while taking optical from 26 to 12. The mechanism is not subtle once seen: the
router's strength is that every path it lays is NEGOTIABLE -- it can rip one up to make
room for another -- and copper laid before it starts is not in that negotiation at all.
It is an obstacle, like a pad or a board edge, and it can never be reconsidered.

So pre-laying converts negotiable copper into fixed copper, and doing that to nets the
router would have solved anyway is pure loss: it takes away the work it does well, leaves
the work it does badly, and shrinks the space left to do it in.

The fix is to stop guessing which nets need help. Route the board; ask DRC what is still
unconnected; lay THOSE nets deterministically; route again. Nothing is declared in
advance and nothing goes stale, because the list is measured fresh every run.

AND KEEP THE BETTER OF THE TWO. The second pass can lose -- the copper it adds is an
obstacle like any other and may cost more than it buys. This compares and keeps whichever
board is actually better, so a retry can never make a board worse than not retrying.
That guarantee is only available because the pipeline is reproducible: without it, "worse"
and "a different roll of the dice" are the same measurement.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import netcheck
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CADKIT = os.path.dirname(HERE)
PY = sys.executable
# kicad-cli sits beside the interpreter this runs under (<KiCad>/bin); $KICAD_CLI overrides
KICAD_CLI = os.environ.get("KICAD_CLI") or next(
    (p for p in (os.path.join(os.path.dirname(os.path.abspath(sys.executable)), n)
                 for n in ("kicad-cli.exe", "kicad-cli")) if os.path.isfile(p)),
    r"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe")


def project_dir(stem):
    """The folder the board's generator lives in: `elec/` for `elec/out/<board>`, or
    $PCBFLOW_PROJECT. See layout.project_dir -- kept in step with it, not imported, so
    this file still needs nothing but the standard library."""
    env = os.environ.get("PCBFLOW_PROJECT")
    return os.path.abspath(env) if env else os.path.dirname(os.path.dirname(os.path.abspath(stem)))


# ── WHAT A PROJECT MAY SUPPLY, all optional, all found in project_dir(stem) ─────────────
#   silk.py            labels the finished board. Default: cadkit/kicad_silk.py (rev r1).
#   export_geom.py     writes the geom file.     Default: cadkit/kicad_geom.py, into
#                      <project>/geom/.
#   cad_geom_check.py  `<cad python> cad_geom_check.py <board>`: is the CAD's board the
#                      routed one (cadkit.board_check)? No default -- only the project
#                      knows which solid its assembly draws -- so without it the run says
#                      plainly that the CAD is UNCHECKED.
#   pcb_declared.py    `declared(board, vtype, refs) -> bool`: DRC violations the design
#                      accepts on purpose, by shape. Everything else stays a violation.
_DEFAULT_STEP = {"silk.py": os.path.join(CADKIT, "kicad_silk.py"),
                 "export_geom.py": os.path.join(CADKIT, "kicad_geom.py")}


def _step(script, stem):
    """Path of a pipeline step: the project's own copy of a HOOK step if it has one, the
    shared default otherwise; core steps always come from here."""
    if script in _DEFAULT_STEP or script == "cad_geom_check.py":
        mine = os.path.join(project_dir(stem), script)
        if os.path.isfile(mine):
            return mine
        return _DEFAULT_STEP.get(script)
    return os.path.join(HERE, script)


def _declared(stem):
    """The project's `declared(board, vtype, refs)`, bound to this board; else nothing is."""
    path = os.path.join(project_dir(stem), "pcb_declared.py")
    if not os.path.isfile(path):
        return lambda t, r: False
    import importlib.util
    spec = importlib.util.spec_from_file_location("pcb_declared", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    board = os.path.basename(stem)
    return lambda t, r: bool(mod.declared(board, t, r))


def _silkfit(stem):
    """Move every silk designator to where it will actually print.

    ⚠ AFTER silk.py AND NOT IN layout.py, AND BOTH HALVES OF THAT WERE LEARNED THE
    HARD WAY. This started as a hook at the end of layout.build(), which is wrong twice
    over. First, --keep-route does not run layout.py at all -- it re-does everything
    AFTER the route -- so on a kept-route board the pass silently never happened and
    fifteen clipped designators went through untouched; the run said "0 violation(s)"
    and A18 was the only thing that noticed. Second, silk.py adds the board-level
    labels, the test-pad nets and the connector pinouts AFTERWARDS, and those are silk
    objects a designator can be clipped against: fitting in layout meant fitting
    against half of the silkscreen and then having the other half printed on top.

    Here it runs on EVERY path, against the finished silkscreen, and the DRC below --
    which silk.py already re-runs to check its own "moves no copper" claim -- grades
    the result. It moves no copper either: silk and .Fab only.
    """
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silkfit.py")
    try:
        spec = importlib.util.spec_from_file_location("silkfit", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as exc:                                # noqa: BLE001
        print("  silkfit did NOT run (%s: %s): silk may be clipped -- A18 decides"
              % (type(exc).__name__, exc))
        return
    try:
        import pcbnew
        import wx                                       # noqa: E402  (KiCad's python ships it)
        wx.DisableAsserts()                             # NO MODAL DIALOGS IN A BUILD STEP -- see route.py
        board = pcbnew.LoadBoard(stem + ".kicad_pcb")
        notes = {}
        try:
            with open(stem + ".board.json", encoding="utf-8") as fh:
                notes = json.load(fh)
        except OSError:
            pass
        # ⚠ THE INK FLOOR COMES OUT OF THE FAB TABLE, not a second copy of 0.15.
        # quality.py owns that table and A12 grades the result against the same
        # entry, so a fab change moves the fixer and the rule together.
        floor = None
        try:
            qpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "quality.py")
            qspec = importlib.util.spec_from_file_location("quality_fab", qpath)
            qmod = importlib.util.module_from_spec(qspec)
            qspec.loader.exec_module(qmod)
            floor = float(qmod.FAB["silk_stroke"])
        except Exception as exc:                            # noqa: BLE001
            # NOT a silent skip: say that the ink was not raised, and let A12 --
            # which reads the same table -- be the thing that fails.
            print("  silk ink NOT raised (%s: %s): A12 decides"
                  % (type(exc).__name__, exc))
        if floor:
            mod.thicken_ink(board, floor, pcbnew=pcbnew, log=lambda m: print(" " + m))

        moved, demoted, kept = mod.fit_refs(
            board, notes=notes.get("quality", {}) or {},
            log=lambda m: print(" " + m), pcbnew=pcbnew)
        if moved or demoted:
            board.Save(stem + ".kicad_pcb")
    except Exception as exc:                                # noqa: BLE001
        print("  silkfit FAILED (%s: %s): silk may be clipped -- A18 decides"
              % (type(exc).__name__, exc))


def _drc(stem):
    """(unconnected count, the net names involved) for the board at `stem`."""
    out = stem + ".finish.drc.json"
    # ⚠ NO --severity-error: THIS PIPELINE HAD NEVER SEEN A DRC WARNING. Asking only for
    # errors is asking KiCad to hide a whole class of finding, and it hid five on the
    # optical board -- four dangling vias and a 9 um track fragment. The vias turned out
    # to be the router's abandoned stubs on the very nets still unconnected, which is
    # useful corroboration, and the fragment is copper that drop_degenerate's 5 um floor
    # is just too low to catch.
    # Warnings do NOT fail a board. They are printed, because a warning nobody prints is
    # the same as a warning nobody gets.
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json",
                    "-o", out, stem + ".kicad_pcb"], capture_output=True, text=True)
    d = json.load(open(out, encoding="utf-8"))
    nets = set()
    for v in d.get("unconnected_items", []):
        for item in v["items"]:
            m = re.search(r"\[([^\]]+)\]", item["description"])
            if m:
                nets.add(m.group(1))
    # ⚠ WHAT IS RETURNED IS THE UNEXPECTED COUNT, NOT THE TOTAL. The optical board
    # declares twenty courtyard overlaps and reporting the total taught everyone to read
    # "20" as "fine" -- at which point 23 also reads as fine for exactly as long as it
    # takes somebody to stop listing them. See netcheck.classify_violations.
    declared = _declared(stem)
    # errors decide the board; warnings are reported and nothing more
    warn = [v for v in d.get("violations", []) if v.get("severity") == "warning"]
    d = dict(d, violations=[v for v in d.get("violations", [])
                            if v.get("severity") != "warning"])
    ok, bad = netcheck.classify_violations(d, declared)
    if warn:
        import collections as _c
        kinds = _c.Counter(v["type"] for v in warn)
        print("  %d DRC warning(s): %s"
              % (len(warn), ", ".join("%s x%d" % kv for kv in sorted(kinds.items()))))
    if ok:
        print("  %d declared violation(s) (pcb_declared.py), %d unexpected"
              % (len(ok), len(bad)))
    for t, refs in bad:
        print("     UNEXPECTED %s: %s" % (t, " + ".join(refs)))
    return len(d.get("unconnected_items", [])), sorted(nets), len(bad)


def _violation_nets(stem):
    """The nets named in the error-level violations of the last DRC run on `stem`."""
    try:
        d = json.load(open(stem + ".finish.drc.json", encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    out = set()
    for v in d.get("violations", []):
        if v.get("severity") == "warning":
            continue
        for item in v.get("items", []):
            out.update(re.findall(r"\[([^\]]+)\]", item.get("description", "")))
    return out


def _run(script, stem):
    """Run a pipeline step, streaming its output as it arrives.

    ⚠ STREAM IT. Capturing the output and printing it at the end made a twenty-minute
    run look exactly like a hung one -- two routing passes on a 153-part board, and not a
    character until both had finished. For a tool whose whole purpose is to be left
    running unattended, "is it working or is it stuck?" is the one question it has to be
    able to answer, and a progress line costs nothing.
    """
    out = []
    proc = subprocess.Popen([PY, _step(script, stem), stem],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    for line in proc.stdout:
        if "image handler" in line:
            continue          # KiCad's Python greets every start-up with a dozen
        out.append(line)
        sys.stdout.write("    " + line)
        sys.stdout.flush()
    if proc.wait():
        raise SystemExit("%s failed on %s" % (script, stem))
    return "".join(out)


def _check_fresh(stem):
    """Refuse to route placements the generator has already changed.

    ⚠ THIS SILENTLY WASTED THREE ROUTING RUNS AND PRODUCED THREE CONFIDENT WRONG
    CONCLUSIONS. finish.py runs layout -> route -> drc; it does NOT run the
    skidl generator, so `.net` and `.board.json` are whatever the last generator run
    wrote. Edit a placement in elec/<board>.py, run finish.py, and it re-routes the OLD
    placement and reports a result -- which reads exactly like a real measurement of the
    change. On lever_sensor that produced "moving the SWD pads does not help" and "moving
    C7 and R6 does not help", both of which were statements about an unmodified board.
    (The same shape of mistake was made on optical earlier: a file reverted, the netlist
    not regenerated, and a regression reported that had never happened.)

    A stale netlist is not a wrong answer, it is an answer to a question nobody asked,
    and there is no way to tell from the output. So compare the timestamps and stop.
    """
    src = os.path.join(project_dir(stem), os.path.basename(stem) + ".py")
    if not os.path.isfile(src):
        return
    for ext in (".net", ".board.json"):
        f = stem + ext
        if os.path.isfile(f) and os.path.getmtime(f) < os.path.getmtime(src):
            raise SystemExit(
                "%s is NEWER than %s.\n"
                "finish.py does not run the generator, so routing now would measure the "
                "PREVIOUS placements and report it as a result. Run:\n"
                "    py -3.12 %s"
                % (os.path.relpath(src), os.path.basename(stem) + ext,
                   os.path.relpath(src)))


def _legible_refs(stem):
    """Raise every VISIBLE silkscreen designator on the finished board to the legible
    minimum (1.0 mm high, 0.15 stroke -- quality A12). layout.py sets these when it places
    a part; a board routed before that changed keeps its old size until it is re-routed,
    and --keep-route exists so that it does not have to be. Run as a child, like every
    other step: pcbnew aborts in teardown often enough that it must not take finish with it."""
    code = (
        "import sys, pcbnew\n"
        "b = pcbnew.LoadBoard(sys.argv[1]); n = 0\n"
        "for fp in b.GetFootprints():\n"
        "    for f in fp.GetFields():\n"
        "        if f.IsVisible() and f.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):\n"
        "            h, t = pcbnew.ToMM(f.GetTextHeight()), pcbnew.ToMM(f.GetTextThickness())\n"
        "            if h < 0.999 or t < 0.149:\n"
        "                f.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(max(h, 1.0)), pcbnew.FromMM(max(h, 1.0))))\n"
        "                f.SetTextThickness(pcbnew.FromMM(max(t, 0.15))); n += 1\n"
        "pcbnew.SaveBoard(sys.argv[1], b)\n"
        "print('  %d designator(s) raised to the legible minimum' % n)\n"
        "sys.stdout.flush()\n"
        "import os; os._exit(0)\n")
    proc = subprocess.run([PY, "-c", code, stem + ".kicad_pcb"], stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout.splitlines():
        if "designator" in line:
            print(line)


def _sync_values(stem):
    """Write the netlist's part values into a board that is being kept.

    ⚠ A KEPT BOARD KEPT ITS OLD VALUES (2026-10-05). A value is not copper, so swapping an
    inductor for another on the same land passes _check_fresh and --keep-route is the
    right tool -- and the board file went on naming the part that had been replaced, with
    the quality pass green, because every check that reads a value read it from the
    netlist or from this stale field alike. The board file is what the fab package is
    built from. Run as a child, like _legible_refs."""
    import layout
    comps, _nets = layout.read_netlist(stem + ".net")
    tmp = stem + ".values.json"
    json.dump({r: v for r, (_fp, v) in comps.items()}, open(tmp, "w", encoding="utf-8"))
    code = (
        "import sys, json, pcbnew\n"
        "want = json.load(open(sys.argv[2], encoding='utf-8'))\n"
        "b = pcbnew.LoadBoard(sys.argv[1]); n = []\n"
        "for fp in b.GetFootprints():\n"
        "    v = want.get(fp.GetReference())\n"
        "    if v is not None and fp.GetValue() != v:\n"
        "        n.append('%s %s -> %s' % (fp.GetReference(), fp.GetValue(), v)); fp.SetValue(v)\n"
        "if n:\n"
        "    pcbnew.SaveBoard(sys.argv[1], b)\n"
        "print('  value(s) brought into step with the netlist: %s' % (', '.join(n) or 'none'))\n"
        "sys.stdout.flush()\n"
        "import os; os._exit(0)\n")
    proc = subprocess.run([PY, "-c", code, stem + ".kicad_pcb", tmp], stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout.splitlines():
        if "value(s)" in line:
            print(line)
    if os.path.isfile(tmp):
        os.remove(tmp)


def finish(stem, rounds=1, keep_route=False):
    """Route `stem`; with rounds>1, retry the nets the router could not finish.

    ⚠ THE RETRY IS OFF BY DEFAULT BECAUSE IT HAS NEVER YET PAID. Re-measured on the
    optical board 2026-09-17, now that layout's inner-layer fallback works: pass 1 gives
    1 unconnected and 0 violations, pass 2 gives 3 and 7. It doubles the wall clock of
    every run and its only achievement is not making things worse, which the
    keep-the-better-board rule guarantees anyway. (The old figures here, 12 -> 27, were
    from before the board had a working pre-lay; the conclusion survived the re-measure
    but the numbers did not.)

    ⚠ AND THE REASON RECORDED HERE WAS WRONG, WHICH MATTERS MORE THAN THE NUMBERS. It
    said a net the router could not finish is usually one the generator cannot finish
    either, blocked by the same geometry. Printing the names of the edges the pre-lay
    skips shows otherwise: the retry LAYS its net without difficulty, 8 segments. What it
    costs is everything laid after it -- local nets drop from 90 segments with nothing
    skipped to 76 with EIGHTEEN skipped, every one a short cluster hop in the strip that
    the long retried run has just cut across. The 3 unconnected and 7 violations are that
    damage, not the retried net.

    ⚠ THE ORDERING IS FIXED AND THE RETRY STILL DOES NOT PAY. Local nets now run BEFORE
    the retry in layout.py, by the same "fewer alternatives first" argument that put the
    stitcher ahead of local nets, and the interference is gone: 90 segments kept, nothing
    skipped, and pass 2's seven violations with it. What is left is pass 2 at 4
    unconnected against pass 1's 1. The retry's failure is now CLEAN rather than
    destructive, which is a better answer than the old one and still not a reason to turn
    it on.

    (That experiment could not report at all until route.py stopped aborting in pcbnew's
    interpreter teardown -- see the note at the bottom of route.py. Two runs died there
    and looked like the reorder breaking the router, when the board had been written
    correctly both times.)

    The remaining question is the one the numbers keep pointing at: the retried net is
    long and the strip is where every failure lives, so pre-laying it uses the scarce
    space to solve the easy half of the problem. A retry that only ever laid the CLUSTER
    end of a failed net, and left the long run to the router, has not been tried.
    """
    _check_fresh(stem)
    retry = stem + ".retry.json"
    if os.path.isfile(retry):
        os.remove(retry)          # always start from the board as designed
    if keep_route:
        # --keep-route: THE COPPER ON DISK IS THE BOARD. Nothing is placed or routed; the
        # run re-does everything AFTER the route (labels, DRC, verify, quality, geometry,
        # CAD check) on the board as it stands. For a change that touches no copper -- a
        # label size, a quality record -- on a board whose route was hard won. A change
        # to the netlist or a placement is NOT that: _check_fresh above refuses it.
        rounds = 1
        _sync_values(stem)
        _legible_refs(stem)
    else:
        _run("layout.py", stem)
        _run("route.py", stem)
        _run("unwick.py", stem)
        _run("repair_planes.py", stem)
    best_n, nets, best_v = _drc(stem)
    print("  %s: %d unconnected, %d violation(s)"
          % ("kept route" if keep_route else "pass 1", best_n, best_v))
    # ⚠ THE DRC FILE TRAVELS WITH THE BOARD, because otherwise it does not. This routine
    # keeps the BEST board but _drc overwrites .finish.drc.json on every pass, so after a
    # two-round run the board on disk was pass 1 and the DRC file beside it described
    # pass 2 -- a file whose whole purpose is to say what the board is, saying something
    # else. It reads as a board that just got worse, and it is the same file the retry
    # list is built from. Caught by re-running DRC by hand and getting a different answer
    # from the one lying next to the board.
    shutil.copy(stem + ".kicad_pcb", stem + ".best.kicad_pcb")
    shutil.copy(stem + ".finish.drc.json", stem + ".best.drc.json")

    for k in range(2, rounds + 1):
        if not best_n:
            break
        json.dump(nets, open(retry, "w", encoding="utf-8"))
        # ⚠⚠ A FAILED RETRY ROUND MUST NOT TAKE THE GOOD BOARD WITH IT, AND IT DID.
        # _run raises SystemExit on a non-zero exit, so a round that died anywhere in
        # layout/route/repair skipped the restore at the end of this function -- and the FIRST
        # thing a round does is re-run layout, which overwrites <stem>.kicad_pcb with a fresh
        # UNROUTED board. So a failed round left the baseline in the worst possible state: the
        # best board existed only as <stem>.best.kicad_pcb, a file nothing else reads, and
        # elec/out is NOT under git -- there is no second copy anywhere.
        # Seen for real on optical, 2026-09-29: pass 2 reached 2 unconnected / 0 violations --
        # the best this board has ever routed -- and pass 3's freerouting produced no session
        # file, leaving an unrouted optical.kicad_pcb as the committed baseline and the SES
        # import reference. Recovered by hand from .best.kicad_pcb (byte-identical to
        # .lastrouted), which is exactly the recovery this makes unnecessary.
        # A retry round is OPTIONAL WORK: it either improves on what we have or it does not
        # happen. Failing is 'does not happen', not 'lose the board'.
        try:
            _run("layout.py", stem)
            _run("route.py", stem)
            _run("unwick.py", stem)
            _run("repair_planes.py", stem)
        except SystemExit as exc:
            print("  ⚠ pass %d FAILED (%s) -- keeping pass %d's board and stopping the "
                  "retries. The best board is restored below, as if this round never ran."
                  % (k, exc, k - 1))
            break
        n, nets_now, v = _drc(stem)
        print("  pass %d: %d unconnected, %d violation(s)" % (k, n, v))
        # ⚠ STRICTLY BETTER OR IT DOES NOT COUNT. A violation is worse than an
        # unconnected pad -- one is a board that cannot be made, the other a board that
        # is not finished -- so violations are compared first and only then the count.
        if (v, n) < (best_v, best_n):
            shutil.copy(stem + ".kicad_pcb", stem + ".best.kicad_pcb")
            shutil.copy(stem + ".finish.drc.json", stem + ".best.drc.json")
            best_n, best_v, nets = n, v, nets_now
        else:
            print("  pass %d did not improve on pass %d -- keeping the better board"
                  % (k, k - 1))
            break

    if os.path.isfile(retry):
        os.remove(retry)
    shutil.copy(stem + ".best.kicad_pcb", stem + ".kicad_pcb")
    os.remove(stem + ".best.kicad_pcb")
    shutil.copy(stem + ".best.drc.json", stem + ".finish.drc.json")
    os.remove(stem + ".best.drc.json")

    # ⚠ THE LAST NET OR TWO, BY MAZE, ON THE BOARD THAT WON (close_last.py says why at
    # length). Only on a board with no violations: a search for copper on a board that
    # already breaks a rule would be judged against a moving baseline. And the same
    # "strictly better or it does not count" test as a routing round -- the search works
    # to the netclass rule on a grid, DRC is the judge, and a repair that buys a
    # connection with a violation is put back.
    # (--keep-route takes this step too: a kept board with a net still open is exactly the
    # board this was written for, and it lays nothing unless DRC then reads better.)
    if best_n and not best_v:
        shutil.copy(stem + ".kicad_pcb", stem + ".preclose.kicad_pcb")
        shutil.copy(stem + ".finish.drc.json", stem + ".preclose.drc.json")
        # ⚠ ONE BAD CLOSURE DOES NOT COST THE GOOD ONES (optical, 2026-10-05). The search
        # closed five nets cleanly and a sixth through a keep-out; judged as one lot, all
        # six were put back and the board stayed at six open. So a failed attempt names
        # the nets its new violations are on, and the next attempt leaves those alone --
        # up to four times, each from the same untouched board.
        #
        # ⚠ unwick.py STAYS IN THE CHAIN: close_last -> unwick -> repair_planes, not
        # close_last -> repair_planes. close_last lays new track AND NEW VIAS, and unwick
        # is what keeps a via out of a pasted land and out of another hole's minimum
        # (PCB_QUALITY M29 / A14). Dropping it puts back open barrels under solder paste
        # SILENTLY, because the board model reports those vias as tented -- so every gate
        # downstream still passes. It has to be a step in this loop and not a pass at the
        # end, because the vias it moves are made inside the loop.
        #
        # This lived as a project-side edit to a vendored copy for one board's lifetime,
        # with a comment explaining that the merge kept two of its three call sites by
        # luck. That was the warning, not the fix; the pass and all three calls are
        # upstream now, which is the only version of "it stays in the chain" that holds.
        _skip = set()
        import time as _time
        _close_t0 = _time.time()
        for _attempt in range(4):
            # a retry is worth a few minutes, not another route's worth (see close_last)
            if _attempt and _time.time() - _close_t0 > 1800:
                print("  close_last: no further attempt, %.0f min spent"
                      % ((_time.time() - _close_t0) / 60))
                break
            os.environ["CLOSE_LAST_SKIP"] = ",".join(sorted(_skip))
            try:
                _run("close_last.py", stem)
                _run("unwick.py", stem)
                _run("repair_planes.py", stem)
                _n3, _nets3, _v3 = _drc(stem)
                print("  close_last: %d unconnected, %d violation(s)" % (_n3, _v3))
            except SystemExit as exc:
                print("  close_last did not run (%s)" % (exc,))
                _n3, _v3 = best_n, best_v + 1
            if (_v3, _n3) < (best_v, best_n):
                best_n, best_v, nets = _n3, _v3, _nets3
                break
            _blame = _violation_nets(stem) & set(nets) - _skip
            print("  close_last did not improve the board -- putting it back")
            shutil.copy(stem + ".preclose.kicad_pcb", stem + ".kicad_pcb")
            shutil.copy(stem + ".preclose.drc.json", stem + ".finish.drc.json")
            if not _blame:
                break
            print("  ... and trying again without %s" % ", ".join(sorted(_blame)))
            _skip |= _blame
        os.environ.pop("CLOSE_LAST_SKIP", None)
        os.remove(stem + ".preclose.kicad_pcb")
        os.remove(stem + ".preclose.drc.json")

    # THE SILKSCREEN GOES ON THE BOARD THAT WON, and only there: name and revision, the
    # test pads' nets, the connectors' pinouts (silk.py). It moves no copper, and every
    # label is dropped rather than squeezed -- but "cannot add a finding" is a claim, so
    # the DRC is run again and the claim is checked rather than trusted.
    try:
        _run("silk.py", stem)
        _silkfit(stem)
        _n2, _nets2, _v2 = _drc(stem)
        if (_v2, _n2) != (best_v, best_n):
            print("  !! THE SILKSCREEN CHANGED THE DRC RESULT: %d unconnected, %d "
                  "violation(s) after it, %d and %d before" % (_n2, _v2, best_n, best_v))
            best_n, best_v = max(best_n, _n2), max(best_v, _v2)
    except SystemExit as exc:
        print("  silk.py did not run (%s): the board has no labels" % (exc,))

    # ⚠ verify.py HAD NEVER BEEN RUN BY ANYTHING. Its own docstring says "THE POINT IS
    # TO REMOVE THE HUMAN, NOT TO ADVISE ONE" and that it exits non-zero when a budget is
    # missed -- and nothing called it. It is the only check in this pipeline that asks
    # whether the board is CORRECT rather than manufacturable: DRC will happily pass a
    # board whose USB pair is split across two layers on two unrelated paths.
    #
    # ⚠ REPORTED HERE, NOT ENFORCED HERE, AND THE SPLIT IS DELIBERATE. _run() aborts
    # the whole run on a non-zero exit, so gating here would throw away a twenty-minute
    # routing result over a skew number -- and the board would still be the best one we
    # have. fab.py is where refusing belongs, because that is the step that produces
    # something orderable; it already refuses a package built from an unrouted board.
    # ⚠ ...BUT THE LAST LINE MUST SAY SO. "Reported, not enforced" left the verdict forty
    # lines up while the summary read "0 unconnected, 0 violation(s)" -- and on 2026-09-30 a
    # board whose THRU pair was split across layers with one via too many was committed AND
    # submitted on the strength of that line. The count rides on the summary now, so a
    # script (or a person) reading only the summary cannot miss it.
    verify_fails = 0
    try:
        proc = subprocess.run([PY, os.path.join(HERE, "verify.py"), stem],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True)
        for line in proc.stdout.splitlines():
            if "image handler" in line or line.startswith("WARNING"):
                continue
            if line.strip():
                print("    " + line)
            if line.lstrip().startswith("FAIL"):
                verify_fails += 1
    except Exception as exc:                      # a check that breaks must not break the
        print("    verify.py did not run: %r" % (exc,))   # board it was checking

    # ...AND WRITE THE BOARD BACK OUT FOR THE CAD, every run. elec/out is git-ignored, so
    # the geometry the CAD builds from has to live in a TRACKED file (elec/geom), and the
    # only way it cannot drift from the board is if the step that makes the board also
    # writes it. The CAD used to model boards from hand-copied placements and nothing
    # re-read the finished board -- see export_geom.py for what that let through.
    # THE QUALITY PASS (cadkit/PCB_QUALITY.md): what DRC cannot judge -- supply choke
    # points, missing bypass capacitors, undeclared pairs, uncited pinouts -- plus the
    # manual checklist still unsigned. It REPORTS here; the count goes in the last line.
    quality = None
    try:
        proc = subprocess.run([PY, os.path.join(HERE, "quality.py"), "--brief", stem],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout.splitlines():
            if "image handler" in line or "memory leak" in line or not line.strip():
                continue
            print("    " + line)
            m = re.search(r"quality (\d+) FAIL, (\d+) OPEN", line)
            if m:
                quality = (int(m.group(1)), int(m.group(2)))
    except Exception as exc:
        print("    quality.py did not run: %r" % (exc,))

    try:
        proc = subprocess.run([PY, _step("export_geom.py", stem), stem],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout.splitlines():
            if line.strip() and "memory leak" not in line:
                print("    " + line)
    except Exception as exc:
        print("    export_geom.py did not run: %r" % (exc,))

    # ...AND THEN COMPARE THE TWO SIDES, every run. Writing the geometry out is only half
    # of it: export_geom has faithfully recorded a board whose CUTOUTS disagreed with the
    # CAD's since the comb replaced the single big hole, and nothing compared them.
    # ⚠ THE OPTICAL BOARD'S GERBERS WOULD HAVE SHIPPED WITH NO COMB. Ten slots were
    # emitted to Edge.Cuts as one 16.41 x 101.6 mm rectangle, so the fab would have cut
    # away the nine copper strips that carry all twenty TIA outputs. The CAD gate was
    # clean, ERC was clean, the netlist was clean, and the CAD/netlist/BOM part
    # reconciliation agreed on all 241 parts -- because every one of those reads a SINGLE
    # SIDE. The router found it by failing to route across copper the fab data denied.
    # cad_geom_check existed and compared the right things; it was simply never run here.
    # A check that has to be remembered is not a guarantee, so it runs with the board.
    # It needs CadQuery, which KiCad's bundled python does not have -- hence a different
    # interpreter from PY, and a LOUD message if none of them works. Silence here is the
    # failure mode this whole note is about.
    # The CAD check runs under the project's CAD interpreter (CadQuery), not this one:
    # $CAD_PYTHON, else the usual launchers in turn.
    _name = os.path.basename(stem)
    _chk = _step("cad_geom_check.py", stem)
    _cqs = ([[os.environ["CAD_PYTHON"]]] if os.environ.get("CAD_PYTHON")
            else [["py", "-3.12"], ["python3"], ["python"]])
    for _cq in (_cqs if _chk else []):
        try:
            proc = subprocess.run(_cq + [_chk, _name],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True)
        except OSError:
            continue
        for line in proc.stdout.splitlines():
            if line.strip() and "memory leak" not in line:
                print("    " + line)
        if proc.returncode:
            print("    !! THE CAD AND THE FAB DATA DISAGREE -- see above")
        break
    else:
        print("    !! cad_geom_check DID NOT RUN: %s. THE CAD AND THE FAB DATA ARE UNCHECKED."
              % ("no CadQuery interpreter found" if _chk else
                 "the project has no %s (see cadkit/PCB_README.md, 'Gate it')"
                 % os.path.join(os.path.basename(project_dir(stem)), "cad_geom_check.py")))

    print("%s: %d unconnected, %d violation(s)%s%s"
          % (os.path.basename(stem), best_n, best_v,
             (" -- AND %d verify.py FAIL(s): NOT A CLEAN BOARD" % verify_fails)
             if verify_fails else "",
             (" | quality: %d FAIL, %d OPEN" % quality) if quality else
             " | quality: DID NOT RUN"))
    return best_n, best_v


if __name__ == "__main__":
    # ⚠ --rounds WAS UNREACHABLE, AND IT IS THE MECHANISM FOR THE LAST FEW UNCONNECTED NETS.
    # finish() has taken `rounds` since it was written -- round 2+ hands the nets the router
    # could not finish back to _local_nets with local_mm=1e9, which is the one pass that will
    # lay a long run deterministically -- but this block called finish(stem) with no second
    # argument, so no invocation could ever reach it. The retry loop, the retry.json
    # plumbing, the strictly-better comparison and the .best.kicad_pcb snapshots were all
    # dead code from the command line.
    # Kept at 1 by default: a round is a full route, so asking for 3 asks for three routes.
    _rounds = None                 # None = not given: take the board's own finish_rounds
    _stems = []
    _argv = sys.argv[1:]
    _keep = "--keep-route" in _argv
    _argv = [x for x in _argv if x != "--keep-route"]
    _i = 0
    while _i < len(_argv):
        if _argv[_i] == "--rounds":
            _rounds = int(_argv[_i + 1])
            _i += 2
        elif _argv[_i].startswith("--rounds="):
            _rounds = int(_argv[_i].split("=", 1)[1])
            _i += 1
        else:
            _stems.append(_argv[_i])
            _i += 1
    if not _stems:
        raise SystemExit("usage: finish.py [--rounds N] [--keep-route] <stem> [<stem> ...]")
    for st in _stems:
        # ⚠ A BOARD CAN SAY HOW MANY ROUNDS IT NEEDS (BOARD_NOTES["finish_rounds"]), because
        # a result that only exists under a flag is a result the next plain run loses.
        # output_panel is the case: pass 1 leaves one net open and pass 2 closes it, so a
        # default invocation would hand back a WORSE board than the committed one and
        # report it as the route. An explicit --rounds still wins.
        _r = _rounds
        if _r is None:
            try:
                with open(os.path.abspath(st) + ".board.json", encoding="utf-8") as _fh:
                    _r = int(json.load(_fh).get("finish_rounds", 1))
            except OSError:
                _r = 1
        finish(os.path.abspath(st), rounds=_r, keep_route=_keep)
