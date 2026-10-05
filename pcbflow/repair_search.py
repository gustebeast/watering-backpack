"""Find a legal via + two-track path to close one stubborn net, on a ROUTED board.

    py -3.12 cadkit/pcbflow/repair_search.py elec/out/optical +3V3A U2 4

⚠ WHY THIS IS A FILE AND NOT A SCRIPT IN A COMMENT. The same search was written inline
four times in one session and got a different answer each time, because each version
quietly checked a different set of obstacles:

  1st  tracks + vias, 0.20 mm margin, run against a STALE board  -> "no legal site"
  2nd  tracks + vias, 0.15 mm margin                             -> 2638 sites, shortest
       one chosen; it closed +3V3A and cost FIVE analog nets, because it was laid as a
       PRE-LAY and the other 76 nets had to plan around it
  3rd  same, after the netlist changed underneath it              -> the chosen spur
       CROSSED TIA_OUT_2A: a short between two nets
  4th  same, longer path to a different rail                      -> SEVEN violations:
       two solder_mask_bridge against the target part's OWN PAD, three
       copper_edge_clearance, a copper_sliver

Every one of those is the same mistake in a different coat: the search knew about less
of the board than DRC does. Tracks and vias are not the obstacles -- PADS and the BOARD
OUTLINE are obstacles too, and a 4 mm path can miss them by luck while a 14 mm path
cannot. Writing it down once, with every obstacle class in it, is the only way the
answer stops depending on which day it was typed.

⚠ AND THE RESULT IS PINNED TO ONE ROUTING. These coordinates are searched against a
specific routed board. Change the netlist -- even a connector going from four ways to
two -- and the router re-plans, the obstacles move, and the answer is silently wrong.
That happened once already. RE-RUN THIS after any netlist change.

The output is meant to be pasted into a board's BOARD_NOTES as repair_vias /
repair_tracks, which route.py applies AFTER routing (see its repair block). Laid before
routing the same geometry is a constraint that costs more than it buys.
"""
from __future__ import annotations

import json
import math
import re
import sys

RULE_CLEAR = 0.127     # the netclass clearance itself -- what DRC actually enforces
MARGIN = 0.15          # on top of each obstacle's own half-width, over the netclass rule
VIA_D, VIA_DRILL = 0.6, 0.3
TRACK_W = 0.25
GRID = 0.1
REACH = 9.0            # how far from the pad to look, mm


def _segments(board_txt):
    out = []
    for b in re.findall(r"\(segment\b(.*?)\n\t\)", board_txt, re.S):
        st = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", b)
        en = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", b)
        ly = re.search(r'\(layer "([^"]+)"', b)
        nt = re.search(r'\(net "([^"]*)"', b)
        w = re.search(r"\(width ([-\d.]+)\)", b)
        if st and en and ly:
            out.append(dict(x1=float(st.group(1)), y1=float(st.group(2)),
                            x2=float(en.group(1)), y2=float(en.group(2)),
                            layer=ly.group(1), net=nt.group(1) if nt else "",
                            half=(float(w.group(1)) if w else TRACK_W) / 2.0))
    return out


def _vias(board_txt):
    out = []
    for b in re.findall(r"\(via\b(.*?)\n\t\)", board_txt, re.S):
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)\)", b)
        sz = re.search(r"\(size ([-\d.]+)\)", b)
        nt = re.search(r'\(net "?([^")\s]*)', b)
        if at:
            out.append(dict(x=float(at.group(1)), y=float(at.group(2)),
                            r=(float(sz.group(1)) if sz else VIA_D) / 2.0,
                            net=nt.group(1) if nt else ""))
    return out


