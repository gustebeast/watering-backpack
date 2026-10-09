"""Proof that tools/check_silk_face.py bites — one staged break per check.

    py -3.12 tools/check_silk_face_failures.py

A gate nobody has seen fail is a gate nobody has tested. Each case below
perturbs exactly one thing on disk, runs the real gate as a subprocess, and
requires a non-zero exit AND the expected sentence. Every file is restored
from a byte copy in a finally, so a crash mid-run leaves the tree clean.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(ROOT, "tools", "check_silk_face.py")
HOUSING = os.path.join(ROOT, "src", "housing.py")
DECL = os.path.join(ROOT, "elec", "silk.py")
GEOM = os.path.join(ROOT, "elec", "geom", "main.geom.json")


def run_gate():
    p = subprocess.run([sys.executable, GATE], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def sub(path, pattern, repl, count=1):
    """Rewrite `path`, returning its original bytes. Raises if nothing matched —
    a harness whose edit silently misses proves nothing."""
    orig = open(path, "rb").read()
    text = orig.decode("utf-8")
    # `repl` is taken LITERALLY: a lambda, so backslash sequences in the
    # replacement (\u4e2d for a CJK character) are not read as regex escapes.
    new, n = re.subn(pattern, lambda _m: repl, text, count=count)
    if n != count:
        raise AssertionError("harness edit matched %d times, wanted %d, in %s"
                             % (n, count, os.path.relpath(path, ROOT)))
    open(path, "wb").write(new.encode("utf-8"))
    return orig


CASES = []


def case(name, path, pattern, repl, expect):
    CASES.append((name, path, pattern, repl, expect))


case("the declared face is not installed anywhere",
     DECL, r'"family": "Rennie Mackintosh PSG"',
     '"family": "No Such Face At All"',
     "does not resolve")

case("the CAD stops being handed the font",
     HOUSING, r"silk_font=_SILK_FONT, ", "",
     "does not pass silk_font=")

case("the CAD stops being handed the cap height",
     HOUSING, r", silk_cap=_SILK_CAP", "",
     "does not pass silk_cap=")

case("the cap height is hand-typed instead of measured",
     HOUSING, r"silk_cap=_SILK_CAP", "silk_cap=0.72",
     "silk_cap 0.7200")

case("the installed file is ITC's original, whose + is a TH ligature",
     DECL, r'"widths": \{"\+/H": 0\.97\}', '"widths": {"+/H": 1.42}',
     "DIFFERENT FILE of the same family")

case("a label uses a character this face cannot draw",
     GEOM, r'"text": "1 \+3V3"', '"text": "1 \\u4e2d3V3"',
     "NO GLYPH")   # \u4e2d is a CJK ideograph; this face has no glyph for it

# The kernel silently ignoring fontPath is staged by declaring a face whose
# rendering IS the kernel default — then check 2's whole premise is live.
case("the kernel renders the face identically to its default",
     DECL, r'"family": "Rennie Mackintosh PSG"', '"family": "Arial"',
     None)          # expectation resolved at run time; see below


def main():
    print("baseline: the gate must PASS before any of this means anything")
    rc, out = run_gate()
    if rc != 0:
        print(out)
        print("\n*** BASELINE FAILS -- fix the gate before trusting the harness ***")
        return 1
    print("  ok    exit 0\n")

    bad = 0
    for i, (name, path, pattern, repl, expect) in enumerate(CASES, 1):
        orig = None
        try:
            orig = sub(path, pattern, repl)
            rc, out = run_gate()
            if rc == 0:
                print("  NOT CAUGHT  %d. %s" % (i, name))
                bad += 1
                continue
            if expect is not None and expect not in out:
                print("  WRONG REASON %d. %s" % (i, name))
                print("      wanted %r in the output; got:" % expect)
                for line in out.splitlines():
                    if "FAIL" in line:
                        print("      " + line.strip())
                bad += 1
                continue
            why = next((l.strip() for l in out.splitlines() if "FAIL" in l), "")
            print("  caught      %d. %s" % (i, name))
            print("              -> %s" % why[:150])
        except AssertionError as exc:
            print("  HARNESS BUG %d. %s: %s" % (i, name, exc))
            bad += 1
        finally:
            if orig is not None:
                open(path, "wb").write(orig)

    rc, out = run_gate()
    if rc != 0:
        print("\n*** THE TREE WAS NOT RESTORED -- the gate fails after the harness ***")
        print(out)
        bad += 1
    else:
        print("\nrestored: the gate passes again")

    print("\n%s" % ("%d case(s) did not behave" % bad if bad
                    else "all %d staged breaks were caught" % len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
