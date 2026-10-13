# -*- coding: utf-8 -*-
"""The two tees — barb x barb x MALE NPT, and the male leg is the one with a job.

U.S. Plastic item 62128, Thogus TT3888/P, black polyethylene. Two of them, one
per circuit, bought 2026-10-06.

WHICH LEG IS WHICH, from DESIGN_V2 section 4. The two inline barbs take the
pump hoses; the THIRD leg is a male 1/2"-14 NPT and it exists to carry a
strainer, not a hose:

* **tank tee** — barbs to pump A's inlet and pump B's outlet, male leg UP toward
  the Uniseal. The strainer on it protects pump A.
* **green tee** — barbs to pump A's outlet and pump B's inlet, male leg DOWN
  toward the wand.

Both strainers show their FEMALE end to the tee, which is what makes the
fittings come out even: one male tee leg screws straight into each, with no
adapter.

⚠ **THE STRAINERS ARE STILL NOT DRAWN, AND THAT IS FINDING 16, STILL OPEN.**
Its words: "the strainers have a LENGTH, and it has never been measured ... It
is a tape-measure job on a part that is already in the drawer." Drawing the tee
does not close it -- but it does take a bite out of the budget that finding was
working with, because the TEE's own half-length was not in that sum either.
`tools/check_tank_outlet.py` prints what is left.

THE DIMENSIONS are Thogus drawing TT 3888 rev D, read out of the PDF U.S.
Plastic links from item 62128. For TT3888/P the row is .395, .500, .24, .60,
1.25, 2.44, .365, .610, .86 inches, and the drawing labels the third leg
"MALE 1/2"-14 NPT".

⚠ SAME CAVEAT AS THE ELBOW, AND IT CROSS-CHECKS BETTER HERE. The letter-to-
feature mapping is inferred, not read -- the dimension letters sit on vector
geometry, and the only raster image in the file is the Thogus logo. But three
of these values appear in TE 2088's row for the same family and the same
nominal size (.365/.360 bore, .60 crest, .86 across the flats), and 2.44 is
the only value that can be a barb-to-barb overall. That makes the run solid.
The BRANCH leg is the soft one: 1.25 is taken for it because it is the only
remaining value of the right order, and it is flagged rather than trusted.
"""

from __future__ import annotations

import cadquery as cq

from cadkit.web.finishes import made_of

from . import plumbing as P

IN = 25.4

# ── Thogus TT3888/P ─────────────────────────────────────────────────────────
TEE_OVERALL = 2.44 * IN            # 61.98 — barb tip to barb tip, the run
TEE_RUN_HALF = TEE_OVERALL / 2.0   # 30.99 — centre to each barb tip
TEE_BRANCH  = 1.25 * IN            # 31.75 — centre to the thread's end. The
                                   # one INFERRED leg; see the caveat above.
TEE_CREST   = 0.600 * IN           # 15.24 — 1/2" vinyl stretches on
TEE_BORE    = 0.365 * IN           #  9.27 — same as the straight's, so the tee
                                   # adds no restriction the line does not have
TEE_HEX     = 0.86 * IN            # 21.84 — across the flats, taken as the body
NPT_D       = 0.840 * IN           # 21.34 — 1/2"-14 NPT major, i.e. the pipe OD

# ── Where they are, and which way the male leg points ───────────────────────
# The barbs are on X at both tees: TANK_TEE takes A_IN from -X and B_OUT from
# +X, GREEN_TEE takes A_OUT from -X and B_IN from +X (src/plumbing.routes).
PLACED = {
    "tee_tank":  (P.TANK_TEE,  +1),    # male leg UP, to the Uniseal
    "tee_green": (P.GREEN_TEE, -1),    # male leg DOWN, to the wand
}


def _rod_x(d, length, centre):
    return (cq.Workplane("YZ").workplane(offset=centre[0] - length / 2.0)
            .circle(d / 2.0).extrude(length)
            .translate((0, centre[1], centre[2])))


def _rod_z(d, length, centre, z_dir):
    z0 = centre[2] if z_dir > 0 else centre[2] - length
    return (cq.Workplane("XY").workplane(offset=z0)
            .circle(d / 2.0).extrude(length)
            .translate((centre[0], centre[1], 0)))


def tee(centre, z_dir) -> cq.Workplane:
    """One tee, in place. Drawn as its envelope: a run between two barb tips, a
    body across the flats, and the male spud on the third leg. The barb ridges
    are not drawn -- what this is for is the LENGTH each leg occupies, which is
    the thing no model here has ever had."""
    run = _rod_x(TEE_CREST, TEE_OVERALL, centre)
    body = _rod_x(TEE_HEX, TEE_HEX, centre)
    branch = _rod_z(NPT_D, TEE_BRANCH, centre, z_dir)
    collar = _rod_z(TEE_HEX, TEE_HEX / 2.0, centre, z_dir)
    return made_of(run.union(body).union(branch).union(collar), "painted")


def parts():
    """[(name, solid)] — both tees, placed."""
    return [(n, tee(c, d)) for n, (c, d) in PLACED.items()]


def solid() -> cq.Workplane:
    out = None
    for _n, s in parts():
        out = s if out is None else out.union(s)
    return out


def barb_end(name, sign):
    """Where a hose pushed fully onto one run barb ENDS — against the body.

    ⚠ NOT THE BARB TIP, AND NOT THE TEE'S CENTRE. A hose does not stop at the
    tip of a barb, it swallows it: 1/2" vinyl has a 12.7 mm bore and the crest
    is 15.24, so it stretches on and runs up against the flats. The vinyl's own
    end is therefore half a body in from the barb tip, and the 20 mm of hose
    over the barb is held dead straight by the barb whatever the route does.

    The routes used to end at the tee's CENTRE, which drew the vinyl straight
    through the body and out the far side -- both run hoses met in the middle
    of the same tee. It also flattered every length: `routes` picked the tees'
    x "so both corners keep >= BEND_R of straight on each side", measured to a
    point inside the fitting. Measured to the flats, tank_to_A keeps 51.1 mm
    against the 50 a bend wants, so the margin is 1.1 mm and not 12.
    """
    c = PLACED[name][0]
    return (c[0] + sign * TEE_HEX / 2.0, c[1], c[2])


def branch_end(name):
    """The far end of the male leg — where a strainer starts."""
    centre, z_dir = PLACED[name]
    return (centre[0], centre[1], centre[2] + z_dir * TEE_BRANCH)
