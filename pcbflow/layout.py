"""Netlist + placement -> a .kicad_pcb with every part already where it belongs.

    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/layout.py elec/out/can_tee

RUNS UNDER KICAD'S OWN PYTHON, not the project's 3.12: it needs `pcbnew`, which
ships only inside the KiCad install. That is also why it talks to the rest of
the project through a JSON file rather than importing anything -- KiCad's Python
has no cadquery, so it can never import src/. The board module (e.g.
elec/can_tee.py) runs under 3.12, reads the mechanical model, and writes both
the netlist and `<board>.board.json`; this reads the pair and writes the board.

WHY NOT kinet2pcb, the obvious existing tool: it hardcodes a list of KiCad
install paths that stops at 9.0, so it cannot find a KiCad 10 installation at
all, and it places parts by a generic auto-arranger. We need the opposite of an
auto-arranger -- the whole point is that these positions come from the
instrument's geometry.

⚠ EXPIRY: `pcbnew` is the SWIG binding, deprecated since KiCad 9 and slated for
removal in KiCad 11. When that lands, this one file is what has to move to the
IPC API (`kicad-python`); nothing else in elec/ imports pcbnew.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import re
import sys

import pcbnew
import wx
# ⚠ NO MODAL DIALOGS IN A BUILD STEP. KiCad's Python is a wxWidgets application, and a
# failed internal assertion pops a GUI alert -- "Do you want to stop the program?" -- and
# WAITS. On a developer's machine that is a surprise; in any automated run it is a hang
# with no output and no exit code, and the whole point of this directory is that someone
# can run it unattended years from now. One real assertion (a KiCad 10 API change in
# PCB_VIA::GetWidth) surfaced this, and the assertion was worth fixing on its own -- but
# a pipeline that CAN block on a dialog is a defect independent of which dialog it is.
wx.DisableAsserts()


def project_dir(stem=None):
    """The folder a board's GENERATOR lives in -- `elec/` for a stem `elec/out/<board>`.

    Everything project-specific hangs off it: `<board>.py` (the generator finish.py checks
    the netlist against), `footprints/` (the project's own `.pretty` libraries) and the
    optional hook scripts finish.py looks for. $PCBFLOW_PROJECT overrides it.
    """
    env = os.environ.get("PCBFLOW_PROJECT")
    if env:
        return os.path.abspath(env)
    if stem is None:
        args = [a for a in sys.argv[1:] if not a.startswith("-")]
        if not args:
            return None
        stem = args[-1]
    return os.path.dirname(os.path.dirname(os.path.abspath(stem)))


def _kicad_footprints():
    """KiCad's own footprint tree: the env var KiCad itself honours, else beside the
    interpreter this is running under (<KiCad>/bin/python.exe -> <KiCad>/share/kicad)."""
    env = os.environ.get("KICAD10_FOOTPRINT_DIR")
    if env:
        return env
    guess = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(sys.executable))),
                         "share", "kicad", "footprints")
    return guess if os.path.isdir(guess) else r"C:\Program Files\KiCad\10.0\share\kicad\footprints"


# KiCad's library first, then the PROJECT's own `footprints/` folder (each `<lib>.pretty`
# in it is library `<lib>`), for parts KiCad has no land for -- draw each one from its
# maker's recommended land pattern. $PCBFLOW_FOOTPRINT_DIRS adds more (os.pathsep-separated).
FP_DIRS = [_kicad_footprints()]
if project_dir():
    FP_DIRS.append(os.path.join(project_dir(), "footprints"))
FP_DIRS += [d for d in os.environ.get("PCBFLOW_FOOTPRINT_DIRS", "").split(os.pathsep) if d]


# ── a very small S-expression reader (the netlist is all we parse) ───────────
def _sexp(text: str):
    tok, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            tok.append(c); i += 1
        elif c == '"':
            j = i + 1
            while text[j] != '"' or text[j - 1] == "\\":
                j += 1
            tok.append(text[i + 1:j]); i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            tok.append(text[i:j]); i = j

    def build(k):
        out = []
        while tok[k] != ")":
            if tok[k] == "(":
                sub, k = build(k + 1)
                out.append(sub)
            else:
                out.append(tok[k]); k += 1
        return out, k + 1

    assert tok[0] == "("
    return build(1)[0]


def _find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def _val(node, key, default=None):
    hit = _find(node, key)
    return hit[0][1] if hit and len(hit[0]) > 1 else default


def read_netlist(path):
    """-> ({ref: (footprint, value)}, {net_name: [(ref, pad), ...]})"""
    root = _sexp(open(path, encoding="utf-8").read())
    comps = {}
    for block in _find(root, "components"):
        for c in _find(block, "comp"):
            comps[_val(c, "ref")] = (_val(c, "footprint"), _val(c, "value", ""))
    nets = {}
    for block in _find(root, "nets"):
        for nt in _find(block, "net"):
            nets[_val(nt, "name")] = [(_val(nd, "ref"), _val(nd, "pin"))
                                      for nd in _find(nt, "node")]
    return comps, nets


# ── board frame ──────────────────────────────────────────────────────────────
# Board-local millimetres have the ORIGIN AT THE BOARD CENTRE with +Y up, which
# is how src/ describes everything. KiCad's page has +Y DOWN and wants the board
# somewhere sensible on the sheet, so every placement goes through here and the
# sign flip lives in exactly one place.
SHEET_ORIGIN = (100.0, 100.0)

# ⚠ DRILL-TO-DRILL, AND IT IS NOT THE COPPER CLEARANCE. Two holes may not share
# laminate even when the copper around them is one net and shorting them is the intent.
# 0.30 mm is chosen against three numbers, not rounded: JLCPCB's published minimum is
# "Via Hole-to-Hole Spacing 0.2mm", KiCad's default board rule -- the one that actually
# reports it -- is 0.25, and their stated hole POSITION tolerance is +-0.05. Sitting at
# 0.25 would satisfy DRC and still let two holes drilled at opposite ends of that
# tolerance meet; 0.30 keeps the full tolerance in hand above the fab limit.
HOLE_GAP = 300000            # 0.30 mm in KiCad internal units (1 nm)



def _to_board(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(SHEET_ORIGIN[0] + x),
                           pcbnew.FromMM(SHEET_ORIGIN[1] - y))


def _load_footprint(spec):
    lib, name = spec.split(":", 1)
    for d in FP_DIRS:
        path = os.path.join(d, lib + ".pretty")
        if os.path.isdir(path):
            fp = pcbnew.FootprintLoad(path, name)
            if fp:
                return fp
    raise SystemExit("footprint not found: %s (looked in %s)" % (spec, FP_DIRS))


# ⚠ A STOCK FOOTPRINT'S ANNULAR RING IS NOT THE FAB'S. KiCad's 1.27 mm pin headers put a
# 1.0 mm pad on a 0.65 mm drill: 0.175 mm of ring, and JLCPCB's absolute minimum on two
# layers at 1 oz is 0.18 (0.15 on four and up). DRC is silent -- its annular rule guards
# vias, and the library is assumed right. The quality pass (A12) measures it; this is the
# fix, applied to every plated pad as it is loaded: a ring under the fab's minimum is grown
# to that minimum plus 0.02, and nothing else is touched. The drill is NOT shrunk -- the
# pin has to go in it, and the fab's hole tolerance is -0.08.
# BOARD_NOTES["min_pth_ring"] overrides the figure (0 turns it off).
PTH_RING = {2: 0.18, 4: 0.15}       # by copper layers; more than four uses the 4-layer figure
PTH_RING_MARGIN = 0.02


def _legible_fields(fp):
    """A footprint's own visible silk text (its designator, usually) at no less than the
    fab's legible minimum: 1.0 mm high, 0.15 stroke (quality A12). Library and local
    footprints carry whatever their author liked -- 0.8 x 0.12 is common."""
    for f in fp.GetFields():
        if f.IsVisible() and f.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            h, t = pcbnew.ToMM(f.GetTextHeight()), pcbnew.ToMM(f.GetTextThickness())
            if h < 0.999:
                f.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.0), pcbnew.FromMM(1.0)))
            if t < 0.149:
                f.SetTextThickness(pcbnew.FromMM(0.15))


def _grow_thin_rings(fp, layers, notes):
    want = notes.get("min_pth_ring")
    if want is None:
        want = PTH_RING[2 if layers <= 2 else 4]
    if not want:
        return 0
    n = 0
    for pad in fp.Pads():
        if pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
            continue
        d, sz = pad.GetDrillSize(), pad.GetSize()
        if min(d.x, d.y) <= 0:
            continue
        need = pcbnew.FromMM(want)
        if min(sz.x - d.x, sz.y - d.y) / 2.0 >= need - 1000:
            continue
        grow = pcbnew.FromMM(want + PTH_RING_MARGIN)
        pad.SetSize(pcbnew.VECTOR2I(max(sz.x, d.x + 2 * grow), max(sz.y, d.y + 2 * grow)))
        n += 1
    return n


def _place_ref(fp, target):
    """Put the reference designator at an absolute board position, upright and
    small. Left where the footprint puts it, a designator sits over the part --
    fine on a roomy board, but here the connector bodies fill most of the copper
    and the text lands on a neighbour's silk or off the edge. The free strips
    between the parts are the only place it can be READ once the board is
    populated, so the board module names them."""
    ref = fp.Reference()
    # 1.0 x 0.15: the fab's stated minimum height and stroke for legible silk (quality A12)
    ref.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.0), pcbnew.FromMM(1.0)))
    ref.SetTextThickness(pcbnew.FromMM(0.15))
    ref.SetPosition(target)
    ref.SetTextAngleDegrees(0.0)      # upright regardless of how the part turned
    ref.SetKeepUpright(True)


def _anchor_on_courtyard(fp, target):
    """Move `fp` so the CENTRE OF ITS COURTYARD sits on `target`.

    ⚠ THE OPTICAL BOARD PLACES BY COURTYARD, NOT BY PAD CENTROID, and it is the only
    one that does. Its placements come from src/optical_pickup.py, where a part's
    coordinate is the centre of the box that has to clear its neighbours, the cover and
    the strings -- a mechanical model reasons about envelopes, not about where the
    solder lands average out. For a two-pad passive the two agree; for a USB-C, a JST
    side-entry header, a SOT-223 or a SOT-23-5 they do not, because the pads sit
    asymmetrically in the body.

    Handing those coordinates to the pad-centroid anchor put four parts into their
    neighbours and hung J1's land off the board's -Y edge -- a shift of a couple of
    millimetres that is invisible in the model and fatal on the board. Rather than
    correcting the CAD (whose convention is right for what the CAD is for) or carrying
    a per-footprint offset table (which would be a second copy of the footprint library
    to keep true), the board says which convention it means and this runs here, where
    pcbnew can measure the footprint directly."""
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    c = bb.GetCenter()
    pos = fp.GetPosition()
    fp.SetPosition(pcbnew.VECTOR2I(pos.x + (target.x - c.x), pos.y + (target.y - c.y)))


def _anchor_on_pads(fp, target):
    """Move `fp` so the CENTROID OF ITS PADS sits on `target`.

    A KiCad footprint's origin is wherever its author put it, and for connectors
    that is almost always PAD 1 -- the JST B4B-XH-A's courtyard runs x -3.00 to
    +10.49 about its origin. src/ places these parts by their PIN ROW instead
    (cadkit's jst_xh_header is centred on the row, which is what a mechanical
    drawing and a mating plug both care about), so handing the model's
    coordinate straight to SetPosition puts the connector 3.75 mm off and the
    error is invisible until something collides.

    Anchoring on the pad centroid makes the two agree for every part we place,
    without a per-footprint offset table to get wrong: it is the origin for
    two-pad passives, and the row centre for a symmetric header. Rotation is
    already applied when this runs, so the correction needs no trig."""
    pads = list(fp.Pads())
    cx = sum(p.GetPosition().x for p in pads) // len(pads)
    cy = sum(p.GetPosition().y for p in pads) // len(pads)
    pos = fp.GetPosition()
    fp.SetPosition(pcbnew.VECTOR2I(pos.x + (target.x - cx), pos.y + (target.y - cy)))


# counters for why a differential-pair hop could not be laid -- the failure message
# quotes them, because "no clear path" on its own sends you looking in the wrong place:
# 'escape' is a placement problem, 'run' an obstacle problem, 'edge' a board-outline one.
_DBG = {}


def _offset_poly(pts, ds, math):
    """`pts` offset by the signed per-vertex distances `ds`, corners mitred.

    This is the whole trick. Offsetting a polyline preserves parallelism through the
    bends, so two rails taken as +d and -d of one line keep their gap and cannot cross,
    however the line turns -- the pair property becomes a consequence of the
    construction instead of something checked for afterwards.

    ⚠ THE OFFSET VARIES PER VERTEX, which is not decoration. At a package the two rails
    have to start ON their own pads, and those are as far apart as the part's pitch
    makes them -- 1.9 mm across a SOT-563, 0.5 mm across a USB-C. Run out at the pair's
    own pitch instead and the rails leave the pads diagonally, straight into the lane
    of the pad BETWEEN them; on this board that missed the ESD array's ground pin by
    0.012 mm and failed every hop. Starting at the pad separation and tapering to the
    pair pitch over the escape is what a person draws, and it is the same polyline
    trick with one number per vertex rather than one for the line.
    """
    if not isinstance(ds, (list, tuple)):
        ds = [ds] * len(pts)
    segs = []
    for i, (p, q) in enumerate(zip(pts, pts[1:])):
        ux, uy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(ux, uy)
        if L == 0:
            continue
        ux, uy = ux / L, uy / L
        nx, ny = -uy, ux
        segs.append(((p[0] + ds[i] * nx, p[1] + ds[i] * ny),
                     (q[0] + ds[i + 1] * nx, q[1] + ds[i + 1] * ny)))
    if not segs:
        return list(pts)
    out = [segs[0][0]]
    for s1, s2 in zip(segs, segs[1:]):
        (x1, y1), (x2, y2) = s1
        (x3, y3), (x4, y4) = s2
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) < 1e-9:
            out.append(s1[1])
            continue
        e = x1 * y2 - y1 * x2
        f = x3 * y4 - y3 * x4
        out.append(((e * (x3 - x4) - (x1 - x2) * f) / den,
                    (e * (y3 - y4) - (y1 - y2) * f) / den))
    out.append(segs[-1][1])
    return out


def _centrelines(p0, p1, detour_mm=6.0, step_mm=0.5):
    """Candidate centrelines from p0 to p1, simplest first.

    Straight, then the two right-angle elbows, then Z routes with the crossbar swept
    across and BEYOND the two endpoints.

    ⚠ THE OVERSHOOT IS THE POINT OF THE Z FAMILY. One corner can only ever route inside
    the rectangle the two endpoints span, and the obstacle that stopped this pair -- a
    USB-C's own shell tab, 1 mm of through-plated copper sitting between the socket and
    the part that feeds it -- is inside that rectangle on every layer. Getting past it
    means going AROUND, which means a crossbar placed outside the span, which no
    one-corner shape can express.
    """
    out = [[p0, p1]]
    if p0[0] != p1[0] and p0[1] != p1[1]:
        out.append([p0, (p1[0], p0[1]), p1])
        out.append([p0, (p0[0], p1[1]), p1])
    step = pcbnew.FromMM(step_mm)
    reach = pcbnew.FromMM(detour_mm)
    for axis in (0, 1):
        lo, hi = sorted((p0[axis], p1[axis]))
        cs = [lo + k * step for k in range(int((hi - lo) // step) + 1)]
        # inside the span first, then working outwards on both sides
        for k in range(1, int(reach // step) + 1):
            cs += [lo - k * step, hi + k * step]
        for c in cs:
            if axis == 0:
                out.append([p0, (c, p0[1]), (c, p1[1]), p1])
            else:
                out.append([p0, (p0[0], c), (p1[0], c), p1])
    return out


def _pad_neck(m, pad, toward, width, clr):
    """The point a pair's centreline must reach, straight out of `pad`'s row, before it
    may start to turn or taper: along the pad's LONG axis, toward `toward`, far enough
    to clear the pad row's end plus a track's half-width and the clearance."""
    bb = pad.GetBoundingBox()
    w, h = bb.GetWidth(), bb.GetHeight()
    reach = max(w, h) / 2.0 + pcbnew.FromMM(width / 2.0 + clr)
    if h >= w:                                  # pads long in Y: leave along Y
        sgn = 1 if toward[1] >= m[1] else -1
        return (m[0], m[1] + sgn * reach)
    sgn = 1 if toward[0] >= m[0] else -1
    return (m[0] + sgn * reach, m[1])


def _flip_merge(fp, na, nb, inner, width, clr, margin, via_margin,
                clear, seg_clear, on_board, g_all, g_thru, math,
                pitch_mm=1.25, neck_mm=0.45, fan_mm=1.90, link_mm=3.00):
    """Join a USB-C receptacle's DUPLICATED D+ and D- pads, which is not optional.

    A USB-C socket carries D+ on two pads and D- on two pads, and joining them is the
    entire mechanism by which the cable works either way up. Join them and the port
    enumerates in both orientations; leave them and it enumerates in one -- a defect no
    bench test finds unless somebody thinks to flip the plug over.

    The pair generator terminates on ONE pad of each net, because a differential pair
    has two rails and not four. The other two were simply left, and came back from every
    routing run as "USB_DP unconnected" -- read for several runs as the router being
    short of room, when no amount of routing could ever have fixed it.

    THE ROUTER CANNOT FIX IT, AND THAT IS WHY IT IS DONE HERE. On the HRO
    TYPE-C-31-M-12 the four pads run, at 0.5 mm pitch:

            B7(D-)   A6(D+)   A7(D-)   B6(D+)

    The two nets INTERLEAVE, so each has to cross the other; a crossing needs a layer
    change; a layer change needs a via; and a 0.6 mm via beside a 0.2 mm track at
    0.127 mm clearance needs 0.537 mm of pitch. There is 0.500. Every arrangement that
    keeps the vias on the pad axis fails by those 37 micrometres -- which is why this
    FANS FIRST: straight out of the pad row, apart to 1.25 mm, and only then across.

    THE ROOM EXISTS, ON THE SIDE NOBODY LOOKS AT. The escape side of the pad row is the
    board's busiest corner -- it is where the pair leaves for the PHY. The other side is
    under the socket's own plastic: 5.0 x 3.3 mm of empty board, bounded by the two NPTH
    locating holes and the shell tabs, and going nowhere. Both sides are tried and the
    one that clears is kept, but it is that one.

    NECK BEFORE FANNING, for the reason recorded against _pad_neck: a diagonal leaving a
    0.5 mm pad row clips its neighbours. Each trace runs straight out past the row and
    its clearance, and only then turns.

    Nothing is emitted unless every segment and both vias clear. A partial merge is never
    laid -- half a flip fix is a board that works one way up with copper claiming
    otherwise, which is worse than the honest failure.
    """
    rows = {}
    for q in fp.Pads():
        if q.GetNetname() in (na, nb):
            rows.setdefault(q.GetNetname(), []).append(q)
    if not all(len(rows.get(n, ())) == 2 for n in (na, nb)):
        return [], None                    # nothing duplicated: an ordinary part

    quads = rows[na] + rows[nb]
    xs = [q.GetPosition().x for q in quads]
    ys = [q.GetPosition().y for q in quads]
    if max(ys) - min(ys) > max(xs) - min(xs):
        return [], ("%s: the duplicated %s / %s pads are not in one row along X, which "
                    "is the only arrangement this handles"
                    % (fp.GetReference(), na, nb))
    row_y = sum(ys) / 4.0
    half = max(abs(q.GetBoundingBox().GetTop() - q.GetBoundingBox().GetBottom())
               for q in quads) / 2.0
    nets = {na, nb}
    order = sorted(quads, key=lambda q: q.GetPosition().x)
    centre = sum(q.GetPosition().x for q in order) / 4.0
    step = pcbnew.FromMM(pitch_mm)
    fx = {id(q): int(centre + (k - 1.5) * step) for k, q in enumerate(order)}

    def span(n):
        a, b = rows[n]
        return abs(fx[id(a)] - fx[id(b)])

    for sign in (+1, -1):                  # +1 first: under the connector body
        neck = row_y + sign * (half + pcbnew.FromMM(neck_mm))
        fan = row_y + sign * (half + pcbnew.FromMM(fan_mm))
        link = row_y + sign * (half + pcbnew.FromMM(link_mm))
        # which net dives is decided by which inner link is shorter, and if that one
        # will not clear the other is tried -- nothing in the geometry says it must be D+
        for dive in sorted((na, nb), key=span):
            flat = nb if dive == na else na
            pend, ok = [], True
            for q in quads:
                px, py = q.GetPosition().x, q.GetPosition().y
                for p0, p1 in (((px, py), (px, neck)),
                               ((px, neck), (fx[id(q)], fan))):
                    if not seg_clear(p0, p1, nets, margin, g_all):
                        ok = False
                        break
                    pend.append(("TRK", q, p0, p1, q.GetLayer()))
                if not ok:
                    break
            if not ok:
                continue

            va, vb = rows[dive]
            pa, pb = (fx[id(va)], fan), (fx[id(vb)], fan)
            for v in (pa, pb):
                if not (clear(v[0], v[1], nets, via_margin, g_all)
                        and on_board(v[0], v[1], 0.3 + clr)):
                    ok = False
            if not ok or not seg_clear(pa, pb, nets, margin, g_thru):
                continue
            pend.append(("VIA", va, pa, pa, None))
            pend.append(("VIA", vb, pb, pb, None))
            pend.append(("TRK", va, pa, pb, _LAYERS[inner]))

            # the flat net drops to the link depth, crosses, and comes back up -- going
            # AROUND the two vias rather than between them, which is the whole reason
            # the link depth is deeper than the fan depth
            fa, fb = rows[flat]
            qa, qb = (fx[id(fa)], fan), (fx[id(fb)], fan)
            la, lb = (qa[0], link), (qb[0], link)
            for p0, p1 in ((qa, la), (la, lb), (lb, qb)):
                if not seg_clear(p0, p1, nets, margin, g_all):
                    ok = False
                    break
                pend.append(("TRK", fa, p0, p1, fa.GetLayer()))
            if ok:
                return pend, None
    return [], ("%s: no clear way to join the duplicated %s / %s pads on either side of "
                "the pad row -- the port would work in ONE cable orientation only"
                % (fp.GetReference(), na, nb))


def _diff_pairs(board, specs, outline=None, inner=None, clr=0.14):
    """Route declared differential pairs AS PAIRS, before the autorouter sees them.

    ⚠ FREEROUTING HAS NO CONCEPT OF A DIFFERENTIAL PAIR. It routes DP and DM as two
    independent nets that happen to share endpoints, and on the optical board that
    produced 39.6 mm of DP against 32.0 mm of DM over a 22 mm path -- two traces
    taking visibly different routes. The timing skew that implies is survivable (46 ps
    against a 2,080 ps bit); what is NOT survivable is that two traces on different
    paths are not COUPLED, so the 90 ohm differential impedance the stack-up was
    designed around stops describing the interconnect at all. No budget number fixes
    that, because the defect is geometric rather than numeric: the pair has to be
    routed as a pair or it is not a pair.

    So it is routed here, deterministically, and excluded from the router's DSN.

    ⚠ EVERYTHING IS BUILT BY OFFSETTING ONE CENTRELINE, and that is the design of this
    routine rather than an implementation detail. It was arrived at the long way round:
    the first version searched a via position for each pad and then joined via to via,
    and every bug it had was one bug in different clothes. Two independently placed
    endpoints share no notion of which rail is on which side, so the rails crossed at a
    package; then crossed in the middle of a run; then -- the one that finally made the
    right shape obvious -- both turned their corner at the same coordinate and ran
    along on top of each other for three millimetres, because an elbow drawn through
    two endpoints is the SAME elbow for both of them.

    A centreline cannot do any of that, and which rail carries D+ reduces to a single
    choice of sign for the whole run, made once by trying both and keeping the shorter
    stubs.

    THE PATH PER HOP: pad-pair midpoint -> escape point -> optional elbow -> escape
    point -> pad-pair midpoint. The escape points stand the vias off far enough to
    clear their neighbours; the run between them drops to `inner` when the component
    layer is blocked, which it nearly always is, because both ends of a hop terminate
    inside a fine-pitch pad field. Short stubs on the component layer join each pad to
    its own rail end.

    If a hop cannot be laid clear, NOTHING is emitted for that pair and it is reported.
    A half-routed pair is worse than an unrouted one: the router would finish it, and
    the finished half would look deliberate.
    """
    import math
    pads = [(pad, fp) for fp in board.GetFootprints() for pad in fp.Pads()]
    boxes = [(q.GetBoundingBox(), q.GetNetname(),
              "%s.%s" % (f.GetReference(), q.GetNumber())) for q, f in pads]
    boxes += [(t.GetBoundingBox(), t.GetNetname(), "track") for t in board.GetTracks()]
    # ⚠ AN INNER-LAYER RUN HAS A DIFFERENT OBSTACLE SET, and using the surface one was
    # why the re-planned board still reported the hop blocked. An SMD pad lives on F.Cu
    # and is no obstacle at all to a trace on In2.Cu; what pierces every layer is
    # THROUGH-HOLE copper -- vias, and the occasional THT pad. Checking a 7 mm inner run
    # against 566 surface pads finds a collision every time, and the message reads as
    # "the board is too dense" when the board is nothing of the kind.
    thru = [(t.GetBoundingBox(), t.GetNetname(), "via") for t in board.GetTracks()
            if t.GetClass() == "PCB_VIA"]
    thru += [(q.GetBoundingBox(), q.GetNetname(),
              "%s.%s" % (f.GetReference(), q.GetNumber())) for q, f in pads
             if q.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)]
    by_ref = {}
    for pad, fp in pads:
        by_ref.setdefault(fp.GetReference(), []).append(pad)

    # ⚠ THE OBSTACLES ARE BUCKETED INTO A GRID, and that is not premature optimisation.
    # A clearance test that walks all 600 pads costs nothing once and everything when
    # the search has to try thousands of candidate paths -- and it does have to, because
    # getting a pair around a connector's shell tabs means considering routes with two
    # corners, not just the three one-corner shapes a cheap test can afford. The honest
    # version of "the board is too dense to route this" is usually "the search gave up
    # early", and a fast test is what lets it not.
    CELL = pcbnew.FromMM(2.0)

    def _grid(items):
        g = {}
        for bb, onet, _lbl in items:
            for cx in range(bb.GetLeft() // CELL, bb.GetRight() // CELL + 1):
                for cy in range(bb.GetTop() // CELL, bb.GetBottom() // CELL + 1):
                    g.setdefault((cx, cy), []).append((bb, onet, _lbl))
        return g

    def clear(x, y, nets, margin, grid):
        x, y = int(x), int(y)
        seen = set()
        for cx in range((x - margin) // CELL, (x + margin) // CELL + 1):
            for cy in range((y - margin) // CELL, (y + margin) // CELL + 1):
                for item in grid.get((cx, cy), ()):
                    if id(item) in seen:
                        continue
                    seen.add(id(item))
                    bb, onet, lbl = item
                    if onet in nets:
                        continue
                    dx = max(bb.GetLeft() - x, 0, x - bb.GetRight())
                    dy = max(bb.GetTop() - y, 0, y - bb.GetBottom())
                    if math.hypot(dx, dy) < margin:
                        return False
        return True

    def seg_clear(p0, p1, nets, margin, grid):
        L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if L == 0:
            return True
        n = max(4, int(pcbnew.ToMM(L) / 0.15) + 1)
        return all(clear(p0[0] + (p1[0] - p0[0]) * t / n,
                         p0[1] + (p1[1] - p0[1]) * t / n, nets, margin, grid)
                   for t in range(n + 1))

    def on_board(x, y, reach_mm):
        """Is copper of half-width `reach_mm` at (x, y) actually ON the board?

        ⚠ THE ESCAPE SEARCH USED TO ASSUME ANY DIRECTION AWAY FROM THE PACKAGE WAS
        BOARD, and at an EDGE CONNECTOR that is false in the one direction it most
        wants to go: the socket sits against the edge because the plug has to reach the
        outside world, so there is half a millimetre of board past its pad row and
        nothing else. The reach has to include the copper's own half-width -- a via
        CENTRE 0.5 mm from the edge has copper 0.2 mm from it, which the fab cares
        about and a bare point-in-polygon test waves through.
        """
        if outline is None:
            return True
        return _inside(outline, int(x), int(y), pcbnew.FromMM(reach_mm + 0.5))

    def rails_for(centre, ds, vi, a0, b0, a1, b1, na, nb, margin, width,
                  surf_layer, run_layer, via_margin, grid):
        """Offset `centre` into two rails and return the copper to emit, or None.

        `centre` runs pad-midpoint -> neck -> escape -> ... -> escape -> neck ->
        pad-midpoint, and `ds` carries one half-pitch per vertex, so the ESCAPE IS PART
        OF THE LINE rather than a stub bolted on afterwards. That is what rotates the
        pair correctly: coming off a connector the two rails are separated ALONG the pad
        row, and heading away down the board they have to be separated ACROSS the run.
        Offsetting a polyline does that turn for free at the corner.

        ⚠ THE NECK IS WHY `ds` VARIES. The pair runs at a via pitch wide enough for
        0.6 mm vias -- 0.74 mm centre to centre -- and a USB-C's pads are on 0.5 mm
        pitch. Arriving at that row still fanned out leaves each rail 0.23 mm from the
        NEIGHBOURING pad, and that was the last thing standing between this board and a
        routed pair. The line therefore necks back to the part's own pad separation
        before it reaches the part and opens out again once clear: a taper, which is
        what a person draws and what a polyline offset expresses in one number per
        vertex.

        ⚠ THE SIGN IS CHOSEN ONCE FOR THE WHOLE RUN. Both options are built and the
        one with the shorter ends wins -- the same thing as "D+ leaves on the side its
        pad is already on". Because both rails are offsets of one line, that single
        decision holds for every segment and every corner of the hop.
        """
        opts = []
        for sa in (+1, -1):
            r = {na: _offset_poly(centre, [sa * d for d in ds], math),
                 nb: _offset_poly(centre, [-sa * d for d in ds], math)}
            pd = {na: (a0, a1), nb: (b0, b1)}
            cost = sum(math.hypot(pd[n][i].GetPosition().x - r[n][j][0],
                                  pd[n][i].GetPosition().y - r[n][j][1])
                       for n in (na, nb) for i, j in ((0, 0), (1, -1)))
            opts.append((cost, r, pd))
        # ⚠ REJECT A CENTRELINE THAT DOUBLES BACK ON ITSELF. Mitring a corner means
        # intersecting the two offset lines, and when the two segments are nearly
        # anti-parallel that intersection runs away to infinity -- the rails fly apart
        # in opposite directions and what lands on the board is not a pair but two long
        # traces to nowhere. It reached DRC looking like a pair whose halves were 10 mm
        # apart. A corner is only a corner if it turns.
        limit = 3.0 * max(ds)
        opts = [o for o in opts
                if all(math.hypot(v[0] - c[0], v[1] - c[1]) < limit
                       for rr in (o[1][na], o[1][nb])
                       for v, c in zip(rr, centre))]
        if not opts:
            return None
        opts.sort(key=lambda o: o[0])
        nets = {na, nb}
        for _, r, pd in opts:
            out, ok = [], True
            for n in (na, nb):
                p_start, p_end = pd[n]
                own = {n}
                # the rail ENDS on its own pad; the neck brings it within microns and
                # this closes the gap exactly.
                rail = list(r[n])
                rail[0] = (p_start.GetPosition().x, p_start.GetPosition().y)
                rail[-1] = (p_end.GetPosition().x, p_end.GetPosition().y)
                if vi is None:
                    # ⚠ OWN NET ONLY, THE SAME RULE AS THE VIA PATH BELOW -- and this branch
                    # was the one that still excluded BOTH. With the pair's partner net
                    # excluded, D+ could not see D-'s PADS: on the optical board's socket
                    # hop it ran diagonally onto A6 straight past B7 (a D- pad), and DRC
                    # reported it. The partner's RAIL is not in the grid yet (nothing is
                    # laid until the whole pair clears), so excluding only the own net
                    # costs the coupled run nothing and makes the partner's pads real.
                    for q0, q1 in zip(rail, rail[1:]):
                        if q0 != q1 and not seg_clear(q0, q1, own, margin, grid):
                            ok = False
                            break
                    if not ok:
                        break
                    for q0, q1 in zip(rail, rail[1:]):
                        if q0 != q1:
                            out.append(("TRK", p_start, q0, q1, surf_layer))
                    continue
                i0, i1 = vi
                # ⚠ THE SURFACE ENDS ARE CHECKED AGAINST THE PARTNER'S PADS, not
                # against "the pair". Excluding both nets is right for the coupled RUN --
                # the rails sit a fixed gap apart on purpose and would otherwise reject
                # each other -- and wrong at a fan-out: D+'s escape ran straight over
                # D-'s pad at the connector, and DRC called it the short it was.
                surf = (list(zip(rail[:i0], rail[1:i0 + 1]))
                        + list(zip(rail[i1:-1], rail[i1 + 1:])))
                run = list(zip(rail[i0:i1], rail[i0 + 1:i1 + 1]))
                for q0, q1 in surf:
                    if q0 != q1 and not seg_clear(q0, q1, own, margin, g_all):
                        ok = False
                        _DBG['escape'] = _DBG.get('escape', 0) + 1
                        break
                if not ok:
                    break
                for v in (rail[i0], rail[i1]):
                    if not clear(v[0], v[1], own, via_margin, g_all):
                        ok = False
                        _DBG['via'] = _DBG.get('via', 0) + 1
                    elif not on_board(v[0], v[1], 0.3):
                        ok = False
                        _DBG['edge'] = _DBG.get('edge', 0) + 1
                    if not ok:
                        break
                if not ok:
                    break
                for q0, q1 in run:
                    if q0 != q1 and not seg_clear(q0, q1, nets, margin, grid):
                        ok = False
                        _DBG['run'] = _DBG.get('run', 0) + 1
                        break
                if not ok:
                    break
                for q0, q1 in surf:
                    if q0 != q1:
                        out.append(("TRK", p_start, q0, q1, surf_layer))
                for q0, q1 in run:
                    if q0 != q1:
                        out.append(("TRK", p_start, q0, q1, run_layer))
                out.append(("VIA", p_start, rail[i0], None, None))
                out.append(("VIA", p_end, rail[i1], None, None))
            if ok:
                return out
        return None

    g_all, g_thru = _grid(boxes), _grid(thru)

    done = []
    for spec in specs:
        na, nb = spec["nets"]
        chain = spec["chain"]
        gap = spec.get("gap", 0.2)
        width = spec.get("width", 0.2)
        off = pcbnew.FromMM((gap + width) / 2.0)
        # ⚠ THE VIA PITCH IS WIDER THAN THE TRACK PITCH. 0.2 mm traces on a 0.2 mm gap
        # sit 0.4 apart centre to centre, which 0.6 mm vias cannot use -- at the track
        # pitch they overlap outright. The inner run is therefore laid at the WIDER
        # pitch throughout, which keeps the geometry a pair (both rails identical,
        # mirror imaged, constant gap) at the cost of weaker coupling than the surface
        # stubs. A constant impedance you have not calculated beats a varying one you
        # have -- and it is not calculated: the actual differential impedance needs the
        # stack-up's dielectric heights, which JLCPCB fixes and nothing here reads.
        voff = max(off, pcbnew.FromMM((0.6 + clr) / 2.0))
        margin = pcbnew.FromMM(width / 2.0 + clr)
        via_margin = pcbnew.FromMM(0.3 + clr)

        # ── the pads to visit: an IN pair and an OUT pair for every part ──
        # ⚠ A PART IN THE MIDDLE OF THE CHAIN NEEDS DIFFERENT PADS ON ITS TWO SIDES, and
        # getting that wrong is what kept the last hop unroutable through three rewrites
        # of the escape search. The ESD array is a SERIES part: the PHY feeds one face
        # and the connector is fed from the other, and the USBLC6 exposes each net on
        # both (D+ on pins 1 and 6, D- on 3 and 4) precisely so that it can be dropped
        # into the run that way. Using one pad pair for both hops means the outgoing hop
        # has to escape backwards across the package it just arrived at -- which is not
        # a hard routing problem, it is an impossible one, and it reported as "no clear
        # path" rather than as the placement mistake it was.
        #
        # So each part gets an IN pair, chosen nearest where the run came from, and an
        # OUT pair, chosen nearest where it is going, and they are only the same pads
        # when the part has nothing else to offer.
        fps = []
        for ref in chain:
            fpo = next((f for f in board.GetFootprints()
                        if f.GetReference() == ref), None)
            cand = {n: [q for q in by_ref.get(ref, []) if q.GetNetname() == n]
                    for n in (na, nb)}
            if fpo is None or not cand[na] or not cand[nb]:
                fps = None
                break
            fps.append((fpo, cand))
        if fps is None:
            done.append((na, "could not find both nets on every part of the chain"))
            continue

        def best_pair(cand, targets, avoid=()):
            """The (D+, D-) pad pair closest to `targets`, preferring pads not in
            `avoid` -- minimising the TOTAL of the two distances, which picks the
            uncrossed combination for free: crossing is always longer than not."""
            best = None
            for qa in cand[na]:
                for qb in cand[nb]:
                    if qa.GetPosition() == qb.GetPosition():
                        continue
                    cost = sum((q.GetPosition() - t).EuclideanNorm()
                               for q, t in zip((qa, qb), targets))
                    cost += sum(pcbnew.FromMM(25.0) for q in (qa, qb) if q in avoid)
                    if best is None or cost < best[0]:
                        best = (cost, qa, qb)
            return best[1], best[2]

        stops = []
        for k, (fpo, cand) in enumerate(fps):
            if k == 0:
                nxt = fps[1][0].GetCourtyard(pcbnew.F_CrtYd).BBox().GetCenter()
                a, b_ = best_pair(cand, (nxt, nxt))
                stops.append({"fp": fpo, "in": (a, b_), "out": (a, b_)})
                continue
            pa0, pb0 = (q.GetPosition() for q in stops[-1]["out"])
            a, b_ = best_pair(cand, (pa0, pb0))
            if k == len(fps) - 1:
                stops.append({"fp": fpo, "in": (a, b_), "out": (a, b_)})
                continue
            nxt = fps[k + 1][0].GetCourtyard(pcbnew.F_CrtYd).BBox().GetCenter()
            oa, ob = best_pair(cand, (nxt, nxt), avoid=(a, b_))
            stops.append({"fp": fpo, "in": (a, b_), "out": (oa, ob)})

        pending, laid, why = [], 0, None
        for s0, s1 in zip(stops, stops[1:]):
            (a0, b0), fp0 = s0["out"], s0["fp"]
            (a1, b1), fp1 = s1["in"], s1["fp"]
            m0 = ((a0.GetPosition().x + b0.GetPosition().x) / 2.0,
                  (a0.GetPosition().y + b0.GetPosition().y) / 2.0)
            m1 = ((a1.GetPosition().x + b1.GetPosition().x) / 2.0,
                  (a1.GetPosition().y + b1.GetPosition().y) / 2.0)

            hs0 = math.hypot(a0.GetPosition().x - b0.GetPosition().x,
                             a0.GetPosition().y - b0.GetPosition().y) / 2.0
            hs1 = math.hypot(a1.GetPosition().x - b1.GetPosition().x,
                             a1.GetPosition().y - b1.GetPosition().y) / 2.0
            hop = None
            # 1. the surface try: no vias at all, if the component layer is open
            # ⚠ NECK OUT OF EACH PAD ROW BEFORE TAPERING. The rails used to taper from one
            # part's pad pitch to the other's along the WHOLE hop, so on a short hop onto
            # a fine-pitch connector they came in diagonally -- and a diagonal entering a
            # 0.5 mm pad row crosses its neighbours. Each end now runs straight out along
            # its pads' long axis, at its own pad separation, until it is past the pad row
            # and its clearance; the taper happens only between those two neck points.
            n0 = _pad_neck(m0, a0, m1, width, clr)
            n1 = _pad_neck(m1, a1, m0, width, clr)
            for sh in _centrelines(n0, n1):
                centre = [m0] + sh + [m1]
                ds = ([max(off, hs0)] * 2 + [off] * (len(sh) - 2)
                      + [max(off, hs1)] * 2)
                hop = rails_for(centre, ds, None, a0, b0, a1, b1, na, nb, margin, width,
                                a0.GetLayer(), None, via_margin, g_all)
                if hop:
                    break

            # 2. otherwise take the WHOLE PAIR down to an inner layer together.
            # ⚠ BOTH NETS GO DOWN AT ONCE. On this board the PHY sits behind two rows of
            # parts, so there is no component-layer path to the connector, and weaving
            # between the rows is precisely the wandering that made the router's own
            # attempt unusable. Taking the pair down keeps it coupled the whole way,
            # runs it on copper that has no pads on it at all, and costs exactly the two
            # vias per net the budget already allows.
            if hop is None and inner is not None:
                for e0 in _escape_plan(fp0, m0, a0, b0, hs0, voff, margin, via_margin,
                                       na, nb, clear, seg_clear, on_board, g_all, math):
                    for e1 in _escape_plan(fp1, m1, a1, b1, hs1, voff, margin,
                                           via_margin, na, nb, clear, seg_clear,
                                           on_board, g_all, math):
                        for sh in _centrelines(e0["e"], e1["e"]):
                            centre = [m0, e0["n"]] + sh + [e1["n"], m1]
                            ds = ([hs0 or voff] * 2 + [voff] * len(sh)
                                  + [hs1 or voff] * 2)
                            hop = rails_for(centre, ds, (2, len(centre) - 3),
                                            a0, b0, a1, b1, na, nb, margin, width,
                                            a0.GetLayer(), _LAYERS[inner],
                                            via_margin, g_thru)
                            if hop:
                                break
                        if hop:
                            break
                    if hop:
                        break
            if hop is None:
                why = "no clear path %s->%s %s" % (fp0.GetReference(), fp1.GetReference(), sorted((k, v) for k, v in _DBG.items() if v))
                break
            pending += hop
        if why:
            done.append((na, why))
            continue

        # ⚠ A PASS-THROUGH PART IS ONE NODE INSIDE AND TWO PADS OUTSIDE, and the board
        # file only knows about the pads. The USBLC6 puts D+ on pins 1 AND 6 and D- on 3
        # AND 4, joined on the die -- which is the whole reason the chain can enter one
        # face and leave the other. KiCad's connectivity does not model that: it sees two
        # pads of one net with no copper between them and calls the net unfinished, and
        # the router then tries to "fix" it, laying stubs that end up as orphan islands.
        # That is exactly how USB_DP and USB_DM came back unconnected on a board whose
        # pair was laid correctly end to end.
        #
        # So the generator links them itself: it CHOSE the in and out pads, so it is the
        # thing that knows they are the same node. The link is short, straight and runs
        # under the part's own body between its own pads, and it is checked like any
        # other segment -- if it does not clear, it is not laid and the net is reported
        # rather than silently shorted to a neighbour.
        for st in stops:
            for n, qi, qo in ((na, st["in"][0], st["out"][0]),
                              (nb, st["in"][1], st["out"][1])):
                if qi is qo or qi.GetPosition() == qo.GetPosition():
                    continue
                p0 = (qi.GetPosition().x, qi.GetPosition().y)
                p1 = (qo.GetPosition().x, qo.GetPosition().y)
                if not seg_clear(p0, p1, {n}, margin, g_all):
                    done.append((n, "pads %s/%s of %s are one node inside the part and "
                                 "no clear link between them exists"
                                 % (qi.GetNumber(), qo.GetNumber(),
                                    st["fp"].GetReference())))
                    continue
                pending.append(("TRK", qi, p0, p1, qi.GetLayer()))

        # AND THE DUPLICATED PADS AT THE ENDS OF THE CHAIN. A pass-through part is one
        # node with two pads because the die joins them; a USB-C socket is one node with
        # two pads because the connector is reversible, and there it is the BOARD that
        # has to do the joining. Same shape, opposite obligation -- and the loop above
        # cannot see it, because at the first and last stop `in` and `out` are the same
        # pad, so its `qi is qo` guard skips them.
        if inner is not None:
            for st in (stops[0], stops[-1]):
                extra, why_fm = _flip_merge(
                    st["fp"], na, nb, inner, width, clr, margin, via_margin,
                    clear, seg_clear, on_board, g_all, g_thru, math)
                if why_fm:
                    done.append((na, why_fm))
                pending += extra

        for kind, pad, q0, q1, layer in pending:
            if kind == "VIA":
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(int(q0[0]), int(q0[1])))
                v.SetWidth(pcbnew.FromMM(0.6))
                v.SetDrill(pcbnew.FromMM(0.3))
                v.SetNet(pad.GetNet())
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                board.Add(v)
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int(q0[0]), int(q0[1])))
            t.SetEnd(pcbnew.VECTOR2I(int(q1[0]), int(q1[1])))
            t.SetWidth(pcbnew.FromMM(width))
            t.SetLayer(layer)
            t.SetNet(pad.GetNet())
            board.Add(t)
            laid += 1
        done.append((na, "laid %d segment(s) as a coupled pair over %d hop(s)"
                     % (laid, len(stops) - 1)))
    return done


def _escape_plan(fpo, m, pa, pb, hs, voff, margin, via_margin, na, nb,
                 clear, seg_clear, on_board, grid, math, limit=16):
    """Workable ways for a pair to leave one package, best first.

    Each entry is a NECK point -- a short run straight out of the pads at the part's own
    pitch -- and an ESCAPE point where the pair has opened out to the via pitch and can
    drop to an inner layer.

    ⚠ THIS EXISTS TO PRUNE, and the pruning is what makes the search honest. The path
    search downstream has to consider two-corner routes to get around a connector's
    shell tabs, and the product of (directions x distances x shapes) is tens of
    thousands of candidates. Checking the escape here -- once per direction and
    distance, before any shape is considered -- removes the combinations that could
    never work whatever the run does, and the ones that survive are few. Everything is
    re-checked exactly downstream; this is a filter, not an authority.

    ⚠ AND THE DIRECTIONS FAN OUT, rather than being just "away from the part". The
    PHY's D+/D- pins face its own 24 MHz crystal, 2 mm away: straight out is into the
    crystal, and the pair has to leave at an angle. Outward is tried first and inward
    last -- inward, under the body, is the only direction open at a connector that sits
    on the board edge, which is where a USB-C always sits.
    """
    c = fpo.GetCourtyard(pcbnew.F_CrtYd).BBox().GetCenter()
    base = math.atan2(m[1] - c.y, m[0] - c.x)
    neck = pcbnew.FromMM(0.6)
    nets = {na, nb}
    pads = ((pa.GetPosition().x, pa.GetPosition().y),
            (pb.GetPosition().x, pb.GetPosition().y))
    out = []
    for turn in (0.0, math.pi):
        for dth in (0.0, 0.4, -0.4, 0.8, -0.8, 1.2, -1.2):
            ang = base + turn + dth
            ux, uy = math.cos(ang), math.sin(ang)
            nx, ny = -uy, ux
            n = (m[0] + ux * neck, m[1] + uy * neck)
            # either pairing of pad to side will do -- which rail is D+ is decided
            # downstream, and pinning it here rejected every escape at the ESD array,
            # where the arbitrary choice happened to send each rail diagonally across
            # the package to the other one's pad.
            if not any(all(seg_clear(pad, (n[0] + sgn * hs * nx, n[1] + sgn * hs * ny),
                                     nets, margin, grid)
                           for pad, sgn in zip(pads, sides))
                       for sides in ((+1, -1), (-1, +1))):
                continue
            for k in range(11):
                r = pcbnew.FromMM(1.0 + 0.25 * k)
                e = (m[0] + ux * r, m[1] + uy * r)
                vs = [(e[0] + sgn * voff * nx, e[1] + sgn * voff * ny)
                      for sgn in (+1, -1)]
                if not all(clear(v[0], v[1], nets, via_margin, grid)
                           and on_board(v[0], v[1], 0.3) for v in vs):
                    continue
                if not all(seg_clear((n[0] + sgn * hs * nx, n[1] + sgn * hs * ny), v,
                                     nets, margin, grid)
                           for v, sgn in zip(vs, (+1, -1))):
                    continue
                out.append({"n": n, "e": e})
                if len(out) >= limit:
                    return out
    return out


def _pad_pitch(fp):
    """The smallest centre-to-centre distance between two pads of `fp`, or None.

    Measured rather than tabulated: at these part counts it costs nothing, and a measured
    pitch cannot disagree with the footprint the way a table can.
    """
    import math as _m
    pts = [(q.GetPosition().x, q.GetPosition().y) for q in fp.Pads()]
    if len(pts) < 2:
        return None
    best = None
    for i, (x0, y0) in enumerate(pts):
        for x1, y1 in pts[i + 1:]:
            d = _m.hypot(x1 - x0, y1 - y0)
            if d > 0 and (best is None or d < best):
                best = d
    return best


def add_missing_vias(board, eps_mm=0.05, via_d=0.6, via_drill=0.3, clr=0.14):
    """Where one net's copper changes layer and nothing carries it across, drop the via.

    ⚠ THE ROUTER DOES NOT LOSE THE ROUTE, IT LOSES THE VIA. TIA_OUT_2B came back from
    the Specctra round trip as a B.Cu track and an F.Cu track ending at exactly the same
    point -- 0.002 mm apart -- with no via between them. Both halves of the layer change
    are there; the thing that makes it a layer change is not.

    That failure reads as a routing failure and is not one. Every attempt to fix it as
    one -- more passes, a different strategy, more room around the parts -- re-routes a
    net that was ALREADY ROUTED and then loses the via again. And the tempting repair,
    bridging the "gap" with copper, cannot work at all: the two ends are on different
    layers, so no segment can join them however short it is.

    So look for the signature instead: two tracks of one net, on DIFFERENT layers,
    whose endpoints coincide. That is a layer change with its via missing, and the
    repair is exact rather than approximate -- the via goes where the route already
    says it goes, and nothing else moves.

    It still has to be LEGAL, and checking that is not optional: a via is bigger than
    the track that leads to it (0.6 against 0.25), so a spot with room for the track can
    be short of room for the via. One that will not fit is left alone and reported,
    because a via placed into a clearance violation turns a board that is unfinished
    into a board that cannot be made.
    """
    import math
    eps = pcbnew.FromMM(eps_mm)
    margin = pcbnew.FromMM(via_d / 2.0 + clr)

    pads, segs, vias = [], [], []
    for fp in board.GetFootprints():
        for q in fp.Pads():
            pads.append((q.GetBoundingBox(), q.GetNetname()))
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias.append((t.GetPosition().x, t.GetPosition().y, _via_r(t), t.GetNetname()))
        else:
            segs.append(((t.GetStart().x, t.GetStart().y),
                         (t.GetEnd().x, t.GetEnd().y),
                         t.GetWidth() / 2.0, t.GetNetname()))

    def clear(x, y, net):
        for bb, onet in pads:
            if onet == net:
                continue
            dx = max(bb.GetLeft() - x, 0, x - bb.GetRight())
            dy = max(bb.GetTop() - y, 0, y - bb.GetBottom())
            if math.hypot(dx, dy) < margin:
                return False
        for (ax, ay), (bx, by), hw, onet in segs:
            if onet == net:
                continue
            vx, vy = bx - ax, by - ay
            L2 = vx * vx + vy * vy
            u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
            if math.hypot(x - (ax + u * vx), y - (ay + u * vy)) - hw < margin:
                return False
        for vx2, vy2, vr, onet in vias:
            if onet == net:
                continue
            if math.hypot(x - vx2, y - vy2) < margin + vr:
                return False
        return True

    ends = {}
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" or not t.GetNetname():
            continue
        for p in (t.GetStart(), t.GetEnd()):
            ends.setdefault(t.GetNetname(), []).append((p.x, p.y, t.GetLayer(), t))

    added, refused = 0, []
    for net, items in ends.items():
        for i in range(len(items)):
            xi, yi, li, ti = items[i]
            for j in range(i + 1, len(items)):
                xj, yj, lj, tj = items[j]
                if li == lj or math.hypot(xi - xj, yi - yj) > eps:
                    continue
                # already carried across? then there is nothing missing.
                # ⚠ "ACROSS" INCLUDES A VIA THE TWO TRACKS BOTH COVER (pi_cap, 2026-10-04).
                # Two declared 2.2 mm patches, one per layer, shared an endpoint with eight
                # declared vias under them, the nearest 0.55 mm from that point: the test
                # was "a via exactly here", so a ninth was dropped in -- and the tidy pass
                # then removed four of the DECLARED ones for crowding it.
                _reach = min(ti.GetWidth(), tj.GetWidth()) / 2.0
                if any(onet == net and math.hypot(xi - vx2, yi - vy2) <= vr + _reach
                       for vx2, vy2, vr, onet in vias):
                    continue
                if not clear(xi, yi, net):
                    refused.append((net, pcbnew.ToMM(xi), pcbnew.ToMM(yi)))
                    continue
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(int(xi), int(yi)))
                v.SetWidth(pcbnew.FromMM(via_d))
                v.SetDrill(pcbnew.FromMM(via_drill))
                v.SetNet(ti.GetNet())
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                board.Add(v)
                vias.append((xi, yi, pcbnew.FromMM(via_d / 2.0), net))
                added += 1
    for net, x, y in refused:
        print("    ⚠ %s changes layer at %.2f,%.2f and a 0.6 via does not fit there"
              % (net, x, y))
    return added


def drop_redundant_pth_vias(board):
    """Delete routing vias that the router drilled into a through-hole pad of their own net.

    ⚠ THIS IS THE ROUTER'S DOING, NOT THE STITCHER'S, and the distinction cost a
    while to find because the symptom is identical. layout.py's stitcher really did put
    20 vias on motor_ctrl's XH pins and 14 on output_panel's, and excluding PTH pads
    from its via-in-pad branch really did fix those. What it did NOT fix -- 8 on
    motor_ctrl, 6 on lever_sensor, 4 on output_panel -- has a different author: measured
    on the UNROUTED board, every one of those boards has ZERO vias sitting in a PTH pad,
    and they all appear in the .ses that comes back. Freerouting treats a through-hole
    pad as a free layer change on its own net, which is electrically true and mechanically
    not: the drill enters an already-drilled hole, risks the bit and leaves an oval bore.
    No amount of tuning the stitcher's clearances reaches a via the stitcher never made.

    ⚠ DELETING IS SAFE HERE AND WOULD NOT BE EARLIER. A PTH pad already connects
    every copper layer -- that is what the barrel is -- so a same-net via inside it
    carries nothing the pad was not already carrying, and any track ending at the via's
    centre ends inside the pad's own copper and stays connected. That is why the test
    below demands BOTH that the holes overlap and that the via centre is inside the pad
    shape: a via merely NEAR the pad may be holding a track that the pad does not touch.

    And the timing is the whole reason this is allowed at all. Removing vias BEFORE
    routing re-plans the board -- it took optical from 0 unconnected to 6, on a board
    with four through-hole pads -- because every other net then routes around the
    absence. Here the router has finished and nothing re-plans; see the deliberate
    repairs in route.py, which are placed after routing for the same reason.
    """
    import math
    pth = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() not in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                continue
            d = pad.GetDrillSize()
            pth.append((pad, pad.GetNetCode(), pad.GetPosition(),
                        max(d.x, d.y) / 2.0, fp.GetReference(), pad.GetNumber()))
    # ⚠ EVERY MEASUREMENT BEFORE ANY REMOVAL -- board.Remove() leaves the track
    # container in a state where GetTracks() raises, the same SWIG ownership hazard that
    # corrupted the footprint IO plugin earlier in this file's history.
    doomed = []
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_VIA):
            continue
        vp, vr = t.GetPosition(), t.GetDrillValue() / 2.0
        for pad, nc, pp, pr, ref, num in pth:
            if t.GetNetCode() != nc:
                continue                       # a DIFFERENT net in the hole is a short,
                                               # which DRC already calls an error
            if math.hypot(vp.x - pp.x, vp.y - pp.y) >= vr + pr:
                continue                       # holes do not touch
            if not pad.HitTest(vp):
                continue                       # centre outside the pad's copper: the
                                               # via may be holding a track the pad is
                                               # not touching, so leave it alone
            doomed.append((t, "%s.%s [%s]" % (ref, num, t.GetNetname())))
            break
    for t, _why in doomed:
        board.Remove(t)
    if doomed:
        board.BuildConnectivity()
        print("  removed %d redundant via(s) drilled into a through-hole pad: %s"
              % (len(doomed), ", ".join(w for _t, w in doomed[:8])))
    return len(doomed)


def drop_redundant_pad_vias(board, notes):
    """Delete a router via drilled into a small soldered land when the net holds without it.

    The through-hole case above is safe by construction: the barrel was already there.
    A surface land has no barrel, so a via in it MAY be the only thing carrying the net
    to another layer, and no geometric test says which. So ask the board the question
    directly -- take the via off its net, rebuild connectivity, and count. If the count
    of unconnected items did not rise, the via carried nothing its neighbours do not.

    The usual origin is a layer change the router put under the pad and then duplicated
    0.7 mm away with a second via and a stub back to the land: both are legal copper,
    and the first one wicks the joint's paste down an open hole.

    Only lands under 4 mm2 that print paste are looked at (a larger land is a thermal
    or power pad and quality counts its barrels separately), and a via declared in the
    board file is somebody's decision, not a leaving. A via that IS needed is left in
    place for quality to report -- too strict here would trade a soldering fault for an
    open net.

    Nothing is removed until every test is done, and the removal re-finds each via by
    UUID on a fresh walk (see tidy_router_vias for why).
    """
    import math
    declared_xy = {(round(rv[1], 3), round(rv[2], 3))
                   for rv in list(notes.get("repair_vias", [])) + list(notes.get("vias", []))}
    lands = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or not pad.GetNetCode():
                continue
            if not (pad.IsOnLayer(pcbnew.F_Paste) or pad.IsOnLayer(pcbnew.B_Paste)):
                continue
            sz = pad.GetSize()
            if pcbnew.ToMM(sz.x) * pcbnew.ToMM(sz.y) >= 4.0:
                continue
            lands.append((pad, pad.GetNetCode(), "%s.%s" % (fp.GetReference(), pad.GetNumber())))
    cand = []
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_VIA):
            continue
        vp = t.GetPosition()
        if (round(pcbnew.ToMM(vp.x) - 100.0, 3), round(100.0 - pcbnew.ToMM(vp.y), 3)) in declared_xy:
            continue
        for pad, nc, name in lands:
            if nc == t.GetNetCode() and pad.HitTest(vp, int(t.GetDrillValue() / 2)):
                cand.append((t, nc, "%s [%s]" % (name, t.GetNetname())))
                break
    if not cand:
        return 0
    conn = board.GetConnectivity()
    board.BuildConnectivity()
    base = conn.GetUnconnectedCount(False)
    doomed = {}
    for t, nc, why in cand:
        t.SetNetCode(0)
        board.BuildConnectivity()
        if board.GetConnectivity().GetUnconnectedCount(False) > base:
            t.SetNetCode(nc)                   # it was carrying the net: keep it
        else:
            doomed[t.m_Uuid.AsString()] = why  # stays off the net for the tests that follow
    del cand, lands
    for u in list(doomed):
        for t in board.GetTracks():
            if isinstance(t, pcbnew.PCB_VIA) and t.m_Uuid.AsString() == u:
                board.Remove(t)
                break
    board.BuildConnectivity()
    if doomed:
        print("  removed %d redundant via(s) drilled into a small soldered land: %s"
              % (len(doomed), ", ".join(list(doomed.values())[:8])))
    return len(doomed)


def tidy_router_vias(board, notes, min_gap_mm=0.25):
    """Remove vias the router left carrying nothing, and merge ones drilled too close.

    ⚠ THE FIRST VERSION OF THIS ASKED THE GEOMETRY AND GOT IT WRONG SIX TIMES OUT OF
    SEVEN. It counted track ends landing in a via's pad and called a via with none
    "dangling" -- but a plane stitching via is attached to a ZONE, which is its entire
    job and which no track-end test can see. On output_panel it found seven and would
    have deleted six real GND stitches. DRC found one, and DRC was right.

    So ask the board: CONNECTIVITY_DATA.TestTrackEndpointDangling is the test DRC itself
    uses, and it knows about zones. Checked against DRC's own report on output_panel it
    returns exactly the one via DRC flags, at the same coordinates. A classifier for
    deleting copper is worth validating against a known answer BEFORE it deletes any.

    ⚠ AND THE VIA ACCESSORS TRAP TWICE, once quietly and once loudly. Widths go
    through _via_r, which exists for this: PCB_VIA::GetWidth() with no layer argument
    trips a wxWidgets assertion, and on Windows that is a MODAL DIALOG -- it stopped a
    run dead waiting for a human to click it. The helper was already in this file and
    this routine called the raw accessor anyway, which is the whole argument for having
    had a helper.

    ⚠ GetDrill() IS NOT THE DRILL, AND IT READ ZERO ON EXACTLY THE PAIR THIS WAS
    WRITTEN FOR. A via whose drill comes from its netclass has no drill of its own, so
    GetDrill() returns 0 and only GetDrillValue() gives the effective size. With zero the
    computed wall gap for output_panel's GND pair came out 0.50 mm instead of 0.20, which
    is comfortably outside the threshold -- so the pass ran, reported nothing, and left
    the warning standing while looking like it had checked.

    ⚠ 0.39 mm APART IS NOT A TIGHT FIT, IT IS ONE HOLE. Two 0.3 mm drills on 0.39 mm
    centres leave 0.09 mm of laminate between the walls, which breaks out on the drill
    and comes back as a single oval bore -- so the second case is real even though both
    vias are on the same net and shorting them is the intent.

    ⚠ THE ONE THIS STILL LEAVES IS A JUDGEMENT, NOT AN OVERSIGHT. output_panel keeps a
    GND stitch pair with 0.202 mm of laminate between the walls, which trips KiCad's
    default 0.25 mm hole-to-hole rule. JLCPCB's published requirement is "Via Hole-to-Hole
    Spacing 0.2mm", so it passes -- by 2.5 MICRONS, against a stated hole position
    tolerance of +-0.05 mm. Nominally legal and practically thin: drilled at the far ends
    of that tolerance the two holes meet.

    ⚠ AND THE FIRST GUESS AT WHOSE FAULT IT IS WAS WRONG, which is worth keeping.
    This note used to say the fix belonged upstream in the stitcher, by analogy with the
    co-located drills. It does not: _stitch_plane_pads ALREADY refuses a site within
    via_d + clr (0.8 mm) of a via it has placed, and this pair is 0.50 mm apart, so a
    stitch via is not what landed second. The other one comes from add_missing_vias or
    link_close_gaps, which run AFTER routing and place a via at a point they do not get
    to choose -- the spot where a net changes layer with nothing carrying it. Making
    those refuse on hole spacing would trade a warning for an OPEN NET, which is the
    same "too strict does not fail safe" trap recorded beside the hole-vs-hole attempt.

    So the movable party is the STITCH via, and the fix is to nudge it after the required
    vias are down -- rescue_stray_stitches already moves stitch vias for a different
    reason and is the place to build it. Left specified rather than half-built.

    ⚠ STITCHING VIAS ARE NEVER MERGED, only reported. They are placed deliberately, a
    later pass re-checks that each one landed in its plane, and this routine has no way
    to know which pad depends on which stitch. Removing the wrong one is how the first
    version would have unstitched six pads.

    ⚠ AND NOTHING IS REMOVED WHILE A PROXY TO IT IS STILL HELD. The first version
    corrupted the board -- the next pass got a bare SwigPyObject back from
    GetFootprints() -- by removing nine items from lists it was still holding. Here the
    decision is recorded as UUIDs, the references are dropped, and the removal re-finds
    each item on a fresh walk of the board. "Count before removing" was necessary and
    not sufficient; do not hold the thing you are about to delete.
    """
    import math
    conn = board.GetConnectivity()
    stitch = set(notes.get("stitch_nets", ()))
    vias = [t for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA)]
    # ⚠ A DECLARED REPAIR VIA IS NEVER A LEAVING. This pass runs at the END of the
    # post-route sequence, which means the deliberate repairs are already down -- and on
    # optical one of them is the only thing closing a net. They are searched geometry
    # somebody committed to the board file on purpose, so they are off limits here
    # whatever they look like to a dangling test.
    # NOT "keep" -- the merge loop below binds that name to the surviving VIA, and this
    # closure then tested membership in a PCB_VIA.
    # (and so is one laid BEFORE routing, in "vias": a declared via field lost four of its
    # eight to this pass, each "crowding" a router via that had been dropped beside it)
    declared_xy = {(round(rv[1], 3), round(rv[2], 3))
                   for rv in list(notes.get("repair_vias", [])) + list(notes.get("vias", []))}

    def _declared(v):
        p = v.GetPosition()
        return (round(pcbnew.ToMM(p.x) - 100.0, 3),
                round(100.0 - pcbnew.ToMM(p.y), 3)) in declared_xy

    # ⚠ NOR IS A PIN'S ESCAPE VIA (optical SAI_FS, 2026-10-05). "pin_escapes" gives a
    # sealed fine-pitch pin a stub and a via before routing. When the router does not use
    # it the via carries one layer and reads as dangling -- and it is exactly the copper
    # the closing step needs: with it removed, close_last had only the F.Cu stub to start
    # from, inside the seal, and reported "no path" on a net it could have closed.
    escape_at = []
    for key in notes.get("pin_escapes", ()):
        ref, _, num = key.partition(".")
        fp = board.FindFootprintByReference(ref)
        pad = fp.FindPadByNumber(num) if fp else None
        if pad is not None:
            pp = pad.GetPosition()
            escape_at.append((pad.GetNetname(), pp.x, pp.y))

    def _escape(v):
        p, name = v.GetPosition(), v.GetNetname()
        return any(name == n and math.hypot(p.x - x, p.y - y) < pcbnew.FromMM(3.0)
                   for n, x, y in escape_at)

    doomed, joins, reported = {}, [], []
    for v in vias:
        if (conn.TestTrackEndpointDangling(v, False) and not _declared(v)
                and not _escape(v)):
            doomed[v.m_Uuid.AsString()] = "dangling %s" % v.GetNetname()

    def _ends(v):
        """Track ends landing in this via's pad, on a layer it spans -- for the HANDOVER
        only. Used to move copper, never to decide whether a via is needed."""
        out, vp, r = [], v.GetPosition(), _via_r(v)
        lo, hi = v.TopLayer(), v.BottomLayer()
        for t in board.GetTracks():
            if isinstance(t, pcbnew.PCB_VIA) or t.GetNetCode() != v.GetNetCode():
                continue
            if not (lo <= t.GetLayer() <= hi):
                continue
            for e in (t.GetStart(), t.GetEnd()):
                if math.hypot(e.x - vp.x, e.y - vp.y) <= r:
                    out.append((t.GetLayer(), t.GetWidth()))
                    break
        return out

    for i, a in enumerate(vias):
        if a.m_Uuid.AsString() in doomed:
            continue
        for b in vias[i + 1:]:
            if b.m_Uuid.AsString() in doomed or a.GetNetCode() != b.GetNetCode():
                continue
            ap, bp = a.GetPosition(), b.GetPosition()
            d = math.hypot(ap.x - bp.x, ap.y - bp.y)
            gap = d - (a.GetDrillValue() + b.GetDrillValue()) / 2.0
            if gap >= pcbnew.FromMM(min_gap_mm):
                continue
            where = "%s at %.2f,%.2f (%.3f mm of laminate between the walls)" % (
                a.GetNetname(), pcbnew.ToMM(ap.x) - 100.0, 100.0 - pcbnew.ToMM(ap.y),
                pcbnew.ToMM(gap))
            if _declared(a) or _declared(b):
                reported.append(where + " -- one is a DECLARED repair via, not touched")
                continue
            if a.GetNetname() in stitch:
                reported.append(where + " -- STITCHING, not touched")
                continue
            ra, rb = _via_r(a), _via_r(b)
            if d > ra + rb:
                # pads apart: a joining segment would be new copper over ground nobody
                # has checked, so say so rather than lay it blind.
                reported.append(where + " -- pads do not overlap, cannot merge")
                continue
            la, lb = _ends(a), _ends(b)
            drop, keep, load = (a, b, la) if len(la) <= len(lb) else (b, a, lb)
            if any(w > 2 * min(ra, rb) for _l, w in load):
                reported.append(where + " -- a track is too wide to hand over")
                continue
            dp, kp = drop.GetPosition(), keep.GetPosition()
            for layer, w in load:
                joins.append((drop.GetNetCode(), layer, w, (dp.x, dp.y), (kp.x, kp.y)))
            doomed[drop.m_Uuid.AsString()] = "crowded %s (%.3f mm gap)" % (
                drop.GetNetname(), pcbnew.ToMM(gap))

    why = list(doomed.values())
    want = set(doomed)
    del vias, doomed                       # drop every proxy before touching the board

    for nc, layer, w, p, q in joins:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(*p))
        t.SetEnd(pcbnew.VECTOR2I(*q))
        t.SetWidth(w)
        t.SetLayer(layer)
        t.SetNetCode(nc)
        board.Add(t)
    # ONE sweep, collected before anything is removed. The old loop re-walked the track
    # list after every Remove and left its loop variable bound to a removed item; on the
    # optical board (34 removals, 2026-09-21) the container came back as a bare
    # SwigPyObject and the next GetTracks() raised, discarding the route.
    hits = [t for t in board.GetTracks() if t.m_Uuid.AsString() in want]
    gone = len(hits)
    for h in hits:
        board.Delete(h)
    del hits
    if gone:
        board.BuildConnectivity()
        print("  tidied %d router via(s) -- %s%s"
              % (gone, "; ".join(why[:6]),
                 (" (+%d joining segment(s))" % len(joins)) if joins else ""))
    for r in reported:
        print("    NOT FIXED -- %s" % r)
    return gone


def snap_hairline_gaps(board, eps_mm=0.02):
    """Close same-net track gaps too small to bridge, by MOVING an end rather than
    adding copper -- and say how many.

    ⚠ THIS EXISTS BECAUSE THE REPAIR AND THE CLEAN-UP WERE UNDOING EACH OTHER.
    link_close_gaps sees two ends of one net 2 MICRONS apart and lays a segment between
    them; drop_degenerate then sees a 2-micron segment, correctly calls it degenerate,
    and removes it. The net goes back to being two islands, DRC reports it as
    unconnected, and nothing in either log says a repair was reverted. TIA_OUT_2B spent
    three routing runs in that loop.

    Neither routine is wrong. A 2-micron track IS junk -- on 0.25 mm copper that is a
    100:1 ratio, and drop_degenerate's reasoning about it holds. The mistake is trying
    to express "these two ends are the same point" as a piece of copper AT ALL. Say it
    by moving the end instead: exact, adds nothing, and there is no fragment left for
    the clean-up to find.

    The displacement is bounded by eps, which is two hundredths of a millimetre --
    two orders below the clearance rule, so a snap cannot walk a track into a violation.
    """
    import math
    eps = pcbnew.FromMM(eps_mm)
    ends = {}
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        key = (t.GetNetname(), t.GetLayer())
        ends.setdefault(key, []).append(t)

    snapped = 0
    for (net, layer), tracks in ends.items():
        if not net or len(tracks) < 2:
            continue
        # bucket the endpoints so this stays linear in the common case
        pts = []
        for t in tracks:
            pts.append((t.GetStart(), t, True))
            pts.append((t.GetEnd(), t, False))
        for i in range(len(pts)):
            pi, ti, si = pts[i]
            for j in range(i + 1, len(pts)):
                pj, tj, sj = pts[j]
                if ti is tj:
                    continue
                d = math.hypot(pi.x - pj.x, pi.y - pj.y)
                if d == 0 or d > eps:
                    continue
                if sj:
                    tj.SetStart(pcbnew.VECTOR2I(pi.x, pi.y))
                else:
                    tj.SetEnd(pcbnew.VECTOR2I(pi.x, pi.y))
                pts[j] = (pcbnew.VECTOR2I(pi.x, pi.y), tj, sj)
                snapped += 1
    return snapped


def drop_degenerate(board, floor_mm=0.005, width_frac=0.1):
    """Remove tracks too short to be anything, and report how many.

    ⚠ A TRACK HAS WIDTH, which is what makes this safe. These fragments are half a
    MICRON long on 0.2 mm wide copper -- a 400:1 ratio -- so whatever a zero-length track
    touches, the copper already at that spot touches far more of. It can never be the
    only link between two things. Either it is redundant with its neighbours, or there
    are no neighbours and it is an orphan.

    ⚠ SO THE FLOOR IS RELATIVE TO THE TRACK'S OWN WIDTH, which is what the argument above
    was saying all along while the code compared against a flat 5 microns. A fret LED
    board came back clean except for one 8.3 micron stub -- above the absolute floor,
    and 3% of its own 0.25 mm width, so the ratio argument covers it completely and the
    absolute number did not. `width_frac` 0.1 keeps a segment only if it is at least a
    tenth as long as it is wide; below that the copper at each end already overlaps the
    whole of it. The absolute floor stays as a lower bound for hair-thin tracks.

    And the orphans are not harmless: an isolated fragment is a separate island of its
    net, so DRC counts it as an unconnected item and a board reads as unfinished because
    of copper 0.0005 mm long. One of output_panel's two remaining failures was exactly
    that, and chasing it as a routing problem would have found nothing to fix.

    They come from both directions -- rounding in the Specctra round trip, and this
    file's own generators emitting a segment whose ends differ in the last nanometre --
    so the clean-up belongs where both can be caught rather than at either source.
    """
    floor = pcbnew.FromMM(floor_mm)
    doomed = [t for t in board.GetTracks()
              if t.GetClass() != "PCB_VIA"
              and t.GetLength() < max(floor, t.GetWidth() * width_frac)]
    for t in doomed:
        board.Remove(t)
    return len(doomed)


def _plane_orphans(board, net):
    """Tracks on `net` that the connectivity graph does NOT place in the plane's component.

    ⚠ KEY ON m_Uuid, NEVER id(). SWIG hands back a FRESH Python wrapper on every call, so
    `id(item)` never matches between two traversals: keying on it reported 52 loose GND
    items on led_strip where DRC found 1. The UUID is the board's own identity and agrees
    with DRC exactly (2 loose tracks for its 1 unconnected item).
    """
    zs = [z for z in board.Zones() if z.GetNetname() == net]
    if not zs:
        return [], []
    conn = board.GetConnectivity()
    linked = set()
    for z in zs:
        for it in conn.GetConnectedItems(z):
            try:
                linked.add(it.m_Uuid.AsString())
            except Exception:
                pass
    loose = [t for t in board.GetTracks()
             if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net
             and t.m_Uuid.AsString() not in linked]
    return loose, zs


def _path_clear(board, a, z, net, layer, w, step_mm=0.1):
    """Sample the straight run a->z and refuse it if any sample sits in ANOTHER net's copper.

    ⚠ THE STEP THE FIRST VERSION LACKED, AND IT SHORTED THE BOARD. Without it the repair
    took led_strip to 0 unconnected AND tracks_crossing 0 -> 1 -- two nets crossing, which
    is strictly worse than the floating stub it removed. A stub that floats is a missing
    connection; a crossing is a short, and only one of those is caught downstream.
    """
    n = max(2, int(math.hypot(z.x - a.x, z.y - a.y) / pcbnew.FromMM(step_mm)))
    others = [o for o in board.GetTracks()
              if o.GetNetname() != net and o.GetLayer() == layer]
    pads = [pd for m in board.GetFootprints() for pd in m.Pads()
            if pd.GetNetname() != net]
    for i in range(n + 1):
        p = pcbnew.VECTOR2I(int(a.x + (z.x - a.x) * i / n),
                            int(a.y + (z.y - a.y) * i / n))
        if any(o.HitTest(p, int(w)) for o in others):
            return False
        if any(pd.HitTest(p) for pd in pads):
            return False
    return True


def _plane_points(pos, zs, probe_mm=12.0, step_mm=0.1, limit=6):
    """Plane positions within reach of `pos`, NEAREST FIRST so a blocked path tries the next."""
    out = []
    for i in range(1, int(probe_mm / step_mm) + 1):
        r = i * step_mm
        for a in range(0, 360, 5):
            p = pcbnew.VECTOR2I(int(pos.x + r * 1e6 * math.cos(math.radians(a))),
                                int(pos.y + r * 1e6 * math.sin(math.radians(a))))
            if any(z.GetFilledPolysList(z.GetLayer()).Collide(p) for z in zs):
                out.append((p, r))
                if len(out) >= limit:
                    return out
    return out


def repair_plane_orphans(board, notes, probe_mm=12.0, max_items=24):
    """Reconnect copper the fill stranded from its own plane, and REFILL.

    The stitcher runs ~140 lines before ZONE_FILLER, so it cannot know where the plane
    will end up (see _check_stitches_landed) -- it can only warn. This runs AFTER the
    fill, when the pour is a fact, and finishes the job: for each stranded track, walk
    outward for real plane copper and lay one short segment to it, but ONLY along a path
    that crosses nothing. A track with no clear path is LEFT ALONE on purpose.

    Measured on led_strip (the only board of the eight with anything to repair): 1
    unconnected -> 0, 0 errors, one track laid 1.35 mm and one declined for lack of a
    clear path. The other seven are untouched -- none has a stranded cluster.
    """
    if not notes.get("zones"):
        return 0
    board.BuildConnectivity()
    laid = 0
    for net in sorted({z.GetNetname() for z in board.Zones()}):
        loose, zs = _plane_orphans(board, net)
        if not loose:
            continue
        if len(loose) > max_items:
            print("  ⚠ %d %s track(s) stranded from the plane -- too many to be stitch "
                  "fallout, NOT repairing (look at the pour, not the tracks)"
                  % (len(loose), net))
            continue
        for t in loose:
            w = t.GetWidth()
            done = False
            for src in (t.GetStart(), t.GetEnd()):
                for tgt, r in _plane_points(src, zs, probe_mm):
                    if not _path_clear(board, src, tgt, net, t.GetLayer(), w):
                        continue
                    dx, dy = tgt.x - src.x, tgt.y - src.y
                    n = math.hypot(dx, dy) or 1.0
                    nt = pcbnew.PCB_TRACK(board)
                    nt.SetStart(src)
                    nt.SetEnd(pcbnew.VECTOR2I(int(tgt.x + dx / n * w),
                                              int(tgt.y + dy / n * w)))
                    nt.SetWidth(w)
                    nt.SetLayer(t.GetLayer())
                    nt.SetNet(t.GetNet())
                    board.Add(nt)
                    laid += 1
                    done = True
                    print("      reconnected %s at %.2f,%.2f to the plane (%.2f mm)"
                          % (net, pcbnew.ToMM(src.x), pcbnew.ToMM(src.y),
                             r + pcbnew.ToMM(w)))
                    break
                if done:
                    break
            if not done:
                print("      ⚠ %s at %.2f,%.2f is stranded from the plane and NO clear "
                      "path reaches it -- left alone (a short is worse). Move the part "
                      "or except the pad." % (net, pcbnew.ToMM(t.GetStart().x),
                                              pcbnew.ToMM(t.GetStart().y)))
    if laid:
        board.BuildConnectivity()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return laid


def via_plane_contact(via, poly):
    """How much of a via's annular ring sits in a filled pour: 0.0 .. 1.0.

    ⚠ THE CENTRE OF A VIA IS A HOLE, AND TESTING IT ANSWERS THE WRONG QUESTION. A
    neighbouring via's antipad is a circle of (its radius + the plane's clearance), and
    with a 0.5 mm plane clearance that circle reaches 0.8 mm -- past the CENTRE of a
    stitch via 0.76 mm away, while half of that via's ring still sits in solid plane.
    The centre test called five such vias "landed where the plane is not" and the
    quality pass called their pins unfed, on boards KiCad's own connectivity (which
    asks whether copper overlaps copper) correctly reported as joined. What matters is
    how much of the ring the plane touches, so measure that: sixteen points round the
    middle of the ring, between the drill wall and the land's edge.
    """
    import math
    c = via.GetPosition()
    r = (via.GetDrillValue() / 2.0 + via.GetWidth(pcbnew.F_Cu) / 2.0) / 2.0
    hit = sum(1 for k in range(16) if poly.Collide(pcbnew.VECTOR2I(
        int(c.x + r * math.cos(k * math.pi / 8.0)),
        int(c.y + r * math.sin(k * math.pi / 8.0)))))
    return hit / 16.0


# a stitch counts as landed with a quarter of its ring in the plane: at 0.6 / 0.3 that is
# 0.35 mm of copper into a barrel whose own wall is the narrower conductor
VIA_CONTACT_MIN = 0.25


def _check_stitches_landed(board, notes):
    """Did every stitch via actually land IN the plane it was aiming at?

    ⚠ THE STITCHER PLACES VIAS BEFORE THE ZONES ARE FILLED, so it cannot know where
    the plane will actually be. It checks that a via clears other copper -- which is a
    different question entirely from whether there is any plane copper AT that spot. A
    zone flows around obstacles and drops islands it cannot connect, so a position that
    is beautifully clear of everything can be a hole in the plane, and a via dropped into
    one reaches nothing.

    It fails silently and it fails late: the board looks stitched, the pad has a track and
    a via, and the only symptom is one unconnected item on a routed board -- attributed by
    DRC to a DIFFERENT pad, because it names the two ends of a missing ratline and either
    end will do. On output_panel it cost an hour of looking at the wrong pin.

    This cannot be prevented at placement time without filling the zones first, so it is
    caught after the fact and reported loudly. A board that fails here needs the part
    moved or the pad excepted -- not another routing run.

    ⚠ WHAT A STRAY STITCH ACTUALLY LOOKS LIKE, SINCE IT IS EASY TO GET WRONG. The two on
    the optical board (GND at 116.36,162.95 and 76.32,100.81) are not loose vias sitting
    in empty copper: each is the far end of a short GND stub -- pad, track, via, no plane
    -- and the boards read clean because those pads reach GND another way. A first probe
    said they touched nothing at all and suggested simply deleting them, which would have
    been wrong twice over: the probe compared each track's GetPosition(), which is its
    START, so a track whose END lands exactly on the via reads as absent, and deleting the
    via would have left the stub and could have cut the pad's only return.

    So they stay, and the message stands: this is a placement problem. Report it, do not
    tidy it away.
    """
    planes = {}
    for z in board.Zones():
        if z.GetNetname() in set(notes.get("stitch_nets", ())):
            planes.setdefault(z.GetNetname(), []).append(z)
    if not planes:
        return
    stray = []
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA":
            continue
        zs = planes.get(t.GetNetname())
        if not zs:
            continue
        if not any(via_plane_contact(t, z.GetFilledPolysList(z.GetLayer())) >= VIA_CONTACT_MIN
                   for z in zs):
            stray.append((t.GetNetname(), pcbnew.ToMM(t.GetPosition().x),
                          pcbnew.ToMM(t.GetPosition().y)) + _plane_gap(t.GetPosition(), zs))
    if stray:
        # ⚠ THE DISTANCE IS THE POINT, not the coordinate. "Landed where the plane is not" says
        # a stitch is stray; it does not say whether the plane is 0.1 mm away or 12, and those
        # want opposite answers -- a longer stub versus a placement change. On led_strip
        # (2026-09-29) chasing that gap by hand cost four scratchpad probes to learn the two
        # strays were 1.30 and 0.10 mm off a pour that is ONE island, so a 2 mm stub would have
        # reached both. Report it inline and nobody measures it twice.
        print("  ⚠ %d stitch via(s) landed where the plane is not: %s"
              % (len(stray), ", ".join(
                  "%s at %.2f,%.2f (%s)" % (n, x, y, "%.2f mm away" % d if d == d
                                            else "no plane within %.0f" % _PLANE_PROBE_MM)
                  for n, x, y, d in stray[:6])))
    return stray


_PLANE_PROBE_MM = 12.0


def _plane_gap(pos, zones):
    """How far is the nearest filled plane from `pos`?  (distance_mm,) or (nan,).

    A stray stitch via is only half a diagnosis. What decides the fix is the GAP: sub-millimetre
    means the stub simply stopped short and a longer one reaches; several millimetres means the
    pour cannot get in at all and the PLACEMENT has to change. Walks outward in 0.1 mm steps on
    a 24-point circle, which is enough to tell those two cases apart and costs nothing next to
    the fill itself.
    """
    import math
    for i in range(1, int(_PLANE_PROBE_MM / 0.1) + 1):
        r = i * 0.1
        for a in range(0, 360, 15):
            p = pcbnew.VECTOR2I(int(pos.x + r * 1e6 * math.cos(math.radians(a))),
                                int(pos.y + r * 1e6 * math.sin(math.radians(a))))
            if any(z.GetFilledPolysList(z.GetLayer()).Collide(p) for z in zones):
                return (r,)
    return (float("nan"),)


def _via_r(v):
    """A via's radius. KiCad 10's PCB_VIA::GetWidth() wants a layer -- a via may be a
    different diameter on different layers -- and calling the no-argument form trips an
    assertion and returns something arbitrary. Ours are plain through vias of one
    diameter, but asking properly costs nothing and the warning was real."""
    try:
        return v.GetWidth(v.GetLayer()) / 2.0
    except TypeError:
        return v.GetWidth() / 2.0


class _Terminal:
    """A track end, dressed up enough to stand in for a pad in link_close_gaps.

    The repair joins two things left in different islands, and a track END is as valid a
    thing to join as a pad -- the router routed most of the way and stopped. Giving it
    the three methods the repair actually calls is cheaper than branching the logic.
    """

    def __init__(self, pos, track):
        self._pos = pcbnew.VECTOR2I(pos.x, pos.y)
        self._t = track

    def GetPosition(self):
        return self._pos

    def GetNetname(self):
        return self._t.GetNetname()

    def GetNet(self):
        return self._t.GetNet()

    def GetLayer(self):
        return self._t.GetLayer()

    def GetParentFootprint(self):
        return None

    def real(self):
        """The board item the connectivity graph actually knows about."""
        return self._t

    def GetSize(self):
        # a track end has no land; its "pad" is the trace width, which is what the
        # via-escape search needs in order to stand a via clear of it
        w = self._t.GetWidth()
        return pcbnew.VECTOR2I(w, w)


def link_close_gaps(board, outline, max_mm=5.0, width=0.25, clr=0.2,
                    same_part_only=True, inner=None):
    """Join same-net pads of ONE part that the routed board left in separate islands.

    ⚠ A REPAIR, NOT A CONSTRAINT, and the difference is the whole lesson of the day. The
    same idea applied BEFORE routing -- "join every part's same-net pads" -- laid 75
    segments and took output_panel from 1 unconnected to 8, because most of those pads
    were already going to be connected and the copper only cost the router freedom.
    Capping it by distance laid 50 and was no better in kind.

    Applied AFTER routing it costs nothing by construction: connectivity has already been
    computed, so the only pads considered are ones actually left in different islands.
    There is no counterfactual route being denied, because the routing is done.

    It exists because the router leaves this case surprisingly often. J7 pins 2 and 3 are
    both +24V, 2.5 mm apart on one connector, and freerouting wired each to a different
    half of the net and never joined them -- the SES has no via and no trace between them.
    And a USBLC6's pins 3 and 4 are one node inside the device, so no copper is needed
    there in reality and KiCad has no way to know that; two millimetres of trace makes the
    netlist's claim true on the board.
    """
    import math
    board.BuildConnectivity()
    cc = board.GetConnectivity()
    pads = [(q.GetBoundingBox(), q.GetNetname())
            for fp in board.GetFootprints() for q in fp.Pads()]
    # ⚠ WITH THE LAYER, because the via hop below needs it. A track is only an obstacle
    # on its OWN layer; a via is one on all of them, which is what None means here.
    segs = [((t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y),
             t.GetWidth() / 2.0, t.GetNetname(), t.GetLayer()) for t in board.GetTracks()
            if t.GetClass() != "PCB_VIA"]
    segs += [((t.GetPosition().x, t.GetPosition().y),
              (t.GetPosition().x, t.GetPosition().y), _via_r(t), t.GetNetname(), None)
             for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    margin = pcbnew.FromMM(width / 2.0 + clr)
    drills = [(t.GetPosition().x, t.GetPosition().y) for t in board.GetTracks()
              if t.GetClass() == "PCB_VIA"]

    def clear(x, y, net, layer=None):
        # ⚠ THE BOARD EDGE, AGAIN. This is the THIRD copper-laying routine in this file
        # to be written without it and caught by DRC afterwards -- the stitcher, then
        # _local_nets, now this. The edge is not in any obstacle list because it is not
        # copper, so every new routine starts out unable to see it and runs traces off
        # the side of the board until something says so.
        # The real fix is that these three should share one obstacle model instead of
        # each building its own; that is a refactor, and this is the note that says why
        # it is worth doing rather than a fourth patch.
        if not _inside(outline, int(x), int(y),
                       margin - pcbnew.FromMM(clr) + pcbnew.FromMM(0.3)):
            return False
        for bb, onet in pads:
            if onet == net:
                continue
            dx = max(bb.GetLeft() - x, 0, x - bb.GetRight())
            dy = max(bb.GetTop() - y, 0, y - bb.GetBottom())
            if math.hypot(dx, dy) < margin:
                return False
        for (ax, ay), (bx, by), hw, onet, olay in segs:
            if onet == net:
                continue
            # ⚠ ONLY WHEN A LAYER IS ASKED FOR. Passing None keeps the old, layer-BLIND
            # behaviour for the surface path on purpose: that path is laid on whatever layer
            # its two terminals share, this routine does not track which, and a blind check
            # there refuses paths it could have taken rather than laying copper it should
            # not. The hop knows its layer and says so.
            if layer is not None and olay is not None and olay != layer:
                continue
            vx, vy = bx - ax, by - ay
            L2 = vx * vx + vy * vy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
            if math.hypot(x - (ax + t * vx), y - (ay + t * vy)) - hw < margin:
                return False
        return True

    # ⚠ WIDENED FROM ONE PART TO ANY TWO PADS WITHIN REACH, because the optical board's
    # remaining failures are the same shape one step out: a feedback capacitor and its
    # feedback resistor, 2 mm apart, on the same net, left in two islands. Same argument
    # as the same-part case and it survives the widening for the same reason -- this runs
    # AFTER routing, so the only pairs considered are ones already left unconnected.
    # There is no route being denied; the routing is over.
    # ⚠ A TERMINAL IS NOT ALWAYS A PAD. Most of what the router leaves unfinished is a
    # TRACK END a millimetre or two short of where it was going -- it routed most of the
    # way and stopped. Considering only pads misses all of those, which on the optical
    # board is most of them: of thirteen failures, one was pad-to-pad and the rest had a
    # track end at one side or both.
    groups = {}
    if same_part_only:
        for fp in board.GetFootprints():
            for q in fp.Pads():
                if q.GetNetname():
                    groups.setdefault((fp.GetReference(), q.GetNetname()), []).append(q)
    else:
        for fp in board.GetFootprints():
            for q in fp.Pads():
                if q.GetNetname():
                    groups.setdefault(q.GetNetname(), []).append(q)
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA" or not t.GetNetname():
                continue
            for end in (t.GetStart(), t.GetEnd()):
                groups.setdefault(t.GetNetname(), []).append(_Terminal(end, t))

    made = 0
    if True:
        by_net = {k: v for k, v in groups.items()}
        for net_key, group in by_net.items():
            net = net_key[1] if isinstance(net_key, tuple) else net_key
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    d = (a.GetPosition() - b.GetPosition()).EuclideanNorm()
                    if d > pcbnew.FromMM(max_mm) or d == 0:
                        continue
                    # the connectivity graph knows board items, not our stand-ins
                    ra = a.real() if hasattr(a, "real") else a
                    rb = b.real() if hasattr(b, "real") else b
                    if ra is rb:
                        continue          # the two ends of one track
                    joined = False
                    for it in cc.GetConnectedItems(ra):
                        if it == rb or it.GetPosition() == b.GetPosition():
                            joined = True
                            break
                    if joined:
                        continue          # already one island, by copper or by the plane
                    p0 = (a.GetPosition().x, a.GetPosition().y)
                    p1 = (b.GetPosition().x, b.GetPosition().y)
                    # ⚠ NOT JUST A STRAIGHT LINE. The pads that need joining are often
                    # diagonally across an intervening pad -- a feedback cap's far pin to
                    # its resistor's far pin passes 0.077 mm from the cap's OWN other pad,
                    # which is a different net. A straight segment is the common case and
                    # not the interesting one; the interesting one turns a corner.
                    way = None
                    for sh in _centrelines(p0, p1, detour_mm=2.0, step_mm=0.25):
                        ok = True
                        for q0, q1 in zip(sh, sh[1:]):
                            L = math.hypot(q1[0] - q0[0], q1[1] - q0[1])
                            n = max(4, int(pcbnew.ToMM(L) / 0.15) + 1)
                            if not all(clear(q0[0] + (q1[0] - q0[0]) * k / n,
                                             q0[1] + (q1[1] - q0[1]) * k / n, net)
                                       for k in range(n + 1)):
                                ok = False
                                break
                        if ok:
                            way = sh
                            break
                    if way is None and inner is not None:
                        # ⚠ GO UNDER, when the component layer is full -- and in the
                        # sensing strip it always is: 107 parts in 13.6 mm, which is
                        # exactly where the router gave up too. The inner layer is empty
                        # by comparison, and an SMD pad is no obstacle at all to a trace
                        # a layer below it.
                        # ⚠ IT TAKES `layer`, AND UNTIL NOW IT DID NOT, WHICH MADE
                        # THE HOP DEAD CODE. _hop_via_inner calls its seg_clear callback
                        # with layer= to test the inner leg, so this signature raised
                        # TypeError the first time a pair got that far -- and route.py was
                        # not passing `inner` at all, so no pair ever did. Two omissions,
                        # each hiding the other, and a repair routine that has never in its
                        # life tried a via.
                        def _seg_ok(q0, q1, netname, thru_only=False, layer=None):
                            L = math.hypot(q1[0] - q0[0], q1[1] - q0[1])
                            n2 = max(4, int(pcbnew.ToMM(L) / 0.15) + 1)
                            return all(clear(q0[0] + (q1[0] - q0[0]) * k / n2,
                                             q0[1] + (q1[1] - q0[1]) * k / n2, netname,
                                             layer)
                                       for k in range(n2 + 1))
                        def _emit(q0, q1, pad, netname, layer, _net=net):
                            if q0 == q1:
                                return
                            tk = pcbnew.PCB_TRACK(board)
                            tk.SetStart(pcbnew.VECTOR2I(int(q0[0]), int(q0[1])))
                            tk.SetEnd(pcbnew.VECTOR2I(int(q1[0]), int(q1[1])))
                            tk.SetWidth(pcbnew.FromMM(width))
                            tk.SetLayer(layer)
                            tk.SetNet(pad.GetNet())
                            board.Add(tk)
                            # ⚠ FIVE FIELDS, INCLUDING THE LAYER. `segs` is built at the
                            # top of this routine as 5-tuples and clear() unpacks five;
                            # these two append sites recorded four, so every track this
                            # routine laid poisoned its own obstacle list. It never showed
                            # while repair_mm was 7.0 because the search gave up before it
                            # reached one, and it crashed the whole route the first time
                            # the reach was raised to 14.0 -- a latent bug, not a new one.
                            # The layer was in hand at both sites all along.
                            segs.append((q0, q1, pcbnew.FromMM(width) / 2.0, _net, layer))
                        hop = _hop_via_inner(board, a, b, net, inner,
                                             lambda x, y, nn, **kw: clear(x, y, nn),
                                             _seg_ok, _emit,
                                             0.6, 0.3, clr, width, math, outline, drills)
                        if hop:
                            made += hop
                            board.BuildConnectivity()
                            cc = board.GetConnectivity()
                        continue
                    if way is None:
                        continue
                    # ⚠ THE LAYER THE TWO TERMINALS SHARE, NOT `a`'s. A through-hole pad
                    # answers F.Cu to GetLayer(), so a join from one to a B.Cu track end
                    # was laid on F.Cu and ended over the track with nothing through the
                    # board: copper added, net still open (output_panel, J6's shell to
                    # the declared PWR_GND bar, 2026-10-02). A through pad is on every
                    # layer, so it takes the OTHER terminal's; two single-layer terminals
                    # on different layers share none and are not a surface join at all.
                    def _thru(q):
                        return (isinstance(q, pcbnew.PAD) and q.IsOnLayer(pcbnew.F_Cu)
                                and q.IsOnLayer(pcbnew.B_Cu))
                    # ⚠ AND AN SMD PAD'S LAYER IS THE ONE IT IS ON, NOT GetLayer(). A pad on
                    # a back-side part answered F.Cu, so two back-side capacitors were
                    # "joined" to their rail with F.Cu copper ending over pads on the other
                    # face: six dangling tracks, net still open, and the closing step then
                    # drilled into a pad to finish what this had started (pi_cap).
                    def _lay(q):
                        if isinstance(q, pcbnew.PAD) and not _thru(q):
                            return pcbnew.B_Cu if q.IsOnLayer(pcbnew.B_Cu) else pcbnew.F_Cu
                        return q.GetLayer()
                    if _thru(a) and not _thru(b):
                        lay = _lay(b)
                    elif _thru(b) or _lay(a) == _lay(b):
                        lay = _lay(a)
                    else:
                        continue
                    for q0, q1 in zip(way, way[1:]):
                        if q0 == q1:
                            continue
                        t = pcbnew.PCB_TRACK(board)
                        t.SetStart(pcbnew.VECTOR2I(int(q0[0]), int(q0[1])))
                        t.SetEnd(pcbnew.VECTOR2I(int(q1[0]), int(q1[1])))
                        t.SetWidth(pcbnew.FromMM(width))
                        t.SetLayer(lay)
                        t.SetNet(a.GetNet())
                        board.Add(t)
                        segs.append((q0, q1, pcbnew.FromMM(width) / 2.0, net, lay))
                        made += 1
                    board.BuildConnectivity()
                    cc = board.GetConnectivity()
    return made


def rescue_stray_stitches(board, notes, via_d=0.6, clr=0.2):
    """Move stitch vias that ended up in a hole in the plane, and say how many.

    ⚠ THE PLANE CHANGES SHAPE WHEN THE BOARD IS ROUTED. At layout time it is poured
    around the parts and every stitch via sits in copper; after routing it is poured
    around the parts AND seven hundred tracks, and it flows differently -- so a via that
    was in the plane can be in a void, connected to nothing, with no warning anywhere.
    The pad still has its track and its via and looks stitched.

    This cannot be prevented at placement time without knowing the routed board, so the
    honest structure is to fix it afterwards: find the vias that missed, and walk each one
    out from its pad until it is somewhere the plane actually IS. The track follows it.

    It runs after the post-route refill, and the caller refills again afterwards, because
    moving copper changes the pour that was just computed.
    """
    import math
    planes = {}
    for z in board.Zones():
        if z.GetNetname() in set(notes.get("stitch_nets", ())):
            planes.setdefault(z.GetNetname(), []).append(z)
    if not planes:
        return 0

    def in_plane(net, x, y):
        pt = pcbnew.VECTOR2I(int(x), int(y))
        return any(z.GetFilledPolysList(z.GetLayer()).Collide(pt)
                   for z in planes.get(net, ()))

    pads = [(q.GetBoundingBox(), q.GetNetname())
            for fp in board.GetFootprints() for q in fp.Pads()]
    segs, vias = [], []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias.append(t)
        else:
            segs.append(((t.GetStart().x, t.GetStart().y),
                         (t.GetEnd().x, t.GetEnd().y), t.GetWidth() / 2.0,
                         t.GetNetname()))

    def clear(x, y, net, margin):
        for bb, onet in pads:
            if onet == net:
                continue
            dx = max(bb.GetLeft() - x, 0, x - bb.GetRight())
            dy = max(bb.GetTop() - y, 0, y - bb.GetBottom())
            if math.hypot(dx, dy) < margin:
                return False
        for (ax, ay), (bx, by), hw, onet in segs:
            if onet == net:
                continue
            vx, vy = bx - ax, by - ay
            L2 = vx * vx + vy * vy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
            if math.hypot(x - (ax + t * vx), y - (ay + t * vy)) - hw < margin:
                return False
        for v in vias:
            # ⚠ COPPER ON ONE NET MAY TOUCH; TWO DRILLS MAY NOT. The same-net skip
            # below is right for clearance and wrong for the hole, and that asymmetry is
            # what put two GND stitch vias 0.50 mm apart on output_panel -- 0.20 mm of
            # laminate between the walls, which breaks out on the drill.
            if (math.hypot(x - v.GetPosition().x, y - v.GetPosition().y)
                    < HOLE_GAP + v.GetDrillValue()):
                return False
            if v.GetNetname() == net:
                continue
                continue
            if math.hypot(x - v.GetPosition().x, y - v.GetPosition().y) < margin + _via_r(v):
                return False
        return True

    v_margin = pcbnew.FromMM(via_d / 2.0 + clr)
    t_margin = pcbnew.FromMM(0.25 / 2.0 + clr)
    moved = 0
    for v in list(vias):
        net = v.GetNetname()
        # ⚠ A CROWDED STITCH CANNOT BE RESCUED FROM HERE, and the attempt is recorded
        # rather than left in as dead code. output_panel ends with one hole_to_hole: a GND
        # stitch 0.50 mm from a via that add_missing_vias or link_close_gaps put down. The
        # obvious fix is to widen this trigger to "outside its plane OR crowding another
        # hole" -- and it can never fire, because route.py calls this routine only when
        # _check_stitches_landed reports a stray, and that block runs BEFORE the passes
        # that create the crowding. The via it would move does not exist yet.
        # To finish it: a separate pass at the END of the post-route sequence, beside
        # tidy_router_vias, reusing this routine's search. Not built, because the pair it
        # would fix passes the fab's real 0.2 mm limit and the pipeline it would change
        # is the one that finally reaches 0/0 on five boards.
        if net not in planes or in_plane(net, v.GetPosition().x, v.GetPosition().y):
            continue
        # the track that feeds this via, and the pad end it comes from
        here = (v.GetPosition().x, v.GetPosition().y)
        feed = None
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA" or t.GetNetname() != net:
                continue
            for a, b in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
                if abs(a.x - here[0]) < 1000 and abs(a.y - here[1]) < 1000:
                    feed = (t, b)
                    break
            if feed:
                break
        if feed is None:
            continue
        track, anchor = feed
        best = None
        for step in range(1, 40):
            r = pcbnew.FromMM(0.4 + 0.1 * step)
            for k in range(24):
                ang = 2 * math.pi * k / 24.0
                x = int(anchor.x + r * math.cos(ang))
                y = int(anchor.y + r * math.sin(ang))
                if not in_plane(net, x, y):
                    continue
                if not clear(x, y, net, v_margin):
                    continue
                n = max(4, int(pcbnew.ToMM(r) / 0.15) + 1)
                if not all(clear(anchor.x + (x - anchor.x) * i / n,
                                 anchor.y + (y - anchor.y) * i / n, net, t_margin)
                           for i in range(1, n + 1)):
                    continue
                best = (x, y)
                break
            if best:
                break
        if best is None:
            continue
        v.SetPosition(pcbnew.VECTOR2I(*best))
        track.SetStart(anchor)
        track.SetEnd(pcbnew.VECTOR2I(*best))
        moved += 1
    return moved



def _canonical_uuids(path):
    """Rewrite a saved board so the same design always produces the same file.

    ⚠ THIS IS THE DIFFERENCE BETWEEN A PIPELINE AND A SLOT MACHINE, and it was
    invisible until one unchanged board was routed three times and came back with 14, 17
    and 30 unconnected. The copper this file lays IS deterministic -- two runs produce
    byte-identical geometry, and proving that is what made the real cause findable. What
    was not deterministic is the ORDER it lands in: KiCad gives every item a random UUID
    and sorts the saved file by it, so each run handed the autorouter the same 153 parts
    introduced in a different sequence. A router's result depends on the order it is
    given things, so the board moved run to run while the design stood still.

    A design that cannot be rebuilt the same way twice cannot be diffed, cannot be
    reviewed, and cannot honestly be handed to anyone. "Download the tools and run the
    script" stops meaning anything if the script answers differently each time.

    THE FIX is two steps, and the second is the one that matters. Each UUID is derived
    from the CONTENT of the block it belongs to, so the same footprint at the same place
    always hashes to the same id. Then the blocks that carry ids -- footprints, tracks,
    vias, zones -- are SORTED BY THOSE IDS HERE, in the text, rather than trusting KiCad
    to re-sort on the next save. It does not: a reload and re-save preserves the order it
    read, so canonical ids alone left the file exactly as random as before.

    Everything else in the file keeps its position: net declarations are indexed by
    number and the header is the header. UUIDs are identity, not data, and nothing
    downstream reads them -- only their order was ever escaping.
    """
    import hashlib
    import uuid as _uuid
    txt = open(path, encoding="utf-8").read()
    ns = _uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")
    # scan parens rather than pattern-match: a footprint block contains everything a
    # board block does, and no regex survives that
    spans, depth, start = [], 0, None
    for i, ch in enumerate(txt):
        if ch == "(":
            if depth == 1 and start is None:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 1 and start is not None:
                spans.append((start, i + 1))
                start = None
    pat = re.compile(r'\(uuid "[0-9a-fA-F-]+"\)')
    blocks = []
    for a, b in spans:
        block = txt[a:b]
        key = hashlib.sha1(pat.sub('(uuid "")', block).encode("utf-8")).hexdigest()
        n = [0]

        def sub(_m, key=key, n=n):
            n[0] += 1
            return '(uuid "%s")' % _uuid.uuid5(ns, "%s:%d" % (key, n[0]))
        blocks.append(pat.sub(sub, block))

    # sort only what carries an id; a (net 3 "GND") block is positional and stays put
    MOVABLE = ("(footprint", "(segment", "(via", "(zone", "(arc")
    idx = [i for i, bl in enumerate(blocks) if bl.startswith(MOVABLE)]
    for slot, bl in zip(idx, sorted(blocks[i] for i in idx)):
        blocks[slot] = bl

    out, last = [], 0
    for (a, b), bl in zip(spans, blocks):
        out.append(txt[last:a])
        out.append(bl)
        last = b
    out.append(txt[last:])
    open(path, "w", encoding="utf-8").write("".join(out))


# nearest-first, so a via still lands as close to the direction of travel as it can
_RING_ANGLES = [0.0] + [s * k * 0.15 for k in range(1, 22) for s in (1.0, -1.0)]


def _hop_via_inner(board, pa, pb, netname, inner, clear, seg_clear, emit,
                   via_d, via_drill, clr, width, math, outline, drills):
    """pad -> via -> a run on `inner` -> via -> pad, or 0 if there is no room.

    The two vias are searched separately and close to their own pads, because unlike a
    differential pair there is nothing to keep parallel here -- one net, one conductor,
    and the only requirement is that it arrives.
    """
    def spot(pad, toward):
        """A via position just off `pad`, preferring the direction of travel."""
        pc = pad.GetPosition()
        half = max(pad.GetSize().x, pad.GetSize().y) / 2.0
        need = pcbnew.FromMM(via_d / 2.0 + clr)
        base = math.atan2(toward[1] - pc.y, toward[0] - pc.x)
        # ⚠ THE SEARCH RANGE IS THE LIMIT, NOT THE ROOM. Probed on the optical board at
        # the five edges this routine gives up on: a 0.6 mm via has 5.48 mm of clearance
        # available beside U1.7 and 2.82 mm beside Rf12.2 -- but at ring radii of 3.31 and
        # 2.16 mm, and the old escalation stopped at 2.0 mm with ten fixed angles. It was
        # not that there was nowhere to put a via; it was that nobody looked that far.
        # ⚠ AND THE ANGULAR RESOLUTION IS THE LIMIT TOO -- the same lesson as the note
        # above, one level finer. The old list stepped 0.4 rad, which at 2 mm out is a
        # 0.8 mm stride, wider than the lanes it is hunting for. Pin 6 of every op-amp is
        # boxed in by pins 5 and 7 on its own row, so its ONLY straight escape is due
        # south, and due south sits between two of those samples: the nine B channels that
        # could not place a via had 2.35 mm of clear column under them the whole time.
        # 0.15 rad is 0.3 mm at 2 mm out, under the 0.45 a via needs, so a lane that exists
        # is now hit rather than stepped over.
        for step in range(40):
            r = half + need + pcbnew.FromMM(0.1 * step)
            for dth in _RING_ANGLES:
                x = int(pc.x + r * math.cos(base + dth))
                y = int(pc.y + r * math.sin(base + dth))
                # ⚠ A VIA IS NOT A TRACK, and checking it as one is what made this
                # routine lay DRC-violating copper the first time it was let loose on a
                # small board: 0.6 mm of pad needs via/2 + clearance, not width/2, and a
                # drilled hole needs room from every OTHER hole and from the board edge,
                # neither of which a track cares about. Three separate rules, and the
                # track margin satisfies none of them.
                if not clear(x, y, netname, margin=pcbnew.FromMM(via_d / 2.0 + clr)):
                    continue
                if not _inside(outline, x, y, pcbnew.FromMM(via_d / 2.0 + 0.3)):
                    continue
                lim = pcbnew.FromMM(via_d + clr)
                if any(math.hypot(x - hx, y - hy) < lim for hx, hy in drills):
                    continue
                if not seg_clear((pc.x, pc.y), (x, y), netname):
                    continue
                drills.append((x, y))
                return (x, y)
        return None

    va = spot(pa, (pb.GetPosition().x, pb.GetPosition().y))
    vb = spot(pb, (pa.GetPosition().x, pa.GetPosition().y))
    if va is None or vb is None:
        if os.environ.get("HOP_DEBUG"):
            _f = pa if va is None else pb
            print("      HOP %s: no via site beside %s.%s"
                  % (netname, _f.GetParentFootprint().GetReference(), _f.GetNumber()))
        return 0
    # the run itself only has to clear THROUGH-HOLE copper: an SMD pad lives on the
    # component layer and is no obstacle at all to a trace an layer down
    # ⚠ THE LAYER ARGUMENT IS AN ID, NOT A NAME, and passing the name here meant the
    # inner layer was never checked at all. `emit` records a segment's layer as
    # _LAYERS[inner] -- an int -- and clear() skips any segment whose olay != layer, so
    # `layer=inner` compared 6 against "In2.Cu", which is always unequal, and every run
    # already laid on In2 was invisible. It cost a crossing between TIA_IN_*B and
    # TIA_OUT_*B on ALL TEN strings: a short from each B channel's summing node to its own
    # output, which turns that TIA into a follower. They are the two nets most likely to
    # want this fallback at the same moment, in the same 2 mm, so they found each other
    # every time. thru_only stays: it is about PADS, which are on the component layer and
    # genuinely no obstacle down here.
    way = None
    for sh in _centrelines(va, vb, detour_mm=2.0, step_mm=0.25):
        if all(seg_clear(q0, q1, netname, thru_only=True, layer=_LAYERS[inner])
               for q0, q1 in zip(sh, sh[1:])):
            way = sh
            break
    if way is None:
        if os.environ.get("HOP_DEBUG"):
            print("      HOP %s: vias placed, no run between them" % netname)
        return 0
    n = 0
    emit((pa.GetPosition().x, pa.GetPosition().y), va, pa, netname, pa.GetLayer())
    emit(vb, (pb.GetPosition().x, pb.GetPosition().y), pb, netname, pb.GetLayer())
    n += 2
    for q0, q1 in zip(way, way[1:]):
        emit(q0, q1, pa, netname, _LAYERS[inner])
        n += 1
    for pt, pad in ((va, pa), (vb, pb)):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(int(pt[0]), int(pt[1])))
        v.SetWidth(pcbnew.FromMM(via_d))
        v.SetDrill(pcbnew.FromMM(via_drill))
        v.SetNet(pad.GetNet())
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        board.Add(v)
    return n


def _local_nets(board, patterns, outline, inner=None, local_mm=6.0, width=0.2,
                clr=0.14, via_d=0.6, via_drill=0.3, same_part_only=False,
                skip_nets=(), corridors=(), holes=()):
    """Lay the SHORT, LOCAL part of repetitive nets before the autorouter sees them.

    ⚠ THE TIA NETS ARE TWO PROBLEMS WEARING ONE NAME, and that is why they were the
    hardest thing left on this board. TIA_OUT_1A has four pads: the op-amp's output, the
    feedback resistor, the feedback capacitor -- a cluster a few millimetres across --
    and one more, 106 mm away, at the MCU's ADC pin. The long run is easy and the router
    is good at it. The cluster is three pads in the tightest part of a 13.6 mm strip
    holding 107 components, and the router is bad at it: nearly every unconnected pad
    left on this board is a feedback R or C failing to reach the op-amp pin beside it.

    Handing the router a net that is both does not let it spend its effort where the
    difficulty is. So the CLUSTER is laid here, deterministically -- twenty identical
    little networks, which is exactly the shape of thing a generator does better than a
    search -- and what reaches the router is the two-point run it is good at.

    Clusters are found by single linkage at `local_mm` rather than declared, because
    declaring them would mean twenty entries that go stale the moment a part moves. A
    net whose pads are all within a few millimetres of each other IS a local network;
    that is what the phrase means, and the geometry already knows it.

    An edge that cannot be laid clear is SKIPPED, not forced: the router still has it in
    the DSN and can try. This routine only ever removes work from the router, never adds
    a constraint it has to honour.
    """
    import math
    trk_margin = pcbnew.FromMM(width / 2.0 + clr)
    CELL = pcbnew.FromMM(2.0)

    pads = [(q, fp) for fp in board.GetFootprints() for q in fp.Pads()]
    # the third field says whether this obstacle pierces EVERY layer: a through pad does
    # and an SMD pad does not, which is the whole difference between a surface run and an
    # inner one
    boxes = [(q.GetBoundingBox(), q.GetNetname(),
              q.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH))
             for q, _ in pads]
    # ⚠ TRACKS AS SEGMENTS, not bounding boxes -- see _stitch_plane_pads. A diagonal
    # trace's box is mostly empty corner, and treating that as copper is how a board
    # that has room reports that it has none.
    # ⚠ AN OBSTACLE HAS A LAYER, AND IGNORING THAT MADE THE INNER-LAYER FALLBACK
    # POINTLESS. The fifth field is the layer a track lives on, or None for a via, which
    # pierces every layer and obstructs them all. Without it every F.Cu trace counted
    # against a run on In2.Cu -- so "the surface is full, go under" was evaluated against
    # the copper on the surface, and the answer was always that under is full too. On the
    # optical board that silently disabled the fallback for all five op-amp blocks:
    # instrumented, both vias placed and the run between them was blocked, every time.
    segs = [((t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y),
             t.GetWidth() / 2.0, t.GetNetname(), t.GetLayer()) for t in board.GetTracks()
            if t.GetClass() != "PCB_VIA"]
    segs += [((t.GetPosition().x, t.GetPosition().y),
              (t.GetPosition().x, t.GetPosition().y), _via_r(t),
              t.GetNetname(), None) for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    grid = {}
    for bb, onet, is_thru in boxes:
        for cx in range(bb.GetLeft() // CELL, bb.GetRight() // CELL + 1):
            for cy in range(bb.GetTop() // CELL, bb.GetBottom() // CELL + 1):
                grid.setdefault((cx, cy), []).append((bb, onet, is_thru))

    def clear(x, y, netname, thru_only=False, margin=None, layer=None):
        """`layer` None means "this obstructs on every layer" -- the right question for a
        VIA, which drills through the board. Pass a layer for a TRACK, and copper on the
        other layers stops counting against it."""
        x, y = int(x), int(y)
        margin = trk_margin if margin is None else margin
        # ⚠ THE BOARD EDGE IS AN OBSTACLE TOO, and it is not in the obstacle list because
        # it is not copper. Checking only against pads and tracks let this routine run
        # traces off the side of a 28 x 21 board -- six edge-clearance violations on a
        # board that had none -- because nothing it could see was in the way. The edge
        # rule is measured from the copper's own half width, not from the centreline, so
        # the clearance term comes out and the fab's edge keep-out goes in.
        _edge_m = margin - pcbnew.FromMM(clr) + pcbnew.FromMM(0.3)
        if not _inside(outline, x, y, _edge_m):
            return False
        if not _clear_of_holes(holes, x, y, _edge_m):
            return False
        for cx in range((x - margin) // CELL, (x + margin) // CELL + 1):
            for cy in range((y - margin) // CELL, (y + margin) // CELL + 1):
                for bb, onet, is_thru in grid.get((cx, cy), ()):
                    if onet == netname or (thru_only and not is_thru):
                        continue
                    dx = max(bb.GetLeft() - x, 0, x - bb.GetRight())
                    dy = max(bb.GetTop() - y, 0, y - bb.GetBottom())
                    if math.hypot(dx, dy) < margin:
                        return False
        for (ax, ay), (bx, by), hw, onet, olay in segs:
            if onet == netname:
                continue
            if layer is not None and olay is not None and olay != layer:
                continue                      # different layer: not in the way
            vx, vy = bx - ax, by - ay
            L2 = vx * vx + vy * vy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
            if math.hypot(x - (ax + t * vx), y - (ay + t * vy)) - hw < margin:
                return False
        return True

    def seg_clear(p0, p1, netname, thru_only=False, layer=None):
        L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        n = max(4, int(pcbnew.ToMM(L) / 0.15) + 1)
        return all(clear(p0[0] + (p1[0] - p0[0]) * t / n,
                         p0[1] + (p1[1] - p0[1]) * t / n, netname, thru_only, layer=layer)
                   for t in range(n + 1))

    by_net = {}
    for q, fp in pads:
        n = q.GetNetname()
        if n and n not in skip_nets and any(re.fullmatch(pat, n) for pat in patterns):
            by_net.setdefault(n, []).append(q)

    def emit(q0, q1, pad, netname, layer):
        """One track segment, registered as an obstacle for everything laid after it."""
        if q0 == q1:
            return
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(int(q0[0]), int(q0[1])))
        t.SetEnd(pcbnew.VECTOR2I(int(q1[0]), int(q1[1])))
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(layer)
        t.SetNet(pad.GetNet())
        board.Add(t)
        segs.append((q0, q1, pcbnew.FromMM(width) / 2.0, netname, layer))

    # every hole already on the board, so a new via keeps clear of all of them
    drills = [(t.GetPosition().x, t.GetPosition().y) for t in board.GetTracks()
              if t.GetClass() == "PCB_VIA"]
    drills += [(q.GetPosition().x, q.GetPosition().y) for q, _ in pads
               if q.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)]

    laid, skipped, reach = 0, 0, pcbnew.FromMM(local_mm)
    # ⚠ NAME THE SKIPS, DO NOT JUST COUNT THEM. A count says five edges could not be
    # laid and points at nothing; the names point straight at the pads that end up
    # unconnected two steps later, which is where the board's last failures live.
    #
    # It paid for itself on the first run. The optical board's five skips are not five
    # problems -- they are ONE problem on five identical op-amp blocks:
    #     TIA_OUT_1B: U1.7 -> Rf12.2 (3.48 mm)   and 3B, 5B, 7B, 9B, all 3.48 mm
    # The straight line from the op-amp output to its feedback resistor's far pad passes
    # the SAME RESISTOR'S OTHER PAD, 0.52 mm off the centreline. A 0.2 mm track needs
    # 0.1 + 0.14 clearance and the pad reaches 0.27 from its centre: 0.51 mm required
    # against 0.52 available. Ten microns, so this pass will not place it.
    #
    # ⚠ THAT IS A LIMIT OF THIS ROUTINE, NOT A RISK ON THE BOARD, and the first version of
    # this note got it backwards -- it said the board was "passing on a hundredth of a
    # millimetre, five times". It is not. Measured on the routed board, the router's own
    # copper clears those pads by 0.600, 0.278 and 0.575 mm on F.Cu against a 0.127 fab
    # rule, and on the other two it simply drops to In2.Cu, where an SMD pad does not
    # exist and there is nothing to clear at all. Ten microns is the margin of the path
    # THIS CODE tries, in its own model; it says nothing about the copper that ends up
    # there.
    #
    # What is worth fixing is narrower: the inner-layer fallback below exists for exactly
    # this case -- surface blocked, a layer down trivial -- and on these five it cannot
    # place its via either, so five nets the generator should own go to the router. That
    # costs the router effort in the densest part of the board, which is where its two
    # remaining failures are. A capability gap, not a fragility.
    skipped_edges = []
    for netname in sorted(by_net):
        group = by_net[netname]
        if same_part_only:
            # ⚠ ONE CLUSTER PER PART, and this is the safest pre-laid copper there is.
            # Two pads of the SAME net on the SAME part are usually centimetres of net
            # apart in the router's eyes and millimetres apart in fact: J7 pins 2 and 3
            # are both +24V on a 2.5 mm connector pitch, and freerouting wired each of
            # them to a different half of the net and never joined them to each other --
            # leaving a board one connection short with a 2.5 mm gap in the middle of it.
            #
            # It costs the router almost nothing in freedom, which is what makes it
            # different from the general case: the copper is the shortest that could
            # possibly exist between those two points, so there is no alternative path it
            # could be denying anything.
            by_fp = {}
            for q in group:
                by_fp.setdefault(q.GetParentFootprint().GetReference(), []).append(q)
            # ⚠ ONLY ADJACENT PADS, and the cap is not a detail -- it is the difference
            # between 75 segments and 8. Unrestricted, "join a part's same-net pads"
            # carpets an MCU in copper joining ground pins on opposite corners, which is
            # exactly the freedom-for-determinism trade this was supposed to avoid, and
            # it took output_panel from 1 unconnected to 8. What the router actually fails
            # at is the SHORT case: two pins of one connector 2.5 mm apart. Past a few
            # millimetres the router is better at this than a straight line is.
            clusters = [[a for a in c
                         if any(a is bq or (a.GetPosition() - bq.GetPosition())
                                .EuclideanNorm() <= reach for bq in c if bq is not a)]
                        for c in by_fp.values()]
            clusters = [c for c in clusters if len(c) > 1]
        else:
            # single-linkage clustering: a pad joins a cluster it is within reach of
            clusters = []
            for q in group:
                here = (q.GetPosition().x, q.GetPosition().y)
                hit = [c for c in clusters
                       if any(math.hypot(here[0] - r.GetPosition().x,
                                         here[1] - r.GetPosition().y) <= reach for r in c)]
                if not hit:
                    clusters.append([q])
                    continue
                hit[0].append(q)
                for other in hit[1:]:                 # this pad merged two clusters
                    hit[0].extend(other)
                    clusters.remove(other)
        for cl in clusters:
            if len(cl) < 2:
                continue
            # ⚠ WHAT IS ALREADY JOINED IS NOT WORK, AND THIS ROUTINE COULD NOT SEE IT.
            # The MST below ran over the cluster's PADS, so it laid copper between pads a
            # spine had already connected -- redundant metal, and worse than redundant,
            # because it becomes an obstacle in the tightest part of the board.
            #
            # Measured: handed +3V3A and SAI_FS as retry nets it laid 65 segments and
            # skipped 13, and the thirteen were edges the spines already carry --
            # U30.8 -> Cd9.1 nine times over, U18.23 -> U17.23. Every one of those is a
            # connection that EXISTS. On a net that is 95% finished the routine spent its
            # whole budget re-laying the 95%.
            #
            # That is also the real mechanism behind "pre-laying failing nets makes the
            # board worse" -- 6 unconnected to 9 on the four-net retry, which I had
            # recorded as a general property of pre-laid copper. It is not general. It is
            # this, and the fix is to span ISLANDS rather than pads: pre-merge whatever the
            # board already connects, and let the MST join only what is genuinely apart.
            #
            # It only became possible once declared copper was laid BEFORE the searches
            # (route/layout ordering fix, 2026-09-24). Before that there was nothing here
            # to see.
            _cc = board.GetConnectivity()
            _uf = {}

            def _find(k, _uf=_uf):
                _uf.setdefault(k, k)
                while _uf[k] != k:
                    _uf[k] = _uf[_uf[k]]
                    k = _uf[k]
                return k

            for _i, _a in enumerate(cl):
                # the connectivity graph hands back fresh wrappers, so identity does not
                # survive the call -- compare by position, as link_close_gaps does
                _at = {(it.GetPosition().x, it.GetPosition().y)
                       for it in _cc.GetConnectedItems(_a)}
                for _j in range(_i + 1, len(cl)):
                    _b = cl[_j]
                    # ⚠ INDICES, NOT cl.index(). A pcbnew pad's __eq__ is not identity,
                    # so index() can hand back the wrong pad of a net that has two at the
                    # same place -- and this board has twenty of those (each photodiode
                    # lands its cathode twice).
                    if (_b.GetPosition().x, _b.GetPosition().y) in _at:
                        _ra, _rb = _find(_i), _find(_j)
                        if _ra != _rb:
                            _uf[_ra] = _rb
            _islands = {}
            for _i, _q in enumerate(cl):
                _islands.setdefault(_find(_i), []).append(_q)
            _isl = list(_islands.values())
            if len(_isl) < 2:
                continue                      # the whole cluster is already one island
            _of = {id(q): n for n, g in enumerate(_isl) for q in g}
            # a minimum spanning tree over the cluster's ISLANDS: every island connected,
            # no loops, shortest total copper
            inside, outside = list(_isl[0]), [q for g in _isl[1:] for q in g]
            while outside:
                best = min(((a, b) for a in inside for b in outside),
                           key=lambda ab: (ab[0].GetPosition() - ab[1].GetPosition())
                           .EuclideanNorm())
                a, b = best
                p0 = (a.GetPosition().x, a.GetPosition().y)
                p1 = (b.GetPosition().x, b.GetPosition().y)
                way = None
                # ⚠ ASK ABOUT THE LAYER THE RUN IS ON. This tested every candidate
                # against copper on ALL layers while emitting it on the pads' own -- so a
                # B.Cu spine two layers away blocked a surface run. Harmless while the
                # declared spines were laid AFTER this routine and it could not see them;
                # the moment they were laid first (as they must be, so this can route
                # around them) it dropped 156 segments. Through-hole copper still counts:
                # the grid carries vias and THT pads with no layer filter at all.
                for sh in _centrelines(p0, p1, detour_mm=3.0, step_mm=0.25):
                    if all(seg_clear(q0, q1, netname, layer=a.GetLayer())
                           for q0, q1 in zip(sh, sh[1:])):
                        way = sh
                        break
                if way is not None:
                    for q0, q1 in zip(way, way[1:]):
                        emit(q0, q1, a, netname, a.GetLayer())
                        laid += 1
                elif inner is not None:
                    # ⚠ GO UNDER, when the component layer is full. Half of these edges
                    # were being skipped on a board where they had somewhere to go: a
                    # feedback resistor 2 mm from its op-amp pin with another part's land
                    # between them has no surface path and a trivial one a layer down.
                    # The surface is where the pads are and therefore where the traffic
                    # is; the free inner layer is empty by construction.
                    # ⚠ TRY B.Cu WHEN In2 IS TAKEN. A string's TIA_IN_B and TIA_OUT_B
                    # both want this fallback, in the same 2 mm, at the same moment --
                    # they are the two ends of one feedback loop -- and on one layer the
                    # second one has nowhere to go. It used to "succeed" only because the
                    # layer check was broken and it laid straight across the first (see
                    # _hop_via_inner). With that fixed, nine of them failed instead.
                    # B.Cu is a pour, not a signal layer, but it already carries deliberate
                    # spines and a 2 mm stub in the op-amp band costs the plane nothing.
                    hop = 0
                    for _lay in (inner, "B.Cu"):
                        hop = _hop_via_inner(board, a, b, netname, _lay, clear, seg_clear,
                                             emit, via_d, via_drill, clr, width, math,
                                             outline, drills)
                        if hop:
                            break
                    if hop:
                        laid += hop
                    else:
                        skipped += 1
                        skipped_edges.append(_edge_name(a, b, netname, math))
                else:
                    skipped += 1
                    skipped_edges.append(_edge_name(a, b, netname, math))
                # ⚠ THE WHOLE ISLAND CROSSES, NOT JUST THE PAD. Moving only b would leave
                # its island-mates in `outside` and the MST would come back for them --
                # laying a second, third and fourth edge into copper already reached.
                _n = _of[id(b)]
                for _q in list(outside):
                    if _of[id(_q)] == _n:
                        inside.append(_q)
                        outside.remove(_q)
    # ── CORRIDOR RUNS: cross a barrier through an ASSIGNED gap ──────────────────
    # ⚠ THE ROUTER LOSES THIS ONE BY DESIGN, NOT BY WEAKNESS. Measured on the optical
    # board: 13 of 20 TIA outputs cross the comb, 7 do not, and the 7 that do not are
    # EXACTLY the 7 the DRC reports unconnected -- verified as identical sets. They are
    # all the B channel. Capacity is not the issue: the busiest 4.00 mm strip carries 3
    # crossings against ~13 per layer.
    # What the router cannot know is that a string's A and B outputs are a PAIR that must
    # take DIFFERENT gaps. It sees twenty independent nets, sends both channels of a
    # string at whichever strip looks cheapest, wins with the first and strands the
    # second. Nothing about searching harder fixes that; it is a missing constraint, not
    # a missing path. Assigning the gaps is a decision, and a decision belongs in code.
    # A goes through the strip +Y of its string, B through the strip -Y. Two nets per
    # strip, every strip used once, by construction rather than by luck.
    # Manhattan, three segments, each one clearance-checked against everything already on
    # the board by the same machinery the local pass uses -- so this cannot lay copper the
    # local pass would have refused. If no layer takes it, it is left for the router
    # rather than forced.
    corridor_laid, corridor_failed = 0, []
    for netname, cy_mm, xw_mm, xe_mm in corridors:
        group = by_net.get(netname) or []
        if len(group) < 2:
            corridor_failed.append("%s: fewer than two pads" % netname)
            continue

        def _mmx(q):
            return pcbnew.ToMM(q.GetPosition().x) - SHEET_ORIGIN[0]

        west = [q for q in group if _mmx(q) <= xw_mm]
        east = [q for q in group if _mmx(q) >= xe_mm]
        if not west or not east:
            corridor_failed.append("%s: nothing on one side of the barrier" % netname)
            continue
        a = max(west, key=_mmx)                    # the east-most pad west of the gap
        b = min(east, key=_mmx)                    # the west-most pad east of it
        p0 = (a.GetPosition().x, a.GetPosition().y)
        p5 = (b.GetPosition().x, b.GetPosition().y)
        cy = _to_board(0.0, cy_mm)[1]
        # ⚠ FIVE SEGMENTS, NOT THREE, AND THE JOG IS THE WHOLE POINT. A three-segment
        # Manhattan path takes its vertical leg at the PAD'S OWN x -- which for these runs
        # is inside the feedback column at one end and inside a converter cell at the
        # other, the two densest places on the board -- and then drags a 28 mm horizontal
        # leg through everything between. It placed 5 of 20. The run has to step into the
        # OPEN BAND either side of the barrier first, turn there, cross, and only then go
        # looking for its pad. Same three moves a person would make.
        # The jog x is searched, not assumed: a millimetre either way decides whether it
        # lands in a via field. Bounded and small -- a few offsets, three layers -- and
        # every candidate is clearance-checked by the same machinery as the local pass,
        # so this cannot place copper that pass would have refused.
        done = False
        for dw in (0.0, -1.0, -2.0, 1.0, -3.0):
            for de in (0.0, 1.0, 2.0, -1.0, 3.0):
                xw = _to_board(xw_mm + dw, 0.0)[0]
                xe = _to_board(xe_mm + de, 0.0)[0]
                # ⚠ STOP EAST OF THE BARRIER, DO NOT CHASE THE PAD. The far pad is a
                # coupling cap deep inside a converter cell -- thirteen capacitors at 1.2
                # mm pitch -- and driving a blind Manhattan leg in there failed 15 of 20.
                # It also solves a problem nobody has: the router connects the east end of
                # every one of these nets already; the ONLY thing it cannot do is pick
                # which gap to cross. So this lays pad -> jog -> ACROSS and stops in open
                # copper, which is the same bargain _local_nets strikes at the other end
                # (lay the part the router is bad at, hand back the part it is good at).
                # Freerouting takes a pre-laid trace as fixed and routes TO it -- that is
                # the 17 "froze ... as (type fix)" wires in route.py's log. The warning
                # about pre-laid geometry on this board is about VIAS, which it will not
                # connect; a track is not a via.
                p1, p2, p3 = (xw, p0[1]), (xw, cy), (xe, cy)
                legs = ((p0, p1), (p1, p2), (p2, p3))
                # `inner` is a layer NAME here, as _hop_via_inner takes it -- _LAYERS
                # maps it to the id SetLayer wants.
                for lay in (pcbnew.F_Cu,
                            _LAYERS[inner] if inner else None, pcbnew.B_Cu):
                    if lay is None:
                        continue
                    if all(seg_clear(q0, q1, netname, layer=lay) for q0, q1 in legs):
                        for q0, q1 in legs:
                            emit(q0, q1, a, netname, lay)
                        corridor_laid += 1
                        done = True
                        break
                if done:
                    break
            if done:
                break
        if not done:
            corridor_failed.append("%s: no layer/jog clear through y=%.2f" % (netname, cy_mm))

    return laid, skipped, skipped_edges, corridor_laid, corridor_failed



def _lx(p):
    """A pcbnew point's board-local X in mm -- the frame the notes are written in."""
    return pcbnew.ToMM(p.x) - SHEET_ORIGIN[0]


