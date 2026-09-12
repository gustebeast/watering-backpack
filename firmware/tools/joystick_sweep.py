#!/usr/bin/env python3
"""
Characterise joystick ADC noise as a function of stick POSITION.

Physics being tested: a pot's Thevenin source impedance is R*x*(1-x) — highest at
mid-travel (R/4), falling toward zero at both ends. So if the noise comes from a
high/degraded source impedance fighting the ESP32's sample-and-hold, it must be
WORST at centre and clearly better at large deflection. If the noise is instead
injected (EMI pickup on the wiper run, or a bad ground), it will be roughly FLAT
across travel. That contrast identifies the fault.

Two things make this measurement honest:

  * It uses `hf` (mean |sample-to-sample difference|), NOT stdev. Electrical noise
    is uncorrelated sample to sample so it shows up in full; a human moving the
    stick is slow against the 200 Hz sample rate and barely registers. Stdev
    cannot separate the two, so an earlier version of this test simply measured
    the operator's hand.
  * It DISCARDS any window that touched an ADC rail. At full deflection the pot
    drives the pin outside the ESP32's usable ~0.15-3.1 V window, so the reading
    pins at 0 or 4095 and the noise is clipped away — which would otherwise look
    like a spectacular (and entirely fake) drop in noise.

The board is DISARMED first and the script aborts unless it can confirm that, so
the pump cannot move water during the sweep.

    python joystick_sweep.py --host 192.168.1.214 --secs 75
"""
import argparse
import re
import socket
import sys
import time

LOG_PORT = 23

STAT_RE = re.compile(
    r"STATS n=(\d+) raw=(-?\d+)\.\.(-?\d+) mean=([-\d.]+) sd=([-\d.]+) hf=([-\d.]+) "
    r"over_deadband=(\d+) maxrun=(\d+) dutymax=(-?\d+)"
)

INSTRUCTIONS = """
  Sweep the stick SLOWLY and CONTINUOUSLY through its full travel, over and over,
  for the whole recording. Roughly 5 seconds from one end to the other.

  Do NOT try to hold still  -- the metric ignores your movement.
  Do NOT linger at the hard stops -- those readings are clipped and get discarded.
  Spend most of the time in between the centre and the ends.
"""

RAIL_LO, RAIL_HI = 5, 4090


def connect_and_disarm(host, timeout=8.0):
    s = socket.create_connection((host, LOG_PORT), timeout=5)
    s.settimeout(0.5)
    s.sendall(b"d")                      # disarm before anything can move
    buf, t0 = b"", time.time()
    while time.time() - t0 < timeout:
        try:
            chunk = s.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        buf += chunk
        if b"DISARMED" in buf:
            print("Confirmed: pump DISARMED. Motor outputs inhibited.\n")
            return s
    s.close()
    sys.exit("ABORT: could not confirm the pump was disarmed — refusing to run a "
             "sweep test that could drive the pump.")


def collect(sock, secs):
    buf, t0 = b"", time.time()
    while time.time() - t0 < secs:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            m = STAT_RE.search(line.decode("utf-8", "replace").rstrip())
            if not m:
                continue
            n, mn, mx, mean, sd, hf, over, run, duty = m.groups()
            yield {"t": time.time() - t0, "n": int(n), "min": int(mn), "max": int(mx),
                   "mean": float(mean), "sd": float(sd), "hf": float(hf),
                   "over": int(over), "maxrun": int(run), "duty": int(duty)}


