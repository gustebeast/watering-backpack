"""Where the fab's own footprint sits against ours, part by part.

THE PLACEMENT FILE IS WRITTEN IN OUR FOOTPRINTS' FRAMES AND READ IN THE FAB'S (found on a
real order page, 2026-10-06). Each of our footprints has an origin and a zero angle; the
fab places ITS library footprint for the same part number, which has its own of each.
Where the two differ the part previews off its pads:

  * ORIGIN. A through-hole header's KiCad origin is pin 1 and the fab's is the middle of
    the row: a 1x20 header previewed 24 mm off its holes.
  * ANGLE. Zero is whichever way the footprint's author drew it. 90 / 180 / 270 apart is
    common for ICs, connectors and anything on tape.

Neither is a convention that can be looked up. Both can be MEASURED: put the fab's pads
over ours, by pad number, and the rotation and shift that make them coincide are the
correction. That is all this module does.

    frames  = the table: {"<LCSC code>|<our footprint name>": {"rot", "dx", "dy", ...}}
    derive  = read the fab's pads for a part and fit them (network; run when parts change)
    apply   = rewrite a placement file's rows with the table (offline; every package)

THE TABLE HOLDS OUR MEASUREMENT, NOT THE FAB'S LIBRARY: three numbers per part. The pad
positions they are measured from are read at derive time and not kept.
Source of those pad positions: JLCEDA/EasyEDA Official Library -- https://lceda.cn/ and
https://easyeda.com . The same statement is written into every table this module saves.

WHAT A PAD FIT CANNOT SEE, and what is done about it:
  * A part whose pad grid is the same turned half round, and whose BODY is to one side --
    a right-angle two-row header. The fab's footprint may number the rows the other way;
    fitted by number the holes agree and the body points into the board. Nothing in the
    pads says so. The project declares it (`turn`: code -> degrees, with the reason) after
    seeing it in the fab's previewer, and the angle is turned about the pads' own centre.
  * A part the fab's library numbers differently from ours (the fit's residual is large).
    It is left as KiCad wrote it and LISTED, so a person looks at exactly those.
  * Parts on the BACK of the board are measured in the part's own frame (KiCad flips a
    footprint top to bottom, so its y is negated before the fit); the angle correction
    is subtracted rather than added, and the result is turned half round, because the
    fab turns a part over left to right where KiCad turns it top to bottom. Seen in the
    fab's previewer for parts whose KiCad angle and frame rotation are 0 or 180 apart;
    a back-side part where they are 90 apart has not been on an order page yet, and the
    report says "back side" beside every such part so it is looked at.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.request

SOURCE = ("pad positions read from the JLCEDA/EasyEDA Official Library "
          "(https://lceda.cn/ , https://easyeda.com); this file keeps only the rotation "
          "and offset measured from them")
# ⚠ THE OLD ENDPOINT IS DEAD, AND IT DIED SILENTLY FOR EVERY PROJECT.
# "https://easyeda.com/api/products/%s/components" now returns 403 from CloudFront
# ("Request blocked") for every code, from urllib and from a browser alike, with or
# without a User-Agent or a Referer -- an edge block rather than a bot check. Every
# derive() run against it reports "lookup failed" on every part and then writes an
# EMPTY table, which reads as "nothing to measure" rather than as a failure. The
# watering-backpack board sat with all 24 of its orientation-critical parts
# unmeasured and a report telling the reader to run the very command that could not
# work.
API_SEARCH = ("https://pro.easyeda.com/api/eda/product/search"
              "?keyword=%s&needAggs=false&currPage=1&pageSize=20")
API_COMPONENT = "https://pro.easyeda.com/api/components/%s"
UNIT = 0.0254                     # the pro library's unit is 1 mil (the old one was 10)
FIT_MM = 0.45                     # a pad further than this from its twin is not the same land


def _get_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; cadkit fab_frames)",
        "Accept": "application/json, text/plain, */*"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def footprint_uuid(code):
    """The fab library's footprint uuid for an LCSC code, or None.

    The search returns near matches as well as the code asked for, so the row is
    picked by its own "Supplier Part" attribute rather than by position -- asking for
    C20526 and silently measuring whatever ranked first is exactly the kind of wrong
    answer this module exists to prevent."""
    d = _get_json(API_SEARCH % code)
    for prod in ((d.get("result") or {}).get("productList") or []):
        attrs = (prod.get("device_info") or {}).get("attributes") or {}
        if attrs.get("Supplier Part") == code and attrs.get("Footprint"):
            return attrs["Footprint"]
    return None


def fetch_pads(code):
    """[(pad number, x, y)] in mm, y up, about the fab footprint's own origin.

    y is NOT negated here, unlike the old reader -- see the module docstring's note
    on how that was measured. The rows are newline-separated JSON arrays and a pad is
    ["PAD", id, _, "", layer, number, x, y, rot, ...]."""
    uuid = footprint_uuid(code)
    if not uuid:
        return []
    d = _get_json(API_COMPONENT % uuid)
    out = []
    for line in ((d.get("result") or {}).get("dataStr") or "").splitlines():
        line = line.strip()
        if not line.startswith('["PAD"'):
            continue
        try:
            f = json.loads(line)
        except ValueError:
            continue
        if len(f) < 8 or f[5] in (None, ""):
            continue
        out.append((str(f[5]), float(f[6]) * UNIT, float(f[7]) * UNIT))
    return out


def _mean(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def by_number(pads):
    """{number: centre of every pad carrying it}."""
    g = {}
    for n, x, y in pads:
        g.setdefault(str(n), []).append((x, y))
    return {n: _mean(v) for n, v in g.items()}


def local_pads(fp):
    """Our footprint's numbered pads in ITS frame: mm, y up, rotation taken out, and the
    flip taken out too for a part on the back (KiCad mirrors those top to bottom)."""
    import pcbnew
    th = math.radians(fp.GetOrientationDegrees())
    o = fp.GetPosition()
    out = []
    for p in fp.Pads():
        n = p.GetNumber()
        if not n or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            continue
        dx, dy = (p.GetPosition().x - o.x) * 1e-6, -(p.GetPosition().y - o.y) * 1e-6
        ux = dx * math.cos(-th) - dy * math.sin(-th)
        uy = dx * math.sin(-th) + dy * math.cos(-th)
        out.append((n, ux, -uy if fp.IsFlipped() else uy))
    return out


def fit(ours, theirs):
    """(residual mm, rot deg, dx, dy, pads used): theirs turned `rot` and moved (dx, dy)
    lies on ours. Rotation is one of the four a placement machine and a footprint differ
    by. None when fewer than two pad numbers are shared."""
    a, b = by_number(ours), by_number(theirs)
    common = sorted(n for n in b if n in a)
    if len(common) < 2:
        return None
    best = None
    for rot in (0, 90, 180, 270):
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        turned = {n: (b[n][0] * c - b[n][1] * s, b[n][0] * s + b[n][1] * c) for n in common}
        ma, mt = _mean([a[n] for n in common]), _mean([turned[n] for n in common])
        dx, dy = ma[0] - mt[0], ma[1] - mt[1]
        err = max(math.hypot(a[n][0] - turned[n][0] - dx, a[n][1] - turned[n][1] - dy)
                  for n in common)
        if best is None or err < best[0] - 1e-9:
            best = (err, rot, dx, dy, len(common))
    return best


def key(code, fp_name):
    return "%s|%s" % (code, fp_name)


def load(path):
    if not os.path.isfile(path):
        return {"_source": SOURCE, "frames": {}}
    with open(path, encoding="utf-8") as f:
        t = json.load(f)
    t.setdefault("frames", {})
    return t


def save(path, table):
    table["_source"] = SOURCE
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(table, f, indent=1, sort_keys=True)
        f.write("\n")


def symmetric(fp):
    """A two-pad chip part both conventions lay along its pad axis: a half turn cannot
    change it, and its origin is its centre in every library."""
    import re
    import pcbnew
    pads = [q for q in fp.Pads() if q.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]
    ref, name = fp.GetReference(), fp.GetFPIDAsString()
    return bool(len({q.GetNumber() for q in pads}) <= 2
                and not re.match(r"^CP", ref)
                and not re.search(r"Polarized|CP_|SOD|SMA|SMB|SMC|LED|Diode|Crystal",
                                  name, re.I)
                and re.match(r"^(R|C|L|FB|TP|JP)[A-Za-z]*[0-9]", ref))


def derive(pcb, code_of, table, refresh=False, log=print, pads_from=fetch_pads):
    """Measure every coded, non-symmetric footprint on `pcb` that the table lacks.
    `code_of(value, footprint id)` is the project's part-number lookup; `pads_from(code)`
    returns the fab's pads (the library by default; a project that already holds them
    passes its own). Returns the number of entries written."""
    import pcbnew
    board = pcbnew.LoadBoard(pcb)
    n = 0
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        if symmetric(fp) or not [p for p in fp.Pads() if p.GetNumber()]:
            continue
        name = str(fp.GetFPID().GetLibItemName())
        code = code_of(fp.GetValue(), fp.GetFPIDAsString())
        if not code:
            continue
        k = key(code, name)
        if k in table["frames"] and not refresh:
            continue
        try:
            theirs = pads_from(code)
        except Exception as exc:                   # the library is not ours; say so
            log("  %-8s %-10s lookup failed: %r" % (fp.GetReference(), code, exc))
            continue
        time.sleep(0.2)
        got = fit(local_pads(fp), theirs) if theirs else None
        if got is None:
            table["frames"][k] = {"fit": False, "why": "the fab's library has no "
                                  "footprint with two of our pad numbers"}
        else:
            err, rot, dx, dy, used = got
            table["frames"][k] = {"fit": err <= FIT_MM, "rot": rot, "dx": round(dx, 4),
                                  "dy": round(dy, 4), "err": round(err, 3), "pads": used,
                                  "read": time.strftime("%Y-%m-%d")}
            if err > FIT_MM:
                table["frames"][k]["why"] = ("its pads are up to %.2f mm from ours at the "
                                             "best of the four rotations" % err)
        e = table["frames"][k]
        log("  %-8s %-10s %-40s %s" % (fp.GetReference(), code, name[:40],
            "rot %3d  origin %+.2f %+.2f  (%d pads, %.2f mm)"
            % (e["rot"], e["dx"], e["dy"], e["pads"], e["err"]) if e.get("fit")
            else "NOT FITTED: " + e["why"]))
        n += 1
    return n


def apply(pcb, rows, code_of, table, turn=None):
    """Correct placement rows [[ref, x, y, layer, rot], ...] in place.

    Returns (corrected, unchecked): corrected = [(ref, value, code, old rot, new rot,
    origin shift mm, note)], unchecked = [(ref, value, footprint, why)] for every
    non-symmetric part left exactly as KiCad wrote it."""
    import pcbnew
    turn = turn or {}
    board = pcbnew.LoadBoard(pcb)
    by_ref = {r[0]: r for r in rows}
    corrected, unchecked = [], []
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        if ref not in by_ref or symmetric(fp):
            continue
        name = str(fp.GetFPID().GetLibItemName())
        val = fp.GetValue()
        code = code_of(val, fp.GetFPIDAsString())
        e = table["frames"].get(key(code, name)) if code else None
        if not e:
            unchecked.append((ref, val, name, "no part number" if not code else
                              "not measured: run fab_package.frames([board])"))
            continue
        if not e.get("fit"):
            unchecked.append((ref, val, name, e.get("why", "not fitted")))
            continue
        row = by_ref[ref]
        k = math.radians(fp.GetOrientationDegrees())
        back = fp.IsFlipped()
        dx, dy = e["dx"], (-e["dy"] if back else e["dy"])
        sx = dx * math.cos(k) - dy * math.sin(k)
        sy = dx * math.sin(k) + dy * math.cos(k)
        old = float(row[4])
        extra, why = turn.get(code, (0, ""))
        # BACK SIDE: the frame rotation is subtracted (the part is seen from behind) AND the
        # whole angle is turned half round. KiCad turns a footprint over top to bottom and
        # the fab's placement turns it over left to right; the two differ by a half turn.
        # Seen on a real order page 2026-10-06: without the half turn every connector on
        # an all-back-side board previewed with its body where its mouth should be.
        new = ((old - (e["rot"] + extra) + 180.0) if back
               else (old + e["rot"] + extra)) % 360.0
        row[1], row[2] = "%.6f" % (float(row[1]) + sx), "%.6f" % (float(row[2]) + sy)
        row[4] = "%.6f" % new
        if e["rot"] or extra or math.hypot(sx, sy) > 0.05:
            note = [("turned %d by hand: %s" % (extra, why))] if extra else []
            if e.get("by"):
                note.append(e["by"].split(":")[0] + "-entered frame")
            if back:
                note.append("back side")
            corrected.append((ref, val, code, old % 360.0, new, math.hypot(sx, sy),
                              "; ".join(note)))
    return corrected, unchecked
