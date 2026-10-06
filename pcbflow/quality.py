"""The standard quality pass for a ROUTED board. The rules live in cadkit/PCB_QUALITY.md.

    "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/quality.py elec/out/<board>

DRC proves the copper matches the netlist and clears itself. It cannot say whether the
board is any GOOD: whether a supply path necks down, whether an IC has a capacitor at its
pins, whether a pair is matched, whether a pinout was read off the right page. This is the
pass for those, and it is the SAME pass for every board in every project -- so a lesson
learned ordering one board is checked on all the boards after it.

Two kinds of rule, both listed in PCB_QUALITY.md:

  A<n>  AUTOMATED -- a function in this file. Reports ok / FAIL / WAIVED.
  M<n>  MANUAL    -- a check only a reader can do. Reports signed / OPEN. The designer
                     (a person or an LLM) does the check and records WHAT THEY LOOKED AT
                     in the board's notes; an unsigned item stays OPEN on every run.

What the board declares, in BOARD_NOTES["quality"] (all optional, all documented in
PCB_QUALITY.md): power_paths, decoupling, pinouts, manual, waive, power_nets, not_power,
unmatched_ok, copper_oz, inner_oz, temp_rise_c.

Returns (and exits with) the number of FAILs; OPEN manual items are counted separately and
printed. Writes <stem>.quality.json with every result. A board is quality-clean at
`0 FAIL, 0 OPEN`.

ADDING A RULE: see "Adding a learning" in PCB_QUALITY.md. An automated rule is a function
here decorated with @rule("A<n>"); a manual rule is one line in the markdown. This file
refuses to run if the two disagree about which automated rules exist.
"""
from __future__ import annotations

import collections
import heapq
import io
import json
import math
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(os.path.dirname(HERE), "PCB_QUALITY.md")
MM = pcbnew.ToMM

GROUND = re.compile(r"^(GND|VSS|[A-Z0-9]+_GND|[AD]GND|GND[A-Z0-9_]*)$")
# A net that LOOKS like a supply rail by name. Override with quality.power_nets (an exact
# list) or remove false positives with quality.not_power.
POWER = re.compile(r"^(\+.+|\d+V\d*[A-Z0-9_]*|V(CC|DD|IN|BUS|BAT|SYS|MOT|PP)[A-Z0-9_]*|VM|"
                   r"[A-Z0-9]+_PWR|PWR_(?!GND)[A-Z0-9_]+)$")
# ...and a net NAMED as not connected is not a rail, whatever else its name says
NOT_CONNECTED = re.compile(r"(^|_)(NC|SPARE|NOT_CONNECTED)(_|$)", re.I)
# The two halves of a differential pair, by suffix.
PAIR = ((r"(.*)_DP$", r"\1_DM"), (r"(.*)_P$", r"\1_N"), (r"(.*)D\+$", r"\1D-"),
        (r"(.*)\+$", r"\1-"))

RULES = {}          # id -> function(ctx) -> [(subject, ok, text)]
# What to DO about a failing rule, printed once under its findings.
HINT = {
    "A1": "declare quality.power_paths; widen with net_widths / declared tracks / a pour",
    "A2": "move or add a bypass capacitor beside the pin. PCB_QUALITY.md A2, 'Deciding a "
          "failure', lists the only cases where a pin may be exempted instead",
    "A3": "add a `match` group, or quality.unmatched_ok with the bit-time arithmetic",
    "A5": "fix the label, or list a deliberate one in quality.single_pin_ok",
    "A6": "one 5.1 k 1% from EACH CC pin to ground on a device port",
    "A7": "one pull-up pair per bus: say where it is, and that it is the only one",
    "A8": "connect the pad as the datasheet says and put vias in it",
    "A10": "keep 1-10 uF directly on VBUS; bulk goes behind a load switch or soft-start",
    "A11": "write each value one way throughout the generator",
    "A12": "move the hole, widen the ring or the track, enlarge the text -- or, if the "
           "order really uses another fab or a costlier option, state its numbers in "
           "quality.fab with where they were read",
    "A9": "move the crystal and its load capacitors up against the oscillator pins",
    "A13": "if the board is wrong, fix the generator (look for an index left over from "
           "another loop); if the declaration is, correct quality.unconnected / "
           "quality.net_groups to what the design MEANS, never to what was built",
    "A4": "read every pin against the maker's datasheet AND the footprint's pad numbering "
          "(top vs bottom view; a connector from its MATING face), then cite document and "
          "page in quality.pinouts -- by ref, value or footprint",
}


# HARD findings: ones no board has a good reason to keep. A waiver written for one is
# IGNORED (and said so); the design or the declaration changes instead. Everything else is
# SOFT: the default is to fix, and PCB_QUALITY.md says, rule by rule, the only cases in
# which a waiver is honest. Matched against the finding's text; "" = every finding.
HARD = {
    "A1": ("is not a pad on", "no copper joins", "declares no power_paths"),
    "A3": ("",),
    "A4": ("",),
    "A5": ("differ only in case",),
    "A6": ("are ONE net", "not 5.1 k", "resistors to ground on one CC"),
    "A10": ("cannot read the value",),
    "A11": ("",),
    "A12": ("ring", "hole", "track width", "pad gap"),
    "A13": ("",),
}


def is_hard(rid, text):
    return any(p in text for p in HARD.get(rid, ()))


def rule(rid):
    def deco(fn):
        RULES[rid] = fn
        return fn
    return deco


# ── the board, read once ─────────────────────────────────────────────────────────────
class Ctx:
    def __init__(self, stem):
        self.stem = stem
        self.name = os.path.basename(stem)
        self.board = pcbnew.LoadBoard(stem + ".kicad_pcb")
        try:
            with open(stem + ".board.json", encoding="utf-8") as fh:
                self.notes = json.load(fh)
        except OSError:
            self.notes = {}
        self.q = self.notes.get("quality", {}) or {}
        self.pads = {}                      # "U1.3" -> pad (first pad of that number)
        self.by_net = collections.defaultdict(list)     # net -> [(ref, num, pad)]
        self.fps = {}
        for fp in self.board.GetFootprints():
            ref = fp.GetReference()
            self.fps[ref] = fp
            for p in fp.Pads():
                key = "%s.%s" % (ref, p.GetNumber())
                self.pads.setdefault(key, p)
                if p.GetNetname():
                    self.by_net[p.GetNetname()].append((ref, p.GetNumber(), p))
        nets = set(self.by_net)
        self.grounds = {n for n in nets if GROUND.match(n)} | set(self.q.get("ground_nets", ()))
        if self.q.get("power_nets") is not None:
            self.power = set(self.q["power_nets"])
        else:
            self.power = {n for n in nets if POWER.match(n) and n not in self.grounds
                          and not NOT_CONNECTED.search(n)}
        self.power -= set(self.q.get("not_power", ()))

    def waived(self, rid, subject):
        return (self.q.get("waive", {}) or {}).get("%s:%s" % (rid, subject))


def _xy(pad):
    p = pad.GetPosition()
    return MM(p.x), MM(p.y)


def _where(ctx, at):
    """A board position in words a reader can find: the nearest pad and how far."""
    best = None
    for fp in ctx.board.GetFootprints():
        for pad in fp.Pads():
            x, y = _xy(pad)
            d = math.hypot(x - at[0], y - at[1])
            if best is None or d < best[0]:
                best = (d, "%s.%s" % (fp.GetReference(), pad.GetNumber()))
    return "%.1f mm from %s" % best if best else "at (%.1f, %.1f)" % tuple(at[:2])


def _prefix(ref):
    """The reference's CLASS letters: "U14" -> "U", "TP3" -> "TP", and "Cs13" -> "C" (a
    lower-case tail is the project's own sub-naming, not a different kind of part)."""
    m = re.match(r"[A-Z]+", ref)
    return m.group(0) if m else ref.rstrip("0123456789")


# ── A1: supply paths carry their current, with no choke point ────────────────────────
def required_width_mm(amps, layer, q):
    """IPC-2221 width for `amps` at the declared temperature rise.

    I = k * dT^0.44 * A^0.725, A in square mils; k = 0.048 on an outer layer, 0.024 inner.
    Copper weight: quality.copper_oz outer (default 1), quality.inner_oz inner (default 0.5,
    the usual 4-layer stack).
    """
    outer = layer in ("F.Cu", "B.Cu")
    k = 0.048 if outer else 0.024
    dt = float(q.get("temp_rise_c", 10.0))
    oz = float(q.get("copper_oz", 1.0)) if outer else float(q.get("inner_oz", 0.5))
    area_mil2 = (amps / (k * dt ** 0.44)) ** (1.0 / 0.725)
    return area_mil2 / (oz * 1.378) * 0.0254


