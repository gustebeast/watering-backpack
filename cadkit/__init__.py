"""cadkit — shared, project-agnostic CAD/3D-printing utilities.

A small library reused across the parametric-3D-printing projects. The core modules
depend only on CadQuery/OCP (no FreeCAD): import them directly, e.g.

    from cadkit.fasteners import cut_anchor, M2, M4
    from cadkit.threads import cut_thread, threaded_rod
    from cadkit.step_export import export_step
    from cadkit.overlap_check import run
    from cadkit.joinery import ...
    from cadkit import cq_colors

FreeCAD-specific helpers (the viewer hub) live in the OPTIONAL `cadkit.freecad`
subpackage, kept separate so the core never drags in a FreeCAD dependency:

    from cadkit.freecad import show      # never raises; viewer trouble can't break a build

Dev-only tooling (the multi-agent worktree/merge CLI) lives in `cadkit/tools/` and is
run as a script, not imported: `py -3.12 cadkit/tools/agent_sync.py`.

Vendored into each project via `git subtree` at `<project>/cadkit`, so a cloned project
repo is fully self-contained; the canonical upstream is the standalone `cadkit` repo.
"""

__all__ = []
