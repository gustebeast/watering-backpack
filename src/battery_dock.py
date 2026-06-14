"""Makita 18V LXT battery dock — parametric CadQuery model.

The dock is a rectangular plate with two T-slot grooves cut into its
underside that capture the battery's slide rails, a latch notch for the
battery's spring-loaded button, and a rectangular pocket for the
Makita 643852-2 contact block.

Frame:
  • X = battery width (perpendicular to slide). Rail pair is symmetric about X=0.
  • Y = slide direction. The battery ENTERS at the y=0 end (the end with
    the front opening) and slides toward +Y until the latch clicks at
    y≈21; the y=90 end is the solid stop / mount-hole region. (Earlier
    sessions assumed entry from +Y — corrected per the user.)
  • Z = thickness. **Z=0 is the FLAT BACK** — the mounting face that goes
    against the host (wall / backpack housing). The +Z side (z=22, with the
    open pocket and side ribs) is the FRONT that fits around the battery —
    the battery engages from that side. (An earlier reading had this
    backwards; corrected per the user against the physical V4 mount.)

Dimensional reference: the Wiseone V4 community mount
(``references/makita_mount_v4.step``) — same family as the user's existing
Wiseone Printables design. We don't import that STEP; instead we read off
its dimensions and rebuild parametrically so we can tune fits, extend the
plate for backpack integration, and add features like the terminal pocket.

Validated against V4 with the oversize-overlap method (src/build.py
diagram stations): nominal battery fit shows ~0 overlap and the terminal
seats without interference. Use ``py -3.12 tools/inspect_step.py
references/makita_mount_v4.step`` to read off any further reference dims.
"""

from __future__ import annotations

import cadquery as cq

from .dimensions import (BOOL_OVERSHOOT, TERMINAL_PLACE,
                         DOVETAIL_ROOT_W, DOVETAIL_TIP_W, DOVETAIL_DEPTH,
                         DOVETAIL_X_OFF, DOVETAIL_END_STOP, DOVETAIL_CLR)


# ── Printability helper ──────────────────────────────────────────────────────
# Print orientation: the Z=0 (battery-slot) face sits on the build plate and
# the part grows toward +Z. Every horizontal downward-facing surface is then
# an overhang. We convert the worst ones to 45° ramps by subtracting (or
# reshaping with) triangular prisms that run along the slide (Y) axis.
def _xz_prism(pts, y0: float, y1: float) -> "cq.Workplane":
    """Triangular (or polygonal) prism: an X-Z section `pts` extruded along
    Y to span [y0, y1]. `pts` are (x, z) tuples in the XZ plane."""
    length = y1 - y0
    return (cq.Workplane("XZ").polyline(pts).close()
            .extrude(-length)                 # XZ extrude(-L) lands at Y in [0,L]
            .translate((0.0, y0, 0.0)))


# ── Plate envelope ───────────────────────────────────────────────────────────
# Outer block size, picked to match the V4 mount's bounding box. The
# backpack-integration extension (mounting flange, pump-side wrap, etc.)
# will grow this later; for now just the dock proper.
PLATE_X = 72.0     # battery-width direction
PLATE_Y = 90.0     # slide direction (battery enters from +Y end)
PLATE_Z = 22.0     # plate thickness (Z=0 face is bottom / battery-facing)


# ── Battery channel cut into the underside ───────────────────────────────────
# A pocket cut up from the bottom face (Z=0) into the plate, opening at the
# +Y end (battery slides in there) and closed at -Y (slide stop).
#
# Two-step profile so it forms the T-slot the rails ride in:
#   • Z = 0..CHANNEL_HAT_H : wider region — accepts the rail "hat" overhangs
#   • Z = CHANNEL_HAT_H..CHANNEL_TOTAL_H : narrower region — accepts the stem
#   • Z > CHANNEL_TOTAL_H : solid plate (no battery above this)
CHANNEL_HAT_H        = 5.0    # depth of the wider lower channel
CHANNEL_STEM_H       = 2.0    # extra depth of the narrower upper channel
CHANNEL_TOTAL_H      = CHANNEL_HAT_H + CHANNEL_STEM_H   # 7

