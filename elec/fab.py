"""The order packages for this project's boards: gerbers, drill, BOM, CPL, one zip each.

COPY THIS FILE TO YOUR PROJECT AS `elec/fab.py`, then:

    "C:/Program Files/KiCad/10.0/bin/python.exe" elec/fab.py           # every board in BOARDS
    "C:/Program Files/KiCad/10.0/bin/python.exe" elec/fab.py main      # just one

(KiCad's own Python: the drill check reads the board with pcbnew.)

It refuses to package a board that is not finished (unconnected items, DRC violations, a
failed length-match), checks the gerbers and drill against the board, and writes
ROTATION-CHECK.txt and ORDER.txt into each zip. See cadkit/pcbflow/fab_package.py.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from cadkit.pcbflow import fab_package as _fab  # noqa: E402

# Every board in the design. A package whose board is not listed here and has no
# generator is deleted as stale.
BOARDS = ("main",)

# value (as the netlist carries it) -> LCSC part number. Write a number here ONLY when you
# have read it off the listing yourself, and check stock the day you order.
LCSC = {
    # ── Read off the JLCPCB parts library 2026-10-04. Stock figures are from that
    # day and are NOT a promise: M12 asks for stock "today", so check again at order
    # time. What does not change between now and then is the REASONING, which is why
    # each line carries it.
    #
    # Actives
    "UCC27517":        "C99395",    # TI UCC27517DBVR, SOT-23-5, 51672. The TI part
                                    # specifically: the UMW listing publishes no VIH at
                                    # all, which is the whole reason main.py names TI.
    "ESP32-WROOM-32E": "C701342",   # Espressif -N8, 17767. N8 over the cheaper N4 on
                                    # purpose: N4's listing names TWO possible dies
                                    # (D0WD-V3 or D0WDR2-V3) and shows idle-only stock,
                                    # and M35's errata sign-off is specific to D0WD-V3.
                                    # 8 MB also leaves OTA room. +$0.94 for an unambiguous
                                    # die is the cheapest certainty on this board.
    "LMR14020SDDA":    "C187824",   # TI LMR14020SDDAR, 22016. ⚠ listed as HSOP-8-EP
                                    # against this board's SOIC-8-1EP land -- same
                                    # 1.27 mm 8-pin body with a thermal pad, but the pad
                                    # geometry is NOT yet measured against the footprint.
                                    # See the open note in quality_signoff M12.
    "MMBT3904":        "C20526",    # BASIC library, 269506, $0.012. The only Basic part
                                    # on this board, so the only one with no extended fee.
    "NFET-60V-10mR":   "C67279",    # Infineon IRLR3636TRPBF, TO-252, 5400. Verified
                                    # against the datasheet (PD-96224) rather than the
                                    # listing: RDS(on) 6.6 typ / 8.3 MAX mOhm at
                                    # Vgs = 4.5 V, so it meets this requirement AS
                                    # WRITTEN -- no relaxation needed -- and 5.4/6.8 at
                                    # the 10 V this board actually drives. V(BR)DSS 60 V
                                    # min, Vgs(th) 1.0-2.5, Qg 33/49 nC at 4.5 V.
                                    # ⚠ Qg is what rejected the alternatives: VGATE is a
                                    # 1k5 dropper and a 10 V shunt, so at a flat 15 V
                                    # pack only (15-10)/1500 = 3.33 mA is available, and
                                    # Qg x 20 kHz has to fit inside it with the Zener's
                                    # knee current left over. IPD034N06N3G (98 nC at
                                    # 10 V) and AP9990GH (Ciss 3.7 nF) are better on
                                    # RDS(on) and do not fit that budget.
    "SCHOTTKY-60V-15A-vf0V59": "C260296",   # SMC MBRB2060CT, D2PAK, 495, 740 mV at 10 A.
                                    # Common-cathode dual, which is what the footprint's
                                    # {1:A, 2:K, 3:A2} declaration expects; both anodes
                                    # are paralleled so each leg sees 3.75 A of the 7.5 A
                                    # peak, and the hot Vf lands near 0.50 V against the
                                    # 0.59 V ceiling main.py derives.
    "SCHOTTKY-60V-3A": "C7428237",  # SS36 in SMA, 8146. The buck's catch diode: 0.50 A
                                    # average, so an SMA jellybean is ample.
    "ZENER-10V-0W5":   "C2103",     # BZT52C10, SOD-123, 84843. 9.4-10.6 V band keeps
                                    # VGATE inside the driver's 4.5-18 V and the gate's
                                    # +-20 V with room.
    # Passives and protection
    "PTC-30V-200mA":   "C69680",    # nSMD020-30V, 1206, 192784. 200 mA hold / 460 mA
                                    # trip / 30 V, which is exactly what the asserts in
                                    # main.py's fuse block check against a 10 mA sensor.
    "SMCJ24A":         "C310039",  # Brightking SMCJ24A/TR13, 12745, $0.1452. ⚠ NOT a
                                    # generic D_SM[AB] land any more and that is the
                                    # point: D_SMC does not match fab_package's GENERIC
                                    # pattern, so this value HAS to carry a number.
                                    # 1.5 kW, VC 38.9 V at 38.6 A -- the SAME clamp as
                                    # the SMBJ24A it replaces, confirmed across five
                                    # makers' listings, so nothing downstream moves.
                                    # IFSM 200 A at 8.3 ms = 332 A2s against the 10 A
                                    # ATO fuse's 115 A2s minimum melt: the fuse clears
                                    # first with 2.9x margin, which is the whole reverse
                                    # polarity story (main.py, TVS_I2T_MARGIN).
                                    # Alternates, same ratings: C224045 Littelfuse
                                    # (2941, $0.3236 -- same maker as the fuse whose
                                    # I2t this is argued against), C284096 DOWO (5247,
                                    # $0.1026), C151903 BORN (4207), C10771 RUILON.
    # Passive, but NOT a generic one -- see the note on OPEN_VALUES below
    "10uH/4A6sat":     "C2046332",  # Bourns SRN6045TA-100M, 1423, $0.2398. The part
                                    # the board was designed around: the footprint is
                                    # literally L_Bourns_SRN6045TA, and the listing's
                                    # "10uH 3.2A 4.6A 52mOhm" matches the line already
                                    # recorded in main.py -- Irms 3.20 A, Isat 4.60 A,
                                    # DCR 52 mOhm -- so the value string "10uH/4A6sat"
                                    # needs no change.
                                    # ⚠ THE REQUIREMENT IS Isat > 3.8 A, NOT 4.6. 3.8 is
                                    # BUCK_ILIM_MAX, the LMR14020's high-side current
                                    # limit at its MAX (SNVSAA5B 5.5), because during a
                                    # short the part drives to that limit and an
                                    # inductor that saturates below it stops being an
                                    # inductor. 4.6 is just this part's typ. main.py
                                    # asserts the inequality, not the number.
                                    # Alternate (M42, single maker): C285869, Chilisin
                                    # LVC606045-100M-N, 10 uH, DCR 60 mOhm, Isat 4.6 A
                                    # typ -- and 4.14 A on the datasheet's worst-case
                                    # column, which still clears 3.8 A by 9 %. Read off
                                    # the Chilisin LVC datasheet page 9, NOT off the
                                    # listing: JLCPCB prints that part as "2.34A 4.6A",
                                    # which is Irms-worst-case then Isat-typ -- neither
                                    # the datasheet's own column order (Isat, Irms) nor
                                    # a consistent one. The same search returned a TDK
                                    # line reading "1.6A 1.6A 10uH", with the
                                    # inductance last. Position means nothing here.
    # Through-hole, hand-soldered at assembly (CIRCUIT.md section 7) -- these
    # five are NOT in the SMT BOM and carry no extended-part fee.
    "3V-ACTIVE":       "C252936",   # INGHAi GMD12065YB-3V2700, 787. Active (built-in
                                    # driving circuit) electromagnetic, so a GPIO-rate
                                    # square wave is not needed -- which is the whole
                                    # reason the schematic drives it through Q3 rather
                                    # than from a timer. 2V~5V operating, 3 V nominal,
                                    # 30 mA, 80 dB, 2.7 kHz. ⚠ CHOSEN ON PITCH, NOT ON
                                    # BODY SIZE: the footprint is Buzzer_12x9.5RM7.6 and
                                    # JLCPCB's own package filter offers both "12x9.5"
                                    # and "12x9.5pitch7mm" -- a 7.0 mm part is a
                                    # footprint mismatch that matching on "12 mm" would
                                    # have walked straight into. This one is 7.6 mm.
                                    # Body 6.5 mm tall against the footprint's 9.5, so
                                    # it fits under the lid with room to spare.
                                    # Alternate: C17701078, HYDZ HYE1206-03ST, same
                                    # ratings and the same 7.6 mm pitch, 256 in stock.
    "PROG":            "C42431790", # PZ2.54-1X6P-H25, 7503, $0.0331. A plain vertical
                                    # 1x6 2.54 header: no maker pinout to get wrong,
                                    # because the order is this board's own and is
                                    # printed on B.Silk (M26).
    # ── The five field terminals, ALL ONE PART FAMILY ──────────────────────
    # Ningbo Kangnex WJ500V-5.08-NP, read from the customer drawing (LCSC C8465,
    # sheet 1/1, rev A 2024.03.10) rather than from the listing -- and the two
    # disagree in a way that matters. The LISTING says 18 A / 14-30 AWG. The
    # DRAWING says UL 10 A / IEC 24 A, 22-12 AWG. The drawing wins, and 10 A is
    # the number to design against: J2 and J3 carry one pump's 7.5 A
    # continuously (75 %), and J1 carries the same 7.5 A chopped at D = 0.60-0.80,
    # so 6.7 A RMS worst case (67 %) -- never both pumps, which is what
    # tools/check_pump_dirs.py exists to hold.
    #
    # ⚠ THE FOOTPRINT IS A PHOENIX MKDS-3 AND THE PART IS NOT A PHOENIX. That is
    # deliberate and it is measured, not assumed:
    #   pin      WJ500V is a 0.90 mm ROUND post (not the square post these blocks
    #            are often assumed to have). MKDS-3 drills 1.30, so +0.40 mm --
    #            inside IPC-2222's +0.25..+0.70 preferred band for a hand-soldered
    #            lead. The drawing's own recommendation is 1.50 (+0.60), also in
    #            band; 1.30 is the tighter of the two and so the better fill.
    #   pitch    5.08 both.
    #   body     MKDS-3's F.Fab is exactly N x 5.08 wide -- identical to the
    #            WJ500V -- and 11.20 mm deep against the WJ500V's 10.00, with the
    #            hole row 5.30/5.90 from the two faces against 4.50/5.50. So the
    #            footprint is a strict SUPERSET of the real body on every side:
    #            anything that clears the footprint clears the part.
    #   height   14.07 mm above board, which is now the measured number in both
    #            component-height tables and is what sets the housing bay depth.
    "TB-5.08-2":       "C8465",     # WJ500V-5.08-2P, 260480, $0.1337. J1/J2/J3.
    # ⚠ THE ONE PART ON THIS BOM THAT WAS CHOSEN BY WHAT IS ALREADY IN A DRAWER.
    # F2 takes a standard ATO/ATC blade, which is what McMaster 7460K45 is -- a
    # 10 A 32 V ATC, bought in a pack of five long before this board existed. The
    # holder was then picked to suit the fuse rather than the other way round, so
    # the fuse itself is NOT a BOM line and never will be: it is the owner's.
    #
    # 178.6165.0002 and 178.6165.0001 are the same holder in different boxes (500
    # and 100); LCSC sells either by the piece, and .0002 is the one in stock --
    # 571 pcs at $3.2949 against .0001's zero (C207060, read 2026-10-05). KiCad's
    # footprint is named for 178.6165 and the datasheet's "4 pins each" matches
    # its eight plated holes, which is how the land was confirmed rather than
    # assumed. Hand-soldered with the five terminal blocks, not reflowed.
    "178.6165.0002":   "C207061",   # Littelfuse FLR ATO holder, 571, $3.2949. F2.
    "TB-5.08-4":       "C42377749", # WJ500V-5.08-04P-14-00A, 6376, $0.3252. J5.
    "TB-5.08-5":       "C42377750", # WJ500V-5.08-05P-14-00A, 2142, $0.4162. J4.
                                    # ⚠ J4 USED TO BE A 3.5 mm PUSH-IN PT-1,5 and
                                    # the comment on it said "no screw to vibrate
                                    # loose". Trading that away was a decision, not
                                    # an oversight: one family means one footprint
                                    # drawing to be wrong about, one screwdriver,
                                    # one wire-range spec and one entry-face rule
                                    # for all five terminals -- and a torqued M2.5
                                    # screw on 0.4 N.m is not the vibration risk a
                                    # spring cage is usually sold against.
    "100u/50V":        "C371283",   # SamYoung MVK50V100M10*10, D10xL10, 1932, 310 mA
                                    # at 120 Hz. ⚠ THE RIPPLE IS THE SPEC HERE AND THE
                                    # VALUE STRING DOES NOT SAY SO. The pumps make the
                                    # supply current a 7.5 A square wave at 20 kHz, so
                                    # the AC the rail must absorb is I*sqrt(D(1-D)) =
                                    # 3.67 A RMS at a fresh pack. It does NOT all land
                                    # in these two: the pack and harness are a branch
                                    # too, and at 20 kHz a 0.3-1.0 uH harness is only
                                    # 68-156 mOhm, so it carries most of it. Each cap
                                    # sees 0.31-0.55 A depending on harness length,
                                    # against ~0.62 A effective after the usual HF
                                    # multiplier -- inside its rating, with the margin
                                    # set by the HARNESS rather than by the capacitor.
                                    # A first pass that omitted the source branch said
                                    # 2.1x OVER and was wrong; it is recorded because
                                    # the omission is the easy mistake to repeat.
}

# Values that are placed but not yet sourced. A value that is neither in LCSC, nor a
# generic passive chosen at order time (an 0603 600R), nor listed here FAILS the build --
# so a changed part number cannot slip through as "just another open item".
OPEN_VALUES = frozenset()
# ── EMPTY, AND THAT IS A RESULT, NOT A DISABLED CHECK ──────────────────────
# Every value placed on this board now has a part number in LCSC above. This set
# held fifteen; the last five to go were the buzzer and the five field terminals
# (which are three values between them). The rule it enforces is unchanged and
# still live: a value that is neither in LCSC, nor a generic passive chosen at
# order time, nor listed here FAILS the build. Emptying it makes that rule
# STRICTER, not weaker -- there is no longer any value exempted from needing a
# number.
#
# ⚠ WHAT THIS SET WAS ALSO DOING, so it is not lost with the entries. Four of
# the fifteen were REQUIREMENTS wearing a value's clothes -- "NFET-60V-10mR",
# "SCHOTTKY-60V-15A-vf0V59", "SCHOTTKY-60V-3A", "PTC-30V-200mA" -- and each one
# sat in a footprint that fab_package's GENERIC pattern matches: R_, C_, Fuse_,
# Inductor_SMD, Diode_SMD:D_SOD and Diode_SMD:D_SM[AB]. The pattern is right to
# exist (a diode in an SMA land normally IS picked by part number, which is why
# D1's "SMBJ24A" needs no entry), but it means the FOOTPRINT says "orderable"
# while the VALUE says something nobody can buy, and the part is quietly counted
# as a generic passive. It caught three parts in one hour, the third within
# minutes of the second. Listing a value here was the only thing that made it
# visible.
#
# So if a requirement-shaped value is ever placed again, it has to come back
# here until it has a number -- otherwise one of those footprints will swallow
# it in the generic count and nothing will say a word.
#
# ⚠ AND A FOURTH ONE GOT THROUGH THAT THIS SET NEVER CAUGHT, because it escaped
# by a different door: "10uH/4A6sat", L1. The GENERIC pattern is matched against
# the WHOLE footprint string as well as the part after the colon, so the LIBRARY
# name can match it -- L1's land is "Inductor_SMD:L_Bourns_SRN6045TA_...", and
# "Inductor_SMD" is in the pattern. The leaf name L_Bourns_... matches nothing.
# So this value was never exempted here and never needed to be; it was counted
# as a generic passive from the day it was placed, and it is a REQUIREMENT -- a
# saturation current, which is the one parameter that decides whether a 10 uH
# 6045 inductor works in this circuit at all. Two parts with identical BOM lines
# can differ 2:1 on it. Found by reading the 19 generic lines one at a time for
# M30, not by any gate. It is sourced now (C2046332).
#
# The lesson is narrower than "list more values": the generic test asks whether
# the LAND is one you normally fill from a catalogue, and then trusts the VALUE
# to be orderable. Those are two different questions and the second one has no
# gate. Reading the generic list by eye before an order is the only thing that
# has ever caught these -- four times out of four.

_fab.configure(HERE, BOARDS, LCSC, OPEN_VALUES)

if __name__ == "__main__":
    _fab.main(sys.argv[1:] or list(BOARDS))
