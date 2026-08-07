# cadkit — CAD & 3D-printing conventions

`cadkit` is a small, project-agnostic CadQuery / 3D-printing toolkit, **vendored into
each project** at `<project>/cadkit` via `git subtree` (canonical upstream
github.com/gustebeast/cadkit). This file travels with it — **read it before doing
CAD / 3D-printing work in any project that vendors cadkit.** For a NEW project, install
the `parametric-3d-printing` skill and copy a reference project (`retractable-cable-spool/`
is canonical).

Commands below use **`py -3.12`** (Windows). On macOS/Linux use **`python3.12`** — the
module paths and everything else are identical.

## Skills & shared code
Two layers of reusable capability back a cadkit project:

- **The `parametric-3d-printing` skill** lives in the Claude **skills folder**
  (`~/.claude/skills/`). Skills are self-contained playbooks Claude Code loads on
  demand; this one is the general CadQuery-for-3D-printing workflow (requirements
  gathering, real-world dimension research, print-friendly rules, tolerances,
  supports). It's the "CAD skill" / "cad-skill" the notes here refer to, and it
  auto-loads when a task looks like designing a printable part. **A cadkit project
  OVERRIDES two of its defaults:** export **STEP, not STL** (no preview PNGs — see STEP
  conventions below), and preview in the shared **FreeCAD viewer hub**, not the
  skill's headless renderer. Use the skill for *method*; use this file + `cadkit`
  for *how we actually build and view*.
- **`cadkit` — shared, project-agnostic utilities**, vendored at `<project>/cadkit`
  (git subtree; canonical upstream github.com/gustebeast/cadkit). Imported as
  `cadkit.*` — NO sys.path hack, because every build runs via `-m` from the project
  root, so the vendored package is already importable:
  - `cadkit.step_export` — `export_step()` (names the STEP product after the file stem)
  - `cadkit.overlap_check` — the parallel interpenetration engine (see the overlap gate)
  - `cadkit.threads` — **self-supporting 45° screw threads**; read **`cadkit/THREADS_README.md`**
    before changing any thread (OCCT fails *silently* in ~7 documented ways — a smooth
    or half-filled rod, 0 solids, or a multi-minute hang). Three public cutters, and you
    **CALL them, never re-model a thread**: `threaded_rod` (short internal/nut threads),
    `cut_thread` (long screw from a smooth blank), and `teardrop_thread_cutter` (a
    **SIDEWAYS/horizontal-axis female thread** — full round bore + a self-supporting
    hexagon peak on the +Y print-up side; print-tested clean, Ø6 in PETG)
  - `cadkit.joinery` — **printable mortise-and-tenon slide joints** (dull arrowhead);
    read **`cadkit/JOINERY_README.md`** first. THE recipe for a tenon printed SIDEWAYS
    (+Y build) mating a mortise printed flat (−Z→+Z) is `ramp=True, hook_h=…`
    (print-validated); plain 45°-everywhere profiles cam apart along the up-ramp
    diagonal — don't reinvent this joint, call the library.
  - `cadkit.fasteners` — shared M2/M4 hole/insert dims · `cadkit.cq_colors` — baked STEP colours
  - `cadkit.freecad` — the FreeCAD viewer hub (`from cadkit.freecad import show`) + `view_assembly.cmd` launcher
  - `cadkit/tools/agent_sync.py` — the multi-agent worktree/merge CLI (run as a script)

  **Changing a shared util — edit the canonical repo, then PROPAGATE.** cadkit is
  vendored (copied) into each project, so the copies DRIFT the moment canonical
  changes. A cadkit change is not done when you commit it — it is done when every
  consumer has been re-pulled. So: edit the **canonical** repo (the `../cadkit`
  sibling, upstream github.com/gustebeast/cadkit), commit there, then run the one
  command that does the whole fan-out:
  `py -3.12 ../cadkit/tools/propagate.py` — it pushes canonical to the upstream and
  re-pulls the subtree into every sibling project that vendors cadkit (dirty repos
  are skipped and reported; exit code = consumers not in sync, so 0 = all current;
  `--dry-run` previews). **Never hand-edit a project's vendored `cadkit/`** and
  never rely on remembering to `subtree pull` each repo by hand — that forgotten
  step IS the drift. (Read `cadkit/README.md` → "Changing cadkit" for the details.)

