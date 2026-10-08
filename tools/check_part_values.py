# -*- coding: utf-8 -*-
"""Every component VALUE written in prose or copied into firmware must be the
value the netlist gives that part.

    py -3.12 tools/check_part_values.py        # exit 0 = every claim holds

WHY THIS EXISTS, and it was asked for by name. firmware/src/main.cpp says, at
RDIV_BOT_K:

    "!! THIS CONSTANT IS A COPY OF A BOARD VALUE AND NOTHING COMPARES THEM.
     tools/check_pin_map.py ties this firmware to the schematic, but only by PIN
     NUMBER -- it never reads a component value, so no gate in the repo covers
     this line."

That was true, and the hole had already been fallen into twice. R21 was 18k and
finding 33 made it 10k; the firmware's copy stayed 18k long enough to be measured,
and a stale divider scale does not fail loudly -- it reads a 15 V pack as 8.94 V,
calls that implausible, falls back to the fresh-pack assumption and puts the WHOLE
PACK across a 12 V pump. The second one was R23: four files said "a 10k pull-up
to 3V3" on a part that is 100k and does not touch the net they said it pulled up,
and two of them drew a safety conclusion from it.

So this gate reads the netlist and checks three different kinds of claim against
it. No value is retyped here.

  1. FIRMWARE CONSTANTS THAT ARE COPIES OF BOARD FACTS (the named gap above).
     A table of C++ constant -> what it is a copy of. These are not comments: get
     one wrong and the firmware computes wrong numbers on correct hardware.
  2. VALUES CLAIMED IN PROSE, anywhere in the gated files. "R26 (100k)" has to be
     100k. Comments are what a person reads with a meter in their hand at bring-up.
  3. SLASH PAIRS MUST SHARE A NET. Prose names an RC filter or a divider as
     "R26/C22", and a pair that shares no net is not a filter -- it is two
     unrelated parts and a sentence that has rotted. This is how C19, a 3V3
     decoupling cap, was found standing in CIRCUIT.md for C22, the part that
     actually filters LEVEL_IO -- a 300x error in the corner frequency, in the
     entry a person reads to understand the level sensor.

WHAT IS DELIBERATELY NOT GATED, and why it is not an oversight. WORK_V2_PUNCHLIST.md
and elec/quality_signoff.py are HISTORIES: their job is to record the claim that was
retracted, so a value-claim gate over them would fail on the very sentences that
exist to say "this was wrong". They are excluded by name, not by accident, and the
same need inside a live document is served by QUOTING the retracted value -- a value
inside double quotes is read here as a quotation and reported in the excused count,
never silently dropped.
"""
import io
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
NET = ROOT / "elec" / "out" / "main.net"
BOARD = ROOT / "elec" / "main.py"
FW_MAIN = ROOT / "firmware" / "src" / "main.cpp"

# The files whose component claims are statements about the board as built. Prose
# in these is read by somebody holding a meter, or compiled.
GATED = ("firmware/src/pins.h", "firmware/src/pins.cpp", "firmware/src/main.cpp",
         "elec/CIRCUIT.md", "BRINGUP.md", "bom_consolidated.md", "DESIGN_V2.md")

# Histories. See the docstring: excluded by name.
NOT_GATED = ("WORK_V2_PUNCHLIST.md", "elec/quality_signoff.py")

fails = []
notes = []


def fail(msg):
    fails.append(msg)


# ---------------------------------------------------------------------------
# The netlist, which is the only authority for a part's value.
# ---------------------------------------------------------------------------
def load_netlist():
    if not NET.exists():
        # NOT a skip. A gate that excuses itself when its source is absent is
        # worse than no gate: it prints as a pass (finding 47's ok=None defect).
        sys.stderr.write("FATAL: %s is missing -- run py -3.12 elec/main.py\n" % NET)
        sys.exit(2)
    s = io.open(NET, encoding="utf-8").read()
    val = dict(re.findall(r'\(ref "([^"]+)"\)\s*\n?\s*\(value "([^"]*)"\)', s))
    on = {}
    for blk in re.split(r"\n    \(net\n", s)[1:]:
        m = re.search(r'\(name "([^"]*)"\)', blk)
        if not m:
            continue
        name = m.group(1)
        for ref, _pin in re.findall(r'\(ref "([^"]+)"\)\s*\n\s*\(pin "([^"]+)"\)', blk):
            on.setdefault(ref, set()).add(name)
    if not val or not on:
        sys.stderr.write("FATAL: parsed 0 parts or 0 nets out of %s\n" % NET)
        sys.exit(2)
    return val, on


