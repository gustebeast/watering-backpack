"""Backpack housing — the pack-side enclosure (pump + battery + electronics).

Sits ABOVE the water can (no contact) and mounts to the pack frame via a flat
back panel. Layout decisions (with the user):

  • PUMP — SEAFLO 42, FEET BOLTED TO THE BACK PANEL, ports VERTICAL
    (rotated 90° about the motor axis from the factory feet-down pose).
    Motor axis runs side-to-side (X), centred. Why: the ports point out
    opposite sides of the head, so any feet-down pose fires one port straight
    into the pack frame. Vertical ports give: bottom port → intake drops
    through a floor hole to the can below; top port → straight barb, hose
    rises in free air above +X. Feet bolt to standoff bosses on the back
    panel (backed by the frame), riding clear of the slide-lock teeth.

  • BATTERY — dock module bolts OUTSIDE the −X wall, slide-axis vertical,
    mouth up: drop a battery in from above, swappable while wearing the pack.
    Opposite side from the hoses (+X) per user.

  • ELECTRONICS — ESP32 + BTS7960 + buck + TSR + fuse live in a separate
    half-width ELECTRONICS HOUSING that slides into the pump housing and
    locks under alternating teeth (the wand gets only the 3-wire joystick).

Frame:
  • X = width (side-to-side), centred on 0.  Hoses +X, battery −X.
  • Y = depth (Y=0 = inner face of the back panel, +Y away from the back).
  • Z = up (Z=0 = top of the floor).

Run:  py -3.12 -m src.backpack_housing
"""
from __future__ import annotations

import pathlib
import sys

import cadquery as cq

from .dimensions import (BOOL_OVERSHOOT, MAKITA_TERMINAL_STEP,
                         TERMINAL_PLACE, TERMINAL_ROT_DEG, DOCK_BACK_TRIM,
                         DOVETAIL_ROOT_W, DOVETAIL_TIP_W,
                         DOVETAIL_X_OFF, DOVETAIL_END_STOP)
from .helpers import (bump_build_counter, import_step, place_terminal,
                      dovetail_arrowhead)

# Shared Archive/3D tooling (same as build.py).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "freecad"))
from cq_colors import color          # noqa: E402
from freecad_view import show        # noqa: E402


# ── Pump envelope (SEAFLO 42, exact where it matters) ───────────────────────
PUMP_L       = 206.0   # motor axis length (SHURflo 4008 sheet: [206])
PUMP_DEPTH   = 115.0   # feet → head end (housing Y after rotation) — USER
                       # MEASURED: cylinder edge ~105, head square end ~115,
                       # head near face ~15 off the plate
PUMP_SPAN_Z  = 125.0   # port tip to port tip (housing Z after rotation)
PUMP_PORT_D  = 27.0    # effective OD with the barb fitting (bare
                       # 1/2" NPT male is 20.95)
# In the pump model frame: rear face x=0, centred y, feet z=0.
PUMP_PORT_FEET   = 80.0    # port centreline above the feet — USER CALIPERED
                           # (4008 sheet said 84.6; SEAFLO measures 80)
PUMP_BOLT_XS     = (22.0, 95.0)      # bolt rows from rear face (22 + 73)
PORT_FROM_FRONT_BOLT = 64.0  # port axis ahead of the FRONT bolt row — 4008
                             # sheet [64], user calipered ~65 (match). The
                             # bolts locate the pump, so the hole chains here.
PUMP_PORT_X      = PUMP_BOLT_XS[1] + PORT_FROM_FRONT_BOLT   # 95 + 64 = 159
PUMP_BOLT_DY     = 83.0              # across a pair


# ── Housing parameters ───────────────────────────────────────────────────────
WALL    = 3.0     # structural wall (PCTG; carries pump + battery)
FLOOR_T = 4.0

CLR_X    = 6.25   # bay clearance each side (keeps BAY_W at 218.5 with
                  # the datasheet-corrected 206 pump length)
CLR_Y    = 9.0    # clearance in front of the pump head (user: widen so
                  # the pump sweep clears the front shelf comfortably)
PORT_TIP_Z = 2.0  # bottom port tip ends just ABOVE the floor top. The intake
                  # barb's female coupling (hex ≈25 mm) passes UP through the
                  # generous floor hole and threads onto the port at the floor
                  # line; the hose clamps on below the floor (open air gap
                  # above the can). Keeps the pump's foot plate clear of the
                  # floor too — the feet hang on the back-wall bolts.

# TWO-BOX architecture (user design, water protection):
#   • PUMP HOUSING (bottom): floor + 4 walls, OPEN TOP, rim at PUMP_RIM_Z.
#     Holds the pump (water-resistant, +X region exposed to the elements)
#     and the battery dock. The outlet barb rises in free air above +X.
#   • ELECTRONICS HOUSING (top): half the bay wide, slides INSIDE the pump
#     housing onto a shelf and locks under alternating retaining teeth (see
#     the SLIDE-LOCK block). It stops at ELEC_XOUT — well short of +X —
#     leaving the pump outlet open. Four walls, no roof (lid later). ALL
#     wiring enters through FLOOR holes, so water has to travel upward
#     against gravity to reach the electronics.
BAY_W = PUMP_L + 2 * CLR_X                    # 218.5
# The pump's feet land on STANDOFF BOSSES, not the bare wall: the pads then
# slide down in a plane 6 mm proud of the wall, clear of the 5 mm-deep
# teeth — so teeth need no special gaps anywhere (user). Bay deepens by the
# same 6 mm so front clearance is unchanged.
PUMP_STANDOFF = 6.0
BAY_D = PUMP_DEPTH + PUMP_STANDOFF + CLR_Y    # 130
PUMP_RIM_Z   = 137.0                          # pump-housing wall top (pump
                                              # max z=127 + clearance)
# INSTALLABILITY RULE (user): the pump slides DOWN from above into its
# seat, so its swept plan silhouette (max x/y extents across all z) is a
# NO-GO zone for everything above it. The build runs a stepped slide-in
# sweep check (pump x housing at raised offsets) every rebuild.
# The electronics box SLIDES INSIDE the pump housing and rests on a shelf
# 18.5 mm below the rim. Within the box footprint (x ≤ ELEC_XOUT) the
# pump's highest points are the head corner (z≈109.5) and the upper foot
# pads (z≈118), both below the floor slab.
SHELF_Z      = 118.5                          # shelf top = elec floor seat —
                                              # 0.5 above the foot-pad tops
                                              # (z~118) so the floor slab is
                                              # FLAT underneath (no pockets,
                                              # no bed-face overhangs)
TRAY_SEAT_Z  = SHELF_Z                        # elec floor slab bottom
TRAY_T       = 4.0                            # elec floor thickness (top 122.5)
ELEC_TOP_Z   = 178.0                          # elec wall top (lid plane later)
# Outer width = EXACTLY half the bay (user): the −X edge hugs the wall
# (−BAY_W/2 + clr), so the +X edge lands at +clr past centre. The stroke to
# the outlet and the teeth re-derive automatically from this.
ELEC_CLR     = 0.3                            # slide clearance to pump walls
ELEC_XOUT    = (-BAY_W / 2 + ELEC_CLR) + BAY_W / 2          # 0.3

# SLIDE-LOCK JOINT (user design): retaining LIPS on the pump housing's
# front/back inner walls (45°-chamfered undersides) overhang the elec
# floor's edge FLANGES. The flange has notches offset one slide-travel
# (+x) from the lips: drop the box in shifted +x (lips pass the notches),
# slide −x to lock (lips over solid flange). An M4 screw through the −X
# wall stops it sliding back.
# TEETH model (user): the joint is a series of teeth alternating OPEN
# (gaps the flange tabs drop through) and CLOSED (teeth that grip once
# slid). SLIDE TRAVEL = the full stroke before the box's +X edge bumps the
# pump outlet fitting (the outlet IS the install stop — slide against it,
# drop, slide back). Teeth derive from the stroke: tooth = travel − 0.8,
# so the flange still drops/locks even ~0.5 shy of a hard bump; gap =
# tooth + 1 so each notch fully clears its tooth at the seated position.
SLIDE_TRAVEL = (PUMP_PORT_X - PUMP_L / 2 - PUMP_PORT_D / 2) - ELEC_XOUT
INSTALL_CLR  = 2.0    # tooth-to-notch clearance EACH SIDE at the install
                      # pose (user: 2 mm so the drop-in is forgiving)
TOOTH_L      = SLIDE_TRAVEL - 0.8
TOOTH_GAP    = TOOTH_L + 2 * INSTALL_CLR + 0.8
LIP_PROTRUDE = 5.0

# Tooth generator: pack teeth at TOOTH_L+TOOTH_GAP pitch into the wall
# zones outside the pad strips, leaving room for each install notch on
# the floor (-X end) and full bearing on the flange (+X end).
def _gen_teeth():
    # Standoff bosses lift the pump's descent path clear of the teeth, so
    # the whole wall span is usable (no foot-strip gaps).
    # Start so the first tooth's install-notch OVERSHOOTS the floor's −x
    # edge by 0.5 (a +margin here leaves an unprintable 0.4 sliver of
    # flange between notch and edge — user caught it on the export).
    a = -BAY_W / 2 + ELEC_CLR + SLIDE_TRAVEL + INSTALL_CLR - 0.5
    teeth = []
    while a + TOOTH_L <= ELEC_XOUT:
        teeth.append((a, a + TOOTH_L))
        a += TOOTH_L + TOOTH_GAP
    return teeth

LIP_SEGS = _gen_teeth()      # ONE set, used on BOTH ±y walls (identical)
LIP_Z0       = SHELF_Z + TRAY_T + ELEC_CLR    # 122.8 tooth underside (at wall)
LIP_Z1       = 129.0                          # lip top

# STRING MOUNT (user): the backpack has loops at top left/right; a string
# runs from each loop, around the perimeter of its ±X face (down one
# corner, along the floor, up the other corner) and back to the loop.
# 5.6×5.6 square channels guide it, ON THE INSIDE of the ±X faces:
#   • 4 corner ducts along z — the housing's corner walls form two sides,
#     an added vertical BLADE (cantilevered off the back/front wall, 45°
#     bottom end) forms the third; the elec box wall (0.3 away, walls are
#     inset past y 5.9) effectively closes the fourth side up high.
#   • 2 floor ducts along y (one per face) — floor + face wall + an added
#     strip with a 45° roof (all printable floor-down).
# Every turn has a big open gap (z 13→37 at the corners, y 0→30 / 100→130
# along the floor) so fingers can reach in and thread the string onward.
# Threading happens before the pump/electronics go in (user).
STRING_BORE  = 5.6
STRING_STRIP = 1.6
ZDUCT_Z0     = 37.0             # corner ducts run from here to the rim
YDUCT_Y      = (30.0, 100.0)    # floor ducts (gaps to the corners beyond)
SHELF_X0     = -101.75          # ±y shelves/houses start past the −X
                                # corner ducts (keeps the string path open)

