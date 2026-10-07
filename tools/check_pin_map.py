"""Cross-check the firmware's pin map against the board's, and both against the
ESP32's own electrical rules.

    py -3.12 tools/check_pin_map.py          # exit 0 = every property holds

WHY THIS EXISTS. Six signals are typed independently in two files that nothing
connects: firmware/src/main.cpp names GPIOs as `*_PIN` constants, and
elec/main.py wires nets to `u_mcu["IOnn"]`. They agree today only because
somebody checked by hand once — elec/main.py still carries the comment
"Joystick on IO34 and pumps on IO25/IO26 match the firmware already running".
Nothing re-checks it. A one-character drift on either side is silent: the board
fabs, the firmware flashes, and a feature is simply dead on arrival, or worse,
a pump gate lands on a pin that is high during boot.

This reads BOTH sides from their own source — no GPIO number is retyped here —
and the correspondence table below is the one place the two domains are tied
together. That makes the table the spec: break either side and this fails.

It also checks what neither file can check alone. Direction is DERIVED from how
the firmware actually uses each pin (ledcAttach/ledcWrite, digitalWrite,
analogRead, digitalRead), not declared, so the electrical rules are applied to
the real role:

  * ADC2 is unusable while WiFi is up (the radio owns that peripheral), and
    this design has WiFi telemetry and OTA. So an ANALOG pin must be on ADC1.
    This is why VBAT sense is on IO35 and the joystick on IO34, and it is the
    rule most likely to be broken by someone "tidying" the pinout.
  * GPIO 34-39 are input-only. An OUTPUT there is a dead feature.
  * Strapping pins decide boot mode. A pump gate or the buzzer on one of those
    fights the bootloader.
  * The module's physical-pin-to-signal map in elec/main.py is checked against
    the WROOM-32E pinout, because a transposition there is a dead board that
    every other check in this repo would pass.

Note on LEVEL_PIN: the firmware sets INPUT_PULLUP and the board also fits R23
to 3V3. Both together is deliberate and harmless (parallel pull-ups); the
external one is what keeps the open-collector sensor's 18 V rail off the pin,
so the internal one is not a substitute for it.
"""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
# The firmware side is three files since the pin setup was written out pin by
# pin: pins.h holds the *_PIN constants, pins.cpp holds the pinMode/attenuation
# calls, main.cpp holds the reads and writes. The role derivation below needs all
# three, so they are read as one text — moving a pin between them must not hide it.
FW = (ROOT / "firmware" / "src" / "pins.h",
      ROOT / "firmware" / "src" / "pins.cpp",
      ROOT / "firmware" / "src" / "main.cpp")
BOARD = ROOT / "elec" / "main.py"
CIRCUIT = ROOT / "elec" / "CIRCUIT.md"

# ---------------------------------------------------------------------------
# THE CORRESPONDENCE. The one place the firmware and the schematic are tied
# together: firmware constant <-> the net variable in elec/main.py that reaches
# the MCU. No GPIO numbers here on purpose — both sides supply their own, and
# the point is to catch them disagreeing.
# ---------------------------------------------------------------------------
PAIRS = (("PUMP_A_PIN", "n_pwmA"),
         ("PUMP_B_PIN", "n_pwmB"),
         ("VBAT_PIN",   "n_vsen"),
         ("JOY_PIN",    "n_joyf"),
         ("LEVEL_PIN",  "n_lvl"),
         ("BUZZ_PIN",   "n_bz"))

# ---------------------------------------------------------------------------
# ESP32 facts (datasheet, not design choices).
# ---------------------------------------------------------------------------
ADC1 = {32, 33, 34, 35, 36, 37, 38, 39}
ADC2 = {0, 2, 4, 12, 13, 14, 15, 25, 26, 27}
INPUT_ONLY = {34, 35, 36, 37, 38, 39}
STRAPPING = {0, 2, 5, 12, 15}
# GPIO6-11 are bonded to the module's own SPI flash and are not led out at all:
# ESP32-WROOM-32E datasheet v2.1 Table 3 note 2, which is also why module pins
# 17-22 are listed as NC. A firmware pin here is not merely illegal, it is a pin
# that does not leave the shield -- and nothing in this gate used to say so.
FLASH_BUS = {6, 7, 8, 9, 10, 11}

