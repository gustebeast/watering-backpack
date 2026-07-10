# `threads.py` — self-supporting 45° screw threads in CadQuery, the reliable way

Cutting a printable helical thread in CadQuery / OpenCASCADE (OCCT) is a known
pain — the kernel fails **silently and weirdly**, returning a smooth cylinder, a
half-filled rod, zero solids, or hanging for minutes, all with *no error*. This
module encodes every workaround we had to find. Import it and move on with your
life; read this if you need to change it.

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "freecad"))
from threads import threaded_rod, cut_thread

# short rods / nut cutters / test coupons:
nut_cutter = threaded_rod(minor_d=11, major_d=13, pitch=4, length=20)
piston = body.cut(nut_cutter)               # -> internal thread in the bore

# a long screw: build a SMOOTH blank, subtract the thread LAST, mill any flat AFTER:
blank = crest_cyl.union(shaft).union(head)  # all smooth
screw = cut_thread(blank, minor_d=11, major_d=13, pitch=4, length=146, z=64)
screw = screw.cut(flat_box)                 # flat AFTER the thread
```

## What the thread looks like

A single-start **45° trapezoidal** thread — symmetric flanks at 45°, with small
flats at the crest and root:

- **Self-supporting.** Because no flank exceeds 45°, an internal thread (a nut)
  prints with its **axis vertical** and needs *no support* in the bore. The screw
  side-prints cleanly too. This is the standard FDM "self-supporting thread".
- **Depth ≤ pitch/2.** 45° flanks need `(major-minor)/2 ≤ pitch/2`. E.g. pitch 4 →
  depth ≤ 2; we run Ø13/Ø11 = depth 1.0 with 1.0 mm flats for margin.
- **Cut, never grown.** The thread is helical **valleys cut out of a solid
  crest-diameter blank**. Do *not* build a thread ridge and union it onto a core —
  OCCT drops the core and you get a hollow spring that still reports `solids == 1`.

## Sideways (horizontal-axis) female threads — `teardrop_thread_cutter`

A female thread whose axis prints **horizontal** (a screw hole in a part that lies flat
on the bed) can't use a plain round bore: the bore's top arc is an unsupported overhang
that **sags into a rough, tight thread**. `teardrop_thread_cutter` is the cutter to
subtract for any horizontally-printed threaded hole. **Print-tested clean** (Ø6 cap
screw, PETG — see the clearance table). Orient the part so **print-up is +Y**.

It returns a threaded rod **unioned** with a self-supporting **hexagon peak** on its +Y
side — subtract it, then `clean=False` / don't heal (same thread rules):

```python
from threads import teardrop_thread_cutter
cutter = teardrop_thread_cutter(minor_d, major_d, pitch, engage_len,
                                z=z0, peak_h=..., over_lo=0.0)   # blind end flush
part = part.cut(cutter.translate((x, y, 0)), clean=False)
```

- **Keep the FULL round bore — never slice its top off.** A round screw needs that top;
  a secant/gable cut that removes it leaves solid material where the screw's upper half
  must go and the screw won't seat. The peak is *added* above the full bore, not carved
  out of it. (Cost a build to learn — the "gable" looked right and blocked the screw.)
- **The peak is a HEXAGON, not a plain teardrop.** The transition from round threads to
  the smooth attic runs on **45° planes** (the lines `y = ±x`, matching the thread's 45°
  flank), so the top-wedge ridges are cut **clean**. A horizontal base (plain
  trapezoid/teardrop) slices each tooth on a flat → thin sub-nozzle **slivers**. The
  hexagon's left/right corners (a +45° meeting a −45° edge) are 90°.
- The round lower ~270° stays threaded; the top ~90° is given up to the peak (same trade
  as the drive screw's milled flat). It grips fine.
- `peak_h` truncates the tip to a short flat **bridge** when the wall above the hole is
  thin (a small sag on a <2 mm bridge is harmless). `over_lo`/`over_hi` set the peak
  overshoot per end: **keep it at the MOUTH** (opens the teardrop cleanly where the
  socket exits into air), **zero it at a BLIND end** — else the hexagon drills a pocket
  deeper than the round bore and you get two visible hole depths.
- The thread **runs out** at each end through `threaded_rod`'s conical lead-in, so the
  last tooth dissolves into a smooth cone instead of a thin feather — don't "fix" it.

## Clearance (print-tested)

Thread clearance is print-dependent — nozzle width, layer height, orientation, and
material all change how much slop you need, so **record what you measure**. Tip: when
the nut is already printed, put the clearance on the **screw** side (shrink the screw,
keep the nut cutter fixed) so you only reprint the screw.

Tested combinations (append as you find them):

| thread | clearance (diametral) | nut / socket print | screw print | nozzle | layer | result |
|---|---|---|---|---|---|---|
| Ø13/Ø11, pitch 4, 45°, depth 1.0 | **0.8 mm** (0.4/side) | axis vertical (self-supporting bore) | on its side, on the flat | 0.8 mm | 0.24 mm | threads fast & easy, a bit loose — fine when the nut is well supported in X/Y |
| Ø6/Ø4.4, pitch 3.5, 45°, **teardrop socket** | **0.4 mm** (0.2/side) | **horizontal axis, hexagon peak up** | on its side, on the flat | 0.8 mm | — | **PETG**: turns in/out easily, on the **loose** side — a good friction hold for a cap here; go **0.2–0.3** for a snugger fit on other projects |

## The rules (each one cost a build)

Every violation below is a **silent** failure. The only reliable detector is a
**crest solid/void probe**: march up Z at `r = major/2 - 0.15` and classify
point-in-solid; a real thread alternates `#....#....#`, a broken one is all `#`
(smooth/filled) or throws (0 solids). Never trust the eye or `solids == 1`.