def _pads(board_txt):
    """⚠ THE CLASS EVERY EARLIER VERSION OF THIS SEARCH MISSED. A pad is copper and it
    is also solder mask -- running a track past one at a legal copper distance can still
    bridge the mask, which is what produced two solder_mask_bridge violations against
    the target part's own pad.

    ⚠ AND A PAD IS A CAPSULE, NOT A CIRCLE. The first version took a circle of half the
    pad's LARGER dimension, which for a SOIC pad (~1.5 x 0.6) is a 0.75 mm radius in
    every direction. Adjacent pads are 1.27 mm apart, so those circles overlapped each
    other and sealed the package off: the search reported ZERO reachable sites around
    U2's pad 3 even at zero margin, for a pad the router had reached to within 2.54 mm.
    An obstacle model that is too FAT fails as silently as one that is too thin -- it
    just reports "impossible" instead of "clear".

    Each pad is now its centreline segment along the long axis plus a half-width of the
    short one, rotated by the footprint's angle and its own."""
    out = []
    for f in re.findall(r"\(footprint\b(.*?)\n\t\)", board_txt, re.S):
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", f)
        if not at:
            continue
        fx, fy = float(at.group(1)), float(at.group(2))
        # ⚠ THE SIGN OF THIS ROTATION WAS WRONG, AND IT MOVED 456 OF 982 PADS -- by up to
        # 10.65 mm. KiCad's angles are counter-clockwise on screen while its y axis points
        # DOWN, so a footprint's local (px, py) lands at
        #     gx = fx + px cos - (-py) sin ... = fx + px cos(a) + py sin(a)
        #     gy = fy - px sin(a) + py cos(a)
        # i.e. the transform of -a, not of +a. With +a every rotated part's pads came out
        # MIRRORED THROUGH ITS CENTRE: on a symmetric two-pad passive that silently swaps
        # which end carries which net (found on a SHDNZ pull-up, where audit_board then
        # reported fifteen problems that were each a track ending on its OWN pad), and on
        # an asymmetric part it is simply wrong. Checked now against pcbnew, part by part,
        # in scratchpad/padtest.py: 0 pads more than 0.02 mm out.
        rot = -math.radians(float(at.group(3)) if at.group(3) else 0.0)
        # ⚠ MATCH THE WHOLE PAD BLOCK, not just up to (size ...). A pad's net sits on a
        # LATER line, so a pattern that ended at the size never saw it and every pad read
        # as net "" -- which kills the same-net exemption silently: the search would
        # refuse to route past the very pad it is trying to reach, and report no legal
        # path when there are hundreds.
        for p in re.finditer(r'\(pad "([^"]*)"(.*?)\n\t\t\)', f, re.S):
            body = p.group(2)
            at = re.search(r"\(at ([-\d.]+) ([-\d.]+)", body)
            size = re.search(r"\(size ([-\d.]+) ([-\d.]+)\)", body)
            if not (at and size):
                continue
            px, py = float(at.group(1)), float(at.group(2))
            prot = re.search(r"\(at [-\d.]+ [-\d.]+ ([-\d.]+)\)", body)
            gx = fx + px * math.cos(rot) - py * math.sin(rot)
            gy = fy + px * math.sin(rot) + py * math.cos(rot)
            sw, sh = float(size.group(1)), float(size.group(2))
            # ⚠⚠ A PAD'S STORED ANGLE IS ABSOLUTE, NOT RELATIVE TO ITS FOOTPRINT, and
            # combining the two turned every rotated pad's CAPSULE 90 DEGREES OFF. Positions
            # were right -- an earlier fix checked those against pcbnew part by part -- so the
            # error hid in the pad's SHAPE, where nothing was comparing anything.
            # U7 on optical is the proof: footprint at -90, pads at 270, size 0.25 x 0.875, and
            # pcbnew reports each pad's world bbox as 0.875 x 0.250 -- long axis along X. The
            # combined angle (90 - 270 = -180) put the long axis along Y instead, which laid
            # three 0.625-long capsules END TO END on one line at 0.5 mm pitch, so adjacent QFN
            # lands OVERLAPPED each other by 0.125 mm. Pads that cannot physically coexist.
            # What that cost: U7 pad 9 is VDDIO, the ULPI PHY's I/O supply, and it read as
            # having NO legal escape in any direction at any radius -- a constant -0.0010 mm
            # against pad [ULPI_D4] whose uniformity was the clue, since a real obstacle field
            # does not give the same answer for every heading. 667 legal via sites, zero
            # reachable, because the phantom capsules sealed the pin off. "An obstacle model
            # that is too FAT fails as silently as one that is too thin" -- this docstring said
            # so about pad SHAPE two paragraphs up, and was wrong about shape anyway.
            ang = -math.radians(float(prot.group(1))) if prot else rot
            if sw >= sh:                       # long axis along the pad's local x
                half_len, half_w = (sw - sh) / 2.0, sh / 2.0
                ux, uy = math.cos(ang), math.sin(ang)
            else:                              # ...or along its local y
                half_len, half_w = (sh - sw) / 2.0, sw / 2.0
                ux, uy = -math.sin(ang), math.cos(ang)
            # ⚠ AND ITS FOUR CORNERS. The capsule above is a STADIUM -- fully rounded ends --
            # and a KiCad pad is a rounded RECTANGLE, which reaches further at the corners. On
            # a SOT-23-5 that is worth up to 0.15 mm, and it is an UNDER-estimate, so the
            # search hands back paths DRC then rejects: this cost three lay-measure-bump
            # cycles in one sitting (four clearance violations at 0.086-0.111, then six at
            # 0.066-0.118, then one at 0.1177) before the shape itself was suspected.
            # The docstring above already tells this story about a pad being modelled as a
            # CIRCLE and being too fat; too thin fails the same way, just more quietly.
            # ⚠ THE SHAPE DECIDES THE MODEL, AND THIS BOARD USES FOUR OF THEM: 881 roundrect,
            # 86 rect, 13 circle, 4 oval. One formula covers all of them -- a rectangle INSET
            # by the corner radius, with that radius added back as a distance offset:
            #     rect      cr = 0            -> the rectangle itself
            #     roundrect cr = rratio*min   -> KiCad's own definition
            #     circle    cr = r            -> the inset is a POINT
            #     oval      cr = min/2        -> the inset is a SEGMENT, i.e. the capsule
            # So the original capsule was exactly right for the 4 oval pads and wrong for the
            # other 980, where it UNDER-states the pad at its corners and therefore OVER-states
            # the clearance -- which is why the search kept approving paths DRC rejected.
            # ⚠ AND A PLAIN RECTANGLE IS NOT THE FIX EITHER: it over-states a roundrect, which
            # flagged an already-DRC-clean repair as violating. Too fat and too thin fail the
            # same way, one by inventing obstacles and one by hiding them.
            _shape = (re.search(r'\(pad "[^"]*" \w+ (\w+)', p.group(0)) or [None, "rect"])[1] \
                if False else _pad_shape(p.group(0))
            _rr = re.search(r"\(roundrect_rratio ([\d.]+)\)", body)
            _mn = min(sw, sh)
            if _shape == "circle":
                _cr = _mn / 2.0
            elif _shape == "oval":
                _cr = _mn / 2.0
            elif _shape == "roundrect":
                _cr = (float(_rr.group(1)) if _rr else 0.25) * _mn
            else:
                _cr = 0.0
            _ihx, _ihy = max(0.0, sw / 2.0 - _cr), max(0.0, sh / 2.0 - _cr)
            _ca, _sa = math.cos(ang), math.sin(ang)
            nt = re.search(r'\(net "([^"]*)"\)', body)
            # ⚠ AND WHICH COPPER LAYERS IT IS ON, which this parser did not record and
            # every caller therefore treated as "all of them". An SMD pad on F.Cu does
            # not block a track on B.Cu, and a QFP's unused pins are dozens of such pads
            # in a row: measured on optical, U6's no-net pins rejected a legal B.Cu
            # repair at -0.275 mm against copper that is two layers away from it.
            # A model that is too FAT fails as silently as one that is too thin -- the
            # note above says exactly that about pad SHAPE, and the same was true of pad
            # LAYERS one line further down.
            # "*.Cu" is a through-hole pad and really is on every layer; vias are checked
            # against ALL pads regardless (via_ok), because a via does pierce them all.
            lay = re.search(r"\(layers([^)]*)\)", body)
            names = re.findall(r'"?([\w.*]+)"?', lay.group(1)) if lay else []
            cu = {n for n in names if n.endswith(".Cu")}
            out.append(dict(x1=gx - ux * half_len, y1=gy - uy * half_len,
                            x2=gx + ux * half_len, y2=gy + uy * half_len,
                            r=half_w, net=nt.group(1) if nt else "",
                            gx=gx, gy=gy, ca=_ca, sa=_sa, ihx=_ihx, ihy=_ihy, cr=_cr,
                            cu=None if (not cu or "*.Cu" in cu) else cu))
    return out


def _zone_clearance(stem):
    """The ZONE clearance rule, read from the project file rather than assumed.

    ⚠ IT IS NOT THE TRACK RULE, AND ON THIS BOARD IT IS FOUR TIMES LARGER. optical's
    board.design_settings.defaults.zones.min_clearance is 0.5000 mm against a 0.127 mm
    netclass clearance, and DRC reports it in those words ("zone clearance 0.5000 mm").
    Assuming the track rule for pours is what let a dog-leg with 0.1557 mm of MEASURED
    headroom land 0.0225 mm from the ground pour. Read it, so it cannot drift from the board.
    """
    try:
        d = json.load(open(stem + ".kicad_pro", encoding="utf-8"))
        return float(d["board"]["design_settings"]["defaults"]["zones"]["min_clearance"])
    except Exception:
        return 0.5              # optical's value: a miss here is conservative, not silent