# ESP32-WROOM-32E module pinout: physical pin -> the name elec/main.py should
# use for it. Pin 32 is NC on this module.
#
# ⚠ PIN 39 WAS MISSING FROM THIS TABLE, and that made the table itself the
# authority on a pin it had never heard of: when elec/main.py grounded pin 39
# this gate called it "NC or unknown on this module". It is GND. Espressif's
# pin-definition table runs 1-38 plus the optional exposed pad P_GND/39, and
# KiCad's own RF_Module symbol declares this module's GND pin as number
# "[1,15,38,39]" -- four pins, of which this file had three.
#
# Pin 39 is OPTIONAL. The module meets its thermal spec unsoldered; grounding it
# just runs cooler, and the "not recommended" note in the older WROOM-32
# datasheet is a translation error for "not necessary". Pin 15 is not optional,
# and it was floating too.
WROOM32E = {
    1: "GND", 2: "3V3", 3: "EN", 4: "IO36", 5: "IO39", 6: "IO34", 7: "IO35",
    8: "IO32", 9: "IO33", 10: "IO25", 11: "IO26", 12: "IO27", 13: "IO14",
    14: "IO12", 15: "GND", 16: "IO13", 17: "IO9", 18: "IO10", 19: "IO11",
    20: "IO6", 21: "IO7", 22: "IO8", 23: "IO15", 24: "IO2", 25: "IO0",
    26: "IO4", 27: "IO16", 28: "IO17", 29: "IO5", 30: "IO18", 31: "IO19",
    33: "IO21", 34: "IO3", 35: "IO1", 36: "IO22", 37: "IO23", 38: "GND",
    39: "GND",
}
# Pins 34/35 carry the UART0 console, which elec/main.py names by function.
ALIAS = {"RXD0": "IO3", "TXD0": "IO1"}


def fw_pins(text):
    """firmware constant -> GPIO number, read out of main.cpp."""
    out = {}
    for m in re.finditer(r"constexpr\s+\w+\s+(\w*_PIN)\s*=\s*(\d+)", text):
        out[m.group(1)] = int(m.group(2))
    return out


def fw_roles(text):
    """firmware constant -> set of roles, DERIVED from how the pin is used.

    Deliberately not a declared table: the whole value of this check is that
    the role comes from the calls, so moving a pin to a new peripheral without
    moving it to a legal GPIO is caught."""
    roles = {}
    calls = (("ledcAttach", "pwm_out"), ("ledcWrite", "pwm_out"),
             ("digitalWrite", "digital_out"), ("pinMode", None),
             ("analogReadMilliVolts", "analog_in"), ("analogRead", "analog_in"),
             ("digitalRead", "digital_in"))
    for fn, role in calls:
        for m in re.finditer(r"\b%s\s*\(\s*(\w*_PIN)\s*(?:,\s*(\w+))?" % fn, text):
            pin, arg2 = m.group(1), m.group(2)
            r = role
            if fn == "pinMode":
                if arg2 == "OUTPUT":
                    r = "digital_out"
                elif arg2 and arg2.startswith("INPUT"):
                    r = "digital_in"
            if r:
                roles.setdefault(pin, set()).add(r)
    return roles