# Y-axis extent of the channel. V4's T-slot is fully enclosed (closed
# on BOTH Y ends) — the battery's rails enter via the upper cavity
# rather than through a slot in an outer Y face. The HAT (lower step)
# is longer than the STEM (upper step) — V4 narrows the stem at the
# back so material above the catch-face stays solid.
CHANNEL_Y_NEAR       = 22.0   # closed -Y wall (shared by hat + stem)
HAT_Y_FAR            = 73.0   # +Y wall of the wider hat region
# Stem void ends exactly where the hat narrows (60.3) — NOT 5 mm short at 58.
# Ending short left a 2.3 mm wide-hat strip capped by solid (the "shoulder"
# overhang that OCC can't chamfer). Aligning them opens that strip into the
# stem void, removing the overhang; the battery still clears (the void only
# grows). The lips (hat±24 vs stem±22) are unchanged over y=22..60.3.
STEM_Y_FAR           = 60.3   # = HAT_BACK_NARROW_Y_START
HAT_LENGTH           = HAT_Y_FAR  - CHANNEL_Y_NEAR        # 51
STEM_LENGTH          = STEM_Y_FAR - CHANNEL_Y_NEAR        # 36

# X-axis extent of each channel level:
#   The HAT level is wide — spans most of the plate's interior.
#   The STEM level is narrower — only the central region between the rails.
HAT_X_INSET          = 12.0   # inset from each X side wall to the hat-channel edge
STEM_X_INSET         = 14.0   # narrower stem level inset further
HAT_WIDTH            = PLATE_X - 2 * HAT_X_INSET   # 48
STEM_WIDTH           = PLATE_X - 2 * STEM_X_INSET  # 44


# ── Lightening cavity (top half of the plate is mostly hollow) ───────────────
# Z-slicing the V4 reference shows its cross-section area drops from
# ~4,000 mm² below z=7 to ~1,800 mm² above z=7 — so V4 carries only a thin
# outer wall in the upper half. Without this cut, our parametric is ~71K mm³
# heavier than V4 (the dominant geometric error).
#
# The cavity is open at the +Y mouth (battery entry side) and closed at -Y
# (back wall) with a wall thickness of POCKET_WALL_BACK. X walls are
# POCKET_WALL_X each side. Z extent runs from the top of the rail channel
# (CHANNEL_TOTAL_H) all the way through the plate's top face.
POCKET_WALL_X     = 4.0    # X wall thickness (each side) - matches V4's outer rim
POCKET_WALL_NEAR  = 1.5    # thin lip at the closed (-Y) back end
POCKET_WALL_FAR   = 19.0   # thick wall at the open (+Y) mouth end - V4 keeps
                           # this region solid (mount-hole area + slide approach).
POCKET_X          = PLATE_X - 2 * POCKET_WALL_X                # 64
POCKET_Y_LENGTH   = PLATE_Y - POCKET_WALL_NEAR - POCKET_WALL_FAR  # 69.5


def _lightening_cutter() -> cq.Workplane:
    """Rectangular pocket from z=CHANNEL_TOTAL_H upward, sitting between a
    thin back-end lip and a thick mount-end wall (closed on BOTH Y ends).
    Matches V4's upper cavity layout: cavity at y=1.5..71, leaving the
    open-mouth side (y=71..90) solid for the slide approach + mount holes.

    Overshoot goes only UPWARD (above the plate top); we must NOT extend
    the cut below z=CHANNEL_TOTAL_H or we slice into the channel-roof
    material V4 keeps.
    """
    return (cq.Workplane("XY")
            .workplane(offset=CHANNEL_TOTAL_H)
            .box(POCKET_X, POCKET_Y_LENGTH,
                 PLATE_Z - CHANNEL_TOTAL_H + BOOL_OVERSHOOT,
                 centered=(True, False, False))
            .translate((0.0, POCKET_WALL_NEAR, 0.0)))


HAT_BACK_NARROW_Y_START  = 60.3      # Y where the hat narrows
HAT_BACK_NARROW_WIDTH    = 24.0      # X=24..48 in V4 frame (vs 48 mm at front)


def _hat_cutter() -> cq.Workplane:
    """Wider lower step of the T-slot pocket (cuts up from Z=0).
    V4 has a STEPPED hat — full width X[12..60] for the front portion and
    a narrower width X[24..48] at the back. The back shoulders carry
    the rail's hat ends where the slot needs to stop the battery."""
    front_y_len = HAT_BACK_NARROW_Y_START - CHANNEL_Y_NEAR     # 38.3
    back_y_len  = HAT_Y_FAR - HAT_BACK_NARROW_Y_START           # 12.7

    front = (cq.Workplane("XY")
             .workplane(offset=-BOOL_OVERSHOOT)
             .box(HAT_WIDTH, front_y_len,
                  CHANNEL_HAT_H + BOOL_OVERSHOOT,
                  centered=(True, False, False))
             .translate((0.0, CHANNEL_Y_NEAR, 0.0)))
    back = (cq.Workplane("XY")
            .workplane(offset=-BOOL_OVERSHOOT)
            .box(HAT_BACK_NARROW_WIDTH, back_y_len,
                 CHANNEL_HAT_H + BOOL_OVERSHOOT,
                 centered=(True, False, False))
            .translate((0.0, HAT_BACK_NARROW_Y_START, 0.0)))
    return front.union(back)


