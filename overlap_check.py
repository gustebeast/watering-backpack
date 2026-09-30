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
agnostic — they never import the project, not even the caller's ``__main__``
(see ``_detached_main``), so ``run()`` is safe to call FROM the build script.

NOTE: OCCT booleans on complex shapes are memory-bandwidth-bound, so the realistic
speedup is ~2-3x, not linear in core count.

INCREMENTAL CACHE (``cache=<path>``). A pair's common volume depends on NOTHING but
the two shapes, so it can be remembered: each shape gets a sha1 of its BRep bytes
(exact geometry AND placement -- not a summary that could collide), and the cache maps
the two fingerprints to the volume. A rebuild that changed three parts recomputes only
the pairs those three are in; everything else is read back. Measured on a 664-part
instrument: fingerprinting all of it costs 1.4 s against a ~300 s scan, and every
fingerprint is byte-identical across separate builds, so an unchanged model reuses
everything. It is LOSSLESS -- a changed part changes its fingerprint, so its pairs miss
and are recomputed; a pair the cache has never seen is computed. This is deliberately
NOT an exclusion list: nothing is assumed unlikely to collide, and the bbox reject
already drops ~98.6% of pairs before any of this. RAW volumes are stored, so a later
run with a different threshold reads the same cache correctly, and entries are kept for
several runs (``CACHE_MAX``) so reverting a change hits the cache instead of rescanning.

Typical use from a project's tools/check_overlaps.py::

    from cadkit.overlap_check import run
    comps = [(n, wp.val()) for n, wp in collect_components()]
    sys.exit(run(comps, intended, jobs=args.jobs, show_all=args.all))
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import multiprocessing as mp
import os
import sys
import tempfile
import time

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp

VOL_EPS = 1.0   # mm^3 — ignore numerically-tiny touching contacts

_SHAPES = None  # per-worker cache: [cq.Shape, ...] indexed like the component list
_MIN_VOL = VOL_EPS   # per-worker threshold; set by the pool initializer, NOT inherited
                     # from the parent (spawn starts a fresh module), which is why a
                     # caller that just reassigned VOL_EPS used to be silently ignored
                     # on the parallel path while working on the serial one.


def bbox_overlap(a, b, tol=0.05) -> bool:
    """Cheap reject: do two bounding boxes overlap (with a small tolerance)?"""
    return (a.xmin < b.xmax - tol and b.xmin < a.xmax - tol and
            a.ymin < b.ymax - tol and b.ymin < a.ymax - tol and
            a.zmin < b.zmax - tol and b.zmin < a.zmax - tol)


def common_volume(sa, sb) -> float:
    """Volume (mm^3) of the boolean intersection of two cq.Shapes.

    NaN when the boolean could not be evaluated -- which is NOT the same fact as
    zero and must never be flattened into it. This returned 0.0 on failure, and the
    failure mode is silent in both directions: a null result shape MEASURES as zero
    volume without raising, so the `except` below never even ran. A coil swept
    through a tenon wall came back "clean".

    Worse, the failures are not random. A boolean fails on awkward geometry -- a
    swept helix, a thin sliver, a tangency -- and awkward-AND-interpenetrating is
    precisely the pair a gate exists to catch. Fail LOUD; the caller reports NaN
    separately from a volume.
    """
    try:
        op = BRepAlgoAPI_Common(sa.wrapped, sb.wrapped)
        common = op.Shape()
        if not op.IsDone() or common.IsNull():
            return float("nan")
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(common, props)
        return props.Mass()
    except Exception:
        return float("nan")


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


def _worker_load(path, min_vol=None):
    """Pool initializer: load the serialized shapes once into this worker, and
    carry the caller's threshold across the spawn boundary."""
    global _SHAPES, _MIN_VOL
    if min_vol is not None:
        _MIN_VOL = min_vol
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
    """RAW common volume for one pair. The threshold is applied in the PARENT, not
    here: the cache stores raw volumes so a run with a different min_vol reads it
    correctly, and a pair's volume must mean the same thing whoever asks."""
    i, j = ij
    return (common_volume(_SHAPES[i], _SHAPES[j]), i, j)


