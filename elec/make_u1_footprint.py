#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cut U1's land to TI's own numbers, from the stock KiCad footprint.

    py -3.12 elec/make_u1_footprint.py          # writes wbp.pretty/<OUT>.kicad_mod

⚠ WHY THIS IS A SCRIPT AND NOT A HAND-EDITED .kicad_mod. The two footprints already
in `wbp.pretty` are edited copies, and that was fine while the edit was one number
(a via drill opened to the fab floor). This one is eleven numbers across three
layers, every one of them read off a specific page of a specific drawing, and the
thing that makes it reviewable is that the page citation sits next to the number
rather than three documents away. Re-running it after a KiCad update also re-reads
the stock land, so a change upstream shows up as a diff instead of being silently
overridden by a stale copy.

THE SOURCE, and it is one document: TI SNVSAA5B, LMR14020SDDA.
  * package drawing 4214849/B p. 31  -- outline, exposed-pad min/max
  * p. 32                            -- example board layout, and the note that the
                                        EP is mask-defined "to prevent shorting to
                                        leads"
  * p. 33                            -- example stencil
  * app note SLMA002H 2.4, pp. 8-10  -- EP land, paste coverage, via tenting
                                        2.3, p. 4 -- on a 2-layer board the surface
                                        layers are all the heat removal there is

WHAT WAS WRONG, measured in punchlist finding 38 -- four deficits, all in the same
direction, on the one part whose datasheet calls its exposed pad "the major heat
dissipation path of the die":

    item            was              TI              deviation
    EP copper       2.29 x 3.00      2.95 x 4.90     -52 % copper
    EP mask         2.29 x 3.00      2.71 x 3.40     -25 % solderable
    definition      mask == copper   mask-defined    not SMD at all
    thermal paste   4 windows 4.8    solid 9.21      52 % of the volume
    signal pad      1.95 x 0.60      1.55 x 0.60     +0.40, ALL of it inboard

The last one is the one that is easy to wave through and should not be. The toe is
right; the extra 0.40 mm goes inboard, under the body, toward the exposed pad -- so
the lead-to-EP solder gap was 0.355 mm against TI's 0.570, eroded by 38 %, at the
same time as the leads carried +26 % paste and the EP got -48 %. The leads float
the package off a paste-starved thermal pad while carrying surplus solder a third
of a millimetre from it.
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STOCK = ("C:/Program Files/KiCad/10.0/share/kicad/footprints/Package_SO.pretty/"
         "SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3mm.kicad_mod")
OUT_NAME = "SOIC-8-1EP-FABDRILL"          # same name: the netlist already asks for it
OUT = os.path.join(HERE, "footprints", "wbp.pretty", OUT_NAME + ".kicad_mod")

# ── TI's numbers ────────────────────────────────────────────────────────────
EP_CU_X, EP_CU_Y = 2.95, 4.90      # p. 32 example layout
EP_MASK_X, EP_MASK_Y = 2.71, 3.40  # p. 31: the MAXIMUM exposed pad, and p. 32/
                                   # SLMA002H p. 9 both say define the SMD pad to
                                   # the maximum, not the nominal -- otherwise a
                                   # max-size part's pad overhangs onto solder mask
                                   # and the joint varies lot to lot.
LEAD_X, LEAD_Y = 1.55, 0.60        # p. 32
LEAD_TOE = 3.475                   # half of TI's 6.95 outer-edge span
LEAD_CX = LEAD_TOE - LEAD_X / 2.0  # 2.700 -- the toe is what stays put

# ⚠ 0.30, NOT TI's 0.20, AND THE REASON IS THE FAB AND NOT THE DATASHEET. This is
# the whole point of the -FABDRILL name: JLCPCB's floor for a plated via is 0.30 mm,
# so a 0.20 mm hole is not manufacturable here at any price. That is not a rounding
# error, it is 2.25x the hole area and therefore 2.25x the barrel volume, and barrel
# volume is the thing that decides finding 32.
VIA_DRILL, VIA_PAD = 0.30, 0.50