def _stem_cutter() -> cq.Workplane:
    """T-shaped stem cut: full-width stem at Y=22..58 + a narrow extension
    at Y=58..71 (X=24..48 = matches the narrowed hat-back). Without the
    narrow extension, ~512 mm³ of BLUE remains at the back of the cavity.
    """
    wide_stem = (cq.Workplane("XY")
                 .workplane(offset=CHANNEL_HAT_H)
                 .box(STEM_WIDTH, STEM_LENGTH,
                      CHANNEL_STEM_H + BOOL_OVERSHOOT,
                      centered=(True, False, False))
                 .translate((0.0, CHANNEL_Y_NEAR, 0.0)))
    # Narrow back extension — same X width as the hat narrow-back (24mm)
    # and same Z range as the stem (z=5..7).
    NARROW_STEM_Y_LEN = 71.0 - STEM_Y_FAR
    narrow_stem = (cq.Workplane("XY")
                   .workplane(offset=CHANNEL_HAT_H)
                   .box(HAT_BACK_NARROW_WIDTH, NARROW_STEM_Y_LEN,
                        CHANNEL_STEM_H + BOOL_OVERSHOOT,
                        centered=(True, False, False))
                   .translate((0.0, STEM_Y_FAR, 0.0)))
    return wide_stem.union(narrow_stem)


# ── Plate body ───────────────────────────────────────────────────────────────
# Built centred on the X axis (so the slide channels are symmetric about X=0)
# but with Y starting at 0 (the closed/back end of the dock).
#
# The pocket is applied as TWO SEPARATE cuts (not a union-then-cut) — strict
# STEP importers (FreeCAD GUI, Onshape) warn on the near-tangent boundary
# the union would leave behind when its two boxes overlap by BOOL_OVERSHOOT.
_plate = (cq.Workplane("XY")
          .box(PLATE_X, PLATE_Y, PLATE_Z,
               centered=(True, False, False)))

# ── Front-end opening ──────────────────────────────────────────────────────
# V4 has the upper cavity opened through the front face. The opening
# is L-shaped in the YZ cross-section:
#
#   • Front-lip-top strip:  Y=0..1.5,  Z=5.5..22 (removes the front-face
#     material above the 5.5 mm-tall front lip — V4 has no front face
#     above z=5.5)
#   • Forward main pocket:  Y=1.5..18, Z=7..22  (already covered by the
#     main lightening pocket — it starts at Y=POCKET_WALL_NEAR=1.5
#     and reaches into this region)
#
# So all we need to add as a separate cut is the front-lip-top strip;
# the rest is taken care of by the lightening pocket. Earlier I had this
# cut going Z=5.5..22 over Y=0..18, which over-removed a 1.5 mm slab in
# Y=1.5..18 / Z=5.5..7 (~1.5K mm³ that V4 keeps as the main cavity
# floor).
FRONT_LIP_HEIGHT       = 5.5     # z-top of the front lip (front face exists at z=0..5.5)
FRONT_LIP_THICKNESS    = 1.5     # y thickness of the front lip


def _front_opening_cutter() -> cq.Workplane:
    """Thin slab above the front lip — opens the upper cavity through
    the Y=0 face. Pairs with the main lightening pocket which already
    extends to Y=POCKET_WALL_NEAR=1.5."""
    return (cq.Workplane("XY")
            .workplane(offset=FRONT_LIP_HEIGHT)
            .box(POCKET_X,
                 FRONT_LIP_THICKNESS + 2 * BOOL_OVERSHOOT,
                 PLATE_Z - FRONT_LIP_HEIGHT + 2 * BOOL_OVERSHOOT,
                 centered=(True, False, False))
            .translate((0.0, -BOOL_OVERSHOOT, 0.0)))


# ── Back-end top recess (shallow tray) ──────────────────────────────────────
# V4 has a shallow recess on the TOP face at the back, 3 mm deep
# (z=19..22) and inset 9 mm from each X side and Y=72..86. Probably a
# clearance / counter-bore for mounting screw heads on the back of the
# dock. The +Z face at z=19 in V4 has this exact footprint.
TOP_RECESS_X         = 54.0     # = 72 - 2*9 inset
# Start 2 mm earlier than the recess proper (was 72.0) so the recess floor
# merges into the lightening pocket back wall instead of leaving a thin
# 1 mm wall at Y≈71-72 / Z=19-22 (X=±27). That wall isn't in V4 — flagged
# from the FreeCAD view by its corner verts (±27, 72, 19..22).
TOP_RECESS_Y_START   = 70.0
TOP_RECESS_Y_LENGTH  = 16.0     # 70..86 (end unchanged)
TOP_RECESS_Z_FLOOR   = 19.0