def analyse(W, centre):
    print("\n" + "=" * 70)
    unsafe = [w for w in W if w["duty"] != 0]
    print("Safety: %s" % ("duty stayed 0 in every window — pump never driven."
                          if not unsafe else
                          "WARNING — non-zero duty seen! disarm did NOT hold."))

    pos = [w["mean"] for w in W]
    print("\nTRAVEL")
    print("  reached           : %.0f .. %.0f  (of 0..4095)" % (min(pos), max(pos)))
    clipped = [w for w in W if w["min"] <= RAIL_LO or w["max"] >= RAIL_HI]
    print("  clipped windows   : %d of %d discarded (touched an ADC rail)"
          % (len(clipped), len(W)))

    clean = [w for w in W if w not in clipped]
    if len(clean) < 8:
        print("\nINCONCLUSIVE: only %d unclipped windows. Re-run, spending more time"
              " between centre and the ends." % len(clean))
        print("=" * 70)
        return

    # How much of the stdev was the operator moving, vs. real electrical noise?
    # For white Gaussian noise hf ~= 1.128*sd, i.e. sd_equiv = hf/1.128.
    print("\nMOVEMENT CHECK (how much of stdev was you, not noise)")
    tot_sd = sum(w["sd"] for w in clean) / len(clean)
    tot_hf = sum(w["hf"] for w in clean) / len(clean)
    print("  mean sd  = %6.1f   mean hf = %6.1f   -> hf-implied sd = %.1f"
          % (tot_sd, tot_hf, tot_hf / 1.128))

    bins = [("0-250    centre", 0, 250), ("250-600", 250, 600), ("600-1000", 600, 1000),
            ("1000-1500", 1000, 1500), ("1500-2000  far", 1500, 9999)]
    print("\nHIGH-FREQUENCY NOISE vs DEFLECTION   (hf = mean |sample-to-sample diff|)")
    print("  %-20s %7s %9s %9s" % ("|deflection|", "windows", "mean hf", "peak hf"))
    rows = []
    for label, lo, hi in bins:
        sel = [w for w in clean if lo <= abs(w["mean"] - centre) < hi]
        if len(sel) < 2:
            continue
        hfs = [w["hf"] for w in sel]
        avg = sum(hfs) / len(hfs)
        rows.append((label, avg, len(sel)))
        print("  %-20s %7d %9.1f %9.1f" % (label, len(sel), avg, max(hfs)))

    print("\nVERDICT")
    if len(rows) < 2:
        print("  INCONCLUSIVE — need usable data in at least two deflection bands.")
    else:
        near, far = rows[0][1], rows[-1][1]
        ratio = near / far if far > 0.01 else 999
        print("  centre hf / far hf = %.2fx   (%s vs %s)" % (ratio, rows[0][0], rows[-1][0]))
        if ratio > 1.8:
            print("  -> Noise falls off with deflection. Consistent with HIGH SOURCE")
            print("     IMPEDANCE: a worn/dirty pot track or a degraded wiper joint.")
            print("     Fix: RC filter at the ADC pin + inspect/reflow the wiper.")
        elif ratio < 1.3:
            print("  -> Noise is FLAT across travel. NOT source impedance. Points to")
            print("     INJECTED noise — EMI pickup on the wiper run, or a bad/shared")
            print("     ground. Fix: shield or reroute the wiper, and fix the ground.")
        else:
            print("  -> Mixed. Likely both mechanisms present; filter first, remeasure.")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--secs", type=float, default=75.0)
    ap.add_argument("--centre", type=float, default=None, help="ADC centre (default: auto)")
    ap.add_argument("--out")
    args = ap.parse_args()

    sock = connect_and_disarm(args.host)
    print(INSTRUCTIONS)
    print("Recording for %.0f seconds — go.\n" % args.secs)

    W = []
    try:
        for w in collect(sock, args.secs):
            W.append(w)
            flag = "CLIP" if (w["min"] <= RAIL_LO or w["max"] >= RAIL_HI) else "    "
            bar = "#" * int(max(0, min(34, (w["mean"] / 4095.0) * 34)))
            print("%5.1fs pos=%6.0f hf=%6.1f sd=%6.1f %s %s"
                  % (w["t"], w["mean"], w["hf"], w["sd"], flag, bar), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()

    if not W:
        sys.exit("No telemetry received.")
    if args.out:
        with open(args.out, "w") as f:
            keys = ["t", "n", "min", "max", "mean", "sd", "hf", "over", "maxrun", "duty"]
            f.write(",".join(keys) + "\n")
            for w in W:
                f.write(",".join(str(w[k]) for k in keys) + "\n")

    centre = args.centre if args.centre else sorted(w["mean"] for w in W)[len(W) // 2]
    analyse(W, centre)


if __name__ == "__main__":
    main()
