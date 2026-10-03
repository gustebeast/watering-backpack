"""Let a project keep `elec/finish.py`, `elec/layout.py`... as its entry points.

A project that grew up with the pipeline in its own `elec/` folder has habits, docs and
tools that say `elec/finish.py elec/out/<board>` and `import layout`. A three-line file
under the old name keeps all of that working while the code lives here:

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cadkit.pcbflow._shim import forward
    forward(__name__, "finish")

Run as a script, it runs pcbflow's script of that name with the same arguments. Imported,
the name resolves to pcbflow's module. A NEW project does not need this: run
`cadkit/pcbflow/finish.py` directly.
"""
import importlib.util
import os
import runpy
import sys

FLOW = os.path.dirname(os.path.abspath(__file__))


def forward(name, script):
    path = os.path.join(FLOW, script + ".py")
    # pcbflow's scripts import each other by bare name from their own folder, and must
    # find each other there rather than the project's forwarding files
    if FLOW in sys.path:
        sys.path.remove(FLOW)
    sys.path.insert(0, FLOW)
    if name == "__main__":
        sys.argv[0] = path
        runpy.run_path(path, run_name="__main__")
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
