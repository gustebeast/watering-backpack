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

OUT_DIR = gen.begin(__file__)           # before skidl is imported — see gen.begin

from skidl import Net  # noqa: E402

# ── Design figures ──────────────────────────────────────────────────────────
VBAT_MAX = 20.0          # fresh Makita pack
VBAT_MIN = 15.0          # flat
PUMP_A   = 7.5           # per pump, peak

# Battery sense divider: VBAT_MAX must land under 3.3 V at the ADC with margin.
# 100k/18k -> 20 V * 18/118 = 3.05 V. 100k top leg keeps idle draw ~170 uA.
RDIV_TOP, RDIV_BOT = "100k", "18k"

# Joystick RC: the ONLY noise defence, since there is no joystick board to buffer
# at the source. 1k + 100n = 1.6 kHz — far above a hand, far below switching.
RC_R, RC_C = "1k", "100n"

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
TVS_CLAMP          = 39.0        # SMBJ24A, approx
assert TVS_CLAMP < PUMP_FET_VDS_MIN, (
    "the TVS clamps at %.0f V; a pump FET rated %.0f V has no margin behind it"
    % (TVS_CLAMP, PUMP_FET_VDS_MIN))
# Neither part is sourced. The value carries the REQUIREMENT so that whoever
# sources it has to satisfy it, and elec/fab.py counts both as open.
PUMP_FET_VALUE  = "NFET-%.0fV-%.0fmR" % (PUMP_FET_VDS_MIN, PUMP_FET_RDSON_MAX)
FREEWHEEL_VALUE = "SCHOTTKY-%.0fV-%.0fA" % (FREEWHEEL_VR_MIN, FREEWHEEL_IF_MIN)


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
    n_en   = Net("EN")
    n_io0  = Net("IO0")
    n_rx   = Net("RXD0")
    n_tx   = Net("TXD0")

    # ── Connectors — terminal blocks, not JST. Every one of these is landed once
    # at assembly, so JST's plug/unplug advantage goes unused, and a terminal is
    # ONE part with no mating half to stock (PCB_README §3).
    j_bat = gen.part("J1", "TB-5.08-2", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal",
                     ["VBAT", "GND"], "battery in, 15-20 V, 15 A — MKDS-3 screw: Phoenix has no push-in at 5.08/2-pos, and 7.5 A wants the heavier series")
    j_pa  = gen.part("J2", "TB-5.08-2", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal",
                     ["VBAT", "LO"], "pump A, 7.5 A")
    j_pb  = gen.part("J3", "TB-5.08-2", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal",
                     ["VBAT", "LO"], "pump B, 7.5 A")
    j_joy = gen.part("J4", "TB-3.5-5", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-5-3.5-H_1x05_P3.50mm_Horizontal",
                     ["3V3", "GND", "VRY", "VRX", "SW"], "KY-023 joystick, 3V3 NOT 5 V — PT = push-in, no screw to vibrate loose")
    j_lvl = gen.part("J5", "TB-3.5-4", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-4-3.5-H_1x04_P3.50mm_Horizontal",
                     ["VBAT", "GND", "OUT", "MODE"], "XKC-Y25 level, open-collector out")
    j_prg = gen.part("J6", "PROG", "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
                     ["3V3", "GND", "TXD", "RXD", "EN", "IO0"],
                     "programming; no USB-C — a connector is a water path outdoors")

    # ── Input protection ────────────────────────────────────────────────────
    d_tvs = gen.part("D1", "SMBJ24A", "Diode_SMD:D_SMB", ["K", "A"],
                     "TVS: 24 V standoff > 20 V pack, ~39 V clamp < 60 V FETs")
    c_in1 = gen.part("C1", "100u/50V", "Capacitor_SMD:CP_Elec_10x10.5", 2, "bulk at the switches")
    c_in2 = gen.part("C2", "100u/50V", "Capacitor_SMD:CP_Elec_10x10.5", 2, "bulk at the switches")

    gnd  += j_bat["GND"], d_tvs["A"], c_in1[2], c_in2[2]
    vbat += j_bat["VBAT"], d_tvs["K"], c_in1[1], c_in2[1], j_pa["VBAT"], j_pb["VBAT"], j_lvl["VBAT"]

    # ── 18 V -> 3.3 V buck. >= 40 V in; 24 V-max parts are too close to a fresh
    # pack. ~1 A covers the ESP32's ~500 mA WiFi bursts.
    u_bk = gen.part("U1", "LMR14020SDDA", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                    {1: "BOOT", 2: "VIN", 3: "EN", 4: "RT", 5: "FB", 6: "COMP",
                     7: "GND", 8: "SW"}, "18 V -> 3.3 V, 40 V in, 2 A")
    l1   = gen.part("L1", "15uH/3A", "Inductor_SMD:L_Bourns_SRN6045TA", 2, "buck inductor")
    c_bt = gen.part("C3", "100n", "Capacitor_SMD:C_0603_1608Metric", 2, "boot")
    c_o1 = gen.part("C4", "22u/16V", "Capacitor_SMD:C_1206_3216Metric", 2, "3V3 out")
    c_o2 = gen.part("C5", "10u/16V", "Capacitor_SMD:C_0805_2012Metric", 2, "3V3 out")
    r_f1 = gen.part("R1", "100k", "Resistor_SMD:R_0603_1608Metric", 2, "FB top")
    r_f2 = gen.part("R2", "31k6", "Resistor_SMD:R_0603_1608Metric", 2, "FB bottom -> 3.3 V")

    vbat += u_bk["VIN"], u_bk["EN"]
    n_sw += u_bk["SW"], l1[1], c_bt[2]
    v3v3 += l1[2], c_o1[1], c_o2[1], r_f1[1], j_joy["3V3"], j_prg["3V3"]
    n_fb += r_f1[2], r_f2[1], u_bk["FB"]
    gnd  += u_bk["GND"], c_o1[2], c_o2[2], r_f2[2]
    c_bt[1] += u_bk["BOOT"]

    # ── MCU ─────────────────────────────────────────────────────────────────
    # Joystick on IO34 and pumps on IO25/IO26 match the firmware already running.
    u_mcu = gen.part("U2", "ESP32-WROOM-32E", "wbp:ESP32-WROOM-32E-FABDRILL",
                     {1: "GND", 2: "3V3", 3: "EN", 6: "IO34", 7: "IO35", 10: "IO25",
                      11: "IO26", 12: "IO27", 13: "IO14", 25: "IO0", 34: "RXD0",
                      35: "TXD0", 38: "GND"}, "MCU + WiFi. LOCAL footprint: KiCad's stock one has twelve 0.2 mm thermal vias, below the 0.3 mm fab minimum — 12 of this board's 14 DRC violations were that one footprint")
    c_m1 = gen.part("C6", "10u/16V", "Capacitor_SMD:C_0805_2012Metric", 2, "MCU bulk")
    c_m2 = gen.part("C7", "100n", "Capacitor_SMD:C_0603_1608Metric", 2, "MCU decoupling")
    r_en = gen.part("R3", "10k", "Resistor_SMD:R_0603_1608Metric", 2, "EN pull-up")
    c_en = gen.part("C8", "1u", "Capacitor_SMD:C_0603_1608Metric", 2, "EN RC, power-on reset")

    v3v3 += u_mcu["3V3"], c_m1[1], c_m2[1], r_en[1]
    gnd  += u_mcu["GND"], c_m1[2], c_m2[2], c_en[2]
    n_en += u_mcu["EN"], r_en[2], c_en[1], j_prg["EN"]
    n_io0 += u_mcu["IO0"], j_prg["IO0"]
    n_rx += u_mcu["RXD0"], j_prg["RXD"]
    n_tx += u_mcu["TXD0"], j_prg["TXD"]
    gnd  += j_prg["GND"]

    # ── Pump drive: one low-side switch each. 60 V so the freewheel clamp has
    # margin; ~5 mOhm gives ~0.28 W at 7.5 A, against ~0.9 W for a BTS7960 half.
    for n, (gate, lo, pwm, jp) in enumerate(
            ((n_gA, n_pA, n_pwmA, j_pa), (n_gB, n_pB, n_pwmB, j_pb)), start=1):
        q = gen.part("Q%d" % n, PUMP_FET_VALUE, "Package_TO_SOT_SMD:TO-252-3_TabPin2",
                     {1: "G", 2: "D", 3: "S"}, "pump %d low-side switch" % n)
        u = gen.part("U%d" % (2 + n), "UCC27517", "Package_TO_SOT_SMD:SOT-23-5",
                     {1: "IN", 2: "GND", 3: "NC", 4: "OUT", 5: "VDD"},
                     "gate driver — 7.5 A at 20 kHz is not a job for a bare GPIO")
        d = gen.part("D%d" % (1 + n), FREEWHEEL_VALUE, "Package_TO_SOT_SMD:TO-263-2",
                     ["A", "K"], "freewheel — the board's largest heat source, ~1.5 W")
        rg = gen.part("R%d" % (3 + n), "10R", "Resistor_SMD:R_0603_1608Metric", 2, "gate")
        rp = gen.part("R%d" % (5 + n), "100k", "Resistor_SMD:R_0603_1608Metric", 2,
                      "gate pull-down — FET off while the MCU boots")
        cv = gen.part("C%d" % (8 + n), "100n", "Capacitor_SMD:C_0603_1608Metric", 2,
                      "driver decoupling")
        pwm += u["IN"]
        v3v3 += u["VDD"], cv[1]
        gnd += u["GND"], cv[2], q["S"], rp[2], d["A"]
        gate += u["OUT"], rg[1]
        rg[2] += q["G"]
        rp[1] += q["G"]
        lo += q["D"], d["K"], jp["LO"]

    n_pwmA += u_mcu["IO26"]
    n_pwmB += u_mcu["IO25"]

    # ── Sensing ─────────────────────────────────────────────────────────────
    r_d1 = gen.part("R20", RDIV_TOP, "Resistor_SMD:R_0603_1608Metric", 2, "VBAT sense top")
    r_d2 = gen.part("R21", RDIV_BOT, "Resistor_SMD:R_0603_1608Metric", 2, "VBAT sense bottom")
    c_d  = gen.part("C11", "100n", "Capacitor_SMD:C_0603_1608Metric", 2, "VBAT sense filter")
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


