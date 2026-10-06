"""Measure the FAB's own pin-1 marking for the polarised two-pad parts.

WHY THIS EXISTS -- it closes PCB_QUALITY M2 for the parts `fab_frames` cannot.

M2: a placement frame fitted by pad NUMBER is not evidence of orientation -- the
fab's library may number the same lands the other way round, and the fit then turns
the part to suit the numbers.  For most parts `fab_frames` escapes that because the
pad cloud is asymmetric: only one rotation puts the lands on the lands.  A polarised
TWO-PAD part has no such escape.  Its pad cloud is mirror-symmetric, so POSITION
cannot settle it either, and a wrong answer is not cosmetic: C1 and C2 are 100 uF
electrolytics across an 18 V battery, and an electrolytic installed backwards vents.

The way out is that the fab's footprint carries more than pads.  Its `dataStr` also
holds silkscreen (layer 3), document (13) and COMPONENT_MARKING (49) geometry, and
layer 49 holds a single point: the pin-1 dot.  That is the fab's own statement of
which land is pin 1, in the fab's own data, and it is a measurement -- not a look at
a render, and not an assumption.

TWO INDEPENDENT READINGS, and they must agree:

  R1 (the gate)  the layer-49 pin-1 dot.  The pad nearest it is the fab's pin 1.
                 Required to be decisive: at least 1.5x nearer one pad than the other.
  R2 (corroboration)  silkscreen ink is not symmetric about the pad midpoint -- the
                 marked end carries the cathode band, or the "+", or both.  The
                 heavier end should be pin 1's end.  R2's margin is thin on some
                 parts (a cathode band is one line), so R2 may not CONFIRM on its
                 own, but if it CONTRADICTS R1 the part needs a person.

OURS is asserted from the NETS, not from a pin name -- `GetPinFunction()` is empty on
a board generated from a netlist, and a net is the stronger witness anyway: it says
what the terminal must be for the circuit to work at all.

Run:  "C:/Program Files/KiCad/10.0/bin/python.exe" elec/fab_polarity.py
Exit 0 = every part agrees.  Exit 1 = at least one does not, and nothing may be ordered.
"""
import json
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)

import wx                                      # noqa: E402
wx.DisableAsserts()
import pcbnew                                  # noqa: E402

from cadkit.pcbflow import fab_frames as F     # noqa: E402

BOARD = "elec/out/main.kicad_pcb"
SILK = 3
MARKING = 49

# ref -> (lcsc, what our pad 1 is, and the net that proves it must be)
PARTS = {
    "C1": ("C371283", "+", "pad 1 is on VBAT and pad 2 on GND: the + terminal of an "
                           "electrolytic across an 18 V battery"),
    "C2": ("C371283", "+", "pad 1 is on VBAT and pad 2 on GND"),
    "D1": ("C310039", "K", "SMCJ24A unidirectional TVS clamping VBAT to GND: pad 1 is "
                           "on VBAT, so pad 1 is the cathode or the TVS is a short"),
    "D5": ("C2103", "K", "zener clamping VGATE: pad 1 is on VGATE, pad 2 on GND, so "
                         "pad 1 is the cathode"),
    "D6": ("C7428237", "K", "buck catch diode: pad 1 is on SW, pad 2 on GND -- the "
                            "cathode goes to the switch node"),
    "D4": ("C81598", "K", "buzzer flyback: pad 1 is on +3V3, pad 2 on the drive node, "
                          "so pad 1 is the cathode"),
}


def _points(blob):
    """Every (x, y) in a FILL/POLY shape, including a CIRCLE's centre."""
    out = []

    def walk(o):
        if not isinstance(o, list):
            return
        if o and o[0] == "CIRCLE":
            out.append((o[1], o[2]))
            return
        flat = [v for v in o if isinstance(v, (int, float))]
        for i in range(0, len(flat) - 1, 2):
            out.append((flat[i], flat[i + 1]))
        for v in o:
            if isinstance(v, list):
                walk(v)

    walk(blob)
    return out


