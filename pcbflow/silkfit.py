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
            if area > 1e-6:
                p = obj.GetPosition()
                out.append((name, area, (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))))
    return sorted(out, key=lambda t: -t[1])


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

            def score(dx, dy):
                """(clipped, silk overlaps) for the text moved by (dx, dy)."""
                t = pcbnew.SHAPE_POLY_SET(base)
                t.Move(pcbnew.VECTOR2I(dx, dy))
                for ps in near_mask:
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
            for i in range(1, RINGS + 1):
                r = i * STEP_MM
                if best is not None and r >= best[0]:
                    break                      # no further ring can beat the best cost
                for k in range(ANGLES):
                    a = 2.0 * math.pi * k / ANGLES
                    dx = pcbnew.FromMM(r * math.cos(a))
                    dy = pcbnew.FromMM(r * math.sin(a))
                    c, n = score(dx, dy)
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
