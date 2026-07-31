# `joinery.py` — printable mortise-and-tenon slide joints

Shared, project-agnostic joint generators, in the spirit of `threads.py`: the
geometry rules live here once, projects import and place. Read this before
adding variants.

## One entrypoint: `joint` — the only way in

**Names name the halves, never the shape.** The public API is `joint`, and a
joint has exactly two parts: a `tenon` and a `mortise`. Which cross-section
they get — octagon, arrow, tee, hook, or whatever replaces those someday —
is the library's decision, made from the SITE you describe:

- **print settings** — a `PrintSpec` per half: nozzle, material, print
  orientation (`facing`);
- **install direction** — the one axis deliberately left without retention;
- **bounding box** — the room the joint may occupy: `width` across the face,
  `length` of engagement, `depth` past the mating plane.

The library builds the optimal printable geometry for that site. Callers
never import a shape.

```python
from cadkit.joinery import PrintSpec, joint

up   = PrintSpec(nozzle=0.8, material="PETG-GF", facing="up")    # part prints -Z→+Z
side = PrintSpec(nozzle=0.8, material="PETG-GF", facing="side")  # part prints -Y→+Y

j = joint(width=5.6, length=6, tenon=side, mortise=up)
host = host.union(j.tenon(root=1.0).translate(...))   # tenon fuses into its host
ring = ring.cut(j.mortise(drop=2.0).translate(...))   # cavity opens through the face
# j.height / j.width_min / j.clearance / j.nozzle / j.dims — size around it
# without knowing internals. j.family names what the optimizer picked —
# informational only, never an input, never something to branch on.

jz = joint(width=7, length=20, depth=3.5, tenon=up, mortise=up,
           install="z")     # width/depth/length = the AVAILABLE room

jb = joint(width=4.15, length=8.5, tenon=up, mortise=up, install="z",
           bounded=True)    # EDGE-BOUNDED site: width = the face's FULL
                            # extent between free edges — the library sizes
                            # every candidate profile for the room and keeps
                            # the one whose thinnest wall lands on the
                            # higher print tier

ja = joint(width=5.0, length=None, tenon=up, mortise=up)   # rotational install:
ring = ring.union(ja.tenon_arc(radius=40, sweep_deg=8))    # profile revolved
top  = top.cut(ja.mortise_arc(radius=40, sweep_deg=30))    # about the Z axis

joint_box_min(up, up, install="z", quality=True)   # -> (4.8, 3.5): the room a
                            # joint NEEDS here before you have geometry —
                            # same site inputs, no solids
```

- **`PrintSpec(nozzle, material, facing)`** — `facing` is `'up'` (−Z→+Z) or `'side'`
  (−Y→+Y). `material` picks the fit clearance from a print-validated table
  (`PETG-GF → 0.15`), falling back to a **default (0.15)** when unknown; override
  any time with `joint(…, clearance=…)`.
- **Materials pick the clearances** (`joint_clearances(tenon, mortise, fit,
  override)` is the policy, public for sizing math): the table value dilates the
  mortise laterally everywhere; **fiber-filled filaments (GF/CF in the material
  name) get 2× on the install-z T's DEPTH faces** — only the mortise's back
  wall moves deeper, every printed wall keeps its tier size. Print finding
  (retractable-cable-spool wall joint, PETG-GF both halves): lateral 0.15 slid
  fine, the depth sandwich bound until its face gap reached 0.3. Other
  families' fiber behavior is unmeasured — they use the base value.
- **`fit`** — `"normal"` (default) is the print-tested slide fit; `"loose"`
  doubles BOTH clearances for joints that must slide with zero effort (glued
  assemblies, frequently-serviced parts). Retention geometry is unchanged —
  only the gaps grow.
