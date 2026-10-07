"""A17's fail harness: break a real board's connector labels on purpose.

    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/test_quality_a17.py \
        elec/out/<board>

A17 says every connector carries its designator, a name for every way and a way-1 mark on
its own side. The board given must PASS the rule as it stands and must have, between its
connectors, one with a word at every way and one with a pinout block and a separate way-1
mark on its own side (the script says which it found, or which it is missing). Then:

  0  the board as it is                      -> no A17 failure, and the summary line
  1  a designator deleted                    -> FAIL for that connector's name, soft
  2  a pinout block moved to the other face  -> FAIL: on the other face and not declared
     ...and declared back_only with a reason -> passes, PRINTS the reason, is counted
     ...and declared with an empty reason    -> FAIL, hard
  3  one way's word deleted                  -> FAIL naming that connector's ways
  4  a way-1 mark deleted                    -> FAIL, hard; a waiver written for it is
                                                ignored and the report says so
  5  back_only declared where the labels     -> FAIL, hard: a stale declaration
     ARE on the connector's side

Each case works on a COPY of the board in a temporary directory. Exit code 0 = every case
answered as it should.
"""
from __future__ import annotations

import gc
import json
import math
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import pcbnew                                   # noqa: E402
import quality                                  # noqa: E402

SILK = (pcbnew.F_SilkS, pcbnew.B_SilkS)


def _case(stem, patch_notes=None, patch_board=None):
    """Copy the board, patch its declarations and/or the board itself, run the pass and
    return A17's rows: [(status, subject, text)]."""
    tmp = tempfile.mkdtemp(prefix="a17-")
    try:
        dst = os.path.join(tmp, os.path.basename(stem))
        shutil.copyfile(stem + ".kicad_pcb", dst + ".kicad_pcb")
        if os.path.isfile(stem + ".net"):
            shutil.copyfile(stem + ".net", dst + ".net")
        with open(stem + ".board.json", encoding="utf-8") as fh:
            notes = json.load(fh)
        notes.setdefault("quality", {})
        if patch_notes:
            patch_notes(notes["quality"])
        with open(dst + ".board.json", "w", encoding="utf-8") as fh:
            json.dump(notes, fh)
        if patch_board:
            b = pcbnew.LoadBoard(dst + ".kicad_pcb")
            patch_board(b)
            b.Save(dst + ".kicad_pcb")
            del b
            gc.collect()
        quality.run(dst, verbose=False)
        with open(dst + ".quality.json", encoding="utf-8") as fh:
            res = json.load(fh)["results"]
        return [(r["status"], r["subject"], r["text"]) for r in res if r["rule"] == "A17"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _fails(rows):
    return [(s, t) for st, s, t in rows if st == "FAIL"]


def _erase(item):
    """Take a drawing out of the print. NOT board.Remove(): after one Remove(), every
    later pcbnew.LoadBoard in the same process hands back a bare SwigPyObject (KiCad 10),
    and this harness loads the board a dozen times. Off the silk layer is as gone as the
    fab is concerned."""
    item.SetLayer(pcbnew.Cmts_User)


def _centre(item):
    b = item.GetBoundingBox()
    return (pcbnew.ToMM(b.GetLeft() + b.GetRight()) / 2.0,
            pcbnew.ToMM(b.GetTop() + b.GetBottom()) / 2.0)


def _find_text(board, string, at):
    """The board-level silk text `string` whose centre is at `at` (as _silk_ink read it)."""
    for d in board.GetDrawings():
        if (d.GetClass() == "PCB_TEXT" and d.GetLayer() in SILK and d.GetText() == string
                and math.dist(_centre(d), at) < 0.05):
            return d
    raise LookupError("no silk text %r at %r" % (string, at))


def _find_dot(board, at):
    for d in board.GetDrawings():
        if d.GetClass() == "PCB_SHAPE" and d.GetLayer() in SILK:
            c = d.GetCenter()
            if math.dist((pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)), at) < 0.05:
                return d
    raise LookupError("no silk dot at %r" % (at,))


