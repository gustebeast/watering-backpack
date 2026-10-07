"""Read a ROUTED KiCad board back and write the geometry the CAD needs: <board>.geom.json.

RUN THIS UNDER KiCad's OWN PYTHON -- it needs `pcbnew`, and nothing else:

    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/kicad_geom.py elec/out/controller
    ... cadkit/kicad_geom.py --out elec/geom elec/out/controller elec/out/panel

Each argument is a board STEM (`<stem>.kicad_pcb` is read). The file lands in `--out`,
or by default in a `geom/` folder BESIDE the stem's own folder (elec/out/x -> elec/geom/
x.geom.json). COMMIT THAT FOLDER: the CAD builds from it, and a checkout without KiCad has
to be able to. Run it at the end of every route so the file is rewritten whenever the
board is -- a stale geom file is a CAD that draws last week's board.

`cadkit/board_geom.py` is the other half (CadQuery, no KiCad); it reads these files.
This module deliberately imports neither CadQuery nor the rest of cadkit, so it runs in
KiCad's interpreter as a plain script.

WHY IT EXISTS. Every other step in a board pipeline flows ONE way: a netlist and
placements go in, a routed board comes out. If nothing reads the finished board back,
the CAD models it from the numbers layout was GIVEN -- and a copy checked against its
source always passes. This is the other direction: what KiCad actually placed.

FRAME: board-centred millimetres (the centre of the Edge.Cuts bounding box), +X right,
+Y UP -- KiCad's Y is down; flipped here so the numbers are the CAD's.

    outline_mm     [w, l] of the Edge.Cuts bounding box, stroke width taken off
    outline_poly   the outline itself (a board with a mounting ear is an L, not a box)
    holes          the cutouts inside it, each a polygon
    thickness_mm   the stackup thickness
    footprints[]   ref, fpid, x/y (the footprint ORIGIN), pads_xy (the pad CENTROID --
                   they differ for asymmetric pads: 0.228 mm on a SOT-23-5, 3.75 on a JST
                   header), rot, side, fab (the F.Fab BODY box: [x0, x1, y0, y1]), crtyd,
                   tht (the box round its through-hole pads, or null for pure SMD)
    silk[]         the lettering the fab prints: text, side, centre, size, angle, box.
                   Board-level text (the name, test-pad nets, pinouts, and the
                   designators kicad_silk lays with `silk_refs`), plus -- marked
                   "kind": "ref" -- every footprint designator KiCad itself shows in ink

A footprint with no F.Fab outline gets `fab: null`; the CAD then has to say what to do
about it rather than quietly use the courtyard, which is the keep-out and not the part.
"""
import json
import os
import sys

import pcbnew


def _bbox(items, cx, cy):
    xs, ys = [], []
    for it in items:
        b = it.GetBoundingBox()
        xs += [b.GetLeft() / 1e6 - cx, b.GetRight() / 1e6 - cx]
        ys += [-(b.GetTop() / 1e6 - cy), -(b.GetBottom() / 1e6 - cy)]
    if not xs:
        return None
    return [round(min(xs), 3), round(max(xs), 3), round(min(ys), 3), round(max(ys), 3)]


def _layer_bbox(fp, layer, cx, cy):
    return _bbox([it for it in fp.GraphicalItems() if it.GetLayerName() == layer], cx, cy)


def _body_bbox(fp, layer, cx, cy):
    """The part's BODY on its fab layer: the drawn outline, and nothing else that has come
    to live there.

    Two other things do. The designator, where a dense board keeps it off the silkscreen
    (pcbflow's `refs_on_fab`), is text and may sit beside the part. And silkscreen that
    would have printed on pads (`strip_silk`) is moved to the fab layer rather than
    deleted: a polarity bar, a bracket round the lands. A box round all of it is not the
    part -- an 0603 LED came out 2.4 long and a SOD-523 2.65 tall, and the CAD-against-
    board probe (cadkit.board_check, the end probes) then reported 32 honest bodies as
    drawn short.

    Text is left out by class. Moved silkscreen is told from the body by its stroke: a
    library footprint draws its fab outline in 0.10 and its silkscreen in 0.12, so of the
    shapes on the layer only the THINNEST strokes are the body. A footprint drawn in one
    width throughout (most hand-made ones) keeps every shape."""
    shapes = [it for it in fp.GraphicalItems()
              if it.GetLayerName() == layer and it.GetClass() == "PCB_SHAPE"]
    if not shapes:
        return None
    drawn = [it.GetWidth() for it in shapes if it.GetWidth() > 0]      # 0 is a fill
    thin = min(drawn) if drawn else 0
    return _bbox([it for it in shapes if it.GetWidth() <= thin + 1000], cx, cy)


def _tht_bbox(fp, cx, cy):
    """Bounding box of this footprint's THROUGH-HOLE pads, or None if it is pure SMD.
    Their tails are geometry below the board that a CAD model otherwise leaves out."""
    return _bbox([p for p in fp.Pads() if p.GetAttribute() in
                  (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)], cx, cy)