- **`install`** — the slide/install axis: the ONE direction deliberately left
  without retention (print orientation alone under-determines a slide joint).
  `'x'` (default) slides ⊥ print-Z — the profile faces are overhangs, so the
  facings pick a print-compromise profile. `'z'` slides ∥ print-Z — the
  profile lies flat in the plan plane and prints as vertical walls, so the
  **square-shouldered T** applies (the angled dovetail was retired, see the
  T section; both hosts must face `'up'`). For a **rotational** install path
  (parts already located on a shared axis), draw the solids with
  `.tenon_arc(radius, sweep_deg)` / `.mortise_arc(…)` instead of
  `.tenon()` / `.mortise()` — up+up sites only.
- **How the profile gets picked** (informational — you never ask for one):
  `x`: `up + up` → the octagon; `side + up` → the arrow ramp+hook. `z`:
  `up + up` → the T — or, with `bounded=True`, the library sizes both the T
  and the single-flank HOOK for the room and keeps the higher-TIER one
  (tie → the T: it retains both pull directions). Any unmodelled combo
  **raises** with an "add the variant" pointer — no silent unprintable
  improvisation.
- **Size = room:** `width` (flat-to-flat) and `length` (engagement), plus
  optional `depth` past the mating plane. Everything else is derived and
  floored per profile; the bridge is pinned to one nozzle on the mortise.
  `width` too small → raises at model time with the floor.
  `joint_box_min(tenon, mortise, install=…, bounded=…, quality=…)` answers
  the inverse question — the smallest (width, depth) a joint needs at the
  hard (1·nozzle) or quality (2·nozzle) tier — for deriving the hosting
  geometry BEFORE the joint exists.

The per-profile generators in `joinery.py` (`_arrow_*`, `_octagon_*`,
`_tee_*`, `_hook_*`) are **private** — the implementation layer `joint`
dispatches to. The sections below document their geometry and the print
findings behind it; the function names in them are internals.

## The joint, and the retention idea

The profile is a **dull arrowhead**: a stem, two 45° barb flares, two 45° tip
tapers, and a small flat tip. It avoids the tight acute corners of a classic
dovetail (fit problems) and every working face is 45° (printable), while the
barbs still lock the +Z (lift) direction like a dovetail would.

```
_______
|   __    |          mortise cavity, symmetric variant
|  /   \  |          (both parts print -Z→+Z)
|  \   /  |
|__|  |__|
```

Joints are **prisms along +X — a slide axis**, not snap-fits. The mortise part
installs by sliding +X→−X: relative to it the tenon travels +X through the
cavity, entering at the cavity's **open −X end** and halting against its
**+X end wall** — the hard stop. Constrained by shape: ±Y (stem/ramp walls),
+Z (barb), further −X (the stop). The one free direction — the part backing
out +X — is covered by an **external preload** (e.g. a rubber band that
already pulls the retainer −X), which keeps the stop loaded
tool-free. No pins, no glue, no flexures.

Multiple short joints along different X-lines beat one long one when the
mating area is a ring or a narrow rail.

## Print-orientation variants

Like threads, each combination of host print orientations needs its own
profile. Present so far:

| variant | mortise host prints | tenon host prints | profile |
|---|---|---|---|
| `ramp=True, hook_h=…` — **THE RECOMMENDED JOINT for this combo (print-validated)** | −Z→+Z | −Y→+Y (tenon sideways) | +Y barb is a SQUARE HOOK: flat underside + vertical outer wall (each ≥ 1 bead); 45° taper closes exactly over the stem plane |
| `ramp=True` (no hook) — demo only, cams apart diagonally | −Z→+Z | −Y→+Y (tenon sideways) | −Y half = one straight 45° ramp |
| `ramp=False` | −Z→+Z | −Z→+Z (tenon standing) | symmetric arrowhead |

