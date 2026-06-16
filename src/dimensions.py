"""Top-level dimensions, material parameters, and fit clearances.

These are the constants every part draws from. Local part-specific
constants (e.g. battery-dock rail profile, joystick-clamshell wall
thicknesses) live in each part's module next to the geometry they apply
to. The contract: anything that two or more parts must agree on lives
here; anything that's purely local to one part stays in that part.
"""

# ── Universal fit clearances ─────────────────────────────────────────────────
# Single source of truth for hand-assembled cylindrical / rectangular fits
# (slip seats, anti-rotation keys, clip pockets, etc). Anything that gets
# pressed/snapped uses a SMALLER local override; anything that needs a
# screwdriver uses a LARGER local override. Mirrors retractable-cable-spool
# conventions so the same printer / material yields the same fit feel.
FIT_CLR        =   0.15   # 0.15 mm per side — slip fit
KEY_CLR        =   0.20   # 0.20 mm per side — anti-rotation keys / notches

# ── Universal thin-structural-wall thickness ─────────────────────────────────
# Used for the bulk wall thickness of the printed enclosures, rib stiffeners,
# and other "structural" thin walls. 2.0 mm = 5 perimeters at a 0.4 mm
# nozzle (extrusion width ~0.42–0.45), printing as a solid wall with no
# infill sliver. Press-fit collars / load-bearing features keep their own
# thicker walls.
STRUCT_WALL    =   2.0

# ── Boolean overshoot ────────────────────────────────────────────────────────
# Standard "extend past a face" margin for boolean cut/union operations.
# Applied to through-cuts (workplane offset by -BOOL_OVERSHOOT, extrude by
# total_depth + 2*BOOL_OVERSHOOT) and to features that need a clean break
# from the host face. Big enough to avoid coincident-face artifacts;
# small enough to not visibly distort geometry if a cut is accidentally
# referenced as a real surface.
BOOL_OVERSHOOT =   0.5


# ── Makita 18V LXT battery interface ─────────────────────────────────────────
# TODO: fill in once the reference STEP is dropped at
# references/makita_battery.step. The dock geometry mates with these
# features on the battery's tool-side face:
#
#   • Two side rails (T-slots) — battery has the male tongues, dock has the
#     female L-grooves that the tongues slide into.
#   • Spring-loaded latch button on the front face of the battery, with a
#     hooked tab on top that engages a notch on the dock. Pressing the
#     button retracts the tab; the dock notch must be positioned so the
#     tab snaps in when the battery is fully seated.
#   • Terminal slot — the 643852-2 contact block sits inside the dock,
#     centered on the battery's terminal channel, sliding spades into the
#     battery's terminal bores as the battery slides home.
#
# Dimensions to extract from the reference STEP (added here once measured):
#   MAKITA_RAIL_PITCH_Y      — center-to-center spacing of the two rails
#   MAKITA_RAIL_W            — tongue width (X)
#   MAKITA_RAIL_H            — tongue height (Z)
#   MAKITA_RAIL_LENGTH       — slide engagement length
#   MAKITA_LATCH_NOTCH_X     — notch X position relative to slide-stop
#   MAKITA_LATCH_NOTCH_W/H/D — notch dimensions
#   MAKITA_TERMINAL_BLOCK_*  — 643852-2 pocket dimensions + position
#
# Fit clearance on the rails uses KEY_CLR (0.20 mm/side, sliding fit).


# ── Path constants ───────────────────────────────────────────────────────────
import pathlib as _pathlib
REPO_ROOT = _pathlib.Path(__file__).resolve().parents[1]
REFERENCES_DIR = REPO_ROOT / "references"
# Community STEP of the OEM Makita 643852-2 contact block — used as the
# viz/demo part inside the dock (the real OEM contact you'll glue in).
# Imported as viz only; never a printed part.
MAKITA_TERMINAL_STEP  = REFERENCES_DIR / "makita_643852_2.step"
# Community Wiseone V4 mount — STEP version of the Printables design 43386.
# DIMENSIONAL reference only — used by tools/inspect_*.py to read off the
# mount's geometry while we iterate src.battery_dock. Not loaded into
# the build assembly.
MAKITA_MOUNT_STEP     = REFERENCES_DIR / "makita_mount_v4.step"
# Community STEP of the Makita 18V LXT battery (BL18xx) — viz reference, seated
# on the dock for fit-checking. Never a printed part.
MAKITA_BATTERY_STEP   = REFERENCES_DIR / "makita_battery.step"