def _layout():
    """pcbflow's layout module, for the geometry it already owns (imported late: it is
    heavy, and most rules never need it)."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import layout
    return layout


class _Net:
    """One net's copper as a graph: nodes are (layer, x, y) points and pads; an edge
    carries the WIDTH of what joins its ends. A pour joins everything it touches on its
    layer with an effectively unlimited width."""

    POUR = 1e3
    VIA_OHM = 0.001          # a plated barrel through 1.6 mm: about a milliohm

    def __init__(self, ctx, net):
        b = ctx.board
        self.g = collections.defaultdict(list)
        self.r = collections.defaultdict(list)       # the same graph, edges in ohms
        self.q = ctx.q
        layers = [b.GetLayerName(l) for l in b.GetEnabledLayers().CuStack()]
        R = lambda v: (round(MM(v.x), 3), round(MM(v.y), 3))        # noqa: E731
        segs, vias_at = [], {}
        for t in b.GetTracks():
            if t.GetNetname() != net:
                continue
            if t.GetClass() == "PCB_VIA":
                p = R(t.GetPosition())
                vias_at[p] = t
                # a via's barrel as an equivalent track width: its circumference, derated
                # for plating (~25 um) against 35 um foil. Parallel vias are NOT summed.
                w = math.pi * MM(t.GetDrillValue()) * 25.0 / 35.0
                for a, c in zip(layers, layers[1:]):
                    self._edge((a,) + p, (c,) + p, w, "via", "all", p, self.VIA_OHM)
            else:
                L = t.GetLayerName()
                a, c = (L,) + R(t.GetStart()), (L,) + R(t.GetEnd())
                w = MM(t.GetWidth())
                mid = ((a[1] + c[1]) / 2.0, (a[2] + c[2]) / 2.0)
                self._edge(a, c, w, "track", L, mid, self._ohm(a, c, w, L))
                segs.append((t, L, a, c, w))
        nodes = list(self.g)
        for t, L, a, c, w in segs:          # T-junctions: a node landing mid-segment
            for n in nodes:
                if n[0] == L and n != a and n != c and t.HitTest(
                        pcbnew.VECTOR2I(pcbnew.FromMM(n[1]), pcbnew.FromMM(n[2])),
                        pcbnew.FromMM(0.02)):
                    self._edge(n, a, w, "track", L, (n[1], n[2]), self._ohm(n, a, w, L))
                    self._edge(n, c, w, "track", L, (n[1], n[2]), self._ohm(n, c, w, L))
        nodes = list(self.g)
        self.pad_keys = {}
        for ref, num, p in ctx.by_net.get(net, ()):
            k = ("PAD", "%s.%s" % (ref, num))
            self.pad_keys[k[1]] = k
            bb = p.GetBoundingBox()
            x, y = _xy(p)
            for L in layers:
                if p.IsOnLayer(b.GetLayerID(L)):
                    self._edge(k, (L, round(x, 3), round(y, 3)), self.POUR, "pad", L, (x, y))
            for n in nodes:
                if n[0] != "PAD" and p.IsOnLayer(b.GetLayerID(n[0])) and bb.Contains(
                        pcbnew.VECTOR2I(pcbnew.FromMM(n[1]), pcbnew.FromMM(n[2]))):
                    self._edge(k, n, self.POUR, "pad", n[0], (n[1], n[2]))
        self.pours = []
        for z in b.Zones():
            if z.GetNetname() != net or z.GetIsRuleArea():
                continue
            for lid in z.GetLayerSet().CuStack():
                L = b.GetLayerName(lid)
                try:
                    poly = z.GetFilledPolysList(lid)
                except Exception:
                    continue
                zk = ("POUR", L, len(self.pours))
                self.pours.append(zk)
                for n in list(self.g):
                    if n[0] != L:
                        continue
                    if poly.Contains(pcbnew.VECTOR2I(
                            pcbnew.FromMM(n[1]), pcbnew.FromMM(n[2]))):
                        self._edge(zk, n, self.POUR, "pour", L, (n[1], n[2]))
                    elif (n[1], n[2]) in vias_at:
                        # a via whose CENTRE a neighbour's antipad has voided can still
                        # have its ring in the pour: joined, by the arc that touches
                        v = vias_at[(n[1], n[2])]
                        f = _layout().via_plane_contact(v, poly)
                        if f > 0:
                            ring = math.pi * (MM(v.GetDrillValue()) + MM(v.GetWidth(pcbnew.F_Cu))) / 2.0
                            self._edge(zk, n, f * ring, "pour contact", L, (n[1], n[2]))

    def _edge(self, a, c, w, kind, layer, at, ohm=0.0):
        self.g[a].append((c, w, kind, layer, at))
        self.g[c].append((a, w, kind, layer, at))
        self.r[a].append((c, ohm))
        self.r[c].append((a, ohm))

    def _ohm(self, a, c, w, layer):
        """Resistance of a track from node a to node c: copper at 20 C, the layer's foil."""
        outer = layer in ("F.Cu", "B.Cu")
        oz = float(self.q.get("copper_oz", 1.0)) if outer else float(self.q.get("inner_oz", 0.5))
        length = math.hypot(a[1] - c[1], a[2] - c[2])
        return 1.72e-5 * length / (max(w, 1e-3) * oz * 0.035)      # ohm; mm throughout

    def resistance(self, src, dst):
        """Ohms along the LEAST-RESISTANCE copper path from pad `src` to pad `dst` (pours
        and pads count as zero, so this is a floor on the track part), or None."""
        s, d = self.pad_keys.get(src), self.pad_keys.get(dst)
        if s is None or d is None:
            return None
        best, pq, n = {s: 0.0}, [(0.0, 0, s)], 0
        while pq:
            r, _i, u = heapq.heappop(pq)
            if r > best[u]:
                continue
            if u == d:
                return r
            for v, ohm in self.r[u]:
                if r + ohm < best.get(v, float("inf")):
                    best[v] = r + ohm
                    n += 1
                    heapq.heappush(pq, (r + ohm, n, v))
        return None

    def shared_drop(self, src, dsts, amps):
        """Volts lost from pad `src` to each pad in `dsts` when `amps` IN TOTAL is drawn by
        them in equal shares: the copper solved as one resistor network, so a trunk
        carries what is downstream of it and parallel paths share. {dst: volts}, or None
        without numpy or when a pad is not on the net."""
        try:
            import numpy as np
        except Exception:
            return None
        keys = [self.pad_keys.get(d) for d in dsts]
        s = self.pad_keys.get(src)
        if s is None or any(k is None for k in keys):
            return None
        # only the island the source is on: a cut rail is reported by widest(), not here
        seen, st = {s}, [s]
        while st:
            u = st.pop()
            for v, _ohm in self.r[u]:
                if v not in seen:
                    seen.add(v)
                    st.append(v)
        if any(k not in seen for k in keys):
            return None
        nodes = list(seen)
        ix = {n: i for i, n in enumerate(nodes)}
        A = np.zeros((len(nodes), len(nodes)))
        rhs = np.zeros(len(nodes))
        for a in nodes:
            for c, ohm in self.r[a]:
                g = 1.0 / max(ohm, 1e-5)       # pads and pours: a 10 micro-ohm link
                A[ix[a], ix[a]] += g
                A[ix[a], ix[c]] -= g
        for k in keys:
            rhs[ix[k]] -= amps / len(keys)
        A[ix[s], :] = 0.0
        A[ix[s], ix[s]] = 1.0
        rhs[ix[s]] = 0.0
        v = np.linalg.solve(A, rhs)
        return {d: float(-v[ix[k]]) for d, k in zip(dsts, keys)}

    def widest(self, src, dst):
        """The path from pad `src` to pad `dst` whose NARROWEST edge is widest:
        (bottleneck width, kind, layer, (x, y), runs through a pour?) or None."""
        s, d = self.pad_keys.get(src), self.pad_keys.get(dst)
        if s is None or d is None:
            return None
        best = {s: (float("inf"), None)}
        pq = [(-float("inf"), 0, s)]
        n = 0
        while pq:
            negw, _i, u = heapq.heappop(pq)
            if -negw < best[u][0]:
                continue
            if u == d:
                break
            for v, w, kind, layer, at in self.g[u]:
                cand = min(-negw, w)
                if cand > best.get(v, (-1.0, None))[0]:
                    info = (w, kind, layer, at) if w <= -negw else best[u][1]
                    best[v] = (cand, info)
                    n += 1
                    heapq.heappush(pq, (-cand, n, v))
        if d not in best:
            return None
        w, info = best[d]
        return (w,) + ((info[1], info[2], info[3]) if info else ("pour", "-", (0.0, 0.0)))


def _rail_volts(net):
    """The voltage a rail's NAME states: "+24V" 24, "+3V3A" 3.3, "+5V_PI" 5, "VBUS" 5."""
    m = re.match(r"^\+?(\d+)V(\d*)", net)
    if m:
        return float("%s.%s" % (m.group(1), m.group(2) or "0"))
    return 5.0 if net.upper().startswith("VBUS") else None


