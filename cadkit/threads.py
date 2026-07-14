"""Self-supporting 45° screw threads for CadQuery / OpenCASCADE — the reliable way
to cut a helical thread that OCCT won't silently mangle. Self-contained (only needs
`cadquery`); import it from the vendored package (no path hack needed).

    from cadkit.threads import threaded_rod, cut_thread, teardrop_thread_cutter

    nut_cutter = threaded_rod(minor_d=11, major_d=13, pitch=4, length=20)   # short rods, nut cutters, coupons
    piston     = body.cut(nut_cutter)                                       # -> internal thread

    # A long screw: build a SMOOTH blank (crest-Ø rod + shaft + head), then subtract
    # the thread LAST, then mill any flat AFTER that:
    screw = cut_thread(blank, minor_d=11, major_d=13, pitch=4, length=146, z=64)
    screw = screw.cut(flat_box)

    # A SIDEWAYS female thread (screw hole whose axis prints HORIZONTAL): a plain round
    # bore sags at its top arc. Use this cutter — full round bore + a self-supporting
    # HEXAGON peak on +Y (the print-up side). ALWAYS call this; never re-model it.
    hole = block.cut(teardrop_thread_cutter(minor_d=4.8, major_d=6.4, pitch=3.5,
                     length=14, z=z0, peak_h=3.75, over_lo=0.0), clean=False)

PUBLIC cutters — reuse them, do NOT hand-roll a thread: `threaded_rod` (short
internal/nut threads), `cut_thread` (long screw from a smooth blank),
`teardrop_thread_cutter` (sideways/horizontal female thread), and the MULTI-START
family for quarter-turn caps — `multistart_rod` (nut cutter) and
`cut_multistart_thread` (male), where `spacing` is the caliper ridge-to-ridge
distance and each helix advances lead = spacing·starts per turn (a 4-start,
spacing-4 thread closes 4 mm per quarter turn and its cross-section is identical
to the proven pitch-4 profile). See THREADS_README.md for the whole story. The rules it bakes in (every violation is
a SILENT failure — a smooth or half-filled rod, 0 solids, or a multi-minute hang —
so ALWAYS probe the crest solid/void up Z; never trust the eye or `solids==1`):

  * CUT helical valleys from a solid crest-Ø blank. Never union a ridge onto a core
    (OCCT drops the core → a hollow spring).
  * 45° flanks → self-supporting: a NUT prints with its axis VERTICAL, no support in
    the bore; the screw side-prints well too. Needs depth = (major-minor)/2 ≤ pitch/2.
  * The valley profile is a 4-POINT quad. Extra vertices make .cut() wipe the part.
  * TILE a long helix in abutting, phase-aligned SEGMENTS (a single sweep is clean to
    ~100 mm, then wipes to 0 solids). Segments must ABUT, not overlap (an overlapping
    cut no-ops → the later span stays FILLED). Sweep AND blank heights must be whole
    turns (a partial turn, or a sweep reaching the top of a non-whole-turn cylinder,
    wipes the part).
  * Cut the thread LAST and ALONE — booleans on the many-face thread are slow. Build
    the smooth blank first; cut the thread; mill the flat AFTER (flat-before-thread
    makes the full-helix cutter overlap the flat void → no-op → filled).
  * Use clean=False on every thread boolean (the post-cut unify crashes) and do NOT
    ShapeFix/heal the threaded parts (heal's unify chokes too). They export fine.
"""

import math

import cadquery as cq

_SEG_LEN = 72.0          # segment tile length: < the ~100 mm single-sweep limit, a multiple of common pitches
_OVERSHOOT = 0.3         # radial overshoot of the valley past the crest (avoids a coincident cut face)


def _cyl(d, h, z=0.0):
    return cq.Workplane("XY").workplane(offset=z).circle(d / 2.0).extrude(h)


def _cone(d_bottom, d_top, h, z):
    return (cq.Workplane("XY").workplane(offset=z).circle(d_bottom / 2.0)
            .workplane(offset=h).circle(d_top / 2.0).loft())


