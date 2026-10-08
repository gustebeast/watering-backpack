"""Behavioural check on the firmware's tank-full debounce and buzzer pattern.

    py -3.12 tools/check_level_alarm.py      # exit 0 = every property holds

Same standing as tools/check_pump_dirs.py, and the same caveat: there is no host
C++ compiler here, so this does NOT execute the firmware. It transcribes
readLevel() and updateBuzzer() from firmware/src/main.cpp, reads their constants
out of that file rather than retyping them, and fails if the C++ text it claims
to transcribe has changed.

AND IT NOW CHECKS THE POLARITY IT USED TO ASSUME. Checks 1-8 take
LEVEL_FULL_IS_LOW as an INPUT -- HIT = full_low -- so every one of them passed
with the flag set either way, and the flag is what decides whether the alarm
fires on a full tank or on an empty one. Check 9 DERIVES the expected value from
elec/out/main.net and fails if the firmware disagrees. It was wrong in this repo
until the inverter went on the board, and no gate said so.

WHY IT EXISTS. This tank is carried on someone's back, so the water sloshes
across the sensor's threshold constantly, and DESIGN_V2.md §7 puts the sensor
BELOW the full line on purpose -- which means it is crossed early and often. The
debounce is the whole feature; a bench with a still bucket cannot test it.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware" / "src" / "main.cpp"

GUARD = """  if (hit != levelRawHit) { levelRawHit = hit; levelSince = now; }
  uint32_t need = hit ? LEVEL_ASSERT_MS : LEVEL_CLEAR_MS;
  if (hit != tankFull && (now - levelSince) >= need) tankFull = hit;"""

TICK_MS = 5                      # one pass of loop()


def constants(text):
    out = {}
    for name in ("LEVEL_ASSERT_MS", "LEVEL_CLEAR_MS", "BUZZ_ON_MS", "BUZZ_OFF_MS"):
        m = re.search(r"constexpr\s+\w+\s+%s\s*=\s*(\d+)" % name, text)
        if not m:
            raise SystemExit("could not read %s out of main.cpp" % name)
        out[name] = int(m.group(1))
    m = re.search(r"constexpr\s+bool\s+LEVEL_FULL_IS_LOW\s*=\s*(true|false)", text)
    if not m:
        raise SystemExit("could not read LEVEL_FULL_IS_LOW out of main.cpp")
    out["LEVEL_FULL_IS_LOW"] = (m.group(1) == "true")
    return out


class Fw:
    """Transcribed from readLevel() and updateBuzzer()."""

    def __init__(self, c):
        self.c = c
        self.tank_full = False
        self.level_raw_hit = False
        self.level_since = 0
        self.phase = 0
        self.on = False
        self.t = 0
        self.ota = False

    def read_level(self, pin_low):
        c = self.c
        hit = (pin_low == c["LEVEL_FULL_IS_LOW"])
        now = self.t
        if hit != self.level_raw_hit:
            self.level_raw_hit = hit
            self.level_since = now
        need = c["LEVEL_ASSERT_MS"] if hit else c["LEVEL_CLEAR_MS"]
        if hit != self.tank_full and (now - self.level_since) >= need:
            self.tank_full = hit

    def update_buzzer(self):
        c = self.c
        if not self.tank_full or self.ota:
            if self.on:
                self.on = False
            self.phase = self.t
            return
        span = c["BUZZ_ON_MS"] if self.on else c["BUZZ_OFF_MS"]
        if self.t - self.phase >= span:
            self.on = not self.on
            self.phase = self.t

    def step(self, pin_low):
        self.read_level(pin_low)
        self.update_buzzer()
        self.t += TICK_MS
        return self.tank_full, self.on


def drive(c, pin_lows, ota=False):
    fw = Fw(c)
    fw.ota = ota
    return [fw.step(p) for p in pin_lows]


# ══ check 9: the polarity, derived from the board ════════════════════════════
NET = ROOT / "elec" / "out" / "main.net"
BOARD = ROOT / "elec" / "main.py"
MCU = "U2"

# Nets a signal cannot travel THROUGH. GND and the rails terminate a walk: R30 goes
# from the base to GND and is a hold-off, not a path, and the 300k string ends at
# +3V3. Without this the walk leaves the level circuit on the first resistor.
RAILS = ("GND", "+3V3", "3V3", "VBAT", "VCC", "VDD")


def _nets():
    """{net name: [(ref, pin), ...]} out of the KiCad netlist."""
    t = NET.read_text(encoding="utf-8")
    out = {}
    for b in re.split(r"\(net\s+\(code", t[t.index("(nets"):])[1:]:
        m = re.search(r'\(name "([^"]*)"\)', b)
        out[m.group(1)] = re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', b)
    return out


def _ways(ref):
    """J5's way labels, read out of its gen.part() call rather than retyped."""
    t = BOARD.read_text(encoding="utf-8")
    m = re.search(r'gen\.part\(\s*"%s"\s*,[^,]*,[^,]*,\s*\[([^\]]*)\]' % ref, t,
                  re.S)
    if not m:
        return {}
    names = re.findall(r'"([^"]+)"', m.group(1))
    return {str(i + 1): n for i, n in enumerate(names)}