@rule("A1")
def power_paths(ctx):
    out = []
    paths = ctx.q.get("power_paths", []) or []
    declared = {p["net"] for p in paths}
    for net in sorted(ctx.power - declared):
        loads = len(ctx.by_net.get(net, ()))
        out.append((net, False,
                    "%s looks like a supply (%d pads) and declares no power_paths entry: say "
                    "where it enters, where it goes and how many amps, or list it in "
                    "quality.not_power" % (net, loads)))
    graphs = {}
    for p in paths:
        net, amps = p["net"], float(p["amps"])
        if net not in graphs:
            graphs[net] = _Net(ctx, net)
        g = graphs[net]
        dsts = p["to"] if isinstance(p["to"], (list, tuple)) else [p["to"]]
        # "split": the amps are what the listed pads draw TOGETHER (one IC's supply pins),
        # so the drop is solved on the network rather than charged in full to each path
        shared = (g.shared_drop(p["from"], list(dsts), amps)
                  if p.get("split") and all(e in g.pad_keys for e in dsts) else None)
        for dst in dsts:
            subject = "%s %s>%s" % (net, p["from"], dst)
            for end in (p["from"], dst):
                if end not in g.pad_keys:
                    out.append((subject, False, "%s is not a pad on %s" % (end, net)))
                    break
            else:
                r = g.widest(p["from"], dst)
                if r is None:
                    out.append((subject, False, "no copper joins %s to %s on %s"
                                % (p["from"], dst, net)))
                    continue
                w, kind, layer, at = r
                if kind in ("pour", "pad") or w >= _Net.POUR:
                    out.append((subject, True, "%.2f A through a pour the whole way" % amps))
                    continue
                need = (required_width_mm(amps, layer, ctx.q) if kind == "track"
                        else required_width_mm(amps, "F.Cu", ctx.q))
                ok = w + 1e-6 >= need
                # ...and the DROP: a path can be wide enough not to heat and still be long
                # and thin enough to starve the load
                ohm = g.resistance(p["from"], dst) or 0.0
                drop_mv = (shared[dst] if shared else ohm * amps) * 1000.0
                limit_mv = p.get("max_drop_mv", ctx.q.get("max_drop_mv"))
                if limit_mv is None:
                    volts = _rail_volts(net)
                    pct = float(ctx.q.get("max_drop_pct", 2.0))
                    limit_mv = volts * 10.0 * pct if volts else 50.0
                limit_mv = float(limit_mv)
                if drop_mv > limit_mv:
                    out.append((subject + " drop", False,
                                "%s %s -> %s, %.2f A%s: %.0f mOhm of track drops %.0f mV "
                                "(limit %.0f mV) -- widen it, shorten it, or pour it"
                                % (net, p["from"], dst, amps,
                                   " shared by %d pads" % len(dsts) if shared else "",
                                   ohm * 1000.0, drop_mv, limit_mv)))
                out.append((subject, ok,
                            "%s %s -> %s, %.2f A: narrowest point is a %.2f mm %s on %s "
                            "%s; %.2f mm needed for %.0f C rise%s"
                            % (net, p["from"], dst, amps, w,
                               "via barrel (equivalent)" if kind == "via" else kind,
                               layer, _where(ctx, at), need,
                               float(ctx.q.get("temp_rise_c", 10.0)),
                               " (%.0f mOhm, %.0f mV)" % (ohm * 1000.0, drop_mv) if ok
                               else " -- CHOKE POINT")))
    return out


# ── A2: every supply pin has a capacitor beside it ───────────────────────────────────
@rule("A2")
def decoupling(ctx):
    cfg = ctx.q.get("decoupling", {}) or {}
    ic_mm = float(cfg.get("ic_mm", 5.0))
    conn_mm = float(cfg.get("connector_mm", 25.0))
    exempt = cfg.get("exempt", {}) or {}
    caps = collections.defaultdict(list)            # net -> [(x, y, ref)]
    for ref, fp in ctx.fps.items():
        if _prefix(ref) != "C":
            continue
        pads = list(fp.Pads())
        nets = {p.GetNetname() for p in pads}
        if not (nets & ctx.grounds):
            continue                                # not a cap to ground: not a bypass
        for p in pads:
            if p.GetNetname() in ctx.power:
                caps[p.GetNetname()].append(_xy(p) + (ref,))
    out = []
    for net in sorted(ctx.power):
        rows = {}                    # subject -> (limit, best distance, cap ref)
        active = any(_prefix(r) in ("U", "Q", "D", "L", "K", "F", "FB", "R")
                     for r, _n, _p in ctx.by_net[net])
        for ref, num, pad in ctx.by_net[net]:
            kind = _prefix(ref)
            if kind not in ("U", "J", "P"):
                continue
            # an IC is judged PIN BY PIN; a connector once per net, by its nearest pin
            subject = "%s.%s" % (ref, num) if kind == "U" else ref
            x, y = _xy(pad)
            near = min([(math.hypot(cx - x, cy - y), cref) for cx, cy, cref in caps[net]],
                       default=(None, None))
            old = rows.get(subject)
            if old is None or (near[0] is not None and (old[1] is None or near[0] < old[1])):
                rows[subject] = (ic_mm if kind == "U" else conn_mm, near[0], near[1])
        for subject in sorted(rows):
            limit, dist, cref = rows[subject]
            why = exempt.get(subject) or exempt.get(subject.split(".")[0])
            if why:
                out.append((subject, None, "exempt: %s" % why))
            elif not active and (dist is None or dist > limit):
                # a rail that only passes between connectors has no load here to step
                out.append((subject, None,
                            "%s passes through this board with no load on it: no "
                            "capacitor required at %s" % (net, subject)))
            elif dist is not None and dist <= limit:
                out.append((subject, True, "%s: %s at %.1f mm" % (net, cref, dist)))
            else:
                out.append((subject, False,
                            "%s on %s has no capacitor to ground within %.1f mm (%s)"
                            % (subject, net, limit,
                               "nearest %s at %.1f mm" % (cref, dist) if dist is not None
                               else "the net has none at all")))
    return out


# ── A3: pairs are declared, matched, and stay a pair ─────────────────────────────────
@rule("A3")
def matched_lengths(ctx):
    out = []
    groups = ctx.notes.get("match", []) or []
    grouped = {n for g in groups for n in g["nets"]}
    ok_unmatched = ctx.q.get("unmatched_ok", {}) or {}
    nets = set(ctx.by_net)
    seen = set()
    for n in sorted(nets):
        for pat, rep in PAIR:
            m = re.match(pat, n)
            if not m:
                continue
            other = re.sub(pat, rep, n)
            if other in nets and (n, other) not in seen:
                seen.add((n, other))
                if n in grouped and other in grouped:
                    continue
                why = ok_unmatched.get(n) or ok_unmatched.get(other)
                out.append(("%s/%s" % (n, other), None if why else False,
                            ("not matched, declared: %s" % why) if why else
                            "%s and %s look like a differential pair and are in no `match` "
                            "group: declare one (max_skew_mm, same_layer, max_vias, why) or "
                            "say why not in quality.unmatched_ok" % (n, other)))
    if groups:
        sys.path.insert(0, HERE)
        import verify                                    # noqa: E402
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            verify.check(ctx.stem)
        finally:
            sys.stdout = old
        for line in buf.getvalue().splitlines():
            s = line.strip()
            if s.startswith("ok  ") or s.startswith("FAIL"):
                parts = s.split()
                out.append((parts[1], s.startswith("ok"), s[4:].strip()))
    return out


# ── A4: pinouts -- pads exist, and every multi-pin part cites where its pinout came from ─
def _netlist_pins(stem):
    """{ref: (value, footprint, {pin numbers})} from the netlist beside the board."""
    try:
        t = open(stem + ".net", encoding="utf-8").read()
    except OSError:
        return {}
    comps = {}
    for m in re.finditer(r'\(comp\s*\(ref "([^"]+)"\)\s*\(value "([^"]*)"\).*?'
                         r'\(footprint "([^"]+)"\)', t, re.S):
        comps[m.group(1)] = [m.group(2), m.group(3), set()]
    for blk in re.finditer(r'\(net\s+\(code \d+\).*?(?=\(net\s+\(code|\Z)', t, re.S):
        for ref, pin in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk.group(0)):
            if ref in comps:
                comps[ref][2].add(pin)
    return comps


