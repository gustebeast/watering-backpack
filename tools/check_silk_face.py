"""The CAD letters the board in the face the FAB plots — checked, not assumed.

    py -3.12 tools/check_silk_face.py

⚠ WRITTEN BECAUSE NOTHING READ THE TYPEFACE (finding 57). elec/silk.py moved
the silkscreen to "Rennie Mackintosh PSG" at finding 52 and the CAD was never
told, so the board was PLOTTED in Rennie Mackintosh and DRAWN in the CAD
kernel's default face for as long as that took to notice. Every gate passed:
`elec/cad_geom_check.py` counts labels by probing for ink where each label is
printed and reported 139 / 139 the whole time, because a label in the wrong
typeface is still a label with ink in it. The face was a figure no gate read.

⚠ EVERY CHECK HERE FAILS RATHER THAN SKIPS. A missing font is not "nothing to
check" — it is the exact condition the CAD was in while it was wrong. A gate
that excuses itself when its subject is absent reports as a pass.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src import silk_face as SF                                    # noqa: E402

HOUSING = os.path.join(ROOT, "src", "housing.py")
GEOM = os.path.join(ROOT, "elec", "geom", "main.geom.json")

fails: list[str] = []
notes: list[str] = []


def fail(msg):
    fails.append(msg)
    print("  FAIL  %s" % msg)


def ok(msg):
    print("  ok    %s" % msg)


print("declared in elec/silk.py: %r%s" % (SF.FAMILY, " Bold" if SF.BOLD else ""))

# ── 1. the declared face must RESOLVE to a file on this machine ─────────────
path, how = SF.font_path()
if path is None:
    fail("the declared face does not resolve: %s" % how)
    print("\n%d FAIL(s) -- the CAD cannot be lettered in the ordered face here."
          % len(fails))
    sys.exit(1)
ok("resolves to %s (%s)" % (os.path.basename(path), how))
if "FILENAME MATCH" in how:
    notes.append("resolved by filename only -- install fontTools to verify the "
                 "family inside the file")

# ── 2. the kernel must ACTUALLY APPLY it ────────────────────────────────────
# Everything below would still pass if CadQuery silently ignored `fontPath`,
# so this is the check the others rest on: the face must draw DIFFERENTLY from
# the kernel's default.
cap = SF.cap_ratio(path)
cap_default = SF.cap_ratio(None)
if abs(cap - cap_default) < 1e-4:
    fail("the drawing kernel renders this face identically to its DEFAULT face "
         "(cap ratio %.4f both) -- fontPath is being ignored, so nothing below "
         "means anything" % cap)
else:
    ok("the kernel applies it: cap ratio %.4f vs the default face's %.4f"
       % (cap, cap_default))

# ── 3. the right FILE, not merely the right family ──────────────────────────
# ITC's original Rennie Mackintosh Bold draws "+" as a TH LIGATURE and "=" as
# TT. Both files carry the same family name, so check 1 proves nothing about
# WHICH is installed -- "+5V" has plotted as "TH5V" on real boards with every
# check passing. elec/silk.py declares the discriminator in `widths`: the
# ADVANCE of "+" against "H", 0.97 here and 1.42 in the file it replaces.
#
# ⚠ THE EXPECTED NUMBER IS NOT TYPED HERE. It is read from the same SILK_FACE
# the fab side uses, so there is one declaration and this gate cannot drift
# from it. (An earlier draft of this check asked whether "+" stands cap-height
# instead; measured across all 135 installed faces that separates nothing --
# Courier Bold's plain "+" is 0.960 of cap height. See src/silk_face.py.)
declared_w = SF.SILK_FACE.get("widths") or {}
if not declared_w:
    fail("elec/silk.py declares no `widths` -- without it, nothing distinguishes "
         "the PSG file from ITC's original, which share a family name")
else:
    try:
        measured_w = SF.advance_ratios(path)
    except ImportError:
        fail("fontTools is not installed, so the advance ratios that prove WHICH "
             "file is installed cannot be read. Not a skip: the TH-ligature file "
             "resolves identically by family name.")
        measured_w = {}
    except Exception as exc:                                    # noqa: BLE001
        fail("could not read advance ratios from %s: %s" % (os.path.basename(path), exc))
        measured_w = {}
    for key, want in sorted(declared_w.items()):
        got = measured_w.get(key)
        if got is None:
            continue
        if abs(got - want) > 0.02:
            fail("advance %s is %.4f in the installed file; elec/silk.py declares "
                 "%.4f. This is a DIFFERENT FILE of the same family -- ITC's "
                 "original measures about 1.42 here." % (key, got, want))
        else:
            ok("advance %s = %.4f, within 0.02 of the declared %.4f -- the "
               "redrawn file, not ITC's original" % (key, got, want))

# ── 4. src/housing.py must actually PASS it to the Boards that draws ────────
# The resolver working is not the same as the drawing using it.
src = open(HOUSING, encoding="utf-8").read()
m = re.search(r"_BOARDS\s*=\s*Boards\((.*?)\)\n", src, re.S)
if not m:
    fail("no `_BOARDS = Boards(...)` found in src/housing.py -- this gate no "
         "longer knows where the board is drawn")
else:
    call = m.group(1)
    for kw in ("silk_font", "silk_cap"):
        if kw + "=" not in call:
            fail("src/housing.py's Boards(...) does not pass %s= -- the CAD is "
                 "drawing in the kernel default face again" % kw)
    if "silk_font=" in call and "silk_cap=" in call:
        ok("src/housing.py passes silk_font= and silk_cap= to the drawing Boards")

# ── 5. the cap ratio in use must be the MEASURED one ────────────────────────
# ⚠ READ THE Boards INSTANCE, NOT THE MODULE VARIABLES IT COMPUTED. This
# check used to read H._SILK_CAP, which is what src/housing.py MEASURED --
# so hardcoding `silk_cap=0.72` in the Boards(...) call left _SILK_CAP at
# 0.6670 and this passed while the drawing was 7.9 % wrong. The failure
# harness caught it. The object the lettering is drawn from is the only
# thing worth asking.
try:
    from src import housing as H
    used = H._BOARDS.silk_cap
    used_font = H._BOARDS.silk_font
except Exception as exc:                                        # noqa: BLE001
    fail("could not read the face src/housing.py is using: %s" % exc)
    used = used_font = None

if used is not None:
    if used_font != path:
        fail("src/housing.py draws with %r but this gate resolves %r"
             % (used_font, path))
    elif abs(used - cap) > 1e-4:
        fail("src/housing.py uses silk_cap %.4f; this face measures %.4f through "
             "the same kernel (%.1f %% off)"
             % (used, cap, abs(used - cap) / cap * 100.0))
    else:
        ok("silk_cap in use is the measured %.4f" % used)

# ── 6. the face must HAVE every character the board prints ─────────────────
# ⚠ ASK THE FONT, NOT THE RENDERER. This check used to draw each character and
# fail if no ink came out. OCC does not come back empty for a glyph the face
# lacks -- it SILENTLY SUBSTITUTES another font. The PSG face has no CJK, and
# cq.text("\u4e2d", fontPath=PSG) returns 33 faces, 9.18 mm tall at size 10
# against this face's 6.67 mm cap height. So the old check was satisfied by
# precisely the failure it was looking for, and the substitution is the real
# hazard: a label drawn in a DIFFERENT typeface, which is finding 57 again.
#
# The cmap is exact and needs no rendering. (elec/silk.py gates the same
# question on the FAB side against its reviewed `glyphs` list; this is the
# drawing side, and the two can disagree.)
chars = set()
try:
    import json
    for lab in json.load(open(GEOM, encoding="utf-8"))["silk"]:
        chars.update(lab["text"])
except Exception as exc:                                        # noqa: BLE001
    fail("could not read the routed board's silk from %s: %s"
         % (os.path.relpath(GEOM, ROOT), exc))

chars.discard(" ")
if chars:
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(path, fontNumber=0, lazy=True)
        try:
            cmap = f.getBestCmap()
        finally:
            f.close()
        absent = sorted(c for c in chars if ord(c) not in cmap)
        if absent:
            fail("the face has NO GLYPH for %d character(s) the board prints: %s "
                 "-- the drawing kernel will substitute another font for them "
                 "without saying so" % (len(absent), " ".join(repr(c) for c in absent)))
        else:
            ok("the face has a glyph for all %d character(s) the routed board "
               "prints" % len(chars))
    except ImportError:
        fail("fontTools is not installed, so the face's character map cannot be "
             "read. Not a skip: a missing glyph is silently substituted by the "
             "kernel, so rendering cannot answer this.")
    except Exception as exc:                                    # noqa: BLE001
        fail("could not read the character map of %s: %s"
             % (os.path.basename(path), exc))

for n in notes:
    print("  note  %s" % n)

print("\n%s" % ("%d FAIL(s)" % len(fails) if fails
                else "the CAD is lettered in the face the fab plots"))
sys.exit(1 if fails else 0)