def _top_recess_cutter() -> cq.Workplane:
    return (cq.Workplane("XY")
            .workplane(offset=TOP_RECESS_Z_FLOOR)
            .box(TOP_RECESS_X, TOP_RECESS_Y_LENGTH,
                 PLATE_Z - TOP_RECESS_Z_FLOOR + 2 * BOOL_OVERSHOOT,
                 centered=(True, False, False))
            .translate((0.0, TOP_RECESS_Y_START, 0.0)))


# ── Front clearance pocket ─────────────────────────────────────────────────
# V4 has a shallow pocket at the front (low-Y end), below the rail
# channel floor — sized like a clearance pocket for the battery's
# spring-loaded latch button (which protrudes from the battery's front
# face when the latch is at rest).
FRONT_POCKET_X         = 36.0
FRONT_POCKET_Y_START   = 4.0
FRONT_POCKET_Y_LENGTH  = 13.0
FRONT_POCKET_Z_START   = 1.5
FRONT_POCKET_Z_DEPTH   = 5.5    # extends to z=7 (the main cavity floor),
                                # not z=6.5 — matches V4's stepped front cavity


def _front_pocket_cutter() -> cq.Workplane:
    return (cq.Workplane("XY")
            .workplane(offset=FRONT_POCKET_Z_START)
            .box(FRONT_POCKET_X, FRONT_POCKET_Y_LENGTH, FRONT_POCKET_Z_DEPTH,
                 centered=(True, False, False))
            .translate((0.0, FRONT_POCKET_Y_START, 0.0)))


# ── Front-corner cutouts ────────────────────────────────────────────────────
# V4 has the front (-Y) corners completely cut away above the front lip:
# at X=0..4 and X=68..72, Y=0..18, the dock is hollow above z=5.5. Without
# these cuts, the front-corner side walls show up as ~2K mm³ of BLUE (I
# have material V4 doesn't). User asked for these as "missing cutouts at -y".
FRONT_CORNER_X         = 4.0    # corner strip width (matches V4 wall offset)
FRONT_CORNER_Y_LENGTH  = 22.0   # extends the 45° taper longer in Y so the mid-Z
                                # cut reaches deeper into V4's hollow corner.
                                # Effective slope = 16.5/22 ≈ 0.75 (~37°).
FRONT_CORNER_Z_FLOOR   = 5.5    # above the front-lip height


BACK_CORNER_Y_LENGTH   = 6.0    # how far the back wedge tapers in (V4 only
                                # opens the top at Y=88.5+; smaller than front)
BACK_CORNER_Z_FLOOR    = 16.0   # back wedge only kicks in at the upper region
                                # (back is solid below this Z)


def _back_corner_cutter(side_sign: int) -> cq.Workplane:
    """45° wedge cut at the back corner: full-depth at Y=PLATE_Y, tapering
    to zero by Y=PLATE_Y - BACK_CORNER_Y_LENGTH. Only cuts the upper
    region (Z >= BACK_CORNER_Z_FLOOR) since V4 keeps the lower back solid."""
    y_taper_start = PLATE_Y - BACK_CORNER_Y_LENGTH
    pts = [
        (PLATE_Y + BOOL_OVERSHOOT, BACK_CORNER_Z_FLOOR),     # back-bottom corner
        (PLATE_Y + BOOL_OVERSHOOT, PLATE_Z + BOOL_OVERSHOOT),# back-top corner
        (y_taper_start,            PLATE_Z + BOOL_OVERSHOOT),# taper start at top
    ]
    width = FRONT_CORNER_X + BOOL_OVERSHOOT
    cutter = (cq.Workplane("YZ")
              .polyline(pts).close()
              .extrude(width))
    if side_sign > 0:
        return cutter.translate((PLATE_X / 2 - FRONT_CORNER_X, 0, 0))
    else:
        return cutter.translate((-PLATE_X / 2 - BOOL_OVERSHOOT, 0, 0))