def _module_pin(fw):
    """The module pin carrying LEVEL_PIN, via the same table check_pin_map.py uses."""
    m = re.search(r"constexpr\s+int\s+LEVEL_PIN\s*=\s*(\d+)", fw)
    if not m:
        return None, None
    gpio = "IO%s" % m.group(1)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from check_pin_map import WROOM32E
    for pin, sig in WROOM32E.items():
        if sig == gpio:
            return str(pin), gpio
    return None, gpio


def expected_full_is_low():
    """(expected LEVEL_FULL_IS_LOW, [lines of working]) derived from the netlist.

    Two independent facts decide it, and NEITHER is in the firmware:

      1. the sensor's MODE way, which selects its output sense. Tied to GND the
         XKC-Y25 is NORMALLY CLOSED -- no liquid -> output HIGH. Tied to the supply
         it is normally open and that is inverted.
      2. the number of INVERTING STAGES between the sensor's OUT way and the module
         pin. Each common-emitter stage flips the sense again.

    Returns None rather than guessing if the topology is not one it can read: a
    check that cannot run has not passed, and run() prints "?" and fails.
    """
    why = []
    try:
        nets = _nets()
    except Exception as e:                                   # noqa: BLE001
        return None, ["could not read %s (%s)" % (NET.name, e)]
    pins_h = ROOT / "firmware" / "src" / "pins.h"
    pin, gpio = _module_pin(pins_h.read_text(encoding="utf-8"))
    if pin is None:
        return None, ["could not place %s on a module pin" % gpio]

    of = {}                                                  # (ref, pin) -> net
    for n, nodes in nets.items():
        for node in nodes:
            of[node] = n
    start = of.get((MCU, pin))
    if start is None:
        return None, ["%s pin %s (%s) is on no net" % (MCU, pin, gpio)]

    # ── walk from the module pin OUTWARD to a connector, counting inversions ──
    # stages are counted ONCE: a transistor sits on both the net we came in on and
    # the net we leave by, so without this Q4 is met twice and two inversions cancel
    # -- which is a WRONG answer, not a missing one, and it read FULL IS LOW.
    seen, inv, conn, used, odd = {start}, 0, None, set(), []
    frontier = [start]
    while frontier and conn is None:
        nxt = []
        for net in frontier:
            for ref, p in nets[net]:
                pins = [q for (r, q) in of if r == ref]
                if ref.startswith("J"):
                    conn = (ref, p)
                    break
                if ref.startswith(("R", "L")) and len(pins) == 2:
                    other = next(of[(ref, q)] for q in pins if q != p)
                    if other not in seen and other not in RAILS:
                        seen.add(other)
                        nxt.append(other)
                elif ref.startswith("Q") and ref not in used:
                    used.add(ref)
                    if len(pins) != 3:
                        # a three-terminal part reached on two nets is not a stage
                        # this can read: say which part, because "no connector
                        # reached" blames the walk for the board's problem.
                        odd.append("%s is on %d net(s), not 3" % (ref, len(pins)))
                        continue
                    # the grounded pin is the emitter/source; of the other two, the
                    # one we arrived on is the output and the third is the input.
                    e = [q for q in pins if of[(ref, q)] == "GND"]
                    if len(e) != 1:
                        return None, ["%s is not a grounded-emitter stage" % ref]
                    src = [q for q in pins if q != p and q not in e]
                    if len(src) != 1:
                        return None, ["cannot read %s's input pin" % ref]
                    inv += 1
                    why.append("%s: common-emitter stage, inverts" % ref)
                    other = of[(ref, src[0])]
                    if other not in seen and other not in RAILS:
                        seen.add(other)
                        nxt.append(other)
            if conn:
                break
        frontier = nxt
    if conn is None:
        return None, (["no connector reached from %s pin %s" % (MCU, pin)] + odd)

    ways = _ways(conn[0])
    why.insert(0, "%s way %s (%s) -> %s pin %s (%s), %d inverting stage(s)"
               % (conn[0], conn[1], ways.get(conn[1], "?"), MCU, pin, gpio, inv))

    # ── the MODE way picks the sensor's own sense ─────────────────────────────
    mode = [q for q, name in ways.items() if name.upper() == "MODE"]
    if len(mode) != 1:
        return None, ["%s has no single MODE way" % conn[0]]
    mnet = of.get((conn[0], mode[0]))
    if mnet == "GND":
        sense_hi = True
        why.append("%s MODE on GND: normally closed, no liquid -> sensor HIGH"
                   % conn[0])
    elif mnet and mnet.startswith(("VBAT", "+3V3", "3V3")):
        sense_hi = False
        why.append("%s MODE on %s: normally open, no liquid -> sensor LOW"
                   % (conn[0], mnet))
    else:
        return None, ["%s MODE is on %r, which picks no documented mode"
                      % (conn[0], mnet)]

    # no liquid at the PIN, then FULL is the other one
    pin_hi = sense_hi if inv % 2 == 0 else not sense_hi
    why.append("no liquid -> pin %s, so FULL is %s"
               % ("HIGH" if pin_hi else "LOW", "LOW" if pin_hi else "HIGH"))
    # ⚠ AND THE SAFE SIDE IS THE ONE THIS PICKS. An open sensor lead leaves the
    # stage held off, so the pin sits at its no-liquid level only if that level is
    # the one the hold-off produces -- which is why the arrangement that reads FULL
    # on a broken wire is the correct one: it stops the pump instead of filling a
    # tank on someone's back. See elec/CIRCUIT.md, tank level.
    return pin_hi, why


