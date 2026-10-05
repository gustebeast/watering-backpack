"""Green-line filter — the SCREEN ELEMENT. DESIGN_V2.md section 4.

WHAT THIS IS, AND WHAT IT IS NOT. Section 4 specifies a sealed, printed,
self-backflushing filter on the green line. This module is the slotted cylinder
only — the part section 4 fully determines. The HOUSING around it is NOT here,
because section 4 does not determine it; see "what the housing still needs"
below. The element is the right thing to build first regardless, because it
carries the whole makeability risk: section 4's own warning is that slots
">= one nozzle diameter (0.2-0.25 mm) or the slicer drops them". If a 0.2 mm
nozzle cannot render these slots, every downstream housing decision changes.
src.test_pieces.test_screen_slice is the coupon that settles it.

FLOW, AND WHICH FACE IS DIRTY. Section 4's table: retract and fertilizer draw
run pot -> filter -> pump (filtering), dispense runs pump -> filter -> pot
(backflushing). The element is fed from its BORE, so the cake builds on the bore
wall and dispense sweeps it back out to the pot — "sand migrates forward one
pot per cycle". That makes the BORE the controlling surface, so the 1" diameter
and the 0.25 mm slot width are both held AT THE BORE (ID 25.4); the slots open
outward through the wall into the annulus. Holding them at the OD instead would
quietly undersize the open area and oversize the slot at the face that does the
filtering.

SIZING IS DERIVED, NOT COPIED. Section 4 lands on "1 inch diameter x 0.8 inch
long", but 0.8 inch does not survive the integer slot count: at a 0.4 mm minimum
rib (two 0.2 mm extrusions, the printability floor) only 122 slots fit the bore
circumference, not the 122.76 the 0.65 mm pitch implies. 122 x 0.25 x 20.32
gives 0.961 in2 against the 0.9625 in2 that 3 GPM at 1 ft/s actually needs —
0.4% short. So the slot length is sized FROM the face-velocity requirement
(asserted below) and comes out longer than 20.32. The requirement is the gate;
0.8 inch was the round number on the way to it.

PRINT (no supports), axis vertical exactly as modelled:
  * slots and ribs are vertical — constant section, zero overhang;
  * the part NARROWS going up out of the bottom ring, so that cone is an
    upward-facing slope, not an overhang;
  * the top ring flares back out over CONE_H, held off the build axis far
    enough to clear the 45 deg gate rather than sit on it (asserted below);
  * each ring roofs the slots below it, but a slot is only SLOT_W = 0.25 mm
    across, which is why bridged-slot screens print at all. main() reports that
    bridged area explicitly — the overhang gate's sliver filter would otherwise
    drop those faces silently, and a pass you cannot see is not a pass.

NOT IN THE ASSEMBLY. src.build.components() does not carry this part, so the
overlap gate does not weigh it. That is deliberate: section 4 mounts the filter
"partway along the green line, on the frame where the line leaves the pack",
which is not a position — placing it would be inventing one, and an invented
placement that passes an interference check is worse than no placement.

WHAT THE HOUSING STILL NEEDS DECIDED (not inventable from section 4):
  1. Port arrangement. "Straight-through" in section 4 describes the SCREEN
     having no sump, not the ports being collinear — and collinear axial ports
     put one barb pointing into the bed in every print orientation.
  2. One piece or a bonded pair. "Sealed, not openable" rules out a thread, not
     a solvent/epoxy joint; a one-piece shell roofs the annulus and fails the
     overhang gate.
  3. Printed barbs or captured bought fittings. The rest of the design buys its
     fittings (Seaflo swivels, Uniseal); printed barb ribs are downward
     overhangs on their undersides.
  4. [SETTLED 2026-10-05 -- the pump-side barb is 1/2 inch.] This used to read
     "the size IS CONTRADICTED IN THE DOCS ... section 5 is the later, broader
     statement so 5/8 is almost certainly right, but this module does not pick".
     It was not settled by the argument. It was settled by a PURCHASE: the owner
     has bought the SEAFLO SFFN1-1220-01 swivels, which are 1/2"-14 FNPT x 1/2"
     BARB, five of them, and they are the fitting on all four pump ports. A 5/8
     inch tube does not grip a 1/2 inch barb, so the main run is 1/2 inch and
     section 5's "5/8 everywhere except the probe" is dead -- not out-argued,
     overtaken. The housing is still the 3/8 -> 1/2 transition; only the number
     on the pump side moved, and it moved to the one the BOM always had.

Run:  py -3.12 -m src.line_filter      -> writes line_filter_screen.step
"""
from __future__ import annotations

import math

import cadquery as cq

from cadkit.step_export import export_step

# ---- the controlling bore (section 4's "1 inch diameter") --------------------
SCREEN_ID   = 25.4              # 1" — the dirty face; slot width is held HERE
WALL_T      = 0.8               # radial wall = 4 x 0.2 mm lines

# ---- slots ------------------------------------------------------------------
SLOT_W      = 0.25              # section 4: 0.25 mm ~ 60 mesh, >= one nozzle dia
NOZZLE      = 0.20              # section 4 prints this on a 0.2 mm nozzle
RIB_MIN     = 0.40              # two 0.2 mm extrusions — the printability floor

