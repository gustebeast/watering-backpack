"""The watering-backpack v2 main board — circuit, outline and placement.

    py -3.12 elec/main.py
    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/finish.py elec/out/main

Design rationale lives in elec/CIRCUIT.md; this file is the executable version of
it. Where a number has a reason, the reason is beside it.

ONE RAIL SETS EVERYTHING: a Makita 18 V LXT pack is ~20 V fresh and ~15 V flat,
and it is the only supply on the board. So every part on VBAT is rated >= 40 V,
and the pump FETs >= 60 V so the inductive clamp has real margin. 24 V-max buck
parts (MP2315, AP63203) sit 4 V from a fresh pack before any switching spike and
are explicitly rejected.

NO H-BRIDGE: each pump runs ONE direction only — direction is chosen by which
pump is energised, not by polarity — so each needs a single low-side switch.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cadkit.pcbflow import gen  # noqa: E402
from elec.quality_signoff import MANUAL as QUALITY_MANUAL  # noqa: E402

OUT_DIR = gen.begin(__file__)           # before skidl is imported — see gen.begin

from skidl import Net  # noqa: E402

# ── Design figures ──────────────────────────────────────────────────────────
VBAT_MAX = 20.0          # fresh Makita pack
VBAT_MIN = 15.0          # flat
PUMP_A   = 7.5           # per pump, peak

# Battery sense divider: VBAT_MAX must land under 3.3 V at the ADC with margin.
# 100k/18k -> 20 V * 18/118 = 3.05 V. 100k top leg keeps idle draw ~170 uA.
RDIV_TOP, RDIV_BOT = "100k", "18k"

# ── The buck's feedback divider, DERIVED from the datasheet's own reference ──
# It was R1=100k / R2=31k6, with the comment "FB bottom -> 3.3 V". It is not
# 3.3 V. LMR14020's VFB is 0.750 V typ (SNVSAA5B, 5.5 Electrical
# Characteristics: 0.744 / 0.750 / 0.756 at 25 C), so 100k/31k6 sets
# 0.75 x (1 + 100/31.6) = 3.12 V -- 5.4% low, on the rail that is also the ADC
# reference for the battery gauge and the joystick.
#
# Written as arithmetic so the comment can no longer disagree with the part.
BUCK_VFB   = 0.750       # V, LMR14020 datasheet
FB_TOP     = "100k"      # datasheet recommends 10k..100k for the BOTTOM leg
FB_BOT     = "29k4"      # E96. 100k * 0.75 / (3.3 - 0.75) = 29.41k
FB_VOUT    = BUCK_VFB * (1.0 + 100.0 / 29.4)
assert abs(FB_VOUT - 3.3) < 0.03, (
    "the feedback divider sets %.3f V, not 3.3" % FB_VOUT)

# RT/SYNC: the datasheet's own table, 500 kHz.
BUCK_FSW_KHZ = 500.0
BUCK_RT      = "49k9"


def _house(v, unit):
    """4.6, 'A' -> '4A6'. The letter is the decimal point, as in 29k4 and 4u7."""
    whole = int(v)
    tenth = int(round((v - whole) * 10))
    return "%d%s%d" % (whole, unit, tenth) if tenth else "%d%s" % (whole, unit)


# ── The buck inductor, DERIVED from the regulator's CURRENT LIMIT ───────────
# ⚠ THIS WAS A 15 uH PART AND THE DATASHEET FORBIDS IT, in those words.
# SNVSAA5B 7.2.2.3, Output Inductor Selection: "The inductor current rating
# must be higher than current limit", because "during an instantaneous short or
# over current operation event, the RMS and peak inductor current can be high".
# The high-side current limit is 2.5 / 3.2 / 3.8 A min/typ/max (5.5 Electrical
# Characteristics), so the number the inductor must beat is 3.8 A.
#
# The part fitted was a Bourns SRN6045TA-150M: Isat 3.80 A TYP. Not above the
# limit -- equal to it, and equal to the *typical* at that, so half the reel
# saturates below a fault the regulator is entitled to sustain indefinitely.
# TI's own design example in the same section sizes "3 A RMS current and 4 A
# saturation current" against the same limit, so this is not a strict reading.
#
# Going UP in inductance makes it worse, which is the part that is not obvious:
# in this series Isat falls as L rises (22 uH is 3.30 A, 33 uH is 2.50 A). The
# fix is DOWN. SRN6045TA-100M, same series, same 6045 land, same price:
#
#   SRN6045TA-100M   10 uH +-20%   DCR 52 mOhm   Irms 3.20 A   Isat 4.60 A
#   SRN6045TA-150M   15 uH +-20%   DCR 71 mOhm   Irms 2.80 A   Isat 3.80 A
#
# (Bourns SRN6045TA datasheet, Electrical Specifications @ 25 C. Read its own
# definitions before comparing these to another maker's: this series quotes
# Isat where "inductance drops 30 %" -- a LOOSER definition than the common
# 20 % -- and Irms at a 40 C rise, not 20.)
#
# 10 uH is also what the datasheet's inductance equation asks for. K_IND is
# "the amount of inductor ripple current relative to the MAXIMUM OUTPUT
# CURRENT" and "must be 20%-40%": against this part's rated 2 A that window is
# 6.9..13.8 uH, and 10 sits in the middle of it. Sizing K_IND against this
# board's 0.6 A load instead would ask for 23..46 uH, and every one of those
# saturates below the current limit -- which is how a 2 A regulator used at
# 0.6 A talks you into an inductor its own fault current destroys.
# ⚠ THE BUCK HAD NO CATCH DIODE, AND IT IS NOT A SYNCHRONOUS PART.
# The LMR14020 integrates ONE switch: "90mOhm high-side MOSFET" (features), "It
# integrates a 90 mOhm (typical) high-side MOSFET" (6.1). There is no low-side
# device in it, so the inductor current has nowhere to go when that switch opens
# unless an external rectifier gives it a path. The datasheet is not subtle
# about this -- 6.3 describes the current freewheeling "through freewheel diode
# with a slope of -VOUT / L", 6.3 again says "the high-side MOSFET is off and the
# EXTERNAL LOW SIDE DIODE conducts", Figure 7-1's application circuit carries a
# component D, 7.2.2.5 is a whole section called Schottky Diode Selection, and
# the layout example on the facing page labels it "Rectifier Diode".
#
# This board had L1, C15, C3, C4, C5, R1, R2, R8 and C14 -- every external part
# in that figure EXCEPT D. With the switch open the SW node is driven negative
# by the inductor until something conducts, and SW's absolute minimum is -3 V
# (5.1). The 3V3 rail would not have come up, which means no MCU, no joystick
# reading and no logic for the gate drivers: the whole board, not just the buck.
#
# THE PART, from 7.2.2.5's own rules:
#   "The breakdown voltage rating of the diode is preferred to be 25% higher
#   than the maximum input voltage" -- 1.25 x 20 V = 25 V, which is the floor.
#   60 V is used instead, for the reason the module docstring gives: everything
#   on this node is rated past a fresh pack AND past the TVS's 38.9 V clamp,
#   and SW's own absolute maximum is 44 V. It also makes this the same
#   requirement as the pump freewheels, one fewer number to get wrong.
#   "The current rating for the diode must be equal to the maximum output
#   current ... A 2.5 A to 3 A rated diode is a good starting point" -- 3 A.
#   The average is far below that: (1 - D) x IOUT = 0.835 x 0.6 = 0.50 A.
BUCK_CATCH_VR_MIN = 60.0     # V, see above; the datasheet's own floor is 25
BUCK_CATCH_IF_MIN = 3.0      # A, SNVSAA5B 7.2.2.5's own starting point
BUCK_CATCH_VALUE  = "SCHOTTKY-%.0fV-%.0fA" % (BUCK_CATCH_VR_MIN, BUCK_CATCH_IF_MIN)
BUCK_CATCH_I_AVG  = (1.0 - 3.3 / VBAT_MAX) * 0.6
assert BUCK_CATCH_VR_MIN >= 1.25 * VBAT_MAX, (
    "SNVSAA5B 7.2.2.5 wants the catch diode 25%% above the maximum input: "
    "%.0f V against a %.0f V pack needs %.1f" % (BUCK_CATCH_VR_MIN, VBAT_MAX,
                                                 1.25 * VBAT_MAX))
assert BUCK_CATCH_IF_MIN > BUCK_CATCH_I_AVG * 2.0, (
    "the catch diode carries %.2f A average and is rated %.1f"
    % (BUCK_CATCH_I_AVG, BUCK_CATCH_IF_MIN))

BUCK_ILIM_MAX   = 3.8        # A, SNVSAA5B 5.5, high-side current limit, max
BUCK_L_UH       = 10.0
BUCK_L_ISAT     = 4.6        # A, SRN6045TA-100M, Isat typ (30 % L drop)
BUCK_L_IRMS     = 3.2        # A, same row, Irms typ (40 C rise)
BUCK_IOUT_RATED = 2.0        # A, what the LMR14020 is
BUCK_IOUT       = 0.6        # A, what this board asks of it (= the +3V3 path)
# peak-to-peak ripple, worst case at the HIGHEST input (smallest duty)
BUCK_RIPPLE_A = (3.3 * (1.0 - 3.3 / VBAT_MAX)
                 / (BUCK_L_UH * 1e-6 * BUCK_FSW_KHZ * 1e3))
BUCK_IPK      = BUCK_IOUT + BUCK_RIPPLE_A / 2.0
BUCK_K_IND    = BUCK_RIPPLE_A / BUCK_IOUT_RATED
assert BUCK_L_ISAT > BUCK_ILIM_MAX, (
    "the inductor saturates at %.1f A and the buck's current limit reaches "
    "%.1f A: SNVSAA5B 7.2.2.3 says the inductor must be the larger"
    % (BUCK_L_ISAT, BUCK_ILIM_MAX))
assert BUCK_IPK < BUCK_L_ISAT / 2.0, (
    "the inductor peaks at %.2f A in normal running against %.1f A of Isat: "
    "less than 2x is not margin on a typ-only number" % (BUCK_IPK, BUCK_L_ISAT))
assert 0.20 <= BUCK_K_IND <= 0.40, (
    "K_IND is %.2f of the part's rated %.1f A; SNVSAA5B 7.2.2.3 wants 0.20..0.40"
    % (BUCK_K_IND, BUCK_IOUT_RATED))
# The value carries the rating the asserts above check, so a substitution has to
# satisfy them rather than silently inherit a number nobody re-read.
# ── The OUTPUT capacitance, derived from 7.2.2.4's own equations ───────────
# ⚠ WHAT THE DATASHEET DOES NOT SAY. Its worked example ends "For stability
# consideration, one 47 uF output capacitor is needed at least", and that
# sentence has NO equation behind it and sits inside "For this design example"
# -- a 5 V / 2 A design, not this one. It is not a general floor that can be
# checked, so it is not what this board is sized against. What CAN be checked
# is equations 11 to 14, applied to this board's own numbers.
#
# The ceiling on undershoot is a BROWNOUT, not a preference: the ESP32's VDD33
# minimum is 3.0 V (WROOM-32E v2.1 table 14) against a 3.301 V rail, so there
# are 301 mV in total and 200 mV is that with margin. The load step is the
# module going from idle to the 0.5 A WiFi burst Espressif specifies.
#
#   eq 13, undershoot  3 x (IOH - IOL) / (fSW x VUS)        -> 16.5 uF
#   eq 14, overshoot   L x (IOH^2 - IOL^2) / ((VOS+V)^2-V^2) ->  2.6 uF
#   eq 12, ripple      diL / (8 x fSW x dVc)  at 20 mV      ->  6.9 uF
#   eq 11, ESR         dVc / diL              at 20 mV      -> < 36 mOhm
#
# So 16.5 uF is the binding number, and C4's 22 uF clears it by 1.33x NOMINAL
# -- and not at all once bias is allowed for. The part is unsourced, so there
# is no maker curve to read (M15), and a 0.6 derate is the pessimistic end for
# a 16 V X7R 1206 at 3.3 V: 13.2 uF against 16.5 needed. That is the finding.
#
# TWO 22 uF RATHER THAN ONE 47. Same value, so it adds no part number and A11
# stays true; two in parallel halve the ESR; and 44 uF nominal / 26.4 uF
# derated is 2.67x and 1.60x. It also lands beside the example's 47 uF, which
# is reassurance rather than evidence. For reference, sizing this rail at the
# 2 % that A1 holds its DC drop to would ask for 50 uF -- not done, because 2 %
# is a drop budget for a reference rail and not a transient spec, and saying
# otherwise would be inventing a requirement.
# ⚠ AND THE 0.6 DERATE ASSUMES X7R, SO X7R IS A REQUIREMENT AND NOT A HOPE.
# "22u/16V" does not state a dielectric, and the derate is the whole argument
# here: an X7R 1206 at 3.3 V on a 16 V part keeps well over 60 %, but a Y5V or
# Z5U of the same marking can lose 80 % and land at 8.8 uF -- under eq 13's
# 16.5 and with nothing in the gate to notice. Both output capacitors are X7R
# or better, class II, and that is recorded as do-not-substitute under M40.
BUCK_COUT_DIELECTRIC = "X7R"
BUCK_VUS_MAX     = 0.200     # V, the brownout ceiling with margin
BUCK_ISTEP_LO    = 0.05      # A, the module idling
BUCK_ISTEP_HI    = 0.6       # A, the declared WiFi burst
BUCK_COUT_NOM    = 44e-6     # C4 + C19, both 22u/16V 1206
BUCK_COUT_DERATE = 0.6       # pessimistic, because the part is not sourced yet
BUCK_COUT_EQ13   = 3.0 * (BUCK_ISTEP_HI - BUCK_ISTEP_LO) / (
    BUCK_FSW_KHZ * 1e3 * BUCK_VUS_MAX)
assert BUCK_VUS_MAX < 3.3 - 3.0, (
    "a %.0f mV undershoot on a 3.3 V rail reaches the ESP32's 3.0 V minimum"
    % (BUCK_VUS_MAX * 1000))
assert BUCK_COUT_NOM * BUCK_COUT_DERATE > BUCK_COUT_EQ13, (
    "SNVSAA5B eq 13 asks for %.1f uF and %.0f uF derated to %.0f%% is %.1f"
    % (BUCK_COUT_EQ13 * 1e6, BUCK_COUT_NOM * 1e6, BUCK_COUT_DERATE * 100,
       BUCK_COUT_NOM * BUCK_COUT_DERATE * 1e6))

BUCK_L_VALUE = "%.0fuH/%ssat" % (BUCK_L_UH, _house(BUCK_L_ISAT, "A"))

# ── VGATE, the gate-driver rail ─────────────────────────────────────────────
GATE_DRV_VDD_MIN = 4.5       # UCC27517 datasheet, "4.5 to 18-V Single-Supply Range"
GATE_DRV_VDD_MAX = 18.0
VGATE_V      = 10.0
VGATE_R_OHM  = 1500.0
VGATE_R      = "1k5"
VGATE_ZENER  = "ZENER-%.0fV-0W5" % VGATE_V
VGATE_I_MIN_MA = (VBAT_MIN - VGATE_V) / VGATE_R_OHM * 1000.0
VGATE_LOAD_MA  = 1.5         # driver Iq + Qg x fsw, one pump at 20 kHz
assert GATE_DRV_VDD_MIN <= VGATE_V <= GATE_DRV_VDD_MAX, (
    "VGATE is %.1f V; the gate driver wants %.1f..%.1f"
    % (VGATE_V, GATE_DRV_VDD_MIN, GATE_DRV_VDD_MAX))
assert VGATE_I_MIN_MA > VGATE_LOAD_MA, (
    "at a %.0f V pack the dropper passes %.1f mA and the drivers want %.1f: "
    "VGATE collapses" % (VBAT_MIN, VGATE_I_MIN_MA, VGATE_LOAD_MA))
# R9's own rating, which nothing checked. The dropper stands across VBAT - VGATE
# the whole time the pack is on: at a FRESH pack that is 10 V across 1k5, and
# R9 is an 0805 -- 0.125 W, the standard rating for that size. 67 mW is 54 % of
# it, which is margin but not much, and it is the reason R9 is 0805 and not the
# 0603 every other resistor on this board is.
VGATE_R_W_MAX = 0.125        # W, a standard 0805 thick-film
VGATE_R_W     = (VBAT_MAX - VGATE_V) ** 2 / VGATE_R_OHM
assert VGATE_R_W < VGATE_R_W_MAX * 0.75, (
    "R9 burns %.0f mW at a fresh pack against an 0805's %.0f mW: that is %.0f %% "
    "of rating, and a dropper runs at it continuously"
    % (VGATE_R_W * 1000, VGATE_R_W_MAX * 1000, 100 * VGATE_R_W / VGATE_R_W_MAX))

# ── Ceramic voltage ratings: 2x the rail, and the rail written down ────────
# ⚠ EVERY CERAMIC ON THIS BOARD NOW STATES ITS RATING, because two of them sat
# on a rail nobody had checked them against. PCB_QUALITY M4: "a ceramic at its
# rated voltage has lost most of its capacitance -- use >= 2x the rail".
#
#   C13 was 10u/16V on VGATE. VGATE is 10 V, so that is 1.6x -- under the rule,
#        and an 0805 X5R at 10 V of bias keeps well under half its marking.
#   C9/C10 were plain "100n", which is a value with no rating at all, and they
#        are the UCC27517 bypasses: also on VGATE, also 10 V. A generic 0603
#        100n can be a 16 V part, and nothing here said it could not be.
#
# The fix is one spelling for all of them rather than a third value: 50 V is
# what a commodity 0603 X7R 100n already is, so "100n/50V" costs nothing, keeps
# A11's one-value-one-spelling, and removes the question everywhere at once --
# including C3, the bootstrap, whose 100n sits on a node the datasheet rates to
# 49 V even though it only ever sees BOOT-SW.
CAP_100N  = "100n/50V"
CAP_VGATE = "10u/25V"        # 2.5x a 10 V rail, same 0805 land as the 16 V part
# ⚠ AND THEN THE 16 V PART WENT AWAY TOO, so there is ONE 10 uF on this board.
# PCB_QUALITY M42 asks for the distinct part-number count to be looked at, and
# for "same value and package at different ratings to collapse to the stricter
# one". This was exactly that case and nothing had noticed: 10u/16V on C5, C6
# and C16 and 10u/25V on C13, same value, same 0805 land, two BOM lines, two
# reels, and two visually identical parts to keep apart on the bench.
#
# They collapse upward, and upward is not merely the tidier direction -- it is
# the better capacitor. C5/C6/C16 sit on +3V3, where 16 V was already 4.8x the
# rail and the rule only wants 2x, so nothing needed 16 V; and a 25 V 0805 holds
# MORE of its marking at 3.3 V of bias than a 16 V one does, because DC-bias
# rolloff scales with how close the bias is to the rating. So the strictest part
# is also the one with the most capacitance where it is used.
CAP_10U   = CAP_VGATE        # the board's only 10 uF: +3V3 bulk and VGATE alike

# ── What the board hands to a cable, and what limits it ────────────────────
# ⚠ VBAT LEFT THIS BOARD UNFUSED, down the most exposed conductor in the whole
# machine. J5 feeds the level sensor, and that lead leaves the sealed bay
# through the chase and then climbs the OUTSIDE of the case to the tank -- so it
# is the one wire that gets rubbed, pinched and walked past. Behind it is a
# Makita 18 V LXT pack, which will put well over a hundred amps into a short,
# and the killswitch at the dock is a SWITCH, not a fuse: it opens when someone
# opens it, not when a chafed sensor lead decides to glow.
#
# PCB_QUALITY M36 asks for a current limit on any supply the board offers to a
# cable, "so a short at the far end does not take the board's own rail down or
# burn the cable", and the second half is the one that matters here.
#
# A RESETTABLE PTC, not a cartridge fuse, and for a reason about this machine:
# it is carried into a garden, and a blown fuse out there is a walk home. A PPTC
# recovers when the fault is removed. 0.2 A of hold current against a sensor
# that draws about 10 mA is twenty times headroom -- no nuisance trips from
# inrush into C18 -- while still being far below what damages the thin lead it
# protects. 30 V is the common 1206 PPTC tier and clears a 20 V fresh pack.
LVL_FUSE_V_MIN  = 30.0       # V, must clear a fresh pack
LVL_FUSE_I_HOLD = 0.2        # A, hold current
LVL_SENSOR_I_MA = 10.0       # the XKC-Y25's own draw, the number holds against
LVL_FUSE_VALUE  = "PTC-%.0fV-%.0fmA" % (LVL_FUSE_V_MIN, LVL_FUSE_I_HOLD * 1000)
assert LVL_FUSE_V_MIN > VBAT_MAX, (
    "a %.0f V PTC on a %.0f V pack is not a rating" % (LVL_FUSE_V_MIN, VBAT_MAX))
assert LVL_FUSE_I_HOLD * 1000 > LVL_SENSOR_I_MA * 5.0, (
    "%.0f mA of hold current against a %.0f mA load leaves no room for inrush"
    % (LVL_FUSE_I_HOLD * 1000, LVL_SENSOR_I_MA))

# ⚠ AND ESP_RX CAN BACK-POWER A DEAD 3V3 RAIL THROUGH A GPIO. J6 pin 4 goes
# straight to the module's U0RXD. An adapter can hold that pin at 3.3 V while
# this board's own 3V3 is down -- the pack out of the dock, which is the
# ordinary way someone programs it -- and the current then flows through the
# pin's ESD diode into a 52 uF rail and whatever else is on it. J6 pin 1 is
# +3V3, so the INTENDED use is for the adapter to power the board, which is why
# this has never bitten; but M18 is about what can happen, and landing only
# TX/RX/GND is a normal thing to do.
#
# M18 names the fix: "a series resistor, a powered-off-tolerant buffer or
# guaranteed sequencing". 1k holds the diode current to about 2.7 mA, and at
# 115200 baud it costs nothing -- 1k into the pin's 2 pF plus a little trace is
# tens of nanoseconds against an 8.7 us bit. It is also a value already on this
# board (R22, R24), so it adds no part number.
PROG_RX_SERIES = "1k"

# Joystick RC: the ONLY noise defence, since there is no joystick board to buffer
# at the source. 1k + 100n = 1.6 kHz — far above a hand, far below switching.
RC_R, RC_C = "1k", CAP_100N

# ── Pump power semiconductors: REQUIREMENTS, not part numbers ───────────────
# CIRCUIT.md §1 fixes both, and the value strings below are DERIVED from these
# numbers so a value can no longer assert a rating the design did not ask for.
# That is not hypothetical. This board previously carried:
#
#   Q1/Q2  "AOD4184A-60V"   -- AOD4184A is a 40 V part. §1 requires >= 60 V and
#                              rejects 40 V by name: "40 V leaves ~20 V of
#                              margin over a fresh pack; 60 V leaves 40. The
#                              part costs the same."
#   D2/D3  "SS16H-60V-15A"  -- SS16H is a 1 A 60 V SMA diode. §1 requires
#                              >= 15 A in D2PAK, and this one sits in a
#                              TO-263-2 land carrying ~3.75 A average and 7.5 A
#                              peak. It would not have survived.
#
# The 40 V FET also broke the protection coordination: the SMBJ24A was chosen
# because its ~39 V clamp sits under the FET rating, and 39 of 40 V is no margin
# at all. The assert below is that coupling, written down.
PUMP_FET_VDS_MIN   = 60.0        # V, CIRCUIT.md §1
PUMP_FET_RDSON_MAX = 10.0        # mOhm at 4.5 V Vgs
FREEWHEEL_VR_MIN   = 60.0        # V
FREEWHEEL_IF_MIN   = 15.0        # A
PUMP_FET_VGS_MAX   = 20.0        # V, the +-20 V every DPAK N-FET in this class has
# ⚠ 38.9, NOT "39.0, approx". The clamp voltage is the number EVERY part on VBAT
# is judged against, so it is read off the table, not rounded from memory:
# Littelfuse SMBJ24A, 24 V standoff, 26.7 V min breakdown, VC = 38.9 V MAX at
# IPP = 15.5 A, 600 W. That is the worst case the board sees, and the three
# asserts below are the three parts it has to survive.
TVS_CLAMP          = 38.9        # V, SMBJ24A VC max at 15.5 A Ipp
BUCK_VIN_ABSMAX    = 44.0        # V, SNVSAA5B 5.1, VIN/EN to GND
BUCK_VIN_RECMAX    = 40.0        # V, SNVSAA5B 5.3, recommended operating
assert TVS_CLAMP < PUMP_FET_VDS_MIN, (
    "the TVS clamps at %.1f V; a pump FET rated %.0f V has no margin behind it"
    % (TVS_CLAMP, PUMP_FET_VDS_MIN))
# THE BUCK IS ON THE SAME NODE AS THE FETS AND IS THE WEAKEST THING ON IT. The
# assert above only ever coupled the clamp to the FETs, which are the part with
# the MOST margin behind it (21.1 V). U1's VIN pin sits on the same copper with
# 5.1 V of absolute maximum and 1.1 V of recommended maximum left -- so the TVS
# is what keeps the buck inside its datasheet, and raising the clamp by 1.2 V
# would take it outside while the FETs still looked fine.
assert TVS_CLAMP < BUCK_VIN_RECMAX, (
    "the TVS clamps at %.1f V and the buck's recommended maximum VIN is %.0f: "
    "a clamp event runs U1 outside its datasheet" % (TVS_CLAMP, BUCK_VIN_RECMAX))
assert TVS_CLAMP < BUCK_VIN_ABSMAX, (
    "the TVS clamps at %.1f V and the buck's VIN absolute maximum is %.0f"
    % (TVS_CLAMP, BUCK_VIN_ABSMAX))
# The GATE side of the same FET. VGATE is a shunt-regulated rail, so the number
# the gate sees is set by D5 and not by the pack, and the only way it reaches
# the FET's +-20 V is if D5 is the wrong Zener or is not fitted -- in which case
# R9 pulls the gate rail to the pack and 20 V arrives at a gate rated 20 V. This
# is why there is a Zener and not just a dropper, written as a check.
# The buck's catch diode sits on SW, and SW follows VIN whenever the high-side
# switch is on -- so a clamp event arrives there too, at the same 38.9 V.
assert BUCK_CATCH_VR_MIN > TVS_CLAMP, (
    "the catch diode is rated %.0f V and the TVS clamps at %.1f: SW follows "
    "VIN, so the clamp arrives at the rectifier as well"
    % (BUCK_CATCH_VR_MIN, TVS_CLAMP))
assert VGATE_V < PUMP_FET_VGS_MAX * 0.75, (
    "VGATE is %.1f V against a %.0f V gate rating: a shunt rail wants real "
    "headroom, because the failure mode of the shunt is the full pack"
    % (VGATE_V, PUMP_FET_VGS_MAX))
# Neither part is sourced. The value carries the REQUIREMENT so that whoever
# sources it has to satisfy it, and elec/fab.py counts both as open.
PUMP_FET_VALUE  = "NFET-%.0fV-%.0fmR" % (PUMP_FET_VDS_MIN, PUMP_FET_RDSON_MAX)
# ── What the pack sees at the instant it is docked (M16) ───────────────────
# ⚠ THE INRUSH HALF OF M16 WAS LEFT OPEN FOR A NUMBER THAT IS NOT NEEDED. The
# note said the surge "has not been computed against their rating, because the
# dock is not part of this repo and its contact rating has not been read" --
# true of the rating, and the wrong conclusion, because the ENERGY does not
# depend on any resistance at all and the I2t can be bounded over every
# resistance that is physically possible.
#
# The pack is docked live, so at the moment of contact it charges every
# capacitor on VBAT from 0 to the pack voltage. C18 is behind F1 and its inrush
# is limited by the PTC rather than by the contacts, but it is counted anyway
# because counting it is the conservative direction.
VBAT_BULK_F = (100e-6      # C1, electrolytic
               + 100e-6    # C2, electrolytic
               + 10e-6     # C17, J1's bypass
               + 4.7e-6    # C15, the buck's input ceramic
               + 10e-6)    # C18, behind F1
VBAT_INRUSH_J = 0.5 * VBAT_BULK_F * VBAT_MAX ** 2        # 0.045 J
# I2t over an RC charge is V^2*C/(2R), so the LOWEST plausible loop resistance
# is the worst case. 60 mOhm is already below what two electrolytics' ESR, the
# harness and a pair of blade contacts can be between them; the figure is a
# deliberate floor rather than an estimate.
VBAT_LOOP_R_MIN = 0.06                                    # ohm, a floor
VBAT_INRUSH_I2T = VBAT_MAX ** 2 * VBAT_BULK_F / (2 * VBAT_LOOP_R_MIN)
# ⚠ AND THE COMPARISON NEEDS NO DATASHEET EITHER. An I2t expressed as the
# protection's OWN rated current tells you how long that current would have to
# flow to do the same heating -- and a 10 A fuse carries 10 A indefinitely, so
# anything that comes out in milliseconds is unconditionally inside it.
FUSE_ATC_A = 10.0                       # the off-board ATC fuse in the + lead
VBAT_INRUSH_EQ_MS = 1000.0 * VBAT_INRUSH_I2T / FUSE_ATC_A ** 2
assert VBAT_INRUSH_EQ_MS < 100.0, (
    "the dock inrush is %.1f ms of the fuse's own rated current: that is no "
    "longer self-evidently inside it, and the fuse's I2t has to be read"
    % VBAT_INRUSH_EQ_MS)
assert VBAT_INRUSH_J < 0.5, (
    "%.3f J of make-arc at the dock contacts is past what a bounding argument "
    "covers; read the contact's make rating" % VBAT_INRUSH_J)


# ── REVERSE POLARITY: what D1 has to survive, and why it is a SHUNT ────────
# WORK_V2_PUNCHLIST item 10. Three documents promised a reverse-polarity P-FET
# this board does not have. The argument that made it optional -- "the Makita
# terminal is KEYED" -- died when the inlet became J1, a 5.08 mm screw terminal
# carrying two identical wires, and nobody went back to it. No gate here can see
# that: every gate reads the BOARD, and the claim lived in PROSE.
#
# ⚠ THE PUNCHLIST FRAMED THE FIX AS A SERIES ELEMENT and that framing is what
# made it look expensive. A series P-FET or ideal-diode controller means
# SPLITTING THE VBAT POUR into two islands bridged by the part -- a re-layout of
# the board's highest-current path, on a board at zero findings. But reverse
# polarity protection by CROWBAR is a SHUNT, and D1 already IS that shunt: a
# unidirectional TVS across VBAT-GND, landing on a pour and a ground plane that
# both already exist. Nothing has to be split. The only question is whether the
# part survives the job, and that is arithmetic.
#
# WHAT A REVERSED PACK DOES. D1 is unidirectional, so with the pack backwards it
# FORWARD-conducts at about 1 V and the pack pours current into it. The current
# itself is not computable from here -- it is set by the pack's internal
# resistance, which is not in this repo -- so the pack is deliberately NOT the
# subject. The subject is I2t, which removes the unknown entirely: the fuse
# clears on charge delivered, the diode dies on charge absorbed, and both are
# I2t. Whichever has the smaller I2t goes first, at ANY fault current.
#
#   D1 as built   SMBJ24A, IFSM 100 A at 8.3 ms  ->  100^2 x 8.3 ms =  83 A2s
#   the fuse      Littelfuse 257-010, 10 A ATO, MINIMUM melting   = 115 A2s
#
# 115 > 83. The fuse does NOT clear first; D1 is destroyed, by 1.4x. (The usual
# TVS failure mode is a short, which then crowbars the rail and blows the fuse
# anyway, so the BOARD survives -- but by sacrificing a part, and only if the
# part fails short rather than open. That is a coin toss to design around.)
#
# ⚠ AND THE FIRST VERSION OF THIS SUM GOT THE ANSWER BACKWARDS, which is why the
# fuse number is cited and not estimated. Guessing "a 10 A blade fuse is about
# 50 A2s" made the fuse clear first and D1 survive. The published minimum is
# 115. The conclusion reversed on a number that was looked up rather than
# remembered.
#
# THE FIX IS ONE FOOTPRINT. SMCJ24A is the same TVS in the next package up:
#
#   clamp         38.9 V at 38.6 A  -- IDENTICAL to the SMBJ24A's 38.9 V, read
#                 off five makers' listings, so TVS_CLAMP below does not move
#                 and NOTHING downstream of it changes
#   power         1500 W against 600 W
#   IFSM          200 A at 8.3 ms  ->  200^2 x 8.3 ms = 332 A2s, 2.9x the fuse
#
# So the fuse opens with 2.9x margin and D1 is not harmed. Reverse polarity
# stops being a defect and becomes a survivable event with a named margin, for
# a package change on a part that was already there -- no series element, no
# split pour, no keyed connector, and no argument with CIRCUIT.md section 7.
TVS_IFSM        = 200.0                 # A, SMCJ series, 8.3 ms single half
                                        # sine (Littelfuse SMCJ, LCSC C224045)
TVS_IFSM_MS     = 8.3                   # ms, the rating's own pulse width
TVS_I2T         = TVS_IFSM ** 2 * TVS_IFSM_MS / 1000.0        # 332 A2s
FUSE_ATC_I2T    = 115.0                 # A2s, Littelfuse 257-010 MINIMUM
                                        # melting I2t -- minimum, because the
                                        # fuse clearing LATE is the bad case
TVS_I2T_MARGIN  = TVS_I2T / FUSE_ATC_I2T
assert TVS_I2T_MARGIN > 1.5, (
    "the TVS absorbs %.0f A2s before the %.0f A2s fuse clears (%.2fx): on a "
    "reversed pack D1 goes before the fuse does, and the board's only reverse "
    "polarity protection is a sacrificial part" % (
        TVS_I2T, FUSE_ATC_I2T, TVS_I2T_MARGIN))


# ── What the freewheel diode has to survive THERMALLY, which is what chooses it ──
# ⚠ THE VOLTS AND AMPS WERE NEVER THE BINDING SPEC. "60 V, 15 A, D2PAK" is met by
# a wide, cheap field of parts; what separates them is Vf, and Vf is the only
# term in this diode's power. D2/D3 are the largest heat on this board -- more
# than the buck, more than the FETs -- and nothing here had computed how hot.
#
# THE DUTY IS NOT THE USER'S. firmware/src/main.cpp sets ONE run duty and says
# so in as many words: "NO INTERMEDIATE DUTY. The stick is used hard-forward or
# hard-back, so engaged means RUN_DUTY and nothing else." RUN_DUTY synthesises
# the pump's 12 V nameplate from whatever the pack is, so D = 12 / V_pack and
# the diode conducts the other (1 - D) of every cycle. That inverts the usual
# intuition about which battery state is worst: a DRAINED pack at 15 V runs
# D = 0.80 and the diode carries 20 % of the time; a FRESH pack at 20 V runs
# D = 0.60 and it carries 40 %. The hot case is a full battery.
#
# CIRCUIT.md still says "at 50 % duty it carries ~3.75 A average". That was a
# round number from before the duty was derived; the real worst case is 3.0 A,
# and it is lower because the firmware will not run the pump at 50 %.
PUMP_I            = 7.5          # A, the pump's running current (CIRCUIT.md 1)
PUMP_V_NOM        = 12.0         # V, pump nameplate -- firmware's PUMP_V_NOM
FREEWHEEL_DUTY    = 1.0 - PUMP_V_NOM / VBAT_MAX      # 0.40 at a fresh 20 V pack
FREEWHEEL_I_AVG   = FREEWHEEL_DUTY * PUMP_I          # 3.00 A
# ⚠ THE BOARD SIDE OF THE THERMAL PATH IS MEASURED; THE PART SIDE IS NOT, AND
# THAT ASYMMETRY IS THE WHOLE POINT. D2's tab is the CATHODE and sits on the
# VBAT pour, which fills as ONE island of 687.0 mm2 (M3's measurement, off the
# filled board). D2 and D3 share it and never conduct together -- direction is
# chosen by WHICH pump is energised, so one is always off -- so each sees the
# whole pour. 687 mm2 of 1 oz copper puts a D2PAK at roughly 42 C/W junction to
# ambient by the standard pad-area curves; that figure is a STATED ASSUMPTION,
# not a reading, and it is the number to replace first when a part is chosen.
# Ambient is the SEALED bay, not the garden: 35 C outside plus the bay's own
# rise gives 50 C to work from.
FREEWHEEL_RTH_JA  = 42.0         # C/W, D2PAK on 687 mm2 of 1 oz -- ASSUMED
FREEWHEEL_TA      = 50.0         # C, inside the sealed bay on a hot day
FREEWHEEL_TJ_MAX  = 125.0        # C, the floor of this class's rating
FREEWHEEL_P_MAX   = (FREEWHEEL_TJ_MAX - FREEWHEEL_TA) / FREEWHEEL_RTH_JA   # 1.786 W
FREEWHEEL_VF_MAX  = FREEWHEEL_P_MAX / FREEWHEEL_I_AVG                      # 0.595 V
assert 0.30 < FREEWHEEL_VF_MAX < 0.90, (
    "the Vf ceiling came out at %.3f V, which is outside what a 60 V Schottky "
    "can be: check the duty, the pour area or the ambient" % FREEWHEEL_VF_MAX)
# ⚠ AND THE VALUE STRING CARRIES IT, because a requirement that lives only in a
# comment is a requirement the person doing the sourcing never sees. The same
# reasoning put the saturation current into L1's "10uH/4A6sat": the BOM line is
# the last place the number can still change the part that gets bought.
# ⚠ FLOORED, NOT ROUNDED, AND _house WOULD HAVE ROUNDED. _house(0.595, "V")
# gives "0V6" -- it rounds to the nearest tenth, which is right for a nominal
# value like 4A6 and wrong for a CEILING: it would print a limit 0.005 V looser
# than the one the arithmetic produced, and a part sourced against the printed
# string would be out of spec against the computed one. Two places, floored.
FREEWHEEL_VALUE = "SCHOTTKY-%.0fV-%.0fA-vf%dV%02d" % (
    FREEWHEEL_VR_MIN, FREEWHEEL_IF_MIN,
    int(FREEWHEEL_VF_MAX), int(FREEWHEEL_VF_MAX * 100) % 100)


def circuit():
    gnd  = Net("GND")
    vbat = Net("VBAT")
    v3v3 = Net("+3V3")
    gen.power(gnd, vbat, v3v3)

    n_sw   = Net("SW")          # buck switch node
    n_fb   = Net("FB")
    n_gA   = Net("GATE_A")
    n_gB   = Net("GATE_B")
    n_pA   = Net("PUMP_A_LO")   # pump A low side (FET drain)
    n_pB   = Net("PUMP_B_LO")
    n_pwmA = Net("PWM_A")
    n_pwmB = Net("PWM_B")
    n_vsen = Net("VBAT_SENSE")
    n_joyr = Net("JOY_RAW")
    n_joyf = Net("JOY_FILT")
    n_lvl  = Net("LEVEL")
    n_bz   = Net("BUZZ")
    n_bzd  = Net("BUZZ_DRV")
    n_rt   = Net("RT")
    n_ss   = Net("SS")
    n_vg   = Net("VGATE")
    n_lvlv = Net("VBAT_LVL")    # VBAT past F1, the only fused net on the board
    n_en   = Net("EN")
    n_io0  = Net("IO0")
    # ⚠ NAMED BY DIRECTION, BECAUSE "TXD" ON A HEADER IS A TRAP. PCB_QUALITY
    # M26 wants a net named TX to reach one transmitter and the far end's
    # RECEIVER, and M31 wants a pin someone will wire to say which way it goes.
    # These were nets "TXD0"/"RXD0" landing on J6 pins silkscreened "TXD"/"RXD"
    # -- and every USB-UART adapter also labels its own pins TXD and RXD, from
    # ITS point of view. Wire like to like and it is output to output: the
    # board will not program, and nothing on either silk says why.
    #
    # The module's own pin names stay RXD0/TXD0 (that is what Espressif calls
    # pins 34/35, and tools/check_pin_map.py ALIASes those spellings to IO3 and
    # IO1), so the rename is on the NETS and on J6's pin names, which are what
    # kicad_silk prints next to the header.
    n_rx   = Net("ESP_RX_FROM_PROG")
    n_tx   = Net("ESP_TX_TO_PROG")
    n_rxj  = Net("PROG_RX_IN")  # J6 side of R25; the module side is n_rx

    # ── Connectors — terminal blocks, not JST. Every one of these is landed once
    # at assembly, so JST's plug/unplug advantage goes unused, and a terminal is
    # ONE part with no mating half to stock (PCB_README §3).
    j_bat = gen.part("J1", "TB-5.08-2", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal",
                     ["VBAT", "GND"], "battery in, 15-20 V, 7.5 A — ONE pump at a time, held by tools/check_pump_dirs.py, so this never carries both; "
                     "WJ500V-5.08-2P, UL 10 A / IEC 24 A")
    j_pa  = gen.part("J2", "TB-5.08-2", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal",
                     ["VBAT", "LO"], "pump A, 7.5 A")
    j_pb  = gen.part("J3", "TB-5.08-2", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal",
                     ["VBAT", "LO"], "pump B, 7.5 A")
    j_joy = gen.part("J4", "TB-5.08-5", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-5-5.08_1x05_P5.08mm_Horizontal",
                     ["3V3", "GND", "VRY", "VRX", "SW"],
                     "KY-023 joystick, 3V3 NOT 5 V. 5.08 mm, not the old "
                     "3.5 mm PT: ONE connector family on the whole board")
    j_lvl = gen.part("J5", "TB-5.08-4", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-4-5.08_1x04_P5.08mm_Horizontal",
                     ["VBAT", "GND", "OUT", "MODE"],
                     "XKC-Y25 level, open-collector out; same 5.08 family")
    j_prg = gen.part("J6", "PROG", "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
                     ["3V3", "GND", "ESP_TX", "ESP_RX", "EN", "IO0"],
                     "programming; no USB-C — a connector is a water path "
                     "outdoors. ESP_TX/ESP_RX are named from the BOARD's end: "
                     "cross them to the adapter")

    # ── Input protection ────────────────────────────────────────────────────
    d_tvs = gen.part("D1", "SMCJ24A", "Diode_SMD:D_SMC", ["K", "A"],
                     "TVS: 24 V standoff > 20 V pack, ~39 V clamp < 60 V FETs")
    c_in1 = gen.part("C1", "100u/50V", "Capacitor_SMD:CP_Elec_10x10.5", 2, "bulk at the switches")
    c_in2 = gen.part("C2", "100u/50V", "Capacitor_SMD:CP_Elec_10x10.5", 2, "bulk at the switches")

    gnd  += j_bat["GND"], d_tvs["A"], c_in1[2], c_in2[2]
    # j_lvl["VBAT"] is NOT on this list any more: it is behind F1, on VBAT_LVL.
    vbat += j_bat["VBAT"], d_tvs["K"], c_in1[1], c_in2[1], j_pa["VBAT"], j_pb["VBAT"]

    # ── 18 V -> 3.3 V buck. >= 40 V in; 24 V-max parts are too close to a fresh
    # pack. ~1 A covers the ESP32's ~500 mA WiFi bursts.
    # PIN 6 IS SS, NOT COMP, and PIN 9 IS THE THERMAL PAD. The LMR14020 is
    # internally compensated -- it has no COMP pin -- and its DDA package is an
    # HSOIC with an exposed pad the datasheet calls "the major heat dissipation
    # path of the die", which "must be connected to ground plane on PCB". This
    # was drawn on a plain Package_SO:SOIC-8 land: no pad under the pad, and the
    # part's whole thermal path landing on solder mask. wbp:SOIC-8-1EP-FABDRILL
    # is KiCad's EP2.29x3mm ThermalVias footprint with its 0.2 mm vias opened to
    # 0.3 for the fab floor, the same fix the ESP32 footprint needed.
    u_bk = gen.part("U1", "LMR14020SDDA", "wbp:SOIC-8-1EP-FABDRILL",
                    {1: "BOOT", 2: "VIN", 3: "EN", 4: "RT", 5: "FB", 6: "SS",
                     7: "GND", 9: "EP", 8: "SW"}, "18 V -> 3.3 V, 40 V in, 2 A")
    l1   = gen.part("L1", BUCK_L_VALUE, "Inductor_SMD:L_Bourns_SRN6045TA", 2,
                    "buck inductor -- Isat %.1f A clears the %.1f A current limit"
                    % (BUCK_L_ISAT, BUCK_ILIM_MAX))
    # ⚠ THE INPUT CAPACITOR THAT WAS NOT THERE. SNVSAA5B asks for a ceramic at
    # VIN "as close as possible to the VIN and GND pins"; this board had only
    # C1/C2, two 100 uF electrolytics THIRTY-EIGHT MILLIMETRES away. At 500 kHz
    # the switching current has to come from somewhere every cycle, and 38 mm of
    # track is about 40 nH: the loop rings VIN on every edge, and a 20 V pack
    # ringing on 40 nH has somewhere to go on a part rated 40 V.
    #
    # The electrolytics are bulk for the PUMP legs and they are staying bulk for
    # the pump legs -- they are now beside the pump terminals, which is both
    # where their own comment always said they belonged and what puts them
    # inside A2's 25 mm of J2 and J3.
    c_bki = gen.part("C15", "4u7/50V", "Capacitor_SMD:C_1206_3216Metric", 2,
                     "buck input -- the hot loop. Keep it AT pins 2 and 7")
    c_bt = gen.part("C3", CAP_100N, "Capacitor_SMD:C_0603_1608Metric", 2, "boot")
    # The rectifier the LMR14020 cannot work without -- see the block above.
    # Cathode on SW, anode on GND: during the off-time the inductor pulls SW
    # DOWN, so this is the part that holds the node one diode drop below ground
    # instead of letting it run to the -3 V where the pin's rating ends.
    d_cat = gen.part("D6", BUCK_CATCH_VALUE, "Diode_SMD:D_SMA", ["K", "A"],
                     "buck catch diode -- %.2f A average, %.0f V node"
                     % (BUCK_CATCH_I_AVG, VBAT_MAX))
    c_o1 = gen.part("C4", "22u/16V", "Capacitor_SMD:C_1206_3216Metric", 2,
                    "3V3 out -- %s or better; the derate is the argument"
                    % BUCK_COUT_DIELECTRIC)
    # C5 is NOT an output capacitor -- see its placement note. It is the local
    # charge for the 3V3 that leaves on J6, which is the job it was already
    # doing from the wrong place.
    c_o2 = gen.part("C5", CAP_10U, "Capacitor_SMD:C_0805_2012Metric", 2,
                    "+3V3 local charge at the programming header")
    # The second half of the output capacitance eq 13 asks for; see the
    # BUCK_COUT block. Same value as C4 on purpose: no new part number, and two
    # in parallel halve the ESR.
    c_o3 = gen.part("C19", "22u/16V", "Capacitor_SMD:C_1206_3216Metric", 2,
                    "3V3 out, the second of two -- %s or better"
                    % BUCK_COUT_DIELECTRIC)
    r_f1 = gen.part("R1", FB_TOP, "Resistor_SMD:R_0603_1608Metric", 2, "FB top")
    r_f2 = gen.part("R2", FB_BOT, "Resistor_SMD:R_0603_1608Metric", 2,
                    "FB bottom -> %.2f V" % FB_VOUT)
    # "The RT/SYNC pin can't be left floating or shorted to ground" -- datasheet
    # SNVSAA5B section 6.3.8, in those words. It was floating. 49.9k is the
    # datasheet's own table value for 500 kHz, which with the 15 uH inductor
    # gives 0.55 A of ripple at a 20 V input with the 10 uH part
    # (BUCK_RIPPLE_A above derives it; 15 uH gave 0.37 and saturated).
    r_rt = gen.part("R8", BUCK_RT, "Resistor_SMD:R_0603_1608Metric", 2,
                    "switching frequency: %.0f kHz" % BUCK_FSW_KHZ)
    # SS, the pin this file used to call COMP. Floating it leaves the ramp to
    # stray capacitance and 3 uA, which is no ramp at all: 10 nF x 0.75 V / 3 uA
    # gives a defined 2.5 ms into 42 uF of output capacitance.
    c_ss = gen.part("C14", "10n", "Capacitor_SMD:C_0603_1608Metric", 2,
                    "buck soft-start, ~2.5 ms")

    vbat += u_bk["VIN"], u_bk["EN"], c_bki[1]
    n_sw += u_bk["SW"], l1[1], c_bt[2], d_cat["K"]
    v3v3 += (l1[2], c_o1[1], c_o2[1], c_o3[1], r_f1[1], j_joy["3V3"],
             j_prg["3V3"])
    n_fb += r_f1[2], r_f2[1], u_bk["FB"]
    n_rt += u_bk["RT"], r_rt[1]
    n_ss += u_bk["SS"], c_ss[1]
    gnd  += (u_bk["GND"], u_bk["EP"], c_o1[2], c_o2[2], c_o3[2], r_f2[2], r_rt[2],
             c_ss[2], c_bki[2], d_cat["A"])
    c_bt[1] += u_bk["BOOT"]

    # ── MCU ─────────────────────────────────────────────────────────────────
    # Joystick on IO34 and pumps on IO25/IO26 match the firmware already running.
    # ALL FOUR GROUND PINS, NOT TWO. KiCad's own RF_Module symbol declares this
    # module's GND pin as number "[1,15,38,39]" -- 1, 15, 38 AND 39. This read
    # {1: GND, ..., 38: GND}, so pin 15 and pin 39 were on no net at all, and
    # pin 39 is the module's underside thermal pad: TWENTY-ONE pads in the
    # footprint, the module's whole RF and thermal ground, floating. Nothing
    # reported it, because a pad with NO net is not an unconnected net -- DRC
    # and the 0-unconnected gate both pass a board full of them.
    # tools/check_ic_pinouts.py counts pads now, which is what found this.
    u_mcu = gen.part("U2", "ESP32-WROOM-32E", "wbp:ESP32-WROOM-32E-FABDRILL",
                     {1: "GND", 2: "3V3", 3: "EN", 6: "IO34", 7: "IO35", 10: "IO25",
                      11: "IO26", 12: "IO27", 13: "IO14", 15: "GND", 25: "IO0",
                      34: "RXD0", 35: "TXD0", 38: "GND", 39: "GND"}, "MCU + WiFi. LOCAL footprint: KiCad's stock one has twelve 0.2 mm thermal vias, below the 0.3 mm fab minimum — 12 of this board's 14 DRC violations were that one footprint")
    c_m1 = gen.part("C6", CAP_10U, "Capacitor_SMD:C_0805_2012Metric", 2, "MCU bulk")
    c_m2 = gen.part("C7", CAP_100N, "Capacitor_SMD:C_0603_1608Metric", 2, "MCU decoupling")
    r_en = gen.part("R3", "10k", "Resistor_SMD:R_0603_1608Metric", 2, "EN pull-up")
    c_en = gen.part("C8", "1u", "Capacitor_SMD:C_0603_1608Metric", 2, "EN RC, power-on reset")

    v3v3 += u_mcu["3V3"], c_m1[1], c_m2[1], r_en[1]
    gnd  += u_mcu["GND"], c_m1[2], c_m2[2], c_en[2]
    n_en += u_mcu["EN"], r_en[2], c_en[1], j_prg["EN"]
    n_io0 += u_mcu["IO0"], j_prg["IO0"]
    r_rx = gen.part("R25", PROG_RX_SERIES, "Resistor_SMD:R_0603_1608Metric", 2,
                    "ESP_RX series -- stops an adapter back-powering a dead 3V3")
    n_rx += u_mcu["RXD0"], r_rx[1]
    n_rxj += r_rx[2], j_prg["ESP_RX"]
    n_tx += u_mcu["TXD0"], j_prg["ESP_TX"]
    gnd  += j_prg["GND"]

    # ── VGATE: the rail the gate drivers actually need ──────────────────────
    # The UCC27517 is a 4.5 V to 18 V part and the only logic rail on this board
    # is 3.3 V. Under 4.5 V its own UVLO holds the output low, so BOTH PUMPS
    # WOULD HAVE BEEN DEAD even with the pinout right. CIRCUIT.md states "There
    # is no 5 V rail" and specifies a UCC27517-class driver in the same
    # document; the two cannot both stand.
    #
    # It is also already implied elsewhere: the FET requirement is "<= 10 mOhm
    # at 4.5 V Vgs", which is a gate drive this board could not produce.
    #
    # A SHUNT, NOT A REGULATOR, and deliberately. The load is tiny -- the
    # driver's quiescent plus Qg x fsw, about 1.5 mA with one pump running at
    # 20 kHz -- so a series resistor and a Zener do the whole job with two
    # passives and no pinout to get wrong. A 60 V LDO would be tidier and would
    # not idle; this costs VBAT/R - I_load of standing current, 6.7 mA at a
    # fresh pack, which is nothing beside the ESP32's 100 mA and the level
    # sensor's own draw. The machine has no low-power idle state to protect.
    #
    # 10 V, not 5: it is inside the driver's 4.5-18 V window with margin at both
    # ends, and it enhances the FET harder than the 4.5 V its Rds(on) is quoted
    # at. 1k5 passes 3.3 mA at a flat 15 V pack and 6.7 mA at a fresh 20 V one.
    r_vg = gen.part("R9", VGATE_R, "Resistor_SMD:R_0805_2012Metric", 2,
                    "VGATE dropper — %.1f mA at a flat pack" % VGATE_I_MIN_MA)
    d_vg = gen.part("D5", VGATE_ZENER, "Diode_SMD:D_SOD-123", ["K", "A"],
                    "VGATE shunt — the gate drivers' supply")
    c_vg = gen.part("C13", CAP_VGATE, "Capacitor_SMD:C_0805_2012Metric", 2,
                    "VGATE bulk — the gate peaks come from here, not through R9")
    vbat += r_vg[1]
    n_vg += r_vg[2], d_vg["K"], c_vg[1]
    gnd  += d_vg["A"], c_vg[2]

    # ── Pump drive: one low-side switch each. 60 V so the freewheel clamp has
    # margin; ~5 mOhm gives ~0.28 W at 7.5 A, against ~0.9 W for a BTS7960 half.
    for n, (gate, lo, pwm, jp) in enumerate(
            ((n_gA, n_pA, n_pwmA, j_pa), (n_gB, n_pB, n_pwmB, j_pb)), start=1):
        q = gen.part("Q%d" % n, PUMP_FET_VALUE, "Package_TO_SOT_SMD:TO-252-3_TabPin2",
                     {1: "G", 2: "D", 3: "S"}, "pump %d low-side switch" % n)
        # THE PINOUT WAS WRONG ON FOUR OF FIVE PINS. TI SLUSAY4C, figure on page
        # 2: 1 VDD, 2 GND, 3 IN+, 4 IN-, 5 OUT. This read
        # {1: IN, 2: GND, 3: NC, 4: OUT, 5: VDD}, which put the MCU's PWM on
        # the driver's SUPPLY pin, the FET gate on an INPUT, the driver's 4 A
        # OUTPUT straight onto the 3.3 V rail, and left the real input floating
        # -- and "Output Held Low when Input Pins are Floating". Neither pump
        # could have run, and powering it would have taken the rail with it.
        #
        # IN- IS TIED TO GND ON PURPOSE: "the unused input pin is not left
        # floating and must be properly biased to ensure that driver output is
        # enabled for normal operation". Grounded IN- enables the non-inverting
        # path; it is also the active-low enable, so this is the enabled state.
        u = gen.part("U%d" % (2 + n), "UCC27517", "Package_TO_SOT_SMD:SOT-23-5",
                     {1: "VDD", 2: "GND", 3: "IN+", 4: "IN-", 5: "OUT"},
                     "gate driver — 7.5 A at 20 kHz is not a job for a bare GPIO")
        # BOTH ANODE LEADS, NOT ONE. TO-263-2 is a THREE-pad land: pads 1 and 3
        # are the outer leads and pad 2 is the 101.5 mm2 tab (measured off
        # KiCad's own footprint). Declared as ["A", "K"] this netted pad 1 and
        # the tab and left PAD 3 WITH NO NET -- and at >= 15 A / 60 V in D2PAK
        # the part you can actually buy is usually a common-cathode DUAL, whose
        # pad 3 is the second anode. Half the diode would never have conducted,
        # in the one part this document calls the board's largest heat source,
        # carrying 7.5 A. Nothing would have reported it: a pad with no net is
        # not an unconnected net, so DRC and the 0-unconnected gate both pass.
        #
        # Tying pad 3 to the anode is right whichever part arrives: on a dual it
        # parallels the two halves as intended, and on a true 2-lead device
        # there is no pin there for it to reach.
        d = gen.part("D%d" % (1 + n), FREEWHEEL_VALUE, "Package_TO_SOT_SMD:TO-263-2",
                     {1: "A", 2: "K", 3: "A2"},
                     "freewheel — the board's largest heat source, ~1.5 W")
        rg = gen.part("R%d" % (3 + n), "10R", "Resistor_SMD:R_0603_1608Metric", 2, "gate")
        rp = gen.part("R%d" % (5 + n), "100k", "Resistor_SMD:R_0603_1608Metric", 2,
                      "gate pull-down — FET off while the MCU boots")
        cv = gen.part("C%d" % (8 + n), CAP_100N, "Capacitor_SMD:C_0603_1608Metric", 2,
                      "driver decoupling")
        pwm += u["IN+"]
        n_vg += u["VDD"], cv[1]
        gnd += u["GND"], u["IN-"], cv[2], q["S"], rp[2]
        gate += u["OUT"], rg[1]
        rg[2] += q["G"]
        rp[1] += q["G"]
        # THE FREEWHEEL DIODE GOES ACROSS THE PUMP, NOT ACROSS THE SWITCH. It
        # was anode on GND and cathode on the FET drain, which is the catch
        # diode for a HIGH-side switch. This is a LOW-side switch with the pump
        # returned to VBAT: when the FET opens, the pump's inductance pushes
        # current INTO the drain node and it has to get back to VBAT. A diode
        # from GND to the drain is reverse-biased for that current and does
        # nothing at all, so the drain would have flown up until the FET
        # avalanched -- 7.5 A, 20 kHz.
        lo += q["D"], d["A"], d["A2"], jp["LO"]
        vbat += d["K"]

    n_pwmA += u_mcu["IO26"]
    n_pwmB += u_mcu["IO25"]

    # ── Sensing ─────────────────────────────────────────────────────────────
    r_d1 = gen.part("R20", RDIV_TOP, "Resistor_SMD:R_0603_1608Metric", 2, "VBAT sense top")
    r_d2 = gen.part("R21", RDIV_BOT, "Resistor_SMD:R_0603_1608Metric", 2, "VBAT sense bottom")
    c_d  = gen.part("C11", CAP_100N, "Capacitor_SMD:C_0603_1608Metric", 2, "VBAT sense filter")
    vbat += r_d1[1]
    n_vsen += r_d1[2], r_d2[1], c_d[1], u_mcu["IO35"]
    gnd += r_d2[2], c_d[2]

    r_rc = gen.part("R22", RC_R, "Resistor_SMD:R_0603_1608Metric", 2, "joystick RC")
    c_rc = gen.part("C12", RC_C, "Capacitor_SMD:C_0603_1608Metric", 2, "joystick RC")
    n_joyr += j_joy["VRY"], r_rc[1]
    n_joyf += r_rc[2], c_rc[1], u_mcu["IO34"]
    gnd += c_rc[2], j_joy["GND"]

    # Level sensor: runs at VBAT and its output is OPEN-COLLECTOR, so this pull-up
    # to 3V3 is what keeps 18 V out of the GPIO. Push-pull mode would destroy it.
    r_lv = gen.part("R23", "10k", "Resistor_SMD:R_0603_1608Metric", 2,
                    "level pull-up — open-collector is what keeps 18 V off the pin")
    v3v3 += r_lv[1]
    n_lvl += r_lv[2], j_lvl["OUT"], u_mcu["IO14"]
    # Power LEAVING the board down a cable, which is the worst inductance in the
    # system (PCB_QUALITY A2, rule 4). Both of these feed a sensor or a stick on
    # the end of a lead and had no charge nearer than the far side of the board:
    # +3V3 at the joystick was 64.7 mm from C4, VBAT at the level sensor 55.1 mm
    # from C1.
    c_joy = gen.part("C16", CAP_10U, "Capacitor_SMD:C_0805_2012Metric", 2,
                     "local charge at the joystick connector")
    c_lvl = gen.part("C17", "10u/50V", "Capacitor_SMD:C_1206_3216Metric", 2,
                     "local charge at the level-sensor connector")
    # The PTC, and the local charge that belongs on its FAR side. A2 gives a
    # connector 25 mm to its nearest bypass, and what was answering for J5 was
    # C15 -- the BUCK's input ceramic, 16.25 mm away, which is on VBAT by
    # accident of placement and has a different job. Fusing the feed makes
    # J5.1 a net of its own, so it needs its own charge, and that is the right
    # side for it anyway: the fuse then sees the DC while the cable's inrush
    # comes from C18. C17 cannot be moved up here to do it -- it is J1's
    # bypass, 24.0 mm away, and the next nearest to J1 is 27.5.
    f_lvl = gen.part("F1", LVL_FUSE_VALUE, "Fuse:Fuse_1206_3216Metric", 2,
                     "level-sensor feed -- the only fused thing on the board")
    c_lvl2 = gen.part("C18", "10u/50V", "Capacitor_SMD:C_1206_3216Metric", 2,
                      "local charge PAST the fuse, at J5")
    vbat += f_lvl[1]
    n_lvlv += f_lvl[2], c_lvl2[1], j_lvl["VBAT"]
    gnd += c_lvl2[2]

    v3v3 += c_joy[1]
    vbat += c_lvl[1]
    gnd  += c_joy[2], c_lvl[2]
    gnd += j_lvl["GND"], j_lvl["MODE"]

    # ── Tank-full buzzer. Active (needs DC, not a waveform); ~30 mA is past a GPIO.
    bz  = gen.part("BZ1", "3V-ACTIVE", "Buzzer_Beeper:Buzzer_12x9.5RM7.6", ["+", "-"],
                   "tank full — filling happens with the pump OFF, so 85 dB is ample")
    q_b = gen.part("Q3", "MMBT3904", "Package_TO_SOT_SMD:SOT-23", {1: "B", 2: "E", 3: "C"},
                   "buzzer driver")
    r_b = gen.part("R24", "1k", "Resistor_SMD:R_0603_1608Metric", 2, "buzzer base")
    d_b = gen.part("D4", "1N4148W", "Diode_SMD:D_SOD-123", ["K", "A"], "buzzer flyback")
    n_bz += u_mcu["IO27"], r_b[1]
    r_b[2] += q_b["B"]
    v3v3 += bz["+"], d_b["K"]
    n_bzd += bz["-"], d_b["A"], q_b["C"]
    gnd += q_b["E"]

    # Unused joystick pins land on the connector but nowhere else; tie them off so
    # netcheck does not see a one-pin net.
    gnd += j_joy["VRX"], j_joy["SW"]

    # ── BRING-UP PADS ───────────────────────────────────────────────────────
    # Ten bare 1.5 mm pads, one per question you ask when a board arrives and
    # does not work. They cost nothing: each one is SEARCHED for a site that
    # already sits on its own net's copper (route.py's _resite_post_pads), so
    # no track is added for them and the search runs against the FINISHED
    # board, not against a coordinate that goes stale when the copper moves.
    #
    # cadkit/kicad_silk.py then labels each one with its NET name, which is the
    # half that makes them useful: a bring-up note saying "probe VGATE" is no
    # help if the board does not say which pad that is.
    #
    # WHY THESE TEN. Each answers one question, in the order you would ask it:
    #   GND         the reference for every other probe. Without it, nothing.
    #   VBAT        did the pack reach the board at all
    #   +3V3        did the buck start, and at what voltage (it sets the ADC's
    #               full scale too, so this reading explains the other two)
    #   VGATE       did the Zener rail come up -- the new rail, and the one
    #               that decides whether either pump can switch
    #   SW          is the buck switching, and at what frequency (R8's job)
    #   GATE_A/B    is the driver driving, or is it the FET that is dead
    #   VBAT_SENSE  what the ADC actually sees, against what the divider says
    #   JOY_FILT    the same for the joystick, after the RC
    #   LEVEL       is the sensor's open collector pulling down
    for ref, net in (("TP1", gnd), ("TP2", vbat), ("TP3", v3v3), ("TP4", n_vg),
                     ("TP5", n_sw), ("TP6", n_gA), ("TP7", n_gB),
                     ("TP8", n_vsen), ("TP9", n_joyf), ("TP10", n_lvl)):
        net += gen.part(ref, "TP", "TestPoint:TestPoint_Pad_D1.5mm", 1,
                        "bring-up probe")[1]


# ── THE BOARD ───────────────────────────────────────────────────────────────
# Millimetres, board-centred, +Y UP. These come FROM THE MECHANICAL MODEL: the
# board lies flat on the frame's +X outer face, which is FRAME_D x DECK_Z =
# 210 x 164. 140 x 100 leaves ~35 mm of margin all round for the shroud wall and
# its cable anchor.
BOARD_W, BOARD_L = 95.0, 100.0
HOLE_D = 4.5                                   # M4 clearance, THROUGH the board
# ⚠ 43, NOT 41, AND THE REASON IS UNDER THE BOARD. A mounting hole is also a
# STANDOFF BOSS in the housing (src/housing.py derives one per hole from the
# routed board, BOSS_D = 10.4 across), and a boss stands in the 4 mm between the
# bay floor and the laminate -- which is exactly where a through-hole terminal's
# solder tails stand. At 41 the boss edge passed 0.1 mm inside J2's VBAT tail:
# 1.17 mm3 of interference, caught by tools/check_overlaps.py, and on a real
# board it is a connector that holds the laminate off its own screws.
# 43 leaves 2.25 mm of laminate round the hole (the assert below wants 1.5) and
# clears that tail by 2.4 mm.
HOLES = [(-43.0, -44.0), (43.0, -44.0), (-43.0, 44.0), (43.0, 44.0)]

BOARD_NOTES = {
    "outline_mm": (BOARD_W, BOARD_L),
    # ── Order-form choices, which live in NO gerber (PCB_QUALITY M12) ────────
    # Two of these four are not preferences, they are DESIGN DEPENDENCIES, and
    # until now they existed only as assumptions inside other people's sums:
    #
    #   copper   EVERY current-carrying width on this board was sized against
    #            IPC-2221 for 1 oz OUTER copper -- it is why the 7.5 A nets are
    #            pours and not tracks (3.18 mm of 1 oz at a 20 C rise). Order
    #            2 oz and the board is merely cooler; the danger is the other
    #            way, and nothing in the gerbers would have said which was
    #            assumed.
    #   thick    A14 (via-in-land) computes a barrel VOLUME as pi r^2 x 1.6 mm
    #            and weighs it against the paste deposit. A 1.0 mm board makes
    #            every one of those numbers wrong by 38 %.
    #
    # The other two are choices, made for reasons rather than taste:
    #
    #   finish   Lead-free HASL. The finest thing here is a 1.27 mm SOIC and a
    #            1.5 mm-pitch castellated module, so HASL's unevenness has
    #            nothing to be uneven against -- and five terminals and a buzzer
    #            get hand-soldered later, which HASL's thicker coat helps. ENIG
    #            is the upgrade if U1's exposed-pad voiding ever needs chasing.
    #   mask     Green. kicad_silk's whole argument for 1.0 mm test-pad and
    #            connector labels is that somebody reads them with a probe in
    #            one hand on a board that does not work; white-on-green is the
    #            highest-contrast and best-tested pair the fab offers, and it is
    #            the cheapest and quickest. A dark mask would spend legibility
    #            on a board that lives inside a sealed box where nobody sees it.
    "order_options": {
        "copper":  "1 oz outer (35 um). ⚠ DESIGN DEPENDENCY -- every width and "
                   "pour on this board is sized against IPC-2221 at 1 oz.",
        "thick":   "1.6 mm. ⚠ DESIGN DEPENDENCY -- A14's via-in-land volume "
                   "check assumes it.",
        "finish":  "Lead-free HASL. Nothing finer than a 1.27 mm SOIC; five "
                   "terminals and a buzzer are hand-soldered afterwards.",
        "mask":    "Green, white silk. Highest contrast for the test-pad and "
                   "connector labels, which exist to be read during bring-up.",
        "tier":    "Whichever of Economic / Standard lists all 11 sourced SMT "
                   "parts -- the DESIGN constrains neither. 56 placements, all "
                   "on top (single-sided, no second-side setup); 95 x 100 mm, "
                   "inside the cheapest size tier and far above the minimum; "
                   "the 5 through-hole lines (BZ1, J1-J6) are hand-soldered, "
                   "so no THT assembly is ordered at all.",
    },
    "cutouts": [{"xy": xy, "d": HOLE_D} for xy in HOLES],
    "layers": 2,
    "thickness_mm": 1.6,
    # == PLACEMENT IS THE DESIGN, AND HERE IT IS THE CURRENT THAT DESIGNS IT ==
    # Rebuilt from the bottom edge up, because PCB_QUALITY A1 failed five supply
    # paths on the old one and every failure said the same thing: the router had
    # taken VBAT, PUMP_A_LO or PUMP_B_LO through a 0.67 mm via barrel. A 0.3 mm
    # drilled via carries about 1-1.5 A. These nets carry 7.5.
    #
    # No width fixes that and no autorouter was going to. What fixes it is that
    # the three high-current nets never change layer at all: each is a POUR on
    # F.Cu (see "zones"), and this placement exists so those pours can be laid
    # without crossing each other or a signal.
    #
    # ⚠ A PLACEMENT COORDINATE IS THE PAD CENTROID, NOT THE FOOTPRINT ORIGIN,
    # and the centroid is taken over EVERY pad including the unnamed thermal and
    # paste pads a DPAK or D2PAK carries -- which appear in no drawing. So the
    # offset from a coordinate to a given pad is measured, never derived; three
    # attempts at deriving it here produced three wrong courtyard gaps in a row.
    # The deltas each number below is built from, all at the rotation used:
    #
    #   MKDS-3-2 (J1/J2/J3) crt dx +-5.63   pad1 dx -2.54   pad2 dx +2.54
    #   MKDS-3-5 (J4)      crt dx -16.24..+10.16  pads dx +-10.16, +-5.08, 0
    #   MKDS-3-4 (J5)      crt dx -13.70..+ 7.62  pads dx -7.62, -2.54,
    #                                             +2.54, +7.62
    #   DPAK rot270 (Q)    crt dx +-3.545  TAB d(0,-2.363) 6.40x5.80
    #                                      leads dy +3.938, dx 0 and +-2.28
    #   D2PAK rot0 (D)     crt dx -9.131..+7.609
    #                      anodes d(-6.536,+-2.54) 4.60x1.10
    #                      cathode tab d(+2.614,0) 9.40x10.80
    #
    # THE FIVE RULES THE BOTTOM HALF OBEYS, in the order they bind:
    #
    #  1. EVERY FIELD CABLE LEAVES THE SAME EDGE. The housing opens at the board
    #     -Y edge (pose_board maps board +Y to world +Z, so -Y is DOWN), and the
    #     four cables a person plugs in -- pump A, the pack, pump B, the joystick
    #     -- are all on it. J5 (level sensor) and J6 (programming) stay on +Y.
    #
    #  2. THE THREE VBAT TERMINALS ARE CONTIGUOUS AND THE JOYSTICK IS OUTSIDE
    #     THEM. J2 | J1 | J3 then a 15 mm gap then J4. VBAT has to reach all
    #     three, and a pour reaching across the joystick would bury +3V3 and
    #     JOY_RAW inside a 7.5 A plane and leave the ADC signal no way out but a
    #     via into the B.Cu ground -- a hole in the return under the one net on
    #     this board whose job is to be quiet.
    #
    #  3. EACH FET TAB SITS ON ITS OWN PUMP PAD'S x. The DPAK tab at rot 270 is
    #     at dx 0, so Q1 at x=-30.26 puts 6.4 mm of drain copper directly above
    #     J2's PUMP_A_LO pad and the riser is a straight 9 mm of pour.
    #
    #  4. THE DIODE'S ANODE LEADS FACE THE FET'S TAB. Q1's tab ends at x=-27.06
    #     and D2's anode pads start at -25.84: the freewheel loop closes in
    #     1.22 mm of copper. That loop carries di/dt when the FET turns off, so
    #     it is the one millimetre on this board that matters most.
    #
    #  5. THE RISERS DO NOT CROSS. Four corridors run up from the bottom edge and
    #     none meets another: PUMP_A_LO at -30.26, VBAT at -10.34 and +6.0,
    #     PUMP_B_LO at -5.26. The VBAT riser at -10.34 lands in D2's cathode tab
    #     directly above it -- which is why pump B's terminal sits next to the
    #     pack's rather than at the far end -- and the one at +6.0 climbs the
    #     empty span between J3 and J4 into D3's tab.
    #
    # The buck and the MCU clusters are untouched. A2 passes on both, and
    # PCB_README is explicit that an experiment on a working region costs a
    # routing you then have nothing to compare against.
    "placements": {
        # -- 1 and 2: the four field cables -----------------------------------
        # Leftmost placement is -32.845: further left and an MKDS-3's SILK (dx
        # -5.605) comes inside 0.3 mm of the (-41,-44) mounting hole, which DRC
        # calls silk_edge_clearance and a person calls a screw you cannot reach
        # because the terminal body is over it.
        "J2": (-32.8, -41.0, 0.0),  # pump A   VBAT -35.34, PUMP_A_LO -30.26
        "J1": (-20.3, -41.0, 0.0),  # the pack VBAT -22.84, GND      -17.76
        "J3": ( -7.8, -41.0, 0.0),  # pump B   VBAT -10.34, PUMP_B_LO -5.26
        # The joystick sits 15 mm clear to the right, and that gap is not waste:
        # it is where VBAT climbs to D3's cathode tab without crossing anything.
        "J4": ( 22.0, -41.0, 0.0),  # +3V3 15.0, GND 18.5, JOY_RAW 22.0, GND, GND
        "J5": (-20.0,  41.0, 0.0), "J6": (12.0, 41.0, 90.0),
        # -- what the two +Y connectors need beside them ----------------------
        # F1 sits in line with J5's own VBAT pad (x -25.25) so the fused run is
        # a straight 9 mm drop, and C18 beside it so the charge is past the
        # fuse. J5's courtyard measures x -27.55..-12.45, y 35.95..44.65, so
        # y 33.0 clears L1 (whose courtyard reaches y 31.2) by 0.605.
        "F1": (-25.25, 33.0, 0.0),      # the level-sensor feed's PTC
        "C18": (-20.0, 33.0, 0.0),      # local charge past it: 9.76 mm to J5.1
        # R25 goes at the CONNECTOR end, where the hazard enters, so the whole
        # long run back to the module sits behind the 1k.
        "R25": (10.0, 36.5, 0.0),       # ESP_RX series
        # -- 3 and 4: the switch row ------------------------------------------
        # Q at 270 puts the tab toward -Y, at its terminal, and the three
        # gull-wing leads (gate, drain, source) toward +Y at dy +3.938 -- clear
        # of the power corridor, so a pour can own the whole tab without coming
        # near the gate. D at 0 puts the anode leads at -X, facing that tab.
        "Q1": (-30.26, -27.5, 270.0), "D2": (-17.0, -27.5, 0.0),
        "Q2": ( -5.26, -27.5, 270.0), "D3": (  7.5, -27.5, 0.0),
        # -- bulk and local charge, each ABOVE the terminal it answers for -----
        # A2 gives a connector 25 mm to its nearest bypass, and the switch row
        # is 11.4 mm of DPAK and D2PAK between the terminals and the first space
        # an electrolytic fits in. That leaves about a millimetre of slack, so
        # these three y values are not round numbers: -16.2 is the lowest a
        # 13.4 x 11.08 can sit while clearing Q1's courtyard by 0.42.
        #   C1  -> J2, pad to pad 24.91 mm
        #   C17 -> J1, 24.0 mm        (a 1206 ceramic, which is why it fits lower)
        #   C2  -> J3, 24.94 mm
        "C1": (-33.5, -16.2, 0.0), "C2": (-8.8, -16.2, 0.0),
        "C17": (-22.0, -17.0, 0.0),
        "D1": (-37.0, -7.0, 0.0),       # TVS, on the VBAT column beside C1
        # -- gate drive: driver, series resistor, pulldown, bypass ------------
        # R4/R6 are pump A's (R4 GATE_A->N$2, R6 N$2->GND); R5/R7 are pump B's.
        # A naming that READS as a pair and is not one: R5 belongs with Q2, and
        # placing it by its number would put pump B's gate drive beside pump A.
        # The driver and its series resistor are 7 mm apart rather than 5, so
        # that the GATE test pad has somewhere to land ON the net it probes:
        # route.py sites a bring-up pad against the finished copper, and a net
        # whose entire run is a 5 mm hop between two courtyards 1.4 mm apart
        # offers it nowhere. Four pads came back unconnected before this.
        "U3": (-30.0, -8.0, 0.0), "R4": (-23.0, -8.0, 0.0),
        "R6": (-23.0, -5.0, 0.0), "C9": (-30.0, -4.0, 0.0),
        "U4": ( -4.0, -8.0, 0.0), "R5": (  3.0, -8.0, 0.0),
        "R7": (  3.0, -5.0, 0.0), "C10": (-4.0, -4.0, 0.0),
        # -- VGATE shunt. 10 mA, so the run is long and does not care; what it
        # must not do is sit in a power corridor.
        "R9": (-21.0, -12.5, 0.0), "D5": (-17.0, -8.0, 0.0),
        "C13": (-17.0, -4.0, 0.0),
        # -- buck: RE-LAID AGAINST SNVSAA5B 7.4, which it did not obey ------
        # The old cluster was never re-laid and it showed, measured on the
        # routed board: 11.61 mm of switch node, the feedback divider 10.93 mm
        # from the pin it is supposed to be AT, the bootstrap capacitor
        # 14.01 mm from BOOT, RT 17.67 and SS 17.08. And it was missing the
        # rectifier entirely -- see the BUCK_CATCH block above, which is the
        # reason this region was opened at all.
        #
        # ⚠ EVERY DELTA BELOW IS MEASURED, and two of the guesses were wrong.
        # U1 is a dual-row HSOIC, so its pin PAIRS sit directly opposite:
        #   pad 1 BOOT d(-2.475,+1.905)   pad 8 SW  d(+2.475,+1.905)
        #   pad 2 VIN  d(-2.475,+0.635)   pad 7 GND d(+2.475,+0.635)
        #   pad 3 EN   d(-2.475,-0.635)   pad 6 SS  d(+2.475,-0.635)
        #   pad 4 RT   d(-2.475,-1.905)   pad 5 FB  d(+2.475,-1.905)
        #   courtyard d(+-3.745, +-2.745)
        #   D_SMA rot 270  pads d(0,+2.000) K and d(0,-2.000) A
        #                  courtyard d(+-1.795, +-3.545)
        # VIN and GND being opposite is the fact that shapes this whole region:
        # they are 4.95 mm apart across the body, so CIN cannot sit beside both
        # and the hot loop has a floor. Centring C15 ABOVE the package makes
        # the two legs EQUAL at 3.80 mm rather than the old 4.43 and 5.44.
        #
        # SNVSAA5B 7.4.1's six guidelines, and where each one landed:
        #   1. "The feedback network ... must be kept close to the FB pin"
        #        -> R2 directly BELOW pin 5, its FB pad 1.77 mm from it, with
        #           R1 beside it so both tap pads share one small node
        #   2. "CIN ... as close as possible to the VIN pin and ground" -> C15
        #   3. "The inductor L must be placed close to the SW pin"      -> L1
        #   4. "COUT must be placed close to the junction of L and the diode"
        #        -> C4 at L1's output pad, 2.85 mm
        #   5. "The ground connection for the diode, CIN, and COUT must be as
        #      small as possible"
        #   6. (a pointer to AN-1149)
        # Note what is NOT in that list: RT and SS. Both carry microamps into a
        # timing pin, so they get what is left over rather than a short run, and
        # C14 at 4.33 mm is not a compromise of anything the datasheet asked.
        #
        # ⚠ THE ORDER RIGHT OF THE PACKAGE IS D6, THEN L1, AND NOT THE OTHER
        # WAY ROUND -- it costs the switch node 3.5 mm and is still right.
        # Guideline 3 wants the inductor at SW and guideline 5 wants the diode's
        # ground short, and they compete for the same 3 mm. The diode wins
        # because it is the part that COMMUTATES: every cycle the inductor
        # current steps out of the high-side switch and into D6, so the loop
        # SW-D6-GND is where di/dt lives, and its area sets the ringing on a
        # node whose rating stops at -3 V. The inductor's own current does not
        # step at all, and guideline 3's stated reason for keeping it close is
        # "to reduce magnetic and electrostatic noise" -- a radiation argument,
        # not a loop-area one. So D6 sits between pins 7 and 8, which are
        # adjacent, with both its legs balanced at 3.60 and 3.79 mm, and L1
        # takes the next place out: 7.05 mm of switch node instead of 11.61.
        "U1": (-36.0, 26.0, 0.0),
        "C15": (-36.0, 30.3, 0.0),      # CIN: the hot loop, 3.80 mm each leg
        "C3": (-36.0, 32.5, 0.0),       # BOOT, above CIN -- also a left-to-
                                        # right bridge (BOOT pin 1, SW pin 8)
        "D6": (-30.1, 27.0, 270.0),     # catch: K up to SW, A down to GND
        "L1": (-24.4, 27.905, 0.0),     # SW pad on pin 8's own y
        "C4": (-18.0, 27.905, 0.0),     # COUT, at L1's output pad
        "C19": (-18.0, 24.3, 0.0),      # COUT's other half, 4.60 mm from L1.2
        # ⚠ C5 IS NOT AT THE BUCK, AND IT NEVER REALLY WAS. It sat at (-8, 26)
        # with a comment calling it "3V3 out", and what it was actually doing
        # there was being J6's bypass: A2 gives a connector 25 mm to its
        # nearest charge, and C5's pad was the only +3V3 ceramic inside that of
        # J6.1 -- 20.9 mm, where C4 was 25.88 and failed. Moving it to the
        # inductor broke A2 on J6 and that is how this was found. So it is
        # placed for the job it has: the local charge for the 3V3 that LEAVES
        # the board down the programmer's cable, exactly as C16 is for J4.
        # C4 is the output capacitor and does the high-frequency work alone.
        "C5": (-6.0, 30.0, 0.0),        # +3V3 at J6: pad to pad 16.7 mm
        "R2": (-33.525, 21.5, 270.0),   # FB -> GND, 1.77 mm below pin 5
        "R1": (-35.6, 21.5, 90.0),      # +3V3 -> FB, its tap pad beside R2's
        "C14": (-30.3, 21.8, 0.0),      # SS, under D6
        "R8": (-41.6, 24.095, 180.0),   # RT, left of the package at pin 4's y
        # -- MCU cluster, UNCHANGED ------------------------------------------
        # 270, not 90: at rot 90 the antenna fan points -X, straight back over
        # the board. At 270 it leaves the laminate at x=47.5 and the only thing
        # it still covers is a corner mounting hole -- a cutout, which the
        # keepout does not forbid.
        "U2": (34.4, 19.5, 270.0),
        # C6 moved up 1.5 mm to free the band the ADC filters needed; it is the
        # MCU's BULK, and A2's 5 mm belongs to C7, which bypasses U2.2 at
        # 3.86 mm. Bulk at 8.97 mm behind an unbroken plane is what bulk is for.
        "C6": (36.5, 33.0, 0.0), "C7": (42.8, 31.5, 0.0),
        "R3": (2.0, 32.0, 0.0),  "C8": (2.0, 26.0, 0.0),
        # -- sensing and the buzzer, right of the switch row ------------------
        # R20's top leg is on VBAT and a long way from the pour, which is right
        # rather than sloppy: the divider passes 170 uA. What must be short is
        # VBAT_SENSE -- the 100k node the ADC reads -- so R21 and C11 sit at the
        # MCU and the long run is the one carrying nothing.
        #
        # ⚠ AND THEY DID NOT. That comment described an intention, not the
        # board: measured on the routed copper, C11 was 28.04 mm from IO35 and
        # C12 -- the joystick RC's capacitor, the ONLY noise defence on an ADC
        # input fed by a hand-held stick on the end of a lead -- was 56.81 mm
        # from IO34. A filter capacitor that far from its pin filters the cable
        # and leaves the board's own 57 mm of high-impedance track unshunted, on
        # the two signals that are the machine's entire input.
        #
        # The module's pads are the constraint. U2 at 270 puts pins 1-19 in one
        # row at y 27.716 and pins 25-38 at y 10.216, with the body between
        # them, so there is no "beside the pin" below -- the only free ground is
        # ABOVE that top row, which is where C6/C7 already are. Measured pads:
        #   U2.7  IO35 VBAT_SENSE  (36.456, 27.716)
        #   U2.6  IO34 JOY_FILT    (37.726, 27.716)
        # The two pins are 1.27 mm apart and an 0603 is 3.05 mm wide, so both
        # capacitors cannot each sit directly over their own pin; they sit side
        # by side just above the row, each rotated so its SIGNAL pad is the one
        # facing its pin.
        #
        # y 29.9 IS THE FLOOR AND IT IS MEASURED. U2's courtyard is not the box
        # its bounding box suggests -- it is one 8-point outline covering the
        # module body at x 25.28..45.13, y 9.22..28.71, plus the antenna keepout
        # hanging off the laminate at x 45.13..66.81. So the body's top edge is
        # y 28.71, and an 0603's half-height is 0.775: 29.9 leaves 0.415.
        # Placing these at 29.3 cost three courtyards_overlap against U2, which
        # is how the real outline got measured instead of assumed.
        "R20": (22.0, 6.0, 0.0),
        "R21": (31.2, 29.9, 180.0),     # divider bottom, at the tap it sets
        "C11": (34.8, 29.9, 180.0),     # VBAT_SENSE filter, 2.35 mm from IO35
        "C12": (38.4, 29.9, 0.0),       # JOY_FILT filter, 2.19 mm from IO34
        # R22 stays at the CONNECTOR end on purpose, and that is the half of an
        # RC that belongs there: with the resistor at J4 and the capacitor at
        # the pin, the whole board run sits INSIDE the filter and its pickup is
        # shunted by C12. Swapping them would put 1k at the pin and leave the
        # run outside the pole, which is the one arrangement that buys nothing.
        "R22": (20.0, -22.0, 0.0),
        "R23": (20.0, -30.0, 0.0),
        "BZ1": (33.0, -24.0, 0.0), "Q3": (26.0, -14.0, 0.0),
        "R24": (28.0, -8.0, 0.0),  "D4": (28.0, -3.0, 0.0),
        "C16": (18.0, -18.0, 0.0),      # +3V3 at J4: pad to pad 23.2 mm
        # -- bring-up pads. PREFERENCES, not sites: route.py re-searches each
        # against the finished copper and nudges it, so a pad that starts on a
        # neighbour's courtyard costs a nudge rather than a board.
        # Each sits ON the run it probes, in the gap its cluster leaves for it:
        # TP6 and TP7 between driver and series resistor, TP4 in the VGATE lane,
        # TP5 on the switch node between U1.8 and L1.
        "TP1": (10.0, -16.0, 0.0),  "TP2": (-18.0, -12.0, 0.0),
        "TP3": (0.0, 31.0, 0.0),    "TP4": (-14.0, -8.0, 0.0),
        "TP5": (-30.1, 32.2, 0.0),  "TP6": (-26.2, -8.0, 0.0),
        "TP7": (-0.2, -8.0, 0.0),   "TP8": (27.0, 3.0, 0.0),
        "TP9": (24.0, -20.0, 0.0),  "TP10": (24.0, -32.0, 0.0),
    },
    # Placed AFTER routing, on copper that is already there -- see the
    # bring-up-pad block in circuit().
    "post_route_refs": tuple("TP%d" % i for i in range(1, 11)),
    # ⚠ PER-NET TRACK WIDTH, because the default is 0.25 mm and cadkit's own
    # note says what that carries: "By IPC-2221 at a 10 C rise, 0.25 mm of 1 oz
    # outer copper carries 0.88 A". VBAT and both pump legs carry 7.5 A peak and
    # ~3.75 A average, and every one of them was drawn at 0.25. Nothing
    # downstream could notice -- "DRC compares copper to the netlist and has no
    # concept of current, and the netlist has no concept of width".
    #
    # 1.2 mm is NOT the IPC answer. 7.5 A at a 10 C rise wants ~4.8 mm of 1 oz
    # copper, and a track that wide is not a track, it is a pour. What a width
    # can do here is carry the AVERAGE (3.75 A wants ~1.9 mm at 10 C, ~1.1 mm at
    # 30 C) and stop the router drawing a 0.25 mm wire between a 5.08 mm screw
    # terminal and a D2PAK tab. The real current path is pad-to-pad and short;
    # what is left after that is this.
    #
    # ⚠ AND A WIDTH IS ONLY USEFUL IF A PAD CAN ACCEPT IT. These three nets land
    # only on MKDS-3 terminal pads, TO-252/TO-263 tabs and 10 x 10.5 electrolytic
    # pads -- all of them wider than 1.2 -- which is why they can take it and the
    # 0603-populated signal nets cannot.
    # ── PCB_QUALITY.md declarations ────────────────────────────────────────
    # The automated half of cadkit/pcbflow/quality.py reads this. Nothing here
    # is a setting: each entry is a claim about the board, and the pass fails if
    # the copper does not back it.
    "quality": {
        # A1 -- every supply net: where it enters, where it goes, how many amps.
        # VBAT's 7.5 A is ONE pump at full duty; check_pump_dirs.py is the gate
        # that holds "never both at once", so the rail is never asked for 15.
        # TWO ENTRIES FOR VBAT, BECAUSE VBAT HAS TWO CURRENTS. The old single
        # entry declared 7.5 A to every load including the buck's VIN pin, and
        # that is not a conservative simplification, it is a false statement
        # about the board: U1 draws 3.3 V x 0.6 A out of a 15-20 V pack, which
        # is ~0.16 A in, and its VIN pad is 1.95 x 0.60 mm -- a pad that cannot
        # physically accept the 3.18 mm the claim demands. The claim was
        # unmeetable because it was wrong, and A1 was right to fail it.
        "power_paths": [
            {"net": "VBAT", "from": "J1.1",
             # NOT Q1.2/Q2.2: those are the FET drains, and a drain is on the
             # pump leg, not on VBAT. The motor is the thing between them.
             # D2.2/D3.2 ARE here -- the freewheel cathodes are where the
             # recirculating current returns to the rail.
             "to": ["J2.1", "J3.1", "C1.1", "C2.1", "D2.2", "D3.2"],
             "amps": 7.5, "max_drop_mv": 300},
            {"net": "VBAT", "from": "J1.1", "to": ["U1.2", "F1.1"],
             # the buck's input (~0.16 A at the flat end of the pack) and the
             # level sensor's feed (milliamps). 0.3 A is the rounded-up total,
             # and these two are the only VBAT loads that are not the pumps.
             # F1.1, NOT J5.1: the sensor's feed is fused now, so VBAT stops at
             # the PTC and the connector is on its own net below.
             "amps": 0.3},
            # The only fused net on the board. 50 mA declared against a sensor
            # that draws about 10, which is also what F1's 200 mA hold current
            # is sized against -- see the LVL_FUSE block. Three pads: the PTC's
            # far side, the connector, and the local charge that belongs past
            # the fuse rather than before it.
            {"net": "VBAT_LVL", "from": "F1.2", "to": ["J5.1", "C18.1"],
             "amps": 0.05},
            {"net": "+3V3", "from": "L1.2",
             "to": ["U2.2", "J4.1", "J6.1"], "amps": 0.6},
            {"net": "PUMP_A_LO", "from": "J2.2", "to": ["Q1.2", "D2.1"], "amps": 7.5,
             "max_drop_mv": 300},
            {"net": "PUMP_B_LO", "from": "J3.2", "to": ["Q2.2", "D3.1"], "amps": 7.5,
             "max_drop_mv": 300},
            {"net": "VGATE", "from": "R9.2", "to": ["U3.1", "U4.1"], "amps": 0.01},
        ],
        # ⚠ max_drop_MV, NOT max_drop_pct, on the three 7.5 A nets, and the rule
        # itself says why: the percentage is taken against "the rail the net's
        # name states", and VBAT / PUMP_A_LO / PUMP_B_LO state no voltage at
        # all, so the check falls back to a flat 50 mV. 50 mV at 7.5 A is a
        # 6.7 milliohm budget end to end -- less than the terminal blocks'
        # own contact resistance, and not a number any amount of copper on a
        # 95 x 100 board reaches.
        #
        # 300 mV is 2% of the pack at its flat-discharge 15 V, which is the
        # figure the percentage would have given if the net had been called
        # VBAT_15V. What it buys is real: at 7.5 A it holds the board's own
        # copper under 2.25 W and keeps the drop below the pump's own lead
        # resistance, so the board is not the thing limiting flow.
        #
        # The 3V3 rail keeps the 2% default untouched, because its name DOES
        # state its voltage and because it is the ADC reference: an error there
        # is an error in every reading the machine takes.
        "temp_rise_c": 20, "copper_oz": 1,
        "not_power": [
            # a divider tap into an ADC pin, not a rail: 5 pads and no current
            "VBAT_SENSE",
        ],
        "decoupling": {
            "ic_mm": 5.0, "connector_mm": 25.0,
            "exempt": {
                "U1.3": "EN is an enable tied straight to VBAT so the buck runs "
                        "whenever the pack is on -- a logic input, not a supply "
                        "pin (PCB_QUALITY A2 rule 6)",
                "U2.7": "VBAT_SENSE at IO35 is the divider's tap into an ADC "
                        "input. It carries the 7 uA the divider passes and "
                        "nothing else (A2 rule 6); C11 is its filter",
            },
        },
        # A4 -- where each multi-pin part's pinout was read. These are the same
        # citations tools/check_ic_pinouts.py compares the netlist against, so
        # the two cannot drift apart without that gate firing.
        "pinouts": {
            "LMR14020SDDA": "TI SNVSAA5B, Pin Functions table, HSOIC-8 (DDA) "
                            "with PowerPAD; pin 9 is the EP",
            "UCC27517": "TI SLUSAY4C p.2, DBV (SOT-23-5): 1 VDD, 2 GND, 3 IN+, "
                        "4 IN-, 5 OUT",
            "ESP32-WROOM-32E": "Espressif ESP32-WROOM-32E datasheet pin "
                               "definitions, 1-38 plus the exposed P_GND/39; "
                               "cross-checked against KiCad RF_Module, which "
                               "declares GND as number \"[1,15,38,39]\"",
            "MMBT3904": "SOT-23 NPN standard pinout: 1 base, 2 emitter, "
                        "3 collector",
            "NFET-60V-10mR": "TO-252-3_TabPin2: KiCad's own land numbers the "
                             "37.1 mm2 tab pad 2, and a DPAK N-FET's tab is the "
                             "DRAIN, so 1 G / 2 D / 3 S",
            FREEWHEEL_VALUE: "TO-263-2: measured off KiCad's land -- pad 2 "
                                "is the 101.5 mm2 tab and a single D2PAK "
                                "Schottky's tab is the CATHODE, so 1 A / 2 K. "
                                "Pad 3 is the second outer lead and is tied to "
                                "the anode, because at this rating the part is "
                                "usually a common-cathode dual",
            "TB-5.08-2": "Phoenix MKDS 3/2-5,08 drawing, read from the WIRE "
                         "entry face; pin 1 is the pad the footprint marks, and "
                         "elec/CIRCUIT.md section 7 records the entry face as "
                         "local +Y for all five terminals",
            "TB-5.08-5": "MKDS 3/5-5,08, the 5-way member of the SAME family "
                         "as J1/J2/J3, so one pinout rule covers all five "
                         "terminals and the entry face is read the same way",
            "TB-5.08-4": "MKDS 3/4-5,08, the 4-way member of that family",
            "PROG": "a 1x06 2.54 header has no maker pinout: the order is this "
                    "board's own, printed on the back silk by kicad_silk and "
                    "listed in elec/CIRCUIT.md -- 3V3, GND, ESP_TX, ESP_RX, "
                    "EN, IO0. The two UART pins are named from the BOARD's end "
                    "on purpose (PCB_QUALITY M26): an adapter's own TXD goes to "
                    "ESP_RX, not to a pin that also says TXD",
        },
        # == THE MANUAL ITEMS ===============================================
        # Thirty-eight sign-offs, each against a primary source or a
        # measurement off the ROUTED board, live in elec/quality_signoff.py
        # -- lifted out of this file because the evidence would have
        # doubled it and buried the circuit. That module also carries an
        # OPEN dict saying, item by item, what is MISSING for the ones
        # that are not signed, which is the half that is easy to fudge.
        "manual": QUALITY_MANUAL,
        "waive": {
            "A8:U1": "the six vias ARE in the pad, but they are footprint PADS "
                     "rather than board vias, so A8 counts zero. "
                     "wbp:SOIC-8-1EP-FABDRILL is KiCad's EP2.29x3mm "
                     "ThermalVias land with its 0.2 mm vias opened to the fab's "
                     "0.3 floor: six plated holes through the exposed pad into "
                     "the B.Cu GND pour, which is what the rule is asking for. "
                     "The same six are why stitch_exceptions lists U1.9.",
        },
    },
    # == THE WIDTH IS NO LONGER THE CURRENT PATH. THE POUR IS. ==============
    # This started at 0.25 (the router default: 0.88 A of 1 oz outer copper),
    # went to 1.2 with a note that said in as many words that 1.2 was not the
    # IPC answer, then to 3.2 -- which IS the IPC answer for 7.5 A at a 20 C
    # rise, and still failed A1 five times, because a track is only as wide as
    # the narrowest thing on it and the router kept putting a 0.67 mm via barrel
    # in the middle. A 0.3 mm drilled via carries about 1-1.5 A.
    #
    # So VBAT, PUMP_A_LO and PUMP_B_LO are POURS now (see "zones"), and these
    # widths have one job left: stop the router drawing the DEFAULT between two
    # big pads, and be narrow enough to land. 1.2 lands on an MKDS-3 2.6 mm
    # through-pad, a 4.4 mm electrolytic pad, a DPAK gull-wing lead and the
    # LMR14020 1.95 x 0.60 VIN pad; 3.2 lands on none of the last two, and
    # a width a pad cannot accept is a neck wherever the pad is.
    #
    # Nothing here claims to carry 7.5 A. A1 measures the copper that exists and
    # reports which element is narrowest, so if a pour ever fails to connect,
    # the check fails rather than quietly grading the 1.2 mm track that is left.
    # That is the whole reason to let the gate measure instead of declaring.
    #
    # +3V3 is 1.0 for a different reason: 0.6 A needs only 0.6 mm of copper for
    # heat, but the rail is also the ADC reference, and the A1 2 % drop limit is
    # 66 mV. At 0.25 the run to the joystick dropped 210.
    "net_widths": {"VBAT": 1.2, "PUMP_A_LO": 1.2, "PUMP_B_LO": 1.2,
                   "+3V3": 1.0,
                   # the gate rail is small but it is the one that makes the
                   # pumps switch; 0.4 keeps it off the 0.25 default floor
                   "VGATE": 0.4},
    # U1's six EP pads ARE the stitching. wbp:SOIC-8-1EP-FABDRILL carries six
    # plated 0.3 mm thermal vias through the exposed pad, which is the LMR14020
    # datasheet's own layout: "Optional vias can be used with 0.2 mm typical
    # diameter". The stitcher asks for a via BESIDE each ground pad and there is
    # no room beside these -- because each of them is already a via to the plane.
    "stitch_exceptions": tuple("U1.9" for _ in range(6)),
    # == THE THREE HIGH-CURRENT NETS, AS COPPER REGIONS =====================
    # A pour is the only thing that can carry these: 7.5 A at a 20 C rise wants
    # 3.18 mm by IPC-2221, and the note that chose this board's old 1.2 mm said
    # the quiet part out loud -- a track that wide is not a track, it is a pour.
    #
    # ⚠ VBAT IS ONE POLYGON, AND IT HAS TO BE. The readable version of this was
    # eight overlapping rectangles, which is how it is still DESCRIBED below --
    # but two zones on the SAME NET at DIFFERENT priorities do not merge: KiCad
    # fills the higher one first and holds the lower one off it by the clearance,
    # so the rectangles came back as eight islands that each filled perfectly and
    # touched nothing. A1 reported "no copper joins J1.1 to D3.2", which is true
    # of the copper and says nothing about the eight numbers that caused it.
    # Equal priorities merge, but then DRC calls every overlap zones_intersect.
    # One outline has neither problem.
    #
    # THE SHAPE, as the rectangles it is the union of -- check these against the
    # measured pad deltas in the placement block, then check the corner list:
    #
    #   bus      x[-38.0,  8.0] y[-46.5,-39.6]  under J2.1, J1.1 and J3.1
    #   column   x[-38.0,-35.5] y[-39.6, -6.0]  up the left to C1 and the TVS
    #   riser A  x[-12.0, -9.7] y[-39.6,-32.0]  into D2's cathode tab
    #   tab A    x[-19.5, -9.7] y[-33.0,-22.0]  D2's cathode tab itself
    #   to C2    x[-15.5, -9.7] y[-22.0,-14.0]
    #   to C17   x[-19.5,-17.0] y[-22.0,-11.5] + x[-24.5,-17.0] y[-19.0,-14.5]
    #            + x[-24.5,-20.6] y[-14.5,-11.5]   (the last reaches R9's top leg
    #            while leaving its VGATE end 0.7 mm outside the pour)
    #   riser B  x[  4.3,  7.7] y[-39.6,-32.0]  up the empty span between J3 and
    #                                           J4, which is what that gap is for
    #   tab B    x[  3.7, 12.3] y[-33.0,-22.0]  D3's cathode tab
    #
    # Short, wide and local survives a routing. The first attempt ran a 3.8 mm
    # VBAT corridor 36 mm up the middle of the board; the router laid tracks
    # across it and the fill came back as NINETEEN islands.
    "zones": [
        ("GND", "B.Cu", 0.3),
        {"net": "VBAT", "layer": "F.Cu", "priority": 0, "poly": [
            (-38.0, -46.5), (8.0, -46.5), (8.0, -39.6),
            # riser B, carrying on into D3's cathode tab
            (7.7, -39.6), (7.7, -33.0), (12.3, -33.0), (12.3, -22.0),
            (3.7, -22.0), (3.7, -33.0), (4.3, -33.0), (4.3, -39.6),
            # riser A, into D2's cathode tab, with the two stubs off its top
            # edge that reach C2, C17 and R9
            (-9.7, -39.6), (-9.7, -14.0), (-15.5, -14.0), (-15.5, -22.0),
            (-17.0, -22.0), (-17.0, -11.5), (-20.6, -11.5), (-20.6, -14.5),
            (-24.5, -14.5), (-24.5, -19.0), (-19.5, -19.0), (-19.5, -33.0),
            (-12.0, -33.0), (-12.0, -39.6),
            # the left column, up to C1's positive pad and the TVS
            (-35.5, -39.6), (-35.5, -6.0), (-38.0, -6.0),
        ]},
        # -- PUMP_A_LO: up from J2.2 into Q1's tab and D2's anodes ------------
        # The top edge is -24.6, not -24.0, because Q1's gull-wing leads sit at
        # dy +3.938: the gate pad's lower edge is -24.162, and a 7.5 A pour
        # 0.16 mm from a gate is not a clearance, it is a coupling.
        {"net": "PUMP_A_LO", "layer": "F.Cu", "priority": 10,
         "poly": [(-31.96, -42.4), (-28.56, -42.4), (-28.56, -33.0),
                  (-20.8, -33.0), (-20.8, -24.6), (-33.7, -24.6),
                  (-33.7, -33.0), (-31.96, -33.0)]},
        # -- PUMP_B_LO: the same shape on J3.2 / Q2 / D3 ---------------------
        {"net": "PUMP_B_LO", "layer": "F.Cu", "priority": 10,
         "poly": [(-6.96, -42.4), (-3.56, -42.4), (-3.56, -33.0),
                  (2.4, -33.0), (2.4, -24.6), (-9.3, -24.6),
                  (-9.3, -33.0), (-6.96, -33.0)]},
    ],
    "stitch_nets": ("GND",),
    "single_sided": True,              # every part on the front: one assembly setup
}

# ── THE CHECKS ──────────────────────────────────────────────────────────────
# Anything DRC cannot see, asserted here so a bad placement stops the generator
# instead of surfacing later in the CAD's overlap gate.
for _xy in HOLES:
    _edge = min(BOARD_W / 2.0 - abs(_xy[0]), BOARD_L / 2.0 - abs(_xy[1])) - HOLE_D / 2.0
    assert _edge >= 1.5, "mounting hole at %s leaves %.2f mm of laminate" % (_xy, _edge)

# The ESP32's antenna must overhang a board edge with copper keepout under it.
_ANT = BOARD_W / 2.0 - BOARD_NOTES["placements"]["U2"][0]
assert _ANT <= 50.0, "ESP32 is %.1f mm from the +X edge; the antenna wants to be at it" % _ANT

# The HOUSING's y budget: the frame is 210 deep, the Makita dock is 72 across
# its slide, and the printed walls and board clearance take ~13. This was the
# BINDING constraint while the dock was 100.6 -- that figure included v1's
# dovetail ears, 14.3 mm a side hosting a joint v2 does not have, and removing
# them freed 28.6. The binding constraint is now the <=100x100 price tier
# asserted below. Kept, and kept exact, because the frame is still a wall: a
# board that grew past it would fit nothing.
_DOCK_W, _WALLS = 72.0, 13.0
assert BOARD_W <= 210.0 - _DOCK_W - _WALLS, (
    "board is %.1f wide; only %.1f fits beside the battery in a 210 deep frame"
    % (BOARD_W, 210.0 - _DOCK_W - _WALLS))
# ... and staying inside 100 x 100 keeps it in JLCPCB's cheapest 2-layer tier.
assert BOARD_W <= 100.0 and BOARD_L <= 100.0, "board leaves the <=100x100 price tier"


if __name__ == "__main__":
    circuit()
    gen.emit("main", OUT_DIR, BOARD_NOTES)
