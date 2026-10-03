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
        length = 0.0
        for L, pts in runs:
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
