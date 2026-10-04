#!/usr/bin/env python3
"""Every named pin on the board, against the datasheet it came from.

WHY THIS EXISTS. `elec/CIRCUIT.md`'s part-by-part audit found nine defects, and
its own conclusion was the reason for this file:

    nothing in the pipeline checks a pin map or a voltage. ERC checks that pins
    are connected, DRC checks that copper matches the netlist, and the netlist
    is a copy of the pin map it is supposed to be verifying.

The worst of the nine was a gate driver wrong on four of five pins, which put a
GPIO on the supply pin and a 4 A driver output onto the 3.3 V rail. Every stage
downstream agreed with it, because every stage downstream was derived from it.
So the comparison has to be against something OUTSIDE the toolchain: a table
transcribed by hand from a named datasheet revision, with the page it is on.

WHAT IT CHECKS, in three parts:

  1. PIN MAPS. Each IC's `gen.part` pin dict in elec/main.py, read with `ast`
     rather than by importing, against EXPECTED below. Transcription errors in
     EXPECTED are the obvious weakness, which is why every entry carries its
     document number and page -- the citation is the thing a reviewer checks.
  2. RAILS. That every part's supply pin is fed by a rail inside the part's own
     operating window. This is finding 2: the drivers were 4.5-18 V parts with
     3.3 V as the only rail on the board, and both halves of that were written
     down, two sections apart, in the same file.
  3. NETLESS NUMBERED PADS on the routed board. This is finding 10: TO-263-2 is
     a three-pad land declared with two pins, so pad 3 carried no net at all. A
     pad with no net is not an unconnected net, so DRC passed and the
     0-unconnected gate passed. Only counting pads finds it.

Exits non-zero on failure, like every other gate in this project.
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAIN = os.path.join(ROOT, "elec", "main.py")

# -- 1. THE PIN MAPS, each transcribed from the document named beside it ------
# The footprint is part of the key on purpose: a pinout belongs to a part number
# IN A PACKAGE, and the same die in another package is a different table.
EXPECTED = {
    ("LMR14020SDDA", "wbp:SOIC-8-1EP-FABDRILL"): (
        "TI SNVSAA5B, Pin Functions (HSOIC-8 with PowerPAD)",
        {1: "BOOT", 2: "VIN", 3: "EN", 4: "RT", 5: "FB", 6: "SS", 7: "GND",
         8: "SW", 9: "EP"}),
    ("UCC27517", "Package_TO_SOT_SMD:SOT-23-5"): (
        "TI SLUSAY4C page 2, DBV (SOT-23-5) package",
        {1: "VDD", 2: "GND", 3: "IN+", 4: "IN-", 5: "OUT"}),
    ("MMBT3904", "Package_TO_SOT_SMD:SOT-23"): (
        "SOT-23 NPN standard pinout (1 base, 2 emitter, 3 collector)",
        {1: "B", 2: "E", 3: "C"}),
}

# Pin-ORDER tables for parts declared as a list, where position is the pin
# number. These are PACKAGE conventions, and the two diode orders on this board
# genuinely differ -- which is exactly why they are written down here.
EXPECTED_ORDER = {
    # Pad 1 is the cathode, the banded end, on KiCad's chip-diode lands.
    "Diode_SMD:D_SOD-123": ("KiCad land, pad 1 = cathode band", ["K", "A"]),
    "Diode_SMD:D_SMB": ("KiCad land, pad 1 = cathode band", ["K", "A"]),
}

# -- 2. THE RAILS ------------------------------------------------------------
# (part value, the pin that is its supply) -> (min V, max V, citation)
SUPPLY_WINDOW = {
    ("UCC27517", "VDD"): (4.5, 18.0, "TI SLUSAY4C, Recommended Operating "
                                     "Conditions: VDD 4.5 V to 18 V"),
    ("LMR14020SDDA", "VIN"): (4.5, 40.0, "TI SNVSAA5B, VIN 4.5 V to 40 V"),
}


# A rail can be inside every part's window and still be the WRONG VOLTAGE.
# Finding 7 was exactly that: 100k / 31k6 set 3.12 V, which no part on the board
# minds, and which is also the ADC reference for the battery gauge and the
# joystick -- so a 5.4% error there is a 5.4% error in every reading the machine
# takes. SUPPLY_WINDOW cannot see it, because 3.12 V is comfortably inside
# 3.0-3.6. So the nominal is declared too, with the tolerance that matters.
# {net: (nominal V, fractional tolerance, why that tolerance)}
RAIL_NOMINAL = {
    "+3V3": (3.3, 0.02,
             "this rail is the ADC reference, so its error is a scale error on "
             "the battery gauge and the joystick; 2% is about a tenth of a volt "
             "at the pack, which is the resolution the duty compensation needs"),
    "VGATE": (10.0, 0.10,
              "a Zener shunt, so it moves with load and with the pack: 10% is "
              "the part tolerance, and the window check above is what actually "
              "protects the drivers"),
}

# -- 3. PADS THAT ARE MEANT TO CARRY NO NET ----------------------------------
# A module brings out more pins than any one design uses, so "no net" is normal
# for some of them and a defect for others. The difference cannot be guessed, so
# it is declared: {ref: {pin: why}}, one line per pin, in this project's habit
# of naming and justifying an accepted finding rather than lumping it. A blanket
# "skip U2" would have hidden pin 15 and pin 39, which is how the module's
# entire thermal ground came to be floating.
_ESP_FLASH = ("wired to the module's own SPI flash inside the can -- Espressif's "
              "guidance is to leave it unconnected, not to use it")
_ESP_SPARE = "spare GPIO, no function in this design"
DECLARED_NETLESS = {
    "U2": dict(
        [(4, "SENSOR_VP / IO36, input-only, " + _ESP_SPARE),
         (5, "SENSOR_VN / IO39, input-only, " + _ESP_SPARE),
         (8, "IO32, " + _ESP_SPARE),
         (9, "IO33, " + _ESP_SPARE),
         (14, "IO12, a strapping pin (flash voltage) -- deliberately left alone"),
         (16, "IO13, " + _ESP_SPARE)]
        + [(n, "flash pin, " + _ESP_FLASH) for n in range(17, 23)]
        + [(23, "IO15, a strapping pin -- deliberately left alone"),
           (24, "IO2, a strapping pin -- deliberately left alone")]
        + [(n, "IO%d, %s" % (io, _ESP_SPARE)) for n, io in
           ((26, 4), (27, 16), (28, 17), (29, 5), (30, 18), (31, 19),
            (33, 21), (36, 22), (37, 23))]
        + [(32, "NC on the module -- there is no pin behind this pad")]),
}


def _ohms(s):
    """'29k4' -> 29400.0, '100k' -> 100000.0, '10R' -> 10.0."""
    m = re.match(r"^(\d+)([kKRM]?)(\d*)$", str(s).strip())
    if not m:
        return None
    whole, suf, frac = m.groups()
    mult = {"k": 1e3, "K": 1e3, "M": 1e6, "R": 1.0, "": 1.0}[suf]
    text = whole + ("." + frac if frac else "")
    return float(text) * mult


def _rail_volts(src):
    """VGATE, +3V3 and VBAT in volts, as elec/main.py's own constants state them.

    Derived rather than typed here, so a change to the divider or the Zener
    moves this gate's idea of the rail with it. The 3V3 arithmetic is
    deliberately redone from BUCK_VFB and the two resistor VALUES rather than
    read from FB_VOUT: finding 7 was a divider whose comment and whose parts
    disagreed, and reading the computed answer would check only itself.
    """
    val = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            try:
                val[node.targets[0].id] = ast.literal_eval(node.value)
            except Exception:
                pass
    out = {}
    if "VGATE_V" in val:
        out["VGATE"] = float(val["VGATE_V"])
    top, bot = _ohms(val.get("FB_TOP", "")), _ohms(val.get("FB_BOT", ""))
    if "BUCK_VFB" in val and top and bot:
        out["+3V3"] = float(val["BUCK_VFB"]) * (1.0 + top / bot)
    if "VBAT_MIN" in val and "VBAT_MAX" in val:
        out["VBAT"] = (float(val["VBAT_MIN"]), float(val["VBAT_MAX"]))
    return out


def _int(s):
    """A pad number as an int, or None -- pads may be named ("A1", "MP")."""
    try:
        return int(str(s).strip())
    except ValueError:
        return None


def _parts(src):
    """Every gen.part call: (value, footprint, pin-spec node, line)."""
    out = []
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "part" and len(node.args) >= 4):
            continue
        try:
            fp = ast.literal_eval(node.args[2])
        except Exception:
            continue
        try:
            value = ast.literal_eval(node.args[1])
        except Exception:
            value = ast.unparse(node.args[1])   # a constant like PUMP_FET_VALUE
        out.append((value, fp, node.args[3], node.lineno))
    return out


def _supply_nets(src):
    """{(part value, pin name): net name} for every `net += part["PIN"]`.

    Read from the source, so the citation and the thing it cites sit in one
    file. Covers the two shapes elec/main.py uses: `vbat += u_bk["VIN"], ...`
    and `n_vg += u["VDD"], ...` inside the per-pump loop.
    """
    tree = ast.parse(src)
    owner, rail = {}, {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)):
            continue
        name, call = node.targets[0].id, node.value
        if isinstance(call.func, ast.Attribute) and call.func.attr == "part" \
                and len(call.args) >= 2:
            try:
                owner[name] = ast.literal_eval(call.args[1])
            except Exception:
                pass
        elif getattr(call.func, "id", "") == "Net" and call.args:
            try:
                rail[name] = ast.literal_eval(call.args[0])
            except Exception:
                pass
    found = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.AugAssign)
                and isinstance(node.target, ast.Name)
                and isinstance(node.op, ast.Add)):
            continue
        net = rail.get(node.target.id)
        if net is None:
            continue
        items = (node.value.elts if isinstance(node.value, ast.Tuple)
                 else [node.value])
        for it in items:
            if not (isinstance(it, ast.Subscript)
                    and isinstance(it.value, ast.Name)):
                continue
            try:
                pin = ast.literal_eval(it.slice)
            except Exception:
                continue
            value = owner.get(it.value.id)
            if value and isinstance(pin, str):
                found[(value, pin)] = net
    return found


def _netless_pads(text):
    """(ref, pad number) for every NUMBERED pad in a .kicad_pcb with no net.

    Parsed rather than loaded through pcbnew, so this gate runs under plain
    python like the rest of tools/ and not only under KiCad's interpreter.
    Unnumbered pads ("" or "~") are mechanical -- mounting tabs, thermal relief
    -- and have nothing to connect to.

    The net form is `(net "GND")` in KiCad 10 and `(net 3 "GND")` in 9 and
    earlier, so both are accepted. Matching only the older one made this gate
    report 199 netless pads on a board with exactly two, which is the failure
    mode worth guarding: a gate that fires on everything gets switched off.
    """
    out = []

    def _block(s, start):
        depth, j = 0, start
        while j < len(s):
            if s[j] == "(":
                depth += 1
            elif s[j] == ")":
                depth -= 1
                if depth == 0:
                    return s[start:j + 1]
            j += 1
        return s[start:]

    for m in re.finditer(r"\(footprint\s", text):
        blk = _block(text, m.start())
        rm = re.search(r'\(property "Reference" "([^"]+)"', blk)
        ref = rm.group(1) if rm else "?"
        for pm in re.finditer(r'\(pad "([^"]*)"', blk):
            num = pm.group(1).strip()
            if not num or num == "~":
                continue
            if not re.search(r'\(net\s+(?:\d+\s+)?"', _block(blk, pm.start())):
                out.append((ref, num))
    return out


def main():
    src = open(MAIN, encoding="utf-8").read()
    bad, checked = [], 0

    # -- 1. pin maps ---------------------------------------------------------
    print("=== pin maps, against the datasheet each came from ===")
    seen = set()
    for value, fp, spec, line in _parts(src):
        if (value, fp) in EXPECTED:
            cite, want = EXPECTED[(value, fp)]
            try:
                got = ast.literal_eval(spec)
            except Exception:
                bad.append("%s: the pin map at elec/main.py:%d is not a "
                           "literal, so it cannot be checked" % (value, line))
                continue
            seen.add((value, fp))
            checked += 1
            if got == want:
                print("  %-13s %d pin(s) agree with %s"
                      % (value, len(want), cite))
            for pin in sorted(set(want) | set(got), key=str):
                g, w = got.get(pin), want.get(pin)
                if g != w:
                    bad.append("%s pin %s is %r in elec/main.py:%d but %r per "
                               "%s" % (value, pin, g, line, w, cite))
        elif fp in EXPECTED_ORDER and isinstance(spec, ast.List):
            cite, want = EXPECTED_ORDER[fp]
            got = ast.literal_eval(spec)
            seen.add(fp)
            checked += 1
            if got != want:
                bad.append("%s in %s is declared %r but the pad order is %r "
                           "per %s (elec/main.py:%d)"
                           % (value, fp.split(":")[-1], got, want, cite, line))
    for key in EXPECTED:
        if key not in seen:
            bad.append("%s (%s) has a datasheet table here but is not on the "
                       "board -- the table is stale, or the part was dropped "
                       "and nothing noticed" % key)

    # -- 2. rails ------------------------------------------------------------
    print("\n=== supply pins, against each part's operating window ===")
    volts, nets = _rail_volts(src), _supply_nets(src)
    for (value, pin) in sorted(SUPPLY_WINDOW):
        vmin, vmax, cite = SUPPLY_WINDOW[(value, pin)]
        net = nets.get((value, pin))
        if net is None:
            bad.append("%s pin %s is on no net in elec/main.py -- a supply pin "
                       "that is not driven is finding 1 again" % (value, pin))
            continue
        v = volts.get(net)
        if v is None:
            bad.append("%s %s is fed by %s, whose voltage this gate cannot "
                       "derive from elec/main.py -- teach _rail_volts about it"
                       % (value, pin, net))
            continue
        lo, hi = v if isinstance(v, tuple) else (v, v)
        checked += 1
        shown = "%.2f" % lo if lo == hi else "%.1f-%.1f" % (lo, hi)
        if lo < vmin or hi > vmax:
            bad.append("%s %s is fed by %s at %s V, OUTSIDE %.1f-%.1f V (%s)"
                       % (value, pin, net, shown, vmin, vmax, cite))
        else:
            print("  %-13s %-4s <- %-6s %9s V   inside %.1f-%.1f V"
                  % (value, pin, net, shown, vmin, vmax))

    print("\n=== each rail against the voltage it is supposed to be ===")
    for net in sorted(RAIL_NOMINAL):
        want, tol, why = RAIL_NOMINAL[net]
        got = volts.get(net)
        if got is None:
            bad.append("%s has a declared nominal of %.2f V but this gate "
                       "cannot derive it from elec/main.py -- teach _rail_volts "
                       "about it" % (net, want))
            continue
        if isinstance(got, tuple):
            continue              # a range, not a set point: VBAT is the pack
        checked += 1
        err = (got - want) / want
        if abs(err) > tol:
            bad.append("%s derives to %.3f V from the parts in elec/main.py, "
                       "%+.1f%% off its %.2f V nominal (tolerance %.0f%%): %s"
                       % (net, got, err * 100.0, want, tol * 100.0, why))
        else:
            print("  %-6s %.3f V from the parts, %+.1f%% of %.2f V nominal"
                  % (net, got, err * 100.0, want))

    # -- 4. numbered pads with no net, on the board that was actually routed --
    print("\n=== every numbered pad on the routed board ===")
    pcb = os.path.join(ROOT, "elec", "out", "main.kicad_pcb")
    if not os.path.exists(pcb):
        print("  NOT CHECKED: no routed board at elec/out/main.kicad_pcb --"
              " run cadkit/pcbflow/finish.py first")
    else:
        netless = _netless_pads(open(pcb, encoding="utf-8").read())
        checked += 1
        declared, seen_dec = 0, set()
        for ref, pin in netless:
            why = DECLARED_NETLESS.get(ref, {}).get(_int(pin))
            if why is not None:
                declared += 1
                seen_dec.add((ref, _int(pin)))
                continue
            bad.append("%s pad %s is on the board with NO NET. A pad with no "
                       "net is not an unconnected net, so DRC and the "
                       "0-unconnected gate both pass it. If it is meant to "
                       "float, say so in DECLARED_NETLESS with the reason"
                       % (ref, pin))
        # A declaration that no longer matches anything is a stale excuse, and a
        # stale excuse stands ready to hide the next real one.
        for ref, pins in sorted(DECLARED_NETLESS.items()):
            for pin, why in sorted(pins.items()):
                if (ref, pin) not in seen_dec:
                    bad.append("%s pad %d is DECLARED netless (%s) but now "
                               "carries a net, or is not on the board at all "
                               "-- the declaration is stale" % (ref, pin, why))
        n_bad = sum(1 for r, p in netless
                    if DECLARED_NETLESS.get(r, {}).get(_int(p)) is None)
        print("  %d numbered pad(s) carry no net; %d of them declared, %d not"
              % (len(netless), declared, n_bad))

    print("\n%d check(s)" % checked)
    if bad:
        print("\n*** %d PROBLEM(S) ***" % len(bad))
        for b in bad:
            print("   " + b)
        return 1
    print("pin maps, rails and pads all agree with their datasheets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
