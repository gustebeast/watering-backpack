"""The Makita 18V LXT pack, as the pack — not as a prism.

It was a 116 x 75 x 65.6 box. The box was not wrong (those three numbers are
the GrabCAD model's own bounding box, which is where they came from), but a box
is only as useful as the question being asked of it, and the questions have
grown: whether the pack can be lifted out past the deck, whether a lead can
reach its contact block, what the owner is actually looking at in the viewer.
A box answers the first with 161 mm3 of imaginary corner and the last not at
all.

WHAT IS DRAWN
    `solid()`     the imported pack, posed on the dock in WORLD coordinates
    `envelope()`  its bounding prism, for anything that wants the old answer
    `BATT_L/W/D`  measured off the model, never typed

The reference STEP is references/makita_battery.step (GrabCAD, "Makita LxT 18V
5A Battery" — see references/README.md). It is not in the repository; without
it `solid()` returns None and `envelope()` falls back to the published figures,
which is also what every gate reports, loudly.

THE POSE, AND WHY IT IS NOT A GUESS
-----------------------------------
The dock's own frame (src/battery_dock.py) is X = pack width, Y = slide, Z =
toward the pack, and src/housing.py maps it to the world with _DOCK_AXES:
dock +X -> world +Y, dock +Y -> world -Z, dock +Z -> world -X. So in the world
the pack slides DOWN to seat (housing._check_dock_orientation asserts exactly
that) and its tool interface faces +X, toward the dock's face.

The GrabCAD model's frame is X = slide (116 mm, terminal slots at x 8..12, the
latch button at the x=111 end), Y = width (75), Z = the tool interface (the
rails and the terminal mouths stand up to z=20.6; tools/inspect_interface.py
reads them off). Putting those together:

    model +X -> world +Z     the terminal end LEADS, so it points -Z, down
    model +Y -> world -Y     (forced: the other sign is a reflection, not a
                              rotation, and would hand the pack its mirror)
    model +Z -> world +X     the interface faces the dock

which is `rotate(-90 about Y)` then `rotate(180 about Z)`. The translation is
NOT a fourth guess on top of those: the model's bounding box IS the prism this
replaces, so the pose is resolved by landing the model's bbox on the prism's,
and the seat v1 validated carries over untouched.

THE TWO SIZES
-------------
The owner has both a compact pack and a double-thickness one. They share an
interface exactly — same rails, same latch, same terminals, same 116 x 75
footprint — and differ only in how deep the cell block is. The design is drawn
with the BIG one, because that is the one that has to fit: a bay that clears
the 5.0 Ah clears the 2.0 Ah with room to spare, and a bay sized on the compact
one would not take the pack the machine is meant to run on.
"""
from __future__ import annotations

import cadquery as cq

from .dimensions import REFERENCES_DIR

STEP = REFERENCES_DIR / "makita_battery.step"

# ── The two packs ───────────────────────────────────────────────────────────
# ⚠ ONE STEP FILE, TWO PACKS, AND THE SECOND ONE IS DERIVED — say so here
# rather than let a drawing imply a model that does not exist.
#
# The reference STEP is the BIG pack (GrabCAD's "LxT 18V 5A"), and it is the
# one the design is drawn with. There is no model of the compact pack, so it is
# made by shortening the big one's cell block from the far face: the interface
# end — rails, latch, terminals, everything that touches this machine — is the
# model's own, and the far end is a FLAT CUT, not the real moulding. Nothing in
# this design touches that end, which is why the shortcut is allowable and why
# it is spelled out.
#
# 17.0 mm is the difference between the two packs as Makita's distributors list
# them: BL1850B 62 mm against BL1820B 45 mm (same 113 x 75 footprint in both
# listings). It is a DIFFERENCE taken from one consistent pair of figures, not
# an absolute depth bolted onto a model measured a different way — the model's
# own 65.6 includes the rail tower that those listings do not.
COMPACT_DROP = 17.0

SIZES = ("large", "compact")
DEFAULT_SIZE = "large"       # see the module docstring: the big one has to fit

# Published figures, used ONLY when the reference STEP is absent, so that a
# checkout without it still has a pack-shaped hole rather than no pack.
_FALLBACK = (116.0, 75.0, 65.6)


def _raw():
    try:
        return cq.importers.importStep(str(STEP))
    except Exception:                                           # noqa: BLE001
        return None


def _posed(size: str):
    """The pack in WORLD orientation, still at the model's own origin."""
    s = _raw()
    if s is None:
        return None
    if size == "compact":
        bb = s.val().BoundingBox()
        keep = cq.Workplane("XY").box(
            bb.xlen + 10.0, bb.ylen + 10.0, bb.zlen - COMPACT_DROP).translate(
            ((bb.xmin + bb.xmax) / 2.0, (bb.ymin + bb.ymax) / 2.0,
             bb.zmax - (bb.zlen - COMPACT_DROP) / 2.0))
        s = s.intersect(keep)
    return (s.rotate((0, 0, 0), (0, 1, 0), -90)
             .rotate((0, 0, 0), (0, 0, 1), 180))


def _size_mm(size: str = DEFAULT_SIZE):
    """(L, W, D) of the pack IN THE WORLD: along Z, along Y, along X."""
    s = _posed(size)
    if s is None:
        d = _FALLBACK[2] - (COMPACT_DROP if size == "compact" else 0.0)
        return _FALLBACK[1], _FALLBACK[0], d          # (Z-len, Y-len, X-len)
    bb = s.val().BoundingBox()
    return bb.zlen, bb.ylen, bb.xlen


# MEASURED OFF THE MODEL, not typed beside it. These were three literals; a
# literal that happens to equal a measurement is a literal that goes stale the
# first time the measurement moves.
BATT_L, BATT_W, BATT_D = _size_mm(DEFAULT_SIZE)
HAVE_MODEL = _raw() is not None
if not HAVE_MODEL:
    print("*** references/makita_battery.step IS NOT HERE — the pack is drawn "
          "as a %.0f x %.0f x %.0f prism and every clearance read off it is "
          "the prism's, not the pack's ***" % (BATT_L, BATT_W, BATT_D))


def place(wp, x_face: float, y_c: float, z0: float, size: str = DEFAULT_SIZE):
    """Land `wp` (already world-oriented) so its bbox sits on the seat.

    `x_face` is the +X face (the interface, against the dock), `y_c` the width
    centre, `z0` the bottom — the same three numbers `build.battery_envelope`
    has always used, so the seat v1 validated is unchanged.
    """
    bb = wp.val().BoundingBox()
    return wp.translate((x_face - bb.xmax, y_c - (bb.ymin + bb.ymax) / 2.0,
                         z0 - bb.zmin))


def solid(x_face: float, y_c: float, z0: float, size: str = DEFAULT_SIZE):
    """The pack itself, seated. None when the reference STEP is absent."""
    s = _posed(size)
    return None if s is None else place(s, x_face, y_c, z0, size)


def envelope(x_face: float, y_c: float, z0: float, size: str = DEFAULT_SIZE):
    """The pack's bounding prism, seated. Always available."""
    length, width, depth = _size_mm(size)
    return (cq.Workplane("YZ").workplane(offset=x_face - depth)
            .center(y_c, z0 + length / 2.0)
            .rect(width, length).extrude(depth))