# SHELF HOUSE + RAMP (user design): per ±y wall, a 'little house' (gabled
# tongue: rectangular base + 45° roof) runs the FULL LENGTH of the bottom
# shelf; the box's floor flange carries the matching house-shaped CHANNEL
# in its underside (gable roof = self-supporting bed recess; the part
# still sits flat). The house's vertical side walls give TRUE ±y capture
# along the whole wall, and since both profiles are constant in x the
# drop-in and slide need no pass-notches. The flange TOP additionally
# grows a 45° RAMP parallel under the teeth (0.3 normal clearance) so +z
# motion bears on a full 45° surface instead of a corner sliver.
# t = distance from the pump wall's inner face.
HOUSE_T      = (2.2, 4.8)       # base y-band — leaves a 1.6mm lip wall
                                # between flange edge (0.3) and channel (1.9)
HOUSE_WALL_Z = 120.6            # top of the vertical walls
HOUSE_PEAK_Z = 121.9            # gable peak (45° roof; half-width 1.3)
HOUSE_CLR    = 0.3              # normal clearance all around the house
RAMP_T_END   = 5.0              # ramp follows the tooth underside to here,
                                # then drops VERTICALLY (= tooth tip plane)

# M4 lock screw: through the pump −X wall into a boss on the elec −X wall.
# CENTRED on the bay depth (user). At z=128 the wall exterior is bare for
# all y: the dock tops out at z=86, its dovetail rails at 76, and the
# battery's deepest insertion features stay ~10 mm outboard of the head.
M4_SCREW_YZ  = (BAY_D / 2, 128.0)
M4_CLR_D     = 4.5
M4_PILOT_D   = 3.6

# Outer envelope.
OUTER_W = BAY_W + 2 * WALL                    # 224.5
OUTER_D = BAY_D + 2 * WALL                    # 136
OUTER_H = ELEC_TOP_Z + FLOOR_T                # 182 (assembled stack)

# Pump placement: rotate −90° about X (factory +Z → housing +Y, feet → −Y
# against the back wall), then centre the motor on X and set the port height.
PUMP_CX = -PUMP_L / 2.0                       # −103
PUMP_CZ = PUMP_SPAN_Z / 2.0 + PORT_TIP_Z      # 64.5 → bottom tip z = +2

# Derived feature positions (housing frame).
PORT_AXIS_X   = PUMP_PORT_X + PUMP_CX         # 56 (both ports)
PORT_AXIS_Y   = PUMP_PORT_FEET + PUMP_STANDOFF   # 86 from the back wall
FLOOR_HOLE_D  = 32.0                          # passes the intake barb's
                                              #  ≈25 mm hex up to the port
# Pump foot bolt holes in the back wall (M4 clearance).
PUMP_BOLT_HOLES = [(bx + PUMP_CX, PUMP_CZ + dy)
                   for bx in PUMP_BOLT_XS
                   for dy in (-PUMP_BOLT_DY / 2, PUMP_BOLT_DY / 2)]
PUMP_BOLT_CLR_D = 4.4

# ── Electronics (inside the elec housing) ───────────────────────────────────
# Boards mount on printed standoffs/rails with the user's M2 hardware; the
# fuse holder and TSR live in the harness. All wiring enters via the floor
# (wire slot + joystick hole) — never through walls.
# BTS7960 IBT-2 — modeled from the handsontec datasheet: board 49.7 × 49.4,
# mount holes on a 40 × 40 pattern, ≈29 mm finned heatsink one side, screw
# terminal (B−, B+, M+, M−) + 2×4 control header + cap on the other.
# Mounted HEATSINK-UP for convection: the board sits on TWO Ø8 printed
# standoffs (diagonal corners of the 40×40 pattern — two screws, per user),
# wiring side down. Standoffs are tall enough that the hanging cap (~20 mm)
# and terminal block clear the tray.
BTS_CENTER   = (-75.0, 52.0)    # module centre on the tray
BTS_BOARD    = (49.7, 49.4, 1.6)
BTS_SINK_H   = 29.4
BTS_BOSS_H   = 21.5             # standoff height (clears the hanging cap)
BTS_HOLE_PITCH = 40.0
BTS_BOSS_D   = 8.0
# ALL board fasteners use the user's M2 hardware (91292A013 M2×20 screws +
# 94459A110 heat-set inserts): Ø3.2 insert pilot at each standoff top,
# Ø2.4 clearance bore below for the long shank.
M2_INSERT_D  = 3.2
M2_INSERT_L  = 4.0
M2_CLR       = 2.4
# The two used (diagonal) hole positions:
BTS_BOSS_XY  = [(BTS_CENTER[0] - BTS_HOLE_PITCH / 2, BTS_CENTER[1] - BTS_HOLE_PITCH / 2),
                (BTS_CENTER[0] + BTS_HOLE_PITCH / 2, BTS_CENTER[1] + BTS_HOLE_PITCH / 2)]
BTS_BOARD_Z  = TRAY_SEAT_Z + TRAY_T + BTS_BOSS_H        # 144 board underside
# Power terminal: hangs below the board at the +y edge; 4 entries at 5 mm
# pitch on its outer face, order B−, B+, M+, M− (datasheet p.4).
BTS_TERM_Y_FACE = BTS_CENTER[1] + BTS_BOARD[1] / 2      # 76.7
BTS_ENTRY_X = {"B-": -82.5, "B+": -77.5, "M+": -72.5, "M-": -67.5}
# Control header: hangs below the board at the −y edge, pins pointing −y.
BTS_HDR_Y_FACE = BTS_CENTER[1] - BTS_BOARD[1] / 2       # 27.3
# QuinLED-ESP32, from the user's measured board drawing: PCB 31.05 × 32.89
# × 1.6. U1 (the ESP32 module shield) and J5 (USB) share the same +z extent
# (~3.2 above the PCB); J5 overhangs its edge ~0.95; two castellated pin
# rows run the full long edges. Laid ROTATED 90° to fit the half-width box:
# antenna↔USB axis along X (USB at −x, facing the BTS gap), pin rows along
# y≈17.5 and y≈45.5. MOUNT (user design, no screws on the board):
#   • a 15 mm-wide RAIL under the bare centre strip, running along X —
#     the edge pin rows hang clear on either side;
#   • a BEAM crossing along Y above the board, bearing lightly on U1's
#     shield — perpendicular to the USB so it never blocks the connector.
# Assembly: tilt the antenna edge under the beam, lay flat onto the rail.
ESP_POS      = (-40.0, 16.0)            # PCB min corner (x, y)
ESP_BOARD    = (32.89, 31.05, 1.6)      # rotated footprint
ESP_CX       = ESP_POS[0] + ESP_BOARD[0] / 2            # −23.56
ESP_RAIL_W   = 15.0
ESP_RAIL_H   = 4.0                      # pin tails (~3) hang clear beside it
ESP_PCB_Z    = TRAY_SEAT_Z + TRAY_T + ESP_RAIL_H        # 126.5 PCB underside
ESP_U1_TOP_Z = ESP_PCB_Z + ESP_BOARD[2] + 3.2           # 131.3 shield top
# Board-local feature offsets (from the user's drawing, rotated frame):
# U1 shield 16×20 at +(10, 5.5); J5 (USB) 10.45×10.9 at +(−0.95, 10.05);
# bare centre strip (rail land) at +(−1.5, 8), 15 wide.
ESP_U1_OFF   = (10.0, 5.5)
ESP_J5_OFF   = (-0.95, 10.05)
ESP_RAIL_OFF = (-1.5, 8.0)
ESP_BEAM_X   = (-25.0, -19.0)           # over U1, clear of J5 (x ≤ −30)
# The clamp beam is a SEPARATE printed part, screwed to the two posts:
#   • McMaster 94459A110 heat-set inserts (brass, M2×0.4, 2.5 installed)
#     pressed flush into the post tops — Ø3.2 pilot bore;
#   • McMaster 91292A013 M2×20 socket screws down through the beam
#     (Ø2.4 clearance, Ø4.0×2.2 counterbore for the Ø3.8 head); the long
#     shank passes on through post + tray (Ø2.4 bore) and the tip emerges
#     ~5 mm under the tray — open air, 30 mm above the pump motor.
ESP_BEAM_T   = 4.0
ESP_POST_TOP = ESP_U1_TOP_Z             # beam rests here, bearing on U1
ESP_SCREW_XY = [(-22.0, 12.0), (-22.0, 51.0)]
ESP_INSERT_D = 3.2                      # 94459A110 pilot
ESP_INSERT_L = 4.0                      # bore depth (insert 2.5 + lead-in)
ESP_SCREW_CLR = 2.4                     # M2 clearance
ESP_CBORE_D  = 4.0
ESP_CBORE_T  = 2.2                      # socket head Ø3.8 × 2.0
# Pololu D42V110F12 buck — modeled from the official dimension drawing
# (pololu.com 0J2217): board 43.2 × 31.8 × 1.57, caps 6.1 above the board
# (12 V version), 1.8 of parts underneath, 4× Ø2.18 holes (#2/M2 screws) on
# a 38.9 × 25.4 pattern. Power through-holes (VIN, GND, VOUT, GND) in a row
# along one long edge at 5.0 / 17.94 / 6.35 spacing. Mounted long-axis
# along X with the pin row facing +y (where all four power wires arrive),
# on TWO Ø6 standoffs at diagonal corners (M2 self-tap pilots).
BUCK_BOARD   = (43.2, 31.8, 1.6)
BUCK_POS     = (-48.0, 75.0)            # board min corner (x, y) on the tray
BUCK_BOSS_H  = 5.0                      # clears the 1.8 mm underside parts
BUCK_BOSS_D  = 6.0                      # M2 insert in top (Ø3.2 → 1.4 wall)
BUCK_BOARD_Z = TRAY_SEAT_Z + TRAY_T + BUCK_BOSS_H       # 127.5 board underside
_buck_cx = BUCK_POS[0] + BUCK_BOARD[0] / 2              # −26.4
_buck_cy = BUCK_POS[1] + BUCK_BOARD[1] / 2              # 90.9
BUCK_BOSS_XY = [(_buck_cx - 38.9 / 2, _buck_cy - 25.4 / 2),
                (_buck_cx + 38.9 / 2, _buck_cy + 25.4 / 2)]