@rule("A4")
def pinouts(ctx):
    out = []
    cited = ctx.q.get("pinouts", {}) or {}
    comps = _netlist_pins(ctx.stem)
    seen_kinds = set()
    for ref in sorted(ctx.fps):
        fp = ctx.fps[ref]
        pads = {p.GetNumber() for p in fp.Pads() if p.GetNumber()}
        value, fpid, pins = comps.get(ref, ("", fp.GetFPIDAsString(), set()))
        missing = sorted(pins - pads)
        if missing:
            out.append((ref, False, "%s: the netlist connects pin(s) %s that footprint %s "
                                    "does not have -- those pins are wired to nothing"
                        % (ref, ", ".join(missing), fpid.split(":")[-1])))
        if len(pads) < 3:
            continue                    # a two-pad part cannot be mirrored (polarity: M-list)
        name = fpid.split(":")[-1]
        cite = cited.get(ref) or cited.get(value) or cited.get(name)
        kind = (value, name)
        if cite:
            if kind not in seen_kinds:
                out.append((value or ref, True, "pinout checked against: %s" % cite))
        elif kind not in seen_kinds:
            out.append((value or ref, False,
                        "%s (%s, %d pads, e.g. %s): no pinout citation"
                        % (value or ref, name, len(pads), ref)))
        seen_kinds.add(kind)
    return out


# ── the manual list, read from the markdown ──────────────────────────────────────────
# ── shared: a resistor's ohms from its value text ────────────────────────────────────
def _ohms(value):
    """"4.7k" / "4k7" / "5K1" / "600R" / "120" / "1M" -> ohms, or None."""
    v = (value or "").strip().replace("Ω", "").replace("ohm", "").replace(" ", "")
    m = re.match(r"^(\d+)([RrkKmM])(\d+)$", v)                 # 4k7, 5K1, 0R5
    if m:
        num, unit = float("%s.%s" % (m.group(1), m.group(3))), m.group(2)
    else:
        m = re.match(r"^(\d+(?:\.\d+)?)([RrkKM]?)", v)
        if not m:
            return None
        num, unit = float(m.group(1)), m.group(2)
    return num * {"k": 1e3, "K": 1e3, "M": 1e6}.get(unit, 1.0)


def _resistors_to(ctx, net, targets):
    """[(ref, ohms or None)] for resistors with one pad on `net` and the other on a net in
    `targets`."""
    out = []
    for ref, _num, _pad in ctx.by_net.get(net, ()):
        if _prefix(ref) != "R":
            continue
        others = {p.GetNetname() for p in ctx.fps[ref].Pads()} - {net}
        if others & targets:
            out.append((ref, _ohms(ctx.fps[ref].GetValue())))
    return out


# ── A5: the netlist says what the designer meant ─────────────────────────────────────
AUTO_NET = re.compile(r"^(N\$|Net-\(|unconnected-|\$)")


@rule("A5")
def net_sanity(ctx):
    out = []
    ok_single = set(ctx.q.get("single_pin_ok", ()))
    for net in sorted(ctx.by_net):
        pads = ctx.by_net[net]
        if (len(pads) == 1 and not AUTO_NET.match(net) and not NOT_CONNECTED.search(net)
                and net not in ok_single):
            out.append((net, False,
                        "net %s reaches only %s.%s: a label that connects to nothing (a "
                        "typo, or a pin that was meant to go somewhere)"
                        % (net, pads[0][0], pads[0][1])))
        else:
            out.append((net, True, "%s: %d pads" % (net, len(pads))))
    folded = collections.defaultdict(set)
    for net in ctx.by_net:
        if not AUTO_NET.match(net):
            folded[re.sub(r"[^A-Z0-9+]", "", net.upper())].add(net)
    for key in sorted(folded):
        if len(folded[key]) > 1:
            names = sorted(folded[key])
            out.append(("/".join(names), False,
                        "nets %s differ only in case or punctuation: one net typed two "
                        "ways is two nets" % " and ".join(names)))
    return out


# ── A6: USB-C configuration channel ──────────────────────────────────────────────────
@rule("A6")
def usb_c_cc(ctx):
    out = []
    for ref in sorted(ctx.fps):
        pads = {p.GetNumber(): p for p in ctx.fps[ref].Pads()}
        if "A5" not in pads or "B5" not in pads:
            continue                                    # not a USB-C receptacle
        cc = [pads["A5"].GetNetname(), pads["B5"].GetNetname()]
        if cc[0] and cc[0] == cc[1]:
            out.append((ref, False,
                        "%s: CC1 and CC2 are ONE net (%s). An e-marked cable then puts its "
                        "Ra in parallel with the shared resistor and the source supplies "
                        "nothing: each CC pin needs its own resistor" % (ref, cc[0])))
            continue
        for pin, net in zip(("A5", "B5"), cc):
            subject = "%s.%s" % (ref, pin)
            if not net:
                out.append((subject, False, "%s (CC) is not connected: a USB-C source "
                                            "will not turn VBUS on" % subject))
                continue
            down = _resistors_to(ctx, net, ctx.grounds)
            up = _resistors_to(ctx, net, ctx.power)
            ics = [r for r, _n, _p in ctx.by_net[net] if _prefix(r) == "U"]
            if down:
                bad = [(r, o) for r, o in down if o is None or abs(o - 5100.0) > 5100 * 0.011]
                if bad:
                    out.append((subject, False, "%s: Rd %s is %s, not 5.1 k 1%%"
                                % (subject, bad[0][0], ctx.fps[bad[0][0]].GetValue())))
                elif len(down) > 1:
                    out.append((subject, False, "%s: %d resistors to ground on one CC pin"
                                % (subject, len(down))))
                else:
                    out.append((subject, True, "%s: 5.1 k to ground (%s)"
                                % (subject, down[0][0])))
            elif up or ics:
                out.append((subject, True, "%s: %s" % (subject, "pulled up (a source port)"
                                                       if up else "on %s" % ics[0])))
            else:
                out.append((subject, False, "%s (CC, net %s) has no resistor to ground, no "
                                            "pull-up and no controller" % (subject, net)))
    return out


# ── A7: I2C pull-ups ─────────────────────────────────────────────────────────────────
I2C = re.compile(r"(^|_)(SDA|SCL)\d*($|_)")


@rule("A7")
def i2c_pullups(ctx):
    out = []
    lo = float(ctx.q.get("i2c_min_ohm", 1000.0))
    for net in sorted(n for n in ctx.by_net if I2C.search(n.upper())):
        ups = _resistors_to(ctx, net, ctx.power)
        if not ups:
            out.append((net, False,
                        "%s has no pull-up on this board. If it is on the other end of the "
                        "bus, waive this saying WHERE -- one pair per bus, not zero"
                        % net))
            continue
        vals = [o for _r, o in ups if o]
        par = 1.0 / sum(1.0 / o for o in vals) if vals else 0.0
        ok = par >= lo
        out.append((net, ok, "%s: %s = %.0f ohm%s"
                    % (net, " || ".join(r for r, _o in ups), par,
                       "" if ok else " -- below %.0f: more than the pins can sink (and count "
                                     "the pull-ups on every other board on this bus)" % lo)))
    return out


# ── A8: exposed pads are connected and stitched ──────────────────────────────────────
@rule("A8")
def exposed_pads(ctx):
    out = []
    vias = collections.defaultdict(list)
    for t in ctx.board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias[t.GetNetname()].append(t.GetPosition())
    for ref in sorted(ctx.fps):
        fp = ctx.fps[ref]
        if not re.search(r"\dEP|_EP\d|-EP", fp.GetFPIDAsString().split(":")[-1]):
            continue
        smd = [p for p in fp.Pads() if p.GetNumber() and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
        if not smd:
            continue
        ep = max(smd, key=lambda p: p.GetSize().x * p.GetSize().y)
        net = ep.GetNetname()
        if not net:
            out.append((ref, False, "%s: the exposed pad (pad %s) is not connected. It is "
                                    "usually the part's main ground AND its heat path"
                        % (ref, ep.GetNumber())))
            continue
        bb = ep.GetBoundingBox()
        n = sum(1 for v in vias[net] if bb.Contains(v))
        ok = n >= int(ctx.q.get("ep_min_vias", 1))
        out.append((ref, ok, "%s: exposed pad on %s, %d via(s) in it%s"
                    % (ref, net, n, "" if ok else " -- no path to the plane or for heat")))
    return out


# ── A9: crystals sit beside the pins they drive ──────────────────────────────────────
@rule("A9")
def crystal_distance(ctx):
    out = []
    limit = float(ctx.q.get("crystal_mm", 10.0))
    for ref in sorted(ctx.fps):
        if _prefix(ref) not in ("Y", "X") or "rystal" not in ctx.fps[ref].GetFPIDAsString():
            continue
        for pad in ctx.fps[ref].Pads():
            net = pad.GetNetname()
            if not net or net in ctx.grounds or net in ctx.power:
                continue
            x, y = _xy(pad)
            ics = [(math.hypot(_xy(p)[0] - x, _xy(p)[1] - y), "%s.%s" % (r, n))
                   for r, n, p in ctx.by_net[net] if _prefix(r) == "U"]
            if not ics:
                # through a series resistor: one hop is enough to find the oscillator pin
                continue
            d, pin = min(ics)
            ok = d <= limit
            nvia = sum(1 for t in ctx.board.GetTracks()
                       if t.GetClass() == "PCB_VIA" and t.GetNetname() == net)
            if nvia:
                out.append(("%s vias" % net, None,
                            "%s changes layer (%d via(s)): better kept on the crystal's "
                            "own layer" % (net, nvia)))
            out.append(("%s.%s" % (ref, pad.GetNumber()), ok,
                        "%s.%s to %s on %s: %.1f mm%s"
                        % (ref, pad.GetNumber(), pin, net, d,
                           "" if ok else " (limit %.0f) -- a long crystal trace is stray "
                                         "capacitance and an antenna" % limit)))
    return out

# ── A10: a USB device's VBUS capacitance is inside the inrush limit ──────────────────
def _farads(value):
    """"100n" / "4.7uF" / "4u7" / "22p" -> farads, or None."""
    v = (value or "").strip().replace("µ", "u").replace(" ", "")
    mult = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}
    m = re.match(r"^(\d+)([pnum])(\d+)", v)
    if m:
        return float("%s.%s" % (m.group(1), m.group(3))) * mult[m.group(2)]
    m = re.match(r"^(\d+(?:\.\d+)?)([pnum])F?", v)
    return float(m.group(1)) * mult[m.group(2)] if m else None