def _zones(board_txt):
    """The FILLED copper pours: [{layer, net, pts, bbox}], one entry per filled_polygon.

    ⚠ THE FILLED POLYGON IS THE COPPER, NOT THE ZONE OUTLINE. A zone's outline can cover the
    whole board; what is actually plated is the filled_polygon list, poured around every
    existing track and pad. It is the only shape clearance can honestly be measured against.

    ⚠ AND THIS FUNCTION WAS MISSING, WHICH MADE EVERY NUMBER THIS MODULE PRODUCED AN
    UNDERSTATEMENT. Board parsed segments, vias, pads and edges; the pours were invisible, so
    "0.1557 mm of headroom" meant headroom against everything except the largest copper feature
    on the board. optical carries 35 filled polygons on F.Cu alone, 10 on B.Cu and 1 on In1.Cu.
    """
    out = []
    for z in re.findall(r"\(zone\b(.*?)\n\t\)", board_txt, re.S):
        # ⚠ IT IS (net "GND"), NOT (net_name ...). KiCad 10 writes a zone's net the same way
        # it writes a segment's, and this file contains ZERO occurrences of net_name -- so the
        # first version silently gave every pour an empty net. That reads as "foreign" against
        # every net, which happens to be right for +3V3D (the pours are GND) and would block a
        # repair on GND against ITS OWN copper. A parser that is accidentally right on the case
        # in front of it is the kind that gets trusted and then surprises somebody.
        nt = re.search(r'\(net "([^"]*)"', z)
        net = nt.group(1) if nt else ""
        # a zone may also carry its own clearance; keep the STRICTER of it and the project rule
        zc = re.search(r"\(clearance ([-\d.]+)\)", z)
        z_clear = float(zc.group(1)) if zc else 0.0
        for fp in re.findall(r"\(filled_polygon\b(.*?)\n\t\t\)", z, re.S):
            ly = re.search(r'\(layer "([^"]+)"', fp)
            if not ly:
                continue
            pts = [(float(a), float(b))
                   for a, b in re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", fp)]
            if len(pts) < 3:
                continue
            xs = [q[0] for q in pts]
            ys = [q[1] for q in pts]
            out.append(dict(layer=ly.group(1), net=net, pts=pts, clear=z_clear,
                            bbox=(min(xs), max(xs), min(ys), max(ys))))
    return out


def _pt_in_poly(px, py, pts):
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > py) != (y2 > py):
            if px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def _d_seg_poly(ax, ay, bx, by, z, reach):
    """Edge-to-edge distance from segment AB to a filled polygon; 0.0 if AB touches or enters.

    `reach` bounds the bbox reject, so a pour whose nearest edge cannot matter is skipped
    before its (often thousands of) points are walked."""
    x0, x1, y0, y1 = z["bbox"]
    if (min(ax, bx) > x1 + reach or max(ax, bx) < x0 - reach
            or min(ay, by) > y1 + reach or max(ay, by) < y0 - reach):
        return 1e9
    pts = z["pts"]
    if _pt_in_poly(ax, ay, pts) or _pt_in_poly(bx, by, pts):
        return 0.0
    best = 1e9
    n = len(pts)
    for i in range(n):
        cx, cy = pts[i]
        dx, dy = pts[(i + 1) % n]
        d = _d_seg_seg(ax, ay, bx, by, cx, cy, dx, dy)
        if d < best:
            best = d
            if best <= 0.0:
                return 0.0
    return best


def _edges(board_txt):
    """The board outline. Copper too close to it is copper_edge_clearance, three of
    which the fourth inline version of this search produced."""
    out = []
    # ⚠ THE LAYER COMES AFTER THE STROKE BLOCK, so a pattern that stops at the first
    # ")" never sees it and silently returns ZERO edges -- which is exactly how three
    # copper_edge_clearance violations got through. Match the whole item.
    for b in re.findall(r"\(gr_line\b(.*?)\n\t\)", board_txt, re.S):
        if "Edge.Cuts" not in b:
            continue
        st = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", b)
        en = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", b)
        if st and en:
            out.append((float(st.group(1)), float(st.group(2)),
                        float(en.group(1)), float(en.group(2))))
    # A ROUND CUT-OUT IS OUTLINE TOO (a mounting hole drawn on Edge.Cuts): as a 24-gon,
    # whose flats sit under 0.9 % of the radius inside the true circle.
    for b in re.findall(r"\(gr_circle\b(.*?)\n\t\)", board_txt, re.S):
        if "Edge.Cuts" not in b:
            continue
        c = re.search(r"\(center ([-\d.]+) ([-\d.]+)\)", b)
        en = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", b)
        if c and en:
            cx, cy = float(c.group(1)), float(c.group(2))
            r = math.hypot(float(en.group(1)) - cx, float(en.group(2)) - cy)
            ring = [(cx + r * math.cos(math.radians(15.0 * i)),
                     cy + r * math.sin(math.radians(15.0 * i))) for i in range(25)]
            out += [(p0[0], p0[1], p1[0], p1[1]) for p0, p1 in zip(ring, ring[1:])]
    return out


def _edge_clearance(stem):
    """The board's copper-to-outline rule, which is NOT the netclass clearance.

    ⚠ THE OUTLINE WAS HELD OFF BY THE TRACK-TO-TRACK RULE (optical SAI_SD4, 2026-10-04).
    The fab wants 0.3 mm of laminate between copper and a routed edge; copper to copper
    is 0.127. The search modelled an edge as a zero-width foreign track, so it ran a
    path 0.13 mm from the outline and DRC called it copper_edge_clearance.
    """
    try:
        pro = json.load(open(stem + ".kicad_pro", encoding="utf-8"))
        return float(pro["board"]["design_settings"]["rules"]["min_copper_edge_clearance"])
    except (OSError, KeyError, ValueError, TypeError):
        return 0.3


