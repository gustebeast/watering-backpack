"""The face the CAD letters the board in — resolved, measured, never retyped.

⚠ WHY THIS FILE EXISTS. `elec/silk.py` declares the face the FAB plots
("Rennie Mackintosh PSG" Bold, finding 52) and `cadkit/board_geom.py` takes a
`silk_font` path to draw the same lettering in the CAD. Nothing connected them,
so the board was plotted in Rennie Mackintosh and DRAWN in the CAD kernel's
default face — which is what the owner saw. Every gate passed throughout:
`cad_geom_check` counts labels by probing for ink at each label's position and
reported 139 / 139, because a label drawn in the wrong typeface is still a
label with ink in it. The typeface was a figure no gate read.

board_geom's own docstring says it plainly: the lettering "is only as true as
the font is the one the fab's ink was plotted in."

THE FACE IS NOT DECLARED TWICE. `SILK_FACE` is parsed straight out of
`elec/silk.py` — the one declaration — rather than copied here. It cannot be
imported: `elec/silk.py` imports `cadkit.kicad_silk`, which imports `pcbnew`,
which only exists under KiCad's interpreter. So it is read with `ast`, which
needs no import and runs no code.

⚠ `silk_cap` IS MEASURED THROUGH THE SAME KERNEL THAT DRAWS THE BOARD, not
read from the font's OS/2 table and not typed. A KiCad text "size" is its
CAPITAL HEIGHT; a CadQuery text size is its EM, so board_geom divides by this
ratio to make them agree. Measuring a rendered "H" asks the question the
drawing actually depends on — what this kernel draws at this size — instead of
trusting metadata the kernel may not use. For this face it lands on 0.6670,
which is exactly the file's sCapHeight/unitsPerEm (667/1000); the agreement is
corroboration, not the source. cadkit's default is 0.72, close to the kernel
default face's own 0.7158 and 7.9 % wrong for this one.

THE LICENSED FILE IS NOT IN THIS REPOSITORY and must not be committed. It has
to be INSTALLED (per-user is enough), same requirement the fab side already
has. If it cannot be found the CAD falls back to the kernel's default face and
SAYS SO — and `tools/check_silk_face.py` FAILS, rather than passing quietly on
a drawing that no longer matches the built thing.
"""
from __future__ import annotations

import ast
import glob
import os

# cadkit's default, correct for the kernel's own default face (measured 0.7158)
# and wrong for any other -- so it is only used when no face was resolved.
from cadkit.board_geom import SILK_CAP as DEFAULT_CAP

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_DECL = os.path.join(_ROOT, "elec", "silk.py")

# Where an installed face lives, in search order. The env var is first so a
# machine that keeps its fonts elsewhere needs no edit here.
_DIRS = [
    os.environ.get("WATERING_SILK_FONT_DIR"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""),
                 "Microsoft", "Windows", "Fonts"),          # per-user install
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    # the project the owner supplied the file from (public-steel-guitar's
    # elec/fonts/ is gitignored there too, so this is a convenience, not a
    # dependency)
    os.path.join(os.path.dirname(_ROOT), "public-steel-guitar", "elec", "fonts"),
]


def declared_face():
    """`SILK_FACE` out of elec/silk.py, read without importing it."""
    with open(_DECL, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=_DECL)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "SILK_FACE":
                    return ast.literal_eval(node.value)
    raise RuntimeError("no SILK_FACE assignment in %s" % _DECL)


SILK_FACE = declared_face()
FAMILY = SILK_FACE["family"]
BOLD = bool(SILK_FACE.get("bold"))


