# -*- coding: utf-8 -*-
"""Shared fastener dimensions AND standard geometry for Archive/3D projects.

Sized/drawn ONCE here so every project pulls the SAME numbers and the SAME
insert/screw geometry instead of keeping its own copy.

════════════════════════════════════════════════════════════════════════════
ONE APPROACH: self-tap now, heat-set insert later.
════════════════════════════════════════════════════════════════════════════
Every screw hole that threads into plastic is the same shape, at every size:

    mouth ─┬─ Ø insert_pilot_d × insert_depth   (empty pocket, waiting)
           └─ Ø selftap_d, continuing to `depth` (the screw bites HERE)

On the first build the pocket is just air and the screw self-taps its own
thread below it — no insert, no extra assembly step. When those plastic threads
eventually strip, melt a heat-set insert into the pocket that was there all
along and switch to it. No reprint, no redesign. That is `cut_anchor()`.

Sizes differ only by CONSTANTS, gathered in a `FastenerSpec` (M2, M4 below).
The geometry functions are generic and take a spec; the `cut_m2_*` / `cut_m4_*`
names are thin wrappers that bind the spec, kept so existing call sites and
other projects don't move.

Derived, not invented:
  * selftap_d  = screw_d + 0.2  — modelled 0.1 mm/side over the major Ø because
                 FDM holes print UNDERSIZE; the as-printed hole lands near the
                 major Ø, which is what lets the screw cut its own thread.
  * shaft_clr_d= screw_d + 0.4  — 0.2 mm/side, screw spins free.
  * min_bite    = 5 × pitch     — five engaged threads is the least worth
                 relying on. M2: 5×0.4 = 2.0. M4: 5×0.7 = 3.5.
  * anchor_min_wall = insert_depth + min_bite — SIZE WALLS/LUGS/BOSSES TO THIS.

════════════════════════════════════════════════════════════════════════════
DEVIATIONS — allowed, but you must say why (they are greppable).
════════════════════════════════════════════════════════════════════════════
The wall budget is insert_depth + min_bite. When a wall cannot afford both, you
drop ONE end — and each escape demands a written reason, so no compromise ships
silently:

  1. cut_anchor(..., pocket=False, reason="…")   keep the self-tap, forfeit the
     insert upgrade path. For walls too thin to hold the pocket at all.
  2. cut_insert_bore(..., reason="…")            keep the insert, forfeit the
     self-tap. Pocket + plain clearance beyond, which no screw can bite. For
     holes with < anchor_min_wall that must still take a real thread, and for
     SET SCREWS (which must never self-tap: they hold position under load).
  3. cut_anchor(..., short_bite="…")             an anchor whose bite lands
     under min_bite. Holds, but it is the weakest kind of joint here.

BEFORE deviating, try `cut_boss_anchor()` — grow a boss and MAKE the room. That
is not a deviation, and it is usually available.

Prefer measuring over trusting: `measured_bite(solid, …)` reports the real
self-tap length left in the finished solid. A nominal `depth` says nothing about
a through-bore crossing a thin wall — only the solid knows.

Consume the same way as the other freecad/ helpers — add this folder to
sys.path, then import flat:

    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "freecad"))
    from fasteners import M2, M4, cut_anchor, cut_boss_anchor, measured_bite
    from fasteners import M2_SELFTAP_D, cut_m2_anchor, cut_m2_head_bore  # bound aliases
"""

import math
from dataclasses import dataclass
from typing import Optional

import cadquery as cq


# ════════════════════════════════════════════════════════════════════════════
# SPECS — the only thing that differs between sizes.
# ════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class FastenerSpec:
    """Everything the geometry below needs to draw one screw size."""
    name:           str
    screw_d:        float            # major thread Ø (nominal)
    pitch:          float            # thread pitch — sets min_bite
    selftap_d:      float            # modelled self-tap hole
    shaft_clr_d:    float            # clearance hole (screw spins free)
    insert_pilot_d: float            # heat-set insert pocket Ø
    insert_depth:   float            # pocket DEPTH (>= insert_l)
    insert_l:       float            # physical insert LENGTH
    insert_bore_d:  float            # the dummy insert's through-bore Ø
    boss_prot:      float            # how far a thin-wall boss protrudes
    boss_wall:      float = 1.0      # material around the pocket in that boss
    head_recess_d:  Optional[float] = None   # cap-head counterbore (None = headless)
    head_recess_h:  Optional[float] = None
    screw_l:        Optional[float] = None   # dummy screw length, if modelled

    @property
    def min_bite(self) -> float:
        """Shortest self-tap worth relying on: five engaged threads."""
        return 5.0 * self.pitch

    @property
    def anchor_min_wall(self) -> float:
        """Material an anchor wants: the pocket, plus a real bite under it."""
        return self.insert_depth + self.min_bite

    @property
    def boss_od(self) -> float:
        return self.insert_pilot_d + 2.0 * self.boss_wall