# ══ check 10: the polarity as WRITTEN DOWN, not just as compiled ═════════════
# Check 9 settles the CONSTANT. It says nothing about the prose, and the prose is
# what a person follows at bring-up with the sensor in a cup of water. Three
# statements were found inverted after check 9 was written and passing:
#
#   * firmware/src/main.cpp, beside the 'b' command: "DRY must read HIGH and WET
#     must read LOW ... Expected here: dry pin=HIGH" -- backwards, in the same
#     comment that quotes the chain giving the opposite answer, and ten lines
#     above the warning NOT to flip the constant if it reads backwards. Following
#     it, a correct board looks miswired and the next move is to take apart Q4.
#   * elec/quality_signoff.py: "LEVEL is an open collector pulled up by R23, so
#     LOW means liquid ... and LEVEL_FULL_IS_LOW encodes exactly that" -- it is
#     false, so it encodes the other thing.
#   * the same file's strapping-pin entry, on which part does the pulling.
#
# BRINGUP.md's table was right, which is the point: the disagreement was silent
# because nothing compared the sentences with each other or with the netlist.
#
# So this reads the claims back out of the prose and checks them against check 9's
# derivation. A value inside double quotes (or the typographic pair) is a
# QUOTATION -- a retraction has to be able to state the old claim -- and every
# quotation is reported, never silently dropped.
POLARITY_FILES = ("firmware/src/main.cpp", "firmware/src/pins.h",
                  "firmware/src/pins.cpp", "BRINGUP.md", "elec/CIRCUIT.md",
                  "elec/quality_signoff.py", "bom_consolidated.md")

_QUOTED = re.compile(u'["\u201c][^"\u201d\n]*["\u201d]')
# \u26a0 AND IN A .py FILE THE WHOLE LINE IS INSIDE A STRING LITERAL, so the plain
# double quote cannot mark a quotation there -- it marks the source. Read that way,
# elec/quality_signoff.py excused every claim it made, which is how the first
# version of this check passed while the inverted sentence was still in the file.
# In Python sources only the TYPOGRAPHIC pair counts as a quotation.
_QUOTED_PY = re.compile(u'\u201c[^\u201d\n]*\u201d')
# "pin=LOW -> not full", which is the form BRINGUP.md tabulates and the form the
# firmware's own logf prints.
_PINSTATE = re.compile(r"pin\s*=\s*(HIGH|LOW)[^|\n]{0,24}?(not full|FULL)")
# "dry ... pin=LOW". Requires the word pin in between, because "WET -> sensor LOW"
# is a statement about the SENSOR's output, which is the opposite level and
# equally true.
_WETDRY = re.compile(r"\b(dry|DRY|wet|WET)\b[^.|\n]{0,60}?pin\s*=?\s*(HIGH|LOW)")
# "LOW means liquid"
_MEANS = re.compile(r"\b(HIGH|LOW)\b\s+means\s+(liquid|wet|dry|DRY|full|not full)",
                    re.I)


