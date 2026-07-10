"""Shared STEP exporter for the Archive/3D projects.

A bare ``cq.exporters.export(obj, "housing.step")`` names the STEP *product*
"Open CASCADE STEP translator 7.8 …", so slicers and viewers (Bambu Studio,
FreeCAD) show that instead of "housing". This helper exports normally, then
rewrites the product name to match the file stem — giving a single, correctly
named product that every viewer reads, with no extra wrapper assembly.

Usage (single printed part):

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "freecad"))
    from step_export import export_step

    export_step(part, "housing.step")          # imports/slices as "housing"

For a multi-part *assembly*, keep using ``cq.Assembly`` with a per-part
``name=`` on each ``.add(...)`` — that already names every product.
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
