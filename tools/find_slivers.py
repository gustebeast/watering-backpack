"""Sliver / tiny-face finder for the battery dock.

Hunts the kind of geometry that signals alignment problems: faces with very
small area, and faces with a very small minimum extent (thin ledges/steps,
usually 0.5 mm artifacts from BOOL_OVERSHOOT mismatches or crude chamfer
wedges). Reports location + normal so each can be traced to its cutter.

Run:  py -3.12 tools/find_slivers.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src import battery_dock as bd

AREA_LIMIT = 3.0      # mm2 — faces smaller than this are suspect
THIN_LIMIT = 0.7      # mm  — a face whose smallest nonzero extent is below
                      # this is a thin ledge/step (e.g. a 0.5 mm overshoot)

dock = bd.battery_dock
faces = dock.faces().vals()
print(f"Dock has {len(faces)} faces. Limits: area<{AREA_LIMIT} mm2, thin<{THIN_LIMIT} mm\n")

rows = []
for f in faces:
    a = f.Area()
    b = f.BoundingBox()
    dims = sorted([b.xlen, b.ylen, b.zlen])
    thin = dims[1]            # 2nd smallest (smallest is ~0 for a planar face)
    if a < AREA_LIMIT or thin < THIN_LIMIT:
        try:
            n = f.normalAt()
            nstr = f"({n.x:+.2f},{n.y:+.2f},{n.z:+.2f})"
        except Exception:
            nstr = "(curved)"
        c = f.Center()
        rows.append((a, thin, c.x, c.y, c.z, nstr))

rows.sort(key=lambda r: (r[0], r[1]))
print(f"{len(rows)} suspect faces (smallest first):")
for a, thin, cx, cy, cz, nstr in rows:
    print(f"  area={a:>6.2f}  thin={thin:>4.2f}  center=({cx:>6.1f},{cy:>6.1f},{cz:>5.1f})  n={nstr}")
print(f"\ntotal suspect-face area: {sum(r[0] for r in rows):,.1f} mm2")
