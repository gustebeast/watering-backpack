"""PCB mounting — a drop-in cradle retained by ONE screw.

The plastic does the work: walls locate the board in X-Y and take the insertion load,
corner pads carry it in Z (clear of bottom-side components), so a single screw only has to
stop lift-out / back-out. NO snap/flexure install (a deliberate rule -- plastic snaps are
not trusted). One edge may be left OPEN for edge connectors/wires, or none.

TWO WAYS TO PLACE THAT ONE SCREW:
  * `screw_xy`  -- THROUGH a board mounting hole, down into a boss under it (the original).
  * `hold_edge` -- BESIDE the board (preferred). The screw passes the board's edge and only
    its HEAD reaches over the board top, so the plastic captures every direction but +Z
    and the head closes +Z. Nothing goes through the board: a purchased board with small
    holes (or none) still takes the project's one M4, and the board needs no hole at all.

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

from .fasteners import M2, M4, M4_BUTTON_HEAD_D, cut_anchor

_EDGES = {"+x", "-x", "+y", "-y"}


# FR4 is 1.6 mm — the industry-standard 2-layer/4-layer board thickness, and a
# PHYSICAL constant, not a print one. It must never be tied to the nozzle: change
# the printer and FR4 does not move. Exported because consumers were repeating it.
PCB_T = 1.6


def _block(w, l, h, cx, cy, z0):
    return cq.Workplane("XY").add(cq.Solid.makeBox(w, l, h, cq.Vector(cx - w / 2, cy - l / 2, z0)))


def _cyl(d, h, cx, cy, z0):
    return cq.Workplane("XY").add(cq.Solid.makeCylinder(d / 2, h, cq.Vector(cx, cy, z0)))


def pcb_hold_xy(board_w, board_l, hold_edge, *, hold_at=0.0, clr=0.3, spec=M4):
    """Axis (x, y) of a SIDE hold-down screw for a board centred on the origin: just outside
    `hold_edge`, `hold_at` along it. The shank's clearance hole comes no closer to the board
    than the board's own `clr` fit gap, so the screw passes BESIDE the board and only its
    head reaches over. Use it to place the assembly's dummy screw where the cradle bored."""
    assert hold_edge in _EDGES, f"hold_edge must be one of {_EDGES}"
    hw, hl = board_w / 2.0, board_l / 2.0
    off = clr + spec.shaft_clr_d / 2.0
    if hold_edge in ("+x", "-x"):
        assert abs(hold_at) <= hl, f"hold_at {hold_at} runs off the {hold_edge} edge (half-length {hl})"
        return ((1.0 if hold_edge == "+x" else -1.0) * (hw + off), hold_at)
    assert abs(hold_at) <= hw, f"hold_at {hold_at} runs off the {hold_edge} edge (half-length {hw})"
    return (hold_at, (1.0 if hold_edge == "+y" else -1.0) * (hl + off))


def pcb_hold_overlap(*, clr=0.3, spec=M4, head_d=M4_BUTTON_HEAD_D):
    """How far the side hold-down's head reaches over the board edge (mm)."""
    return head_d / 2.0 - (clr + spec.shaft_clr_d / 2.0)


