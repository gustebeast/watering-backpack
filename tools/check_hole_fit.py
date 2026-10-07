#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Does every plated hole admit the pin that has to go through it?

    py -3.12 tools/check_hole_fit.py

⚠ THIS GATE EXISTS BECAUSE NOTHING COMPARED A HOLE TO A PIN. Punchlist finding 37:
F2's holes were drilled 1.400 mm, finishing about 1.330 mm plated, for a holder whose
pin is 1.4 +-0.1 mm WIDE and 1.2 mm thick -- a worst-case diagonal of 1.921 mm. The
part could not have been inserted. It got all the way to a cart.

Every other geometry check in this repo compares the board to ITSELF or to the fab's
rules -- annular ring, hole-to-hole, clearance, courtyard. All of those passed, and
all of them would pass again, because the pin's size lives in a datasheet and nothing
read it. That is the whole category of defect this file is for.

THE RULE, strict in the same way A16 is: a plated hole on a part THIS BOARD PLACES,
with no declared pin, is a FAILURE. An undeclared hole is not a hole that fits; it is
a hole nobody checked. An ESTIMATE is allowed and a bare number is not -- every entry
carries its source, and `est:` marks the ones not read off a drawing (PCB_README).

⚠ SHAPE IS NOT A DETAIL, AND GETTING IT WRONG WAS THIS FILE'S OWN FIRST BUG. The
first version took hypot(w, t) for every pin, which is right for a stamped blade and
wrong for a round lead: it charged a 1.0 mm round terminal pin 1.414 mm of hole and
"failed" three terminal blocks and a pin header that have fitted their stock lands for
decades. A round pin needs its DIAMETER. The shape is therefore declared, not assumed,
and the two cases are computed differently.
"""
import glob
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GEOM = os.path.join(ROOT, "elec", "geom")
PROJ_FP = os.path.join(ROOT, "elec", "footprints", "wbp.pretty")
STOCK_ROOT = "C:/Program Files/KiCad/10.0/share/kicad/footprints"

PLATING = 0.07          # mm off the drill diameter once the barrel is plated
# ⚠ 0.02, AND IT IS A FLOOR AND NOT A TARGET. A 2.54 mm header post is 0.64 mm
# square, 0.905 across the diagonal, into a 1.00 mm drill that finishes 0.93 -- 25 um,
# and those have been a press fit since before surface mount. So this gate asks only
# that the pin GOES IN; a part that has to be inserted by hand wants more, and the
# generator that owns such a part asks for it there (make_f2_footprint.py wants 0.10).
SLIDE = 0.02

# ── the pins: (shape, a, b, source). "round" uses a as the diameter and ignores b;
#    "rect" is a stamped pin and uses the diagonal of a x b.
PINS = {
    "FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165-PINFIT": (
        "rect", 1.50, 1.20,
        "Littelfuse 178.6165 datasheet p.2 bottom view: pin width 1.4 +-0.1, so "
        "1.50 worst case; 1.20 thickness off the front view. STAMPED, so the "
        "diagonal is what has to pass."),
    "PinHeader_1x06_P2.54mm_Vertical": (
        "rect", 0.64, 0.64,
        "a 2.54 mm header post is 0.64 mm square -- the dimension this whole part "
        "class shares, and the one KiCad's 1.00 mm drill is drawn around"),
    "Buzzer_12x9.5RM7.6": (
        "round", 0.60, 0.60,
        "est: the HYDZ 12 mm magnetic buzzer (LCSC C252936) publishes its 7.6 mm "
        "pitch and body but not its lead; 0.6 round is the conservative end for "
        "this part class. The PITCH is the dimension that had to match and it is "
        "checked elsewhere (M42's alternate is chosen on it)"),
    # ⚠ NO ENTRY FOR CP_Elec_10x10.5, AND THAT IS DELIBERATE. C1 and C2 look like
    # the most through-hole parts on the board -- two 10 x 10.5 mm cans -- and they
    # are SMD: KiCad resolves that name out of Capacitor_SMD.pretty and the land is
    # two 4.4 x 2.5 mm roundrects with no drill anywhere. An entry here would be a
    # declared pin for a part that has none, which is the same kind of false record
    # this gate exists to catch. If a radial THT electrolytic is ever fitted, it
    # needs its own footprint and its own entry.
}
_MKDS = ("round", 1.00, 1.00,
         "est: the land is an MKDS-3 and the part fitted is a Ningbo Kangnex "
         "WJ500V-5.08-NP, whose customer drawing (LCSC C8465) dimensions the body "
         "but not the pin. ROUND 1.0 is what this class of 5.08 mm block uses and "
         "what KiCad's 1.30 mm drill is drawn around. MEASURE IT if one is reseated.")
for _n in ("2-5.08_1x02", "4-5.08_1x04", "5-5.08_1x05"):
    PINS["TerminalBlock_Phoenix_MKDS-3-%s_P5.08mm_Horizontal" % _n] = _MKDS

# A pad marked pad_prop_heatsink is a THERMAL VIA inside a land, not a lead hole --
# U1's and U2's exposed pads. Those are graded by A14 and by the footprint
# generators, not here: nothing is inserted into them.
HEATSINK = "pad_prop_heatsink"

# ⚠ THE GATE'S OWN FAIL CASE, RUN EVERY TIME. A gate that has only ever returned
# "ok" has not been shown to be looking. This is the land finding 37 actually found,
# still on disk in KiCad's library, and it MUST come back as a failure -- so the
# check that catches it is exercised on every run rather than once by hand.
SELFTEST = ("FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165",
            PINS["FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165-PINFIT"])

PAD_RE = re.compile(r"\(pad\s+\"([^\"]*)\"\s+(\S+)\s+\S+(.*?)(?=\n\t\(pad |\n\t\(embedded|\n\)\s*$)",
                    re.S)
DRILL_RE = re.compile(r"\(drill\s+([0-9.]+)")


def _required(shape, a, b):
    """The smallest round hole a pin of this shape passes through."""
    if shape == "round":
        return a
    if shape == "rect":
        return math.hypot(a, b)
    raise ValueError("unknown pin shape %r" % shape)


def _resolve(name):
    p = os.path.join(PROJ_FP, name + ".kicad_mod")
    if os.path.exists(p):
        return p
    hit = glob.glob(os.path.join(STOCK_ROOT, "*.pretty", name + ".kicad_mod"))
    return hit[0] if hit else None


def _plated_drills(path):
    """The drill diameters of every PLATED lead hole in a footprint."""
    src = open(path, encoding="utf-8").read()
    out = []
    for m in PAD_RE.finditer(src):
        kind, body = m.group(2), m.group(3)
        d = DRILL_RE.search(body)
        if not d or kind == "np_thru_hole" or HEATSINK in body:
            continue
        out.append(float(d.group(1)))
    return out


def _judge(name, pin, drills, label="  "):
    shape, a, b, src = pin
    need = _required(shape, a, b)
    worst = min(drills)
    finished = worst - PLATING
    slack = finished - need
    ok = slack >= SLIDE
    print("%s%-4s %-56s %s pin %.2f x %.2f, needs %.3f"
          % (label, "ok" if ok else "FAIL", name[:56], shape, a, b, need))
    print("%s     smallest drill %.2f -> %.3f finished, %+.3f mm of slide"
          % (label, worst, finished, slack))
    print("%s     %s" % (label, src))
    if not ok:
        print("%s     *** THE PART CANNOT GO IN: a %.3f mm finished hole does not "
              "admit %.3f mm." % (label, finished, need))
    return ok


def main():
    bad = 0
    checked = 0
    boards = sorted(glob.glob(os.path.join(GEOM, "*.geom.json")))
    if not boards:
        print("no exported geometry; run elec/main.py and finish.py first")
        return 1

    print("=== plated holes against the pins that go through them ===")
    for bp in boards:
        g = json.load(open(bp, encoding="utf-8"))
        board = os.path.basename(bp)[: -len(".geom.json")]
        # Only the parts THIS BOARD PLACES, and only the ones with THT pads. The
        # list comes off the routed board, never from a list kept by hand.
        # ⚠ EVERY FOOTPRINT, AND THE HOLES COME FROM THE FOOTPRINT FILE. The first
        # version filtered on the geom's `tht` field, which sounds exactly right and
        # is not: `tht` is about modelled LEG TAILS for the CAD, not about drilled
        # pads, so C1 and C2 -- two 10 x 10.5 mm through-hole electrolytics with a
        # plated hole each -- reported tht=None and were invisible to this gate. A
        # gate reading a field that merely sounds like the one it wants is the same
        # class of mistake as the one it was written to catch.
        seen = {}
        for f in g["footprints"]:
            seen.setdefault(f["fpid"].split(":")[-1], []).append(f["ref"])
        print("%s: %d footprint(s) with plated holes" % (board, len(seen)))
        for name in sorted(seen):
            refs = ", ".join(sorted(seen[name]))
            path = _resolve(name)
            if path is None:
                print("  *** %s (%s): footprint not found, so its holes cannot be "
                      "read" % (name, refs))
                bad += 1
                continue
            drills = _plated_drills(path)
            if not drills:
                continue
            pin = PINS.get(name)
            if pin is None:
                print("  *** %s (%s): %d plated hole(s) and NO DECLARED PIN."
                      % (name, refs, len(drills)))
                print("      An undeclared hole is not a hole that fits, it is a "
                      "hole nobody checked. Add it to PINS with its source.")
                bad += 1
                continue
            checked += 1
            if not _judge("%s  [%s]" % (name, refs), pin, drills):
                bad += 1

    print("\n=== the gate's own fail case: the land finding 37 found ===")
    st_path = _resolve(SELFTEST[0])
    if st_path is None:
        print("  *** the stock land is gone, so this check proves nothing")
        bad += 1
    else:
        caught = not _judge(SELFTEST[0], SELFTEST[1], _plated_drills(st_path))
        print("  -> %s" % ("CAUGHT, as it must be" if caught else
                           "*** NOT CAUGHT -- this gate is not looking ***"))
        if not caught:
            bad += 1

    print("\n%d footprint(s) checked against a declared pin" % checked)
    print("every plated hole admits its pin" if not bad
          else "*** %d HOLE/PIN FAILURE(S) ***" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