def main(stem):
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        print("  %-4s %s%s" % ("ok" if cond else "FAIL", label,
                               "" if cond else "\n       -> " + detail))
        ok = ok and bool(cond)

    # what the rule found on the board as it stands: the things to break
    ctx = quality.Ctx(stem)
    quality.connector_labels(ctx)
    found = ctx.connector_ink
    del ctx             # pcbnew hands back a bare pointer for a second board loaded
    gc.collect()        # while the first is still referenced
    worded = [r for r, f in found.items() if len(f["words"]) > 1
              and not f["own_block"] and f["way1"] in f["words"]]
    blocked = [r for r, f in found.items() if f["own_block"] and f["marks"]
               and f["way1"] not in f["words"]]
    if not worded or not blocked:
        raise SystemExit("%s cannot run this harness: it needs a connector with a word at "
                         "every way (found: %s) and one with a pinout block and a separate "
                         "way-1 mark on its own side (found: %s)"
                         % (os.path.basename(stem), worded or "none", blocked or "none"))
    W, B = sorted(worded)[0], sorted(blocked)[0]
    print("breaking %s (a word at every way) and %s (a pinout block and a way-1 mark)" % (W, B))

    # ── 0. the board as it stands ───────────────────────────────────────────────
    print("case 0  the board as it is")
    rows = _case(stem)
    fails = _fails(rows)
    notes = [t for st, _s, t in rows if st == "note"]
    check("no A17 failure", not fails, "; ".join(t for _s, t in fails))
    check("a summary, not a silence", any("connector(s):" in t for t in notes), "%r" % notes)
    for t in notes:
        print("       %s" % t)

    # ── 1. a designator deleted ──────────────────────────────────────────────────
    print("case 1  %s's designator deleted" % W)

    def no_name(board):
        fp = board.FindFootprintByReference(W)
        fp.Reference().SetVisible(False)
        layer = pcbnew.B_SilkS if fp.IsFlipped() else pcbnew.F_SilkS
        for d in list(board.GetDrawings()):
            if d.GetClass() == "PCB_TEXT" and d.GetLayer() == layer:
                words = d.GetText().split(" ")
                if W in words and "\n" not in d.GetText():
                    rest = " ".join(w for w in words if w != W)
                    if rest:
                        d.SetText(rest)         # "J1 GND": the word stays, the name goes
                    else:
                        _erase(d)
    fails = _fails(_case(stem, patch_board=no_name))
    hit = [t for s, t in fails if s == W]
    check("FAILs, naming the connector", bool(hit) and "designator is not printed" in hit[0],
          "%r" % (fails,))
    check("soft", bool(hit) and not quality.is_hard("A17", hit[0]))
    check("nothing else changed", len(fails) == 1, "%r" % (fails,))
    if hit:
        print("       %s" % hit[0])

    # ── 2. a pinout block moved to the other face ────────────────────────────────
    print("case 2  %s's pinout block moved to the other face" % B)
    s_blk, c_blk = found[B]["own_block"]

    def flip(board):
        d = _find_text(board, s_blk, c_blk)
        back = d.GetLayer() == pcbnew.B_SilkS
        d.SetLayer(pcbnew.F_SilkS if back else pcbnew.B_SilkS)
        d.SetMirrored(not back)
    fails = _fails(_case(stem, patch_board=flip))
    hit = [t for s, t in fails if s == B + " ways"]
    check("FAILs: on the other face and not declared",
          bool(hit) and "other face only" in hit[0] and "does not say why" in hit[0],
          "%r" % (fails,))
    check("soft, and the only failure", len(fails) == 1 and bool(hit)
          and not quality.is_hard("A17", hit[0]), "%r" % (fails,))
    if hit:
        print("       %s" % hit[0])
    why = "the harness moved it there to see this line print"
    rows = _case(stem, lambda q: q.setdefault("connector_labels", {}).update(
        {B: {"back_only": why}}), flip)
    said = [t for st, s, t in rows if st == "note" and s == B + " ways"]
    check("declared with a reason: passes", not _fails(rows), "%r" % (_fails(rows),))
    check("and prints the reason on every run", bool(said) and why in said[0], "%r" % (said,))
    check("and is counted", any("OTHER face (declared)" in t for st, s, t in rows
                                if st == "note" and s == "-"))
    rows = _case(stem, lambda q: q.setdefault("connector_labels", {}).update(
        {B: {"back_only": " "}}), flip)
    hit = [t for s, t in _fails(rows) if "gives no reason" in t]
    check("declared with no reason: FAILs, hard",
          bool(hit) and quality.is_hard("A17", hit[0]), "%r" % (_fails(rows),))

    # ── 3. one way's word deleted ────────────────────────────────────────────────
    k = max(found[W]["words"])
    print("case 3  the word at %s way %d deleted" % (W, k))
    s_w, c_w = found[W]["words"][k]
    fails = _fails(_case(stem, patch_board=lambda b: _erase(_find_text(b, s_w, c_w))))
    hit = [t for s, t in fails if s == W + " ways"]
    check("FAILs on that connector's ways", bool(hit), "%r" % (fails,))
    check("says which way, or that only the other face has it",
          bool(hit) and ("way(s) %d " % k in hit[0] or "other face only" in hit[0]),
          "%r" % (hit,))
    check("the way-1 mark is not what failed",
          not [1 for s, _t in fails if s == W + " way-1"], "%r" % (fails,))
    if hit:
        print("       %s" % hit[0])

    # ── 4. a way-1 mark deleted ──────────────────────────────────────────────────
    print("case 4  %s's way-1 mark deleted" % B)
    marks = found[B]["marks"]

    def unmark(board):
        for kind, s, c in marks:
            _erase(_find_dot(board, c) if kind == "dot" else _find_text(board, s, c))
    fails = _fails(_case(stem, patch_board=unmark))
    hit = [t for s, t in fails if s == B + " way-1"]
    check("FAILs", bool(hit) and "which contact is way" in hit[0], "%r" % (fails,))
    check("hard", bool(hit) and quality.is_hard("A17", hit[0]))
    check("its pinout block does not stand in for the mark",
          not [1 for s, _t in fails if s == B + " ways"], "%r" % (fails,))
    rows = _case(stem, lambda q: q.setdefault("waive", {}).update(
        {"A17:%s way-1" % B: "the harness tried to waive it"}), unmark)
    hit = [t for s, t in _fails(rows) if s == B + " way-1"]
    check("a waiver written for it is IGNORED, and said to be",
          bool(hit) and "IGNORED" in hit[0], "%r" % (_fails(rows),))
    if hit:
        print("       %s" % hit[0])

    # ── 5. a stale declaration ───────────────────────────────────────────────────
    print("case 5  back_only declared for %s, whose words are on its own side" % W)
    fails = _fails(_case(stem, lambda q: q.setdefault("connector_labels", {}).update(
        {W: {"back_only": "left over from an older layout"}})))
    hit = [t for s, t in fails if "stale declaration" in t]
    check("FAILs, hard", bool(hit) and quality.is_hard("A17", hit[0]), "%r" % (fails,))

    print("\n%s" % ("every case answered as it should" if ok else "A17 HARNESS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    a = args[0]
    sys.exit(main(os.path.abspath(a[:-10] if a.endswith(".kicad_pcb") else a)))
