"""joinery.py — printable mortise-and-tenon SLIDE joints.

FRONT DOOR: `slide_joint`. Describe how each half PRINTS (a PrintSpec: nozzle,
material, facing) and the room it has (width, length); the facings pick the joint
family and the materials pick the fit clearance. See JOINERY_README.md.

    from cadkit.joinery import PrintSpec, slide_joint

    up   = PrintSpec(nozzle=0.8, material="PETG-GF", facing="up")    # prints -Z→+Z
    side = PrintSpec(nozzle=0.8, material="PETG-GF", facing="side")  # prints -Y→+Y

    j   = slide_joint(width=5.6, length=6, tenon=side, mortise=up)   # → arrow ramp+hook
    host = host.union(j.tenon(root=1.0).translate(...))    # tenon fuses into its host
    ring = ring.cut(j.mortise(drop=2.0).translate(...))    # cavity opens through the face
    #   tenon=up, mortise=up → the octagon instead; j.height/j.family/j.width_min exposed

The per-family generators below (`octagon_*`, `arrow_*`, both one-`width`-knob) are
the fine-control layer `slide_joint` dispatches to.

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
BOTH-hosts-(-Z→+Z) case with an octagon-on-fat-stem ("stop sign") section: one
`width` knob (the stem is a computed width/2), the nozzle FLOOR on the tenon and
the one-nozzle bridge CAP on the mortise roof. See the README's "Octagon joint".

A third FAMILY, `dovetail_tenon` / `dovetail_mortise`, exists because print
orientation alone under-determines the joint — the INSTALL AXIS (the direction
deliberately left without retention) matters too. When the install axis is Z
(`slide_joint(..., install="z")`, both hosts -Z→+Z), the profile lies flat in
the plan plane and prints as vertical walls, so the classic sharp dovetail
needs none of the families' print compromises.

Every working face is 45° ON PURPOSE — see the README for why the shared
ramp face can't be steepened for one part without hurting the other. The
only flat is the dull tip: it's pre-shrunk so the MORTISE bridge lands on
exactly one nozzle (a one-bead bridge), same as the octagon roof.
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
    # Nozzle floor is on the TENON's load segments. The dull TIP is EXEMPT — it's
    # the capped bridge (pre-shrunk so the mortise roof lands on one nozzle), a
    # supported last layer on the tenon, not a load face.
    segs = {"stem_h (mortise neck + clearance)": stem_h, "flare (barb per side)": flare}
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


def arrow_width_min(nozzle=0.8):
    """Smallest printable dovetail `width`: at 3·nozzle every segment (stem, barb
    flare, hook) is exactly one nozzle bead."""
    return 3.0 * nozzle


def arrow_dims(width, nozzle=0.8, clearance=0.1):
    """Width-based ramp+hook dovetail dims, sized for MAX STRENGTH at a given width:

        stem_w = flare = hook_h = width/3   (head_w = stem_w + 2·flare = width)

    That split is the analytic optimum. Under a pull-apart load the tenon has two
    failure modes — the NECK shears (capacity ∝ stem_w) and the BARB shears off its
    root (capacity ∝ hook_h) — and with a SQUARE hook (hook_h = flare) and the width
    budget stem_w + 2·flare = width, joint strength = min(stem_w, flare) is maximised
    when stem_w = flare, i.e. width/3. A fatter stem would starve the barb; a bigger
    barb would starve the neck. (σ≈τ assumed for the two modes.) The dull tip is
    PRE-SHRUNK so the MORTISE bridge lands on one nozzle. Floors at 3·nozzle."""
    if width < arrow_width_min(nozzle) - 1e-9:
        raise ValueError(f"width {width:.3f} below the dovetail minimum "
                         f"{arrow_width_min(nozzle):.3f} mm (every segment one bead at "
                         f"nozzle={nozzle}) — give it more room, or a finer nozzle")
    seg = width / 3.0                                      # stem_w = flare = hook_h
    return dict(stem_w=seg, head_w=width,                  # head = stem + 2·flare = 3·seg
                stem_h=seg + clearance,                    # mortise neck = flare = seg
                tip_w=_tenon_roof(nozzle, clearance),      # bridge → one nozzle in the mortise
                hook_h=seg)                                # square hook


def arrow_height(width, nozzle=0.8, clearance=0.1):
    """Tenon height above the mating plane (what the mortise host must swallow)."""
    _, h = _profile(ramp=True, base_z=0.0, nozzle=nozzle,
                    **arrow_dims(width, nozzle, clearance))
    return h


def arrow_tenon(width, length, nozzle=0.8, clearance=0.1, root=1.0):
    """Ramp+hook dovetail TENON — tenon host prints -Y→+Y (sideways), mortise host
    -Z→+Z. One `width` knob; prism along +X, base at z=0, `root` below for fusion.
    Pass the SAME width/nozzle/clearance to the mortise so they mate."""
    pts, _ = _profile(ramp=True, base_z=-abs(root), nozzle=nozzle,
                      **arrow_dims(width, nozzle, clearance))
    return cq.Workplane("YZ").polyline(pts).close().extrude(length)


def arrow_mortise(width, length, nozzle=0.8, clearance=0.1, drop=2.0):
    """Cavity CUTTER matching arrow_tenon: the tenon profile dilated `clearance` per
    side (mitred), dropped `drop` below the mating plane to open through the host
    face. Extrude PAST the host's -X face (open entry); the +X end left inside is
    the stop wall. The mortise neck (= width/4) must clear the nozzle."""
    d = arrow_dims(width, nozzle, clearance)
    if d["stem_h"] - clearance < nozzle - 1e-9:
        raise ValueError(f"width {width:.2f}: mortise neck {d['stem_h'] - clearance:.2f} "
                         f"below the {nozzle} nozzle floor — widen to >= {4 * nozzle:.1f} mm")
    pts, _ = _profile(ramp=True, base_z=-abs(drop), nozzle=nozzle, **d)
    return (cq.Workplane("YZ").polyline(pts).close()
            .offset2D(clearance, "intersection")
            .extrude(length))


# ─────────────────── OCTAGON ("stop-sign") slide joint ───────────────────────
# A keyed slide joint whose cross-section is an OCTAGON on a POST — a "stop sign".
# BOTH hosts print -Z→+Z (octagon pointing +z), so it's the joint to reach for when
# neither part prints sideways. It exists for all-45°/one-bead printability:
#   • the LOWER 45° diagonal FLARES OUT (self-supporting overhang) — this flare is
#     also the retention shoulder the mortise lip captures;
#   • above the waist the UPPER diagonal TUCKS IN (each layer smaller than the one
#     below — always printable);
#   • the only unsupported span, the flat ROOF of the MORTISE cavity, is one nozzle
#     wide so the printer bridges it in a single bead. A sharp peak would print
#     rounded — the flat roof is the smallest peak a nozzle can actually lay.
#
# Two constraints, on OPPOSITE parts (both correct):
#   • the ROOF CAP is on the MORTISE roof — the face the printer bridges. The tenon
#     roof is pre-shrunk so that after the mortise's clearance dilation the bridge
#     lands on exactly one nozzle.
#   • the nozzle MINIMUM (thin-feature floor) is on the TENON — the smaller part
#     (mortise = tenon dilated), so the tenon's segments are what bind. The nominal
#     profile below IS the tenon; `octagon_width_min` is the smallest width whose
#     tenon segments all clear the nozzle.
#
# SIZING — give it ROOM, not force (see JOINERY_README "Octagon joint"). ONE knob:
#   • `width` (flat-to-flat) — the joint size. It sets the UPPER diagonal (the
#     "green" line): wider = bigger, and 45° means taller too.
#   • the STEM is width/2 and the LOWER ("orange") diagonal follows as the shoulder
#     — both computed (see _STEM_FRAC), NOT knobs. `length` is the engagement depth;
#     verticals are locked at one nozzle. The callsite makes no shape decisions.

# The stem is HALF the width — not a knob, a computed optimum. Under a lift load
# the stem carries tension (∝ stem width) while the TWO mortise lips resist in
# shear (∝ shoulder each); setting those equal gives stem = width/2 (shoulder =
# width/4 per side). Wider would starve retention, narrower would starve the neck.
_STEM_FRAC = 0.5


def _tenon_roof(nozzle, clearance):
    """Tenon top-flat width that makes the MORTISE roof (tenon dilated by
    `clearance`, mitred) exactly one nozzle. The dilation widens the horizontal
    roof by 2·clearance·(√2−1), so the tenon roof is pre-shrunk by that — the cap
    lands on the mortise BRIDGE (what the printer spans), not the tenon."""
    t = nozzle - 2.0 * clearance * (math.sqrt(2.0) - 1.0)
    if t <= 1e-6:
        raise ValueError(f"clearance {clearance} is too large for nozzle {nozzle}: "
                         "the tenon roof would vanish before the mortise bridge shrank "
                         "to one nozzle — use a smaller clearance or a coarser nozzle")
    return t


def octagon_width_min(nozzle=0.8, clearance=0.1):
    """Smallest `width` whose TENON segments (stem, upper + lower diagonal) all
    clear the nozzle floor — the tenon is the smaller part, so it binds. (The roof
    is exempt: it's the capped bridge, a supported last layer on the tenon.)"""
    n, sf = nozzle, _STEM_FRAC
    roof_t = _tenon_roof(n, clearance)
    return max(n / sf,                                       # stem = width/2 ≥ n
               n * math.sqrt(2.0) / (1.0 - sf),              # lower (orange) diagonal ≥ n
               roof_t + n * math.sqrt(2.0))                  # upper (green) diagonal ≥ n


def _octagon_profile(width, nozzle, base_z, clearance, height=None):
    """Closed (y, z) points for the TENON cross-section — the smaller part, where the
    nozzle floor is enforced. A stop sign: a `width`-wide waist over a stem of
    `width/2` (see _STEM_FRAC), joined by 45° diagonals — the UPPER (green) set by
    `width`, the LOWER (orange) shorter so the stem stays fat. The roof is
    pre-shrunk so the MORTISE roof (this dilated by clearance) is one nozzle. z=0 is
    the mating plane; the stem runs from base_z up through it. Returns
    (points, roof_z).

    `height` (optional): total profile height above the mating plane — the room
    bound past the mating plane (the octagon's analogue of the dovetail's
    `depth`). The 45° diagonals and one-nozzle roof are printability-locked, so
    ALL extra height over the width-driven minimum goes into the two VERTICALS,
    split evenly: a taller stem POST (deeper mortise-lip engagement = more
    capture shear) and a taller WAIST wall (more flat flank bearing).
    height=None keeps the minimal profile — verticals at the TWO-NOZZLE
    quality tier (user print finding; the ROOF alone stays one nozzle: it is
    the mortise's bridge, intentionally the smallest possible overhang)."""
    if nozzle <= 0:
        raise ValueError("nozzle must be > 0")
    wmin = octagon_width_min(nozzle, clearance)
    if width < wmin - 1e-9:
        raise ValueError(f"width {width:.3f} is below the printable minimum "
                         f"{wmin:.3f} mm (a tenon segment would drop under the {nozzle} "
                         "nozzle) — give the joint more room, or use a finer nozzle")
    n = nozzle
    pv = _bead_pref(n)                     # verticals: two-nozzle quality tier
    roof_t = _tenon_roof(n, clearance)     # tenon roof → mortise roof = one nozzle
    hw = width / 2.0                       # half flat-to-flat (the waist)
    stem = _STEM_FRAC * width              # FAT stem (strength optimum, = width/2)
    orange = hw - stem / 2.0               # lower diagonal run = shoulder overhang / side
    green = hw - roof_t / 2.0              # upper diagonal run (set by width)
    h_min = pv + orange + pv + green       # the width-driven minimal height
    extra = 0.0
    if height is not None:
        if height < h_min - 1e-9:
            raise ValueError(f"height {height:.3f} is below this width's minimum "
                             f"{h_min:.3f} mm (45° diagonals + two-nozzle verticals "
                             "are incompressible) — raise height or shrink width")
        extra = height - h_min
    post_h = pv + extra / 2.0              # stem standoff above the mating plane
    z_neck = post_h
    z_wb = z_neck + orange                 # lower (orange) diagonal → waist bottom
    z_wt = z_wb + pv + extra / 2.0         # vertical (grows with height) → waist top
    z_roof = z_wt + green                  # upper (green) diagonal → roof
    pts = [
        (stem / 2.0,  base_z),             # stem right (below the mating plane)
        (stem / 2.0,  z_neck),             # stem right wall (through z=0) to the bottom flat
        (hw,          z_wb),               # lower-right 45° diagonal → waist (shoulder)
        (hw,          z_wt),               # right vertical (one nozzle tall)
        (roof_t / 2.0, z_roof),            # upper-right 45° diagonal → roof
        (-roof_t / 2.0, z_roof),           # tenon ROOF (dilates to one nozzle in the mortise)
        (-hw,         z_wt),               # upper-left diagonal (mirror)
        (-hw,         z_wb),               # left vertical
        (-stem / 2.0, z_neck),             # lower-left diagonal
        (-stem / 2.0, base_z),             # stem left
    ]
    return pts, z_roof


def octagon_height(width, nozzle=0.8, clearance=0.1, height=None):
    """Tenon height above the mating plane (what the mortise host must swallow).
    With `height` given, echoes it back (after validating the width's minimum)."""
    _, h = _octagon_profile(width, nozzle, 0.0, clearance, height)
    return h


def octagon_tenon(width, length, nozzle=0.8, clearance=0.1, root=1.0,
                  height=None):
    """Stop-sign TENON (the nominal shape, where the nozzle floor is enforced): an
    octagon-on-stem prism along +X, base at the z=0 mating plane and extended `root`
    below for fusion. Prints -Z→+Z. `width` = joint size, the stem is width/2 (a
    computed strength optimum, not a knob), `length` = engagement depth. Pass the
    SAME width/nozzle/clearance to the mortise so they mate."""
    pts, _ = _octagon_profile(width, nozzle, -abs(root), clearance, height)
    return cq.Workplane("YZ").polyline(pts).close().extrude(length)


def _octagon_pocket_profile(width, nozzle, base_z, clearance, height=None):
    """POCKET variant of the cavity profile: the octagon's waist walls continued
    STRAIGHT DOWN to the opening face — the lower diagonals + stem neck (the
    Z-retention) removed, so the tenon can enter along Z. The upper tapers and
    the one-nozzle roof bridge are unchanged (same print story). ±Y stays
    located by the waist walls; ±Z and ±X hold nothing — a pocket is an ENTRY
    feature, always paired with a retained mortise segment the tenon slides
    into."""
    pts, z_roof = _octagon_profile(width, nozzle, base_z, clearance, height)
    hw = width / 2.0
    # pts: [stemR base, stemR neck, waistR bot, waistR top, roofR, roofL,
    #       waistL top, waistL bot, stemL neck, stemL base] — keep waist-top →
    # roof → waist-top, drop the sides straight to base_z.
    keep = pts[3:7]
    return [(hw, base_z)] + keep + [(-hw, base_z)], z_roof


def octagon_mortise(width, length, nozzle=0.8, clearance=0.1, drop=2.0,
                    pocket=False, height=None):
    """Cavity CUTTER — the tenon profile DILATED `clearance` per side (mitred → faces
    stay 45°/vertical) and dropped `drop` below the mating plane so it opens through
    the host's face. Extrude PAST the host's open X-face so the tenon slides in; the
    far end left inside is the stop wall. The printed roof BRIDGE is exactly one
    nozzle (the tenon roof was pre-shrunk for this).

    `pocket=True` cuts the ENTRY-POCKET variant instead: the Z-retention (neck
    lips) is removed so the tenon can enter straight along Z — used when the
    slide travel is obstructed and the parts must first mate along Z at an
    offset position, then slide along X into the adjacent retained mortise.
    A pocket retains nothing by itself; always pair it with a mortise segment."""
    prof = _octagon_pocket_profile if pocket else _octagon_profile
    pts, _ = prof(width, nozzle, -abs(drop), clearance, height)
    return (cq.Workplane("YZ").polyline(pts).close()
            .offset2D(abs(clearance), "intersection")
            .extrude(length))


# ─────────────────── OCTAGON ARC (rotational install) variant ─────────────────
# For parts that are BOTH already located on a shared axis (e.g. an axle
# through both centres), no straight slide direction exists — the one free
# motion is ROTATION about that axis. The install path is then an ARC: offset
# the moving part by some angle, mate along Z through the open gaps, and
# rotate to seat against an ANGULAR stop. Geometry = the straight octagon
# profile placed at `radius` from the Z axis and REVOLVED about it; the sweep
# is horizontal, so the print rules are identical (both hosts -Z→+Z, roof
# bridge one nozzle). Angular clearances convert as arc length ≈ radius·angle.


def _arc_wire(pts, radius, clearance=0.0):
    """Closed profile wire in the XZ plane at `radius` (profile y → radial
    offset), optionally dilated — ready to revolve about global Z."""
    wp = (cq.Workplane("XZ")
          .polyline([(radius + y, z) for (y, z) in pts]).close())
    if clearance:
        wp = wp.offset2D(abs(clearance), "intersection")
    return wp


def octagon_tenon_arc(width, radius, sweep_deg, nozzle=0.8, clearance=0.1,
                      root=1.0, height=None):
    """ROTATIONAL-install octagon TENON: the octagon section revolved
    `sweep_deg` about the Z axis at `radius`. Sweeps from plan angle 0 toward
    +Y (rotate about Z to place); mating plane z=0, `root` sunk below for
    volumetric fusion."""
    pts, _ = _octagon_profile(width, nozzle, -abs(root), clearance, height)
    return _arc_wire(pts, radius).revolve(sweep_deg, (0, 0), (0, 1))


def octagon_mortise_arc(width, radius, sweep_deg, nozzle=0.8, clearance=0.1,
                        drop=2.0, height=None):
    """Cavity CUTTER matching octagon_tenon_arc — dilated `clearance` per side
    (mitred in the radial plane), dropped `drop` below the mating plane, swept
    over the LONGER arc (engagement + angular entry overshoot + seat). Sweep
    past the host's open face on the entry side; the far angular end left
    inside the host is the stop."""
    pts, _ = _octagon_profile(width, nozzle, -abs(drop), clearance, height)
    return _arc_wire(pts, radius, clearance).revolve(sweep_deg, (0, 0), (0, 1))


# ──────────── T-SLOT (install ∥ print-Z) slide joint — was the dovetail ──────
# Third family, unlocked by the INSTALL AXIS rather than a print trick: print
# orientation alone under-determines a slide joint — the INSTALL direction (the
# one axis deliberately left without retention) matters just as much. When that
# axis is Z, the same axis both hosts print in, the profile lies flat in the
# X-Y plane and every working face is a printed VERTICAL WALL.
#
# The profile is a SQUARE-SHOULDERED T: neck through the mating plane, short
# lips, then a parallel-sided head bar. It REPLACED the classic angled
# dovetail (print finding at a 0.8 nozzle, retractable-cable-spool): the
# dovetail concentrates its engagement in sharp plan corners, and the nozzle
# radius rounds the tenon's acute corners DOWN while rounding the mortise's
# inner corners UP — the corners collide before the faces seat and most of
# the wedge detail is gone. Square 90° corners round compatibly on both
# halves; retention becomes flat shoulder bearing, which also removes the
# dovetail's lateral cam component (pull-out no longer levers the mortise
# lips apart). The one dovetail virtue lost — wedge take-up of clearance —
# was never used: these are SLIDE joints running print-tested clearances.
# (Function names keep "dovetail_" — they are the install-z family entry
# points; only the profile changed.)
# Convention: profile in the local (x, y) PLAN plane — width across Y (like the
# other families), the head toward +X (rotate about Z to aim it), mating
# plane at x=0 — and the prism extrudes along +Z, the INSTALL axis. The joint
# constrains ±X (neck lips / head end wall) and ±Y (neck + head side walls)
# by shape; ±Z is free by design. The caller closes ONE Z-end with a hard
# stop (un-cut host material past the cavity's far end) and guards the other
# with a preload or the next part in the stack.

# The joint is sized by the ROOM it MAY occupy — the caller passes the mortise's
# AVAILABLE space, not the joint's dimensions:
#   length — available height (the Z engagement, the prism height — used fully:
#            taller is always stronger)
#   depth  — available depth into the host, past the mating plane
#   width  — available width across the host's face
# The profile is then MAX-MIN OPTIMIZED, not inscribed: pull-out capacity is
# the WEAKEST of four links, per unit engagement, same material, shear ≈
# 0.6·tensile, bearing ≈ 1.5·tensile — note the T has TWO stacked shear
# elements SHARING the depth (the angled dovetail's single flank was both):
#   neck tension       ∝ 1.0 · neck
#   mortise LIP shear  ∝ 2 · 0.6 · lip   (face → head channel, mortise side)
#   tenon BAR shear    ∝ 2 · 0.6 · bar   (the head bar off the stem)
#   shoulder bearing   ∝ 2 · 1.5 · o     → parity at o = neck/3
# Strongest joint in the given box (user's rule), with TWO-TIER wall sizing
# (user print finding): every tenon segment TARGETS 2·nozzle — two clean
# perimeters slice crisply where a single bead prints mushy — and degrades
# toward the ONE-NOZZLE hard floor only when the room is too tight:
#   neck = 0.6·min(width, depth)  — shear parity across both stacked
#          elements; floored at 2·nozzle, capped at width − 2·nozzle
#   o    = min((width − neck)/2, max(neck/3, 2·nozzle))
#   bar  = max(min(2·nozzle, (depth−clr)/2), min(neck/1.2, (depth−clr)/2))
#   lip  = bar + clearance;  depth_used = lip + bar
#   (surplus room beyond parity stays host material)
# The MORTISE is the dilated copy — larger everywhere EXCEPT its lip (the
# one concave feature: dilation THINS it by `clearance`) — so the tenon
# lip is pre-grown and the printed mortise lip = the tenon bar, keeping
# both halves' walls at tier. See dovetail_box_min() for the smallest
# boxes that guarantee the hard (nozzle) and quality (2·nozzle) tiers.

_DT_SHEAR_RATIO = 1.2    # lip-shear parity: neck = 1.2·depth_used (τ ≈ 0.6·σ, 2 planes)
_DT_BEAR_FRAC   = 3.0    # bearing parity: shoulder overhang o = neck/3 (σ_c ≈ 1.5·σ, 2 sides)


def _bead(nozzle):
    """The HARD FLOOR for a printed wall: exactly ONE NOZZLE. (An earlier
    +0.05 buffer guarded against classic wall generators dropping
    exactly-nozzle lines; the projects slice with ARACHNE now, which
    handles them — buffer removed, user's call 2026-07-22.)"""
    return nozzle


def _bead_pref(nozzle):
    """The QUALITY TARGET for a printed wall: TWO nozzles (user print
    finding — two clean perimeters slice crisply where a single bead prints
    mushy). Segments aim here and degrade toward _bead only in tight
    rooms."""
    return 2.0 * nozzle


def dovetail_width_min(nozzle=0.8):
    """Smallest available `width` that fits a printable joint: a 2-nozzle
    neck + one nozzle of shoulder per side."""
    return 2.0 * nozzle + 2.0 * _bead(nozzle)


def dovetail_dims(width, depth, nozzle=0.8, clearance=0.1,
                  back_clearance=None):
    """MAX-MIN the plan profile inside the available room (`width` across the
    face, `depth` into the host): returns (neck_w, head_w, depth_used) per
    the model above. The TENON LIP carries +`back_clearance` over the tenon
    BAR, because the cavity's lip face lands that far behind it (the lip is
    the one CONCAVE feature — "the mortise is always larger" is false
    there, user-caught at 1.45): mortise lip = tenon bar, and the two shear
    elements balance by construction. `back_clearance` (default =
    `clearance`) is the DEPTH-FACE gap — BOTH the lip↔head-back pair and
    the head-front↔cavity-back pair run at it (fiber-filled filaments bind
    on the depth sandwich; see joint_clearances) — and the depth allocation
    runs on it so every wall keeps its tier size. Unused room stays host
    material. Raises when the room can't fit a printable joint."""
    b = _bead(nozzle)
    c = abs(clearance)
    bc = c if back_clearance is None else abs(back_clearance)
    wmin = dovetail_width_min(nozzle)
    if width < wmin - 1e-9:
        raise ValueError(f"width {width:.3f} is below the printable minimum "
                         f"{wmin:.3f} mm (a 2-nozzle neck + a nozzle of "
                         "shoulder per side) — give the joint more room, or use "
                         "a finer nozzle")
    if depth < 2.0 * b + bc - 1e-9:
        raise ValueError(f"depth {depth:.3f} is too shallow for the T profile: "
                         f"no room for a one-bead MORTISE lip + a one-bead head "
                         f"bar + the lip's depth-face clearance "
                         f"(2 × {b:.2f} + {bc:.2f}) — deepen the mortise")
    shear_room = (depth - bc) / 2.0             # per shear element
    neck = min(0.6 * width, _DT_SHEAR_RATIO * shear_room)
    neck = min(max(neck, 2.0 * nozzle), width - 2.0 * b)
    # prefer QUALITY-TIER shoulders over surplus neck (the neck's own floor
    # still wins on a truly tight width) — this is what makes the quality
    # bounding box (dovetail_box_min(quality=True)) actually deliver ≥
    # 2·nozzle EVERYWHERE on both halves
    neck = max(min(neck, width - 2.0 * _bead_pref(nozzle)), 2.0 * nozzle)
    o = min((width - neck) / 2.0,
            max(neck / _DT_BEAR_FRAC, _bead_pref(nozzle)))
    head = neck + 2.0 * o
    bar = max(min(_bead_pref(nozzle), shear_room),
              min(neck / _DT_SHEAR_RATIO, shear_room))
    depth_used = 2.0 * bar + bc                 # tenon lip = bar + back_clearance
    return neck, head, depth_used


def dovetail_box_min(nozzle=0.8, clearance=0.1, quality=False,
                     back_clearance=None):
    """The smallest (width, depth) BOUNDING BOX whose joint has NO geometry —
    on the TENON or the MORTISE — under the tier size: nozzle (hard floor,
    quality=False) or 2·nozzle (quality floor, quality=True). Overhang/
    bridge features are excluded from the rule everywhere in the library —
    they are intentionally one nozzle. Width: neck (≥ 2·nozzle either tier)
    + a shoulder per side; depth: head bar + MORTISE lip (each at tier) +
    the lip's DEPTH-FACE clearance (the tenon lip pre-grows by
    `back_clearance`, default = `clearance`, so the cavity's lip stays at
    tier)."""
    seg = _bead_pref(nozzle) if quality else _bead(nozzle)
    bc = abs(clearance) if back_clearance is None else abs(back_clearance)
    return (2.0 * nozzle + 2.0 * seg, 2.0 * seg + bc)


def dovetail_height(width, depth, nozzle=0.8, clearance=0.1,
                    back_clearance=None):
    """Protrusion past the mating plane (what the mortise host must actually
    swallow — depth_used, NOT the full available depth), clearance included.
    `back_clearance` (≥ clearance; see joint_clearances) is the depth-face
    gap: it sizes the profile's depth allocation AND the cavity's extra
    back-wall depth — fiber-filled depth-face relief."""
    bc = abs(clearance) if back_clearance is None else abs(back_clearance)
    return dovetail_dims(width, depth, nozzle, clearance, bc)[2] + bc


def _dovetail_profile(width, depth, nozzle, back, clearance,
                      back_clearance=None):
    """Closed (x, y) plan-view points for the TENON: the SQUARE-SHOULDERED T
    — optimized neck through the mating plane (x=0), the LIP step (= bar +
    back_clearance, so the mortise's lip face lands a full depth-face gap
    behind it at the bar's size), then the parallel-sided head bar out to
    depth_used. Every corner is 90°: the nozzle rounds tenon and mortise
    corners COMPATIBLY (the angled dovetail's acute corners rounded into
    interference). `back` = extension behind the plane (tenon root /
    mortise opening drop)."""
    bc = abs(clearance) if back_clearance is None else abs(back_clearance)
    neck_w, head_w, d_used = dovetail_dims(width, depth, nozzle, clearance, bc)
    lip = (d_used + bc) / 2.0                    # = bar + back_clearance
    neck, head = neck_w / 2.0, head_w / 2.0
    return [(-back, -neck), (lip, -neck), (lip, -head), (d_used, -head),
            (d_used, head), (lip, head), (lip, neck), (-back, neck)]


def dovetail_tenon(width, depth, length, nozzle=0.8, clearance=0.1, root=1.0,
                   back_clearance=None):
    """Install-z TENON (square-shouldered T; the name predates the profile
    swap): a plan-view T prism along +Z (the INSTALL axis), mating plane at
    x=0, head toward +X, extended `root` behind the plane for volumetric
    fusion into its host. Both hosts print -Z→+Z; every face is a vertical
    wall and every corner 90°. (`clearance`/`back_clearance` dilate the
    mortise side, but they also SIZE the tenon's lip and depth — pass the
    same values to both halves, as slide_joint does.)"""
    pts = _dovetail_profile(width, depth, nozzle, abs(root), clearance,
                            back_clearance)
    return cq.Workplane("XY").polyline(pts).close().extrude(length)


def dovetail_mortise(width, depth, length, nozzle=0.8, clearance=0.1, drop=2.0,
                     back_clearance=None):
    """Cavity CUTTER — the tenon plan profile DILATED `clearance` per side
    (mitred → the square corners stay square) and extended `drop` behind the
    mating plane so it opens through the host's face. The dilation THINS the
    cavity's lip by `clearance`; the tenon's lip is pre-grown by the same
    amount, so the printed mortise lip is a full bar-sized wall.
    `back_clearance` (≥ clearance) opens the DEPTH-FACE gaps to its value on
    BOTH pairs — the cavity's back wall moves deeper AND its lip face drops
    further behind the tenon's (pre-grown) lip — the relief fiber-filled
    filaments need to slide (see joint_clearances). The LATERAL faces keep
    `clearance`, and because the tenon's lip and depth box are sized on
    `back_clearance` too, every printed wall on both halves keeps its tier
    size. Extrude PAST the host's open Z-end (pass a longer `length` /
    translate) so the tenon can enter; the far end left inside the host is
    the hard stop."""
    c = abs(clearance)
    bc = c if back_clearance is None else abs(back_clearance)
    e = bc - c                                    # extra beyond the dilation
    pts = _dovetail_profile(width, depth, nozzle, abs(drop), clearance, bc)
    if e > 1e-12:
        d_used = dovetail_dims(width, depth, nozzle, clearance, bc)[2]
        lip = (d_used + bc) / 2.0
        # back wall out by e (dilation adds the remaining c → bc total);
        # lip step back by e (dilation thins a further c → the cavity lip
        # face lands bc behind the tenon's, still a full bar-sized wall)
        pts = [(x + e if abs(x - d_used) < 1e-9 else
                (x - e if abs(x - lip) < 1e-9 else x), y)
               for x, y in pts]
    return (cq.Workplane("XY").polyline(pts).close()
            .offset2D(c, "intersection")
            .extrude(length))


# ─────────── HOOK (single-flank dovetail) — install ∥ print-Z, EDGE-BOUNDED ──
# The dovetail above assumes its `width` room sits INSIDE a larger host face:
# solid material continues past both flanks, so only the profile itself has
# to fit the room. Some sites are EDGE-BOUNDED instead — the mating face's
# FULL extent between two free edges IS the room (first case: a brake-lever
# arm 4.15 mm tall carrying a TPU friction pad). There the symmetric profile
# dies long before its width floor: after reserving one printable wall per
# free edge, two flanks + a 2-bead neck no longer fit (at a 0.8 nozzle the
# symmetric dovetail needs ≥ ~5 mm edge-to-edge; anything less slices into
# sub-bead shoulders whose retention lips end up attached to nothing).
#
# The HOOK spends the scarce width on ONE flank: a fat stem (it takes every
# spare bead — the tension link), a single one-nozzle hook toward +Y, and a
# one-nozzle LIP on the mortise side filling the notch behind the hook.
#
#      ____________
#      |  ____________|      plan view: stem on the -Y side, hook at +Y;
#      |  |     _____       the mortise adds a one-nozzle lip (dashed)
#      |  |    |  ____|      into the notch — pulling the tenon -X hooks
#      |__|    |_|           the notch on the lip. Cavity floor + roof
#                            (closed, unlike the dovetail's open ±Y) lock ±Y.
#
# `width` = the FULL edge-to-edge extent INCLUDING the walls the joint must
# leave standing — the profile budgets them itself (exactly one nozzle per
# edge survives the mortise dilation). Retention: ±X (lip / face bearing),
# ±Y (cavity floor + roof); ±Z is the free install axis — the caller closes
# one end with a stop, and siting the stop DOWN-LOAD of the working force
# (e.g. brake drag) makes the joint self-tightening. Print story identical
# to the dovetail: install ∥ print-Z, every wall vertical, any rotation
# about the install axis allowed.


def hook_width_min(nozzle=0.8, clearance=0.1):
    """Smallest edge-to-edge `width` that fits the hook: a nozzle of wall per
    free edge (post-dilation), a nozzle of stem, a nozzle of hook."""
    return 4.0 * nozzle + 2.0 * clearance


def hook_dims(width, nozzle=0.8, clearance=0.1):
    """(stem_h, notch_depth, full_depth) of the hook profile inside the
    edge-to-edge `width`. The hook, lip and edge walls are bead-fixed; ALL
    surplus width goes into the STEM — the tension link. Raises when the
    width can't fit a printable joint."""
    wmin = hook_width_min(nozzle, clearance)
    if width < wmin - 1e-9:
        raise ValueError(f"width {width:.3f} is below the printable minimum "
                         f"{wmin:.3f} mm for the hook (a nozzle each of edge "
                         "wall x2, stem, and hook) — the site is too short "
                         "even for the single-flank profile")
    stem_h = width - 3.0 * nozzle - 2.0 * clearance
    return stem_h, nozzle + clearance, 2.0 * nozzle + clearance


def hook_depth(nozzle=0.8, clearance=0.1):
    """Protrusion past the mating plane (what the mortise host must swallow):
    the bead-fixed full depth + clearance."""
    return 2.0 * nozzle + 2.0 * clearance


def _hook_profile(width, nozzle, clearance, back):
    """Closed (x, y) plan points for the TENON: stem from the -Y side, hook
    flare toward +Y, `back` extension behind the mating plane (tenon root /
    mortise opening drop). y=0 is the FACE CENTRE — the free edges sit at
    ±width/2. The mortise (this dilated `clearance`) lands exactly one
    nozzle inside each edge."""
    stem_h, d1, d2 = hook_dims(width, nozzle, clearance)
    y0 = -width / 2.0 + nozzle + clearance       # stem bottom
    y1 = y0 + stem_h                             # stem top = the lip's seat
    y2 = y1 + nozzle                             # hook top
    return [(-back, y0), (d2, y0), (d2, y2), (d1, y2), (d1, y1), (-back, y1)]


def hook_tenon(width, length, nozzle=0.8, clearance=0.1, root=1.0):
    """Single-flank hook TENON: a plan-view prism along +Z (the INSTALL
    axis), mating plane at x=0, hook toward +Y, extended `root` behind the
    plane for volumetric fusion. `width` = the host face's FULL edge-to-edge
    extent (see the section note). Both hosts print along the install axis;
    every face is a vertical wall."""
    pts = _hook_profile(width, nozzle, clearance, abs(root))
    return cq.Workplane("XY").polyline(pts).close().extrude(length)


def hook_mortise(width, length, nozzle=0.8, clearance=0.1, drop=2.0):
    """Cavity CUTTER — the hook tenon profile DILATED `clearance` per side
    (mitred; the notch edges dilate INWARD, thinning the lip to exactly one
    nozzle) and extended `drop` behind the mating plane. Extrude PAST the
    host's open Z-end; the far end left inside is the hard stop."""
    pts = _hook_profile(width, nozzle, clearance, abs(drop))
    return (cq.Workplane("XY").polyline(pts).close()
            .offset2D(abs(clearance), "intersection")
            .extrude(length))


# ─────────────────── Unified print-aware entry point ─────────────────────────
# One entrypoint for all joint families. The consumer describes how each half
# PRINTS (a PrintSpec: nozzle, material, facing), the room it has (width,
# length), and the INSTALL axis — the one direction deliberately left without
# retention; the facings + install axis pick the shape and the materials pick
# the clearance:
#   install='x' (slide ⊥ print-Z, the default):
#     • tenon 'up',   mortise 'up'   → octagon (both parts print -Z→+Z)
#     • tenon 'side', mortise 'up'   → ramp+hook dovetail (tenon prints -Y→+Y)
#   install='z' (slide ∥ print-Z — profile prints as vertical walls):
#     • tenon 'up',   mortise 'up'   → plain dovetail
# Other combinations aren't modelled yet and raise.

# Fit clearance per side, print-VALIDATED (~0.8 nozzle, long-engagement slide
# joints). Clearance is print-TESTED, not formulaic (it also creeps up with
# engagement length), so this holds only measured materials; anything else falls
# back to the default and should be print-checked (or passed explicitly via
# `clearance=`).
#
# FIBER-FILLED filaments (GF/CF — detected from the material name) get DOUBLE
# clearance on the install-z T's DEPTH faces — BOTH pairs: head-front ↔
# cavity-back AND lip ↔ head-back (the retention faces): the stiff,
# rough-surfaced walls bind in the depth sandwich long before the lateral
# faces do — print finding, retractable-cable-spool wall joint in PETG-GF:
# lateral 0.15 slid fine, the depth faces needed 0.3. The LATERAL faces keep
# the table value, and the T's depth allocation runs on the depth gap (tenon
# lip pre-grows by it), so every printed wall on both halves keeps its tier
# size — the depth BOX grows instead. Other families use the base value
# (their fiber behavior is unmeasured — print-check before extending the rule).
#
# `fit` picks the tier: "normal" (default) = the print-tested slide fit;
# "loose" = 2× BOTH values, for joints that must slide with zero effort
# (glued assemblies, frequently-serviced parts) — retention geometry is
# unchanged, only the gaps grow.
_MATERIAL_CLEARANCE = {
    "PETG-GF": 0.15,
}
_DEFAULT_CLEARANCE = 0.15
_FIT_FACTORS = {"normal": 1.0, "loose": 2.0}


def _is_fiber_filled(material):
    """GF/CF token anywhere in the material name (e.g. 'PETG-GF', 'PA-CF')."""
    if not material:
        return False
    m = material.upper()
    return "GF" in m or "CF" in m


def joint_clearances(tenon, mortise, fit="normal", override=None):
    """The library's clearance POLICY — (clearance, back_clearance) for a
    joint between two PrintSpecs. `clearance` dilates the mortise laterally
    (every family); `back_clearance` is the install-z T's DEPTH-face gap
    (both the cavity-back and lip pairs) — 2× the base when either half is
    fiber-filled (see the table note). `fit="loose"` doubles both.
    `override` replaces the material-table base (the fiber and fit factors
    still apply)."""
    if fit not in _FIT_FACTORS:
        raise ValueError("fit must be one of %s, got %r"
                         % (sorted(_FIT_FACTORS), fit))
    c = _clearance_for(tenon, mortise, override)
    bc = 2.0 * c if any(_is_fiber_filled(s.material)
                        for s in (tenon, mortise)) else c
    k = _FIT_FACTORS[fit]
    return c * k, bc * k


class PrintSpec:
    """How one half of a joint prints: `nozzle` (mm), `material` (a key into the
    clearance table, or None), and `facing` — 'up' (the part prints -Z→+Z) or
    'side' (prints -Y→+Y, on its side)."""
    __slots__ = ("nozzle", "material", "facing")

    def __init__(self, nozzle=0.8, material=None, facing="up"):
        if facing not in ("up", "side"):
            raise ValueError("facing must be 'up' or 'side', got %r" % (facing,))
        if nozzle <= 0:
            raise ValueError("nozzle must be > 0")
        self.nozzle, self.material, self.facing = nozzle, material, facing


def _clearance_for(tenon, mortise, override):
    if override is not None:
        return override
    found = [_MATERIAL_CLEARANCE[s.material] for s in (tenon, mortise)
             if s.material in _MATERIAL_CLEARANCE]
    return max(found) if found else _DEFAULT_CLEARANCE


# x-slide families share a signature; the dovetail (extra `depth` bound) is
# dispatched explicitly in _SlideJoint.
_FAMILY_FUNCS = {
    "octagon":  (octagon_tenon,  octagon_mortise,  octagon_height,  octagon_width_min),
    "arrow":    (arrow_tenon,    arrow_mortise,    arrow_height,    arrow_width_min),
}


class _SlideJoint:
    """Result of `slide_joint`: call `.tenon(root=…)` / `.mortise(drop=…)` for the two
    solids. Attributes: `.family` ('octagon'|'arrow'|'dovetail'|'hook'), `.install` ('x'|'z'),
    `.height` (how deep the mortise host must actually be), `.width_min` (the
    printable floor), `.clearance`, `.nozzle` (the coarser of the two halves),
    and `.depth` (dovetail only: the AVAILABLE depth bound)."""
    def __init__(self, width, length, tenon, mortise, clearance, install, depth,
                 bounded=False, back_clearance=None):
        self.back_clearance = (clearance if back_clearance is None
                               else back_clearance)
        if install not in ("x", "z"):
            raise ValueError("install must be 'x' or 'z', got %r" % (install,))
        if bounded and install != "z":
            raise ValueError("bounded=True is modelled for install='z' only "
                             "(the x-slide families assume host material past "
                             "the profile — add the variant if a site needs it)")
        self.width, self.length, self.clearance = width, length, clearance
        self.install = install
        self.nozzle = max(tenon.nozzle, mortise.nozzle)   # coarser drives the min feature
        kind = (tenon.facing, mortise.facing)
        if install == "z":
            # Slide axis ∥ print-Z: the profile lies in the plan plane, so its
            # faces are vertical printed walls — but ONLY for hosts printing
            # -Z→+Z. A side-printed host would see the profile's -Y-normal
            # faces as full 90° overhangs.
            if kind != ("up", "up"):
                raise NotImplementedError(
                    "install='z' needs BOTH hosts printing -Z→+Z (facing 'up'); "
                    "got tenon '%s' + mortise '%s' — a side-printed host would "
                    "overhang the plan profile" % kind)
            if bounded:
                # EDGE-BOUNDED site: `width` = the face's FULL extent between
                # free edges, walls included — the GEOMETRY ADAPTS to the
                # room: symmetric dovetail while it still fits inside the
                # reserved edge walls, single-flank HOOK when it doesn't.
                usable = width - 2.0 * (self.nozzle + self.clearance)
                if usable >= dovetail_width_min(self.nozzle) - 1e-9:
                    self.family = "dovetail"
                    self.width = usable          # profile stays edge-walled
                    self.depth = usable / 2.0 if depth is None else depth
                    self.height = dovetail_height(usable, self.depth,
                                                  self.nozzle, self.clearance,
                                                  self.back_clearance)
                    self.width_min = dovetail_width_min(self.nozzle)
                    return
                if depth is not None:
                    raise ValueError("the hook's depth is bead-fixed — drop "
                                     "the `depth` bound for this site")
                self.family = "hook"
                hook_dims(width, self.nozzle, self.clearance)   # width floor
                self.height = hook_depth(self.nozzle, self.clearance)
                self.width_min = hook_width_min(self.nozzle, self.clearance)
                return
            self.family = "dovetail"
            # `depth` = AVAILABLE room past the mating plane; the optimizer may
            # use less (strength parity). Default: half the available width.
            self.depth = width / 2.0 if depth is None else depth
            self.height = dovetail_height(width, self.depth, self.nozzle,
                                          self.clearance, self.back_clearance)
            self.width_min = dovetail_width_min(self.nozzle)
            return
        if kind == ("up", "up"):
            self.family = "octagon"
        elif kind == ("side", "up"):
            self.family = "arrow"
        else:
            raise NotImplementedError(
                "no joint for tenon '%s' + mortise '%s' yet (have up+up, side+up) — "
                "add the variant the way threads.py grew" % kind)
        if depth is not None and self.family != "octagon":
            raise ValueError("depth on install='x' applies only to the octagon "
                             "(its profile HEIGHT past the mating plane); the "
                             "arrow's height is width-locked")
        self.depth = depth
        if self.family == "octagon":
            # depth = room past the mating plane; extra over the width-driven
            # minimum grows the profile's two verticals evenly (max strength
            # in the given bounds) — see _octagon_profile
            self.height = octagon_height(self.width, self.nozzle,
                                         self.clearance, depth)
            self.width_min = octagon_width_min(self.nozzle)
            return
        _, _, f_height, f_wmin = _FAMILY_FUNCS[self.family]
        self.height = f_height(self.width, self.nozzle, self.clearance)
        self.width_min = f_wmin(self.nozzle)

    def tenon(self, root=1.0):
        if self.family == "hook":
            return hook_tenon(self.width, self.length, self.nozzle,
                              self.clearance, root)
        if self.family == "dovetail":
            return dovetail_tenon(self.width, self.depth, self.length,
                                  self.nozzle, self.clearance, root,
                                  self.back_clearance)
        if self.family == "octagon":
            return octagon_tenon(self.width, self.length, self.nozzle,
                                 self.clearance, root, height=self.depth)
        return _FAMILY_FUNCS[self.family][0](
            self.width, self.length, self.nozzle, self.clearance, root)

    def mortise(self, drop=2.0, pocket=False):
        if pocket:
            if self.family != "octagon":
                raise NotImplementedError(
                    "pocket mortises are modelled for the octagon family only "
                    "(the dovetail's install axis IS z — no pocket needed; the "
                    "arrow's would need its own profile)")
            return octagon_mortise(self.width, self.length, self.nozzle,
                                   self.clearance, drop, pocket=True,
                                   height=self.depth)
        if self.family == "hook":
            return hook_mortise(self.width, self.length, self.nozzle,
                                self.clearance, drop)
        if self.family == "dovetail":
            return dovetail_mortise(self.width, self.depth, self.length,
                                    self.nozzle, self.clearance, drop,
                                    self.back_clearance)
        if self.family == "octagon":
            return octagon_mortise(self.width, self.length, self.nozzle,
                                   self.clearance, drop, height=self.depth)
        return _FAMILY_FUNCS[self.family][1](
            self.width, self.length, self.nozzle, self.clearance, drop)


def slide_joint(width, length, tenon, mortise, clearance=None, install="x",
                depth=None, bounded=False, fit="normal"):
    """Build a printable slide joint sized to the AVAILABLE room (`width`,
    `length`, and `depth` — the room past the mating plane: install='z' sizes
    the dovetail with it, install='x' octagons grow their VERTICALS into it
    for max strength; the octagon may not use less than given), the way
    each half prints (`tenon`, `mortise`: PrintSpec), and the INSTALL axis — the
    one direction deliberately left without retention. `install='x'` (default)
    slides ⊥ print-Z (facings pick octagon or arrow); `install='z'` slides ∥
    print-Z (both hosts must print 'up'; a plain dovetail whose plan profile is
    OPTIMIZED for strength inside the room — it may use less than the room where
    more adds nothing). `bounded=True` (install='z' only) declares an
    EDGE-BOUNDED site: `width` is the mating face's FULL extent between free
    edges, walls included — the geometry then ADAPTS to the room: the
    symmetric dovetail while it fits inside the reserved edge walls, the
    single-flank HOOK when the face is too short for it. The MATERIALS pick
    the clearances (see joint_clearances — fiber-filled halves get a doubled
    depth-face gap on the install-z T; override the base with `clearance=`),
    and `fit` picks the tier: "normal" (default) or "loose" (2× everything —
    for joints that must slide with zero effort, e.g. glued assemblies).
    Returns a _SlideJoint with `.tenon(root)` / `.mortise(drop)`."""
    c, bc = joint_clearances(tenon, mortise, fit, clearance)
    return _SlideJoint(width, length, tenon, mortise, c, install, depth,
                       bounded, back_clearance=bc)


# ── Self-test: geometry gates (run `py -3.12 joinery.py`) ────────────────────
if __name__ == "__main__":
    import sys

    CLR = 0.1
    fails = []

    def vol(a, b):
        try:
            v = a.intersect(b).val().Volume()
            return v if v > 1e-6 else 0.0
        except Exception:
            return 0.0

    # ── ramp+hook dovetail (width-based): tenon prints -Y→+Y, mortise -Z→+Z ──
    print("-- arrow (ramp+hook) --")
    AW = 5.6                                      # width; barb/neck = 1.6/3.2 at nozzle 0.8
    ten = arrow_tenon(AW, 12, clearance=CLR).translate((6.3, 0, 0))    # x 6.3..18.3
    host = (cq.Workplane("XY").box(26, 24, 8, centered=(False, True, False))
            .cut(arrow_mortise(AW, 22.6, clearance=CLR).translate((-4, 0, 0))))  # stop at +x
    n = len(ten.val().Solids())
    if n != 1:
        fails.append(f"arrow: tenon is {n} solids")
    g = CLR + 0.3
    d45 = g / 2 ** 0.5
    achecks = [
        ("seated",                   (0, 0, 0),   "=0"),
        ("+x free (uninstall dir)",  (2, 0, 0),   "=0"),
        ("-x stop (install ends)",   (-0.5, 0, 0), ">0"),
        ("+z lift locked",           (0, 0, g),   ">0"),
        ("+y locked",                (0, g, 0),   ">0"),
        ("-y locked",                (0, -g, 0),  ">0"),
        ("diag +y+z locked (the hook's job)", (0, d45, d45), ">0"),
    ]
    for label, d, expect in achecks:
        v = vol(host.translate(d), ten)
        ok = (v == 0.0) if expect == "=0" else (v > 0.0)
        print(f"  {label:<34} {v:>9.3f} mm3 (must be {expect}){'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"arrow: {label} = {v:.3f}")
    # bridge cap on the MORTISE = one nozzle (measured off the cutter's top face)
    am = arrow_mortise(AW, 6, clearance=CLR)
    atop = max(am.val().Faces(), key=lambda f: f.Center().z)
    arw = atop.BoundingBox().ylen
    ok = abs(arw - 0.8) < 1e-3
    print(f"  mortise bridge   {arw:.3f} mm (must be = nozzle 0.8){'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"arrow: mortise bridge {arw:.3f} != 0.8")

    # ── octagon ("stop-sign") joint: both hosts print -Z→+Z ──
    print("-- octagon --")
    WIDTH, NZ, CLR2 = 6.0, 0.8, 0.1
    Hh = octagon_height(WIDTH, NZ)
    oten = octagon_tenon(WIDTH, 14, nozzle=NZ, clearance=CLR2)      # x 0..14
    ohost = (cq.Workplane("XY").box(20, WIDTH + 8, Hh + 6, centered=(False, True, True))
             .translate((0, 0, Hh / 2.0))                          # z -3 .. Hh+3
             .cut(octagon_mortise(WIDTH, 22, nozzle=NZ, clearance=CLR2, drop=3)
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
    # POCKET variant: Z-retention removed (host lifts off along +z freely), ±Y
    # still located, slide axis still free — an entry feature, not a retainer.
    phost = (cq.Workplane("XY").box(20, WIDTH + 8, Hh + 6, centered=(False, True, True))
             .translate((0, 0, Hh / 2.0))
             .cut(octagon_mortise(WIDTH, 22, nozzle=NZ, clearance=CLR2, drop=3,
                                  pocket=True).translate((-1, 0, 0))))
    pchecks = [
        ("pocket seated",       (0, 0, 0),  "=0"),
        ("pocket +z FREE",      (0, 0, g),  "=0"),
        ("pocket +x free",      (2, 0, 0),  "=0"),
        ("pocket +y locked",    (0, g, 0),  ">0"),
        ("pocket -y locked",    (0, -g, 0), ">0"),
    ]
    for label, d, expect in pchecks:
        v = vol(phost.translate(d), oten)
        ok = (v == 0.0) if expect == "=0" else (v > 0.0)
        print(f"  {label:<20} {v:>9.3f} mm3 (must be {expect}){'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"octagon: {label} = {v:.3f}")
    # the ROOF CAP is on the MORTISE — exactly one nozzle at any width (measured off
    # the cutter's top face — this is the face the printer actually bridges)
    for w in (WIDTH, WIDTH * 3.0, octagon_width_min(NZ, CLR2)):
        m = octagon_mortise(w, 6, nozzle=NZ, clearance=CLR2)
        top = max(m.val().Faces(), key=lambda f: f.Center().z)
        rw = top.BoundingBox().ylen
        ok = abs(rw - NZ) < 1e-3
        print(f"  mortise roof @ w={w:5.2f}  {rw:.3f} mm (must be = nozzle {NZ}){'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"octagon: mortise roof at width {w} = {rw:.3f} != {NZ}")
    # the MINIMUM is on the TENON: every load segment (stem, both diagonals,
    # vertical) >= nozzle — the tenon is the smaller part. (Roof is exempt: it's the
    # capped bridge, a supported last layer.) seg(1)=lower/orange, seg(2)=vertical,
    # seg(3)=upper/green; stem = 2·pts[1].y.
    wmin = octagon_width_min(NZ, CLR2)
    tpts, _ = _octagon_profile(wmin, NZ, 0.0, CLR2)           # nominal = tenon
    seg = lambda i: math.hypot(tpts[i + 1][0] - tpts[i][0], tpts[i + 1][1] - tpts[i][1])
    stem_w, orange, vert, green = 2 * tpts[1][0], seg(1), seg(2), seg(3)
    worst = min(stem_w, orange, vert, green)
    ok = worst >= NZ - 1e-6
    print(f"  tenon floor @ wmin={wmin:.2f}  stem={stem_w:.3f} orange={orange:.3f} "
          f"vert={vert:.3f} green={green:.3f} (min >= {NZ}){'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"octagon: tenon segment {worst:.3f} < nozzle {NZ}")
    # the fat stem: stem = width/2 (computed optimum), and the lower (orange)
    # diagonal is SHORTER than the upper (green) so the stem stays thick
    tpts, _ = _octagon_profile(WIDTH, NZ, 0.0, CLR2)
    seg = lambda i: math.hypot(tpts[i + 1][0] - tpts[i][0], tpts[i + 1][1] - tpts[i][1])
    stem_w, orange, green = 2 * tpts[1][0], seg(1), seg(3)
    ok = abs(stem_w - 0.5 * WIDTH) < 1e-6 and orange < green
    print(f"  fat stem @ w={WIDTH}   stem={stem_w:.3f} (=width/2) "
          f"orange={orange:.3f} < green={green:.3f}{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"octagon: stem {stem_w:.3f} or orange>=green")
    # below the tenon-minimum width must raise
    try:
        octagon_tenon(wmin - 0.2, 10, nozzle=NZ, clearance=CLR2)
        fails.append("octagon: sub-minimum width did not raise")
        print("  width floor           did NOT raise  <-- FAIL")
    except ValueError:
        print(f"  width floor           raises below {wmin:.2f} mm (ok)")

    # ── octagon HEIGHT (the install-x `depth` room bound): extra grows verticals ──
    print("-- octagon height --")
    W3, H3 = 28.0, 32.0
    h0 = octagon_height(W3, NZ, CLR2)
    ok = abs(octagon_height(W3, NZ, CLR2, H3) - H3) < 1e-6
    print(f"  height echo           min {h0:.2f} -> sized {H3} {'ok' if ok else 'FAIL'}")
    if not ok:
        fails.append("octagon-h: height not honoured")
    hpts, _ = _octagon_profile(W3, NZ, 0.0, CLR2, H3)
    seg = lambda i: math.hypot(hpts[i + 1][0] - hpts[i][0], hpts[i + 1][1] - hpts[i][1])
    post, vert = hpts[1][1], seg(2)              # stem post height, waist vertical
    want = 2.0 * NZ + (H3 - h0) / 2.0            # verticals base = quality tier
    ok = abs(post - want) < 1e-6 and abs(vert - want) < 1e-6
    print(f"  verticals             post={post:.3f} vert={vert:.3f} (want {want:.3f} each)"
          f"{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"octagon-h: verticals {post:.3f}/{vert:.3f} != {want:.3f}")
    hm = octagon_mortise(W3, 6, nozzle=NZ, clearance=CLR2, height=H3)
    htop = max(hm.val().Faces(), key=lambda f: f.Center().z)
    hrw = htop.BoundingBox().ylen
    ok = abs(hrw - NZ) < 1e-3
    print(f"  mortise roof @ H={H3}  {hrw:.3f} mm (must be {NZ}){'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"octagon-h: roof {hrw:.3f} != {NZ}")
    hten = octagon_tenon(W3, 14, nozzle=NZ, clearance=CLR2, height=H3)
    hhost = (cq.Workplane("XY").box(20, W3 + 8, H3 + 8, centered=(False, True, True))
             .translate((0, 0, H3 / 2.0))
             .cut(octagon_mortise(W3, 22, nozzle=NZ, clearance=CLR2, drop=3,
                                  height=H3).translate((-1, 0, 0))))
    g = CLR2 + 0.2
    for label, d, expect in [("seated", (0, 0, 0), "=0"), ("+z", (0, 0, g), ">0"),
                             ("-z", (0, 0, -g), ">0"), ("+y", (0, g, 0), ">0"),
                             ("-y", (0, -g, 0), ">0")]:
        v = vol(hhost.translate(d), hten)
        ok = (v == 0.0) if expect == "=0" else (v > 0.0)
        print(f"  sized {label:14s} {v:>9.3f} mm3 (must be {expect})"
              f"{'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"octagon-h: {label} = {v:.3f}")
    # slide_joint depth -> octagon height; arrow + depth raises
    js = slide_joint(W3, 14, PrintSpec(facing="up"), PrintSpec(facing="up"),
                     clearance=CLR2, depth=H3)
    ok = abs(js.height - H3) < 1e-6
    print(f"  slide_joint depth     .height={js.height:.2f} (want {H3}) {'ok' if ok else 'FAIL'}")
    if not ok:
        fails.append("octagon-h: slide_joint depth not honoured")
    try:
        slide_joint(5.6, 12, PrintSpec(facing="side"), PrintSpec(facing="up"),
                    depth=10.0)
        fails.append("octagon-h: arrow+depth did not raise")
        print("  arrow + depth         did NOT raise  <-- FAIL")
    except ValueError:
        print("  arrow + depth         raises (ok)")
    try:
        octagon_tenon(W3, 10, nozzle=NZ, clearance=CLR2, height=h0 - 1.0)
        fails.append("octagon-h: sub-minimum height did not raise")
        print("  height floor          did NOT raise  <-- FAIL")
    except ValueError:
        print(f"  height floor          raises below {h0:.2f} mm (ok)")

    # ── octagon ARC (rotational install): seats by rotation about Z ──
    print("-- octagon arc --")
    AW2, AR = 5.0, 40.0
    Hh2 = octagon_height(AW2, NZ)
    seat_a = math.degrees(0.15 / AR)
    aten2 = octagon_tenon_arc(AW2, AR, 8.0, nozzle=NZ, clearance=CLR2)   # 0..8° CCW
    # host: full ring; cavity swept from the CW stop (−seat) far past the
    # tenon's CCW end (open entry side) — CW rotation seats against the stop.
    ahost2 = (cq.Workplane("XY").workplane(offset=-3.0)
              .circle(AR + 10).circle(AR - 10).extrude(Hh2 + 6)
              .cut(octagon_mortise_arc(AW2, AR, 30.0, nozzle=NZ,
                                       clearance=CLR2, drop=3)
                   .rotate((0, 0, 0), (0, 0, 1), -seat_a)))
    g = CLR2 + 0.2

    def _rot(w, d):
        return w.rotate((0, 0, 0), (0, 0, 1), d)

    archecks = [
        ("seated",              aten2,                       "=0"),
        ("CW past stop locked", _rot(aten2, -0.5),           ">0"),
        ("CCW uninstall free",  _rot(aten2, 2.0),            "=0"),
        ("+z lift locked",      aten2.translate((0, 0, g)),  ">0"),
        ("radial out locked",   aten2.translate((g, 0, 0)),  ">0"),
        ("radial in locked",    aten2.translate((-g, 0, 0)), ">0"),
    ]
    for label, solid, expect in archecks:
        v = vol(ahost2, solid)
        ok = (v == 0.0) if expect == "=0" else (v > 0.0)
        print(f"  {label:<20} {v:>9.3f} mm3 (must be {expect}){'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"octagon arc: {label} = {v:.3f}")

    # ── dovetail (install ∥ print-Z): both hosts -Z→+Z, slides along Z ──
    print("-- dovetail --")
    DW, DD, NZ3, CLR3 = 6.0, 4.0, 0.8, 0.1        # AVAILABLE room: width 6, depth 4
    Dh = dovetail_height(DW, DD, NZ3, CLR3)
    dten = dovetail_tenon(DW, DD, 14, nozzle=NZ3, clearance=CLR3)    # z 0..14
    dhost = (cq.Workplane("XY").box(Dh + 6, DW + 8, 20, centered=(False, True, False))
             .translate((0, 0, -3))                                  # z -3..17, face at x=0
             .cut(dovetail_mortise(DW, DD, 22, nozzle=NZ3, clearance=CLR3, drop=3)
                  .translate((0, 0, -4))))                           # through-slot in z
    n_solids = len(dten.val().Solids())
    if n_solids != 1:
        fails.append(f"dovetail: tenon is {n_solids} solids")
    g = CLR3 + 0.2
    dchecks = [
        ("seated",              (0, 0, 0),  "=0"),
        ("+z slide free",       (0, 0, 2),  "=0"),
        ("-z slide free",       (0, 0, -2), "=0"),
        ("+x push locked",      (g, 0, 0),  ">0"),
        ("-x pull locked",      (-g, 0, 0), ">0"),
        ("+y locked",           (0, g, 0),  ">0"),
        ("-y locked",           (0, -g, 0), ">0"),
    ]
    for label, d, expect in dchecks:
        v = vol(dhost.translate(d), dten)
        ok = (v == 0.0) if expect == "=0" else (v > 0.0)
        print(f"  {label:<20} {v:>9.3f} mm3 (must be {expect}){'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"dovetail: {label} = {v:.3f}")
    # profile is Y-symmetric (a lopsided +Y flank once shipped — the ±Y lock
    # probes can't see it, so gate the mirror directly)
    dpts = _dovetail_profile(DW, DD, NZ3, 1.0, CLR3)
    fwd = sorted((round(x, 6), round(y, 6)) for x, y in dpts)
    mir = sorted((round(x, 6), round(-y, 6)) for x, y in dpts)
    ok = fwd == mir
    print(f"  profile Y-symmetric   {'ok' if ok else 'ASYMMETRIC  <-- FAIL'}")
    if not ok:
        fails.append("dovetail: profile not Y-symmetric")
    # SQUARE corners: every edge axis-parallel (the reason the T replaced the
    # angled dovetail — 90° corners round compatibly on both halves)
    ok = all(abs(a[0] - b[0]) < 1e-9 or abs(a[1] - b[1]) < 1e-9
             for a, b in zip(dpts, dpts[1:] + dpts[:1]))
    print(f"  square corners        {'ok' if ok else 'ANGLED EDGE  <-- FAIL'}")
    if not ok:
        fails.append("dovetail: non-axis-parallel edge")
    # every wall segment on BOTH HALVES >= one nozzle across a spread of
    # rooms — the MORTISE lip = tenon bar (its dilation eats the lip's
    # +clearance, the reason the tenon lip is pre-grown)
    BEAD = NZ3
    for w, d in ((DW, DD), (10.0, 2.0), (dovetail_width_min(NZ3), 3.0),
                 (30.0, 30.0)):
        n2, h2, du2 = dovetail_dims(w, d, NZ3, CLR3)
        bar2 = (du2 - CLR3) / 2.0                # = the printed MORTISE lip
        o2 = (h2 - n2) / 2.0
        worst = min(bar2, o2, n2)
        ok = worst >= BEAD - 1e-9 and du2 <= d + 1e-9 and h2 <= w + 1e-9
        print(f"  bead floors @({w:5.2f},{d:5.2f}) bar/m-lip={bar2:.2f} "
              f"o={o2:.2f} neck={n2:.2f}{'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"dovetail: bead floors at ({w},{d})")
    # QUALITY BOUNDING BOX: at dovetail_box_min(quality=True), EVERY segment
    # on both halves lands exactly at the 2-nozzle tier
    qw, qd = dovetail_box_min(NZ3, CLR3, quality=True)
    n2, h2, du2 = dovetail_dims(qw, qd, NZ3, CLR3)
    bar2, o2 = (du2 - CLR3) / 2.0, (h2 - n2) / 2.0
    ok = (abs(n2 - 1.6) < 1e-9 and abs(o2 - 1.6) < 1e-9
          and abs(bar2 - 1.6) < 1e-9 and abs(h2 - qw) < 1e-9)
    print(f"  quality box ({qw:.2f},{qd:.2f}) neck={n2:.2f} o={o2:.2f} "
          f"bar={bar2:.2f}{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"dovetail: quality box → {n2},{o2},{bar2}")
    # OPTIMIZER gates — max-min, TWO stacked shear elements sharing
    # (depth − clearance), walls at the quality tier where room allows:
    # (6, 4): shear_room 1.95 → neck 2.34, o 1.6, head 5.54,
    # bar 1.95 → depth_used 4.0 (full depth)
    neck, head, dused = dovetail_dims(DW, DD, NZ3, CLR3)
    ok = (abs(neck - 2.34) < 1e-9 and abs(head - 5.54) < 1e-9
          and abs(dused - 4.0) < 1e-9)
    print(f"  optimizer @room(6,4)  neck={neck:.2f} head={head:.2f} "
          f"depth_used={dused:.2f}{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"dovetail: optimizer (6,4) → {neck},{head},{dused}")
    # depth-bound room (10, 2): parity neck rides its 2-nozzle floor →
    # neck=1.6, o=quality 1.6, head=4.8, bar=0.95 (degraded, ≥ the floor)
    neck, head, dused = dovetail_dims(10.0, 2.0, NZ3, CLR3)
    ok = (abs(neck - 1.6) < 1e-9 and abs(head - 4.8) < 1e-9
          and abs(dused - 2.0) < 1e-9 and head < 10.0)
    print(f"  optimizer @room(10,2) neck={neck:.2f} head={head:.2f} "
          f"depth_used={dused:.2f}{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"dovetail: optimizer (10,2) → {neck},{head},{dused}")
    # depth-rich room: parity caps depth_used at the (shoulder-trimmed)
    # neck's shear balance — surplus depth stays host material
    neck, head, dused = dovetail_dims(6.0, 30.0, NZ3, CLR3)
    ok = (abs(dused - (2.0 * neck / 1.2 + CLR3)) < 1e-9 and dused < 30.0
          and abs((head - neck) / 2.0 - 1.6) < 1e-9)
    print(f"  optimizer @room(6,30) neck={neck:.2f} depth_used={dused:.2f} "
          f"(parity-capped, quality shoulders){'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"dovetail: depth-rich cap → {neck},{dused}")
    # width floor raises
    try:
        dovetail_tenon(dovetail_width_min(NZ3) - 0.2, 4.0, 10, nozzle=NZ3)
        fails.append("dovetail: sub-minimum width did not raise")
        print("  width floor           did NOT raise  <-- FAIL")
    except ValueError:
        print(f"  width floor           raises below {dovetail_width_min(NZ3):.2f} mm (ok)")
    # too-shallow depth raises (no room for the mortise lip + head bar)
    for bad_d in (1.0, 1.6):
        try:
            dovetail_tenon(6.0, bad_d, 10, nozzle=NZ3)
            fails.append(f"dovetail: depth {bad_d} did not raise")
            print(f"  depth floor {bad_d}       did NOT raise  <-- FAIL")
        except ValueError:
            print(f"  depth floor {bad_d}       raises (ok)")

    # ── clearance policy: material table, fiber depth rule, fit tiers ──
    print("-- clearance policy --")
    up_gf = PrintSpec(nozzle=0.8, material="PETG-GF", facing="up")
    up_pl = PrintSpec(nozzle=0.8, facing="up")
    pchecks = [
        ("GF+GF normal → (0.15, 0.30)", joint_clearances(up_gf, up_gf), (0.15, 0.30)),
        ("plain normal → (0.15, 0.15)", joint_clearances(up_pl, up_pl), (0.15, 0.15)),
        ("GF one side → (0.15, 0.30)", joint_clearances(up_pl, up_gf), (0.15, 0.30)),
        ("GF loose → (0.30, 0.60)", joint_clearances(up_gf, up_gf, "loose"), (0.30, 0.60)),
        ("override 0.1 + GF → (0.1, 0.2)",
         joint_clearances(up_gf, up_gf, override=0.1), (0.10, 0.20)),
    ]
    for label, got, want in pchecks:
        ok = all(abs(g - w) < 1e-9 for g, w in zip(got, want))
        print(f"  {label:<34} got ({got[0]:.2f}, {got[1]:.2f})"
              f"{'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"policy: {label} got {got}")
    try:
        joint_clearances(up_gf, up_gf, fit="wobbly")
        fails.append("policy: unknown fit did not raise")
        print("  unknown fit           did NOT raise  <-- FAIL")
    except ValueError:
        print("  unknown fit           raises (ok)")

    # ── fiber depth-face relief: ONLY the mortise back wall moves ──
    # GF joint through slide_joint: laterals stay at the base clearance
    # (±y probes unchanged), but the tenon can float an extra base-worth
    # of depth toward the cavity's back before touching.
    BC = 0.30                                     # = 2 × the GF base 0.15
    gj = slide_joint(DW, 14, up_gf, up_gf, install="z", depth=DD)
    if abs(gj.clearance - 0.15) > 1e-9 or abs(gj.back_clearance - BC) > 1e-9:
        fails.append(f"policy: slide_joint GF clr ({gj.clearance}, {gj.back_clearance})")
    gten = gj.tenon(root=1.0)
    gj_cut = slide_joint(DW, 22, up_gf, up_gf, install="z", depth=DD)
    ghost = (cq.Workplane("XY").box(Dh + 6, DW + 8, 20, centered=(False, True, False))
             .translate((0, 0, -3))
             .cut(gj_cut.mortise(drop=3).translate((0, 0, -4))))
    gchecks = [
        ("seated",              (0, 0, 0),             "=0"),
        ("+y locked as before", (0, 0.15 + 0.2, 0),    ">0"),
        ("-y locked as before", (0, -(0.15 + 0.2), 0), ">0"),
        # the LIP pair also runs at the depth gap: pulling out rides the
        # full 0.3 before the lips engage (was `clearance` when only the
        # back wall grew — user print finding, both depth faces bind)
        ("pull rides depth gap", (0.25, 0, 0),         "=0"),
        ("lips engage past it",  (0.35, 0, 0),         ">0"),
    ]
    for label, d, expect in gchecks:
        v = vol(ghost.translate(d), gten)
        ok = (v == 0.0) if expect == "=0" else (v > 0.0)
        print(f"  {label:<26} {v:>9.3f} mm3 (must be {expect})"
              f"{'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"policy: GF T {label} = {v:.3f}")
    # the cavity's BACK WALL sits back_clearance past the tenon head (the
    # lateral shift probes can't isolate it — the lips bind at the base
    # clearance by design, so gate the cutter's extent directly), and the
    # swallow reports the deeper cavity
    du_gf = dovetail_dims(DW, DD, NZ3, 0.15, BC)[2]
    gbb = gj.mortise(drop=3).val().BoundingBox()
    ok = abs(gbb.xmax - (du_gf + BC)) < 1e-6
    print(f"  cavity back at du+bc      {gbb.xmax:.3f} vs {du_gf + BC:.3f}"
          f"{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"policy: GF cavity back {gbb.xmax}")
    # tier survives the bigger gaps: tenon bar = mortise lip = (du − bc)/2
    bar_gf = (du_gf - BC) / 2.0
    ok = bar_gf >= _bead(NZ3) - 1e-9
    print(f"  GF bar / mortise lip      {bar_gf:.3f} (>= bead)"
          f"{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"policy: GF bar {bar_gf}")
    pbb = (slide_joint(DW, 14, up_pl, up_pl, install="z", depth=DD)
           .mortise(drop=3).val().BoundingBox())
    du_pl = dovetail_dims(DW, DD, NZ3, 0.15)[2]
    ok = abs(pbb.xmax - (du_pl + 0.15)) < 1e-6
    print(f"  plain back at du+c        {pbb.xmax:.3f} vs {du_pl + 0.15:.3f}"
          f"{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"policy: plain cavity back {pbb.xmax}")
    if abs(gj.height - (du_gf + BC)) > 1e-9:
        fails.append(f"policy: GF height {gj.height}")

    # ── hook (single-flank dovetail): EDGE-BOUNDED faces too short for the dovetail ──
    print("-- hook --")
    HW, NZ4, CLR4 = 4.2, 0.8, 0.1                 # a face too short for the dovetail
    hten2 = hook_tenon(HW, 12, nozzle=NZ4, clearance=CLR4)           # z 0..12
    # host block spans EXACTLY the width — both ±Y faces are FREE EDGES
    hhost2 = (cq.Workplane("XY").box(6, HW, 20, centered=(False, True, False))
              .translate((0, 0, -3))
              .cut(hook_mortise(HW, 22, nozzle=NZ4, clearance=CLR4, drop=3)
                   .translate((0, 0, -4))))                          # through-slot in z
    n_solids = len(hten2.val().Solids())
    if n_solids != 1:
        fails.append(f"hook: tenon is {n_solids} solids")
    g = CLR4 + 0.2
    hchecks = [
        ("seated",              (0, 0, 0),  "=0"),
        ("+z slide free",       (0, 0, 2),  "=0"),
        ("-z slide free",       (0, 0, -2), "=0"),
        ("+x push locked",      (g, 0, 0),  ">0"),
        ("-x pull locked (the hook's job)", (-g, 0, 0), ">0"),
        ("+y locked",           (0, g, 0),  ">0"),
        ("-y locked",           (0, -g, 0), ">0"),
    ]
    for label, d, expect in hchecks:
        v = vol(hhost2.translate(d), hten2)
        ok = (v == 0.0) if expect == "=0" else (v > 0.0)
        print(f"  {label:<34} {v:>9.3f} mm3 (must be {expect}){'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"hook: {label} = {v:.3f}")
    # bead budget: the dilated cavity leaves EXACTLY one nozzle of wall at
    # each free edge, and the lip (notch minus dilation) is one nozzle
    hpts2 = _hook_profile(HW, NZ4, CLR4, 1.0)
    y_lo = min(y for _x, y in hpts2)              # stem bottom (tenon)
    y_hi = max(y for _x, y in hpts2)              # hook top (tenon)
    bot_wall = (y_lo - CLR4) - (-HW / 2.0)
    top_wall = HW / 2.0 - (y_hi + CLR4)
    stem_h2, hd1, hd2 = hook_dims(HW, NZ4, CLR4)
    lip = hd1 - CLR4
    ok = (abs(bot_wall - NZ4) < 1e-9 and abs(top_wall - NZ4) < 1e-9
          and abs(lip - NZ4) < 1e-9 and abs(hd2 - hd1 - NZ4) < 1e-9
          and stem_h2 >= NZ4 - 1e-9)
    print(f"  bead budget           walls={bot_wall:.2f}/{top_wall:.2f} lip={lip:.2f} "
          f"hook={hd2 - hd1:.2f} stem={stem_h2:.2f} (walls/lip/hook = nozzle)"
          f"{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"hook: bead budget walls {bot_wall:.2f}/{top_wall:.2f} "
                     f"lip {lip:.2f} stem {stem_h2:.2f}")
    # surplus width goes into the STEM alone
    stem_w6, _d1w, _d2w = hook_dims(6.0, NZ4, CLR4)
    ok = abs((stem_w6 - stem_h2) - (6.0 - HW)) < 1e-9
    print(f"  stem takes surplus    {stem_h2:.2f} -> {stem_w6:.2f} for width {HW} -> 6.0"
          f"{'' if ok else '  <-- FAIL'}")
    if not ok:
        fails.append(f"hook: stem surplus {stem_w6:.2f} vs {stem_h2:.2f}")
    # width floor raises
    try:
        hook_tenon(hook_width_min(NZ4, CLR4) - 0.2, 10, nozzle=NZ4, clearance=CLR4)
        fails.append("hook: sub-minimum width did not raise")
        print("  width floor           did NOT raise  <-- FAIL")
    except ValueError:
        print(f"  width floor           raises below {hook_width_min(NZ4, CLR4):.2f} mm (ok)")

    # ── unified slide_joint dispatch ──
    print("-- slide_joint --")
    up = PrintSpec(nozzle=0.8, material="PETG-GF", facing="up")
    side = PrintSpec(nozzle=0.8, material="PETG-GF", facing="side")
    CGF = _MATERIAL_CLEARANCE["PETG-GF"]          # 0.15 — the table's GF base
    cases = [
        ("up+up -> octagon", up, up, "x",
         octagon_tenon(6.0, 12, 0.8, CGF).val().Volume()),
        ("side+up -> arrow", side, up, "x",
         arrow_tenon(5.6, 12, 0.8, CGF).val().Volume()),
        ("up+up z -> dovetail", up, up, "z",
         dovetail_tenon(6.0, 3.0, 12, 0.8, CGF,                    # default depth = width/2;
                        back_clearance=2 * CGF).val().Volume()),   # GF → depth faces 2×
    ]
    for label, tspec, mspec, inst, want_vol in cases:
        w = 6.0 if tspec.facing == "up" else 5.6
        j = slide_joint(w, 12, tenon=tspec, mortise=mspec, install=inst)
        got = j.tenon().val().Volume()
        ok = abs(got - want_vol) < 1e-3 and j.clearance == CGF
        print(f"  {label:<22} clr={j.clearance} vol={got:.1f}{'' if ok else '  <-- FAIL'}")
        if not ok:
            fails.append(f"slide_joint: {label} vol {got:.1f}/{want_vol:.1f} clr {j.clearance}")
    # install='z' with a side-printed host must raise (plan profile would overhang)
    try:
        slide_joint(6, 12, side, up, install="z")
        fails.append("slide_joint: install='z' with side host did not raise")
        print("  z-install side host   did NOT raise  <-- FAIL")
    except NotImplementedError:
        print("  z-install side host   raises (ok)")
    # bounded install='z': the geometry ADAPTS to the edge-to-edge room —
    # roomy face → dovetail inside reserved edge walls; short face → hook
    jb = slide_joint(8.0, 12, up, up, install="z", bounded=True)
    ok = (jb.family == "dovetail"
          and abs(jb.width - (8.0 - 2 * (0.8 + CGF))) < 1e-9)
    print(f"  bounded 8.0 -> dovetail (usable {jb.width:.1f}) {'ok' if ok else 'FAIL'}")
    if not ok:
        fails.append(f"slide_joint: bounded 8.0 -> {jb.family}/{jb.width}")
    jb = slide_joint(4.2, 12, up, up, install="z", bounded=True)
    ok = jb.family == "hook" and abs(jb.height - hook_depth(0.8, CGF)) < 1e-9
    print(f"  bounded 4.2 -> hook (height {jb.height:.1f}) {'ok' if ok else 'FAIL'}")
    if not ok:
        fails.append(f"slide_joint: bounded 4.2 -> {jb.family}")
    ok = abs(jb.tenon().val().Volume()
             - hook_tenon(4.2, 12, 0.8, CGF).val().Volume()) < 1e-3
    print(f"  bounded hook tenon    matches hook_tenon {'ok' if ok else 'FAIL'}")
    if not ok:
        fails.append("slide_joint: bounded hook tenon volume mismatch")
    # bounded on an x-install must raise; bounded sub-minimum must raise
    try:
        slide_joint(6, 12, up, up, bounded=True)
        fails.append("slide_joint: bounded install='x' did not raise")
        print("  bounded x-install     did NOT raise  <-- FAIL")
    except ValueError:
        print("  bounded x-install     raises (ok)")
    try:
        slide_joint(3.0, 12, up, up, install="z", bounded=True)
        fails.append("slide_joint: bounded sub-minimum did not raise")
        print("  bounded width floor   did NOT raise  <-- FAIL")
    except ValueError:
        print("  bounded width floor   raises (ok)")
    # depth on an x-install family must raise (it's a dovetail-only bound)
    try:
        slide_joint(6, 12, up, up, depth=3)
        fails.append("slide_joint: depth on install='x' did not raise")
        print("  x-install depth       did NOT raise  <-- FAIL")
    except ValueError:
        print("  x-install depth       raises (ok)")
    # pocket on a non-octagon family must raise
    try:
        slide_joint(6, 12, up, up, install="z").mortise(pocket=True)
        fails.append("slide_joint: pocket on dovetail did not raise")
        print("  dovetail pocket       did NOT raise  <-- FAIL")
    except NotImplementedError:
        print("  dovetail pocket       raises (ok)")
    # material default + override
    unknown = PrintSpec(material="MysteryPLA")
    ok = (slide_joint(6, 12, unknown, unknown).clearance == _DEFAULT_CLEARANCE and
          slide_joint(6, 12, up, up, clearance=0.22).clearance == 0.22)
    print(f"  clearance default/override {'ok' if ok else 'FAIL'}")
    if not ok:
        fails.append("slide_joint: clearance default/override")
    # unsupported facing combo raises
    try:
        slide_joint(6, 12, up, side)          # tenon up, mortise side — not modelled
        fails.append("slide_joint: unsupported combo did not raise")
        print("  unsupported combo     did NOT raise  <-- FAIL")
    except NotImplementedError:
        print("  unsupported combo     raises (ok)")

    if fails:
        print("FAIL:", *fails, sep="\n  ")
    else:
        print("OK — all variants: seat clear, only the band-guarded +x is free; "
              "hook locks the up-ramp diagonal; octagon locks +-y/+-z, fat stem, "
              "tenon floor >= nozzle, mortise roof one nozzle at any width; "
              "install-z T: square corners, every tenon wall >= one nozzle, "
              "max-min allocation in the box; edge-bounded z-sites "
              "adapt T->single-flank hook with one-nozzle walls and lip.")
    sys.exit(len(fails))