def _d_pt_seg(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _seg_hit(ax, ay, bx, by, cx, cy, dx_, dy_):
    """True when the two segments properly cross."""
    def side(ox, oy, px, py, qx, qy):
        return (px - ox) * (qy - oy) - (py - oy) * (qx - ox)
    d1 = side(ax, ay, bx, by, cx, cy)
    d2 = side(ax, ay, bx, by, dx_, dy_)
    d3 = side(cx, cy, dx_, dy_, ax, ay)
    d4 = side(cx, cy, dx_, dy_, bx, by)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _d_seg_seg(ax, ay, bx, by, cx, cy, dx_, dy_):
    """⚠ THE MINIMUM OF THE FOUR ENDPOINT DISTANCES IS ONLY THE SEGMENT-TO-SEGMENT
    DISTANCE WHEN THE SEGMENTS DO NOT CROSS. Two segments that properly intersect are
    at distance ZERO, but every endpoint can still be far from the other segment -- so
    the endpoint minimum comes back POSITIVE and a crossing reads as clearance.

    Measured on this board: the MID repair line and a +3V3A diagonal intersect at
    x 72.128, and the endpoint minimum reported +0.758 mm of room. The search passed the
    path, the repair was laid, and DRC returned it as a tracks_crossing -- a short
    between two nets. An earlier tracks_crossing in this session was blamed on stale
    coordinates; this is at least as likely to have been the real cause both times.

    A clearance test that cannot see an intersection is not a clearance test."""
    if _seg_hit(ax, ay, bx, by, cx, cy, dx_, dy_):
        return 0.0
    return min(_d_pt_seg(ax, ay, cx, cy, dx_, dy_), _d_pt_seg(bx, by, cx, cy, dx_, dy_),
               _d_pt_seg(cx, cy, ax, ay, bx, by), _d_pt_seg(dx_, dy_, ax, ay, bx, by))


def _pad_shape(block):
    m = re.search(r'\(pad "[^"]*"\s+\S+\s+(\w+)', block)
    return m.group(1) if m else "rect"


def _d_seg_pad(ax, ay, bx, by, pad):
    """Edge-to-edge distance from segment AB to a pad, EXACT for rect/roundrect/circle/oval.

    The pad is an inset axis-aligned box in its own frame plus a corner radius, so the work is
    a segment-to-box distance there and one subtraction. Falls back to the old capsule if a pad
    somehow has no frame -- a parser that silently changes shape is the thing this module keeps
    being bitten by, so the fallback is explicit rather than implied."""
    if "ihx" not in pad:
        return _d_pt_seg(ax, ay, pad["x1"], pad["y1"], pad["x2"], pad["y2"]) - pad["r"]
    ca, sa = pad["ca"], pad["sa"]
    gx, gy = pad["gx"], pad["gy"]

    def loc(x, y):
        dx, dy = x - gx, y - gy
        return (dx * ca + dy * sa, -dx * sa + dy * ca)

    ux, uy = loc(ax, ay)
    vx, vy = loc(bx, by)
    hx, hy = pad["ihx"], pad["ihy"]
    inside = (abs(ux) <= hx and abs(uy) <= hy) or (abs(vx) <= hx and abs(vy) <= hy)
    if inside:
        return -pad["cr"]
    best = 1e9
    corners = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
    for i in range(4):
        cx, cy = corners[i]
        dx, dy = corners[(i + 1) % 4]
        d = _d_seg_seg(ux, uy, vx, vy, cx, cy, dx, dy)
        if d < best:
            best = d
    return best - pad["cr"]


class Board:
    def __init__(self, stem, net):
        txt = open(stem + ".kicad_pcb", encoding="utf-8").read()
        self.net = net
        self.segs = _segments(txt)
        self.vias = _vias(txt)
        self.pads = _pads(txt)
        self.edges = _edges(txt)
        self.edge_clear = _edge_clearance(stem)
        # ⚠ AND THE POURS, which this class did not model at all until 2026-09-30.
        self.zones = _zones(txt)
        self.zone_clear = _zone_clearance(stem)

    def via_ok(self, x, y, r=VIA_D / 2.0):
        # the caller's own small soldered lands: a hole there takes the joint's paste
        for cx, cy, hx, hy in getattr(self, "own_lands", ()):
            if abs(x - cx) < hx + VIA_DRILL / 2.0 + 0.05 and abs(y - cy) < hy + VIA_DRILL / 2.0 + 0.05:
                return False
        for s in self.segs:
            if s["net"] == self.net:
                continue
            if _d_pt_seg(x, y, s["x1"], s["y1"], s["x2"], s["y2"]) < r + s["half"] + MARGIN:
                return False
        for v in self.vias:
            if v["net"] == self.net:
                continue
            if math.hypot(x - v["x"], y - v["y"]) < r + v["r"] + MARGIN:
                return False
        for p in self.pads:                       # pads: capsules, not circles
            if p["net"] == self.net:
                continue
            if _d_seg_pad(x, y, x, y, p) < r + MARGIN:
                return False
        for e in self.edges:                      # and the outline, at ITS rule
            if _d_pt_seg(x, y, *e) < r + max(MARGIN, getattr(self, "edge_clear", 0.3)):
                return False
        return True

    def track_gap(self, p, q, layer, half=TRACK_W / 2.0):
        """Smallest EDGE-TO-EDGE gap this track leaves, and what it is against.

        ⚠ track_ok() answers a SEARCH question -- "is there comfortable room here" -- by
        demanding MARGIN (0.15) on top of every obstacle, which is deliberately more than
        the netclass rule (0.127). That is right when CHOOSING a path and wrong as the
        only verdict on one that has already been measured and DRC-checked: it cannot
        tell "breaks the rule" from "legal but tighter than we like to search for", and
        those deserve different words. This returns the number so the caller can say
        which it is.
        """
        worst, who = 1e9, None
        for s in self.segs:
            if s["layer"] != layer or s["net"] == self.net:
                continue
            d = _d_seg_seg(*p, *q, s["x1"], s["y1"], s["x2"], s["y2"]) - half - s["half"]
            if d < worst:
                worst, who = d, "track [%s]" % s["net"]
        for v in self.vias:
            if v["net"] == self.net:
                continue
            d = _d_pt_seg(v["x"], v["y"], *p, *q) - half - v["r"]
            if d < worst:
                worst, who = d, "via [%s]" % v["net"]
        for pd in self.pads:
            if pd["net"] == self.net:
                continue
            if pd.get("cu") is not None and layer not in pd["cu"]:
                continue                      # see _pads: an F.Cu pad is not a B.Cu obstacle
            d = _d_seg_pad(*p, *q, pd) - half
            if d < worst:
                worst, who = d, "pad [%s]" % (pd["net"] or "no net")
        for e in self.edges:
            d = _d_seg_seg(*p, *q, *e) - half
            if d < worst:
                worst, who = d, "board edge"
        return worst, who

    def zone_gap(self, p, q, layer, half=TRACK_W / 2.0):
        """Edge-to-edge gap from this track to the nearest FOREIGN copper pour, and its net.

        ⚠ KEPT SEPARATE FROM track_gap ON PURPOSE. The two answer to DIFFERENT RULES -- the
        netclass clearance (0.127 on optical) for tracks, pads, vias and the outline, and the
        zone clearance (0.5000) for pours. Folding pours into track_gap would return one "worst
        gap" that the caller then compares against one rule, which is exactly the mistake that
        approved a dog-leg sitting 0.0225 mm from the ground pour: the number was true and the
        rule it was judged against was the wrong one.
        """
        worst, who = 1e9, None
        reach = half + self.zone_clear + 1.0
        for z in self.zones:
            if z["layer"] != layer or z["net"] == self.net:
                continue
            d = _d_seg_poly(p[0], p[1], q[0], q[1], z, reach) - half
            if d < worst:
                worst, who = d, "zone [%s] on %s" % (z["net"] or "?", z["layer"])
        return worst, who

    def zone_ok(self, p, q, layer, half=TRACK_W / 2.0):
        g, _ = self.zone_gap(p, q, layer, half)
        return g >= self.zone_clear

    def track_ok(self, p, q, layer, half=TRACK_W / 2.0, pours=False):
        """Is there comfortable room for this track? `pours` decides whether the EXISTING
        copper pours count as obstacles, and the default is NO. That is not laziness:

        ⚠ A POST-ROUTE REPAIR IS FOLLOWED BY A ZONE REFILL, so the pour that is on the board
        while we search is NOT the pour the repair will live in -- repair_planes.py refills,
        and the fill retreats around whatever copper it finds. Treating the old pour as an
        obstacle rejects paths that work: it declared optical's +3V3D dog-leg at U6.36
        impossible ("0 legal dog-legs") when laying that exact path and refilling gives DRC
        violations IDENTICAL to the baseline and zero clearance. I had this switched on by
        default for one tick and it hid a repair that was already proven good.

        Pass pours=True to ask the other question -- "is this legal against the board AS IT
        STANDS" -- which is what an auditor wants, and what audit_board asks through zone_gap.
        """
        if pours and not self.zone_ok(p, q, layer, half):
            return False
        for s in self.segs:
            if s["layer"] != layer or s["net"] == self.net:
                continue
            if _d_seg_seg(*p, *q, s["x1"], s["y1"], s["x2"], s["y2"]) < half + s["half"] + MARGIN:
                return False
        for v in self.vias:
            if v["net"] == self.net:
                continue
            if _d_pt_seg(v["x"], v["y"], *p, *q) < half + v["r"] + MARGIN:
                return False
        for pd in self.pads:
            if pd["net"] == self.net:
                continue
            if pd.get("cu") is not None and layer not in pd["cu"]:
                continue                      # an F.Cu pad does not block a B.Cu track
            if _d_seg_pad(*p, *q, pd) < half + MARGIN:
                return False
        for e in self.edges:
            if _d_seg_seg(*p, *q, *e) < half + MARGIN:
                return False
        return True


# ── the third shape: a MAZE path, because the first two cannot bend ────────────────────
# ⚠ WHY THIS EXISTS, IN NUMBERS. search() above offers a straight track or via-plus-spur.
# On optical's +3V3A at U11.5 that returns 0 same-layer paths and 755 via paths whose SHORTEST
# is 48.92 mm -- for a net whose nearest island is 6.97 mm away. It aims at whatever point of
# the net it can reach and on B.Cu that is 40 mm off, which this module's own notes already
# call out: it has "no notion that its own net's copper is a destination rather than an
# obstacle". A 40 mm hand-laid trace is not a repair, it is a liability.
# A dog-leg was searched by hand and found nothing here either, and so did via -> In2 -> via.
# ⚠ AND THE DIAGNOSTIC IS WHAT MADE THAT LAST ONE MEAN SOMETHING: 63 legal via sites beside the
# pad, 224-563 beside each island, and all ~8000 sampled pairs failing on the RUN BETWEEN THEM.
# The endpoints were never the problem. In2.Cu carries no pour -- which is what made it look
# like the free layer -- but the board's 400 vias pierce EVERY layer, so a straight run across
# it meets them. Emptiness of pour is not emptiness of obstacles, and the answer is a path that
# can bend around them.
MAZE_STEP = 0.15               # grid pitch; below the rule, so adjacent free cells overlap
MAZE_PAD = 4.0                 # how far outside the start/goal box the search may wander


class _Index:
    """Uniform bucket index over one layer's obstacles, so a cell test looks at ~10 of them
    instead of ~2700. Built once per (layer, net) and reused for every cell of the search."""

    CELL = 2.0

    def __init__(self, board, layer):
        self.b, self.layer, self.g = board, layer, {}
        for s_ in board.segs:
            if s_["layer"] != layer or s_["net"] == board.net:
                continue
            self._put(min(s_["x1"], s_["x2"]), min(s_["y1"], s_["y2"]),
                      max(s_["x1"], s_["x2"]), max(s_["y1"], s_["y2"]),
                      ("seg", s_["x1"], s_["y1"], s_["x2"], s_["y2"], s_["half"]))
        for v in board.vias:
            if v["net"] == board.net:
                continue
            # ⚠ EVERY LAYER. A via is a plated hole through the whole stack, so it obstructs
            # In2 exactly as it obstructs F.Cu -- which is the entire reason the "empty" inner
            # layer was not empty.
            self._put(v["x"] - v["r"], v["y"] - v["r"], v["x"] + v["r"], v["y"] + v["r"],
                      ("pt", v["x"], v["y"], v["r"]))
        for pd in board.pads:
            if pd["net"] == board.net:
                continue
            if pd.get("cu") is not None and layer not in pd["cu"]:
                continue
            _xs = [q[0] for q in pd["poly"]] if pd.get("poly") else [pd["x1"], pd["x2"]]
            _ys = [q[1] for q in pd["poly"]] if pd.get("poly") else [pd["y1"], pd["y2"]]
            self._put(min(_xs) - pd["r"], min(_ys) - pd["r"],
                      max(_xs) + pd["r"], max(_ys) + pd["r"], ("pad", pd))
        # the outline carries the EXTRA its own rule asks over the netclass clearance the
        # caller inflates by, as if it were a track that wide (see _edge_clearance)
        _eh = max(0.0, getattr(board, "edge_clear", 0.3) - RULE_CLEAR)
        for e in board.edges:
            self._put(min(e[0], e[2]) - _eh, min(e[1], e[3]) - _eh,
                      max(e[0], e[2]) + _eh, max(e[1], e[3]) + _eh,
                      ("seg", e[0], e[1], e[2], e[3], _eh))

    def _put(self, x0, y0, x1, y1, item):
        c = self.CELL
        for gx in range(int(math.floor(x0 / c)) - 1, int(math.floor(x1 / c)) + 2):
            for gy in range(int(math.floor(y0 / c)) - 1, int(math.floor(y1 / c)) + 2):
                self.g.setdefault((gx, gy), []).append(item)

    def clear(self, x, y, r):
        """Is a disc of radius r at (x, y) clear of every foreign obstacle on this layer?"""
        for it in self.g.get((int(math.floor(x / self.CELL)), int(math.floor(y / self.CELL))), ()):
            if it[0] == "pad":
                if _d_seg_pad(x, y, x, y, it[1]) < r:
                    return False
            elif it[0] == "pt":
                if math.hypot(x - it[1], y - it[2]) < r + it[3]:
                    return False
            else:
                if _d_pt_seg(x, y, it[1], it[2], it[3], it[4]) < r + it[5]:
                    return False
        return True


def maze(board, layer, start, goal, w=TRACK_W, step=MAZE_STEP, clearance=None, reach=None):
    """A grid path from `start` to `goal` on `layer` that bends around obstacles.

    Returns a simplified list of points, or None. `clearance` defaults to the netclass rule
    rather than this module's SEARCH margin -- a repair that exists at all beats one that is
    comfortable, and every segment is re-measured with track_gap afterwards either way.

    ⚠ POURS ARE NOT OBSTACLES HERE, deliberately: a post-route repair is followed by a zone
    refill (repair_planes), so the pour on the board now is not the pour the repair will live
    in. See track_ok's note -- treating the old pour as solid once declared a proven-good
    dog-leg impossible.
    """
    import heapq

    clr = RULE_CLEAR if clearance is None else clearance
    # ⚠ THE GRID GUARANTEES LESS THAN THE DISC IT TESTS, AND THIS IS THE WHOLE GUARD BAND.
    # Two adjacent cleared cells are step*sqrt(2) apart at worst, so every point of the segment
    # between them is within step*sqrt(2)/2 of one centre -- and a disc of radius r therefore
    # guarantees only r - step*sqrt(2)/2 along the track. Asking for the rule and getting
    # 0.121 back is not a model error, it is that half-diagonal, and it cost three
    # lay-measure-bump cycles before it was named: 0.175 failed, 0.26 worked, and the boundary
    # is exactly 0.127 + 0.106. Inflate here so the CALLER's clearance is the one delivered.
    r = w / 2.0 + clr + step * math.sqrt(2.0) / 2.0
    idx = _Index(board, layer)
    reach = MAZE_PAD if reach is None else reach
    x0 = min(start[0], goal[0]) - reach
    x1 = max(start[0], goal[0]) + reach
    y0 = min(start[1], goal[1]) - reach
    y1 = max(start[1], goal[1]) + reach

    def key(p):
        return (int(round((p[0] - x0) / step)), int(round((p[1] - y0) / step)))

    def pos(k):
        return (x0 + k[0] * step, y0 + k[1] * step)

    sk, gk = key(start), key(goal)
    nx = int((x1 - x0) / step) + 1
    ny = int((y1 - y0) / step) + 1
    # ⚠ THE ENDPOINTS ARE EXEMPT FROM THE CELL TEST. They sit ON their own net's copper, which
    # is not an obstacle -- but the pad they touch often puts foreign copper inside r, and a
    # search that refuses to start is indistinguishable from one that finds nothing.
    seen = {sk: None}
    pq = [(0.0, 0.0, sk)]
    diag = math.sqrt(2.0) * step
    while pq:
        _f, g, k = heapq.heappop(pq)
        if k == gk:
            break
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nk = (k[0] + dx, k[1] + dy)
                if nk in seen or not (0 <= nk[0] < nx and 0 <= nk[1] < ny):
                    continue
                q = pos(nk)
                if nk != gk and not idx.clear(q[0], q[1], r):
                    continue
                ng = g + (diag if dx and dy else step)
                h = math.hypot(q[0] - goal[0], q[1] - goal[1])
                seen[nk] = k
                heapq.heappush(pq, (ng + h, ng, nk))
    if gk not in seen:
        return None
    path = []
    k = gk
    while k is not None:
        path.append(pos(k))
        k = seen[k]
    path.reverse()
    path[0], path[-1] = start, goal
    # collapse collinear runs so the result is a few segments, not hundreds
    out = [path[0]]
    for i in range(1, len(path) - 1):
        ax, ay = out[-1]
        bx, by = path[i]
        cx, cy = path[i + 1]
        if abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) > 1e-9:
            out.append(path[i])
    out.append(path[-1])
    return out


