"""Our own models of the board parts KiCad's library has no model for.

cadkit.web.boards swaps a footprint's box for KiCad's part model. Some parts have no
model file in KiCad's library (the USB-C receptacle, the TRS jack, the side-entry SMD
JSTs, the power inlet, the LEDs ...). The fab house's viewer shows them, but those models
are the fab house's, and its terms keep them out of a public repository. So these are
DRAWN HERE, from what is already this project's own and from the makers' published
drawings:

  * the OUTLINE is the footprint's F.Fab body, read from the routed board;
  * the HEIGHT is the one the CAD already stands the part at (the project's
    cadkit.board_geom.Boards HEIGHT table, each from its datasheet);
  * a panel connector's mouth and axis height are cadkit.board_geom.PANEL's, off the
    makers' drawings;
  * the detail inside that envelope (a housing's cavity and pins, a shell's tongue, a
    lens) is REPRESENTATIVE: right in kind and colour, not dimensioned.

So a part drawn here is exact where the design depends on it (where it is, how big, where
its mouth is) and a likeness elsewhere. Nothing in it is copied or measured off anybody's
model.

Every generator draws in one frame: X across the mouth and centred, Y from the mouth
face (0) back to the depth D, Z from the board (0) up to H. `build()` hands back
[(solid, (r, g, b))] in the BOARD's frame.

SAME_BODY is the other half: where KiCad's library has the same body under another
name (an inductor series by another maker, a QFN that differs in its exposed pad, which
is underneath), that model is used.
"""

from __future__ import annotations

import math
import re

import cadquery as cq

CREAM = (0.93, 0.90, 0.80)       # a JST housing
TIN = (0.78, 0.78, 0.80)
STEEL = (0.70, 0.71, 0.74)
BLACK = (0.07, 0.07, 0.08)
GREEN = (0.18, 0.50, 0.28)       # a terminal block
GOLD = (0.83, 0.68, 0.25)
WHITE = (0.94, 0.94, 0.92)
LENS = (0.96, 0.88, 0.45)        # phosphor under an LED's window
SMOKE = (0.16, 0.17, 0.22)       # a photodiode's window
CERAMIC = (0.80, 0.74, 0.62)

# a model file KiCad's library does not have -> one it does, with the same body
SAME_BODY = {
    "L_Taiyo-Yuden_NR-30xx.step": "Inductor_SMD.3dshapes/L_APV_ANR3015.step",
    "L_TDK_VLS6045EX_VLS6045AF.step": "Inductor_SMD.3dshapes/L_APV_ANR6045.step",
    "QFN-16-1EP_3x3mm_P0.5mm_EP1.45x1.45mm.step":
        "Package_DFN_QFN.3dshapes/QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm.step",
    "HVQFN-24-1EP_4x4mm_P0.5mm_EP2.5x2.5mm.step":
        "Package_DFN_QFN.3dshapes/HVQFN-24-1EP_4x4mm_P0.5mm_EP2.1x2.1mm.step",
}


def _box(w, d, h, x=0.0, y=0.0, z=0.0):
    """w across (centred on x), d deep from y, h up from z."""
    return cq.Workplane("XY").box(w, d, h, centered=(True, False, False)).translate((x, y, z))


def _cyl_y(r, length, x=0.0, y=0.0, z=0.0):
    """A cylinder along +Y from y, its axis at (x, z)."""
    return (cq.Workplane("XY").circle(r).extrude(length)
            .rotate((0, 0, 0), (1, 0, 0), -90).translate((x, y, z)))


def _cyl_z(r, h, x=0.0, y=0.0, z=0.0):
    return cq.Workplane("XY").circle(r).extrude(h).translate((x, y, z))


def _ways(n, pitch):
    return [(i - (n - 1) / 2.0) * pitch for i in range(n)]


