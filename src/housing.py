"""The one printed part: battery mount + PCB case, plus a lid.

Everything else is lumber or bought. This bolts to the outer face of the
frame's two -X posts and carries the Makita dock and the main board side by
side along Y.

WHY THE TWO BAYS SIT WHERE THEY DO
----------------------------------
The frame is 210 deep and that is the whole budget. It used to be spent to the
last 1.4 mm:

    3  outer wall
  100.6  battery dock (its across-slide dimension)
    3  divider
   99  PCB cavity (the 95 mm board + 2 mm clearance a side)
    3  outer wall
  ----
  208.6     with 1.4 to spare

That is where the board's 95 mm came from — it is the leftover, not a choice,
and elec/main.py asserts the same arithmetic from the other end so the two
cannot drift.

28.6 of that 100.6 was never the dock. It was the pair of side EARS that hosted
v1's dovetail mortises, and v2 unions the dock into this part instead of
sliding it on, so the joint they served does not exist (src/battery_dock.py,
`dock(joinery=...)`). With them gone the dock is 72 across. The dock did not
MOVE — it is anchored on its centreline at y=53.3, the seat the battery, the
contact block and the deck notch were all validated against — so the 28.6 came
out as air on both sides of it, and the bay could then be laid out from the
frame's back edge instead of from the dock:

   17.3  back plate only (the -Y wood screws land at y=19)
   72    battery dock, centred on y=53.3
    9.7  air
    3    divider        <- the lid's -Y skirt drops past this wall
   99    PCB cavity (unchanged: the board is routed at 95)
    3    divider        <- and past this one
    6    air            <- the lid's +Y skirt
  -----
  210     exactly the frame

The board does not grow into the slack IN Y, which is the axis this budget is
about: it is 95 wide and JLCPCB's cheapest tier stops at 100, so the price tier
is the binding constraint there, not the frame. What the slack buys is the lid:
a shoebox skirt needs air outboard of the bay walls on all four sides, and at
1.4 mm there was none.

⚠ IN Z IT DID GROW, 100 -> 112, for the on-board blade fuse (elec/main.py's
outline note). That axis has no price tier in it and never had this much slack
either: the bay is pinned between the wire slot's top and the lid screw boss,
and absorbing 12 mm of board took BAY_BORDER from 8 to 3 and moved PCB_Z_C.

HOW THE CABLES GET OUT
----------------------
They could not, until they did: the bay was a closed rectangular tube with four
power terminals facing a wall. There is now ONE down-facing chase through the
bay floor, and under it a slot straight through the back plate so the battery's
own leads can come from the timber side without going round the housing.
Down-facing because the tank
is five gallons of water sitting directly above, and CIRCUIT.md already counts an
opening as an ingress path — which is why the level sensor's lead comes out of
the bottom and climbs back up outside rather than leaving through the roof.

WHY THE WOOD SCREWS ARE ABOVE AND BELOW THE BAYS
------------------------------------------------
The screws into the posts have to be driven from OUTBOARD, which means their
heads land inside the housing. Anywhere inside the dock bay that is in the
battery's slot, and anywhere inside the PCB bay it is under the board. So the
back plate runs taller than either bay and the four screws go in the flange
bands above and below them, where the heads sit in open air. The posts are
150 tall, so both bands are still on wood.

PRINTING
--------
The whole thing stands on its back face — the one that goes against the wood —
and builds outboard in -X. That is the same orientation v1 printed the dock in,
which is why the dock's T-slot still prints: its overhangs were already made
45 deg ramps for exactly this build. The PCB bay's walls and bosses rise from
the same plane, and the flanges ARE that plane. Nothing is cantilevered.

The lid is separate because an integral cover would roof the cavity — the same
reason the old printed shroud's cover had to be its own part.

Run:  py -3.12 -m src.housing
"""
from __future__ import annotations

import cadquery as cq

from cadkit.board_geom import Boards
from cadkit.fasteners import M4, ScrewJoint

from . import lumber_frame as L
from . import pump_frame as F
from .battery_dock import battery_dock, terminal_cutter
from .dimensions import BOOL_OVERSHOOT

# ── The board comes from the ROUTED board, never a typed placement ──────────
# PCB_README: "Model from the routed board, never from the placement table. A
# hand-typed copy can only be checked against itself, and it always agrees."
# This repo has the scars. A typed copy agreed while two connectors sat 0.54 mm
# short of the board edge; and when the board was re-laid from 140x100 to
# 95x100 the CAD kept drilling mounting bosses at the old (+-64, +-44) while
# the laminate had moved to (+-41, +-44). Neither drift is catchable by a copy
# that agrees with itself.
#
# So everything below reads geom.json: outline, cutouts, hole positions and
# part heights. src/build.py runs the agreement gate (elec/cad_geom_check.py)
# that fails if this solid and the routed board diverge -- and it is pointed at
# THIS solid, the one the assembly actually places.
_BOARDS = Boards(str(F.OUT / "elec" / "geom"), height=F._PCB_HEIGHT)


# ── Where it mounts ─────────────────────────────────────────────────────────
BACK_X  = -(L.POST_X + L.BEAM / 2.0)      # -190: the posts' outer face
# ── EVERY PRINTED LENGTH ON THE BEAD GRID ──────────────────────────────────
# cadkit/AGENTS.md, "The bead GRID": *every printed length is either N x BEAD,
# or another feature +- N x BEAD*, because the projects slice with Arachne and a
# wall that is not a whole number of beads is a wall the SLICER chooses the
# section of. 3.0 mm at a 0.8 nozzle is 3.75 beads: Arachne either stretches
# three to 1.0 each or starves a fourth, and on a load-bearing ledge that
# improvised bead is where the part delaminates.
#
# This file had 3.0 everywhere -- walls, plate, lid, skirt -- and none of it was
# chosen, it was just a round number.
#
# NOT EVERYTHING IS ON THE GRID, and the exceptions are the ones AGENTS.md
# names. src/battery_dock.py is HARDWARE: its sections match the Makita pack and
# its adapter, and rounding them to a bead would make the model lie about what
# has to fit. Clearances (LID_GAP, SKIRT_CLR, RET_CLR, the slot and bore sizes)
# are gaps -- no bead is laid across one -- and BOARD_T is the laminate.
NOZZLE_D = 0.8
BEAD = NOZZLE_D
WALL    = 3 * BEAD            # 2.4
# The plate is FOUR beads where the walls are three, and the extra bead is the
# countersink's: WOOD_CSK_DEPTH is 2.55, so a 2.4 plate would have the cone
# break clean through and leave the screw head no seat at all.
BACK_T  = 4 * BEAD            # 3.2

# ── Y layout (see the docstring's budget) ───────────────────────────────────
# MEASURED off the dock, not typed. It was 100.6 -- the ear-to-ear width of
# v1's dovetail joinery -- and when the ears came off (they hosted a joint v2
# does not have) a typed copy would have gone on reserving 28.6 mm of the
# frame's 210 for material that is no longer there.
DOCK_W  = battery_dock.val().BoundingBox().xlen        # 72.0
# ⚠ READ OFF THE BOARD, NOT TYPED. These were two literals, 95.0 and 100.0, and
# the day the board grew 8 mm for the fuse holder they were simply wrong -- the
# bay would have been built around a board that no longer existed, and nothing
# in the CAD would have said a word. geom.json carries the outline the ROUTED
# board actually has, which is the same file the agreement gate measures
# against, so the two can no longer disagree.
PCB_W, PCB_L = _BOARDS.load("main")["outline_mm"]
assert (PCB_W, PCB_L) == (95.0, 112.0), (
    "the board outline moved to %s x %s: every Z number below was chosen "
    "against 95 x 112 and wants re-reading, starting with BAY_Z1 against the "
    "lid screw boss" % (PCB_W, PCB_L))
