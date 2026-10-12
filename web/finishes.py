"""What the parts are made of, for the viewer: filaments and finishes.

A PRINTED part is shown as it comes off the printer: a project names its FILAMENT and
the part takes that filament's colour and surface, whatever colour the build gave it.
Glass-filled PETG is matte (the fibre breaks up the surface, so it barely reflects),
PCTG is a glossy plastic and picks up the room, TPU is dull rubber. A filament named
...-clear is seen through. A part whose filament is not named keeps the build's colour.

A model is mostly printed plastic, and the rest of it must not look like plastic: a
bearing is polished steel, a heat-set insert is brass, a belt is rubber. A project
names each such part's FINISH (the `materials=` callable of cadkit.web.export returns
it, as it returns a printed part's filament), and the page and the ray tracer give the
part that surface. A finish is a surface, not a colour: the part keeps the colour the
build gave it, so a black-oxide screw and a zinc one are both "steel". The exceptions
are in COLOURS: a finish that IS one material has that material's colour, whatever the
build gave the part -- every heat-set insert is the same brass, in every project.

The surfaces travel inside the exported model, so a page reads the same ones the export
had. (metalness, roughness), as glTF means them, and optionally how much of the room the
surface reflects (0..1) where the page's own figure for its kind is wrong.
"""

# (colour, roughness, how much of the room it reflects). The colour is linear, as glTF's.
FILAMENTS = {
    "petg-gf":    ((0.0086, 0.0091, 0.0103), 0.92, 0.25),
    "pctg":       ((0.0070, 0.0513, 0.0137), 0.22, 1.0),
    "pctg-clear": ((0.815, 0.855, 0.888), 0.18, 1.0),      # a little milky
    "pctg-black": ((0.006, 0.006, 0.007), 0.22, 1.0),
    "tpu":        ((0.0052, 0.0052, 0.0056), 1.0, 0.15),
}

FINISHES = {
    "steel":     (1.0, 0.34),     # screws, washers, rods, springs: bright but not mirror
    "polished":  (1.0, 0.26),     # bearing races, plated magnets, strings: ground, not mirror
    "brass":     (1.0, 0.36),     # heat-set inserts
    "stainless": (1.0, 0.30),     # stainless hardware: brighter and whiter than plain steel
    "gold":      (1.0, 0.24),     # contact plating
    "aluminium": (1.0, 0.46),     # anodised or bead-blasted
    "painted":   (0.0, 0.42),     # a painted or powder-coated metal case
    "rubber":    (0.0, 0.95),     # belts
    "nylon":     (0.0, 0.50),     # connector housings
    "pvc":       (0.0, 0.55),     # wire insulation
    "board":     (0.0, 0.36),     # a circuit board's solder mask: a hard gloss lacquer
    "ink":       (0.0, 0.90),     # silkscreen
    "glass":     (0.0, 0.06),     # a window: it mirrors the room
    "screen":    (0.0, 1.0, 0.0),  # a display's face: where it is dark it stays dark,
                                  # whatever is overhead (the third number: it reflects
                                  # none of the room)
}

# a finish that is one material, and so one colour (linear, as glTF's)
COLOURS = {
    "brass": (0.571, 0.319, 0.073),
    "gold": (0.656, 0.420, 0.051),
    "stainless": (0.565, 0.578, 0.604),
}

# ── WHAT A PART IS MADE OF IS SAID WHERE THE PART IS MADE ─────────────────────────────
# A part's material is a name from this module (a filament or a finish), and there are
# three places it can come from, the first that speaks winning:
#
#   1. THE CODE THAT DREW IT. cadkit's own bought parts (cadkit.fasteners: every screw
#      and every heat-set insert) say what they are as they are made: made_of(solid,
#      "brass"). A project cannot get those wrong, or forget them, whatever it names
#      them and however it places them.
#   2. THE PROJECT, ON THE PART: made_of(part, "pctg") for a solid of its own; or a
#      fourth item in the (name, solid, colour, material) it hands the viewer; or
#      metadata={"material": ...} on a cadquery Assembly's add().
#   3. THE PROJECT, BY NAME: the materials= function of cadkit.web.export (older).
#
# made_of() does not mark the solid (cadquery makes a new object at every move): it
# remembers WHAT THE SOLID IS -- its face count, volume and surface area, none of which
# a move, a turn, a mirror or a trip through a STEP file changes -- and the export asks
# the same three numbers of each part it is given. The memory is this process's own: a
# build and its export in one run, which is every build.
_MADE = []                      # (faces, volume, area, material)
_MADE_MAX_FACES = 400           # nothing asked of a part bigger than anything remembered


def known(material) -> bool:
    return material in FILAMENTS or material in FINISHES


def _what(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    n, ex = 0, TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        n += 1
        ex.Next()
    if n == 0:
        return None
    v, a = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, v)
    BRepGProp.SurfaceProperties_s(shape, a)
    return n, v.Mass(), a.Mass()


def _one(solid):
    if hasattr(solid, "vals"):
        import cadquery as cq
        vals = [v for v in solid.vals() if isinstance(v, cq.Shape)]
        return vals[0].wrapped if len(vals) == 1 else cq.Compound.makeCompound(vals).wrapped
    return getattr(solid, "wrapped", solid)


def made_of(solid, material):
    """Say what `solid` (cq.Workplane / cq.Shape / TopoDS_Shape) is made of, and get it
    back. The viewer then shows it as that material wherever it ends up, under any name."""
    if not known(material):
        raise ValueError("%r is no material cadkit knows: %s"
                         % (material, ", ".join(sorted(list(FILAMENTS) + list(FINISHES)))))
    w = _what(_one(solid))
    if w is not None and not any(_same(w, m) and m[3] == material for m in _MADE):
        _MADE.append(w + (material,))
    return solid


def _same(w, m):
    return (w[0] == m[0] and abs(w[1] - m[1]) <= 1e-6 * max(1.0, abs(m[1]))
            and abs(w[2] - m[2]) <= 1e-6 * max(1.0, abs(m[2])))


def material_made(shape):
    """The material made_of() was told for a solid that is `shape` (a TopoDS_Shape),
    or None. Two materials told for one and the same solid: None, and nobody guesses."""
    if not _MADE:
        return None
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    n, ex, most = 0, TopExp_Explorer(shape, TopAbs_FACE), max(m[0] for m in _MADE)
    while ex.More() and n <= most:
        n += 1
        ex.Next()
    if n > most or not any(m[0] == n for m in _MADE):
        return None
    w = _what(shape)
    got = {m[3] for m in _MADE if w is not None and _same(w, m)}
    return got.pop() if len(got) == 1 else None

# A COMPONENT MODEL carries many colours and no names, but the libraries draw their
# metal in a handful of fixed ones (sRGB): KiCad's "metal grey pins" and "gold pins",
# and the four cadkit.web.parts draws leads, shells, plated shells and contacts in.
METAL_COLOURS = ((0.824, 0.820, 0.781), (0.859, 0.738, 0.496),
                 (0.78, 0.78, 0.80), (0.70, 0.71, 0.74), (0.86, 0.85, 0.82),
                 (0.83, 0.68, 0.25))
METAL_TOL = 0.02


def surfaces():
    """What the model file carries: {filament or finish: [metalness, roughness]}, a
    filament with how much of the room it reflects as a third number."""
    out = {k: list(v) for k, v in FINISHES.items()}
    out.update({k: [0.0, rough, room] for k, (_, rough, room) in FILAMENTS.items()})
    return out
