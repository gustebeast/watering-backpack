"""Targeted dimensional dump of the Makita battery's tool-side interface.

Usage:
  py -3.12 tools/inspect_interface.py [Z_FLOOR]

Prints a structured inventory of every planar face with center Z >= Z_FLOOR
(default 0). This is the slice where the slide rails, latch notch, and
terminal pocket live — its planar faces, grouped by outward normal,
let us read off the dock geometry without needing a viewer.

Output sections:
  +Z faces — the "tops" the dock sits against; rail-top heights live here.
  -Z faces — the "ceilings" of features cut into the battery top
             (e.g. the floor of the latch notch).
  +Y / -Y faces — the inner / outer walls of the slide rails.
  +X / -X faces — the front (latch) and back walls / stops.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import cadquery as cq


REFERENCES = Path(__file__).resolve().parents[1] / "references"
BATTERY    = REFERENCES / "makita_battery.step"


def _round(x: float, n: int = 2) -> float:
    return round(x, n)


def _classify_normal(nx: float, ny: float, nz: float, tol: float = 1e-3) -> str | None:
    for axis, val in (("X", nx), ("Y", ny), ("Z", nz)):
        if abs(abs(val) - 1.0) < tol:
            other = [v for a, v in zip("XYZ", (nx, ny, nz)) if a != axis]
            if all(abs(o) < tol for o in other):
                return f"{'+' if val > 0 else '-'}{axis}"
    return None  # non-axis-aligned


def main() -> None:
    z_floor = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    wp = cq.importers.importStep(str(BATTERY))
    solid = wp.val()
    bbox = solid.BoundingBox()
    print(f"Z range of whole model: {_round(bbox.zmin)} .. {_round(bbox.zmax)}")
    print(f"Filtering to faces with center Z >= {z_floor}")

    # Group axis-aligned planar faces above the cutoff, by outward normal axis.
    by_axis: dict[str, list] = defaultdict(list)
    for f in solid.Faces():
        try:
            if f.geomType() != "PLANE":
                continue
            n = f.normalAt()
        except Exception:                                       # noqa: BLE001
            continue
        axis_key = _classify_normal(n.x, n.y, n.z)
        if axis_key is None:
            continue
        c = f.Center()
        if c.z < z_floor:
            continue
        try:
            area = f.Area()
        except Exception:                                       # noqa: BLE001
            area = 0.0
        # Face's own bounding box reveals its extent on each axis.
        fb = f.BoundingBox()
        by_axis[axis_key].append((area, c, fb))

    for axis_key in ("+Z", "-Z", "+Y", "-Y", "+X", "-X"):
        group = by_axis.get(axis_key, [])
        if not group:
            continue
        group.sort(key=lambda t: -t[0])
        print(f"\n== {axis_key} faces ({len(group)}) ==")
        for area, c, fb in group[:20]:
            xspan = f"x:[{_round(fb.xmin):>6} .. {_round(fb.xmax):>6}]"
            yspan = f"y:[{_round(fb.ymin):>6} .. {_round(fb.ymax):>6}]"
            zspan = f"z:[{_round(fb.zmin):>6} .. {_round(fb.zmax):>6}]"
            print(f"  area={_round(area):>7}  cz={_round(c.z):>6}  {xspan} {yspan} {zspan}")
        if len(group) > 20:
            print(f"  ... and {len(group) - 20} smaller")


if __name__ == "__main__":
    main()