def _flood(idx, start, x0, y0, nx, ny, step, r, goal=None):
    """Dijkstra over the free cells of one layer from `start`. Returns (cost, parent), both
    keyed by grid cell. `goal`, if given, is exempt from the clearance test for the same
    reason `start` always is -- an endpoint sits ON its own net's copper while foreign copper
    is often inside the radius, and a flood that refuses to finish looks exactly like one that
    found nothing."""
    import heapq

    def key(pt):
        return (int(round((pt[0] - x0) / step)), int(round((pt[1] - y0) / step)))

    def pos(k):
        return (x0 + k[0] * step, y0 + k[1] * step)

    sk = key(start)
    gk = key(goal) if goal is not None else None
    cost = {sk: 0.0}
    parent = {sk: None}
    pq = [(0.0, sk)]
    diag = math.sqrt(2.0) * step
    while pq:
        g, k = heapq.heappop(pq)
        if g > cost.get(k, 1e18):
            continue
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nk = (k[0] + dx, k[1] + dy)
                if not (0 <= nk[0] < nx and 0 <= nk[1] < ny):
                    continue
                ng = g + (diag if dx and dy else step)
                if ng >= cost.get(nk, 1e18):
                    continue
                q = pos(nk)
                if nk != gk and not idx.clear(q[0], q[1], r):
                    continue
                cost[nk] = ng
                parent[nk] = k
                heapq.heappush(pq, (ng, nk))
    return cost, parent


