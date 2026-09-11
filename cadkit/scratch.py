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
        colors=lambda n: __import__("src.build", fromlist=["e"])._color_for(n),
        crop=(400.0, 400.0, 900.0, -614.0, 43.0, -375.0),   # optional
    )
    if __name__ == "__main__":
        raise SystemExit(main(VIEW))

Gives the project a four-command loop:

    --start    BEGIN a flow: rebuild the cache from scratch, then render
    (bare)     iterate -- the LIVE part is rebuilt fresh, context comes from cache
    --gate     run the project's own gates over that cache (~30 s vs ~6 min) --
               the contributor's gate; the FULL gate runs in the lead's build
    --merge    END a flow: DELETE the cache, then do the real build

Register gates as `gates=(("label", fn(comps) -> int), ...)`; they receive
[(name, cq.Shape)] exactly as the real gates do, so the project passes the SAME
functions rather than a second implementation that could disagree.

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

`--gate` lives inside that boundary rather than breaking it. The gates it runs are
the project's own, unchanged, and still rebuild everything when invoked normally --
what changes is only that this hands them the cache. So the AUTHORITATIVE run is
still cache-free, a cropped cache is loudly declared as unable to see what it did
not load, and the fast check is a way to notice a mistake sooner, never a way to
certify anything. The reason scoping had to work this way: `--only <names>` scopes
what gets CHECKED, and the model build is ~95% of a gate's cost, so name-scoping
saves almost nothing. What has to be scoped is what gets BUILT.

That boundary is also why the default output is `scratch.step` and NOT
`assembly.step`. Writing the canonical name would let a scratch render overwrite
the real build's output — a file the viewer, the gate tooling and the human all
treat as the finished model. The two must be distinguishable on disk, not just by
who remembers which command they last ran.
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
                 out="scratch.step", cache_dir=".scratch_cache",
                 live_color=(0.85, 0.45, 0.20), context_color=(0.32, 0.36, 0.40),
                 pose=None, colors=None, gates=()):
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
        # THE LIVE SET WEARS ITS REAL COLOURS BY DEFAULT (user). `colors` is the
        # project's own resolver, name -> cq.Color; pass the SAME one the full build
        # uses and the part under work looks in here exactly as it will in the finished
        # assembly. Without it the live set is one flat highlight colour, which reads
        # every part as the same material and hides which piece is which. The CONTEXT
        # stays deliberately grey -- that is what distinguishes cached from live.
        self.colors = colors            # optional (name) -> cq.Color for the live set
        self.gates = tuple(gates)       # optional ((label, fn(comps) -> int), ...)

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
        """Load the cached surroundings, re-applying `replaced` ON THE WAY IN.

        Filtering only at build_cache() time was a silent-staleness bug, and of
        exactly the kind this module exists to prevent. `replaced` is the set the
        live part SUPERSEDES, and it lives in per-agent state that changes mid-flow:
        grow your scope to cover another part and its cached copy is already on
        disk, so the render served BOTH -- the fresh live one and the superseded
        grey one, interpenetrating, with the stale copy drawn on top. It reads as
        "my part did not render". The cache does not need rebuilding for this; the
        filter just has to run on both ends.
        """
        import cadquery as cq
        stamp = self.cache / "STAMP"
        if not stamp.exists():
            return None
        age = time.time() - float(stamp.read_text())
        files = [f for f in sorted(self.cache.glob("*.brep"))
                 if not f.stem.startswith(self.replaced)]
        out = [(f.stem, cq.Workplane("XY").add(cq.Shape.importBrep(str(f))))
               for f in files]
        return age, out

    # ── inner-loop gate ─────────────────────────────────────────────────────
    def check(self) -> int:
        """Run the project's gates over CACHED context + the FRESH live part.

        This is the contributor's SCOPED check, not the full gate, and the distinction
        is the whole point. The gates themselves are unchanged and still rebuild the model
        from scratch when run normally -- what this does is hand them the same
        cache the view uses, so an agent can ask "did I just break something?" in
        seconds instead of the ~5.5 min a full gate spends REBUILDING geometry it is
        not going to look at. Scoping a gate by name (--only) never helped, because
        the build is ~95% of its cost, not the checking.

        The cache boundary still holds: nothing authoritative reads it. A drift shows
        up as a surprise in the lead's build, which runs the FULL gates on the merged
        tree -- contributors do not run them before `submit` (user, 2026-09-11) -- rather
        than as a wrong part. It says so on every invocation."""
        if not self.gates:
            print("no gates registered — pass gates=((label, fn), ...) to ScratchView")
            return 0
        loaded = self.load_cache()
        if loaded is None:
            print("no cache -- begin a flow with:  --start")
            return 1
        age, ctx = loaded
        comps = ([(n, (self.pose(n, wp) if self.pose else wp).val())
                  # POSED, exactly as render() draws them. This used to hand the
                  # gates the RAW live parts, so any scope with a pose was gated
                  # wherever its module happened to author it -- the redesigned
                  # leg was checked floating clear of the instrument for weeks and
                  # reported clean while overlapping four TRRS parts in place.
                  for n, wp in self.live()]
                 + [(n, wp.val()) for n, wp in ctx])
        print("=" * 70)
        print(" INNER-LOOP GATE -- live part FRESH, %d context solids CACHED (%.0f min old)"
              % (len(ctx), age / 60.0))
        print(" SCOPED: context is cached and may be CROPPED, so it can only find")
        print(" faults involving what is loaded -- widen the live set if your change")
        print(" moved anything else. The FULL gates run in the lead's build on merge;")
        print(" do not run them yourself before `submit`.")
        print("=" * 70)
        bad = 0
        for label, fn in self.gates:
            print()
            print("--- %s ---" % label)
            try:
                bad += fn(comps)
            except Exception as exc:                  # a gate crash must not end the loop
                print("[scratch] %s skipped: %s" % (label, exc))
        return 1 if bad else 0

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
            col = None
            if self.colors is not None:
                try:
                    col = self.colors(name)
                except Exception:
                    col = None          # an unknown part falls back, never crashes
            asm.add(self.pose(name, wp) if self.pose else wp,
                    name=name, color=col or cq.Color(*self.live_color))
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
    ap.add_argument("--gate", action="store_true",
                    help="run the project's gates over cached context + your fresh "
                         "part (seconds) -- the scoped gate; the FULL gate runs in "
                         "the lead's build")
    a = ap.parse_args(argv)

    if a.gate:
        return view.check()
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