**Use `hook_h` whenever the joint must not cam apart** (print-test finding): an
all-45° profile has a DEGENERACY — the up-ramp diagonal (+Y+Z) is parallel to
every working face, so the parts cam out that way with zero geometric
resistance (the library self-test prints this number for the plain ramp:
0.000). The square hook's flat shelf locks +Z — and with it the diagonal —
flat-on-flat instead of cam-on-cam. It also removes the 45°+45° pointed barb
tip (a "45-rotated right angle" that prints unreliably — user finding); the
hook's corners are axis-aligned edges, which print cleanly in BOTH parts'
orientations. Only valid with `ramp=True`: the flat underside is a
model-horizontal face, print-VERTICAL on a sideways tenon; a +Z-printed tenon
would see a 90° overhang. Keep every hook segment ≥ one nozzle bead.
A retention undercut CANNOT go on the ramp (−Y) side: any such hook points at
the tenon host's print bed and its leading face starts in mid-air — the seed
failure the ramp exists to avoid. Mirror the lock to the +Y side instead.

```
_____________
|        __       |     ramp=True cavity: right half keeps the barb,
|       /   \      |     left (−Y) half is a single straight 45° ramp
|     /     /      |
|__/      |_____|
```

**Why the symmetric arrowhead fails printed sideways** (the reason `ramp=True`
exists): it is NOT the 45° faces — those are at the self-support threshold
either way. It's the **bed-side barb's leading edge**: in a −Y→+Y build the
first material of that barb is a knife-edge sliver hanging at barb height with
*nothing behind it* in the build direction — it starts in mid-air. The ramp
replaces that half with a single 45° line **rooted at the host surface**, so
every print layer is a column grounded on the rail below it. Point the ramp
side toward the tenon host's print bed.

**Site rule for `ramp=True`:** the ramp foot lands `tip_w/2 + height` to the
−Y side of the joint axis (45° is wide). The foot must land ON host material
(or behind it in the build direction) — a foot hanging past the rail's edge
recreates the mid-air problem the ramp exists to solve.

## Rules (the non-negotiables)

1. **Everything is 45°, exactly — don't "add margin" here.** The ramp/taper
   faces are SHARED by both parts, and the two builds pull opposite ways: the
   mortise's +Z print wants those cavity ceilings *steeper*, the sideways
   tenon wants them *shallower*. 45° is the unique angle satisfying both.
   Consequence: overhang gates will report small dead-45° areas on both parts.
   That is by design — do not "fix" it by tilting a mating face for one part
   (you'd either break the other part's print or introduce fit slop).
2. **The dull tip is the only flat** — a `tip_w × length` bridge in the
   mortise ceiling. Keep it small but printable: ≥ ~2 bead widths
   (default 1.6 for a 0.8 nozzle). Too small a tip prints as a blob and jams
   the slide; too big bridges badly.
3. **Fuse volumetrically.** The tenon carries a `root` (default 1 mm) sunk
   into its host — union it overlapping, never coplanar (OCCT can leave
   coplanar-contact unions as floating solids).
4. **Clearance is print-tested, not theoretical** — same policy as threads.
   `clearance` offsets the whole cavity profile per side (mitred, so angles
   are preserved). Record what you measure:

| profile | clearance (per side) | mortise print | tenon print | nozzle | layer | result |
|---|---|---|---|---|---|---|
| ramp, stem 2.4 / head 4.8 / tip 1.6, neck 0.5 | 0.3 | flat (+Z) | sideways (+Y) | 0.8 | — | **TOO LOOSE**: block pops onto the tenon VERTICALLY (barbs cam over the slot) — dovetail defeated. Two causes: clearance, and the cavity's vertical entry wall was only ~0.46 (barbs at the face). |
| ramp, stem 2.4 / head 4.8 / tip 1.6, neck 0.8 | 0.1 | flat (+Z) | sideways (+Y) | 0.8 | — | Slides well, but pops out along the up-ramp DIAGONAL under force (all-45° degeneracy — see the hook variant, which this finding produced). |
| ramp, stem 2.4 / head 4.8 / tip 1.6, neck 0.78 | 0.15 | flat (+Z) | sideways (+Y) | 0.8 | — | REJECTED: pops out vertically easily. |
| ramp+hook, stem 2.4 / head 4.0 / tip 0.8 / hook 0.8, neck 0.8, taper-return closure | **0.1 — VALIDATED** | flat (+Z) | sideways (+Y) | 0.8 | — | **Print-validated (2026-07-10): "the joint looks great."** Slides to the stop, no vertical pop-on/off, diagonal locked. THE reference recipe for this orientation combo. |
| ramp+hook, segments scaled to 1.6 (2 beads): head 5.6 / tip 1.6 / hook 1.6 / neck 1.6, tenon 5.3 long | **0.15 — VALIDATED** | flat (+Z) | sideways (+Y) | 0.8 | — | **A/B print-tested (2026-07-10): 0.1 TOO TIGHT at this size, 0.15 slides right.** CLEARANCE SCALES WITH ENGAGEMENT: the small 0.8-segment joint wanted 0.1; the 2×-segments, 5.3-long version wants 0.15 — retest clearance whenever a joint grows. |