# ---- the flow requirement the slot length is sized from ---------------------
FLOW_IN3_S  = 11.55             # 3 GPM, section 4
FACE_FPS    = 1.0               # section 4's face-velocity ceiling
IN2_MM2     = 645.16

# ---- rings ------------------------------------------------------------------
END_RING_T  = 2.0               # seal/locator land the housing captures
MID_RING_T  = 1.0               # halves the ribs' unsupported span
RING_OD     = 33.0              # sized so the annulus beats the line bore
CONE_H      = 3.5               # ring -> wall transition
BAND_N      = 2                 # slot bands (BAND_N - 1 mid rings)

OV = 0.5                        # boolean overshoot

# -- derived, with the spec's own arithmetic re-done at the bore ---------------
N_SLOTS   = int(math.floor(math.pi * SCREEN_ID / (SLOT_W + RIB_MIN)))
PITCH     = math.pi * SCREEN_ID / N_SLOTS
RIB_W     = PITCH - SLOT_W
OPEN_NEED = FLOW_IN3_S / (FACE_FPS * 12.0) * IN2_MM2          # mm2
SLOT_L    = math.ceil(OPEN_NEED / (N_SLOTS * SLOT_W) * 10.0) / 10.0
BAND_L    = SLOT_L / BAND_N
OPEN_AREA = N_SLOTS * SLOT_W * SLOT_L
GROSS     = math.pi * SCREEN_ID * SLOT_L
SCREEN_OD = SCREEN_ID + 2.0 * WALL_T
LENGTH    = 2.0 * (END_RING_T + CONE_H) + SLOT_L + (BAND_N - 1) * MID_RING_T

# Two kinds of check below, and the difference matters.
#
# DERIVATION GUARDS. N_SLOTS is computed FROM RIB_MIN and SLOT_L FROM OPEN_NEED,
# so these two can only ever catch the derivation being rewritten wrongly — most
# usefully a rounding direction (floor instead of ceil on SLOT_L drops the open
# area to 619.2 mm2, under the 620.9 needed). They do NOT police the inputs, and
# must not be read as if they do.
assert RIB_W >= RIB_MIN, "rib %.3f under the %.2f mm print floor" % (RIB_W, RIB_MIN)
assert OPEN_AREA >= OPEN_NEED, (
    "open area %.1f mm2 under the %.1f mm2 that %.2f in3/s at %.0f ft/s needs"
    % (OPEN_AREA, OPEN_NEED, FLOW_IN3_S, FACE_FPS))

# INPUT GUARDS. These do police the inputs, against the nozzle they are printed
# with — the constraint section 4 raises and that no gate in this repo measures.
assert SLOT_W >= NOZZLE, (
    "a %.2f mm slot is under the %.2f mm nozzle; the slicer will drop it"
    % (SLOT_W, NOZZLE))
assert RIB_MIN >= 2.0 * NOZZLE, (
    "a %.2f mm rib is under two %.2f mm extrusions" % (RIB_MIN, NOZZLE))
assert WALL_T >= 2.0 * NOZZLE, (
    "a %.2f mm wall is under two %.2f mm extrusions" % (WALL_T, NOZZLE))

# SPEC-DRIFT GUARD. Section 4 states 0.8 inch of slot. The length here is derived
# instead, and lands 0.08 mm over — but if a premise moves (flow, face velocity,
# slot width, bore) the derived length walks away from the document silently.
# Fail at 10% so DESIGN_V2 section 4 gets revisited rather than quietly outvoted.
SPEC_SLOT_L = 0.8 * 25.4
assert abs(SLOT_L - SPEC_SLOT_L) <= 0.10 * SPEC_SLOT_L, (
    "derived slot length %.2f mm is %.0f%% off section 4's %.2f mm — a premise "
    "moved; reconcile the document" % (SLOT_L, 100.0 * abs(SLOT_L - SPEC_SLOT_L)
                                       / SPEC_SLOT_L, SPEC_SLOT_L))
# the annulus outside the screen must not become the new restriction
ANNULUS = math.pi / 4.0 * (RING_OD ** 2 - SCREEN_OD ** 2)
# ⚠ 1/2", NOT 5/8", AND THE CHANGE MAKES THIS ASSERT EASIER -- which is the
# right direction and is still worth saying out loud. The test is "the annulus
# round the screen must not become a tighter restriction than the line feeding
# it", so it has to be taken against the line that EXISTS. That line is 1/2"
# now (see item 4 in the header: the owner's swivels are 1/2" barb), and the
# annulus goes from 1.43x the bore to 2.23x. Nothing was relaxed to make the
# geometry pass; the geometry did not move.
LINE_BORE = math.pi / 4.0 * 12.7 ** 2                         # 1/2"
assert ANNULUS >= LINE_BORE, (
    "annulus %.0f mm2 chokes the %.0f mm2 line" % (ANNULUS, LINE_BORE))
