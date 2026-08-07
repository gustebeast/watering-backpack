# -*- coding: utf-8 -*-
"""cadkit.printing — FDM print-process limits that geometry must respect.

Two rules, and they are the same rule seen from two distances:

  * the BEAD GRID — every printed length is a whole number of beads (below)
  * the MINIMUM MATERIAL floor — the smallest legal count on that grid

    min_wall(nozzle_d)          -> one bead:  nozzle_d          (the HARD floor)
    min_wall(nozzle_d, beads=N) -> N beads:   N * nozzle_d

Design printed material as an INTEGER number of beads. The projects slice with a
variable-width wall generator (ARACHNE), which fills exact nozzle multiples
cleanly — so there is NO buffer. (An earlier nozzle+0.05 pad guarded against
CLASSIC generators dropping exactly-one-nozzle lines; retired once everything
moved to Arachne — user's call 2026-07-22.)

──────────────────────────────────────────────────────────────────────────────
THE BEAD GRID — not just the floor, the whole ruler (user's call, 2026-08-06)
──────────────────────────────────────────────────────────────────────────────
min_wall answers "how THIN may this get?". The grid answers the bigger question:
what should ANY printed length be? Same answer, applied everywhere.

    EVERY printed length is either N * BEAD, or another feature ± N * BEAD.

The floor alone leaves the middle of the range unmanaged, and that is where the
slicer starts improvising. A 1.75 mm wall passes a 1.6 floor and is 2.19 beads:
Arachne cannot lay 2.19 beads, so it either stretches two to 0.875 each or
squeezes in a starved third. On a cosmetic face, fine. On a load-bearing ledge
the improvised bead is exactly where the part delaminates — and you did not
choose it, the slicer did. Sizing on the grid means the extruded part is the
part you drew.

The "another feature ± N beads" half matters as much as the multiples. Derived
constants then land on the grid for free, so an off-grid DERIVED value is a
signal that one of its parents is off-grid — which is the bug worth finding.

    beads(3)                     -> 3 * DEFAULT_NOZZLE_D
    beads(3, 0.8)                -> 2.4
    on_grid(1.75, 0.8)           -> False   (2.19 beads)
    snap(1.75, 0.8)              -> 1.6     ('nearest'; also 'up' / 'down')
    snap(1.75, 0.8, 'up')        -> 2.4     (use UP for anything load-bearing)

THREE KINDS OF LENGTH ARE LEGITIMATELY OFF-GRID. Each is off-grid for a reason
that is about the world, not about convenience — and every one of them should
carry that reason in a comment, because a bare off-grid number is
indistinguishable from an oversight:

  HARDWARE   a dummy modelling a REAL object. A NEMA17 is 42.3 mm square whether
             or not that suits your nozzle; a GT2 pulley is Ø8.4 over teeth.
             Rounding these to the grid does not make them print better, it
             makes the model LIE about what it has to fit. Model them true, and
             let the printed material AROUND them be the thing that sits on the
             grid. (Where a real part is a soft spec — a coil's free length, a
             cut-to-length rod — rounding to the nearest bead is fine and often
             convenient; that is a choice, so say so.)

  CLEARANCE  a slip fit is 0.25 mm BY NECESSITY, and always will be smaller than
             a bead. Clearances are GAPS, not material: no bead is ever laid
             across a clearance, so the grid has nothing to say about them. This
             is the one exemption that needs no per-case justification.

  DOMAIN     a dimension the physical problem sets — scale length, string pitch,
             a gear ratio, a mounting standard. The printer does not get a vote.

Anything else off-grid is an oversight. A project that wants this enforced can
walk its own constants with on_grid() (see the pedal-steel's tools/check_beads.py
for the shape: an exemption table keyed by name, each entry carrying its reason,
and a non-zero exit for anything off-grid that has none).

THE GRID IS A PROPERTY OF THE PART, NOT THE PROJECT (user, 2026-08-06). A
project sets a DEFAULT nozzle because most of it is structure, but a part whose
detail is finer than a bead can resolve gets printed with a finer nozzle and is
designed on ITS grid. The pedal-steel's belt splice clamp is the case: its grip
face has GT2 ridges at a 2.0 mm tooth pitch, 0.75 mm tall, and a 0.8 bead cannot
resolve that -- one bead per tooth IS the tooth, so the ridges smear and the
mesh that stops the splice slipping stops existing. It prints 0.2 (10 beads per
pitch) and is graded against 0.2.

MATING ACROSS TWO GRIDS is safe in ONE direction, and it is worth knowing which:
a coarse length is always a whole number of fine beads (0.8 = exactly two 0.4s,
four 0.2s), but a fine length is generally NOT a whole number of coarse ones. So
a face SHARED between a 0.8 part and a 0.4 part must sit on the COARSER grid --
size shared features from the coarse part and let the fine part inherit them.
Getting this backwards puts the off-grid dimension on the part that can least
afford it.

CHOOSING A COUNT: round the way the feature fails. Load-bearing or sealing —
snap UP, since the cost is a little material and the risk is a crack. A
clearance-side pocket or a cosmetic relief — snap DOWN or nearest. When a snap
would move a MATING face, move the mate with it or you have traded a slicer
problem for a fit problem: that is why the rule is phrased "another feature ± N
beads" rather than "round every number independently".

ONE bead is the hard floor, but a lone bead slices a bit mushy; TWO beads
(2*nozzle) is the QUALITY TARGET — two clean perimeters print crisp. Aim for two
beads on anything load- or seal-bearing; drop to one only in a genuinely tight
room. (This mirrors joinery._bead / _bead_pref and contact.contact_rib_size.)

Set the DEFAULT nozzle once per project and derive every minimum from it (a part
that prints finer declares its own, as above):

    from cadkit.printing import min_wall
    NOZZLE_D    = 0.8
    MIN_WALL    = min_wall(NOZZLE_D)          # 0.8 — one-bead hard floor
    MIN_WALL_2P = min_wall(NOZZLE_D, beads=2) # 1.6 — two-bead quality target

RULE OF THUMB: no load- or seal-bearing material below min_wall(nozzle); PREFER
min_wall(nozzle, 2). This bites hardest at HIDDEN thin spots — a boss ceiling
over a cross-bore, a web between two pockets — where a nominal number looks fine
but the finished solid is a razor. Check those on the real solid, not on paper.

Self-test: `python -m cadkit.printing` (or run this file).
"""