# ── the generators: (W, D, H, facts) -> [(workplane, colour)] ─────────────────────────
def jst_side(W, D, H, n=4, pitch=2.0, series=None, smt=True, ways=None, pads_y=None, **_):
    """A side-entry JST header KiCad's library has no model of (the SMT ones: S*B-PH-SM4-TB,
    S*B-XH-SM4-TB, S*B-ZR-SM4A-TF), drawn so the crimp housing cadkit.pcb.jst_housing draws
    SEATS in it: the pocket is cut from the same cadkit.pcb.JST_SERIES record the housing
    is built from, round the same contact axis, and each post is on its own pad (`ways`:
    every way's x in this frame, read from the routed board).

    What is drawn: the moulded body (the F.Fab box, or the front `body_d` of it where the
    box also takes in the tails), the pocket open at the mouth, the top wall's slots (XH:
    one by each end way) or notch (PH: one, between the end ways) that the housing's rails
    run in, a post a way, the SMD tails from the back wall down onto their pads (`pads_y`),
    and the two solder tabs that hold the part down, one at each end. The outline and
    height are the footprint's and the CAD's; the pocket is JST_SERIES; the tabs and tails
    are a likeness."""
    from cadkit.pcb import JST_SERIES, JST_FIT
    s = JST_SERIES.get(series)
    xs = list(ways) if ways else _ways(n, pitch)
    if s is None or smt not in s["side"]:
        s = dict(near=0.3 * H, far=0.3 * H, pocket_over=1.4 * pitch, post=min(0.5, 0.3 * pitch),
                 rails=None)
        axis, pocket, body_d = H / 2.0, 0.6 * D, None
    else:
        axis, _proud, pocket, body_d = s["side"][smt]
    Db = min(D, body_d) if body_d else D
    wall = 0.4
    x0, x1 = min(xs), max(xs)
    pw = min((x1 - x0) + s["pocket_over"], W - 2 * wall)
    pcx = (x0 + x1) / 2.0
    z0 = max(axis - s["far"], wall)
    z1 = min(axis + s["near"], H - wall)
    pocket = min(pocket, Db - 2 * wall)
    body = _box(W, Db, H).cut(_box(pw, pocket + 0.01, z1 - z0, x=pcx, y=-0.01, z=z0))
    slot = min(0.75 * pocket, pocket - 0.3)                 # how far back the top wall is cut
    if s["rails"] == "slots":
        for a, b in ((x0 - 0.5, x0 + 1.0), (x1 - 1.0, x1 + 0.5)):
            body = body.cut(_box(b - a, slot + 0.01, H - z1 + 0.02, x=(a + b) / 2.0, y=-0.01,
                                 z=z1 - 0.01))
    elif s["rails"] == "notch" and x1 - x0 > 1.2:
        body = body.cut(_box((x1 - x0) - 1.1, slot + 0.01, H - z1 + 0.02, x=pcx, y=-0.01,
                             z=z1 - 0.01))
    out = [(body, CREAM)]
    post = s["post"]
    for x in xs:
        # the post, from just inside the mouth back through the rear wall...
        out.append((_box(post, Db - 0.5 + 0.01, post, x=x, y=0.5, z=axis - post / 2.0), TIN))
        if smt:
            # ...down the back of the body and out along the board onto its pad
            end = max((pads_y if pads_y is not None else Db) + 0.6, Db + 0.8)
            out.append((_box(post, post, axis + post / 2.0, x=x, y=Db), TIN))
            out.append((_box(1.4 * post, end - Db, 0.2, x=x, y=Db), TIN))
    if smt:
        for sx in (-1.0, 1.0):                              # the solder tabs, one at each end
            leaf = _box(0.2, 0.3 * Db, 0.55 * H, x=sx * (W / 2.0 + 0.1), y=0.15 * Db)
            foot = _box(0.9, 0.3 * Db, 0.2, x=sx * (W / 2.0 + 0.45), y=0.15 * Db)
            out.append((leaf.union(foot), TIN))
    return out


def usb_c(W, D, H, **_):
    """A USB-C receptacle: the drawn steel shell, open at the mouth, and the tongue."""
    r = 0.42 * min(W, H)
    wall = 0.3
    shell = _box(W, D, H).edges("|Y").fillet(r)
    bore = (_box(W - 2 * wall, 0.86 * D, H - 2 * wall, y=-0.01, z=wall)
            .edges("|Y").fillet(max(r - wall, 0.05)))
    tongue = _box(0.74 * W, 0.70 * D, 0.7, y=0.12 * D, z=H / 2 - 0.35)
    return [(shell.cut(bore), STEEL), (tongue, BLACK)]


