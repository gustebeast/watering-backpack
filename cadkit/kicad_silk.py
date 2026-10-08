"""Silkscreen a FINISHED KiCad board: its name and revision, what each test pad is, what
each connector pin carries. Run after routing, UNDER KiCad's OWN PYTHON, on the board
already on disk:

    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/kicad_silk.py elec/out/controller
    ... cadkit/kicad_silk.py --rev r2 --dark D,Q elec/out/sensor elec/out/panel
    ... cadkit/kicad_silk.py --refs all elec/out/breakout        # a designator per part

Run it BEFORE `cadkit/kicad_geom.py`: the exporter carries this lettering into the geom
file, and `cadkit.board_geom.Boards.silk()` draws it in the CAD as a part of its own.

WHY. A generated board tends to carry no board-level text at all: the designators go to
F.Fab on a dense board for a good reason (0402s at courtyard pitch leave no room, and an
assembly house places from the position file, not from ink), and three things go with
them that are NOT about placement:

  * WHICH BOARD IT IS, and which revision. Mirror-image boards are otherwise told apart
    by holding them up to each other; a re-order with changed copper cannot be told from
    the first at all.
  * WHICH BARE PAD IS WHICH. A bring-up guide says "probe SWCLK"; the board has to say
    which pad that is. A test pad (ref TP*) is labelled with its NET where that fits in
    ten characters, else its ref.
  * WHAT A JUMPER OR A CONTROL IS FOR. A solder jumper (ref JP*) is labelled with its
    value; `silk_labels` in the board's notes ({"SW1": "RESET"}) names anything else.
  * WHAT A CONNECTOR PIN CARRIES. Each connector (ref J<n>) of LEGEND_MAX_PINS or fewer
    gets its pinout printed -- on the back for choice, where the through-hole tails are.
  * ...AND WHICH WAY IS WHICH, FROM THE SIDE THE PLUG GOES IN. The block on the back is
    read with the board turned over, which is not how a lead gets plugged. So each of
    those connectors also gets ONE WORD PER WAY on its own side, in line with the way it
    names and all on one side of the row (at one distance where the board allows it,
    else each at its own nearest, no more than WAY_SPREAD apart), way 1's word led by
    a "1". Flat where a word is narrower than the pitch, turned to run away from the
    row where it is not (that turn is what puts each word against its own pin): the net's
    name where that fits, else its short word (`silk_short` in the board's notes,
    {"CAN_H": "H"}, over a built-in handful -- G, 24, 5V, 3V3, H, L). Only at the
    legible size, and all of a connector's ways or none: a row with one way unnamed
    reads as a row with one way unused. A connector whose row has no room for them is
    REPORTED ("ways"), and the block is tried on its side instead.
  * WHICH END IS WAY 1, ON EVERY CONNECTOR OF MORE THAN ONE WAY, whatever its size: where
    the words did not go down (or the part is over LEGEND_MAX_PINS and was never offered
    them) a bare "1" stands nearer way 1's pad than any other pad of the part, and where
    not even that fits, a dot. A SINGLE ROW over the limit, or any ref listed in
    `silk_ends`, has its LAST way numbered the same way ("20"): on a long row the far end
    is a long way from the "1". `silk_pinout` in the notes (["J2"]) prints the pinout
    block for a listed connector whatever its pin count -- two columns for a two-row
    header, odd ways left and even right, as the part has them.

  * WHICH PART IS WHICH, when the board asks for it. `silk_refs` in the board's notes
    (or `--refs`) prints each part's designator beside it: `true` / `all` for every part,
    or a list of reference prefixes (["U", "Q", "D", "SW"]). Off by default, because on
    a dense board most of them have no site and an assembly house places from the
    position file; ON for a board that is assembled, reworked or probed by hand. Parts
    with the most pads are given their sites first, a designator goes down only within
    REF_REACH of its own part (one that drifts beside a neighbour is worse than none)
    and only at the legible size, and the ones with no site are counted, not squeezed in.
    Like every other label these are board-level text, so the geom exporter carries them
    and `Boards.silk()` draws them in the CAD.

WHAT IT DOES NOT DO BY DEFAULT: put a designator beside every passive.

ONE READING DIRECTION PER BOARD. `silk_read` in the board's notes (0, 90, 180 or 270;
default 0) is the way the lettering reads -- set it to the way a person looks at the
board INSTALLED, not the way it sat in the layout. Everything this lays reads that way.
A QUARTER TURN from it (never a half turn, never the other quarter) is the LAST resort,
and only for a label that belongs to one place -- a test pad's net, a way's word, a
connector's pinout, a designator: first every site in reach at the reading direction,
then a wider ring in which the label is still nearer its own part than a rival's, then
(for a way's word) the short word; a label that is still homeless is turned, and each
one turned is LOGGED with what it is turned against. Text facing two ways because a
default site was taken is what this replaced: on four boards a third to a half of the
labels were turned, and none of them needed to be. The footprints' own designators are
brought round the same way: KiCad already draws them upright (0 or 90), and the ones
at 90 are laid flat where there is room for that beside the part.

EVERY LABEL IS SEARCHED FOR A FREE SITE AND DROPPED IF THERE IS NONE. A label is placed
only where its whole box clears every pad, hole, via, part and other label on that side,
and the board edge; one that cannot be placed is REPORTED, never squeezed in. So this
step cannot add a DRC finding and cannot move copper -- but "cannot" is a claim: run DRC
before and after and compare.

`--dark P1,P2`: reference PREFIXES of parts no ink may come near (optical sensors on a
board ordered in black mask to keep stray light down).
Without it, a `<stem>.board.json` beside the board supplies
them from its "strip_silk" list (what a pcbflow-generated board carries). The same notes
supply `silk_rev` (the revision, when `--rev` is not given), `silk_refs`, `silk_labels`
and `silk_name`.

`silk_words` in the same notes: `[(text, x, y, "front" | "back"), ...]`, words that belong
to a PLACE rather than to a part's pad -- what a socket is for, a warning beside an inlet.
x, y are the centre of the site in the BOARD FILE's millimetres (what the editor's cursor
and a DRC report give). They are laid LAST, so they move nothing else, at the free site
nearest the point and no further than WORD_REACH from it; one with no site there is
reported like any other label and never squeezed in.

IDEMPOTENT: it deletes the board-level silkscreen text it finds first and lays the set
again. The board's NAME is the stem's basename, upper-cased, underscores as spaces.
"""
from __future__ import annotations

import os
import sys

import pcbnew  # noqa: E402
import wx  # noqa: E402

wx.DisableAsserts()

REV = "r1"                 # the default; bump it when a board is RE-ORDERED with changed copper
MM = pcbnew.FromMM
PAD_CLR = 0.20             # label box <-> any pad's mask opening
EDGE_CLR = 0.40            # label box <-> board edge or cutout
STROKE = 0.15              # a common fab minimum silkscreen line (JLCPCB's)
SIZES_ID = (1.5, 1.2, 1.0, 0.8)
SIZE_TP = 1.0             # 1.0 is the fab's stated minimum legible height (quality A12)
SIZE_J = 1.0
# 1.0 mm is the height the fab calls legible; 0.8 is what is tried when a label has no site
# at 1.0 ANYWHERE in reach. A small label beats no label (which of two mirror-image boards
# is this?), but it is reported, and the quality pass (A12) makes someone sign for it.
SIZE_SMALL = 0.8
LEGEND_MAX_PINS = 8        # a 2x20 gets its name only
# how far from its connector a pinout block may be laid. The block names its connector
# and lists the ways in order, so it still reads from further off (`silk_pinout_reach`);
# the nearest free site is taken first whatever the reach.
PINOUT_REACH = 14.0
OPTICS_CLR = 12.0          # no label this close to a part whose own silk was stripped
OPTICS_NAME_CLR = 30.0     # ...and the board's name, which can go anywhere, further still
SIZE_REF = 1.0             # a designator is printed legibly or not at all
REF_REACH = 2.0            # mm past the part's own half-diagonal: beside it, or nowhere
REF_SKIP = ("TP", "H", "MH", "FID", "REF", "G", "LOGO")   # no part there to name

