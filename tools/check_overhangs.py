"""Overhang report for the battery dock (FDM printability).

Print orientation assumed: the Z=0 (battery-slot) face on the build plate,
part growing toward +Z. Any planar face whose normal points downward more
steeply than 45° from horizontal is an overhang that needs support; a 45°
(or shallower) ramp is self-supporting.

Run:  py -3.12 tools/check_overhangs.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src import battery_dock as bd

# 45° self-support limit: a planar ceiling has normal.z = -1; a 45° ramp has
# normal.z = -cos(45°) = -0.707. Flag anything STEEPER than ~45° (more
# negative than -0.72, leaving a small tolerance band around the 45° ramps).
STEEP = -0.72

dock = bd.battery_dock
rows = []
ramps = []
for f in dock.faces().vals():
    try:
        n = f.normalAt()
    except Exception:
        continue
    c = f.Center()
    if c.z <= 0.1:                 # on / near the build plate — supported
        continue
    if n.z < STEEP:
        rows.append((f.Area(), c.x, c.y, c.z, n.z))
    elif n.z < -0.5:              # downward but 45°-ish — printable ramp
        ramps.append((f.Area(), c.x, c.y, c.z, n.z))

rows.sort(key=lambda r: -r[0])
ramps.sort(key=lambda r: -r[0])

print(f"=== Battery dock overhang report (steep-overhang threshold n.z<{STEEP}) ===\n")
print(f"NEEDS-SUPPORT flats/steep faces: {len(rows)}")
for area, cx, cy, cz, nz in rows:
    print(f"  area={area:>6,.1f} mm2  center=({cx:>6.1f},{cy:>6.1f},{cz:>5.1f})  n.z={nz:>5.2f}")
print(f"  total steep area: {sum(r[0] for r in rows):,.1f} mm2\n")

print(f"45°-ish ramps (self-supporting, informational): {len(ramps)}")
for area, cx, cy, cz, nz in ramps:
    print(f"  area={area:>6,.1f} mm2  center=({cx:>6.1f},{cy:>6.1f},{cz:>5.1f})  n.z={nz:>5.2f}")
print(f"  total ramp area: {sum(r[0] for r in ramps):,.1f} mm2")
