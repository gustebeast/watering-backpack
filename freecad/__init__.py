"""cadkit.freecad — FreeCAD-specific helpers (the shared viewer hub).

Isolated from cadkit's core so the geometry/fastener/thread utilities never depend
on FreeCAD. The one public verb is `show()`; it never raises, so viewer trouble can
never break a build:

    from cadkit.freecad import show
    show(str(OUT / "assembly.step"))     # opens/refreshes the project's tab in the hub

The CPython-side entry point is `freecad_view.py`; `freecad_viewer.py` + `view.FCMacro`
run inside FreeCAD (the hub + its file-watcher). `view_assembly.cmd` is the double-click
launcher each project's `View Assembly.cmd` forwards to. These reference each other by
`__file__`-relative sibling paths, so they must stay co-located in this folder.
"""

from .freecad_view import show

__all__ = ["show"]
