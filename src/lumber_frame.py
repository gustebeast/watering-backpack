"""The frame in LUMBER — 38 x 38 beams and 137 x 20 planks, not printed.

v2's frame was printed because v1's was. It does not need to be: it is a
rectangular table carrying a static 21 kg, which is what framing lumber is for.
Wood is also stiffer per gram than PCTG, immune to the creep that drove the
material choice, and free of the whole X-build argument that the printed frame
was contorted around.

What stays printed is the thing that actually wants printing: the electronics
and battery housing, which screws onto these beams.

STOCK (user-measured)
---------------------
  BEAM   38 x 38 mm square
  PLANK  137 x 20 mm flat

WHAT SETS EACH DIMENSION
------------------------
Only three numbers here are chosen; the rest fall out of stock sizes.

  POST_X     The elbow swivel nuts reach |x| = 147. A post inboard of that sits
             on a fitting. 152 is the first clear inner face, so the posts run
             x = 152..190 and the frame is 380 wide — 20 mm proud of the 340 mm
             shelf on each side, which the user has accepted ("we can also go
             wider than 340, just it won't be supported"). Wood cantilevers 20 mm
             without noticing.

  RAIL_Z0    The hose that crosses OVER the pumps is the binding constraint, not
             the pumps. Its centreline is at z=134 and it is 19 mm across, so
             nothing may intrude below 143.5. The rails start at 150.

  FRAME_D    The pumps are 206 long and sit at y=2..208, so 210 is the shallowest
             frame that contains them. That is ALSO why there are no lower cross
             rails: there is no y left to put one in. The base is two side rails
             only, and racking is taken by the deck planks acting as a diaphragm
             plus the pack's own shelf underneath.

The deck planks run FRONT TO BACK (their 137 spans X) so they bear on the cross
rails rather than on their ends, and three of them cover the tank's 348 mm.

Run:  py -3.12 -m src.lumber_frame        # cut list + clearance report
"""
from __future__ import annotations

import cadquery as cq

from . import pump_frame as F

# ── Stock ───────────────────────────────────────────────────────────────────
BEAM   = 38.0            # square section
PLANK_W, PLANK_T = 137.0, 20.0

# ── Layout ──────────────────────────────────────────────────────────────────
POST_X   = 171.0                         # centre; spans 152..190
FRAME_W  = 2 * (POST_X + BEAM / 2.0)     # 380
FRAME_D  = 210.0
POST_YS  = (BEAM / 2.0, FRAME_D - BEAM / 2.0)    # 19 and 191

RAIL_Z0  = 150.0                         # rail underside — set by the overhead hose
RAIL_Z1  = RAIL_Z0 + BEAM                # 188
DECK_Z   = RAIL_Z1 + PLANK_T             # 208 — the tank sits here

N_DECK_PLANKS = 3

# ── Pump floor ──────────────────────────────────────────────────────────────
# The pumps had nothing to stand on. The frame was four posts, rails and a top
# deck carrying the tank; the pump bay below was open air, and the pumps were
# placed at a z that came from a 4 mm PRINTED deck in src/pump_frame.py which
# never made it into the lumber frame.
#
# The floor goes UNDER the posts rather than between them, and that is forced:
# a pump is 115 mm tall and the rails start at RAIL_Z0 = 150, so everything
# below the pump feet has to fit in 35 mm. Bearers plus planks do not. With the
# frame standing ON the floor, the floor's TOP face lands exactly on the pump
# seating plane already in use, so the pumps and every hose route keep the
# heights they have -- this adds a part without moving anything.
#
# The posts shorten to suit: they start at the floor top instead of z=0.
FLOOR_TOP = F.FLOOR_T                      # 4.0 -- pumps bolt to this face
FLOOR_Z0  = FLOOR_TOP - PLANK_T            # -16.0
# Three planks, spanning the frame width EXACTLY (380): the two outer ones are
# ripped to 121.5 so the floor stops at the post outer face. Full 137s would
# reach x = -205.5 and foul the electronics housing, which comes down to z = 0
# at x = -221.5..-190.
FLOOR_RIP_W = (FRAME_W - PLANK_W) / 2.0    # 121.5
M4_CLR      = 4.5                          # pump bolt clearance (M4 + nut under)