def _walk(parent, k, x0, y0, step, endpoint):
    out = []
    while k is not None:
        out.append((x0 + k[0] * step, y0 + k[1] * step))
        k = parent[k]
    out.reverse()
    # ⚠ out[0] IS THE FLOOD'S SOURCE AND out[-1] IS THE JOIN CELL. Snapping out[-1] instead
    # -- which the first version did -- overwrites the join with the endpoint and invents a
    # segment straight across the board. It showed up as a path the flood had certified at
    # 0.175 clearance whose measured gaps were -0.2135 and -0.2990: the flood was fine, the
    # reconstruction was not. track_gap caught it before a single track was laid, which is the
    # whole reason the caller re-measures instead of trusting the search.
    out[0] = endpoint
    keep = [out[0]]
    for i in range(1, len(out) - 1):
        ax, ay = keep[-1]
        bx, by = out[i]
        cx, cy = out[i + 1]
        if abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) > 1e-9:
            keep.append(out[i])
    keep.append(out[-1])
    return keep


def maze_via(board, layer_a, layer_b, start, goal, w=TRACK_W, step=MAZE_STEP,
             clearance=None, reach=None, via_d=VIA_D):
    """A repair that CHANGES LAYER: maze on `layer_a` from `start`, one via, maze on
    `layer_b` to `goal`. Returns (path_a, (vx, vy), path_b) or None.

    ⚠ THE SHAPE BOTH REMAINING OPTICAL NETS NEED. maze() is single-layer, and what is left on
    that board is cross-layer: +3V3A's second break is F.Cu to In2.Cu, and SAI_FS has no F.Cu
    path at any clearance across its 20.97 mm. The old two-via bridge search failed for a
    different reason -- it only tried STRAIGHT runs between via sites, and the run is exactly
    what is blocked.

    ⚠ FLOOD BOTH LAYERS ONCE, THEN JOIN -- do not maze per candidate via. There are hundreds of
    legal via sites (63 beside one pad, 224-563 beside the islands), and mazing for each would
    be hundreds of searches. Two Dijkstra floods and a scan over the shared cells gives the
    optimal join for the cost of two searches, which is what makes this usable at all.
    """
    clr = RULE_CLEAR if clearance is None else clearance
    r = w / 2.0 + clr + step * math.sqrt(2.0) / 2.0   # see maze()'s note on the half-diagonal
    reach = MAZE_PAD if reach is None else reach
    x0 = min(start[0], goal[0]) - reach
    x1 = max(start[0], goal[0]) + reach
    y0 = min(start[1], goal[1]) - reach
    y1 = max(start[1], goal[1]) + reach
    nx = int((x1 - x0) / step) + 1
    ny = int((y1 - y0) / step) + 1

    ca, pa = _flood(_Index(board, layer_a), start, x0, y0, nx, ny, step, r)
    cb, pb = _flood(_Index(board, layer_b), goal, x0, y0, nx, ny, step, r)

    best = None
    vr = via_d / 2.0 + clr
    for k, g in ca.items():
        gb = cb.get(k)
        if gb is None:
            continue
        tot = g + gb
        if best is not None and tot >= best[0]:
            continue
        vx, vy = x0 + k[0] * step, y0 + k[1] * step
        # ⚠ THE VIA IS CHECKED AGAINST EVERY LAYER, not the two it joins: it is a plated hole
        # through the whole stack. That is the same fact that made In2 "empty of pour but not
        # of obstacles", and getting it wrong here would put a drill through someone's track.
        if not board.via_ok(vx, vy, r=vr):
            continue
        best = (tot, k, (vx, vy))
    if best is None:
        return None
    _tot, k, v = best
    # pa runs start -> join; pb comes back goal -> join, so it is reversed to join -> goal.
    return (_walk(pa, k, x0, y0, step, start), v,
            list(reversed(_walk(pb, k, x0, y0, step, goal))))