def _valley_profile(minor_d, major_d, spacing):
    """The 4-point 45° trapezoid valley quad, in (radius, axial) coordinates.
    `spacing` is the AXIAL ridge-to-ridge distance — the pitch for a
    single-start thread, lead/starts for a multi-start one. Raises on the two
    geometry errors that would otherwise fail SILENTLY (a no-op cutter)."""
    core_r = minor_d / 2.0
    crest_r = major_d / 2.0
    depth = crest_r - core_r
    if depth > spacing / 2.0 + 1e-6:
        raise ValueError(
            f"thread depth {depth:.2f} > spacing/2 {spacing / 2:.2f}: 45° flanks "
            f"need depth ≤ spacing/2. Raise the spacing or the minor Ø.")
    flat = (spacing - 2.0 * depth) / 2.0         # equal crest + root flats (axial)
    hw_root = flat / 2.0                          # valley half-width at the root floor
    hw_out = flat / 2.0 + (crest_r + _OVERSHOOT - core_r)   # at the overshoot
    if 2.0 * hw_out >= spacing - 1e-6:
        raise ValueError(
            f"valley {2 * hw_out:.2f} wide at the overshoot ≥ spacing {spacing}: "
            f"adjacent turns/starts would overlap into an invalid cutter "
            f"(silent no-op). Raise the spacing or shrink the depth.")
    return [(core_r, -hw_root), (crest_r + _OVERSHOOT, -hw_out),
            (crest_r + _OVERSHOOT, hw_out), (core_r, hw_root)]


def thread_segments(minor_d, major_d, pitch, length):
    """A LIST of ABUTTING (non-overlapping) helical valley cutters, base at z=0,
    tiling `length`. CUT THEM SEQUENTIALLY (`solid = solid.cut(seg)` in a loop) from
    a crest-Ø blank; don't union them first (unioning the overlapping helices fills).

    Each is swept from a fresh short helix, rotated by the running phase
    (360°·z0/pitch) and dropped at z0, so the valleys form ONE continuous single-
    start thread across the seams. Valley = 4-point 45° trapezoid, inner edge at
    minor_r (never reaches the core), width < pitch (turns never self-overlap)."""
    r_mid = (minor_d + major_d) / 4.0
    gpts = _valley_profile(minor_d, major_d, pitch)
    segs = []
    for i in range(int(math.ceil(length / _SEG_LEN))):
        z0 = i * _SEG_LEN
        need = min(_SEG_LEN, length - z0)         # ABUT (no overlap — overlap no-ops the cut)
        if need <= 1e-6:
            break
        h = math.ceil(need / pitch - 1e-6) * pitch   # whole turns (a partial turn wipes the part)
        seg = cq.Workplane("XZ").polyline(gpts).close().sweep(cq.Workplane("XY").add(
            cq.Wire.makeHelix(pitch=pitch, height=h, radius=r_mid)), isFrenet=True)
        segs.append(seg.rotate((0, 0, 0), (0, 0, 1), 360.0 * z0 / pitch).translate((0, 0, z0)))
    return segs


def threaded_rod(minor_d, major_d, pitch, length, z=0.0):
    """A self-supporting 45° threaded ROD (crest-Ø solid with the valleys cut) plus
    lead-in chamfers at both ends. Use for SHORT rods, nut cutters and coupons. For a
    long screw, build a blank and use cut_thread() instead. The rod height is rounded
    UP to a whole turn (a non-whole-turn cylinder wipes when the helix reaches its
    top); the ~pitch of extra is a harmless lead-in / cuts air above the mating part."""
    core_r = minor_d / 2.0
    crest_r = major_d / 2.0
    H = math.ceil(length / pitch - 1e-6) * pitch
    rod = _cyl(2.0 * crest_r, H)
    for seg in thread_segments(minor_d, major_d, pitch, H):
        rod = rod.cut(seg, clean=False)
    run = min(3.0, H / 4.0)
    bevel = crest_r + 1.0
    bot = _cyl(2 * bevel, run, z=0.0).cut(_cone(2 * core_r, 2 * bevel, run, 0.0))
    top = _cyl(2 * bevel, run, z=H - run).cut(_cone(2 * bevel, 2 * core_r, run, H - run))
    return rod.cut(bot, clean=False).cut(top, clean=False).translate((0, 0, z))


_PK_OVER = 0.5          # peak overshoot past the rod ends (opens the teardrop at the socket mouth)


