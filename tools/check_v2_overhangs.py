"""Overhang gate — does every part this project SHIPS print without support?

    py -3.12 tools/check_v2_overhangs.py        # exit 0 = clean

Exit code is the number of parts carrying steep overhang area, so this works as
a build gate.

WHY IT ENUMERATES printed_parts(). This gate used to carry its own hand-written
list of parts, and that list had drifted: it named the housing, the lid and the
filter screen while `src.build.printed_parts()` exported five things. So
`joystick_mount` and `dual_clamp_19` -- both shipped, both printed -- had never
been checked by anything. The joystick mount was not clean: its plate underside
spanned 0.225 mm between the gusset foot and the grip with nothing beneath it,
two flat ceilings at n.z = -1.00, while its docstring claimed support-free.

So the list is gone. This reads `printed_parts()` -- the same tuples the build
exports STEPs from -- and a part cannot be shipped without being checked here.

IT ALSO TAKES THE POSE FROM THERE, which matters more than it looks. The old
version did `H.PRINT_ROT.get(name)`: it looked every part's rotation up in the
HOUSING module, so a part defined anywhere else silently got None. That happened
to be harmless only because the other parts' PRINT_ROT genuinely is None -- the
moment one needed a rotation, this gate would have measured a pose the exporter
never writes. Build direction is the whole question an overhang gate answers, so
reading the pose from a different place than the exporter does makes the answer
meaningless. Now there is one source for it.

Each part is checked IN ITS PRINT POSE, so Z here is the build direction -- the
same orientation the slicer sees. A face whose normal points down more steeply
than ~45 degrees needs support. Faces sitting on the build plate are supported
by definition and are skipped.

KNOWN LIMIT, unchanged and worth stating: a curved face is judged by its normal
at one parametric point, which for a cylinder is not a meaningful summary. A
horizontal bore's underside is a real unsupported region that this can only
report as a single sample, and a bore small enough to bridge is not an overhang
at all. Flat ceilings -- the defect this gate exists for -- are planar and are
caught exactly. Treat a curved finding as a prompt to look, not as a verdict.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import cadquery as cq                          # noqa: E402
from cadkit.step_export import print_pose      # noqa: E402
from src import build as B                     # noqa: E402

# A planar ceiling has n.z = -1; a 45 degree ramp has n.z = -0.707. Flag anything
# steeper than ~45 degrees, with a small tolerance band so true 45 degree ramps
# pass.
STEEP = -0.72
BED_EPS = 0.2            # a face this close to z=0 rests on the plate
MIN_AREA = 1.0           # ignore slivers; they are modelling noise, not overhangs

# ── ACCEPTED overhangs ───────────────────────────────────────────────────────
# Same idiom as OVERLAP_BASELINE and pcbflow's pcb_declared.py, and for the same
# reason: a gate that cannot be satisfied gets ignored, and a gate that reports
# one lump total teaches everyone to read the number as "fine". So each entry is
# a specific feature with a measured area and a reason it cannot be designed
# out. ANY part not listed here fails on a single mm2, and a listed part fails
# the moment its area or face count GROWS -- a new overhang cannot hide behind
# an accepted one.
#
# Nothing FIXABLE is accepted. The four sideways SCREW bores on these two parts
# were real circular ceilings (15.0 mm2 and 83.4 mm2); they were fixed with
# cadkit.supports.printable_bore rather than listed here.
ACCEPTED = {
    "joystick_mount": dict(
        mm2=306.0, faces=3,
        why="the 12.3 mm hose bore's crown (301 mm2). A clamp bore must match "
            "the hose it grips, so it cannot be teardropped: the apex needs "
            "r*sqrt(2) = 8.70 mm above the axis, landing at z 19.45 inside a "
            "plate that spans 16.90-19.40 -- cadkit/holes.py's own warning that "
            "'in thin webs the apex will slit the crown'. It is the classic "
            "sideways-hole droop on a 12.3 mm bore, which a slicer arches "
            "acceptably, and this bore is a grip surface, not a fit. The "
            "remaining 3.8 mm2 is the two teardrop DULL TIPS, which "
            "cadkit/holes.py states bridge without deforming by design."),
    "dual_clamp_19": dict(
        mm2=377.0, faces=4,
        why="the 19 mm hose bore's crown (366 mm2), same reason: its teardrop "
            "apex would need 13.4 mm above the axis through a 3.0 mm WALL and "
            "would punch straight out of it. The 9.2 mm2 balance is teardrop "
            "dull tips. NOTE the POLE bore is not in this total at all -- it "
            "runs along the build direction, so it has no ceiling."),
}


def _faces(f):
    """[(area, centroid_z, outward n.z)] for one face.

    A PLANE is one patch with one exact normal -- same treatment the gate has
    always given it, so flat-ceiling verdicts are unchanged. Anything curved is
    tessellated and each triangle classified on its own.

    WHY TESSELLATE AT ALL. The original gate called normalAt() ONCE per face and
    took that as the whole face's direction. Exact for a plane; meaningless for a
    cylinder, where it samples one arbitrary parametric point. It reported the
    joystick mount's 270 degree hose grip as 855 mm2 of dead-flat ceiling and
    the pole clamp's bore as 1017 mm2 -- both open-bottomed arcs. It stayed
    hidden only because the gate was aimed at three parts whose curved faces
    happened to sample the other way.

    WHY normalAt(point) AND NOT THE ORIENTATION FLAG. Deriving "outward" from
    triangle winding plus f.wrapped.Orientation() is what I tried first, and it
    is wrong twice over. It put the M4 clamp bore's overhang at z 2.5-3.1 when
    the axis is at 4.8 -- the bore's FLOOR -- and it reported a 467 mm2
    pole-bore crown that does not exist: that bore runs ALONG the build
    direction, where a round hole has no ceiling at all, so the flag version
    INVENTED an overhang rather than merely mislocating one. It also called
    the joystick ear's UPWARD top face a
    ceiling on the -x side but not the mirrored +x side, because mirror() and
    union() leave the two copies with different flags. normalAt(point) composes
    the surface direction with the face orientation itself, which is the one
    thing that has to be right here.
    """
    out = []
    if f.geomType() == "PLANE":
        try:
            return [(f.Area(), f.Center().z, f.normalAt().z)]
        except Exception:
            return out
    try:
        verts, tris = f.tessellate(0.1)
    except Exception:
        return out
    for a, b, c in tris:
        pa, pb, pc = verts[a], verts[b], verts[c]
        u = (pb.x - pa.x, pb.y - pa.y, pb.z - pa.z)
        v = (pc.x - pa.x, pc.y - pa.y, pc.z - pa.z)
        nx = u[1] * v[2] - u[2] * v[1]
        ny = u[2] * v[0] - u[0] * v[2]
        nz = u[0] * v[1] - u[1] * v[0]
        mag = (nx * nx + ny * ny + nz * nz) ** 0.5
        if mag <= 1e-12:
            continue
        cen = cq.Vector((pa.x + pb.x + pc.x) / 3.0,
                        (pa.y + pb.y + pc.y) / 3.0,
                        (pa.z + pb.z + pc.z) / 3.0)
        try:
            n = f.normalAt(cen)
        except Exception:
            continue
        out.append((0.5 * mag, cen.z, n.z))
    return out


def report(name, part, rot):
    posed = print_pose(part, rot)
    bb = posed.val().BoundingBox()
    steep, ramps = [], []
    for f in posed.faces().vals():
        s = r = 0.0
        zs = []
        steepest = 0.0
        for area, cz, nz in _faces(f):
            if cz - bb.zmin <= BED_EPS:       # on the build plate - supported
                continue
            if nz < STEEP:
                s += area
                zs.append(cz)
                steepest = min(steepest, nz)
            elif nz < -0.5:
                r += area
        if s >= MIN_AREA:
            c = f.Center()
            steep.append((s, c.x, c.y, sum(zs) / len(zs), steepest,
                          f.geomType()))
        if r >= MIN_AREA:
            ramps.append(r)

    steep.sort(key=lambda q: -q[0])
    total = sum(q[0] for q in steep)
    print("%-20s build %6.1f x %6.1f x %6.1f mm   rot=%s"
          % (name, bb.xlen, bb.ylen, bb.zlen, rot))
    if steep:
        print("   NEEDS SUPPORT: %d face(s), %.1f mm2" % (len(steep), total))
        for area, cx, cy, cz, nz, gt in steep[:8]:
            print("     area=%8.1f  at (%7.1f,%7.1f,%6.1f)  n.z=%5.2f  %s"
                  % (area, cx, cy, cz, nz, gt))
        if len(steep) > 8:
            print("     ... +%d more" % (len(steep) - 8))
    else:
        print("   clean - no face steeper than 45 deg off the plate")
    if ramps:
        print("   (%d self-supporting ramp(s), %.1f mm2)"
              % (len(ramps), sum(ramps)))
    return total, len(steep)


def main():
    parts = B.printed_parts()
    print("=== overhang gate: every part src.build exports "
          "(steep threshold n.z < %.2f) ===\n" % STEEP)
    bad = 0
    for n, part, rot in parts:
        area, faces = report(n, part, rot)
        if faces == 0:
            continue
        acc = ACCEPTED.get(n)
        if acc is None:
            print("   *** NOT ACCEPTED: this part has no ACCEPTED entry ***")
            bad += 1
        elif area > acc["mm2"] + 0.05 or faces > acc["faces"]:
            print("   *** GREW past the accepted %.1f mm2 / %d face(s) ***"
                  % (acc["mm2"], acc["faces"]))
            bad += 1
        else:
            print("   ACCEPTED (<= %.1f mm2, <= %d face(s)):"
                  % (acc["mm2"], acc["faces"]))
            for line in _wrap(acc["why"]):
                print("      %s" % line)
    print("\n%d part(s) checked, from printed_parts()" % len(parts))
    print("%s" % ("every shipped part prints without support, or carries only "
                  "accepted overhangs" if not bad else
                  "*** %d PART(S) WITH UNACCEPTED OVERHANG ***" % bad))
    return bad


def _wrap(s, w=70):
    out, line = [], ""
    for word in s.split():
        if len(line) + len(word) + 1 > w:
            out.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        out.append(line)
    return out


if __name__ == "__main__":
    sys.exit(main())