# ⚠ EVERY BARREL SITS OUTSIDE THE MASK OPENING, AND THAT IS FINDING 32'S FIX --
# arrived at by arithmetic rather than by the fix the finding itself proposed.
#
# Finding 32 asked for two things: move the via pads clear of the paste, and tent the
# barrels on the COMPONENT side (SLMA002H p. 9 -- tenting from the far side instead
# traps flux gas and shows as voiding in x-ray, which is what this board did). The
# obvious way to do both is mask islands over each barrel INSIDE the opening. Costed,
# that is a bad trade: eight 0.70 mm dots inside a 2.71 x 3.40 opening take 3.9 of
# 9.21 mm2, so tenting in place would cost 43 % of the solderable area -- worse than
# the 25 % deficit finding 38 is here to fix.
#
# WHY THE PASTE MATTERS MORE THAN IT LOOKS: an open 0.30 mm barrel through 1.6 mm of
# laminate holds 0.113 mm3. The paste printed over this EP is 9.21 mm2 x 0.12 mm of
# stencil = 1.11 mm3 for the whole joint. Eight barrels could swallow 0.90 mm3 --
# EIGHTY-ONE PERCENT OF THE DEPOSIT. That is the same volume-not-area argument
# cadkit's unwick.py makes, and it is why "a few vias in the pad" is not a small
# thing at this drill size.
#
# So the barrels move out to two rows beyond the opening, still under the EP copper.
# Nothing is printed over them, so nothing wicks and no gas is sealed in; and with no
# mask opening there, the component side tents them for free.
#
# THE COST, MEASURED RATHER THAN WAVED AT: heat now spreads laterally about 0.9 mm
# through 35 um of copper to reach the nearest barrel. Across the 2.71 mm width that
# is 0.9e-3 / (400 x 2.71e-3 x 35e-6) = 24 K/W, and this regulator dissipates of
# order 0.3 W at the 0.6 A the 3V3 rail actually draws -- so about 7 K. Against a
# 2-layer board where SLMA002H 2.3 says the surface layers are all the heat removal
# there is, 7 K to stop losing most of the joint is the right way round.
VIA_ROW_Y = EP_MASK_Y / 2.0 + VIA_PAD / 2.0 + 0.05    # 1.75: clear of the opening
# ⚠ NOT AN EVEN 0.70 PITCH, AND A12 IS WHY. Four barrels evenly spaced across the
# EP copper want 0.70 mm between centres, which at a 0.30 mm drill leaves 0.400 mm
# of laminate -- under the 0.45 a PAD hole needs. The row is therefore spread to
# the widest four positions the copper still contains: 1.18 + 0.25 of pad = 1.43
# against the 1.475 half-width, with 0.54 and 0.46 mm of laminate between them.
# Even spacing was never a requirement; clearing the fab's floor is.
VIA_XS = (-1.18, -0.42, 0.42, 1.18)
VIA_XY = [(x, y) for y in (-VIA_ROW_Y, VIA_ROW_Y) for x in VIA_XS]

EP_HALF_Y = EP_MASK_Y / 2.0
_tented = [xy for xy in VIA_XY if abs(xy[1]) - VIA_PAD / 2.0 > EP_HALF_Y]
assert len(_tented) == len(VIA_XY), (
    "finding 32 is only fixed if EVERY barrel is clear of the mask opening; %d of "
    "%d are" % (len(_tented), len(VIA_XY)))
# ...and all of them still have to be ON the copper, or they are not thermal vias at
# all, and clear of the signal leads' heel.
for _x, _y in VIA_XY:
    assert abs(_x) + VIA_PAD / 2.0 < EP_CU_X / 2.0, (
        "a thermal via at x %.2f reaches past the EP copper" % _x)
    assert abs(_y) + VIA_PAD / 2.0 < EP_CU_Y / 2.0, (
        "a thermal via at y %.2f reaches past the EP copper" % _y)
    assert (LEAD_TOE - LEAD_X) - (abs(_x) + VIA_PAD / 2.0) > 0.2, (
        "a thermal via at x %.2f is within 0.2 mm of a lead's heel" % _x)