PCB_CLR = 2.0
# The dock is anchored by its CENTRELINE, not by its -Y edge. Its edge moved
# 14.3 mm when the ears came off; its battery, its contact block and the deck
# notch the pack lifts out through did not, and anchoring on the edge dragged
# all three with it -- far enough to put the connector's back inside a post
# (the overlap gate caught it at 3 mm3).
DOCK_Y_C = 53.3                                       # validated seat, v1 and v2
Y_DOCK0 = DOCK_Y_C - DOCK_W / 2.0                     # 17.3
Y_DOCK1 = DOCK_Y_C + DOCK_W / 2.0                     # 89.3
# The PCB bay is now laid out from the +Y END, not from the dock. It has to be:
# the thing with no slack on that side is the lid's skirt, which hangs outboard
# of the bay's +Y wall and has only the frame's back edge to live in. Laying it
# out from the dock instead would park the whole bay 1.4 mm short of the edge
# again and put the slack where nothing needs it.
SKIRT_T   = 3 * BEAD    # 2.4                   # the lid's skirt, defined here because the
SKIRT_CLR = 0.4                   # bay's Y layout has to leave room for it
SKIRT_GAP = 6.0                                       # air outboard of the +Y wall
Y_PCB1  = L.FRAME_D - SKIRT_GAP - WALL                # 201

# THE CAVITY IS SIZED OFF THE POSED BOARD, NOT OFF PCB_W. The laminate is 95
# and PCB_CLR is 2, which gives 99 and is what this used to use -- but the
# ESP32's ANTENNA overhangs the laminate's +X edge by 4.12 mm, deliberately
# (elec/main.py asserts it must be at the edge). Board +X is world -Y, so the
# antenna needs its clearance on the -Y side and the laminate needs its own on
# the +Y side. They are different numbers and only the board knows them.
#
# It was invisible until pose_board stopped centring the bounding box: that
# bug shifted the laminate 2.06 mm toward +Y, which is exactly half the
# antenna's overhang, so the two errors very nearly cancelled. "Very nearly"
# was -0.06 mm, and this file used to quote that figure as the reason a lid
# skirt could not fit.
_BBB = _BOARDS.solid("main").val().BoundingBox()      # the BOARD's own frame
BOARD_Y_PLUS  = _BBB.xmax                             # 51.62 — toward world -Y
BOARD_Y_MINUS = -_BBB.xmin                            # 47.50 — toward world +Y
PCB_Y_C = Y_PCB1 - PCB_CLR - BOARD_Y_MINUS            # 151.5
Y_PCB0  = PCB_Y_C - BOARD_Y_PLUS - PCB_CLR            # 97.88
Y_OUTER = Y_PCB1 + WALL                               # 204 — the bay's +Y face
assert Y_OUTER + SKIRT_CLR + SKIRT_T <= L.FRAME_D, (
    "the +Y skirt runs %.1f past the frame's %.1f"
    % (Y_OUTER + SKIRT_CLR + SKIRT_T, L.FRAME_D))
assert Y_PCB0 - WALL - SKIRT_CLR - SKIRT_T >= Y_DOCK1, (
    "the -Y skirt lands on the dock: skirt at %.1f, dock ends at %.1f"
    % (Y_PCB0 - WALL - SKIRT_CLR - SKIRT_T, Y_DOCK1))

# The back plate is the full frame depth, NOT the bays' extent. It carries the
# four wood screws and L.POST_YS puts one pair at y=191 -- 11 mm outboard of the
# bay. While the plate ended where the bay ended it only just reached them, and
# once the bay moved it would not have.
Y_PLATE0, Y_PLATE1 = 0.0, L.FRAME_D

# ⚠ 75.6, NOT 75.0, AND THE 0.6 IS NOT A PREFERENCE. The bay is pinned top and
# bottom by things that are not the board (see BAY_BORDER), and at 112 mm of
# laminate what is left over is 1.55 mm. Centring the board in the WINDOW rather
# than on the old 75.0 is what splits that evenly instead of spending it all at
# one end.
PCB_Z_C = 74.75
# ⚠ AND THE WINDOW IS NARROW ENOUGH TO BE WORTH ASSERTING, because both of its
# ends are in other parts: the wire slot is cut through the back plate and the
# boss belongs to the lid, so nothing that reads this file alone would notice
# either moving. The overlap gate does catch it -- that is how the boss's real
# underside was found -- but it catches it as a volume in a build log, which is
# a long way from the number that caused it.

# ── Z layout ────────────────────────────────────────────────────────────────
# The bay is taller than the board needs, and that is deliberate. It used to be
# 11 mm of border above and below, sized to host the four lid pillars, because
# there was no room for them inside the board's own footprint (the board fills
# the bay in Y, which is the tight axis).
#
# The pillars are gone -- the lid is held by its skirt and one wood screw -- so
# the border now answers to two other things, and 8 is what BOTH of them want:
#
#   * the board's own Z retention lives in it (see the retention ribs below);
#   * the lid's screw boss has to clear the bay's +Z wall. The screw is fixed
#     at z=145 and the boss is LID_BOSS_H = 16 mm of lid around a Ø9.5 bore, so
#     its UNDERSIDE IS AT 137.0. At BAY_BORDER=11 the bay wall reached 139 and
#     the two interpenetrated -- 912 mm3, which the overlap gate caught.
#     ⚠ THIS USED TO SAY 138.25, which is the bore plus the 2 mm of lid the
#     assert below demands -- the MINIMUM boss, not the boss that is drawn. The
#     gate caught the difference the moment the bay was pushed up against it:
#     237.6 mm3 at z 137.00..137.50, y 183..199, which is the boss's own 16 mm
#     band. A number taken from a rule rather than from the geometry is exactly
#     the kind of thing that survives until something moves.
# ⚠ AND IT IS 5 NOW, BECAUSE THE BOARD GREW 8 mm AND THE BAY HAD NOWHERE TO PUT
# THEM. The bay is pinned at both ends by things that are not the board: the wire
# slot's top at Z 10.5, which the bay's -Z wall must start above, and the lid
# screw boss's underside at 138.25, which its +Z wall must stay below. That is
# 125.35 mm of Z for a bay of PCB_L + 2*BAY_BORDER + 2*WALL. At 112 x 8 that is
# 132.8 and it does not fit -- the first build after the board grew failed on the
# wire slot, by 2.3 mm at 108 and 6.3 at 112, which is a real collision and not a
# tolerance.
#
# 3.0 makes the bay 122.8, and PCB_Z_C moves to 74.75 to share what is left
# evenly: 0.45 mm over the wire slot and 0.85 under the boss. Nothing was traded
# away for the border: the two jobs it had are both
# somewhere else now. The lid pillars it was originally sized for are gone, and
# the board's Z retention is the rib on the LID (see PRINT_ROT), not a feature of
# this border at all -- the comment above still says "lives in it" and was
# already out of date when it was written.
#
# The alternative was the plate, and the owner offered it ("we can make the plate
# larger to compensate"). It was not taken because the plate's top is L.RAIL_Z0 =
# 150: growing past it is a change to the BACKPACK FRAME, which is a much bigger
# thing to disturb than 3 mm of empty border, and the border had the 3 mm.
BAY_BORDER = 3.0
BAY_Z0     = PCB_Z_C - (PCB_L / 2.0 + BAY_BORDER + WALL)  # 11
BAY_Z1     = PCB_Z_C + (PCB_L / 2.0 + BAY_BORDER + WALL)  # 139
_BOSS_Z0 = 145.0 - 16.0 / 2.0            # LID_BOSS_Z/-H, 400 lines below
assert BAY_Z1 <= _BOSS_Z0 - 0.4, (
    "the bay's +Z wall reaches %.2f and the lid's screw boss starts at %.2f: "
    "they interpenetrate, which the overlap gate reports as a volume and not "
    "as a dimension" % (BAY_Z1, _BOSS_Z0))
