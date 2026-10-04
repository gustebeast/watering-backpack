"""Overhang gate for the v2 frame — does the X-axis build actually print clean?

The whole v2 frame rests on one claim: built along X with each half standing on
its OUTER face, nothing overhangs. Deck and beams are constant Y-Z section, the
posts land in the first layers, and the joint is the last layers. That argument
is only as good as the geometry, so this MEASURES it instead of trusting it.

Each part is checked IN ITS PRINT POSE (`print_pose` with the module's own
PRINT_ROT), so Z here is the build direction — the same orientation the slicer
sees.

A planar face whose normal points down more steeply than ~45° needs support.
Faces sitting on the build plate are supported by definition and are skipped.

    py -3.12 tools/check_v2_overhangs.py        # exit 0 = clean

Exit code is the number of parts carrying steep overhang area, so this works as
a build gate.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cadkit.step_export import print_pose      # noqa: E402
from src import housing as H                   # noqa: E402

# A planar ceiling has n.z = -1; a 45° ramp has n.z = -0.707. Flag anything
# steeper than ~45°, with a small tolerance band so true 45° ramps pass.
STEEP = -0.72
BED_EPS = 0.2            # a face this close to z=0 rests on the plate
MIN_AREA = 1.0           # ignore slivers; they are modelling noise, not overhangs

PARTS = (("v2_housing",     H.housing()),
         ("v2_housing_lid", H.lid()))


def report(name, part):
    posed = print_pose(part, H.PRINT_ROT.get(name))
    bb = posed.val().BoundingBox()
    steep, ramps = [], []
    for f in posed.faces().vals():
        try:
            n = f.normalAt()
        except Exception:
            continue                      # non-planar: curvature is judged by the slicer
        c = f.Center()
        if c.z - bb.zmin <= BED_EPS:      # on the build plate — supported
            continue
        if f.Area() < MIN_AREA:
            continue
        if n.z < STEEP:
            steep.append((f.Area(), c.x, c.y, c.z, n.z))
        elif n.z < -0.5:
            ramps.append((f.Area(), c.x, c.y, c.z, n.z))

    steep.sort(key=lambda r: -r[0])
    total = sum(r[0] for r in steep)
    print("%-16s build %6.1f x %6.1f x %6.1f mm" % (name, bb.xlen, bb.ylen, bb.zlen))
    if steep:
        print("   NEEDS SUPPORT: %d face(s), %.1f mm2" % (len(steep), total))
        for area, cx, cy, cz, nz in steep[:8]:
            print("     area=%8.1f  at (%7.1f,%7.1f,%6.1f)  n.z=%5.2f"
                  % (area, cx, cy, cz, nz))
        if len(steep) > 8:
            print("     ... +%d more" % (len(steep) - 8))
    else:
        print("   clean — no face steeper than 45 deg off the plate")
    if ramps:
        print("   (%d self-supporting ramp(s), %.1f mm2)"
              % (len(ramps), sum(r[0] for r in ramps)))
    return 1 if steep else 0


def main():
    print("=== v2 frame overhang gate (steep threshold n.z < %.2f) ===\n" % STEEP)
    bad = sum(report(n, p) for n, p in PARTS)
    print("\n%s" % ("every v2 part prints without support"
                    if not bad else
                    "*** %d PART(S) NEED SUPPORT — the X-build claim does not hold ***" % bad))
    return bad


if __name__ == "__main__":
    sys.exit(main())
