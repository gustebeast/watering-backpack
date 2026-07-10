"""joinery.py — printable mortise-and-tenon slide joints (dull arrowhead).

See JOINERY_README.md for the full story. THE standard recipe — a tenon on a
sideways-printed (+Y build) host mated to a mortise in a flat-printed (+Z
build) host — is `ramp=True, hook_h=...` (print-validated in PETG; plain
`ramp=True` without a hook cams apart along the up-ramp diagonal and survives
only as a demo):

    from cadkit.joinery import arrow_tenon, arrow_mortise

    # print-validated 0.8-nozzle numbers (every face ≥ one bead); scale beads
    # not ratios for other nozzles. neck rule: stem_h = wanted_neck + clearance.
    J = dict(stem_w=2.4, head_w=4.0, stem_h=0.9, tip_w=0.8, ramp=True, hook_h=0.8)
    ten = arrow_tenon(length=5.5, **J)                      # +Y-printed host
    cut = arrow_mortise(length=12, clearance=0.1, **J)      # +Z-printed host
    host  = host.union(ten.translate(...))      # rail grows the tenon
    other = other.cut(cut.translate(...))       # ring gets the cavity

CONVENTIONS
- The profile lives in the local Y-Z plane and is extruded along +X — the
  SLIDE axis. The mortise part installs by sliding -X: relative to it the
  tenon travels +X through the cavity, entering at the cavity's OPEN -X end
  and halting against its +X END WALL — the hard stop. An external preload
  toward -X (our rubber band) then keeps the stop loaded; the only escape
  (the part sliding back +X) works against that preload.
- z=0 is the MATING PLANE (host surface the tenon grows from / the face the
  mortise opens through). The tenon extends `root` below it (union it into
  its host — volumetric fusion, never coplanar). The mortise cutter extends
  `drop` below it so the cavity opens cleanly through the host's face.
- The joint constrains ±Y and +Z (lift) by shape, -X by the stop wall; +X is
  free by design (that's the install/uninstall direction the preload guards).

VARIANTS (by print orientation of each part; more combos welcome — add them
here like threads.py grew):
- ramp=False — symmetric dull arrowhead. Mortise host AND tenon host both
  print -Z→+Z (tenon standing up).
- ramp=True  — the -Y half of the arrowhead is replaced by one straight 45°
  ramp so the TENON prints on a -Y→+Y host (mortise host still -Z→+Z).
  Point the ramp side toward the tenon host's PRINT BED.

A separate FAMILY, `octagon_tenon` / `octagon_mortise` (below), covers the
BOTH-hosts-(-Z→+Z) case with an octagon-on-post ("stop sign") section: one
`span` knob, a nozzle-pinned roof bridge. See the README's "Octagon joint".

Every working face is 45° ON PURPOSE — see the README for why the shared
ramp face can't be steepened for one part without hurting the other. The
only flat is the dull tip (default 1.6 = 2 bead widths of a 0.8 nozzle): a
tiny bridge in the mortise, deliberately "just big enough to print".
"""

import math

import cadquery as cq

_TIP_W = 1.6      # dull-tip flat: ~2 bead widths of a 0.8 mm nozzle