# The back plate runs the posts' full height so the countersinks have laminate
# all round them. The screws then sit far enough from the bay that their Ø9
# cones do not undercut its wall -- at z=7 the cone reached z=11.5 and left a
# 1.4 mm2 crescent of wall hanging over nothing, which the gate caught.
BACK_Z0, BACK_Z1 = 0.0, L.RAIL_Z0                         # 0..150, the post
SCREW_ZS   = (5.0, 145.0)
SCREW_YS   = L.POST_YS                                    # 19 and 191 — on the posts
# A COUNTERSINK, not a counterbore. A counterbore leaves a flat Ø8 ceiling
# (the overhang gate measured 4 x 50.3 mm2), and in a 3 mm plate it would
# leave 0.5 mm of material under the head anyway. A cone opening inboard is a
# void that only widens as the build rises, so nothing overhangs it — and a
# flat-head wood screw is what you would use into timber regardless.
# THE HEAD IS O9.3, and that is a MEASURED number, not a guess: it is the
# "v2's validated screw geometry, verbatim" block in the retractable-cable-spool
# project (src/params.py, WOOD_SCREW_SHAFT_D 4.0 / WOOD_SCREW_HEAD_D 9.3 /
# WOOD_SCREW_HEAD_H 4.0), and the same screws are what goes in here.
#
# The countersink used to be O9.0 -- 0.3 mm SMALLER than the head it was cut
# for, so the head would have landed on the pocket's rim instead of seating in
# it. It opens O9.6 now, 0.3 of clearance on a printed cone.
#
# The 45 degree pocket is the right shape for an 82 degree screw and not an
# accident of printability: the pocket's half-angle (45) is STEEPER than the
# head's (41), so the head contacts near the mouth and seats flush. A shallower
# pocket would bottom the head out early and hold the plate off the post.
WOOD_HEAD_D = 9.3                     # the real head, cited above
WOOD_CSK_CLR = 0.3
WOOD_CLR_D, WOOD_CSK_D = 4.5, WOOD_HEAD_D + WOOD_CSK_CLR     # 4.5, 9.6
WOOD_CSK_DEPTH = (WOOD_CSK_D - WOOD_CLR_D) / 2.0             # 45 deg -> 2.55
assert WOOD_CSK_DEPTH < BACK_T, (
    "a %.2f mm countersink breaks through a %.1f mm plate: there would be no "
    "seat left for the head" % (WOOD_CSK_DEPTH, BACK_T))


# ── PCB stack, measured outboard from the back plate's inner face ───────────
FLOOR_X    = BACK_X - BACK_T                 # -193
STANDOFF   = 4.0
BOARD_T    = 1.6
LID_GAP    = 2.5
BOSS_D     = 13 * BEAD                       # 10.4
BOARD_X0   = FLOOR_X - STANDOFF              # -197 board underside
BOARD_X1   = BOARD_X0 - BOARD_T              # -198.6 board top (parts face -X)
LID_T      = 3 * BEAD                        # 2.4
# Plate left UNPIERCED behind every insert bore. All eight used to run clean
# through the back face -- four of them opening into the free air between the
# posts -- which put eight holes into the one bay this design deliberately gave
# a single down-facing opening, on a machine carrying five gallons of water
# directly above it.
#
# They ran through because "a blind bore along the build ends in a flat
# ceiling". That is true, and it is why the OLD frame-mounted plate's bores had
# to be run out. It does not hold here: the build runs -X and these bores are
# entered from the BAY side, which is the top of the print, so they run
# DOWNWARD through it. A blind end is a floor printed on solid plate, not a
# ceiling printed over air. The overhang gate agrees -- it is still clean.
SEAL_T     = 1.5



# ── Cable exit and strain relief ────────────────────────────────────────────
# The bay was a closed rectangular tube: four power terminals sat on the board's
# bottom edge with NO WAY OUT. The housing could not be wired.
#
# One chase, not a hole per connector, and it faces DOWN. CIRCUIT.md counts an
# opening as a water path ("a connector is a water-ingress path on an outdoor
# machine") and the tank sits directly above at z=208, so nothing opens upward —
# the level sensor's lead leaves through this chase too and climbs outside.
#
# IT SPANS THE WHOLE CONNECTOR GROUP, and it is measured off the routed board
# to do it. It used to be a 24 mm slot "between J3 and J4", placed for the
# shortest internal gather and then forced to y=134 by a lid pillar. The four
# blocks span 62 mm, so a wire landing on J1 had to travel the length of the
# bay sideways, under the board, to reach a hole it could not see out of. These
# are screw terminals facing DOWN: the wire has to arrive along its own axis
# with a screwdriver behind it. A chase that does not reach the block is a
# chase that does not work, and the pillar that forced it is gone (the lid is
# held by its skirt and the wood screw now).
#
# Derived, not typed: anything on the board's bottom border whose footprint is
# a TerminalBlock. Add a connector down there and the chase grows to meet it.
CHASE_MARGIN = 2.0                           # air each side of the group


def _edge_connector_span():
    """(y0, y1) in WORLD that the bottom-edge screw terminals occupy.

    FROM THE ROUTED BOARD (PCB_README: never a typed placement). fab[] is
    (xmin, xmax, ymin, ymax) in board mm; board +X maps to world -Y, so the
    extremes swap."""
    lo, hi = None, None
    for f in _BOARDS.load("main")["footprints"]:
        if "TerminalBlock" not in f.get("fpid", ""):
            continue
        x0, x1, y0, _y1 = f["fab"]
        if y0 > -PCB_L / 4.0:                # not on the bottom border
            continue
        a, b = PCB_Y_C - x1, PCB_Y_C - x0
        lo = a if lo is None else min(lo, a)
        hi = b if hi is None else max(hi, b)
    if lo is None:
        raise AssertionError("no bottom-edge terminal blocks on the routed board")
    return lo, hi


_CONN_Y0, _CONN_Y1 = _edge_connector_span()
CHASE_Y0 = _CONN_Y0 - CHASE_MARGIN
CHASE_Y1 = _CONN_Y1 + CHASE_MARGIN
assert Y_PCB0 < CHASE_Y0 and CHASE_Y1 < Y_PCB1, (
    "the chase (%.1f..%.1f) runs past the bay cavity (%.1f..%.1f)"
    % (CHASE_Y0, CHASE_Y1, Y_PCB0, Y_PCB1))

# ── THE BATTERY WIRES COME THROUGH THE PLATE, NOT ROUND IT ─────────────────
# The pack's leads are on the +X side of the back plate, with the timber; every
# terminal they have to reach is on the -X side, in the bay. Until now there was
# no opening for them at all and the implicit answer was "round the edge of the
# housing", which is a 200 mm detour on a 7.5 A pair.
#
# A slot straight through the plate, directly below the bay, and then a 90
# degree turn +Z into the chase. The turn happens in open air: the chase ALREADY
# cuts the bay's -Z wall away over this whole Y band, so once the leads are
# through the plate they are looking straight up into the bay with nothing in
# between.
#
# WHERE IT CAN GO IS A 7 mm BAND, and all three edges of it are measured:
#   Z <= 11.0   the bay's -Z wall starts here; above it is the bay, not air
#   Z >=  4.0   the floor plank's top, measured off the frame solid -- below
#               this the slot opens into timber, which is no opening at all
#   Y 121.7..172.0  the chase at one end, the +Y post's inboard face at the
#               other. Drill outside that and the slot is blind against a post.
# The slot sits inside all three with margin and the asserts below hold it there.
#
# It needs no overhang relief: the housing builds -X (PRINT_ROT), so a hole
# bored through the plate along X is a VERTICAL hole with no ceiling anywhere
# in it.
WIRE_SLOT_Y_C = 147.0
WIRE_SLOT_Z_C = 8.0
WIRE_SLOT_W   = 50 * BEAD   # 40.0 along Y, tip to tip. It is not just the
                            # battery: the PUMP leads cross here too. Every
                            # terminal is on the board's bottom edge and the
                            # chase is the bay's only exit, so J1's battery pair
                            # and J2/J3's two pump pairs all come down the chase
                            # and all have to cross the plate -- six conductors,
                            # and the pumps are 65 mm further +X again. At 14
                            # AWG for the battery and 16 for the pumps that is
                            # 17.8 mm laid side by side, and a 5 mm slot is one
                            # layer deep, so the width is what has to carry them.
                            # 22 mm held exactly six with no slack and no room
                            # to be wrong about gauge.
WIRE_SLOT_H   = 5.0         # along Z, and the end radius
WIRE_WOOD_Z   = 4.0         # measured: the floor plank's top at this Y
WIRE_POST_Y   = 172.0       # measured: the +Y post's inboard face


