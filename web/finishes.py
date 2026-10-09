"""What the parts that are NOT printed are made of, for the viewer.

A model is mostly printed plastic, and the rest of it must not look like plastic: a
bearing is polished steel, a heat-set insert is brass, a belt is rubber. A project
names each such part's FINISH (the `materials=` callable of cadkit.web.export returns
it, as it returns a printed part's filament), and the page and the ray tracer give the
part that surface. A finish is a surface, not a colour: the part keeps the colour the
build gave it, so a black-oxide screw and a zinc one are both "steel".

The table travels inside the exported model, so a page reads the same one the export
had. (metalness, roughness), as glTF means them.
"""

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
    "glass":     (0.0, 0.06),     # a display's window
}

# A COMPONENT MODEL carries many colours and no names, but the libraries draw their
# metal in a handful of fixed ones (sRGB): KiCad's "metal grey pins" and "gold pins",
# and the three cadkit.web.parts draws leads, shells and contacts in.
METAL_COLOURS = ((0.824, 0.820, 0.781), (0.859, 0.738, 0.496),
                 (0.78, 0.78, 0.80), (0.70, 0.71, 0.74), (0.83, 0.68, 0.25))
METAL_TOL = 0.02
