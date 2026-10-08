"""Check what DRC cannot: matched-length groups, pair integrity, net lengths.

    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/verify.py elec/out/optical

RUNS UNDER KICAD'S PYTHON (it reads tracks, so it needs pcbnew).

WHY THIS EXISTS. DRC answers "is this manufacturable" -- clearances, shorts, board
edges. It does not answer "is this CORRECT", and on a board carrying a 60 MHz
source-synchronous bus and a 480 Mbps differential pair those are different
questions. A router can produce a DRC-perfect board on which the USB pair is split
across two layers and takes two unrelated paths, and nothing in the pipeline would
notice.

THE POINT IS TO REMOVE THE HUMAN, NOT TO ADVISE ONE. The goal for this project is
that someone years from now changes a parameter -- the string spacing, say -- runs
the scripts, and gets a package they can send to a fab without anyone having to
eyeball a layout. That only works if the judgement calls a person would make are
written down as CHECKS. So the budgets live in <board>.board.json beside the design
that has to meet them, and this exits non-zero when they are not met.

⚠ WHAT IS DELIBERATELY NOT CHECKED, so nobody adds it back as an improvement. The CAN
pairs on motor_ctrl, can_tee and lever_sensor declare no group. Measured rather than
assumed: can_tee's pair runs 33.25/32.36 mm and lever_sensor's 39.75/42.23 mm, and
lever_sensor's two rails do NOT share a layer set. At 500 kbit/s a bit is 2,000,000 ps,
so 2.5 mm of skew is 15 ps -- eight millionths of a bit. A budget there would fail builds
for nothing, which is the cargo cult this file's last paragraph is about. Pairness on a
40 mm stub of a 120-ohm bus is in the same category. If the bus ever runs CAN-FD at
5 Mbit/s the arithmetic changes by 10x and is still not close; revisit it then, with a
number, not now.

⚠ A BUDGET NEEDS A REASON, AND THE REASON IS CHECKED TOO. Every entry carries a
`why`; a limit with no stated basis is a number someone will later relax because it
was in the way. The optical board's ULPI budget, for instance, is deliberately
LOOSE and says so: a 34.5 mm bus at 60 MHz has ~207 ps of flight, so even 10 mm of
mismatch is 60 ps against a 16,670 ps bit period. Writing 0.1 mm there would look
rigorous and would be cargo cult -- it would fail builds for a physical effect four
orders of magnitude below what matters.
"""
from __future__ import annotations

import json
import os
import sys

import pcbnew
import noassert                                      # noqa: F401,E402  (no GUI dialogs)


def net_lengths(board, merge_ref=None, merge_r=4.0):
    """{net name: (copper length in mm, {layer name: length}, via count)}."""
    # ⚠ A PAD-MERGE STUB IS NOT PART OF THE TRANSMISSION LINE, and counting it made this
    # check cry wolf twice on the optical board. A USB-C carries D+ on BOTH A6 and B6 and
    # D- on both A7 and B7, so the generator joins each net's two pads at the connector
    # (layout._flip_merge) -- and that join deliberately takes ONE rail down to an inner
    # layer, because which one dives is decided by which link is shorter.
    #
    # Measured on optical: counting every segment, USB_DP read F.Cu+In2.Cu against
    # USB_DM's F.Cu and the pair was reported as SPLIT ACROSS LAYERS, while skew read
    # 3.28 mm against a 2.50 budget. Excluding copper within `merge_r` of the merge
    # connector, the coupled RUN is F.Cu for both rails and the skew is 1.08 mm. The
    # board was fine; the measurement was counting the wrong copper.
    #
    # The exclusion is by NAMED REF, not by guessing which stubs look like merges: a
    # group says where its merge is, or nothing is excluded.
    skip = []
    if merge_ref:
        fp = board.FindFootprintByReference(merge_ref)
        if fp is not None:
            c = fp.GetPosition()
            skip.append((c.x, c.y, pcbnew.FromMM(merge_r)))

    def _in_merge(t):
        for cx, cy, r in skip:
            p = t.GetPosition() if t.GetClass() == "PCB_VIA" else t.GetStart()
            q = t.GetPosition() if t.GetClass() == "PCB_VIA" else t.GetEnd()
            mx, my = (p.x + q.x) / 2.0, (p.y + q.y) / 2.0
            if ((mx - cx) ** 2 + (my - cy) ** 2) ** 0.5 < r:
                return True
        return False

    out = {}
    for t in board.GetTracks():
        name = t.GetNetname()
        if not name:
            continue
        if _in_merge(t):
            continue
        total, per_layer, vias = out.get(name, (0.0, {}, 0))
        if t.GetClass() == "PCB_VIA":
            vias += 1
        else:
            mm = pcbnew.ToMM(t.GetLength())
            total += mm
            layer = board.GetLayerName(t.GetLayer())
            per_layer[layer] = per_layer.get(layer, 0.0) + mm
        out[name] = (total, per_layer, vias)
    return out