## The build loop
Build with `py -3.12 -m src.build` from the project folder. That writes the STEP
files **and** opens/refreshes the model in the shared FreeCAD viewer hub via
`show()` — no separate launch step, no Onshape.

**Write outputs relative to the build script, never to the cwd.** Anchor every
output path (and the `show()` path) to `OUT = pathlib.Path(__file__).resolve().parent`,
e.g. `export_step(obj, str(OUT / "housing.step"))`, `show(str(OUT / "assembly.step"))`.
A bare `"housing.step"` writes to wherever the build was *launched* from — which
scatters files into a parent dir when a package is run as `-m pkg.build`, or into
the build counter's folder. `__file__`-anchored paths land in the project folder
no matter the cwd.

## FreeCAD viewer hub
`from cadkit.freecad import show` opens/refreshes the project's assembly in a shared
FreeCAD hub window (each part coloured + individually show/hide-able; the tab
auto-reloads on every rebuild). `show()` never raises — viewer trouble can't break a
build.

**FreeCAD is located automatically — no hardcoded path.** `cadkit.freecad` resolves the
executable in this order: `freecad_exe=` arg → `FREECAD_EXE` env → a cached config file
(`%APPDATA%\cadkit\freecad.path` on Windows, `~/.config/cadkit/freecad.path` elsewhere)
→ auto-discovery of the usual install locations (Windows `Program Files\FreeCAD*`, macOS
`FreeCAD.app`, Linux AppImage / `PATH`), which is **cached on first success**. So on a
fresh machine the first `show()` just finds FreeCAD and remembers it. If FreeCAD isn't
installed, `show()` prints a link to download it and how to pin the path —
`py -m cadkit.freecad --set-path "<exe>"` (or set `FREECAD_EXE`) — and skips the viewer.
The config file is machine-local and outside every repo, so it never gets committed.

**Double-click launcher.** Every project ships a `View Assembly.cmd` in its root so the
user can open the last-built model straight from Explorer — no rebuild, no build-counter
bump, just whatever STEP is on disk. The logic lives in the vendored
`cadkit/freecad/view_assembly.cmd`; each project's root `View Assembly.cmd` is a one-line
forwarder (it must physically sit in the root — it's the double-click target — but
carries no logic):

```bat
@echo off
REM Double-click to open this project's assembly.step in the FreeCAD viewer hub.
REM All logic lives in the vendored launcher (cadkit subtree); this forwards our folder.
call "%~dp0cadkit\freecad\view_assembly.cmd" "%~dp0"
```

(The `.cmd` launcher is Windows-only; on macOS/Linux run `py -3.12 -m cadkit.freecad`
from the project folder instead.)

## STEP file conventions
- **Export STEP, never STL.** This workflow is STEP-only: the FreeCAD viewer and
  the slicer both consume STEP, and STEP keeps the named, separable, coloured
  structure that STL discards. Use `export_step(obj, "name.step")` for a part
  (see naming bullet) and `asm.save("assembly.step", mode="default")` for the
  assembly. **Do not write `.stl`** (no `.stl` outputs, no STL previews). ⚠️ The
  `cad-skill` emits STL + preview PNGs by default — override it and produce
  `.step` instead.
- **One STEP per printed part** (`housing.step`, `axle.step`, …) — one printable
  solid each; the slicer imports these.
- **Name every product to match its filename.** A bare
  `cq.exporters.export(part, "housing.step")` names the STEP product *"Open
  CASCADE STEP translator 7.8 …"*, which is what Bambu/FreeCAD then display. Use
  the shared exporter instead — it exports normally, then rewrites the product
  name to the file stem (a single, correctly named product):
  ```python
  from cadkit.step_export import export_step
  export_step(part, "housing.step")          # imports/slices as "housing"
  ```
  (For `assembly.step`, the per-part `name=` on each `.add(...)` already does this.)