def jack_635(W, D, H, axis_h=None, spec=None, **_):
    """A rear-mount 6.35 mm jack, as the panel table gives it (the maker's drawing): the
    moulded body back from its SHOULDER, the round stub in front of the shoulder, and the
    nose nut that clamps the panel -- a hex head on a threaded sleeve that runs back into
    the stub. Bored through for the plug."""
    spec = spec or {}
    zc = axis_h if axis_h and axis_h < H else H / 2
    sd, sl = spec.get("stub") or (0.6 * min(W, H), 0.0)
    body = _box(W, D - sl, H, y=sl)
    try:
        body = body.edges("|Y and >Z").chamfer(min(2.0, 0.2 * H))
    except Exception:
        pass
    bore = _cyl_y(3.3, 0.8 * D + 10.0, y=-10.0, z=zc)
    out = [(body.cut(bore), BLACK)]
    nut = spec.get("nut")
    if sl:
        # the stub is bored for the nut's threaded sleeve where it has one: two solids
        # in one place (and two bore walls on one radius) flicker in the viewer
        hole = _cyl_y(nut[2] / 2.0, sl + 0.02, y=-0.01, z=zc) if nut else bore
        out.append((_cyl_y(sd / 2.0, sl, z=zc).cut(hole), BLACK))
    if nut:
        af, ht, shd, shl = nut
        head_back = sl - spec.get("clamp", 0.0)              # the head bears on the panel's face
        head = (cq.Workplane("XY").polygon(6, af / math.cos(math.pi / 6)).extrude(ht)
                .rotate((0, 0, 0), (1, 0, 0), -90).translate((0, head_back - ht, zc)))
        shank = _cyl_y(shd / 2.0, shl, y=head_back, z=zc)
        out.append((head.union(shank).cut(bore), TIN))
    out.append((_cyl_y(3.22, 0.4 * D, y=sl + 0.5, z=zc).cut(_cyl_y(2.95, D, z=zc)), TIN))
    return out


def power_din(W, D, H, axis_h=None, spec=None, **_):
    """A shielded mini-DIN power inlet: the shield can that is its whole outside, the
    round nose in front of the body (the panel table's, off the maker's drawing), and
    the moulded insert inside it with a hole per contact and the key."""
    spec = spec or {}
    zc = axis_h if axis_h and axis_h < H else H / 2
    nose = spec.get("nose")
    r, reach = (nose[1] / 2.0, nose[2]) if nose else (0.42 * min(W, 2 * zc), 0.0)
    mouth = _cyl_y(r - 0.5, 0.5 * D + reach, y=-reach - 0.01, z=zc)
    can = _box(W, D, H).cut(mouth)
    ring = _cyl_y(r, reach + 0.5, y=-reach, z=zc).cut(mouth) if reach else None
    core = _cyl_y(r - 0.5, 0.5 * D + reach - 1.2, y=-reach + 1.2, z=zc)
    for dx, dz in ((-0.38, 0.30), (0.38, 0.30), (-0.38, -0.30), (0.38, -0.30)):
        core = core.cut(_cyl_y(0.7, 3.0, x=dx * r, y=-reach + 1.19, z=zc + dz * r))
    core = core.cut(_box(0.36 * r, 3.0, 0.5 * r, y=-reach + 1.19, z=zc - 0.25 * r))
    out = [(can, STEEL), (core, BLACK)]
    if ring is not None:
        out.append((ring, STEEL))
    return out


def terminal_block(W, D, H, n=2, pitch=5.0, **_):
    """A screw terminal block: a wire entry per way at the mouth, a screw from above."""
    body = _box(W, D, H)
    out = []
    for x in _ways(n, pitch):
        body = body.cut(_box(0.6 * pitch, 0.4 * D, 0.38 * H, x=x, y=-0.01, z=0.12 * H))
        body = body.cut(_cyl_z(0.34 * pitch, 0.9, x=x, y=0.62 * D, z=H - 0.9))
        out.append((_cyl_z(0.30 * pitch, 0.5, x=x, y=0.62 * D, z=H - 0.9), TIN))
    return [(body, GREEN)] + out