# the ring flare must clear the overhang gate, not sit on it
_SLOPE   = (RING_OD - SCREEN_OD) / 2.0 / CONE_H
_CONE_NZ = -_SLOPE / math.hypot(1.0, _SLOPE)
assert _CONE_NZ > -0.72, "top ring flare at n.z %.3f needs support" % _CONE_NZ


def _slot_cutters(z0: float, h: float, slot_w: float) -> cq.Workplane:
    """N_SLOTS radial through-slots as ONE compound — a single cut is far
    cheaper than N_SLOTS of them, and the flanks stay planar, which is what
    the slicer sees (and what a real wedge-wire screen has)."""
    depth = WALL_T + 2.0 * OV
    rm = SCREEN_ID / 2.0 - OV + depth / 2.0
    solids = []
    for k in range(N_SLOTS):
        solids.append(
            cq.Workplane("XY")
            .box(slot_w, depth, h, centered=(True, True, False))
            .translate((0.0, rm, z0))
            .rotate((0, 0, 0), (0, 0, 1), 360.0 * k / N_SLOTS)
            .val())
    return cq.Workplane(obj=cq.Compound.makeCompound(solids))


def screen(bands: int = BAND_N, slot_w: float = SLOT_W) -> cq.Workplane:
    """The element. `bands`/`slot_w` exist so the coupon is THIS geometry
    shortened, and so a slot-width sweep is a one-argument change — never a
    second model of the same feature."""
    slot_l = BAND_L * bands
    length = 2.0 * (END_RING_T + CONE_H) + slot_l + (bands - 1) * MID_RING_T
    ri, ro, rr = SCREEN_ID / 2.0, SCREEN_OD / 2.0, RING_OD / 2.0

    # one revolved outer profile: ring, cone in, wall, cone out, ring
    z_top = END_RING_T + CONE_H + slot_l + (bands - 1) * MID_RING_T
    pts = [(ri, 0.0), (rr, 0.0),
           (rr, END_RING_T),
           (ro, END_RING_T + CONE_H),
           (ro, z_top),
           (rr, z_top + CONE_H),
           (rr, z_top + CONE_H + END_RING_T),
           (ri, z_top + CONE_H + END_RING_T)]
    body = (cq.Workplane("XZ").polyline(pts).close()
            .revolve(360.0, (0, 0, 0), (0, 1, 0)))

    cut = None
    z = END_RING_T + CONE_H
    for _ in range(bands):
        c = _slot_cutters(z, BAND_L, slot_w)
        cut = c if cut is None else cut.union(c)
        z += BAND_L + MID_RING_T
    body = body.cut(cut)
    assert abs(body.val().BoundingBox().zlen - length) < 1e-6, (
        "screen length %.3f, expected %.3f"
        % (body.val().BoundingBox().zlen, length))
    return body


PRINT_ROT = None                # the modelled axis IS the build axis


def bridged_area(bands: int = BAND_N, slot_w: float = SLOT_W) -> float:
    """Total downward-facing area the rings bridge over slots. Each face is
    slot_w x WALL_T, which the overhang gate drops as a sliver — correctly, but
    only if someone has looked at the number."""
    return bands * N_SLOTS * slot_w * WALL_T


def main():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    part = screen()
    b = part.val().BoundingBox()
    export_step(part.val(), str(root / "line_filter_screen.step"))
    print("Wrote line_filter_screen.step")
    print("  bore / wall / outer : ID %.2f  wall %.2f  OD %.2f mm"
          % (SCREEN_ID, WALL_T, SCREEN_OD))
    print("  slots               : %d x %.2f mm at %.4f pitch, rib %.3f (floor %.2f)"
          % (N_SLOTS, SLOT_W, PITCH, RIB_W, RIB_MIN))
    print("  slot length         : %.2f mm in %d band(s) of %.2f, %.1f mm mid ring"
          % (SLOT_L, BAND_N, BAND_L, MID_RING_T))
    print("  gross screen area   : %.0f mm2 = %.3f in2" % (GROSS, GROSS / IN2_MM2))
    print("  open area           : %.0f mm2 = %.4f in2  (need %.4f at %.0f ft/s)"
          % (OPEN_AREA, OPEN_AREA / IN2_MM2, OPEN_NEED / IN2_MM2, FACE_FPS))
    print("  open fraction       : %.1f%%   face velocity %.2f ft/s"
          % (100.0 * OPEN_AREA / GROSS,
             FLOW_IN3_S * IN2_MM2 / OPEN_AREA / 12.0))
    print("  annulus outside     : %.0f mm2 vs %.0f mm2 of 1/2 in line bore"
          % (ANNULUS, LINE_BORE))
    print("  ring flare          : n.z %.3f (gate flags below -0.72)" % _CONE_NZ)
    print("  bridged slot roofs  : %.1f mm2 over %d faces of %.3f mm2, each a "
          "%.2f mm span" % (bridged_area(), BAND_N * N_SLOTS,
                            SLOT_W * WALL_T, SLOT_W))
    print("  envelope            : %.1f x %.1f x %.1f mm   solids %d"
          % (b.xlen, b.ylen, b.zlen, len(part.val().Solids())))


if __name__ == "__main__":
    main()
