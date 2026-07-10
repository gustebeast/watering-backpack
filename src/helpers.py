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
    dock pocket cut and the assembly viz so they always agree."""
    return wp.rotate((0, 0, 0), (1, 0, 0), rot_deg).translate(translate)


def import_step(path) -> cq.Workplane | None:
    """Import a STEP file as a CadQuery Workplane. Returns None if the file is
    missing — lets the build degrade gracefully when a reference STEP hasn't
    been dropped in yet."""
    p = pathlib.Path(path)
    if not p.exists():
        return None
    return cq.importers.importStep(str(p))