def prose_polarity(full_is_low):
    """Every written claim about the pin's level, checked against check 9.

    Returns (claims read, [quotation notes], [contradictions]).
    """
    # From the derivation: FULL is LOW when the constant is true, HIGH when false.
    full_level = "LOW" if full_is_low else "HIGH"
    dry_level = "HIGH" if full_is_low else "LOW"
    read, notes, bad = 0, [], []
    per_file = []
    for rel in POLARITY_FILES:
        path = ROOT / rel
        if not path.exists():
            bad.append("%s is missing" % rel)
            continue
        before = read
        quoter = _QUOTED_PY if rel.endswith(".py") else _QUOTED
        for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            spans = [m.span() for m in quoter.finditer(line)]

            def quoted(m):
                return any(a <= m.start() < b for a, b in spans)

            for m in _PINSTATE.finditer(line):
                lvl, state = m.group(1), m.group(2)
                want = full_level if state == "FULL" else dry_level
                if quoted(m):
                    notes.append("%s:%d quotes pin=%s -> %s" % (rel, ln, lvl, state))
                    continue
                read += 1
                if lvl != want:
                    bad.append("%s:%d says pin=%s -> %s; the board gives pin=%s "
                               "for %s\n        %s"
                               % (rel, ln, lvl, state, want, state, line.strip()[:90]))
            for m in _WETDRY.finditer(line):
                which, lvl = m.group(1).lower(), m.group(2)
                want = full_level if which == "wet" else dry_level
                if quoted(m):
                    notes.append("%s:%d quotes %s -> pin=%s" % (rel, ln, which, lvl))
                    continue
                read += 1
                if lvl != want:
                    bad.append("%s:%d says %s reads pin=%s; the board gives %s"
                               "\n        %s"
                               % (rel, ln, which, lvl, want, line.strip()[:90]))
            for m in _MEANS.finditer(line):
                lvl, what = m.group(1).upper(), m.group(2).lower()
                wet = what in ("liquid", "wet", "full")
                want = full_level if wet else dry_level
                if quoted(m):
                    notes.append("%s:%d quotes \"%s means %s\"" % (rel, ln, lvl, what))
                    continue
                read += 1
                if lvl != want:
                    bad.append("%s:%d says \"%s means %s\"; the board gives %s"
                               "\n        %s"
                               % (rel, ln, lvl, what, want, line.strip()[:90]))
        per_file.append("%s %d" % (rel.rsplit("/", 1)[-1], read - before))
    return read, notes, bad, per_file


