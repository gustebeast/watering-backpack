"""Reconnect copper the zone fill stranded from its own plane. One stage, one process.

⚠ WHY THIS IS A SEPARATE SCRIPT AND NOT THREE LINES AT THE END OF route.py. It was three
lines at the end of route.py first, and it could not run there: by that point route.py has
called board.Remove() (drop_degenerate), and after a removal pcbnew hands back raw
SwigPyObjects -- first board.Zones() had no GetNetname, and then a FRESH pcbnew.LoadBoard()
in the same interpreter had no BuildConnectivity either. The damage is to the process, not
to the one board, so no amount of reloading inside route.py escapes it. finish.py already
runs every stage as its own subprocess for exactly this family of reason; this is one more.

It also must run AFTER route.py rather than inside layout.py's pour: that pour happens
during PLACEMENT, when the board has no tracks at all and nothing is stranded yet.
"""
import json
import os
import sys

import layout
import pcbnew
import noassert                                      # noqa: F401,E402  (no GUI dialogs)


def main(stem):
    pcb = stem + ".kicad_pcb"
    if not os.path.isfile(pcb):
        return 0
    try:
        notes = json.load(open(stem + ".board.json", encoding="utf-8"))
    except Exception:
        return 0
    if not notes.get("zones"):
        return 0
    board = pcbnew.LoadBoard(pcb)
    # ⚠ REFILL THE POUR FIRST, BECAUSE NOTHING ELSE EVER DID, AND THE REPAIRS NEED IT.
    # The pour is computed in layout.py DURING PLACEMENT, when the board has no tracks at all
    # (this file's own header says so). route.py then lays the post-route repair tracks into a
    # fill that predates them, so a repair reads as a clearance violation against the pour even
    # when it is perfectly placed -- optical's +3V3D dog-leg measured 0.4892 and 0.0225 mm
    # against a 0.5000 mm zone rule and was very nearly abandoned as impossible.
    # Refilled, the pour retreats around the new copper and the SAME dog-leg is clean: DRC goes
    # from 4 unconnected items to 2 with violations IDENTICAL to the baseline, zero clearance.
    # ⚠ AND THE ORDER IS THE POINT. This script exists to reconnect copper the fill STRANDED,
    # so it has to run after the fill it is cleaning up after -- and until now it cleaned up
    # after a fill computed before the tracks existed. Refill, then reconnect what the NEW fill
    # stranded. Doing it the other way round reconnects against a fill that is about to change.
    n_zones = len(board.Zones())
    if n_zones:
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.Save(pcb)
        board = pcbnew.LoadBoard(pcb)      # a fresh handle: Fill+Save then reuse is asking for
                                           # the SwigPyObject damage this file was split out for
        print("  refilled %d zone(s) around the post-route copper" % n_zones)
    laid = layout.repair_plane_orphans(board, notes)
    if laid or n_zones:
        board.Save(pcb)
        # the repair added copper after route.py canonicalised, so do it again --
        # otherwise the repaired tracks carry random UUIDs and every diff of a
        # routed board picks up noise route.py went to trouble to remove.
        layout._canonical_uuids(pcb)
    return laid


if __name__ == "__main__":
    sys.exit(0 if main(os.path.abspath(sys.argv[1])) >= 0 else 1)