def _canonical(shapes):
    """Put every shape into the SAME internal flag state before fingerprinting.

    BRep bytes carry OCCT's per-TShape flags, not just geometry, and handing shapes to
    the workers (adding them to a compound) flips one: measured, 654 of 664 shapes
    changed their bytes after one ``_serialize``. Fingerprints taken before and after
    would then disagree for reasons that have nothing to do with the model. Adding them
    all to a throwaway compound first makes the state the same in every run, whatever
    the caller did with these shapes beforehand (export a STEP, tessellate a GLB).

    Note OCCT also mutates a boolean's OPERANDS, so a second scan of the SAME in-memory
    shapes can still miss. A build runs one scan per process, where shapes are freshly
    built, and that path is stable -- verified byte-identical across separate builds."""
    from OCP.TopoDS import TopoDS_Compound
    from OCP.BRep import BRep_Builder
    builder = BRep_Builder()
    comp = TopoDS_Compound()
    builder.MakeCompound(comp)
    for s in shapes:
        builder.Add(comp, s.wrapped)


def fingerprint(shape) -> str:
    """sha1 of a shape's BRep bytes: its exact geometry and placement. Used as the
    cache key, so it must be a hash of the real thing rather than a summary (face
    count, volume, bbox) that two different shapes could share. Call ``_canonical``
    on the whole set first."""
    buf = io.BytesIO()
    shape.exportBrep(buf)
    return hashlib.sha1(buf.getvalue()).hexdigest()


def _cache_key(fa, fb) -> str:
    return f"{fa}:{fb}" if fa <= fb else f"{fb}:{fa}"


CACHE_MAX = 50_000      # entries kept; ~4 MB of JSON, ~15 runs of a 3k-pair assembly