def board_mcu(text):
    """Parse elec/main.py: net variable -> set of u_mcu[...] names it reaches,
    plus the module's physical-pin dict. Uses ast so the pin-NAME dict at the
    part declaration is never mistaken for a net connection."""
    tree = ast.parse(text)

    def mcu_keys(node):
        found = []
        for n in ast.walk(node):
            if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
                    and n.value.id == "u_mcu"
                    and isinstance(n.slice, ast.Constant)):
                found.append(n.slice.value)
        return found

    def part_terms(node):
        """(part_var, terminal) for every two-terminal subscript in an expression."""
        out = []
        for n in ast.walk(node):
            if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
                    and n.value.id != "u_mcu"
                    and isinstance(n.slice, ast.Constant)
                    and n.slice.value in (1, 2)):
                out.append((n.value.id, n.slice.value))
        return out

    nets = {}
    touches = {}        # net var -> {(part var, terminal)}
    for n in ast.walk(tree):
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
            keys = mcu_keys(n.value)
            if keys:
                nets.setdefault(n.target.id, set()).update(keys)
            touches.setdefault(n.target.id, set()).update(part_terms(n.value))
        # `vbat += r_d1[1]` style never touches u_mcu, so it is skipped.

    # ⚠ A SIGNAL MAY NOW REACH ITS PIN THROUGH A SERIES PART, and before finding
    # 30 none did. LEVEL used to land on IO14 directly; it now ends at R26 and the
    # protected side, LEVEL_IO, is what touches the pin. This gate reported
    # "net n_lvl reaches no u_mcu pin", which was literally true and the wrong
    # answer -- the firmware's LEVEL_PIN still has to be the pin the sensor reaches,
    # and a series resistor does not change which pin that is. So the walk follows
    # two-terminal parts.
    #
    # ⚠ BUT ONLY WHERE NEITHER END IS A RAIL, AND THAT RESTRICTION IS THE WHOLE
    # DIFFICULTY. Propagating through EVERY two-terminal part makes this gate useless
    # in one step: C22 is a two-terminal part from LEVEL_IO to GND, so GND would
    # inherit IO14, and GND touches a two-terminal part on nearly every net on the
    # board -- after which every net reaches every pin and the gate can no longer
    # disagree with anything. A SERIES element is one whose both ends are signals.
    # The pull-up string is excluded by the same rule at R23, which touches +3V3.
    RAILS = ("gnd", "v3v3", "vbat", "vgate", "vbat_raw", "vbat_lvl")
    rail_parts = set()
    for var, terms in touches.items():
        if var in RAILS:
            rail_parts.update(p for p, _ in terms)
    series = {}
    for var, terms in touches.items():
        for part, term in terms:
            if part not in rail_parts:
                series.setdefault(part, {})[term] = var
    # one hop at a time until nothing new is learned, so a chain of two series
    # elements still resolves and a cycle cannot spin.
    for _ in range(len(series) + 1):
        grew = False
        for part, ends in series.items():
            if len(ends) != 2:
                continue
            a, b = ends[1], ends[2]
            for src, dst in ((a, b), (b, a)):
                gained = nets.get(src, set()) - nets.get(dst, set())
                if gained:
                    nets.setdefault(dst, set()).update(gained)
                    grew = True
        if not grew:
            break

    # the physical pin dict: the 4th positional arg of gen.part(... "ESP32-...")
    pinmap = None
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and len(n.args) >= 4
                and isinstance(n.args[1], ast.Constant)
                and str(n.args[1].value).startswith("ESP32-WROOM")
                and isinstance(n.args[3], ast.Dict)):
            pinmap = {k.value: v.value for k, v in zip(n.args[3].keys,
                                                       n.args[3].values)}
    # net variable -> the schematic net NAME, for readable output
    names = {}
    for n in ast.walk(tree):
        if (isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name)
                and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Name)
                and n.value.func.id == "Net" and n.value.args
                and isinstance(n.value.args[0], ast.Constant)):
            names[n.targets[0].id] = n.value.args[0].value
    return nets, pinmap, names


# ⚠ THIS GATE'S SERIES WALK IS RUN AGAINST ITS OWN FAIL CASES ON EVERY RUN. The
# walk was added to stop a true report ("LEVEL reaches no pin") being the wrong answer,
# and a walk that is too GENEROUS is far worse than one that is too strict: it would
# quietly report every pin as correct. So three synthetic boards are checked here --
# one where the series part legitimately carries the signal through, one where the part
# is missing and the reach must NOT appear, and one where the intervening part is a
# capacitor to ground, which must NOT propagate or the rail short-circuits the gate.
_T_HEAD = 'u_mcu = gen.part("U2", "ESP32-WROOM-32E", "x", {1: "GND"}, "")\n'


