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
    n_rt   = Net("RT")
    n_ss   = Net("SS")
    n_vg   = Net("VGATE")
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
    l1   = gen.part("L1", "15uH/3A", "Inductor_SMD:L_Bourns_SRN6045TA", 2, "buck inductor")
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
    c_bt = gen.part("C3", "100n", "Capacitor_SMD:C_0603_1608Metric", 2, "boot")
    c_o1 = gen.part("C4", "22u/16V", "Capacitor_SMD:C_1206_3216Metric", 2, "3V3 out")
    c_o2 = gen.part("C5", "10u/16V", "Capacitor_SMD:C_0805_2012Metric", 2, "3V3 out")
    r_f1 = gen.part("R1", FB_TOP, "Resistor_SMD:R_0603_1608Metric", 2, "FB top")
    r_f2 = gen.part("R2", FB_BOT, "Resistor_SMD:R_0603_1608Metric", 2,
                    "FB bottom -> %.2f V" % FB_VOUT)
    # "The RT/SYNC pin can't be left floating or shorted to ground" -- datasheet
    # SNVSAA5B section 6.3.8, in those words. It was floating. 49.9k is the
    # datasheet's own table value for 500 kHz, which with the 15 uH inductor
    # gives 0.37 A of ripple at a 20 V input.
    r_rt = gen.part("R8", BUCK_RT, "Resistor_SMD:R_0603_1608Metric", 2,
                    "switching frequency: %.0f kHz" % BUCK_FSW_KHZ)
    # SS, the pin this file used to call COMP. Floating it leaves the ramp to
    # stray capacitance and 3 uA, which is no ramp at all: 10 nF x 0.75 V / 3 uA
    # gives a defined 2.5 ms into 42 uF of output capacitance.
    c_ss = gen.part("C14", "10n", "Capacitor_SMD:C_0603_1608Metric", 2,
                    "buck soft-start, ~2.5 ms")

    vbat += u_bk["VIN"], u_bk["EN"], c_bki[1]
    n_sw += u_bk["SW"], l1[1], c_bt[2]
    v3v3 += l1[2], c_o1[1], c_o2[1], r_f1[1], j_joy["3V3"], j_prg["3V3"]
    n_fb += r_f1[2], r_f2[1], u_bk["FB"]
    n_rt += u_bk["RT"], r_rt[1]
    n_ss += u_bk["SS"], c_ss[1]
    gnd  += (u_bk["GND"], u_bk["EP"], c_o1[2], c_o2[2], r_f2[2], r_rt[2],
             c_ss[2], c_bki[2])
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
    c_vg = gen.part("C13", "10u/16V", "Capacitor_SMD:C_0805_2012Metric", 2,
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
        cv = gen.part("C%d" % (8 + n), "100n", "Capacitor_SMD:C_0603_1608Metric", 2,
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
    # Power LEAVING the board down a cable, which is the worst inductance in the
    # system (PCB_QUALITY A2, rule 4). Both of these feed a sensor or a stick on
    # the end of a lead and had no charge nearer than the far side of the board:
    # +3V3 at the joystick was 64.7 mm from C4, VBAT at the level sensor 55.1 mm
    # from C1.
    c_joy = gen.part("C16", "10u/16V", "Capacitor_SMD:C_0805_2012Metric", 2,
                     "local charge at the joystick connector")
    c_lvl = gen.part("C17", "10u/50V", "Capacitor_SMD:C_1206_3216Metric", 2,
                     "local charge at the level-sensor connector")
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
    #   MKDS-3 (J1/J2/J3)  crt dx +-5.63   pad1 dx -2.54   pad2 dx +2.54
    #   PT-1,5-5 (J4)      crt dx +-9.295  pads dx -7, -3.5, 0, +3.5, +7
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
        # -- buck, top left: UNCHANGED ---------------------------------------
        "U1": (-36.0, 26.0, 0.0), "L1": (-20.0, 26.0, 0.0),
        "C3": (-36.0, 14.0, 0.0), "C4": (-8.0, 20.0, 0.0),
        "C5": (-8.0, 26.0, 0.0),  "R1": (-27.0, 16.0, 0.0),
        "R2": (-27.0, 22.0, 0.0), "R8": (-27.0, 10.0, 0.0),
        "C14": (-20.0, 14.0, 0.0),
        # The buck's input ceramic, AT the part: U1's VIN pad is at (-38.5,
        # 26.6) and its GND pad at (-33.5, 26.6), so this sits just above both
        # and the hot loop closes in millimetres instead of in 38.
        "C15": (-38.5, 30.8, 0.0),
        # -- MCU cluster, UNCHANGED ------------------------------------------
        # 270, not 90: at rot 90 the antenna fan points -X, straight back over
        # the board. At 270 it leaves the laminate at x=47.5 and the only thing
        # it still covers is a corner mounting hole -- a cutout, which the
        # keepout does not forbid.
        "U2": (34.4, 19.5, 270.0),
        "C6": (36.5, 31.5, 0.0), "C7": (42.8, 31.5, 0.0),
        "R3": (2.0, 32.0, 0.0),  "C8": (2.0, 26.0, 0.0),
        # -- sensing and the buzzer, right of the switch row ------------------
        # R20's top leg is on VBAT and a long way from the pour, which is right
        # rather than sloppy: the divider passes 170 uA. What must be short is
        # VBAT_SENSE -- the 100k node the ADC reads -- so R21 and C11 sit at the
        # MCU and the long run is the one carrying nothing.
        "R20": (22.0, 6.0, 0.0), "R21": (22.0, 0.0, 0.0), "C11": (33.0, 0.0, 0.0),
        "R22": (20.0, -22.0, 0.0), "C12": (20.0, -26.0, 0.0),
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
        "TP5": (-28.0, 26.0, 0.0),  "TP6": (-26.2, -8.0, 0.0),
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
            {"net": "VBAT", "from": "J1.1", "to": ["U1.2", "J5.1"],
             # the buck's input (~0.16 A at the flat end of the pack) and the
             # level sensor's feed (milliamps). 0.3 A is the rounded-up total,
             # and these two are the only VBAT loads that are not the pumps.
             "amps": 0.3},
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
            "SCHOTTKY-60V-15A": "TO-263-2: measured off KiCad's land -- pad 2 "
                                "is the 101.5 mm2 tab and a single D2PAK "
                                "Schottky's tab is the CATHODE, so 1 A / 2 K. "
                                "Pad 3 is the second outer lead and is tied to "
                                "the anode, because at this rating the part is "
                                "usually a common-cathode dual",
            "TB-5.08-2": "Phoenix MKDS 3/2-5,08 drawing, read from the WIRE "
                         "entry face; pin 1 is the pad the footprint marks, and "
                         "elec/CIRCUIT.md section 7 records the entry face as "
                         "local +Y for all five terminals",
            "TB-3.5-5": "Phoenix PT 1,5/5-3,5-H drawing, same face and the same "
                        "measurement (CIRCUIT.md section 7: 43 mm3 behind +Y "
                        "against 185 behind -Y, so +Y is the opening)",
            "TB-3.5-4": "Phoenix PT 1,5/4-3,5-H drawing, same face; measured "
                        "54 mm3 behind +Y against 232 behind -Y",
            "PROG": "a 1x06 2.54 header has no maker pinout: the order is this "
                    "board's own, printed on the back silk by kicad_silk and "
                    "listed in elec/CIRCUIT.md -- 3V3, GND, TXD, RXD, EN, IO0",
        },
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