# M2 cap screw + McMaster 94459A110 heat-set insert.
M2 = FastenerSpec(
    name="M2", screw_d=2.0, pitch=0.4,
    selftap_d=2.2, shaft_clr_d=2.4,
    insert_pilot_d=3.3, insert_depth=3.5, insert_l=2.5, insert_bore_d=2.0,
    boss_prot=5.5, boss_wall=1.0,
    head_recess_d=4.1, head_recess_h=2.0,
)

# M4 set screw + heat-set insert. Headless (a set screw has no cap head), and its
# pocket is bored EXACTLY the insert size (melt fit, no margin): insert_depth ==
# insert_l. A set screw must NEVER self-tap — it holds position under load — so
# M4 holes legitimately use cut_insert_bore(reason=...), the sanctioned deviation.
M4 = FastenerSpec(
    name="M4", screw_d=4.0, pitch=0.7,
    selftap_d=4.2, shaft_clr_d=4.4,
    insert_pilot_d=6.0, insert_depth=5.0, insert_l=5.0, insert_bore_d=4.4,
    boss_prot=6.0, boss_wall=1.0,
    head_recess_d=None, head_recess_h=None, screw_l=10.0,
)


# ── Flat constant aliases (legacy; every project already imports these) ──────
M2_SCREW_D         = M2.screw_d
M2_SELFTAP_D       = M2.selftap_d
M2_SHAFT_CLR_D     = M2.shaft_clr_d
M2_HEAD_RECESS_D   = M2.head_recess_d
M2_HEAD_RECESS_H   = M2.head_recess_h
M2_INSERT_PILOT_D  = M2.insert_pilot_d
M2_INSERT_DEPTH    = M2.insert_depth
M2_INSERT_L        = M2.insert_l
M2_MIN_BITE        = M2.min_bite            # 2.0
M2_ANCHOR_MIN_WALL = M2.anchor_min_wall     # 5.5

M4_SCREW_D          = M4.screw_d
M4_SCREW_L          = M4.screw_l            # 10.0
M4_SELFTAP_D        = M4.selftap_d
M4_SHAFT_CLR_D      = M4.shaft_clr_d
M4_INSERT_D         = M4.insert_pilot_d     # historic name for the pocket Ø
M4_INSERT_L         = M4.insert_l
M4_INSERT_BOSS_PROT = M4.boss_prot
M4_MIN_BITE         = M4.min_bite           # 3.5
M4_ANCHOR_MIN_WALL  = M4.anchor_min_wall    # 8.5


# ════════════════════════════════════════════════════════════════════════════
# PRIMITIVES
# ════════════════════════════════════════════════════════════════════════════
# Holes take a direction VECTOR (it matches how a hole is actually drilled).
# Lengths measure from the nominal mouth face; `overshoot` extends the cutter
# backwards OUT of the material (dodging coincident-face booleans) without
# moving any real feature.

def _cyl(d, h, pnt, direction):
    return cq.Solid.makeCylinder(d / 2.0, h, cq.Vector(*pnt), cq.Vector(*direction))


def _unit(direction):
    return cq.Vector(*direction).normalized()


def _back(pnt, direction, overshoot):
    """`pnt` moved `overshoot` backwards along -direction (out of the material)."""
    return (cq.Vector(*pnt) - _unit(direction).multiply(overshoot)).toTuple()


def _fwd(pnt, direction, dist):
    return (cq.Vector(*pnt) + _unit(direction).multiply(dist)).toTuple()


def _dir_from(axis, deg):
    """The direction local +Z maps to under the legacy (axis, deg) rotation."""
    v = cq.Workplane(obj=_cyl(0.001, 1.0, (0, 0, 0), (0, 0, 1))).rotate((0, 0, 0), axis, deg)
    b = v.val().BoundingBox()
    return _unit((b.xmax + b.xmin, b.ymax + b.ymin, b.zmax + b.zmin))


def _oriented(s, axis, deg, pt):
    return s.rotate((0, 0, 0), axis, deg).translate(pt)


