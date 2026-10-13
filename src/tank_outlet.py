# -*- coding: utf-8 -*-
"""The chain from the tank wall to the hose — four rigid things before the vinyl starts.

WHY THIS FILE EXISTS. `WORK_V2_PUNCHLIST` findings 16 and 19 say it in their own
words: "`src/plumbing.py` routes `tank_down` as a bare centreline and
`check_plumbing.py` measures hose against hose. Neither knows a fitting has
length, so **both will keep passing either layout**." The hose used to leave the
model AT the tank wall, as if the Uniseal were a hose barb. It is not. In the
order the owner wrote it out:

    tank wall -> Uniseal -> PVC stub -> PVC female adapter -> MNPT-to-barb -> hose

That is four rigid parts, and the first millimetre of vinyl is about 68 mm from
the wall on the straight fitting, which is what finding 19 measured and what no
gate could see.

WHICH FITTING IS FITTED. Both are bought (U.S. Plastic 62017 straight and 62043
elbow, $1.30 for the pair rather than a second freight charge). `FITTING`
chooses, and the elbow is the default because finding 19 found the straight
overruns the horizontal leg by ~29 mm. Change the constant to see the other.

WHERE THE NUMBERS COME FROM, and every one says:

* **The PVC** is 1/2" schedule 40 to ASTM D1785 — 0.840" OD, 0.622" ID. Not an
  estimate and not a choice: the Uniseal seals on that OD, which is why the
  chain starts with rigid pipe rather than the hose.
* **The Uniseal's bore** is its 1.25" hole saw, which the vendor publishes
  because it is the thing you have to buy. Its own body is NOT published and is
  an estimate, flagged below.
* **The elbow** is Thogus drawing TE 2088 rev E, read off the drawing U.S.
  Plastic links from item 62043: for TE2088/P (polyethylene, the part bought),
  A 1.23, B .360, C 1.21, D .610, E .86, F .60, G .240, H .495, I .500, J .545
  inches, at ANSI Y14.5 1994 with X.XX = +-0.05.
  ⚠ **THE VALUES ARE THE DRAWING'S; THE LETTER-TO-FEATURE MAPPING IS INFERRED.**
  The dimension letters sit on vector geometry that cannot be read as text, so B
  and F are matched to features by value — .360 against the straight's measured
  .365 bore, .60 against its measured .600 crest, both of which are the same
  Thogus hose-ID family — and A and C are taken as the two corner-to-end leg
  lengths because they are the only pair big enough to be. That inference is
  load-bearing for `ELBOW_CORNER_Y`, and the owner has the part: two minutes
  with a caliper settles it. See `tools/check_tank_outlet.py`, which fails on
  the consequence rather than on the inference.
* **The two ESTIMATES are the two this project has always had** and are finding
  19's, unchanged, so this file does not invent a second set: the stub's reach
  past the wall and the female adapter's length net of its socket.
"""

from __future__ import annotations

import cadquery as cq

from cadkit.web.finishes import made_of

from . import plumbing as P

# ── The wall, and the axis everything is on ─────────────────────────────────
WALL_Y = P.UNISEAL_Y               # 173 — the tank's +Y face
AXIS_X = P.UNISEAL_X               # 73  — in line with the tank tee
AXIS_Z = P.UNISEAL_Z               # 234 — as low as a seal can sit

# ── 1/2" schedule-40 PVC, ASTM D1785 ────────────────────────────────────────
PVC_OD, PVC_ID = 21.34, 15.80      # 0.840" / 0.622"

# ── The Uniseal ─────────────────────────────────────────────────────────────
UNISEAL_BORE = 31.75               # 1.25" hole saw — the vendor's own figure
UNISEAL_OD   = 44.0                # ESTIMATE: the seal's outer lip on the wall
UNISEAL_L    = 19.0                # ESTIMATE: how much wall it grips
TANK_WALL_T  = 3.0                 # ESTIMATE: a blow-moulded can's wall

# ── The PVC stub ────────────────────────────────────────────────────────────
STUB_IN    = 25.4                  # ~1" proud INSIDE — the vendor says to clear
                                   # the seal's inner lip by about an inch
STUB_PROUD = 25.0                  # ESTIMATE (finding 19): enough to seat in
                                   # the adapter socket