def _front_corner_cutter(side_sign: int) -> cq.Workplane:
    """45° wedge cut at the front corner: full-depth Z=5.5..22 at Y=0,
    tapering linearly to zero by Y=FRONT_CORNER_Y_LENGTH (16.5 → 45°).
    Approximates V4's sloped front side-wall transition."""
    pts = [
        (-BOOL_OVERSHOOT, FRONT_CORNER_Z_FLOOR),            # Y=-0.5, Z=5.5
        (-BOOL_OVERSHOOT, PLATE_Z + BOOL_OVERSHOOT),        # Y=-0.5, Z=22.5
        (FRONT_CORNER_Y_LENGTH, PLATE_Z + BOOL_OVERSHOOT),  # Y=16.5, Z=22.5
    ]
    # Workplane("YZ") extrudes in +X; pre-translate cutter sits at X=0..W+δ.
    width = FRONT_CORNER_X + BOOL_OVERSHOOT
    cutter = (cq.Workplane("YZ")
              .polyline(pts).close()
              .extrude(width))
    if side_sign > 0:
        # Land cutter at X[PLATE_X/2 - FRONT_CORNER_X .. PLATE_X/2 + δ]
        return cutter.translate((PLATE_X / 2 - FRONT_CORNER_X, 0, 0))
    else:
        # Land cutter at X[-PLATE_X/2 - δ .. -PLATE_X/2 + FRONT_CORNER_X]
        return cutter.translate((-PLATE_X / 2 - BOOL_OVERSHOOT, 0, 0))


# ── Side ribs inside the upper cavity ───────────────────────────────────────
# V4 has two thin rectangular ribs running along the X side walls inside
# the upper cavity, near the top. They sit between Y=20..71 at Z=16.5..22
# (5mm wide × 51mm long × 5.5mm tall each). Without these we leave ~2.7K
# mm³ of unmodelled material against V4.
RIB_W = 5.0                              # X extent (inboard from wall)
RIB_LENGTH = 51.0                        # Y length
RIB_THICKNESS = PLATE_Z - 16.5           # 5.5 — from z=16.5 to plate top
RIB_Y_START = 20.0


RIB_Z_FLOOR = PLATE_Z - RIB_THICKNESS    # 16.5 — rib underside height


def _rib(x_inboard_edge: float) -> cq.Workplane:
    """One side rib: solid box hugging an X wall inside the cavity."""
    return (cq.Workplane("XY")
            .workplane(offset=RIB_Z_FLOOR)
            .box(RIB_W, RIB_LENGTH, RIB_THICKNESS,
                 centered=(False, False, False))
            .translate((x_inboard_edge, RIB_Y_START, 0.0)))


# Ribs sit at x=-32..-27 and x=27..32 (centred frame). Their underside at
# z=RIB_Z_FLOOR overhangs the open pocket when printed Z-up — the single
# largest overhang on the part. Reshape each into a triangular bracket: full
# thickness at the wall, ramping down to zero at the inboard edge (≈45°), so
# the underside is self-supporting. We cut the inboard-lower triangle away.
_RIB_X_WALL_R  = PLATE_X / 2 - POCKET_WALL_X            # 32
_RIB_X_IN_R    = _RIB_X_WALL_R - RIB_W                  # 27
_rib_chamfer_r = _xz_prism(
    [(_RIB_X_IN_R, RIB_Z_FLOOR), (_RIB_X_WALL_R, RIB_Z_FLOOR),
     (_RIB_X_IN_R, RIB_Z_FLOOR + RIB_W)],
    RIB_Y_START - BOOL_OVERSHOOT, RIB_Y_START + RIB_LENGTH + BOOL_OVERSHOOT)
_rib_chamfer_l = _xz_prism(
    [(-_RIB_X_IN_R, RIB_Z_FLOOR), (-_RIB_X_WALL_R, RIB_Z_FLOOR),
     (-_RIB_X_IN_R, RIB_Z_FLOOR + RIB_W)],
    RIB_Y_START - BOOL_OVERSHOOT, RIB_Y_START + RIB_LENGTH + BOOL_OVERSHOOT)

_ribs = (_rib(-_RIB_X_WALL_R).union(_rib(_RIB_X_IN_R))
         .cut(_rib_chamfer_r).cut(_rib_chamfer_l))


# ── Printability chamfers on the slot's downward edges (OCC edge-chamfer) ────
# Every downward-facing surface at the top of the battery slot (z=5) is an
# overhang when printed Z-up: the two retaining lips (the battery's Z-retention
# faces) plus the closed Y-end caps (wide-stem far-end shoulders, narrow
# hat-back). Rather than subtract wedges — which leave 0.5 mm overshoot ledges
# and un-mitered corners — we let OCC chamfer the actual void-side bottom
# edges. OCC auto-miters where chamfers meet and leaves no slivers. Selected
# edges (at z≈5):
#   • lips:            ‖Y at x=±STEM_WIDTH/2
#   • stem far end:    ‖X at y=STEM_Y_FAR (|x|<20)
#   • narrow hat-back: ‖X at y=71
SLOT_CHAMFER = 1.99                # ≈ the 2 mm lip height (near-full 45° ramp;
                                   # exactly 2.0 makes OCC fail on the
                                   # degenerate face, 1.99 leaves only a
                                   # ~0.01 mm strip — sub-resolution)