def _profile(stem_w, head_w, stem_h, tip_w, ramp, base_z, hook_h=None, nozzle=0.8):
    """Closed profile points in the local (y, z) plane, base at z=base_z.
    ENFORCES the nozzle floor: every working segment must be ≥ `nozzle`, or the
    printer can't render it accurately (raises ValueError)."""
    a, b, t = stem_w / 2.0, head_w / 2.0, tip_w / 2.0
    flare, taper = b - a, b - t
    if not (flare > 0 and taper > 0 and tip_w > 0 and stem_h >= 0):
        raise ValueError("need head_w > stem_w, head_w > tip_w > 0, stem_h >= 0")
    segs = {"stem_h (mortise neck + clearance)": stem_h, "tip_w": tip_w,
            "flare (barb per side)": flare}
    if hook_h is not None:
        segs["hook_h"] = hook_h
    else:
        segs["taper"] = taper
    bad = {k: v for k, v in segs.items() if v < nozzle - 1e-9}
    if bad:
        raise ValueError(f"segments below the {nozzle} nozzle floor: {bad} — "
                         "the printer can't render them accurately")
    if hook_h is not None:
        # SQUARE HOOK barb (print-tested fix): every 45° face is PARALLEL to the
        # up-ramp escape diagonal (+y+z), so an all-45 joint cams out that way.
        # A FLAT barb underside + vertical outer wall lock +z (and the diagonal)
        # flat-on-flat. Only for ramp=True: the flat underside is a model-(−z)
        # face = print-VERTICAL on a sideways (+Y-build) tenon; a +Z-printed
        # tenon would see it as a 90° overhang.
        # CANONICAL CLOSURE (user rule): the 45° taper off the hook is NOT free
        # length — it runs exactly until it is back HORIZONTALLY over the
        # profile's start (the stem wall), i.e. rise = the hook-flat width;
        # the dull tip then spans tip_w inward from the stem plane, and the
        # ramp closes to the base. Keeps the apex compact instead of running
        # to an arbitrary centreline.
        if not ramp:
            raise ValueError("hook_h needs ramp=True (see comment)")
        H = stem_h + hook_h + flare
        pts = [(a, base_z), (a, stem_h),           # stem wall (the profile's start)
               (b, stem_h),                        # FLAT hook underside (≥ nozzle wide)
               (b, stem_h + hook_h),               # square barb outer wall
               (a, H),                             # 45° taper — ends over the start
               (a - tip_w, H)]                     # dull tip, inward from the stem plane
    else:
        H = stem_h + flare + taper                 # total height above z=0
        pts = [(a, base_z), (a, stem_h),           # right stem wall
               (b, stem_h + flare),                # right barb (45° flare out)
               (t, H), (-t, H)]                    # 45° taper in, dull tip
    tip_left = pts[-1][0]
    if ramp:
        # ramp-side half = ONE straight 45° line, tip → foot at z=0. Rooted at
        # the host surface, so a side-printed (+Y-build) tenon never starts a
        # layer in mid-air the way a barb's leading edge would.
        pts += [(tip_left - H, 0.0)]
        if base_z < 0:
            pts += [(tip_left - H, base_z)]
    else:
        pts += [(-b, stem_h + flare), (-a, stem_h), (-a, base_z)]
    return pts, H


def arrow_height(stem_w, head_w, stem_h, tip_w=_TIP_W, hook_h=None):
    """Total tenon height above the mating plane (what the mortise host must swallow)."""
    b, t = head_w / 2.0, tip_w / 2.0
    flare = b - stem_w / 2.0
    if hook_h is not None:
        return stem_h + hook_h + flare      # hook: the taper returns over the start
    return stem_h + flare + (b - t)


def arrow_tenon(stem_w, head_w, stem_h, length, tip_w=_TIP_W, ramp=False, root=1.0,
                hook_h=None, nozzle=0.8):
    """Tenon prism along +X, base at z=0, extended `root` below for fusion.
    hook_h: square-hook barb height (flat underside; ramp=True only) — locks the
    up-ramp diagonal an all-45° profile cams out along. Every working segment is
    validated ≥ `nozzle`."""
    pts, _ = _profile(stem_w, head_w, stem_h, tip_w, ramp, -abs(root), hook_h, nozzle)
    return cq.Workplane("YZ").polyline(pts).close().extrude(length)