def _wire_slot() -> cq.Workplane:
    """The battery leads' way in: through the plate, below the bay."""
    # From FLOOR_X, not BACK_X. A YZ workplane extrudes +X and the plate runs
    # FLOOR_X -> BACK_X, so starting at the outboard face cut a 0.5 mm blind
    # pocket in the back of the plate and left it otherwise solid -- the same
    # slip the wood screws' comment above records, and the overhang gate caught
    # this one too: a blind pocket has a floor, and that floor read as 104.6 mm2
    # of flat ceiling facing the bed.
    return (cq.Workplane("YZ").workplane(offset=FLOOR_X - BOOL_OVERSHOOT)
            .center(WIRE_SLOT_Y_C, WIRE_SLOT_Z_C)
            .slot2D(WIRE_SLOT_W, WIRE_SLOT_H, 0.0)
            .extrude(BACK_T + 2 * BOOL_OVERSHOOT))


assert WIRE_SLOT_Z_C + WIRE_SLOT_H / 2.0 <= BAY_Z0 - WALL, (
    "the wire slot reaches Z %.1f and the bay's -Z wall starts at %.1f: it "
    "would open into the wall, not under it"
    % (WIRE_SLOT_Z_C + WIRE_SLOT_H / 2.0, BAY_Z0 - WALL))
assert WIRE_SLOT_Z_C - WIRE_SLOT_H / 2.0 >= WIRE_WOOD_Z, (
    "the wire slot reaches Z %.1f and the floor plank's top is %.1f: it would "
    "open into timber" % (WIRE_SLOT_Z_C - WIRE_SLOT_H / 2.0, WIRE_WOOD_Z))
assert CHASE_Y0 <= WIRE_SLOT_Y_C - WIRE_SLOT_W / 2.0 and        WIRE_SLOT_Y_C + WIRE_SLOT_W / 2.0 <= min(CHASE_Y1, WIRE_POST_Y), (
    "the wire slot spans Y %.1f..%.1f, outside the chase/post window %.1f..%.1f"
    % (WIRE_SLOT_Y_C - WIRE_SLOT_W / 2.0, WIRE_SLOT_Y_C + WIRE_SLOT_W / 2.0,
       CHASE_Y0, min(CHASE_Y1, WIRE_POST_Y)))


# CIRCUIT.md: "Terminals provide NO strain relief — a tugged cable pulls out of
# the clamp or snaps at it. The printed shroud needs a cable-tie anchor."
#
# ⚠ THERE IS NO ANCHOR AT THE MOMENT, and that is worth saying plainly rather
# than letting the absence pass as a decision. It was a 14 mm buttress rib
# first, then a pair of diamond tie slots through the bay floor; the slots are
# gone at the user's request and nothing replaced them. What the design still
# has is the wire slot above, which the battery pair threads through a 3 mm
# plate and turns 90 degrees against -- a bend through a close-fitting hole is
# real relief for THAT pair, and it is the pair carrying 7.5 A.
#
# It is not relief for the leads that arrive down the chase from the tank side
# (the level sensor, the joystick), and those still land straight on a terminal
# clamp. A tie around the bundle where it leaves the chase, anchored to anything
# at all, would close it.


def _slab(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("YZ").workplane(offset=min(x0, x1))
            .center((y0 + y1) / 2.0, (z0 + z1) / 2.0)
            .rect(y1 - y0, z1 - z0).extrude(abs(x1 - x0)))


def pose_board(solid):
    """Board into the bay: +X -> -Y, +Y -> +Z, +Z -> -X.

    +Y to +Z is the one that matters — it puts the board's -Y edge, which is
    where every power terminal sits, at the BOTTOM of the bay, so the cables
    leave downward through the open edge. A proper rotation, not a mirror:
    (-Y) x (+Z) = -X, which is where +Z lands.

    PLACED BY THE BOARD'S OWN ORIGIN, NOT BY ITS BOUNDING BOX. The KiCad origin
    is the laminate's centre on its underside, so after the rotation a single
    translate puts the laminate exactly where BOARD_X0, PCB_Y_C and PCB_Z_C say
    it is -- which is where _hole_points() drills, where the standoff bosses
    stand and where pcb_screws() starts.

    It used to centre the BOUNDING BOX instead, and the bounding box is not the
    board. It is the board plus whatever hangs off it, and two things do:

      * the ESP32's ANTENNA overhangs the +X edge by 4.12 mm, on purpose --
        elec/main.py asserts it must. Centring the box therefore pushed the
        laminate 2.06 mm toward +Y, so the solid sat 2.06 off the holes the
        same file drills for it;
      * the through-hole LEAD TAILS stand 3.4 mm off the back. Centring put
        their TIPS on the standoff plane, which floated the laminate 3.4 mm
        clear of the bosses it is supposed to be bolted to -- x -202.0..-200.4
        where BOARD_X0/BOARD_X1 say -198.6..-197.0.

    Neither was catchable by anything here: a gap is not an overlap, and
    elec/cad_geom_check compares the solid to the routed board in the BOARD's
    own frame, where both agree perfectly. The one visible symptom was that
    _parts_height() read 20.4 -- the 3.4 of tails, counted as part height --
    which is why this file carries a comment correcting an earlier "guess" of
    17 mm. The guess was right.

    The tails now end 0.6 mm clear of the bay floor (4.0 standoff - 3.4), which
    is the clearance that mattered and the only thing the old pose got right."""
    r = (solid.rotate((0, 0, 0), (0, 1, 0), -90)
               .rotate((0, 0, 0), (1, 0, 0), 90))
    return r.translate((BOARD_X0, PCB_Y_C, PCB_Z_C))


def pcb_solid():
    return pose_board(_BOARDS.solid("main"))


# Cavity depth comes FROM THE POSED BOARD, not from a guess at the tallest
# part -- and it reads 17.0, which is what an earlier guess said and what this
# comment used to call wrong. It read 20.4 while pose_board was centring the
# bounding box, because that counted the 3.4 mm of lead tails on the BACK of
# the board as part height on the front.
def _parts_height():
    return BOARD_X1 - pcb_solid().val().BoundingBox().xmin


WALL_X = BOARD_X1 - _parts_height() - LID_GAP      # inner face of the lid


def _hole_points():
    """Board mounting holes, in world (y, z). FROM THE ROUTED BOARD."""
    out = []
    for hx, hy, _d in _BOARDS.holes("main"):
        out.append((PCB_Y_C - hx, PCB_Z_C + hy))      # board +X -> -Y, +Y -> +Z
    return out


# ONE screw, at the corner furthest from the +Y retention lip. There were four,
# one per corner, and three of them were holding a board that the lip and the Z
# stops now hold for nothing: four blind bores, four heat-set inserts and four
# screws, on a board that comes out for every firmware reflash until it has OTA.
#
# WHICH corner: -Y, because that is the end the lip does not reach, and the
# BOTTOM one, because the cable bundle leaves from the bottom edge and a tugged
# cable is the only real -X load this board sees. The screw belongs nearest the
# load. The hole at (110.5, 31) is also clear of the terminal group, which stops
# at y=123.7 -- the top -Y hole would have been just as clear, and the choice
# between them is the cable, not the geometry.
SCREW_HOLE = (0, 1)        # (index among _hole_points(): min y, min z)


def _screw_hole_point():
    """The one mounting hole that gets a screw: lowest y, lowest z."""
    return min(_hole_points(), key=lambda p: (p[0], p[1]))


def pcb_screws():
    """The one M4: board -> boss -> back plate, into a heat-set insert.

    Stops SEAL_T short of the back face. It used to run through it; see SEAL_T
    for why that was unnecessary here and what it cost."""
    out = []
    depth = (BOARD_X0 - BOARD_X1) + STANDOFF + BACK_T - SEAL_T
    for hy, hz in [_screw_hole_point()]:
        out.append(ScrewJoint(
            spec=M4, entry=(BOARD_X1, hy, hz), direction=(1.0, 0.0, 0.0),
            # M4x6, not x8. The insert ends 6.6 mm in, so the extra 2 mm of
            # screw bought no engagement -- it only forced the bore to within
            # 0.6 mm of the back face, which is no barrier at all. 6 mm gives
            # 4.4 mm of bite in a 5 mm insert (>1D) and leaves 1.5 mm of plate.
            length=6.0, insert_at=BOARD_X0 - BOARD_X1, end_at=depth,
            head_d=7.6, head_h=2.2))
    return out