def main():
    text = SRC.read_text(encoding="utf-8")
    if GUARD not in text:
        print("STALE: the firmware block this test transcribes has changed.")
        print("Re-read firmware/src/main.cpp against Fw before trusting it.")
        return 1
    c = constants(text)
    print("constants from main.cpp: %s\n" % c)
    full_low = c["LEVEL_FULL_IS_LOW"]
    HIT, MISS = full_low, not full_low       # what the pin reads for each
    a_ticks = c["LEVEL_ASSERT_MS"] // TICK_MS
    bad = 0

    # 1. idle: a pin held at the no-liquid level never alarms. This is also the
    #    state of a DISCONNECTED sensor: its base held down by R30, Q4 is off and
    #    the 300k string pulls LEVEL up. (This said "R23 pulls the pin up". R23 is
    #    the FAR END of that string and does not touch LEVEL -- see check 9.)
    h = drive(c, [MISS] * 2000)
    ok = not any(f for f, _ in h)
    print("  idle / no sensor   -> never alarms            %s" % ("ok" if ok else "FAIL"))
    bad += not ok

    # 2. slosh: hits shorter than LEVEL_ASSERT_MS must not alarm. A wave that
    #    wets the sensor for 400 ms every second is the realistic case.
    burst = [HIT] * (400 // TICK_MS) + [MISS] * (600 // TICK_MS)
    h = drive(c, burst * 30)
    ok = not any(f for f, _ in h)
    print("  400 ms slosh x30   -> never alarms            %s" % ("ok" if ok else "FAIL"))
    bad += not ok

    # 3. a real fill asserts, and at the stated time
    h = drive(c, [HIT] * 400)
    i = next((k for k, (f, _) in enumerate(h) if f), None)
    ok = i is not None and abs(i * TICK_MS - c["LEVEL_ASSERT_MS"]) <= TICK_MS
    print("  sustained liquid   -> alarms at %s ms (want %d)   %s"
          % (i * TICK_MS if i is not None else "never", c["LEVEL_ASSERT_MS"],
             "ok" if ok else "FAIL"))
    bad += not ok

    # 4. once alarming, a brief dropout must NOT clear it -- the level is at the
    #    threshold, so it will be crossed both ways repeatedly.
    tr = [HIT] * 400 + ([MISS] * (1000 // TICK_MS) + [HIT] * (200 // TICK_MS)) * 10
    h = drive(c, tr)
    ok = all(f for f, _ in h[400:])
    print("  1 s dropouts x10   -> stays alarming          %s" % ("ok" if ok else "FAIL"))
    bad += not ok

    # 5. a genuine empty does clear it, after LEVEL_CLEAR_MS
    tr = [HIT] * 400 + [MISS] * 1000
    h = drive(c, tr)
    j = next((k for k, (f, _) in enumerate(h) if k > 400 and not f), None)
    lag = (j - 400) * TICK_MS if j is not None else None
    ok = j is not None and abs(lag - c["LEVEL_CLEAR_MS"]) <= TICK_MS
    print("  tank drained       -> clears after %s ms (want %d)  %s"
          % (lag, c["LEVEL_CLEAR_MS"], "ok" if ok else "FAIL"))
    bad += not ok

    # 6. asymmetry is the point: assert must be faster than clear
    ok = c["LEVEL_ASSERT_MS"] < c["LEVEL_CLEAR_MS"]
    print("  asymmetry          -> assert %d < clear %d        %s"
          % (c["LEVEL_ASSERT_MS"], c["LEVEL_CLEAR_MS"], "ok" if ok else "FAIL"))
    bad += not ok

    # 7. the buzzer beeps rather than sitting on, and only while full
    h = drive(c, [HIT] * 2000)
    beeps = [on for _, on in h[a_ticks:]]
    duty = sum(beeps) / float(len(beeps))
    want = c["BUZZ_ON_MS"] / float(c["BUZZ_ON_MS"] + c["BUZZ_OFF_MS"])
    ok = abs(duty - want) < 0.05 and any(beeps) and not all(beeps)
    print("  buzzer while full  -> %.0f%% duty (want %.0f%%), period %d ms   %s"
          % (100 * duty, 100 * want, c["BUZZ_ON_MS"] + c["BUZZ_OFF_MS"],
             "ok" if ok else "FAIL"))
    bad += not ok

    # 8. silent mid-OTA, so a reflash is not done to a screaming board
    h = drive(c, [HIT] * 2000, ota=True)
    ok = not any(on for _, on in h)
    print("  mid-OTA            -> silent                  %s" % ("ok" if ok else "FAIL"))
    bad += not ok

    # 9. THE POLARITY ITSELF, derived from the board rather than assumed.
    want, why = expected_full_is_low()
    ok = want is not None and want == full_low
    print("  polarity vs board  -> LEVEL_FULL_IS_LOW = %s, board wants %s   %s"
          % (str(full_low).lower(),
             "?" if want is None else str(want).lower(), "ok" if ok else "FAIL"))
    for line in why:
        print("        %s" % line)
    bad += not ok

    # 10. the same polarity as it is WRITTEN DOWN, everywhere it is written down.
    if want is None:
        print("  polarity in prose  -> not checked: check 9 could not derive it   FAIL")
        bad += 1
    else:
        read, notes, contra, per_file = prose_polarity(want)
        # The verdict in the margin includes read == 0. A check that read nothing
        # printing "ok" beside its own failure line is the margin lying, which is
        # the whole of finding 47.
        print("  polarity in prose  -> %d claim(s) read, %d quoted, %d contradict "
              "the board   %s" % (read, len(notes), len(contra),
                                  "ok" if not contra and read else "FAIL"))
        print("        coverage: %s" % ", ".join(per_file))
        for n in notes:
            print("        note: %s" % n)
        for c in contra:
            print("        * %s" % c)
        if read == 0:
            # Nothing read is not a pass: the patterns have stopped matching the
            # way the repo writes it, and the check has quietly become decoration.
            print("        * NO polarity claim matched anywhere -- check 10 is "
                  "reading nothing and cannot pass on that")
            bad += 1
        bad += bool(contra)

    print("\n%s" % ("every level/alarm property holds" if not bad
                    else "*** %d PROPERTY FAILURE(S) ***" % bad))
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
