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
