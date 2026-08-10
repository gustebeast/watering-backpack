"""Shared STEP exporter for CadQuery 3D-printing projects.

A bare ``cq.exporters.export(obj, "housing.step")`` names the STEP *product*
"Open CASCADE STEP translator 7.8 …", so slicers and viewers (Bambu Studio,
FreeCAD) show that instead of "housing". This helper exports normally, then
rewrites the product name to match the file stem — giving a single, correctly
named product that every viewer reads, with no extra wrapper assembly.

Usage (single printed part):

    from cadkit.step_export import export_step

    export_step(part, "housing.step")          # imports/slices as "housing"

For a multi-part *assembly*, keep using ``cq.Assembly`` with a per-part
``name=`` on each ``.add(...)`` — that already names every product.

PRINT POSE (user, cable-spool #935): per-part STEP files should land in the
slicer ALREADY print-oriented — nobody should have to remember which way to
flip a part in Bambu. Wrap each export in ``print_pose``:

    export_step(print_pose(part, "flip"), "lid.step")     # a +z→−z print
    export_step(print_pose(part), "frame.step")           # models as printed
    export_step(print_pose(part, ((1, 0, 0), -90)), ...)  # bed = its +y face

It rotates the part onto its documented bed face, drops it to z = 0 and
centres it on x/y. EXPORT-ONLY by design: pass the posed copy straight to
``export_step`` and keep adding the as-modeled part to the ``cq.Assembly`` —
the viewer keeps every part in its assembly place. Keep a small
``PRINT_ROT = {name: rotate}`` table next to the project's PARTS list so each
part's bed face is declared once, beside its export (parts that already model
as printed simply get the drop-and-centre).

Self-test: ``python -m cadkit.step_export`` (or run this file).
"""

import pathlib
import re

import cadquery as cq

# Matches a STEP PRODUCT entity's first two fields (id, name), which both carry
# the OCC default name. The fields can be split across lines, so \s* spans them.
_PRODUCT_RE = re.compile(r"PRODUCT\(\s*'[^']*'\s*,\s*'[^']*'")


def export_step(obj, path, name=None):
    """Export ``obj`` to ``path`` as STEP, naming the product after the file
    stem (or ``name`` if given).

    ``obj`` may be a ``cq.Workplane``, ``cq.Shape``/``cq.Solid`` — anything
    ``cq.exporters.export`` accepts. The geometry is the standard CadQuery
    export; only the product name is rewritten.
    """
    path = str(path)
    label = name or pathlib.Path(path).stem
    cq.exporters.export(obj, path)
    _rename_products(path, label)


def print_pose(obj, rotate=None):
    """``obj`` posed for PRINTING: rotated onto its bed face, dropped so
    its lowest point sits at z = 0, centred on x/y. EXPORT-ONLY — feed
    the result to ``export_step`` and keep the as-modeled part in the
    assembly, so viewer poses never move.

    rotate:
      None         the part already models in print orientation
                   (drop-and-centre only)
      "flip"       180° about X — the standard +z→−z print (the modeled
                   TOP face is the bed)
      (axis, deg)  anything else, about the origin: ((1, 0, 0), -90)
                   stands a part on its +y face, etc.
    """
    w = obj if isinstance(obj, cq.Workplane) else cq.Workplane(obj=obj)
    if rotate == "flip":
        rotate = ((1.0, 0.0, 0.0), 180.0)
    if rotate is not None:
        axis, deg = rotate
        w = w.rotate((0.0, 0.0, 0.0), tuple(axis), deg)
    bb = w.val().BoundingBox()
    return w.translate((-(bb.xmin + bb.xmax) / 2.0,
                        -(bb.ymin + bb.ymax) / 2.0, -bb.zmin))


def _rename_products(path, label):
    """Rewrite every PRODUCT id/name in the STEP file to ``label`` so the
    slicer/viewer show the part as its filename, not the OCC translator
    string. No-op if the file has no PRODUCT entity."""
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    new = _PRODUCT_RE.sub(f"PRODUCT('{label}','{label}'", text)
    if new != text:
        # newline="" keeps the file's existing line endings unchanged.
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)


if __name__ == "__main__":
    # print_pose self-test: an off-origin box with a marker nub on its +z
    # face, in each rotate mode.
    def _box():
        b = (cq.Workplane("XY").workplane(offset=30.0)
             .center(50.0, -20.0).rect(10.0, 6.0).extrude(4.0))
        return b.union(cq.Workplane("XY").workplane(offset=34.0)
                       .center(50.0, -20.0).rect(2.0, 2.0).extrude(1.0))

    def _bb(w):
        return w.val().BoundingBox()

    bb = _bb(print_pose(_box()))                       # drop + centre only
    assert abs(bb.zmin) < 1e-9 and abs(bb.zmax - 5.0) < 1e-9
    assert abs(bb.xmin + bb.xmax) < 1e-9 and abs(bb.ymin + bb.ymax) < 1e-9

    bb = _bb(print_pose(_box(), "flip"))               # nub becomes the bed side
    assert abs(bb.zmin) < 1e-9 and abs(bb.zmax - 5.0) < 1e-9
    # flipped: the 2-wide nub is DOWN, so the slab's full 10x6 face is at the TOP
    assert abs(bb.xlen - 10.0) < 1e-9 and abs(bb.ylen - 6.0) < 1e-9

    bb = _bb(print_pose(_box(), ((1.0, 0.0, 0.0), -90.0)))   # stand on +y face
    assert abs(bb.zmin) < 1e-9 and abs(bb.zlen - 6.0) < 1e-9, \
        "the 6-long y edge must become the height"

    # a bare Shape (not a Workplane) is accepted too
    bb = _bb(print_pose(_box().val()))
    assert abs(bb.zmin) < 1e-9

    print("cadkit.step_export self-test OK")
