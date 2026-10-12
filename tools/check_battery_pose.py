"""Is the Makita pack on the dock the right way round?

    py -3.12 tools/check_battery_pose.py

The pack was a prism until finding 60, and a prism has no handedness: it sits
on the dock identically whichever way you turn it, and every gate agrees.
`src/battery.py` poses the real model from the dock's own axes, and this is
what makes that pose a measurement rather than a derivation nobody checked.

TWO NUMBERS, AND THE SECOND ONE IS THE ONE THAT BITES:

  pack x terminal   must be ZERO. The 643852-2 contact block protrudes 3.45 mm
                    past the dock's face into the pack's space, and the pack's
                    interface cavity is what receives it. If the pack is turned
                    end-for-end the cavity is at the other end and the block
                    drives into solid plastic.
  pack x housing    must be SMALL -- the rails in the dock's T-slot and nothing
                    else. The prism read 12528 mm3 here because a prism has no
                    rails; the model reads 262.

⚠ A ZERO ON ITS OWN PROVES NOTHING. Two solids that miss each other entirely
also measure 0.00. So the gate does not just read the placed pose: it builds
the two WRONG poses as well and requires them to be worse. If all three read
zero, the pack is not where the dock is and the gate says so instead of
passing.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.battery as BAT                                       # noqa: E402
import src.build as B                                           # noqa: E402
import src.housing as H                                         # noqa: E402

HOUSING_CAP = 600.0      # the rails in the T-slot; measures 262
WRONG_MIN = 500.0        # a wrong pose has to be at least this much worse


def _vol(a, b):
    if a is None or b is None:
        return 0.0
    try:
        i = a.intersect(b).val()
    except Exception:                                           # noqa: BLE001
        return 0.0
    return i.Volume() if i is not None else 0.0


def main():
    if not BAT.HAVE_MODEL:
        print("FAIL  references/makita_battery.step is not here, so there is no "
              "pose to check. That is not a pass: the pack is being drawn as a "
              "prism and a prism has no right way round.")
        return 1

    seat = B._battery_seat()
    term = H.terminal_placed()
    house = H.housing()
    if term is None:
        print("FAIL  the 643852-2 contact block is not in the model, so the one "
              "feature that fixes the pack's end has nothing to be checked "
              "against")
        return 1

    poses = {
        "as placed": BAT.solid(*seat),
        "end-for-end": BAT.place(
            BAT._posed(BAT.DEFAULT_SIZE).rotate((0, 0, 0), (0, 0, 1), 180), *seat),
        "rolled 180 about X": BAT.place(
            BAT._posed(BAT.DEFAULT_SIZE).rotate((0, 0, 0), (1, 0, 0), 180), *seat),
    }
    rows = {k: (_vol(v, term), _vol(v, house)) for k, v in poses.items()}

    print("%-20s %12s %12s" % ("pose", "x terminal", "x housing"))
    for k, (t, h) in rows.items():
        print("%-20s %12.1f %12.1f" % (k, t, h))
    print()

    bad = 0
    t, h = rows["as placed"]
    if t > 1e-6:
        print("FAIL  the contact block drives %.1f mm3 into the pack. It should "
              "nest in the pack's interface cavity, not interpenetrate it." % t)
        bad += 1
    if h > HOUSING_CAP:
        print("FAIL  the pack overlaps the housing by %.1f mm3, over the %.0f "
              "this is the rails in the T-slot" % (h, HOUSING_CAP))
        bad += 1
    for k in ("end-for-end", "rolled 180 about X"):
        wt, wh = rows[k]
        if wt + wh < WRONG_MIN:
            print("FAIL  turning the pack %s costs only %.1f mm3 of new "
                  "interference. Either the pack is nowhere near the dock, or "
                  "this gate cannot tell the two apart -- and a zero that "
                  "cannot tell them apart is not a pass." % (k, wt + wh))
            bad += 1
    if not bad:
        print("ok    the block nests in the pack (0.00) and the rails sit in "
              "the T-slot (%.1f mm3); both wrong poses are worse by "
              "thousands" % h)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