def _family_of(path):
    """The family name inside a font file, or None if it cannot be read.

    fontTools is used ONLY here and only to confirm a candidate file really is
    the declared family -- matching on filename would accept any file somebody
    renamed. It is not needed to draw, so a machine without it degrades to a
    filename match and the gate says which happened.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return None
    try:
        f = TTFont(path, fontNumber=0, lazy=True)
        try:
            return f["name"].getDebugName(1)
        finally:
            f.close()
    except Exception:                                      # noqa: BLE001
        return None


def font_path():
    """(path, how) for the declared family, or (None, why not)."""
    seen = 0
    by_name = []
    for d in _DIRS:
        if not d or not os.path.isdir(d):
            continue
        for path in sorted(glob.glob(os.path.join(d, "*.otf"))
                           + glob.glob(os.path.join(d, "*.ttf"))):
            seen += 1
            fam = _family_of(path)
            if fam == FAMILY:
                return path, "family name read from the file"
            if fam is None and FAMILY.replace(" ", "").lower() in \
                    os.path.basename(path).replace("-", "").lower():
                by_name.append(path)
    if by_name:
        return by_name[0], ("FILENAME MATCH ONLY -- fontTools is not installed, "
                            "so the family inside the file was not verified")
    return None, ("no file with family %r in any of: %s (%d font file(s) looked at)"
                  % (FAMILY, ", ".join(d for d in _DIRS if d), seen))


def cap_ratio(path):
    """Rendered capital height as a fraction of the requested size, measured
    through the drawing kernel. `path` None measures the kernel default face."""
    import cadquery as cq
    face = {"fontPath": path} if path else {}
    bb = cq.Workplane("XY").text("H", 10.0, 1.0, **face).val().BoundingBox()
    return bb.ylen / 10.0


def advance_ratios(path, pairs=None):
    """{"+/H": measured} for each ratio elec/silk.py declares in `widths`.

    ⚠ THIS IS THE FILE-VERSION PROOF AND IT IS NOT A HEIGHT TEST. ITC's
    original Rennie Mackintosh Bold draws "+" as a TH ligature and "=" as TT;
    the PSG file exists because those were redrawn plain. Both files carry the
    SAME family name, so resolving the family proves nothing about which one is
    installed -- and "+5V" has plotted as "TH5V" on real boards with every
    check passing.

    An earlier version of this asked whether "+" stands cap-height, on the
    theory that a ligature is a letterform and a plus sign is not. That does
    not hold: across the 135 faces installed here, Courier Bold's plain "+"
    measures 0.960 of cap height and Verdana Bold 0.889, so the question
    cannot separate them. elec/silk.py's own proof is the ADVANCE ratio --
    0.97 for the PSG file against 1.42 for the ITC one -- which is a 46 %
    difference rather than an overlap, so that is what is read here.

    Raises ImportError without fontTools: advances live in the font's hmtx
    table and there is no way to ask the drawing kernel for them.
    """
    from fontTools.ttLib import TTFont

    pairs = SILK_FACE.get("widths", {}) if pairs is None else pairs
    f = TTFont(path, fontNumber=0, lazy=True)
    try:
        cmap = f.getBestCmap()
        hmtx = f["hmtx"]

        def adv(ch):
            gid = cmap.get(ord(ch))
            if gid is None:
                raise KeyError("the face has no glyph for %r" % ch)
            return hmtx[gid][0]

        out = {}
        for key in pairs:
            a, b = key.split("/")
            den = adv(b)
            out[key] = (adv(a) / den) if den else float("inf")
        return out
    finally:
        f.close()


def resolve():
    """(path, cap, note). `note` is None when the declared face was found;
    otherwise it is the line the build should print, loudly."""
    path, how = font_path()
    if path is None:
        return None, DEFAULT_CAP, (
            "*** THE CAD IS NOT LETTERED IN THE ORDERED FACE *** %r: %s.\n"
            "    Drawing in the CAD kernel's default face instead. The BOARD is "
            "unaffected -- this is the drawing, not the gerbers -- but the CAD no "
            "longer shows what the fab prints. Install the .otf (per-user is "
            "enough) or set WATERING_SILK_FONT_DIR. tools/check_silk_face.py fails "
            "while this is true." % (FAMILY, how))
    note = None
    if "FILENAME MATCH" in how:
        note = "[silk] %s resolved by FILENAME only (%s)" % (FAMILY, how)
    return path, cap_ratio(path), note