@rule("A10")
def usb_vbus_capacitance(ctx):
    out = []
    lo, hi = 1e-6, 10e-6
    for ref in sorted(ctx.fps):
        pads = {p.GetNumber(): p for p in ctx.fps[ref].Pads()}
        if "A5" not in pads or "B5" not in pads or "A4" not in pads:
            continue
        cc = [pads[k].GetNetname() for k in ("A5", "B5")]
        if not any(n and _resistors_to(ctx, n, ctx.grounds) for n in cc):
            continue                        # not a device (sink) port: the limit is the sink's
        vbus = pads["A4"].GetNetname()
        if not vbus or NOT_CONNECTED.search(vbus):
            continue
        total, caps, unknown = 0.0, [], []
        for cref, _n, _p in ctx.by_net[vbus]:
            if _prefix(cref) != "C":
                continue
            if not ({p.GetNetname() for p in ctx.fps[cref].Pads()} & ctx.grounds):
                continue
            f = _farads(ctx.fps[cref].GetValue())
            if f is None:
                unknown.append(cref)
            else:
                total += f
                caps.append(cref)
        if unknown:
            out.append((ref, False, "%s: cannot read the value of %s on %s"
                        % (ref, ", ".join(unknown), vbus)))
            continue
        if total > hi:
            ok, tail = False, (" -- over 10 uF at plug-in trips a host's inrush limit: put "
                               "the rest behind a load switch or a soft-start")
        elif total < lo:
            # guidance, not the specification's hard limit: reported, never a FAIL
            ok, tail = None, " -- under the 1 uF usually recommended on a device's VBUS"
        else:
            ok, tail = True, ""
        out.append((ref, ok, "%s: %.1f uF directly on %s (%s)%s"
                    % (ref, total * 1e6, vbus, ", ".join(sorted(caps)) or "no capacitor",
                       tail)))
    return out

# ── A11: one value, one spelling ─────────────────────────────────────────────────────
@rule("A11")
def value_spelling(ctx):
    """The same resistance or capacitance written two ways ("100n" and "0.1uF") is two
    BOM lines, two feeders and a part that can drift apart."""
    out = []
    seen = collections.defaultdict(lambda: collections.defaultdict(list))
    for ref, fp in ctx.fps.items():
        kind = _prefix(ref)
        if kind not in ("R", "C"):
            continue
        text = (fp.GetValue() or "").strip()
        num = _ohms(text) if kind == "R" else _farads(text)
        if num is None:
            continue
        # the VALUE token and whatever qualifies it ("10k" + "0.1%"): a different rating
        # or tolerance is a different part on purpose, a different spelling of the same
        # number is not
        token = re.split(r"[\s/]", text, 1)[0]
        qualifier = re.sub(r"\s+", "", text[len(token):].lower())
        key = (kind, fp.GetFPIDAsString().split(":")[-1], "%.4g" % num, qualifier)
        seen[key][token].append(ref)
    for key in sorted(seen):
        spellings = seen[key]
        if len(spellings) > 1:
            out.append(("/".join(sorted(spellings)), False,
                        "%s in %s is written %s: one part, one spelling"
                        % ("the same value", key[1],
                           " and ".join("'%s' (%s)" % (t, ", ".join(sorted(r)[:3]))
                                        for t, r in sorted(spellings.items())))))
        else:
            out.append((next(iter(spellings)), True, "one spelling"))
    return out


# ── A12: the board, measured against what the fab says it can make ───────────────────
# The numbers a board is ROUTED to live in its design rules, and those were typed by
# someone: on the first seven boards this was run on they were looser than the fab's own
# page in five places (pad-hole spacing, plated-hole to track, silk height and stroke,
# pad-to-pad). So this does not read the rules. It measures the copper, the holes and the
# text that will be sent, against the fab's published minimums.
FAB = {     # JLCPCB, standard (not "advanced") service, 1 oz -- capabilities page read 2026-10-04
    "name": "JLCPCB standard 1 oz (capabilities page, read 2026-10-04)",
    "track_2l": 0.10, "track_ml": 0.09,     # minimum track width, 1-2 layer / multilayer
    "via_drill": 0.15,                      # smallest via hole at all
    "via_drill_std": 0.30,                  # smaller than this costs more: a note
    "via_ring": 0.05,                       # via pad at least 0.1 larger than its hole
    "pth_ring_2l": 0.18, "pth_ring_ml": 0.15,   # component-hole annular ring, absolute min
    "npth_min": 0.50,                       # smallest non-plated hole
    "hole_hole_via": 0.20,                  # via hole to via hole, edge to edge
    "hole_hole_pad": 0.45,                  # a pad hole to any other hole
    "via_track": 0.20, "pth_track": 0.28, "npth_track": 0.20,   # hole edge to foreign copper
    "pad_gap": 0.15,                        # SMD pad to pad, different nets
    "silk_height": 1.0, "silk_stroke": 0.15,
}


def _seg_d(a, b, c, d):
    """Least distance between segments a-b and c-d (points are (x, y) in mm)."""
    def pt_seg(p, u, v):
        ux, uy = v[0] - u[0], v[1] - u[1]
        L2 = ux * ux + uy * uy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - u[0]) * ux + (p[1] - u[1]) * uy) / L2))
        return math.hypot(p[0] - u[0] - t * ux, p[1] - u[1] - t * uy)

    def ccw(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    if a != b and c != d:
        d1, d2, d3, d4 = ccw(c, d, a), ccw(c, d, b), ccw(a, b, c), ccw(a, b, d)
        if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
            return 0.0
    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))


def _via_dia(v):
    for args in ((pcbnew.F_Cu,), ()):
        try:
            return MM(v.GetWidth(*args))
        except Exception:               # noqa: BLE001 -- the signature moved between KiCad versions
            pass
    return 0.0


def _pad_size(p):
    for args in ((pcbnew.F_Cu,), ()):
        try:
            sz = p.GetSize(*args)
            return MM(sz.x), MM(sz.y)
        except Exception:               # noqa: BLE001
            pass
    return 0.0, 0.0