# ── THE FACE (`silk_font`) ───────────────────────────────────────────────────
# None = KiCad's own stroke font, and every size above. A board (or its project, through
# the `face` argument of silk()) may ask for an INSTALLED outline font instead:
#
#     "silk_font": {"family": "Some Family", "bold": true, "size": 1.5}
#
# ⚠ ONE SIZE, AND NO SMALLER FALLBACK. An outline font's strokes are a fixed fraction of
# its height, so "try it at 0.8" is not a smaller legible label, it is an unprintable
# one: `size` is the height at which the face's THINNEST stroke reaches the fab's
# minimum, and it is the caller's to have measured (KiCad's text size is not the cap
# height either -- measure the plotted ink, not the font's tables).
# ⚠ KICAD FALLS BACK SILENTLY. A family it cannot find (not installed for this user) is
# drawn in a substitute face with no error and no warning, so _set_face proves the family
# resolved before any label is placed, by drawing in it and in a name that cannot exist.
# A missing family STOPS the run, unless the face says `"fallback": true`: then the board
# is lettered in the stroke font at the stroke font's sizes, and the run says so loudly.
FACE = None
FACE_MISSING = None        # the family a `fallback` face asked for and KiCad did not have


def _apply_face(t, board):
    if FACE:
        t.SetBold(bool(FACE.get("bold")))
        t.SetUnresolvedFontName(FACE["family"])
        t.ResolveFont(board.GetEmbeddedFonts())
    return t


def _set_face(face, board):
    """Take `face` for this run: the sizes, and proof that KiCad found the family."""
    global FACE, FACE_MISSING, SIZE_TP, SIZE_J, SIZE_SMALL, SIZE_REF, SIZES_ID
    if not face:
        return
    size = float(face["size"])

    def width(family, s="HIJ+-_024"):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
        t.SetBold(bool(face.get("bold")))
        t.SetUnresolvedFontName(family)
        t.ResolveFont(board.GetEmbeddedFonts())
        return t.GetBoundingBox().GetWidth()
    if width(face["family"]) == width("no such family \x7f%s" % face["family"]):
        if face.get("fallback"):
            # the project would rather have a board in KiCad's own stroke font than no
            # board (someone who cloned it and cannot have the face). Said, never silent;
            # FACE stays None, so every size above is the stroke font's own again.
            FACE_MISSING = face["family"]
            print("  !! kicad_silk: the font family %r is NOT INSTALLED for this user. "
                  "Lettering this board in KiCad's stroke font instead (silk_font "
                  "fallback): it is a correct board, but NOT the one the project orders "
                  "-- labels sit and size differently. Install the family and re-run "
                  "for the project's own silk." % face["family"])
            return
        raise SystemExit("kicad_silk: the font family %r is not installed for this user -- "
                         "KiCad would draw a substitute face without saying so. Install "
                         "it (per-user is enough) and re-run" % face["family"])
    if not face.get("glyphs"):
        raise SystemExit("kicad_silk: the face %r declares no `glyphs` -- the characters "
                         "someone has looked at, drawn, in this font. A display face puts "
                         "ornaments on ordinary code points ('+' drawn as a TH ligature "
                         "has been printed); list what was checked" % face["family"])
    # ...and the INSTALLED file is the one that was looked at. A face that had a glyph
    # redrawn keeps its family name, so a machine with the older file still resolves it
    # and still prints the ornament: `widths` gives, for a redrawn character, its advance
    # as a fraction of another's ({"+/H": 0.97}), measured off the file that was checked.
    for pair, want in (face.get("widths") or {}).items():
        a, b = pair.split("/")
        got = width(face["family"], a * 20) / float(width(face["family"], b * 20))
        if abs(got - want) > 0.05 * want:
            raise SystemExit("kicad_silk: the installed %r is not the file its `glyphs` "
                             "were verified in: %r is %.2f of %r wide, and %.2f in the "
                             "checked file. Install the current font file and re-run"
                             % (face["family"], a, got, b, want))
    FACE = dict(face)
    SIZE_TP = SIZE_J = SIZE_SMALL = SIZE_REF = size
    SIZES_ID = tuple(z for z in SIZES_ID if z >= size) or (size,)


def _outline(t):
    return bool(t.GetFontName())          # the stroke font has no name


# ── WHAT A FACE MAY PRINT (`glyphs`) ─────────────────────────────────────────
# ⚠ A GLYPH BEING IN THE FONT DOES NOT MEAN IT DRAWS THE CHARACTER. A display face fills
# ordinary code points with ornaments: the one this was written for draws "+" as a TH
# ligature, so "+5V" plotted, legibly and at full size, as "TH5V" on five boards, and
# every check passed -- the text object still said "+5V". A character table cannot see
# that; only someone looking at the drawn glyph can. So a face carries `glyphs`, the
# characters its owner has LOOKED AT, and a text that needs any other stops the run.
def unverified_glyphs(board, glyphs):
    """[(text, characters)] for every printed silk text in an outline font that uses a
    character outside `glyphs`. Space and newline are never ink."""
    ok = set(glyphs or "") | {" ", chr(10)}
    out = []
    texts = [d for d in board.GetDrawings() if d.GetClass() == "PCB_TEXT"]
    texts += [f for fp in board.GetFootprints() for f in fp.GetFields() if f.IsVisible()]
    for t in texts:
        if t.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) and _outline(t):
            bad = sorted(set(t.GetText()) - ok)
            if bad:
                out.append((t.GetText().split(chr(10))[0], "".join(bad)))
    return out


# ── A LIST BESIDE A ROW OF PINS IS READ AS LABELS FOR THOSE PINS ─────────────
# ⚠ A pinout block is a LIST: its head names the connector and its lines are numbered.
# Laid with its lines stepping ALONG a connector's pad row and close to it, it stops
# being read as a list: each line sits under a pin and is taken for that pin's label,
# and at a line pitch near the connector's every one of them is the WRONG pin ("1 GND"
# under the 24 V way of a power connector). So within REGISTER_NEAR of any connector's
# pads a block may only lie ACROSS the row -- lines stepping away from it -- which nobody
# reads pin by pin. A word per way (_ways) is the registered form and is laid elsewhere.
REGISTER_NEAR = 3.0
REGISTER_UNDER = 8.0       # ...and this far, for a block stepping along the row beneath it


def _rows(board, back):
    """(ref, pad box, 'x' or 'y', body) for each connector's pads present on this side;
    `body` is its courtyard where the part itself is on this side, else None."""
    cu = pcbnew.B_Cu if back else pcbnew.F_Cu
    out = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not (ref.startswith("J") and ref[1:].isdigit()):
            continue
        bs = [_box(q) for q in fp.Pads() if q.GetNumber().isdigit() and q.IsOnLayer(cu)]
        if len(bs) < 2:
            continue
        b = [min(q[0] for q in bs), min(q[1] for q in bs),
             max(q[2] for q in bs), max(q[3] for q in bs)]
        body = None
        if fp.IsFlipped() == back:
            c = _rect(fp.GetCourtyard(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd).BBox())
            if c[2] > c[0] and c[3] > c[1]:
                body = c
        out.append((ref, b, "x" if b[2] - b[0] >= b[3] - b[1] else "y", body))
    return out


def _misread(r, ang, rows, own=None):
    """The connector whose pins a block at `r`, reading at `ang`, would be read against,
    or None. `own` is the block's connector: ANOTHER connector's pads or body that close
    are refused outright -- a list hard against J3 is J3's to the eye, whatever its head
    says (J4's went down in the corner beside J3's mounting pad)."""
    steps = "y" if round(ang) % 180 == 0 else "x"       # the way its lines step
    for ref, b, axis, body in rows:
        g = _gap(r, b)
        if g < MM(REGISTER_NEAR) and (axis == steps or (own and ref != own)):
            return ref
        if own and ref != own and body and _gap(r, body) < MM(REGISTER_NEAR):
            return ref
        # ...and further off than that while it is still UNDER the row: lines stepping
        # along the pins, across the pins' own span, are matched to them by eye from a
        # good deal more than 3 mm (off the END of the row they are not)
        k = 0 if axis == "x" else 1
        if axis == steps and g < MM(REGISTER_UNDER) and min(r[k + 2], b[k + 2]) > max(r[k], b[k]):
            return ref
    return None


def misregistered(board):
    """[(block's connector, the connector it reads against)] over the printed pinout
    blocks of a board: the check a quality pass makes of what the labeller laid."""
    out = []
    rows = {False: _rows(board, False), True: _rows(board, True)}
    for d in board.GetDrawings():
        if d.GetClass() != "PCB_TEXT" or d.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            continue
        lines = d.GetText().split(chr(10))
        if len(lines) < 3 or not (lines[0].startswith("J") and lines[0][1:].isdigit()):
            continue
        hit = _misread(_box(d), d.GetTextAngleDegrees(),
                       rows[d.GetLayer() == pcbnew.B_SilkS], lines[0])
        if hit:
            out.append((lines[0], hit))
    return out


