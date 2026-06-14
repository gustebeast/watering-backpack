"""Assembly-only visualization parts.

Non-printed reference geometry that lives in the assembly STEP for
dimensional verification (does the terminal block fit in the dock pocket?
does the pump fit the cavity?). Each ``viz_*`` is either imported from a
STEP in ``references/`` or built parametrically from CadQuery primitives.

If a STEP reference file is missing, the corresponding ``viz_*`` is
``None`` and build.py skips adding it. Lets the build keep running while
references are still being sourced.
"""

from __future__ import annotations

from .dimensions import (MAKITA_TERMINAL_STEP, MAKITA_MOUNT_STEP, KEY_CLR,
                         TERMINAL_PLACE, TERMINAL_ROT_DEG)
from .helpers import import_step, heal, place_terminal


# ── Makita 643852-2 contact terminal (the OEM part) ─────────────────────────
# The plastic contact block with metal spades that you epoxy into the
# dock pocket. Imported from a clean BREP STEP — we don't print this, we
# just want to see where it sits inside the parametric dock so the
# pocket lines up.
viz_makita_terminal = import_step(MAKITA_TERMINAL_STEP)

# ── Wiseone V4 mount (side-by-side comparison reference) ───────────────────
# The community-designed mount we're using as a dimensional target.
# Loaded as viz so we can compare the parametric dock against it in the
# same FreeCAD tab. Positioned by build.py.
viz_mount_ref = import_step(MAKITA_MOUNT_STEP)


# ── Boolean diff: parametric dock vs. V4 reference ──────────────────────────
# The eyeball-comparison sucks when one model has 14 faces and the other
# has 91; boolean difference is the proper tool.
#
#   v4_minus_parametric  : material V4 has that we DON'T (red below)
#                          → features we still need to add
#                            (latch notch material, mount-hole bosses,
#                            terminal-pocket walls, wing tabs, etc.)
#
#   parametric_minus_v4  : material WE have that V4 doesn't (blue below)
#                          → places we're over-cutting or over-extending
#
# Both diff parts are placed in the same coordinate frame as V4 so they
# overlay the reference. Volume of each → numeric "how close are we"
# score (printed by build.py).
#
# Wrapped in a try/except: imported STEPs sometimes have face tolerances
# that confuse boolean ops; if either subtract fails we skip the diff
# rather than break the build.
def _compute_dock_diff():
    from .battery_dock import battery_dock, PLATE_X
    if viz_mount_ref is None:
        return None, None
    # Align parametric to V4's origin: parametric is centered in X
    # (-PLATE_X/2 .. +PLATE_X/2), V4 is corner-mounted (0 .. PLATE_X).
    aligned = battery_dock.translate((PLATE_X / 2, 0.0, 0.0))
    try:
        v4_extra = heal(viz_mount_ref.cut(aligned))
    except Exception:                                              # noqa: BLE001
        v4_extra = None
    try:
        our_extra = heal(aligned.cut(viz_mount_ref))
    except Exception:                                              # noqa: BLE001
        our_extra = None
    return v4_extra, our_extra


viz_diff_v4_minus_parametric, viz_diff_parametric_minus_v4 = _compute_dock_diff()


# ── Battery fit-overlap diagram ─────────────────────────────────────────────
# Goal (per the printability workflow): build a solid model of the battery's
# tool-side rail+latch that fills the dock slot, then
#
#   1. at NOMINAL size, verify it does NOT overlap the dock — there must be a
#      clearance gap, or the battery wouldn't slide in;
#   2. OVERSIZE it slightly until it overlaps — the intersection with the dock
#      is then the set of CONTACT SURFACES (load-bearing faces: rail side
#      walls, the T-slot retaining lips, the latch faces).
#
# When we later carve 45° chamfers into the dock for printability, we re-run
# this and confirm the contact set is preserved (it may shrink where a
# chamfer eats a lip — that's acceptable — but it must not vanish, and the
# chamfer must not introduce NEW interference that blocks the slide).
#
# The rail is built in the dock's own (X-centred) frame. `g` is the per-face
# size offset: g<0 undersizes (clearance check), g>0 oversizes (contact map).
BATTERY_FIT_GAP   = KEY_CLR        # 0.20 mm/face nominal slide clearance
BATTERY_OVERSIZE  = 0.40           # 0.40 mm/face interference → visible contact