def _ly(p):
    return SHEET_ORIGIN[1] - pcbnew.ToMM(p.y)


def _dedupe(pts, eps=1e-6):
    """Drop repeated points, so a path whose jog happens to be zero does not emit a
    zero-length track. Six of those reached the board on the first run that laid
    anything -- harmless, but the importer counts them and they read as real copper."""
    out = [pts[0]]
    for q in pts[1:]:
        if abs(q[0] - out[-1][0]) > eps or abs(q[1] - out[-1][1]) > eps:
            out.append(q)
    return out


_DBG_TALLY = {}


def _comb_lanes(board, notes, width=0.2, clr=0.15, pitch=0.50, inner="In2.Cu",
                via_d=0.6, via_drill=0.3, verbose=True):
    """THE COMB CROSSING, LAID AS ONE PATTERN AND COPIED ONCE PER STRING PAIR (user).

    THIS IS THE NET THE ROUTER HAS NEVER FINISHED. Twenty TIA outputs have to get from
    the op-amp column, across the comb, to a coupling cap in their converter cell. The
    comb is SLOTS -- holes through the board -- so no layer crosses one; every run has to
    thread a 4.00 mm lane between two of them. Left to freerouting this came out as
    twenty different improvisations and seven failed, always the same way: a 5.3 mm stub
    dying at the first slot wall with 0.00 mm of copper on the escape layer, because the
    run never got a via down.

    The hardware is ten identical string cells feeding five identical converter cells on
    an 18.72 mm pitch, so the routing should be one pattern five times. What makes that
    expressible is that the geometry is monotonic: the four runs of a group leave the
    op-amp column north-to-south in the same order their caps sit west-to-east (see the
    channel-assignment note in elec/optical.py), so the northernmost run peels out of the
    lane first and no two of the four ever cross.

    THE PATH, west to east:
      F.Cu  out of the feedback cap, a short stub to a via west of the slot field
      In2   down the lane between this pair's own two slots, then north past the cell
      F.Cu  down through the Cm row's own gap onto the coupling cap's pad

    The last leg looks impossible and is not: Ci sits on a 1.2 mm pitch and Cm on the same
    pitch offset 0.8, so EVERY Ci pad sits in a door between two Cm pads -- 0.64 mm of it,
    and a 0.2 track with clearance needs 0.50. That stagger is what the cell near/far row
    split buys, and it is the only way in: Ci north pad has 0.52 mm to the Cm row and its
    south pad belongs to the converter.

    LAID PAD TO PAD, deliberately. This file is emphatic that pre-laid copper is an
    obstacle the router can never renegotiate, and orphan MID-NET copper is worse: the
    corridor generator laid stubs three times and made the board worse every time (19/5,
    16/0, 14/3 against 10/0) because freerouting does not adopt copper that reaches no
    pad. A COMPLETE net is a different proposition -- the router has nothing left to do
    on it, so there is nothing to renegotiate.

    The template is SEARCHED, not hand-placed, over a few offsets per run, because two
    obstacles sit exactly where the naive path wants to be: a row of GND stitch vias at
    the Cm x-positions, and the converter pad via, which is 0.30 mm off one approach
    against the 0.55 a 0.2 track needs. Anything that will not go clear is SKIPPED, not
    forced, and reaches the router exactly as it would have anyway.
    """
    import math

    trk_m = pcbnew.FromMM(width / 2.0 + clr)
    via_m = pcbnew.FromMM(via_d / 2.0 + clr)
    CELL = pcbnew.FromMM(2.0)

    slots = [s["poly"] for s in notes.get("outline_slots", ())]
    if len(slots) < 2:
        return 0, []
    band = []
    for p in slots:
        xs = [q[0] for q in p]
        ys = [q[1] for q in p]
        band.append((min(xs), max(xs), min(ys), max(ys)))
    band.sort(key=lambda b: -b[2])
    sx0 = min(b[0] for b in band)
    sx1 = max(b[1] for b in band)

    pads = [(q, fp) for fp in board.GetFootprints() for q in fp.Pads()]
    # ⚠ THE THIRD FIELD SAYS WHETHER THE PAD PIERCES EVERY LAYER, and leaving it out is
    # what made the first version of this lay nothing at all: 0 of 20, every candidate
    # rejected. An SMD pad has copper on ONE layer, so counting it against an In2.Cu run
    # measures the escape layer's space using the surface's obstacles -- and the converter
    # cell, which every run has to pass under, is nothing but surface pads. The very first
    # diagnostic said so: blocked by ADC1_IN4M, a pad with no In2.Cu copper on it. Same
    # field, same reason, as the one in _local_nets.
    boxes = [(q.GetBoundingBox(), q.GetNetname(),
              q.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH))
             for q, _ in pads]
    segs = [((t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y),
             t.GetWidth() / 2.0, t.GetNetname(), t.GetLayer())
            for t in board.GetTracks() if t.GetClass() != "PCB_VIA"]
    segs += [((t.GetPosition().x, t.GetPosition().y),
              (t.GetPosition().x, t.GetPosition().y), _via_r(t), t.GetNetname(), None)
             for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    grid = {}
    for bb, onet, thru in boxes:
        for cx in range(bb.GetLeft() // CELL, bb.GetRight() // CELL + 1):
            for cy in range(bb.GetTop() // CELL, bb.GetBottom() // CELL + 1):
                grid.setdefault((cx, cy), []).append((bb, onet, thru))

    # ⚠ THE SEGMENTS ARE INDEXED, NOT SCANNED. _local_nets walks its whole track list for
    # every sample point, which is fine when the hops are 2 mm long and there are a few
    # hundred of them. These runs are 30 mm and the candidate search tries dozens per net,
    # so the same linear scan is 20 nets x 140 candidates x 250 samples x 2400 segments --
    # it did not finish. Same 2 mm cell grid the pads already use.
    sgrid = {}

    def index_seg(i):
        (ax, ay), (bx, by), hw, _n, _l = segs[i]
        r = int(hw) + CELL
        for cx in range((min(ax, bx) - r) // CELL, (max(ax, bx) + r) // CELL + 1):
            for cy in range((min(ay, by) - r) // CELL, (max(ay, by) + r) // CELL + 1):
                sgrid.setdefault((cx, cy), []).append(i)

    for _i in range(len(segs)):
        index_seg(_i)

    def add_seg(s):
        segs.append(s)
        index_seg(len(segs) - 1)

    outline = _outline_pts(notes)
    holes = _hole_pts(notes)

    def clear(x, y, netname, margin, layer=None, thru_only=False):
        x, y = int(x), int(y)
        edge = margin - pcbnew.FromMM(clr) + pcbnew.FromMM(0.3)
        if not _inside(outline, x, y, edge):
            return False
        if not _clear_of_holes(holes, x, y, edge):
            return False
        for cx in range((x - margin) // CELL, (x + margin) // CELL + 1):
            for cy in range((y - margin) // CELL, (y + margin) // CELL + 1):
                for bb, onet, thru in grid.get((cx, cy), ()):
                    if onet == netname or (thru_only and not thru):
                        continue
                    dx = max(bb.GetLeft() - x, 0, x - bb.GetRight())
                    dy = max(bb.GetTop() - y, 0, y - bb.GetBottom())
                    if math.hypot(dx, dy) < margin:
                        return False
        seen = set()
        for cx in range((x - margin) // CELL, (x + margin) // CELL + 1):
            for cy in range((y - margin) // CELL, (y + margin) // CELL + 1):
                for i in sgrid.get((cx, cy), ()):
                    if i in seen:
                        continue
                    seen.add(i)
                    (ax, ay), (bx, by), hw, onet, olay = segs[i]
                    if onet == netname:
                        continue
                    if layer is not None and olay is not None and olay != layer:
                        continue
                    vx, vy = bx - ax, by - ay
                    L2 = vx * vx + vy * vy
                    t = (0.0 if L2 == 0 else
                         max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2)))
                    if math.hypot(x - (ax + t * vx), y - (ay + t * vy)) - hw < margin:
                        return False
        return True

    def run_clear(pts, netname, layer):
        # an INNER run only meets pads that drill through; a surface run meets them all
        thru_only = layer not in (pcbnew.F_Cu, pcbnew.B_Cu)
        # ⚠ A COARSE-THEN-FINE PREFILTER WAS TRIED HERE AND REMOVED, MEASURED, not
        # reasoned away: walking each candidate at 0.8 mm before the real 0.12 mm walk
        # made the whole stage SLOWER, 5:00 -> 6:25. The premise was that most candidates
        # die on something big. They do not -- the things that stop a run here are a via
        # 0.23 mm off the centre line and a pad edge a few tenths away -- so the coarse
        # pass almost never rejected and every candidate simply paid for both walks.
        for a, b in zip(pts, pts[1:]):
            pa, pb = _to_board(*a), _to_board(*b)
            L = math.hypot(pb.x - pa.x, pb.y - pa.y)
            n = max(4, int(pcbnew.ToMM(L) / 0.12) + 1)
            for t in range(n + 1):
                if not clear(pa.x + (pb.x - pa.x) * t / n,
                             pa.y + (pb.y - pa.y) * t / n, netname, trk_m, layer,
                             thru_only):
                    return False
        return True

    def remember(pts, netname, layer):
        for a, b in zip(pts, pts[1:]):
            pa, pb = _to_board(*a), _to_board(*b)
            add_seg(((pa.x, pa.y), (pb.x, pb.y),
                     pcbnew.FromMM(width) / 2.0, netname, layer))

    nets = {n.GetNetname(): n for n in board.GetNetInfo().NetsByName().values()}
    laid, why = 0, []
    # why each candidate died, AT THE TIME IT WAS TRIED. Replaying the finished board
    # answers a different question and answers it wrongly: it reports copper laid after
    # the attempt, so a run reads as blocked by one that was not there yet.
    import collections
    blame = collections.defaultdict(collections.Counter)
    # ⚠ THE FIVE GROUPS ARE THE SAME PROBLEM. Converter cells sit on an exact 18.72 mm
    # pitch and every candidate parameter here is already RELATIVE -- x_v to the slot
    # field, dxn and up_dy to the cap, x_t to the slot field, y_e to the cap -- so the
    # tuple that solved run j in one group is the first thing worth trying for run j in
    # the next. When it works, which is the normal case, the search is one candidate
    # instead of up to 740. It is only a reordering: if the remembered tuple does not go
    # clear, the full list is tried behind it exactly as before.
    won = {}

    def _cands(pref=None):
        """Candidate shapes, cheapest deviation first. Two topologies: straight along the
        lane to the cap's own x, and a turn north in the empty corridor between the slot
        ends and the converter, then east above the Cm row."""
        out = []
        # ⚠ SEVEN ENTRY COLUMNS, NOT FOUR. A tile's four runs all leave westward through
        # the same band and each drops a via there, so they need four DIFFERENT x or the
        # last one has nowhere to go -- which is exactly how the fourth door failed in
        # every tile: 2B blocked by 2A's via and 1B's track, with the geometry at its
        # destination already solved (its climb is -0.07 mm). Four offsets for four runs
        # left no slack once the other constraints had their say. The band between the
        # feedback caps at -16.61 and the slot field at -11.51 is 5 mm wide, so columns
        # every 0.3 mm cost nothing and give the search somewhere to put the last one.
        # ⚠ FORCING THE ENTRY ORDER WAS TRIED AND CHANGED NOTHING (2026-09-24), so the
        # column is searched. The analysis behind it still holds and is worth keeping: a
        # tile's four runs all leave west through one band, drop a via, then turn east
        # along their own lane, and run i's eastward leg crosses run j's vertical entry leg
        # whenever j entered EAST of i and i's lane lies inside j's span. For this geometry
        # that makes 1B enter west of 1A and 2A west of 2B. Pre-ordering the columns to
        # satisfy it measured 15 of 20 -- exactly what searching them gives -- so the
        # crossing order is NOT what stops the fourth door, and the next person should look
        # elsewhere rather than re-deriving this.
        # ⚠ 0.5 MM APART, NOT 0.3 -- and the 0.3 grid WAS the fourth door. Two risers
        # 0.3 apart need 0.35 (two 0.2 tracks and 0.15 of clearance), so a column NEXT TO
        # an occupied one is not a column at all. 2A takes sx0-1.0, which left 2B only
        # sx0-0.7 and sx0-1.3 -- both its neighbours, both short by 0.051 mm -- and every
        # remaining column is WEST of 2A's, where 2B's lane is already sealed by 2A's own
        # riser crossing it on the way north. All 1145 candidates failed: 335 on the riser
        # and 810 on the eastward leg. Set COMB_DEBUG=<net> to see that split again. The
        # band still holds seven columns at 0.5 and no two runs share a lane boundary.
        _cols = [sx0 - d for d in (1.0, 2.0, 1.5, 2.5, 3.0, 3.5, 4.0)]
        if pref is not None:
            _cols = [sx0 - pref] + [c for c in _cols if abs(c - (sx0 - pref)) > 1e-9]
        for x_v in _cols:
            for dxn in (0.0, -0.10, 0.10, -0.20, 0.20, -0.30, 0.30):
                for up_dy in (3.6, 4.2, 4.8, 5.4, 6.0):
                    out.append((x_v, dxn, up_dy, None, None))
        for x_v in (sx0 - 1.0, sx0 - 1.6, sx0 - 2.2):
            for dxn in (0.0, -0.15, 0.15, -0.30, 0.30):
                for up_dy in (3.6, 4.2, 4.8):
                    for x_t in (sx1 + 0.7, sx1 + 1.4, sx1 + 2.1, sx1 + 2.8, sx1 + 3.5):
                        for y_e in (3.6, 4.4, 5.2, 6.0):
                            out.append((x_v, dxn, up_dy, x_t, y_e))
        return out

    def _ends(net):
        mine = [q for q, fp in pads if q.GetNetname() == net]
        west = [q for q in mine if _lx(q.GetPosition()) < sx0]
        east = [q for q in mine if _lx(q.GetPosition()) > sx1]
        if not west or not east:
            return None
        src = max(west, key=lambda q: _lx(q.GetPosition()))
        dst = min(east, key=lambda q: _lx(q.GetPosition()))
        return (_lx(src.GetPosition()), _ly(src.GetPosition()),
                _lx(dst.GetPosition()), _ly(dst.GetPosition()))

    def _try(net, lane_y, cand, lay=False):
        """Build this run in the given shape. Returns its path, or None if anything along
        it is not clear. EVERY offset in `cand` is relative -- to the slot field, to the
        cap -- so one tuple means the same shape wherever it is applied."""
        e = _ends(net)
        if e is None:
            return None
        s_x, s_y, d_x, d_y = e
        x_v, dxn, up_dy, x_t, y_e = cand
        x_n, y_up = d_x + dxn, d_y + up_dy
        pv0, pv1 = _to_board(x_v, s_y), _to_board(x_n, y_up)
        if os.environ.get("COMB_DEBUG", "") == net:
            _DBG_TALLY["_tried"] = _DBG_TALLY.get("_tried", 0) + 1
        if not clear(pv0.x, pv0.y, net, via_m):
            if os.environ.get("COMB_DEBUG", "") == net:
                _DBG_TALLY["via west of the slots"] = _DBG_TALLY.get("via west of the slots", 0) + 1
            return None
        if not clear(pv1.x, pv1.y, net, via_m):
            if os.environ.get("COMB_DEBUG", "") == net:
                _DBG_TALLY["via north of the cell"] = _DBG_TALLY.get("via north of the cell", 0) + 1
            return None
        _dbg = os.environ.get("COMB_DEBUG", "") == net
        f0 = _dedupe([(s_x, s_y), (x_v, s_y)])
        if x_t is None:
            pi = [(x_v, s_y), (x_v, lane_y), (x_n, lane_y), (x_n, y_up)]
        else:
            pi = [(x_v, s_y), (x_v, lane_y), (x_t, lane_y),
                  (x_t, d_y + y_e), (x_n, d_y + y_e), (x_n, y_up)]
        pi = _dedupe(pi)
        f1 = _dedupe([(x_n, y_up), (x_n, d_y), (d_x, d_y)])
        if not run_clear(pi, net, _LAYERS[inner]):
            if _dbg:
                _DBG_TALLY["inner crossing"] = _DBG_TALLY.get("inner crossing", 0) + 1
                # which leg, so a blocked lane is named rather than guessed at
                for _i in range(len(pi) - 1):
                    if not run_clear(pi[_i:_i + 2], net, _LAYERS[inner]):
                        _k = "  leg %d %.2f,%.2f->%.2f,%.2f" % (
                            _i, pi[_i][0], pi[_i][1], pi[_i + 1][0], pi[_i + 1][1])
                        _DBG_TALLY[_k] = _DBG_TALLY.get(_k, 0) + 1
                        break
            return None
        if not run_clear(f0, net, pcbnew.F_Cu):
            if _dbg:
                _DBG_TALLY["stub off the cap"] = _DBG_TALLY.get("stub off the cap", 0) + 1
            return None
        if not run_clear(f1, net, pcbnew.F_Cu):
            if _dbg:
                _DBG_TALLY["drop through the door"] = _DBG_TALLY.get("drop through the door", 0) + 1
            return None
        if lay:
            _add_track(board, nets[net], "F.Cu", width, f0)
            _add_via(board, nets[net], x_v, s_y, via_drill, via_d)
            _add_track(board, nets[net], inner, width, pi)
            _add_via(board, nets[net], x_n, y_up, via_drill, via_d)
            _add_track(board, nets[net], "F.Cu", width, f1)
            remember(pi, net, _LAYERS[inner])
            remember(f0, net, pcbnew.F_Cu)
            remember(f1, net, pcbnew.F_Cu)
            for vx, vy in ((x_v, s_y), (x_n, y_up)):
                pv = _to_board(vx, vy)
                add_seg(((pv.x, pv.y), (pv.x, pv.y),
                         pcbnew.FromMM(via_d) / 2.0, net, None))
        return pi

    # ⚠ ONE LANE PER STRING, NOT ONE PER PAIR (user, 2026-09-24: "why are there two orange
    # traces competing for room in a single lane when there is an empty lane next to it").
    # The first version gave each converter group the lane between its OWN two slots, on
    # the reasoning that a pair shares a converter so it may as well share a lane. There is
    # no routing reason for that and it is the worst available choice: FOUR runs in every
    # second lane, with lanes 1, 3, 5 and 7 carrying nothing -- double the congestion in
    # the tightest part of the board while half the channel sat empty.
    #
    # A run belongs in a lane beside ITS OWN string -- A takes the lane above, B the lane
    # below -- which keeps the y jog just as short and spreads 20 runs over 9 lanes instead
    # of 5. Interior lanes carry two (string k+1's B and string k+2's A, opposite sides so
    # they never want the same slot); the two end lanes carry three, string 1 having no
    # lane above it and string 10 none below.
    # ⚠ AND THE TWO END MARGINS ARE CHANNELS TOO. String 1 has no slot above it and
    # string 10 none below, so an A-above/B-below rule with only the INTERIOR lanes pushes
    # both of string 1's runs into one lane and both of string 10's into another -- three
    # runs in the end lanes and the board's own margin, which is open, left empty. The
    # board continues past the end slots (slot 1 tops at y 73.82 and the wrap is at 94),
    # so those margins carry a run each. Eleven channels for twenty runs: exactly two per
    # channel, none crowded, and every run still beside its own string.
    _W = band[0][3] - band[0][2]              # a slot's own height, so a margin matches a lane
    lanes = ([(band[0][3], band[0][3] + _W)]
             + [(band[k + 1][3], band[k][2]) for k in range(len(band) - 1)]
             + [(band[-1][2] - _W, band[-1][2])])

    # ⚠ BOTH OF A STRING'S RUNS SHARE ONE CHANNEL, so a TILE owns its two channels
    # outright. The user named the test that decides this: treat strings 1 and 2 as a
    # separate PCB with no connections anywhere else, and a tile that passes copies
    # blindly. A-above/B-below fails it -- it puts string 2's B in the channel string 3's
    # A uses, so tiles 1 and 2 share a lane and every copy has to be checked against its
    # neighbour rather than simply stamped down. One channel per string means nothing a
    # tile lays can reach into the next one, which is the property that makes copying safe.
    # Channel s (not s-1) so string 1 takes the lane below it, an ordinary inter-slot lane,
    # and only string 10 uses a board margin.
    # ⚠ ALL FOUR OF A TILE'S RUNS CROSS IN THE LANE BETWEEN ITS OWN TWO STRINGS, and the
    # history here is worth keeping because two plausible alternatives are both wrong.
    #
    # The user saw four runs sharing a lane with empty lanes beside it and asked why; I
    # spread them one-per-string, and later one-channel-per-string. BOTH are worse, and
    # the reason only became visible after the cap row moved onto the pair centre: the
    # caps now sit BETWEEN the two strings, so the lane between them is where every one of
    # the four runs is going. Spreading them puts a run 8.95 mm from its own destination
    # instead of alongside it -- one-channel-per-string measured 10 of 20 against 14.
    #
    # And the density that prompted it is not real: four runs at 0.50 mm pitch is 2.0 mm in
    # a 3.4 mm usable lane. It looks crowded and is not. The lanes that stay empty are not
    # wasted capacity, they are lanes nothing needs to cross.
    #
    # It also satisfies the user's own test better than the alternatives: a tile owns ONE
    # lane outright, so nothing it lays can reach into its neighbour.
    runs = [("TIA_OUT_%d%s" % (s, side), s, side, 2 * ((s - 1) // 2) + 1)
            for s in range(1, len(band) + 1) for side in ("A", "B")]
    share = {}
    for r in runs:
        share.setdefault(r[3], []).append(r)
    lane_y_of = {}
    for k, occ in share.items():
        lo, hi = lanes[k]
        c = (lo + hi) / 2.0
        for i, r in enumerate(occ):
            lane_y_of[r[0]] = c + ((len(occ) - 1) / 2.0 - i) * pitch

    # ⚠ NARROW THE BUILD WHILE THE SHAPE IS STILL BEING FOUND (user: "you should narrow
    # your builds so they only build the area around string 1"). COMB_STRINGS=1 lays that
    # string's two runs and leaves every other one to the router, which turns a seven
    # minute layout into well under one and shows the pattern on its own in the viewer.
    _only = os.environ.get("COMB_STRINGS", "").strip()
    _want = set(int(v) for v in _only.replace(",", " ").split()) if _only else None

    # ⚠ ONE SHAPE PER RUN ROLE, CHOSEN ACROSS EVERY STRING THAT USES IT -- the difference
    # between a pattern and a search. The first version picked each run's parameters
    # independently and took whatever cleared first: nine runs came out with three
    # different segment counts, two entry-via positions and four exit positions, visibly
    # not a pattern (user: "What I can see in kicad doesn't look like a consistent
    # repeating pattern"). That is the same improvisation this generator exists to replace,
    # only mine instead of the router's. The remembered-tuple reuse added earlier did not
    # prevent it: it merely REORDERED the candidates, and fell through to a different
    # shape whenever the remembered one did not clear.
    #
    # A candidate is now accepted only if it clears for EVERY string in its role, and a run
    # that cannot take the chosen shape is left to the router rather than given another.
    # Consistent by construction: every laid run congruent to its fellows, and the ones
    # that could not take it visibly absent rather than improvised.
    # ⚠ ONE SHAPE PER SIDE, ACROSS ALL TEN STRINGS -- and the granularity is the whole
    # point. What made the board look improvised was runs differing between STRINGS: nine
    # laid with three segment counts and four exit positions. A and B differing from each
    # other is not that. They are different roles by construction -- different op-amp
    # output pin, different lane, different cap channel -- so one shape for both was tried
    # (2026-09-24) and is too strict: it lays 2 of 6 on three strings where per-side lays
    # all of string 1. Per side, repeated down the board, is the pattern; per string is
    # the improvisation.
    # ⚠ THE ROLE IS THE CONVERTER CHANNEL, NOT THE SIDE -- measured, after trying both.
    # One shape for all twenty lays 7 of 20, and the failures are not scattered: every ODD
    # string's A lays and every EVEN string's A fails. That maps exactly onto the cap row.
    # A converter's four coupling caps sit at 1.2 mm pitch, and the assignment sends odd
    # strings to the two WEST doors and even strings to the two EAST ones -- so a shape
    # that clears x 10.40 does not clear x 14.00, whose door has 0.04 mm to its neighbour.
    # Side was the wrong axis: it splits the runs across doors instead of along them.
    #
    # The repeating unit is the CELL. Four shapes, one per channel, each copied to all five
    # converters -- which is the thing the hardware actually repeats, and what "define the
    # pattern for one and copy it" means here. Keyed on the cap's own x so it is read from
    # the geometry rather than assumed from the net name.
    # ⚠ THE REPEATING UNIT IS THE CONVERTER CELL: TWO STRINGS, FOUR RUNS (user, 2026-09-24:
    # "Given the ADC we can't have a pattern for a single string but I still think we should
    # be able to have a two string pattern which gets copied"). Exactly right, and it is why
    # the earlier attempts kept coming out uneven. A shape was chosen per DOOR, independently,
    # across all five cells -- so the four doors competed for the same space without ever
    # being considered together, and whichever door was solved first took what the next one
    # needed. Choosing per side was worse still: it splits the runs ACROSS doors rather than
    # along them.
    #
    # So: solve ONE cell completely -- all four runs, each laid before the next is chosen, so
    # they see each other -- and then copy that set of four shapes to the other four cells.
    # The cells are identical on an exact 18.72 mm pitch, so a set that works in one is
    # geometrically valid in all; where a copy does not go clear, the difference is something
    # ELSE on the board at that y, and that run goes to the router rather than getting a shape
    # of its own. Every laid cell is congruent to the reference by construction.
    _by_door = {}
    for r in runs:
        e = _ends(r[0])
        if e is not None:
            _by_door.setdefault(round(e[2], 2), []).append(r)

    def _cell_of(r):
        return (r[1] - 1) // 2

    _live = [r for r in runs if _want is None or r[1] in _want]
    _cells = sorted({_cell_of(r) for r in _live})
    if not _cells:
        _cells = [0]
    _ref = _cells[0]
    # ⚠ THE ENTRY COLUMN IS ASSIGNED, NOT SEARCHED, AND THIS IS WHAT THE FOURTH DOOR WAS.
    # A run enters the band, drops a via, climbs to its own lane and turns east. That climb
    # crosses every lane BETWEEN the cap row and its own, and seals each one east of the
    # column -- so run i's lane must start east of any run j whose riser crosses it.
    #
    # The four runs of a cell are 1A/1B (caps NORTH of the shared lane, climbing down) and
    # 2A/2B (caps SOUTH, climbing up), with lanes north-to-south 1A, 1B, 2A, 2B. Only two
    # crossings exist: 1B's riser cuts 1A's lane, and 2A's riser cuts 2B's. So 1A must
    # enter east of 1B and 2B east of 2A, and nothing else is constrained.
    #
    # Searching cannot find that. Doors are solved west to east -- 1A, 1B, 2A, 2B -- and
    # each takes the first column that clears, so 2A took sx0-1.0 and boxed 2B in: the
    # columns east of it are 0.3 and 0.4 away, and a riser passing a VIA needs 0.55 (0.3
    # annulus, 0.1 track, 0.15 clearance). 0.55 east of sx0-1.0 is inside the slot field.
    # Widening the grid to 0.5 did not help either, for the same reason -- the problem was
    # never the grid, it was 2A sitting where 2B had to be.
    #
    # North and south risers never overlap in y (they meet at the lane and stop), so 1A can
    # share 2B's column and 1B can share 2A's. Two columns, 1.0 apart, assigned by role.
    _COL_PREF = (1.0, 2.0, 2.0, 1.0)

    pattern = {}
    for _di, _door in enumerate(sorted(_by_door)):
        ref = [r for r in _by_door[_door] if _cell_of(r) == _ref and r in _live]
        if not ref:
            continue
        for cand in _cands(pref=_COL_PREF[_di % len(_COL_PREF)]):
            if all(_try(r[0], lane_y_of[r[0]], cand) is not None for r in ref):
                pattern[_door] = cand
                for r in ref:
                    if _try(r[0], lane_y_of[r[0]], cand, lay=True) is not None:
                        laid += 1
                    else:
                        why.append(r[0])
                break
        else:
            why += [r[0] for r in ref]
    for _door in sorted(_by_door):
        cand = pattern.get(_door)
        for r in _by_door[_door]:
            if _cell_of(r) == _ref or r not in _live:
                continue
            if cand is not None and _try(r[0], lane_y_of[r[0]], cand, lay=True) is not None:
                laid += 1
            else:
                why.append(r[0])
    if verbose and pattern:
        print("  comb lanes: pattern solved on cell %d, %d of 4 doors, copied to %d cell(s)"
              % (_ref + 1, len(pattern), len(_cells) - 1))
    if verbose:
        tail = ""
        if why:
            tail = ", %d left to the router (%s)" % (len(why), ", ".join(why))
        if _DBG_TALLY:
            print("  COMB_DEBUG %s: %s" % (os.environ.get("COMB_DEBUG"), _DBG_TALLY))
        print("  comb lanes: laid %d of %d run(s) as one repeated pattern%s"
              % (laid, 4 * (len(band) // 2), tail))
        for _n in why:
            print("      %s: could not take the chosen shape" % _n)
    return laid, why


def _edge_name(a, b, netname, math):
    """"net: REF.pad -> REF.pad (d mm)" for an edge this routine could not lay."""
    def _p(q):
        fp = q.GetParentFootprint()
        return "%s.%s" % (fp.GetReference() if fp else "?", q.GetNumber())
    d = pcbnew.ToMM((a.GetPosition() - b.GetPosition()).EuclideanNorm())
    return "%s: %s -> %s (%.2f mm)" % (netname, _p(a), _p(b), d)


def _local_inner(notes):
    """The layer local and retried nets may dive to, or None.

    ⚠ THIS USED TO READ diff_pair_inner, WHICH SILENTLY DISABLED THE FALLBACK ON ANY
    BOARD WITHOUT A DIFFERENTIAL PAIR. "Surface blocked, go a layer down" has nothing to
    do with differential pairs; it needs an inner layer with no pads on it and nothing
    else. Keying it on a diff-pair setting meant lever_sensor -- four layers, In1.Cu a
    ground plane, In2.Cu empty, and a recorded history of nets "stranded at that package"
    that "neither the router nor the generator could get out" -- never called it once.
    Instrumented per end, the hop was not failing: it was never reached, because the
    caller passed None and _local_nets skips the edge without comment when inner is None.

    A board can now say `local_inner` outright, and diff_pair_inner stays as the fallback
    so the boards that already work keep working.
    """
    return notes.get("local_inner") or notes.get("diff_pair_inner")


def _outline_pts(notes):
    """The board edge as board-local mm points, whichever way the board declared it."""
    if notes.get("outline_poly"):
        return [tuple(pt) for pt in notes["outline_poly"]]
    w, h = notes["outline_mm"]
    return [(-w / 2.0, -h / 2.0), (w / 2.0, -h / 2.0), (w / 2.0, h / 2.0), (-w / 2.0, h / 2.0)]


def _hole_pts(notes):
    """Every CUTOUT in the board, as board-local mm polygons.

    ⚠ THE CLEARANCE CHECK KNEW ABOUT THE BOARD EDGE AND NOT ABOUT THE HOLES, which on a
    board whose middle is a ten-slot comb is most of the edge there is. _outline_pts
    returns the outer polygon alone, so _inside() believed the slots were solid copper and
    the retry pass laid 28 mm runs straight across them: 5 unconnected and THIRTY-SEVEN
    violations, nearly all "copper_edge_clearance: Segment on Edge.Cuts + Track". The
    keep-the-better-board rule threw that away and the board stayed at 10/0, so the retry
    looked like it could not help when in fact it had halved the unconnected count and
    been disqualified for driving through the holes.
    Same shape as the CAD/fab divergence this board already produced: a check that reads
    one part of the geometry and silently assumes the rest.
    """
    import math
    out = []
    for sl in notes.get("outline_slots", ()):
        out.append([tuple(q) for q in sl["poly"]])
    for h in notes.get("cutouts", ()):
        cx, cy = h["xy"]
        r = h["d"] / 2.0
        out.append([(cx + r * math.cos(t * math.pi / 8.0),
                     cy + r * math.sin(t * math.pi / 8.0)) for t in range(16)])
    for r in notes.get("outline_holes", ()):
        x0, y0, x1, y1 = r
        out.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    return out


def _clear_of_holes(holes, x, y, margin):
    """Is (x, y) OUTSIDE every cutout by at least `margin`? (all internal units)

    ⚠ NOT _inside() WITH A NEGATIVE MARGIN. That was the first version and it is wrong in
    the direction that matters: _inside returns False as soon as the ray cast says
    "outside", before it ever looks at the margin, so it catches only copper laid THROUGH
    a hole and misses copper laid 0.1 mm BESIDE one -- which is exactly what
    copper_edge_clearance flags. Both tests are needed and neither implies the other.
    """
    import math
    for poly in holes:
        pts = [_to_board(px, py) for px, py in poly]
        n = len(pts)
        inside = False
        for i in range(n):
            ax, ay = pts[i].x, pts[i].y
            bx, by = pts[(i + 1) % n].x, pts[(i + 1) % n].y
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / float(by - ay) + ax:
                inside = not inside
        if inside:
            return False
        for i in range(n):
            ax, ay = pts[i].x, pts[i].y
            bx, by = pts[(i + 1) % n].x, pts[(i + 1) % n].y
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
            if math.hypot(x - (ax + t * dx), y - (ay + t * dy)) < margin:
                return False
    return True


def _inside(outline, x, y, margin):
    """Is board-coordinate (x, y) inside `outline` by at least `margin` (all internal
    units)? Ray cast for the inside test, then point-to-segment for the margin -- a
    point can be well inside a polygon and still be 0.05 mm from one of its edges,
    which is what a via on a board edge looks like to the fab."""
    import math as _m
    pts = [(_to_board(px, py)) for px, py in outline]
    n = len(pts)
    inside = False
    for i in range(n):
        ax, ay = pts[i].x, pts[i].y
        bx, by = pts[(i + 1) % n].x, pts[(i + 1) % n].y
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / float(by - ay) + ax:
            inside = not inside
    if not inside:
        return False
    for i in range(n):
        ax, ay = pts[i].x, pts[i].y
        bx, by = pts[(i + 1) % n].x, pts[(i + 1) % n].y
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        if _m.hypot(x - (ax + t * dx), y - (ay + t * dy)) < margin:
            return False
    return True


def _stitch_plane_pads(board, nets_wanted, outline, via_d=0.6, via_drill=0.3,
                       clr=0.2, max_reach=3.0, allow=(), keepouts=(),
                       escape_pins=(), escape_runs=None, declared=(), declared_vias=(),
                       net_widths=None):
    """Give every pad on a plane net its own via down to the plane layers.

    ⚠ WITHOUT THIS, A GROUND PAD'S CONNECTION DEPENDS ON THE POUR'S ISLAND TOPOLOGY,
    which the router decides after the fact. The F.Cu ground pour connects every
    ground pad when the board is placed -- and then routing lays 2400 track segments
    across it, chopping it into islands, and every island that does not happen to
    reach a via is unconnected copper and gets removed. 86 ground endpoints went that
    way on the optical board. The pour is still worth having (it is what stops the
    router having to find 75 separate paths), but it cannot be the ONLY thing holding
    a pad to the plane.

    A via per pad makes each connection independent of everything that happens later:
    the pad reaches In1.Cu directly, and the pour becomes a bonus rather than the
    mechanism.

    PLACEMENT IS SEARCHED, NOT ASSUMED. The via goes beside the pad, in the first of
    eight directions at increasing radius that clears every other pad on the board by
    `clr`. Same-net pads do not block it -- a ground via touching ground copper is the
    point -- and a direction that fails simply is not used. Pads with nowhere to put a
    via are REPORTED rather than skipped silently, because that is a real placement
    problem and the board should not quietly ship with one pad floating.
    """
    import math
    pads = [(pad, fp) for fp in board.GetFootprints() for pad in fp.Pads()]
    # ⚠ PADS ARE RECTANGLES AND MODELLING THEM AS CIRCLES DOES NOT WORK HERE. The
    # first version took each pad's radius as half its LARGEST dimension, which for an
    # LQFP144 pin -- 1.48 long by 0.30 wide -- inflates its width by five times. Every
    # point near the pad row then reads as occupied, and the search failed on all nine
    # of the MCU's VSS pins with "no room" when there was plenty. Bounding boxes are
    # what pcbnew already computes, they follow the pad's rotation, and point-to-box is
    # not meaningfully more code than point-to-circle.
    others = [(p.GetBoundingBox(), p.GetNetname()) for p, _ in pads]
    # ⚠ AND THE COPPER THAT IS ALREADY THERE. This used to look at pads only, which was
    # true when stitching was the first thing to lay anything. It is not any more: the
    # differential pairs are routed before this, and their tracks and transition vias
    # are obstacles like any other. Ignoring them put stitch vias on top of diff-pair
    # vias and stitch tracks across diff-pair traces -- five shorts and a pair of
    # co-located drills, none of which either routine could see on its own.
    # ⚠ A TRACK IS A SEGMENT, NOT ITS BOUNDING BOX, and for a DIAGONAL track those
    # are wildly different things: a 45-degree trace 2 mm long has a bounding box with
    # 1.4 mm of empty corner on either side of it, and every one of those corners reads
    # as occupied copper. It is the same mistake this file already fixed for pads -- a
    # pad modelled as a circle of its largest half-dimension -- and it cost the same
    # thing twice. Here it made the ESD array's GROUND pin unstitchable: the pair leaves
    # the two pins either side of it at an angle, and the empty corner of one of those
    # bounding boxes sat 0.17 mm from the ground pin's only way out. The real copper is
    # 0.86 mm away. Point-to-segment is four lines of arithmetic and it is not optional
    # on a board where the pairs are the things running at angles.
    # ⚠ AN OBSTACLE HAS A LAYER, and this list did not carry one -- the same omission
    # _local_nets already fixed, in the same words, for the same reason. The stitch TRACK
    # is laid on its pad's own layer, so copper on another layer is not in its way; only
    # the VIA, which drills through everything, meets all of it. Without the distinction
    # the +3V3D trunk on B.Cu blocked an F.Cu stub passing over it, and four Cm caps in
    # four different cells reported "no room to stitch" while the only obstruction was on
    # a layer their track never touches.
    segs = [((t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y),
             t.GetWidth() / 2.0, t.GetNetname(), t.GetLayer()) for t in board.GetTracks()
            if t.GetClass() != "PCB_VIA"]
    segs += [((t.GetPosition().x, t.GetPosition().y),
              (t.GetPosition().x, t.GetPosition().y), _via_r(t),
              t.GetNetname(), None) for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    # ⚠ AND THE DECLARED COPPER, WHICH IS NOT ON THE BOARD YET. Stitching runs before
    # notes["tracks"] / notes["vias"] are laid (see the ordering note in layout()), so the
    # search could not see them: a capacitor's ground stitch went 1.4 mm north into a
    # declared 2 mm +5 V bar and the first anyone knew was two shorting_items on the
    # routed board. A declared rail is a decision already made; it is an obstacle here
    # exactly as if it had been drawn, and the order of laying stays what it was.
    for _dn, _dl, _dw, _dpts in declared:
        _lid = board.GetLayerID(_dl)
        _q = [_to_board(px_, py_) for px_, py_ in _dpts]
        segs += [((a_.x, a_.y), (b_.x, b_.y), pcbnew.FromMM(_dw) / 2.0, _dn, _lid)
                 for a_, b_ in zip(_q, _q[1:])]
    for _dv in declared_vias:
        _c = _to_board(_dv[1], _dv[2])
        segs.append(((_c.x, _c.y), (_c.x, _c.y),
                     pcbnew.FromMM(_dv[4] if len(_dv) > 4 else 0.6) / 2.0, _dv[0], None))

    # ⚠ HOLE-VS-HOLE ON EVERY NET WAS TRIED HERE AND REVERTED -- IT BROKE THE BUILD.
    # The idea is sound: copper on one net may touch, two DRILLS may never, and
    # _clear_of skips same-net obstacles, so a stitch via beside one GND connector pin
    # can land in the NEXT GND pin's hole. That is the 8 on motor_ctrl and 6 on
    # output_panel still reported as holes_co_located after the via-in-pad fix.
    #
    # What it cost: `need` is measured from the pad CENTRE and is about 0.5 mm, which is
    # outside an SMD land and INSIDE a PTH land's 1.0 mm barrel. Make holes obstacles and
    # every candidate ring for a through-hole pad falls in its own hole -- seven pads on
    # motor_ctrl reported "no room to stitch" and layout.py failed outright. A rule that
    # is too strict does not fail safe: it turns a DRC warning into a build that does not
    # complete. Two attempts at the margin (via pad radius, then drill-edge clearance)
    # both failed the same way, because the margin was never the problem -- the SEARCH
    # RING starting inside the barrel was.
    #
    # To finish this properly: raise `need` for PTH pads to clear their own drill before
    # making holes obstacles, and re-measure all three boards. Left undone rather than
    # half-done, because the remaining co-located drills are warnings and a broken layout
    # is not.
    # ⚠ A DRILL IN A SMALL LAND IS NOT A SAME-NET NICETY. _clear_of skips copper on the
    # stitch's own net, which is right for copper and wrong for the HOLE: an open barrel
    # in a pasted 0402 or SOT land wicks the joint's solder down the hole. Two cases
    # reached a finished board -- a pin's own stitch via overlapping the edge of its own
    # land, and one part's stitch landing in the ground land of the capacitor beside it.
    # So every small pasted SMD land is a keep-out for the hole on EVERY net, its own
    # included. Large lands (thermal tabs) are left to the quality pass, which weighs the
    # barrel volume against the paste.
    small_lands = []
    for _fp in board.GetFootprints():
        for _p in _fp.Pads():
            if _p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            _bb = _p.GetBoundingBox()
            if pcbnew.ToMM(_bb.GetWidth()) * pcbnew.ToMM(_bb.GetHeight()) >= 4.0:
                continue
            small_lands.append(_bb)

    def _hole_off_lands(x, y):
        lim = pcbnew.FromMM(via_drill / 2.0 + 0.05)
        for bb in small_lands:
            dx = max(bb.GetLeft() - x, 0, x - bb.GetRight())
            dy = max(bb.GetTop() - y, 0, y - bb.GetBottom())
            if math.hypot(dx, dy) < lim:
                return False
        return True

    def _clear_of(x, y, netname, margin, layer=None):
        """True if (x, y) keeps `margin` from every pad or track NOT on `netname`.

"""
        for bb, onet in others:
            if onet == netname:
                continue
            dx = max(bb.GetLeft() - x, 0, x - bb.GetRight())
            dy = max(bb.GetTop() - y, 0, y - bb.GetBottom())
            if math.hypot(dx, dy) < margin:
                return False
        for (ax, ay), (bx, by), half_w, onet, olay in segs:
            if onet == netname:
                continue
            # layer None means "this obstructs every layer" -- a via. Pass a layer for a
            # track and copper elsewhere in the stack stops counting against it.
            if layer is not None and olay is not None and olay != layer:
                continue
            vx, vy = bx - ax, by - ay
            L2 = vx * vx + vy * vy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
            if math.hypot(x - (ax + t * vx), y - (ay + t * vy)) - half_w < margin:
                return False
        return True
    made, failed, done_vias = 0, [], []
    for pad, fp in pads:
        # ⚠ SIGNAL PINS CAN ASK FOR THE SAME THING, BY NAME. A fine-pitch pin whose
        # neighbours took the escape positions first is left on F.Cu with no way off the
        # layer, and the router never goes back to make room -- SAI_FS, ULPI_D1 and
        # ULPI_D6 on the optical board, each found by eye as "disconnected AND no via".
        # This routine already searches for a legal via beside a pad and lays the stub
        # with it; naming a pin here is asking it to do that for a signal.
        # ⚠ AND IT MUST BE BY REF.PAD, NOT BY COORDINATE. The first version of this put
        # scanned x/y in the board notes, and the moment the board's length changed every
        # pad moved ~1.1 mm while the declared vias did not -- stubs at angles through
        # paths nobody had checked. A site is only valid for the placement it was measured
        # against, so it has to be measured HERE, where the placement exists.
        _key = "%s.%s" % (fp.GetReference(), pad.GetNumber())
        _is_escape = _key in escape_pins
        if pad.GetNetname() not in nets_wanted and not _is_escape:
            continue
        # ⚠ A PAD'S OWN DRILL IS INVISIBLE TO ITS OWN STITCH VIA, and on a THROUGH-HOLE
        # pad that means the via lands in the hole. `free()` below skips every obstacle
        # on the same net -- correct for copper, wrong for a BARREL -- so a PTH pad's
        # stitch via is placed at the one spot guaranteed to collide with it. DRC grades
        # the result holes_co_located, severity WARNING, so finish.py's error count stayed
        # at zero and nobody looked: 20 on motor_ctrl, 14 on output_panel, every one a
        # stitch via on an XH connector pin.
        #
        # ⚠ AND SKIPPING PTH PADS ALTOGETHER WAS THE WRONG FIX -- MEASURED. It is
        # defensible on paper (a PTH pad reaches the plane by existing, so the via is
        # redundant) and it cost the optical board SIX NETS, reproducibly: 0 unconnected
        # to 6, on a board with only four through-hole pads. Removing four vias from a
        # board at its routing limit re-planned the whole thing. The narrow fix keeps
        # every stitch via and only moves it OFF the hole, so nothing else sees a change.
        net = pad.GetNet()
        pc = pad.GetPosition()
        half = max(pad.GetSize().x, pad.GetSize().y) / 2.0
        need = pcbnew.FromMM(via_d / 2.0 + clr)
        # ⚠ STAY OUT OF A FINE-PITCH PART'S ESCAPE FAN. This routine puts a ground via
        # as close to its pad as it will fit, which is right in open board and wrong at
        # the edge of a 0.4 mm QFN: the via lands in the first rank of the fan-out and
        # the SIGNAL pins either side of it -- 0.4 mm away -- have nowhere left to leave.
        # On lever_sensor one via at pin 16 was enough to strand pins 15 and 17, and it
        # read as "the router cannot escape a fine-pitch package" rather than as this
        # routine having taken their lane.
        #
        # Ground has somewhere else to go and signals do not: the plane is directly
        # underneath, so a millimetre more track to reach it costs a ground connection
        # nothing, while that millimetre is the whole difference for a signal. Threshold
        # is 0.65 mm because 0.8 mm pitch and coarser has room for both.
        pitch = _pad_pitch(fp)
        if pitch is not None and pitch < pcbnew.FromMM(0.65) and not _is_escape:
            # ...but NOT for a named signal escape. That margin exists to keep GROUND out
            # of a fine-pitch fan, on the reasoning that ground has the plane underneath
            # and can afford the extra millimetre while a signal cannot. An escape pin IS
            # the signal, so pushing it out of its own fan defeats the request.
            need += pcbnew.FromMM(1.1)
        # ⚠ A BIG PAD TAKES THE VIA INSIDE ITSELF, and that is the right answer rather
        # than a concession. An exposed thermal pad -- a QFN's belly, a SOT-223's tab --
        # is enclosed by its own part's pins, so there is no "beside" to search; the
        # first version of this raised on U7.25 for exactly that reason. Vias straight
        # through a thermal pad are how those parts are meant to be grounded anyway, and
        # inside the pad there is nothing to collide with by definition.
        # The threshold keeps ordinary SMD lands out of it: an 0805's 1.0 mm land is too
        # narrow to swallow a 0.6 via and still hold solder, and via-in-pad there wicks
        # paste down the hole.
        # ⚠ "NOTHING TO COLLIDE WITH BY DEFINITION" IS TRUE OF AN SMD PAD AND FALSE OF A
        # THROUGH-HOLE ONE, whose own drill is at exactly the point this branch puts the
        # via. An XH connector land is ~1.7 mm, so it passes the threshold above and gets
        # a via dead centre, in the hole. DRC calls that holes_co_located at severity
        # WARNING, finish.py counts only unexpected ERRORS, and the count stayed at zero:
        # 20 on motor_ctrl and 14 on output_panel, every one an XH pin.
        #
        # PTH pads fall through to the beside-the-pad search instead, which keeps the
        # stitch and only moves it off the hole. Skipping them ENTIRELY was tried first
        # and cost the optical board six nets reproducibly (0 unconnected -> 6, on a
        # board with four through-hole pads) -- removing vias from a board at its routing
        # limit re-plans the whole thing. The narrow fix changes where one via sits; the
        # blunt one changed how many exist.
        _is_pth = pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
        # ...UNLESS IT IS A NAMED EXCEPTION: then there is no via at all. This branch checks
        # nothing (by the argument above), and that argument fails the moment something is
        # PRE-LAID under the package on an inner layer -- the output board's DN2 pair runs
        # on In2 beneath the hub, and the hub's belly via landed on it. Naming the pad in
        # stitch_exceptions said "this one reaches ground through the pour"; honour that
        # here rather than only in the report. A PTH exception is skipped too: its own plated
        # barrel reaches the plane, and every PTH exception before this one had "no room"
        # beside it anyway, so no board that already used one loses a via. (The optical
        # board's USB-C shell tabs are why: the pad-number fix gave three of them GND for
        # the first time, each drew a stitch via, and the re-plan cost a TIA net.)
        if "%s.%s" % (fp.GetReference(), pad.GetNumber()) in allow:
            continue
        # ⚠ AND THE LAND HAS TO BE BIG ENOUGH TO LOSE THE PASTE (quality A12, 2026-10-04).
        # Width alone let a 1.4 x 1.2 crystal ground pad take a via: its barrel holds half
        # the paste that pad is printed with. 4 mm2 is where the barrel is a quarter of it.
        # A pad with no paste (a test pad) has nothing to lose and keeps the old test.
        _area_ok = (pcbnew.ToMM(pad.GetSize().x) * pcbnew.ToMM(pad.GetSize().y) >= 4.0
                    or not (pad.IsOnLayer(pcbnew.F_Paste) or pad.IsOnLayer(pcbnew.B_Paste)))
        if (not _is_pth and _area_ok
                and min(pad.GetSize().x, pad.GetSize().y) >= pcbnew.FromMM(via_d + 0.6)):
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pc)
            v.SetWidth(pcbnew.FromMM(via_d))
            v.SetDrill(pcbnew.FromMM(via_drill))
            v.SetNet(net)
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            board.Add(v)
            done_vias.append((pc.x, pc.y))
            made += 1
            continue
        # ⚠ FINE-PITCH PINS NEED A FANOUT, NOT A NUDGE. A via cannot fit beside an
        # LQFP144 pin on a 0.5 mm pitch -- its neighbours are 0.5 mm away and a 0.6 mm
        # via with clearance needs about 1.0. The escape is to go OUTWARD, past the pad
        # row entirely, which is how every fine-pitch package is fanned out; the first
        # version searched only 0.5 mm and gave up on all 9 of the MCU's VSS pins.
        # So: search out to several millimetres, and try the direction pointing AWAY
        # from the part first, because that is where the open board is. Inward from a
        # QFP pin is the package's own belly and there is never room there.
        # THE COURTYARD CENTRE, not fp.GetPosition() -- a footprint's origin is
        # wherever its author put it, which for most packages is PIN 1, i.e. a corner.
        # Pointing "outward" away from a corner sends half the pins sideways along their
        # own pad row instead of off the package, and the search then fails on exactly
        # the fine-pitch pins it was added for.
        def _lay(pad_, net_, pts_):
            """Check a stitch path -- pad -> corners -> via at pts_[-1] -- and lay it.

            Returns False and emits nothing if anything along it is too close to
            foreign copper, so a caller can simply try the next candidate.
            """
            x_, y_ = pts_[-1]
            # ⚠ CHECK THE WHOLE SEGMENT, NOT JUST THE VIA. The first version tested only
            # the via's centre and let the short track from the pad run wherever it
            # liked -- straight across U10's USB_DM pad, in one case, which DRC correctly
            # called a short between GND and a USB data line. The track is copper too.
            # ⚠ AND SAMPLE BY LENGTH, NOT BY A FIXED COUNT. Five samples over a 5 mm
            # track is one every 1.25 mm, and a 0.5 mm pad fits between two of them --
            # which is exactly how that short got laid while every sample said clear.
            samples = []
            for q0_, q1_ in zip(pts_, pts_[1:]):
                seg_ = math.hypot(q1_[0] - q0_[0], q1_[1] - q0_[1])
                n_ = max(4, int(pcbnew.ToMM(seg_) / 0.15) + 1)
                samples += [(q0_[0] + (q1_[0] - q0_[0]) * t / n_,
                             q0_[1] + (q1_[1] - q0_[1]) * t / n_) for t in range(n_ + 1)]
            if not _inside(outline, x_, y_, pcbnew.FromMM(via_d / 2.0 + 0.3)):
                return False      # a via hanging off the board edge is not a via
            # ⚠ STAY OUT OF THE RESERVED CHANNELS. A through via pierces every layer, so
            # 75 ground stitches turn the inner layers into a sieve -- and an inner layer
            # is exactly where a differential pair needs a clear run under the component
            # rows. Without a reserved corridor the two features simply cannot both
            # succeed: whichever goes first wins and the other reports failure.
            # ⚠ THE VIA ONLY, AND DELIBERATELY. Extending this to the stitch TRACK was
            # tried on 2026-09-24 and reverted the same hour: it cost Cm24.2, Cm34.2,
            # Cm44.2 and Cm54.2 their ground vias outright, because their stubs cross the
            # B.Cu spine lane on F.Cu and had nowhere else to go. These are VIA keepouts
            # and the reason is in the note above -- a through via pierces every layer, so
            # it turns a reserved inner-layer channel into a sieve. A surface track over a
            # B.Cu spine does not touch it. The rule was generalised past its reason.
            if any(kx0 <= pcbnew.ToMM(x_ - _to_board(0, 0).x) <= kx1
                   and ky0 <= -pcbnew.ToMM(y_ - _to_board(0, 0).y) <= ky1
                   for kx0, ky0, kx1, ky1 in keepouts):
                return False
            # ⚠ TWO DIFFERENT MARGINS, because two different things are being placed.
            # The VIA is 0.6 across and needs via/2 + clearance; the TRACK reaching it is
            # 0.25 and needs only track/2 + clearance, about half as much. Holding the
            # track to the via's margin is what made the search fail on every fine-pitch
            # VSS pin: the first sample sits at the pad's own centre, 0.35 mm from the
            # neighbouring land, which clears a 0.25 track easily and never a 0.6 via.
            # ⚠ THE STUB IS AS WIDE AS ITS NET IS DECLARED (2026-10-04). It was 0.25 mm
            # whatever net_widths said, so a rail the router drew at 0.5 mm left its
            # inductor through a 0.25 mm neck 1.2 mm long -- the narrowest copper on the
            # path, and the one piece nobody had drawn (fret_led_key +14V, 1.38 A, quality
            # A1). Capped by the land it leaves: copper wider than its own pad is a bridge
            # to the next one.
            import fnmatch as _fn
            _sw = max([0.25] + [w for pat, w in (net_widths or {}).items()
                                if _fn.fnmatchcase(pad_.GetNetname(), pat)])
            _sw = max(0.25, min(_sw, pcbnew.ToMM(min(pad_.GetSize().x, pad_.GetSize().y))))
            via_lim = pcbnew.FromMM(via_d / 2.0 + clr)
            trk_lim = pcbnew.FromMM(_sw / 2.0 + 0.127)
            if not _clear_of(x_, y_, pad_.GetNetname(), via_lim):
                return False
            if not _hole_off_lands(x_, y_):
                return False
            if not all(_clear_of(px, py, pad_.GetNetname(), trk_lim, pad_.GetLayer())
                       for px, py in samples[1:]):
                return False
            # ...and against the vias already placed, or two neighbouring pads choose
            # the same gap and drill the same hole twice.
            lim = pcbnew.FromMM(via_d + clr)
            if any(math.hypot(x_ - vx, y_ - vy) < lim for vx, vy in done_vias):
                return False
            v_ = pcbnew.PCB_VIA(board)
            v_.SetPosition(pcbnew.VECTOR2I(int(x_), int(y_)))
            v_.SetWidth(pcbnew.FromMM(via_d))
            v_.SetDrill(pcbnew.FromMM(via_drill))
            v_.SetNet(net_)
            v_.SetViaType(pcbnew.VIATYPE_THROUGH)
            board.Add(v_)
            for q0_, q1_ in zip(pts_, pts_[1:]):
                t_ = pcbnew.PCB_TRACK(board)
                t_.SetStart(pcbnew.VECTOR2I(int(q0_[0]), int(q0_[1])))
                t_.SetEnd(pcbnew.VECTOR2I(int(q1_[0]), int(q1_[1])))
                t_.SetWidth(pcbnew.FromMM(_sw))
                t_.SetLayer(pad_.GetLayer())
                t_.SetNet(net_)
                board.Add(t_)
            done_vias.append((x_, y_))
            # ⚠ AN ESCAPE MAY CARRY ITS OWN INNER RUN, laid FROM THE VIA THIS CALL JUST
            # PLACED. Declaring that run in the board notes instead would mean writing the
            # via's x/y there, and a hard-coded escape position goes stale the moment any
            # placement moves -- it already did once, leaving stubs at angles through paths
            # nobody had checked. Here the position is not a guess, it is where the via is.
            # ⚠ VERIFY AN escape_run FROM THE VIA, NOT FROM THE PAD. The run starts HERE,
            # at a position this search chose, which is typically 1-2 mm off the pad -- so
            # a path measured pad-to-target is a DIFFERENT line from the one laid. ULPI_D0
            # was verified clear from its pad and then laid from a via 1.25 mm south of it,
            # straight past a GND via: one short and one clearance error. The via position
            # is not knowable before layout runs, so either lay out once and re-verify from
            # the via that appears, or declare the whole escape (stub + via + run) at
            # coordinates checked together.
            _run = (escape_runs or {}).get("%s.%s" % (fp.GetReference(), pad.GetNumber()))
            if _run:
                _lay_name, _pts = _run
                _prev = (x_, y_)
                for _px, _py in _pts:
                    _q = _to_board(_px, _py)
                    _t = pcbnew.PCB_TRACK(board)
                    _t.SetStart(pcbnew.VECTOR2I(int(_prev[0]), int(_prev[1])))
                    _t.SetEnd(_q)
                    _t.SetWidth(pcbnew.FromMM(_sw))
                    _t.SetLayer(board.GetLayerID(_lay_name))
                    _t.SetNet(net_)
                    board.Add(_t)
                    _prev = (_q.x, _q.y)
            return True

        fc = fp.GetCourtyard(pcbnew.F_CrtYd).BBox().GetCenter()
        out_a = math.atan2(pc.y - fc.y, pc.x - fc.x) if (pc.x, pc.y) != (fc.x, fc.y) else 0.0
        dirs = sorted((math.pi * k / 4.0 for k in range(8)),
                      key=lambda a: abs(((a - out_a + math.pi) % (2 * math.pi)) - math.pi))
        placed = False
        # ⚠ A FINE RADIAL STEP, because the spot that works is sometimes a slot rather
        # than a field. The ESD array's centre pin is its GROUND -- where the clamp
        # diodes dump what they catch -- and it is boxed in: the pair's two rails leave
        # either side of it and the package's other pad row faces it across 0.96 mm.
        # The only via position that clears everything is the middle of that lane, and
        # the window is 0.08 mm wide. On a 0.15 mm step whether it is found at all is
        # luck, and the failure mode is a protection device grounded only through the
        # pour, which routing can orphan -- which is to say not grounded.
        for step in range(84):
            r = half + need + pcbnew.FromMM(0.05 * step)
            # A stitch is a SHORT hop to the plane. Past a couple of millimetres it has
            # stopped being that and become a wire with an impedance and a loop area,
            # and the honest thing is to fail and say the pad has no room rather than
            # quietly run one across the board.
            if r - half > pcbnew.FromMM(max_reach):
                break
            for a in dirs:
                x = int(pc.x + r * math.cos(a))
                y = int(pc.y + r * math.sin(a))
                # ⚠ CHECK THE WHOLE SEGMENT, NOT JUST THE VIA. The first version tested
                # only the via's centre and let the short track from the pad run wherever
                # it liked -- straight across U10's USB_DM pad, in one case, which DRC
                # correctly called a short between GND and a USB data line. The track is
                # copper too; sample along it and hold it to the same clearance.
                # ⚠ SAMPLE BY LENGTH, NOT BY A FIXED COUNT. Five samples over a
                # 5 mm track is one every 1.25 mm, and a 0.5 mm pad fits between two
                # of them -- which is exactly how a GND stitch ended up laid straight
                # across U10's USB_DM pad while every sample said it was clear.
                if not _lay(pad, net, [(pc.x, pc.y), (x, y)]):
                    continue
                made += 1
                placed = True
                break
            if placed:
                break

        # ⚠ AN L, WHEN A STRAIGHT HOP CANNOT WORK -- and on the ESD array it cannot,
        # ever, on any board. Its centre pin is GROUND and its two neighbours are the
        # differential pair, so the only clear direction is straight out between two
        # traces that are 0.5 mm apart by the time they leave the package. The nearest
        # position with room for a via is 2.4 mm away around the corner of the part.
        #
        # This is what a person draws without thinking about it: down the lane between
        # the two pad rows, out from under the belly, via. It is still a SHORT hop --
        # the whole path is held to max_reach -- but it is allowed one turn. A straight
        # line is tried first and almost always wins; this runs only for the pads that
        # would otherwise be reported as having nowhere to go, which is the honest
        # alternative and not a better one: a protection device grounded through the
        # pour alone, where routing can orphan it, is not grounded.
        if not placed:
            dirs8 = [math.pi * k / 4.0 for k in range(8)]
            for d1 in [pcbnew.FromMM(0.4 + 0.2 * k) for k in range(9)]:
                for a1 in dirs:
                    mx = int(pc.x + d1 * math.cos(a1))
                    my = int(pc.y + d1 * math.sin(a1))
                    for a2 in dirs8:
                        if abs(((a2 - a1 + math.pi) % (2 * math.pi)) - math.pi) < 0.1:
                            continue          # same heading: that is the straight try
                        for k in range(24):
                            d2 = half + need + pcbnew.FromMM(0.1 * k)
                            if pcbnew.ToMM(d1 + d2) > max_reach:
                                break
                            x = int(mx + d2 * math.cos(a2))
                            y = int(my + d2 * math.sin(a2))
                            if _lay(pad, net, [(pc.x, pc.y), (mx, my), (x, y)]):
                                made += 1
                                placed = True
                                break
                        if placed:
                            break
                    if placed:
                        break
                if placed:
                    break

        if not placed:
            failed.append("%s.%s" % (fp.GetReference(), pad.GetNumber()))
    failed = [f for f in failed if f not in allow]
    if failed:
        raise SystemExit(
            "no room for a stitching via beside %d pad(s): %s\n"
            "Those pads can only reach the plane through the pour, which routing can "
            "orphan. Move the part, widen its neighbourhood, or -- if the pad really "
            "can live on the pour alone -- name it in stitch_exceptions with a reason."
            % (len(failed), ", ".join(failed[:12])))
    return made


def _edge_poly(board, pts):
    """An arbitrary closed outline on Edge.Cuts, in board-local mm.

    THE BOARD IS NOT ALWAYS A RECTANGLE. The motor tee grew an EAR off its +X end
    to carry a mounting hole -- a positive M4 through the board instead of a screw
    beside it, because a screw beside the board only resists pull-out by friction
    and the tee's connectors face the direction it would be pulled. The layout
    region stays 40 x 16 and every part stays where it was; the outline is what
    changed."""
    for a, b in zip(pts, pts[1:] + pts[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(_to_board(*a))
        seg.SetEnd(_to_board(*b))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.1))
        board.Add(seg)


def _cutout(board, cx, cy, d, keepout=0.6):
    """A round hole as an Edge.Cuts circle -- which is how a board CUTOUT is drawn,
    as against a plated pad. These M4 clearance holes are mechanical: nothing
    connects to one, so giving it a pad would invent a net that does not exist.

    ⚠ AND IT GETS A KEEPOUT, WHICH THE TEE'S HOLE DID NOT NEED AND THE TRRS
    ADAPTER'S DOES. KiCad's Specctra exporter does not turn an Edge.Cuts circle
    into a DSN boundary, so FREEROUTING CANNOT SEE THE HOLE -- it happily lays
    track across it. The tee's ear hole sits in a bare tab where nothing wanted to
    route, so the gap never showed; the adapter's sits mid-board between the two
    connectors, where every net has to pass, and the first route put a +V track
    0.166 from the edge of it. A keepout zone DOES export, so the router is told
    about the hole in the only language it reads.

    `keepout` is the ring added to the hole's RADIUS: 0.6 covers the 0.3 board-edge
    clearance plus half a 0.25 track and a little rounding."""
    c = pcbnew.PCB_SHAPE(board)
    c.SetShape(pcbnew.SHAPE_T_CIRCLE)
    c.SetCenter(_to_board(cx, cy))
    c.SetEnd(_to_board(cx + d / 2.0, cy))
    c.SetLayer(pcbnew.Edge_Cuts)
    c.SetWidth(pcbnew.FromMM(0.1))
    board.Add(c)

    import math
    r = d / 2.0 + keepout
    poly = pcbnew.SHAPE_LINE_CHAIN()
    for i in range(24):
        a = 2.0 * math.pi * i / 24.0
        poly.Append(_to_board(cx + r * math.cos(a), cy + r * math.sin(a)))
    poly.SetClosed(True)
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowZoneFills(True)
    z.SetLayerSet(pcbnew.LSET.AllCuMask())
    z.AddPolygon(poly)
    board.Add(z)


def _edge_hole(board, x0, y0, x1, y1, keepout=0.6):
    """A RECTANGULAR board cutout: Edge.Cuts for the fab, and a keepout so the router
    can see it.

    ⚠ BOTH, FOR THE REASON _cutout SPELLS OUT ABOVE: KiCad's Specctra exporter does not
    turn Edge.Cuts geometry into a DSN boundary, so freerouting is blind to a hole drawn
    that way and will lay track straight across it. The keepout zone is the only language
    it reads. This one matters more than the round ones -- the optical board is a RING and
    its hole is 30 x 105 mm with the bridge bearings inside it, so a router that cannot
    see it would route half the board through thin air.
    """
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for a, b in zip(corners, corners[1:] + corners[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(_to_board(*a))
        seg.SetEnd(_to_board(*b))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.1))
        board.Add(seg)
    k = keepout
    poly = pcbnew.SHAPE_LINE_CHAIN()
    for cx, cy in ((x0 - k, y0 - k), (x1 + k, y0 - k), (x1 + k, y1 + k), (x0 - k, y1 + k)):
        poly.Append(_to_board(cx, cy))
    poly.SetClosed(True)
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowZoneFills(True)
    z.SetLayerSet(pcbnew.LSET.AllCuMask())
    z.AddPolygon(poly)
    board.Add(z)


def _edge_slot(board, poly, rects, keepout=0.15):
    """ONE slot of the comb: an arbitrary closed Edge.Cuts outline for the fab, plus
    keepout zones the router can actually see.

    ⚠ TWO REPRESENTATIONS ON PURPOSE, and they are not redundant. The fab needs ONE closed
    outline per hole -- the bearing slot and the string slot of a string OVERLAP by 0.25 mm,
    so drawing them as two rectangles leaves two intersecting closed contours and the CAM
    operator gets to guess. `poly` is their merged 8-point outline.
    The ROUTER cannot read Edge.Cuts at all (see _edge_hole), so it needs a rule area --
    and a rule area does not have to be one shape. `rects` is the two sub-rectangles, each
    grown by `keepout`; overlapping keepouts are harmless, where overlapping Edge.Cuts is
    not. Exact where it must be, convenient where it may be.
    """
    for a, b in zip(poly, poly[1:] + poly[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(_to_board(*a))
        seg.SetEnd(_to_board(*b))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.1))
        board.Add(seg)
    for x0, y0, x1, y1 in rects:
        k = keepout
        chain = pcbnew.SHAPE_LINE_CHAIN()
        for cx, cy in ((x0 - k, y0 - k), (x1 + k, y0 - k),
                       (x1 + k, y1 + k), (x0 - k, y1 + k)):
            chain.Append(_to_board(cx, cy))
        chain.SetClosed(True)
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowZoneFills(True)
        z.SetLayerSet(pcbnew.LSET.AllCuMask())
        z.AddPolygon(chain)
        board.Add(z)


def _edge_rect(board, w, h):
    """The outline on Edge.Cuts, centred on the board origin."""
    hw, hh = w / 2.0, h / 2.0
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    for a, b in zip(corners, corners[1:] + corners[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(_to_board(*a))
        seg.SetEnd(_to_board(*b))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.1))
        board.Add(seg)


def _rules(board, notes):
    """Stack-up and clearances. A board left on KiCad's defaults fails DRC on
    fine-pitch parts for a reason that has nothing to do with the design: the
    default 0.2 mm clearance is wider than the gap between a 0.4 mm-pitch QFN's
    own pads, so every adjacent pin pair is reported. 0.127 mm (5 mil) is
    JLCPCB's standard capability and is what these boards are made to."""
    bds = board.GetDesignSettings()
    bds.SetCopperLayerCount(int(notes.get("layers", 2)))
    bds.m_MinClearance = pcbnew.FromMM(0.127)
    # 0.127 (5 mil) is JLCPCB's standard capability on 2 and 4 layer, and it is
    # what these boards are ordered to. KiCad's 0.200 default is not a fab limit
    # -- leaving it in place reports the router's own legal narrowing (it drops
    # to 0.187 to escape a 0.4 mm-pitch QFN) as 50 violations.
    bds.m_TrackMinWidth = pcbnew.FromMM(0.127)
    # ⚠ THE MINIMUMS HAVE TO FOLLOW THE NET CLASS OR DRC GRADES THE BOARD AGAINST A
    # RULE IT NO LONGER USES. Setting only the net class via and leaving these at 0.6/0.3
    # gave lever_sensor 0 unconnected and 36 errors -- 18 via_diameter and 18
    # drill_out_of_range -- every one of them the board complaining about vias it had
    # just been told to make.
    _mvd, _mvdr = notes.get("via_mm", (0.6, 0.3))
    bds.m_ViasMinSize = pcbnew.FromMM(_mvd)
    bds.m_MinThroughDrill = pcbnew.FromMM(_mvdr)
    bds.m_CopperEdgeClearance = pcbnew.FromMM(0.3)
    for nc in board.GetAllNetClasses().values():
        nc.SetClearance(pcbnew.FromMM(0.127))
        # ⚠ TRACK WIDTH IS A BOARD-LEVEL CHOICE, because escape room is set by the
        # finest-pitch part on the board and not by a house default. 0.25 with 0.127
        # clearance needs 0.377 mm per lane, which fits a 0.5 mm pitch part comfortably
        # and a 0.4 mm QFN only just -- and "only just" is not enough once the fan has to
        # turn. A board whose tightest package is 0.4 says so and gets narrower default
        # track; boards without one keep 0.25, which is cheaper to manufacture and more
        # forgiving of etch variation.
        nc.SetTrackWidth(pcbnew.FromMM(notes.get("track_mm", 0.25)))
        # KiCad's default 0.8/0.4 via cannot escape a 0.4 mm-pitch QFN -- it does
        # not fit between the pads, so the router simply leaves those pins
        # unrouted. 0.6/0.3 is JLCPCB's STANDARD (not advanced) capability and
        # costs nothing extra.
        # ⚠ PER-BOARD, BECAUSE ONE BOARD'S FAN NEEDS THREE LANES WHERE 0.6 GIVES TWO.
        # lever_sensor puts CAN_RX, CAN_TX and SWDIO on three adjacent 0.4 mm-pitch QFN
        # pins; measured there, the two that escape park their vias in the third's only
        # opening. A smaller via is the standard answer, and it is NOT free -- a 0.25 mm
        # drill leaves the standard capability the note above is about -- so a board that
        # wants one says so and pays for it explicitly.
        _vd, _vdr = notes.get("via_mm", (0.6, 0.3))
        nc.SetViaDiameter(pcbnew.FromMM(_vd))
        nc.SetViaDrill(pcbnew.FromMM(_vdr))

    # ⚠ PER-NET WIDTH, BECAUSE UNTIL NOW EVERY NET ON EVERY BOARD WAS 0.25 mm AND A 24 V
    # TRUNK WAS ONE OF THEM. The fleet's 24 V bus is budgeted under 5 A: the cable was
    # raised to 2 x 22 AWG for it and the XH contacts were doubled for it. The copper
    # between them was never sized, because there was nowhere to say so -- track_mm is one
    # number for the whole board. By IPC-2221 at a 10 C rise, 0.25 mm of 1 oz outer copper
    # carries 0.88 A. Nothing downstream can notice: DRC compares copper to the netlist
    # and has no concept of current, and the netlist has no concept of width.
    #
    # ⚠ AND A WIDTH IS ONLY USEFUL IF A PAD CAN ACCEPT IT. freerouting does not neck down
    # into a land, so a net that touches an 0402 (0.6 mm pads) cannot sensibly be drawn
    # much over 0.5 mm, whatever the current argument says. That is why this is a per-NET
    # dial and not a per-current one, and why a trunk that genuinely needs 2 mm wants
    # deliberate copper of its own rather than a bigger number here.
    for _pattern, _w in sorted((notes.get("net_widths") or {}).items()):
        _name = "W%.2f" % _w
        if not bds.m_NetSettings.HasNetclass(_name):
            _nc = pcbnew.NETCLASS(_name)
            _nc.SetClearance(pcbnew.FromMM(0.127))
            _nc.SetTrackWidth(pcbnew.FromMM(_w))
            _nc.SetViaDiameter(pcbnew.FromMM(0.6))
            _nc.SetViaDrill(pcbnew.FromMM(0.3))
            bds.m_NetSettings.SetNetclass(_name, _nc)
        bds.m_NetSettings.SetNetclassPatternAssignment(_pattern, _name)
    if notes.get("net_widths"):
        bds.m_NetSettings.RecomputeEffectiveNetclasses()


_LAYERS = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu,
           "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu}


def _add_track(board, net, layer, width, pts):
    """A polyline of tracks on one layer, all on one net."""
    for a, b in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(_to_board(*a))
        t.SetEnd(_to_board(*b))
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(_LAYERS[layer])
        t.SetNet(net)
        board.Add(t)


def _edge_row_escape(board, ref, outline, width=0.15, clr=0.15, back=1.5):
    """Fan the EDGE-SIDE row of a two-row through-hole header out round its ends.

    ⚠ WHY THIS EXISTS (2026-10-02). A right-angle pin header has to stand with its plastic
    at the board edge and its pins overhanging, or the socket that goes on them fouls the
    laminate. That puts the outer pad row 1.0 mm from the edge with the inner row 1.27
    behind it: 0.27 between pads, and a lane in front that takes one default-width track.
    The router was handed that on the Pi cap and the UI board the same day and left four
    and three ways open -- every one of them a pad in that row.
    It is a PLACEMENT-shaped problem with one answer, so it is drawn rather than searched:
    the lane takes TWO 0.15 tracks per layer, each end of the row has a way round, and
    that is eight ways for a row of seven. From the row's end inward:
        k=0  B.Cu  straight out sideways, then back past the inner row
        k=1  F.Cu  inner lane, inner column        k=2  F.Cu  outer lane, outer column
        k=3  B.Cu  inner lane, outer column
    Each track stops `back` mm behind the inner row, on open board, for the router --
    and the two columns stand 0.6 apart and stop 1.0 apart, because the router arrives
    with a 0.25 track and at the lane's own 0.3 pitch it could not land on one column's
    end without fouling the other (first run: all seven laid, six left unconnected).
    ⚠ `outline` IS PASSED IN, NOT READ OFF THE BOARD: Edge.Cuts is drawn AFTER this runs,
    so the board's own edge box is empty here -- which on the UI board picked the INNER
    row and drove seven tracks out across the edge.
    Read off the PLACED pads, not derived from the placement: the Pi cap's header is on
    the back of the board and the UI board's is on the front, turned differently.
    """
    fp = next(f for f in board.GetFootprints() if f.GetReference() == ref)
    pads = [q for q in fp.Pads() if q.GetNumber().isdigit()]
    xs = sorted({q.GetPosition().x for q in pads})
    ys = sorted({q.GetPosition().y for q in pads})
    assert 2 in (len(xs), len(ys)), "%s is not a two-row header on a 90 degree turn" % ref
    rows_along_y = len(xs) == 2          # the two rows differ in x; pads run along y
    _ob = [_to_board(x, y) for x, y in outline]
    lo, hi = ((xs[0], xs[1]) if rows_along_y else (ys[0], ys[1]))
    _oc = [q.x for q in _ob] if rows_along_y else [q.y for q in _ob]
    e_lo, e_hi = min(_oc), max(_oc)
    assert min(lo - e_lo, e_hi - hi) < pcbnew.FromMM(2.5), (
        "%s is not at a board edge: nothing for an edge-row fan to do" % ref)
    outer, sgn = (lo, -1) if lo - e_lo < e_hi - hi else (hi, 1)      # sgn: toward the edge

    def pt(n, u):                         # (across the rows, along the row) -> board
        return pcbnew.VECTOR2I(int(n), int(u)) if rows_along_y else pcbnew.VECTOR2I(int(u), int(n))

    def nu(q):
        c = q.GetPosition()
        return (c.x, c.y) if rows_along_y else (c.y, c.x)
    row = sorted((q for q in pads if nu(q)[0] == outer), key=lambda q: nu(q)[1])
    rad = max(q.GetSize().x for q in row) / 2
    w, c = pcbnew.FromMM(width), pcbnew.FromMM(clr)
    lane = [rad + c + w // 2, rad + c + w // 2 + w + c]
    colu = [lane[0], lane[0] + pcbnew.FromMM(0.6)]
    inner_n = outer - sgn * abs(hi - lo)
    stop = inner_n - sgn * pcbnew.FromMM(back)
    plan = [("B.Cu", None, 0), ("F.Cu", 0, 0), ("F.Cu", 1, 1), ("B.Cu", 0, 1)]
    half = (len(row) + 1) // 2
    assert half <= len(plan), "%s: a row of %d is more than this fan can turn" % (ref, len(row))
    n_laid = 0
    for side, group in ((-1, row[:half]), (1, row[half:][::-1])):
        u_end = nu(group[0])[1]
        for k, q in enumerate(group):
            layer, ln, col = plan[k]
            n0, u0 = nu(q)
            ucol = u_end + side * colu[col]
            pts = [pt(n0, u0)]
            if ln is not None:
                pts += [pt(n0 + sgn * lane[ln], u0), pt(n0 + sgn * lane[ln], ucol)]
            else:
                pts += [pt(n0, ucol)]
            # F.Cu columns run 1.2 further than B.Cu ones: a column on each layer shares
            # one XY, and an end stacked on the other layer's end has nowhere to via
            _far = col * 1.0 + (1.2 if layer == "F.Cu" else 0.0)
            pts += [pt(stop - sgn * pcbnew.FromMM(_far), ucol)]
            for p0, p1 in zip(pts, pts[1:]):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(p0)
                t.SetEnd(p1)
                t.SetWidth(w)
                t.SetLayer(_LAYERS[layer])
                t.SetNet(q.GetNet())
                board.Add(t)
            n_laid += 1
    return n_laid


def _add_via(board, net, x, y, drill=0.3, diameter=0.6):
    """One explicit through via, in board-local mm.

    ⚠ WHY THIS EXISTS. `tracks` could already lay explicit copper, but only ON ONE
    LAYER, so a connection that has to CHANGE layers was not expressible at all. The
    optical board's last unconnected net is exactly that shape: +3V3A already passes
    3.86 mm from U2's supply pad on B.Cu, and the F.Cu lane at the pad's own y is
    shadowed by MID at 0.56 mm centre to centre. The fix is a via and a short hop, and
    before this there was no way to say so -- which is why four successive attempts all
    reached for router SETTINGS (pre-lay, retry rounds, dropping the B.Cu pour,
    narrowing the net) and all four made the board worse.

    A via here is pre-laid copper, and this file is emphatic that pre-laid copper is an
    obstacle the router can never renegotiate. That objection is real and it is why this
    takes explicit coordinates instead of a net name: one via placed deliberately is a
    different proposition from a rule that lays 122 segments.
    """
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(_to_board(x, y))
    v.SetWidth(pcbnew.FromMM(diameter))
    v.SetDrill(pcbnew.FromMM(drill))
    v.SetNet(net)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    board.Add(v)


def _add_zone(board, net, layer, inset, w, h):
    """A copper pour over the whole board less `inset`. Not decoration: it is
    how the THT pads reach GND at all, since no GND track is drawn."""
    zone = pcbnew.ZONE(board)
    zone.SetLayer(_LAYERS[layer])
    zone.SetNet(net)
    zone.SetIsFilled(True)
    # SOLID pad connection, not thermal relief. Thermals exist to stop a pour
    # stealing heat from a hand-soldering iron; these boards are reflowed by the
    # fab, and on a board this small KiCad reports the two-spoke minimum as
    # "starved" anyway. Solid is also the better electrical answer for a return.
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    # ⚠ ISLAND HANDLING MUST BE SET EXPLICITLY, and not setting it was a live bug.
    # A bare pcbnew.ZONE() comes up with a min-island-area of 1e13 nm2 -- 10,000 mm2,
    # larger than any board here -- which is uninitialised memory, not a default. With
    # the AREA mode that number would purge every island on the board.
    #
    # It went unnoticed because the pours that existed were each ONE island: a plane on
    # an inner layer with nothing on it to break it up. The moment GND was poured on
    # F.Cu, where 153 parts fragment it into hundreds of islands, the zone filled to
    # exactly ZERO square millimetres -- and a zone that fills to nothing looks, in the
    # board file, exactly like a zone that filled fine.
    #
    # ALWAYS is the right mode and the one KiCad's own UI defaults to: an island of
    # copper not connected to its net is an antenna, so drop it. The islands that
    # matter are the ones touching a pad, and those are connected by definition.
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    hw, hh = w / 2.0 - inset, h / 2.0 - inset
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
        pt = _to_board(x, y)
        outline.Append(pt.x, pt.y)
    board.Add(zone)
    return zone


def build(stem):
    """stem = the path prefix shared by <stem>.net and <stem>.board.json."""
    comps, nets = read_netlist(stem + ".net")
    notes = json.load(open(stem + ".board.json", encoding="utf-8"))
    placements = notes["placements"]

    missing = set(comps) - set(placements)
    if missing:
        # A part with no place is a part someone has to find a home for by hand,
        # which is exactly the drift this pipeline exists to prevent.
        raise SystemExit("no placement given for: %s" % ", ".join(sorted(missing)))

    board = pcbnew.CreateEmptyBoard()
    _rules(board, notes)
    # ⚠ THE PARTS THE ROUTER MUST NEVER SEE. A bare test pad on a rail that is already
    # routed needs no route -- it sits ON that rail's copper -- but handed to the router
    # BEFORE routing it is still an obstacle, and on the optical board six of them cost a
    # net in four consecutive runs: 2 unconnected, 2, 4, 2, always at the USB PHY, and
    # +3V3A failed even in the run where its own pad had been REMOVED. That region is
    # re-solved from scratch every run and only just succeeds, so the cost is not the
    # pad's area, it is the perturbation.
    #
    # So these are placed AFTER routing, by route.py's repair block, for exactly the
    # reason the SAI_FS repair and link_close_gaps are done there: "before routing the
    # same idea is a constraint that costs more than it buys." A pad that arrives after
    # the router has finished cannot change what the router did. It still has to pass
    # DRC, which is the check that matters and the one that is kept.
    #
    # They stay in the NETLIST and in the CAD -- this is a routing-order decision, not a
    # deletion -- so the fab, the geometry check and the pick-and-place all see them.
    post = set(notes.get("post_route_refs", ()))
    for ref, (fp_spec, value) in sorted(comps.items()):
        if ref in post:
            continue
        fp = _load_footprint(fp_spec)
        _grown = _grow_thin_rings(fp, int(notes.get("layers", 2)), notes)
        _legible_fields(fp)
        if _grown:
            print("  %s: %d plated pad(s) grown to the fab's minimum annular ring" % (ref, _grown))
        # LAND RESIZE: [(ref regex, x or None, y or None)] -- a stock footprint with its pads
        # resized in the footprint's own frame (None keeps that dimension). Kept as a board
        # note rather than a copied .kicad_mod, so the part stays KiCad's and only the one
        # number that had a reason to change does.
        for _pat, _sx, _sy in notes.get("land_resize", ()):
            if re.fullmatch(_pat, ref):
                for _pad in fp.Pads():
                    _sz = _pad.GetSize()
                    _pad.SetSize(pcbnew.VECTOR2I(
                        pcbnew.FromMM(_sx) if _sx is not None else _sz.x,
                        pcbnew.FromMM(_sy) if _sy is not None else _sz.y))
        board.Add(fp)
        fp.SetReference(ref)
        fp.SetValue(value)
        x, y, rot = placements[ref]
        # ⚠ FLIP BEFORE POSITIONING, NOT AFTER. A part named in back_refs sits on the
        # BOARD'S UNDERSIDE -- the pi_cap's 2x20 socket is the only one so far, and it has
        # to be, because that socket is what the board hangs off the Pi's header by: its
        # body occupies the standoff between the two boards, not the space above the cap.
        # KiCad's Flip mirrors about the point it is given, so flipping after SetPosition
        # would move the part as well as turn it over; flipping at the origin first leaves
        # the anchor routines below to place it exactly as they place anything else.
        # export_geom already reports side "B" for a flipped part and board_geom already
        # grows such a part DOWNWARD from the board, so nothing downstream needs teaching.
        if ref in notes.get("back_refs", ()):
            fp.Flip(fp.GetPosition(), False)
        fp.SetPosition(_to_board(x, y))
        fp.SetOrientationDegrees(rot)
        # WHICH POINT OF THE FOOTPRINT THE PLACEMENT NAMES. Everywhere but the optical
        # board it is the pad centroid, which is what elec/ reasons in; the optical
        # board's placements come from the CAD and name the courtyard centre instead.
        # See both anchor functions -- the difference is a couple of millimetres on
        # asymmetric parts and nothing at all on a two-pad passive, which is exactly
        # what makes it worth stating rather than inferring.
        if notes.get("anchor") == "courtyard":
            _anchor_on_courtyard(fp, _to_board(x, y))
        else:
            _anchor_on_pads(fp, _to_board(x, y))
        # The VALUE text is the part number, which is already on the assembly
        # drawing and the BOM; printed on a 22 mm board it only lands on top of
        # a pad or a neighbour's silk. Reference designators stay -- they are
        # what you read when probing the thing.
        fp.Value().SetVisible(False)
        if notes.get("refs_on_fab"):
            # DENSE BOARD: 29 designators will not fit on the silkscreen of a
            # 28 x 25 without landing on pads or each other, and JLCPCB places
            # from the CPL file, not from silk. Put them on F.Fab, which is the
            # assembly drawing, and leave the silkscreen clean. Boards with room
            # (the tee, the adapter) keep theirs on silk where a person can read
            # them while probing.
            fp.Reference().SetLayer(pcbnew.F_Fab)
        # ⚠ SILKSCREEN THAT LANDS ON A PAD IS NOT PRINTED -- the solder mask clips it --
        # so a footprint outline inside a deliberately tight cluster is ink the fab
        # cannot lay down and DRC has to complain about. The optical board's sensor
        # triplets are exactly that: an emitter between two detectors at a 1.6 pitch,
        # ten times over, producing 140 silk warnings on top of the 20 declared
        # courtyard overlaps. All 160 come from the same intended geometry.
        #
        # THE REASON TO STRIP IT IS NOT TIDINESS, IT IS LEGIBILITY. A DRC report with
        # 160 known-noise warnings is a report nobody reads, and that is how the seven
        # REAL violations from the routing pass hide in it. Nothing is lost: these parts
        # are machine-placed from the CPL, their designators are already on F.Fab, and
        # an outline printed under a component nobody can see once it is fitted was
        # never doing any work.
        # ⚠ MOVED TO F.Fab, NOT DELETED, and that is not a stylistic choice. Calling
        # fp.Remove() on a graphical item hands ownership back across the SWIG boundary
        # and pcbnew has no destructor for PCB_SHAPE: it leaks the shape AND leaves the
        # IO plugin in a state where the very next FootprintLoad raises
        # AttributeError on a SwigPyObject. Relocating the layer touches no ownership.
        # It is also the better answer -- the outline is not noise, it is just on the
        # wrong layer. F.Fab is the assembly drawing, which is exactly where a part
        # outline nobody can see once the part is fitted belongs.
        if any(ref.startswith(pre) for pre in notes.get("strip_silk", ())):
            for g in fp.GraphicalItems():
                if g.GetLayer() == pcbnew.F_SilkS:
                    g.SetLayer(pcbnew.F_Fab)
                elif g.GetLayer() == pcbnew.B_SilkS:
                    g.SetLayer(pcbnew.B_Fab)
        ref_pos = notes.get("ref_pos", {}).get(ref)
        if ref_pos:
            _place_ref(fp, _to_board(*ref_pos))

    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    # ⚠ SINGLE-PAD NETS ARE NOT GIVEN TO THE BOARD AT ALL. The netlist names every
    # deliberately-unconnected pin -- U6_NC_57, K1_UNUSED_7, DAC_OUT_R_NC -- because a
    # NAMED no-connect is a decision on the record and a silently floating pin is not.
    # That is right for the SCHEMATIC and wrong for the BOARD: a net with one pad on it
    # cannot be routed, has nothing to connect to, and its only effect downstream is to
    # occupy the autorouter's search space and the DRC report. On the optical board that
    # is 88 pads of 566 -- 16% of everything the router is asked to think about, all of
    # it work that cannot be done and does not need doing.
    #
    # Counted by PADS rather than matched by NAME on purpose: a naming convention is a
    # habit someone can break, whereas "one pad" is the actual property that makes a net
    # unroutable. It also catches the genuine mistake -- a net that was MEANT to connect
    # to something and does not -- and those show up in ERC, which is where they belong.
    skipped = 0
    # ⚠ AND A NET CAN BE POST-ROUTE AS WELL AS A PART. A pad on an already-routed rail
    # only needs the rail; a USART pin needs a NET that does not exist yet, and creating
    # it here would put it in the DSN -- so the router's input would stop being the input
    # that produced the route the pad's site was measured against. Named here, the pin
    # carries no net pre-route, which is exactly what it carried before as a declared
    # no-connect, and route.py builds the net over every node after routing.
    post_nets = set(notes.get("post_route_nets", ()))
    for name, nodes in nets.items():
        if name in post_nets:
            continue
        if len(nodes) < 2:
            skipped += 1
            continue
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        for ref, pad_no in nodes:
            if ref in post:
                continue        # placed after routing; route.py gives it this net
            # EVERY pad with that number, not the first: a USB-C's four shell tabs are all
            # "SH", and FindPadByNumber handed the net to one of them. The other three
            # (on both output-board USB-Cs) came out <no net> -- shell tabs soldered to
            # nothing, found in the routed board's own pad list.
            pads = [p for p in by_ref[ref].Pads() if p.GetNumber() == str(pad_no)]
            if not pads:
                raise SystemExit("%s has no pad %s" % (ref, pad_no))
            for pad in pads:
                pad.SetNet(net)

    # ⚠ ORDER MATTERS, AND IT IS PAIRS FIRST. Both routines lay copper and each
    # treats the other's as an obstacle, so whichever runs first gets the free board.
    # I had it the other way round on the argument that ground is 75 pads against the
    # pair's four -- and with 75 stitching vias already down, the pair could not find
    # room for a PAIRED escape anywhere and gave up entirely.
    #
    # The trade is not close once stated. A ground pad that misses its via still
    # reaches the plane through the pour and whatever the router lays; it is a
    # degraded connection, not an absent one. A differential pair that cannot escape
    # as a pair is not a differential pair at all, and nothing downstream recovers it.
    # So the pair goes first and the handful of ground pads it displaces are declared.
    for name, msg in _diff_pairs(board, notes.get("diff_pairs", ()),
                                 outline=_outline_pts(notes),
                                 inner=notes.get("diff_pair_inner")):
        print("  diff pair %s: %s" % (name, msg))

    stitch = set(notes.get("stitch_nets", ()))
    if stitch:
        n = _stitch_plane_pads(board, stitch, _outline_pts(notes),
                               allow=set(notes.get("stitch_exceptions", ())),
                               keepouts=notes.get("via_keepouts", ()),
                               escape_pins=set(notes.get("pin_escapes", ())),
                               escape_runs=notes.get("escape_runs"),
                               declared=notes.get("tracks", ()),
                               declared_vias=notes.get("vias", ()),
                               net_widths=notes.get("net_widths"))
        print("  stitched %d pad(s) on %s straight to the plane"
              % (n, "/".join(sorted(stitch))))


    # ⚠ AFTER THE STITCHING, WHICH REVERSES WHAT THIS COMMENT USED TO SAY. The first
    # ordering ran local nets before the stitcher on the argument that a via can go
    # almost anywhere and a track cannot. That was true when this routine laid 39
    # segments; at 85 on a 28 x 21 board it is not -- the local nets filled the space
    # around a QFN and the stitcher then had nowhere to put ONE ground via, which it
    # correctly refused to fake.
    #
    # The asymmetry that decides it is the same one that moved ground vias out of the
    # escape fan: a ground pad has exactly one destination, the plane directly beneath
    # it, and a via is the only way there. A local net has a whole board and an inner
    # layer to find a path through, and it SKIPS what it cannot lay rather than failing.
    # The routine with no alternative goes first.
    # ⚠ DECLARED COPPER GOES DOWN BEFORE ANYTHING SEARCHES, and it did not until
    # 2026-09-24. notes["tracks"] and notes["vias"] were added at the END of build, after
    # _local_nets and _comb_lanes had already run, so the two halves of the pre-lay were
    # laid BLIND AGAINST EACH OTHER: the spines could not be seen by the routines that
    # search, and they were then stamped down on top of whatever those routines had done.
    # Most of a day's collisions came out of that one ordering -- a +3V3A via landing on a
    # TIA_OUT_B run, a MID spine crossing V5_PRE's taps -- and each looked like a separate
    # geometry mistake.
    #
    # The order that makes sense is the one the stitcher already argued for two blocks up:
    # whatever has no alternative goes first. A declared spine has none -- it is a stated
    # decision about where a rail lives -- while _local_nets skips an edge it cannot lay
    # and _comb_lanes hands its run to the router. So: stitching, then declared copper,
    # then the searches, which now see it.
    nets_by_name = {n.GetNetname(): n for n in board.GetNetInfo().NetsByName().values()}
    for net_name, layer, width, pts in notes.get("tracks", []):
        _add_track(board, nets_by_name[net_name], layer, width, pts)
    for _ref in notes.get("edge_escape", ()):
        print("      %s: edge-side row fanned round its ends, %d way(s)"
              % (_ref, _edge_row_escape(board, _ref, _outline_pts(notes))))
    for _v in notes.get("vias", []):
        _net, _vx, _vy = _v[0], _v[1], _v[2]
        _drill = _v[3] if len(_v) > 3 else 0.3
        _dia = _v[4] if len(_v) > 4 else 0.6
        assert _net in nets_by_name, (
            "vias names net %r, which this board does not have" % _net)
        _add_via(board, nets_by_name[_net], _vx, _vy, _drill, _dia)
    if notes.get("vias"):
        print("      placed %d explicit via(s)" % len(notes["vias"]))

    if notes.get("local_nets"):
        # NOT `skipped` -- that name already holds the single-pad net count this
        # function reports at the end, and shadowing it made the summary line claim
        # 40 nets had appeared out of nowhere.
        n_laid, n_left, n_why, c_laid, c_why = _local_nets(
            board, notes["local_nets"], _outline_pts(notes),
            inner=_local_inner(notes), corridors=notes.get("corridors", ()),
            holes=_hole_pts(notes), local_mm=notes.get("local_mm", 6.0))
        print("  local nets: laid %d segment(s)%s"
              % (n_laid, ", %d left to the router" % n_left if n_left else ""))
        for _e in n_why:
            print("      not placeable: %s" % _e)
        if notes.get("corridors"):
            print("  corridor runs: %d of %d crossed on an assigned gap"
                  % (c_laid, len(notes["corridors"])))
            for _e in c_why:
                print("      corridor not placeable: %s" % _e)

    # ⚠ AFTER THE LOCAL CLUSTERS, BEFORE THE ROUTER. The clusters are three pads a couple
    # of millimetres apart in the tightest part of the strip and have almost no freedom;
    # the comb crossing has a whole lane and an inner layer. Same argument the retry got
    # below -- the routine with fewer alternatives goes first -- and it also means the
    # crossing sees the cluster copper it has to leave from as a real obstacle.
    if notes.get("comb_lanes", True) and notes.get("outline_slots"):
        _comb_lanes(board, notes)

    # ⚠ LOCAL NETS FIRST, RETRY SECOND, BY THE SAME ARGUMENT THE STITCHER GOT ABOVE: the
    # routine with fewer alternatives goes first. A local cluster is three pads a couple
    # of millimetres apart in the tightest part of the strip. A retried net is a long run
    # with a whole board and an inner layer to find a way through. Running the long one
    # first spends the strip's space on the part of the problem that did not need it.
    #
    # ⚠ AND THAT IS WHAT THE RETRY'S BAD REPUTATION ACTUALLY WAS. finish.py used to
    # explain its failure as "a net the router could not finish is usually one the
    # generator cannot finish either". Measured with the skipped edges NAMED rather than
    # counted, that is false: the retry lays its net, 8 segments, without trouble. What it
    # cost was everything laid after it -- local nets fell from 90 segments with nothing
    # skipped to 76 with EIGHTEEN skipped, all of them short cluster hops in the strip
    # that the long run had just cut across.
    # ⚠ NETS THE ROUTER ALREADY FAILED ON, handed back for a second attempt. finish.py
    # writes this file after a routing pass that left something unconnected, and the
    # difference from `local_nets` is the whole point: those are guessed in advance and
    # frozen whether the router needed help or not, while these are MEASURED -- the
    # router has been given its chance and demonstrably could not take it.
    #
    # That inverts the trade. Pre-laid copper costs the router freedom it can never
    # recover, so freezing nets it would have solved makes a board worse -- measured at
    # 2 -> 5 on output_panel and 4 -> 7 on lever_sensor. Freezing only the nets it just
    # failed costs it freedom on exactly the paths it was not using anyway.
    #
    # No span limit here: a failed net is laid however far it reaches, because the
    # alternative on offer is not laying it at all.
    retry = stem + ".retry.json"
    if os.path.isfile(retry):
        want = json.load(open(retry, encoding="utf-8"))
        if want:
            # ⚠ AT THE NET'S OWN WIDTH, NOT AT 0.2 (2026-10-01). This call used to take
            # _local_nets' default, so a net the board had asked to be 0.5 mm
            # (`net_widths`) came back from the retry at 0.2 -- and the nets the router
            # fails on are disproportionately the wide ones, because wide is what is hard
            # to fit. Found on output_panel (the buck's 24 V feed and its return, 30 and
            # 35 mm at 0.2) and motor_ctrl (67 mm of +24V at 0.2); DRC cannot see it, since
            # the netlist has no concept of width.
            # Widest first, each group at its width; whatever will not go at that width is
            # then tried at 0.2 and SAID, because a thin connection beats an open one and
            # a silent thin one is how this was missed.
            import fnmatch
            _nw = notes.get("net_widths") or {}
            _groups = {}
            for _n in want:
                _w = max([0.2] + [w for pat, w in _nw.items() if fnmatch.fnmatchcase(_n, pat)])
                _groups.setdefault(_w, []).append(_n)
            n_laid = n_left = 0
            n_why = []
            for _w in sorted(_groups, reverse=True):
                _pats = [re.escape(n) for n in _groups[_w]]
                _a, _b, _c, _cl, _cw = _local_nets(
                    board, _pats, _outline_pts(notes), local_mm=1e9, width=_w,
                    inner=_local_inner(notes), holes=_hole_pts(notes))
                n_laid += _a
                if _b and _w > 0.2:
                    _a2, _b, _c, _cl, _cw = _local_nets(
                        board, _pats, _outline_pts(notes), local_mm=1e9,
                        inner=_local_inner(notes), holes=_hole_pts(notes))
                    n_laid += _a2
                    print("  retry: ⚠ %d segment(s) of %s laid at 0.20 mm, not the %.2f mm "
                          "the board asks for -- no room at that width"
                          % (_a2, ", ".join(_groups[_w]), _w))
                n_left += _b
                n_why += list(_c)
            print("  retry: laid %d segment(s) for %d net(s) the router could not finish"
                  "%s" % (n_laid, len(want),
                          ", %d edge(s) still not placeable" % n_left if n_left else ""))
            for _e in n_why:
                print("      not placeable: %s" % _e)

    # outline_poly wins when present; outline_mm stays the LAYOUT REGION either way
    # (place_check and the zone filler both measure parts against it).
    if notes.get("outline_poly"):
        _edge_poly(board, [tuple(pt) for pt in notes["outline_poly"]])
    else:
        _edge_rect(board, *notes["outline_mm"])
    for h in notes.get("cutouts", ()):
        _cutout(board, h["xy"][0], h["xy"][1], h["d"])
        # "head_d": the screw HEAD (or washer, or standoff) that bears on the board round
        # this hole. Tracks and vias are kept out from under it -- solder mask is not
        # insulation against a steel head torqued down on a live track -- on the face it
        # bears on: "head_side" is "front" (default), "back" or "both". "head_margin"
        # (default 0.2) is added to the head's radius for the screw's play in its hole.
        if h.get("head_d"):
            _r = float(h["head_d"]) / 2.0 + float(h.get("head_margin", 0.2))
            _side = h.get("head_side", "front")
            _ls = pcbnew.LSET()
            if _side in ("front", "both"):
                _ls.AddLayer(pcbnew.F_Cu)
            if _side in ("back", "both"):
                _ls.AddLayer(pcbnew.B_Cu)
            _poly = pcbnew.SHAPE_LINE_CHAIN()
            for _i in range(32):
                _a = 2.0 * math.pi * _i / 32.0
                _poly.Append(_to_board(h["xy"][0] + _r * math.cos(_a), h["xy"][1] + _r * math.sin(_a)))
            _poly.SetClosed(True)
            _z = pcbnew.ZONE(board)
            _z.SetIsRuleArea(True)
            _z.SetDoNotAllowTracks(True)
            _z.SetDoNotAllowVias(True)
            _z.SetDoNotAllowZoneFills(True)
            _z.SetDoNotAllowPads(False)
            _z.SetLayerSet(_ls)
            _z.AddPolygon(_poly)
            board.Add(_z)
    for r in notes.get("outline_holes", ()):
        _edge_hole(board, *r)
    for sl in notes.get("outline_slots", ()):
        _edge_slot(board, [tuple(p) for p in sl["poly"]], sl["rects"])

    for net_name, layer, inset in notes.get("zones", []):
        _add_zone(board, nets_by_name[net_name], layer, inset, *notes["outline_mm"])
    if notes.get("zones"):
        # ⚠ BUILD THE CONNECTIVITY GRAPH FIRST. A board assembled by script has none --
        # it is built by the editor as you work, and nothing here was ever "worked on".
        # The zone filler uses it to decide which islands are attached to their net, so
        # without it EVERY island reads as unconnected and island removal discards the
        # lot. On an inner-layer plane that is invisible (one island, kept by luck); on
        # a pour fragmented by 153 parts it fills to exactly ZERO square millimetres,
        # and a zone that filled to nothing looks in the file just like one that
        # filled fine.
        board.BuildConnectivity()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        _check_stitches_landed(board, notes)

    n_junk = drop_degenerate(board)
    if n_junk:
        print("  dropped %d degenerate track fragment(s)" % n_junk)

    out = stem + ".kicad_pcb"
    # ⚠ KEEP THE LAST ROUTED BOARD BEFORE CLOBBERING IT (user, 2026-09-25: "whenever a
    # route completes it overwrites the file so my revert can grab it"). route.py already
    # saves the routed result back to THIS path, so the file is the right one to revert
    # to -- except between here and that save, where it is the bare placement. A route is
    # half an hour long, so that window is most of the time the user spends looking at
    # the board, and reverting into it shows an unrouted board that reads exactly like a
    # route that failed. Park the previous routed copy beside it rather than losing it:
    # a board with tracks is a result someone may still want, and regenerating one costs
    # the same half hour.
    if os.path.exists(out):
        try:
            _prev = pcbnew.LoadBoard(out)
            if any(t.GetClass() == "PCB_TRACK" for t in _prev.GetTracks()):
                shutil.copyfile(out, stem + ".lastrouted.kicad_pcb")
                print("  kept the previous routed board as %s.lastrouted.kicad_pcb"
                      % os.path.basename(stem))
        except Exception as _e:                    # an unreadable board is not worth failing over
            print("  could not preserve the previous board: %s" % _e)
    board.Save(out)
    _canonical_uuids(out)
    print("%s: %d parts, %d nets%s, %.1f x %.1f mm"
          % (os.path.basename(out), len(comps), len(nets) - skipped,
             (" (+%d single-pad, not placed)" % skipped) if skipped else "",
             *notes["outline_mm"]))
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__.strip().splitlines()[2].strip())
    build(os.path.abspath(sys.argv[1]))