MULT = {"r": 1.0, "k": 1e3, "m": 1e6,
        "n": 1e-9, "u": 1e-6, "p": 1e-12}


def quantity(tok):
    """'100k' -> 1e5, '4u7' -> 4.7e-6, '10R' -> 10.0, '100 nF' -> 1e-7.

    Returns None for anything that is not a value, so the caller can ignore it
    rather than guess.
    """
    t = tok.strip().split("/")[0]
    # "100 kOhm" first, so the multiplier survives: otherwise the ohm sign becomes
    # an R and "100 kR" parses as nothing at all -- which is how a claim goes
    # UNCHECKED rather than wrong. That silence is what `unparsed` below counts.
    t = re.sub(r"[kK]\s*[Ωω]", "k", t)
    t = re.sub(r"[kK]\s*[Oo]hms?", "k", t)
    t = re.sub(r"[mM]\s*[Ωω]", "M", t)
    t = t.replace("Ω", "R").replace("ω", "R").replace("µ", "u")
    t = t.replace("ohm", "R").replace("Ohm", "R").replace("OHM", "R")
    t = re.sub(r"[Ff]$", "", t.strip())      # nF -> n, uF -> u
    t = t.replace(" ", "")
    m = re.match(r"^(\d+)([rRkKmMnNuUpP])(\d*)$", t)
    if m:
        whole, mult, frac = m.groups()
        num = float(whole + ("." + frac if frac else ""))
        return num * MULT[mult.lower()]
    m = re.match(r"^(\d+(?:\.\d+)?)([rRkKmMnNuUpP])$", t)
    if m:
        return float(m.group(1)) * MULT[m.group(2).lower()]
    return None


def same(a, b):
    """Equal to within float noise. Values are decade-separated; no tolerance."""
    if a is None or b is None:
        return False
    return abs(a - b) <= 1e-9 * max(abs(a), abs(b), 1e-12)