# ════════════════════════════════════════════════════════════════════════════
# CUTTERS — each returns the bare solid; each has a `cut_*` sibling.
# ════════════════════════════════════════════════════════════════════════════
def pocket_cutter(spec, pnt, direction, overshoot=0.0):
    """The heat-set insert pocket alone: Ø insert_pilot_d × insert_depth."""
    mouth = _back(pnt, direction, overshoot)
    return cq.Workplane(obj=_cyl(spec.insert_pilot_d, spec.insert_depth + overshoot,
                                 mouth, direction))


def selftap_cutter(spec, pnt, direction, length, overshoot=0.0):
    """Ø selftap_d bore — the screw cuts its own thread in this."""
    mouth = _back(pnt, direction, overshoot)
    return cq.Workplane(obj=_cyl(spec.selftap_d, length + overshoot, mouth, direction))


def clearance_cutter(spec, pnt, direction, length, overshoot=0.0):
    """Ø shaft_clr_d bore — the screw spins free (it threads in the FAR part)."""
    mouth = _back(pnt, direction, overshoot)
    return cq.Workplane(obj=_cyl(spec.shaft_clr_d, length + overshoot, mouth, direction))


def head_bore_cutter(spec, pnt, direction, clr_len, overshoot=0.0):
    """Cap-head counterbore + shaft clearance, both opening at the mouth."""
    if spec.head_recess_d is None:
        raise ValueError("%s is headless (a set screw) — it has no head recess."
                         % spec.name)
    mouth = _back(pnt, direction, overshoot)
    recess = _cyl(spec.head_recess_d, spec.head_recess_h + overshoot, mouth, direction)
    clr = _cyl(spec.shaft_clr_d, clr_len + overshoot, mouth, direction)
    return cq.Workplane(obj=recess.fuse(clr))


def anchor_cutter(spec, pnt, direction, depth, pocket=True, overshoot=0.0,
                  reason=None, short_bite=None):
    """THE standard hole — self-tap now, heat-set insert later.

    Ø selftap_d running `depth` from the mouth `pnt` along `direction`, plus a
    concentric Ø insert_pilot_d × insert_depth pocket opening at the SAME mouth.
    `depth` is the full bore depth from the mouth face, pocket included, so the
    self-tapping length is (depth - insert_depth).

    The mouth is the face the INSERT enters — usually also the screw's entry
    face, but in a pinch clamp the screw arrives from the opposite side.

    Deviations must be justified in words (see module docstring):
      pocket=False  -> requires reason="…"
      bite<min_bite -> requires short_bite="…"
    """
    if depth <= 0:
        raise ValueError("anchor_cutter(%s): depth must be > 0, got %r"
                         % (spec.name, depth))
    if not pocket:
        if not reason:
            raise ValueError(
                "anchor_cutter(%s): pocket=False forfeits the heat-set-insert "
                "upgrade path. That is a last resort — pass reason='…' saying why "
                "the pocket will not fit (e.g. 'floor thinner than the pocket'). "
                "Try cut_boss_anchor() first: grow a boss and make the room."
                % spec.name)
        return selftap_cutter(spec, pnt, direction, depth, overshoot)

    bite = depth - spec.insert_depth
    if bite <= 0:
        raise ValueError(
            "anchor_cutter(%s): depth %.2f <= insert_depth %.2f — the pocket "
            "would consume the whole bore, leaving nothing to self-tap. Deepen "
            "the hole, grow a boss (cut_boss_anchor), or pass pocket=False with "
            "a reason." % (spec.name, depth, spec.insert_depth))
    if bite < spec.min_bite and not short_bite:
        raise ValueError(
            "anchor_cutter(%s): only %.2f mm of self-tap below the pocket "
            "(min_bite = %.2f = 5 threads). Give the wall %.2f mm "
            "(anchor_min_wall), grow a boss (cut_boss_anchor), or acknowledge it "
            "with short_bite='…' explaining why the thin bite is acceptable."
            % (spec.name, bite, spec.min_bite, spec.anchor_min_wall))

    mouth = _back(pnt, direction, overshoot)
    bore = _cyl(spec.selftap_d, depth + overshoot, mouth, direction)
    bore = bore.fuse(_cyl(spec.insert_pilot_d, spec.insert_depth + overshoot,
                          mouth, direction))
    return cq.Workplane(obj=bore)