# The dock's own axes, in world terms. battery_dock is modelled with z=0 the
# FLAT BACK (what goes against the host) and +Z the front that wraps the
# battery; +Y is the slide, the battery ENTERING at y=0 and travelling +Y to
# the latch. Both have to land correctly:
#
#   dock +Z -> world -X   front faces AWAY from the wood, battery outboard
#   dock +Y -> world -Z   battery enters at the TOP and slides DOWN, so gravity
#                         holds it against the latch rather than the latch
#                         holding it against gravity
#   dock +X -> world +Y   (forced: the frame has to stay right-handed)
_DOCK_AXES = {"+X": (0.0, 1.0, 0.0), "+Y": (0.0, 0.0, -1.0), "+Z": (-1.0, 0.0, 0.0)}


def _dock_oriented_raw() -> cq.Workplane:
    """The dock in its own frame (the transform is applied by _dock_to_world)."""
    return battery_dock


def _dock_oriented() -> cq.Workplane:
    return (battery_dock
            .rotate((0, 0, 0), (0, 1, 0), -90)
            .rotate((0, 0, 0), (1, 0, 0), -90))


def _dock_to_world(wp: cq.Workplane) -> cq.Workplane:
    """Put a solid modelled in the DOCK's own frame into world coordinates.

    Factored out so the dock and any cutter aimed at it share ONE transform.
    The translation is measured off the oriented DOCK's bounding box, never the
    passed solid's -- a cutter has a different bbox, and resolving the placement
    against it would land the cut somewhere else entirely while still looking
    like it tracked the part.
    """
    w = (wp.rotate((0, 0, 0), (0, 1, 0), -90)
           .rotate((0, 0, 0), (1, 0, 0), -90))
    bb = _dock_oriented().val().BoundingBox()
    return w.translate((BACK_X - bb.xmax,
                        DOCK_Y_C - (bb.ymin + bb.ylen / 2.0),
                        PCB_Z_C - (bb.zmin + bb.zlen / 2.0)))


def _dock_placed() -> cq.Workplane:
    """v1's Makita dock, oriented and dropped into the left bay."""
    return _dock_to_world(_dock_oriented_raw())


def _terminal_window() -> cq.Workplane:
    """The 643852-2 opening, re-cut through the housing's BACK PLATE.

    v1's dock already carries this pocket -- the lowercase-'t' plan of the
    connector, with its flange lips -- and the v2 housing unions that whole dock
    in. But the housing's own 3 mm back plate lands on the dock's mounting face
    and seals the pocket shut, so in v2 the terminal had nowhere to go in from.
    The connector is inserted from the REAR, against the wood, and its spade
    tabs and soldered leads have to come out on that side.

    Cut with battery_dock's OWN cutter through the shared dock transform, so it
    cannot drift from the pocket it is reopening. Everything that locates the
    connector -- the flange lips, the 0.2 mm install clearance, the mitred
    45 degree seats -- stays exactly as v1 measured it.
    """
    return _dock_to_world(terminal_cutter())


def terminal_placed():
    """The 643852-2 contact block, seated in the pocket _terminal_window()
    reopens. Same seat v1 validated (TERMINAL_PLACE/ROT in the dock frame, via
    the shared place_terminal helper), carried over by the shared dock
    transform. Returns None if the reference STEP is absent.

    It is here to be CHECKED, not drawn: a pocket that nothing is ever test-fit
    into is a pocket that agrees with itself.
    """
    from .dimensions import MAKITA_TERMINAL_STEP, TERMINAL_PLACE, TERMINAL_ROT_DEG
    from .helpers import import_step, place_terminal
    raw = import_step(MAKITA_TERMINAL_STEP)
    if raw is None:
        return None
    return _dock_to_world(place_terminal(raw, TERMINAL_ROT_DEG, TERMINAL_PLACE))


def _check_dock_orientation():
    """The dock's flat BACK must face the wood, and its slide must run DOWN.

    Asserted on the PLACED geometry, not on the rotation arguments, because the
    arguments are what a future edit would change. The back is the dock's one
    big planar face (~5265 mm2); if it is not against the frame with the body
    outboard of it, the battery is mounted into the frame. The first cut of this
    design had exactly that, and had the battery sliding UP to seat as well.
    """
    d = _dock_placed()
    bb = d.val().BoundingBox()
    best, best_a = None, 0.0
    for f in d.faces().vals():
        try:
            n = f.normalAt()
        except Exception:
            continue
        if f.Area() > best_a:
            best, best_a = (n, f.Center()), f.Area()
    n, c = best
    if not (n.x > 0.99 and abs(c.x - bb.xmax) < 0.5):
        raise AssertionError(
            "battery dock faces the wrong way: largest face (%.0f mm2) normal "
            "%s at x=%.1f, wanted +X at x=%.1f"
            % (best_a, (round(n.x, 2), round(n.y, 2), round(n.z, 2)), c.x, bb.xmax))
    if _DOCK_AXES["+Y"][2] >= 0:
        raise AssertionError("the battery must slide DOWN to seat")
    return best_a


_check_dock_orientation()


# ── HOW THE BOARD IS HELD: plastic on five sides, one screw on the sixth ───
# It used to be four M4s and nothing else, and the four were doing every job at
# once -- Y, Z, and holding the board down on its standoffs. That is three jobs
# a shape can do for free and one it cannot, so the shapes do three of them now
# and a single screw does the fourth.
#
#   -X (off its standoffs)  the +Y LIP, and the one screw at the far corner
#   +X (into the floor)     the four standoff bosses
#   +-Y                     the cavity walls, sized off the posed board
#   +-Z                     four Z STOPS on the floor, at the laminate's edges
#
# THE INSTALLATION IS A SLOT AND A ROTATE. Tilt the board, slide its +Y edge in
# under the lip, lower the -Y edge onto its standoffs, fit one screw. To take it
# out: screw out, slide 2 mm toward -Y until the edge clears the lip's tip, lift.
# That 2 mm is the antenna's clearance at the far wall, and it is the reason the
# lip reaches only RET_OVER past the board: reach further and the board is in
# for good.
#
# WHY THE LIP IS ROOTED 0.5 FROM THE BOARD AND NOT ON THE WALL. The lip's
# underside is a ceiling, and the housing builds in -X, so it has to be a 45
# degree ramp. A ramp rooted at the cavity wall would be 2.0 mm up by the time
# it reached the board's edge, and 2.0 mm of float is most of the LID_GAP. So
# the lip stands on its own 1.5 mm of rib first -- which has solid material
# under it the whole way, the board does not reach there -- and only ramps over
# the last stretch. The board floats RET_CLR + RET_OVER, not 2.3.
RET_CLR      = 0.3      # air over the laminate at the lip's root
RET_ROOT_GAP = 0.5      # lip root to the board's +Y edge
RET_OVER     = 2 * BEAD # 1.6 -- how far the lip reaches over the board
RET_LEN      = 18 * BEAD # 14.4 -- each lip's length along Z
# ⚠ THE RAMP USED TO END IN A KNIFE EDGE. The hook's far corner was the meeting
# of the 45 degree underside and the vertical back face: a 45 degree wedge
# tapering to nothing, which a nozzle cannot resolve -- it prints as a ragged
# tip a layer or two thick, in the one feature that holds the board down.
# RET_TIP_T of square section goes on the END of the ramp, so the extreme face
# is a flat land instead of a line. The ramp keeps its 45 degrees and its reach
# over the board is unchanged; the lip simply stands RET_TIP_T taller.
RET_TIP_T    = 2 * BEAD # 1.6 -- the blunt land at the hook's tip
RET_LIP_ZS   = (35.0, 70.0, 105.0)       # three of them, spread up the edge
RET_STOP_T   = 3 * BEAD # 2.4 -- Z stop thickness
RET_STOP_CLR = 0.3      # air between a Z stop and the laminate
# ⚠ A STOP THE HEIGHT OF THE BOARD IS NOT A STOP. These used to rise to exactly
# BOARD_X1, the laminate's top face, so a board lifted by its own thickness --
# 1.6 mm, which is nothing when the whole machine is being carried and shaken --
# cleared them and could walk along Z. They stand RET_STOP_OVER proud of the top
# face now, so the board has to come most of the way out of the bay before Z is
# free. There is room: the lid's inner face is 19.5 mm above the board top.
RET_STOP_OVER = 3 * BEAD  # 2.4 -- how far a Z stop reaches past the laminate