# ── The PVC female adapter, slip x FNPT ─────────────────────────────────────
# ⚠ FEMALE. Both hose adapters are male, and nothing in this repo checks a
# thread gender — the BOM carries that warning because this step read "male"
# for one revision while step 3 was also male.
ADAPTER_SOCKET_D = 26.7            # ESTIMATE: hub over a 0.840" socket
ADAPTER_SOCKET_L = 22.2            # 0.875", the standard 1/2" socket depth
ADAPTER_NET      = 13.0            # ESTIMATE (finding 19): length past the stub

# The face the hose fitting screws against. 173 + 25 + 13 = 211, which is
# finding 19's own figure for the start of the bottom horizontal leg.
FNPT_FACE_Y    = WALL_Y + STUB_PROUD + ADAPTER_NET
THREAD_ENGAGED = 13.0              # finding 19, for the straight; the elbow's
                                   # NPT is the same 1/2"-14 taper

# ── The hose fittings, both bought ──────────────────────────────────────────
IN = 25.4

# Thogus TE2088/P — U.S. Plastic 62043, the ELBOW, black HDPE
ELBOW_LEG_THREAD = 1.23 * IN       # DIM A, 31.24 — corner to the thread's end
ELBOW_LEG_BARB   = 1.21 * IN       # DIM C, 30.73 — corner to the barb's tip
ELBOW_BORE       = 0.360 * IN      # DIM B,  9.14
ELBOW_CREST      = 0.600 * IN      # DIM F, 15.24 — 1/2" vinyl stretches on
ELBOW_HEX        = 0.86 * IN       # DIM E, 21.84 — taken as the wrench flats

# Thogus TA1088/P — U.S. Plastic 62017, the STRAIGHT, black HDPE.
# Measured in finding 19 rather than read off a drawing.
STRAIGHT_OVERALL = 1.69 * IN       # 42.93
STRAIGHT_PAST    = 29.9            # beyond the FNPT face, ~13 mm engaged
STRAIGHT_CREST   = 0.600 * IN
STRAIGHT_BORE    = 0.365 * IN

FITTING = "elbow"                  # "elbow" (62043) or "straight" (62017)

# The NPT male spud, common to both: 1/2"-14 tapered, drawn as its crest
NPT_D = 0.840 * IN                 # the thread's major diameter is the pipe OD
NPT_L = 18.0                       # ESTIMATE: the spud's full length


def _tube(od, idd, y0, y1):
    """A pipe along +Y between two y values."""
    t = (cq.Workplane("XZ").workplane(offset=-y0)
         .circle(od / 2.0).extrude(-(y1 - y0)))
    if idd:
        t = t.cut(cq.Workplane("XZ").workplane(offset=-(y0 - 1))
                  .circle(idd / 2.0).extrude(-((y1 - y0) + 2)))
    return t.translate((AXIS_X, 0, AXIS_Z))


def uniseal() -> cq.Workplane:
    """The seal in the tank wall. EPDM, and it installs entirely from outside —
    which is the whole reason it is here: a Scepter's 44 mm opening will not
    admit a hand, so a conventional bulkhead with a nut on the inside cannot be
    fitted at all (DESIGN_V2 section 3)."""
    y0 = WALL_Y - UNISEAL_L / 2.0
    body = _tube(UNISEAL_OD, PVC_OD, y0, y0 + UNISEAL_L)
    return made_of(body, "rubber")


def pvc_stub() -> cq.Workplane:
    """The rigid pipe through the seal. The hose cannot go through a Uniseal —
    1/2" vinyl is 0.750" OD against the seal's 0.840" — which is why this
    chain has four parts instead of one."""
    return made_of(_tube(PVC_OD, PVC_ID, WALL_Y - STUB_IN, WALL_Y + STUB_PROUD),
                   "pvc")


def pvc_adapter() -> cq.Workplane:
    """Slip x FNPT, solvent-welded to the stub outside the tank."""
    y0 = WALL_Y + STUB_PROUD - ADAPTER_SOCKET_L
    sock = _tube(ADAPTER_SOCKET_D, PVC_OD, y0, WALL_Y + STUB_PROUD)
    nut = _tube(ADAPTER_SOCKET_D, NPT_D, WALL_Y + STUB_PROUD, FNPT_FACE_Y)
    return made_of(sock.union(nut), "pvc")


def _npt_spud(y_face):
    """The male taper, from `y_face` back into the adapter."""
    return _tube(NPT_D, 0, y_face - THREAD_ENGAGED, y_face - THREAD_ENGAGED + NPT_L)