def _cache_load(path):
    """-> ({key: volume}, last run number). Unreadable or stale-format caches are
    simply empty: this is an optimisation and must never be able to fail a gate."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("v") == 2 and isinstance(d.get("pairs"), dict):
            return d["pairs"], int(d.get("run", 0))
    except (OSError, ValueError):
        pass
    return {}, 0


def _cache_save(path, old, fresh, run):
    """Merge this run's results into the old ones and keep a RETENTION HISTORY.

    Pruning to just-this-run was the obvious policy and the wrong one: agents revert
    and re-merge constantly, and a part that goes back to a geometry seen two runs ago
    should hit, not recompute. (Measured: nudge one part, revert it, and a
    prune-to-this-run cache reused 9 pairs of 3170 -- the revert cost a full scan.)
    So entries carry the run that last used them and the oldest are evicted only when
    the file would exceed CACHE_MAX."""
    merged = dict(old)
    merged.update({k: [v, run] for k, v in fresh.items()})
    if len(merged) > CACHE_MAX:
        keep = sorted(merged.items(), key=lambda kv: kv[1][1], reverse=True)[:CACHE_MAX]
        merged = dict(keep)
    tmp = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"v": 2, "run": run, "pairs": merged}, f)
        os.replace(tmp, path)
    except OSError as e:                      # a cache is an optimisation, never a gate
        print(f"  (overlap cache not written: {e})")
        with contextlib.suppress(OSError):
            os.remove(tmp)


@contextlib.contextmanager
def _detached_main():
    """Stop spawned workers from re-importing the CALLER's ``__main__``.

    Windows uses spawn, and spawn's bootstrap re-imports the parent's main module
    (as ``__mp_main__``) purely to resolve pickled references. This engine never
    needs it: the pool's initializer and task function both live in THIS module,
    which the workers import by name. But if the caller's ``__main__`` is the
    project build script, that re-import re-runs its module-level geometry in
    EVERY worker. Hiding ``__spec__``/``__file__`` for the duration of the pool
    makes multiprocessing skip the main fixup entirely.
    """
    main = sys.modules.get("__main__")
    saved = {}
    for attr in ("__spec__", "__file__"):
        if main is not None and hasattr(main, attr):
            saved[attr] = getattr(main, attr)
            setattr(main, attr, None)
    try:
        yield
    finally:
        for attr, val in saved.items():
            setattr(main, attr, val)


def _scan(components, jobs, min_vol=None, cache=None):
    """Return raw [(vol, name_a, name_b), ...] for interpenetrating pairs.

    With ``cache`` (a path), pairs whose BOTH shapes are byte-identical to a previous
    run are read back instead of re-booleaned; see INCREMENTAL CACHE above."""
    names = [n for n, _ in components]
    shapes = [s for _, s in components]
    bboxes = [s.BoundingBox() for s in shapes]
    cands = _candidate_pairs(bboxes)
    eps = VOL_EPS if min_vol is None else min_vol

    known, keys, todo = {}, {}, cands
    if cache:
        t_fp = time.perf_counter()
        _canonical(shapes)
        fps = [fingerprint(s) for s in shapes]
        cached, last_run = _cache_load(cache)
        todo = []
        for i, j in cands:
            k = _cache_key(fps[i], fps[j])
            keys[(i, j)] = k
            hit = cached.get(k)
            if hit is not None:
                known[(i, j)] = hit[0]
            else:
                todo.append((i, j))
        print(f"  overlap cache: {len(known)} of {len(cands)} pairs reused, "
              f"{len(todo)} to compute (fingerprints {time.perf_counter() - t_fp:.1f}s)")

    if not todo:
        computed = []
    elif jobs <= 1:
        computed = [(common_volume(shapes[i], shapes[j]), i, j) for i, j in todo]
    else:
        fd, path = tempfile.mkstemp(suffix=".bin", prefix="overlap_")
        os.close(fd)
        try:
            _serialize(shapes, path)
            with _detached_main(),                     mp.Pool(jobs, initializer=_worker_load, initargs=(path, eps)) as pool:
                computed = list(pool.imap_unordered(_pair_vol, todo, chunksize=1))
        finally:
            os.remove(path)

    raw = list(computed) + [(v, i, j) for (i, j), v in known.items()]
    if cache:
        # NaN (the boolean did not evaluate) is NOT a result and must not be cached:
        # it would freeze one run's failure into every later run, and the caller has to
        # see the pair as unchecked each time. `v == v` is the not-NaN test.
        _cache_save(cache, cached,
                    {keys[(i, j)]: v for v, i, j in raw if (i, j) in keys and v == v},
                    last_run + 1)
    # keep NaN through the threshold: every comparison against it is False, so a plain
    # `> eps` would silently drop exactly the pairs that could not be checked
    return [(v, names[i], names[j]) for v, i, j in raw if v > eps or v != v]


def default_jobs() -> int:
    """Half the cores by default — booleans are memory-bound, so more workers buy
    little and cost RAM (each holds the whole shape set). Override with --jobs."""
    return max(1, (os.cpu_count() or 2) // 2)


def run(components, is_intended, jobs=None, show_all=False, min_vol=None,
        cache=None) -> int:
    """Scan ``components`` ([(name, cq.Shape)]); print and return the count of
    UNINTENDED overlaps. ``is_intended(a, b)`` marks designed contacts (applied in
    the parent). ``jobs<=1`` forces a single-process scan. ``cache`` is a path for the
    incremental pair cache (see INCREMENTAL CACHE); None disables it."""
    if jobs is None:
        jobs = default_jobs()
    t0 = time.perf_counter()
    pairs = _scan(components, jobs, min_vol, cache)
    dt = time.perf_counter() - t0

    bad, ok, failed = [], [], []
    for vol, na, nb in pairs:
        if vol != vol:                       # NaN: the boolean did not evaluate
            failed.append((na, nb))
            continue
        (ok if is_intended(na, nb) else bad).append((vol, na, nb))
    bad.sort(reverse=True)
    ok.sort(reverse=True)
    failed.sort()

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
    if failed:
        # NOT clean and NOT dismissable. An unevaluable pair is an unknown, and an
        # unknown in a gate counts against it -- that is the whole lesson here.
        print(f"\n== COULD NOT BE CHECKED ({len(failed)}) -- boolean FAILED, "
              f"treat as suspect ==")
        for na, nb in failed:
            print(f"   {'  ?  ':>9}       {na:14} <-> {nb}")
        print("   re-check these by sampling points (shape.isInside), not by volume.")
    return len(bad) + len(failed)
