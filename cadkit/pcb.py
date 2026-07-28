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


# ════════════════════════════════════════════════════════════════════════════
# JST XH — 2.5 mm pitch wire-to-board connector (dummies for clearance work)
# ════════════════════════════════════════════════════════════════════════════
# Every number below is off JST's own XH drawing (eXH.pdf, "Header / Top entry
# type" + "Housing" tables), not a catalogue summary:
#   header B*B-XH-A   A = 2.5(n-1)   B = A + 4.9   body 5.75 across the pin row
#                     7.0 tall above the board, posts □0.64 with a 3.4 tail
#                     BELOW the board, pin row 2.0 in from one long side edge
#   housing XHP-n     B = A + 4.8, 5.7 wide, 7.5 tall
#   MATED height above the board = 9.8 ("assembled board height", p.1) — that
#                     is the number that decides clearance, not the 7.0.
# The pin ROW is the datum (y=0), because that is what a PCB footprint is
# placed by; the body straddles it 2.0 / 3.75, so the connector is NOT
# symmetric about its pins and which way it faces matters for clearance.
XH_PITCH      = 2.5
XH_BODY_W     = 5.75      # across the pin row
XH_BODY_H     = 7.0       # header alone, above the board's top face
XH_MATED_H    = 9.8       # header + XHP-n plug seated on it
XH_PLUG_W     = 5.7
XH_POST       = 0.64      # square post
XH_POST_TAIL  = 3.4       # post protrusion BELOW the board
XH_HOLE_D     = 1.0       # PCB hole (drawing: 3+ circuits Ø0.9 +0.1/-0)
XH_ROW_OFF    = 2.0       # pin row in from one long side edge of the body


def xh_length(n):
    """Header overall length B (mm) for an n-circuit B*B-XH-A."""
    return XH_PITCH * (n - 1) + 4.9


def jst_xh_header(n, *, mated=False, tails=True, flip=False):
    """Dummy JST B<n>B-XH-A top-entry header, for clearance checking.

    Frame: the board's TOP FACE is z=0 and the connector rises +Z; the PIN ROW
    is on y=0 and the part is centred on x=0. `mated=True` returns the envelope
    with an XHP-n plug seated (9.8 tall) instead of the bare 7.0 header — use it
    for clearance, since a connector nobody can plug into is not a fit. `tails`
    adds the □0.64 posts protruding 3.4 BELOW z=0, which on a board mounted
    against something matters more than the body does. `flip` puts the wide
    side of the body on -y instead of +y (the connector is not symmetric about
    its pins, so this is a real choice at layout, not a cosmetic one)."""
    L = xh_length(n)
    s = -1.0 if flip else 1.0
    y0, y1 = -XH_ROW_OFF, XH_BODY_W - XH_ROW_OFF
    if flip:
        y0, y1 = -y1, -y0
    h = XH_MATED_H if mated else XH_BODY_H
    body = _block(L, y1 - y0, h, 0.0, (y0 + y1) / 2, 0.0)
    if not tails:
        return body
    for i in range(n):
        x = (i - (n - 1) / 2.0) * XH_PITCH
        body = body.union(_block(XH_POST, XH_POST, XH_POST_TAIL, x, 0.0, -XH_POST_TAIL))
    return body


# ── SIDE-ENTRY XH (S*B-XH-A / S*B-XH-SM4-TB) ────────────────────────────────
# Same drawing, "Header / Side entry type" + "Header / SMT type": the plug mates
# PARALLEL to the board instead of off it, so the clearance that matters is a
# horizontal RUN-IN, not headroom. Off the tables:
#   THT S*B-XH-A      B = 2.5(n-1) + 4.9 , overall depth C = 9.2 or 7.6
#   SMT S*B-XH-SM4-TB B = 2.5(n-1) + 7.5 (S4B = 15.0), and being SMT it has NO
#                     post tails through the board — which is the whole reason to
#                     reach for it when the far face of the board is spoken for.
# Both stand 7.0 off the board with a 4.5 mouth and a 6.1 body depth.
XH_SIDE_H     = 7.0       # height above the board
XH_SIDE_D     = 6.1       # body depth along the mating axis
XH_SIDE_MOUTH = 4.5       # shroud opening height


def xh_side_length(n, *, smt=True):
    """Overall length B (mm) of an n-circuit side-entry XH header."""
    return XH_PITCH * (n - 1) + (7.5 if smt else 4.9)


def jst_xh_side_header(n, *, smt=True, mated=False, plug_run=7.5):
    """Dummy side-entry XH header (S<n>B-XH-SM4-TB by default).

    Frame: the board's top face is z=0 and the connector rises +Z; the MOUTH
    FACE is y=0 with the body extending +Y, so the plug arrives travelling +Y
    and `mated=True` adds its envelope on -y. Centred on x=0 along the row.

    `plug_run` is the plug's reach beyond the mouth. It is an ENVELOPE, not a
    drawing figure — JST publishes the XHP-n housing but not its mated
    projection for side entry, so this is the housing's own 7.5 taken at face
    value with no credit for shroud engagement. Deliberately pessimistic: the
    number exists to reserve room, and reserving too much is the safe error."""
    L = xh_side_length(n, smt=smt)
    body = _block(L, XH_SIDE_D, XH_SIDE_H, 0.0, XH_SIDE_D / 2, 0.0)
    if mated:
        body = body.union(_block(L, plug_run, XH_SIDE_H, 0.0, -plug_run / 2, 0.0))
    return body
