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

The board does NOT grow into the slack. It is routed at 95 x 100 and JLCPCB's
cheapest tier stops at 100 x 100, so the price tier is the binding constraint
now, not the frame. What the slack buys is the lid: a shoebox skirt needs air
outboard of the bay walls on all four sides, and at 1.4 mm there was none.

HOW THE CABLES GET OUT
----------------------
They could not, until they did: the bay was a closed rectangular tube with four
power terminals facing a wall. There is now ONE down-facing chase through the
bay floor at y 134..158, and a buttress rib under it with a tie slot through it
so the bundle has something to be relieved against. Down-facing because the tank
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

# ── Where it mounts ─────────────────────────────────────────────────────────
BACK_X  = -(L.POST_X + L.BEAM / 2.0)      # -190: the posts' outer face
WALL    = 3.0
BACK_T  = 3.0

# ── Y layout (see the docstring's budget) ───────────────────────────────────
# MEASURED off the dock, not typed. It was 100.6 -- the ear-to-ear width of
# v1's dovetail joinery -- and when the ears came off (they hosted a joint v2
# does not have) a typed copy would have gone on reserving 28.6 mm of the
# frame's 210 for material that is no longer there.
DOCK_W  = battery_dock.val().BoundingBox().xlen        # 72.0
PCB_W   = 95.0
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
SKIRT_GAP = 6.0                                       # air outboard of each bay wall
Y_PCB1  = L.FRAME_D - SKIRT_GAP - WALL                # 201
Y_PCB0  = Y_PCB1 - (PCB_W + 2 * PCB_CLR)              # 102
Y_OUTER = Y_PCB1 + WALL                               # 204 — the bay's +Y face
assert Y_OUTER + SKIRT_GAP <= L.FRAME_D, (
    "the +Y skirt runs %.1f past the frame's %.1f"
    % (Y_OUTER + SKIRT_GAP, L.FRAME_D))
assert Y_PCB0 - WALL - SKIRT_GAP >= Y_DOCK1, (
    "the -Y skirt lands on the dock: bay wall at %.1f, dock ends at %.1f"
    % (Y_PCB0 - WALL, Y_DOCK1))

# The back plate is the full frame depth, NOT the bays' extent. It carries the
# four wood screws and L.POST_YS puts one pair at y=191 -- 11 mm outboard of the
# bay. While the plate ended where the bay ended it only just reached them, and
# once the bay moved it would not have.
Y_PLATE0, Y_PLATE1 = 0.0, L.FRAME_D

PCB_Y_C = (Y_PCB0 + Y_PCB1) / 2.0
PCB_Z_C = 75.0

# ── Z layout ────────────────────────────────────────────────────────────────
PCB_L      = 100.0
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
#     at z=145 and the boss needs 2 mm of lid under a Ø9.5 bore, which puts the
#     boss's underside at 138.25. At BAY_BORDER=11 the bay wall reached 139 and
#     the two interpenetrated -- 912 mm3, which the overlap gate caught.
BAY_BORDER = 8.0
BAY_Z0     = PCB_Z_C - (PCB_L / 2.0 + BAY_BORDER + WALL)  # 11
BAY_Z1     = PCB_Z_C + (PCB_L / 2.0 + BAY_BORDER + WALL)  # 139
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
WOOD_CLR_D, WOOD_CSK_D = 4.5, 9.0


# ── PCB stack, measured outboard from the back plate's inner face ───────────
FLOOR_X    = BACK_X - BACK_T                 # -193
STANDOFF   = 4.0
BOARD_T    = 1.6
LID_GAP    = 2.5
BOSS_D     = 10.0
BOARD_X0   = FLOOR_X - STANDOFF              # -197 board underside
BOARD_X1   = BOARD_X0 - BOARD_T              # -198.6 board top (parts face -X)
LID_T      = 3.0
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

