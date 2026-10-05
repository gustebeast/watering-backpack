"""Move a via out of a solder land small enough that the barrel would drain the joint.

⚠ THE BOARD SAYS "TENTED" AND THE EXPORTED MASK SAYS OTHERWISE, which is why this is
measured on copper and paste rather than on the via's tenting flag. A via inside an SMD
pad has no mask opening of its OWN -- KiCad reports IsOnLayer(F_Mask) False for every one
of them -- but the PAD's aperture is already open over it. On the board this came from,
F.Mask exported as 208 dark flashes, one per pad on the layer, and not one clear flash
anywhere: there is no mask island inside any aperture, so every barrel sitting in a land
is open under the paste.

⚠ AND THE NUMBER THAT DECIDES IT IS VOLUME, NOT AREA. An open 0.3 mm barrel through 1.6 mm
of laminate holds 0.113 mm3. The paste printed over it is the aperture area times the
stencil foil -- on an 0603 land, 0.855 mm2 x 0.12 mm = 0.103 mm3. The barrel can swallow
MORE than the whole deposit. As an area ratio the same via reads 8 % of the pad and looks
like nothing, which is how four of them survived a quality pass that was looking for them.

⚠ THIS RUNS AFTER ROUTING BECAUSE THAT IS WHERE THE VIAS COME FROM. layout.py's stitcher
already refuses to put a via inside a land under via_d + 0.6 mm, and its vias are not the
problem: on the board this came from the two it placed in lands (Q1.3, Q2.3, both
2.20 x 1.20) clear that threshold and sit dead centre on purpose. The four that mattered
-- C6.2, C12.2, C15.2, C16.2 -- all had tracks attached, i.e. the ROUTER put them there,
and the stitcher's careful threshold has no authority over the router at all.

The move is deliberately small and conservative: a ring search for the nearest position
that is clear of foreign copper and outside every land, and the attached track ends come
with it so the connection is not broken. A via that cannot be moved is REPORTED, not
forced and not silently left -- quality A14 then fails on it, which is the right place for
a decision a script should not be taking.
"""
import json
import math
import os
import sys

import pcbnew

MM = pcbnew.ToMM
FM = pcbnew.FromMM
FOIL = 0.12          # mm of stencil, for the volume the report quotes
THICK = 1.6          # mm of laminate


def _lands(board, margin_mm):
    """SMD pads that open the paste and are too small to hold a barrel: (pad, shape)."""
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            if not (p.IsOnLayer(pcbnew.F_Paste) or p.IsOnLayer(pcbnew.B_Paste)):
                continue          # no paste, no joint to starve (a bare test pad)
            sz = p.GetSize()
            if min(MM(sz.x), MM(sz.y)) >= margin_mm:
                continue          # big enough to swallow a via and still hold solder
            out.append((p, "%s.%s" % (fp.GetReference(), p.GetNumber())))
    return out


def _clear(board, x, y, via, lands, keep):
    """Is a via centred at (x, y) clear of every land, and no closer to foreign copper
    than `keep`? Measured against pads and tracks of OTHER nets, like the stitcher."""
    pt = pcbnew.VECTOR2I(int(x), int(y))
    r = via.GetWidth(pcbnew.F_Cu) / 2 + keep
    # ⚠ CLEARING THE LAND IS NOT ENOUGH; THERE HAS TO BE A MASK DAM BETWEEN THEM. A via
    # whose edge stops 0.1 mm from the pad's edge leaves no room for a strip of solder
    # mask, so the fab prints none, and the joint simply flows down the barrel sideways
    # instead of through it. That is the same failure with an extra step. So the land is
    # grown by the via's radius AND the keepout, which is what a dam needs.
    for pad, _name in lands:
        bb = pad.GetBoundingBox()
        bb.Inflate(int(via.GetWidth(pcbnew.F_Cu) / 2 + keep))
        if bb.Contains(pt):
            return False
    # ⚠ A HOLE IS A HOLE WHATEVER NET IT IS ON, and skipping same-net copper skipped
    # that too. The first run moved C16.2's via 1.10 mm and parked it 0.165 mm INTO
    # another GND via -- A12 called it hole-to-hole and was right. Electrically the two
    # barrels are the same net and nothing shorts; mechanically the drill cannot make
    # them, and the panel comes back as an engineering query. So every other via's hole
    # is checked by hole-to-hole spacing regardless of net, before anything else.
    hh = FM(0.20)                     # the fab's via-hole to via-hole minimum
    r_hole = via.GetDrillValue() / 2
    for t in board.GetTracks():
        if t is via or t.GetClass() != "PCB_VIA":
            continue
        d = math.hypot(t.GetPosition().x - x, t.GetPosition().y - y)
        if d < r_hole + t.GetDrillValue() / 2 + hh:
            return False
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetDrillSizeX() <= 0:
                continue              # SMD: no hole to collide with
            d = math.hypot(p.GetPosition().x - x, p.GetPosition().y - y)
            if d < r_hole + p.GetDrillSizeX() / 2 + FM(0.45):
                return False          # a pad hole wants the wider pad-hole spacing
    net = via.GetNetCode()
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() == net:
                continue
            bb = p.GetBoundingBox()
            bb.Inflate(int(r))
            if bb.Contains(pt):
                return False
    for t in board.GetTracks():
        if t is via or t.GetNetCode() == net:
            continue
        bb = t.GetBoundingBox()
        bb.Inflate(int(r))
        if bb.Contains(pt):
            return False
    return True