def check(stem):
    board = pcbnew.LoadBoard(stem + ".kicad_pcb")
    notes = json.load(open(stem + ".board.json", encoding="utf-8"))
    lens = net_lengths(board)
    groups = notes.get("match", [])
    if not groups:
        print("%s: no matched-length groups declared -- nothing to check"
              % os.path.basename(stem))
        return 0

    # ⚠ SKEW IS MEANINGLESS ON AN UNROUTED BOARD, and reporting it anyway is actively
    # misleading. The first real run printed "ULPI skew 56.08 mm" -- alarming, and
    # nonsense: four of the twelve nets were 1 mm stubs the router had not finished, so
    # the number was measuring incompleteness, not mismatch. Say which it is.
    board.BuildConnectivity()
    try:
        rn = board.GetConnectivity().GetUnconnectedCount(False)
    except TypeError:          # the signature gained aVisibleOnly somewhere in KiCad 9/10
        rn = board.GetConnectivity().GetUnconnectedCount()
    if rn:
        print("⚠ %s has %d unconnected item(s): the board is NOT fully routed, so the "
              "lengths below measure how far the router got, not how well matched the "
              "groups are. Finish routing before reading them as skew.\n"
              % (os.path.basename(stem), rn))

    bad = 0
    for g in groups:
        # a group measured through a pad-merge connector says so; see net_lengths
        if g.get("merge_at"):
            lens = net_lengths(board, g["merge_at"], g.get("merge_r", 4.0))
        else:
            lens = net_lengths(board)
        nets = g["nets"]
        missing = [n for n in nets if n not in lens]
        if missing:
            print("FAIL %-10s nets carry no copper at all: %s"
                  % (g["name"], ", ".join(missing)))
            print("     (%s)" % g["why"])
            bad += 1
            continue
        ls = {n: lens[n][0] for n in nets}
        skew = max(ls.values()) - min(ls.values())
        ok = skew <= g["max_skew_mm"] + 1e-9
        print("%s %-10s skew %6.2f mm (budget %5.2f)  %s"
              % ("ok  " if ok else "FAIL", g["name"], skew, g["max_skew_mm"],
                 "%.1f..%.1f mm over %d nets" % (min(ls.values()), max(ls.values()),
                                                 len(nets))))
        if not ok:
            print("     (%s)" % g["why"])
            for n in sorted(ls, key=ls.get):
                print("       %-12s %6.2f mm" % (n, ls[n]))
            bad += 1
        # ⚠ A PAIR THAT SPLITS ACROSS LAYERS IS NOT A PAIR. Differential impedance is
        # a property of two conductors' geometry RELATIVE TO EACH OTHER; put one on
        # F.Cu and the other on In2.Cu and the number the stack-up was designed for
        # stops describing anything. DRC has no opinion about this, and it is exactly
        # the kind of thing an autorouter does when a direct path is congested.
        if g.get("same_layer"):
            layersets = {n: frozenset(lens[n][1]) for n in nets}
            if len(set(layersets.values())) != 1:
                print("FAIL %-10s the group does not share a layer set:" % g["name"])
                for n in nets:
                    print("       %-12s %s" % (n, ", ".join(sorted(layersets[n]))))
                print("     (%s)" % g["why"])
                bad += 1
        if g.get("max_vias") is not None:
            for n in nets:
                if lens[n][2] > g["max_vias"]:
                    print("FAIL %-10s %s has %d vias (budget %d) -- every via on a "
                          "high-speed net is an impedance discontinuity"
                          % (g["name"], n, lens[n][2], g["max_vias"]))
                    bad += 1
    print("\n%s: %d group(s) checked, %d problem(s)"
          % (os.path.basename(stem), len(groups), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(check(os.path.abspath(sys.argv[1])))
