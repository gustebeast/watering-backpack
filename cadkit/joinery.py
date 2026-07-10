"""joinery.py — printable mortise-and-tenon slide joints (dull arrowhead).

See JOINERY_README.md for the full story. THE standard recipe — a tenon on a
sideways-printed (+Y build) host mated to a mortise in a flat-printed (+Z
build) host — is `ramp=True, hook_h=...` (print-validated in the toothpaste
dispenser; plain `ramp=True` without a hook cams apart along the up-ramp
diagonal and survives only as a demo):

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "freecad"))
    from joinery import arrow_tenon, arrow_mortise

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

Every working face is 45° ON PURPOSE — see the README for why the shared
ramp face can't be steepened for one part without hurting the other. The
only flat is the dull tip (default 1.6 = 2 bead widths of a 0.8 nozzle): a
tiny bridge in the mortise, deliberately "just big enough to print".
"""

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

    if fails:
        print("FAIL:", *fails, sep="\n  ")
    else:
        print("OK — all variants: seat clear, only the band-guarded +x is free; "
              "hook locks the up-ramp diagonal.")
    sys.exit(len(fails))