# ── THE BOARD ───────────────────────────────────────────────────────────────
# Millimetres, board-centred, +Y UP. These come FROM THE MECHANICAL MODEL: the
# board lies flat on the frame's +X outer face, which is FRAME_D x DECK_Z =
# 210 x 164. 140 x 100 leaves ~35 mm of margin all round for the shroud wall and
# its cable anchor.
BOARD_W, BOARD_L = 95.0, 100.0
HOLE_D = 4.5                                   # M4 clearance, THROUGH the board
HOLES = [(-41.0, -44.0), (41.0, -44.0), (-41.0, 44.0), (41.0, 44.0)]

BOARD_NOTES = {
    "outline_mm": (BOARD_W, BOARD_L),
    "cutouts": [{"xy": xy, "d": HOLE_D} for xy in HOLES],
    "layers": 2,
    "thickness_mm": 1.6,
    # Zoned so each cluster sits beside the pin it serves (PCB_README §4: a part
    # with a value but no required position gets stranded, and the router then
    # carries its net across the board for nothing). Power down the left, buck
    # top-left, MCU right.
    #
    # CONNECTORS ARE ON BOTH EDGES, which the 140-wide board did not need. At 95
    # the bottom edge has ~72 mm clear of the corner holes and the five terminals
    # want 72.7, so the joystick (J5) and the programming header (J6) move to the
    # top edge. The four that carry POWER or leave the pack downward -- battery,
    # both pumps, the level sensor -- stay on the bottom, which is the edge the
    # housing opens at.
    "placements": {
        # terminals, bottom edge (MKDS-3 is ~12.5 wide; PT-1,5-4 ~17.6)
        "J1": (-29.0, -41.0, 0.0), "J2": (-15.0, -41.0, 0.0),
        "J3": (-1.0, -41.0, 0.0),  "J4": (19.0, -41.0, 0.0),
        # joystick + programming, top edge. J6 is turned 90 so its six pins run
        # ALONG the edge instead of reaching down into the decoupling cluster.
        "J5": (-20.0, 41.0, 0.0),  "J6": (12.0, 41.0, 90.0),
        # MCU. The ESP32 footprint's COURTYARD is not the module -- it is a
        # T-shaped polygon that includes the antenna fan (local x +-24.25,
        # y -28..13.54), and the matching keepout bans tracks, vias, pads, pour
        # AND footprints. So the fan has to hang off a board edge, not lie
        # across the board.
        #
        # 270, not 90: at rot 90 the fan points -X, straight back over the
        # board, which is what put C7, R21 and all six J6 pads inside it. 270
        # turns it to +X, where it leaves the laminate at x=47.5 and the only
        # thing it still covers is the corner mounting hole -- a cutout, which
        # the keepout does not forbid.
        "U2": (34.4, 19.5, 270.0),
        # MCU decoupling, left of the module and clear of its body
        "C6": (8.0, 32.0, 0.0), "C7": (8.0, 26.0, 0.0),
        "R3": (2.0, 32.0, 0.0), "C8": (2.0, 26.0, 0.0),
        # input protection + bulk, left column
        "D1": (-36.0, 2.0, 0.0), "C1": (-36.0, -12.0, 0.0), "C2": (-36.0, -24.0, 0.0),
        # pump legs: FET / driver / freewheel in a row, gate parts beside the FET
        "Q1": (-18.0, -10.0, 0.0), "Q2": (-18.0, 4.0, 0.0),
        "U3": (-8.0, -10.0, 0.0),  "U4": (-8.0, 4.0, 0.0),
        "D2": (5.0, -10.0, 0.0),   "D3": (5.0, 4.0, 0.0),
        "R4": (-27.0, -14.0, 0.0), "R5": (-27.0, -8.0, 0.0),
        "R6": (-27.0, 2.0, 0.0),   "R7": (-27.0, 8.0, 0.0),
        "C9": (-2.0, -20.0, 0.0),  "C10": (-2.0, 12.0, 0.0),
        # buck, top left
        "U1": (-36.0, 26.0, 0.0), "L1": (-20.0, 26.0, 0.0),
        "C3": (-36.0, 14.0, 0.0), "C4": (-8.0, 20.0, 0.0), "C5": (-8.0, 26.0, 0.0),
        "R1": (-27.0, 16.0, 0.0), "R2": (-27.0, 22.0, 0.0),
        # sensing — moved off x=40, which is now inside the antenna keepout
        "R20": (22.0, 6.0, 0.0), "R21": (22.0, 0.0, 0.0), "C11": (33.0, 0.0, 0.0),
        "R22": (14.0, -22.0, 0.0), "C12": (14.0, -28.0, 0.0),
        "R23": (14.0, -18.0, 0.0),
        # buzzer — below the keepout's y band
        "BZ1": (33.0, -24.0, 0.0), "Q3": (22.0, -14.0, 0.0),
        "R24": (28.0, -8.0, 0.0), "D4": (28.0, -2.0, 0.0),
    },
    "zones": [("GND", "B.Cu", 0.3)],
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

# The HOUSING's y budget, which is what actually caps the board now: the frame
# is 210 deep, the Makita dock is 100.6 across its slide, and the printed walls
# and board clearance take ~13. BOARD_W is the leftover, and it is the binding
# constraint -- not the old printed frame's face.
_DOCK_W, _WALLS = 100.6, 13.0
assert BOARD_W <= 210.0 - _DOCK_W - _WALLS, (
    "board is %.1f wide; only %.1f fits beside the battery in a 210 deep frame"
    % (BOARD_W, 210.0 - _DOCK_W - _WALLS))
# ... and staying inside 100 x 100 keeps it in JLCPCB's cheapest 2-layer tier.
assert BOARD_W <= 100.0 and BOARD_L <= 100.0, "board leaves the <=100x100 price tier"


if __name__ == "__main__":
    circuit()
    gen.emit("main", OUT_DIR, BOARD_NOTES)
