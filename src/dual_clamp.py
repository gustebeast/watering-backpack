"""Dual C-clamp — ties a hose to one of the pack frame's poles.

Two grips fused by a web, holding the pole and the hose:

  * dual_clamp_19 (PERPENDICULAR): pole 25 + hose 19, hose bore turned 90° so the
    hose runs ACROSS the pole. It's an L-bracket: the pole grip stays a vertical
    C, the hose grip is a horizontal-bore C beside it, dropped so both lug
    bottoms sit at z=0 for a flat print base. BOTH are driven by ONE M4 (+nut)
    on a shared screw line — see `_build_perp`, which is the authority here; an
    earlier version of this docstring claimed one screw per grip.

19 is the hose: `plumbing.TUBE_OD` is 19.05.

THERE USED TO BE A dual_clamp_23, and a PARALLEL `_build` to make it. It gripped
a 23 mm **valve** body, and DESIGN_V2 §1 is "Two pumps, no reversing valve" —
there is no valve, and nothing in v2 is 23 mm across. It was still being exported
as a print deliverable and billed in the BOM at 17 cm³. Both are gone; `git log`
has the parallel variant if a second hose ever needs strapping to the first.

Each grip is a C whose mouth is INT (=3 mm) narrower than the cylinder so it
snaps on to HOLD during assembly; the screw does the real clamping.

PRINT (no supports): pole grip is a vertical extrusion (clean). The hose grip's
bore is horizontal with its mouth DOWN — its crown is a short overhang;
bridge-able in PCTG, or ask for a teardrop top.

WHERE IT GOES is not in this model. It clamps to the Stansport pack frame's
tubing, which `plumbing.pack_frame()` draws as a flat reference panel, not as
poles. So this part carries no position in the assembly and sits outside the
interference gate — along with `joystick_mount`, which mounts on the shoulder
strap. Modelling the pack frame's tubing is what would bring both inside it.

Run:  py -3.12 -m src.dual_clamp   -> writes dual_clamp_19.step
"""
from __future__ import annotations

import math

import cadquery as cq

# ── Pole (fixed) + gap ───────────────────────────────────────────────────────
# ESTIMATE, and labelled as one per cadkit/AGENTS.md: nominal 25 mm for the
# Stansport frame's tubing, not measured off the frame. A 1" tube would be
# 25.4; on a 3 mm snap interference that 0.4 is tolerable, but measure it.
POLE_D,  POLE_R  = 25.0, 12.5         # frame pole
GAP   = 6.0                           # surface-to-surface gap (valve OD set per build)

# ── Grip ─────────────────────────────────────────────────────────────────────
WALL  = 3.0                           # C-arm wall thickness
POLE_RO  = POLE_R + WALL              # 15.5 — pole grip outer radius
CLAMP_LEN = 25.0                      # length along the cylinder axis (print height)
INT  = 3.0                            # mouth interference (mouth = D - INT): snaps on
                                      # to HOLD for assembly; the SCREW does the grip
POLE_MOUTH = POLE_D - INT             # 22.0 — pole opening width

# ── Web (rigid bridge fusing the two grips through the gap) ───────────────────
WEB_X = 12.0
WEB_Y = 16.0

# ── M4 clamp screw(s) ────────────────────────────────────────────────────────
M4_CLR     = 4.5                      # M4 clearance bore — consistent the whole way
                                      # through (head one end, nut the other)
LUG_W      = 7.0                      # lug reach past the mouth edge (head/nut seat)
SCREW_DROP = 4.0                      # pole-clearing screw drop (parallel: clears the
                                      # pole; perp pole grip: same)
HOSE_DROP  = 3.0                      # perp hose grip: its own screw only clears the hose
LUG_WALL   = 2.5                      # material beyond the screw bore

OV = 0.5


def _ring(cx: float, ro: float) -> cq.Workplane:
    return cq.Workplane("XY").center(cx, 0).circle(ro).extrude(CLAMP_LEN)


def _bore(cx: float, r: float) -> cq.Workplane:
    return (cq.Workplane("XY").workplane(offset=-OV).center(cx, 0)
            .circle(r).extrude(CLAMP_LEN + 2 * OV))


def _mouth(cx: float, ro: float, width: float) -> cq.Workplane:
    """Bottom (-Y) opening slot."""
    depth = ro + OV
    return (cq.Workplane("XY").workplane(offset=-OV).center(cx, -depth / 2.0)
            .box(width, depth, CLAMP_LEN + 2 * OV, centered=(True, True, False)))