def _selftest():
    ok = _T_HEAD + "n_lvl += r_ls[1]\nn_io += r_ls[2], u_mcu['IO14']\n"
    gone = _T_HEAD + "n_lvl += j[1]\nn_io += u_mcu['IO14']\n"
    rail = (_T_HEAD + "n_lvl += c[1]\ngnd += c[2]\n"
            "n_io += u_mcu['IO14']\nx += c2[1]\ngnd += c2[2]\n")
    cases = (("a series resistor carries the signal to the pin", ok, "n_lvl", True),
             ("no part between them, so there is no path", gone, "n_lvl", False),
             ("a capacitor to GND is not a series element", rail, "gnd", False))
    bad = 0
    print("=== the series walk against its own fail cases ===")
    for why, text, var, want in cases:
        got = "IO14" in board_mcu(text)[0].get(var, set())
        hit = (got == want)
        print("  %-4s %-52s %s reach -> %s"
              % ("ok" if hit else "FAIL", why, "expected" if want else "expected NO",
                 "reached" if got else "did not reach"))
        if not hit:
            bad += 1
            print("       *** the walk is %s: this gate cannot be trusted to "
                  "disagree with the board"
                  % ("too generous" if got else "too strict"))
    return bad


def doc_table(text):
    """{net_name: (gpio, module_pin)} from CIRCUIT.md section 3's pin table.

    The table is generated fact written out by hand, which is the same shape of
    liability as the BOM's volume and cut-list tables -- both of those had gone
    stale within a day of the edits that moved them. This one was written in the
    same session as the gate below and nothing checked it either, so it is a
    third source here rather than documentation nobody re-reads.
    """
    out = {}
    for m in re.finditer(r"^\|\s*`([A-Z0-9_]+)`\s*\|\s*(IO\d+)\s*\|\s*(\d+)\s*\|",
                         text, re.M):
        out[m.group(1)] = (m.group(2), int(m.group(3)))
    return out


def gpio(name):
    """'IO26' -> 26. Anything that is not a plain GPIO returns None."""
    m = re.fullmatch(r"IO(\d+)", name)
    return int(m.group(1)) if m else None