# ── Battery access notch ────────────────────────────────────────────────────
# The battery hangs on the -X face of the frame and seats by sliding DOWN --
# src/housing.py asserts that, because a pack that seated upward would be
# fighting its own latch against gravity. So changing it means lifting it clear
# of the dock's rails, 93 mm, straight up. The deck's outboard overhang is a
# roof directly over that path: the battery ran into the plank after 43.5 of
# the 93 mm, which means it could not be changed at all. Nothing caught this
# because the gate weighed the battery SEATED, as a static envelope.
#
# A notch, and not a narrower or shifted deck. What it removes is the part of
# the plank that laps past the rail at x=-190 and bears on nothing, so it costs
# no strength, and the deck stays three full planks -- centred, un-ripped, the
# whole reason the deck is 411 wide in the first place. Shifting the deck clear
# instead would have put another 14 mm outside the pack frame on the far side.
#
# src/build.py gates the swept volume, so neither this notch nor the dock can
# drift back into blocking it.
NOTCH_X  = -195.5        # inboard limit; still laps the rail's outer face by 5.5
NOTCH_Y0, NOTCH_Y1 = 10.0, 96.0


def _box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY").center((x0 + x1) / 2.0, (y0 + y1) / 2.0)
            .rect(x1 - x0, y1 - y0).extrude(z1 - z0).translate((0, 0, z0)))


def pieces():
    """Every stick of wood, as (name, length_mm, solid). The lengths ARE the
    cut list — nothing here is drawn at a size the stock cannot be cut to."""
    out = []
    h = BEAM / 2.0
    for sx in (-1, 1):
        for py in POST_YS:
            out.append(("post", RAIL_Z0 - FLOOR_TOP,
                        _box(sx * POST_X - h, sx * POST_X + h,
                             py - h, py + h, FLOOR_TOP, RAIL_Z0)))
    # floor planks: the frame STANDS on these, and the pumps bolt through them
    floor_xs = ((-FRAME_W / 2.0, -FRAME_W / 2.0 + FLOOR_RIP_W),
                (-PLANK_W / 2.0, PLANK_W / 2.0),
                (FRAME_W / 2.0 - FLOOR_RIP_W, FRAME_W / 2.0))
    bolts = F.pump_bolt_xy()
    for x0, x1 in floor_xs:
        plank = _box(x0, x1, 0.0, FRAME_D, FLOOR_Z0, FLOOR_TOP)
        for bx, by in bolts:
            if x0 < bx < x1:
                plank = plank.cut(cq.Workplane("XY")
                                  .workplane(offset=FLOOR_Z0 - 1.0)
                                  .center(bx, by).circle(M4_CLR / 2.0)
                                  .extrude(PLANK_T + 2.0))
        out.append(("plank_floor", FRAME_D, plank))
    # cross rails run the full width and land on the posts
    for py in POST_YS:
        out.append(("rail_cross", FRAME_W,
                    _box(-FRAME_W / 2.0, FRAME_W / 2.0,
                         py - h, py + h, RAIL_Z0, RAIL_Z1)))
    # side rails tie front to back BETWEEN the cross rails, so nothing intersects
    side_len = POST_YS[1] - POST_YS[0] - BEAM
    for sx in (-1, 1):
        out.append(("rail_side", side_len,
                    _box(sx * POST_X - h, sx * POST_X + h,
                         POST_YS[0] + h, POST_YS[1] - h, RAIL_Z0, RAIL_Z1)))
    # deck planks run front-to-back, bearing on the cross rails
    span = N_DECK_PLANKS * PLANK_W
    for i in range(N_DECK_PLANKS):
        x0 = -span / 2.0 + i * PLANK_W
        plank = _box(x0, x0 + PLANK_W, 0.0, FRAME_D, RAIL_Z1, DECK_Z)
        if i == 0:                      # the outboard plank, over the battery
            plank = plank.cut(_box(x0 - 1.0, NOTCH_X, NOTCH_Y0, NOTCH_Y1,
                                   RAIL_Z1 - 1.0, DECK_Z + 1.0))
        out.append(("plank_deck", FRAME_D, plank))
    return out


