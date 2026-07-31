# -*- coding: utf-8 -*-
"""cadkit.printing — FDM print-process limits that geometry must respect.

Currently one rule: the MINIMUM MATERIAL floor, counted in WHOLE BEADS.

    min_wall(nozzle_d)          -> one bead:  nozzle_d          (the HARD floor)
    min_wall(nozzle_d, beads=N) -> N beads:   N * nozzle_d

Design printed material as an INTEGER number of beads. The projects slice with a
variable-width wall generator (ARACHNE), which fills exact nozzle multiples
cleanly — so there is NO buffer. (An earlier nozzle+0.05 pad guarded against
CLASSIC generators dropping exactly-one-nozzle lines; retired once everything
moved to Arachne — user's call 2026-07-22.)

ONE bead is the hard floor, but a lone bead slices a bit mushy; TWO beads
(2*nozzle) is the QUALITY TARGET — two clean perimeters print crisp. Aim for two
beads on anything load- or seal-bearing; drop to one only in a genuinely tight
room. (This mirrors joinery._bead / _bead_pref and contact.contact_rib_size.)

Set the nozzle ONCE per project and derive every minimum from it:

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

__all__ = ["DEFAULT_NOZZLE_D", "min_wall"]

# A common FDM nozzle. Projects override with their own (this repo runs 0.8).
DEFAULT_NOZZLE_D = 0.4


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
    print("cadkit.printing self-test OK")