- **Dummy / purchased parts get NO standalone STEP** (springs, bearings, screws,
  switch bodies, motors) — they appear ONLY inside the assembly, for fit-checks.
- **One `assembly.step`** — every part placed as-built, kept SEPARATE and
  coloured (`cq.Assembly().add(part, name=…, color=…)`, exported un-fused). This
  is the file the viewer opens; each `name=` is a toggleable, coloured entry.

## Test parts / print-fit coupons
Sometimes you want a small COUPON to test-print a tricky feature (a thread fit, a
snap joint) without printing the whole part. Two rules keep coupons honest and
zero-maintenance:

- **SHARE CODE with the real part — never re-model the feature for the coupon.** Factor
  the feature's geometry into ONE function (e.g. `cut_cap_socket(solid)` in a shared
  module) and have BOTH the real part and the coupon call it. A hand-retyped copy drifts
  silently — you tune the coupon, the real part doesn't change, and the test stops being
  representative. The coupon should be *the real geometry*, just re-oriented for printing
  (match the real part's PRINT ORIENTATION — that's usually the whole point of the test).
- **Name every test part `test_*.step` and export it to the PROJECT ROOT, next to the
  regular part STEPs** (`test_nut.step`, `test_joint_tenon.step`, `test_cap_socket.step`).
  The `test` prefix is what separates coupons from shippable parts in the folder
  listing, and the slicer finds them in the same place as everything else. Never
  ship a coupon STEP under any other name, and never scatter them into `tools/`
  or scratch dirs.
- **RENDER coupons IN the assembly too, off to the side** (`.add(coupon.translate((90,0,0)),
  name="…_coupon", …)`) so they're rebuilt with every `src.build`, visible in the one
  FreeCAD tab, and can't silently diverge from the model. Give them a non-TPU colour and
  a `_coupon` name so they read as test pieces, not product parts. Prefer exporting the
  `test_*.step` from `src.build` alongside the real parts (a `tools/*.py` that only
  writes its STEP when hand-run can go stale between regenerations — if such a tool
  exists for gating reasons, keep its geometry shared-code so staleness can't lie about
  the design, and rerun it after dimension changes). Once a coupon's fit is print-validated
  and the design has settled, it's fine to remove it from the build to de-clutter.

## ALWAYS announce the build number
The assembly floats a 3-D build number, bumped every full build; the build prints
`[build #N]`. **Tell the user that number every time it changes** (e.g. "Pushed
build #42.") — it's their proof a fresh model reached the viewer.

## Overlap gate (catch part collisions)
After a build, run an overlap check to confirm no parts unintentionally
interpenetrate — it catches real regressions (e.g. a wall-thickness bump driving
the I/O jacks into an endplate). The shared engine is **`cadkit.overlap_check`**
(parallel: build once, serialize shapes, hand bbox-surviving *pairs* to a worker
pool). Each project adds a thin `tools/check_overlaps.py` that supplies its parts
(`collect_components()` → `[(name, cq.Shape)]`) and an `intended(a, b)` whitelist of
designed contacts, then calls `overlap_check.run(components, intended)`:

```
py -3.12 -m tools.check_overlaps        # exit code = unintended pairs; 0 = clean
py -3.12 -m tools.check_overlaps --all  # also list the intended contacts
```

**Know what a standalone gate run actually costs.** The time the gate prints
(~13-20 s) is only the *pairwise scan*. Everything before it is
`collect_components()` — a COMPLETE model build, the same one `src.build` does.
Measured on this project: `check_overlaps` end-to-end is **5 m 51 s**, of which
13 s is checking. So gate-then-build pays for **two** full model builds.

The fix is to fold the scan into the build, which already has the components in
memory: `src/build.py` runs it at the end of `_export_assembly()` (see
`_report_overlaps`), making a whole-tree gate cost ~+15 s instead of ~+6 min, and
the build's exit code non-zero on a NEW overlap (`OVERLAP_BASELINE` holds the
accepted, separately-tracked ones). `--no-gate` / `--gate-full` override it.
`tools/check_overlaps.gate(comps, ...)` is the shared entry point both use — a
project's `main()` builds then calls it; the build calls it with what it has.
This is only safe because `overlap_check._detached_main()` stops the spawned
workers from re-importing the caller's `__main__` (which, called from the build
script, would re-run its module-level geometry in EVERY worker).