def _face_refs(board):
    """The footprints' own designators, where they print, in the face and at its size."""
    n = 0
    if FACE_MISSING:
        # a board lettered in the face on another machine still NAMES it on every
        # designator, and KiCad would substitute for each one silently: back to stroke
        for fp in board.GetFootprints():
            for f in fp.GetFields():
                if f.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) and _outline(f):
                    f.SetFont(None)
                    f.SetBold(False)
                    f.SetTextSize(pcbnew.VECTOR2I(MM(SIZE_REF), MM(SIZE_REF)))
                    f.SetTextThickness(MM(STROKE))
                    n += 1
        return n
    if not FACE:
        return 0
    for fp in board.GetFootprints():
        for f in fp.GetFields():
            if f.IsVisible() and f.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                f.SetTextSize(pcbnew.VECTOR2I(MM(SIZE_REF), MM(SIZE_REF)))
                f.SetTextThickness(MM(STROKE))
                _apply_face(f, board)
                n += 1
    return n
LINE_GAP = 0.8             # mm kept clear before and after a label, along its line
WIDER = 1.6                # the second ring: this much further out, before any turn
MARK_D = 0.6               # a way-1 DOT, where not even a "1" fits: four fab line widths
REF_SLIDE = 2.5            # mm a footprint's own designator may move to lie flat


def _box(item):
    b = item.GetBoundingBox()
    return [b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()]


def _ink(t):
    """The box of a text's INK, where _box is the box of its line: an outline face
    reserves room over and under the capitals for accents and descenders (2.31 mm of
    line for 1.45 mm of ink at size 1.5), and a row of words a pitch apart is judged on
    what prints."""
    if not _outline(t):
        return _box(t)
    try:
        ps = pcbnew.SHAPE_POLY_SET()
        t.TransformTextToPolySet(ps, 0, MM(0.005), pcbnew.ERROR_INSIDE)
        b = ps.BBox()
        if b.GetWidth() > 0 and b.GetHeight() > 0:
            return [b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()]
    except Exception:                                       # noqa: BLE001
        pass
    return _box(t)


def _grow(r, d):
    return [r[0] - d, r[1] - d, r[2] + d, r[3] + d]


def _rect(b):
    return [b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()]


def _gap(a, b):
    """Distance between two rects (0 if they touch or overlap)."""
    dx = max(a[0] - b[2], b[0] - a[2], 0)
    dy = max(a[1] - b[3], b[1] - a[3], 0)
    return (dx * dx + dy * dy) ** 0.5


def _hit(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class Side:
    """Everything a label on one side of the board has to stay off."""

    def __init__(self, board, back, dark=(), read=0.0):
        self.small = []          # labels that only fitted under the legible size
        self.read = read % 360.0 # the board's reading direction (`silk_read`)
        self.turned = []         # (label, why) for each one laid a quarter turn off it
        self.board, self.back = board, back
        self.layer = pcbnew.B_SilkS if back else pcbnew.F_SilkS
        cu = pcbnew.B_Cu if back else pcbnew.F_Cu
        self.rects, self.dark = [], []
        for fp in board.GetFootprints():
            same = fp.IsFlipped() == back
            # NO INK NEAR THE OPTICS. A board that strips its sensors' own outlines
            # (strip_silk) and is ordered in black mask to keep stray light down does not
            # then get white lettering beside the same sensors.
            if same and any(fp.GetReference().startswith(q) for q in dark):
                self.dark += [_box(pad) for pad in fp.Pads()]
            for pad in fp.Pads():
                if pad.IsOnLayer(cu) or pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH,
                                                               pcbnew.PAD_ATTRIB_NPTH):
                    self.rects.append(_grow(_box(pad), MM(PAD_CLR)))
            if same:
                # the part's own body: ink under a fitted part is ink nobody reads
                # ...which a bare test pad does not have. Its courtyard is a 2 mm square
                # round a 1 mm pad with nothing fitted on it, and treating that as a body
                # pushed every name half a millimetre further off than the pad needs --
                # on a row of pads at 2.4 mm that left no site beside any of them, and the
                # names went down beside each other's pads instead. The pad itself (and
                # its clearance) is already in the list above.
                cy = fp.GetCourtyard(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd)
                if cy.OutlineCount() and not fp.GetReference().startswith("TP"):
                    b = cy.BBox()
                    self.rects.append([b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()])
                for g in fp.GraphicalItems():
                    if g.GetLayer() == self.layer:
                        self.rects.append(_box(g))
                if fp.Reference().IsVisible() and fp.Reference().GetLayer() == self.layer:
                    self.rects.append(_box(fp.Reference()))
        # A via HOLE swallows ink, so a label keeps off it -- unless the via is tented on
        # this side, where the hole is under mask and a stroke across it prints. Ask the
        # via (KiCad's board default is tented, and a fab follows the mask layer it is
        # sent). On a board a few centimetres square this decides whether a name stands
        # beside its own pad or its neighbour's: the router scatters vias differently
        # every run, and the nearest site clear of all of them was not reliably the
        # adjacent one -- lever_sensor's DIO went down under the CLK pad.
        mask = pcbnew.B_Mask if back else pcbnew.F_Mask
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA" and t.IsTented(mask):
                continue
            if t.GetClass() == "PCB_VIA":
                p, r = t.GetPosition(), t.GetDrillValue() // 2 + MM(0.1)
                self.rects.append([p.x - r, p.y - r, p.x + r, p.y + r])
        self.outline = pcbnew.SHAPE_POLY_SET()
        board.GetBoardPolygonOutlines(self.outline, False)
        # A HOLE WHOLLY INSIDE A LABEL'S BOX is invisible to inside(), which walks the
        # box's perimeter: the first run printed a board's name straight across its
        # mounting hole. Every cutout is an obstacle in its own right.
        for o in range(self.outline.OutlineCount()):
            for h in range(self.outline.HoleCount(o)):
                hb = self.outline.Hole(o, h).BBox()
                self.rects.append(_grow([hb.GetLeft(), hb.GetTop(), hb.GetRight(),
                                         hb.GetBottom()], MM(EDGE_CLR)))
        e = board.GetBoardEdgesBoundingBox()
        self.bbox = [e.GetLeft(), e.GetTop(), e.GetRight(), e.GetBottom()]

    def inside(self, r):
        """The whole box is board, EDGE_CLR from any edge or cutout. Sampled round the
        grown box's perimeter, because a slot can cross a box whose corners are all on
        laminate."""
        g = _grow(r, MM(EDGE_CLR))
        n = max(2, int((g[2] - g[0] + g[3] - g[1]) / MM(0.4)))
        for k in range(n + 1):
            x = g[0] + (g[2] - g[0]) * k // n
            y = g[1] + (g[3] - g[1]) * k // n
            for px, py in ((x, g[1]), (x, g[3]), (g[0], y), (g[2], y)):
                if not self.outline.Contains(pcbnew.VECTOR2I(int(px), int(py))):
                    return False
        cx, cy = (g[0] + g[2]) // 2, (g[1] + g[3]) // 2
        return self.outline.Contains(pcbnew.VECTOR2I(int(cx), int(cy)))

    def free(self, r, optics=None):
        g = _grow(r, MM(OPTICS_CLR if optics is None else optics))
        return (not any(_hit(g, o) for o in self.dark)
                and not any(_hit(r, o) for o in self.rects) and self.inside(r))

    def text(self, s, size, angle=0.0):
        t = pcbnew.PCB_TEXT(self.board)
        t.SetText(s)
        t.SetLayer(self.layer)
        t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
        t.SetTextThickness(MM(STROKE))
        _apply_face(t, self.board)
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        t.SetMirrored(self.back)
        t.SetKeepUpright(False)           # the angle asked for IS the angle printed
        t.SetTextAngleDegrees(angle)
        t.SetPosition(pcbnew.VECTOR2I(0, 0))
        return t

    def dot(self, near, reach, rivals):
        """A filled dot MARK_D across at the free site nearest `near` and nearer it than
        any of `rivals`. Returns True if it went down. Recognised (and cleared) on the
        next run by being a filled board-level silkscreen circle of exactly this size."""
        h = MM(MARK_D) // 2
        n = int(reach / 0.25)
        best = None
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                d2 = i * i + j * j
                if d2 > n * n or (best is not None and d2 >= best[0]):
                    continue
                x, y = near.x + MM(i * 0.25), near.y + MM(j * 0.25)
                if any((x - q.x) ** 2 + (y - q.y) ** 2
                       < (x - near.x) ** 2 + (y - near.y) ** 2 for q in rivals):
                    continue
                r = [x - h, y - h, x + h, y + h]
                if self.free(r):
                    best = (d2, x, y, r)
        if best is None:
            return False
        c = pcbnew.PCB_SHAPE(self.board, pcbnew.SHAPE_T_CIRCLE)
        c.SetLayer(self.layer)
        c.SetCenter(pcbnew.VECTOR2I(int(best[1]), int(best[2])))
        c.SetEnd(pcbnew.VECTOR2I(int(best[1]) + h, int(best[2])))
        c.SetFilled(True)
        c.SetWidth(0)
        self.board.Add(c)
        self.rects.append(_grow(best[3], MM(0.15)))
        return True

    def place_legible(self, s, size, near, reach, **kw):
        """`place` at `size`, else at SIZE_SMALL. Returns the size used, or 0."""
        for z in (size, SIZE_SMALL):
            if z <= size and self.place(s, z, near, reach, **kw):
                if z < size:
                    self.small.append(s.split(chr(10))[0])
                return z
        return 0

    def _nearest(self, s, size, ang, near, reach, step, optics, rivals=None, inner=0.0,
                 ok=None, okang=None):
        """The free site nearest `near` for `s` at `ang`, within `reach` mm (and outside
        `inner`): (d2, x, y, box) or None. With `rivals` (points), only a site nearer to
        `near` than to any of them counts -- a label out there is read as belonging to
        whatever it is closest to."""
        t = self.text(s, size, ang)
        b = _box(t)                                   # about the origin
        n = int(reach / step)
        lo = (inner / step) ** 2
        best = None
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                d2 = i * i + j * j
                if d2 > n * n or d2 <= lo or (best is not None and d2 >= best[0]):
                    continue
                x, y = near.x + MM(i * step), near.y + MM(j * step)
                if rivals and any((x - q.x) ** 2 + (y - q.y) ** 2
                                  < (x - near.x) ** 2 + (y - near.y) ** 2 for q in rivals):
                    continue
                r = [b[0] + x, b[1] + y, b[2] + x, b[3] + y]
                if ok is not None and not ok(r):
                    continue
                if okang is not None and not okang(r, ang):
                    continue
                if self.free(r, optics):
                    best = (d2, x, y, r)
        return best

    def place(self, s, size, near, reach, step=0.25, optics=None, turn=None,
              rivals=None, wider=True, own=False, ok=None, okang=None):
        """Lay `s` at the free site nearest `near` (a VECTOR2I), no further than `reach`
        mm, at the board's reading direction. Returns True if it went down.

        Tried in this order, and the first that has a site wins: the reading direction
        within `reach`; the reading direction in a WIDER ring (unless `wider=False`),
        where the site must still be nearer `near` than any of `rivals`; and, only for
        a label given a `turn` reason -- what it belongs beside -- a quarter turn within
        `reach`. A label with no `turn` is never turned: its default site being taken is
        not a reason. `own=True` holds EVERY ring to the rivals rule, for a mark that
        means nothing unless it is nearest its own pad (a way-1 mark)."""
        ang = self.read
        close = rivals if own else None
        best = self._nearest(s, size, ang, near, reach, step, optics, rivals=close, ok=ok,
                             okang=okang)
        if best is None and wider:
            best = self._nearest(s, size, ang, near, reach * WIDER, step, optics,
                                 rivals=rivals, inner=reach, ok=ok, okang=okang)
        if best is None and turn:
            ang = (self.read + 90.0) % 360.0
            best = self._nearest(s, size, ang, near, reach, step, optics, rivals=close,
                                 ok=ok, okang=okang)
            if best is not None:
                self.turned.append((s.split(chr(10))[0], turn))
        if best is None:
            return False
        t = self.text(s, size, ang)
        t.SetPosition(pcbnew.VECTOR2I(int(best[1]), int(best[2])))
        self.board.Add(t)
        # ...and a WORD SPACE kept clear along its line: two labels end to end at 0.15
        # are one phrase ("NRST" ran straight into the board's name)
        r = _grow(best[3], MM(0.15))
        k = 0 if round(ang) % 180 == 0 else 1
        r[k] -= MM(LINE_GAP)
        r[k + 2] += MM(LINE_GAP)
        self.rects.append(r)
        return True