def pcb_cradle(board_w, board_l, screw_xy=None, *, board_t=PCB_T, standoff=2.5, wall_t=1.6,
               wall_over=0.8, clr=0.3, pad=3.2, base_t=None, open_edge="+x", spec=M2,
               hold_edge=None, hold_at=0.0, hold_spec=M4, head_d=M4_BUTTON_HEAD_D,
               min_overlap=1.0):
    r"""A drop-in PCB cradle. `board_w` x `board_l` = board footprint (X x Y), centred on
    the origin; board bottom rests at z=`standoff`. Walls (thickness `wall_t`) rise on every
    edge except `open_edge` (None = all four) at `clr` fit to locate the board and stand
    `wall_over` above its top face. Corner pads (`pad` square) carry the board in Z. A base
    plate (the mounting area, thickness `base_t`, default sized so the screw anchor just fits
    above z=0) ties it together; fuse it onto the parent (chassis/housing) or print standalone.

    Retention is ONE screw -- give exactly one of:
      `screw_xy`  a board MOUNTING-HOLE position (from the board centre): a boss under it
                  takes a `spec` screw down through the board.
      `hold_edge` in {'+x','-x','+y','-y'}: a `hold_spec` screw BESIDE that edge, `hold_at`
                  along it (see pcb_hold_xy). Its boss stands on the mounting surface with
                  its top FLUSH with the board's underside -- so it is also the pad under
                  that edge, and the head clamps the board onto it -- and the wall there is
                  notched for the head. Refuses a head that reaches less than `min_overlap`
                  over the board: a head that barely laps the edge is not retention.
    Returns the cradle solid."""
    assert open_edge is None or open_edge in _EDGES, f"open_edge must be None or one of {_EDGES}"
    if (screw_xy is None) == (hold_edge is None):
        raise ValueError("pcb_cradle: give exactly ONE retention -- screw_xy (a screw through a "
                         "board hole) or hold_edge (a screw beside the board)")
    if hold_edge is not None and hold_edge == open_edge:
        raise ValueError(f"pcb_cradle: hold_edge {hold_edge} is the open edge -- the head's "
                         "notch needs a wall to sit in, and the board a stop that way")
    hw, hl = board_w / 2.0, board_l / 2.0
    board_top = standoff + board_t
    wall_h = board_top + wall_over
    inner_x, inner_y = hw + clr, hl + clr          # wall inner faces (clr fit to the board)
    out_x, out_y = inner_x + wall_t, inner_y + wall_t
    anchor = hold_spec if hold_edge is not None else spec
    if base_t is None:
        base_t = max(1.6, anchor.anchor_min_wall - standoff)  # screw anchor reaches z >= -base_t; floor at
                                                              # 2 beads (0.8 nozzle) so the base isn't sub-1.6

    solid = _block(2 * out_x, 2 * out_y, base_t, 0.0, 0.0, -base_t)   # base plate = mounting area
    if hold_edge is not None:
        overlap = pcb_hold_overlap(clr=clr, spec=hold_spec, head_d=head_d)
        if overlap < min_overlap - 1e-9:
            raise ValueError(f"pcb_cradle: the O{head_d} head reaches only {overlap:.2f} over the board "
                             f"edge (clr {clr} + {hold_spec.name} clearance r {hold_spec.shaft_clr_d / 2}) "
                             f"-- under min_overlap {min_overlap}")
        hx, hy = pcb_hold_xy(board_w, board_l, hold_edge, hold_at=hold_at, clr=clr, spec=hold_spec)
        # boss from the mounting surface up to the board's UNDERSIDE: a pad under that edge
        solid = solid.union(_cyl(hold_spec.boss_od, base_t + standoff, hx, hy, -base_t))
    walls = {
        "-x": (wall_t, 2 * out_y, -(inner_x + wall_t / 2), 0.0),
        "+x": (wall_t, 2 * out_y, +(inner_x + wall_t / 2), 0.0),
        "-y": (2 * out_x, wall_t, 0.0, -(inner_y + wall_t / 2)),
        "+y": (2 * out_x, wall_t, 0.0, +(inner_y + wall_t / 2)),
    }
    for edge, (w, l, cx, cy) in walls.items():
        if edge != open_edge:
            solid = solid.union(_block(w, l, wall_h, cx, cy, 0.0))
    if hold_edge is not None:                      # notch the wall for the head (above the board's underside only)
        solid = solid.cut(_cyl(head_d + 2 * clr, wall_h - standoff + 1.0, hx, hy, standoff))
    for sx in (-1, 1):                              # corner support pads (Z rest, clears bottom parts)
        for sy in (-1, 1):
            solid = solid.union(_block(pad, pad, standoff, sx * (hw - pad / 2), sy * (hl - pad / 2), 0.0))
    if screw_xy is not None:
        bx, by = screw_xy                          # retention boss under the board hole
        solid = solid.union(_cyl(pad + 1.5, standoff, bx, by, 0.0))
        return cut_anchor(spec, solid, (bx, by, standoff), (0, 0, -1), spec.anchor_min_wall)
    return cut_anchor(hold_spec, solid, (hx, hy, standoff), (0, 0, -1), hold_spec.anchor_min_wall)


def pcb_board(board_w, board_l, *, board_t=PCB_T, standoff=2.5):
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


