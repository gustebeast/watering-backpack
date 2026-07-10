"""Watering Backpack — build entry point.

  py -3.12 -m src.build     # export every printed-part STEP + assembly.step,
                            # then open/refresh the model in the FreeCAD viewer.

Geometry lives in the part modules; this just re-exports each printable part to
the project root and then builds the full assembly (src.backpack_housing), which
writes the housing STEPs + assembly.step and refreshes the viewer.

Individual parts can also be built on their own, e.g. `py -3.12 -m src.dual_clamp`.
"""
from __future__ import annotations

import pathlib
import sys

# Shared Archive/3D exporter (names the STEP product to match the file stem).
from cadkit.step_export import export_step                                  # noqa: E402

from .battery_dock import battery_dock
from .joystick_mount import joystick_mount
from .dual_clamp import dual_clamp_19, dual_clamp_23
from .backpack_housing import _build as _build_assembly

OUT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    export_step(battery_dock, str(OUT / "battery_dock.step"))
    export_step(joystick_mount, str(OUT / "joystick_mount.step"))
    export_step(dual_clamp_23, str(OUT / "dual_clamp_23.step"))
    export_step(dual_clamp_19, str(OUT / "dual_clamp_19.step"))
    _build_assembly()          # housing STEPs + assembly.step + viewer refresh


if __name__ == "__main__":
    main()
