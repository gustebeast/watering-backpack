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
the viewer keeps every part in its assembly place.

DECLARE IT ONCE (cable-spool #1070). A part's bed face is a fact about the
part, and the project states it in ONE table of `PrintOrientation`s, which
both this exporter and the joinery's `facing` read:

    from cadkit.orientation import PrintOrientation as PO

    PRINT_ORIENTATION = {
        "lid":   PO("flip", "modelled top is the bed — slots print clean"),
        "frame": PO(None, "models as printed"),
    }

    for name, part, fname in PARTS:
        export_print(part, PRINT_ORIENTATION[name], out / fname)

`export_print` REFUSES anything that is not a `PrintOrientation`, so a part
can no longer be exported with its bed face unstated — which is how a TPU pin
shipped standing on its end as a 5.9:1 tower. Call `require_declared()` on the
table at import time to catch a missing or stale name, and print
`unconfirmed()` on every build so a guessed orientation stays visible. The
legacy ``PRINT_ROT = {name: rotate}`` forms still work through `print_pose`
during migration.

Self-test: ``python -m cadkit.step_export`` (or run this file).
"""

import pathlib
import re

import cadquery as cq

from .orientation import PrintOrientation

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


def export_print(obj, orientation, path, name=None):
    """Pose ``obj`` for printing and export it — the ONE export path for a
    printed part.

    Unlike ``export_step(print_pose(obj, rot), path)`` this REFUSES an
    undeclared bed face: ``orientation`` must be a
    `cadkit.orientation.PrintOrientation`, so "nobody said" can no longer
    arrive as the same ``None`` that means "models as printed" (#1070).
    """
    if not isinstance(orientation, PrintOrientation):
        raise TypeError(
            "export_print needs a PrintOrientation for %s, not %r. Every "
            "printed part declares its bed face AND the reason for it:\n"
            "    from cadkit.orientation import PrintOrientation as PO\n"
            "    PO(None, 'models as printed')   PO('flip', 'why')\n"
            "    PO(((1, 0, 0), -90), 'stands on its +y face')"
            % (name or pathlib.Path(str(path)).stem, orientation))
    export_step(print_pose(obj, orientation), path, name)


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

    A `cadkit.orientation.PrintOrientation` is also accepted, and is what
    projects should pass — it carries the same rotation plus the REASON for
    it. Prefer `export_print`, which refuses the bare forms outright.
    """
    if isinstance(rotate, PrintOrientation):
        rotate = rotate.rot
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

    # a PrintOrientation poses exactly like the bare form it carries
    from .orientation import PrintOrientation as _PO
    for _rot in (None, "flip", ((1.0, 0.0, 0.0), -90.0)):
        a = _bb(print_pose(_box(), _rot))
        b = _bb(print_pose(_box(), _PO(_rot, "self-test")))
        assert (abs(a.zlen - b.zlen) < 1e-9 and abs(a.xlen - b.xlen) < 1e-9
                and abs(a.ylen - b.ylen) < 1e-9), _rot

    # export_print refuses an undeclared bed face, in every bare form
    import tempfile, os
    _d = tempfile.mkdtemp()
    for _bad in (None, "flip", ((1.0, 0.0, 0.0), -90.0)):
        try:
            export_print(_box(), _bad, os.path.join(_d, "x.step"))
        except TypeError as e:
            assert "PrintOrientation" in str(e)
        else:
            raise AssertionError("export_print accepted %r" % (_bad,))
    _f = os.path.join(_d, "nub.step")
    export_print(_box(), _PO("flip", "self-test"), _f)
    assert "nub" in pathlib.Path(_f).read_text(errors="replace")

    print("cadkit.step_export self-test OK")
