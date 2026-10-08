"""Autoroute a placed board: .kicad_pcb -> Specctra .dsn -> freerouting -> .ses -> board.

    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/route.py elec/out/lever_sensor

RUNS UNDER KICAD'S PYTHON, like layout.py and for the same reason (pcbnew).

WHY AUTOROUTE THIS ONE AND NOT THE OTHERS. The tee and the TRRS adapter are four
nets of straight track and a pour -- hand-routing them in `tracks` gives better
copper than any router would, and the source stays readable. The lever board is
29 parts and 20 nets on four layers, where hand-specifying every segment would be
neither reviewable nor better. Freerouting is the right tool at that size.

The router is NOT authoritative: it produces a candidate, and `kicad-cli pcb drc`
is what says whether the candidate is acceptable. Re-running can give a different
result, so the routed .kicad_pcb is a build artifact like the netlist -- the
placement in <board>.board.json is the thing under version control.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import time
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


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout                                        # noqa: E402  (needs the path above)

def _find_java():
    """$JAVA, else the newest Temurin under %LOCALAPPDATA%\\Programs\\temurin, else `java`
    on PATH. Returns a path that may not exist -- route() reports that with the fix."""
    import glob
    env = os.environ.get("JAVA")
    if env:
        return env
    found = sorted(glob.glob(os.path.expandvars(
        r"%LOCALAPPDATA%\Programs\temurin\*\bin\java.exe")), reverse=True)
    if found:
        return found[0]
    return shutil.which("java") or "java"


JAVA = _find_java()
# Freerouting 2.4.1 is built for Java 25 (class file 69) -- a Java 21 runtime
# fails to load it at all, which is the first thing to check if this breaks.
def _find_jar():
    r"""Locate freerouting.jar, and NOT in a session scratch directory.

    ⚠⚠ THIS USED TO POINT INTO a session scratch directory under %LOCALAPPDATA%\Temp, which
    means the whole routing pipeline stopped working the moment that temp directory was
    cleaned -- for the lead and every other agent who took the merge, not just the session
    that happened to download it. Nothing would have said why: the jar simply is not there.
    This project has already lost a tool that way (scratchpad/maze.py, whose own replacement
    note reads "anything that has to be re-run every time the route changes cannot live in a
    scratch directory"), and then the ROUTER itself did the same thing.
    Order: an explicit override, then a stable per-machine install, then the old scratch path
    so an existing checkout keeps working until the copy is made.
    """
    import glob
    cands = [os.environ.get("FREEROUTING_JAR"),
             os.path.expandvars(r"%LOCALAPPDATA%\Programs\freerouting\freerouting.jar")]
    cands += sorted(glob.glob(os.path.expandvars(
        r"%LOCALAPPDATA%\Temp\*\*\*\scratchpad\freerouting.jar")), reverse=True)
    for c in cands:
        if c and os.path.isfile(c):
            return c
    raise SystemExit(
        r"freerouting.jar not found. Put it at "
        r"%LOCALAPPDATA%\Programs\freerouting\freerouting.jar, or set FREEROUTING_JAR. "
        r"(~64 MB, so deliberately NOT in the repo -- but it must not live in a session "
        r"scratch directory either: that is how this pipeline came to depend on a temp dir.)")


JAR = _find_jar()
# ⚠ PASSES BUY CONNECTIVITY ON A HARD BOARD, AND THIS COMMENT USED TO SAY THEY DO NOT.
# The old claim was that freerouting finds connectivity in the first pass or two and
# every pass after that only shortens track, so "the curve is flat after about 10". It
# was measured on the small boards, where it is true because they finish. On the optical
# board it is false, and not marginally:
#
#     1 pass  -> 105 unconnected
#     3       ->  50
#    10       ->  13
#    25       ->   6          (1069 s, against ~700 for ten)
#
# Half the failures of a ten-pass run are still there because the optimiser has not got
# to them yet. That is what a board near its routing limit looks like: the early passes
# leave a mess that later passes rip up and re-lay, and stopping early freezes the mess.
# 60% more wall clock for 54% fewer failures is not a marginal trade.
#
# SO THE RULE IS PER-BOARD, not global. Boards that finish easily gain nothing past ten
# and should not pay for the passes; boards that do not finish should ask for more via
# `router_passes` (optical does). Keep this default low for iteration.
#
# ⚠ AND RAISE `timeout` WITH THE PASS COUNT. 25 passes on the optical board needs about
# 1070 s and the default was 900, so the first attempt at this measurement was KILLED --
# and the DRC that followed reported 266 unconnected, which is the UNROUTED board. A
# timeout that fires looks exactly like a routing result unless you read the log.
DSN_CLEAR_MARGIN_UM = 10      # see the clearance block in route()
PASSES = 10


def failing_nets(stem):
    """The nets the last DRC left unconnected, for an incremental re-route."""
    d = json.load(open(stem + ".finish.drc.json", encoding="utf-8"))
    out = set()
    for v in d.get("unconnected_items", []):
        for item in v["items"]:
            m = re.search(r"\[([^\]]+)\]", item.get("description", ""))
            if m:
                out.add(m.group(1))
    return sorted(out)


# The bring-up pads are placed after routing, which is what makes them cheap and what
# makes them ROT: a site that clears every track of one route is inside a track of the
# next. Three separate runs have now lost real work to this -- most recently a pass that
# routed TWO MORE NETS than the one we kept, thrown away because TP10's frozen site had
# become a 6.02 mm short against V5_PRE.
#
# route.py's own comment above post_route_refs already says the right thing -- "THE SITE IS
# SEARCHED AGAINST THE FINISHED BOARD, not chosen" -- and that was true when the site was
# searched. Freezing the ANSWER into notes["placements"] is what broke it: the search was a
# one-off by hand (tools/padsite.py) and the board moves underneath it. So do the search
# HERE, where the finished board is in hand, and treat the recorded coordinate as a
# PREFERENCE rather than a fact: if it still clears, nothing moves and this costs nothing.
#
# ⚠ ONLY THE TP PADS. Rs11..Rs51 are post-route too, but each carries a pull-up on a new
# SHDNZ net that has to reach its converter's pin -- moving one is not free the way moving a
# bare pad on a finished rail is.
POST_PAD_CLR_MM = 0.127            # the fab copper rule this board is built to
POST_PAD_REACH_MM = 20.0           # how far a stale site may be nudged before giving up
POST_PAD_STEP_MM = 0.25


def _resite_post_pads(board, refs, notes):
    """Re-search each bring-up pad's site against the copper that is actually there.

    A good site, in the original search's words: a clear circle that ALREADY OVERLAPS ITS
    OWN NET'S COPPER, so the pad needs no track of its own. Rejected: too close to foreign
    copper, or under a footprint's courtyard (a pad under a part is electrically legal and
    physically unprobeable).

    Returns a list of (ref, dx, dy) for the pads that had to move. Run AFTER the nets are
    assigned -- the search needs to know which copper is the pad's own."""
    import math

    segs, vias = [], []
    for t in board.Tracks():
        n = t.GetNetname()
        if isinstance(t, pcbnew.PCB_VIA):
            a = t.GetStart()
            vias.append((pcbnew.ToMM(a.x), pcbnew.ToMM(a.y),
                         pcbnew.ToMM(t.GetWidth()) / 2.0, n))
        else:
            if t.GetLayer() != pcbnew.F_Cu:
                continue           # a bare pad probes the front; other layers cannot short it
            a, b = t.GetStart(), t.GetEnd()
            segs.append((pcbnew.ToMM(a.x), pcbnew.ToMM(a.y),
                         pcbnew.ToMM(b.x), pcbnew.ToMM(b.y),
                         pcbnew.ToMM(t.GetWidth()) / 2.0, n))
    # ⚠ THE DECLARED REPAIR TRACKS ARE COPPER TOO, AND THEY ARE NOT ON THE BOARD YET.
    # They are laid just after this, so a pad whose only copper IS its declared stub -- a
    # debug pad on a pin that was a no-connect until now -- read as standing on nothing
    # and was walked off the end of the stub it was declared with. Counted here, a
    # declared stub is own copper to its pad and an obstacle to every other one.
    for _net, _lay, _w, _pts in notes.get("repair_tracks", ()):
        if _lay != "F.Cu":
            continue
        _q = [layout._to_board(_x, _y) for _x, _y in _pts]
        for _a, _b in zip(_q, _q[1:]):
            segs.append((pcbnew.ToMM(_a.x), pcbnew.ToMM(_a.y),
                         pcbnew.ToMM(_b.x), pcbnew.ToMM(_b.y), _w / 2.0, _net))

    courts = []
    for fp in board.GetFootprints():
        if fp.GetReference() in refs:
            continue
        try:
            bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
            if bb.GetWidth() <= 0:
                bb = fp.GetBoundingBox(False, False)
        except Exception:
            bb = fp.GetBoundingBox(False, False)
        courts.append((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetRight()),
                       pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetBottom())))

    def _seg_d(px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 == 0 else max(0.0, min(1.0,
                                             ((px - x1) * dx + (py - y1) * dy) / l2))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    # ⚠ THE OTHER BRING-UP PADS ARE OBSTACLES TOO, AND THEY WERE NOT. The
    # courtyard list above skips every ref in `refs`, which is right for the pad
    # being sited -- a pad cannot block itself -- but it also skipped the NINE
    # others, including the ones this very loop had just placed. So a pad could
    # be re-sited directly on top of one already moved: on watering-backpack's
    # main board TP9 (JOY_FILT) moved 9.25 mm onto TP10 (LEVEL), and DRC
    # reported courtyards_overlap plus three silk collisions between two parts
    # this function had put there itself.
    #
    # Sites are recorded here as they are decided, in the loop's own order, and
    # a later pad keeps clear of them. It is deliberately not the courtyard
    # list: these are circles, because that is what the ring search produces and
    # what the keepout radius already measures.
    taken = []

    def _ok(px, py, r, net, r_keep=None, need_own=True):
        r_keep = r if r_keep is None else r_keep
        for tx, ty, tr in taken:
            if math.hypot(px - tx, py - ty) < r_keep + tr:
                return None
        own = 1e9
        for x1, y1, x2, y2, hw, n in segs:
            d = _seg_d(px, py, x1, y1, x2, y2) - hw
            if n == net:
                own = min(own, d)
            elif d < r + POST_PAD_CLR_MM:
                return None
        for vx, vy, vr, n in vias:
            d = math.hypot(px - vx, py - vy) - vr
            if n == net:
                own = min(own, d)
            elif d < r + POST_PAD_CLR_MM:
                return None
        if need_own and own > r:
            return None            # not on its own copper: the pad would need a track
        # ⚠ THE PAD'S OWN COURTYARD, NOT ITS COPPER, IS WHAT MEETS A NEIGHBOUR'S COURTYARD.
        # Tested with the copper radius, a site 0.2 mm off a part passed here and came
        # back from DRC as courtyards_overlap -- a violation, which also stops close_last
        # from running on the board at all.
        keep = max(r + POST_PAD_CLR_MM, r_keep + 0.02)
        # ...and never less than the courtyard itself, which is HEAD's own test of
        # the same thing: r_keep already falls back to the copper radius when the
        # part has no courtyard, so the max() is the stricter of the two always.
        for cx0, cx1, cy0, cy1 in courts:
            if cx0 - keep <= px <= cx1 + keep and cy0 - keep <= py <= cy1 + keep:
                return None
        return own

    moved, stubbed, dropped = [], [], []
    for fp in list(board.GetFootprints()):
        ref = fp.GetReference()
        if ref not in refs or not ref.startswith("TP"):
            continue
        pads = list(fp.Pads())
        if len(pads) != 1:
            continue               # a multi-pad post-route part is not a bare probe pad
        pad = pads[0]
        net = pad.GetNetname()
        # ⚠ THE RADIUS IS THE COURTYARD'S, NOT THE PAD'S, because the courtyard is
        # what DRC compares. Searching on the pad radius accepted sites whose
        # COURTYARD overlapped a neighbour's: a D1.5 mm test pad is a 1.5 mm pad
        # inside a ~2.6 mm courtyard, so the search was working to a circle 0.55 mm
        # too small in every direction. Measured on the watering-backpack board:
        # nine pads re-sited, five of them straight into a courtyards_overlap
        # violation, and the run reported 5 violations it had just created.
        #
        # The own-copper test still uses the PAD radius -- that question is "does
        # this pad land on its own net", and the courtyard carries no copper.
        r = pcbnew.ToMM(max(pad.GetSize().x, pad.GetSize().y)) / 2.0
        try:
            _cbb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
            if _cbb.GetWidth() > 0:
                r_keep = pcbnew.ToMM(max(_cbb.GetWidth(), _cbb.GetHeight())) / 2.0
            else:
                r_keep = r
        except Exception:
            r_keep = r
        px = pcbnew.ToMM(pad.GetPosition().x)
        py = pcbnew.ToMM(pad.GetPosition().y)
        if _ok(px, py, r, net, r_keep) is not None:
            taken.append((px, py, r_keep))
            continue               # the recorded site still clears: nothing to do
        # Ring search outwards, so a pad that has to move moves as little as possible --
        # these coordinates were chosen next to the thing they help bring up, and that
        # intent is worth keeping even when the copper no longer allows the exact point.
        def _ring(need_own):
            k = 1
            while k * POST_PAD_STEP_MM <= POST_PAD_REACH_MM:
                rad = k * POST_PAD_STEP_MM
                n_th = max(8, int(2.0 * math.pi * rad / POST_PAD_STEP_MM))
                for i in range(n_th):
                    th = 2.0 * math.pi * i / n_th
                    qx, qy = px + rad * math.cos(th), py + rad * math.sin(th)
                    if _ok(qx, qy, r, net, r_keep, need_own) is not None:
                        return (qx, qy, rad)
                k += 1
            return None

        best = _ring(True)
        if best is None:
            # ⚠ NEVER LEAVE THE PAD WHERE IT IS. This used to do exactly that,
            # and "where it is" is a coordinate chosen against an OLDER route:
            # on the watering-backpack board it put TP10 (LEVEL) on top of a
            # VBAT track, and DRC reported a 27.8 mm SHORT from the battery to
            # the level-sensor input, plus a mask bridge to D2's pad. A bring-up
            # pad is a convenience. It is never worth a short, so the fallbacks
            # go in order of what is actually at stake:
            #
            #   1. a site that is merely SAFE -- clear of foreign copper and of
            #      every courtyard, but not on its own net. The pad arrives
            #      unconnected and close_last.py maze-routes a stub to it, which
            #      is how SW, GATE_A and GATE_B get probed at all; their nets are
            #      short runs boxed in between the FETs, drivers and gate
            #      resistors with no exposed front copper anywhere.
            #   2. no pad. If the board has nowhere safe within reach, the
            #      footprint comes off entirely and the run says so. A board that
            #      is missing one test point can still be brought up; a board
            #      with VBAT shorted to a GPIO cannot be powered.
            best = _ring(False)
            if best is None:
                board.Remove(fp)
                dropped.append((ref, net))
                continue
            stubbed.append((ref, net, best[2]))
        qx, qy, rad = best
        taken.append((qx, qy, r_keep))
        pos = fp.GetPosition()
        fp.SetPosition(pcbnew.VECTOR2I(
            pos.x + pcbnew.FromMM(qx - px), pos.y + pcbnew.FromMM(qy - py)))
        moved.append((ref, net, rad))
    if moved:
        print("      re-sited %d bring-up pad(s) against THIS route's copper: %s"
              % (len(moved), ", ".join("%s (%s) moved %.2f mm" % m for m in moved)))
    if stubbed:
        print("      %d bring-up pad(s) have no exposed copper of their own on "
              "this route -- parked clear and left for close_last to stub: %s"
              % (len(stubbed), ", ".join("%s (%s) at %.2f mm" % t for t in stubbed)))
    if dropped:
        # Loud, because the board now has fewer test points than the schematic
        # asked for and nothing else will mention it.
        print("      ⚠ REMOVED %d bring-up pad(s) ENTIRELY -- no site within "
              "%.1f mm was even safe, and a pad that shorts is worse than no "
              "pad: %s" % (len(dropped), POST_PAD_REACH_MM,
                           ", ".join("%s (%s)" % d for d in dropped)))
        board.BuildConnectivity()
    return moved



def route(stem, passes=None, timeout=14400, incremental=False, dsn_only=False):
    """Route the board at `stem`.

    ⚠ `incremental` ROUTES FROM THE BOARD AS IT STANDS, NOT FROM A FRESH PLACEMENT, and
    it is the answer to "must every experiment cost a full run". The normal path throws
    the routing away (finish.py re-runs layout.py first) and hands freerouting all 96
    nets; incremental hands it the routed board with every net FROZEN except the handful
    DRC says are still unconnected. The router then has one small problem instead of a
    whole board, and the copper it already got right cannot be disturbed.

    It only became possible once the frozen-copper restore existed. Freezing a wire in
    the DSN is half the operation -- the session file does not carry fixed wires, so
    without the re-lay below an incremental run would delete everything it froze, which
    is exactly the bug that cost a routing run to find.

    ⚠ IT IS NOT A SUBSTITUTE FOR A FULL RUN. The frozen copper is an obstacle the router
    cannot move, so a net that fails because its neighbour took the only channel will go
    on failing. Use it to attack the last few nets on a board that is otherwise good;
    use a full run after anything that changes the netlist or the placement.
    """
    pcb, dsn, ses = stem + ".kicad_pcb", stem + ".dsn", stem + ".ses"
    # ⚠ A BOARD MAY ASK FOR MORE PASSES, and recording that beats remembering it.
    # "Raise it for the final run" is an instruction to a person, and a person who is
    # not there when someone regenerates this in three years. A board that needs 30 says
    # so in its own notes and gets 30 every time it is built.
    if passes is None:
        passes = json.load(open(stem + ".board.json", encoding="utf-8")).get(
            "router_passes", PASSES)
    notes = None
    if os.path.isfile(stem + ".board.json"):
        notes = json.load(open(stem + ".board.json", encoding="utf-8"))
    board = pcbnew.LoadBoard(pcb)
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        raise SystemExit("Specctra DSN export failed")
    print("exported %s (%.0f kB)" % (os.path.basename(dsn), os.path.getsize(dsn) / 1e3))

    # ⚠ DECLARE THE PLANE LAYERS AS PLANES, or the router treats them as free copper.
    # KiCad's Specctra exporter marks EVERY copper layer "(type signal)", so a 4-layer
    # board hands freerouting four routing layers -- including the one the design calls
    # an unbroken ground plane and relies on for the USB pair's impedance reference.
    # It duly routes through it: the optical board's In1.Cu pour came back at 1043 mm2
    # of an original 5729, shredded into islands by tracks laid across it, and the
    # "continuous reference plane" in the header was simply not true of any routed board
    # here. Specctra's own word for this is (type power); freerouting honours it and
    # leaves the layer alone.
    #
    # It also makes the routing PROBLEM smaller and better posed, which is the happy
    # part: two signal layers with a solid reference between them, instead of four
    # layers of contention and a reference that is not there.
    planes = notes.get("plane_layers", ()) if notes else ()
    if planes:
        txt = open(dsn, encoding="utf-8").read()
        for layer in planes:
            marker = "(layer %s\n      (type signal)" % layer
            if marker not in txt:
                raise SystemExit("plane layer %s not found in the DSN as expected"
                                 % layer)
            txt = txt.replace(marker, "(layer %s\n      (type power)" % layer)
        open(dsn, "w", encoding="utf-8").write(txt)
        print("  declared %s as plane layer(s) -- the router will not route on them"
              % ", ".join(planes))

    # ⚠ KEEP THE ROUTER'S VIAS OFF THE STITCH VIAS. A stitch via is only a connection
    # where the plane reaches it, and the plane is poured AFTER routing, round whatever
    # the router added. Every foreign via voids a circle of (via radius + the plane's
    # clearance) in the plane, and the router knows nothing of that: it spaces vias by
    # the copper rule, 0.14 mm apart, which is far inside a 0.5 mm plane clearance. One
    # neighbour 0.76 mm away took half the ring of a driver's supply stitch; two, one
    # each side, would take all of it, and nothing after routing can put it back --
    # another run lays the same via in the same place.
    # So each stitch via gets a via keepout out to (plane clearance + its drill radius):
    # no foreign antipad can then reach its barrel. Tracks are untouched -- this is a
    # keepout for vias only -- and on a plane poured at 0.3 mm the circle is no bigger
    # than the spacing the copper rule already enforces, so it costs nothing there.
    stitch_nets = set(notes.get("stitch_nets", ())) if notes else set()
    if stitch_nets and planes:
        plane_ids = set(board.GetLayerID(n) for n in planes)
        zclr = {}
        for z in board.Zones():
            if z.GetNetname() in stitch_nets and plane_ids & set(z.GetLayerSet().Seq()):
                c_ = z.GetLocalClearance()
                c_ = c_ if isinstance(c_, int) else (c_.value() if c_ and c_.has_value() else 0)
                zclr[z.GetNetname()] = max(zclr.get(z.GetNetname(), 0), c_)
        # a foreign via is voided out of EVERY plane, so the clearance that matters is
        # the widest of them, whichever net the stitch itself is on
        worst = max(list(zclr.values()) + [board.GetDesignSettings().m_MinClearance])
        outs = []
        for t in board.GetTracks():
            if t.GetClass() != "PCB_VIA" or t.GetNetname() not in zclr:
                continue
            rad = pcbnew.ToMM(worst + t.GetDrillValue() / 2.0) * 1000.0
            cx_, cy_ = pcbnew.ToMM(t.GetPosition().x) * 1000.0, -pcbnew.ToMM(t.GetPosition().y) * 1000.0
            pts = ["%.1f %.1f" % (cx_ + rad * math.cos(k * math.pi / 6.0),
                                  cy_ + rad * math.sin(k * math.pi / 6.0)) for k in range(13)]
            outs.append('    (via_keepout "" (polygon signal 0  %s))\n' % "  ".join(pts))
        if outs:
            txt = open(dsn, encoding="utf-8").read()
            at = txt.find("    (via ")
            if at < 0:
                raise SystemExit("no (via ...) line in the DSN structure to anchor keepouts")
            open(dsn, "w", encoding="utf-8").write(txt[:at] + "".join(outs) + txt[at:])
            print("  %d stitch via(s) fenced with a %.2f mm via keepout (plane clearance "
                  "%.2f)" % (len(outs), pcbnew.ToMM(worst) + 0.15, pcbnew.ToMM(worst)))

    # ⚠ THE ROUTER IS GIVEN MORE CLEARANCE THAN THE FAB RULE, ON PURPOSE. freerouting
    # routes right up to the clearance it is handed, and its geometry and KiCad's do not
    # round the same way -- so a board it considers finished comes back with tracks
    # 0.1212-0.1247 mm apart against a 0.127 mm rule. Four such violations on the optical
    # board, all of them 4-6 um short, all of them freerouting's own copper touching
    # freerouting's own copper. There is nothing to fix on the board; the router simply
    # aims at the line instead of inside it.
    #
    # THE FIX BELONGS IN THE DSN, NOT IN THE DESIGN RULE. Raising the netclass to 0.137
    # would raise it for the fab as well, and 0.127 mm is what the cheap JLCPCB process
    # is quoted at -- we want the real rule checked by the real DRC. So the exported DSN
    # gets the margin and the board keeps its rule: the router aims 10 um inside the
    # line, DRC still measures against the line.
    #
    # The smd_smd clearance is deliberately NOT bumped. That one is pad-to-pad, decided
    # by placement before the router ever runs, and widening it only makes the router
    # refuse geometry that is already legal and already built.
    txt = open(dsn, encoding="utf-8").read()
    bumped = set()

    def _bump(m):
        v = float(m.group(1))
        bumped.add(v)
        return "(clearance %g)" % (v + DSN_CLEAR_MARGIN_UM)

    txt, n_bump = re.subn(r"\(clearance ([\d.]+)\)", _bump, txt)
    if not n_bump:
        raise SystemExit("no plain (clearance N) rule in the DSN -- cannot add the "
                         "router margin, and routing without it produces violations")
    # ⚠ THE COPPER THE GENERATOR LAID IS HANDED TO THE ROUTER AS A SUGGESTION, AND FOR
    # THE DIFFERENTIAL PAIR THAT IS A BUG. kicad-cli exports every existing track as
    # `(type route)`, which in Specctra means the router owns it and may rip it up -- so
    # all 223 pre-laid segments are advisory. For the GND stitches and the local nets
    # that is fine and arguably the point; they were measured as a help, not a promise.
    #
    # FOR A COUPLED PAIR IT DEFEATS THE ENTIRE ROUTINE THAT LAID IT. _diff_pairs exists
    # because freerouting has no concept of a differential pair and routes D+ and D- as
    # two independent nets; it builds both rails by offsetting ONE centreline so they
    # cannot diverge. Measured on 2026-09-17, the generator handed over
    #     DP 11.62 mm / 8 segments / 0 vias      DM 11.80 mm / 8 segments / 0 vias
    # -- matched to 0.18 mm, same shape -- and freerouting gave back
    #     DP 12.78 mm / 7 segments / 1 via       DM 15.44 mm / 12 segments / 0 vias
    # which is 2.66 mm of mismatch, different segment counts, and a via on one rail
    # only. That is not a pair. It is the exact defect the docstring of _diff_pairs
    # opens by describing, reintroduced one step downstream, and nothing downstream
    # could see it: DRC checks copper against the netlist and both nets were connected.
    #
    # `(type fix)` is freerouting's "do not touch" -- its FixedState has UNFIXED,
    # SHOVE_FIXED, USER_FIXED and SYSTEM_FIXED, and only the last two survive a rip-up
    # pass unchanged. SHOVE_FIXED would let the pair be shoved, which changes the
    # geometry and so is no better for coupling.
    #
    # ONLY THE DECLARED PAIRS ARE FROZEN BY DEFAULT. Freezing everything is a different
    # question with a real trade behind it -- pre-laid copper becomes a hard obstacle
    # instead of negotiable, which this project has measured going the wrong way before
    # -- so it is exposed as `fix_prelaid` in the board notes to be MEASURED rather than
    # assumed. The pairs are not a trade: copper that must not move, must not move.
    frozen = set()
    for spec in (notes or {}).get("diff_pairs", ()):
        frozen.update(spec.get("nets", ()))
    # ...AND ANY NET THE BOARD DECLARES FROZEN OUTRIGHT (2026-09-30). `diff_pairs` freezes
    # what layout._diff_pairs LAID; this freezes copper the board file supplies itself as
    # notes["tracks"]/["vias"]. It exists for pairs _diff_pairs cannot escape (a QFN fan-out,
    # a USB-C with its rows along Y): output_panel's THRU and HUB_DN1 were routed one
    # conductor at a time, and six placement changes in a row split one or both across
    # layers. Their copper is lifted from the one clean board and pinned here instead.
    frozen.update((notes or {}).get("frozen_nets", ()))
    pair_nets = None if (notes or {}).get("fix_prelaid") else frozen
    if (notes or {}).get("fix_prelaid"):
        # ⚠ FREEZING AND RESTORING ARE TWO HALVES OF ONE THING, AND fix_prelaid ONLY DID
        # THE FIRST. `pair_nets = None` fixes EVERY wire in the DSN so the router leaves
        # the pre-lay alone -- but `frozen` was still just the declared pairs, and
        # `frozen` is what the restore below re-lays. So the router obediently returned a
        # session with none of the pre-laid copper in it (a session reports what the
        # ROUTER did, and a fixed wire is not that) and the import deleted the lot.
        #
        # Measured on the optical board, north of the border only: 2952.6 mm of pre-laid
        # copper and 207 vias went in, 818.7 mm and 2 vias came out. The north half --
        # verified at 0 ratlines before the DSN was written -- came back with 127, and
        # every one of them read as "the router failed", which is the opposite of what
        # happened. It never touched them. We threw them away on import.
        #
        # So: everything that already has copper is frozen. That is exactly the set the
        # DSN just fixed, which is the invariant that was missing -- the two halves are
        # now derived from the same condition instead of happening to agree for pairs.
        frozen = {t.GetNetname() for t in board.GetTracks() if t.GetNetname()}
    if incremental:
        # Everything that HAS copper is frozen except the nets still unfinished.
        free = set(failing_nets(stem))
        have = {t.GetNetname() for t in board.GetTracks() if t.GetNetname()}
        frozen = have - free
        pair_nets = frozen
        print("  incremental: %d net(s) left free (%s), %d frozen"
              % (len(free), ", ".join(sorted(free)) or "-", len(frozen)))

    def _fix(m):
        if pair_nets is None or m.group(1) in pair_nets:
            _fix.n += 1
            return "(net %s)(type fix)" % m.group(1)
        return m.group(0)
    _fix.n = 0
    txt = re.sub(r"\(net ([^)]+)\)\(type route\)", _fix, txt)
    if frozen and not _fix.n:
        raise SystemExit(
            "no pre-laid wiring found for the declared differential pair(s) %s -- the "
            "pair is supposed to be generated before the router sees it, so either it "
            "was not laid or the DSN's wire syntax has changed. Routing on would hand "
            "the pair to freerouting, which does not know it is one."
            % ", ".join(sorted(pair_nets)))

    # ⚠ LAYER COSTS ARE A DEAD LEVER IN FREEROUTING 2.4.1, AND THE CODE THAT EMITTED
    # THEM IS GONE. The measurement that motivated it stands: in the MCU approach corridor
    # on the optical board, F.Cu carried 10.6% copper, In2.Cu 12.8% and B.Cu 4.6% -- the
    # bottom layer less than half the top, in the one region where the board ran out of
    # room. Pushing traffic down there would have cost a router setting instead of a
    # placement change. It cannot be done this way.
    #
    # Four experiments, and the first three all failed SILENTLY and DIFFERENTLY:
    #   1. autoroute_settings emitted as a sibling of (structure) -> the reader skips an
    #      unknown scope at the level it is reading, and the routed board came back
    #      BYTE-IDENTICAL. Read as "the lever does nothing" until the md5s matched.
    #   2. nested correctly -> 294 track segments instead of 2426 and 190 nets
    #      unconnected. AutorouteSettings.readScope applies its (autoroute)/(postroute)
    #      flags unconditionally when the scope closes, so omitting them means OFF. The
    #      block does not patch the defaults, it REPLACES them.
    #   3. the cost keywords are PLURAL, ..._trace_costs. Grepping the jar for the
    #      singular matched, because the plural contains it, so the check that was meant
    #      to confirm the spelling confirmed nothing.
    #   4. even a complete, correctly nested block in the DSN stops the router dead: a
    #      one-pass run writes a 254-byte session against 114378 bytes for the same DSN
    #      with the scope removed. The scope belongs in a .rules file passed with -dr, and
    #      there it routes normally.
    #
    # ⚠ AND THROUGH -dr, WHERE IT IS READ PROPERLY, THE TRACE COST STILL DOES NOTHING.
    # Two runs whose rules files differed ONLY in B.Cu's cost, 1.0 against 0.7, produced
    # sessions of identical size and identical per-layer wire length to the tenth of a
    # millimetre. What moved the earlier comparison was preferred_direction, which was
    # changed in the same file -- an experiment with two variables in it. Direction is a
    # real lever and cost is not:
    #     defaults (no rules file)      B.Cu  161.2 mm,  6.2% of wire, 238 vias
    #     F h, In1 v, In2 h, B v        B.Cu  134.6 mm,  4.9%,         255 vias
    #     F h,        In2 v, B h        B.Cu   49.6 mm,  2.0%,         228 vias
    # Every direction set tried is WORSE than freerouting's own defaults, on B.Cu share
    # and on total wire and vias alike, so there is nothing here to adopt. If someone
    # wants to try again, the channel is a .rules file via -dr, and the control to beat is
    # the default. The corridor still needs a placement answer.

    open(dsn, "w", encoding="utf-8").write(txt)
    if _fix.n:
        print("  froze %d pre-laid wire(s) as (type fix)%s" % (
            _fix.n, "" if pair_nets is None else " -- the declared pair(s)"))
    print("  router clearance %s um (fab rule %s um + %g um of rounding margin)"
          % ("/".join("%g" % (v + DSN_CLEAR_MARGIN_UM) for v in sorted(bumped)),
             "/".join("%g" % v for v in sorted(bumped)), DSN_CLEAR_MARGIN_UM))

    # ⚠ --dsn-only STOPS HERE, and it exists for the pin search rather than for people.
    # elec/pinsearch.py scores a string-to-pair assignment by routing the twenty analog
    # nets ALONE, which means it wants this function's DSN -- the real placement, the real
    # clearances, the real pre-laid copper -- and then its own filtered copy of it. Making
    # it re-implement the export would be a second copy of the rules to keep true.
    if dsn_only:
        print("  --dsn-only: stopping after the export")
        return dsn
    if not os.path.isfile(JAVA):
        raise SystemExit("no Java runtime at %s -- freerouting 2.x needs Java 25 (e.g. "
                         "Temurin JRE 25). Install one, or set JAVA to its java.exe" % JAVA)
    # -Djava.awt.headless=true: freerouting has no --no-gui flag and pops an
    # "Autorouter Confirmation" dialog on every run, which steals focus from
    # whoever is at the machine -- and this gets run many times per board.
    # Headless AWT suppresses it and the router works unchanged.
    # ⚠ -mt 1 BY DEFAULT: freerouting warns that its multi-threaded optimiser is broken
    # and generates clearance violations, and a board that cannot be manufactured is not
    # worth any amount of wall clock. The note that used to sit here also claimed single
    # threading "costs a fraction of a second on boards this size" -- true when the boards
    # were 20 parts, and badly false now: the optical board takes ten minutes, which is
    # the main brake on iterating it.
    # So `threads` is exposed per board to be MEASURED rather than assumed. Raising it is
    # only defensible if the result is both violation-free and reproducible, and both are
    # checkable.
    # ⚠ MEASURED 2026-09-23: ON THE OPTICAL BOARD THE STRATEGY CHANGES NOTHING AT ALL.
    # Five trees routed in parallel -- no strategy, -us Hybrid, -us Global, -us Greedy,
    # -is prioritized -- on the same placement. All five returned 9 unconnected and 0
    # violations, the same nine NETS, 1983 segments, and BYTE-IDENTICAL .ses files (one
    # md5 across all five). The flags reach freerouting: this function prints the command
    # and the logs show `-us Hybrid` and the rest going in. They are simply ignored by
    # this build.
    # That is not the old case-sensitivity bug below, which was real and is fixed -- it is
    # the same symptom from the opposite cause, and the note under it inherited a
    # conclusion nobody had actually tested. So: do NOT spend routes on the strategy on
    # this board. The claim that follows is kept because a different freerouting build may
    # honour it, but it is an expectation, not a measurement.
    # ⚠ THE OPTIMISER'S STRATEGY IS A BOARD-LEVEL CHOICE, not a global constant. It
    # changes which nets freerouting revisits and in what order, and on a board that is
    # one or two connections short that is exactly the lever that matters -- far more
    # than the pass count, which buys track length and not connectivity. It is only
    # worth exposing now: before the pipeline was reproducible, comparing two strategies
    # meant comparing two samples from a distribution wider than the difference.
    strat = json.load(open(stem + ".board.json", encoding="utf-8")).get("router")
    cmd = [JAVA, "-Djava.awt.headless=true", "-jar", JAR, "-de", dsn, "-do", ses,
           "-mp", str(passes), "-mt", str((strat or {}).get("threads", 1))]
    # ⚠ THE VALUES ARE CASE-SENSITIVE AND A WRONG ONE IS IGNORED IN SILENCE, which is
    # the worst way for an option to fail: a sweep of four strategies came back with four
    # identical boards -- 668 segments each -- and read as "strategy does not matter on
    # this board" when in fact none of them had been applied. Spelled as freerouting
    # spells them, checked here rather than trusted, and the command is printed so the
    # next person can see what actually ran.
    US = {"greedy": "Greedy", "global": "Global", "hybrid": "Hybrid"}
    IS = {"sequential": "Sequential", "random": "random", "prioritized": "prioritized"}
    for flag, key, table in (("-us", "updating", US), ("-is", "selection", IS)):
        want = (strat or {}).get(key)
        if not want:
            continue
        if want.lower() not in table:
            raise SystemExit("%s: router %s=%r is not one of %s"
                             % (os.path.basename(stem), key, want, sorted(table)))
        cmd += [flag, table[want.lower()]]
    if (strat or {}):
        print("  router strategy: %s" % " ".join(cmd[cmd.index("-mt") + 2:]))
    # ⚠ A TIMEOUT HERE MUST NOT LOOK LIKE A ROUTING RESULT. subprocess.run raises
    # TimeoutExpired, which a caller redirecting stderr will never see -- and the board
    # is then left exactly as it was, PLACED AND UNROUTED. Downstream that reads as
    # "the router could not connect anything", which sent me chasing a phantom
    # regression twice. Catch it and say what actually happened.
    # ROUTE_REUSE_SES=1 re-imports the session file already on disk instead of routing
    # again -- for recovering a run whose IMPORT failed after the router had finished.
    # Only valid when the placement and netlist are unchanged since that session.
    if os.environ.get("ROUTE_REUSE_SES") and os.path.isfile(ses):
        print("  ROUTE_REUSE_SES: importing the existing %s, not routing"
              % os.path.basename(ses))
        r = subprocess.CompletedProcess(cmd, 0, "", "")
    else:
      # ⚠ TIME THE ROUTER. "Did that change make it faster?" came up and
      # nothing recorded a duration -- not the finish log, not the DRC json --
      # so the only evidence was file mtimes. It matters most for fix_prelaid:
      # frozen copper is cheaper per evaluation (nothing to rip up) but it also
      # removes the room the router negotiates in, so it can go either way.
      _t0 = time.time()
      try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
      except subprocess.TimeoutExpired:
        raise SystemExit(
            "freerouting exceeded %d s on %s at %d passes and was killed. The board is "
            "UNROUTED -- it has not silently produced a bad result, it has produced "
            "none. Lower the pass count or raise `timeout` -- and note that passes DO "
            "buy connectivity on this board, so lowering them has its own cost."
            % (timeout, os.path.basename(stem), passes))
      print("  freerouting: %.1f s wall, %s pass(es)"
            % (time.time() - _t0, passes))
    tail = (r.stdout or "").strip().splitlines()[-6:]
    print("\n".join("  " + t for t in tail))
    if not os.path.isfile(ses):
        raise SystemExit("freerouting produced no session file\n" + (r.stderr or "")[-800:])

    # Import onto a FRESH copy: ImportSpecctraSES adds tracks to the board it is
    # given, so importing twice onto the same file stacks two routings.
    shutil.copyfile(pcb, stem + ".unrouted.kicad_pcb")
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise SystemExit("Specctra SES import failed")

    # PUT THE FROZEN COPPER BACK, BECAUSE THE SESSION FILE DOES NOT CARRY IT. This is
    # the half of `(type fix)` that a reasonable reading of Specctra misses, and it cost
    # a routing run to find: a SESSION file reports what the ROUTER did, and a fixed
    # wire is by definition not something the router did. freerouting therefore omits it
    # -- measured, 797 wires in the session and not one of them on either pair net --
    # and ImportSpecctraSES replaces the board's routing wholesale, so the frozen pair
    # was not preserved but DELETED. The board came back with the pair 11.62 mm shorter
    # and five of its eight unconnected items on USB_DP/USB_DM, which reads exactly like
    # a router that ran out of room and is nothing of the kind.
    #
    # The router still SAW the copper -- it routed around it as an obstacle, which is
    # what freezing is for -- so re-laying it here is geometrically consistent with
    # everything else in the session, not a patch over a conflict.
    #
    # ⚠ THIS IS ALSO THE MECHANISM FOR INCREMENTAL ROUTING, and the reason to get it
    # right rather than revert. "Freeze what already routed, re-run only the failures"
    # needs exactly these two halves: fix the wires in the DSN so the router leaves them
    # alone, and re-lay them here so they survive the import.
    if frozen:
        src = pcbnew.LoadBoard(stem + ".unrouted.kicad_pcb")
        back = 0
        for t in src.GetTracks():
            if t.GetNetname() not in frozen:
                continue
            net = board.FindNet(t.GetNetname())
            if net is None:
                raise SystemExit("frozen net %s is not on the board after import"
                                 % t.GetNetname())
            if t.GetClass() == "PCB_VIA":
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(t.GetPosition())
                v.SetWidth(t.GetWidth())
                v.SetDrill(t.GetDrill())
                v.SetViaType(t.GetViaType())
                v.SetNet(net)
                board.Add(v)
            else:
                k = pcbnew.PCB_TRACK(board)
                k.SetStart(t.GetStart())
                k.SetEnd(t.GetEnd())
                k.SetWidth(t.GetWidth())
                k.SetLayer(t.GetLayer())
                k.SetNet(net)
                board.Add(k)
            back += 1
        print("  re-laid %d frozen wire(s) the session file does not carry" % back)
    # CLAMP ANY TRACK THE ROUTER NECKED BELOW THE FAB FLOOR. Freerouting works in
    # its own units and rounds, so it lands a couple of segments at 0.125 against
    # JLCPCB's 0.127 minimum -- 2 microns under, but under. Widening a track can
    # only reduce clearance, never create an open, and the DRC pass afterwards is
    # what confirms the widening did not cost anything.
    floor = board.GetDesignSettings().m_TrackMinWidth
    necked = 0
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetWidth() < floor:
            t.SetWidth(floor)
            necked += 1
    if necked:
        print("  widened %d track(s) back up to the %.3f mm floor"
              % (necked, pcbnew.ToMM(floor)))

    # REFILL THE POURS. layout.py fills them at creation, before any routing
    # exists, so every via the router adds lands in copper that has no clearance
    # cut-out around it -- 164 violations on the first try, all of them a zone
    # against a via that was not there when it was filled.
    if board.Zones():
        # ⚠ AND BUILD CONNECTIVITY FIRST, exactly as layout.py does. The filler uses
        # the connectivity graph to decide which islands are attached to their net, and
        # a board loaded from a file and modified by script has no graph until asked.
        # Skipping it here is subtler than skipping it there, because the board ARRIVES
        # correctly poured: layout.py filled it properly, and this refill then silently
        # discards the lot. The optical board's F.Cu ground pour vanished at exactly
        # this line and took 74 pads with it -- the routed board came back WORSE than
        # before the pour existed, which is a confusing way to learn it.
        board.BuildConnectivity()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        # ⚠ AND CHECK THE STITCHES AGAIN HERE, NOT ONLY IN layout.py. At layout time the
        # plane is poured around 60 parts and every stitch via lands in copper. THIS
        # refill pours it around those parts plus 700 routed tracks, and the plane that
        # results is a different shape -- so a via that was in the plane before routing
        # can be in a hole after it. Every board passes the check in layout.py and
        # output_panel failed it here, which is exactly why it has to run twice.
        if layout._check_stitches_landed(board, notes):
            n_moved = layout.rescue_stray_stitches(board, notes)
            if n_moved:
                # moving copper changes the pour that was just computed, so pour again
                board.BuildConnectivity()
                pcbnew.ZONE_FILLER(board).Fill(board.Zones())
                print("    moved %d of them into the plane and re-poured" % n_moved)
            if layout._check_stitches_landed(board, notes):
                print("    (the rest have nowhere to go: move the part or except the "
                      "pad -- another routing run will not help)")
    # ⚠ THE ROUTER LEAVES SAME-PART GAPS, and they are cheap to close once it has
    # finished. Done here rather than before routing because before routing the same
    # idea is a constraint that costs more than it buys -- see link_same_part_gaps.
    # ⚠ SNAP THE HAIRLINES FIRST. A gap of a couple of microns cannot be repaired by
    # laying copper across it -- the segment that results is itself degenerate and the
    # clean-up below removes it again, which is a loop the logs do not show. Move the
    # endpoint instead; see snap_hairline_gaps.
    n_snap = layout.snap_hairline_gaps(board)
    if n_snap:
        print("  snapped %d hairline gap(s) shut (no copper added)" % n_snap)
        board.BuildConnectivity()
    # ⚠ AND THE LAYER CHANGES THE ROUND TRIP DROPPED. Two tracks of one net ending at
    # the same point on DIFFERENT layers is a via that went missing, not a gap -- no
    # amount of re-routing recovers it and no copper can bridge it. See add_missing_vias.
    n_via = layout.add_missing_vias(board)
    if n_via:
        print("  dropped in %d via(s) where a net changed layer with nothing to carry it"
              % n_via)
        board.BuildConnectivity()
    # ⚠ AND TAKE BACK THE VIAS THE ROUTER DRILLED INTO THROUGH-HOLE PADS. Freerouting
    # changes layer on a THT pad for free, which is electrically true and leaves a drill
    # inside an already-drilled hole. DRC grades it holes_co_located at severity WARNING,
    # so finish.py's ERROR count stays at zero and nobody looks. See drop_redundant_pth_vias
    # for why removing them is safe HERE and was not before routing.
    layout.drop_redundant_pth_vias(board)
    # ⚠ WITH THE INNER LAYER, WHICH THIS CALL LEFT OUT. link_close_gaps takes `inner` and
    # falls back to a via hop when no surface path exists; omitting it silently disabled
    # that half of the routine, so any pair separated by copper on its own layer was
    # abandoned even where a hop had room. Measured at the four +3V3D pairs this board
    # still fails on: 0.86, 1.03, 1.11 and 1.36 mm of via room against the 0.45 a 0.6 via
    # needs, and not one of them was tried.
    # ⚠ AND HOW FAR IT MAY REACH IS A BOARD'S OWN BUSINESS. The 5 mm default is a
    # sensible floor, not a law: the optical board came out of a route with I2C2_SDA
    # 5.85 mm short of the spine it was heading for -- the router got that close and
    # stopped -- and 0.85 mm of policy was the only thing between it and a finished net.
    # Raising it is free in the way the whole routine is free: this runs AFTER routing,
    # so the only pairs it can act on are ones already left unconnected, and there is no
    # counterfactual route being denied. `clear()` still refuses anything that would not
    # pass DRC, so the cap is on ambition, not on safety.
    n_link = layout.link_close_gaps(board, layout._outline_pts(notes),
                                   same_part_only=False,
                                   max_mm=(notes or {}).get("repair_mm", 5.0),
                                   inner=layout._local_inner(notes))
    if n_link:
        print("  joined %d same-net pad pair(s) the router left in separate islands"
              % n_link)

    # ⚠ DELIBERATE COPPER GOES IN HERE, NOT IN layout.py, AND THE DIFFERENCE IS THE
    # WHOLE POINT. The optical board's last net, +3V3A at U2 pad 4, is closed by one via
    # and two short tracks -- that geometry was searched and it works. Laid BEFORE
    # routing it also cost FIVE analog nets, 1 unconnected to 5, because 76 other nets
    # then had to plan around it. Laid here it closes the same gap and disturbs nothing,
    # for exactly the reason the same-part gap repair above is done here: before routing
    # the same idea is a constraint that costs more than it buys.
    #
    # A re-search confirmed the placement was not the problem. Scored by how many analog
    # nets sit within 1.2 mm of the path, the best of all 2638 legal sites touches SIX --
    # and so does the one already chosen. There is no quiet corner in that corridor, so
    # no amount of re-siting helps and the timing is the only lever left.
    #
    # These are repairs, not hints: they are applied after the router has finished and
    # are never visible to it.
    # ⚠ AND THE BRING-UP PADS GO IN HERE, FOR THE SAME REASON THE REPAIRS DO. A bare pad
    # on a rail the router has already finished needs no route at all -- it is placed ON
    # that rail's copper -- but given to the router BEFORE routing it is an obstacle, and
    # six of them cost the optical board a net in four consecutive runs, always at the USB
    # PHY, once even on a rail whose own pad had been removed. See layout.build's note on
    # post_route_refs: the netlist and the CAD carry them, the DSN does not.
    #
    # THE SITE IS SEARCHED AGAINST THE FINISHED BOARD, not chosen: scratchpad/padsite.py
    # sweeps a grid for a circle that clears every segment, via, pad, COURTYARD (a pad
    # under a part is legal and unprobeable) and the outline, and that already sits on its
    # own net's copper so no copper has to be added. What is left for DRC to check is a
    # clearance, which is the check that caught every earlier version of this.
    _post = list(notes.get("post_route_refs", ()))
    if _post:
        _comps, _nl = layout.read_netlist(stem + ".net")
        # ⚠ EVERY PAD OF EVERY POST-ROUTE PART, NOT ONE PER REF. The first version of
        # this kept a single (net, pad) per reference, which is true of a test pad and
        # false of a resistor: the SHDNZ pull-ups have pad 1 on a brand-new net and pad 2
        # on +3V3D, and one-per-ref silently dropped whichever came second.
        _of = {}
        for _nm, _nodes in _nl.items():
            for _r, _pn in _nodes:
                if _r in _post:
                    _of.setdefault(_r, []).append((_nm, str(_pn)))
        _newnets = set(notes.get("post_route_nets", ()))
        for _ref in _post:
            _fp = layout._load_footprint(_comps[_ref][0])
            board.Add(_fp)
            _fp.SetReference(_ref)
            _fp.SetValue(_comps[_ref][1])
            _fp.Value().SetVisible(False)
            _x, _y, _rot = notes["placements"][_ref]
            _fp.SetPosition(layout._to_board(_x, _y))
            _fp.SetOrientationDegrees(_rot)
            if notes.get("anchor") == "courtyard":
                layout._anchor_on_courtyard(_fp, layout._to_board(_x, _y))
            else:
                layout._anchor_on_pads(_fp, layout._to_board(_x, _y))
            if notes.get("refs_on_fab"):
                _fp.Reference().SetLayer(pcbnew.F_Fab)
            for _nm, _pn in _of[_ref]:
                # ⚠ A NET MAY BE POST-ROUTE TOO, AND THAT IS WHAT KEEPS THE DSN IDENTICAL
                # WHERE IT CAN BE. A pad on a rail joins a net the router has already
                # finished; a converter's SHDNZ pin does not, because its net is new. So
                # layout skips the nets named in post_route_nets -- those pins carry no net
                # pre-route, which is what a no-connect carried -- and the net is built
                # here, over every node it has, including the ones on parts that were
                # placed normally.
                _net = board.FindNet(_nm)
                if _net is None:
                    if _nm not in _newnets:
                        raise SystemExit(
                            "post-route pad %s.%s wants net %s, which is not on the "
                            "board. A net that does not exist pre-route has to be "
                            "declared in post_route_nets, so that layout skips it "
                            "deliberately rather than by accident." % (_ref, _pn, _nm))
                    _net = pcbnew.NETINFO_ITEM(board, _nm)
                    board.Add(_net)
                    _by = {_f.GetReference(): _f for _f in board.GetFootprints()}
                    for _r2, _p2 in _nl[_nm]:
                        if _r2 == _ref or _r2 not in _by:
                            continue          # placed later in this same loop
                        for _pad in _by[_r2].Pads():
                            if _pad.GetNumber() == str(_p2):
                                _pad.SetNet(_net)
                _hit = 0
                for _pad in _fp.Pads():
                    if _pad.GetNumber() == _pn:
                        _pad.SetNet(_net)
                        _hit += 1
                if not _hit:
                    raise SystemExit("post-route part %s has no pad %s" % (_ref, _pn))
        # ⚠ AND A SECOND PASS, BECAUSE A POST-ROUTE NET CAN JOIN TWO POST-ROUTE PARTS.
        # SHDNZ<k> is a converter pin, a pull-up and a pad: when the pull-up created the
        # net, the pad's footprint did not exist yet. Whichever order the refs come in, one
        # of them would be missed -- so every node is re-asserted once they are all placed.
        _by = {_f.GetReference(): _f for _f in board.GetFootprints()}
        for _ref in _post:
            for _nm, _pn in _of[_ref]:
                _net = board.FindNet(_nm)
                for _r2, _p2 in _nl[_nm]:
                    for _pad in _by[_r2].Pads():
                        if _pad.GetNumber() == str(_p2):
                            _pad.SetNet(_net)
        board.BuildConnectivity()
        _resite_post_pads(board, set(_post), notes)
        print("  placed %d part(s)/pad(s) AFTER routing, invisible to the router: %s"
              % (len(_post), ", ".join(_post)))
        board.BuildConnectivity()

    _nets = {n.GetNetname(): n for n in board.GetNetInfo().NetsByName().values()}
    for _rv in notes.get("repair_vias", []):
        assert _rv[0] in _nets, "repair_vias names unknown net %r" % (_rv[0],)
        layout._add_via(board, _nets[_rv[0]], _rv[1], _rv[2],
                        _rv[3] if len(_rv) > 3 else 0.3, _rv[4] if len(_rv) > 4 else 0.6)
    for _rt in notes.get("repair_tracks", []):
        assert _rt[0] in _nets, "repair_tracks names unknown net %r" % (_rt[0],)
        layout._add_track(board, _nets[_rt[0]], _rt[1], _rt[2], _rt[3])
    if notes.get("repair_vias") or notes.get("repair_tracks"):
        print("  laid %d deliberate via(s) and %d track(s) AFTER routing"
              % (len(notes.get("repair_vias", [])), len(notes.get("repair_tracks", []))))
        board.BuildConnectivity()

    # ⚠ THE ROUTER'S LEAVINGS GO LAST, AFTER EVERY PASS THAT CAN ADD A VIA. Vias
    # attached to nothing, and same-net vias drilled so close that the laminate between
    # them breaks out, are both DRC WARNINGS -- invisible to the error count. Called
    # BEFORE link_close_gaps this missed a pair outright, because link_close_gaps lays
    # vias of its own and one of them landed 0.50 mm from an existing GND stitch: the
    # pass cannot see copper that does not exist yet, and every earlier slot in this
    # sequence has something after it that adds more. So it runs at the end.
    # ⚠ COUNTED BEFORE tidy_router_vias, WHICH REMOVES. 2026-09-21: the count used to sit
    # after it, and on the optical board tidy's removals left the track container in the
    # SWIG state described below -- GetTracks() raised and threw away a 52-minute route.
    n = len(list(board.GetTracks())) - layout.drop_redundant_pad_vias(board, notes)
    layout.tidy_router_vias(board, notes)
    # ⚠ COUNT BEFORE REMOVING. board.Remove() leaves the track container in a state
    # where GetTracks() raises -- the same SWIG ownership hazard that made fp.Remove()
    # corrupt the footprint IO plugin earlier in this file's history. The rule that
    # comes out of both: take every measurement you need from a board BEFORE deleting
    # anything from it, and delete last.
    n_junk = layout.drop_degenerate(board)
    if n_junk:
        # the Specctra round trip rounds, and rounding leaves sub-micron fragments
        print("  dropped %d degenerate track fragment(s) from the import" % n_junk)
        n -= n_junk

    # ⚠ POUR AGAIN, BECAUSE THE REPAIRS ABOVE ADDED COPPER AFTER THE LAST POUR. The
    # zones were last filled before the repair block; snap/add_missing_vias/link then
    # put down vias and tracks, and a zone does not know to clear around copper that
    # arrived after it was computed. The result is a via sitting in un-cleared pour --
    # which DRC reports as a clearance AND a hole-clearance violation against the zone,
    # and which looks like a badly placed via rather than a stale pour.
    # Measured: five violations on the optical board, four of them this, from two vias.
    if board.Zones():
        board.BuildConnectivity()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # ⚠ AND ONLY NOW CAN THE STRANDED COPPER BE FOUND. _check_stitches_landed runs in
    # layout.py ~140 lines BEFORE the first pour and can only warn; even the retry above
    # gives up on vias with "nowhere to go". This pass runs after tidy AND after the
    # final pour, when the plane is a fact, and lays one short segment from each stranded
    # track to real plane copper -- but only where the path crosses nothing, because a
    # short is worse than the floating stub it would replace.
    # ⚠ IT MUST BE HERE, NOT AT THE layout.py POUR. Put there first, it printed nothing
    # on a board it then left at 1 unconnected: that pour happens during PLACEMENT, when
    # the board has no tracks at all, so there is nothing stranded yet to find.
    board.Save(pcb)
    # ⚠ CANONICALISE THE ROUTED BOARD TOO, for the same reason layout.py does it --
    # and the reason is now MEASURED rather than argued. Two independent runs of the
    # whole pipeline lay 2,299 copper items that are byte-identical: freerouting is
    # deterministic given deterministic input, which is what makes "run the script" a
    # promise rather than a hope. All that separated the two files was 12,268 lines of
    # random UUID. Left alone it would put noise in every diff of a routed board and
    # make "did this change anything?" unanswerable at exactly the point where the
    # answer matters most.
    layout._canonical_uuids(pcb)
    print("%s: %d track segments + vias imported" % (os.path.basename(pcb), n))
    return pcb


if __name__ == "__main__":
    _p = None
    for _a in sys.argv[2:]:
        if _a.startswith("--passes="):
            _p = int(_a.split("=", 1)[1])
    route(os.path.abspath(sys.argv[1]), passes=_p,
          incremental="--incremental" in sys.argv[2:],
          dsn_only="--dsn-only" in sys.argv[2:])
    # ⚠ LEAVE WITHOUT TEARING DOWN THE INTERPRETER. pcbnew's SWIG bindings hand back
    # objects they have no destructor for -- every run says so, a dozen times, about
    # PCB_TRACK and ZONE_FILLER -- and with enough of them the shutdown itself aborts.
    # It cost a whole experiment to find: route.py returned non-zero on a board it had
    # just written correctly, no traceback, the segments imported and the file on disk,
    # and finish.py quite reasonably treated that as a failed step and threw the pass
    # away. The board was never in question; only the exit was.
    #
    # ⚠ THIS DOES NOT HIDE REAL FAILURES, which is the only reason it is acceptable. An
    # exception from route() propagates and never reaches this line, so anything that
    # actually goes wrong still exits non-zero with its traceback. Only a CLEAN return
    # gets here, and all this says is that a clean return should be a clean exit.
    # The flush is not optional: os._exit skips it, and finish.py reads this stdout
    # through a pipe, so the last lines would vanish.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