def _battery_rail(g: float):
    """Solid filling the dock's battery slot, offset by `g` on every wall it
    shares with the slot (X both sides, Y both ends, Z top). The Z bottom
    stays at the open mouth (z=0) — the rail enters from below there."""
    import cadquery as cq
    from .battery_dock import (
        HAT_WIDTH, STEM_WIDTH, HAT_Y_FAR, STEM_Y_FAR,
        CHANNEL_Y_NEAR, CHANNEL_HAT_H, CHANNEL_TOTAL_H,
        HAT_BACK_NARROW_Y_START, HAT_BACK_NARROW_WIDTH,
    )

    def gbox(w, y0, y1, z0, z1):
        W = w + 2 * g
        Y0, Y1 = y0 - g, y1 + g
        Z0 = 0.0 if z0 <= 0.0 else z0 - g     # never poke below the open mouth
        Z1 = z1 + g
        return (cq.Workplane("XY").workplane(offset=Z0)
                .box(W, Y1 - Y0, Z1 - Z0, centered=(True, False, False))
                .translate((0.0, Y0, 0.0)))

    hat_front = gbox(HAT_WIDTH, CHANNEL_Y_NEAR, HAT_BACK_NARROW_Y_START,
                     0.0, CHANNEL_HAT_H)
    hat_back  = gbox(HAT_BACK_NARROW_WIDTH, HAT_BACK_NARROW_Y_START, HAT_Y_FAR,
                     0.0, CHANNEL_HAT_H)
    stem      = gbox(STEM_WIDTH, CHANNEL_Y_NEAR, STEM_Y_FAR,
                     CHANNEL_HAT_H, CHANNEL_TOTAL_H)
    return hat_front.union(hat_back).union(stem)


def _compute_battery_fit():
    """Return (nominal_overlap, contact_map). nominal_overlap should be ~0."""
    try:
        import cadquery as cq
        from .battery_dock import battery_dock
    except Exception:                                              # noqa: BLE001
        return None, None

    dock = battery_dock
    try:
        nominal = heal(_battery_rail(-BATTERY_FIT_GAP).intersect(dock))
    except Exception:                                              # noqa: BLE001
        nominal = None
    try:
        contact = heal(_battery_rail(+BATTERY_OVERSIZE).intersect(dock))
    except Exception:                                              # noqa: BLE001
        contact = None
    return nominal, contact


viz_battery_nominal_overlap, viz_battery_contact = _compute_battery_fit()


# ── Terminal (643852-2) fit-overlap diagram ─────────────────────────────────
# The OEM contact block seats blades-DOWN in the dock's central region: its
# blade contacts (terminal-frame z≈−27..−15, narrow ±12) poke toward the
# battery, its full-width flange (z≈−13..−7, 47.8 mm wide ≈ the 48 mm channel)
# sits in the channel, and the tall wire-terminal housing (z≈−7..+21) rises
# out the top of the dock for wiring.
#
# The STEP imports in its own frame already oriented width-along-X and
# tall-along-Z, centred in X. We translate it to seat in the dock:
#   • X: 0 (already centred on the channel)
#   • Y: place the body toward the closed (−Y) seated end of the channel
#   • Z: lift so the flange lands in the channel (≈ dock z 0..6), blades below
# These are a best-guess seating; tweak TERMINAL_PLACE (in dimensions.py) from
# the FreeCAD view.
#
# The fit check is the same overlap method: terminal ∩ dock = INTERFERENCE
# (dock material sitting where the terminal needs to be). For the terminal to
# drop in, that interference must be ~0; the dock's central T opening
# (battery_dock._terminal_t_cutter) is sized to the connector to clear it.
viz_terminal_placed = (
    place_terminal(viz_makita_terminal, TERMINAL_ROT_DEG, TERMINAL_PLACE)
    if viz_makita_terminal is not None else None
)


def _compute_terminal_fit():
    """Return dock material overlapping the seated terminal (interference)."""
    if viz_terminal_placed is None:
        return None
    try:
        from .battery_dock import battery_dock
        return heal(viz_terminal_placed.intersect(battery_dock))
    except Exception:                                              # noqa: BLE001
        return None


viz_terminal_interference = _compute_terminal_fit()