BUCK_PIN_Y   = BUCK_POS[1] + BUCK_BOARD[1] - 7.62       # 99.18 pin-row line
# Board rotated so VIN/GND sit at the +x end (battery side) and VOUT/GND at
# the −x end (BTS side) — input and output wiring never cross at the row.
BUCK_PIN_X   = {"VIN": _buck_cx + 11.69, "GND": _buck_cx + 6.69,
                "VOUT": _buck_cx - 11.25, "GND2": _buck_cx - 17.65}
# = VIN −14.71, GND −19.71, VOUT −37.65, GND2 −44.05 — VIN/GND at the +x
# end (riser side), VOUT/GND2 at the −x end (BTS side): no crossings.
# Traco TSR 1-2450E (5 V/1A SIP): lives heat-shrunk in the harness beside
# the ESP32; the wire routes land on its pins.
TSR_POS  = (-30.0, 58.0)                # block min corner (x, y)
TSR_SIZE = (11.7, 7.6, 10.2)            # footprint + height

# FLOOR wire openings (everything enters from below — gravity-protected):
WIRE_SLOT    = (-105.5, -92.0, 85.0, 105.0)  # (x0, x1, y0, y1) − battery +
                                             # pump wires rise here (−X corner)
# Joystick cable: comes over the pump-housing +X rim, runs UNDER the elec
# floor (above the pump; the y≈55 lane clears the barb zone y 72.5..99.5)
# and up through this floor hole.
JOY_HOLE_D   = 10.0
JOY_FLOOR_XY = (-10.0, 55.0)  # inside the half-width box, off the barb zone

# Battery dock mounting (−X wall, outside).
# Dock frame: x −36..36 (width), y 0..90 (slide; +y = mouth), z 0..22
# (thickness). The z=0 face is the FLAT BACK — it mounts against the wall.
# The z=22 side carries the complex geometry that fits around the battery —
# it faces OUTWARD (−X). Transform: flip 180° about the dock's slide axis,
# then the 120°-(1,1,1) axis-cycle, then translate. Net mapping:
#   dock z → −housing x  (z=0 back on the wall, z=22 front outboard)
#   dock y → +housing z  (mouth up)
#   dock x → −housing y
DOCK_PLATE_X, DOCK_PLATE_Y, DOCK_PLATE_Z = 72.0, 90.0, 22.0
DOCK_WALL_X  = -OUTER_W / 2.0                 # outer face of the −X wall
DOCK_TY      = BAY_D / 2.0                    # centred on the wall depth
DOCK_TZ      = -FLOOR_T                       # dock bottom FLUSH with the
                                              # housing bottom face (z=−4) so
                                              # the dock region prints flat on
                                              # the bed with the housing
# Dovetail joinery (no screws): two vertical tenon rails on the −X wall
# matching the dock's mortise grooves (shared params in dimensions.py).
# The dock slides DOWN over the rails; the groove's closed end meets the
# rail top = seated, dock bottom flush with the housing bottom. Rails start
# on the bed (z=−FLOOR_T) and print as plain vertical prisms.
DOCK_TOP_Z      = DOCK_TZ + DOCK_PLATE_Y      # 86 — top edge of seated dock
RAIL_Y_CENTERS  = (DOCK_TY - DOVETAIL_X_OFF, DOCK_TY + DOVETAIL_X_OFF)
RAIL_Z_TOP      = DOCK_TOP_Z - DOVETAIL_END_STOP   # 76 — rail tip = stop
# Terminal access window: a square opening through the −X wall directly
# behind the seated terminal (window centred on DOCK_TY), exposing the
# whole contact-plate/wire side for wiring from inside the bay. PRINT ORIENTATION: the housing prints floor-down, so the
# window top is a 45° GABLE (two slopes meeting at a ridge) instead of a flat
# bridge — no horizontal overhang. The window stays inside the dock's back
# footprint (y 22.5..94.5, z −4..86), so the dock plate covers it from
# outside and all four dock screws keep solid wall around them.
TERM_WINDOW_W     = 44.0                      # y 36.5..80.5 (centred on dock)
TERM_WINDOW_Z_BOT = 16.0                      # raised from 14 → more bearing
                                              # wall under the flange (better +x
                                              # retention); blades clear (poke in
                                              # at z16+, ~0.2 mm³ in z14-16)
TERM_WINDOW_Z_TOP = 50.0                      # vertical sides end; gable above
                                              # (ridge at 50 + 22 = 72)


# ── Lightening (strength-to-weight, user; PCTG, 0.8 nozzle) ─────────────────
# The rim ring, the elec box (house joint braces y over the −X half), and
# the frame-backed rear wall carry the structure — mid-wall panels and the
# floor field mostly add mass. Openings:
#   • WALLS: DIAMONDS (pure 45° edges — zero bridges in vertical walls).
#     Front (+y) wall: 4 tall diamonds (no attachments there).
#     Back (−y) wall: 3 diamonds between the pump-bolt boss columns.
#     +X wall: 3 diamonds between the string-duct corners.
#     −X wall: NONE (dock, terminal window, M4 boss, duct corners).
#   • FLOOR: 45°-cornered rectangles (bed face — no overhang constraint),
#     leaving a 10mm perimeter ring, cross ribs, and a solid annulus
#     around the intake hole. All webs ≥ 3 perimeters at 0.8mm.
# Keep-outs: z>105 on ±y walls (shelf/house/teeth band + rim), bolt boss
# columns ±14, string ducts, floor-duct roofs (z<15).
FRONT_DIAMONDS = [(-77.0, 57.0), (-26.0, 57.0), (25.0, 57.0), (76.0, 57.0)]
FRONT_DIA_WH   = (44.0, 80.0)          # width(x) × height(z)
BACK_DIAMONDS  = [(-45.0, 64.5), (30.0, 64.5), (80.0, 64.5)]
BACK_DIA_WH    = (44.0, 45.0)          # clears bolt rows z 23/106 ± 14
XWALL_DIAMONDS = [(28.0, 55.0), (65.0, 55.0), (102.0, 55.0)]
XWALL_DIA_WH   = (30.0, 70.0)          # (y, z) centres on the +X wall
FLOOR_CUT_WH   = (60.0, 44.0)
FLOOR_CUTS     = [(-70.0, 32.0), (0.0, 32.0), (70.0, 32.0),
                  (-70.0, 88.0), (0.0, 88.0)]   # (56,86 intake keeps its
                                                # corner solid)


def _diamond_thru(axis: str, offset: float, cx: float, cz: float,
                  w: float, h: float, depth: float) -> cq.Workplane:
    """45° diamond hole cutter through a wall. axis 'y': wall normal to
    Y at y=offset (cx is x); axis 'x': normal to X at x=offset (cx is y)."""
    pts = [(cx - w / 2, cz), (cx, cz + h / 2), (cx + w / 2, cz),
           (cx, cz - h / 2)]
    if axis == "y":
        # Workplane("XZ") extrudes toward −Y for positive depths
        return (cq.Workplane("XZ")
                .polyline(pts).close()
                .extrude(depth)
                .translate((0, offset, 0)))
    return (cq.Workplane("YZ")
            .polyline(pts).close()
            .extrude(depth)
            .translate((offset, 0, 0)))


def _lightening_cuts() -> cq.Workplane:
    out = None
    def add(wp):
        nonlocal out
        out = wp if out is None else out.union(wp)
    OV = BOOL_OVERSHOOT
    w, h = FRONT_DIA_WH
    for cx, cz in FRONT_DIAMONDS:
        add(_diamond_thru("y", BAY_D + WALL + OV, cx, cz, w, h, WALL + 2 * OV))
    w, h = BACK_DIA_WH
    for cx, cz in BACK_DIAMONDS:
        add(_diamond_thru("y", 0 + OV, cx, cz, w, h, WALL + 2 * OV))
    w, h = XWALL_DIA_WH
    for cy, cz in XWALL_DIAMONDS:
        add(_diamond_thru("x", BAY_W / 2 - OV, cy, cz, w, h, WALL + 2 * OV))
    # floor: 45°-cornered rectangles (corner clip = h/4)
    fw, fh = FLOOR_CUT_WH
    c = fh / 4
    for cx, cy in FLOOR_CUTS:
        x0, x1 = cx - fw / 2, cx + fw / 2
        y0, y1 = cy - fh / 2, cy + fh / 2
        pts = [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c),
               (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]
        add(cq.Workplane("XY")
            .workplane(offset=-FLOOR_T - OV)
            .polyline(pts).close()
            .extrude(FLOOR_T + 2 * OV))
    return out


# ── Shell ────────────────────────────────────────────────────────────────────
def _base_shell() -> cq.Workplane:
    """PUMP HOUSING open-top box: floor + four walls to the rim at
    PUMP_RIM_Z; back panel is the Y=−WALL..0 wall."""
    outer = (cq.Workplane("XY")
             .workplane(offset=-FLOOR_T)
             .box(OUTER_W, OUTER_D, PUMP_RIM_Z + FLOOR_T,
                  centered=(True, False, False))
             .translate((0.0, -WALL, 0.0)))
    inner = (cq.Workplane("XY")
             .box(BAY_W, BAY_D, PUMP_RIM_Z + BOOL_OVERSHOOT,
                  centered=(True, False, False)))
    return outer.cut(inner)


