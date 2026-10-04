"""Close the nets a finished route left open, by maze search on the ROUTED board.

    KiCad-python cadkit/pcbflow/close_last.py elec/out/output_panel

finish.py runs this itself, after the last routing round, on a board with nothing wrong
but unconnected items; it keeps the result only if DRC then reads strictly better.

WHY IT EXISTS (output_panel, 2026-10-02). With the USB-C sockets the board sat exactly at
the router's limit: seven consecutive routes each left ONE or TWO nets open, and never the
same ones -- POT_SDI, then HUB_DN2_DP, then NRST and PWR_GND, then OSC_IN and POT_CS, then
NRST again. Every per-net medicine (a pin escape, more passes, another round) closed the
net it was aimed at and opened a neighbour. That is not a placement fault to find; it is
the last half-percent of a search the router does not finish.

⚠ AND THE ANSWER CANNOT BE WRITTEN DOWN. repair_search.py says why at the top: a repair is
pinned to the routing it was searched against, and BOARD_NOTES["repair_tracks"] has gone
stale that way more than once. So this does not emit coordinates for anyone to paste. It
searches AGAIN, every run, against whatever the router just produced, and nothing it finds
outlives the board it was found on.

It reuses repair_search's obstacle model and maze3d rather than growing a fourth.
"""
from __future__ import annotations

import json
import os
import re
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repair_search as RS   # noqa: E402

LAYERS = ("F.Cu", "In2.Cu", "B.Cu")
WIDTH = 0.2                   # the board's own signal width: a QFN pad row is on 0.4
REACH = 6.0                   # mm of margin round the two ends' bounding box


def _ends(item):
    m = re.search(r"\[([^\]]+)\]", item["description"])
    lay = re.search(r"on ((?:F|B|In\d)\.Cu)", item["description"])
    return (m.group(1) if m else None, lay.group(1) if lay else "F.Cu",
            (item["pos"]["x"], item["pos"]["y"]))