@rule("A12")
def fab_capability(ctx):
    b = ctx.board
    fab = dict(FAB)
    fab.update(ctx.q.get("fab", {}) or {})
    multi = b.GetCopperLayerCount() > 2
    lim_track = fab["track_ml"] if multi else fab["track_2l"]
    lim_ring = fab["pth_ring_ml"] if multi else fab["pth_ring_2l"]
    out = [("fab", None, "measured against: %s%s" % (
        fab["name"], "" if "fab" not in ctx.q else " + quality.fab"))]

    def worst(subject, items, limit, what, unit="mm"):
        """items: [(value, where)] -- one finding per check, naming the worst and the count."""
        if not items:
            return
        bad = sorted(i for i in items if i[0] < limit - 1e-6)
        v, where = min(items)
        if bad:
            out.append((subject, False, "%s: %.3f %s at %s, the fab's minimum is %.2f (%d place(s))"
                        % (what, v, unit, where, limit, len(bad))))
        else:
            out.append((subject, True, "%s: least %.3f %s (minimum %.2f), %d checked"
                        % (what, v, unit, limit, len(items))))

    # holes: (kind, a, b, radius, net, name) -- a round hole has a == b, a slot is a-b
    holes, tracks, small_vias = [], [], 0
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            xy = (MM(t.GetPosition().x), MM(t.GetPosition().y))
            dr, dia = MM(t.GetDrillValue()), _via_dia(t)
            holes.append(("via", xy, xy, dr / 2.0, t.GetNetname(), "via %s" % _where(ctx, xy), dia))
            if dr < fab["via_drill_std"] - 1e-6:
                small_vias += 1
        else:
            a = (MM(t.GetStart().x), MM(t.GetStart().y))
            c = (MM(t.GetEnd().x), MM(t.GetEnd().y))
            tracks.append((a, c, MM(t.GetWidth()), t.GetNetname(), t.GetLayerName()))
    rings = []
    for ref, fp in ctx.fps.items():
        for pad in fp.Pads():
            att = pad.GetAttribute()
            if att not in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                continue
            ds = pad.GetDrillSize()
            dx, dy = MM(ds.x), MM(ds.y)
            if min(dx, dy) <= 0:
                continue
            x, y = _xy(pad)
            r = min(dx, dy) / 2.0
            half = (max(dx, dy) - min(dx, dy)) / 2.0
            ang = math.radians(pad.GetOrientation().AsDegrees())
            ux, uy = (math.cos(ang), -math.sin(ang)) if dx >= dy else (math.sin(ang), math.cos(ang))
            a, c = (x - ux * half, y - uy * half), (x + ux * half, y + uy * half)
            name = "%s.%s" % (ref, pad.GetNumber() or "hole")
            if att == pcbnew.PAD_ATTRIB_PTH:
                holes.append(("pth", a, c, r, pad.GetNetname(), name, 0.0))
                sx, sy = _pad_size(pad)
                if sx and sy:
                    rings.append((min(sx - dx, sy - dy) / 2.0, name))
            else:
                holes.append(("npth", a, c, r, "", name, 0.0))

    worst("track width", [(w, "%s on %s %s" % (n or "no net", L, _where(ctx, a)))
                          for a, c, w, n, L in tracks], lim_track, "narrowest track width")
    vias = [h for h in holes if h[0] == "via"]
    worst("via hole", [(2 * h[3], h[5]) for h in vias], fab["via_drill"], "smallest via hole")
    worst("via ring", [((h[6] - 2 * h[3]) / 2.0, h[5]) for h in vias if h[6]],
          fab["via_ring"], "thinnest via ring")
    if small_vias:
        out.append(("via cost", None, "%d via(s) are drilled under %.2f mm: the fab charges "
                    "more for them -- select that option on the order" % (small_vias, fab["via_drill_std"])))
    worst("pad ring", rings, lim_ring, "thinnest plated-hole annular ring")
    worst("npth hole", [(2 * h[3], h[5]) for h in holes if h[0] == "npth"], fab["npth_min"],
          "smallest non-plated hole")

    # hole to hole, edge to edge
    hh_via, hh_pad = [], []
    order = sorted(range(len(holes)), key=lambda i: holes[i][1][0])
    for ii, i in enumerate(order):
        hi = holes[i]
        for j in order[ii + 1:]:
            hj = holes[j]
            if hj[1][0] - hi[2][0] > 8.0 and hj[1][0] - hi[1][0] > 8.0:
                break
            if abs(hj[1][1] - hi[1][1]) > 8.0:
                continue
            gap = _seg_d(hi[1], hi[2], hj[1], hj[2]) - hi[3] - hj[3]
            if gap > 1.0:
                continue
            (hh_via if hi[0] == hj[0] == "via" else hh_pad).append((gap, "%s / %s" % (hi[5], hj[5])))
    worst("via hole spacing", hh_via or [(1.0, "none nearer than 1 mm")], fab["hole_hole_via"],
          "via hole to via hole")
    worst("pad hole spacing", hh_pad or [(1.0, "none nearer than 1 mm")], fab["hole_hole_pad"],
          "pad hole to its nearest hole")

    # hole edge to copper of another net (tracks; pads and pours keep their own clearance
    # from the PAD, which is the ring further out -- so the ring check covers them)
    grid = collections.defaultdict(list)
    cell = 2.0
    for k, (a, c, w, n, L) in enumerate(tracks):
        for gx in range(int(math.floor(min(a[0], c[0]) / cell)) - 1, int(math.floor(max(a[0], c[0]) / cell)) + 2):
            for gy in range(int(math.floor(min(a[1], c[1]) / cell)) - 1, int(math.floor(max(a[1], c[1]) / cell)) + 2):
                grid[(gx, gy)].append(k)
    near = {"via": [], "pth": [], "npth": []}
    for kind, a, c, r, net, name, _d in holes:
        seen = set()
        for pt in (a, c):
            for k in grid.get((int(math.floor(pt[0] / cell)), int(math.floor(pt[1] / cell))), ()):
                if k in seen:
                    continue
                seen.add(k)
                ta, tc, w, tn, L = tracks[k]
                if kind != "npth" and tn == net:
                    continue
                gap = _seg_d(a, c, ta, tc) - r - w / 2.0
                if gap < 1.0:
                    near[kind].append((gap, "%s / %s on %s" % (name, tn or "no net", L)))
    for kind, key, what in (("via", "via_track", "via hole to another net's track"),
                            ("pth", "pth_track", "plated pad hole to another net's track"),
                            ("npth", "npth_track", "non-plated hole to a track")):
        if any(h[0] == kind for h in holes):
            worst("%s hole to track" % kind, near[kind] or [(1.0, "none nearer than 1 mm")],
                  fab[key], what)

    # SMD pad to pad, different nets, same face
    gaps = []
    smd = []
    for ref, fp in ctx.fps.items():
        for pad in fp.Pads():
            if pad.GetAttribute() in (pcbnew.PAD_ATTRIB_SMD,):
                layer = pcbnew.F_Cu if pad.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
                smd.append((_xy(pad), layer, pad, "%s.%s" % (ref, pad.GetNumber())))
    smd.sort(key=lambda e: e[0][0])
    lim_iu = pcbnew.FromMM(fab["pad_gap"] - 0.0005)
    try:
        for i, (xy, layer, pad, name) in enumerate(smd):
            for xy2, layer2, pad2, name2 in smd[i + 1:]:
                if xy2[0] - xy[0] > 3.0:
                    break
                if layer2 != layer or abs(xy2[1] - xy[1]) > 3.0:
                    continue
                if pad.GetNetname() == pad2.GetNetname() and pad.GetNetname():
                    continue
                if pad.GetParentFootprint() is not None and pad2.GetParentFootprint() is not None \
                        and pad.GetParentFootprint().GetReference() == pad2.GetParentFootprint().GetReference() \
                        and pad.GetNumber() == pad2.GetNumber():
                    continue
                if pad.GetEffectiveShape(layer).Collide(pad2.GetEffectiveShape(layer), lim_iu):
                    gaps.append("%s / %s" % (name, name2))
        if gaps:
            out.append(("pad gap", False, "SMD pad gap under the fab's %.2f mm between different "
                        "nets at %s (%d place(s))" % (fab["pad_gap"], gaps[0], len(gaps))))
        elif smd:
            out.append(("pad gap", True, "SMD pad gap: none under %.2f mm, %d pad(s) checked"
                        % (fab["pad_gap"], len(smd))))
    except Exception as e:              # noqa: BLE001 -- shape API differs by KiCad version
        out.append(("pad gap", None, "SMD pad gaps not measured on this KiCad (%s): check the "
                    "finest-pitch part by hand" % type(e).__name__))

    # an open via in an SMD pad wicks the paste down the barrel and starves the joint
    if smd and vias and not fab.get("via_in_pad"):
        inpad, touch, thermal, drained = [], [], 0, []
        _thick = MM(b.GetDesignSettings().GetBoardThickness()) or 1.6
        try:
            for xy, layer, pad, name in smd:
                # Where a via in a pad is harmless or wanted: a pad with NO PASTE (a test
                # pad: nothing is soldered), an exposed pad or its unnumbered paste
                # sub-pads (A8 asks for vias there), and any land of 4 mm2 or more -- a
                # 0.3 mm barrel through 1.6 mm holds 0.11 mm3, a quarter of what a 0.12 mm
                # stencil prints on 4 mm2; on a 1.4 x 1.2 crystal pad it is half.
                if not (pad.IsOnLayer(pcbnew.F_Paste) or pad.IsOnLayer(pcbnew.B_Paste)):
                    continue
                _sz = _pad_size(pad)
                _fp = pad.GetParentFootprint()
                _ep = bool(_fp is not None and re.search(
                    r"\dEP|_EP\d|-EP", _fp.GetFPIDAsString().split(":")[-1]))
                _big = 0.0
                if _ep:
                    _big = max(_pad_size(q)[0] * _pad_size(q)[1] for q in _fp.Pads()
                               if q.GetAttribute() == pcbnew.PAD_ATTRIB_SMD)
                _is_ep = _ep and (not pad.GetNumber() or _sz[0] * _sz[1] >= _big - 1e-6)
                is_thermal = _sz[0] * _sz[1] >= 4.0 or _is_ep
                _barrels = 0.0
                for t in b.GetTracks():
                    if t.GetClass() != "PCB_VIA":
                        continue
                    pos = t.GetPosition()
                    if abs(MM(pos.x) - xy[0]) > 6.0 or abs(MM(pos.y) - xy[1]) > 6.0:
                        continue
                    if pad.HitTest(pos, int(t.GetDrillValue() / 2)):
                        if is_thermal:
                            thermal += 1
                            _barrels += math.pi * (MM(t.GetDrillValue()) / 2.0) ** 2 * _thick
                        else:
                            inpad.append(name)
                    elif pad.HitTest(pos, int(pcbnew.FromMM(_via_dia(t) / 2.0))):
                        touch.append(name)
                # ...AND A BIG LAND IS ONLY EXEMPT FOR AS MANY BARRELS AS IT CAN FEED. The
                # 4 mm2 line is one 0.3 mm via; two 0.4 mm vias in a 5.9 mm2 connector land
                # are 0.40 mm3 out of 0.70 printed, and four are more than all of it. An
                # exposed pad is not counted: its datasheet asks for the vias and the
                # joint that matters there is thermal.
                _paste = _sz[0] * _sz[1] * 0.12
                if _barrels > 0.25 * _paste + 1e-9 and not _is_ep:
                    drained.append((name, _barrels, _paste))
            if drained:
                _n, _v, _p = max(drained, key=lambda d: d[1] / d[2])
                out.append(("via in pad volume", False, "open vias in SMD land %s hold %.2f mm3 "
                            "of the %.2f mm3 of paste printed on it (%d land(s) over a "
                            "quarter): move the vias beside the land, or order them filled "
                            "(quality.fab via_in_pad)" % (_n, _v, _p, len(drained))))
            if inpad:
                out.append(("via in pad", False, "open via hole inside SMD pad %s (%d place(s)): "
                            "solder wicks down it -- move the via off the pad, or order "
                            "filled-and-capped vias and say so (quality.fab via_in_pad)"
                            % (inpad[0], len(inpad))))
            else:
                out.append(("via in pad", True, "no via hole inside an SMD pad, %d via(s) checked"
                            % len(vias)))
            if thermal:
                out.append(("thermal vias", None, "%d via(s) in large or thermal pads (4 mm2 "
                            "or more, or an exposed pad): expected there" % thermal))
            if touch:
                out.append(("via at pad", None, "%d via ring(s) touch an SMD pad (first: %s): fine "
                            "if the via is tented, which the fab does by default"
                            % (len(touch), touch[0])))
        except Exception as e:          # noqa: BLE001
            out.append(("via in pad", None, "vias in pads not checked on this KiCad (%s)"
                        % type(e).__name__))

    # silk text that will be printed
    silk = (pcbnew.F_SilkS, pcbnew.B_SilkS)
    texts = []
    for d in b.GetDrawings():
        if d.GetClass() == "PCB_TEXT" and d.GetLayer() in silk:
            texts.append((d, (d.GetText() or "").split("\n")[0][:16]))
    for ref, fp in ctx.fps.items():
        items = []
        try:
            items = list(fp.GetFields())
        except Exception:               # noqa: BLE001
            items = [fp.Reference(), fp.Value()]
        for f in items:
            if f.GetLayer() in silk and f.IsVisible():
                texts.append((f, "%s %s" % (ref, (f.GetText() or "")[:12])))
        for g in fp.GraphicalItems():
            if g.GetClass() == "PCB_TEXT" and g.GetLayer() in silk:
                texts.append((g, "%s %s" % (ref, (g.GetText() or "")[:12])))
    worst("silk text height", [(MM(t.GetTextHeight()), "'%s'" % n) for t, n in texts],
          fab["silk_height"], "smallest silk text")
    worst("silk text stroke", [(MM(t.GetTextThickness()), "'%s'" % n) for t, n in texts],
          fab["silk_stroke"], "thinnest silk stroke")
    return out