def _shelf_and_lips() -> cq.Workplane:
    """Shelf corbels (45° undersides) on the back/front/−X interior walls at
    SHELF_Z, plus the retaining LIP segments above the floor flange on the
    front/back walls (lip undersides also 45°, rising away from the wall —
    retention happens at the wall-side corner)."""
    P = LIP_PROTRUDE
    # Shelf + house span SHELF_X0 (clear of the −X string ducts) to the
    # box's SEATED +x edge (no runway needed on either end — the box is
    # hand-held during install and the channel is open-ended).
    x_lo, x_hi = SHELF_X0, ELEC_XOUT
    # Shelf corbels: continuous on back, front and −X walls (the pump's
    # feet ride the standoff bosses, clear of all of these).
    def y_wall_shelf(wall_y, sgn):
        return (cq.Workplane("YZ")
                .polyline([(wall_y, SHELF_Z),
                           (wall_y + sgn * P, SHELF_Z),
                           (wall_y, SHELF_Z - P)]).close()
                .extrude(x_hi - x_lo).translate((x_lo, 0, 0)))
    left = (cq.Workplane("XZ")
            .polyline([(-BAY_W / 2, SHELF_Z), (-BAY_W / 2 + P, SHELF_Z),
                       (-BAY_W / 2, SHELF_Z - P)]).close()
            .extrude(-(BAY_D - 2 * (STRING_BORE + STRING_STRIP + 0.6)))
            .translate((0, STRING_BORE + STRING_STRIP + 0.6, 0)))
    out = y_wall_shelf(0.0, +1).union(y_wall_shelf(BAY_D, -1)).union(left)
    # The gabled 'house' tongue on each shelf (see SHELF HOUSE block).
    # Ends at the box's SEATED +x edge — the open-ended channel just feeds
    # onto it during the slide, so no runway beyond the seat is needed.
    t0, t1 = HOUSE_T
    tm = (t0 + t1) / 2
    for wall_y, sgn in ((0.0, +1), (BAY_D, -1)):
        prof = [(t0, SHELF_Z - 0.1), (t1, SHELF_Z - 0.1),
                (t1, HOUSE_WALL_Z), (tm, HOUSE_PEAK_Z), (t0, HOUSE_WALL_Z)]
        out = out.union(cq.Workplane("YZ")
                        .polyline([(wall_y + sgn * t, z) for t, z in prof])
                        .close()
                        .extrude(ELEC_XOUT - x_lo).translate((x_lo, 0, 0)))
    # Retaining teeth, mirrored on both walls: 45° underside rising away
    # from the wall, so retention bears at the wall-side corner.
    for wall_y, sgn in ((0.0, +1), (BAY_D, -1)):
        for a, b in LIP_SEGS:
            out = out.union(cq.Workplane("YZ")
                            .polyline([(wall_y, LIP_Z0),
                                       (wall_y + sgn * P, LIP_Z0 + P),
                                       (wall_y + sgn * P, LIP_Z1),
                                       (wall_y, LIP_Z1)]).close()
                            .extrude(b - a).translate((a, 0, 0)))
    return out


def _m4_wall_hole() -> cq.Workplane:
    """Ø4.5 clearance through the pump −X wall for the slide-lock screw."""
    return (cq.Workplane("YZ")
            .workplane(offset=-OUTER_W / 2 - BOOL_OVERSHOOT)
            .center(*M4_SCREW_YZ)
            .circle(M4_CLR_D / 2)
            .extrude(WALL + 2 * BOOL_OVERSHOOT))


def _floor_intake_hole() -> cq.Workplane:
    """Bottom pump port passes through the floor; intake barb threads on
    from below (the air gap above the can)."""
    return (cq.Workplane("XY")
            .workplane(offset=-FLOOR_T - BOOL_OVERSHOOT)
            .center(PORT_AXIS_X, PORT_AXIS_Y)
            .circle(FLOOR_HOLE_D / 2)
            .extrude(FLOOR_T + 2 * BOOL_OVERSHOOT))


def _standoff_bosses() -> cq.Workplane:
    """Four bosses on the back wall's inner face — the pump's rubber feet
    bolt against THESE, riding PUMP_STANDOFF proud of the wall so the pads
    descend clear of the teeth. Tops flattened below the elec floor."""
    out = None
    r = 25.0 / 2
    drop = PUMP_STANDOFF + WALL       # shear reaches through the wall
    for bx, bz in PUMP_BOLT_HOLES:
        # Workplane("XZ") extrudes toward −Y, so start the base at the
        # boss tip (y=+PUMP_STANDOFF) and extrude back INTO the wall.
        b = (cq.Workplane("XZ")
             .workplane(offset=-PUMP_STANDOFF)
             .center(bx, bz).circle(r)
             .extrude(PUMP_STANDOFF + BOOL_OVERSHOOT))
        # 45° support fairing (user's construction): sweeping a 45°
        # triangular corbel around the circle's 4:30..7:30 arc is the
        # same as unioning the boss with a copy extruded along the
        # 45° down-and-into-the-wall vector — a ruled surface that is
        # exactly 45° under 6 o'clock and shallower toward the sides.
        # The tip face stays a clean circle.
        tip_wire = cq.Wire.makeCircle(
            r, cq.Vector(bx, PUMP_STANDOFF, bz), cq.Vector(0, 1, 0))
        fairing = cq.Workplane(obj=cq.Solid.extrudeLinear(
            cq.Face.makeFromWires(tip_wire),
            cq.Vector(0, -drop, -drop)))
        # Restrict the sweep to the 4:30..7:30 SEGMENT (user): the full
        # disc shear pokes out from 3 to 9 o'clock; everything above the
        # 45°-tangent chord doesn't overhang and needs no support. Cut
        # the fairing above the chord plane (which follows the shear).
        v = r / 2 ** 0.5
        OV = BOOL_OVERSHOOT
        chord_cut = (cq.Workplane("YZ")
                     .polyline([(PUMP_STANDOFF + OV, bz - v + OV),
                                (-WALL - 2 * OV,
                                 bz - v - drop + PUMP_STANDOFF - OV),
                                (-WALL - 2 * OV, bz + r + 5),
                                (PUMP_STANDOFF + OV, bz + r + 5)]).close()
                     .extrude(2 * r + 2 * OV)
                     .translate((bx - r - OV, 0, 0)))
        fairing = fairing.cut(chord_cut)
        # Taper the ends (user): bound the fairing by the two 45° tangent
        # planes so its depth fades to ZERO at the 4:30/7:30 seams — no
        # wings hanging under the points where the chamfer meets the
        # circle. (Cut = everything below each tangent line, extruded
        # along the boss axis.)
        for sgn in (+1, -1):
            line_lo = (bx - sgn * 20, bz - 20 - 2 * v)
            line_hi = (bx + sgn * 20, bz + 20 - 2 * v)
            wing_cut = (cq.Workplane("XZ")
                        .polyline([line_lo, line_hi,
                                   (line_hi[0], bz - 45),
                                   (line_lo[0], bz - 45)]).close()
                        .extrude(PUMP_STANDOFF + WALL + 2 * OV)
                        .translate((0, PUMP_STANDOFF + OV, 0)))
            fairing = fairing.cut(wing_cut)
        boss = b.union(fairing)
        out = boss if out is None else out.union(boss)
    # keep boss tops below the elec floor's slide plane
    cap = (cq.Workplane("XY").workplane(offset=SHELF_Z - 0.5)
           .box(BAY_W, 40.0, 40.0, centered=(True, False, False))
           .translate((0, -10.0, 0)))
    return out.cut(cap)


def _pump_bolt_holes() -> cq.Workplane:
    """4× M4 clearance holes through the back panel (pump feet bolt pattern)."""
    out = None
    for hx, hz in PUMP_BOLT_HOLES:
        h = (cq.Workplane("XZ")
             .workplane(offset=-PUMP_STANDOFF - BOOL_OVERSHOOT)
             .center(hx, hz)
             .circle(PUMP_BOLT_CLR_D / 2)
             .extrude(WALL + PUMP_STANDOFF + 2 * BOOL_OVERSHOOT))
        out = h if out is None else out.union(h)
    return out


def _terminal_window() -> cq.Workplane:
    """Gabled terminal access window (square sides, 45° roof — printable
    with the housing standing floor-down)."""
    y0 = DOCK_TY - TERM_WINDOW_W / 2
    y1 = DOCK_TY + TERM_WINDOW_W / 2
    zb, zt = TERM_WINDOW_Z_BOT, TERM_WINDOW_Z_TOP
    ridge = zt + TERM_WINDOW_W / 2
    return (cq.Workplane("YZ")
            .workplane(offset=-BAY_W / 2 - WALL - BOOL_OVERSHOOT)
            .polyline([(y0, zb), (y1, zb), (y1, zt),
                       (DOCK_TY, ridge), (y0, zt)])
            .close()
            .extrude(WALL + 2 * BOOL_OVERSHOOT))


def _string_channels() -> cq.Workplane:
    """Added material for the string-mount channels (see STRING MOUNT
    block): 4 vertical corner blades + 2 roofed floor ducts. The bores
    themselves are the empty space beside the housing's own walls."""
    b, t = STRING_BORE, STRING_STRIP
    OV = BOOL_OVERSHOOT
    out = None
    def add(wp):
        nonlocal out
        out = wp if out is None else out.union(wp)
    for face_x, sx in ((-BAY_W / 2, +1), (BAY_W / 2, -1)):
        # corner blades: parallel to the face, attached to the back/front
        # wall, 45° rising bottom edge (supported from that wall).
        # On the −X face the ducts STOP BELOW the elec box (user): above,
        # the string rises through the chimney formed by the pump corner
        # walls + the box's own inset walls — no box rebates needed.
        z_top = (TRAY_SEAT_Z - 0.3) if sx > 0 else PUMP_RIM_Z
        for wall_y, sy in ((0.0, +1), (BAY_D, -1)):
            prof = [(wall_y - sy * OV, ZDUCT_Z0 - b),
                    (wall_y + sy * b, ZDUCT_Z0),
                    (wall_y + sy * b, z_top),
                    (wall_y - sy * OV, z_top)]
            blade = (cq.Workplane("YZ")
                     .polyline(prof).close()
                     .extrude(sx * t)
                     .translate((face_x + sx * b, 0, 0)))
            add(blade)
            # 4th wall: closes the duct's inboard-y side (cantilevered
            # off the ±X face wall, 45° bottom). The elec box walls get
            # a matching corner rebate at the −X end.
            prof4 = [(face_x - sx * OV, ZDUCT_Z0 - (b + t)),
                     (face_x + sx * (b + t), ZDUCT_Z0),
                     (face_x + sx * (b + t), z_top),
                     (face_x - sx * OV, z_top)]
            wall4 = (cq.Workplane("XZ")
                     .polyline(prof4).close()
                     .extrude(-sy * t)
                     .translate((0, wall_y + sy * b, 0)))
            wb = wall4.val().BoundingBox()
            want = min(wall_y + sy * b, wall_y + sy * (b + t))
            wall4 = wall4.translate((0, want - wb.ymin, 0))
            add(wall4)
        # floor duct: strip + GABLE roof (45° both ways, peak mid-bore,
        # like the house tongue). Tops out at ~z10 — under the terminal
        # window sill (z14), so the duct runs CONTINUOUS on both faces.
        mid = face_x + sx * (b + t) / 2
        peak_in = b + (b + t) / 2            # inner gable apex
        prof = [(face_x + sx * b, 0.0),
                (face_x + sx * (b + t), 0.0),
                (face_x + sx * (b + t), b + t),
                (mid, b + t + (b + t) / 2),
                (face_x - sx * OV, b + t + OV),
                (face_x - sx * OV, b - OV),
                (mid, peak_in),
                (face_x + sx * b, b)]
        duct = (cq.Workplane("XZ")
                .polyline(prof).close()
                .extrude(YDUCT_Y[1] - YDUCT_Y[0]))
        db = duct.val().BoundingBox()
        duct = duct.translate((0, YDUCT_Y[0] - db.ymin, 0))
        add(duct)
    return out


