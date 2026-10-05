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
            (item["pos"]["x"], item["pos"]["y"]), item["description"].startswith("Track"))


def _free_end(board, net, layer, pos, target):
    """The end of the dangling copper at `pos` that is NEAREST `target`, as (layer, point).

    ⚠ DRC REPORTS A TRACK BY ITS START POINT, NOT BY ITS LOOSE END (pi_cap, 2026-10-04).
    An unconnected "Track [UI_RES_N] on F.Cu" came back positioned at the END OF THE
    HEADER'S EDGE LANE -- the far end of a 4.7 mm escape stub whose free end stood in open
    board -- so the search started in a lane with 0.15 mm to its neighbour, left it with a
    0.05 mm jog at this file's 0.2 mm width, and the one clearance error that made was
    enough for finish.py to throw away a board with nothing else wrong.
    So: walk the copper joined to that point (same net, joined end to end on one layer) and
    start from whichever of its ends is closest to where the net has to go.
    """
    eps = pcbnew.FromMM(0.005)
    lid = board.GetLayerID(layer)
    segs = [t for t in board.GetTracks()
            if t.GetClass() != "PCB_VIA" and t.GetNetname() == net and t.GetLayer() == lid]
    key = lambda p: (round(p.x / eps), round(p.y / eps))
    here = (round(pcbnew.FromMM(pos[0]) / eps), round(pcbnew.FromMM(pos[1]) / eps))
    seen, edge, used = {here}, [here], set()
    while edge:
        k = edge.pop()
        for i, t in enumerate(segs):
            if i in used:
                continue
            a, b = key(t.GetStart()), key(t.GetEnd())
            if k in (a, b):
                used.add(i)
                for q in (a, b):
                    if q not in seen:
                        seen.add(q)
                        edge.append(q)
    if not used:
        return layer, pos
    count = {}
    for i in used:
        for q in (key(segs[i].GetStart()), key(segs[i].GetEnd())):
            count[q] = count.get(q, 0) + 1
    tips = [q for q, n in count.items() if n == 1] or list(count)
    best = min(tips, key=lambda q: (pcbnew.ToMM(int(q[0] * eps)) - target[0]) ** 2
               + (pcbnew.ToMM(int(q[1] * eps)) - target[1]) ** 2)
    return layer, (pcbnew.ToMM(int(best[0] * eps)), pcbnew.ToMM(int(best[1] * eps)))


def _via_starts(board, net, pos, layers):
    """Every (layer, point) the net's copper joined to `pos` offers through a via of its own.

    ⚠ AN END THAT ALREADY HAS ITS ESCAPE VIA WAS SEARCHED FROM THE WRONG LAYER
    (motor_ctrl PG_5V, 2026-10-04). Both ends of that net were declared escapes: a QFN pin
    with a 0.15 mm track to a via 1 mm away, and a regulator pin walled in on the front by
    its own thermal pad and the input copper, with a via beside it. The search started on
    F.Cu at each -- the one layer with no way out, which is why the vias were drawn -- and
    said "no path" for two vias with open board between them on both other layers.
    So: walk the net's copper from `pos` across layers, and offer each via it reaches as a
    start on every routable layer.
    """
    eps = pcbnew.FromMM(0.005)
    key = lambda p: (round(p.x / eps), round(p.y / eps))
    segs = [t for t in board.GetTracks()
            if t.GetClass() != "PCB_VIA" and t.GetNetname() == net]
    vias = {key(t.GetPosition()): t for t in board.GetTracks()
            if t.GetClass() == "PCB_VIA" and t.GetNetname() == net}
    here = (round(pcbnew.FromMM(pos[0]) / eps), round(pcbnew.FromMM(pos[1]) / eps))
    seen, edge, used = {here}, [here], set()
    while edge:
        k = edge.pop()
        for i, t in enumerate(segs):
            if i in used:
                continue
            a, b = key(t.GetStart()), key(t.GetEnd())
            if k in (a, b):
                used.add(i)
                for q in (a, b):
                    if q not in seen:
                        seen.add(q)
                        edge.append(q)
    out = []
    for k in seen:
        if k in vias:
            c = vias[k].GetPosition()
            out += [(L, (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y))) for L in layers]
    return out


def _pad_layer(board, net, layer, pos):
    """The layer an SMD pad at `pos` is really on (a through-hole pad keeps `layer`).

    ⚠ A DRC ITEM FOR A PAD NAMES NO LAYER, and the default here was F.Cu -- so a search
    for a capacitor on the BACK ended on the front, over the pad, and reached it with a
    via drilled into a 0.56 mm land (quality A12, pi_cap 2026-10-04).
    """
    at = pcbnew.VECTOR2I(pcbnew.FromMM(pos[0]), pcbnew.FromMM(pos[1]))
    for f in board.GetFootprints():
        for q in f.Pads():
            if q.GetNetname() == net and q.GetDrillSize().x == 0 and q.HitTest(at):
                return "B.Cu" if q.IsOnLayer(pcbnew.B_Cu) else "F.Cu"
    return layer


