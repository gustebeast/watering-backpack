"""The Scepter 5 gal military water can, as a can rather than a brick.

It was `rect(348, 173).extrude(478)` — the right envelope and nothing else. The
envelope is the part that matters for clearance and it has not moved: every
figure below is inside the same 348 x 173 x 478 box, so no gate that passed
against the brick can fail against this. What it adds is the shape the owner is
actually looking at, and the two base runners the LUMBER FRAME WAS ALREADY
BUILT AROUND — `pump_frame.BEAM_YS` puts a cross rail under each of them at
y 12 and 161 and the model drew a flat bottom that touched everywhere.

WHICH CAN, AND HOW SURE
-----------------------
bom_consolidated.md: "Scepter 5 gal MILITARY water can — OWNED. Base ~348 x 173
mm, standing on two wide ribs, ~12 mm in from each end". That is Scepter's
Military Water Can, model 05177, which retailers list at 13.5–13.7 x 6.75–6.8 x
18.8–19 in (343–348 x 171–173 x 478–483 mm) — the owner's measured base to
within a couple of millimetres — and which is sold in MILITARY GREEN. It is not
the "Military STYLE" 4933, the blue/black big-box can of the same capacity.

⚠ THE COLOUR IS A GUESS FROM THE MODEL NUMBER, not from a page I was shown. If
the can in the garage is sand, olive drab or blue, `BODY` below is the one line
to change and nothing else moves.

WHAT IS MODELLED, AND WHAT IS NOT
---------------------------------
Modelled: the rounded body, the two base runners, the ribbed long faces, the
recessed panel each side, the moulded top handle and the cap boss. All of it
from the envelope and the two figures the BOM measured.

NOT modelled, and not guessed at: the exact rib count and spacing, the handle's
section, the spout. None of them is measured and none of them is load-bearing
in this design — the only part of this can the machine TOUCHES is its base
(on the deck) and the flat of a long face (the Uniseal, src/plumbing.py), and
both are drawn where they were. A detail nobody measured is decoration; it is
drawn so the picture is a can, and it is listed here so nobody reads a
dimension off it.
"""
from __future__ import annotations

import cadquery as cq

from . import pump_frame as F

W, D, H = F.TANK_W, F.TANK_D, F.TANK_H

# The can's own colour, as sold. See the docstring: model 05177 is the green one.
BODY = "#4b5440"            # Scepter military green
CAP = "#2f3429"             # the cap is darker than the body

CORNER_R = 24.0             # the vertical corners' radius — from the photos
RUNNER_H = 8.0              # how far the base ribs stand below the body
RUNNER_INSET = F.RIB_INSET  # 12 — MEASURED (bom_consolidated.md)
# ⚠ CLAMPED, and the clamp is the interesting part. pump_frame carries two
# ESTIMATES — RIB_INSET 12 and RIB_W 28 — and a 28 mm rib centred 12 mm in from
# the base's edge hangs 2 mm off the side of the can. One of the two is wrong
# and nobody has put a straightedge on either. What must NOT move is the inset:
# the lumber frame puts a cross rail under each rib at y 12 and 161
# (pump_frame.BEAM_YS reads RIB_INSET for exactly that), so the centre is the
# figure the structure depends on and the width is the one that gives.
RUNNER_W = min(F.RIB_W, 2 * F.RIB_INSET)    # 24, not 28
RIB_N = 6                   # ribs across each long face
RIB_DEPTH = 2.5             # how far a rib is recessed
PANEL_INSET = 26.0          # the recessed panel's margin inside the face
PANEL_DEPTH = 3.5
HANDLE_W = 46.0             # across the can's depth
HANDLE_L = 190.0            # along its width
HANDLE_T = 26.0             # the grip bar's thickness in Z
HANDLE_GAP = 34.0           # knuckle room under the bar
CAP_D = 86.0                # the cap's outer flats
CAP_H = 22.0                # how far it stands above the shoulder
SHOULDER = 34.0             # the top taper's height


BODY_H = H - RUNNER_H       # the hull stands ON the runners, inside the envelope


def _body():
    """The hull: a rounded box that tapers in to the shoulder at the top."""
    low = (cq.Workplane("XY").rect(W, D).extrude(BODY_H - SHOULDER)
           .edges("|Z").fillet(CORNER_R))
    # the shoulder: the same plan, drawn in, lofted up to it
    shoulder = (cq.Workplane("XY").workplane(offset=BODY_H - SHOULDER)
                .rect(W, D).workplane(offset=SHOULDER)
                .rect(W - 2 * PANEL_INSET, D - 2 * 8.0).loft(ruled=True))
    return low.union(shoulder)