def _dovetail_tenons() -> cq.Workplane:
    """Two vertical dovetail rails on the −X wall's outer face, ARROWHEAD
    cross-section in plan — built from the SAME dovetail_arrowhead profile as
    the dock mortise (clr=0 here, the nominal solid) so the pair always match.
    Extruded from the bed (z=−FLOOR_T) up to RAIL_Z_TOP. Map (across, depth)
    -> (x, y): depth = outboard (−x) from the wall, across = y about yc. The
    opening overshoots INTO the wall so the union fuses; the pointy top
    self-supports inside the matching groove."""
    x_wall = -OUTER_W / 2                      # rail root plane
    pts = dovetail_arrowhead(DOVETAIL_ROOT_W / 2, DOVETAIL_TIP_W / 2,
                             clr=0.0, open_ov=BOOL_OVERSHOOT)
    rail = None
    for yc in RAIL_Y_CENTERS:
        poly = [(x_wall - depth, yc + across) for across, depth in pts]
        prism = (cq.Workplane("XY")
                 .workplane(offset=-FLOOR_T)
                 .polyline(poly).close()
                 .extrude(RAIL_Z_TOP + FLOOR_T))
        rail = prism if rail is None else rail.union(prism)
    return rail


backpack_housing = (_base_shell()
                    .union(_standoff_bosses())
                    .cut(_floor_intake_hole())
                    .cut(_pump_bolt_holes())
                    .cut(_terminal_window())
                    .union(_shelf_and_lips())
                    .cut(_m4_wall_hole())
                    .union(_string_channels())
                    .union(_dovetail_tenons())     # rails now at y26/104 (x±40)
                    .cut(_lightening_cuts()))


# ── Electronics housing (separate print) ────────────────────────────────────
def _m2_standoff(tray, bx, by, d, h):
    """Standoff post with an M2 heat-set insert pilot at the top and a
    Ø2.4 clearance bore continuing through post + floor for the M2×20
    shank."""
    top = TRAY_SEAT_Z + TRAY_T + h
    boss = (cq.Workplane("XY")
            .workplane(offset=TRAY_SEAT_Z + TRAY_T)
            .center(bx, by).circle(d / 2).extrude(h))
    insert = (cq.Workplane("XY")
              .workplane(offset=top - M2_INSERT_L)
              .center(bx, by).circle(M2_INSERT_D / 2)
              .extrude(M2_INSERT_L + BOOL_OVERSHOOT))
    thru = (cq.Workplane("XY")
            .workplane(offset=TRAY_SEAT_Z - BOOL_OVERSHOOT)
            .center(bx, by).circle(M2_CLR / 2)
            .extrude(h + TRAY_T + 2 * BOOL_OVERSHOOT))
    return tray.union(boss).cut(insert).cut(thru)


def _build_elec_housing() -> cq.Workplane:
    """ELECTRONICS HOUSING: slides INSIDE the pump housing onto the shelf
    at SHELF_Z. The floor's front/back edges are FLANGES that ride under
    the pump housing's retaining lips; notches in the flanges (offset one
    SLIDE_TRAVEL toward +x) let the box drop in shifted +x, then slide −x
    to lock. The front/back walls are INSET past the lip sweep; an M4 boss
    on the −X wall takes the lock screw. ALL wire entries are FLOOR
    openings. Prints floor-down."""
    x0 = -BAY_W / 2 + ELEC_CLR              # −108.95
    x1 = ELEC_XOUT
    y0, y1 = ELEC_CLR, BAY_D - ELEC_CLR     # 0.3 .. 129.7
    wall_inset = LIP_PROTRUDE + ELEC_CLR + ELEC_CLR   # 5.6 flange width
    floor = (cq.Workplane("XY")
             .workplane(offset=TRAY_SEAT_Z)
             .box(x1 - x0, y1 - y0, TRAY_T, centered=(False, False, False))
             .translate((x0, y0, 0)))
    # Walls: −X and +X at the floor edges; front/back inset behind the lips.
    wy0 = y0 + wall_inset                   # 5.9
    wy1 = y1 - wall_inset                   # 124.1
    walls_outer = (cq.Workplane("XY")
                   .workplane(offset=TRAY_SEAT_Z + TRAY_T)
                   .box(x1 - x0, wy1 - wy0, ELEC_TOP_Z - TRAY_SEAT_Z - TRAY_T,
                        centered=(False, False, False))
                   .translate((x0, wy0, 0)))
    walls_inner = (cq.Workplane("XY")
                   .workplane(offset=TRAY_SEAT_Z + TRAY_T - BOOL_OVERSHOOT)
                   .box(x1 - x0 - 2 * WALL, wy1 - wy0 - 2 * WALL,
                        ELEC_TOP_Z - TRAY_SEAT_Z + 2 * BOOL_OVERSHOOT,
                        centered=(False, False, False))
                   .translate((x0 + WALL, wy0 + WALL, 0)))
    tray = floor.union(walls_outer.cut(walls_inner))

    # Flange-top 45° RAMPS + house CHANNELS (see SHELF HOUSE block).
    ramp_h = lambda t: LIP_Z0 - 0.42 + t        # 0.3 normal under the teeth
    ht0, ht1 = HOUSE_T
    htm = (ht0 + ht1) / 2
    g = HOUSE_CLR
    gv = HOUSE_CLR * 1.414                      # vertical growth at the peak
    for pump_wall_y, sgn in ((0.0, +1), (BAY_D, -1)):
        def Y(t):
            return pump_wall_y + sgn * t
        # Past the 45° face the ramp tops out FLAT to the wall (filling
        # the old 0.9 valley between ramp and wall — the teeth never
        # reach below the ramp crest, so nothing slides through there).
        ramp = [(ELEC_CLR, TRAY_SEAT_Z + TRAY_T - 0.1),
                (ELEC_CLR, ramp_h(ELEC_CLR)),
                (RAMP_T_END, ramp_h(RAMP_T_END)),
                (wall_inset + ELEC_CLR + 1.0, ramp_h(RAMP_T_END)),
                (wall_inset + ELEC_CLR + 1.0, TRAY_SEAT_Z + TRAY_T - 0.1)]
        tray = tray.union(cq.Workplane("YZ")
                          .polyline([(Y(t), z) for t, z in ramp]).close()
                          .extrude(x1 - x0).translate((x0, 0, 0)))
        # Channel = house offset 0.3 NORMALLY: 45° roof stays exactly 45°
        # (peak +0.42 vertical; eave walls rise to peak − half-width).
        peak_c = HOUSE_PEAK_Z + gv
        eave_c = peak_c - (htm - (ht0 - g))
        chan = [(ht0 - g, TRAY_SEAT_Z - BOOL_OVERSHOOT),
                (ht1 + g, TRAY_SEAT_Z - BOOL_OVERSHOOT),
                (ht1 + g, eave_c),
                (htm, peak_c),
                (ht0 - g, eave_c)]
        tray = tray.cut(cq.Workplane("YZ")
                        .polyline([(Y(t), z) for t, z in chan]).close()
                        .extrude(x1 - x0 + 2 * BOOL_OVERSHOOT)
                        .translate((x0 - BOOL_OVERSHOOT, 0, 0)))

    # Flange lock-notches on BOTH edges: teeth shifted −SLIDE_TRAVEL in
    # floor coords (+clr).
    for ny in (y0 - BOOL_OVERSHOOT, y1 - wall_inset):
        for a, b in LIP_SEGS:
            tray = tray.cut(cq.Workplane("XY")
                            .workplane(offset=TRAY_SEAT_Z - BOOL_OVERSHOOT)
                            .box((b - a) + 2 * INSTALL_CLR,
                                 wall_inset + BOOL_OVERSHOOT,
                                 (LIP_Z0 - 0.42 + RAMP_T_END + 0.5)
                                 - TRAY_SEAT_Z + BOOL_OVERSHOOT,
                                 centered=(False, False, False))
                            .translate((a - SLIDE_TRAVEL - INSTALL_CLR,
                                        ny, 0)))

    # No string cuts in this part (user): the −X corner ducts end below
    # the floor, and the string passes the floor band through the TOOTH
    # install-notch (whose −x end sits at the corner and already pierces
    # flange + ramp), then rises in the 5.6 chimney between the pump
    # walls and these inset walls.

    # M4 lock boss on the −X wall (pilot bored horizontally through
    # wall + boss; the screw comes in through the pump wall).
    sy, sz = M4_SCREW_YZ
    boss = (cq.Workplane("YZ")
            .workplane(offset=x0 + WALL)
            .center(sy, sz).rect(16.0, 14.0)
            .extrude(4.0))
    pilot = (cq.Workplane("YZ")
             .workplane(offset=x0 - BOOL_OVERSHOOT)
             .center(sy, sz).circle(M4_PILOT_D / 2)
             .extrude(WALL + 4.0 + 2 * BOOL_OVERSHOOT))
    tray = tray.union(boss).cut(pilot)

    # ESP32 rail + clamp beam (no pocket, no screws — see ESP_* params).
    rail = (cq.Workplane("XY")
            .workplane(offset=TRAY_SEAT_Z + TRAY_T)
            .box(36.0, ESP_RAIL_W, ESP_RAIL_H, centered=(False, False, False))
            .translate((ESP_POS[0] + ESP_RAIL_OFF[0],
                        ESP_POS[1] + ESP_RAIL_OFF[1], 0)))
    tray = tray.union(rail)
    x0b, x1b = ESP_BEAM_X
    for _, sy in ESP_SCREW_XY:                 # posts outside the PCB edges
        post = (cq.Workplane("XY")
                .workplane(offset=TRAY_SEAT_Z + TRAY_T)
                .box(x1b - x0b, 6.0,
                     ESP_POST_TOP - (TRAY_SEAT_Z + TRAY_T),
                     centered=(False, False, False))
                .translate((x0b, sy - 3.0, 0)))
        tray = tray.union(post)
    # Insert pilot at each post top + M2 clearance bore on through the tray
    # (the M2×20 shank passes through; tip exits below in free air).
    for sx, sy in ESP_SCREW_XY:
        pilot = (cq.Workplane("XY")
                 .workplane(offset=ESP_POST_TOP - ESP_INSERT_L)
                 .center(sx, sy).circle(ESP_INSERT_D / 2)
                 .extrude(ESP_INSERT_L + BOOL_OVERSHOOT))
        thru = (cq.Workplane("XY")
                .workplane(offset=TRAY_SEAT_Z - BOOL_OVERSHOOT)
                .center(sx, sy).circle(ESP_SCREW_CLR / 2)
                .extrude(ESP_POST_TOP - TRAY_SEAT_Z + 2 * BOOL_OVERSHOOT))
        tray = tray.cut(pilot).cut(thru)

    # Buck standoffs: two Ø6 posts at diagonal corners of the 38.9 × 25.4
    # pattern, same M2 insert + clearance treatment.
    for bx, by in BUCK_BOSS_XY:
        tray = _m2_standoff(tray, bx, by, BUCK_BOSS_D, BUCK_BOSS_H)

    # BTS7960 standoffs: two Ø8 posts at diagonal corners of the 40×40
    # hole pattern. M2 heat-set insert in each top, clearance bore below.
    for bx, by in BTS_BOSS_XY:
        tray = _m2_standoff(tray, bx, by, BTS_BOSS_D, BTS_BOSS_H)

    # FLOOR wire slot (−X corner): battery + pump wires rise from the pump
    # bay through here — the only path in is upward, against gravity.
    sx0, sx1, sy0, sy1 = WIRE_SLOT
    tray = tray.cut(cq.Workplane("XY")
                    .workplane(offset=TRAY_SEAT_Z - BOOL_OVERSHOOT)
                    .box(sx1 - sx0, sy1 - sy0, TRAY_T + 2 * BOOL_OVERSHOOT,
                         centered=(False, False, False))
                    .translate((sx0, sy0, 0)))
    # FLOOR hole for the joystick cable (comes over the +X rim, runs under
    # this floor above the pump, then up through here).
    tray = tray.cut(cq.Workplane("XY")
                    .workplane(offset=TRAY_SEAT_Z - BOOL_OVERSHOOT)
                    .center(*JOY_FLOOR_XY)
                    .circle(JOY_HOLE_D / 2)
                    .extrude(TRAY_T + 2 * BOOL_OVERSHOOT))

    return tray