def led_window(W, D, H, lens=LENS, body=WHITE, **_):
    """A top-emitting LED (or, in other colours, a photodiode): the moulded body with a
    round window in its top."""
    r = 0.40 * min(W, D)
    dip = min(0.5, 0.4 * H)
    b = _box(W, D, H).cut(_cyl_z(r, dip + 0.01, y=D / 2, z=H - dip))
    return [(b, body), (_cyl_z(r, 0.6 * dip, y=D / 2, z=H - dip), lens)]


def photodiode(W, D, H, **_):
    return led_window(W, D, H, lens=SMOKE, body=BLACK)


def oscillator(W, D, H, **_):
    """A ceramic oscillator can: the base and the seam-welded lid."""
    base = 0.45 * H
    return [(_box(W, D, base), CERAMIC),
            (_box(W - 0.3, D - 0.3, H - base, y=0.15, z=base), STEEL)]


def pogo(W, D, H, n=4, **_):
    """A spring-pin connector: the moulded block and a plunger per way, along its
    longer side."""
    block = 0.5 * H
    out = [(_box(W, D, block), BLACK)]
    along_x = W >= D
    pitch = (W if along_x else D) / n
    r = min(0.3 * pitch, 0.35 * min(W, D))
    for s in _ways(n, pitch):
        x, y = (s, D / 2) if along_x else (0.0, D / 2 + s)
        out.append((_cyl_z(r, H - block, x=x, y=y, z=block), GOLD))
    return out


def dip_switch(W, D, H, **_):
    return [(_box(W, D, 0.8 * H), BLACK),
            (_box(0.3 * W, 0.4 * D, 0.2 * H, y=0.3 * D, z=0.8 * H), WHITE)]


def stick(W, D, H, **_):
    """A stick / encoder: the metal frame and the shaft."""
    frame = 0.55 * H
    return [(_box(W, D, frame), STEEL),
            (_cyl_z(0.16 * min(W, D), H - frame, y=D / 2, z=frame), BLACK)]


def push_latch(W, D, H, **_):
    """A self-locking push switch of the square board-mount kind: the moulded case, the
    steel strap that clips over its top and down two sides, and the plunger's shoulder
    in the strap's window. The stem above the case is the project's to draw: how far it
    stands is the state the switch is in."""
    t = min(0.3, 0.05 * W)
    top = 0.9 * H
    win = 0.56 * min(W, D)
    case = _box(W - 2 * t, D, top)
    strap = (_box(W, 0.62 * D, H, y=0.19 * D)
             .cut(_box(W - 2 * t, 0.62 * D + 0.02, H - t, y=0.19 * D - 0.01, z=-0.01))
             .cut(_box(win, win, 3 * t, y=(D - win) / 2, z=H - 2 * t)))
    shoulder = _box(win - 0.3, win - 0.3, H - top, y=(D - win + 0.3) / 2, z=top)
    return [(case, BLACK), (strap, STEEL), (shoulder, WHITE)]


# footprint name -> (generator, facts read from the name)
_RULES = [
    (r"^JST_(ZH|PH|XH)_S(\d+)B.*(Horizontal|TightCourtyard|MouthOnEdge)", jst_side),
    (r"^USB_C_Receptacle", usb_c),
    (r"^Jack_6\.35mm", jack_635),
    (r"^Kycon_KPJX", power_din),
    (r"^TerminalBlock_.*_1x(\d+)_P(\d+\.\d+)mm", terminal_block),
    (r"XL-5050", led_window),
    (r"PD15-22B", photodiode),
    (r"^Oscillator_SMD", oscillator),
    (r"^Xinyangze_YZ1[68]\d+.*-(\d\d)\d\d\d$", pogo),
    (r"DSHP01", dip_switch),
    (r"RKJXT1F", stick),
    (r"PB-22E", push_latch),
]
_PITCH = {"ZH": 1.5, "PH": 2.0, "XH": 2.5}