class _SlotChamferEdges(cq.Selector):
    """Pick the slot's void-side downward bottom edges at z≈5."""

    def filter(self, objs):
        out = []
        for o in objs:
            if not hasattr(o, "Center"):
                continue
            c = o.Center()
            if not (CHANNEL_HAT_H - 0.4 < c.z < CHANNEL_HAT_H + 0.4):
                continue
            b = o.BoundingBox()
            is_y = b.ylen > b.xlen and b.ylen > b.zlen
            is_x = b.xlen > b.ylen and b.xlen > b.zlen
            if is_y and abs(abs(c.x) - STEM_WIDTH / 2) < 1.0:
                out.append(o)                                  # lips
            elif is_x and abs(c.y - STEM_Y_FAR) < 1.0 and abs(c.x) < 20:
                out.append(o)                                  # stem far end
            elif is_x and abs(c.y - 71.0) < 1.0:
                out.append(o)                                  # narrow hat-back
        return out


def _chamfer_slot(wp: cq.Workplane) -> cq.Workplane:
    """45° chamfer the slot's downward edges; fall back to unchamfered if the
    OCC operation can't be performed (never break the build)."""
    try:
        return wp.edges(_SlotChamferEdges()).chamfer(SLOT_CHAMFER)
    except Exception:                                          # noqa: BLE001
        return wp


# The battery slot is the base for the chamfer op (simplest topology). The
# battery T-slot (hat/stem) is currently disabled while the central opening
# is built from the connector; it returns when the battery-capture side is
# reconciled with the terminal slot.
_slot = _plate
#          .cut(_hat_cutter())
#          .cut(_stem_cutter())
_slot = _chamfer_slot(_slot)            # no-op while the battery slot is off

# ── Dovetail mortise grooves (housing joinery) ──────────────────────────────
# Two grooves in the FLAT BACK (z=0 face), running along the slide axis,
# matching the backpack housing's vertical tenon rails (params shared via
# dimensions.py). Open at the y=PLATE_Y end (that edge sits at the housing
# bottom; the rail tip enters there as the dock slides down) and CLOSED at
# y=DOVETAIL_END_STOP — the closed end hits the rail tip = seating stop.
# Profile is undercut (wider deeper in) per dovetail; DOVETAIL_CLR per side.
def _dovetail_mortises() -> cq.Workplane:
    half_root = DOVETAIL_ROOT_W / 2 + DOVETAIL_CLR
    half_tip  = DOVETAIL_TIP_W / 2 + DOVETAIL_CLR
    depth     = DOVETAIL_DEPTH + DOVETAIL_CLR
    length    = PLATE_Y - DOVETAIL_END_STOP + BOOL_OVERSHOOT
    # Trapezoid in the X-Z plane (opening at z=0 back face, wide at depth),
    # extruded along +Y from the closed end to past the open edge.
    # The ceiling gets a TRUNCATED GABLE (45° shoulders + 4.8 flat): the
    # dock prints back-face-down, and a flat 9.6 ceiling sliced as a long
    # bridge; rise is capped at 2.4 because front-side features start at
    # z=7 (probed) — the housing tenons (3.5 deep) never reach the gable.
    rise = 2.4
    profile = [(-half_root, -BOOL_OVERSHOOT), (half_root, -BOOL_OVERSHOOT),
               (half_tip, depth),
               (half_tip - rise, depth + rise),
               (-(half_tip - rise), depth + rise),
               (-half_tip, depth)]
    groove = (cq.Workplane("XZ")
              .polyline(profile).close()
              .extrude(-length)                  # XZ extrude(-L) lands at +Y
              .translate((0.0, DOVETAIL_END_STOP, 0.0)))
    return (groove.translate((-DOVETAIL_X_OFF, 0, 0))
            .union(groove.translate((DOVETAIL_X_OFF, 0, 0))))


TERM_CLR = 0.2     # install clearance per face around the connector (X-Y)