The library ENFORCES the nozzle floor: the arrow generators take
`nozzle=0.8` and raise on any working segment below it (including the derived
mortise neck = `stem_h − clearance`). Size UP from the floor for strength —
segments are beads, so scale in bead multiples, not ratios.

Residual-behaviour note: with everything locked at 45°, a lone printed joint
can always be forced apart vertically (the flanks are one big cam and FDM
walls flex) — single-coupon pop-out force is a TUNING signal, not the
retention spec. Retention comes from several joints latching together plus
the preload; judge that on the real parts.

Fit lessons from the first row:
- The cavity needs a REAL vertical entry wall below the barb pocket (≥ ~0.8,
  several layers) — with the pocket starting at the opening face, the 45°
  barbs act as a ramp and the joint snaps together vertically no matter the
  slide geometry.
- The mitred clearance offset SHORTENS the cavity's neck by clr·(√2−1)
  relative to the tenon's stem (user-measured in CAD: tenon 0.80, cavity
  0.76 at clr 0.1) — so spec the neck on the MORTISE side and oversize the
  tenon `stem_h` by clr·(√2−1). Gate it with a point-probe, and mind probe
  bias: sampling ε outside the slot wall reads the 45° pocket face ε high
  (an unbiased-looking 0.80 hid exactly this once). Gate it in your project's
  joint test — a mortise-neck constant plus a `_neck_height` point-probe.

5. **Verify with volume probes, not eyes** (see `joinery.py` self-test —
   `py -3.12 joinery.py`): seated = 0, +X free = 0, −X / ±Y / +Z all > 0.
   A joint that "looks right" can still be an unconstrained slot.

## Octagon ("stop-sign") joint — both hosts print −Z→+Z

A second joint family for when **neither** part prints sideways — the tenon host
*and* the mortise host both print −Z→+Z. Its cross-section is an **octagon on a fat
stem**, a stop sign:

```
   __             ROOF = one nozzle (the MORTISE bridge cap — the ONE
  /  \              intentionally-minimal segment: it is the bridge)
 |    |           vertical (two nozzles — the quality tier)
  \  /            lower 45° "orange" diagonal ← (width−stem)/2, the shoulder
  |  |            STEM = width/2 (fat, computed)
```

```python
j = joint(width=6.0, length=12, tenon=up, mortise=up, clearance=0.1)  # up+up
host = host.union(j.tenon(root=1.0).translate(...))   # nominal shape, +X prism
ring = ring.cut(j.mortise(drop=2.0, length=24).translate(...))  # dilated cavity
```

Same slide-along-X convention as the arrowhead: the profile lives in Y-Z, extrudes
along +X, and the parts mate by sliding along X. The octagon captures **±Y and
±Z** by shape (the lower diagonal is the retention shoulder — to lift the bulb out,
its waist can't pass back through the neck), leaving X the install axis; add the
hard stop by trimming the cavity's far end, as with the arrowhead.

Why an octagon and not a triangle (which is also all-45°)? A triangle meets at a
sharp **peak** the nozzle rounds off — you can't print the point as drawn. The
octagon replaces that peak with a short flat roof, and that roof is the joint's
one real print risk: printed −Z→+Z, the **mortise cavity's roof is an unsupported
bridge**. So it's held to **one nozzle width** — a single bead the printer spans
without sag.

### Two constraints, on OPPOSITE parts

- **Roof cap → the MORTISE.** The face that bridges is the mortise roof, so that is
  what's pinned to one nozzle. The tenon roof is *pre-shrunk* so that after the
  mortise's mitred clearance dilation the bridge lands on exactly one nozzle. (Cap
  the tenon instead and the mortise roof widens to `nozzle + 2·clearance·(√2−1)` —
  0.88 mm at 0.1 — which sags.)