def main():
    fw_text = chr(10).join(f.read_text(encoding="utf-8") for f in FW)
    bd_text = BOARD.read_text(encoding="utf-8")
    pins = fw_pins(fw_text)
    roles = fw_roles(fw_text)
    nets, pinmap, names = board_mcu(bd_text)
    bad = 0

    if not pins or not nets or not pinmap:
        print("could not parse one side: %d fw pins, %d nets, pinmap=%s"
              % (len(pins), len(nets), bool(pinmap)))
        return 1

    print("=== firmware GPIO vs schematic net ===")
    for const, netvar in PAIRS:
        if const not in pins:
            print("  %-12s FAIL - no such constant in main.cpp" % const)
            bad += 1
            continue
        if netvar not in nets:
            print("  %-12s FAIL - net %s reaches no u_mcu pin in elec/main.py"
                  % (const, netvar))
            bad += 1
            continue
        want = pins[const]
        got = {gpio(k) for k in nets[netvar]}
        ok = got == {want}
        nm = names.get(netvar, netvar)
        print("  %-12s IO%-3d  net %-12s %-8s %s"
              % (const, want, nm,
                 ",".join(sorted(nets[netvar])), "ok" if ok else "*** FAIL ***"))
        bad += not ok

    # every firmware pin must be accounted for by the table above
    print("\n=== coverage ===")
    listed = {c for c, _ in PAIRS}
    extra = sorted(set(pins) - listed)
    print("  %d firmware pin constant(s), %d in the table%s"
          % (len(pins), len(listed & set(pins)),
             "" if not extra else "  *** UNCHECKED: %s ***" % ", ".join(extra)))
    bad += len(extra)

    # no two signals on one GPIO
    used = {}
    for c in listed & set(pins):
        used.setdefault(pins[c], []).append(c)
    clash = {g: cs for g, cs in used.items() if len(cs) > 1}
    print("  distinct GPIOs : %d for %d signals   %s"
          % (len(used), len(listed & set(pins)),
             "ok" if not clash else "*** COLLISION %s ***" % clash))
    bad += len(clash)

    print("\n=== ESP32 rules, against the role the firmware actually uses ===")
    for const in sorted(listed & set(pins)):
        g, rs = pins[const], roles.get(const, set())
        if not rs:
            print("  %-12s IO%-3d  FAIL - never used; role cannot be derived"
                  % (const, g))
            bad += 1
            continue
        problems = []
        if "analog_in" in rs and g not in ADC1:
            problems.append("analog on ADC%s - unusable with WiFi up"
                            % ("2" if g in ADC2 else "?"))
        if ("digital_out" in rs or "pwm_out" in rs) and g in INPUT_ONLY:
            problems.append("output on an input-only pin")
        if ("digital_out" in rs or "pwm_out" in rs) and g in STRAPPING:
            problems.append("output on a strapping pin - fights boot mode")
        if g in FLASH_BUS:
            problems.append("on the module's internal flash bus - not led out")
        print("  %-12s IO%-3d  %-22s %s"
              % (const, g, ",".join(sorted(rs)),
                 "ok" if not problems else "*** " + "; ".join(problems) + " ***"))
        bad += len(problems)

    print("\n=== CIRCUIT.md section 3 pin table vs both sources ===")
    doc = doc_table(CIRCUIT.read_text(encoding="utf-8"))
    if not doc:
        print("  could not read the pin table out of CIRCUIT.md")
        bad += 1
    else:
        # module pin number -> the name elec/main.py gives it, inverted
        num_of = {v: k for k, v in pinmap.items()}
        for const, netvar in PAIRS:
            nm = names.get(netvar, netvar)
            if nm not in doc:
                print("  %-12s *** %s is not in the CIRCUIT.md table ***"
                      % (const, nm))
                bad += 1
                continue
            d_io, d_pin = doc[nm]
            want_io = "IO%d" % pins[const]
            want_pin = num_of.get(want_io)
            ok = d_io == want_io and d_pin == want_pin
            print("  %-12s doc says %-5s pin %-3s   sources say %-5s pin %-3s  %s"
                  % (nm, d_io, d_pin, want_io, want_pin,
                     "ok" if ok else "*** FAIL ***"))
            bad += not ok
        extra_doc = sorted(set(doc) - {names.get(nv, nv) for _, nv in PAIRS})
        if extra_doc:
            print("  *** table lists nets that are not in the pin map: %s ***"
                  % ", ".join(extra_doc))
            bad += len(extra_doc)

    print("\n=== module footprint pin names vs WROOM-32E pinout ===")
    wrong = []
    for num, nm in sorted(pinmap.items()):
        want = WROOM32E.get(num)
        have = ALIAS.get(nm, nm)
        if want is None:
            wrong.append("pin %s is NC or unknown on this module (named %s)"
                         % (num, nm))
        elif have != want:
            wrong.append("pin %s named %s, datasheet says %s" % (num, nm, want))
    print("  %d pin(s) declared, %d checked against the datasheet   %s"
          % (len(pinmap), len(pinmap),
             "ok" if not wrong else "*** %d WRONG ***" % len(wrong)))
    for w in wrong:
        print("     %s" % w)
    bad += len(wrong)

    # and the series walk that produced all of the above is itself exercised,
    # every run -- a walk that is too GENEROUS would report every pin as correct.
    print("")
    bad += _selftest()

    print("\n%s" % ("firmware and board agree, and the pinout is legal"
                    if not bad else "*** %d PIN-MAP FAILURE(S) ***" % bad))
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