def main(stem):
    d = json.load(open(stem + ".finish.drc.json", encoding="utf-8"))
    todo = []
    for u in d.get("unconnected_items", []):
        if len(u.get("items", [])) != 2:
            continue
        (na, la, pa), (nb, lb, pb) = _ends(u["items"][0]), _ends(u["items"][1])
        if na and na == nb:
            todo.append((na, la, pa, lb, pb))
    if not todo:
        print("close_last: nothing to close")
        return 0
    board = pcbnew.LoadBoard(stem + ".kicad_pcb")
    layer_id = {L: board.GetLayerID(L) for L in LAYERS}
    have = {L for L in LAYERS if board.IsLayerEnabled(layer_id[L])}
    plane = set(json.load(open(stem + ".board.json", encoding="utf-8")).get("plane_layers", ()))
    layers = [L for L in LAYERS if L in have and L not in plane]
    made = 0
    for net, la, pa, lb, pb in todo:
        if la not in layers or lb not in layers:
            print("close_last: %s ends on a layer this does not route (%s / %s)"
                  % (net, la, lb))
            continue
        # a fresh model per net: the copper laid for the previous one is an obstacle now
        board.Save(stem + ".kicad_pcb")
        model = RS.Board(stem, net)
        # ⚠ TWO GRIDS, COARSE FIRST. maze3d pads its clearance by half a cell diagonal, and
        # at the default 0.15 mm cell that pad alone (0.106) walls in a QFN pin on 0.4 mm
        # pitch: 0.1 + 0.127 + 0.106 = 0.333 against the 0.3 to its neighbour's edge, so
        # the START cell is blocked and the answer is "no path" for a pin with a clear
        # run straight out. A 0.05 mm cell costs nine times the cells and 0.035 of pad.
        res = None
        for step in (RS.MAZE_STEP, 0.05):
            res = RS.maze3d(model, layers, pa, la, pb, lb, w=WIDTH, step=step, reach=REACH)
            if res is not None:
                break
        if res is None:
            print("close_last: %s -- no path between (%.2f, %.2f) and (%.2f, %.2f)"
                  % (net, pa[0], pa[1], pb[0], pb[1]))
            continue
        runs, vias = res
        code = board.GetNetcodeFromNetname(net)
        # ⚠ TWO VIAS A TENTH OF A MILLIMETRE APART ARE ONE VIA. The maze can
        # return a layer change that immediately reverses -- F.Cu down to B.Cu
        # and back up, with a B.Cu run between them shorter than the drill. On
        # the watering-backpack board that put two LEVEL vias 0.067 mm apart and
        # two GATE_A vias 0.242 mm apart, against a 0.25 mm hole-to-hole
        # minimum. DRC reports it as hole_to_hole at "actual 0.0000 mm" -- the
        # holes do not merely crowd, they OVERLAP -- and grades it a WARNING, so
        # the error count stays at zero and nobody looks. A fab either rejects
        # the drill file or drills one ragged hole.
        #
        # So the via list is merged first and the track ends are snapped onto
        # whatever they merged into: one via still joins F.Cu to B.Cu at that
        # point, which is all the pair ever did, and the short run between them
        # collapses to nothing and is dropped. Snapping can only move a point by
        # less than the merge radius, and finish.py keeps this whole pass only
        # if DRC comes out strictly better, so a snap that hurt would be thrown
        # away rather than shipped.
        merge_r = RS.VIA_DRILL + 0.25
        # Seeded with the vias ALREADY on this net, because the hole the new one
        # crowds need not be another new one. The first version of this merged
        # only within close_last's own list and left a LEVEL via 0.0673 mm from
        # one the ROUTER had put down -- same violation, different neighbour.
        # Snapping onto an existing via is better than merging two new ones: the
        # layer transition is already there and already in the zones' pour.
        keep_v, snap = [], {}
        for _t in board.GetTracks():
            if isinstance(_t, pcbnew.PCB_VIA) and _t.GetNetname() == net:
                _p = _t.GetPosition()
                keep_v.append((pcbnew.ToMM(_p.x), pcbnew.ToMM(_p.y)))
        n_existing = len(keep_v)

        def _snap(q):
            for k in keep_v:
                if (q[0] - k[0]) ** 2 + (q[1] - k[1]) ** 2 < merge_r ** 2:
                    return k
            return None

        for q in vias:
            k = _snap(q)
            if k is None:
                keep_v.append(q)
            else:
                snap[(round(q[0], 6), round(q[1], 6))] = k
        vias = keep_v[n_existing:]
        if len(vias) != len(res[1]):
            print("close_last: %s -- merged %d via(s) that would have overlapped "
                  "a neighbouring hole (min %.2f mm)"
                  % (net, len(res[1]) - len(vias), merge_r))

        def _pt(q):
            return snap.get((round(q[0], 6), round(q[1], 6)), q)

        length = 0.0
        for L, pts in runs:
            pts = [_pt(q) for q in pts]
            for q0, q1 in zip(pts, pts[1:]):
                if q0 == q1:
                    continue
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(q0[0]), pcbnew.FromMM(q0[1])))
                t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(q1[0]), pcbnew.FromMM(q1[1])))
                t.SetWidth(pcbnew.FromMM(WIDTH))
                t.SetLayer(layer_id[L])
                t.SetNetCode(code)
                board.Add(t)
                length += ((q1[0] - q0[0]) ** 2 + (q1[1] - q0[1]) ** 2) ** 0.5
        # ⚠ ONE VIA PER POINT. The maze can hand back a layer change that
        # immediately reverses -- F.Cu down to B.Cu and straight back up at the
        # same coordinate, with the zero-length B.Cu run between them already
        # dropped by the `q0 == q1` skip above. Emitted literally that is TWO
        # drills in one hole: DRC grades it hole_to_hole at 0.0000 mm against a
        # 0.2500 mm minimum, and because hole_to_hole is a WARNING the error
        # count stays at zero and nobody looks. It showed up on the
        # watering-backpack board the first time close_last had to reach a
        # bring-up pad (LEVEL, F/B/F, "2 via(s)").
        #
        # Collapsing to one via is not a compromise: a single via already joins
        # F.Cu and B.Cu at that point, which is the whole of what the pair did.
        for vx, vy in vias:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(vx), pcbnew.FromMM(vy)))
            v.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(RS.VIA_D))
            v.SetDrill(pcbnew.FromMM(RS.VIA_DRILL))
            v.SetNetCode(code)
            board.Add(v)
        made += 1
        print("close_last: %s closed with %.2f mm over %s and %d via(s)"
              % (net, length, "/".join(L for L, _p in runs), len(vias)))
    board.Save(stem + ".kicad_pcb")
    return made


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]))