- **Nozzle minimum → the TENON.** The mortise is the tenon dilated, so the tenon is
  the *smaller* part everywhere — its segments are what bottom out. `width_min` is
  the smallest width whose **tenon** stem and diagonals all clear one nozzle. (The
  roof is exempt: capped bridge on the mortise, supported last layer on the tenon.)

### Sizing — give it room, not force

- **`width`** — flat-to-flat = *the lateral room* = the joint size, and the **only
  shape knob**. Sets the upper ("green") diagonal; wider = bigger (and, at 45°,
  taller).
- **`length`** — slide/engagement depth = *the other room dimension*, and the real
  load path of a slide joint.
- **`nozzle`** the physical constant; `clearance` = fit gap; `root`/`drop` = fusion
  / cavity-opening depth.

The **mortise neck survives the dilation at the tier**: the mitred clearance
offset SHORTENS the cavity's neck vertical by `clearance·(√2−1)` at the reflex
shoulder corner, so the tenon post is pre-grown by exactly that (print-caught:
a mount-channel neck measured 1.54 at clearance 0.15 before the relief). Same
lesson as the arrow's oversized `stem_h` and the T's pre-grown lip — the
self-test measures the cutter's neck face directly.

The **stem is width/2** and the **shoulder follows** — both *computed*, not knobs.
width/2 is where the stem (tension) and the two mortise lips (shear) fail at the
same load, so it's the deterministic strength optimum; wider starves retention,
narrower starves the neck. Verticals sit at the TWO-NOZZLE quality tier (user
print finding — crisper walls); only the ROOF stays one nozzle, because it is
the mortise's printed bridge and is intentionally the smallest possible
overhang. So the callsite
reports *room* (`width`, `length`) and nothing else — no `force`, no `stem_frac`,
no raw segments to get wrong.

The self-test (`py -3.12 joinery.py`) gates all of this: ±Y/±Z locked, X free, the
fat stem (`width/2`, orange < green), the **tenon floor** ≥ nozzle, and the
**mortise roof** measured at three widths to prove it stays one nozzle.

### Entry POCKET (`.mortise(pocket=True)`)

When the slide travel is obstructed — a tenon site whose channel can't reach an
open face for axial entry — the parts must first mate ALONG Z at an offset
position, then slide along X to seat. The obstructed site gets a **pocket**:
the cavity profile with its Z-retention deleted (the waist walls continue
straight down to the opening face; upper tapers + the one-nozzle roof bridge
unchanged, so the print story is identical). A tenon rises into it freely
along Z, stays located in ±Y, and is retained by NOTHING else — a pocket is an
entry feature, always adjacent to a retained mortise segment the tenon then
slides into. Up+up install='x' sites only; an install-z site's install
axis is already the entry, so `pocket=True` there raises.

```
_____________          ____________
|    __     |          |   __      |     mortise (left) vs pocket (right):
|   /   \    |          |  /   \     |     same roof + tapers, but the pocket's
|   \   /    |          |  |     |    |     waist walls drop STRAIGHT to the
|__|  |__|          |__|     |__|     opening — z-entry, no retention
```

## T-slot joint — install ∥ print-Z (`install="z"`)

The third family exists because of a dimension the other two ignore: the
**install axis** — the one direction a slide joint deliberately leaves without
retention. The arrow and octagon assume it is X (⊥ print-Z), which is what
makes their profiles overhang problems needing ramps, hooks, and bridge caps.
When the joint instead installs **along Z — the same axis both hosts print
in** — the profile lies flat in the plan (X-Y) plane and every working face is
a printed **vertical wall**.

