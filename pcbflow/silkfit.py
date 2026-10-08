# -*- coding: utf-8 -*-
"""Make the silkscreen in the design be the silkscreen that gets printed.

⚠ THE RULE THIS ENFORCES IS THE OWNER'S, AND IT IS NOT A TIDINESS RULE: the design
must not show a letter that is missing on the real board. A fab prints silk and then
opens the solder mask, and anywhere the two overlap the ink is removed -- KiCad calls
it "Silkscreen clipped by solder mask". A designator half over a neighbour's pad is
therefore drawn in full in every render, every plot and every review, and arrives with
a letter gone. Nothing in the flow caught that, because of WHERE the silk work lived:
layout.py's fitter places the board-level labels and holds 0.20 mm off every mask
opening, but a footprint's REFERENCE DESIGNATOR arrives with the land, from whoever
drew it, and went onto the board untouched. One class of silk was fitted, another was
not, and "the fitter holds 0.20 mm" was read as a statement about the board.

So this pass owns every silk field on the board, and its contract is binary:

  * a designator is moved to the nearest position where it prints INTACT, or
  * it is moved to the F.Fab / B.Fab assembly drawing, where it is not silk at all.

There is no third outcome in which something is drawn on silk and does not print. A
part whose designator cannot fit anywhere is still identified -- F.Fab is the assembly
drawing, and the fab places from the CPL rather than from silk -- but the silkscreen
stops promising ink it cannot lay down.

WHY THE MASK IS THE OBSTACLE AND NOT THE COPPER. Silk over a buried track prints
perfectly: the mask covers the copper and the ink sits on the mask. What removes ink
is an OPENING, so the obstacle set is the mask layer -- pad apertures -- and not the
copper layer. This is also why the pass can run straight after placement: tracks and
pours do not open mask, so routing cannot invalidate the result.

SILK OVER SILK IS A SEPARATE AND MILDER THING, and it is deliberately not fatal here.
Two silk objects that touch both still print; the result is ugly, not absent. It is
costed in the search so a free spot beats a crowded one, but a designator is never
exiled to F.Fab merely for brushing a courtyard line.
"""
from __future__ import annotations

import math

ERR_MM = 0.005                  # polygon approximation of arcs and glyphs
LOCAL_MM = 12.0                 # obstacles further than this cannot touch the text
STEP_MM = 0.125                 # ring search radial step
RINGS = 48                      # 48 x 0.125 = 6.0 mm of search
ANGLES = 48
SILK_COST_MM = 2.0              # how much detour is worth dodging one silk overlap


def _sides(pcbnew):
    return ((pcbnew.F_SilkS, pcbnew.F_Mask, pcbnew.F_Fab),
            (pcbnew.B_SilkS, pcbnew.B_Mask, pcbnew.B_Fab))


def _poly_of(pcbnew, obj, layer):
    """`obj` as a SHAPE_POLY_SET on `layer`, or None if this build will not give one.

    ⚠ PADS ARE ASKED FOR THEIR COPPER SHAPE, NOT THEIR MASK SHAPE, ON PURPOSE. On
    KiCad 10.0.6 PAD.TransformShapeToPolygon(..., F_Mask, ...) raises from inside its
    own GetSolderMaskExpansion(), which the SWIG binding calls without the layer
    argument it now requires. The copper shape plus the board's mask expansion is the
    same polygon and does not go through that path.
    """
    ps = pcbnew.SHAPE_POLY_SET()
    try:
        obj.TransformShapeToPolygon(ps, layer, 0, pcbnew.FromMM(ERR_MM),
                                    pcbnew.ERROR_OUTSIDE)
    except Exception:                                      # noqa: BLE001
        return None
    return ps if ps.OutlineCount() else None


def _pad_mask_poly(pcbnew, pad, mask_layer, cu_layer, expansion):
    ps = _poly_of(pcbnew, pad, mask_layer)
    if ps is None:
        ps = _poly_of(pcbnew, pad, cu_layer)
        if ps is None:
            return None
        if expansion:
            ps.Inflate(expansion, 16)
    return ps


def _hits(pcbnew, a, b):
    """Do these two poly sets share any area?

    The copy constructor rather than Clone(): SHAPE_POLY_SET.Clone() is not in this
    build's SWIG surface, and intersecting in place would destroy the caller's shape.
    """
    c = pcbnew.SHAPE_POLY_SET(a)
    c.BooleanIntersection(b)
    return c.OutlineCount() > 0