def insert_bore_cutter(spec, pnt, direction, clr_len, overshoot=0.0, reason=None):
    """DEVIATION — insert MANDATORY, no self-tap fallback.

    Pocket at the mouth, then Ø shaft_clr_d *clearance* running `clr_len` further
    (measured from the pocket's inner end). The screw threads into the melted-in
    insert; the clearance beyond is not something a screw can bite. Correct where
    the screw must pull two lugs together, where it passes on into a far part, or
    for a SET SCREW (which must not self-tap). Requires reason='…'.
    """
    if not reason:
        raise ValueError(
            "insert_bore_cutter(%s): this hole REQUIRES a heat-set insert from "
            "day one — there is no self-tap fallback. Prefer cut_anchor(). If you "
            "truly need it, pass reason='…' (e.g. 'set screw: must not self-tap', "
            "or 'only 3.6 mm of wall')." % spec.name)
    mouth = _back(pnt, direction, overshoot)
    inner = _fwd(pnt, direction, spec.insert_depth)
    pocket = _cyl(spec.insert_pilot_d, spec.insert_depth + overshoot, mouth, direction)
    clr = _cyl(spec.shaft_clr_d, clr_len, inner, direction)
    return cq.Workplane(obj=pocket.fuse(clr))


# --- `cut_*` siblings: apply the cutter to a workplane. ----------------------
def cut_pocket(spec, w, pnt, direction, overshoot=0.0):
    return w.cut(pocket_cutter(spec, pnt, direction, overshoot))


def cut_selftap(spec, w, pnt, direction, length, overshoot=0.0):
    return w.cut(selftap_cutter(spec, pnt, direction, length, overshoot))


def cut_clearance(spec, w, pnt, direction, length, overshoot=0.0):
    return w.cut(clearance_cutter(spec, pnt, direction, length, overshoot))


def cut_head_bore(spec, w, pnt, direction, clr_len, overshoot=0.0):
    return w.cut(head_bore_cutter(spec, pnt, direction, clr_len, overshoot))


def cut_anchor(spec, w, pnt, direction, depth, pocket=True, overshoot=0.0,
               reason=None, short_bite=None):
    return w.cut(anchor_cutter(spec, pnt, direction, depth, pocket, overshoot,
                               reason, short_bite))


def cut_insert_bore(spec, w, pnt, direction, clr_len, overshoot=0.0, reason=None):
    return w.cut(insert_bore_cutter(spec, pnt, direction, clr_len, overshoot, reason))


def anchor_bite(spec, depth):
    """Nominal self-tap length below the pocket. See measured_bite() for the truth."""
    return depth - spec.insert_depth


# ════════════════════════════════════════════════════════════════════════════
# BOSSES — grow material instead of deviating. Try this FIRST.
# ════════════════════════════════════════════════════════════════════════════
def cut_boss_anchor(spec, w, pt, direction, depth=None):
    """Where the wall is too thin, add a protruding boss and put a standard
    ANCHOR in it. `direction` points INTO the material (the screw's travel);
    the boss protrudes boss_prot backwards from `pt`, so the pocket opens on
    the boss's outer face and the self-tap runs on toward the tip.

    This is the preferred answer to a thin wall — it makes the room rather than
    forfeiting the pocket or the bite. Default depth = boss_prot (>= anchor_min
    _wall for both specs, so the bite always clears min_bite)."""
    bp = spec.boss_prot
    if depth is None:
        depth = bp
    base = _back(pt, direction, bp)
    w = w.union(cq.Workplane(obj=_cyl(spec.boss_od, bp, base, direction)))
    return cut_anchor(spec, w, base, direction, depth)


def cut_boss_insert_bore(spec, w, pt, direction, clr_len, reason=None):
    """Thin-wall boss hosting an insert-MANDATORY bore (pocket + clearance to the
    working tip). This is the SET-SCREW shape. Requires reason='…' like any
    insert-mandatory hole."""
    bp = spec.boss_prot
    base = _back(pt, direction, bp)
    w = w.union(cq.Workplane(obj=_cyl(spec.boss_od, bp, base, direction)))
    w = w.cut(pocket_cutter(spec, base, direction))
    if not reason:
        raise ValueError(
            "cut_boss_insert_bore(%s): insert-mandatory. Pass reason='…', or use "
            "cut_boss_anchor() for the standard self-tap+pocket boss." % spec.name)
    inner = _fwd(base, direction, spec.insert_depth)
    return w.cut(cq.Workplane(obj=_cyl(spec.shaft_clr_d, clr_len, inner, direction)))