def _barb(length, crest, axis="-Z", origin=(0.0, 0.0, 0.0)):
    """A hose barb as its crest envelope: the ridges are what grips, and a
    stepped cone is the honest shape for a clearance drawing."""
    r = crest / 2.0
    if axis == "+Y":
        w = cq.Workplane("XZ").workplane(offset=-origin[1]).circle(r).extrude(-length)
    else:
        w = cq.Workplane("XY").workplane(offset=origin[2]).circle(r).extrude(-length)
    return w


# ── Where the corner and the hose actually are ──────────────────────────────
# The elbow's thread leg runs from its engaged end OUT to the corner, so the
# corner sits one leg past the thread's end, not at the adapter's face. That is
# the figure finding 19 could not have: it measured the bottom horizontal leg
# from the FNPT face at y 211, and the hose's vertical axis is not there.
ELBOW_CORNER_Y = FNPT_FACE_Y - THREAD_ENGAGED + ELBOW_LEG_THREAD
ELBOW_TIP_Z    = AXIS_Z - ELBOW_LEG_BARB
STRAIGHT_TIP_Y = FNPT_FACE_Y + STRAIGHT_PAST


def elbow() -> cq.Workplane:
    """U.S. Plastic 62043 / Thogus TE2088/P, black HDPE, turning the line DOWN
    at the tank so the rigid stack lands on the leg that has room."""
    spud = _npt_spud(FNPT_FACE_Y)
    run = _tube(ELBOW_HEX, 0, FNPT_FACE_Y - THREAD_ENGAGED + NPT_L, ELBOW_CORNER_Y)
    # ⚠ THE TWO LEGS' AXES MEET AT THE CORNER POINT, and the drawing's A and C
    # are measured from THAT intersection — not from a face. Putting the barb
    # leg half a hex inboard of it (which an earlier draft did) moves the hose's
    # whole vertical axis 11 mm back toward the tank and quietly buys back a
    # third of the shortfall this file exists to measure.
    corner = (cq.Workplane("XY").workplane(offset=AXIS_Z - ELBOW_HEX / 2.0)
              .circle(ELBOW_HEX / 2.0).extrude(ELBOW_HEX)
              .translate((AXIS_X, ELBOW_CORNER_Y, 0)))
    leg = (_barb(ELBOW_LEG_BARB, ELBOW_CREST, "-Z", (0, 0, AXIS_Z))
           .translate((AXIS_X, ELBOW_CORNER_Y, 0)))
    return made_of(spud.union(run).union(corner).union(leg), "painted")


def straight() -> cq.Workplane:
    """U.S. Plastic 62017 / Thogus TA1088/P — BOUGHT AND NOT FITTED, drawn so
    the alternative is a thing the model can be asked about rather than a line
    in a punchlist. Finding 19: its barb tip lands ~68 mm off the wall and
    leaves 21 mm of hose before a corner that needs 50."""
    spud = _npt_spud(FNPT_FACE_Y)
    hexc = _tube(ELBOW_HEX, 0, FNPT_FACE_Y - THREAD_ENGAGED + NPT_L,
                 FNPT_FACE_Y + STRAIGHT_PAST - 20.0)
    barb = (_barb(20.0, STRAIGHT_CREST, "+Y", (0, STRAIGHT_TIP_Y, 0))
            .translate((AXIS_X, 0, AXIS_Z)))
    return made_of(spud.union(hexc).union(barb), "painted")


def hose_start():
    """The first point of VINYL — where `plumbing.tank_down` has to begin."""
    if FITTING == "elbow":
        return (AXIS_X, ELBOW_CORNER_Y, ELBOW_TIP_Z)
    return (AXIS_X, STRAIGHT_TIP_Y, AXIS_Z)


def parts():
    """[(name, solid)] — the stack, with only the FITTED hose adapter in it.

    ⚠ NAMED outlet_*, NOT tank_*, ON PURPOSE. build.intended() carries a
    BLANKET rule that any two parts both named tank_/green_ may interpenetrate
    -- it is there for the hoses meeting at a tee, and it gets no volumes. A
    rigid fitting that inherited it would be exempt from the overlap gate by
    its spelling, which is the kind of whitelist this file's own neighbours
    were written to get rid of. These earn their exemptions one at a time."""
    out = [("outlet_uniseal", uniseal()),
           ("outlet_pvc_stub", pvc_stub()),
           ("outlet_pvc_adapter", pvc_adapter())]
    out.append(("outlet_fitting", elbow() if FITTING == "elbow" else straight()))
    return out


def solid() -> cq.Workplane:
    out = None
    for _n, s in parts():
        out = s if out is None else out.union(s)
    return out