def _facts(gen, m):
    if gen is jst_side:
        return {"n": int(m.group(2)), "pitch": _PITCH[m.group(1)], "series": m.group(1),
                "smt": "-SM" in m.string}
    if gen is terminal_block:
        return {"n": int(m.group(1)), "pitch": float(m.group(2))}
    if gen is pogo:
        return {"n": int(m.group(1))}
    return {}


def _mouth(f, name, panel, outline=None):
    """The mouth's direction in the board frame: the panel table's where it has the
    part; else away from the pads (a side-entry header's lands are at its back); else,
    for a part whose pads are under its middle (a screw terminal), toward the NEAREST
    BOARD EDGE -- wires come in from outside the board."""
    from cadkit.board_geom import _rot
    spec = panel.get(name)
    if spec:
        d = _rot(spec["mouth"], f["rot"])
        return (round(d[0]), 0) if abs(d[0]) > 0.5 else (0, round(d[1]))
    x0, x1, y0, y1 = f["fab"]
    px, py = f.get("pads_xy") or ((x0 + x1) / 2, (y0 + y1) / 2)
    dx, dy = ((x0 + x1) / 2 - px) / (x1 - x0), ((y0 + y1) / 2 - py) / (y1 - y0)
    if max(abs(dx), abs(dy)) < 0.08:
        if not outline:
            return (0, -1)
        bx0, bx1, by0, by1 = outline
        return min(((x0 - bx0, (-1, 0)), (bx1 - x1, (1, 0)), (y0 - by0, (0, -1)),
                    (by1 - y1, (0, 1))), key=lambda e: e[0])[1]
    return (1 if dx > 0 else -1, 0) if abs(dx) > abs(dy) else (0, 1 if dy > 0 else -1)


def side_entry(name):
    """True for a side-entry header: the one kind of part a board may draw MATED."""
    return bool(re.search(_RULES[0][0], name) or re.search(r"^JST_.*Horizontal", name))


def mouth(f, panel=None, outline=None):
    return _mouth(f, f["fpid"].split(":")[-1], panel or {}, outline)


def knows(name):
    return any(re.search(p, name) for p, _ in _RULES)


def build(f, h, thickness, panel=None, outline=None):
    """[(cq solid, (r, g, b))] for footprint record `f` (a geom file's), standing h tall,
    in the board's frame; None for a part there is no generator for. `outline` is the
    board's own (x0, x1, y0, y1)."""
    name = f["fpid"].split(":")[-1]
    for pat, gen in _RULES:
        m = re.search(pat, name)
        if m:
            break
    else:
        return None
    x0, x1, y0, y1 = f["fab"]
    mx, my = _mouth(f, name, panel or {}, outline)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    if mx:
        W, D = y1 - y0, x1 - x0
        origin, turn = ((x0 if mx < 0 else x1), cy), (-90.0 if mx < 0 else 90.0)
    else:
        W, D = x1 - x0, y1 - y0
        origin, turn = (cx, (y0 if my < 0 else y1)), (0.0 if my < 0 else 180.0)
    facts = _facts(gen, m)
    if gen is jst_side and f.get("pads"):
        # each way where the routed board has its pad, in the generator's frame: its X is
        # the board's X turned by `turn`, its Y runs from the mouth back into the body
        a = math.radians(turn)
        gx, gy = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        try:
            pads = [f["pads"][str(k)] for k in range(1, facts["n"] + 1)]
            facts["ways"] = [(p[0] - origin[0]) * gx[0] + (p[1] - origin[1]) * gx[1] for p in pads]
            facts["pads_y"] = sum((p[0] - origin[0]) * gy[0] + (p[1] - origin[1]) * gy[1]
                                  for p in pads) / len(pads)
        except KeyError:
            pass
    spec = (panel or {}).get(name) or {}
    if "axis_h" in spec:
        facts["axis_h"] = spec["axis_h"]
    facts["spec"] = spec
    back = f["side"] == "B"
    out = []
    for w, colour in gen(W, D, h, **facts):
        if back:
            w = w.mirror("XY")                       # under the board, hanging down
        w = (w.rotate((0, 0, 0), (0, 0, 1), turn)
             .translate((origin[0], origin[1], 0.0 if back else thickness)))
        out += [(s, colour) for s in w.vals()]
    return out