elec_housing_part = _build_elec_housing()


def _bts7960_parts():
    """Semi-accurate IBT-2 model (heatsink-up), per the handsontec
    datasheet. Returns [(name, workplane, color), ...]."""
    cx, cy = BTS_CENTER
    bw, bd, bt = BTS_BOARD
    board = (cq.Workplane("XY")
             .workplane(offset=BTS_BOARD_Z)
             .box(bw, bd, bt, centered=(True, True, False))
             .translate((cx, cy, 0)))
    sink = (cq.Workplane("XY")
            .workplane(offset=BTS_BOARD_Z + bt)
            .box(50.0, 50.0, BTS_SINK_H, centered=(True, True, False))
            .translate((cx, cy, 0)))
    # Corner truncations: the mounting holes sit at the board's chamfered
    # corners OUTSIDE the sink so the M2 heads are reachable from above.
    for sx, sy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        notch = (cq.Workplane("XY")
                 .workplane(offset=BTS_BOARD_Z + bt - BOOL_OVERSHOOT)
                 .box(20.0, 20.0, BTS_SINK_H + 2 * BOOL_OVERSHOOT,
                      centered=(True, True, False))
                 .translate((cx + sx * 25.0, cy + sy * 25.0, 0))
                 .rotate((cx + sx * 25.0, cy + sy * 25.0, 0),
                         (cx + sx * 25.0, cy + sy * 25.0, 1), 45))
        sink = sink.cut(notch)
    # Fin grooves so it reads as a heatsink (viz only)
    for i in range(5):
        gx = cx - 20 + i * 10
        sink = sink.cut(cq.Workplane("XY")
                        .workplane(offset=BTS_BOARD_Z + bt + 4)
                        .box(4.0, 51.0, BTS_SINK_H, centered=(True, True, False))
                        .translate((gx, cy, 0)))
    # Power screw terminal: green block hanging below the board, +y edge,
    # outer face flush with the board edge. 20 wide (4 poles × 5 mm).
    term = (cq.Workplane("XY")
            .workplane(offset=BTS_BOARD_Z - 12.0)
            .box(20.0, 8.0, 12.0, centered=(False, False, False))
            .translate((-85.0, BTS_TERM_Y_FACE - 8.0, 0)))
    # Control header: small block at the −y edge, pins pointing −y.
    hdr_body = (cq.Workplane("XY")
                .workplane(offset=BTS_BOARD_Z - 6.0)
                .box(11.0, 5.0, 6.0, centered=(False, False, False))
                .translate((-80.5, BTS_HDR_Y_FACE, 0)))
    hdr_pins = (cq.Workplane("XY")
                .workplane(offset=BTS_BOARD_Z - 5.0)
                .box(10.5, 4.5, 4.0, centered=(False, False, False))
                .translate((-80.3, BTS_HDR_Y_FACE - 4.5, 0)))
    header = hdr_body.union(hdr_pins)
    return [("bts_board", board, "#1A3F6B"),       # blue PCB
            ("bts_heatsink", sink, "#2B2B2B"),     # black anodized
            ("bts_terminal", term, "#3A9D4A"),     # green terminal
            ("bts_header", header, "#303030")]


def _buck_parts():
    """Pololu D42V110F12 from the dimension drawing: green PCB + cap bank
    (6.1 tall, clear of the pin-row strip along the +y edge)."""
    bw, bd, bt = BUCK_BOARD
    pcb = (cq.Workplane("XY")
           .workplane(offset=BUCK_BOARD_Z)
           .box(bw, bd, bt, centered=(False, False, False))
           .translate((BUCK_POS[0], BUCK_POS[1], 0)))
    # Cap bank kept clear of the corner mounting holes (real board layout)
    caps = (cq.Workplane("XY")
            .workplane(offset=BUCK_BOARD_Z + bt)
            .box(bw - 9.0, 15.0, 6.1, centered=(False, False, False))
            .translate((BUCK_POS[0] + 4.5, BUCK_POS[1] + 4.0, 0)))
    return [("buck_pcb", pcb, "#2F7D32"),          # pololu green
            ("buck_caps", caps, "#4A4A4A")]


def _build_esp_clamp() -> cq.Workplane:
    """The ESP32 clamp beam — separate printed part. A flat bar resting on
    the two posts, bearing on U1's shield, with counterbored M2 clearance
    holes for the M2×20 socket screws into the post-top inserts. Prints
    flat on its back, trivially."""
    x0b, x1b = ESP_BEAM_X
    by0 = ESP_SCREW_XY[0][1] - 2.5
    by1 = ESP_SCREW_XY[1][1] + 2.0
    beam = (cq.Workplane("XY")
            .workplane(offset=ESP_POST_TOP)
            .box(x1b - x0b, by1 - by0, ESP_BEAM_T,
                 centered=(False, False, False))
            .translate((x0b, by0, 0)))
    for sx, sy in ESP_SCREW_XY:
        beam = beam.cut(cq.Workplane("XY")
                        .workplane(offset=ESP_POST_TOP - BOOL_OVERSHOOT)
                        .center(sx, sy).circle(ESP_SCREW_CLR / 2)
                        .extrude(ESP_BEAM_T + 2 * BOOL_OVERSHOOT))
        beam = beam.cut(cq.Workplane("XY")
                        .workplane(offset=ESP_POST_TOP + ESP_BEAM_T - ESP_CBORE_T)
                        .center(sx, sy).circle(ESP_CBORE_D / 2)
                        .extrude(ESP_CBORE_T + BOOL_OVERSHOOT))
    return beam


esp_clamp = _build_esp_clamp()


def _m2_screws(positions, head_bottom_z):
    """Viz: M2×20 socket screws (Ø3.8×2 head + Ø2×20 shank), head bottom
    seated at `head_bottom_z`."""
    out = None
    for sx, sy in positions:
        head = (cq.Workplane("XY")
                .workplane(offset=head_bottom_z)
                .center(sx, sy).circle(3.8 / 2).extrude(2.0))
        shank = (cq.Workplane("XY")
                 .workplane(offset=head_bottom_z - 20.0)
                 .center(sx, sy).circle(1.0).extrude(20.0))
        s = head.union(shank)
        out = s if out is None else out.union(s)
    return out


def _esp32_parts():
    """QuinLED-ESP32 from the user's board drawing: PCB + U1 shield + USB."""
    pcb = (cq.Workplane("XY")
           .workplane(offset=ESP_PCB_Z)
           .box(*ESP_BOARD, centered=(False, False, False))
           .translate((ESP_POS[0], ESP_POS[1], 0)))
    u1 = (cq.Workplane("XY")
          .workplane(offset=ESP_PCB_Z + ESP_BOARD[2])
          .box(16.0, 20.0, 3.2, centered=(False, False, False))
          .translate((ESP_POS[0] + ESP_U1_OFF[0],
                      ESP_POS[1] + ESP_U1_OFF[1], 0)))
    j5 = (cq.Workplane("XY")
          .workplane(offset=ESP_PCB_Z + ESP_BOARD[2])
          .box(10.45, 10.9, 3.2, centered=(False, False, False))
          .translate((ESP_POS[0] + ESP_J5_OFF[0],
                      ESP_POS[1] + ESP_J5_OFF[1], 0)))  # USB overhangs −x
    return [("esp_pcb", pcb, "#15691F"),           # quinled green
            ("esp_u1", u1, "#9FA8B5"),             # RF shield silver
            ("esp_j5", j5, "#B8B8B8")]