1. **Groove profile must be a 4-point quad.** A 6-point profile (e.g. a "capped"
   valley) makes the swept cutter's `.cut()` wipe the whole part to 0 solids.

2. **Depth ≤ pitch/2**, and keep margin — a valley near `pitch/2` wide, tilted by
   the helix lead angle (isFrenet), self-overlaps turn-to-turn into an invalid
   cutter that no-ops.

3. **A single sweep is clean only to ~100 mm.** Longer, and the sweep+cut wipes the
   part (0 solids). So **tile** the length in short **segments** (`_SEG_LEN = 72`).

4. **Segments must ABUT, never overlap.** Cutting a helix cutter that overlaps an
   already-cut region **silently no-ops** — so every segment after the first leaves
   its span *filled*. (Unioning the overlapping segments into one cutter first fills
   too.) Abut them and **phase-align** each (`rotate 360°·z0/pitch`) so the valleys
   line up into one continuous single-start thread across the seams. Pick a segment
   length that's a multiple of the pitch so the joins land on a tooth edge (phase 0).

5. **Sweep height AND blank height must be whole turns** (multiples of pitch). A
   *partial* final turn wipes the part; so does a sweep that reaches the top of a
   non-whole-turn cylinder. `threaded_rod` rounds its rod **up** to a whole turn;
   `cut_thread` rounds the span **down** so the thread ends *inside* the blank —
   overshooting up into a smaller-Ø shaft grazes it and leaves a thin degenerate
   face at the thread top (a visible "rectangle" artifact).

6. **Cut the thread LAST and ALONE.** Every boolean on the finished (many-face)
   thread is slow — unions/cuts that took ~6 s on a smooth blank *hung for minutes*
   on the thread. So build the whole smooth blank (crest rod + shaft + head) first,
   subtract the thread, and mill the **flat after** the thread (flat-before-thread
   makes the full-helix cutter overlap the flat's void → no-op → filled thread).

7. **`clean=False` on every thread boolean, and never `heal()`/ShapeFix a threaded
   part.** CadQuery's default post-boolean unify (`ShapeUpgrade_UnifySameDomain`)
   and OCCT's `ShapeFix` both crash or hang on the many-face helix. The un-unified
   solid exports to STEP and slices fine.

## Debugging approach (reuse these)

When a thread change misbehaves, don't stare at the render — **probe**. The scratch
scripts that cracked this (kept in the session scratchpad) were:

- **crest probe** — march up Z at the crest radius, print `#`/`.`; catches
  smooth/filled/partial instantly.
- **height matrix** — sweep single cuts at heights 12…150 and at cylinder-vs-sweep
  height combos; this is how the ~100 mm limit and the whole-turn rule surfaced.
- **min-wall / distance probes** (`BRepClass3d_SolidClassifier`,
  `BRepExtrema_DistShapeShape`) for rims and clearances.

## Prior art

This matches long-standing CadQuery/OCCT reports — the "silent empty result on
helix boolean" and "split the helix into <360° segments" advice:
- <https://github.com/CadQuery/cadquery/issues/1328>
- <https://github.com/CadQuery/cadquery/issues/595>
- <https://github.com/CadQuery/cadquery/issues/407>