# ── SIDE-ENTRY PH (S*B-PH-SM4-TB) ───────────────────────────────────────────
# JST's 2.0 mm PH series, SMT side entry. Reached for where an XH will not fit:
# XH's SMT side-entry line stops at 4 way, so a board that needs one connector
# carrying more than four circuits AND surface mount AND side entry has no XH
# option at all (the lever sensor board's trunk is the case that forced this).
#
# PROVENANCE: JST's own ePH drawing (jst-mfg.com/product/pdf/eng/ePH.pdf, read
# 2026-09-21 by RENDERING the pages -- the PDF's text layer uses a shifted font
# map, which is why these were placeholders borrowed from XH until now):
#   p.4 "Header (SMT type) / Side entry": B = 2.0(n-1) + 5.9 (S8B 19.9),
#       height 5.5 above the board, body 6.0 deep, (2.6) solder tabs behind it
#   p.2 "Assembly layout / Side entry": mated pair (9.6) long overall, (5.5) tall
#       -> the plug stands 9.6 - 6.0 = 3.6 proud of the mouth
#   p.3 "Housing": PHR-n is 6.85 long along the mating axis x 4.5 thick
#   (the TOP-entry B*B-PH-SM4-TB is a different part: 6.6 tall, 5.0 deep.)
PH_PITCH      = 2.0
PH_SIDE_D     = 6.0       # body depth along the mating axis (JST p.4)
PH_TAB_D      = 2.6       # solder tabs behind the body, flat on the board (JST p.4)
PH_SIDE_H     = 5.5       # height above the board (JST p.4; the mated pair too, p.2)
PH_ROW_OFF    = 0.40      # pad row back from the mouth face (KiCad footprint)
PH_PLUG_RUN   = 9.6 - PH_SIDE_D   # 3.6: the mated plug past the mouth (JST p.2)


def ph_side_length(n):
    """Overall body length (mm) of an n-circuit S<n>B-PH-SM4-TB."""
    return PH_PITCH * (n - 1) + 5.9     # JST p.4, dimension B


def jst_ph_side_header(n, *, mated=False, plug_run=PH_PLUG_RUN):
    """Dummy side-entry SMT PH header (S<n>B-PH-SM4-TB).

    Frame matches jst_xh_side_header so the two are interchangeable at a call
    site: the board's top face is z=0 and the connector rises +Z; the MOUTH FACE
    is y=0 with the body extending +Y, so the plug arrives travelling +Y and
    `mated=True` adds its envelope on -y. Centred on x=0 along the row.

    SMT, so there are NO post tails below the board -- which is usually the
    reason this part is chosen over a through-hole side-entry XH."""
    L = ph_side_length(n)
    body = _block(L, PH_SIDE_D, PH_SIDE_H, 0.0, PH_SIDE_D / 2, 0.0)
    if mated:
        body = body.union(_block(L, plug_run, PH_SIDE_H, 0.0, -plug_run / 2, 0.0))
    return body


