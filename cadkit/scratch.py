# -*- coding: utf-8 -*-
"""cadkit.scratch — fast iteration: rebuild ONE part, cache the rest.

A full assembly build is minutes, and almost all of it is geometry you are not
touching. This caches the surroundings as BREP and rebuilds only the part under
work, so the inner loop is seconds. On the pedal-steel that is 12 s against a
~4 min build.

    # tools/scratch_view.py in the project
    from cadkit.scratch import ScratchView, main

    VIEW = ScratchView(
        root=pathlib.Path(__file__).resolve().parent.parent,
        context=lambda: __import__("src.build", fromlist=["e"]).collect_components(),
        live=lambda: __import__("src.leg_stack", fromlist=["e"]).assembly(),
        replaced=("leg_", "latch_"),        # context parts the live one supersedes
        crop=(400.0, 400.0, 900.0, -614.0, 43.0, -375.0),   # optional
    )
    if __name__ == "__main__":
        raise SystemExit(main(VIEW))

Gives the project a three-command loop:

    --start    BEGIN a flow: rebuild the cache from scratch, then render
    (bare)     iterate -- the LIVE part is rebuilt fresh, context comes from cache
    --merge    END a flow: DELETE the cache, then do the real build

────────────────────────────────────────────────────────────────────────────
WHY A GEOMETRY CACHE IS SAFE HERE, WHICH IS THE ONLY INTERESTING PART
────────────────────────────────────────────────────────────────────────────
A stale cache is SILENTLY wrong. A part that should have changed but did not
looks exactly like a correct build, and you then design against a lie. That is
a worse failure than a slow build, and CAD projects accumulate it easily —
constants read across module boundaries mean "did this part change?" is not a
question a file timestamp can answer.

The tempting fix is to invalidate on a hash of the import closure. Don't. It
LOOKS rigorous, and then misses the one edge that matters (a constant reached
through two modules, a value read at import time) and fails silently when it
does — the exact failure mode you were trying to prevent.

THE LIFECYCLE IS THE INVALIDATION STRATEGY instead (user's call, 2026-08-07):
rebuild on --start, delete on --merge, so a cache never outlives one sitting.
Staleness is bounded by the length of a session rather than by the correctness
of a dependency graph, and that needs no cleverness to be right.

Three rules follow, and they are enforced here rather than left to discipline:

  * THE PART UNDER WORK IS NEVER CACHED. Only the surroundings are.
  * NO CACHE, NO RENDER. A bare run without one is an error telling you to
    --start, not a silent auto-build that begins a flow nobody declared.
  * IT SAYS SO, LOUDLY, every run, with the cache's age. A silent cache is the
    dangerous kind.

And the boundary that makes the whole thing acceptable: THE CACHE IS FOR THE
VIEW ONLY. The canonical build and the overlap gate must never read it, so a
drift costs a surprise at merge — which is exactly when you are looking for
surprises — instead of a wrong part.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import time

__all__ = ["ScratchView", "main"]


class ScratchView:
    """Config for a project's scratch loop. See the module docstring."""

    def __init__(self, root, context, live, replaced=(), crop=None,
                 out="assembly.step", cache_dir=".scratch_cache",
                 live_color=(0.85, 0.45, 0.20), context_color=(0.32, 0.36, 0.40),
                 pose=None):
        self.root = pathlib.Path(root)
        self.context = context          # () -> iterable of (name, Workplane)
        self.live = live                # () -> iterable of (name, Workplane)
        self.replaced = tuple(replaced)
        self.crop = crop                # (w, d, h, x, y, z) or None
        self.out = self.root / out
        self.cache = self.root / cache_dir
        self.live_color = live_color
        self.context_color = context_color
        self.pose = pose                # optional (name, wp) -> wp for the live set

    # ── cache ───────────────────────────────────────────────────────────────
    def _crop_solid(self):
        if not self.crop:
            return None
        import cadquery as cq
        w, d, h, x, y, z = self.crop
        return (cq.Workplane("XY").box(w, d, h).translate((x, y, z)))

    def build_cache(self):
        """Run the heavy build ONCE and write the surroundings as BREP."""
        crop = self._crop_solid()
        self.cache.mkdir(parents=True, exist_ok=True)
        kept = skipped = 0
        t0 = time.time()
        for name, wp in self.context():
            if name.startswith(self.replaced):
                skipped += 1
                continue
            try:
                shape = wp.intersect(crop) if crop is not None else wp
                if not shape.solids().vals():
                    continue
                shape.val().exportBrep(str(self.cache / (name + ".brep")))
                kept += 1
            except Exception:
                skipped += 1        # compounds that will not serialise; not fatal
        (self.cache / "STAMP").write_text(str(time.time()))
        print("cached %d context solids in %.0fs (%d skipped/replaced)"
              % (kept, time.time() - t0, skipped))

    def load_cache(self):
        import cadquery as cq
        stamp = self.cache / "STAMP"
        if not stamp.exists():
            return None
        age = time.time() - float(stamp.read_text())
        out = [(f.stem, cq.Workplane("XY").add(cq.Shape.importBrep(str(f))))
               for f in sorted(self.cache.glob("*.brep"))]
        return age, out

    # ── render ──────────────────────────────────────────────────────────────
    def render(self):
        import cadquery as cq
        age, ctx = self.load_cache()
        # LOUD, every run: the whole risk of a geometry cache is not knowing you
        # are on one. The age is what tells you whether to --start again.
        print("=" * 70)
        print(" SCRATCH VIEW -- the live part is FRESH; %d context solids CACHED"
              % len(ctx))
        print(" cache age: %.0f min   (--start to re-cache | --merge to end)"
              % (age / 60.0))
        print("=" * 70)

        asm = cq.Assembly()
        for name, wp in self.live():
            asm.add(self.pose(name, wp) if self.pose else wp,
                    name=name, color=cq.Color(*self.live_color))
        for name, wp in ctx:
            asm.add(wp, name="cached_" + name,
                    color=cq.Color(*self.context_color))
        asm.save(str(self.out), exportType="STEP")
        print("wrote %s (%.0f KB)" % (self.out.name,
                                      self.out.stat().st_size / 1024))
        try:
            from cadkit.freecad import show
            show(str(self.out))
        except Exception as exc:                      # never break the loop
            print("[scratch] viewer skipped: %s" % exc)


def main(view: ScratchView, argv=None) -> int:
    ap = argparse.ArgumentParser(description="cadkit scratch view")
    ap.add_argument("--start", action="store_true",
                    help="BEGIN a flow: rebuild the cache from scratch, then render")
    ap.add_argument("--merge", action="store_true",
                    help="END a flow: delete the cache, then do the real build")
    a = ap.parse_args(argv)

    if a.merge:
        shutil.rmtree(view.cache, ignore_errors=True)
        print("cache DELETED -- now merge back with the project's REAL build,")
        print("and gate it. Anything the scratch loop hid shows up there.")
        return 0
    if a.start:
        shutil.rmtree(view.cache, ignore_errors=True)
        view.build_cache()
    elif not (view.cache / "STAMP").exists():
        print("no cache -- begin a flow with:  --start")
        return 1
    view.render()
    return 0
