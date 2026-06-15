"""Geometric helper functions used by part modules.

Pure functions — no module-level state. All dimensions are passed in as
arguments OR pulled from src.dimensions.
"""

from __future__ import annotations

import pathlib

import cadquery as cq

_BUILD_COUNTER_FILE = (pathlib.Path(__file__).resolve().parents[1]
                       / "tools" / "build_counter.txt")


def bump_build_counter() -> int:
    """Increment + persist the shared build counter (floated as 3D text
    above each assembly so a stale FreeCAD tab is obvious)."""
    try:
        n = int(_BUILD_COUNTER_FILE.read_text().strip()) + 1
    except (OSError, ValueError):
        n = 1
    try:
        _BUILD_COUNTER_FILE.write_text(f"{n}\n")
    except OSError:                                                # noqa: BLE001
        pass
    return n


def cyl(d: float, h: float, z: float = 0.0) -> cq.Workplane:
    """Solid cylinder, diameter d, height h, base at z."""
    return cq.Workplane("XY").workplane(offset=z).circle(d / 2).extrude(h)


def box(w: float, d: float, h: float,
        x: float = 0.0, y: float = 0.0, z: float = 0.0,
        centered: tuple[bool, bool, bool] = (True, True, False)) -> cq.Workplane:
    """Axis-aligned box. Default: centered in X/Y, base at z. Translate to (x, y, z)."""
    return (
        cq.Workplane("XY")
        .box(w, d, h, centered=centered)
        .translate((x, y, z))
    )


def cone_solid(d_bottom: float, d_top: float, h: float, z_base: float) -> cq.Workplane:
    """Solid truncated cone: d_bottom at z_base, d_top at z_base+h (filled from axis)."""
    return (
        cq.Workplane("XY").workplane(offset=z_base)
        .circle(d_bottom / 2)
        .workplane(offset=h)
        .circle(d_top / 2)
        .loft()
    )


def heal(wp: cq.Workplane) -> cq.Workplane:
    """Clean up sliver faces / near-tangent boolean artifacts before STEP export.

    Wraps OCC's ShapeFix_Shape, which:
      • fixes face/wire orientations,
      • re-projects PCurves onto their host surfaces,
      • repairs near-tangent boolean residue,
      • tightens shape tolerances toward the geometric truth.

    Strict STEP importers (FreeCAD's GUI import, Onshape) emit warnings on
    untreated boolean output; healing usually clears them. Never raises —
    if the fixer can't help, we hand back the original shape.
    """
    try:
        from OCP.ShapeFix import ShapeFix_Shape
        solid = wp.val()
        fixer = ShapeFix_Shape(solid.wrapped)
        fixer.Perform()
        fixed = fixer.Shape()
        # Shape.cast() returns the proper subclass (Solid/Compound) so the
        # healed result is usable as a boolean BASE (findSolid needs a typed
        # Solid), not only as a cut tool or via .val(). A bare cq.Shape(fixed)
        # is a generic Shape that findSolid can't locate.
        return cq.Workplane("XY").add(cq.Shape.cast(fixed))
    except Exception:                                              # noqa: BLE001
        return wp


def dovetail_arrowhead(half_root: float, half_tip: float,
                       clr: float = 0.0, open_ov: float = 0.0) -> list[tuple]:
    """Arrowhead dovetail cross-section as (across, depth) points.

    Narrow opening at depth 0, 45° flanks flaring OUT to the widest point (the
    undercut that traps the joint), then 45° flanks tapering IN to a single
    POINTY top — no flat ridge, so it's fully self-supporting when printed with
    the opening on the bed. SHARED by the dock mortise and the housing tenon so
    the two always have the identical shape: tenon uses clr=0 (nominal solid),
    mortise uses clr>0 (the void, offset out for slide clearance). `open_ov`
    pushes the opening edge back past depth 0 (a boolean overshoot into the
    parent wall / back face) so the union/cut fuses cleanly.

        across↑        (0, d_peak)          <- pointy top (45° each side)
              |        /\\
              |   (ht,d_max)  (-ht,d_max)    <- widest (undercut)
              |   /              \\
              | (hr,0)        (-hr,0)        <- opening (on the bed)
              +-------------------> depth
    """
    hr = half_root + clr
    ht = half_tip + clr
    d_max  = ht - hr                 # 45° flare from the opening to the widest
    d_peak = d_max + ht              # 45° taper from the widest to the point
    return [(-hr, -open_ov), (hr, -open_ov),
            (ht, d_max),
            (0.0, d_peak),
            (-ht, d_max)]


def place_terminal(wp: cq.Workplane, rot_deg: float, translate) -> cq.Workplane:
    """Seat the imported 643852-2 terminal in the dock frame: rotate about the
    +X axis (through the origin) by `rot_deg`, then translate. Shared by the
    dock (pocket cut) and viz (fit check) so they always agree."""
    return wp.rotate((0, 0, 0), (1, 0, 0), rot_deg).translate(translate)


def import_step(path) -> cq.Workplane | None:
    """Import a STEP file as a CadQuery Workplane. Returns None if the file
    is missing — lets viz.py degrade gracefully when reference STEPs haven't
    been dropped in yet."""
    import pathlib
    p = pathlib.Path(path)
    if not p.exists():
        return None
    return cq.importers.importStep(str(p))


def import_stl(path) -> cq.Workplane | None:
    """Import an STL mesh as a CadQuery Workplane.

    For viz only — STL geometry is tessellated, so booleans against it are
    fragile. Good enough for "show this in the assembly so we can see
    where it sits"; not suitable for printable parts. Returns None if
    the file is missing.

    CadQuery 2.x doesn't expose a top-level STL importer, so we drop down
    to OCP's StlAPI_Reader, which builds an OCC shell from the mesh.
    """
    import pathlib
    p = pathlib.Path(path)
    if not p.exists():
        return None

    from OCP.StlAPI import StlAPI_Reader
    from OCP.TopoDS import TopoDS_Shape

    shape = TopoDS_Shape()
    reader = StlAPI_Reader()
    if not reader.Read(shape, str(p)):
        return None
    return cq.Workplane("XY").add(cq.Shape(shape))
