#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Open F2's holes until the holder's own pins fit through them.

    py -3.12 elec/make_f2_footprint.py

⚠ THE PART PHYSICALLY WOULD NOT GO IN, and no gate in this repo could have said so.
Punchlist finding 37. KiCad's stock land for this holder drills 1.400 mm, which
finishes at about 1.330 mm once plated. Littelfuse's own drawing (178.6165
datasheet p. 2, "Dimensions", bottom view) gives the terminal pin WIDTH as
1.4 +-0.1 mm -- so the finished hole was smaller than the pin's width before its
thickness was considered at all.

    pin                       diagonal
    1.40 x 1.20 nominal        1.844
    1.50 x 1.20 worst width    1.921   <- what this is sized against
    1.50 x 0.80 thin stamped   1.700   <- the most generous reading, still too big

Under every interpretation the stock hole is undersized, which is why this is not a
tolerance argument.

⚠ AND LITTELFUSE PUBLISHES NO RECOMMENDED LAND. p. 2's "Recommended Assembly" is two
cross-sections carrying no numbers at all -- no pad diameter, no hole, no annular
ring, no keepout. Every number below is therefore DERIVED FROM THE PIN DIMENSION,
which is the one thing the drawing does state.

⚠ WHY THIS DOES NOT WAIT FOR A CALIPER. The owner has the holder in hand and a
measurement would be better than a derivation -- but the error is one-directional. A
hole that is too BIG solders fine: the joint is a fillet and the pin is a loose fit
in a plated barrel. A hole that is too SMALL cannot be assembled at any price, and it
cannot be fixed after fabrication either, because drilling out a plated barrel
destroys the plating and F2 is in the main power path (VBAT_RAW -> VBAT). So this is
sized to the published WORST CASE and ordered on that; a later measurement can only
make it tighter, which is an optional improvement and not a blocker.
"""
import math
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
STOCK = ("C:/Program Files/KiCad/10.0/share/kicad/footprints/Fuse.pretty/"
         "FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165.kicad_mod")
OUT_NAME = "FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165-PINFIT"
OUT = os.path.join(HERE, "footprints", "wbp.pretty", OUT_NAME + ".kicad_mod")

# ── the pin, off the drawing ────────────────────────────────────────────────
PIN_W, PIN_W_TOL = 1.40, 0.10     # p. 2, stated with tolerance
PIN_T = 1.20                      # p. 2 front view; the thickness is NOT toleranced
PIN_DIAG = math.hypot(PIN_W + PIN_W_TOL, PIN_T)        # 1.921

# ── the hole ────────────────────────────────────────────────────────────────
PLATING = 0.07          # mm lost off the drill diameter once the barrel is plated
SLIDE = 0.10            # mm of clearance the pin needs to go in by hand, not press
RING_MIN = 0.13         # the fab's plated annular-ring floor at this class
DRILL_STEP = 0.05       # fabs stock drills in 0.05 mm steps; do not ask for 2.031
ROW_PITCH = 2.5         # the holder's own, off the stock land -- NOT ours to change
# ⚠ 0.45, AND THE 0.25 BELOW USED TO SAY WAS A DIFFERENT RULE READ OFF THE WRONG LINE.
# The fab publishes a generic hole-to-hole and a PAD-hole-to-hole and they are not the
# same number: a pad hole carries an annular ring and a mask relief, so it needs more
# laminate beside it. A12 grades at 0.45. This was invisible here only because the
# routed geometry still named the stock land, so A12 was grading 1.40 mm holes.
HOLE_MIN = 0.45

# ⚠ TWO FLOORS PUSH AGAINST EACH OTHER HERE AND THE PITCH WINS, so this is the one
# number on the part that is a compromise rather than a derivation.
#   the pin wants   1.921 diagonal + 0.10 slide + 0.07 plating = 2.091 -> 2.10 drill
#   the fab allows  2.50 pitch - 0.45 of laminate              =         2.05 drill
# 2.05 it is, and the slide drops from the 0.10 asked for to 0.059 against the
# WORST-CASE pin -- 0.136 against the nominal 1.40 x 1.20. That still admits the part,
# which is the test that matters; 2.10 would not be manufacturable at this pitch. The
# alternative is to merge each terminal's pad pair into a plated slot, which is legal
# (they are one net) but changes the land's topology for 0.04 mm of slide.
_want = PIN_DIAG + SLIDE + PLATING
_by_pin = math.ceil(_want / DRILL_STEP) * DRILL_STEP
# ⚠ THE 1e-9 IS NOT COSMETIC. (2.5 - 0.45) / 0.05 evaluates to 40.99999999999999 in
# binary floating point, so a bare floor() returns 40 and quietly hands back a
# 2.00 mm drill -- 1.930 finished against a 1.921 pin, NINE MICRONS of slide, which
# is not a fit. The number that decides whether a part can be inserted must not be
# decided by the last bit of a division.
_by_fab = math.floor((ROW_PITCH - HOLE_MIN) / DRILL_STEP + 1e-9) * DRILL_STEP
DRILL = min(_by_pin, _by_fab)
# ...and the check of it needs the same tolerance, for the same reason in the other
# direction: 2.5 - 2.05 is 0.44999999999999996, so a bare >= rejects the very drill the
# line above just derived AS the largest legal one. A geometric floor compared at full
# double precision is a floor nothing can sit exactly on.
TOL = 1e-6
assert ROW_PITCH - DRILL >= HOLE_MIN - TOL, (
    "two %.2f mm holes on a %.1f mm pitch leave %.3f mm, under the fab's %.2f"
    % (DRILL, ROW_PITCH, ROW_PITCH - DRILL, HOLE_MIN))
FINISHED = DRILL - PLATING
# the pad has to grow with the hole or the ring goes under the fab's floor -- which is
# the reason finding 37 is a re-spin rather than a one-line drill change
PAD = math.ceil((FINISHED + 2 * RING_MIN) / 0.1) * 0.1  # 2.30

# the slide is no longer the SLIDE asked for -- it is whatever the pitch left -- so
# what is asserted is the thing that actually matters: the part goes in.
assert FINISHED > PIN_DIAG, (
    "a %.2f mm drill finishes at %.3f and the pin's worst-case diagonal is %.3f -- "
    "THE PART CANNOT GO IN" % (DRILL, FINISHED, PIN_DIAG))
assert (PAD - FINISHED) / 2.0 >= RING_MIN, (
    "a %.2f mm pad on a %.3f mm finished hole leaves %.3f mm of annular ring, "
    "under the %.2f the fab can hold"
    % (PAD, FINISHED, (PAD - FINISHED) / 2.0, RING_MIN))

# ── and the land has to stay legal with the bigger pads ─────────────────────
# Stock positions, read out of the file below rather than retyped: four pads per
# terminal on a 2.5 mm row pitch and 3.5 mm across, with the holder's 2.4 mm NON-
# PLATED locking spigot between the two terminals at (6.4, 1.25).
# (ROW_PITCH and HOLE_MIN are set above, where the drill is derived from them.)
# ⚠ THE PADS WITHIN ONE TERMINAL NOW NEARLY TOUCH, AND THAT IS ACCEPTED RATHER THAN
# MISSED. At 2.30 mm on a 2.5 mm pitch the gap is 0.20 mm -- but both pads are the
# SAME NET (all four pads of a terminal are one pin), so this is not a clearance
# violation, it is effectively a slot. 2.40 mm pads would leave 0.10 and buy nothing:
# the ring is already over the floor at 2.30.
PAD_GAP = ROW_PITCH - PAD


def build():
    if not os.path.exists(STOCK):
        print("stock footprint not found: %s" % STOCK)
        return 1
    src = open(STOCK, encoding="utf-8").read()

    # Only the PLATED pads change. The np_thru_hole spigot and everything else --
    # silk, fab, courtyard, the 3D model -- is untouched, which keeps this diffable
    # against the stock land.
    n = [0]

    def fix(m):
        block = m.group(0)
        if "np_thru_hole" in block:
            return block
        n[0] += 1
        block = re.sub(r"\(size [0-9.]+ [0-9.]+\)", "(size %.2f %.2f)" % (PAD, PAD),
                       block)
        block = re.sub(r"\(drill [0-9.]+\)", "(drill %.2f)" % DRILL, block)
        return block

    out = re.sub(r"\n\t\(pad .*?\n\t\)", fix, src, flags=re.S)
    assert n[0] == 8, "expected 8 plated pads, changed %d" % n[0]

    descr = ("Littelfuse 178.6165 ATO blade fuse holder, holes opened to fit the "
             "part: %.2f mm drill (%.3f finished) against a pin whose worst-case "
             "diagonal is %.3f, with %.2f mm pads for %.3f mm of annular ring. "
             "Stock KiCad drills 1.40, which finishes UNDER the pin's width alone. "
             "Derived from the pin dimension on datasheet p.2 because Littelfuse "
             "publishes no land pattern. See punchlist finding 37; generated by "
             "elec/make_f2_footprint.py, do not hand-edit."
             % (DRILL, FINISHED, PIN_DIAG, PAD, (PAD - FINISHED) / 2.0))
    out = re.sub(r'\(descr "[^"]*"\)', '(descr "%s")' % descr, out, count=1)
    out = re.sub(r'\(footprint "[^"]*"', '(footprint "%s"' % OUT_NAME, out, count=1)
    out = out.replace('"FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165"',
                      '"%s"' % OUT_NAME)

    if os.path.exists(OUT):
        shutil.copy(OUT, OUT + ".prev")
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out)
    print("wrote %s" % OUT)
    print("  pin         %.2f(+%.2f) x %.2f  ->  diagonal %.3f mm" %
          (PIN_W, PIN_W_TOL, PIN_T, PIN_DIAG))
    print("  drill       %.2f mm  (was 1.40)  ->  %.3f finished" % (DRILL, FINISHED))
    print("  clearance   %.3f mm of slide over the worst-case pin"
          % (FINISHED - PIN_DIAG))
    print("  pad         %.2f mm  (was 2.20)  ->  %.3f mm annular ring"
          % (PAD, (PAD - FINISHED) / 2.0))
    print("  within one terminal: %.2f mm between pads, SAME NET" % PAD_GAP)
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