BOARD_Y1 = PCB_Y_C + BOARD_Y_MINUS                  # 199.0 — laminate's +Y edge
BOARD_Y0 = PCB_Y_C - BOARD_Y_MINUS                  # 104.0 — laminate's -Y edge
BOARD_Z0 = PCB_Z_C + _BBB.ymin                      # 25.0
BOARD_Z1 = PCB_Z_C + _BBB.ymax                      # 125.0
assert Y_PCB1 - BOARD_Y1 > RET_ROOT_GAP, "no room between the board and the wall"
BOARD_SLIDE_Y = (PCB_Y_C - BOARD_Y_PLUS) - Y_PCB0   # 2.0 — travel toward -Y,
                                                    # set by the antenna, not
                                                    # by the laminate
assert RET_OVER < BOARD_SLIDE_Y, (
    "the lip reaches %.1f over the board but it can only slide %.1f toward -Y: "
    "the board would go in and never come out" % (RET_OVER, BOARD_SLIDE_Y))

# Z stops go where the floor is free: clear of the cable chase, and clear of
# the lip. Two bands, one each side of the chase.
#
# DERIVED FROM THE CHASE, NOT TYPED BESIDE IT. These used to be a flat 10 mm in
# from each end of the board, which was true of the board the chase was then --
# and the chase is derived from the routed terminals (see _edge_connector_span),
# so re-laying the bottom edge moved it and left the +Y stop sitting over the
# opening. The assert below caught that, which is the system working; but an
# assert that fires every time the board is re-laid is a constant that should
# have been a derivation. A stop now takes what is left between the chase and
# the board's edge, up to the 10 mm it wants.
RET_STOP_MAX  = 10.0    # as long as a stop gets to be, where the floor allows
RET_STOP_MIN  =  4.0    # shorter than this is not a stop, it is a bump
RET_STOP_CHASE_GAP = 1.0                       # floor left either side of the chase
RET_STOP_YS = ((BOARD_Y0 + 1.0,
                min(BOARD_Y0 + 1.0 + RET_STOP_MAX, CHASE_Y0 - RET_STOP_CHASE_GAP)),
               (max(BOARD_Y1 - 1.0 - RET_STOP_MAX, CHASE_Y1 + RET_STOP_CHASE_GAP),
                BOARD_Y1 - 1.0))
for _y0, _y1 in RET_STOP_YS:
    assert _y1 <= CHASE_Y0 or _y0 >= CHASE_Y1, (
        "a Z stop at y %.1f..%.1f sits over the cable chase" % (_y0, _y1))
    # ⚠ AND IT HAS TO BE LONG ENOUGH TO BE ONE. Deriving the band from the chase
    # means a wide enough chase silently shrinks it to nothing, and a 0.5 mm rib
    # holding a 1.6 mm laminate down is not retention, it is a witness mark.
    assert _y1 - _y0 >= RET_STOP_MIN, (
        "a Z stop is only %.1f mm long (min %.1f): the cable chase at %.1f..%.1f "
        "has eaten the floor it needs. Narrow the connector group on the board's "
        "bottom edge, or move a stop to the board's Y edges"
        % (_y1 - _y0, RET_STOP_MIN, CHASE_Y0, CHASE_Y1))


def _pcb_lip() -> cq.Workplane:
    """The +Y retention lip: a rib on the wall side with a 45 deg hook."""
    y_root = BOARD_Y1 + RET_ROOT_GAP
    y_tip = BOARD_Y1 - RET_OVER
    x_root = BOARD_X1 - RET_CLR
    x_ramp = x_root - (y_root - y_tip)              # 45 deg, where the ramp ends
    x_tip = x_ramp - RET_TIP_T                     # ...and the land above it
    pts = [(FLOOR_X, Y_PCB1), (x_tip, Y_PCB1), (x_tip, y_tip),
           (x_ramp, y_tip), (x_root, y_root), (FLOOR_X, y_root)]
    out = None
    for z0 in RET_LIP_ZS:
        s = (cq.Workplane("XY").polyline(pts).close()
             .extrude(RET_LEN).translate((0.0, 0.0, z0)))
        out = s if out is None else out.union(s)
    return out


def _pcb_z_stops() -> cq.Workplane:
    """Four ribs on the bay floor, bounding the laminate's Z edges."""
    out = None
    for y0, y1 in RET_STOP_YS:
        for z_in, side in ((BOARD_Z0, -1), (BOARD_Z1, +1)):
            z_a = z_in + side * RET_STOP_CLR
            z_b = z_a + side * RET_STOP_T
            s = _slab(FLOOR_X, BOARD_X1 - RET_STOP_OVER,
                      y0, y1, min(z_a, z_b), max(z_a, z_b))
            out = s if out is None else out.union(s)
    return out


def housing() -> cq.Workplane:
    # back plate, full height so the screw flanges are part of it
    h = _slab(BACK_X, FLOOR_X, Y_PLATE0, Y_PLATE1, BACK_Z0, BACK_Z1)
    # PCB bay: a rectangular tube of wall, open outboard
    outer = _slab(FLOOR_X, WALL_X, Y_PCB0 - WALL, Y_OUTER, BAY_Z0, BAY_Z1)
    inner = _slab(FLOOR_X + BOOL_OVERSHOOT, WALL_X - BOOL_OVERSHOOT,
                  Y_PCB0, Y_PCB1, BAY_Z0 + WALL, BAY_Z1 - WALL)
    h = h.union(outer.cut(inner))
    # standoff bosses under the board's own holes
    for hy, hz in _hole_points():
        h = h.union(cq.Workplane("YZ").workplane(offset=BOARD_X0)
                    .center(hy, hz).circle(BOSS_D / 2.0).extrude(STANDOFF))
    # the board's own retention: a hooked lip on the +Y wall and four Z stops
    h = h.union(_pcb_lip()).union(_pcb_z_stops())
    # cable chase — the terminals faced a closed box before this. It spans the
    # whole bottom connector group (see _edge_connector_span).
    h = h.cut(_slab(FLOOR_X + BOOL_OVERSHOOT, WALL_X - BOOL_OVERSHOOT,
                    CHASE_Y0, CHASE_Y1,
                    BAY_Z0 - BOOL_OVERSHOOT, BAY_Z0 + WALL + BOOL_OVERSHOOT))
    # ...and the battery leads' way through the plate, under that same chase
    h = h.cut(_wire_slot())
    h = h.union(_dock_placed())
    # ...and reopen the connector pocket the back plate just sealed. AFTER the
    # union, necessarily: the plate is what closes it.
    h = h.cut(_terminal_window())
    # wood screws, in the flange bands clear of both bays
    for sy in SCREW_YS:
        for sz in SCREW_ZS:
            # from the INBOARD face outward through the plate: a YZ workplane
            # extrudes +X, so starting at BACK_X sent this into the wood and
            # left the plate un-pierced (gate: 4 x 15.9 mm2 of Ø4.5 ceiling).
            h = h.cut(cq.Workplane("YZ").workplane(offset=FLOOR_X - BOOL_OVERSHOOT)
                      .center(sy, sz).circle(WOOD_CLR_D / 2.0)
                      .extrude(BACK_T + 2 * BOOL_OVERSHOOT))
            csk = cq.Solid.makeCone(
                WOOD_CSK_D / 2.0, WOOD_CLR_D / 2.0,
                (WOOD_CSK_D - WOOD_CLR_D) / 2.0,
                cq.Vector(FLOOR_X, sy, sz), cq.Vector(1, 0, 0))
            h = h.cut(cq.Workplane(obj=csk))
    up = (-1.0, 0.0, 0.0)                      # the build direction
    for sj in pcb_screws():
        h = h.cut(sj.cutter(print_up=up))
    return h