# ════════════════════════════════════════════════════════════════════════════
# JST CRIMP HOUSINGS (XHP-n, PHR-n, ZHR-n) AND WHERE THEIR WIRES LEAVE
# ════════════════════════════════════════════════════════════════════════════
# ONE TABLE for the plug a header is mated with, read by three things that must agree:
# the housing drawn in the viewer (jst_housing below, placed by cadkit.web.boards),
# cadkit.board_geom.Boards.plug / wire_exit / way (where each wire leaves each plug) and
# the side-entry SMT headers cadkit.web.parts draws (KiCad's library has no model of
# them, so their pocket is cut from the same numbers and the plug seats in it).
#
# WHERE EACH NUMBER IS FROM. Three grades, and the list below says which:
#   [JST]    JST's own drawing, as already cited in this file (eXH, ePH) or in the
#            project that first used the part (eZR, for the ZR/ZH pair).
#   [KiCad]  measured off KiCad's library model of the mating header
#            (Connector_JST.3dshapes, generated from JST's drawings): the POCKET the
#            housing goes into -- its depth, and how far its two broad walls stand from
#            the pin axis. JST dimensions the outside of a housing, not the pocket.
#   [est]    an estimate, to be replaced when the drawing is read or a part is measured.
# The housing's LENGTH is not taken from a drawing at all: it is what reaches from the
# pocket's floor to the back face, and the back face is where the drawings put it (the
# mated height, the mated length). So what shows -- how far the plug stands proud, and
# where its wires leave -- is as true as the drawing figure behind it, even where the
# length hidden inside the shroud is not.
#
#   pitch        [JST]
#   near, far    [KiCad] the pocket's broad walls from the PIN AXIS: `near` is the wall the
#                housing's rails pass through (XH: two slots; PH: one wide notch), and the
#                pins stand nearer it. On a top-entry header that is the side of the body
#                the pad row is off-centre toward; on a side-entry one it is the TOP.
#                ZH [est].
#   pocket_over  [KiCad] pocket width = pitch (n - 1) + this. ZH [est].
#   overall      [JST] XHP-n: B = A + 4.8 across its two end ears. PH, ZH: no ears.
#   pocket       [KiCad] pocket depth, mouth to floor (the same top and side entry)
#   cavity       [est] the square a crimped wire goes into at the back face
#   post         [JST] XH 0.64 square; [KiCad] PH 0.5; [est] ZH
#   top          (header height, mated height) above the board, top entry:
#                XH 7.0 / 9.8 [JST eXH]; PH 6.0 [JST ePH p.2] / 8.0 [est: the series'
#                advertised mounted height, not read off the drawing here]
#   side         {smt: (axis, proud, pocket, body_d)} for side entry:
#     axis    the pin axis above the board. THT [KiCad]: XH 3.75, PH 3.1. SMT [est]: the
#             same distance below the TOP as the THT part (XH 6.0 - 2.35, PH 5.5 - 1.75);
#             ZH [est] mid-pocket of a 3.7 body.
#     proud   the mated housing past the mouth. PH SMT 3.6 [JST ePH p.2: 9.6 - 6.0];
#             ZH 2.0 [JST eZR p.2: 7 - 5.0]; XH 2.8 and PH THT 2.0 [est]: the top-entry
#             figure (mated - header), on the grounds that pocket and housing are the same.
#     pocket  pocket depth of the header AS DRAWN BY cadkit.web.parts (SMT only; a THT
#             header is KiCad's model and its pocket is `pocket` above). PH SMT 3.25 =
#             PHR's 6.85 [JST ePH p.3] less the 3.6 proud; XH = the THT pocket; ZH [est].
#     body_d  the moulded body's depth where the footprint's F.Fab box also takes in the
#             tails: PH 6.0 [JST ePH p.4], ZH 5.0 [JST eZR p.5]; None = the F.Fab box.
JST_FIT = 0.05            # housing to pocket, a side: enough that no two faces coincide
JST_SERIES = {
    "XH": dict(housing="XHP-%d", pitch=XH_PITCH, near=1.5, far=2.65, pocket_over=3.2,
               overall=4.8, pocket=5.15, cavity=1.9, post=XH_POST, rails="slots",
               top=(XH_BODY_H, XH_MATED_H),
               side={False: (3.75, XH_MATED_H - XH_BODY_H, 5.15, None),
                     True: (3.65, XH_MATED_H - XH_BODY_H, 5.15, None)}),
    "PH": dict(housing="PHR-%d", pitch=PH_PITCH, near=1.1, far=2.3, pocket_over=2.9,
               overall=None, pocket=4.2, cavity=1.5, post=0.5, rails="notch",
               top=(6.0, 8.0),
               side={False: (3.1, 2.0, 4.2, None),
                     # ⚠ THE SMT PART'S CONTACT AXIS IS HALF ITS HEIGHT, AND THAT IS UNREAD.
                     # JST's drawing (ePH p.4) has it; nobody has taken it off the page.
                     # Projects have laid cables out round "the middle of the header"
                     # for as long as there has been one, so the housing is drawn
                     # there too: one figure, and one place to correct it.
                     True: (PH_SIDE_H / 2.0, PH_PLUG_RUN, 6.85 - PH_PLUG_RUN, PH_SIDE_D)}),
    "ZH": dict(housing="ZHR-%d", pitch=1.5, near=1.0, far=1.5, pocket_over=3.1,
               overall=None, pocket=3.3, cavity=1.1, post=0.4, rails=None,
               top=None,
               side={True: (2.0, 2.0, 3.3, 5.0)}),
}
_JST_NAME = []