# A net's short word for a per-way label, where the board's notes give none. Matched in
# order against the net's name; the first that fits wins.
SHORT = (("GND", "G"), ("+24V", "24"), ("V24", "24"), ("+12V", "12"), ("+5V", "5V"),
         ("V5", "5V"), ("+3V3", "3V3"), ("VBUS", "5V"))
WAY_REACH = 9.0            # mm from the pad row to the near end of a way's word
WAY_GAP = 0.5              # ...and the nearest it starts
WAY_SPREAD = 5.0           # how far apart a row's words may start, where they cannot line up


def _short(net, given):
    """The short word for `net`: the board's own, a supply's, a bus line's last letter
    (CAN_H / CANA_L -> H / L), else what follows its last underscore, to four letters."""
    if net in given:
        return given[net]
    for head, word in SHORT:
        if net.upper().startswith(head):
            return word
    tail = net.rsplit("_", 1)[-1].lstrip("+")
    return tail[:4] if tail else net[:4]


def _ways(side, fp, pins, forms):
    """One word per way on `side`, in line with each pad, or nothing. `pins` is
    {number: pad}; `forms` is [{number: text}], the fullest wording first. Returns True
    if the whole row went down.

    The row has to be a ROW: its pads on one line along X or Y. The words all go on one
    side of it. They start the same distance out where there is such a distance -- the
    nearest, on either side, at which every one is free. On a board too full for that
    each starts at its own nearest free distance, as long as the row's words stay
    within WAY_SPREAD of each other: in line with its way a word is still that way's,
    but one that has wandered a centimetre past its neighbours is beside something else.

    FLAT BEFORE TURNED. At the board's reading direction a word's LENGTH lies along
    one axis; where that is across the row, or the word is narrower than the pitch, it
    goes down flat. Every wording is tried flat before any is turned, so a short word
    read the right way up beats a long one on its side; the quarter turn (the word
    running away from the row) is what is left for a pitch too fine for even the short
    words, and it is logged as what it is: each word against its own pin.
    A connector of ONE way gets its word at the nearest free site beside the pad."""
    nums = sorted(pins)
    pos = [pins[k].GetPosition() for k in nums]
    xs, ys = [q.x for q in pos], [q.y for q in pos]
    if len(nums) == 1:
        # every wording flat before any is turned
        return (any(side.place(f[nums[0]], SIZE_J, pos[0], 5.0) for f in forms)
                or any(side.place(f[nums[0]], SIZE_J, pos[0], 5.0, wider=False,
                                  turn="beside its own pad") for f in forms))
    if max(ys) - min(ys) < MM(0.05):
        along_x = True
    elif max(xs) - min(xs) < MM(0.05):
        along_x = False
    else:
        return False                      # two rows, a ring, a diagonal: the block's job
    line = xs if along_x else ys
    pitch = min(abs(line[i + 1] - line[i]) for i in range(len(nums) - 1))
    steps = [WAY_GAP + 0.25 * i for i in range(int((WAY_REACH - WAY_GAP) / 0.25) + 1)]

    def lay(words, ang):
        texts = [side.text(words[k], SIZE_J, ang) for k in nums]
        boxes = [_ink(x) for x in texts]      # about the origin
        # across the pitch each word needs its own width and a gap to the next
        if max((b[2] - b[0]) if along_x else (b[3] - b[1]) for b in boxes) > pitch - MM(0.2):
            return None

        def site(q, b, sgn, d, taken):
            half = (b[3] - b[1]) / 2.0 if along_x else (b[2] - b[0]) / 2.0
            off = int(sgn * (MM(d) + half))
            x, y = (q.x, q.y + off) if along_x else (q.x + off, q.y)
            r = [b[0] + x, b[1] + y, b[2] + x, b[3] + y]
            if not side.free(r) or any(_hit(r, o[2]) for o in taken):
                return None
            return (x, y, r)

        best = None
        for sgn in (1, -1):                   # 1. one distance for the whole row
            for d in steps:
                if best is not None and d >= best[0]:
                    break
                sites = []
                for q, b in zip(pos, boxes):
                    s_ = site(q, b, sgn, d, sites)
                    if s_ is None:
                        break
                    sites.append(s_)
                else:
                    best = (d, sites)
                    break
        if best is None:
            for sgn in (1, -1):               # 2. each its own, the row kept together
                sites, ds = [], []
                for q, b in zip(pos, boxes):
                    for d in steps:
                        s_ = site(q, b, sgn, d, sites)
                        if s_ is not None:
                            sites.append(s_)
                            ds.append(d)
                            break
                    else:
                        break
                if len(sites) == len(pos) and max(ds) - min(ds) <= WAY_SPREAD and (
                        best is None or max(ds) < best[0]):
                    best = (max(ds), sites)
        return None if best is None else (texts, best[1])

    flat, turned = side.read, (side.read + 90.0) % 360.0
    for ang in (flat, turned):
        for words in forms:
            got = lay(words, ang)
            if got is None:
                continue
            for x_, (x, y, r) in zip(*got):
                x_.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
                side.board.Add(x_)
                side.rects.append(_grow(r, MM(0.15)))
            if ang != flat:
                side.turned.append(("%s ways" % fp.GetReference(),
                                    "each word against its own pin: at %.2f mm pitch "
                                    "none fits flat" % (pitch / 1e6)))
            return True
    return False


