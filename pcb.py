"""PCB mounting — a 3-wall drop-in cradle retained by ONE screw.

The plastic does the work: three walls locate the board in X-Y and take the insertion
load, corner pads carry it in Z (clear of bottom-side components), so a single screw only
has to stop lift-out / back-out. NO snap/flexure install (a deliberate rule -- plastic
snaps are not trusted). The 4th edge is left OPEN for the board's edge connectors/wires.

Built with the mounting surface at z=0 (base-plate top) and the board footprint centred on
X-Y; the board's underside sits at z=`standoff` above the base, so bottom components clear.
The screw enters from +Z through a board mounting hole and threads DOWN into a boss; its
anchor is the shared `cut_anchor` (Ø2.2 self-tap + Ø3.3 heat-set-insert pocket fallback), so
a serviced board can graduate to an insert with no reprint.

    from cadkit.pcb import pcb_cradle, pcb_board
    cradle = pcb_cradle(25.0, 18.0, screw_xy=(9.0, 6.0))   # board WxL, one mounting hole
"""
from __future__ import annotations

import cadquery as cq

from .fasteners import M2, cut_anchor

_EDGES = {"+x", "-x", "+y", "-y"}


def _block(w, l, h, cx, cy, z0):
    return cq.Workplane("XY").add(cq.Solid.makeBox(w, l, h, cq.Vector(cx - w / 2, cy - l / 2, z0)))


def _cyl(d, h, cx, cy, z0):
    return cq.Workplane("XY").add(cq.Solid.makeCylinder(d / 2, h, cq.Vector(cx, cy, z0)))


def pcb_cradle(board_w, board_l, screw_xy, *, board_t=1.6, standoff=2.5, wall_t=1.6,
               wall_over=0.8, clr=0.3, pad=3.2, base_t=None, open_edge="+x", spec=M2):
    r"""A 3-wall drop-in PCB cradle. `board_w` x `board_l` = board footprint (X x Y),
    centred on the origin; board bottom rests at z=`standoff`. Walls (thickness `wall_t`)
    rise on the THREE edges other than `open_edge` at `clr` fit to locate the board and
    stand `wall_over` above its top face. Corner pads (`pad` square) carry the board in Z.
    A boss under `screw_xy` (a board mounting-hole position, from the board centre) takes
    ONE screw whose anchor runs `spec.anchor_min_wall` deep. A base plate (the mounting
    area, thickness `base_t`, default sized so the screw anchor just fits above z=0) ties
    walls, pads and boss; fuse it onto the parent (chassis/housing) or print standalone.
    Returns the cradle solid. `open_edge` in {'+x','-x','+y','-y'} = the wall-free edge."""
    assert open_edge in _EDGES, f"open_edge must be one of {_EDGES}"
    hw, hl = board_w / 2.0, board_l / 2.0
    board_top = standoff + board_t
    wall_h = board_top + wall_over
    inner_x, inner_y = hw + clr, hl + clr          # wall inner faces (clr fit to the board)
    out_x, out_y = inner_x + wall_t, inner_y + wall_t
    if base_t is None:
        base_t = max(1.2, spec.anchor_min_wall - standoff)   # screw anchor reaches z >= -base_t

    solid = _block(2 * out_x, 2 * out_y, base_t, 0.0, 0.0, -base_t)   # base plate = mounting area
    walls = {
        "-x": (wall_t, 2 * out_y, -(inner_x + wall_t / 2), 0.0),
        "+x": (wall_t, 2 * out_y, +(inner_x + wall_t / 2), 0.0),
        "-y": (2 * out_x, wall_t, 0.0, -(inner_y + wall_t / 2)),
        "+y": (2 * out_x, wall_t, 0.0, +(inner_y + wall_t / 2)),
    }
    for edge, (w, l, cx, cy) in walls.items():
        if edge != open_edge:
            solid = solid.union(_block(w, l, wall_h, cx, cy, 0.0))
    for sx in (-1, 1):                              # corner support pads (Z rest, clears bottom parts)
        for sy in (-1, 1):
            solid = solid.union(_block(pad, pad, standoff, sx * (hw - pad / 2), sy * (hl - pad / 2), 0.0))
    bx, by = screw_xy                              # retention boss under the board hole
    solid = solid.union(_cyl(pad + 1.5, standoff, bx, by, 0.0))
    solid = cut_anchor(spec, solid, (bx, by, standoff), (0, 0, -1), spec.anchor_min_wall)
    return solid


def pcb_board(board_w, board_l, *, board_t=1.6, standoff=2.5):
    """Fit-check dummy of the seated board (a plain slab at the rest plane) for the assembly."""
    return _block(board_w, board_l, board_t, 0.0, 0.0, standoff)