# ── THE LID IS A SHOEBOX LID NOW ───────────────────────────────────────────
# It was a flanged plate butted onto the bay rim and held by four M4s into four
# Ø10 pillars that ran the bay's full depth. Three things were wrong with that:
# the seam was a straight butt joint directly under five gallons of water; the
# pillars ate the Z border the board needs for retention; and the four M4s were
# four blind holes in a part whose whole job is to come off.
#
# An earlier finding in this file said a skirt did not fit, and it measured
# honestly: inward there was -0.06 mm of room, outward there was nothing to lap
# onto because the bay filled the frame's depth to the last 1.4 mm. Both
# readings were of a housing whose dock was still carrying v1's dovetail ears.
# With those gone the bay has SKIRT_GAP of air outboard of each Y wall, and the
# Z walls always had open air above and below them.
#
# WHAT IT LAPS. The bay is a box standing 28.5 mm proud of the back plate. The
# skirt drops SKIRT_D over the outside of all four of its walls, which is the
# labyrinth the butt joint never was. It stops short of the plate on purpose:
# the lid seats on the bay RIM, not on the skirt's end, so the lap carries no
# load and its depth is free to choose.
# HOW DEEP, AND WHY NOT DEEPER. The skirt used to drop 20.0 while the BOSS
# reaches the full 25.1 to the back plate, so 5.1 x 16 mm of boss stuck out past
# the skirt's end with its underside hanging in open air -- a step that looks
# like an oversight and very nearly is.
#
# The two X limits are set by different jobs and cannot be the same number. The
# boss MUST touch the back plate: the screw clamps lid, plate and timber in one
# stack, and a gap there is a gap the lid rocks through. The skirt must NOT
# touch it: the lid seats on the bay RIM, and a skirt that bottoms out on the
# plate first holds the lid off the rim it is supposed to be sealing against.
#
# Measured: a test skirt is clear of the dock, the pack and the timber at 25.1,
# and fouls the back plate at 26.0. The rule is "the last whole bead that still
# leaves the lid a real gap to close on".
#
# ⚠ THAT RULE WAS WRITTEN DOWN AS ITS ANSWER, 30 * BEAD, AND THE ANSWER WENT
# STALE THE MOMENT A PART GOT SHORTER. The bay's depth is abs(WALL_X - FLOOR_X),
# and WALL_X comes from _parts_height() -- the tallest thing on the POSED BOARD.
# So the bay is only ever as deep as the tallest part needs, and the tallest
# parts here are the five terminal blocks. When their height stopped being a
# 17.0 mm guess and became the WJ500V drawing's measured 14.07, the bay went
# from 25.1 deep to 22.2 and a skirt frozen at 24.0 was suddenly 1.8 mm LONGER
# than the bay -- it would have bottomed on the back plate and held the lid off
# the one joint that is under five gallons of water. The assert below caught
# it, which is the gate working; hard-coding the answer is what made there be
# something to catch.
#
# So the rule computes. SKIRT_PLATE_MIN is the gap the lid closes on and is the
# thing actually being chosen; the depth falls out of it, to the bead.
SKIRT_PLATE_MIN = 1.0             # the lid must close on the RIM, not the skirt
SKIRT_D   = (int((abs(WALL_X - FLOOR_X) - SKIRT_PLATE_MIN) / BEAD)) * BEAD
                                  # how far it drops, to the whole bead. The
                                  # dock's +Y face is the other limit and the
                                  # skirt is clear of it at any depth <= 25.1.
BAY_Y0, BAY_Y1 = Y_PCB0 - WALL, Y_OUTER       # the bay's outer faces
LID_Y0 = BAY_Y0 - SKIRT_CLR - SKIRT_T
LID_Y1 = BAY_Y1 + SKIRT_CLR + SKIRT_T
LID_Z0 = BAY_Z0 - SKIRT_CLR - SKIRT_T
LID_Z1 = BAY_Z1 + SKIRT_CLR + SKIRT_T
assert LID_Y0 > Y_DOCK1, (
    "the -Y skirt lands on the dock: skirt at %.1f, dock ends at %.1f"
    % (LID_Y0, Y_DOCK1))
assert LID_Y1 <= L.FRAME_D, "the +Y skirt runs past the frame"
assert SKIRT_D < abs(WALL_X - FLOOR_X), "the skirt is deeper than the bay is tall"
# ⚠ AND IT HAS TO STAY SHORT OF THE PLATE BY A REAL GAP, not just by epsilon.
# The lid seats on the bay RIM. If the skirt reaches the back plate it lands
# there first and holds the lid off the rim -- the one joint under five gallons
# of water -- and nothing downstream would notice, because every part still
# fits and the install gate still sweeps clear.
SKIRT_PLATE_GAP = abs(WALL_X - FLOOR_X) - SKIRT_D
assert SKIRT_PLATE_GAP >= SKIRT_PLATE_MIN, (
    "the skirt ends %.2f mm from the back plate; the lid would close on its "
    "skirt instead of on the bay rim" % SKIRT_PLATE_GAP)

# ── The -Z skirt has to let the wiring out ─────────────────────────────────
# Every other side laps a closed wall. This one laps the wall the cable chase
# goes through, so a continuous skirt there would re-close the only opening
# this bay has. A window, spanning the chase and nothing more. The skirt stops
# 4.9 mm short of the back plate, so the battery slot and the 90 degree turn the
# leads make out of it are both inboard of the skirt's end and the window never
# has to grow to clear them.
LID_WIN_MARGIN = 1.5

# ── Lid retention ──────────────────────────────────────────────────────────
# ONE wood screw, plus the skirt. Not four M4s.
#
# The screw is the housing's own +Y +Z one at (y=191, z=145), which drives +X
# into the post: the lid reaches 28.5 mm inboard to the back plate and that one
# screw clamps lid, plate and timber together.
#
# WHY ONLY ONE. The other two screws are at y=19, 76 mm beyond the lid's edge.
# The +Y -Z one at z=5 is the obvious second and it clears the bay floor fine,
# but its boss is 16 mm wide on the y=191 screw line and the cable chase ends
# at y=187.6 -- so the boss would stand back across 4.6 mm of the chase's exit
# through the skirt window, which is the one opening this bay has. If the
# connector group ever moves off that corner it is worth revisiting.
#
# ONE IS ENOUGH, and the skirt is why. A single screw leaves the lid free to
# pivot about it, but the pivot has to tilt the skirt inside a SKIRT_CLR gap
# over a SKIRT_D lap -- 0.4 in 20, about 1.1 degrees. Over the 145 mm to the
# far corner that is 2.9 mm of outboard travel, against a 20 mm lap. It cannot
# get out.
#
# ── and the screw has to be able to GET there ──────────────────────────────
# The first version of this tab could not be screwed down. It reached the screw
# correctly and then filled the space in front of it: the tab sat 7 mm proud of
# its rib in Z, the step was ramped at 45 degrees to keep it printable, and the
# ramp put 8 mm of solid lid across the screw's axis at z=145. Nothing could
# reach the head, and the screw could not even be entered.
#
# So the retention is a BOSS with an axial bore, not a tab behind a ramp. The
# boss runs the lid's full depth; the bore is Ø9.5 -- wide enough to drop a
# flat-head wood screw down -- and steps to a countersink at the far end, where
# the head seats against the plate. A long bit reaches it through the same hole.
#
# THE RAMP IS GONE ENTIRELY, not relocated. The lid builds +X (see PRINT_ROT),
# so the boss rises off the lid plate as a vertical wall and needs no ramp
# where the plate is under it -- and the plate is simply carried up to the
# boss's top in that one Y band to make sure it is. 509 mm3 of plate, against
# an access path that did not exist.
LID_BOSS_W  = 16.0                            # Y width
LID_BOSS_H  = 16.0                            # Z height
LID_BORE_D  = WOOD_HEAD_D + 1.7               # 11.0 -- the head is Ø9.3 and
                                              # this is a hole you post a screw
                                              # down on the end of a driver. 9.5
                                              # cleared the head by 0.1 a side,
                                              # which is a fit, not an access
                                              # path.