def main(stem):
    d = json.load(open(stem + ".finish.drc.json", encoding="utf-8"))
    todo = []
    for u in d.get("unconnected_items", []):
        if len(u.get("items", [])) != 2:
            continue
        (na, la, pa, ta), (nb, lb, pb, tb) = _ends(u["items"][0]), _ends(u["items"][1])
        if na and na == nb:
            todo.append((na, la, pa, ta, lb, pb, tb))
    if not todo:
        print("close_last: nothing to close")
        return 0
    board = pcbnew.LoadBoard(stem + ".kicad_pcb")
    layer_id = {L: board.GetLayerID(L) for L in LAYERS}
    have = {L for L in LAYERS if board.IsLayerEnabled(layer_id[L])}
    plane = set(json.load(open(stem + ".board.json", encoding="utf-8")).get("plane_layers", ()))
    layers = [L for L in LAYERS if L in have and L not in plane]
    made = 0
    for net, la, pa, ta, lb, pb, tb in todo:
        if ta:
            la, pa = _free_end(board, net, la, pa, pb)
        else:
            la = _pad_layer(board, net, la, pa)
        if tb:
            lb, pb = _free_end(board, net, lb, pb, pa)
        else:
            lb = _pad_layer(board, net, lb, pb)
        if la not in layers or lb not in layers:
            print("close_last: %s ends on a layer this does not route (%s / %s)"
                  % (net, la, lb))
            continue
        # a fresh model per net: the copper laid for the previous one is an obstacle now
        board.Save(stem + ".kicad_pcb")
        model = RS.Board(stem, net)
        # ⚠ NO VIA IN A SMALL SOLDERED PAD OF THE NET'S OWN (output_panel PWR_GND,
        # 2026-10-04). Same-net copper is free ground to the search, so it changed layer
        # in the middle of a SOD-523 land -- quality A12's hard finding, "solder wicks down
        # it". Lands under 4 mm2 that carry paste are closed to vias; bigger ones can
        # afford one, and a pad with no paste has nothing to lose.
        model.own_lands = []
        for f in board.GetFootprints():
            for q in f.Pads():
                if (q.GetNetname() != net or q.GetDrillSize().x > 0
                        or not (q.IsOnLayer(pcbnew.F_Paste) or q.IsOnLayer(pcbnew.B_Paste))):
                    continue
                bb = q.GetBoundingBox()
                w, h = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
                if w * h < 4.0:
                    c = bb.GetCenter()
                    model.own_lands.append((pcbnew.ToMM(c.x), pcbnew.ToMM(c.y), w / 2, h / 2))
        # ⚠ TWO GRIDS, COARSE FIRST. maze3d pads its clearance by half a cell diagonal, and
        # at the default 0.15 mm cell that pad alone (0.106) walls in a QFN pin on 0.4 mm
        # pitch: 0.1 + 0.127 + 0.106 = 0.333 against the 0.3 to its neighbour's edge, so
        # the START cell is blocked and the answer is "no path" for a pin with a clear
        # run straight out. A 0.05 mm cell costs nine times the cells and 0.035 of pad.
        # From any via the end's copper already reaches, inner layers first, and from the
        # end as DRC named it last: a via was drawn because the pin's own layer is shut,
        # so the search from the pin is the one most likely to spend its time failing.
        # The fine grid is for a pin in a 0.4 mm row and is tried on that pairing alone --
        # sixteen pairings at nine times the cells was a quarter of an hour of "no path".
        pref = {L: i for i, L in enumerate(("In2.Cu", "B.Cu", "F.Cu"))}
        via_a = sorted(_via_starts(board, net, pa, layers), key=lambda c: pref.get(c[0], 9))
        via_b = sorted(_via_starts(board, net, pb, layers), key=lambda c: pref.get(c[0], 9))
        named = ((la, pa), (lb, pb))
        tries = ([(x, y, RS.MAZE_STEP) for x in via_a for y in via_b]
                 + [(x, named[1], RS.MAZE_STEP) for x in via_a]
                 + [(named[0], y, RS.MAZE_STEP) for y in via_b]
                 + [(named[0], named[1], RS.MAZE_STEP), (named[0], named[1], 0.05)])
        res = None
        for (la, pa), (lb, pb), step in tries:
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
        # ⚠ NO VIA IN A THROUGH-HOLE PAD OF THE SAME NET (pi_cap, 2026-10-04). The search
        # is told which layer each end is on, and a DRC "PTH pad" item names F.Cu whatever
        # layer the route arrives on -- so a path that came in on B.Cu changed layer AT the
        # pin, and the via it dropped there was a second hole drilled through the pin's own
        # (quality A12: hole to hole -0.65 mm). The plated barrel is already the layer
        # change; the two runs meet at its centre without one.
        barrels = [(pcbnew.ToMM(q.GetPosition().x), pcbnew.ToMM(q.GetPosition().y),
                    pcbnew.ToMM(min(q.GetSize().x, q.GetSize().y)) / 2.0)
                   for f in board.GetFootprints() for q in f.Pads()
                   if q.GetNetname() == net and q.GetDrillSize().x > 0]
        # ...and the same for a via the net already has (motor_ctrl PG_5V, 2026-10-04): a
        # search started FROM an escape via on one layer and changing to another beside it
        # dropped its own via 0.02 mm from the first -- two holes 0.28 mm into each other.
        barrels += [(pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y),
                     RS.VIA_D) for t in board.GetTracks()
                    if t.GetClass() == "PCB_VIA" and t.GetNetname() == net]
        vias = [(vx, vy) for vx, vy in vias
                if not any((vx - bx) ** 2 + (vy - by) ** 2 <= br * br
                           for bx, by, br in barrels)]
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