def _terminal_t_cutter() -> cq.Workplane:
    """The central T opening as a lowercase 't', sized to the CONNECTOR's
    (643852-2) plan extents and cut straight through the plate thickness
    (dock Z = back face to plate top; this is the housing X axis in the
    seated/slicer view). Three rectangular prisms, zero clearance:

    The flush (zero-clearance) connector extents are:
      • top nub (narrow front): x -9.60..+5.40, y 21.54..23.63 — the flange
                                tip is OFFSET (centred at x=-2.1, not 0).
      • crossbar (wide body)  : x ±23.90, y 23.63..61.33
      • stem (narrow back)    : x ±12.00, y 60.00..73.33

    Each prism is then grown by TERM_CLR (0.2 mm) on all four X-Y sides for
    install clearance all around. The cut passes fully through Z, so there
    is no Z wall to clear. The boxes overlap in Y for clean unions. The
    battery rail also runs through the front of this opening — reconciling
    that with the connector slot is handled when the battery side is
    rebuilt."""
    OV = BOOL_OVERSHOOT
    C  = TERM_CLR

    def thru(x0, x1, y0, y1):
        # grow the flush extents outward by C on every X-Y side
        x0, x1, y0, y1 = x0 - C, x1 + C, y0 - C, y1 + C
        return (cq.Workplane("XY")
                .box(x1 - x0, y1 - y0, PLATE_Z + 2 * OV,
                     centered=(False, False, False))
                .translate((x0, y0, -OV)))

    nub      = thru(-9.60, 5.40, 21.54, 23.63)
    crossbar = thru(-23.90, 23.90, 23.63, 61.33)
    stem     = thru(-12.00, 12.00, 60.00, 73.33)
    return nub.union(crossbar).union(stem)


# Connector (643852-2) geometry referenced by the chamfers so they track the
# connector seat automatically (no hard-coded z values):
CONN_FLANGE_HALF_X    = 23.90   # ±x flange-lip extent (measured; z-move-invariant)
CONN_FLANGE_TOP_DZ    = 1.90    # flange-lip top above TERMINAL_PLACE z (measured)
CONN_FLANGE_SHOULDER_Y = 61.33  # +y flange shoulder (wide→narrow step) (measured)
CONN_STEM_HALF_X      = 12.00   # ±x stem flange-lip edge (measured)
STEM_HALF_X           = 12.20   # stem opening +x wall (= flange ±12 + clearance)


def _crossbar_chamfer(side_sign: int) -> cq.Workplane:
    """X-positioning chamfer/lip on a crossbar outer wall, above the
    connector flange. side_sign +1 = side 10 (+x wall), −1 = side 4 (−x
    wall); the connector flange/body are symmetric in x, so side 4 is the
    mirror of side 10. A 45° inner face grazes the connector's flange-lip
    edge and runs up-and-inward to the mount's cavity floor
    (CHANNEL_TOTAL_H), just clearing the body. Fills the clearance gap,
    growing in width from the flange edge (outboard) inward.

    PARAMETRIC — the graze height tracks the connector seat (TERMINAL_PLACE)
    and the top tracks the cavity floor, so moving the connector in z
    auto-updates the chamfer."""
    s        = side_sign
    OV       = BOOL_OVERSHOOT
    flange_x = s * CONN_FLANGE_HALF_X                   # connector flange edge
    wall_x   = s * (CONN_FLANGE_HALF_X + TERM_CLR)      # the crossbar wall
    z_lip    = TERMINAL_PLACE[2] + CONN_FLANGE_TOP_DZ   # flange-lip top (tracks seat)
    z_top    = CHANNEL_TOTAL_H                          # mount cavity floor
    # The 45° line through the flange edge (flange_x, z_lip) drops in z by
    # exactly the flange→wall gap (it's 45°), so it meets the wall at z_wall.
    # Computed from the connector + wall positions + the graze requirement —
    # no hard-coded clearance, so it's correct even if the gap changes.
    z_wall   = z_lip - abs(wall_x - flange_x)
    x_top    = flange_x - s * (z_top - z_lip)           # 45° inner at z_top
    # quad: the 45° underside is anchored at the ACTUAL wall (wall_x, z_wall)
    # so it grazes the flange; only the back vertices overshoot into the solid
    # wall (putting OV on the 45° anchor would shift the whole slope outward).
    poly = [(wall_x, z_wall), (x_top, z_top),
            (wall_x + s * OV, z_top), (wall_x + s * OV, z_wall)]
    y0, y1 = 23.43, 61.53                               # crossbar wall span
    return (cq.Workplane("XZ").polyline(poly).close()
            .extrude(-(y1 - y0)).translate((0, y0, 0)))