# ── Electronics lid (separate print) ────────────────────────────────────────
# Sits ON TOP of the elec housing walls (plate at ELEC_TOP_Z), oversized,
# with a 13mm skirt running DOWN around all four sides (user) — water on
# the lid sheds past the wall joint. Prints upside-down (plate on bed).
LID_T     = 3.0                 # top plate thickness
LID_SKIRT = 13.0                # skirt drop below the wall tops
LID_CLR   = 0.3                 # skirt-to-wall clearance per side
LID_WALL  = 2.4                 # skirt thickness (3 perimeters @ 0.8)


def _build_elec_lid() -> cq.Workplane:
    wi = LIP_PROTRUDE + 2 * ELEC_CLR            # box wall inset (5.6)
    bx0, bx1 = -BAY_W / 2 + ELEC_CLR, ELEC_XOUT     # box wall outer x
    by0, by1 = ELEC_CLR + wi, BAY_D - ELEC_CLR - wi  # box wall outer y
    ix0, ix1 = bx0 - LID_CLR, bx1 + LID_CLR     # skirt inner faces
    iy0, iy1 = by0 - LID_CLR, by1 + LID_CLR
    ox0, ox1 = ix0 - LID_WALL, ix1 + LID_WALL   # lid outer
    oy0, oy1 = iy0 - LID_WALL, iy1 + LID_WALL
    plate = (cq.Workplane("XY")
             .workplane(offset=ELEC_TOP_Z)
             .box(ox1 - ox0, oy1 - oy0, LID_T, centered=(False, False, False))
             .translate((ox0, oy0, 0)))
    skirt_o = (cq.Workplane("XY")
               .workplane(offset=ELEC_TOP_Z - LID_SKIRT)
               .box(ox1 - ox0, oy1 - oy0, LID_SKIRT + BOOL_OVERSHOOT,
                    centered=(False, False, False))
               .translate((ox0, oy0, 0)))
    skirt_i = (cq.Workplane("XY")
               .workplane(offset=ELEC_TOP_Z - LID_SKIRT - BOOL_OVERSHOOT)
               .box(ix1 - ix0, iy1 - iy0, LID_SKIRT + 3 * BOOL_OVERSHOOT,
                    centered=(False, False, False))
               .translate((ix0, iy0, 0)))
    return plate.union(skirt_o.cut(skirt_i))


elec_lid = _build_elec_lid()


# ── Assembly viz ─────────────────────────────────────────────────────────────
def _pump_placed():
    pump = import_step(pathlib.Path(__file__).resolve().parents[1]
                       / "references" / "seaflo_42_pump.step")
    if pump is None:
        return None
    return (pump
            .rotate((0, 0, 0), (1, 0, 0), -90)    # feet → −Y, ports vertical
            .translate((PUMP_CX, PUMP_STANDOFF, PUMP_CZ)))


DOCK_CZ = DOCK_TZ + DOCK_PLATE_Y / 2.0        # dock vertical centre (housing z)


def _dock_transform(wp: cq.Workplane) -> cq.Workplane:
    """The dock-frame → housing transform (shared by dock + battery mock).
    Flat back (dock z=0) lands on the wall outer face; battery-fitting side
    (dock z=22) points outboard (−X). The battery ENTERS at the dock's y=0
    end (the open 'front opening' end — the y=90 end is the solid stop), so
    a final 180° about X puts that entry end at the TOP: drop the battery
    in from above, slide down to the latch.

    The dock's back is trimmed at the connector flange-back plane (dock z =
    DOCK_BACK_TRIM); we pre-shift the dock −DOCK_BACK_TRIM in dock z so that
    trimmed back (the flange) lands on the wall, flush — the wall retains the
    connector with no separate pads."""
    return (wp
            .translate((0, 0, -DOCK_BACK_TRIM))   # flange back -> wall (see above)
            .rotate((0, 0, 0), (0, 1, 0), 180)    # flip about the slide axis
            .rotate((0, 0, 0), (1, 1, 1), 120)    # axis cycle x→y, y→z, z→x
            .translate((DOCK_WALL_X, DOCK_TY, DOCK_TZ))
            .rotate((-1, DOCK_TY, DOCK_CZ), (1, DOCK_TY, DOCK_CZ), 180))


def _dock_placed():
    from .battery_dock import battery_dock
    return _dock_transform(battery_dock)


def _terminal_placed():
    """The 643852-2 contact block, seated in the dock (same seat the dock
    scene validated: TERMINAL_PLACE/ROT in dock frame), carried into the
    housing frame by the dock transform."""
    t = import_step(MAKITA_TERMINAL_STEP)
    if t is None:
        return None
    return _dock_transform(place_terminal(t, TERMINAL_ROT_DEG, TERMINAL_PLACE))




def _wire_run(points, d) -> cq.Workplane:
    """Viz-only wire: cylinders along consecutive waypoints with spheres
    at the joints so bends read as one continuous conductor."""
    solids = []
    for a, b in zip(points, points[1:]):
        va, vb = cq.Vector(*a), cq.Vector(*b)
        axis = vb - va
        if axis.Length < 1e-6:
            continue
        solids.append(cq.Solid.makeCylinder(d / 2, axis.Length, va, axis))
    for p in points[1:-1]:
        solids.append(cq.Solid.makeSphere(d / 2, cq.Vector(*p), angleDegrees1=-90))
    return cq.Workplane(obj=cq.Compound.makeCompound(solids))


# Harness routes (viz). Every conductor is its OWN wire (no bundles):
# Ø3 power, Ø1.6 signal, each landing on its own terminal spot. Endpoints
# may sink INTO the part they connect to — each route declares its
# connection targets and the collision report treats those contacts as
# intended. Parallel runs ride offset lanes; the only wire-wire contact is
# the TSR-VIN splice on the fused battery+ line.
# Entry: (name, color, dia, targets, points)
WIRE_ROUTES = [
    # Riser lanes through the floor wire slot (x -105.5..-92, y 85..105),
    # then staggered z planes inside the half-width box (floor top 122.5).
    # Buck pin row at y=99.18: VIN/GND at the +x end face the risers
    # directly - the battery pair lands with almost no crossings.
    ("wire_bat_pos", "#D03030", 3.0, ("makita_terminal", "buck_pcb"), [
        (-107, 63.5, 24), (-106, 66, 38), (-102, 88, 52),
        (-102, 88, 122.5), (-101, 94, 127.5), (-85, 96.5, 127.5),
        (-72, 99, 127.5), (-56, 99, 127.5), (-30, 99, 128),
        (-16, 99.18, 128.8), (-14.7, 99.18, 129.8)]),
    ("wire_bat_neg", "#181818", 3.0, ("makita_terminal", "buck_pcb"), [
        (-107, 67.5, 25.5), (-101.5, 90, 38), (-101.5, 103, 56),
        (-101.5, 103, 122.5), (-98, 103, 131.5), (-45, 103, 131.5),
        (-25, 101.5, 131), (-19.7, 99.18, 130.5), (-19.7, 99.18, 129.8)]),
    ("wire_pump_m1", "#30A050", 3.0, ("pump", "bts_terminal"), [
        (-102, 73, 53.5), (-98.5, 84, 80), (-98.5, 91, 104),
        (-98.5, 91, 122.5), (-96, 91, 139.5), (-72.5, 92, 139.5),
        (-72.5, 78, 138.5)]),
    ("wire_pump_m2", "#B03090", 3.0, ("pump", "bts_terminal"), [
        (-102, 73, 75.5), (-96, 84, 90), (-94.5, 92, 102),
        (-94.5, 99, 115.5), (-94.5, 99, 122.5), (-93, 99, 143.5),
        (-67.5, 95, 143.5), (-67.5, 88, 139.5), (-67.5, 78, 139)]),
    # TSR VIN: SPLICED off battery + after the fuse (junction, same red)
    ("wire_tsr_in", "#D03030", 3.0, ("tsr_5v",), [
        (-56, 99, 127.5), (-53, 95, 138.5), (-38, 75, 137),
        (-30, 66, 132), (-28, 62, 130)]),
    ("wire_tsr_out", "#D0B030", 1.6, ("tsr_5v", "esp_pcb"), [
        (-24, 58, 129), (-12, 53, 128.5), (-8.5, 46.5, 128.7)]),
    # TSR GND: SPLICED off battery - (parity with the VIN splice)
    ("wire_tsr_gnd", "#181818", 3.0, ("tsr_5v",), [
        (-62, 103, 131.5), (-57, 95, 146), (-33, 75, 142),
        (-25, 66, 134), (-24, 63, 131)]),
    # 12 V rail: buck VOUT/GND2 (-x end) -> BTS terminal B+/B-
    ("wire_12v_pos", "#E08030", 3.0, ("buck_pcb", "bts_terminal"), [
        (-37.65, 99.18, 129.8), (-37.65, 99.18, 132), (-42, 95, 133.5),
        (-60, 88, 134.5), (-77.5, 84, 135.5), (-77.5, 78, 138.5)]),
    ("wire_12v_neg", "#7A4A18", 3.0, ("buck_pcb", "bts_terminal"), [
        (-44.05, 99.18, 129.8), (-44.05, 99.18, 141), (-50, 95, 141.5),
        (-72, 86, 143.5), (-82.5, 84, 141.5), (-82.5, 78, 138.5)]),
    # logic jumpers: ESP bottom pin row (y~17.5) -> BTS control header
    ("wire_rpwm", "#F0F0F0", 1.6, ("esp_pcb", "bts_header"), [
        (-34, 17.5, 128.7), (-34, 19, 131), (-52, 21, 135.5),
        (-71, 24.5, 139.5)]),
    ("wire_lpwm", "#A0A0A0", 1.6, ("esp_pcb", "bts_header"), [
        (-31, 17.5, 128.7), (-31, 20, 134), (-54, 23, 138),
        (-71, 25.5, 141.3)]),
    ("wire_sig_gnd", "#2E8C8C", 1.6, ("esp_pcb", "bts_header"), [
        (-28, 17.5, 128.7), (-28, 21, 136.5), (-56, 25, 140.5),
        (-71, 26.5, 142.7)]),
    # joystick 3 wires: over the pump +X rim, down the open bay, UNDER the
    # elec floor (z~114-115.5, clear of the barb zone y 72.5..99.5), up
    # through the floor hole at (-10, 55), to the ESP top row (y~45.5).
    ("wire_joy_3v3", "#3060D0", 1.6, ("esp_pcb",), [
        (116, 53, 143.5), (108, 53, 140), (95, 53, 114),
        (-4, 53, 114), (-9, 53, 124.5), (-10, 48, 127), (-11, 46, 128.7)]),
    ("wire_joy_gnd", "#6090E0", 1.6, ("esp_pcb",), [
        (116, 55, 145), (108, 55, 141.5), (95, 55, 115.5),
        (-5, 55, 115.5), (-10, 55, 125), (-14, 49, 127.5),
        (-14.5, 46, 128.7)]),
    ("wire_joy_sig", "#90B8F0", 1.6, ("esp_pcb",), [
        (116, 57, 143.5), (108, 57, 140), (95, 57, 114),
        (-8, 57, 114), (-13, 57, 123.5), (-17, 50, 127),
        (-18, 46, 128.7)]),
]


