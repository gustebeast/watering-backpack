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
}

# A COMPONENT MODEL carries many colours and no names, but the libraries draw their
# metal in a handful of fixed ones (sRGB): KiCad's "metal grey pins" and "gold pins",
# and the three cadkit.web.parts draws leads, shells and contacts in.
METAL_COLOURS = ((0.824, 0.820, 0.781), (0.859, 0.738, 0.496),
                 (0.78, 0.78, 0.80), (0.70, 0.71, 0.74), (0.83, 0.68, 0.25))
METAL_TOL = 0.02


def surfaces():
    """What the model file carries: {filament or finish: [metalness, roughness]}, a
    filament with how much of the room it reflects as a third number."""
    out = {k: list(v) for k, v in FINISHES.items()}
    out.update({k: [0.0, rough, room] for k, (_, rough, room) in FILAMENTS.items()})
    return out