def floor_note():
    bolts = F.pump_bolt_xy()
    return ("floor: 2 planks RIPPED to %.1f mm (outer) + 1 full %.0f mm, all "
            "%.0f long, laid under the posts; the frame stands on them. Drill "
            "%d x D%.1f for the pump M4s (bolt + nut, nuts underneath) at the "
            "positions src.pump_frame.pump_bolt_xy() reports."
            % (FLOOR_RIP_W, PLANK_W, FRAME_D, len(bolts), M4_CLR))


def notch_note():
    """The one cut that is not a length. Without it the battery cannot come
    out, and a cut list of four lengths gives no hint that it exists."""
    edge = -N_DECK_PLANKS * PLANK_W / 2.0
    return ("notch the OUTBOARD deck plank: %.0f mm deep x %.0f mm long in its "
            "outer edge, %.0f..%.0f mm from the front. The battery lifts out "
            "through it." % (NOTCH_X - edge, NOTCH_Y1 - NOTCH_Y0,
                             NOTCH_Y0, NOTCH_Y1))


def frame() -> cq.Workplane:
    s = None
    for _, _, solid in pieces():
        s = solid if s is None else s.union(solid)
    return s


def cut_list():
    from collections import Counter
    c = Counter((n, round(L, 1)) for n, L, _ in pieces())
    return sorted(c.items())


def tank() -> cq.Workplane:
    return (cq.Workplane("XY").workplane(offset=DECK_Z)
            .center(0, F.TANK_D / 2.0).rect(F.TANK_W, F.TANK_D)
            .extrude(F.TANK_H))


def clearance_report():
    """Does anything hit the wood? Per-solid, never against a union."""
    from . import plumbing as P
    others = [("pump_a", F._pump_placed(-1)), ("pump_b", F._pump_placed(+1)),
              ("fittings", F._elbows())]
    for name, pts in P.routes():
        others.append((name, P.run(pts)))
    bad = 0
    for pname, piece_solid in (("wood", frame()),):
        for name, s in others:
            try:
                i = piece_solid.intersect(s)
                v = i.val().Volume() if i.val() is not None else 0.0
            except Exception:
                v = 0.0
            flag = "clear" if v <= 1.0 else "HITS WOOD %.0f mm3" % v
            if v > 1.0:
                bad += 1
            print("   %-14s %s" % (name, flag))
    return bad


def _build() -> None:
    from cadkit.cq_colors import color
    from cadkit.freecad import show
    from . import plumbing as P
    print("=== cut list (38x38 beam, 137x20 plank) ===")
    for (nm, L), n in cut_list():
        print("   %2d x  %-12s %6.1f mm" % (n, nm, L))
    print("    + " + notch_note())
    deck_w = N_DECK_PLANKS * PLANK_W
    print("\nposts/rails %.0f wide x %.0f deep; DECK %.0f wide — three full "
          "planks, %.0f proud of the rails each side (no ripping; the tank "
          "needs %.0f)"
          % (FRAME_W, FRAME_D, deck_w, (deck_w - FRAME_W) / 2.0, F.TANK_W))
    print("deck top z=%.0f, rail underside z=%.0f" % (DECK_Z, RAIL_Z0))
    print("\n=== clearance ===")
    bad = clearance_report()
    asm = cq.Assembly()
    for i, (nm, _, solid) in enumerate(pieces()):
        tint = "#8B5A2B" if nm.startswith("plank") else "#A0724A"   # wood browns
        asm.add(solid, name="%s_%d" % (nm, i), color=color(tint))
    asm.add(F._pump_placed(-1), name="pump_a", color=color("slategray"))
    asm.add(F._pump_placed(+1), name="pump_b", color=color("#5a6b7a"))
    asm.add(F._elbows(), name="fittings", color=color("#c8a24a"))
    asm.add(tank(), name="tank_viz", color=color("#9fd4e8", alpha=0.35))
    for name, pts in P.routes():
        tint = "#b03030" if name.startswith("tank") else "#30a050"
        asm.add(P.run(pts), name=name, color=color(tint, alpha=0.85))
    out = str(F.OUT / "assembly_lumber.step")
    asm.save(out, mode="default")
    print("\nwrote", out)
    return bad


if __name__ == "__main__":
    import sys
    sys.exit(_build())