# ════════════════════════════════════════════════════════════════════════════
# DUMMIES — fit-check only. They go in assembly.step, never in a part STEP.
# ════════════════════════════════════════════════════════════════════════════
def insert(spec):
    """Dummy heat-set insert: Ø insert_pilot_d × insert_l TUBE (Ø insert_bore_d
    bore), axis +Z, top at z=0 (extends -Z). Drawn at the POCKET Ø — the envelope
    it occupies once melted in, which is what a fit-check wants to see."""
    body = cq.Workplane(obj=_cyl(spec.insert_pilot_d, spec.insert_l,
                                 (0, 0, -spec.insert_l), (0, 0, 1)))
    bore = cq.Workplane(obj=_cyl(spec.insert_bore_d, spec.insert_l + 2,
                                 (0, 0, -spec.insert_l - 1), (0, 0, 1)))
    return body.cut(bore)


def _rot_z_onto(shape, direction):
    v = _unit(direction)
    z = cq.Vector(0, 0, 1)
    axis = z.cross(v)
    ang = math.degrees(math.acos(max(-1.0, min(1.0, z.dot(v)))))
    if axis.Length > 1e-9:
        return shape.rotate((0, 0, 0), axis.toTuple(), ang)
    if z.dot(v) < 0:
        return shape.rotate((0, 0, 0), (1, 0, 0), 180.0)
    return shape


def seated_insert(spec, pnt, direction):
    """The insert dummy seated in the pocket of a cut_anchor / cut_insert_bore at
    the SAME (pnt, direction): it fills the pocket from the mouth inward."""
    ins = _rot_z_onto(insert(spec).translate((0, 0, spec.insert_l)), direction)
    return ins.translate(cq.Vector(*pnt).toTuple())


def boss_insert(spec, pt, direction):
    """The insert dummy seated in a cut_boss_* pocket (SAME pt/direction)."""
    ins = insert(spec).translate((0, 0, -spec.boss_prot + spec.insert_l))
    return _rot_z_onto(ins, direction).translate(cq.Vector(*pt).toTuple())


def screw(spec, length=None):
    """Dummy headless screw, axis Z, top at z=0 (extends -Z), 2 mm hex socket."""
    length = length or spec.screw_l
    if length is None:
        raise ValueError("screw(%s): no screw_l in the spec; pass length=" % spec.name)
    body = cq.Workplane(obj=_cyl(spec.screw_d, length, (0, 0, -length), (0, 0, 1)))
    hexd = 2.0 / math.cos(math.radians(30))
    socket = cq.Workplane("XY").polygon(6, hexd).extrude(-3.0).translate((0, 0, 0.5))
    return body.cut(socket)


# ════════════════════════════════════════════════════════════════════════════
# MEASUREMENT — a nominal depth cannot see a thin wall. The solid can.
# ════════════════════════════════════════════════════════════════════════════
def measured_bite(solid, pnt, direction, spec, has_pocket=True, max_scan=40.0, step=0.02):
    """REAL self-tap length left in a finished solid, below the pocket.

    A nominal `depth` says nothing about a through-bore crossing a thin wall —
    e.g. a full-width Ø2.2 bore through a 4.6 mm wall nominally has 20 mm of
    'bite' but really has 1.1 mm. Only the solid knows.

    Walks the finished solid just past the pocket and counts the contiguous run
    where BOTH hold: inside the bore radius is VOID (the self-tap hole is really
    there) and just outside it is MATERIAL (there is plastic for the thread to
    cut). Either condition failing ends the bite — so a bore that runs out of
    wall, and a wall that runs out of bore, both report honestly.

    `solid` is a cq.Shape/Solid (pass `part.val()`). `pnt`/`direction` are the
    anchor's mouth and bore direction, as handed to cut_anchor().
    """
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON
    from OCP.gp import gp_Pnt

    clf = BRepClass3d_SolidClassifier(solid.wrapped)

    def inside(v):
        clf.Perform(gp_Pnt(v.x, v.y, v.z), 1e-7)
        return clf.State() in (TopAbs_IN, TopAbs_ON)

    ax = _unit(direction)
    perp = cq.Vector(0, 0, 1) if abs(ax.z) < 0.9 else cq.Vector(1, 0, 0)
    perp = ax.cross(perp).normalized()
    mouth = cq.Vector(*pnt)
    r_in = 0.40 * spec.selftap_d / 2.0                                  # inside the bore
    r_out = 0.5 * (spec.selftap_d / 2.0 + spec.insert_pilot_d / 2.0)    # bore..pocket annulus
    o_in = mouth + perp.multiply(r_in)
    o_out = mouth + perp.multiply(r_out)

    t = (spec.insert_depth if has_pocket else 0.0) + step / 2.0
    bite = 0.0
    while t <= max_scan:
        if inside(o_in + ax.multiply(t)):          # bore ended — no hole left
            break
        if not inside(o_out + ax.multiply(t)):     # wall ended — no plastic left
            break
        bite += step
        t += step
    return round(bite, 3)