def teardrop_thread_cutter(minor_d, major_d, pitch, length, z=0.0, peak_h=None,
                           over_lo=_PK_OVER, over_hi=_PK_OVER):
    """Cutter for a self-supporting SIDEWAYS female thread — a threaded rod PLUS a HEXAGON
    peak UNIONED onto its +Y side. Cut it from a block whose PRINT-UP direction is +Y.

    This keeps the FULL round threaded bore (a round screw slides all the way in) and ADDS
    a self-supporting attic above it. Do NOT instead slice the top off the bore — a full
    round screw needs that top, and a secant/gable cut leaves solid material where the
    screw's upper half must go.

    The peak is a HEXAGON (not a plain teardrop), because the transition from round threads
    to the smooth attic must happen on 45° PLANES to cut the thread ridges CLEANLY. A plain
    teardrop / trapezoid meets the bore on a HORIZONTAL edge (y = tan): that flat plane
    slices each 45°-flanked thread tooth into a thin sub-nozzle sliver. The hexagon replaces
    that horizontal edge with two 45° edges on the lines y = ±x — the same 45° as the thread
    flanks — so the top-wedge ridges end clean. Its left/right corners (where a +45° meets a
    −45° edge, at the crest-circle tangent points (±tan, tan)) are 90°.

    Profile (crest frame, +Y up), widest at the 90° corners (±tan, tan):
        top flat (±half, peak_h) ─ upper 45° edges ─ CORNERS (±tan, tan)
                                 ─ lower 45° edges (on y=±x) ─ bottom flat (±half, 2·tan−peak_h)
    The whole hexagon is unioned, so its lower half (inside the round bore) only trims the
    top ~90° of ridges along y=±x and never narrows the bore.

    peak_h = corner-to-tip height above the axis; default (major/2)·√2 is the FULL point.
    A smaller peak_h truncates the tip to a short self-supporting flat bridge (and, by the
    mirror, gives the bottom flat) — use it when a full point won't fit the wall above.

    over_lo / over_hi = how far the hexagon peak overshoots the rod past the z / z+H ends.
    The overshoot opens the teardrop cleanly where the socket exits into air (the MOUTH), so
    keep it there. But at a BLIND end the peak would poke past the round bore and drill a
    hexagon pocket deeper than the circular thread bore (two visible depths) — pass 0 for
    that end. Rod ends stay at exactly [z, z+H] regardless.

    Returns ONE solid (rod ∪ hexagon); translate/rotate it into place, then `solid.cut(it,
    clean=False)`. Keep clean=False and don't heal (thread rules)."""
    R = major_d / 2.0
    full = R * math.sqrt(2.0)
    peak_h = full if peak_h is None else min(peak_h, full)
    tan = R / math.sqrt(2.0)                 # 45° tangent points / 90° corners at (±tan, tan)
    half = full - peak_h                     # flat half width (0 → a full point → a diamond)
    bot = 2.0 * tan - peak_h                  # bottom flat height = mirror of peak_h over y=tan
    if half < 0.05:
        prof = [(tan, tan), (0.0, full), (-tan, tan), (0.0, 2.0 * tan - full)]
    else:
        prof = [(tan, tan), (half, peak_h), (-half, peak_h),
                (-tan, tan), (-half, bot), (half, bot)]
    H = math.ceil(length / pitch - 1e-6) * pitch          # match threaded_rod's whole-turn height
    peak = (cq.Workplane("XY").polyline(prof).close().extrude(H + over_lo + over_hi)
            .translate((0, 0, z - over_lo)))
    return threaded_rod(minor_d, major_d, pitch, length, z=z).union(peak, clean=False)


def cut_thread(blank, minor_d, major_d, pitch, length, z=0.0):
    """Subtract a self-supporting thread from an existing SMOOTH `blank` solid, over a
    whole number of turns starting at height z. Build the blank fully smooth first
    (crest-Ø rod + shaft + head), call this, THEN mill any flat afterwards — the flat
    must come after the thread, or the full-helix cutter overlaps the flat void and the
    cut no-ops. The span is rounded DOWN to a whole turn so the thread ends inside the
    blank (overshooting into a smaller-Ø shaft above grazes it and leaves a thin
    degenerate face). Returns the threaded solid (un-healed; keep clean=False)."""
    turns_len = math.floor(length / pitch + 1e-6) * pitch
    out = blank
    for seg in thread_segments(minor_d, major_d, pitch, turns_len):
        out = out.cut(seg.translate((0.0, 0.0, z)), clean=False)
    return out