def maze3d(board, layers, start, start_layer, goal, goal_layer, w=TRACK_W, step=MAZE_STEP,
           clearance=None, reach=None, via_d=VIA_D, via_cost=2.0):
    """The general repair: route over (x, y, LAYER), where a via is an EDGE between layers.

    Returns (runs, vias) with runs = [(layer, [pts...]), ...] and vias = [(x, y), ...], or None.

    ⚠ THIS SUBSUMES maze() AND maze_via(), AND SAI_FS IS WHY IT HAD TO EXIST. Both its islands
    are on F.Cu with no F.Cu path at any clearance, so the repair needs to leave the layer AND
    COME BACK -- two via transitions, which a one-via search cannot express by construction. The
    old disabled SAI_FS repair went F.Cu -> B.Cu -> In2.Cu -> F.Cu, three of them.

    ⚠ VIA COST IS NOT ZERO. At zero the search hops layers whenever a cell is momentarily
    cheaper and returns a staircase of dozens of vias that is legal and absurd. `via_cost` is in
    millimetres of equivalent track, so 2.0 says "a layer change is worth 2 mm of detour".
    """
    import heapq

    clr = RULE_CLEAR if clearance is None else clearance
    # the same half-diagonal guard band maze() documents: the grid guarantees r - step*sqrt2/2
    r = w / 2.0 + clr + step * math.sqrt(2.0) / 2.0
    reach = MAZE_PAD if reach is None else reach
    x0 = min(start[0], goal[0]) - reach
    x1 = max(start[0], goal[0]) + reach
    y0 = min(start[1], goal[1]) - reach
    y1 = max(start[1], goal[1]) + reach
    nx = int((x1 - x0) / step) + 1
    ny = int((y1 - y0) / step) + 1
    idx = {L: _Index(board, L) for L in layers}
    li = {L: i for i, L in enumerate(layers)}
    vr = via_d / 2.0 + clr

    def pos(k):
        return (x0 + k[0] * step, y0 + k[1] * step)

    def key(pt):
        return (int(round((pt[0] - x0) / step)), int(round((pt[1] - y0) / step)))

    sk, gk = key(start), key(goal)
    S = (sk[0], sk[1], li[start_layer])
    G = (gk[0], gk[1], li[goal_layer])
    cost = {S: 0.0}
    parent = {S: None}
    pq = [(0.0, S)]
    diag = math.sqrt(2.0) * step
    via_ok_cache = {}
    while pq:
        g, n = heapq.heappop(pq)
        if n == G:
            break
        if g > cost.get(n, 1e18):
            continue
        kx, ky, L = n
        # in-plane
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nk = (kx + dx, ky + dy, L)
                if not (0 <= nk[0] < nx and 0 <= nk[1] < ny):
                    continue
                ng = g + (diag if dx and dy else step)
                if ng >= cost.get(nk, 1e18):
                    continue
                q = pos(nk)
                if nk != G and not idx[layers[L]].clear(q[0], q[1], r):
                    continue
                cost[nk] = ng
                parent[nk] = n
                heapq.heappush(pq, (ng, nk))
        # layer change: one via, at this cell, through the whole stack
        c = via_ok_cache.get((kx, ky))
        if c is None:
            q = pos((kx, ky))
            c = board.via_ok(q[0], q[1], r=vr)
            via_ok_cache[(kx, ky)] = c
        if not c:
            continue
        for L2 in range(len(layers)):
            if L2 == L:
                continue
            nk = (kx, ky, L2)
            ng = g + via_cost
            if ng >= cost.get(nk, 1e18):
                continue
            cost[nk] = ng
            parent[nk] = n
            heapq.heappush(pq, (ng, nk))
    if G not in parent:
        return None
    chain = []
    n = G
    while n is not None:
        chain.append(n)
        n = parent[n]
    chain.reverse()
    runs, vias, cur, curL = [], [], [], chain[0][2]
    for n in chain:
        if n[2] != curL:
            vias.append(pos((n[0], n[1])))
            if len(cur) > 1:
                runs.append((layers[curL], cur))
            cur, curL = [pos((n[0], n[1]))], n[2]
        cur.append(pos((n[0], n[1])))
    if len(cur) > 1:
        runs.append((layers[curL], cur))
    # snap the two ends and drop collinear interior points
    if runs:
        runs[0][1][0] = start
        runs[-1][1][-1] = goal
    out = []
    for L, pts in runs:
        keep = [pts[0]]
        for i in range(1, len(pts) - 1):
            ax, ay = keep[-1]
            bx, by = pts[i]
            cx, cy = pts[i + 1]
            if abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) > 1e-9:
                keep.append(pts[i])
        keep.append(pts[-1])
        out.append((L, keep))
    return out, vias


