"""Quick-look inspector for an imported STEP file.

Run from repo root:
  py -3.12 tools/inspect_step.py references/makita_battery.step

Prints overall bounding box, face count, and a list of all *planar* faces
grouped by their outward-pointing normal direction. For a slide-on dock
interface (which is mostly planar), this exposes the geometry we need to
design the dock against: which face is the tool-side, where the rails
live, where the terminal recess is, etc.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import cadquery as cq


def _round(x: float, n: int = 2) -> float:
    return round(x, n)


def _classify_normal(nx: float, ny: float, nz: float, tol: float = 1e-3) -> str:
    for axis, val in (("X", nx), ("Y", ny), ("Z", nz)):
        if abs(abs(val) - 1.0) < tol:
            other = [v for a, v in zip("XYZ", (nx, ny, nz)) if a != axis]
            if all(abs(o) < tol for o in other):
                return f"{'+' if val > 0 else '-'}{axis}"
    return f"({_round(nx, 3)},{_round(ny, 3)},{_round(nz, 3)})"


def main(path: str) -> None:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: {p} not found", file=sys.stderr)
        sys.exit(2)

    wp = cq.importers.importStep(str(p))
    solid = wp.val()
    bbox = solid.BoundingBox()

    print(f"=== {p.name} ===")
    print(f"Bounding box (mm):")
    print(f"  X: {_round(bbox.xmin)} .. {_round(bbox.xmax)}   (width  {_round(bbox.xlen)})")
    print(f"  Y: {_round(bbox.ymin)} .. {_round(bbox.ymax)}   (depth  {_round(bbox.ylen)})")
    print(f"  Z: {_round(bbox.zmin)} .. {_round(bbox.zmax)}   (height {_round(bbox.zlen)})")

    faces = solid.Faces()
    print(f"\nTotal faces: {len(faces)}")

    # Group planar faces by outward normal direction.
    planar_by_normal: dict[str, list] = defaultdict(list)
    nonplanar = 0
    for f in faces:
        try:
            n = f.normalAt()
        except Exception:                                       # noqa: BLE001
            nonplanar += 1
            continue
        # Only keep faces whose normal is well-defined and constant — i.e. truly planar.
        try:
            geom = f.geomType()
        except Exception:                                       # noqa: BLE001
            geom = None
        if geom != "PLANE":
            nonplanar += 1
            continue
        key = _classify_normal(n.x, n.y, n.z)
        planar_by_normal[key].append(f)

    print(f"  planar: {sum(len(v) for v in planar_by_normal.values())}")
    print(f"  non-planar: {nonplanar}")

    # Show the planar groups ordered by area descending — the largest faces
    # of any given normal direction are usually the "main" wall on that side.
    print("\nPlanar faces, grouped by outward normal:")
    for normal_key in sorted(planar_by_normal):
        group = planar_by_normal[normal_key]
        # Sort by area descending
        scored = []
        for f in group:
            try:
                area = f.Area()
            except Exception:                                   # noqa: BLE001
                area = 0.0
            c = f.Center()
            scored.append((area, c))
        scored.sort(key=lambda t: -t[0])
        print(f"\n  normal {normal_key}  ({len(scored)} faces)")
        for area, c in scored[:8]:
            print(f"    area={_round(area, 1):>8}  center=({_round(c.x):>7}, {_round(c.y):>7}, {_round(c.z):>7})")
        if len(scored) > 8:
            print(f"    ... and {len(scored) - 8} smaller")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: py -3.12 tools/inspect_step.py PATH_TO_STEP", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