The profile is a **square-shouldered T**. It REPLACED the classic angled
dovetail (print finding, 0.8 nozzle, retractable-cable-spool): the dovetail
concentrates its engagement in sharp plan corners, and the nozzle radius
rounds the tenon's acute corners DOWN while rounding the mortise's inner
corners UP — the halves collide at the corners before the faces seat and most
of the wedge detail is gone off the print. Square 90° corners round
COMPATIBLY on both halves; retention becomes flat shoulder bearing, which
also removes the dovetail's lateral cam (pull-out no longer levers the
mortise lips apart). The one dovetail virtue lost — wedge take-up of
clearance — was never used: these are SLIDE joints running print-tested
clearances. (Internally this is the `_tee_*` profile.)

```
 ______
 |__    |       plan view (looking down Z): neck through the mating plane,
    |   |       a LIP step at depth_used/2, then the parallel-sided head
  __|   |       bar out to depth_used — every corner 90°, every tenon wall
 |______|       segment ≥ one nozzle
```

```python
# width/depth are the AVAILABLE room (across the face / into the host) — the
# profile inside is OPTIMIZED for strength, and may use less than the room.
j = joint(width=7, length=20, depth=3.5, tenon=up, mortise=up, install="z")
wall = wall.union(j.tenon(root=1.0).translate(...))   # prism along +Z
beam = beam.cut(j.mortise(drop=2.0, length=24).translate(...))  # far Z-end
                                                      # left inside = the stop
```

Conventions: profile in the plan plane, width across Y, head toward +X (rotate
about Z to aim it radially), mating plane at x=0; the prism extrudes along +Z.
The joint locks ±X (neck lips / head end wall) and ±Y (neck + head side
walls); **±Z is free by design** — the caller closes one end with a stop
(un-cut host material past the cavity's far end) and guards the other with a
preload or the next part in the stack.

**Sizing = room in, max-min profile out.** The three parameters are the
mortise's AVAILABLE space — `length` (tall, the Z engagement — used fully;
taller is always stronger), `depth` (into the host), `width` (across the face)
— NOT the joint's dimensions. The T has FOUR failure links — and unlike the
old dovetail's single flank, its TWO shear elements (the mortise lips at the
face, the tenon's head bar off the stem) STACK in the depth. The profile is
the strongest joint the box admits (shear ≈ 0.6·σ, bearing ≈ 1.5·σ):

    neck       = 0.6·min(width, depth)   — shear parity across both stacked
                 elements; floored at 2·nozzle, capped at width − 2·bead
    shoulder o = max(bead, min(neck/3, (width − neck)/2))
    head       = neck + 2·o              (≤ width)
    bar        = max(bead, min(neck/1.2, (depth − back_clearance)/2))
    lip        = bar + back_clearance;  depth_used = lip + bar
                 — parity depth; SURPLUS ROOM IS NOT USED (host material)

where walls TARGET the 2·nozzle QUALITY tier and degrade toward the
one-nozzle HARD floor only in tight rooms (Arachne slicing keeps
exactly-nozzle lines — the old +0.05 buffer is gone). The MORTISE is the
dilated copy — larger everywhere EXCEPT its lip, the one CONCAVE feature:
its face lands `back_clearance` behind the tenon's pre-grown lip, so the
printed **mortise lip = the tenon bar**. `back_clearance` (default =
`clearance`; 2× the base for fiber-filled materials, see
`joint_clearances`) is the DEPTH-FACE gap on BOTH pairs — head-front ↔
cavity-back AND lip ↔ head-back — the depth BOX absorbs it, every wall
keeps tier. The derived numbers are exposed on the result — `j.dims`
(`neck`, `head`, `depth_used`, `lip`) for geometry alongside the joint,
and `j.height` for what the host must actually swallow
(depth_used + back_clearance).

**Minimum bounding boxes** — `joint_box_min(tenon, mortise, install="z",
quality=…)` returns the smallest (width, depth) whose joint has NO wall
under the tier on EITHER half (overhangs/bridges are exempt everywhere in
the library — they are intentionally one nozzle):