def main(stem):
    pcb = stem + ".kicad_pcb"
    if not os.path.isfile(pcb):
        return 0
    try:
        notes = json.load(open(stem + ".board.json", encoding="utf-8"))
    except Exception:                       # noqa: BLE001 -- a board with no notes is fine
        notes = {}
    q = notes.get("quality", {}) or {}
    keep_mm = float(q.get("via_land_keepout", 0.25))
    cap_mm = float(q.get("via_land_move_max", 1.5))
    board = pcbnew.LoadBoard(pcb)

    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    if not vias:
        return 0
    margin = MM(max(v.GetWidth(pcbnew.F_Cu) for v in vias)) + 0.6
    lands = _lands(board, margin)
    if not lands:
        return 0

    plane_nets = set(notes.get("stitch_nets", ()))
    merge_mm = float(q.get("via_land_merge", 2.0))
    hole_mm = float(q.get('via_hole_hole', 0.45))
    moved, stuck, retired = [], [], []
    drilled, crowded = [], []
    for v in vias:
        vp = v.GetPosition()
        hit = [(p, n) for p, n in lands if p.GetBoundingBox().Contains(vp)]
        if not hit:
            continue
        pad, name = hit[0]
        barrel = math.pi * (MM(v.GetDrillValue()) / 2.0) ** 2 * THICK
        sz = pad.GetSize()
        paste = MM(sz.x) * MM(sz.y) * FOIL
        # the ring search: nearest first, and outward in 0.1 mm steps
        # ⚠ AND THE SEARCH IS CAPPED, BECAUSE A LONG MOVE IS NOT A FIX. The first run of
        # this put C12's via 4.00 mm away -- C12 is the ADC filter capacitor for the
        # joystick axis, placed 2.19 mm from the pin it filters on purpose, and a ground
        # return that then walks 4 mm is a worse board than the one with the wicking
        # risk. Past the cap this reports instead, and a person moves the PART.
        best = None
        step = FM(0.1)
        for ring in range(1, int(cap_mm / 0.1) + 1):
            for k in range(24):
                a = 2 * math.pi * k / 24.0
                x = vp.x + ring * step * math.cos(a)
                y = vp.y + ring * step * math.sin(a)
                if _clear(board, x, y, v, lands, FM(keep_mm)):
                    best = (int(x), int(y), MM(int(ring * step)))
                    break
            if best:
                break
        if not best:
            # ⚠ BEFORE GIVING UP, ASK WHETHER THE VIA IS NEEDED AT ALL. C12.2 could not be
            # moved because the space around it is full -- and what filled it included a
            # SECOND GND via 1.03 mm away, outside the land, joined to the same pad by
            # 0.97 mm of F.Cu. The router had dropped two. Moving the one in the land was
            # never the only answer; retiring it was the better one, and it is the answer
            # the search could not see because it was looking for empty board rather than
            # for a via already doing the job.
            #
            # Narrow on purpose. Only a net the DESIGN declares to be a plane
            # (notes["stitch_nets"]) qualifies, so "the pour carries it" is the board's own
            # statement and not this script's guess; the keeper must be within merge_mm and
            # itself outside every land; and the short stub that fed the dead via goes with
            # it, while anything longer is left for the pour to absorb. finish.py re-runs
            # DRC and the unconnected count straight after this, which is what proves it.
            keeper = None
            if v.GetNetname() in plane_nets:
                for o in vias:
                    if o is v or o.GetNetCode() != v.GetNetCode():
                        continue
                    d = math.hypot(o.GetPosition().x - vp.x, o.GetPosition().y - vp.y)
                    if d > FM(merge_mm):
                        continue
                    if any(q.GetBoundingBox().Contains(o.GetPosition()) for q, _n in lands):
                        continue
                    keeper = (o, MM(int(d)))
                    break
            if not keeper:
                stuck.append((name, 100.0 * barrel / paste))
                continue
            for t in list(board.GetTracks()):
                if t.GetClass() == "PCB_VIA" or t.GetNetCode() != v.GetNetCode():
                    continue
                if (t.GetStart() == vp or t.GetEnd() == vp) and t.GetLength() < FM(0.3):
                    board.Remove(t)
            board.Remove(v)
            retired.append((name, keeper[1], 100.0 * barrel / paste))
            continue
        nx, ny, dist = best
        np_ = pcbnew.VECTOR2I(nx, ny)
        # the attached track ends come with it, or the move breaks the connection
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                continue
            if t.GetNetCode() != v.GetNetCode():
                continue
            if t.GetStart() == vp:
                t.SetStart(np_)
            if t.GetEnd() == vp:
                t.SetEnd(np_)
        v.SetPosition(np_)
        moved.append((name, dist, 100.0 * barrel / paste))

    # ── second pass: a hole drilled on top of another hole ────────────────────────
    # ⚠ THE SAME DEFECT WEARING A DIFFERENT TRIGGER, and the first pass cannot see it
    # because it only looks at lands small enough to starve. U2 is an ESP32 module whose
    # thermal pad is 21 pad objects -- nine 0.90 mm SMD lands and TWELVE 0.70 mm plated
    # holes on a 0.700 mm grid, the module's own thermal via array. The pad is far too big
    # to be in `lands`, so the first pass walks past it; meanwhile the router had dropped
    # its own GND vias into the same pad, and one of them sat 0.300 mm from a footprint
    # barrel -- two 0.3 mm holes exactly tangent, which the drill cannot make as two
    # holes. Ten places in all, from 0.000 to 0.416 mm of gap against a 0.45 mm minimum.
    #
    # Those vias were redundant the moment they were laid: the pad they are in is on GND
    # and already has twelve plated barrels of its own. So the keeper here may be a PAD
    # hole as well as a via -- a plated barrel reaches the plane whichever object owns it.
    holes = [(t.GetPosition(), t.GetDrillValue(), t.GetNetCode(), None) for t in vias]
    for fp in board.GetFootprints():
        for pd in fp.Pads():
            if pd.GetDrillSizeX() > 0:
                holes.append((pd.GetPosition(), pd.GetDrillSizeX(), pd.GetNetCode(), pd))

    def _gap(a, ra, b, rb):
        return math.hypot(a.x - b.x, a.y - b.y) - ra / 2.0 - rb / 2.0

    for v in [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]:
        vp, vd = v.GetPosition(), v.GetDrillValue()
        tight = [(MM(int(_gap(vp, vd, hp, hd))), owner)
                 for hp, hd, _nc, owner in holes
                 if not (hp.x == vp.x and hp.y == vp.y and owner is None)
                 and _gap(vp, vd, hp, hd) < FM(hole_mm)]
        if not tight:
            continue
        worst_gap, _owner = min(tight)
        keeper = None
        if v.GetNetname() in plane_nets:
            for hp, hd, nc, owner in holes:
                if nc != v.GetNetCode() or (hp.x == vp.x and hp.y == vp.y):
                    continue
                if math.hypot(hp.x - vp.x, hp.y - vp.y) > FM(merge_mm):
                    continue
                if _gap(vp, vd, hp, hd) >= FM(hole_mm) or owner is not None:
                    keeper = (owner, MM(int(math.hypot(hp.x - vp.x, hp.y - vp.y))))
                    break
        if not keeper:
            crowded.append((v.GetNetname(), worst_gap))
            continue
        for t in list(board.GetTracks()):
            if t.GetClass() == "PCB_VIA" or t.GetNetCode() != v.GetNetCode():
                continue
            if (t.GetStart() == vp or t.GetEnd() == vp) and t.GetLength() < FM(0.3):
                board.Remove(t)
        board.Remove(v)
        drilled.append((v.GetNetname(), worst_gap, keeper[1]))

    for net, gap, d in drilled:
        print("  retired a %s via drilled %.3f mm from another hole -- the same net has a "
              "plated barrel %.2f mm away that is not" % (net, gap, d))
    for net, gap in crowded:
        print("  COULD NOT clear a %s via %.3f mm from another hole: quality A12 will say "
              "so" % (net, gap))
    for name, dist, pct in moved:
        print("  moved the via out of %s by %.2f mm -- its barrel was %.0f %% of the "
              "paste printed there" % (name, dist, pct))
    for name, d, pct in retired:
        print("  retired the redundant via in %s -- the same net already has one %.2f mm "
              "away outside the land, and the barrel was %.0f %% of the paste printed there"
              % (name, d, pct))
    for name, pct in stuck:
        print("  COULD NOT move the via out of %s (barrel is %.0f %% of the paste "
              "printed there): quality A14 will say so" % (name, pct))
    if moved or retired or drilled:
        board.Save(pcb)
        try:
            import layout
            layout._canonical_uuids(pcb)
        except Exception:                   # noqa: BLE001
            pass
    return len(moved) + len(retired) + len(drilled)


if __name__ == "__main__":
    sys.exit(0 if main(os.path.abspath(sys.argv[1])) >= 0 else 1)