# ── Multi-start (quarter-turn) threads ───────────────────────────────────────
# A multi-start thread is the SAME cross-section as a single-start thread of
# pitch = `spacing` (the caliper ridge-to-ridge distance), swept along `starts`
# steeper helices: lead = spacing·starts per turn. A 4-start spacing-4 thread
# advances 4 mm per quarter turn — that's how quarter-turn caps close — while
# looking locally identical to the print-proven pitch-4 profile.


def multistart_valleys(minor_d, major_d, spacing, starts, length, z=0.0):
    """Valley cutters for a STARTS-start thread COVERING [z, z+length], all
    starts. Sweep heights are WHOLE turns of the LEAD (rule 5), so the sweeps
    RUN OUT upward past z+length — the region above must be air or a
    sub-minor-Ø section. Below z they extend only ~one groove half-width
    (thread run-in — plan for the shallow helical notch it leaves in a
    shoulder). CUT SEQUENTIALLY with clean=False; never union the cutters.
    Phase is 360°·z/lead + 360°·i/starts, so geometry is position-independent
    and chunks of long threads stay continuous across seams."""
    lead = spacing * starts
    if lead > _SEG_LEN:
        raise ValueError(
            f"lead {lead} > {_SEG_LEN}: one whole turn exceeds the single-sweep "
            f"limit — reduce starts or spacing")
    gpts = _valley_profile(minor_d, major_d, spacing)
    r_mid = (minor_d + major_d) / 4.0
    seg_len = math.floor(_SEG_LEN / lead) * lead          # whole leads per sweep
    segs = []
    z0 = 0.0
    while z0 < length - 1e-6:
        h = min(seg_len, math.ceil((length - z0) / lead - 1e-6) * lead)
        sweep = (cq.Workplane("XZ").polyline(gpts).close()
                 .sweep(cq.Workplane("XY").add(
                     cq.Wire.makeHelix(pitch=lead, height=h, radius=r_mid)),
                     isFrenet=True))
        for i in range(starts):
            segs.append(sweep
                        .rotate((0, 0, 0), (0, 0, 1),
                                360.0 * (z + z0) / lead + 360.0 * i / starts)
                        .translate((0, 0, z + z0)))
        z0 += h
    return segs


def multistart_rod(minor_d, major_d, spacing, starts, length, z=0.0, bevel=2.0):
    """A STARTS-start threaded ROD over EXACTLY [z, z+length] — no whole-turn
    height rounding, because a quarter-turn nut band is much shorter than one
    lead. The valley sweeps are based a spacing below the rod and pass
    THROUGH both rod faces, running out in air: rule 5's failure mode is a
    sweep ENDING at a blank face, not passing through it (validated by crest
    probes in superglue-cap). Use as a NUT CUTTER
    (`body.cut(rod, clean=False)`); `bevel` (mm, 0 to skip) cuts a conical
    lead-in at the BOTTOM end — the mouth."""
    rod = _cyl(major_d, length, z=z)
    for seg in multistart_valleys(minor_d, major_d, spacing, starts,
                                  length + 2.0 * spacing, z=z - spacing):
        rod = rod.cut(seg, clean=False)
    if bevel:
        core_r, brim = minor_d / 2.0, major_d / 2.0 + 1.0
        bot = _cyl(2 * brim, bevel, z=z).cut(_cone(2 * core_r, 2 * brim, bevel, z))
        rod = rod.cut(bot, clean=False)
    return rod


def cut_multistart_thread(blank, minor_d, major_d, spacing, starts, length, z=0.0):
    """Subtract a STARTS-start MALE thread from a SMOOTH `blank` over
    [z, z+length]. Same contract as cut_thread — build the blank fully smooth
    first, cut the thread LAST, mill any flat after — plus the multistart
    run-out rules from multistart_valleys: a shallow helical notch a groove
    half-width below z, and whole-lead run-out above z+length (air or
    sub-minor-Ø only up there). Returns the threaded solid (un-healed)."""
    out = blank
    for seg in multistart_valleys(minor_d, major_d, spacing, starts, length, z=z):
        out = out.cut(seg, clean=False)
    return out