# ── A13: every pin and every channel is accounted for ────────────────────────────────
# A netlist that is wrong but internally consistent routes clean and passes DRC: two
# channels wired to the same four driver outputs are simply fewer nets. The only thing
# that can see it is the number the DESIGN means, written down beside the board.
def _expand(ctx, pattern):
    """Pads ("REF.PIN") matching one fnmatch pattern over REF.PIN."""
    import fnmatch
    return sorted(k for k in ctx.pads if k.split(".")[-1] and fnmatch.fnmatchcase(k, pattern))


def _unconnected(ctx):
    """{"REF.PIN"} for every numbered pad of a part with three or more pin numbers that
    has no net, or sits alone on its net."""
    out = set()
    for ref, fp in ctx.fps.items():
        nums = {}
        for pad in fp.Pads():
            if pad.GetNumber():
                nums.setdefault(pad.GetNumber(), []).append(pad)
        if len(nums) < 3:
            continue
        for num, pads in nums.items():
            nets = {q.GetNetname() for q in pads} - {""}
            if not nets or all((r, n) == (ref, num) for x in nets
                               for r, n, _p in ctx.by_net[x]):
                out.add("%s.%s" % (ref, num))
    return out


def _nat(s):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]


@rule("A13")
def accounted_for(ctx):
    out = []
    # 1. unconnected pins: the board's against the declaration, both ways
    actual = _unconnected(ctx)
    declared, why = set(), {}
    for key, val in (ctx.q.get("unconnected", {}) or {}).items():
        if isinstance(val, dict):
            pins = val.get("pins", "")
            pins = pins.split() if isinstance(pins, str) else [str(x) for x in pins]
            reason = val.get("why", "")
            refs = sorted({k.rsplit(".", 1)[0] for k in _expand(ctx, key + ".*")}) or [key]
            hits = ["%s.%s" % (r, n) for r in refs for n in pins]
            missing = [h for h in hits if h not in ctx.pads]
            if missing:
                out.append((key, False, "quality.unconnected names %s, which the board "
                                        "does not have" % ", ".join(missing[:6])))
            hits = [h for h in hits if h in ctx.pads]
        else:
            reason = val
            hits = _expand(ctx, key)
            if not hits:
                out.append((key, False, "quality.unconnected has %r, which matches no pin "
                                        "on the board: a stale declaration" % key))
        if not str(reason).strip():
            out.append((key, False, "quality.unconnected[%r] gives no reason" % key))
        for h in hits:
            declared.add(h)
            why[h] = reason
    for ref in sorted({k.rsplit(".", 1)[0] for k in actual - declared}, key=_nat):
        pins = sorted((k.rsplit(".", 1)[1] for k in actual - declared
                       if k.rsplit(".", 1)[0] == ref), key=_nat)
        out.append((ref, False, "%s (%s): pin(s) %s connect to nothing and are not declared "
                                "in quality.unconnected -- an idle pin on a part that was "
                                "meant to be full is how a mis-indexed loop shows"
                    % (ref, ctx.fps[ref].GetValue(), " ".join(pins))))
    for k in sorted(declared - actual, key=_nat):
        pad = ctx.pads[k]
        out.append((k, False, "%s is declared unconnected and is on net %s"
                    % (k, pad.GetNetname() or "(none)")))
    if not (actual - declared) and not (declared - actual):
        out.append(("unconnected", True, "%d unconnected pin(s), every one declared"
                    % len(actual)))
    # 2. functional groups: how many nets the design means, and how many pins on each
    groups = ctx.q.get("net_groups")
    if groups is None:
        out.append((ctx.name, False,
                    "%s declares no net_groups: say, for each repeated structure "
                    "(channels, zones, sensors, ways of a connector), how many distinct "
                    "nets its pins are on -- or [] with nothing repeated" % ctx.name))
        return out
    for g in groups:
        name = g.get("name", "?")
        if g.get("nets_like"):
            rx = re.compile(g["nets_like"])
            hit = sorted((n for n in ctx.by_net if rx.fullmatch(n)), key=_nat)
            problems = []
            if g.get("count") is not None and len(hit) != g["count"]:
                problems.append("%d net(s) named like %s where %d are meant"
                                % (len(hit), g["nets_like"], g["count"]))
            if g.get("pads") is not None:
                bad = [n for n in hit if len(ctx.by_net[n]) != g["pads"]]
                if bad:
                    problems.append("meant %d pads on each; %s" % (g["pads"], ", ".join(
                        "%s has %d" % (n, len(ctx.by_net[n])) for n in bad[:6])))
            if problems:
                out.append((name, False, "net group %r: %s" % (name, "; ".join(problems))))
            else:
                out.append((name, True, "net group %r: %d net(s)" % (name, len(hit))))
            continue
        pats = g.get("pins", [])
        pats = [pats] if isinstance(pats, str) else list(pats)
        pads = sorted({k for pat in pats for k in _expand(ctx, pat)}, key=_nat)
        if not pads:
            out.append((name, False, "net group %r: %s matches no pin" % (name, pats)))
            continue
        nets = collections.Counter()
        loose = []
        for k in pads:
            n = ctx.pads[k].GetNetname()
            if n:
                nets[n] += 1
            else:
                loose.append(k)
        problems = []
        if loose:
            problems.append("%s on no net" % ", ".join(loose[:6]))
        want = g.get("nets")
        if want is not None and len(nets) != want:
            problems.append("%d distinct net(s) where %d are meant" % (len(nets), want))
        each = g.get("each")
        if each is not None:
            bad = sorted((n for n, c in nets.items() if c != each), key=_nat)
            if bad:
                problems.append("meant %d of these pins per net; %s"
                                % (each, ", ".join("%s has %d" % (n, nets[n]) for n in bad[:6])))
        if g.get("pins_count") is not None and len(pads) != g["pins_count"]:
            problems.append("%d pin(s) match where %d are meant" % (len(pads), g["pins_count"]))
        if problems:
            out.append((name, False, "net group %r (%d pins): %s"
                        % (name, len(pads), "; ".join(problems))))
        else:
            out.append((name, True, "net group %r: %d pin(s) on %d net(s)%s"
                        % (name, len(pads), len(nets),
                           ", %d per net" % each if each is not None else "")))
    return out