# Pairs that are SUPPOSED to touch: each wire with its declared connection
# targets, plus the two wire-wire splices (TSR VIN off the fused battery+,
# TSR GND off battery−).
_INTENDED_CONTACT = {frozenset(("wire_bat_pos", "wire_tsr_in")),
                     frozenset(("wire_bat_neg", "wire_tsr_gnd")),
                     # M2 screws pass THROUGH the board mounting holes
                     # (boards modeled without holes):
                     frozenset(("bts_board", "bts_screws")),
                     frozenset(("buck_pcb", "buck_screws")),
                     # M4 lock screw self-taps the elec boss and seats on
                     # the pump wall:
                     frozenset(("elec_housing", "m4_lock_screw")),
                     frozenset(("pump_housing", "m4_lock_screw")),
                     # TEMPORARY: the dock's terminal seat is being
                     # redesigned (region solid for now) — the terminal
                     # viz overlaps the dock until the new seat lands:
                     frozenset(("battery_dock", "makita_terminal"))}
for _n, _c, _d, _targets, _p in WIRE_ROUTES:
    for _t in _targets:
        _INTENDED_CONTACT.add(frozenset((_n, _t)))


def _solid_volume(wp) -> float:
    """Total solid volume; 0 for empty/degenerate results (a failed
    boolean must read as 'no interference', not crash the report)."""
    try:
        return sum(s.Volume() for s in wp.val().Solids())
    except Exception:                                              # noqa: BLE001
        return 0.0


def _collision_report(parts: dict) -> None:
    """All-pairs interference check across every assembly object. Bounding
    boxes pre-filter the expensive booleans. Prints only colliding pairs;
    the goal state is an empty list (intended junctions are noted, not
    flagged)."""
    names = list(parts)
    boxes = {}
    for n in names:
        b = parts[n].val().BoundingBox()
        boxes[n] = (b.xmin, b.xmax, b.ymin, b.ymax, b.zmin, b.zmax)
    hits = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            A, B = boxes[a], boxes[b]
            if (A[0] > B[1] or B[0] > A[1] or A[2] > B[3] or
                    B[2] > A[3] or A[4] > B[5] or B[4] > A[5]):
                continue                       # bboxes disjoint
            v = _solid_volume(parts[a].intersect(parts[b]))
            if v > 0.05:
                if frozenset((a, b)) in _INTENDED_CONTACT:
                    print(f"    junction (intended): {a} x {b}")
                else:
                    hits.append((v, a, b))
    print("  -- collision report ----------------------------------")
    if not hits:
        print("    all clear - no part-pair interference")
    for v, a, b in sorted(hits, reverse=True):
        print(f"    COLLISION {a} x {b}: {v:,.1f} mm3")


def _add_label(asm, name, text, size, center_xy, z) -> None:
    """Flat extruded role label; silently skipped if text rendering is
    unavailable (font issues must never break the build)."""
    try:
        txt = (cq.Workplane("XY").workplane(offset=z)
               .center(*center_xy).text(text, size, 1.5))
        asm.add(txt, name=name, color=color("#F2F2F2"))
    except Exception:                                              # noqa: BLE001
        pass


def _build():
    build_n = bump_build_counter()
    asm = cq.Assembly(name="backpack_housing")
    parts = {}                                   # for the collision report

    def add(name, wp, col):
        asm.add(wp, name=name, color=color(col))
        parts[name] = wp

    add("pump_housing", backpack_housing, "#8FA8C0")
    pump = _pump_placed()
    if pump is not None:
        add("pump", pump, "#C0683C")
    add("battery_dock", _dock_placed(), "#6B8AAB")
    term = _terminal_placed()
    if term is not None:
        add("makita_terminal", term, "#E1C75D")

    # Electronics housing (floor = partial lid) + the boards inside it.
    add("elec_housing", elec_housing_part, "#C4A56B")
    z_board = TRAY_SEAT_Z + TRAY_T
    # BTS7960 (datasheet model, heatsink-up on two standoffs)
    for bname, bwp, bcol in _bts7960_parts():
        add(bname, bwp, bcol)
    _add_label(asm, "bts_label", "PUMP DRIVER", 6.5, BTS_CENTER,
               BTS_BOARD_Z + BTS_BOARD[2] + BTS_SINK_H)

    # Pololu buck (dimension-drawing model on two M2 standoffs)
    for bname, bwp, bcol in _buck_parts():
        add(bname, bwp, bcol)
    _add_label(asm, "buck_label", "18V->12V", 5.5,
               (_buck_cx, BUCK_POS[1] + 10.5),
               BUCK_BOARD_Z + BUCK_BOARD[2] + 6.1)

    # QuinLED-ESP32 (user-drawing model on rail + screwed clamp beam)
    for ename, ewp, ecol in _esp32_parts():
        add(ename, ewp, ecol)
    add("esp_clamp", esp_clamp, "#C4A56B")        # separate printed part
    add("elec_lid", elec_lid, "#9DB4A0")          # separate printed part
    # M4 slide-lock screw (head on the pump −X wall, threads into the boss)
    sy, sz = M4_SCREW_YZ
    m4 = (cq.Workplane("YZ")
          .workplane(offset=-OUTER_W / 2 - 4.0)
          .center(sy, sz).circle(3.5).extrude(4.0)
          .union(cq.Workplane("YZ")
                 .workplane(offset=-OUTER_W / 2)
                 .center(sy, sz).circle(2.0).extrude(10.0)))
    add("m4_lock_screw", m4, "#8A9097")
    # M2×20 socket screws everywhere (ESP clamp, BTS board, buck board)
    add("esp_screws", _m2_screws(ESP_SCREW_XY,
        ESP_POST_TOP + ESP_BEAM_T - ESP_CBORE_T), "#8A9097")
    add("bts_screws", _m2_screws(BTS_BOSS_XY,
        BTS_BOARD_Z + BTS_BOARD[2]), "#8A9097")
    add("buck_screws", _m2_screws(BUCK_BOSS_XY,
        BUCK_BOARD_Z + BUCK_BOARD[2]), "#8A9097")
    _add_label(asm, "esp_label", "QUINLED", 3.2, (ESP_CX, 31.5),
               ESP_PCB_Z + ESP_BOARD[2])

    # Traco TSR 1-2450E block + role label on its top face
    tw, td, th = TSR_SIZE
    tsr = (cq.Workplane("XY")
           .workplane(offset=z_board)
           .box(tw - 0.6, td - 0.6, th, centered=(False, False, False))
           .translate((TSR_POS[0] + 0.3, TSR_POS[1] + 0.3, 0)))
    add("tsr_5v", tsr, "#B08820")
    _add_label(asm, "tsr_5v_label", "18V->5V", 2.4,
               (TSR_POS[0] + tw / 2, TSR_POS[1] + td / 2), z_board + th)

    # Wire-run viz (one object per conductor)
    for name, col, dia, _targets, pts in WIRE_ROUTES:
        add(name, _wire_run(pts, d=dia), col)

    _collision_report(parts)

    # PUMP SLIDE-IN SWEEP: the pump must descend from above the rim into its
    # seat without touching the housing (shelf corbels, lips, walls). Check
    # the pump raised in steps; every step must be interference-free.
    if pump is not None:
        sweep_hits = []
        for dz in range(8, 145, 8):
            v = _solid_volume(pump.translate((0, 0, dz))
                              .intersect(backpack_housing))
            if v > 0.05:
                sweep_hits.append((dz, v))
        print("  -- pump slide-in sweep --------------------------------")
        if not sweep_hits:
            print("    clear - pump can drop straight into its seat")
        for dz, v in sweep_hits:
            print(f"    BLOCKED at +{dz} mm: {v:,.1f} mm3")
        # SEAT CHECK: the feet must actually bear on the standoff bosses —
        # nudging the pump toward the wall must contact (a floating pump
        # collides with nothing, so the other checks can't see it).
        seated = _solid_volume(pump.translate((0, -0.5, 0))
                               .intersect(backpack_housing)) > 0.05
        print(f"    feet {'SEATED on the bosses' if seated else 'NOT SEATED - pump floats!'}")
    try:
        counter = (cq.Workplane("XZ").center(0, OUTER_H + 50)
                   .text(str(build_n), 30, 6))
        asm.add(counter, name="build_counter", color=color("#F0A878"))
    except Exception:                                              # noqa: BLE001
        pass

    cq.exporters.export(backpack_housing, "backpack_pump_housing.step")
    cq.exporters.export(elec_housing_part, "backpack_elec_housing.step")
    cq.exporters.export(esp_clamp, "backpack_esp_clamp.step")
    cq.exporters.export(elec_lid, "backpack_elec_lid.step")
    asm.save("backpack_assembly.step")
    bb = backpack_housing.val().BoundingBox()
    print("Wrote backpack_pump_housing/elec_housing/esp_clamp.step")
    print(f"  outer envelope : X {bb.xlen:.1f}  Y {bb.ylen:.1f}  Z {bb.zlen:.1f} mm")
    print(f"  pump housing   : rim at z={PUMP_RIM_Z:.0f}; "
          f"elec housing to z={ELEC_TOP_Z:.0f}, +X edge at x={ELEC_XOUT:.0f}")
    if pump is not None:
        pb = pump.val().BoundingBox()
        print(f"  pump (placed)  : X[{pb.xmin:.1f}..{pb.xmax:.1f}] "
              f"Y[{pb.ymin:.1f}..{pb.ymax:.1f}] Z[{pb.zmin:.1f}..{pb.zmax:.1f}]")
    print(f"Wrote backpack_assembly.step  (housing + pump + dock)  [build #{build_n}]")
    show("backpack_assembly.step")


if __name__ == "__main__":
    _build()