def read(stem):
    """The geometry dict for `<stem>.kicad_pcb` (see the module docstring for its keys)."""
    board = pcbnew.LoadBoard(stem + ".kicad_pcb")
    edge = board.GetBoardEdgesBoundingBox()
    cx = (edge.GetLeft() + edge.GetRight()) / 2e6
    cy = (edge.GetTop() + edge.GetBottom()) / 2e6
    # the Edge.Cuts LINE has width; the board's edge is its centre, so take the stroke
    # back off
    lw = 0.0
    for d in board.GetDrawings():
        if d.GetLayerName() == "Edge.Cuts":
            lw = max(lw, d.GetWidth() / 1e6)
    out = {
        "outline_mm": [round(edge.GetWidth() / 1e6 - lw, 3),
                       round(edge.GetHeight() / 1e6 - lw, 3)],
        "thickness_mm": round(board.GetDesignSettings().GetBoardThickness() / 1e6, 3),
        "footprints": [],
    }
    polys = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(polys, True)

    def _pts(chain):
        return [[round(chain.CPoint(i).x / 1e6 - cx, 3),
                 round(-(chain.CPoint(i).y / 1e6 - cy), 3)]
                for i in range(chain.PointCount())]
    out["outline_poly"] = _pts(polys.Outline(0))
    out["holes"] = [_pts(polys.Hole(0, h)) for h in range(polys.HoleCount(0))]
    for fp in board.GetFootprints():
        p = fp.GetPosition()
        pads = list(fp.Pads())
        pc = ([round(sum(q.GetPosition().x for q in pads) / len(pads) / 1e6 - cx, 3),
               round(-(sum(q.GetPosition().y for q in pads) / len(pads) / 1e6 - cy), 3)]
              if pads else None)
        back = fp.IsFlipped()
        out["footprints"].append({
            "ref": fp.GetReference(),
            "fpid": fp.GetFPIDAsString(),
            "x": round(p.x / 1e6 - cx, 3),
            "y": round(-(p.y / 1e6 - cy), 3),
            "pads_xy": pc,
            "rot": round(fp.GetOrientationDegrees(), 3),
            "side": "B" if back else "F",
            "fab": _body_bbox(fp, "B.Fab" if back else "F.Fab", cx, cy),
            "crtyd": _layer_bbox(fp, "B.CrtYd" if back else "F.CrtYd", cx, cy),
            "tht": _tht_bbox(fp, cx, cy),
        })
    out["footprints"].sort(key=lambda f: f["ref"])
    # the board's lettering, so the CAD can draw it as a part of its own: what the fab
    # will print, and nothing it will not. Board-level text first (name, test pads,
    # pinouts, kicad_silk's designators); then each footprint's OWN designator where it
    # is visible on a silkscreen layer -- a board that keeps its references in ink shows
    # them in the CAD too. A footprint's outline graphics are not lettering and stay out.
    out["silk"] = []

    def _letter(d, kind=None):
        bb = d.GetBoundingBox()
        lab = {
            "text": d.GetShownText(True) if kind else d.GetText(),
            "side": "F" if d.GetLayerName() == "F.Silkscreen" else "B",
            "x": round(bb.GetCenter().x / 1e6 - cx, 3),
            "y": round(-(bb.GetCenter().y / 1e6 - cy), 3),
            "size": round(d.GetTextHeight() / 1e6, 3),
            "angle": round(d.GetTextAngleDegrees(), 1),
            "box": [round(bb.GetLeft() / 1e6 - cx, 3), round(bb.GetRight() / 1e6 - cx, 3),
                    round(-(bb.GetBottom() / 1e6 - cy), 3),
                    round(-(bb.GetTop() / 1e6 - cy), 3)],
        }
        if kind:
            lab["kind"] = kind
        return lab

    for d in board.GetDrawings():
        if d.GetClass() == "PCB_TEXT" and d.GetLayerName() in ("F.Silkscreen",
                                                               "B.Silkscreen"):
            out["silk"].append(_letter(d))
    for fp in board.GetFootprints():
        r = fp.Reference()
        if r.IsVisible() and r.GetLayerName() in ("F.Silkscreen", "B.Silkscreen"):
            out["silk"].append(_letter(r, "ref"))
    out["silk"].sort(key=lambda t: (t["side"], t.get("kind", ""), t["text"]))
    return out


def default_geom_dir(stem):
    """`geom/` beside the folder the board lives in: elec/out/x -> elec/geom."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(stem))), "geom")


def export(stem, geom_dir=None):
    """Write `<geom_dir>/<board>.geom.json` for `<stem>.kicad_pcb`; returns its path."""
    stem = os.path.abspath(stem)
    geom_dir = geom_dir or default_geom_dir(stem)
    out = read(stem)
    name = os.path.basename(stem)
    dst = os.path.join(geom_dir, name + ".geom.json")
    os.makedirs(geom_dir, exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    missing = [f["ref"] for f in out["footprints"] if f["fab"] is None]
    print("%s.geom.json: %d footprints, board %.2f x %.2f%s"
          % (name, len(out["footprints"]), out["outline_mm"][0], out["outline_mm"][1],
             ("; NO F.Fab body on " + ", ".join(missing)) if missing else ""))
    return dst


def main(argv):
    geom_dir, stems, i = None, [], 0
    while i < len(argv):
        if argv[i] == "--out":
            geom_dir = argv[i + 1]
            i += 2
        elif argv[i].startswith("--out="):
            geom_dir = argv[i].split("=", 1)[1]
            i += 1
        else:
            stems.append(argv[i])
            i += 1
    if not stems:
        raise SystemExit("usage: kicad_geom.py [--out DIR] <board stem> [<stem> ...]")
    for s in stems:
        export(s, geom_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