# ⚠ 0.45, AND THE 0.25 THIS USED TO SAY WAS A DIFFERENT RULE READ OFF THE WRONG
# LINE. The fab publishes a generic hole-to-hole and a PAD-hole-to-hole, and they
# are not the same number: a pad hole carries an annular ring and a mask relief, so
# it needs more laminate beside it than a bare via does. A12 grades against 0.45 and
# caught this at 0.400 mm -- which is the gate doing exactly its job, since the
# generator asserted its own floor and its own floor was wrong.
HOLE_MIN = 0.45        # A12, pad hole to nearest hole
for _i in range(len(VIA_XS) - 1):
    _gap = VIA_XS[_i + 1] - VIA_XS[_i] - VIA_DRILL
    assert _gap >= HOLE_MIN, (
        "barrels %d and %d leave %.3f mm of laminate, under the fab's %.2f"
        % (_i, _i + 1, _gap, HOLE_MIN))
assert 2 * VIA_ROW_Y - VIA_DRILL >= HOLE_MIN, "the two rows are too close"


def _pad(num, kind, shape, at, size, layers, extra=()):
    body = ["\t(pad \"%s\" %s %s" % (num, kind, shape),
            "\t\t(at %s)" % " ".join("%g" % v for v in at),
            "\t\t(size %g %g)" % size]
    body += ["\t\t%s" % e for e in extra]
    body.append("\t\t(layers %s)" % " ".join('"%s"' % l for l in layers))
    body.append("\t)")
    return "\n".join(body)