def _plus_x_lips() -> cq.Workplane:
    """+x flange-lip system — faces 10 (crossbar wall), 9 (step shoulder),
    8 (stem wall) — with both step corners mitered to their type:

      • 9/10 corner (x≈24, +x crossbar wall meets shoulder): INNER (concave,
        solid wraps it). Cut each lip's 45° SEPARATELY, then union -> the two
        faces meet at a VALLEY, corner stays full.
      • 8/9 corner (x≈12, shoulder meets +x stem wall): OUTER (convex, solid
        juts out). Union the two lips, then cut BOTH 45°s through both ->
        the two faces meet at a HIP.

    Every 45° starts flush at its wall (z_wall = z_lip − gap, no flat) and
    grazes the connector flange edge. Parametric in TERMINAL_PLACE + floor."""
    OV       = BOOL_OVERSHOOT
    z_lip    = TERMINAL_PLACE[2] + CONN_FLANGE_TOP_DZ   # 5.10
    z_top    = CHANNEL_TOTAL_H                          # 7.0
    dz       = z_top - z_lip                            # 1.90
    cb_y0    = 23.43                                    # crossbar front (lip start)
    stem_y1  = 73.53                                    # stem opening back wall

    # face 10 (+x crossbar wall), 9 (+y step shoulder), 8 (+x stem wall):
    fx10, wx10 = CONN_FLANGE_HALF_X,     CONN_FLANGE_HALF_X + TERM_CLR     # 23.90 / 24.10
    fy9,  wy9  = CONN_FLANGE_SHOULDER_Y, CONN_FLANGE_SHOULDER_Y + TERM_CLR # 61.33 / 61.53
    fx8,  wx8  = CONN_STEM_HALF_X,       STEM_HALF_X                       # 12.00 / 12.20
    z_wall   = z_lip - abs(wx10 - fx10)                 # 4.90 (= flange→wall gap, 45°)
    pz       = z_top - z_wall                           # 2.10
    x_in10   = fx10 - dz                                # 22.00 (45° inner @ z_top)
    y_in9    = fy9 - dz                                 # 59.43
    x_in8    = fx8 - dz                                 # 10.10

    # ── lip prisms ───────────────────────────────────────────────────────
    lip10 = (cq.Workplane("XY")
             .box(wx10 + OV - x_in10, wy9 - cb_y0, pz, centered=(False, False, False))
             .translate((x_in10, cb_y0, z_wall)))
    lip9  = (cq.Workplane("XY")
             .box(wx10 + OV - wx8, wy9 + OV - y_in9, pz, centered=(False, False, False))
             .translate((wx8, y_in9, z_wall)))
    lip8  = (cq.Workplane("XY")
             .box(wx8 + OV - x_in8, stem_y1 + OV - y_in9, pz, centered=(False, False, False))
             .translate((x_in8, y_in9, z_wall)))

    # ── 45° cut wedges (each anchored flush at its wall, grazing the flange) ─
    triA = [(wx10, z_wall), (x_in10 - OV, z_top + OV),
            (x_in10 - OV, z_wall - OV), (wx10, z_wall - OV)]     # face10 x-slope
    cutA = (cq.Workplane("XZ").polyline(triA).close()
            .extrude(-(wy9 + OV - cb_y0)).translate((0, cb_y0, 0)))
    triB = [(wy9, z_wall), (y_in9 - OV, z_top + OV),
            (y_in9 - OV, z_wall - OV), (wy9, z_wall - OV)]       # face9 y-slope
    cutB = (cq.Workplane("YZ").polyline(triB).close()
            .extrude(wx10 + OV - (x_in8 - OV)).translate((x_in8 - OV, 0, 0)))
    triC = [(wx8, z_wall), (x_in8 - OV, z_top + OV),
            (x_in8 - OV, z_wall - OV), (wx8, z_wall - OV)]       # face8 x-slope
    cutC = (cq.Workplane("XZ").polyline(triC).close()
            .extrude(-(stem_y1 + OV - (y_in9 - OV))).translate((0, y_in9 - OV, 0)))

    # 9/10 INNER: cutA isolated to lip10 (so it doesn't reach lip9 -> valley)
    lip10p = lip10.cut(cutA)
    # 8/9 OUTER: union shoulder + stem, cut BOTH 45°s through both -> hip.
    # (cutB also grazes lip9 along its length; cutC grazes lip8 along its.)
    shoulder_stem = lip9.union(lip8).cut(cutB).cut(cutC)
    return lip10p.union(shoulder_stem)


battery_dock = (_slot
                .cut(_lightening_cutter())
                .cut(_front_pocket_cutter())
                .cut(_front_opening_cutter())
                .cut(_top_recess_cutter())
                .cut(_front_corner_cutter(+1))
                .cut(_front_corner_cutter(-1))
                .cut(_back_corner_cutter(+1))
                .cut(_back_corner_cutter(-1))
                # The dock mounts to the backpack housing via the dovetail
                # grooves below — no mount-hole screws.
                .cut(_dovetail_mortises())
                .cut(_terminal_t_cutter())
                .union(_plus_x_lips())             # sides 10 + 9 + 8 (inner 9/10, outer 8/9)
                .union(_crossbar_chamfer(-1))      # side 4  (−x wall)
                .union(_ribs))
