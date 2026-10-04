"""Behavioural check on the firmware's direction state machine.

    py -3.12 tools/check_pump_dirs.py        # exit 0 = every property holds

WHAT THIS IS, EXACTLY. There is no host C++ compiler in this environment -- only
the xtensa cross-compiler, whose output cannot be run here -- so this does NOT
execute the firmware. It is a TRANSCRIPTION of the decision block in
firmware/src/main.cpp, driven over joystick traces that are awkward to produce by
hand on a bench.

So it can lie if the transcription drifts. Two things keep it honest:

  * every constant is READ OUT OF main.cpp, never retyped here;
  * the C++ block it transcribes is pinned by GUARD below, and the run fails if
    that text is no longer in main.cpp. Change the firmware and this fails until
    someone re-reads both sides.

The compile-time half of the verification lives in main.cpp as static_asserts.

WHY IT MATTERS. DESIGN_V2.md section 1 puts two pumps in anti-parallel across
shared tees -- pump A tank->pot, pump B pot->tank. Running both at once makes
them fight through those tees and pulls 2 x 7.5 A off one pack, so "never both"
is the property that has to hold, not just usually hold.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware" / "src" / "main.cpp"

# The firmware text this file claims to transcribe. If it moves, we stop.
GUARD = """  Dir wasDir = runDir;
  if (runDir == DIR_NONE) {
    bool fwd = (nFwd >= VOTE_K_ON), rev = (nRev >= VOTE_K_ON);
    // Both votes passing at once is not physically possible on one axis, so it
    // means something is wrong with the stick or its wiring. Start neither.
    if (fwd != rev &&
        (!everStopped || (millis() - lastStopMs) >= DIR_DEAD_MS)) {"""


def constants(text):
    out = {}
    for name in ("DEADBAND_ON", "DEADBAND_OFF", "VOTE_N_ON", "VOTE_K_ON",
                 "VOTE_N_OFF", "VOTE_K_OFF", "DIR_DEAD_MS"):
        m = re.search(r"constexpr\s+\w+\s+%s\s*=\s*(-?\d+)" % name, text)
        if not m:
            raise SystemExit("could not read %s out of main.cpp" % name)
        out[name] = int(m.group(1))
    return out


class Machine:
    """Transcribed from main.cpp. Tick = one 5 ms pass of loop()."""

    TICK_MS = 5

    def __init__(self, c):
        self.c = c
        self.fwd_hist = self.rev_hist = self.near_hist = 0
        self.dir = 0                      # DIR_NONE
        self.last_stop_ms = 0
        self.ever_stopped = False
        self.t = 0

    def step(self, raw_offset):
        c = self.c
        self.fwd_hist = ((self.fwd_hist << 1) |
                         (1 if raw_offset > c["DEADBAND_ON"] else 0)) & 0xFFFF
        self.rev_hist = ((self.rev_hist << 1) |
                         (1 if raw_offset < -c["DEADBAND_ON"] else 0)) & 0xFFFF
        self.near_hist = ((self.near_hist << 1) |
                          (1 if abs(raw_offset) < c["DEADBAND_OFF"] else 0)) & 0xFFFF
        n_fwd = bin(self.fwd_hist & ((1 << c["VOTE_N_ON"]) - 1)).count("1")
        n_rev = bin(self.rev_hist & ((1 << c["VOTE_N_ON"]) - 1)).count("1")
        n_near = bin(self.near_hist & ((1 << c["VOTE_N_OFF"]) - 1)).count("1")

        if self.dir == 0:
            fwd, rev = n_fwd >= c["VOTE_K_ON"], n_rev >= c["VOTE_K_ON"]
            if fwd != rev and (not self.ever_stopped or
                               (self.t - self.last_stop_ms) >= c["DIR_DEAD_MS"]):
                self.dir = 1 if fwd else -1
        else:
            opp = (n_rev >= c["VOTE_K_ON"]) if self.dir == 1 else (n_fwd >= c["VOTE_K_ON"])
            if n_near >= c["VOTE_K_OFF"] or opp:
                self.dir = 0
                self.last_stop_ms = self.t
                self.ever_stopped = True
        self.t += self.TICK_MS
        return self.dir

    def pins(self, duty=255):
        """What drivePumps would write. Mutual exclusion is structural there."""
        return (duty if self.dir == 1 else 0, duty if self.dir == -1 else 0)


def run(c, trace, label):
    """Drive a trace of offsets; return the direction history."""
    m = Machine(c)
    hist = []
    for off in trace:
        m.step(off)
        a, b = m.pins()
        if a and b:
            raise SystemExit("%s: BOTH PUMPS DRIVEN at t=%d ms" % (label, m.t))
        hist.append(m.dir)
    return hist


def first(hist, want):
    return next((i for i, d in enumerate(hist) if d == want), None)


def main():
    text = SRC.read_text(encoding="utf-8")
    if GUARD not in text:
        print("STALE: the firmware block this test transcribes has changed.")
        print("Re-read firmware/src/main.cpp against Machine.step before trusting it.")
        return 1
    c = constants(text)
    on, off = c["DEADBAND_ON"], c["DEADBAND_OFF"]
    dead_ticks = c["DIR_DEAD_MS"] // Machine.TICK_MS
    print("constants from main.cpp: %s\n" % c)
    bad = 0

    # 1. hard forward, held
    h = run(c, [on + 100] * 60, "forward")
    i = first(h, 1)
    ok = i is not None and i * 5 <= 100 and all(d == 1 for d in h[i:])
    print("  forward hold      -> pump A at %s ms, stays   %s"
          % (i * 5 if i is not None else "never", "ok" if ok else "FAIL"))
    bad += not ok

    # 2. forward then centred
    h = run(c, [on + 100] * 40 + [0] * 40, "release")
    ok = 1 in h[:40] and h[-1] == 0
    print("  release to centre -> stops                     %s" % ("ok" if ok else "FAIL"))
    bad += not ok

    # 3. THE EDGE CASE: snap from hard-forward to hard-back in one sample, never
    #    dwelling inside the release band. The near vote alone can never fire.
    tr = [on + 100] * 40 + [-(on + 100)] * 120
    h = run(c, tr, "snap")
    assert 1 in h[:40], "trace never engaged A; the rest proves nothing"
    last_a = max(i for i, d in enumerate(h) if d == 1)
    lag = (last_a - 39) * Machine.TICK_MS
    got_b = first(h, -1)
    ok = (lag <= c["VOTE_N_ON"] * Machine.TICK_MS and got_b is not None
          and last_a < got_b)
    print("  snap fwd->rev     -> A off %d ms after the flick (vote window %d), "
          "B at %s ms   %s"
          % (lag, c["VOTE_N_ON"] * Machine.TICK_MS,
             got_b * 5 if got_b else "never", "ok" if ok else "FAIL"))
    bad += not ok

    # 4. the dead time is actually waited out, and nothing runs during it
    last_a = max(i for i, d in enumerate(h) if d == 1)
    stop_i = last_a + 1
    gap = (got_b - stop_i) * Machine.TICK_MS
    ok = gap >= c["DIR_DEAD_MS"] and all(d == 0 for d in h[stop_i:got_b])
    print("  dead time         -> %d ms idle before B (need >= %d)      %s"
          % (gap, c["DIR_DEAD_MS"], "ok" if ok else "FAIL"))
    bad += not ok

    # 5. no A->B edge anywhere: every direction change passes through NONE
    edges = [(h[i - 1], h[i]) for i in range(1, len(h)) if h[i] != h[i - 1]]
    ok = all(0 in e for e in edges)
    print("  transitions       -> %s   %s"
          % (" ".join("%d>%d" % e for e in edges), "ok" if ok else "FAIL"))
    bad += not ok

    # 6. at rest: jitter that never clears the engage threshold must not start
    #    a pump in EITHER direction. (With reverse live there are now two ways
    #    to false-trigger, so the spurious rate is 2x what it was -- still
    #    ~1e-10 per window by main.cpp's own arithmetic.)
    import random
    random.seed(1)
    h = run(c, [random.randint(-off, off) for _ in range(20000)], "rest")
    ok = all(d == 0 for d in h)
    print("  20 k rest samples -> no engage either way      %s"
          % ("ok" if ok else "FAIL"))
    bad += not ok

    # 7. a stick reading past threshold BOTH ways is impossible on one axis, so
    #    it means broken wiring: start neither.
    h = run(c, [on + 100] * 0 + [0] * 60, "none")
    m = Machine(c)
    for _ in range(60):
        m.fwd_hist = m.rev_hist = 0xFFFF      # force both votes to pass
        m.step(0)
    ok = m.dir == 0
    print("  both votes pass   -> starts neither             %s"
          % ("ok" if ok else "FAIL"))
    bad += not ok

    print("\n%s" % ("every direction property holds" if not bad
                    else "*** %d PROPERTY FAILURE(S) ***" % bad))
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
