# -*- coding: utf-8 -*-
"""Tiny colour helper for baking per-part colours into a CadQuery assembly.

`cq.Color` already accepts an SVG/X11 colour *name* ("red") or float RGB(A) in
0..1 — but NOT hex strings or 0..255 ints, which are what you usually have on
hand. This wraps all of those into a `cq.Color` so build scripts can stay terse:

    from cq_colors import color   # see README for the sys.path one-liner
    assy.add(carriage, name="carriage", color=color("#3a7bd5"))
    assy.add(motor,    name="motor",    color=color((210, 94, 58)))
    assy.add(rail,     name="rail",     color=color("slategray"))

Colours baked this way are written into the STEP file, so they show up in any
STEP viewer (FreeCAD, KiCad, online viewers, ...), not just our viewer.
"""

import cadquery as cq


def color(spec, alpha=1.0):
    """Return a cq.Color from a hex string, an (r,g,b[,a]) tuple (0..1 or
    0..255), or an SVG/X11 colour name."""
    if isinstance(spec, cq.Color):
        return spec
    if isinstance(spec, str):
        s = spec.strip()
        if s.startswith("#"):
            s = s[1:]
            if len(s) == 3:                      # short form #abc
                s = "".join(ch * 2 for ch in s)
            r, g, b = (int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
            a = int(s[6:8], 16) / 255.0 if len(s) >= 8 else alpha
            return cq.Color(r, g, b, a)
        return cq.Color(s)                       # named colour
    # sequence of numbers
    vals = list(spec)
    r, g, b = vals[0], vals[1], vals[2]
    if max(r, g, b) > 1.0:                        # treat as 0..255
        r, g, b = r / 255.0, g / 255.0, b / 255.0
    a = vals[3] if len(vals) > 3 else alpha
    return cq.Color(r, g, b, a)
