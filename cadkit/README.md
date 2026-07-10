# cadkit

Small, project-agnostic helpers for **parametric 3D-printing with CadQuery** — the
shared code behind a set of printable-hardware projects. Vendored into each project via
`git subtree`, so every project repo stays self-contained.

## Layout

```
cadkit/
  fasteners.py       M2/M4 hole + heat-set-insert geometry (self-tap now, insert later);
                     one FastenerSpec API, print-undersize aware
  threads.py         self-supporting 45° FDM screw threads (read THREADS_README.md first)
  joinery.py         printable mortise-and-tenon slide joints (read JOINERY_README.md)
  step_export.py     export_step(obj, path) — names the STEP product after the file
  overlap_check.py   parallel interpenetration gate (wrap in tools/check_overlaps.py)
  cq_colors.py       hex / 0..255 / name -> cq.Color, for baking colours into a STEP
  freecad/           OPTIONAL FreeCAD viewer hub (isolated so the core needs no FreeCAD)
    __init__.py        `from cadkit.freecad import show`
  tools/
    agent_sync.py    dev-only multi-agent git-worktree coordination CLI (run as a script)
```

The **core** modules depend only on CadQuery/OCP — no FreeCAD. The FreeCAD-specific
viewer lives in `cadkit.freecad` and is opt-in; `show()` never raises, so viewer trouble
can't break a build.

## Use

```python
from cadkit.fasteners import cut_anchor, M2, M4
from cadkit.threads import cut_thread, threaded_rod
from cadkit.joinery import arrow_tenon, arrow_mortise
from cadkit.step_export import export_step
from cadkit.overlap_check import run
from cadkit import cq_colors
from cadkit.freecad import show          # optional; opens/refreshes a FreeCAD viewer tab
```

A project vendors cadkit at its repo root and runs its build via `python -m` from there,
so `cadkit` is importable with no path hack.

## Vendoring into a project

```
git remote add cadkit https://github.com/gustebeast/cadkit
git subtree add  --prefix=cadkit cadkit main --squash    # first time
git subtree pull --prefix=cadkit cadkit main --squash    # to update later
```

See `THREADS_README.md` and `JOINERY_README.md` before changing threads or joinery —
both encode FDM-specific rules that fail silently if broken.