# CIRCUIT.md: "Terminals provide NO strain relief — a tugged cable pulls out of
# the clamp or snaps at it. The printed shroud needs a cable-tie anchor."
#
# THE ANCHOR IS CUT, NOT BUILT. It used to be a 14 mm buttress rib standing off
# the back plate below the chase, with a tie slot bored through it — 3.4 cm3 of
# added material whose whole job was to give a cable tie something to pass
# through. A pair of slots through the bay floor does the same job and adds
# nothing: the tie goes up through one, over the bundle, down the other, and
# cinches it against the floor's underside, which is the face the bundle runs
# along anyway. The rib also stood exactly where the lid's -Z skirt now drops.
#
# DIAMOND slots, for the same reason the rib's was a diamond: they are cut
# through a 3 mm floor that is PARALLEL to the build (the housing builds in -X),
# so a rectangular slot presents a flat 3 x 3 ceiling where the floor closes
# back over it. A diamond's roof is two planes 17 degrees off the build axis.
#
# They sit at the floor's INBOARD end, in the 8.5 mm of it the lid's skirt does
# not reach (SKIRT_D), so the tie and the bundle it holds are never pinched
# between the floor and the skirt -- and the skirt's wiring window only has to
# clear the chase.
TIE_SLOT_HX = 3.0                            # half-length along the build (X)
TIE_SLOT_HY = 2.0                            # half-width across it; 34 deg roof
TIE_SLOT_OFFSET = 5.0                        # chase edge -> slot centre
TIE_SLOT_YS = (CHASE_Y0 - TIE_SLOT_OFFSET, CHASE_Y1 + TIE_SLOT_OFFSET)
TIE_SLOT_X  = FLOOR_X - 4.25                 # -197.25, mid-way in that strip


def _slab(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("YZ").workplane(offset=min(x0, x1))
            .center((y0 + y1) / 2.0, (z0 + z1) / 2.0)
            .rect(y1 - y0, z1 - z0).extrude(abs(x1 - x0)))


def pose_board(solid):
    """Board into the bay: +X -> -Y, +Y -> +Z, +Z -> -X.

    +Y to +Z is the one that matters — it puts the board's -Y edge, which is
    where every power terminal sits, at the BOTTOM of the bay, so the cables
    leave downward through the open edge. A proper rotation, not a mirror:
    (-Y) x (+Z) = -X, which is where +Z lands."""
    r = (solid.rotate((0, 0, 0), (0, 1, 0), -90)
               .rotate((0, 0, 0), (1, 0, 0), 90))
    bb = r.val().BoundingBox()
    return r.translate((BOARD_X0 - bb.xmax,
                        PCB_Y_C - (bb.ymin + bb.ylen / 2.0),
                        PCB_Z_C - (bb.zmin + bb.zlen / 2.0)))


def pcb_solid():
    return pose_board(_BOARDS.solid("main"))


# Cavity depth comes FROM THE POSED BOARD, not from a guess at the tallest
# part. The guess was 17 mm (the 5.08 terminal blocks); the board actually
# stands 20.4 proud, so a lid set from the guess closed 1 mm INTO the parts.
def _parts_height():
    return BOARD_X1 - pcb_solid().val().BoundingBox().xmin


WALL_X = BOARD_X1 - _parts_height() - LID_GAP      # inner face of the lid


def _hole_points():
    """Board mounting holes, in world (y, z). FROM THE ROUTED BOARD."""
    out = []
    for hx, hy, _d in _BOARDS.holes("main"):
        out.append((PCB_Y_C - hx, PCB_Z_C + hy))      # board +X -> -Y, +Y -> +Z
    return out


def pcb_screws():
    """One M4 per corner, board -> boss -> back plate, into a heat-set insert.

    Stops SEAL_T short of the back face. It used to run through it; see SEAL_T
    for why that was unnecessary here and what it cost."""
    out = []
    depth = (BOARD_X0 - BOARD_X1) + STANDOFF + BACK_T - SEAL_T
    for hy, hz in _hole_points():
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


