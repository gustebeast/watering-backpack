"""Behavioural check on the firmware's tank-full debounce and buzzer pattern.

    py -3.12 tools/check_level_alarm.py      # exit 0 = every property holds

Same standing as tools/check_pump_dirs.py, and the same caveat: there is no host
C++ compiler here, so this does NOT execute the firmware. It transcribes
readLevel() and updateBuzzer() from firmware/src/main.cpp, reads their constants
out of that file rather than retyping them, and fails if the C++ text it claims
to transcribe has changed.

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
    #    state of a DISCONNECTED sensor, since R23 pulls the pin up.
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

    print("\n%s" % ("every level/alarm property holds" if not bad
                    else "*** %d PROPERTY FAILURE(S) ***" % bad))
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