def read_fab(code):
    """-> (pads, marking_points, silk_shapes) in mm, in the fab's own frame."""
    doc = F._get_json(F.API_COMPONENT % F.footprint_uuid(code))
    rows = [r for r in (json.loads(l) for l in doc["result"]["dataStr"].splitlines()
                        if l.strip().startswith("[")) if r]
    pads, marks, silk = {}, [], []
    for r in rows:
        if r[0] == "PAD":
            pads[r[5]] = (r[6] * F.UNIT, r[7] * F.UNIT)
        elif r[0] in ("FILL", "POLY") and r[4] in (SILK, MARKING):
            pts = _points(r[6] if r[0] == "POLY" else r[7])
            if not pts:
                continue
            pts = [(x * F.UNIT, y * F.UNIT) for x, y in pts]
            (marks if r[4] == MARKING else silk).append(pts)
    return pads, marks, silk


def r1(pads, marks):
    """The layer-49 pin-1 dot: which pad number it names, and how decisively."""
    if len(marks) != 1 or len(marks[0]) != 1:
        return None, 0.0, "layer 49 does not hold exactly one point"
    mx, my = marks[0][0]
    d = sorted((math.hypot(x - mx, y - my), n) for n, (x, y) in pads.items())
    near, far = d[0], d[1]
    ratio = far[0] / near[0] if near[0] else float("inf")
    return near[1], ratio, "dot %.2f mm from pad %s, %.2f from pad %s" % (
        near[0], near[1], far[0], far[1])


def r2(pads, silk):
    """Silk ink either side of the pad midpoint. The marked end should be pin 1's."""
    sep = abs(pads["2"][0] - pads["1"][0])
    mid = (pads["1"][0] + pads["2"][0]) / 2.0
    side = {"-": 0.0, "+": 0.0}
    for pts in silk:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        w = max(xs) - min(xs)
        if w > sep * 0.7:            # the body outline spans the part: it says nothing
            continue
        side["-" if sum(xs) / len(xs) < mid else "+"] += max(w, max(ys) - min(ys), 0.05)
    heavy = "-" if side["-"] > side["+"] else "+"
    total = side["-"] + side["+"]
    margin = abs(side["-"] - side["+"]) / total * 100 if total else 0.0
    pad = min(pads, key=lambda n: pads[n][0]) if heavy == "-" else \
        max(pads, key=lambda n: pads[n][0])
    return pad, margin, "ink %.2f mm on the %s end vs %.2f" % (
        side[heavy], heavy, side["+" if heavy == "-" else "-"])


def main():
    board = pcbnew.LoadBoard(BOARD)
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    cache, fails = {}, []

    print("fab pin-1 marking vs our pad 1 -- closes M2 on the polarised two-pad parts")
    print("")
    for ref in sorted(PARTS):
        code, mine, why = PARTS[ref]
        if ref not in fps:
            fails.append("%s: not on the board" % ref)
            continue
        nets = {p.GetNumber(): p.GetNetname() for p in fps[ref].Pads()}
        if code not in cache:
            cache[code] = read_fab(code)
        pads, marks, silk = cache[code]
        if set(pads) != set(nets):
            fails.append("%s %s: we have pads %s, the fab has %s"
                         % (ref, code, sorted(nets), sorted(pads)))
            continue

        p1, ratio, how1 = r1(pads, marks)
        p2, margin, how2 = r2(pads, silk)

        print("%-3s %-9s our pad 1 = %-2s on %s" % (ref, code, mine, nets["1"]))
        print("      R1 pin-1 dot  -> their pad %s   (%s, %.1fx decisive)"
              % (p1, how1, ratio))
        print("      R2 silk ink   -> their pad %s   (%s, %.0f%% margin)"
              % (p2, how2, margin))

        if p1 is None:
            fails.append("%s %s: no usable pin-1 dot -- %s" % (ref, code, how1))
        elif ratio < 1.5:
            fails.append("%s %s: the pin-1 dot is not decisive (%.2fx) -- %s"
                         % (ref, code, ratio, how1))
        elif p1 != "1":
            fails.append("%s %s: THE FAB CALLS PAD %s PIN 1, WE CALL PAD 1 %s. %s"
                         % (ref, code, p1, mine, why))
        elif p2 != p1:
            fails.append("%s %s: R2 CONTRADICTS R1 -- the dot says pad %s, the silk "
                         "says pad %s. Needs a person." % (ref, code, p1, p2))
        else:
            print("      OK    the fab's pin 1 is our pad 1, so %s is our %s. %s"
                  % (nets["1"], mine, why))
        print("")

    if fails:
        print("FAIL (%d)" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("%d polarised parts, all agree: the fab's pin 1 is our pad 1." % len(PARTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