def assert_bite(solid, pnt, direction, spec, short_bite=None, label=""):
    """Raise unless the MEASURED bite clears spec.min_bite. `short_bite='…'`
    acknowledges a known-thin site (the same escape cut_anchor takes)."""
    b = measured_bite(solid, pnt, direction, spec)
    if b < spec.min_bite and not short_bite:
        raise ValueError(
            "assert_bite(%s%s): measured self-tap is %.2f mm, under min_bite "
            "%.2f. Thicken the wall to anchor_min_wall (%.2f), grow a boss, or "
            "pass short_bite='…'." % (spec.name, (" " + label) if label else "",
                                      b, spec.min_bite, spec.anchor_min_wall))
    return b


# ════════════════════════════════════════════════════════════════════════════
# BOUND ALIASES — same geometry, spec pre-bound. Existing call sites use these.
# ════════════════════════════════════════════════════════════════════════════
def m2_anchor_cutter(pnt, direction, depth, pocket=True, overshoot=0.0,
                     reason=None, short_bite=None):
    return anchor_cutter(M2, pnt, direction, depth, pocket, overshoot, reason, short_bite)


def cut_m2_anchor(w, pnt, direction, depth, pocket=True, overshoot=0.0,
                  reason=None, short_bite=None):
    return cut_anchor(M2, w, pnt, direction, depth, pocket, overshoot, reason, short_bite)


def m2_insert_bore_cutter(pnt, direction, clr_len, overshoot=0.0, reason=None):
    return insert_bore_cutter(M2, pnt, direction, clr_len, overshoot, reason)


def cut_m2_insert_bore(w, pnt, direction, clr_len, overshoot=0.0, reason=None):
    return cut_insert_bore(M2, w, pnt, direction, clr_len, overshoot, reason)


def m2_clearance_cutter(pnt, direction, length, overshoot=0.0):
    return clearance_cutter(M2, pnt, direction, length, overshoot)


def cut_m2_clearance(w, pnt, direction, length, overshoot=0.0):
    return cut_clearance(M2, w, pnt, direction, length, overshoot)


def m2_head_bore_cutter(pnt, direction, clr_len, overshoot=0.0):
    return head_bore_cutter(M2, pnt, direction, clr_len, overshoot)


def cut_m2_head_bore(w, pnt, direction, clr_len, overshoot=0.0):
    return cut_head_bore(M2, w, pnt, direction, clr_len, overshoot)


def cut_m2_boss(w, pt, direction, depth=None):
    return cut_boss_anchor(M2, w, pt, direction, depth)


def m2_anchor_bite(depth):
    return anchor_bite(M2, depth)


def m2_insert():
    return insert(M2)


def seated_m2_insert(pnt, direction):
    return seated_insert(M2, pnt, direction)


def m2_boss_insert(pt, direction):
    return boss_insert(M2, pt, direction)


# --- M4 aliases keep the legacy (axis, deg) orientation of their call sites. --
_M4_SET_SCREW_REASON = "set screw: must never self-tap — it holds position under load"


def set_screw():
    """Dummy M4×10 cup-tip set screw, axis Z, top at z=0 (extends -Z)."""
    return screw(M4)


def m4_insert():
    return insert(M4)


def cut_m4_pocket(w, mouth_pt, axis, deg):
    """The STANDARD Ø6×5 melt-fit pocket, mouth at `mouth_pt`, bore +axis."""
    return cut_pocket(M4, w, mouth_pt, _dir_from(axis, deg))


def seated_m4_insert(mouth_pt, axis, deg):
    return seated_insert(M4, mouth_pt, _dir_from(axis, deg))


def cut_m4_boss(w, pt, axis, deg, clr_len=(M4.screw_l - M4.insert_l) + 2.0):
    """Set-screw boss: Ø8 boss, Ø6×5 melt pocket, Ø4.4 clearance to the tip."""
    return cut_boss_insert_bore(M4, w, pt, _dir_from(axis, deg), clr_len,
                                reason=_M4_SET_SCREW_REASON)


def m4_boss_insert(pt, axis, deg):
    return boss_insert(M4, pt, _dir_from(axis, deg))