def _ribs(s):
    """Horizontal ribs across both long faces: shallow grooves, not structure."""
    band0 = RUNNER_H + 90.0
    band1 = BODY_H - SHOULDER - 60.0
    step = (band1 - band0) / float(RIB_N - 1)
    for k in range(RIB_N):
        z = band0 + k * step
        cut = (cq.Workplane("XY").workplane(offset=z - 6.0)
               .rect(W - 2 * CORNER_R, D + 20.0).extrude(12.0))
        shell = (cq.Workplane("XY").rect(W + 20, D + 20).extrude(H + 20)
                 .translate((0, 0, -10))
                 .cut(cq.Workplane("XY").rect(W + 20, D - 2 * RIB_DEPTH)
                      .extrude(H + 20).translate((0, 0, -10))))
        s = s.cut(cut.intersect(shell))
    return s


def _panels(s):
    """The recessed oval-ish panel on each long face. Drawn as a rounded
    rectangle, because an oval is a guess and a rectangle is a simplification."""
    pw, ph = W - 2 * (CORNER_R + 18.0), 150.0
    zc = RUNNER_H + (BODY_H - SHOULDER) / 2.0
    for sign in (-1.0, 1.0):
        pocket = (cq.Workplane("XZ").workplane(
            offset=-sign * (D / 2.0) - (0.0 if sign > 0 else PANEL_DEPTH))
            .center(0, zc).rect(pw, ph).extrude(PANEL_DEPTH)
            .edges("|Y").fillet(20.0))
        s = s.cut(pocket)
    return s


def _runners():
    """The two wide ribs the can stands on. MEASURED (the BOM): 12 mm in from
    each end of the 173 mm base. The frame already puts a cross rail under
    each; until now the model stood on a flat bottom and touched everywhere."""
    out = None
    for y in (RUNNER_INSET, D - RUNNER_INSET):
        r = (cq.Workplane("XY").center(0, y - D / 2.0)
             .rect(W - 2 * CORNER_R, RUNNER_W).extrude(RUNNER_H))
        out = r if out is None else out.union(r)
    return out


def _handle():
    """The moulded top handle: a bar over a gap, spanning the can's width."""
    bar = (cq.Workplane("XY").workplane(offset=BODY_H - HANDLE_T)
           .rect(HANDLE_L, HANDLE_W).extrude(HANDLE_T)
           .edges("|Z").fillet(14.0))
    gap = (cq.Workplane("XY").workplane(offset=BODY_H - HANDLE_T - HANDLE_GAP)
           .rect(HANDLE_L - 70.0, HANDLE_W + 10.0).extrude(HANDLE_GAP))
    legs = None
    for sx in (-1.0, 1.0):
        leg = (cq.Workplane("XY").workplane(offset=BODY_H - SHOULDER)
               .center(sx * (HANDLE_L / 2.0 - 17.0), 0)
               .rect(34.0, HANDLE_W).extrude(SHOULDER))
        legs = leg if legs is None else legs.union(leg)
    return bar.union(legs).cut(gap)


def _cap():
    """The filler cap, at one end of the shoulder. 44 mm opening (the BOM)."""
    return (cq.Workplane("XY").workplane(offset=BODY_H - CAP_H)
            .center(-(W / 2.0 - PANEL_INSET - CAP_D / 2.0 - 6.0), 0)
            .circle(CAP_D / 2.0).extrude(CAP_H))


def can() -> cq.Workplane:
    """The can in ITS OWN frame: base at z=0, centred in X, y 0..D."""
    s = _body().translate((0, 0, RUNNER_H))
    s = _ribs(s)
    s = _panels(s)
    s = s.union(_runners())
    s = s.union(_handle().translate((0, 0, RUNNER_H)))
    s = s.union(_cap().translate((0, 0, RUNNER_H)))
    return s.translate((0, D / 2.0, 0))


def envelope() -> cq.Workplane:
    """The brick this replaces. Kept so a gate can say what it is comparing."""
    return (cq.Workplane("XY").center(0, D / 2.0).rect(W, D).extrude(H))
