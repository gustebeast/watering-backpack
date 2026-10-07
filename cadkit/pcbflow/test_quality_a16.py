"""A16's fail harness: break a real board on purpose and check the rule says so.

    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/test_quality_a16.py \
        elec/out/main

A gate nobody has seen FAIL is a gate nobody has tested. A16 is the rule that says every
net's worst-case voltage is declared and every pin on it is rated for what it sees, so the
harness asks it five different questions and insists on five different answers:

  0  the board as it is                     -> no A16 failure, and a MEASUREMENT (the
                                               tightest steady-state margin), not a silence
  1  a 20 V net on a 16 V part              -> FAIL, naming the part AND the pin
  2  one pin whose rating is deleted        -> FAIL for that pin, not a quiet pass
  3  every rating gone (pin_volts emptied   -> the rule says it can make NO CLAIM, rather
     and the voltage qualifiers stripped       than reporting a clean board
     out of the BOM values)
  4  net_volts emptied                      -> likewise: no net has a worst case, so there
                                               is nothing to make a claim against
  5  a transient raised above a rating      -> FAIL, and a DIFFERENT one from case 1: the
                                               clamped transient, which is soft, where the
                                               steady-state failure is hard

Each case works on a COPY of the board, in a temporary directory: nothing here can touch
the project's own files. Exit code 0 = every case answered as it should.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import pcbnew                                   # noqa: E402
import quality                                  # noqa: E402


def _case(stem, name, patch_notes=None, patch_board=None):
    """Copy the board into a temp dir, patch its declarations (and, optionally, the board
    itself), run the pass and return A16's rows: [(status, subject, text)]."""
    tmp = tempfile.mkdtemp(prefix="a16-")
    try:
        dst = os.path.join(tmp, os.path.basename(stem))
        shutil.copyfile(stem + ".kicad_pcb", dst + ".kicad_pcb")
        with open(stem + ".board.json", encoding="utf-8") as fh:
            notes = json.load(fh)
        if patch_notes:
            patch_notes(notes["quality"])
        with open(dst + ".board.json", "w", encoding="utf-8") as fh:
            json.dump(notes, fh)
        if patch_board:
            b = pcbnew.LoadBoard(dst + ".kicad_pcb")
            patch_board(b)
            b.Save(dst + ".kicad_pcb")
        quality.run(dst, verbose=False)
        with open(dst + ".quality.json", encoding="utf-8") as fh:
            res = json.load(fh)["results"]
        return [(r["status"], r["subject"], r["text"]) for r in res if r["rule"] == "A16"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _fails(rows):
    return [(s, t) for st, s, t in rows if st == "FAIL"]


def _strip_value_volts(board):
    """Take the voltage qualifier out of every BOM value ("10u/25V" -> "10u"), so no part
    on the board states a rating anywhere."""
    for fp in board.GetFootprints():
        fp.SetValue(quality.VALUE_VOLTS.sub("", fp.GetValue() or ""))


def main(stem):
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        print("  %-4s %s%s" % ("ok" if cond else "FAIL", label,
                               "" if cond else "\n       -> " + detail))
        ok = ok and bool(cond)

    # ── 0. the board as it stands. A harness that only ever fails proves nothing ──
    rows = _case(stem, "clean")
    fails = _fails(rows)
    notes = [t for st, _s, t in rows if st == "note"]
    print("case 0  the board as it is")
    check("no A16 failure", not fails, "; ".join(t for _s, t in fails))
    check("a measurement, not a silence",
          any("margin" in t for t in notes), "no margin note: %r" % notes)
    for t in notes:
        print("       %s" % t)

    # ── 1. a 20 V net on a 16 V part ─────────────────────────────────────────────
    # C17 is a 10u/50V on VBAT, which is 20 V steady. Rate it 16 and the rule has to
    # name the part and the pin.
    print("case 1  a 20 V net on a 16 V part")
    rows = _case(stem, "under-rated",
                 lambda q: q["pin_volts"].update(
                     {"C17": {"max": 16.0, "src": "the A16 harness: a deliberate lie"}}))
    fails = _fails(rows)
    hit = [t for s, t in fails if s == "C17.1"]
    check("FAILs", bool(hit), "A16 did not fail: %r" % (fails,))
    check("names the part and the pin",
          hit and "C17.1" in hit[0] and "10u/50V" in hit[0], "%r" % (hit,))
    check("names both numbers", hit and "16 V" in hit[0] and "20 V" in hit[0], "%r" % (hit,))
    check("hard: a waiver would be ignored",
          bool(hit) and quality.is_hard("A16", hit[0]), "%r" % (hit,))
    check("nothing else changed", len(fails) == 1, "%r" % (fails,))
    if hit:
        print("       %s" % hit[0])

    # ── 2. a pin with no rating at all ───────────────────────────────────────────
    # C8 is the one 1 uF on the board and its value string carries no voltage, so the
    # entry keyed "1u" is the only thing that rates it. Delete that entry.
    print("case 2  a pin with no rating at all")
    rows = _case(stem, "unrated", lambda q: q["pin_volts"].pop("1u"))
    fails = _fails(rows)
    hit = [t for s, t in fails if s == "C8.1"]
    check("FAILs rather than passing quietly", bool(hit), "%r" % (fails,))
    check("says WHY an unrated pin is not a pass",
          hit and "nobody has done" in hit[0], "%r" % (hit,))
    check("hard", bool(hit) and quality.is_hard("A16", hit[0]), "%r" % (hit,))
    if hit:
        print("       %s" % hit[0])

    # ── 3. every rating absent ───────────────────────────────────────────────────
    print("case 3  a board where every rating is absent")
    rows = _case(stem, "no ratings", lambda q: q.__setitem__("pin_volts", {}),
                 _strip_value_volts)
    fails = _fails(rows)
    claim = [t for _s, t in fails if "can make NO CLAIM" in t]
    check("says it can make no claim", bool(claim), "%r" % (fails[:3],))
    check("does not report a clean board", bool(fails))
    check("hard", bool(claim) and quality.is_hard("A16", claim[0]))
    if claim:
        print("       %s" % claim[0])

    # ── 4. no net voltages at all ────────────────────────────────────────────────
    print("case 4  a board that declares no net voltages")
    rows = _case(stem, "no nets", lambda q: q.__setitem__("net_volts", {}))
    fails = _fails(rows)
    claim = [t for _s, t in fails if "can make NO CLAIM" in t]
    check("says it can make no claim", bool(claim), "%r" % (fails[:3],))
    check("grades nothing instead of passing everything",
          not [1 for st, _s, t in rows if st == "ok" and " against " in t],
          "something was still graded: %r" % (rows[:3],))
    if claim:
        print("       %s" % claim[0])

    # ── 5. a transient over a rating, which is a different answer ────────────────
    print("case 5  a clamped transient over a rating")

    def raise_clamp(q):
        for key, spec in q["net_volts"].items():
            if isinstance(spec, dict) and spec.get("peak"):
                spec["peak"] = 100.0
    rows = _case(stem, "clamp", raise_clamp)
    fails = _fails(rows)
    trans = [(s, t) for s, t in fails if "clamped transient" in t]
    check("FAILs on the transient", bool(trans), "%r" % (fails[:3],))
    check("and only on the transient",
          len(trans) == len(fails) and not [1 for _s, t in fails
                                            if "steady-state worst case" in t],
          "%r" % (fails[:3],))
    check("soft: it is the case a declaration can answer",
          bool(trans) and not quality.is_hard("A16", trans[0][1]), "%r" % (trans[:1],))
    check("names the pin and how far over",
          bool(trans) and " over, for as long as the clamp conducts" in trans[0][1])
    if trans:
        print("       %d pin(s) over, e.g. %s" % (len(trans), trans[0][1]))

    print("\n%s" % ("every case answered as it should" if ok else "A16 HARNESS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    a = args[0]
    sys.exit(main(os.path.abspath(a[:-10] if a.endswith(".kicad_pcb") else a)))