# ── which manual rules a board cannot need ───────────────────────────────────────────
# A manual rule about a kind of circuit is signed BY THE SCRIPT when the board has none of
# the parts that make that circuit, so a passive board is not asked thirty questions about
# regulators. Conservative on purpose: absence of the part, never a guess about its use.
# A signature in the board's notes always wins.
def _census(ctx):
    kinds = collections.Counter(_prefix(r) for r in ctx.fps)
    names = [fp.GetFPIDAsString().split(":")[-1] for fp in ctx.fps.values()]
    nets = [n.upper() for n in ctx.by_net]
    usb = any({"A5", "B5"} <= {p.GetNumber() for p in fp.Pads()} for fp in ctx.fps.values()) \
        or any(re.search(r"USB|(^|_)D[PM]$|D[+-]$|VBUS", n) for n in nets)
    return {
        "ic": kinds["U"] > 0,
        "active": kinds["U"] + kinds["Q"] > 0,
        "inductor": kinds["L"] > 0,
        "ferrite": kinds["FB"] > 0,
        "transistor": kinds["Q"] > 0,
        "crystal": kinds["Y"] + kinds["X"] > 0,
        "switch": kinds["SW"] + kinds["S"] + kinds["K"] > 0,
        "polarised": kinds["D"] + kinds["LED"] > 0 or any(n.startswith("CP_") for n in names),
        "usb": usb,
        "bus": kinds["U"] > 0 or any(I2C.search(n) or "CAN" in n for n in nets),
        "thermal": kinds["U"] + kinds["Q"] > 0,
    }


NOT_APPLICABLE = {      # rule -> (census key that must be true for it to apply, the reason)
    "M2": ("polarised", "no diode, LED or polarised capacitor"),
    "M6": ("ic", "no IC: no high-speed bus"),
    "M7": ("ic", "no IC"),
    "M8": ("ic", "no IC: no configuration pins"),
    "M13": ("inductor", "no inductor: no switching regulator"),
    "M14": ("inductor", "no inductor"),
    "M15": ("ic", "no IC: no regulator"),
    "M17": ("ferrite", "no ferrite bead"),
    "M18": ("active", "no IC or transistor to back-power"),
    "M19": ("transistor", "no discrete transistor"),
    "M20": ("bus", "no IC and no I2C or CAN net"),
    "M21": ("ic", "no IC: no converter"),
    "M22": ("ic", "no IC: no op-amp"),
    "M23": ("usb", "no USB connector or net"),
    "M24": ("crystal", "no crystal"),
    "M25": ("thermal", "no IC or transistor to cool"),
    "M26": ("ic", "no IC: no directional link ends here"),
    "M27": ("ic", "no IC: no strap or debug pins"),
    "M35": ("ic", "no IC"),
    "M39": ("ic", "no IC: no unused pins"),
    "M41": ("switch", "no switch, button or relay"),
}


def doc_rules():
    """({A id: title}, [(M id, title, text)]) parsed from PCB_QUALITY.md."""
    auto, manual = {}, []
    try:
        text = open(DOC, encoding="utf-8").read()
    except OSError:
        return auto, manual
    for m in re.finditer(r"^### (A\d+) — (.+)$", text, re.M):
        auto[m.group(1)] = m.group(2).strip()
    for m in re.finditer(r"^- \*\*(M\d+) — (.+?)\*\*\s*(.*?)(?=^- \*\*M\d+|^#|^---|\Z)", text,
                         re.M | re.S):
        manual.append((m.group(1), m.group(2).strip().rstrip("."),
                       " ".join(m.group(3).split())))
    return auto, manual


def run(stem, verbose=True, brief=False):
    """Run every rule on the board at `stem`. Returns (fails, opens) and writes
    <stem>.quality.json. `brief` prints each open manual item as its title only."""
    auto, manual = doc_rules()
    if set(auto) != set(RULES):
        raise SystemExit("quality.py and PCB_QUALITY.md disagree about the automated rules: "
                         "code has %s, the document has %s"
                         % (sorted(RULES), sorted(auto)))
    ctx = Ctx(stem)
    results, fails, waived = [], 0, 0
    say = print if verbose else (lambda *a, **k: None)
    say("%s: quality pass (cadkit/PCB_QUALITY.md)" % ctx.name)
    for rid in sorted(RULES, key=lambda r: int(r[1:])):
        try:
            rows = RULES[rid](ctx)
        except Exception as exc:                     # a check that breaks is a finding
            rows = [("-", False, "the check itself failed: %r" % (exc,))]
        bad = []
        for subject, ok, text in rows:
            status = "ok" if ok else ("note" if ok is None else "FAIL")
            hard = ok is False and is_hard(rid, text)
            if ok is False:
                why = ctx.waived(rid, subject)
                if why and hard:
                    text += "  [a waiver is written for this and is IGNORED: a hard finding"\
                            " is fixed, not waived]"
                elif why:
                    status, text = "WAIVED", "%s  [waived: %s]" % (text, why)
                    waived += 1
                if status == "FAIL":
                    text = ("[hard] " if hard else "[soft] ") + text
            results.append({"rule": rid, "subject": subject, "status": status, "text": text,
                            "hard": hard})
            if status != "ok":
                bad.append((status, subject, text))
        nfail = sum(1 for s, _a, _b in bad if s == "FAIL")
        fails += nfail
        say("  %s %-4s %s -- %d checked%s" % ("FAIL" if nfail else "ok  ", rid, auto[rid],
                                              len(rows),
                                              (", %d FAIL" % nfail) if nfail else ""))
        for status, subject, text in bad:
            say("        %-6s %s" % (status, text))
        if nfail and rid in HINT:
            say("        -> %s" % HINT[rid])
    signed = ctx.q.get("manual", {}) or {}
    opens = 0
    census = _census(ctx)
    for mid, title, text in manual:
        note = signed.get(mid)
        key, why = NOT_APPLICABLE.get(mid, (None, None))
        if not note and key and not census[key]:
            results.append({"rule": mid, "subject": title, "status": "n/a", "text": why})
            if not brief:
                say("  n/a  %-4s %s -- %s" % (mid, title, why))
            continue
        results.append({"rule": mid, "subject": title, "status": "signed" if note else "OPEN",
                        "text": note or text})
        if note:
            say("  ok   %-4s %s -- %s" % (mid, title, note))
        else:
            opens += 1
            say("  OPEN %-4s %s" % (mid, title))
            if not brief:
                say("        %s" % text)
    stale = sorted(set(signed) - {m[0] for m in manual})
    for mid in stale:
        say("  !!   %s is signed in the board's notes and is not a rule in PCB_QUALITY.md" % mid)
    if opens and brief:
        say("        -> what each OPEN item asks for is in cadkit/PCB_QUALITY.md (or run "
            "quality.py without --brief); sign each in quality.manual with the evidence")
    with open(stem + ".quality.json", "w", encoding="utf-8") as fh:
        json.dump({"board": ctx.name, "fail": fails, "open": opens, "waived": waived,
                   "results": results}, fh, indent=1)
    say("%s: quality %d FAIL, %d OPEN manual item(s)%s"
        % (ctx.name, fails, opens, (", %d waived" % waived) if waived else ""))
    return fails, opens


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("usage: quality.py [--brief] <board stem> [<stem> ...]")
    total = 0
    for a in args:
        f, _o = run(os.path.abspath(a[:-10] if a.endswith(".kicad_pcb") else a),
                    brief="--brief" in sys.argv)
        total += f
    sys.exit(1 if total else 0)
