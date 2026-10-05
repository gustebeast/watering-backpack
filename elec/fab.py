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
OPEN_VALUES = frozenset({
    # ── THE TWO THAT ARE DECIDED AS REQUIREMENTS BUT NOT AS PARTS ──────────
    # Both carried a part number that did not meet the requirement. See the
    # "Pump power semiconductors" block in main.py; do not re-source these two
    # without reading it.
    "NFET-60V-10mR",     # >= 60 V Vds, <= 10 mOhm at 4.5 V Vgs, DPAK/TO-263
    "SCHOTTKY-60V-15A-vf0V59",  # >= 60 V, >= 15 A, low Vf, D2PAK. 1 A parts share the
                         # SS1x numbering and will not survive this leg.
    # ⚠ AND THIS ONE WAS COUNTED AS "GENERIC" UNTIL IT WAS LISTED HERE, which is
    # worth knowing about the gate: fab_package's GENERIC pattern matches
    # Diode_SMD:D_SM[AB], because a diode in an SMA land is normally picked by
    # PART NUMBER and D1's "SMBJ24A" and D4's "1N4148W" are perfectly good
    # orderable values. This one is not a part number, it is a requirement in
    # the same style as the two above -- so the footprint said "orderable" and
    # the value said nothing anybody could buy, and the package reported it in
    # the generic count. The declaration below is what makes it visible.
    "SCHOTTKY-60V-3A",   # the buck's CATCH diode, which the board did not have
                         # at all: the LMR14020 integrates only a high-side
                         # MOSFET (SNVSAA5B 6.1), so without this the SW node
                         # is driven past its -3 V rating every cycle and the
                         # 3V3 rail -- hence the MCU, the joystick and the gate
                         # drivers' logic -- never comes up. >= 60 V (the
                         # datasheet's floor is 1.25 x VIN = 25; 60 matches
                         # everything else on this node and the TVS's 38.9 V
                         # clamp), >= 3 A per 7.2.2.5's own starting point,
                         # against a 0.50 A average. SMA.
    # And a third one through the same hole, within the hour: GENERIC also
    # matches "Fuse_", for the same good reason -- a fuse is normally named by
    # part number. This is a requirement.
    "PTC-30V-200mA",     # the level sensor's feed, the only fused net on the
                         # board. VBAT left here unfused down the most exposed
                         # conductor in the machine -- J5's lead climbs the
                         # OUTSIDE of the case to the tank -- with a Makita pack
                         # behind it and only a switch at the dock. Resettable
                         # on purpose: this thing is carried into a garden, and
                         # a cartridge fuse out there is a walk home. >= 30 V
                         # (clears a 20 V fresh pack), 0.2 A hold against a
                         # ~10 mA sensor. 1206.
    # ── decided in the schematic, part number not read off a listing yet ───
    "ESP32-WROOM-32E",   # expect an Extended part at JLCPCB (CIRCUIT.md section 3)
    "LMR14020SDDA",      # the >= 40 V buck; CIRCUIT.md section 2 lists the alternates
    "UCC27517",          # gate driver, non-inverting -- the inverting sibling
                         # (UCC27516) would run the pumps whenever the MCU was held
                         # in reset, so the suffix matters
    "MMBT3904",          # buzzer driver
    "ZENER-10V-0W5",     # VGATE shunt. The gate drivers are 4.5-18 V parts and
                         # 3V3 is the only other rail on the board, so this is
                         # what makes the pumps switch at all. Any 10 V +-5%,
                         # >= 0.5 W SOD-123 Zener does it.
    "100u/50V",          # bulk electrolytic, CP_Elec_10x10.5 -- not a generic 0603
    "3V-ACTIVE",         # active buzzer, 3 V rated (CIRCUIT.md section 5)
    "PROG",              # 1x06 2.54 header
    "TB-5.08-2",         # Phoenix MKDS-3, battery + both pumps
    "TB-3.5-4",          # Phoenix PT-1,5-4, level sensor
    "TB-3.5-5",          # Phoenix PT-1,5-5, joystick
})

_fab.configure(HERE, BOARDS, LCSC, OPEN_VALUES)

if __name__ == "__main__":
    _fab.main(sys.argv[1:] or list(BOARDS))
