#!/usr/bin/env python3
"""
Capture pump-controller telemetry, over WiFi or USB, and summarise it.

    # remote, over WiFi — disarm the motor first so no water moves
    python capture.py --host watering-backpack.local --cmd d --secs 30

    # local, over USB
    python capture.py --port COM4 --secs 15

    # re-arm when finished
    python capture.py --host watering-backpack.local --cmd a --secs 2

Commands (--cmd): a=arm  d=disarm  c=recalibrate centre  s=status  R=reboot

STATS lines are parsed as generic key=value tokens rather than a fixed pattern, so
adding or removing a field in the firmware does not break this tool.
"""
import argparse
import math
import re
import socket
import sys
import time

LOG_PORT = 23


def parse_stats(line):
    i = line.find("STATS ")
    if i < 0:
        return None
    d = {}
    for tok in line[i + 6:].split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            d[k] = v
    return d or None


def num(d, key, default=0.0):
    v = d.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def stream_tcp(host, cmd, secs):
    s = socket.create_connection((host, LOG_PORT), timeout=5)
    s.settimeout(0.5)
    if cmd:
        s.sendall(cmd.encode())
    buf, t0 = b"", time.time()
    while time.time() - t0 < secs:
        try:
            chunk = s.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield time.time() - t0, line.decode("utf-8", "replace").rstrip()
    s.close()


def stream_serial(port, cmd, secs, reset):
    import serial

    s = serial.Serial(port, 115200, timeout=0.2)
    if reset:
        # Pulse EN via RTS, DTR high so we boot the app rather than the ROM loader.
        s.dtr, s.rts = False, True
        time.sleep(0.15)
        s.rts = False
        time.sleep(0.05)
        s.reset_input_buffer()
    if cmd:
        s.write(cmd.encode())
    t0 = time.time()
    while time.time() - t0 < secs:
        line = s.readline()
        if line:
            yield time.time() - t0, line.decode("utf-8", "replace").rstrip()
    s.close()


def summarise(raws, stats):
    print("\n" + "=" * 66)
    if raws:
        n = len(raws)
        mean = sum(raws) / n
        sd = math.sqrt(sum((r - mean) ** 2 for r in raws) / n)
        print("PRINTED LINES (1 sample per 250 ms — coarse)")
        print("  samples   : %d" % n)
        print("  raw range : %d .. %d  (span %d)" % (min(raws), max(raws), max(raws) - min(raws)))
        print("  mean / sd : %.1f / %.1f counts" % (mean, sd))

    if not stats:
        print("=" * 66)
        return

    total = sum(num(d, "n") for d in stats)
    sds = [num(d, "sd") for d in stats]
    hfs = [num(d, "hf") for d in stats]
    fsds = [num(d, "fsd") for d in stats if "fsd" in d]
    over = sum(num(d, "over_deadband") for d in stats)
    fover = sum(num(d, "fover") for d in stats if "fover" in d)
    runs = max([num(d, "maxrun") for d in stats] or [0])
    dmax = max([num(d, "dutymax") for d in stats] or [0])
    engages = sum(num(d, "engages") for d in stats if "engages" in d)
    secs = len(stats)

    print("\nFIRMWARE STATS (every loop sample, ~200/s — the real picture)")
    print("  samples          : %d over %d windows" % (total, secs))
    print("  raw stdev        : %.1f counts (mean), peak %.1f" % (sum(sds) / len(sds), max(sds)))
    if hfs and max(hfs) > 0:
        hf = sum(hfs) / len(hfs)
        print("  raw hf           : %.1f  -> implies white-noise sd %.1f" % (hf, hf / 1.128))
    if fsds:
        print("  filtered stdev   : %.1f counts  (%.1fx better — diagnostic path only)"
              % (sum(fsds) / len(fsds), (sum(sds) / len(sds)) / max(0.01, sum(fsds) / len(fsds))))
    print("  deadband crosses : raw %d (%.2f%% of samples)" % (over, 100.0 * over / max(1, total)))
    if any("fover" in d for d in stats):
        print("                   : filtered %d" % fover)
    print("  longest raw run  : %d consecutive samples over deadband" % runs)
    print("  max duty         : %d" % dmax)

    if any("engages" in d for d in stats):
        print("\n  >>> SPURIOUS ENGAGES : %d  in %d s" % (engages, secs))
        if engages == 0:
            print("      The vote rejected every noise excursion. Pump never commanded on.")
        else:
            print("      NOT ZERO — the vote let noise through. Raise VOTE_K_ON or DEADBAND_ON.")
    print("=" * 66)


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--host", help="hostname/IP for WiFi telemetry")
    src.add_argument("--port", help="serial port, e.g. COM4")
    ap.add_argument("--secs", type=float, default=20.0)
    ap.add_argument("--cmd", default="", help="command to send on connect (a/d/c/s/R)")
    ap.add_argument("--reset", action="store_true", help="serial only: reset to catch boot lines")
    ap.add_argument("--out", help="also write the raw trace to this file")
    ap.add_argument("--quiet", action="store_true", help="only print STATS and events")
    args = ap.parse_args()

    stream = (stream_tcp(args.host, args.cmd, args.secs) if args.host
              else stream_serial(args.port, args.cmd, args.secs, args.reset))

    raw_re = re.compile(r"raw=\s*(\d+)")
    raws, stats, sink = [], [], open(args.out, "w") if args.out else None
    try:
        for t, line in stream:
            d = parse_stats(line)
            if not (args.quiet and d is None and "raw=" in line):
                print("%6.2f  %s" % (t, line), flush=True)
            if sink:
                sink.write("%6.2f  %s\n" % (t, line))
            if d:
                stats.append(d)
            elif "raw=" in line:
                m = raw_re.search(line)
                if m:
                    raws.append(int(m.group(1)))
    except KeyboardInterrupt:
        pass
    except (socket.error, OSError) as e:
        print("connection error: %s" % e, file=sys.stderr)
    finally:
        if sink:
            sink.close()
    summarise(raws, stats)


if __name__ == "__main__":
    main()
