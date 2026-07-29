"""Minimal-contact RUB features between moving printed parts.

A printed mechanism wants its moving parts to rub on the SMALLEST reliable
surface: a single extruder bead. `contact_rib_size(nozzle)` is that rule -
nozzle + 0.05 (the buffer keeps the slicer from dropping a feature that is
exactly one nozzle wide) - and every generator here sizes its contact face
with it, BOTH across (width) and along (proud) the touch direction.

`contact_ring(bore_d, axis_point, axis_dir, nozzle, print_up)` is the
annular THRUST RING around a pivot bore on a wall face - a lever's only
side contact. It returns a SOLID disc (no bore - cut yours through it
afterwards, e.g. cadkit.holes.teardrop_hole for a sideways pivot), with
the matching supports.teardrop_boss_support tail fused on by default
(sideways-printed rings need it; pass the print_up you actually print
with, same conventions as supports.py - never post-rotate the output).
"""

import math

import cadquery as cq

try:
    from .supports import teardrop_boss_support
except ImportError:                    # run directly as a script (self-test)
    from supports import teardrop_boss_support

__all__ = ["contact_rib_size", "contact_ring"]

_RIB_BUFFER = 0.05      # one bead + this = a line the slicer never drops


def _unit(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n < 1e-12:
        raise ValueError("zero-length direction")
    return (v[0] / n, v[1] / n, v[2] / n)


def contact_rib_size(nozzle=0.8):
    """The one-bead contact dimension: nozzle + 0.05 - use it for BOTH the
    width and the proud of any deliberate rub feature."""
    if nozzle <= 0.0:
        raise ValueError("nozzle must be > 0")
    return nozzle + _RIB_BUFFER


def contact_ring(bore_d, axis_point=(0.0, 0.0, 0.0), axis_dir=(1.0, 0.0, 0.0),
                 nozzle=0.8, print_up=(0.0, 0.0, 1.0), support=True):
    """Thrust-ring stock around a pivot: a solid disc of Ø bore_d + 2 ribs,
    exactly contact_rib_size(nozzle) PROUD of the wall at `axis_point`,
    growing along `axis_dir`. Cut the pivot bore through it afterwards -
    the ring that survives is one bead wide and one bead proud. With
    `support=True` (default) the teardrop tail for a sideways-printed ring
    is fused on (axis must then be perpendicular to `print_up`; the tail
    generator enforces that). `support=False` for rings printed flat."""
    if bore_d <= 0.0:
        raise ValueError("bore_d must be > 0")
    t = contact_rib_size(nozzle)
    r_out = bore_d / 2.0 + t
    a = _unit(axis_dir)
    u = _unit(print_up)
    x = (u[1] * a[2] - u[2] * a[1],
         u[2] * a[0] - u[0] * a[2],
         u[0] * a[1] - u[1] * a[0])
    if math.sqrt(x[0] ** 2 + x[1] ** 2 + x[2] ** 2) < 1e-9:
        # axis ∥ print_up (a flat-printed ring): any perpendicular works
        x = (0.0, -a[2], a[1]) if abs(a[0]) < 0.9 else (-a[2], 0.0, a[0])
        x = _unit(x)
    plane = cq.Plane(origin=cq.Vector(*axis_point), xDir=cq.Vector(*x),
                     normal=cq.Vector(*a))
    disc = cq.Workplane(plane).circle(r_out).extrude(t)
    if not support:
        return disc
    return disc.union(teardrop_boss_support(r_out, t, axis_point, axis_dir,
                                            print_up))


# ── Self-test: geometry gates (run `py -3.12 contact.py`) ────────────────────
if __name__ == "__main__":
    import sys

    fails = []
    ok = abs(contact_rib_size(0.8) - 0.85) < 1e-12 and \
        abs(contact_rib_size(0.4) - 0.45) < 1e-12
    print(f"rib size      0.8->{contact_rib_size(0.8)} 0.4->{contact_rib_size(0.4)}"
          f"{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append("rib size rule")

    D = 5.3
    T = contact_rib_size(0.8)
    R = D / 2.0 + T
    bare = contact_ring(D, (0, 0, 0), (0, 1, 0), support=False)
    v = bare.val().Volume()
    want = math.pi * R * R * T
    ok = abs(v - want) < 1e-3
    print(f"bare disc     vol {v:.3f} (want {want:.3f}){'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"disc volume {v} != {want}")
    bb = bare.val().BoundingBox()
    ok = abs(bb.ymin) < 1e-6 and abs(bb.ymax - T) < 1e-6 and abs(bb.zmax - R) < 1e-6
    print(f"bare extents  y[{bb.ymin:.3f},{bb.ymax:.3f}] r {bb.zmax:.3f}"
          f"{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append("disc extents")

    full = contact_ring(D, (2.0, 5.0, 1.0), (0, 1, 0))
    vf = full.val().Volume()
    bbf = full.val().BoundingBox()
    ok = (vf > v + 1e-3                                  # the tail added material
          and abs(bbf.zmin - (1.0 - R * math.sqrt(2.0))) < 1e-3   # tail tip r*sqrt2 down
          and len(full.val().Solids()) == 1)
    print(f"with tail     vol {vf:.3f} tip z {bbf.zmin:.3f} "
          f"(want {1.0 - R * math.sqrt(2.0):.3f}){'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append("tail fuse/tip")

    # flat-printed ring: axis ∥ print_up allowed with support=False...
    flat = contact_ring(D, (0, 0, 0), (0, 0, 1), support=False)
    ok = abs(flat.val().Volume() - want) < 1e-3
    print(f"flat ring     vol {flat.val().Volume():.3f}{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append("flat ring")
    # ...but a supported ring with axis ∥ print_up must raise (no sideways tail)
    try:
        contact_ring(D, (0, 0, 0), (0, 0, 1))
        fails.append("parallel supported ring did not raise")
        print("parallel+support did NOT raise  <-- FAIL")
    except ValueError:
        print("parallel+support raises (ok)")
    try:
        contact_ring(0.0)
        fails.append("zero bore did not raise")
        print("zero bore     did NOT raise  <-- FAIL")
    except ValueError:
        print("zero bore     raises (ok)")

    if fails:
        print("FAIL:", *fails, sep="\n  ")
    else:
        print("OK - contact ribs are one bead + 0.05 wide AND proud; ring "
              "fuses its sideways teardrop tail; flat rings skip it; "
              "validation raises.")
    sys.exit(len(fails))