def arrow_mortise(stem_w, head_w, stem_h, length, tip_w=_TIP_W, ramp=False,
                  clearance=0.3, drop=2.0, hook_h=None, nozzle=0.8):
    """Cavity CUTTER: the tenon profile dilated `clearance` per side (mitred
    offset, so all faces stay 45°/vertical), dropped `drop` below the mating
    plane to open through the host's face. Extrude it out PAST the host's -X
    face so the channel is open on that side (where the tenon enters as the
    host slides -X onto it); the cutter's +X end, left inside the host, is
    the hard stop wall. Boolean-friendly plain prism."""
    if stem_h - clearance < nozzle - 1e-9:
        raise ValueError(f"mortise neck = stem_h - clearance = {stem_h - clearance:.2f} "
                         f"is below the {nozzle} nozzle floor")
    pts, _ = _profile(stem_w, head_w, stem_h, tip_w, ramp, -abs(drop), hook_h, nozzle)
    return (cq.Workplane("YZ").polyline(pts).close()
            .offset2D(clearance, "intersection")
            .extrude(length))


# ─────────────────── OCTAGON ("stop-sign") slide joint ───────────────────────
# A keyed slide joint whose cross-section is an OCTAGON on a POST — a "stop
# sign". BOTH hosts print -Z→+Z (octagon pointing +z), so it's the joint to reach
# for when neither part prints sideways. It exists for all-45°/one-bead
# printability:
#   • the octagon's lower half FLARES OUT at 45° (self-supporting overhang) —
#     this flare is also the retention shoulder the mortise lip captures;
#   • the upper half TUCKS IN (each layer smaller than the one below — always
#     printable);
#   • the only unsupported span, the flat ROOF of the mortise cavity, is pinned
#     to ONE nozzle width so the printer bridges it in a single bead. A sharp
#     peak would print rounded — the flat roof is the smallest peak a nozzle can
#     actually lay.
#
# SIZING — ONE knob (see JOINERY_README "Octagon joint"). `span` = the octagon's
# flat-to-flat width = the room the joint may occupy. Bigger span → longer
# load-bearing segments → stronger, automatically; it floors at the nozzle-
# minimum regular octagon (every side = nozzle). THE ROOF OVERHANG IS NOT A
# PARAMETER: it is pinned to `nozzle` internally and never scales with `span`, so
# no caller can configure a joint whose bridge the printer can't lay. `nozzle` is
# the one physical constant, `length` the slide/engagement depth, `clearance` the
# fit — nothing else to get wrong.

def octagon_span_min(nozzle=0.8):
    """Smallest printable `span`: a regular octagon with every side = nozzle."""
    return nozzle * (1.0 + math.sqrt(2.0))


def _octagon_profile(span, nozzle, base_z):
    """Closed (y, z) points for the stop-sign cross-section: an octagon of
    flat-to-flat width `span` sitting on a post of width L = span/(1+√2), the
    post running from z=base_z up through the z=0 mating plane into the bulb. The
    flat ROOF is pinned to `nozzle` (the bridge cap) no matter how large `span`
    is. Returns (points, roof_z). Enforcing span ≥ the nozzle minimum makes EVERY
    segment ≥ nozzle in one check (side, flare, taper, roof and post all bottom
    out together at the minimum)."""
    if nozzle <= 0:
        raise ValueError("nozzle must be > 0")
    smin = octagon_span_min(nozzle)
    if span < smin - 1e-9:
        raise ValueError(f"span {span:.3f} is below the printable minimum "
                         f"{smin:.3f} mm (a nozzle-side octagon at nozzle={nozzle}) — "
                         "give the joint more room, or use a finer nozzle")
    n = nozzle
    a = span / 2.0                          # half flat-to-flat width
    L = span / (1.0 + math.sqrt(2.0))       # octagon side = post width = neck
    post_h = L                              # neck standoff (scales with the joint)
    z_neck = post_h                         # post top = octagon bottom flat level
    z_wb = z_neck + (a - L / 2.0)           # top of lower 45° flare = bottom of verticals
    z_wt = z_wb + L                         # top of verticals
    z_roof = z_wt + (a - n / 2.0)           # flat roof (upper 45° tapers meet here)
    pts = [
        (L / 2.0,  base_z),                 # post bottom-right (below the mating plane)
        (L / 2.0,  z_neck),                 # post right wall (through z=0) to the bulb
        (a,        z_wb),                   # lower-right 45° flare → waist (retention shoulder)
        (a,        z_wt),                   # right vertical
        (n / 2.0,  z_roof),                 # upper-right 45° taper → roof
        (-n / 2.0, z_roof),                 # ROOF — one nozzle wide (the pinned bridge cap)
        (-a,       z_wt),                   # upper-left taper (mirror)
        (-a,       z_wb),                   # left vertical
        (-L / 2.0, z_neck),                 # lower-left flare
        (-L / 2.0, base_z),                 # post bottom-left
    ]
    return pts, z_roof