def show(q):
    for unit, scale in (("M", 1e6), ("k", 1e3), ("", 1.0),
                        ("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if q >= scale or scale == 1e-12:
            return "%g%s" % (q / scale, unit)
    return "%g" % q


VALUES, ONNET = load_netlist()


def const(path, name):
    """One `constexpr <type> NAME = <number>` out of a C++ file."""
    s = io.open(path, encoding="utf-8").read()
    m = re.search(r"constexpr\s+\w+\s+%s\s*=\s*([0-9.]+)f?\s*;" % re.escape(name), s)
    if not m:
        fail("firmware: no constexpr %s in %s" % (name, path.name))
        return None
    return float(m.group(1))


def board_const(name):
    s = io.open(BOARD, encoding="utf-8").read()
    m = re.search(r"^%s\s*=\s*([0-9.]+)" % re.escape(name), s, re.M)
    if not m:
        fail("elec/main.py: no %s" % name)
        return None
    return float(m.group(1))


# ---------------------------------------------------------------------------
# 1. Firmware constants that are copies of board facts.
# ---------------------------------------------------------------------------
print("1. firmware constants that copy a board value")

PAIRS = (("RDIV_TOP_K", "R20", 1e3),
         ("RDIV_BOT_K", "R21", 1e3))
for name, ref, unit in PAIRS:
    got = const(FW_MAIN, name)
    want = quantity(VALUES.get(ref, ""))
    if got is None or want is None:
        fail("%s / %s: cannot compare (%r vs %r)" % (name, ref, got, VALUES.get(ref)))
        continue
    if not same(got * unit, want):
        fail("%s = %g (i.e. %s) but %s is %s in the netlist -- the firmware's "
             "VBAT_SCALE is wrong, so every pack reading and the duty cap with it"
             % (name, got, show(got * unit), ref, VALUES[ref]))
    else:
        print("   %-12s %-8s == %s %s" % (name, show(got * unit), ref, VALUES[ref]))

VBAT_MAX = board_const("VBAT_MAX")
VBAT_MIN = board_const("VBAT_MIN")
assumed = const(FW_MAIN, "VBAT_ASSUMED")
plaus_hi = const(FW_MAIN, "VBAT_PLAUS_HI")
plaus_lo = const(FW_MAIN, "VBAT_PLAUS_LO")

if None not in (VBAT_MAX, assumed):
    # The fallback is used when the sense path reads implausibly, and it sets the
    # duty cap. Cap = PWM_MAX * 12 / assumed, so an assumption BELOW the real pack
    # raises the cap and overdrives the pump -- the exact failure the cap exists to
    # prevent. The safe assumption is therefore the HIGHEST pack the board admits.
    if assumed < VBAT_MAX - 1e-9:
        fail("VBAT_ASSUMED = %.1f V is BELOW elec/main.py's VBAT_MAX = %.1f V. The "
             "fallback cap would be %d, and a real %.1f V pack would see %.2f V "
             "across a 12 V pump. The sense-failure assumption must be the top of "
             "the range, not the middle of it"
             % (assumed, VBAT_MAX, int(255 * 12.0 / assumed + 0.5), VBAT_MAX,
                int(255 * 12.0 / assumed + 0.5) / 255.0 * VBAT_MAX))
    else:
        print("   VBAT_ASSUMED %.1f V >= VBAT_MAX %.1f V  (fallback cannot overdrive)"
              % (assumed, VBAT_MAX))

if None not in (VBAT_MAX, plaus_hi):
    if plaus_hi <= VBAT_MAX:
        fail("VBAT_PLAUS_HI = %.1f V is not above VBAT_MAX = %.1f V: a fresh pack "
             "would be called implausible and the board would run on the fallback "
             "for ever" % (plaus_hi, VBAT_MAX))
    else:
        print("   VBAT_PLAUS_HI %.1f V > VBAT_MAX %.1f V  (margin %.1f V)"
              % (plaus_hi, VBAT_MAX, plaus_hi - VBAT_MAX))

if None not in (VBAT_MIN, plaus_lo):
    if plaus_lo >= VBAT_MIN:
        fail("VBAT_PLAUS_LO = %.1f V is not below VBAT_MIN = %.1f V: a flat pack "
             "would read implausible instead of flat" % (plaus_lo, VBAT_MIN))
    else:
        print("   VBAT_PLAUS_LO %.1f V < VBAT_MIN %.1f V  (margin %.1f V)"
              % (plaus_lo, VBAT_MIN, VBAT_MIN - plaus_lo))

# ---------------------------------------------------------------------------
# 2. Values claimed in prose.
# ---------------------------------------------------------------------------
print("2. component values claimed in prose")

# A ref, then within a few characters a value token. The window is deliberately
# short: "R26 (100k)" and "R23 is 100k" are claims about R26 and R23; a value two
# clauses away is about something else.
CLAIM = re.compile(
    r"\b([RC]\d{1,2})\b([^.\n]{0,12}?)"
    r"(?<![\w.])(\d{1,4}\s?(?:[kKmMnNuUpP]\d*|[kK]Ω|R|Ω|[numkp]?[FfR])"
    r"|\d{1,4}\s?(?:nF|uF|pF|µF|kΩ|k|R))(?![\w])")

QUOTED = re.compile(r"[\"“][^\"”\n]*[\"”]")
# (the pair rule became the chain rule above; the regex it used is gone with it)

seen = quoted = summed = 0
unparsed = []
per_file = []
for rel in GATED:
    path = ROOT / rel
    if not path.exists():
        fail("gated file is missing: %s" % rel)
        continue
    text = io.open(path, encoding="utf-8").read()
    before = seen
    for lineno, line in enumerate(text.splitlines(), 1):
        spans = [m.span() for m in QUOTED.finditer(line)]
        for m in CLAIM.finditer(line):
            ref, _gap, tok = m.groups()
            if ref not in VALUES:
                continue
            claimed = quantity(tok)
            if claimed is None:
                # Not thrown away quietly: an unparseable token is a claim this
                # gate did not read, and a gate whose coverage silently falls to
                # zero still prints OK.
                unparsed.append("%s:%d  %s %r" % (rel, lineno, ref, tok))
                continue
            seen += 1
            want = quantity(VALUES[ref])
            if same(claimed, want):
                continue
            # A value inside quotation marks is somebody else's sentence being
            # reported, not a claim about the board.
            at = m.start(3)
            if any(a <= at < b for a, b in spans):
                quoted += 1
                notes.append("%s:%d quotes %s as %s (it is %s) -- read as a "
                             "quotation" % (rel, lineno, ref, tok, VALUES[ref]))
                continue
            # "C4 + C19 = 44 uF" and "+3V3 -> R23 -> R27 -> R28 -> LEVEL, 300k" are
            # claims about the CHAIN, not about the part the window happened to
            # reach first. Sum every part of the same class named on the line and
            # check that instead -- which VERIFIES those two sentences rather than
            # excusing them. Reported in the `summed` count either way.
            chain = []
            for other in dict.fromkeys(re.findall(r"\b([RC]\d{1,2})\b", line)):
                if other[0] == ref[0] and other in VALUES:
                    chain.append(other)
            if len(chain) > 1:
                tot = sum(quantity(VALUES[r]) or 0 for r in chain)
                if same(claimed, tot):
                    summed += 1
                    continue
            fail("%s:%d claims %s is %s; the netlist says %s\n        %s"
                 % (rel, lineno, ref, tok, VALUES[ref], line.strip()[:100]))

    per_file.append("%s %d" % (rel, seen - before))

print("   %d value claims read, %d quotations excused, %d checked as pair sums"
      % (seen, quoted, summed))
print("   coverage: %s" % ", ".join(per_file))
for n in notes:
    print("   note: %s" % n)
if unparsed:
    # A value token this gate cannot parse is not a pass. It is a hole, and it is
    # one line of normaliser away from being closed.
    fail("%d value token(s) matched a part but could not be parsed, so they were "
         "NOT checked:\n        %s" % (len(unparsed), "\n        ".join(unparsed)))

# ---------------------------------------------------------------------------
# 3. Slash pairs must share a net.
# ---------------------------------------------------------------------------
print("3. the duty cap BRINGUP.md tells an operator to expect")

# ⚠ THESE ARE THE NUMBERS A PERSON CHECKS THE PUMP PROTECTION BY, at the one stage
# where it is still free to check -- stage 2, before a pump is wired. They are
# derived from three constants in two files (PWM_MAX and PUMP_V_NOM in the firmware,
# VBAT_MIN/MAX on the board), so written down they are exactly the kind of figure
# that goes stale the next time one of them moves -- which is how VBAT_ASSUMED came
# to sit below VBAT_MAX in the first place. Read back and recomputed here.
CAPROW = re.compile(r"`cap=`[^|\n]*?255[^|\n]*?\|?([^|\n]*)")
CAPPAIR = re.compile(r"(\d+)\s+at\s+(\d+(?:\.\d+)?)\s*V")

def _pwm_max():
    """PWM_MAX is DERIVED in the firmware -- (1 << PWM_RES) - 1, with PWM_RES in
    pins.h, not main.cpp. Derive it the same way rather than writing 255 down here:
    the whole subject of this gate is copies of other files' numbers."""
    s = (ROOT / "firmware" / "src" / "pins.h").read_text(encoding="utf-8")
    m = re.search(r"constexpr\s+int\s+PWM_RES\s*=\s*(\d+)", s)
    if not m:
        fail("firmware: no constexpr PWM_RES in pins.h, so PWM_MAX cannot be derived")
        return None
    return (1 << int(m.group(1))) - 1


pwm_max = _pwm_max()
v_nom = const(FW_MAIN, "PUMP_V_NOM")

bring = (ROOT / "BRINGUP.md")
pairs = []
if bring.exists() and pwm_max and v_nom:
    for line in io.open(bring, encoding="utf-8").read().splitlines():
        if "`cap=`" not in line:
            continue
        pairs += [(float(v), int(c)) for c, v in CAPPAIR.findall(line)]
if not pairs:
    fail("BRINGUP.md states no `cap=` expectation that this could check -- the "
         "operator has no way to tell a working duty cap from a broken one at the "
         "stage where no pump is attached yet")
else:
    for volts, want in pairs:
        got = int(pwm_max * v_nom / volts + 0.5)
        got = max(1, min(pwm_max, got))
        if got != want:
            fail("BRINGUP.md says cap=%d at %.1f V; %d x %.0f / %.1f rounds to %d"
                 % (want, volts, pwm_max, v_nom, volts, got))
    ends = {p[0] for p in pairs}
    for name, v in (("VBAT_MAX", VBAT_MAX), ("VBAT_MIN", VBAT_MIN)):
        if v is not None and v not in ends:
            fail("BRINGUP.md's cap= row does not give the figure at %s = %.1f V, "
                 "which is the end of the range the operator is holding a meter to"
                 % (name, v))
    print("   %d cap figure(s) recomputed from PWM_MAX=%d, PUMP_V_NOM=%.0f: %s"
          % (len(pairs), pwm_max, v_nom,
             ", ".join("%d@%.1fV" % (c, v) for v, c in pairs)))

print("4. the pack range CIRCUIT.md publishes in its rail table")

# ⚠ CIRCUIT.md SAYS OF ITSELF that the pack ceiling "is the number that drives part
# selection", and its rail table is where that number is published. The VBAT_MAX
# sweep (punchlist 48) moved elec/main.py and the sign-off and left this document
# behind: it opened "21 V fresh" and then, ONE LINE LATER, "that 20 V ceiling ...
# parts rated 24 V max sit 4 V from the top", advertising a margin a third larger
# than the real 3 V. One line, one regex, and that cannot happen again.
RAIL = re.compile(r"\|\s*\*\*VBAT\*\*\s*(\d+(?:\.\d+)?)\s*[–—-]\s*"
                  r"(\d+(?:\.\d+)?)\s*V\s*\|")
circuit = ROOT / "elec" / "CIRCUIT.md"
if not circuit.exists():
    fail("elec/CIRCUIT.md is missing")
else:
    m = RAIL.search(io.open(circuit, encoding="utf-8").read())
    if not m:
        fail("elec/CIRCUIT.md's rail table no longer publishes a VBAT range this can "
             "read -- the one line that states the pack ceiling the whole BOM is "
             "chosen against")
    else:
        lo, hi = float(m.group(1)), float(m.group(2))
        if (lo, hi) != (VBAT_MIN, VBAT_MAX):
            fail("elec/CIRCUIT.md publishes VBAT as %g-%g V; elec/main.py says "
                 "%g-%g V" % (lo, hi, VBAT_MIN, VBAT_MAX))
        else:
            print("   VBAT %g-%g V == elec/main.py's VBAT_MIN/VBAT_MAX" % (lo, hi))

print("5. slash pairs name parts that share a net")

# Connectors are excluded: "J1/J2/J3" enumerates three terminals that share a
# FOOTPRINT, which is a different claim and a legitimate one.
PAIR = re.compile(r"\b([RCDQLU]\d{1,2})/([RCDQLU]\d{1,2})\b")
pairs = 0
for rel in GATED:
    path = ROOT / rel
    if not path.exists():
        continue
    for lineno, line in enumerate(io.open(path, encoding="utf-8").read().splitlines(), 1):
        for m in PAIR.finditer(line):
            a, b = m.groups()
            if a not in ONNET or b not in ONNET:
                continue
            pairs += 1
            if not (ONNET[a] & ONNET[b]):
                fail("%s:%d writes %s/%s, but they share no net (%s is on %s; %s "
                     "is on %s)\n        %s"
                     % (rel, lineno, a, b, a, ",".join(sorted(ONNET[a])), b,
                        ",".join(sorted(ONNET[b])), line.strip()[:100]))
print("   %d slash pairs checked" % pairs)

# ---------------------------------------------------------------------------
print("-" * 70)
print("not gated, by design: %s" % ", ".join(NOT_GATED))
if fails:
    print("FAIL: %d" % len(fails))
    for f in fails:
        print("  * %s" % f)
    sys.exit(1)
print("OK: every component value claimed in the gated files matches the netlist")
