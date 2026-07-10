"""Parallel assembly overlap checker — shared engine for CadQuery 3D projects.

A project supplies (a) its placed parts as ``components = [(name, cq.Shape), ...]``
and (b) an ``is_intended(name_a, name_b) -> bool`` predicate marking designed
contacts; ``run()`` finds every pair whose solids actually interpenetrate (volume
> ``VOL_EPS`` mm^3) and prints the UNINTENDED ones, returning their count (use it
as the process exit code).

Why it's structured this way: the per-pair common-volume booleans are independent,
so they run across worker processes. The caller builds the assembly ONCE; the engine
serializes the shapes with BinTools (OCP shapes don't pickle and Windows can't fork)
and each worker loads them ONCE (~0.3 s, vs tens of seconds to rebuild), then the
bbox-surviving PAIRS are handed out with dynamic scheduling (``imap_unordered``) so
the few expensive booleans spread across cores. ``is_intended`` is applied in the
PARENT, so the verdict is identical to a serial scan and workers stay project-
agnostic (they never import the project).

NOTE: OCCT booleans on complex shapes are memory-bandwidth-bound, so the realistic
speedup is ~2-3x, not linear in core count.

Typical use from a project's tools/check_overlaps.py::

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "freecad"))
    from overlap_check import run
    comps = [(n, wp.val()) for n, wp in collect_components()]
    sys.exit(run(comps, intended, jobs=args.jobs, show_all=args.all))
"""

from __future__ import annotations

import multiprocessing as mp
import os
import tempfile
import time

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp

VOL_EPS = 1.0   # mm^3 — ignore numerically-tiny touching contacts

_SHAPES = None  # per-worker cache: [cq.Shape, ...] indexed like the component list


def bbox_overlap(a, b, tol=0.05) -> bool:
    """Cheap reject: do two bounding boxes overlap (with a small tolerance)?"""
    return (a.xmin < b.xmax - tol and b.xmin < a.xmax - tol and
            a.ymin < b.ymax - tol and b.ymin < a.ymax - tol and
            a.zmin < b.zmax - tol and b.zmin < a.zmax - tol)


def common_volume(sa, sb) -> float:
    """Volume (mm^3) of the boolean intersection of two cq.Shapes; 0 on failure."""
    try:
        common = BRepAlgoAPI_Common(sa.wrapped, sb.wrapped).Shape()
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(common, props)
        return props.Mass()
    except Exception:
        return 0.0


def _candidate_pairs(bboxes):
    n = len(bboxes)
    return [(i, j) for i in range(n) for j in range(i + 1, n)
            if bbox_overlap(bboxes[i], bboxes[j])]


def _serialize(shapes, path):
    """Write all shapes into one BinTools compound (child order preserved on read)."""
    from OCP.TopoDS import TopoDS_Compound
    from OCP.BRep import BRep_Builder
    from OCP.BinTools import BinTools
    builder = BRep_Builder()
    comp = TopoDS_Compound()
    builder.MakeCompound(comp)
    for s in shapes:
        builder.Add(comp, s.wrapped)
    BinTools.Write_s(comp, path)


def _worker_load(path):
    """Pool initializer: load the serialized shapes once into this worker."""
    global _SHAPES
    import cadquery as cq
    from OCP.TopoDS import TopoDS_Compound, TopoDS_Iterator
    from OCP.BinTools import BinTools
    comp = TopoDS_Compound()
    BinTools.Read_s(comp, path)
    it = TopoDS_Iterator(comp)
    _SHAPES = []
    while it.More():
        _SHAPES.append(cq.Shape(it.Value()))
        it.Next()


def _pair_vol(ij):
    i, j = ij
    vol = common_volume(_SHAPES[i], _SHAPES[j])
    return (vol, i, j) if vol > VOL_EPS else None


def _scan(components, jobs):
    """Return raw [(vol, name_a, name_b), ...] for interpenetrating pairs."""
    names = [n for n, _ in components]
    shapes = [s for _, s in components]
    bboxes = [s.BoundingBox() for s in shapes]
    cands = _candidate_pairs(bboxes)
    if jobs <= 1:
        raw = [(common_volume(shapes[i], shapes[j]), i, j) for i, j in cands]
        raw = [r for r in raw if r[0] > VOL_EPS]
    else:
        fd, path = tempfile.mkstemp(suffix=".bin", prefix="overlap_")
        os.close(fd)
        try:
            _serialize(shapes, path)
            with mp.Pool(jobs, initializer=_worker_load, initargs=(path,)) as pool:
                raw = [r for r in pool.imap_unordered(_pair_vol, cands, chunksize=1)
                       if r]
        finally:
            os.remove(path)
    return [(v, names[i], names[j]) for v, i, j in raw]


def default_jobs() -> int:
    """Half the cores by default — booleans are memory-bound, so more workers buy
    little and cost RAM (each holds the whole shape set). Override with --jobs."""
    return max(1, (os.cpu_count() or 2) // 2)


def run(components, is_intended, jobs=None, show_all=False) -> int:
    """Scan ``components`` ([(name, cq.Shape)]); print and return the count of
    UNINTENDED overlaps. ``is_intended(a, b)`` marks designed contacts (applied in
    the parent). ``jobs<=1`` forces a single-process scan."""
    if jobs is None:
        jobs = default_jobs()
    t0 = time.perf_counter()
    pairs = _scan(components, jobs)
    dt = time.perf_counter() - t0

    bad, ok = [], []
    for vol, na, nb in pairs:
        (ok if is_intended(na, nb) else bad).append((vol, na, nb))
    bad.sort(reverse=True)
    ok.sort(reverse=True)

    mode = "serial" if jobs <= 1 else f"{jobs} workers"
    print(f"checked {len(components)} components for overlaps ({mode}, {dt:.1f}s)")
    if show_all:
        print(f"\n-- intended contacts ({len(ok)}) --")
        for vol, na, nb in ok:
            print(f"   {vol:9.1f} mm^3   {na:14} <-> {nb}")
    print(f"\n== UNINTENDED overlaps ({len(bad)}) ==")
    for vol, na, nb in bad:
        print(f"   {vol:9.1f} mm^3   {na:14} <-> {nb}")
    if not bad:
        print("   none - clean!")
    return len(bad)
