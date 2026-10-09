# -*- coding: utf-8 -*-
"""cadkit.scratch — fast iteration: rebuild ONE part, take the rest as already built.

A full assembly build is minutes, and almost all of it is geometry you are not
touching. So the build that has to happen anyway -- the LEAD's, on every merge --
leaves every component behind as a BREP file, in one place every worktree can read,
and a contributor's loop builds only the part under work:

    yours, fresh        the LIVE set: what your scope names, rebuilt every run
    yours, kept         parts you built earlier in this sitting (your OWN cache)
    everything else     the lead's last build (the SHARED cache)

    # tools/scratch_view.py in the project
    from cadkit.scratch import ScratchView, main

    VIEW = ScratchView(
        root=pathlib.Path(__file__).resolve().parent.parent,
        context=lambda: __import__("src.build", fromlist=["e"]).collect_components(),
        live=lambda: __import__("src.leg_stack", fromlist=["e"]).assembly(),
        replaced=("leg_", "latch_"),        # shared parts the live one supersedes
        colors=lambda n: __import__("src.build", fromlist=["e"])._color_for(n),
    )
    if __name__ == "__main__":
        raise SystemExit(main(VIEW))

    # and once, at the end of the project's full build
    from cadkit.scratch import publish_cache
    publish_cache(components, root, build=build_number)

The loop:

    (bare)         your part FRESH, the rest as above; the viewer page reloads itself
    --cache-only   build nothing: the page alone, in seconds
    --gate         the project's own gates over the same model (the scoped gate; the
                   FULL gate runs in the lead's build)
    --own          build EVERYTHING here, into your own cache (minutes): for a change
                   that moves what other parts read, or when there is no shared cache
    --lead         forget your own cache: back to the lead's build for all but the
                   live part (after your work is merged, or to drop an experiment)

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

So nothing here decides for you that a part is unchanged. WHAT IS REBUILT IS WHAT
YOU SAID: the live set, every run. What you built before stays as you built it until
you rebuild it or say `--lead`. Everything else is the lead's build, whole, and it is
replaced whole by the lead's next one. Each of the three is exactly what it claims to
be, and every run says which is which, with the build number and its age.

Rules that follow, enforced here rather than left to discipline:

  * THE PART UNDER WORK IS REBUILT, never read back, unless you ask (--cache-only).
  * A PART YOU HAVE BUILT WINS over the lead's copy of it, by name: move on to a
    second part and the first stays as you left it, not as main has it.
  * NOTHING TO SHOW, NO RENDER. With no shared cache and none of your own, a run is
    an error telling you how to get one, not a silent full build.
  * IT SAYS SO, LOUDLY, every run. A silent cache is the dangerous kind.

And the boundary that makes the whole thing acceptable: THE CACHES ARE FOR THE VIEW
AND THE SCOPED GATE ONLY. The canonical build and its gates never read them, so a
drift costs a surprise at merge — which is exactly when you are looking for
surprises — instead of a wrong part. The scoped gate is a way to notice a mistake
sooner, never a way to certify anything: if your change moved something you did not
rebuild, it cannot see that. Widen the live set, or `--own`.

A scratch render goes to the worktree's `.webview/` folder (cadkit.web), never to
where the real build publishes. The page says which it is showing.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import pathlib
import shutil
import time

__all__ = ["ScratchView", "main", "publish_cache", "shared_cache", "read_brep"]

MANIFEST = "MANIFEST.json"      # the shared cache: which build, when, and each part's hash
OWN = "OWN.json"                # an own cache: which shared parts it supersedes by prefix


def shared_cache(root) -> pathlib.Path:
    """Where the lead's build leaves its components: under the repository's COMMON
    git folder, so every worktree reads the same one and none can commit it."""
    from cadkit.agents import scopes_path
    p = scopes_path(cwd=str(root))
    if p is None:                       # not a git repository: one folder, one cache
        return pathlib.Path(root) / ".scratch_cache" / "shared"
    return p.parent / "cache"


def _git(root, *args) -> str:
    import subprocess
    try:
        r = subprocess.run(["git", *args], text=True, capture_output=True, cwd=str(root))
        return r.stdout.strip() if r.returncode == 0 else ""
    except OSError:
        return ""


def _shape(wp):
    """The solid to keep of a component, or None if it has neither solids nor faces
    (a part of bare FACES is a part too: board lettering, cadkit.board_geom)."""
    shape = wp.val() if hasattr(wp, "val") else wp
    try:
        if not (shape.Solids() or shape.Faces()):
            return None
    except Exception:
        return None
    return shape


def _brep(shape) -> bytes:
    buf = io.BytesIO()
    shape.exportBrep(buf)
    return buf.getvalue()


def _put(path: pathlib.Path, data: bytes):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    for attempt in range(40):           # a reader sees the old file or the new, never half
        try:
            return os.replace(tmp, path)
        except PermissionError:         # Windows: someone is reading the old one right now
            if attempt == 39:
                raise
            time.sleep(0.05)


def read_brep(path):
    """The solid in a cache file. The file is read WHOLE, then parsed: a build
    replacing it meanwhile cannot hand over half of one, and on Windows the instant of
    the replace (when the name cannot be opened) is waited out rather than failed on."""
    import cadquery as cq
    for attempt in range(40):
        try:
            data = pathlib.Path(path).read_bytes()
            break
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.05)
    return cq.Shape.importBrep(io.BytesIO(data))


def _write_parts(comps, out: pathlib.Path, known=None):
    """Write each component's BREP into `out`. A part whose bytes are what `known`
    ({name: sha1}) already has is LEFT ALONE, so its file keeps its time and whatever
    was derived from that file (a mesh) stays good. Returns ({name: sha1}, written)."""
    out.mkdir(parents=True, exist_ok=True)
    known = known or {}
    parts, wrote = {}, 0
    for name, wp in comps:
        shape = _shape(wp)
        if shape is None:
            continue
        try:
            data = _brep(shape)
        except Exception:
            continue                    # a compound that will not serialise; not fatal
        h = hashlib.sha1(data).hexdigest()
        parts[name] = h
        f = out / (name + ".brep")
        if known.get(name) != h or not f.exists():
            _put(f, data)
            wrote += 1
    return parts, wrote


def publish_cache(comps, root, build=None, cache=None, log=print):
    """THE FULL BUILD's last word: leave every component it just built where the
    scratch loop of every worktree will find it. `comps` is [(name, Workplane/Shape)],
    untouched. Only the lead's build publishes -- a contributor's worktree running the
    full build must not replace what everyone else is looking at -- unless `cache`
    names a folder outright. Never raises; returns the folder, or None if skipped."""
    try:
        if cache is None:
            from cadkit.agents import current_agent, LEAD
            if current_agent(cwd=str(root)) != LEAD:
                log("shared cache: not the lead's build -> not published")
                return None
            cache = shared_cache(root)
        cache = pathlib.Path(cache)
        t0 = time.time()
        try:
            known = json.loads((cache / MANIFEST).read_text())["parts"]
        except Exception:
            known = {}
        parts, wrote = _write_parts(comps, cache, known)
        gone = [f for f in cache.glob("*.brep") if f.stem not in parts]
        for f in gone:
            f.unlink()
        # THE MANIFEST LAST: until it lands, a reader has the previous build's word for
        # what the folder holds, and every file in it is whole (see _put).
        _put(cache / MANIFEST, json.dumps(
            {"t": time.time(), "build": build, "commit": _git(root, "rev-parse", "HEAD"),
             "parts": parts}).encode())
        log("shared cache: %d parts for every worktree's scratch view (%d changed, %d gone) "
            "in %.0f s" % (len(parts), wrote, len(gone), time.time() - t0))
        return cache
    except Exception as exc:
        log("shared cache: not published (%s: %s)" % (type(exc).__name__, exc))
        return None


class ScratchView:
    """Config for a project's scratch loop. See the module docstring."""

    def __init__(self, root, context, live, replaced=(), cache_dir=".scratch_cache",
                 pose=None, colors=None, gates=(), web=None, shared=None, crop=None):
        self.root = pathlib.Path(root)
        self.context = context          # () -> iterable of (name, Workplane): EVERYTHING
        self.live = live                # () -> iterable of (name, Workplane): yours
        self.replaced = tuple(replaced)
        self.cache = self.root / cache_dir                      # your own
        self.shared = pathlib.Path(shared) if shared else shared_cache(self.root)
        self.pose = pose                # optional (name, wp) -> wp for the live set
        # what the page needs beyond the parts, as keywords for cadkit.web.scratch_export:
        # rig= (writes the animation rig), boards=, materials=, extras= (title ...)
        self.web = dict(web or {})
        # `colors` is the project's own resolver, name -> cq.Color; pass the SAME one
        # the full build uses and every part looks in here exactly as it will in the
        # finished assembly. The page remembers a colour per part name between runs.
        self.colors = colors
        self.gates = tuple(gates)       # optional ((label, fn(comps) -> int), ...)
        self._live_memo = None          # the live set is built ONCE per run

    # ── the live set ────────────────────────────────────────────────────────
    def live_parts(self):
        """The live set as it stands in the model (posed), built once per run.

        Its NAMES are load-bearing: a cached part that shares a name with a live part
        IS THE SAME PART, and is never drawn beside it. `replaced` is for the other
        case, a live part that supersedes parts under DIFFERENT names -- a per-agent
        list of prefixes kept by hand, which is why name identity does not rely on it.
        """
        if self._live_memo is None:
            t0 = time.time()
            parts = list(self.live())
            if self.pose:
                parts = [(n, self.pose(n, w)) for n, w in parts]
            self._live_memo = parts
            # SAY WHAT THE SCOPE COSTS: this is the whole price of an iteration, and it
            # is mostly whatever the scope's module IMPORTS, not the part itself
            print("live set: %d part(s) imported and built in %.0f s" % (len(parts), time.time() - t0))
        return self._live_memo

    # ── your own cache ──────────────────────────────────────────────────────
    def _own(self) -> dict:
        try:
            return json.loads((self.cache / OWN).read_text())
        except Exception:
            return {"hidden": []}

    def keep(self, parts):
        """Remember parts as just built: they stand in for the lead's copies, and for
        whatever `replaced` says they supersede, until rebuilt or `--lead`."""
        own = self._own()
        known = own.get("parts", {})
        fresh, _ = _write_parts(parts, self.cache, known)
        own["parts"] = dict(known, **fresh)
        own["hidden"] = sorted(set(own.get("hidden", [])) | set(self.replaced))
        own.setdefault("since", time.time())
        _put(self.cache / OWN, json.dumps(own).encode())

    def build_own(self):
        """Build EVERYTHING here and keep it: the whole model as this worktree has it."""
        t0 = time.time()
        shutil.rmtree(self.cache, ignore_errors=True)
        self.keep([(n, w) for n, w in self.context() if not n.startswith(self.replaced)])
        print("own cache: %d parts built here in %.0f s"
              % (len(self._own().get("parts", {})), time.time() - t0))

    def forget_own(self):
        shutil.rmtree(self.cache, ignore_errors=True)

    # ── what the model is made of, this run ─────────────────────────────────
    def manifest(self) -> dict:
        try:
            return json.loads((self.shared / MANIFEST).read_text())
        except Exception:
            return {}

    def files(self, superseded=()) -> dict:
        """{part name: BREP file} of the whole model: the lead's build, less what you
        have superseded, under what you have built yourself. A scope's `replaced` hides
        the lead's parts only once the part that replaces them HAS been built here
        (keep() records it); `superseded` adds prefixes for a live set not kept."""
        hidden = tuple(set(self._own().get("hidden", [])) | set(superseded))
        out = {}
        if self.manifest():
            for f in sorted(self.shared.glob("*.brep")):
                if not (hidden and f.stem.startswith(hidden)):
                    out[f.stem] = f
        for f in sorted(self.cache.glob("*.brep")):
            out[f.stem] = f
        return out

    def describe(self, live_names=()) -> dict:
        """What a run is showing, for the banner and the page."""
        man, own = self.manifest(), self._own()
        mine = set(own.get("parts", {})) - set(live_names)
        return {"live": sorted(live_names), "own": len(mine), "own_names": sorted(mine),
                "build": man.get("build"), "drift": self._drift(man.get("commit")),
                "cache_age_min": round((time.time() - man["t"]) / 60.0, 1) if man else None}

    def _drift(self, commit) -> str:
        """'' if this worktree's code is the tree the lead built, apart from its own
        commits; else one line saying how they differ. The rest of the model was built
        from THAT tree, so a part there that this branch's code would build differently
        is being shown (and gated) as the lead has it."""
        if not commit:
            return ""
        head = _git(self.root, "rev-parse", "HEAD")
        base = _git(self.root, "merge-base", "HEAD", commit)
        if not head or not base:
            return "the lead built %s, which this worktree cannot find" % commit[:8]
        if base == commit:
            return ""                   # the lead's tree, plus this branch's own work
        behind = _git(self.root, "rev-list", "--count", "%s..%s" % (base, commit)) or "?"
        return ("the lead built %s; this branch leaves main at %s, %s commit(s) EARLIER -- "
                "`sync`, or the rest is newer than your code" % (commit[:8], base[:8], behind))

    def _banner(self, title, d):
        print("=" * 70)
        print(" %s" % title)
        if d["live"]:
            print("   FRESH        %d part(s): %s%s" % (len(d["live"]), ", ".join(d["live"][:5]),
                                                       " ..." if len(d["live"]) > 5 else ""))
        if d["own"]:
            print("   KEPT, yours  %d part(s) as you last built them (--lead to drop): %s%s"
                  % (d["own"], ", ".join(d["own_names"][:5]), " ..." if d["own"] > 5 else ""))
        if d["cache_age_min"] is not None:
            print("   THE REST     the lead's build%s, %.0f min old"
                  % (" #%s" % d["build"] if d["build"] is not None else "", d["cache_age_min"]))
        else:
            print("   THE REST     nothing: no shared cache (the lead's next build writes it)")
        if d.get("drift"):
            print(" !! NOT THE SAME TREE: %s" % d["drift"])
        print("=" * 70)

    def _nothing(self) -> bool:
        if self.files():
            return False
        print("nothing to show: the lead's build has not left a shared cache yet, and this\n"
              "worktree has none of its own. Either wait for the lead's next build, or\n"
              "build the whole model here (minutes):  --own")
        return True

    # ── inner-loop gate ─────────────────────────────────────────────────────
    def check(self) -> int:
        """Run the project's gates over the scratch model: the live part FRESH and
        posed exactly as the view draws it, the rest from the caches.

        This is the contributor's SCOPED check, not the full gate. The gates are the
        project's own, unchanged; what this saves is the minutes a full gate spends
        REBUILDING geometry it is not going to look at. Nothing authoritative reads a
        cache: a drift shows up as a surprise in the lead's build, which runs the FULL
        gates on the merged tree. It says so on every invocation."""
        if not self.gates:
            print("no gates registered — pass gates=((label, fn), ...) to ScratchView")
            return 0
        if self._nothing():
            return 1
        live = self.live_parts()
        mine = {n for n, _ in live}
        rest = [(n, read_brep(f))
                for n, f in self.files(self.replaced).items() if n not in mine]
        comps = [(n, wp.val()) for n, wp in live] + rest
        self._banner("INNER-LOOP GATE -- scoped", self.describe(mine))
        print(" Every pair of the whole model is scanned: FRESH against everything, and the")
        print(" rest among themselves (those pairs are remembered, so they cost nothing).")
        print(" A part you KEPT is gated as YOU built it, not as the lead has it. What it")
        print(" cannot see: something your change moved that you did not rebuild -- widen")
        print(" the live set (or --own). The FULL gates run in the lead's build on merge;")
        print(" do not run them yourself before `submit`.")
        bad = 0
        for label, fn in self.gates:
            print()
            print("--- %s ---" % label)
            try:
                bad += fn(comps)
            except Exception as exc:                  # a gate crash must not end the loop
                # ...BUT IT IS NOT A PASS: a gate that could not run must not exit 0,
                # indistinguishable from one that ran and found nothing.
                print("[scratch] %s DID NOT RUN (counted as a FAILURE): %r" % (label, exc))
                bad += 1
        return 1 if bad else 0

    # ── render ──────────────────────────────────────────────────────────────
    def render(self, live=True, rig=False):
        """The page (cadkit.web). An open page reloads itself. live=False builds
        nothing; rig=True rewrites the animation rig as well."""
        from cadkit.web import scratch_show
        mine = []
        if live:
            parts = self.live_parts()
            self.keep(parts)
            mine = [n for n, _ in parts]
        if self._nothing():
            return 1
        d = self.describe(mine)
        self._banner("SCRATCH VIEW", d)
        scratch_show(self, describe=d, refresh_rig=rig, **self.web)
        return 0


def main(view: ScratchView, argv=None) -> int:
    ap = argparse.ArgumentParser(description="cadkit scratch view")
    ap.add_argument("--cache-only", action="store_true",
                    help="build nothing: show the model as it was last built")
    ap.add_argument("--rig", action="store_true",
                    help="rewrite the page's animation rig as well")
    ap.add_argument("--gate", action="store_true",
                    help="run the project's gates over the scratch model (seconds) -- "
                         "the scoped gate; the FULL gate runs in the lead's build")
    ap.add_argument("--own", action="store_true",
                    help="build EVERYTHING here into your own cache (minutes), then render")
    ap.add_argument("--lead", action="store_true",
                    help="forget your own cache: the lead's build for all but the live part")
    a = ap.parse_args(argv)

    if a.lead:
        view.forget_own()
        print("own cache DELETED -- everything but the live part is the lead's build again")
    if a.own:
        view.build_own()
    if a.gate:
        return view.check()
    return view.render(live=not a.cache_only, rig=a.rig)