Caveats: it only finds *interpenetration* — NOT too-thin walls, too-tight
clearances, or missing/should-touch contact (use point-probes / cross-sections for
those), and a wrong whitelist entry can mask a real clash. OCCT booleans are
memory-bandwidth-bound, so it's ~2-3x with cores, not linear — treat it as a
pre-commit gate, not an inner-loop check.

## M2 / M4 holes — self-tap now, insert later
Default M2 screw holes to **Ø2.2 mm**. At that size an M2 screw self-taps and
holds directly, so the first build needs no heat-set inserts — simpler part,
simpler assembly.

Self-tapped plastic threads strip after enough insert/remove cycles, though. So
**wherever the surrounding wall has room, also sink a Ø3.3 mm × 3.5 mm heat-set-
insert pocket, concentric with the Ø2.2 hole and opening at the hole mouth**
(Ø2.2 / Ø3.3 / 3.5 = `M2_SELFTAP_D` / `M2_INSERT_PILOT_D` / `M2_INSERT_DEPTH`,
shared in `cadkit.fasteners` — never redefine per project). The part still ships
and runs on the bare Ø2.2 self-tap; the Ø2.2 continues below the pocket so the
screw bites on the first build. If those threads later strip, melt a heat-set
insert into the waiting Ø3.3 × 3.5 pocket and switch to it — no reprint, no redesign.

Rule of thumb: **Ø2.2 always; Ø3.3 × 3.5 insert pocket as a built-in fallback
wherever wall thickness allows.**

**Don't hand-roll the hole — `cadkit.fasteners` draws it.** Both the numbers
AND the geometry are shared; a project should never `makeCylinder` its own M2
bore. Cutters come in two flavours, and picking the wrong one is the easy
mistake:

- **`cut_m2_anchor(w, pnt, dir, depth)`** — the DEFAULT, and the convention
  above: Ø2.2 self-tap running `depth`, with the Ø3.3 × 3.5 pocket waiting
  concentric at its mouth. Use wherever **the screw threads into this part**. It
  raises if `depth <= M2_INSERT_DEPTH` (the pocket would swallow the whole bore,
  leaving nothing to self-tap); pass `pocket=False` where the wall is too thin.
  Keep `m2_anchor_bite(depth)` ≥ 2 mm.
- **`cut_m2_insert_bore(w, pnt, dir, clr_len)`** — insert-MANDATORY: Ø3.3 × 3.5
  pocket, then Ø2.4 *clearance* (which no screw can bite). **No self-tap
  fallback.** Correct ONLY where the screw must pull two lugs together (a pinch
  clamp) or pass through into a far part.

**One API, all sizes.** `M2` and `M4` are `FastenerSpec`s; the geometry functions
take a spec, so both sizes are the same code with different constants
(`cut_anchor(M2, …)` / `cut_anchor(M4, …)`, or the pre-bound `cut_m2_anchor(…)`).
Nothing about a size is special-cased — `selftap_d = screw_d + 0.2` (FDM holes
print undersize), `shaft_clr_d = screw_d + 0.4`, and **`min_bite = 5 × pitch`**
(five engaged threads: M2 → 2.0, M4 → 3.5). Adding M3 means adding one spec.

**Size the wall to `spec.anchor_min_wall`** (= `insert_depth + min_bite`; 5.5 mm
for M2, 8.5 for M4). Thinner and you must give up one end — so when you place a
screw that threads into plastic, budget that much wall from the start.