def _tie_slots() -> cq.Workplane:
    """Two diamond slots through the bay floor, one each side of the chase.

    A tie passes up through one, over the bundle and down the other, cinching
    it against the floor's underside. Diamonds because the floor is parallel to
    the build (-X) and a rectangular slot would close over a flat ceiling."""
    cut = None
    for y_c in TIE_SLOT_YS:
        d = (cq.Workplane("XY").workplane(offset=BAY_Z0 - BOOL_OVERSHOOT)
             .center(TIE_SLOT_X, y_c)
             .polyline([(TIE_SLOT_HX, 0.0), (0.0, TIE_SLOT_HY),
                        (-TIE_SLOT_HX, 0.0), (0.0, -TIE_SLOT_HY)]).close()
             .extrude(WALL + 2 * BOOL_OVERSHOOT))
        cut = d if cut is None else cut.union(d)
    return cut


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
    # cable chase — the terminals faced a closed box before this. It spans the
    # whole bottom connector group (see _edge_connector_span).
    h = h.cut(_slab(FLOOR_X + BOOL_OVERSHOOT, WALL_X - BOOL_OVERSHOOT,
                    CHASE_Y0, CHASE_Y1,
                    BAY_Z0 - BOOL_OVERSHOOT, BAY_Z0 + WALL + BOOL_OVERSHOOT))
    # ...flanked by two diamond tie slots through the floor: the strain relief
    h = h.cut(_tie_slots())
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
SKIRT_T   = 3.0
SKIRT_CLR = 0.4                   # air between skirt and bay wall, per side
SKIRT_D   = 20.0                  # how far it drops. The dock's +Y face is the
                                  # limit and it is 6.3 mm clear at this depth.
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

# ── The -Z skirt has to let the wiring out ─────────────────────────────────
# Every other side laps a closed wall. This one laps the wall the cable chase
# goes through, so a continuous skirt there would re-close the only opening
# this bay has. A window, spanning the chase and nothing more: the tie slots
# are deliberately INBOARD of SKIRT_D (see TIE_SLOT_X) so the strain relief
# stays under solid skirt and the window does not have to grow to clear it.
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
LID_BORE_D  = 9.5                             # the screw head is Ø9
LID_BOSS_Y  = SCREW_YS[1]                     # 191
LID_BOSS_Z  = SCREW_ZS[1]                     # 145
LID_BOSS_X1 = FLOOR_X                         # -193: the back plate's inboard face
LID_CSK_T   = 3.0                             # material the countersink lives in
LID_UP      = (1.0, 0.0, 0.0)                 # build direction (see PRINT_ROT)
assert LID_BORE_D > WOOD_CSK_D, (
    "a %.1f mm screw head will not pass a %.1f mm access bore"
    % (WOOD_CSK_D, LID_BORE_D))
assert LID_BOSS_H / 2.0 - LID_BORE_D / 2.0 >= 2.0, "under 2 mm of boss over the bore"
assert LID_BOSS_W / 2.0 - LID_BORE_D / 2.0 >= 2.0, "under 2 mm of boss beside the bore"
assert LID_CSK_T >= (LID_BORE_D - WOOD_CLR_D) / 2.0, "the countersink is deeper than its seat"


def _lid_plate() -> cq.Workplane:
    """The cover, plus the strip of it that carries the boss above the bay."""
    pl = _slab(WALL_X, WALL_X - LID_T, LID_Y0, LID_Y1, LID_Z0, LID_Z1)
    boss_z1 = LID_BOSS_Z + LID_BOSS_H / 2.0
    if boss_z1 > LID_Z1:                       # carry the plate up under the boss
        pl = pl.union(_slab(WALL_X, WALL_X - LID_T,
                            LID_BOSS_Y - LID_BOSS_W / 2.0,
                            LID_BOSS_Y + LID_BOSS_W / 2.0,
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
    # -- the overhang gate's whole subject. Starting it at Ø9.5 removes the step
    # and costs 0.25 mm of head seat on a 45 deg cone.
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
