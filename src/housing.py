"""The one printed part: battery mount + PCB case, plus a lid.

Everything else is lumber or bought. This bolts to the outer face of the
frame's two -X posts and carries the Makita dock and the main board side by
side along Y.

WHY THE TWO BAYS SIT WHERE THEY DO
----------------------------------
The frame is 210 deep and that is the whole budget:

    3  outer wall
  100.6  battery dock (its across-slide dimension)
    3  divider
   99  PCB cavity (the 95 mm board + 2 mm clearance a side)
    3  outer wall
  ----
  208.6     with 1.4 to spare

That is where the board's 95 mm came from — it is the leftover, not a choice.
elec/main.py asserts the same arithmetic from the other end so the two cannot
drift.

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
DOCK_W  = 100.6
PCB_W   = 95.0
PCB_CLR = 2.0
Y_WALL0 = 0.0
Y_DOCK0 = Y_WALL0 + WALL                              # 3
Y_DOCK1 = Y_DOCK0 + DOCK_W                            # 103.6
Y_PCB0  = Y_DOCK1 + WALL                              # 106.6
Y_PCB1  = Y_PCB0 + PCB_W + 2 * PCB_CLR                # 205.6
Y_OUTER = Y_PCB1 + WALL                               # 208.6
assert Y_OUTER <= L.FRAME_D, (
    "housing is %.1f deep; the frame is %.1f" % (Y_OUTER, L.FRAME_D))

PCB_Y_C = (Y_PCB0 + Y_PCB1) / 2.0
PCB_Z_C = 75.0

# ── Z layout ────────────────────────────────────────────────────────────────
PCB_L      = 100.0
# The bay is taller than the board needs, and that is deliberate: the LID has
# to screw into something, and there is no room for pillars inside the board's
# own footprint (the board fills the bay in Y, which is the tight axis). So the
# spare goes into Z, where there is plenty, giving an 11 mm border above and
# below the board for the four lid pillars. Putting them in the corners instead
# collided with the board's own M4s -- 4 x 10 mm2 of flat ceiling where the
# corner bore clipped a pillar.
BAY_BORDER = 11.0
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

# ── Cable exit and strain relief ────────────────────────────────────────────
# The bay was a closed rectangular tube: four power terminals sat on the board's
# bottom edge with NO WAY OUT. The housing could not be wired.
#
# One chase, not a hole per connector, and it faces DOWN. CIRCUIT.md counts an
# opening as a water path ("a connector is a water-ingress path on an outdoor
# machine") and the tank sits directly above at z=208, so nothing opens upward —
# the level sensor's lead leaves through this chase too and climbs outside.
#
# It lands between J3 and J4, the middle of the bottom connector group, which is
# the shortest internal gather. 134 is forced: the lid pillar at y=125.1 is Ø10
# through the full depth, so a chase any lower in Y is split in two by it.
CHASE_Y0, CHASE_Y1 = 134.0, 158.0
# CIRCUIT.md: "Terminals provide NO strain relief — a tugged cable pulls out of
# the clamp or snaps at it. The printed shroud needs a cable-tie anchor." The
# shroud is gone; this is that anchor. A rib on the back plate's OUTBOARD face,
# set below the bay floor, with the gap between the two taking the tie.
#
# It is a rib and not a bar across the chase because of the build direction
# (-X). A member spanning the chase in Y lands on the bottom wall's cut edges,
# which makes it a 28.5 mm cantilever of 4 x 3 section loaded across the layers
# — 10 N at the tip is already 51 MPa in PCTG. Fused flat to the plate instead,
# the tie load goes in as shear over 32 mm of weld, and the rib starts at build
# height 3 directly on top of plate that is already there, so it overhangs
# nothing.
TIE_T   = BAY_Z0                             # 11 — up to the bay floor
TIE_D   = 14.0                               # how far it stands off the plate
TIE_Y0, TIE_Y1 = CHASE_Y0 - 4.0, CHASE_Y1 + 4.0
# A tie has to pass THROUGH the rib — you cannot loop one around a block that
# is fused to the plate along its whole length, which is what the rib would be
# without this. The hole runs in Y, across the build, so it is a DIAMOND and
# not a rectangle: a rectangular slot across the build has a flat roof, and a
# 10 mm flat roof is the exact defect this project's overhang gate exists to
# catch (it has caught four of them already). A diamond's roof is two planes
# at 31 degrees off the build axis, which self-supports.
TIE_SLOT_HX = 5.0                            # half-length along the build (X)
TIE_SLOT_HZ = 3.5
TIE_SLOT_OFF = TIE_D / 2.0 + 0.5             # centred in the rib, 2.5 mm walls
TIE_SLOT_Z  = (TIE_T - 1.0) / 2.0 + 1.0

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


def _lid_bosses_xy():
    """Four pillars in the Z border, clear of the board AND of its four M4s."""
    zs = (BAY_Z0 + WALL + 5.0, BAY_Z1 - WALL - 5.0)
    ys = (PCB_Y_C - 31.0, PCB_Y_C + 31.0)
    return [(y, z) for z in zs for y in ys]


def lid_screws():
    out = []
    for hy, hz in _lid_bosses_xy():
        out.append(ScrewJoint(
            spec=M4, entry=(WALL_X - LID_T, hy, hz), direction=(1.0, 0.0, 0.0),
            length=12.0, insert_at=LID_T,
            # Through the boss but NOT out the back face: stops SEAL_T short.
            end_at=BACK_X - (WALL_X - LID_T) - SEAL_T,
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
                        Y_DOCK0 - bb.ymin,
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


def housing() -> cq.Workplane:
    # back plate, full height so the screw flanges are part of it
    h = _slab(BACK_X, FLOOR_X, Y_WALL0, Y_OUTER, BACK_Z0, BACK_Z1)
    # PCB bay: a rectangular tube of wall, open outboard
    outer = _slab(FLOOR_X, WALL_X, Y_PCB0 - WALL, Y_OUTER, BAY_Z0, BAY_Z1)
    inner = _slab(FLOOR_X + BOOL_OVERSHOOT, WALL_X - BOOL_OVERSHOOT,
                  Y_PCB0, Y_PCB1, BAY_Z0 + WALL, BAY_Z1 - WALL)
    h = h.union(outer.cut(inner))
    # standoff bosses under the board's own holes
    for hy, hz in _hole_points():
        h = h.union(cq.Workplane("YZ").workplane(offset=BOARD_X0)
                    .center(hy, hz).circle(BOSS_D / 2.0).extrude(STANDOFF))
    # lid bosses
    for hy, hz in _lid_bosses_xy():
        h = h.union(cq.Workplane("YZ").workplane(offset=WALL_X)
                    .center(hy, hz).circle(BOSS_D / 2.0)
                    .extrude(abs(WALL_X - FLOOR_X)))
    # cable-tie rib, a buttress on the plate from the ground to the bay floor.
    # It goes on BEFORE the chase is cut, so the chase trims it. Unioned after,
    # it roofed the 0.5 mm the chase's own overshoot takes out of the back plate
    # — 24 x 0.5 mm of flat ceiling, which the overhang gate caught.
    h = h.union(_slab(FLOOR_X, FLOOR_X - TIE_D, TIE_Y0, TIE_Y1, 0.0, TIE_T))
    # cable chase — the terminals faced a closed box before this
    h = h.cut(_slab(FLOOR_X + BOOL_OVERSHOOT, WALL_X - BOOL_OVERSHOOT,
                    CHASE_Y0, CHASE_Y1,
                    BAY_Z0 - BOOL_OVERSHOOT, BAY_Z0 + WALL + BOOL_OVERSHOOT))
    # ...with a diamond tie slot bored through it along Y
    dia = (cq.Workplane("XZ").workplane(offset=-TIE_Y1)
           .center(FLOOR_X - TIE_SLOT_OFF, TIE_SLOT_Z)
           .polyline([(TIE_SLOT_HX, 0.0), (0.0, TIE_SLOT_HZ),
                      (-TIE_SLOT_HX, 0.0), (0.0, -TIE_SLOT_HZ)]).close()
           .extrude(TIE_Y1 - TIE_Y0))
    h = h.cut(dia)
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
    for sj in pcb_screws() + lid_screws():
        h = h.cut(sj.cutter(print_up=up))
    return h


# ── WHY THERE IS NO PERIMETER SKIRT ON THE LID ─────────────────────────────
# Asked for (a shoebox lid lapping the bay rim, to break the straight seam the
# tank drips onto) and it does not fit. Measured, both ways it could be built:
#
#   PLUG INWARD, skirt inside the cavity: the board PLUS its parts spans
#   y 106.5..205.7 against cavity walls at 106.6..205.6 -- a gap of -0.06 mm.
#   There is not room for a skirt of any thickness on either y edge. The z
#   edges have 11.00 mm each, but a skirt on two opposite edges is not a lap,
#   it is a pair of fins, and it seals nothing the butt joint did not.
#
#   LAP OUTWARD, skirt over the housing's outside: there is nothing to lap
#   onto. The outboard face only exists over the bay footprint -- above z=139
#   and below z=11 the housing is back plate only (x -193..-190), so a skirt
#   there would hang in open air. -y is the dock bay, not an outer face.
#
# So the lap needs the bay narrowed or the housing grown, and both move the
# board arithmetic that section "WHY THE TWO BAYS SIT WHERE THEY DO" above
# fixes from the frame's 210 mm. That is a bigger decision than a lid detail
# and it is the user's to make, so the lid stays a flanged plate for now and
# the retention tab below is what changed.

# ── Lid retention tab: the lid reaches the +y +z wood screw ─────────────────
# User's call. The lid was a loose plate held only by its four M4s; it now runs
# up past the bay and inboard to the wood screw at (y=191, z=145), which faces
# +X into the post, so that one screw clamps the lid as well as the housing.
#
# The reach is 28.5 mm, because the flange band above the bay is BACK PLATE
# ONLY -- measured x -193..-190 at z>139, with open air inboard of it. So the
# tab bears on the back plate's INBOARD face and the screw passes through tab,
# plate and into the wood.
#
# THE 45 IS NOT DECORATION. The lid prints plate-down (see PRINT_ROT below), so
# world +X is build UP and the rib rises off the plate as a vertical wall. The
# tab is taller than the rib -- it has to be, to cover a screw at z=145 with a
# rib that must stay BELOW z=145 or the bolt would have to bore 18 mm of rib
# lengthwise instead of 3 mm of tab. That step would be a flat ceiling of
# 7 x 14 mm at n.z = -1.00, so the rib ramps up to the tab at exactly 45.
LID_RIB_W  = 14.0                 # y width of rib + tab
LID_RIB_Z1 = 143.0                # rib top: under the screw at 145
LID_TAB_Z1 = 150.0                # tab top = the housing's own top
LID_TAB_T  = 3.0                  # tab thickness in X
LID_TAB_X1 = FLOOR_X              # -193: the back plate's inboard face
LID_UP     = (1.0, 0.0, 0.0)      # build direction for the lid (see PRINT_ROT)


def _lid_tab() -> cq.Workplane:
    y_c = SCREW_YS[1]                          # 191 -- the +y screw line
    x_out = WALL_X - LID_T                     # -224.5, the lid's outer face
    ramp = LID_TAB_Z1 - LID_RIB_Z1             # rise == run -> 45 deg
    pts = [(x_out, BAY_Z1), (x_out, LID_RIB_Z1),
           (LID_TAB_X1 - LID_TAB_T - ramp, LID_RIB_Z1),
           (LID_TAB_X1 - LID_TAB_T, LID_TAB_Z1),
           (LID_TAB_X1, LID_TAB_Z1), (LID_TAB_X1, BAY_Z1)]
    assert ramp > 0, "tab must stand proud of the rib or there is no step"
    return (cq.Workplane("XZ").polyline(pts).close()
            .extrude(-LID_RIB_W)               # XZ extrude(-L) lands at +Y
            .translate((0.0, y_c - LID_RIB_W / 2.0, 0.0)))


def _lid_tab_screw() -> cq.Workplane:
    """Clearance + countersink for the wood screw, through the tab only."""
    y_c, z_c = SCREW_YS[1], SCREW_ZS[1]
    x0 = LID_TAB_X1 - LID_TAB_T
    clr = (cq.Workplane("YZ").workplane(offset=x0 - BOOL_OVERSHOOT)
           .center(y_c, z_c).circle(WOOD_CLR_D / 2.0)
           .extrude(LID_TAB_T + 2 * BOOL_OVERSHOOT))
    csk = cq.Solid.makeCone(WOOD_CSK_D / 2.0, WOOD_CLR_D / 2.0,
                            (WOOD_CSK_D - WOOD_CLR_D) / 2.0,
                            cq.Vector(x0, y_c, z_c), cq.Vector(1, 0, 0))
    return clr.union(cq.Workplane(obj=csk))


def lid() -> cq.Workplane:
    l = _slab(WALL_X, WALL_X - LID_T, Y_PCB0 - WALL, Y_OUTER, BAY_Z0, BAY_Z1)
    l = l.union(_lid_tab()).cut(_lid_tab_screw())
    for sj in lid_screws():
        l = l.cut(sj.cutter(print_up=LID_UP))
    return l


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