def octagon_height(span, nozzle=0.8):
    """Tenon height above the mating plane (what the mortise host must swallow)."""
    _, h = _octagon_profile(span, nozzle, 0.0)
    return h


def octagon_tenon(span, length, nozzle=0.8, root=1.0):
    """Stop-sign tenon: an octagon-on-post prism along +X, base at the z=0 mating
    plane and extended `root` below it for volumetric fusion into its host. Prints
    -Z→+Z (octagon pointing +z). ONE size knob `span` (flat-to-flat width); the
    roof overhang stays one `nozzle` wide at every span."""
    pts, _ = _octagon_profile(span, nozzle, -abs(root))
    return cq.Workplane("YZ").polyline(pts).close().extrude(length)


def octagon_mortise(span, length, nozzle=0.8, clearance=0.1, drop=2.0):
    """Cavity CUTTER matching octagon_tenon: the same profile dilated `clearance`
    per side (mitred → every face stays 45°/vertical) and dropped `drop` below the
    mating plane so it opens through the host's face. Extrude PAST the host's open
    X-face so the tenon slides in; leave the far end inside the host as the stop
    wall. The printed roof bridge is `nozzle + 2·clearance`, so keep `clearance`
    small (0.1 default ≈ one bead)."""
    pts, _ = _octagon_profile(span, nozzle, -abs(drop))
    return (cq.Workplane("YZ").polyline(pts).close()
            .offset2D(clearance, "intersection")
            .extrude(length))