LID_BOSS_Y  = SCREW_YS[1]                     # 191
LID_BOSS_Z  = SCREW_ZS[1]                     # 145
LID_BOSS_X1 = FLOOR_X                         # -193: the back plate's inboard face
LID_CSK_T   = 5 * BEAD                        # 4.0 -- material the countersink
                                              # lives in. Set BY the bore: a 45
                                              # deg cone from Ø11.0 to Ø4.5 is
                                              # 3.25 deep, so this is the first
                                              # whole number of beads that holds
                                              # it.
LID_UP      = (1.0, 0.0, 0.0)                 # build direction (see PRINT_ROT)
assert LID_BORE_D >= WOOD_HEAD_D + 1.0, (
    "a %.1f mm screw head needs more than %.1f mm of bore to be posted through "
    "it, not just to fit" % (WOOD_HEAD_D, LID_BORE_D))
assert LID_BOSS_H / 2.0 - LID_BORE_D / 2.0 >= 2.0, "under 2 mm of boss over the bore"
assert LID_BOSS_W / 2.0 - LID_BORE_D / 2.0 >= 2.0, "under 2 mm of boss beside the bore"
assert LID_CSK_T >= (LID_BORE_D - WOOD_CLR_D) / 2.0, "the countersink is deeper than its seat"


def _lid_plate() -> cq.Workplane:
    """The cover, plus the strip of it that carries the boss above the bay."""
    pl = _slab(WALL_X, WALL_X - LID_T, LID_Y0, LID_Y1, LID_Z0, LID_Z1)
    boss_z1 = LID_BOSS_Z + LID_BOSS_H / 2.0
    if boss_z1 > LID_Z1:                       # carry the plate up under the boss
        # ⚠ THE STRIP RUNS TO THE LID'S +Y EDGE, NOT THE BOSS'S. It used to stop
        # at the boss's own +Y face, which left the boss standing on a tab with
        # an 8.4 x 13.6 mm notch between it and the +Y skirt corner -- two walls
        # that look like they should meet, not meeting. They never did line up
        # and they never will: the boss is placed by the SCREW, which is on the
        # post centreline at y=191, and the skirt is placed by the BAY it laps,
        # whose outer face is at y=204. Nothing can bring those together.
        #
        # So the strip closes the gap instead of the boss moving. The boss ties
        # into the skirt corner, the notch goes, and the one feature that takes
        # the whole lid's retention load stops cantilevering off a tab.
        pl = pl.union(_slab(WALL_X, WALL_X - LID_T,
                            LID_BOSS_Y - LID_BOSS_W / 2.0, LID_Y1,
                            LID_Z1, boss_z1))
    return pl


def _lid_skirt() -> cq.Workplane:
    outer = _slab(WALL_X, WALL_X + SKIRT_D, LID_Y0, LID_Y1, LID_Z0, LID_Z1)
    inner = _slab(WALL_X - BOOL_OVERSHOOT, WALL_X + SKIRT_D + BOOL_OVERSHOOT,
                  BAY_Y0 - SKIRT_CLR, BAY_Y1 + SKIRT_CLR,
                  BAY_Z0 - SKIRT_CLR, BAY_Z1 + SKIRT_CLR)
    window = _slab(WALL_X - BOOL_OVERSHOOT, WALL_X + SKIRT_D + BOOL_OVERSHOOT,
                   CHASE_Y0 - LID_WIN_MARGIN, CHASE_Y1 + LID_WIN_MARGIN,
                   LID_Z0 - BOOL_OVERSHOOT, BAY_Z0 - SKIRT_CLR + BOOL_OVERSHOOT)
    return outer.cut(inner).cut(window)


def _lid_boss() -> cq.Workplane:
    """The one retention boss, from the lid plate inboard to the back plate."""
    return _slab(WALL_X, LID_BOSS_X1,
                 LID_BOSS_Y - LID_BOSS_W / 2.0, LID_BOSS_Y + LID_BOSS_W / 2.0,
                 LID_BOSS_Z - LID_BOSS_H / 2.0, LID_BOSS_Z + LID_BOSS_H / 2.0)


def _lid_screw_path() -> cq.Workplane:
    """Access bore -> countersink -> clearance, all on the screw's own axis."""
    y_c, z_c = LID_BOSS_Y, LID_BOSS_Z
    x_csk = LID_BOSS_X1 - LID_CSK_T                       # -196, head seat
    # the access bore, from the lid's outer face to the countersink mouth
    bore = (cq.Workplane("YZ").workplane(offset=WALL_X - LID_T - BOOL_OVERSHOOT)
            .center(y_c, z_c).circle(LID_BORE_D / 2.0)
            .extrude(x_csk - (WALL_X - LID_T) + BOOL_OVERSHOOT))
    # The cone's mouth is the ACCESS BORE's diameter, not the screw head's. At
    # Ø9.0 into a Ø9.5 bore the step left a 7.3 mm2 flat annulus facing the bed
    # -- the overhang gate's whole subject. Starting it at the bore removes the
    # step; the Ø9.3 head then seats 0.85 mm down the cone instead of at its
    # mouth, which is seat spent to buy a hole you can actually post a screw
    # through.
    csk = cq.Solid.makeCone(LID_BORE_D / 2.0, WOOD_CLR_D / 2.0,
                            (LID_BORE_D - WOOD_CLR_D) / 2.0,
                            cq.Vector(x_csk, y_c, z_c), cq.Vector(1, 0, 0))
    clr = (cq.Workplane("YZ").workplane(offset=x_csk)
           .center(y_c, z_c).circle(WOOD_CLR_D / 2.0)
           .extrude(LID_CSK_T + BOOL_OVERSHOOT))
    return bore.union(cq.Workplane(obj=csk)).union(clr)


def lid() -> cq.Workplane:
    return (_lid_plate().union(_lid_skirt()).union(_lid_boss())
            .cut(_lid_screw_path()))


PRINT_ROT = {
    # Stand on the back face (the one against the wood) and build OUTBOARD.
    # +90, not -90: rotating about +Y by +90 maps x -> -z, so the back face at
    # the LEAST negative x ends up lowest. At -90 it is the lid side that lands
    # on the plate and the whole part prints upside down, cantilevered on its
    # bay walls.
    "v2_housing": ((0, 1, 0), 90),
    # The LID goes the other way: -90 maps world +X to build UP, so the plate
    # lands face-down on the bed and the retention rib rises off it as a
    # vertical wall. At +90 (what it inherited while it was a plain plate) the
    # rib prints first and the whole 105 x 128 plate cantilevers off its top.
    "v2_housing_lid": ((0, 1, 0), -90),
}


def _build() -> None:
    from cadkit.cq_colors import color
    from cadkit.freecad import show
    from cadkit.step_export import export_step, print_pose
    from . import plumbing as P
    asm = cq.Assembly()
    for i, (nm, _L, solid) in enumerate(L.pieces()):
        tint = "#8B5A2B" if nm.startswith("plank") else "#A0724A"
        asm.add(solid, name="%s_%d" % (nm, i), color=color(tint))
    asm.add(housing(), name="housing", color=color("#6a8fb5"))
    asm.add(lid(), name="housing_lid", color=color("#8fb56a"))
    asm.add(pcb_solid(), name="pcb", color=color("#2f7d4f"))
    asm.add(F._pump_placed(-1), name="pump_a", color=color("slategray"))
    asm.add(F._pump_placed(+1), name="pump_b", color=color("#5a6b7a"))
    asm.add(F._elbows(), name="fittings", color=color("#c8a24a"))
    asm.add(L.tank(), name="tank_viz", color=color("#9fd4e8", alpha=0.35))
    for name, pts in P.routes():
        tint = "#b03030" if name.startswith("tank") else "#30a050"
        asm.add(P.run(pts), name=name, color=color(tint, alpha=0.85))
    for nm, part in (("v2_housing", housing()), ("v2_housing_lid", lid())):
        posed = print_pose(part, PRINT_ROT[nm])
        export_step(posed, str(F.OUT / (nm + ".step")))
        bb = posed.val().BoundingBox()
        print("%-16s print pose %6.1f x %6.1f x %6.1f mm  (bed 255)"
              % (nm, bb.xlen, bb.ylen, bb.zlen))
    out = str(F.OUT / "assembly_v2.step")
    asm.save(out, mode="default")
    print("wrote", out)
    show(out)


if __name__ == "__main__":
    _build()