**Deviations are allowed but must say why, in code.** Each escape takes a reason
string, so no compromise ships silently and every one is greppable:
`cut_anchor(…, pocket=False, reason=…)` forfeits the insert path;
`cut_insert_bore(…, reason=…)` forfeits the self-tap (this is what a **set
screw** must use — it may never self-tap); `cut_anchor(…, short_bite=…)`
acknowledges a bite under `min_bite`. **Before deviating, try
`cut_boss_anchor()`** — grow a boss and *make* the room. That isn't a deviation,
and it's usually available.

**A nominal `depth` cannot see a thin wall.** A through-bore across 4.6 mm of
material nominally has 20 mm of bite and really has 1.1 mm. Use
`measured_bite(solid, …)` / `assert_bite(…)` on the *finished* part, and gate it
in `tools/check_m2_anchors.py` (see the retractable-cable-spool project).

**The anchor's mouth is the face the INSERT enters, not necessarily the face the
screw enters.** Usually they're the same (a blind hole in a wall). In a pinch
clamp they're opposite: the screw must spin free in the near lug to pull the
joint closed, so the anchor lives in the far lug — and its pocket opens on that
lug's OUTER face, where a soldering iron can reach, with the Ø2.2 self-tap
running from there back toward the slit. Same `cut_m2_anchor` call, just mouthed
from the outside and pointing inward. Don't invent a special cutter for clamps.

Plus `cut_m2_head_bore` (Ø4.1 counterbore + Ø2.4 shaft), `cut_m2_clearance`, and
the `m2_insert()` / `seated_m2_insert()` fit-check dummies. `cut_m2_insert_bore`
(pocket + Ø2.4 clearance, insert MANDATORY, no self-tap fallback) exists for the
rare hole with under 5.5 mm of wall that must still take a real thread — reach
for it last, not first. Each cutter is also exposed as a `*_cutter(...)` returning
the bare solid, for fusing into a larger cut. They take a direction **vector**
(`(0,-1,0)`), not the M4 helpers' `(axis, deg)`. Lengths measure from the nominal
mouth face; `overshoot=` extends the cutter backwards out of the material to dodge
coincident-face booleans without moving any real feature.