def _vgrip(r: float, mouth: float, screw_drop: float):
    """A single vertical-axis C grip at the origin (bore Z, mouth −Y) with two
    lugs flanking the mouth — NO screw bored (the caller bores one shared screw).
    Returns (solid, local_screw_y, lug_x_out)."""
    ro = r + WALL
    half = mouth / 2.0
    tip = math.sqrt(r * r - half * half)
    screw_y = -(r + screw_drop)
    y_bot   = screw_y - (M4_CLR / 2.0 + LUG_WALL)
    body = _ring(0.0, ro).cut(_bore(0.0, r)).cut(_mouth(0.0, ro, mouth))
    for sx in (1.0, -1.0):
        x0 = min(sx * half, sx * (half + LUG_W))
        body = body.union(cq.Workplane("XY")
                          .box(LUG_W, (-tip) - y_bot, CLAMP_LEN,
                               centered=(False, False, False))
                          .translate((x0, y_bot, 0)))
    return body, screw_y, half + LUG_W


def _build_perp(valve_d: float):
    """PERPENDICULAR clamp: hose bore turned 90° (runs across the pole). Pole grip
    vertical, hose grip horizontal beside it, BOTH driven by ONE M4 (+nut) along a
    shared screw line. The hose grip drops so its lug bottoms sit at z=0, coplanar
    with the pole grip bottom — a flat print base."""
    valve_r  = valve_d / 2.0
    valve_ro = valve_r + WALL
    cc = POLE_R + GAP + valve_r                  # pole↔hose axis separation (in X)
    valve_mouth = valve_d - INT

    # Shared screw line: along X at (y = Ys, z = Zs). Ys clears the pole (its mouth
    # opens −Y); Zs sits just above the bottom so a lug wall remains below it.
    Ys = -(POLE_R + SCREW_DROP)
    Zs = M4_CLR / 2.0 + LUG_WALL

    pole, pole_sy, pole_xout = _vgrip(POLE_R, POLE_MOUTH, SCREW_DROP)   # pole_sy == Ys
    hose, hose_sy, hose_xout = _vgrip(valve_r, valve_mouth, HOSE_DROP)

    # Turn the hose grip 90° about X (bore Z→Y, mouth −Y→−Z) and translate so its
    # OWN screw line lands on the shared (Ys, Zs): rot maps local screw
    # (y=hose_sy, z=LEN/2) → (y=−LEN/2, z=hose_sy).
    hose = (hose.rotate((0, 0, 0), (1, 0, 0), 90)
                .translate((cc, Ys + CLAMP_LEN / 2.0, Zs - hose_sy)))
    # The pole +X lug and hose −X lug overlap along the shared screw line, so the
    # union fuses the two grips. A rib BELOW the bores (clear of the hose mouth
    # gap) stiffens the joint and broadens the flat base.
    rib_top = (Zs - hose_sy) - valve_r - 0.5     # just under the hose bore
    rib = (cq.Workplane("XY")
           .box((cc - valve_r) - (POLE_R - 2.5), WEB_Y, rib_top,
                centered=(False, True, False))
           .translate((POLE_R - 2.5, Ys, 0)))
    body = pole.union(hose).union(rib)

    head_x = -pole_xout
    nut_x  = cc + hose_xout
    bore = (cq.Workplane("YZ").workplane(offset=head_x - OV)
            .center(Ys, Zs).circle(M4_CLR / 2.0).extrude(nut_x - head_x + 2 * OV))
    body = body.cut(bore)
    info = dict(valve_d=valve_d, valve_mouth=valve_mouth,
                note=f"ONE screw + nut, ~{nut_x - head_x:.0f} mm (perpendicular)")
    return body, info


dual_clamp_19, INFO_19 = _build_perp(19.0)
dual_clamp = dual_clamp_19            # default instance for the assembly viz


def main():
    # `from step_export import ...` — the bare name, which is not importable, so
    # the Run: line in this module's own docstring had never worked.
    import os
    from cadkit.step_export import export_step
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for stem, solid, info in (("dual_clamp_19", dual_clamp_19, INFO_19),):
        export_step(solid, os.path.join(root, f"{stem}.step"))
        b = solid.val().BoundingBox()
        print(f"Wrote {stem}.step  (pole D{POLE_D:.0f} / hose D{info['valve_d']:.0f})")
        print(f"  envelope : X {b.xlen:.1f}  Y {b.ylen:.1f}  Z {b.zlen:.1f} mm  "
              f"solids {len(solid.val().Solids())}")
        print(f"  screws   : {info['note']}")


if __name__ == "__main__":
    main()