# ── Self-test: geometry gates (run `py -3.12 joinery.py`) ────────────────────
if __name__ == "__main__":
    import sys

    # neck = STEMH - CLR must clear the 0.8 floor (the library enforces it)
    STEM, HEAD, STEMH, TIP, CLR = 4.0, 7.0, 1.1, _TIP_W, 0.3
    fails = []

    def vol(a, b):
        try:
            v = a.intersect(b).val().Volume()
            return v if v > 1e-6 else 0.0
        except Exception:
            return 0.0

    for name, ramp, hook in (("symmetric", False, None), ("ramp", True, None),
                             ("ramp+hook", True, 1.0)):
        # tenon fixed at x 6.3..18.3; cavity open through the host's -x face,
        # stop wall at x = 18.6 (0.3 x-gap at the seat). The HOST moves, like
        # the real mortise part: install slide is -x, uninstall is +x.
        ten = arrow_tenon(STEM, HEAD, STEMH, 12, ramp=ramp, hook_h=hook).translate((6.3, 0, 0))
        host = (cq.Workplane("XY").box(26, 24, 7, centered=(False, True, False))
                .cut(arrow_mortise(STEM, HEAD, STEMH, 22.6, ramp=ramp, clearance=CLR,
                                   hook_h=hook)
                     .translate((-4, 0, 0))))
        n = len(ten.val().Solids())
        if n != 1:
            fails.append(f"{name}: tenon is {n} solids")
        d45 = (CLR + 0.3) / 2 ** 0.5
        checks = [
            ("seated",                   (0, 0, 0),            "=0"),
            ("+x free (uninstall dir)",  (2, 0, 0),            "=0"),
            ("-x stop (install ends)",   (-0.5, 0, 0),         ">0"),
            ("+z lift locked",           (0, 0, CLR + 0.3),    ">0"),
            ("+y locked",                (0, CLR + 0.3, 0),    ">0"),
            ("-y locked",                (0, -(CLR + 0.3), 0), ">0"),
        ]
        if hook is not None:
            # the hook's whole reason: an all-45° profile is PARALLEL to the
            # up-ramp diagonal and cams out along it (print-test finding)
            checks.append(("diag +y+z locked (the hook's job)", (0, d45, d45), ">0"))
        print(f"-- {name} --")
        for label, d, expect in checks:
            v = vol(host.translate(d), ten)
            ok = (v == 0.0) if expect == "=0" else (v > 0.0)
            print(f"  {label:<34} {v:>9.3f} mm3 (must be {expect}){'' if ok else '  <-- FAIL'}")
            if not ok:
                fails.append(f"{name}: {label} = {v:.3f}")
        if name == "ramp":
            # document the degeneracy, don't fail it: plain ramp+45 CANNOT block this
            v = vol(host.translate((0, d45, d45)), ten)
            print(f"  (known degeneracy: diag +y+z {v:>9.3f} mm3 — use hook_h to lock it)")

    # ── octagon ("stop-sign") joint: both hosts print -Z→+Z ──
    print("-- octagon --")
    SPAN, NZ, CLR2 = 4.0, 0.8, 0.1
    Hh = octagon_height(SPAN, NZ)
    oten = octagon_tenon(SPAN, 14, nozzle=NZ)                       # x 0..14
    ohost = (cq.Workplane("XY").box(20, 16, Hh + 6, centered=(False, True, True))
             .translate((0, 0, Hh / 2.0))                          # z -3 .. Hh+3
             .cut(octagon_mortise(SPAN, 22, nozzle=NZ, clearance=CLR2, drop=3)
                  .translate((-1, 0, 0))))                         # through-slot in x
    n_solids = len(oten.val().Solids())
    if n_solids != 1:
        fails.append(f"octagon: tenon is {n_solids} solids")
    g = CLR2 + 0.2
    ochecks = [
        ("seated",              (0, 0, 0),  "=0"),
        ("+x slide free",       (2, 0, 0),  "=0"),
        ("-x slide free",       (-2, 0, 0), "=0"),
        ("+z lift locked",      (0, 0, g),  ">0"),
        ("-z push locked",      (0, 0, -g), ">0"),
        ("+y locked",           (0, g, 0),  ">0"),
        ("-y locked",           (0, -g, 0), ">0"),
    ]
    for label, d, expect in ochecks:
        v = vol(ohost.translate(d), oten)
        ok = (v == 0.0) if expect == "=0" else (v > 0.0)
        print(f"  {label:<20} {v:>9.3f} mm3 (must be {expect}){'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"octagon: {label} = {v:.3f}")
    # the hard cap: the roof is exactly one nozzle wide, and does NOT grow with span
    for s in (SPAN, SPAN * 3.0, octagon_span_min(NZ)):
        pts, _ = _octagon_profile(s, NZ, 0.0)
        zr = max(z for _, z in pts)
        roof = sorted(y for y, z in pts if abs(z - zr) < 1e-6)
        w = roof[-1] - roof[0]
        ok = abs(w - NZ) < 1e-9
        print(f"  roof @ span={s:5.2f}   {w:.3f} mm (must be = nozzle {NZ}){'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"octagon: roof at span {s} = {w:.3f} != {NZ}")
    # the floor: below the nozzle-minimum span must raise
    try:
        octagon_tenon(octagon_span_min(NZ) - 0.2, 10, nozzle=NZ)
        fails.append("octagon: sub-minimum span did not raise")
        print("  span floor            did NOT raise  <-- FAIL")
    except ValueError:
        print(f"  span floor            raises below {octagon_span_min(NZ):.2f} mm (ok)")

    if fails:
        print("FAIL:", *fails, sep="\n  ")
    else:
        print("OK — all variants: seat clear, only the band-guarded +x is free; "
              "hook locks the up-ramp diagonal; octagon locks ±y/±z and pins its "
              "roof at one nozzle.")
    sys.exit(len(fails))