import math

__all__ = ["DEFAULT_NOZZLE_D", "min_wall", "beads", "on_grid", "snap"]

# A common FDM nozzle. Projects override with their own (this repo runs 0.8).
DEFAULT_NOZZLE_D = 0.4

# Float slop for grid tests. Bead counts are small integers times a 1-decimal
# nozzle, so accumulated FP error is ~1e-15; 1e-9 is loose enough to never trip
# on arithmetic and far tighter than any dimension anyone would call "on grid".
GRID_TOL = 1e-9


def min_wall(nozzle_d=DEFAULT_NOZZLE_D, beads=1):
    """Smallest reliably-printable material thickness = beads * nozzle_d.

    One bead is the hard floor; two beads (the default quality target) print
    crisp where a lone bead goes mushy. No buffer — with a variable-width wall
    generator (Arachne) the slicer fills exact nozzle multiples cleanly."""
    if nozzle_d <= 0:
        raise ValueError("min_wall: nozzle_d must be > 0, got %r" % (nozzle_d,))
    if beads < 1:
        raise ValueError("min_wall: beads must be >= 1, got %r" % (beads,))
    return beads * nozzle_d


def beads(n, nozzle_d=DEFAULT_NOZZLE_D):
    """N beads as a length. The unit the grid is counted in.

    Unlike min_wall this places no floor on n — it is the ruler, not the limit,
    and plenty of legitimate lengths are 0 beads (a datum) or 30 (a rail). Use
    min_wall when you mean "this must not get thinner than"; use beads when you
    mean "this is exactly this many extrusions across"."""
    if nozzle_d <= 0:
        raise ValueError("beads: nozzle_d must be > 0, got %r" % (nozzle_d,))
    return n * nozzle_d


def on_grid(value, nozzle_d=DEFAULT_NOZZLE_D, tol=GRID_TOL):
    """True if `value` is a whole number of beads (sign-agnostic).

    Sign-agnostic because coordinates land on the grid just as thicknesses do,
    and -2.4 is as on-grid as +2.4. Zero is on the grid: it is 0 beads."""
    if nozzle_d <= 0:
        raise ValueError("on_grid: nozzle_d must be > 0, got %r" % (nozzle_d,))
    n = abs(float(value)) / nozzle_d
    return abs(n - round(n)) <= tol * max(1.0, n)


