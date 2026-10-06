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
OPTICS_CLR = 12.0          # no label this close to a part whose own silk was stripped
OPTICS_NAME_CLR = 30.0     # ...and the board's name, which can go anywhere, further still
SIZE_REF = 1.0             # a designator is printed legibly or not at all
REF_REACH = 2.0            # mm past the part's own half-diagonal: beside it, or nowhere
REF_SKIP = ("TP", "H", "MH", "FID", "REF", "G", "LOGO")   # no part there to name


def _box(item):
    b = item.GetBoundingBox()
    return [b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()]


def _grow(r, d):
    return [r[0] - d, r[1] - d, r[2] + d, r[3] + d]


def _hit(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class Side:
    """Everything a label on one side of the board has to stay off."""

    def __init__(self, board, back, dark=()):
        self.small = []          # labels that only fitted under the legible size
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
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        t.SetMirrored(self.back)
        t.SetTextAngleDegrees(angle)
        t.SetPosition(pcbnew.VECTOR2I(0, 0))
        return t

    def place_legible(self, s, size, near, reach, **kw):
        """`place` at `size`, else at SIZE_SMALL. Returns the size used, or 0."""
        for z in (size, SIZE_SMALL):
            if z <= size and self.place(s, z, near, reach, **kw):
                if z < size:
                    self.small.append(s.split(chr(10))[0])
                return z
        return 0

    def place(self, s, size, near, reach, angles=(0.0, 90.0), step=0.25, optics=None):
        """Lay `s` at the free site nearest `near` (a VECTOR2I), no further than `reach`
        mm. Returns True if it went down."""
        best = None
        for ang in angles:
            t = self.text(s, size, ang)
            b = _box(t)                                   # about the origin
            n = int(reach / step)
            for i in range(-n, n + 1):
                for j in range(-n, n + 1):
                    d2 = i * i + j * j
                    if d2 > n * n or (best is not None and d2 >= best[0]):
                        continue
                    x, y = near.x + MM(i * step), near.y + MM(j * step)
                    r = [b[0] + x, b[1] + y, b[2] + x, b[3] + y]
                    if self.free(r, optics):
                        best = (d2, ang, x, y, r)
        if best is None:
            return False
        t = self.text(s, size, best[1])
        t.SetPosition(pcbnew.VECTOR2I(int(best[2]), int(best[3])))
        self.board.Add(t)
        self.rects.append(_grow(best[4], MM(0.15)))
        return True


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


def silk(stem, rev=None, dark=(), labels=None, short=None, refs=None):
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
    rev = rev or REV
    board = pcbnew.LoadBoard(stem + ".kicad_pcb")
    name = os.path.basename(stem)
    old = [d for d in board.GetDrawings()
           if d.GetClass() == "PCB_TEXT" and d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
    dark = tuple(dark)
    sides = {False: Side(board, False, dark), True: Side(board, True, dark)}
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
        if s.place_legible(label, SIZE_TP, fp.GetPosition(), 5.0):
            done.append("%s=%s" % (ref, label))
        elif label != ref and s.place_legible(ref, SIZE_TP, fp.GetPosition(), 5.0):
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
        if s.place_legible(wanted[ref], SIZE_TP, fp.GetPosition(), 10.0):
            done.append("%s=%s" % (ref, wanted[ref]))
        else:
            missed.append("%s (%s)" % (ref, wanted[ref]))

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
    for size, ident, back in [(z, f, b) for z in SIZES_ID for f in forms for b in (False, True)]:
        if sides[back].place(ident, size, centre, reach, step=0.5, optics=OPTICS_NAME_CLR):
            done.append("name %.1f mm (%s)" % (size, "back" if back else "front"))
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
        if not shown and not s.place_legible(ref, SIZE_J, fp.GetPosition(), 12.0):
            missed.append(ref)
        pins = {}
        for pad in fp.Pads():
            if pad.GetNumber().isdigit() and _net(pad):
                pins[int(pad.GetNumber())] = _net(pad)
        if not pins or len(pins) > LEGEND_MAX_PINS:
            continue
        # `silk_labels` may give a NET a shorter word too ({"+24V_LED": "24V"}): a legend
        # is as wide as its longest net name, and on a small board that width is what
        # decides whether it goes down at a legible size or at all.
        legend = ref + "\n" + "\n".join(
            "%d %s" % (k, (labels or {}).get(v, v)) for k, v in sorted(pins.items()))
        for size, back in [(z, b) for z in (SIZE_J, SIZE_SMALL) for b in (True, False)]:
            if sides[back].place(legend, size, fp.GetPosition(), 14.0, step=0.5):
                done.append("%s pinout (%s)" % (ref, "back" if back else "front"))
                if size < SIZE_J:
                    sides[back].small.append(ref + " pinout")
                break
        else:
            missed.append(ref + " pinout")

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
        if s.place(ref, SIZE_REF, fp.GetPosition(), half * 1.42 + REF_REACH):
            ref_done.append(ref)
        else:
            ref_missed.append(ref)

    for d in old:                           # after every read; the save is next
        board.Remove(d)
    board.Save(stem + ".kicad_pcb")
    print("%s: %d label(s) -- %s" % (name, len(done), ", ".join(done)))
    if ref_done or ref_missed:
        print("  designators: %d of %d placed%s" % (
            len(ref_done), len(ref_done) + len(ref_missed),
            "; no site beside: " + ", ".join(sorted(ref_missed)) if ref_missed else ""))
    if missed:
        print("  no free site for: %s" % ", ".join(missed))
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