def search(stem, net, pad_xy, top=5):
    """Return (board, direct_paths, via_paths).

    ⚠ TWO SHAPES OF REPAIR, AND AN EARLIER VERSION ONLY KNEW ONE. A break is often a
    gap on the SAME layer the pad is on -- MID's was 2.54 mm straight up F.Cu -- and
    needs no via at all. That version modelled only via-plus-spur and reported "0 legal
    paths" for a net whose repair is one straight track, which reads as impossible when
    it is actually trivial.

    ⚠ AND IT TARGETED B.Cu ONLY. MID carries 132 segments on F.Cu, 52 on In2.Cu and 3
    on B.Cu, so hunting B.Cu alone aimed at the 3 and ignored the 52. In2.Cu is the one
    layer with no ground pour on this board, i.e. the emptiest place to land. Target
    every layer the net actually occupies, and let the distance decide.
    """
    b = Board(stem, net)
    own = [s for s in b.segs if s["net"] == net]
    if not own:
        raise SystemExit("no copper on %s to reach" % net)

    def points_on(layer):
        out = []
        for s in own:
            if s["layer"] != layer:
                continue
            for k in (0.0, 0.25, 0.5, 0.75, 1.0):
                out.append((s["x1"] + (s["x2"] - s["x1"]) * k,
                            s["y1"] + (s["y2"] - s["y1"]) * k))
        return out

    # shape 1: a straight track on the pad's own layer, no via
    direct = []
    for (tx, ty) in points_on("F.Cu"):
        if b.track_ok(pad_xy, (tx, ty), "F.Cu"):
            direct.append((round(math.hypot(tx - pad_xy[0], ty - pad_xy[1]), 3),
                           round(tx, 3), round(ty, 3)))
    direct.sort()

    # shape 2: via to another layer, then a spur to the net's copper there
    layers = [L for L in ("In2.Cu", "B.Cu") if any(s["layer"] == L for s in own)]
    found = []
    n = int(REACH / GRID)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            vx, vy = round(pad_xy[0] + i * GRID, 3), round(pad_xy[1] + j * GRID, 3)
            if not b.via_ok(vx, vy):
                continue
            if not b.track_ok(pad_xy, (vx, vy), "F.Cu"):
                continue
            for L in layers:
                hit = None
                for (tx, ty) in points_on(L):
                    if b.track_ok((vx, vy), (tx, ty), L):
                        hit = (tx, ty)
                        break
                if hit:
                    found.append((round(math.hypot(vx - pad_xy[0], vy - pad_xy[1])
                                        + math.hypot(hit[0] - vx, hit[1] - vy), 3),
                                  vx, vy, round(hit[0], 3), round(hit[1], 3), L))
                    break
    found.sort()
    return b, direct, found


def main(argv):
    if len(argv) < 5:
        raise SystemExit(__doc__.strip().splitlines()[2].strip())
    stem, net, ref, pad = argv[1], argv[2], argv[3], argv[4]
    d = json.load(open(stem + ".finish.drc.json", encoding="utf-8"))
    xy = None
    for v in d.get("unconnected_items", []):
        for it in v["items"]:
            if ("Pad %s" % pad) in it["description"] and ("of %s" % ref) in it["description"]:
                xy = (it["pos"]["x"], it["pos"]["y"])
    if xy is None:
        raise SystemExit("pad %s of %s is not reported unconnected -- nothing to repair"
                         % (pad, ref))
    b, direct, found = search(stem, net, xy)
    print("obstacles: %d segments, %d vias, %d pads, %d edge lines"
          % (len(b.segs), len(b.vias), len(b.pads), len(b.edges)))
    print("target pad %s.%s at (%.4f, %.4f)" % (ref, pad, xy[0], xy[1]))
    print("same-layer paths (no via): %d      via paths: %d" % (len(direct), len(found)))
    for t, tx, ty in direct[:3]:
        print("   F.Cu straight to (%.2f, %.2f)   %.2f mm" % (tx, ty, t))
    for t, vx, vy, tx, ty, L in found[:3]:
        print("   via(%.2f, %.2f) -> %s (%.2f, %.2f)   total %.2f mm" % (vx, vy, L, tx, ty, t))
    if direct:
        t, tx, ty = direct[0]
        print()
        print("    # one track, no via -- the break is on the pad's own layer")
        print('    "repair_tracks": [("%s", "F.Cu", %.2f, [(%.3f, %.3f), (%.3f, %.3f)])],'
              % (net, TRACK_W, xy[0] - 100, 100 - xy[1], tx - 100, 100 - ty))
    elif found:
        t, vx, vy, tx, ty, L = found[0]
        print()
        print('    "repair_vias": [("%s", %.3f, %.3f)],' % (net, vx - 100, 100 - vy))
        print('    "repair_tracks": [("%s", "F.Cu", %.2f, [(%.3f, %.3f), (%.3f, %.3f)]),'
              % (net, TRACK_W, xy[0] - 100, 100 - xy[1], vx - 100, 100 - vy))
        print('                      ("%s", "%s", %.2f, [(%.3f, %.3f), (%.3f, %.3f)])],'
              % (net, L, TRACK_W, vx - 100, 100 - vy, tx - 100, 100 - ty))
    return 0 if (direct or found) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