def _centre(box):
    o, s = box.GetOrigin(), box.GetSize()
    return (o.x + s.x // 2, o.y + s.y // 2)


def _edges(board, pcbnew):
    """Edge_Cuts as (obstacles, extent): the outline's own shapes, and its bbox.

    ⚠ THE BOARD EDGE WAS NOT AN OBSTACLE, WHICH MADE THE FIXER DANGEROUS RATHER
    THAN MERELY INCOMPLETE. The obstacle set was mask apertures and silk, so nothing
    stopped the ring search parking a designator PAST THE OUTLINE. Demonstrated: a
    reference 1.0 mm inside the right edge, with a wide aperture covering everything
    inboard, was moved 1.50 mm to x 148.05 on a board whose edge is at 147.55 -- off
    the board -- and clipped() then reported all 74 silk objects printing as drawn.
    KiCad's own DRC called it silk_edge_clearance. A designator that is entirely
    ABSENT is strictly worse than the missing letter this rule exists to prevent,
    and the fixer is what put it there.

    TWO TESTS, BECAUSE ONE DOES NOT COVER IT. Intersecting the outline's shapes
    catches text STRADDLING an edge -- including the edge of an internal cutout,
    which a bounding box would miss entirely. But text parked wholly outside the
    board intersects nothing at all, so containment in the extent is checked too.
    Neither is sufficient alone; together they bound a board that is convex or has
    cutouts, which is every board this toolchain makes.
    """
    polys = []
    lo_x = lo_y = hi_x = hi_y = None
    half = 0
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        # ⚠ THE BOUNDARY IS THE CENTRELINE, AND THE BOUNDING BOX IS NOT. An
        # Edge_Cuts shape is a STROKE, so its box is the cut line plus half a line
        # width either side -- about 0.05 mm here. Measured against the box, U2's
        # footprint outline, which sits 0.050 mm inside the edge, read as crossing it
        # and this gate reported 0.0050 mm2 of lost ink on a board that is fine.
        half = max(half, (getattr(d, "GetWidth", lambda: 0)() or 0) // 2)
        bb = d.GetBoundingBox()
        lo_x = bb.GetLeft() if lo_x is None else min(lo_x, bb.GetLeft())
        hi_x = bb.GetRight() if hi_x is None else max(hi_x, bb.GetRight())
        lo_y = bb.GetTop() if lo_y is None else min(lo_y, bb.GetTop())
        hi_y = bb.GetBottom() if hi_y is None else max(hi_y, bb.GetBottom())
        ps = _poly_of(pcbnew, d, pcbnew.Edge_Cuts)
        if ps is not None:
            polys.append((bb, ps))
    if lo_x is None:
        return [], None
    return polys, (lo_x + half, lo_y + half, hi_x - half, hi_y - half)


# 1 um, which no fab holds, so "exactly on the cut line" counts as inside
_EDGE_EPS = 1000


def _off_board(box, extent, margin=0):
    """True when `box` reaches measurably outside `extent` (the Edge_Cuts centreline).

    Proximity to the edge is NOT this function's business: KiCad's own
    silk_edge_clearance owns that and finish.py runs it on every board. This answers
    the one question that rule cannot -- is the ink on the board at all.
    """
    if extent is None:
        return False
    lo_x, lo_y, hi_x, hi_y = extent
    return (box.GetLeft() < lo_x + margin - _EDGE_EPS
            or box.GetRight() > hi_x - margin + _EDGE_EPS
            or box.GetTop() < lo_y + margin - _EDGE_EPS
            or box.GetBottom() > hi_y - margin + _EDGE_EPS)


def _near(pcbnew, box, obstacles, reach):
    """The obstacles whose box comes within `reach` of this one; the rest cannot matter.

    ⚠ SCREENED BOX TO BOX, NOT CENTRE TO CENTRE. Comparing centres asks whether two
    objects are near each other ON AVERAGE, which is the wrong question for anything
    long: a 20 mm footprint outline has a centre well clear of a designator its edge
    runs right past, so the text would be fitted against an obstacle list missing the
    one thing it touches. An inflated box that INTERSECTS is the right question.

    This was found by reading the screening code rather than from a failure, and
    fixing it changed no placement on the board that prompted it -- the one overlap
    left there is a deliberate cost trade-off below, not a missed obstacle. It is
    still a defect: it would have mattered the first time a long outline happened to
    sit where a designator wanted to go.
    """
    probe = pcbnew.BOX2I(box.GetOrigin(), box.GetSize())
    probe.Inflate(reach)
    return [ps for bb, ps in obstacles if probe.Intersects(bb)]


def clipped(board, pcbnew=None):
    """Every silk object the solder mask will clip, as [(name, mm2, (x, y))].

    This is the measurement behind quality A18, and it lives here rather than in
    quality.py so the pass that MOVES the text and the rule that GRADES it read the
    same geometry. A rule that re-implements its fixer's model is a rule that passes
    a board the fixer broke.

    Every silk object is checked, not only the designators the pass can move: a
    footprint OUTLINE over a pad is clipped exactly as much as a letter is, and the
    answer for it is the board's `strip_silk` note, not a nudge.
    """
    if pcbnew is None:
        import pcbnew as _p
        pcbnew = _p
    ds = board.GetDesignSettings()
    expansion = getattr(ds, "m_SolderMaskExpansion", 0) or 0
    edges, extent = _edges(board, pcbnew)
    out = []
    for silk_layer, mask_layer, _fab in _sides(pcbnew):
        cu_layer = pcbnew.F_Cu if silk_layer == pcbnew.F_SilkS else pcbnew.B_Cu
        masks = []
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if not p.IsOnLayer(mask_layer):
                    continue
                ps = _pad_mask_poly(pcbnew, p, mask_layer, cu_layer, expansion)
                if ps is not None:
                    masks.append((p.GetBoundingBox(), ps))
        items = []
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            for f in fp.GetFields():
                if f.IsVisible() and f.GetLayer() == silk_layer:
                    items.append(("%s field %r" % (ref, (f.GetText() or "")[:12]), f))
            for g in fp.GraphicalItems():
                if g.GetLayer() == silk_layer:
                    items.append(("%s %s" % (ref, g.GetClass()), g))
        for d in board.GetDrawings():
            if d.GetLayer() == silk_layer:
                items.append(("board %s %r" % (d.GetClass(),
                                               (getattr(d, "GetText", lambda: "")()
                                                or "")[:12]), d))
        for name, obj in items:
            ps = _poly_of(pcbnew, obj, silk_layer)
            if ps is None:
                continue
            box = obj.GetBoundingBox()
            area = 0.0
            for m in _near(pcbnew, box, masks, pcbnew.FromMM(1.0)):
                c = pcbnew.SHAPE_POLY_SET(ps)
                c.BooleanIntersection(m)
                if c.OutlineCount():
                    area += abs(c.Area()) * 1e-12
            # ⚠ THE ROUTER REMOVES INK AS SURELY AS THE MASK DOES. Ink past the
            # outline is cut off the board; ink across it is cut in half. Neither is
            # a solder-mask opening, so this used to report NEITHER -- and the fitter,
            # which shares this geometry, would happily park a designator off the
            # board and be told it printed as drawn.
            if _off_board(box, extent):
                # The reported area is the WHOLE glyph: exact when the object is
                # wholly outside, an upper bound when it straddles. It is not
                # refined, because the figure only has to be non-zero to fail the
                # rule and the remedy is the same either way -- put the ink on the
                # board.
                area += abs(ps.Area()) * 1e-12
                name += " [past the board outline]"
            if area > 1e-6:
                p = obj.GetPosition()
                out.append((name, area, (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))))
    return sorted(out, key=lambda t: -t[1])


def thicken_ink(board, floor_mm, pcbnew=None, log=print):
    """Raise every silk GRAPHIC thinner than the fab's minimum to it. Returns
    (raised, thinnest_before).

    ⚠ WHY THIS IS HERE AND NOT LEFT TO THE FOOTPRINT. A part outline arrives with
    the land, drawn by whoever drew the library, and KiCad's default silk width is
    0.12 mm -- below every fab's stated silkscreen minimum, and below the width the
    same board's TEXT is held to. The fab does not reject it; it prints it thin,
    broken, or not at all, and whichever happens the plot that was reviewed is not
    the board that arrives. That is the same rule A18 enforces for clipped ink, and
    it is the owner's: a drawing must match the built thing.

    This moves no copper and touches no text -- silk shapes only -- so it is safe on
    a kept-route board, and it runs BEFORE fit_refs so the fitter dodges the final
    ink rather than the thin ink.
    """
    if pcbnew is None:
        import pcbnew as _p
        pcbnew = _p
    silk = (pcbnew.F_SilkS, pcbnew.B_SilkS)
    floor = pcbnew.FromMM(floor_mm)
    raised, thinnest = 0, None
    items = [g for fp in board.GetFootprints() for g in fp.GraphicalItems()] \
        + list(board.GetDrawings())
    for g in items:
        if g.GetClass() == "PCB_TEXT" or g.GetLayer() not in silk:
            continue
        try:
            w = g.GetWidth()
        except Exception:                                   # noqa: BLE001
            continue        # a shape with no width (a bitmap) has no ink to raise
        if w <= 0:
            continue        # 0 means "use the design default", which layout.py sets
        thinnest = w if thinnest is None else min(thinnest, w)
        if w < floor - 1:                                   # 1 nm of slack
            g.SetWidth(floor)
            raised += 1
    if raised:
        log("silk ink: %d graphic(s) raised to the fab's %.2f mm minimum "
            "(thinnest was %.3f mm)" % (raised, floor_mm, pcbnew.ToMM(thinnest)))
    return raised, (pcbnew.ToMM(thinnest) if thinnest is not None else None)


def fit_refs(board, notes=None, log=print, pcbnew=None):
    """Move every visible silk reference so it prints as drawn.

    Returns (moved, demoted, kept) -- moved is [(ref, mm, (x, y))], demoted is
    [(ref, why)], kept is the number already clear.
    """
    if pcbnew is None:
        import pcbnew as _p
        pcbnew = _p
    notes = notes or {}
    if notes.get("silkfit") is False:
        log("   silkfit: off by board request")
        return [], [], 0

    ds = board.GetDesignSettings()
    expansion = getattr(ds, "m_SolderMaskExpansion", 0) or 0
    moved, demoted, kept = [], [], 0

    for silk_layer, mask_layer, fab_layer in _sides(pcbnew):
        cu_layer = pcbnew.F_Cu if silk_layer == pcbnew.F_SilkS else pcbnew.B_Cu

        # ── the obstacle sets, built once per side ──────────────────────────
        # the outline is side-independent, and it is FORBIDDEN rather than costed:
        # see _edges(). A move that puts a designator off the board is not a cheaper
        # trade than a silk overlap, it is the defect this pass exists to prevent.
        edges, extent = _edges(board, pcbnew)
        # ⚠ A CONNECTOR THAT HANGS OVER THE EDGE BRINGS ITS OUTLINE WITH IT. A jack or a
        # header mounted at the board's edge has a library outline drawn round the whole
        # body, and the strokes of it that lie past the cut line are ink the router
        # removes: drawn, not printed, and A18 says so. They cannot be nudged -- they are
        # where the body is -- so those strokes, and only those, go to .Fab, where a body
        # outline off the board belongs. (`strip_silk` is the tool for taking a part's
        # WHOLE outline off the silk; it acts at layout, so it costs a re-route, and it
        # would take the strokes that do print with it.) Graphics only: text is a
        # designator or a label and is handled as one.
        _over = {}
        for fp in board.GetFootprints():
            for g in fp.GraphicalItems():
                if (g.GetLayer() == silk_layer and g.GetClass() == "PCB_SHAPE"
                        and _off_board(g.GetBoundingBox(), extent)):
                    g.SetLayer(fab_layer)
                    _over[fp.GetReference()] = _over.get(fp.GetReference(), 0) + 1
        for _ref in sorted(_over):
            demoted.append((_ref, "%d outline stroke(s) past the board edge" % _over[_ref]))
        masks, silks = [], []
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if not p.IsOnLayer(mask_layer):
                    continue
                ps = _pad_mask_poly(pcbnew, p, mask_layer, cu_layer, expansion)
                if ps is not None:
                    masks.append((p.GetBoundingBox(), ps))
            for g in fp.GraphicalItems():
                if g.GetLayer() != silk_layer:
                    continue
                ps = _poly_of(pcbnew, g, silk_layer)
                if ps is not None:
                    silks.append((g.GetBoundingBox(), ps))
        for d in board.GetDrawings():
            if d.GetLayer() != silk_layer:
                continue
            ps = _poly_of(pcbnew, d, silk_layer)
            if ps is not None:
                silks.append((d.GetBoundingBox(), ps))

        # every visible silk FIELD on this side, including the ones we may move
        fields = []
        for fp in board.GetFootprints():
            for f in fp.GetFields():
                if f.IsVisible() and f.GetLayer() == silk_layer:
                    fields.append((fp, f))

        others = []
        for fp, f in fields:
            ps = _poly_of(pcbnew, f, silk_layer)
            if ps is not None:
                others.append((fp.GetReference(), f.GetBoundingBox(), ps))

        for fp, f in fields:
            ref = fp.GetReference()
            base = _poly_of(pcbnew, f, silk_layer)
            if base is None:
                continue
            box = f.GetBoundingBox()
            reach = pcbnew.FromMM(LOCAL_MM)
            near_mask = _near(pcbnew, box, masks, reach)
            near_silk = _near(pcbnew, box, silks, reach)
            near_silk += _near(pcbnew, box,
                               [(bb, ps) for r, bb, ps in others if r != ref], reach)

            def score(dx, dy, shape=None):
                """(clipped, silk overlaps) for the text moved by (dx, dy).

                None means "this position is not allowed": a mask opening, or the
                board outline.
                """
                t = pcbnew.SHAPE_POLY_SET(base if shape is None else shape)
                t.Move(pcbnew.VECTOR2I(dx, dy))
                for ps in near_mask:
                    if _hits(pcbnew, t, ps):
                        return None, None
                tb = t.BBox()
                if _off_board(tb, extent):
                    return None, None
                for ps in _near(pcbnew, tb, edges, pcbnew.FromMM(1.0)):
                    if _hits(pcbnew, t, ps):
                        return None, None
                n = 0
                for ps in near_silk:
                    if _hits(pcbnew, t, ps):
                        n += 1
                return 0, n

            clipped, overlaps = score(0, 0)
            if clipped == 0 and overlaps == 0:
                kept += 1
                continue

            best = None
            if clipped == 0:
                best = (overlaps * SILK_COST_MM, 0.0, 0, 0, overlaps)
            # ⚠ SCORE THE SHAPE THE TEXT WILL HAVE, NOT THE ONE IT HAS. A text that is
            # moved is also laid upright (below), and a designator that was turned is a
            # different polygon once it is: scored as it stood and then re-angled, R3 and
            # R4 on one board landed 0.03-0.04 mm2 INTO the openings they had just been
            # moved off, and only a second whole run -- which found them already upright
            # -- cleared them. So the candidates are scored upright.
            _was = (f.GetTextAngle().AsDegrees(), f.IsKeepUpright())
            f.SetTextAngleDegrees(0.0)
            f.SetKeepUpright(True)
            upright = _poly_of(pcbnew, f, silk_layer)
            f.SetTextAngleDegrees(_was[0])
            f.SetKeepUpright(_was[1])
            if upright is None:
                upright = base
            for i in range(1, RINGS + 1):
                r = i * STEP_MM
                if best is not None and r >= best[0]:
                    break                      # no further ring can beat the best cost
                for k in range(ANGLES):
                    a = 2.0 * math.pi * k / ANGLES
                    dx = pcbnew.FromMM(r * math.cos(a))
                    dy = pcbnew.FromMM(r * math.sin(a))
                    c, n = score(dx, dy, upright)
                    if c is None:
                        continue
                    cost = r + n * SILK_COST_MM
                    if best is None or cost < best[0]:
                        best = (cost, r, dx, dy, n)

            if best is None:
                # ⚠ NO SPOT PRINTS, SO IT DOES NOT GO ON SILK. F.Fab is the assembly
                # drawing; the fab places from the CPL, so the part is still named
                # everywhere a person or a machine looks for it -- just not in ink
                # that would have arrived with a letter missing.
                f.SetLayer(fab_layer)
                demoted.append((ref, "no position within %.1f mm prints intact"
                                % (RINGS * STEP_MM)))
                continue
            if best[1] > 0.0:
                p = f.GetPosition()
                f.SetPosition(pcbnew.VECTOR2I(p.x + best[2], p.y + best[3]))
                f.SetTextAngleDegrees(0.0)
                f.SetKeepUpright(True)
                moved.append((ref, best[1],
                              (pcbnew.ToMM(f.GetPosition().x),
                               pcbnew.ToMM(f.GetPosition().y))))
                # the moved text is now an obstacle at its new place
                for idx, (r0, bb0, ps0) in enumerate(others):
                    if r0 == ref:
                        ps = _poly_of(pcbnew, f, silk_layer)
                        if ps is not None:
                            others[idx] = (r0, f.GetBoundingBox(), ps)
                        break
            else:
                kept += 1

    if moved or demoted:
        log("   silkfit: %d designator(s) moved clear of a mask opening, %d to .Fab, "
            "%d already printed as drawn" % (len(moved), len(demoted), kept))
        for ref, mm, xy in sorted(moved, key=lambda t: -t[1])[:12]:
            log("      %-5s %.2f mm -> (%.3f, %.3f)" % (ref, mm, xy[0], xy[1]))
        for ref, why in demoted:
            log("      %-5s -> .Fab: %s" % (ref, why))
    else:
        log("   silkfit: all %d silk designator(s) already print as drawn" % kept)
    return moved, demoted, kept
