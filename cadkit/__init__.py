"""cadkit — shared, project-agnostic CAD/3D-printing utilities.

A small library reused across the parametric-3D-printing projects. The modules depend
only on CadQuery/OCP: import them directly, e.g.

    from cadkit.fasteners import cut_anchor, M2, M4
    from cadkit.threads import cut_thread, threaded_rod
    from cadkit.step_export import export_step
    from cadkit.overlap_check import run
    from cadkit.joinery import ...
    from cadkit.printing import min_wall        # min-material floor (whole nozzle beads, no buffer)
    from cadkit import cq_colors
    from cadkit.board_geom import Boards        # a ROUTED KiCad board as CAD solids
    from cadkit.board_check import check        # ...and the gate that it is the routed one
                                                # (read PCB_README.md; kicad_geom.py and
                                                # kicad_silk.py run under KiCad's Python)
    from cadkit.pcbflow import gen              # MAKE a board from code (PCB_README.md §0)
    from cadkit.agents import current_agent, get_scope   # multi-agent: who owns what
    from cadkit.scratch import ScratchView               # fast per-part iteration loop

The assembly viewer is a web page, `cadkit.web`:

    from cadkit.web import show          # never raises; viewer trouble can't break a build

Dev-only tooling (the multi-agent worktree/merge CLI) lives in `cadkit/tools/` and is
run as a script, not imported: `py -3.12 cadkit/tools/agent_sync.py`.

Vendored into each project via `git subtree` at `<project>/cadkit`, so a cloned project
repo is fully self-contained; the canonical upstream is the standalone `cadkit` repo.
"""

__all__ = []