| tier | width | depth | at nozzle 0.8, clr 0.15 |
|---|---|---|---|
| hard (1·nozzle) | 4·nz | 2·nz + clr | 3.2 × 1.75 |
| quality (2·nozzle) | 6·nz | 4·nz + clr | 4.8 × 3.35 |

Below the hard box the generators raise. Clearance
policy is the same print-tested table as the other families; it dilates the
mortise only (the T profile itself is print-UNVALIDATED as of 2026-07-22 —
A/B the first print like the arrow rows above).

## Hook (single-flank dovetail) — EDGE-BOUNDED install ∥ print-Z sites

The dovetail's `width` is a region INSIDE a larger face — host material
continues past both flanks. Some sites are **edge-bounded** instead: the
mating face's full extent between two FREE EDGES is the room (first case: a
brake-lever arm 4.15 mm tall carrying its TPU friction pad). There the
symmetric profile dies long before its width floor — after reserving one
printable wall per edge, two flanks + a 2-bead neck no longer fit (at a 0.8
nozzle the symmetric dovetail needs ≥ ~5 mm edge-to-edge; less slices into
sub-bead shoulders whose retention lips attach to nothing).

The HOOK spends the scarce width on ONE flank: a fat stem (all surplus width
— the tension link), one one-nozzle hook toward +Y, and a one-nozzle LIP on
the mortise side filling the notch behind the hook.

```python
j = joint(width=4.15, length=8.5, tenon=up, mortise=up, install="z",
          bounded=True, clearance=0.1)            # short face -> the hook
pad = pad.union(j.tenon(root=1.0).rotate(...).translate(...))
arm = arm.cut(j.mortise(drop=1.0, length=9.5).rotate(...).translate(...))
```

- **`width` = the FULL edge-to-edge extent, walls included** — unlike every
  other family, the hook budgets its own edge walls: after the mortise
  dilation exactly one nozzle survives at each free edge (self-test-gated).
- **Retention:** ±X (the lip hooks the notch / the face bears), ±Y (cavity
  floor + roof — CLOSED, unlike the dovetail's open flanks). ±Z is the free
  install axis: close one end with a stop, and site the stop DOWN-LOAD of
  the working force so the joint self-tightens (the brake pad's stop sits
  where braking drag pushes).
- **Tier-sized** (was bead-fixed; grew with the T's quality tier — print
  finding: sub-1.6 TPU rails tear): the edge walls, hook, mortise lip and
  minimum stem all print at `_hook_seg` = (width − 2·clearance)/4 clamped
  [nozzle, 2·nozzle] — equal-split parity, no segment starves first. Depths
  track the tier: notch = seg + clearance, full depth = 2·seg + clearance;
  `j.height` = what the mortise host swallows (width-dependent now).
  Floors via `joint_box_min(…, install="z", bounded=True)`: hard =
  4·nozzle + 2·clearance; `quality=True` → 8·nozzle + 2·clearance = the
  width where every segment on both halves reaches 2·nozzle — SIZE THE
  HOSTING FACE to this when the site can grow (the brake-pad band did).
- **Print story = the dovetail's:** install ∥ print-Z, every wall vertical,
  any rotation about the install axis allowed. (In the first consumer both
  hosts print along an axis ~9° off the channel — near-vertical walls, fine.)

`bounded=True` declares the edge-bounded contract, and the library sizes
BOTH candidate profiles for the room — the symmetric T inside reserved
edge walls, the hook spending the width on one flank — and keeps the one
whose THINNEST printed wall lands on the higher tier (tie → the T, which
retains both pull directions; below the hook's floor it raises). The
geometry adapts; the callsite just reports the space.

## Adding a variant

Model the new print-orientation combination as a profile tweak (like
`ramp=True`), keep the slide-along-X + hard-stop + external-preload
convention, add it to the table above, and extend the self-test loop. The
open combos: tenon host −Z→+Z with mortise host −Y→+Y (a sideways-printed
ring), and X-build hosts (profile end faces become the print problem).