## Minimum material — count it in whole beads
Design printed material as an **integer number of nozzle beads.** The projects
slice with a variable-width wall generator (**Arachne**), which fills exact nozzle
multiples cleanly — so there is **NO buffer.** (An earlier `nozzle + 0.05` pad
guarded against classic generators dropping exactly-one-nozzle lines; retired once
everything moved to Arachne — user's call 2026-07-22. If you see `0.85`/`+0.05`
anywhere, it's a leftover to clear.)

**One bead is the hard floor; two beads (`2 × nozzle`) is the QUALITY TARGET** — a
lone bead slices a bit mushy, two clean perimeters print crisp. **Prefer two beads**
on anything load- or seal-bearing; drop to one only in a genuinely tight room.

`cadkit.printing` owns the rule — never hard-code `0.8`/`1.6`:
```python
from cadkit.printing import min_wall
NOZZLE_D    = 0.8                        # set ONCE per project (this repo runs 0.8)
MIN_WALL    = min_wall(NOZZLE_D)         # 0.8 — one-bead HARD floor
MIN_WALL_2P = min_wall(NOZZLE_D, beads=2)   # 1.6 — two-bead quality target (prefer this)
```
### The bead GRID — every length, not just the thin ones

`min_wall` answers *"how thin may this get?"*. That leaves the middle of the
range unmanaged, and that is where the slicer starts improvising. The rule is
bigger than the floor:

> **Every printed length is either `N × BEAD`, or another feature `± N × BEAD`.**

A 1.75 mm wall clears a 1.6 floor and is **2.19 beads.** Arachne cannot lay 2.19
beads — it stretches two to 0.875 each, or squeezes in a starved third. Harmless
on a cosmetic face; on a load-bearing ledge that improvised bead is exactly where
the part delaminates, and *you* did not choose it. On the grid, the extruded part
is the part you drew.

The `± N beads` half carries as much weight as the multiples: derived constants
then land on the grid **for free**, so an off-grid *derived* value means one of
its parents is off-grid — which is the bug worth chasing.

```python
from cadkit.printing import beads, on_grid, snap
beads(3, 0.8)              # 2.4  — the ruler (no floor; 0 beads is legal)
on_grid(1.75, 0.8)         # False — 2.19 beads
snap(1.75, 0.8, "up")      # 2.4  — load-bearing rounds UP; 'down' for clearance pockets
```

**Three kinds of length are legitimately off-grid** — each for a reason about the
world, and each needing that reason written down, because a bare off-grid number
is indistinguishable from an oversight:

- **hardware** — a dummy modelling a REAL object. A NEMA17 is 42.3 mm whether or
  not that suits your nozzle. Rounding it doesn't print better, it makes the
  model **lie about what has to fit**. Model it true; put the *printed material
  around it* on the grid. (A soft spec — a coil's free length, a cut rod — may be
  rounded to a bead for convenience; that's a choice, so say so.)
- **clearance** — a slip fit is 0.25 mm by necessity and is always sub-bead.
  Clearances are **gaps, not material**: no bead is laid across one, so the grid
  has nothing to say. The only exemption needing no per-case justification.
- **domain** — scale length, string pitch, a mounting standard. The printer
  doesn't get a vote.

Anything else off-grid is an oversight. Enforce it with **`cadkit.bead_check`**,
the shared audit engine (bare literals checked by VALUE, derived constants by
the OFFSETS they add — the result may sit anywhere, it inherits its datum).
Each project ships a thin `tools/check_beads.py` driver supplying its constants
package and an exemption table keyed by name, every entry carrying its reason;
non-zero exit for off-grid values that have none (the overlap-gate pattern; the
pedal-steel's is the reference driver). Counts (`N_*`), angles (`*_DEG`,
`THROW*`) and `n × BEAD` coefficients are skipped automatically.

**The grid governs DIFFERENCES, not positions.** The printer quantises one
thing only: the distance between opposing surfaces that bound material.
Positions are continuous — no lattice, and the slicer prints a perfect circle;
the grid is a worst-case guarantee about thin-wall fill, not a voxel model. So:
**snap where free, chain where coupled** — an isolated feature goes on the
absolute grid (`70 × BEAD`, and always written as a count, never `56.0`); a
feature sharing material with an off-grid datum (hardware, scale length) is
sized `datum ± N × BEAD` so the *web between them* is what lands on-grid.
Snapping it absolutely instead moves the remainder onto the load-bearing web.
**Joinery: fit beats grid** — a tenon is `mortise − clearance`, sub-bead by
necessity, so one side is off-grid *by construction*; put the nominal profile
on the grid and the whole clearance on ONE side (cadkit.joinery: the tenon).
Parts print separately — their frames share no grid at print time.

What a full audit actually finds (pedal-steel, 264 findings → 0): mostly not
walls but **stale spelled datums** — literal copies of a chain whose parents
had since snapped, each silently wrong by a fraction of a bead. Fix by
referencing the live datum (or, where import direction forbids, spelling it
via the same shared constants and saying so). And expect a few constants that
**cannot** snap because a model assert pins them at a limit — those are tuned
knobs: exempt them citing the assert, don't fight it.

**The grid is a property of the PART, not the project.** A project sets a default
nozzle because most of it is structure, but a part whose detail is finer than a
bead can resolve gets a finer nozzle *and a finer grid*. The pedal-steel's belt
splice clamp is the case: GT2 ridges at a 2.0 mm tooth pitch, 0.75 mm tall — a
0.8 bead cannot resolve that (one bead per tooth *is* the tooth, so the ridges
smear and the mesh that stops the splice slipping stops existing). It declares
its own `NOZZLE_D = 0.2` and is graded against 0.2.

Mating across two grids is safe in **one direction**: a coarse length is always a
whole number of fine beads (0.8 = two 0.4s), but not the reverse. So a face
**shared** between a 0.8 part and a 0.4 part must sit on the **coarser** grid —
size shared features from the coarse part and let the fine part inherit them.

**Round the way the feature fails.** Load-bearing or sealing → snap **up** (cost:
a little material; risk avoided: a crack). Clearance-side pocket or cosmetic
relief → down or nearest. And when a snap would move a **mating** face, move the
mate with it — otherwise you've traded a slicer problem for a fit problem. That
is exactly why the rule reads *"another feature ± N beads"* and not *"round every
number independently"*.

Size features from these (e.g. a boss ceiling over a cross-bore = `axis_z + bore_r
+ MIN_WALL_2P`). Same rule lives in `joinery._bead`/`_bead_pref` and
`contact.contact_rib_size`. It bites hardest at **hidden** thin spots — a boss
ceiling over a horizontal set-screw bore, a web between two pockets — where the
nominal numbers look fine but the finished solid is a razor. The overlap gate
does NOT catch thin material (see its caveats), so **verify these on the real
solid** with a point-probe / cross-section, not on paper.

## Don't
- Don't re-add Onshape (push scripts, credentials, `_push_onshape`) — removed on
  purpose.
- Don't hand-set part colours in the FreeCAD GUI — they reset on reload. Bake
  colours into the STEP in the build (`cadkit.cq_colors`).
- Don't colour any non-TPU part black (or near-black): **black is reserved for
  TPU parts**, so material reads at a glance in the viewer. Wires follow their
  own scheme (coloured by gauge bucket in the project's build colour table).

## Token efficiency
Delegate heavy, read-only exploration to **subagents**; run **`/compact`** at
natural breakpoints (after a part is finalised) rather than near the limit.
Claude Code has no fixed-percentage auto-compact threshold, so this is a habit,
not a setting.

## Multi-agent collaboration (git worktrees + merge requests)
**Default: work solo — ignore this section.** One agent, one working dir, build
and commit normally; zero overhead. This stays DORMANT until the human turns it on
— by telling the original chat *"let's go multi-agent"*, or by telling a second
chat *"you're a sub-agent on this project."* It exists because two chats editing
the **same** working dir clobber each other's files and race the single FreeCAD
tab / build.

Shared CLI: **`cadkit/tools/agent_sync.py`** (run with `-h` for the full reference;
run it from the project dir; coordination state lives in `.git/agent-sync/`,
shared across worktrees, never committed). **Work out your role from what the human
told you, then follow that block:**

**► You were told you're a SUB-AGENT / contributor.** You are NOT the lead. Before
editing anything:
1. `py -3.12 cadkit/tools/agent_sync.py join <name>` (name = your task, e.g. `pedal`),
   then `cd` into the worktree it prints. Do ALL your work there — a separate
   directory, so you never collide with the lead. (If you already had uncommitted
   work in the lead's main dir, `git stash` it BEFORE `join`, then `git stash pop`
   once you're in your worktree — that carries it over without losing anything.)
2. **Never run `src.build` or open the viewer** — that's the lead's single tab.
   **Validating your change is YOUR job, not the lead's** — the lead merges and
   builds, and does not re-derive whether your geometry is right. Before every
   `submit`, on your own branch:
   - `py -3.12 -m tools.check_overlaps` — the full gate. Say the result in your
     submit summary ("gate green, N inherited"). Inner-loop iterations can use
     `--only <your,bases>`, which skips the pairwise cost but NOT the model build,
     so it saves less than you'd think; the full gate is the one that counts.
   - the project's other checks (bead/grid, min-wall, thread rules) — same rule.
   - **anything that MOVES: probe it swept, by hand.** The gate only ever sees the
     rest pose, and allowlisted pairs are invisible to it forever. A mechanism that
     collides at 20° of throw passes a green gate.
   If you genuinely can't verify something without a build, say so in the submit
   summary rather than shipping it silently — the lead's build is a real failure
   check, but only for import/geometry errors, not for your design intent.
3. **`sync` BEFORE you start each task — not only between rounds.** Run
   `py -3.12 cadkit/tools/agent_sync.py sync` to pull the lead's latest `main` into
   your branch *before you edit anything*, every round. The lead is landing commits
   the whole time (its own work AND other contributors'); if you branch or keep
   working from a **stale `main`**, your next `submit` is built on old code — it
   silently REVERTS whatever the lead merged in the meantime, and forces the lead
   into a painful conflict resolution (or, worse, a clean-looking auto-merge that
   quietly rolls their tuning back). A stale base is the #1 cause of merge pain
   here. So: **`sync` → edit → verify → `submit`**, and `sync` again next round.
4. Hand off: `py -3.12 cadkit/tools/agent_sync.py submit "<summary>"` — commits your
   branch and files a merge request. That request itself wakes the lead, so you
   don't ping anyone. Then loop back to step 3 (`sync` first!) for the next round.

**► You're the LEAD** (original/only chat; the human said "multi-agent" or named
another agent alongside you). Keep working in the main worktree on `main`. You OWN
the build + the FreeCAD tab — the ONLY chat that runs `src.build` / `show()`. To
take contributors' work **hands-free**:
1. Arm the notifier ONCE, in the **BACKGROUND**:
   `py -3.12 cadkit/tools/agent_sync.py wait`  (run_in_background). It blocks in the
   shell until a request lands, then exits and auto re-invokes you — no polling by
   you, no human relay.
2. When it wakes you: `take <name>` (resolve any conflicts) → `build` (announce the
   build #) → **re-arm** `wait` in the background for the next one.
3. **Batch.** If several requests are queued, `take` them ALL first, then run ONE
   `build`. A build is minutes; merging is seconds. Never build per-request.
4. **Don't re-run the contributors' validation** — they gate their own branch and
   report it (see the sub-agent block). What you owe is the thing none of them can
   see: the **combination**. Two branches that are each green alone can collide
   once merged, and only the post-merge whole-tree check catches it — which is why
   the gate is folded into the build (above) and costs you ~15 s rather than a
   second 6-minute model build. Read the gate line before you push.

Rules that keep it from clobbering:
- **Only the lead builds / opens the viewer.** `agent_sync.py build` refuses
  outside the main worktree and holds a single-build lock — never a second tab or
  a concurrent build. Contributors verify with the overlap gate only.
- **Contributors edit ONLY in their own worktree**, never in the lead's directory.
- **Contributors `sync` before each task, never work from a stale base.** Branching
  or editing off an old `main` makes `submit` roll back whatever the lead landed
  meanwhile — a clean auto-merge can silently undo the lead's tuning. If a request
  arrives on a stale base, the lead should **inspect the diff before `take`**
  (`git diff --stat main..agent/<name>`); if it reverts current work, `drop` it and
  have the contributor `sync` and resubmit rather than resolving by hand.
- **The merge request IS the notification.** `submit` writing the request file is
  exactly what ends the lead's background `wait` and re-invokes it — fully
  hands-free, no human in the loop.
- **Shared `cadkit/` edits are now normal tracked diffs** (cadkit is a git subtree,
  not the old on-disk `freecad/`). A contributor who changes a shared util just commits
  `cadkit/*` and `submit`s like any other change — the lead `take`s it normally. (The
  old "[freecad-only: empty diff]" handoff is retired.) Once merged, that util change
  lives only in this project's vendored copy until the lead PROPAGATES it to the other
  projects — the lead runs `py -3.12 ../cadkit/tools/propagate.py` (pushes canonical,
  re-pulls every consumer; see the "Changing a shared util" bullet up top). Do this
  before considering a shared-code change finished — an un-propagated util is drift
  waiting to bite.
- `done` prints how to retire a worktree once everything is merged.