def _flatten_refs(board, read):
    """Bring each footprint's own designator, where it prints, to the reading direction.

    KiCad draws a footprint's text "upright": whatever the part's rotation, at 0 or 90.
    So nothing prints upside down -- but a part laid at 90 or 270 has its designator on
    its side, and a board read from another edge (`silk_read`) has all of them facing
    the layout's way. Each is turned to the reading direction where its box, there or
    within REF_SLIDE of there, is clear of every pad, part and other designator; one
    with no such site keeps a quarter turn and is returned as (ref, why)."""
    read = read % 360.0
    quarter = (read + 90.0) % 360.0
    refs = [fp for fp in board.GetFootprints()
            if fp.Reference().IsVisible()
            and fp.Reference().GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
    kept = []
    for fp in sorted(refs, key=lambda f: f.GetReference()):
        r = fp.Reference()
        back = r.GetLayer() == pcbnew.B_SilkS
        cu = pcbnew.B_Cu if back else pcbnew.F_Cu
        drawn = r.GetDrawRotation().AsDegrees() % 360.0
        if abs(drawn - read) < 0.5:
            r.SetKeepUpright(False)
            r.SetTextAngleDegrees(read)
            continue
        if abs(abs(drawn - read) - 180.0) < 0.5:
            # a HALF turn: the same box, the other way up. Turned about the box's own
            # centre it covers exactly what it covered, so there is nothing to search
            # for and nothing new it can touch.
            was_c = r.GetBoundingBox().GetCenter()
            r.SetKeepUpright(False)
            r.SetTextAngleDegrees(read)
            now_c = r.GetBoundingBox().GetCenter()
            q = r.GetPosition()
            r.SetPosition(pcbnew.VECTOR2I(int(q.x + was_c.x - now_c.x),
                                          int(q.y + was_c.y - now_c.y)))
            continue
        rects = []
        for o in board.GetFootprints():
            for pad in o.Pads():
                if pad.IsOnLayer(cu) or pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH,
                                                               pcbnew.PAD_ATTRIB_NPTH):
                    rects.append(_grow(_box(pad), MM(PAD_CLR)))
            # ...and every OTHER part's body. Not its own: a designator laid inside its
            # own part's courtyard (a connector's, between its rows) was put there by the
            # layout and prints; what it must not do is land under a neighbour.
            if o.IsFlipped() == back and o.GetReference() != fp.GetReference():
                cy = o.GetCourtyard(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd)
                if cy.OutlineCount():
                    b = cy.BBox()
                    rects.append([b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()])
            if o is not fp and o.GetReference() != fp.GetReference():
                q = o.Reference()
                if q.IsVisible() and q.GetLayer() == r.GetLayer():
                    rects.append(_grow(_box(q), MM(0.1)))
        e = board.GetBoardEdgesBoundingBox()
        edge = _grow([e.GetLeft(), e.GetTop(), e.GetRight(), e.GetBottom()], -MM(EDGE_CLR))
        was = (r.GetTextAngleDegrees(), r.IsKeepUpright(), r.GetPosition())
        home = r.GetPosition()
        stood = _box(r)                   # what it covers as it stands
        mid = r.GetBoundingBox().GetCenter()
        r.SetKeepUpright(False)
        r.SetTextAngleDegrees(read)
        r.SetPosition(pcbnew.VECTOR2I(0, 0))
        b = _box(r)
        n = int(REF_SLIDE / 0.25)
        best = None
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                d2 = i * i + j * j
                if d2 > n * n or (best is not None and d2 >= best[0]):
                    continue
                x, y = home.x + MM(i * 0.25), home.y + MM(j * 0.25)
                box = [b[0] + x, b[1] + y, b[2] + x, b[3] + y]
                if (box[0] >= edge[0] and box[1] >= edge[1] and box[2] <= edge[2]
                        and box[3] <= edge[3] and not any(_hit(box, o) for o in rects)):
                    best = (d2, x, y)
        if best is not None:
            r.SetPosition(pcbnew.VECTOR2I(int(best[1]), int(best[2])))
            continue
        # No CLEAR site -- but the layout may have stood it on its own pad, or against a
        # neighbour, to begin with. Laid flat about its own middle, if it touches nothing
        # it was not already touching and stays on the board, it is no worse placed than
        # it was and reads the right way.
        c0 = pcbnew.VECTOR2I(int((b[0] + b[2]) // 2), int((b[1] + b[3]) // 2))
        x, y = mid.x - c0.x, mid.y - c0.y
        box = [b[0] + x, b[1] + y, b[2] + x, b[3] + y]
        if (box[0] >= edge[0] and box[1] >= edge[1] and box[2] <= edge[2]
                and box[3] <= edge[3]
                and all(_hit(stood, o) for o in rects if _hit(box, o))):
            r.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
            continue
        # no room to lie flat: where it was, on the quarter turn the fab would have
        # printed anyway (never the half turn, never the other quarter)
        r.SetPosition(was[2])
        r.SetTextAngleDegrees(quarter)
        kept.append((fp.GetReference(), "its own designator: no room to lie flat within "
                                        "%.1f mm of where it stands" % REF_SLIDE))
    return kept


def _net(pad):
    n = pad.GetNetname().lstrip("/")
    return n if n and not n.startswith("unconnected") else ""


def _want_ref(refs, ref):
    """Does `silk_refs` (True / "all" / a list of prefixes) ask for this designator?"""
    if not refs or ref.startswith(REF_SKIP) or not ref.rstrip("0123456789"):
        return False
    if refs is True or refs == "all" or "all" in refs:
        return True
    return ref.rstrip("0123456789") in tuple(refs)


def _one_row(pads):
    """True if these pads lie on one line along X or Y."""
    xs = [q.GetPosition().x for q in pads]
    ys = [q.GetPosition().y for q in pads]
    return max(ys) - min(ys) < MM(0.05) or max(xs) - min(xs) < MM(0.05)


def _legend(ref, pins, word, two_rows):
    """The pinout block's text: a line a way, or -- for a two-row header -- a line a PAIR,
    odd way then even, which is how the part has them."""
    if not two_rows:
        return ref + "\n" + "\n".join("%d %s" % (k, word(v)) for k, v in sorted(pins.items()))
    left = {k: "%d %s" % (k, word(pins[k])) for k in pins if k % 2}
    wide = max([len(v) for v in left.values()] or [0])
    lines = []
    for k in sorted({(n + 1) // 2 for n in pins}):
        a, b = 2 * k - 1, 2 * k
        lines.append(("%-*s  %s" % (wide, left.get(a, ""),
                                    "%d %s" % (b, word(pins[b])) if b in pins else "")).rstrip())
    return ref + "\n" + "\n".join(lines)


WORD_REACH = 1.5           # mm a `silk_words` entry may sit from the point it was given


def silk(stem, rev=None, dark=(), labels=None, short=None, refs=None, way_words=None,
         read=None, pinout=None, ends=None, face=None, reach=None, sited=None):
    """Label `<stem>.kicad_pcb` in place. Returns the labels that found no free site
    (designators asked for by `refs` are reported but not returned: on a dense board
    most of them having no site is the expected result, not a finding)."""
    if os.path.isfile(stem + ".board.json"):
        import json
        with open(stem + ".board.json", encoding="utf-8") as fh:
            _notes = json.load(fh)
        labels = _notes.get("silk_labels", {}) if labels is None else labels
        short = _notes.get("silk_name") if short is None else short
        refs = _notes.get("silk_refs") if refs is None else refs
        rev = _notes.get("silk_rev") if rev is None else rev
        way_words = _notes.get("silk_short", {}) if way_words is None else way_words
        read = _notes.get("silk_read") if read is None else read
        pinout = _notes.get("silk_pinout") if pinout is None else pinout
        ends = _notes.get("silk_ends") if ends is None else ends
        face = _notes.get("silk_font") if face is None else face
        reach = _notes.get("silk_pinout_reach") if reach is None else reach
        sited = _notes.get("silk_words") if sited is None else sited
    way_words = dict(way_words or {})
    pinout, ends = set(pinout or ()), set(ends or ())
    read = float(read or 0.0) % 360.0
    if read not in (0.0, 90.0, 180.0, 270.0):
        raise SystemExit("silk_read is %r: a board reads at 0, 90, 180 or 270" % read)
    rev = rev or REV
    board = pcbnew.LoadBoard(stem + ".kicad_pcb")
    name = os.path.basename(stem)
    old = [d for d in board.GetDrawings()
           if d.GetClass() == "PCB_TEXT" and d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
    # ...and the way-1 dots of the last run (Side.dot)
    old += [d for d in board.GetDrawings()
            if d.GetClass() == "PCB_SHAPE" and d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)
            and d.GetShape() == pcbnew.SHAPE_T_CIRCLE and d.GetWidth() == 0
            and abs(d.GetRadius() - MM(MARK_D) // 2) <= 1]
    dark = tuple(dark)
    _set_face(face, board)
    if reach:
        global PINOUT_REACH
        PINOUT_REACH = float(reach)
    _face_refs(board)                            # BEFORE they are turned and read
    ref_turned = _flatten_refs(board, read)      # BEFORE the sides read where they are
    sides = {False: Side(board, False, dark, read), True: Side(board, True, dark, read)}
    fps = sorted(board.GetFootprints(), key=lambda f: f.GetReference())
    done, missed = [], []

    # 1. test pads FIRST: they have the least freedom, a pad's label is no use far away
    for fp in fps:
        ref = fp.GetReference()
        if not ref.startswith("TP"):
            continue
        pads = list(fp.Pads())
        net = _net(pads[0]) if pads else ""
        label = net if net and len(net) <= 10 else ref
        label = (labels or {}).get(ref, label)      # the board's own word for it wins
        s = sides[fp.IsFlipped()]
        others = [o.GetPosition() for o in fps
                  if o.GetReference().startswith("TP") and o is not fp
                  and o.GetReference() != ref]
        why = "beside its own pad (%s)" % ref
        # the net's name flat, then the pad's own (shorter) name flat, and only then
        # either of them turned
        # own=True: NEARER ITS OWN PAD THAN ANY OTHER TEST PAD, at every distance. Inside
        # the first ring that used not to be asked, and "SWCLK" went down 2.4 mm from the
        # +3V3 pad and 4.5 mm from its own: a probe is put where the nearest word says.
        if s.place(label, SIZE_TP, fp.GetPosition(), 5.0, rivals=others, own=True):
            done.append("%s=%s" % (ref, label))
        elif label != ref and s.place(ref, SIZE_TP, fp.GetPosition(), 5.0, rivals=others,
                                      own=True):
            done.append("%s=%s" % (ref, ref))
        elif s.place_legible(label, SIZE_TP, fp.GetPosition(), 5.0, rivals=others,
                             own=True, turn=why):
            done.append("%s=%s" % (ref, label))
        elif label != ref and s.place_legible(ref, SIZE_TP, fp.GetPosition(), 5.0,
                                              rivals=others, own=True, turn=why):
            done.append("%s=%s" % (ref, ref))
        else:
            missed.append(ref)

    # 1b. the things a PERSON operates or closes, by what they are FOR. A solder jumper
    #     named JP1 tells whoever holds the iron nothing; its value ("TERM", "BOOT0") does.
    #     `silk_labels` in <stem>.board.json ({"SW1": "RESET", "D3": "PWR"}) names anything
    #     else -- buttons, LEDs, a switch position -- and wins over the jumper default.
    wanted = {}
    for fp in fps:
        ref = fp.GetReference()
        if ref.startswith("JP") and ref[2:].isdigit():
            val = fp.GetValue().strip()
            if val and len(val) <= 10 and not val.lower().startswith("solderjumper"):
                wanted[ref] = val
    wanted.update(labels or {})
    for fp in fps:
        ref = fp.GetReference()
        if ref not in wanted or ref.startswith("TP"):      # test pads were step 1
            continue
        s = sides[fp.IsFlipped()]
        if s.place_legible(wanted[ref], SIZE_TP, fp.GetPosition(), 10.0,
                           rivals=[o.GetPosition() for o in fps
                                   if o.GetReference() in wanted and o.GetReference() != ref],
                           turn="beside the part it names (%s)" % ref):
            done.append("%s=%s" % (ref, wanted[ref]))
        else:
            missed.append("%s (%s)" % (ref, wanted[ref]))

    # 1c. each connector's ways, named on the connector's OWN side, in line with the way.
    #     Before the name and the blocks: a way's word has one place it can be, and the
    #     name can go anywhere. The net's own name first, then the short words.
    wayless, united = [], set()          # united: named in the same label as its word
    far_worded = set()                   # a numbered word at each tail on the far side
    for fp in fps:
        ref = fp.GetReference()
        if not (ref.startswith("J") and ref[1:].isdigit()):
            continue
        pads = {int(q.GetNumber()): q for q in fp.Pads()
                if q.GetNumber().isdigit() and _net(q)}
        # every numbered pad, wired or not: way 1 is way 1 whether or not it carries a net
        ways = {}
        for q in fp.Pads():
            if q.GetNumber().isdigit():
                ways.setdefault(int(q.GetNumber()), q)
        s = sides[fp.IsFlipped()]
        worded = False
        if pads and len(pads) <= LEGEND_MAX_PINS:
            first = min(pads)
            full = {k: (labels or {}).get(_net(q), _net(q)) for k, q in pads.items()}
            brief = {k: _short(_net(q), way_words) for k, q in pads.items()}
            shown = fp.Reference().IsVisible() and fp.Reference().GetLayer() == s.layer
            forms = []
            for words in (full, brief):
                words = dict(words)
                if len(pads) > 1:
                    words[first] = "%d %s" % (first, words[first])
                elif not shown:
                    # A ONE-WAY connector (a pogo land, a single turret): no "1" -- there
                    # is no second way to tell it from -- and its designator goes down
                    # WITH its word, as one label. Laid separately on a row of such lands
                    # at a tight pitch, each designator lost its place to the next land's
                    # word and came to rest beside the wrong pad.
                    words[first] = "%s %s" % (ref, words[first])
                if words not in forms:
                    forms.append(words)
            if _ways(s, fp, pads, forms):
                done.append("%s ways (%s)" % (ref, "back" if fp.IsFlipped() else "front"))
                worded = True
                if len(pads) == 1 and not shown:
                    united.add(ref)
            else:
                wayless.append(ref)
        if worded or len(ways) < 2:
            continue
        # NO WORD PER WAY (no room, or more ways than words are offered to): THEN AT LEAST
        # WHICH END IS WAY 1, on the connector's own side, whatever the part's size. A
        # pinout block -- wherever it ends up -- says what way 1 carries and not which
        # contact it is. A bare number, nearer its own pad than any other pad of the
        # part, at the legible size; flat first, turned only if that is the only way to
        # stand it against its own pin; a dot where not even a "1" fits.
        # far enough to get out from under the part's own body: a terminal block's pad is
        # 4 mm inside its courtyard
        cyb = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
        far = max(4.0, min(cyb.GetWidth(), cyb.GetHeight()) / 2e6 + 2.5)
        marks = [1] if 1 in ways else []
        last = max(ways)
        if last != 1 and (ref in ends or (len(ways) > LEGEND_MAX_PINS
                                          and _one_row(list(ways.values())))):
            marks.append(last)            # a long row: the far end gets its number too
        # ⚠ AND NEARER ITS OWN CONNECTOR'S BODY THAN ANY OTHER CONNECTOR'S. A mark in the
        # gap between two connectors is read as belonging to whichever body it is closer
        # to (quality A17 attributes it the same way), and "nearest its own pad" does not
        # settle that: a '1' under one header's pin 1 landed 0.05 mm nearer the jack below.
        mine = _rect(cyb)
        theirs = [_rect(o.GetCourtyard(pcbnew.B_CrtYd if o.IsFlipped()
                                       else pcbnew.F_CrtYd).BBox())
                  for o in fps if o is not fp and o.IsFlipped() == fp.IsFlipped()
                  and o.GetReference().startswith("J")]
        theirs = [q for q in theirs if q[2] > q[0] and q[3] > q[1]]

        # ⚠ AND NEARER ITS OWN CONTACTS THAN ANY TEST PAD. A bare "1" beside a test pad
        # is that pad's to anyone reading the board (and to quality A17, which gives ink
        # to a test pad when one is the nearest copper): a bring-up pad sited on the
        # track leaving way 1 took the mark standing in line with the way.
        lands = [_rect(q.GetBoundingBox()) for q in ways.values()]
        probes = [_rect(q.GetBoundingBox()) for o in fps
                  if o.GetReference().startswith("TP") and o.IsFlipped() == fp.IsFlipped()
                  for q in o.Pads()]

        def own_side(r, mine=mine, theirs=theirs, lands=lands, probes=probes):
            g = _gap(r, mine)
            if not all(g + MM(0.3) <= _gap(r, q) for q in theirs):
                return False
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            at = (cx, cy, cx, cy)
            d = min(_gap(at, q) for q in lands)
            return all(d + MM(0.1) <= _gap(at, q) for q in probes)
        for k in marks:
            what = "way-1" if k == 1 else "way-%d" % k
            others = [q.GetPosition() for n, q in ways.items() if n != k]
            if s.place(str(k), SIZE_J, ways[k].GetPosition(), far, rivals=others,
                       wider=False, own=True, ok=own_side,
                       turn="way %d's mark against its own pin (%s)" % (k, ref)):
                done.append("%s %s mark" % (ref, what))
            elif k == 1 and s.dot(ways[k].GetPosition(), far, others):
                # not even a "1": a dot beside way 1, the smallest mark that prints
                done.append("%s way-1 dot" % ref)
            else:
                missed.append("%s %s mark" % (ref, what))

    # 2. the board's own name, as large as will fit, front for choice. BEFORE the
    #    pinouts: on a 10 x 17 mm board there is room for one or the other, and which
    #    of two mirror-image boards this is matters more. One line, else two.
    centre = pcbnew.VECTOR2I((sides[False].bbox[0] + sides[False].bbox[2]) // 2,
                             (sides[False].bbox[1] + sides[False].bbox[3]) // 2)
    reach = max(sides[False].bbox[2] - sides[False].bbox[0],
                sides[False].bbox[3] - sides[False].bbox[1]) / 1e6
    # `silk_name` in the board's notes: a SHORT name for a board too small for its stem
    # ("POGO FEM BOT" for leg_pogo_female_bottom). The revision is still appended.
    words = (short.upper().split() if short else name.upper().split("_")) + [rev]
    forms = [" ".join(words)]
    if len(words) > 2:
        h = len(words) // 2
        forms.append(" ".join(words[:h]) + chr(10) + " ".join(words[h:]))
    if len(words) > 3:
        # a board a centimetre wide: three lines, then one word a line (the revision
        # rides on the last word). Squarer blocks find a site where a long line cannot.
        t = (len(words) + 2) // 3
        forms.append(chr(10).join(" ".join(words[i:i + t]) for i in range(0, len(words), t)))
        forms.append(chr(10).join(words[:-2] + [" ".join(words[-2:])]))
    # Every size, wording and face at the reading direction first. The name belongs to no
    # one place, so it has no claim on a quarter turn -- except that a board with no name
    # cannot be told from its mirror image, so as the very last thing it is turned, and
    # logged as that.
    tries = [(z, f, b) for z in SIZES_ID for f in forms for b in (False, True)]
    for why in (None, "the board's name: no site at the reading direction, at any size, "
                      "on either face"):
        for size, ident, back in tries:
            if sides[back].place(ident, size, centre, reach, step=0.5,
                                 optics=OPTICS_NAME_CLR, turn=why, wider=False):
                done.append("name %.1f mm (%s)" % (size, "back" if back else "front"))
                break
        else:
            continue
        break
    else:
        missed.append("BOARD NAME")

    # 3. connectors: the name on the part's own side, the pinout on the back where the
    #    through-hole tails are and nothing else is
    for fp in fps:
        ref = fp.GetReference()
        if not (ref.startswith("J") and ref[1:].isdigit()):
            continue
        s = sides[fp.IsFlipped()]
        shown = fp.Reference().IsVisible() and fp.Reference().GetLayer() == s.layer
        if ref in united:
            shown = True
        if not shown and not s.place_legible(ref, SIZE_J, fp.GetPosition(), 12.0,
                                             turn="beside its own connector (%s)" % ref):
            missed.append(ref)
        pins = {}
        for pad in fp.Pads():
            if pad.GetNumber().isdigit() and _net(pad):
                pins[int(pad.GetNumber())] = _net(pad)
        if not pins or (len(pins) > LEGEND_MAX_PINS and ref not in pinout):
            continue
        # `silk_labels` may give a NET a shorter word too ({"+24V_LED": "24V"}): a legend
        # is as wide as its longest net name, and on a small board that width is what
        # decides whether it goes down at a legible size or at all.
        # two columns only for the big two-row headers `silk_pinout` asks for: a 4-pin
        # power DIN is not in one row either, and reads better a way a line
        two = (len(pins) > LEGEND_MAX_PINS
               and not _one_row([q for q in fp.Pads() if q.GetNumber().isdigit()]))
        legend = _legend(ref, pins, lambda v: (labels or {}).get(v, v), two)
        brief = _legend(ref, pins, lambda v: _short(v, way_words), two)
        own = fp.IsFlipped()
        rivals = [o.GetPosition() for o in fps if o is not fp and o.GetReference() != ref
                  and o.GetReference().startswith("J")]
        why = "the pinout beside its own connector (%s)" % ref
        # never where it would be read against a row of pins (_misread); and beside its
        # OWN connector before beside anybody else's
        rows = {b: _rows(board, b) for b in (False, True)}

        def clear(back, strict, ref=ref, rows=rows):
            return lambda r, ang: not _misread(r, ang, rows[back], ref)
        if ref in wayless:
            # no room for a word per way: the block on the connector's own side is the
            # next best thing to read while plugging, at the legible size or not at all.
            # The full names flat, the short words flat, and only then either turned.
            for strict, text, turn in [(q, x, w) for q in (True, False)
                                       for x, w in ((legend, None), (brief, None),
                                                    (legend, why), (brief, why))]:
                if sides[own].place(text, SIZE_J, fp.GetPosition(), PINOUT_REACH, step=0.5,
                                    rivals=rivals, turn=turn, okang=clear(own, strict)):
                    done.append("%s pinout (%s, in place of its ways)"
                                % (ref, "back" if own else "front"))
                    break
            else:
                missed.append(ref + " ways")
            if own and (ref + " ways") not in missed:
                continue                  # that IS the back: no second copy beside it
        # ON THE FAR SIDE OF A THROUGH-HOLE ROW, A NUMBERED WORD AT EACH TAIL BEFORE ANY
        # BLOCK. That side is where a probe goes, and there a label is read by POSITION:
        # "2 24V" in line with tail 2 is right however it is read, where a list beside
        # the row is right only to someone who reads it as a list (_misread). Every
        # word carries its number -- seen from the back the row runs the other way.
        far = not own
        cu = pcbnew.B_Cu if far else pcbnew.F_Cu
        tails = {int(q.GetNumber()): q for q in fp.Pads()
                 if q.GetNumber().isdigit() and _net(q) and q.IsOnLayer(cu)}
        if not two and len(tails) > 1 and sorted(tails) == sorted(pins):
            forms = []
            for word in (lambda v: (labels or {}).get(v, v), lambda v: _short(v, way_words)):
                f = {k: "%d %s" % (k, word(_net(q))) for k, q in tails.items()}
                if f not in forms:
                    forms.append(f)
            if _ways(sides[far], fp, tails, forms):
                far_worded.add(ref)
                done.append("%s pinout (%s, a word at each pin)"
                            % (ref, "back" if far else "front"))
                if not sides[far].place_legible(ref, SIZE_J, fp.GetPosition(), 12.0,
                                                rivals=rivals,
                                                turn="beside its own connector (%s)" % ref):
                    missed.append("%s (%s)" % (ref, "back" if far else "front"))
                continue
        # THE SHORT WORDS AT THE LEGIBLE SIZE BEFORE THE FULL NAMES UNDER IT: a block is
        # as wide as its longest net name, and "GND 24V H L" read at 1.0 mm serves the
        # person plugging the lead better than PWR_GND / CAN_A_H at 0.8.
        texts = [legend] + ([brief] if brief != legend else [])
        for strict, size, text, back, turn in [(q, z, x, b, w) for q in (True, False)
                                               for z in (SIZE_J, SIZE_SMALL)
                                               for x in texts for w in (None, why)
                                               for b in (True, False)]:
            if sides[back].place(text, size, fp.GetPosition(), PINOUT_REACH, step=0.5,
                                 rivals=rivals, turn=turn, okang=clear(back, strict)):
                done.append("%s pinout (%s%s)" % (ref, "back" if back else "front",
                                                  ", short words" if text is not legend else ""))
                if size < SIZE_J:
                    sides[back].small.append(ref + " pinout")
                break
        else:
            missed.append(ref + " pinout")

    # 3b. WHICH TAIL IS WAY 1, ON THE FAR SIDE OF A THROUGH-HOLE CONNECTOR TOO. That face
    #     is the one in view when a board hangs under what it plugs into (a 2x20 socket
    #     put on a row late is 5 V on a ground pin), and the one a probe is put to. A
    #     numbered word at each tail already says it; a block, or nothing, does not.
    for back in (False, True):
        rws = {r_: b_ for r_, b_, _a, _c in _rows(board, back)}
        for fp in fps:
            ref = fp.GetReference()
            if ref not in rws or fp.IsFlipped() == back or ref in far_worded:
                continue
            cu = pcbnew.B_Cu if back else pcbnew.F_Cu
            tails = {int(q.GetNumber()): q for q in fp.Pads()
                     if q.GetNumber().isdigit() and q.IsOnLayer(cu)}
            if 1 not in tails or len(tails) < 2:
                continue
            theirs = [b_ for r_, b_ in rws.items() if r_ != ref]

            def own_row(r, mine=rws[ref], theirs=theirs):
                g = _gap(r, mine)
                return all(g + MM(0.3) <= _gap(r, q) for q in theirs)
            others = [q.GetPosition() for n, q in tails.items() if n != 1]
            face_ = "back" if back else "front"
            if sides[back].place("1", SIZE_J, tails[1].GetPosition(), 4.0, rivals=others,
                                 wider=False, own=True, ok=own_row,
                                 turn="way 1's mark against its own tail (%s)" % ref):
                done.append("%s way-1 mark (%s)" % (ref, face_))
            elif sides[back].dot(tails[1].GetPosition(), 4.0, others):
                done.append("%s way-1 dot (%s)" % (ref, face_))
            else:
                missed.append("%s way-1 mark (%s)" % (ref, face_))

    # 4. a designator beside each part, where the board asked for them (`silk_refs`).
    #    LAST, so no designator takes a site a test pad's net or a pinout needed, and
    #    the parts with the most pads first: U3 matters more than R17.
    ref_done, ref_missed = [], []
    named = set(wanted) | {x.split("=")[0] for x in done}
    for fp in sorted(fps, key=lambda f: (-len(list(f.Pads())), f.GetReference())):
        ref = fp.GetReference()
        if not _want_ref(refs, ref) or any(ref.startswith(q) for q in dark):
            continue
        s = sides[fp.IsFlipped()]
        if ref in named or (ref.startswith("J") and ref[1:].isdigit()):
            continue                         # steps 1b and 3 have already named it
        if fp.Reference().IsVisible() and fp.Reference().GetLayer() == s.layer:
            continue                         # its own designator is already in ink
        b = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
        half = max(b.GetWidth(), b.GetHeight(), MM(1.0)) / 2e6
        if s.place(ref, SIZE_REF, fp.GetPosition(), half * 1.42 + REF_REACH, wider=False,
                   turn="a designator beside its own part"):
            ref_done.append(ref)
        else:
            ref_missed.append(ref)

    # 6. words for a place (`silk_words`). LAST: every other label has its site by now,
    #    so asking for one cannot move another, and a kept board re-lettered with a word
    #    added differs from the last run by that word alone.
    for text, wx, wy, face_ in (sited or ()):
        if face_ not in ("front", "back"):
            raise SystemExit("silk_words: %r is on %r -- 'front' or 'back'" % (text, face_))
        s = sides[face_ == "back"]
        if s.place_legible(text, SIZE_J, pcbnew.VECTOR2I(MM(wx), MM(wy)), WORD_REACH,
                           wider=False):
            done.append("'%s' (%s)" % (text, face_))
        else:
            missed.append(text)

    for d in old:                           # after every read; the save is next
        board.Remove(d)
    if FACE:
        bad = unverified_glyphs(board, FACE["glyphs"])
        if bad:
            raise SystemExit("kicad_silk: %s -- %d text(s) need a character nobody has "
                             "verified in %r: %s. Look at each one DRAWN in the face; "
                             "add it to the face's `glyphs` if it is the character, and "
                             "if it is an ornament redraw it in the font or reword the "
                             "label. The board on disk is as it was."
                             % (name, len(bad), FACE["family"],
                                ", ".join("%r in %r" % (c, s) for s, c in bad[:8])))
    board.Save(stem + ".kicad_pcb")
    # what this run lettered in, for the quality pass (which has the board's notes but
    # not a project's face): the family, and the characters verified in it
    import json
    with open(stem + ".silk.json", "w", encoding="utf-8") as fh:
        json.dump({"family": FACE["family"] if FACE else None, "missing": FACE_MISSING,
                   "glyphs": FACE["glyphs"] if FACE else None}, fh)
    print("%s: %d label(s) -- %s" % (name, len(done), ", ".join(done)))
    if ref_done or ref_missed:
        print("  designators: %d of %d placed%s" % (
            len(ref_done), len(ref_done) + len(ref_missed),
            "; no site beside: " + ", ".join(sorted(ref_missed)) if ref_missed else ""))
    if missed:
        print("  no free site for: %s" % ", ".join(missed))
    # how the board reads: every printed text, the footprints' own designators included
    turned = sides[False].turned + sides[True].turned + ref_turned
    total = len([d for d in board.GetDrawings()
                 if d.GetClass() == "PCB_TEXT"
                 and d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]) + len(
        [f for f in fps if f.Reference().IsVisible()
         and f.Reference().GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)])
    print("  reads at %d deg; %d of %d text(s) a quarter turn off it%s"
          % (read, len(turned), total, ":" if turned else ""))
    for what, why in turned:
        print("      turned: %-12s %s" % (what, why))
    small = sides[False].small + sides[True].small
    if small:
        print("  placed at %.1f mm, under the legible %.1f (no site at full size): %s"
              % (SIZE_SMALL, SIZE_J, ", ".join(small)))
    return missed


def main(argv):
    """One board per PROCESS: board.Remove() on the old labels can leave pcbnew's SWIG
    layer handing back a bare SwigPyObject from the NEXT LoadBoard (seen on the ninth of
    ten boards in one run), so several stems are fanned out to child processes."""
    rev, dark, refs, stems, i = None, (), None, [], 0
    while i < len(argv):
        if argv[i] in ("--rev", "--dark", "--refs"):
            val = argv[i + 1]
            if argv[i] == "--rev":
                rev = val
            elif argv[i] == "--refs":
                refs = "all" if val == "all" else [p for p in val.split(",") if p]
            else:
                dark = tuple(p for p in val.split(",") if p)
            i += 2
        else:
            stems.append(argv[i][:-10] if argv[i].endswith(".kicad_pcb") else argv[i])
            i += 1
    if not stems:
        raise SystemExit("usage: kicad_silk.py [--rev rN] [--dark P1,P2] "
                         "[--refs all|U,Q,D] <stem> [...]")
    if len(stems) == 1:
        if not dark and os.path.isfile(stems[0] + ".board.json"):
            # a generated board says it in its own notes (pcbflow BOARD_NOTES "strip_silk")
            import json
            with open(stems[0] + ".board.json", encoding="utf-8") as fh:
                dark = tuple(json.load(fh).get("strip_silk", ()))
        silk(stems[0], rev, dark, refs=refs)
        return 0
    import subprocess
    for stem in stems:
        cmd = [sys.executable, os.path.abspath(__file__)]
        if rev:
            cmd += ["--rev", rev]
        if refs:
            cmd += ["--refs", "all" if refs == "all" else ",".join(refs)]
        if dark:
            cmd += ["--dark", ",".join(dark)]
        p = subprocess.run(cmd + [stem], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True)
        sys.stdout.write("".join(ln + chr(10) for ln in p.stdout.splitlines()
                                 if "image handler" not in ln and "memory leak" not in ln))
        if p.returncode:
            raise SystemExit("kicad_silk.py failed on %s" % stem)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