def jst_part(name):
    """What a footprint name says about a JST wire-to-board header, or None if it is not
    one JST_SERIES covers: {"series": "XH" | "PH" | "ZH", "n": ways, "side": side entry,
    "smt": surface mount}. Read from the PART NUMBER in the name (B4B-XH-A, S8B-PH-SM4-TB,
    S4B-ZR-SM4A-TF), not from the word Horizontal: a project's own footprint of the same
    part (..._MouthOnEdge, ..._TightCourtyard) is named after the part and not the pose."""
    if not _JST_NAME:
        import re
        _JST_NAME.append(re.compile(r"^JST_(XH|PH|ZH)_([BS])(\d+)B-(?:XH|PH|ZR|ZH)-([A-Z0-9]+)"))
    m = _JST_NAME[0].match(name)
    if not m:
        return None
    series, side, smt = m.group(1), m.group(2) == "S", m.group(4).startswith("SM")
    s = JST_SERIES[series]
    if (side and smt not in s["side"]) or (not side and (smt or not s["top"])):
        return None                       # a pose of the part the table has no numbers for
    return {"series": series, "n": int(m.group(3)), "side": side, "smt": smt}


_HOUSINGS = {}


def jst_housing(series, length, ways):
    """The crimp housing of `series` as it LOOKS, in its own frame, built from JST_SERIES:

        X  along the row; `ways` is each way's x, in way order (so a housing is drawn on
           the contacts it mates with, wherever the caller's origin is along the row)
        Y  the mating axis: y = 0 is the BACK FACE, where the wires leave toward -Y, and
           the body runs +Y into the header for `length`
        Z  across: z = 0 is the CONTACT AXIS, +Z the side the rails are on (JST_SERIES
           `near`)

    so way k's wire cavity is centred on (ways[k], 0, 0): the point Boards.wire_exit
    returns, by construction rather than by agreement. The cavities are open at the back
    (an unused way is an empty hole, as on the bench), each with its lance window in the
    far broad face; XHP has its two rails and end ears, PHR its one wide rib."""
    key = (series, round(length, 3), tuple(round(x, 4) for x in ways))
    if key in _HOUSINGS:
        return _HOUSINGS[key]
    s = JST_SERIES[series]
    x0, x1 = min(ways), max(ways)
    cx = (x0 + x1) / 2.0
    bw = (x1 - x0) + s["pocket_over"] - 2 * JST_FIT
    near, far = s["near"] - JST_FIT, s["far"] - JST_FIT
    body = _block(bw, length, near + far, cx, length / 2.0, -far).edges("|Y").chamfer(0.2)
    if s["overall"]:
        ear = ((x1 - x0) + s["overall"] - bw) / 2.0
        el = min(2.0, 0.3 * length)
        for sx in (-1.0, 1.0):
            body = body.union(_block(ear + 0.1, el, 1.5, cx + sx * (bw / 2.0 + ear / 2.0 - 0.05),
                                     el / 2.0, -0.75))
    if s["rails"] == "slots":               # XHP: a rail by each end way, in the header's slots
        for a, b in ((x0 - 0.5 + JST_FIT, x0 + 1.0 - JST_FIT),
                     (x1 - 1.0 + JST_FIT, x1 + 0.5 - JST_FIT)):
            body = body.union(_block(b - a, length - 0.9, 0.85, (a + b) / 2.0,
                                     0.9 + (length - 0.9) / 2.0, near - 0.05))
    elif s["rails"] == "notch":             # PHR: one low rib between the end ways
        a, b = x0 + 0.55 + JST_FIT, x1 - 0.55 - JST_FIT
        body = body.union(_block(b - a, length - 0.8, 0.6, (a + b) / 2.0,
                                 0.8 + (length - 0.8) / 2.0, near - 0.05))
    cav = s["cavity"]
    for x in ways:
        body = body.cut(_block(cav, 0.55 * length + 0.01, cav, x, 0.55 * length / 2.0 - 0.01,
                               -cav / 2.0))
        # the lance window: through the far broad face into the cavity
        body = body.cut(_block(0.55 * cav, 0.18 * length, far, x, 0.5 * length, -far - 0.01))
    _HOUSINGS[key] = body
    return body
