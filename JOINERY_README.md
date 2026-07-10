# `joinery.py` — printable mortise-and-tenon slide joints (dull arrowhead)

Shared, project-agnostic joint generators, in the spirit of `threads.py`: the
geometry rules live here once, projects import and place. Read this before
adding variants.

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "freecad"))
from joinery import arrow_tenon, arrow_mortise, arrow_height

ten = arrow_tenon(stem_w=4, head_w=7, stem_h=1, length=12, ramp=True)
cut = arrow_mortise(stem_w=4, head_w=7, stem_h=1, length=24, ramp=True, clearance=0.3)
rail = rail.union(ten.translate(...))    # tenon fuses into its host (root sunk 1 mm)
ring = ring.cut(cut.translate(...))      # cavity opens through the other host's face
```

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
out +X — is covered by an **external preload** (in the toothpaste dispenser:
the rubber band already pulls the retainer −X), which keeps the stop loaded
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

The library ENFORCES the nozzle floor: `arrow_tenon`/`arrow_mortise` take
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
  (an unbiased-looking 0.80 hid exactly this once). See toothpaste-dispenser
  `RJOINT_MORTISE_NECK` + `_neck_height` in `tools/joint_test.py`.

5. **Verify with volume probes, not eyes** (see `joinery.py` self-test —
   `py -3.12 joinery.py`): seated = 0, +X free = 0, −X / ±Y / +Z all > 0.
   A joint that "looks right" can still be an unconstrained slot.

## Adding a variant

Model the new print-orientation combination as a profile tweak (like
`ramp=True`), keep the slide-along-X + hard-stop + external-preload
convention, add it to the table above, and extend the self-test loop. The
open combos: tenon host −Z→+Z with mortise host −Y→+Y (a sideways-printed
ring), and X-build hosts (profile end faces become the print problem).