def snap(value, nozzle_d=DEFAULT_NOZZLE_D, mode="nearest"):
    """Round `value` to the bead grid. mode: 'nearest' | 'up' | 'down'.

    'up'/'down' mean AWAY FROM / TOWARD ZERO in magnitude, not toward +inf — so
    a negative coordinate snapped 'up' gets larger in magnitude, which is what
    "give this feature more material" means on either side of an origin. Snap UP
    for load- or seal-bearing material, DOWN for clearance-side pockets."""
    if nozzle_d <= 0:
        raise ValueError("snap: nozzle_d must be > 0, got %r" % (nozzle_d,))
    v = float(value)
    n = abs(v) / nozzle_d
    if mode == "nearest":
        k = round(n)
    elif mode == "up":
        k = math.ceil(n - GRID_TOL)
    elif mode == "down":
        k = math.floor(n + GRID_TOL)
    else:
        raise ValueError("snap: mode must be 'nearest'|'up'|'down', got %r" % (mode,))
    return math.copysign(k * nozzle_d, v)


if __name__ == "__main__":
    # Whole-bead multiples, no buffer.
    assert abs(min_wall(0.8) - 0.8) < 1e-12, min_wall(0.8)
    assert abs(min_wall(0.8, beads=1) - 0.8) < 1e-12
    assert abs(min_wall(0.8, beads=2) - 1.6) < 1e-12   # two-bead quality target
    assert abs(min_wall(0.4) - 0.4) < 1e-12
    assert abs(min_wall(0.4, beads=3) - 1.2) < 1e-12
    for bad in (0.0, -0.4):
        try:
            min_wall(bad); raise AssertionError("expected ValueError")
        except ValueError:
            pass
    try:
        min_wall(0.8, beads=0); raise AssertionError("expected ValueError")
    except ValueError:
        pass

    # ── bead grid ────────────────────────────────────────────────────────────
    assert abs(beads(3, 0.8) - 2.4) < 1e-12
    assert abs(beads(0, 0.8)) < 1e-12          # 0 beads is a legal length
    assert abs(beads(2) - 0.8) < 1e-12         # default nozzle
    # min_wall(n) and beads(n) agree wherever both are legal -- one rule
    for k in (1, 2, 5):
        assert abs(min_wall(0.8, beads=k) - beads(k, 0.8)) < 1e-12

    assert on_grid(2.4, 0.8) and on_grid(0.8, 0.8) and on_grid(0.0, 0.8)
    assert on_grid(-2.4, 0.8), "coordinates land on the grid too; sign-agnostic"
    assert not on_grid(1.75, 0.8), "2.19 beads -- the case the floor rule misses"
    assert not on_grid(2.0, 0.8), "2.5 beads: passes a 1.6 floor, still off grid"
    # arithmetic that should stay on grid must not trip the tolerance
    assert on_grid(sum([0.8] * 30), 0.8), "accumulated FP error must not read off-grid"
    assert on_grid(17 * 0.8 - 5 * 0.8, 0.8)

    assert abs(snap(1.75, 0.8) - 1.6) < 1e-12          # nearest: 2.19 -> 2
    assert abs(snap(1.75, 0.8, "up") - 2.4) < 1e-12    # load-bearing rounds UP
    assert abs(snap(1.75, 0.8, "down") - 1.6) < 1e-12
    assert abs(snap(2.0, 0.8, "up") - 2.4) < 1e-12     # 2.5 beads -> 3
    assert abs(snap(2.0, 0.8, "down") - 1.6) < 1e-12   # 2.5 beads -> 2
    # already on grid: every mode is a no-op (up must NOT push to the next bead)
    for mode in ("nearest", "up", "down"):
        assert abs(snap(2.4, 0.8, mode) - 2.4) < 1e-12, mode
    # negative: 'up' grows the MAGNITUDE, so a -X face moves further out
    assert abs(snap(-1.75, 0.8, "up") - -2.4) < 1e-12
    assert abs(snap(-1.75, 0.8, "down") - -1.6) < 1e-12
    # snap output is on the grid, by construction, for anything
    for v in (0.0, 0.03, 1.75, -13.37, 615.0):
        for mode in ("nearest", "up", "down"):
            assert on_grid(snap(v, 0.8, mode), 0.8), (v, mode)

    for bad in (0.0, -0.4):
        for fn in (beads, on_grid, snap):
            try:
                fn(1.0, bad); raise AssertionError("expected ValueError from %s" % fn.__name__)
            except ValueError:
                pass
    try:
        snap(1.0, 0.8, "sideways"); raise AssertionError("expected ValueError")
    except ValueError:
        pass

    print("cadkit.printing self-test OK")