# ── Dock ↔ housing dovetail joinery (shared contract) ────────────────────────
# The battery dock mounts to the backpack housing with PLASTIC DOVETAILS, no
# screws: the housing carries two vertical male rails (tenons), the dock's
# flat back carries matching mortise grooves. The dock slides DOWN onto the
# rails and bottoms out seated — battery-insertion force pushes it deeper
# into the joint. Rails print as vertical prisms (no overhang); grooves print
# into the dock's bed-side face (steep flanks + short ceiling bridge).
# Sized to fit the dock's back land between the battery channel edge (±24)
# and the plate edge (±36): tip half-width 4.5 + 0.2 clr at centre ±30 spans
# x 25.3..34.7 — ≥1.3 mm wall to the channel AND to the edge. (A first cut at
# 8/11/4 @ ±29 broke 0.7 mm into the battery channel walls and cost ~80 mm³
# of battery contact surface.)
DOVETAIL_ROOT_W   = 6.5    # arrowhead width at the opening (narrow root)
DOVETAIL_TIP_W    = 9.0    # arrowhead width at its widest (the undercut). The
                           # depth is DERIVED (45° flanks → 2·tip/2 − root/2),
                           # not a separate constant — see helpers.dovetail_arrowhead.
DOVETAIL_X_OFF    = 40.0   # groove centrelines at dock x = ±40 — moved
                           # outboard (was 30) of the battery rail (dock x∓32)
                           # and connector (±24), into the side ears the dock
                           # grows to host them (see _dovetail_ears)
DOVETAIL_END_STOP = 0.0    # 0 = mortise + rail run the dock's FULL slide
                           # length (to the +z top, dock y0 / housing z86);
                           # was 10 (stopped 10 mm short at z76). Seating is by
                           # the dock bottoming flush on the housing floor.
DOVETAIL_CLR      = 0.30   # per-side groove clearance — looser than KEY_CLR
                           # (0.20): this is a long (76 mm) engagement on big
                           # wall surfaces, so it needs the extra room to
                           # slide without binding.


# ── Terminal (643852-2) seating ──────────────────────────────────────────────
# Transform that drops the imported terminal STEP into the dock's central
# region: centred in X, body toward the closed (-Y) end, lifted so the
# full-width flange lands in the channel with blades poking below toward the
# battery and the wire housing rising out the top. Best-guess seating, tuned
# from the FreeCAD view; both the dock (pocket cut) and viz (fit check) use it.
# Rotated 90° about +X so the terminal's 22.3 mm dimension runs through the
# plate thickness (≈22 mm), its 51.8 mm axis lies along the slide (Y), and the
# blade contacts engage in the slide direction — how the Makita terminal mates.
TERMINAL_ROT_DEG     = 90.0
# Y=47 is the visually-correct seat (user-confirmed at build #39): the terminal
# spans Y≈21.5..73.3, aligned with the channel (Y=22..73). NOTE: a
# minimise-interference-vs-V4 search suggested Y=42, but that slid the block
# 5 mm forward out of channel alignment and read as wrong — the visual seat
# wins over the interference metric for placement.
#
# Z=3 (was 7): the terminal hangs on its 1.8 mm perimeter LIP RING (the full
# 47.8 mm-wide band, at z 6.6..9.0 of the part when placed at z=7). It
# installs from the dock's BACK side; the lips bear on the hat→stem shoulder
# at dock z=5 (lips fit the 48 mm hat, not the 44 mm stem; the 43.6 mm body
# passes on through). Seating the lip front face ON that shoulder = shift −4:
# lips at z 2.6..5.0, body onward to z 18.3, and the wire-blade tail pokes
# ~4 mm out the dock's back — through the housing's terminal window, where
# the wiring happens. The housing wall it mounts against closes the back.
TERMINAL_PLACE       = (0.0, 47.0, 3.2)   # translate after rotation; z=3.2
                                          # seats the connector's body-step
                                          # face flush with the dock cavity
                                          # floor (dock z = CHANNEL_TOTAL_H = 7;
                                          # was z=3.0, leaving a 0.2 mm gap)
TERMINAL_POCKET_CLR  = 0.20    # clearance per ~face for the conformal pocket
# The connector's flange back sits at dock z = TERMINAL_PLACE[2]. We trim the
# dock's back off at that plane so the flange back becomes the dock's mounting
# face, and shift the dock placement by the same amount so it lands flush on
# the housing wall — the wall then retains the connector (no separate pads,
# and nothing fixed in the slot to clip the dock during its slide).
DOCK_BACK_TRIM       = TERMINAL_PLACE[2]   # 3.2 mm of dock back removed


# ── Sanity checks (catch silent miscoordinations early) ──────────────────────
# Each assert represents an invariant that other code silently depends on.
# A violation usually means someone tightened a clearance past zero or
# shrunk one feature past another.
assert FIT_CLR > 0, "fit clearance must be positive"
assert KEY_CLR >= FIT_CLR, "key clearance should be looser than slip-fit"
assert STRUCT_WALL >= 1.2, "wall thickness < 1.2 mm risks under-extrusion / weakness"