def build():
    if not os.path.exists(STOCK):
        print("stock footprint not found: %s" % STOCK)
        return 1
    src = open(STOCK, encoding="utf-8").read()

    # Strip every pad; they are all replaced. Keep the silk, fab, courtyard and
    # the 3D model, which no finding disputes.
    pads = list(re.finditer(r"\n\t\(pad .*?\n\t\)", src, re.S))
    assert pads, "no pads matched -- the stock file's formatting changed"
    head = src[:pads[0].start()]
    tail = src[pads[-1].end():]

    out = [head]
    # the eight signal leads: copper, mask and paste together, TI's 1.55 x 0.60
    ys = (-1.905, -0.635, 0.635, 1.905)
    for i, y in enumerate(ys):
        out.append("\n" + _pad(i + 1, "smd", "roundrect", (-LEAD_CX, y),
                               (LEAD_X, LEAD_Y),
                               ("F.Cu", "F.Mask", "F.Paste"),
                               ("(roundrect_rratio 0.25)",)))
    for i, y in enumerate(reversed(ys)):
        out.append("\n" + _pad(i + 5, "smd", "roundrect", (LEAD_CX, y),
                               (LEAD_X, LEAD_Y),
                               ("F.Cu", "F.Mask", "F.Paste"),
                               ("(roundrect_rratio 0.25)",)))

    # ⚠ THE EXPOSED PAD IS THREE PADS, NOT ONE, AND THAT IS WHAT MAKES IT
    # SOLDER-MASK DEFINED. KiCad sizes mask from copper on a single pad, so a
    # 2.95 x 4.90 copper pad carrying "F.Mask" would open the mask to 2.95 x 4.90
    # as well -- which is the opposite of what TI asks for. Copper, mask opening
    # and paste are therefore separate pads on the same pin number: the copper is
    # larger, the mask opening is TI's maximum exposed pad, and the paste matches
    # the opening at 100 % coverage.
    out.append("\n" + _pad(9, "smd", "rect", (0, 0), (EP_CU_X, EP_CU_Y),
                           ("F.Cu",),
                           ("(property pad_prop_heatsink)", "(zone_connect 2)")))
    out.append("\n" + _pad(9, "smd", "rect", (0, 0), (EP_MASK_X, EP_MASK_Y),
                           ("F.Mask",), ("(property pad_prop_heatsink)",)))
    out.append("\n" + _pad(9, "smd", "rect", (0, 0), (EP_MASK_X, EP_MASK_Y),
                           ("F.Paste",), ("(property pad_prop_heatsink)",)))
    # the far side: unchanged in size, and it is the only other copper the heat
    # has on a two-layer board (SLMA002H 2.3, p. 4)
    out.append("\n" + _pad(9, "smd", "rect", (0, 0), (1.8, 2.5),
                           ("B.Cu",),
                           ("(property pad_prop_heatsink)", "(zone_connect 2)")))
    for x, y in VIA_XY:
        out.append("\n" + _pad(9, "thru_hole", "circle", (x, y),
                               (VIA_PAD, VIA_PAD), ("*.Cu",),
                               ("(drill %g)" % VIA_DRILL,
                                "(property pad_prop_heatsink)",
                                "(remove_unused_layers no)")))
    out.append(tail)
    blob = "".join(out)

    # the derivation travels WITH the footprint, because the next person to open
    # this in pcbnew will not be reading this script
    descr = ("LMR14020SDDA land cut to TI SNVSAA5B 4214849/B p.32: EP copper "
             "%.2fx%.2f, mask-defined opening %.2fx%.2f (the package MAXIMUM "
             "exposed pad, p.31), solid paste at 100%% coverage, %d thermal vias "
             "outside the mask opening, leads %.2fx%.2f with the toe at %.3f. Vias are "
             "%.2f mm and not TI's 0.20 because that is the fab's plated floor. "
             "See punchlist findings 38 and 32; generated by "
             "elec/make_u1_footprint.py, do not hand-edit."
             % (EP_CU_X, EP_CU_Y, EP_MASK_X, EP_MASK_Y, len(VIA_XY),
                LEAD_X, LEAD_Y, LEAD_TOE, VIA_DRILL))
    blob = re.sub(r'\(descr "[^"]*"\)', '(descr "%s")' % descr, blob, count=1)
    blob = re.sub(r'\(footprint "[^"]*"', '(footprint "%s"' % OUT_NAME, blob,
                  count=1)
    blob = blob.replace('"SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3mm"',
                        '"%s"' % OUT_NAME)

    if os.path.exists(OUT):
        shutil.copy(OUT, OUT + ".prev")
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(blob)
    print("wrote %s" % OUT)
    print("  EP copper   %.2f x %.2f mm  (%.2f mm2)"
          % (EP_CU_X, EP_CU_Y, EP_CU_X * EP_CU_Y))
    print("  EP mask     %.2f x %.2f mm  (%.2f mm2), solder-mask defined"
          % (EP_MASK_X, EP_MASK_Y, EP_MASK_X * EP_MASK_Y))
    print("  EP paste    solid, 100% of the opening")
    print("  leads       %.2f x %.2f at x +-%.3f, toe %.3f, heel %.3f"
          % (LEAD_X, LEAD_Y, LEAD_CX, LEAD_TOE, LEAD_TOE - LEAD_X))
    print("  lead<->EP   %.3f mm of solder gap (TI 0.570, was 0.355)"
          % (LEAD_TOE - LEAD_X - EP_MASK_X / 2.0))
    print("  vias        %d x %.2f drill in two rows at y +-%.2f; ALL %d sit "
          "outside the mask opening, so nothing is printed over a barrel"
          % (len(VIA_XY), VIA_DRILL, VIA_ROW_Y, len(_tented)))
    print("  barrel vol  %.3f mm3 of hole against %.3f mm3 of paste -- which is "
          "why they had to move" % (len(VIA_XY) * 3.14159 * (VIA_DRILL / 2.0) ** 2
                                    * 1.6, EP_MASK_X * EP_MASK_Y * 0.12))
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
