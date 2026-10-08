"""This board's lettering: the face, and what it is allowed to print.

    "C:/Program Files/KiCad/10.0/bin/python.exe" elec/silk.py elec/out/main

The labeller itself is cadkit's (`cadkit/kicad_silk.py` — what it prints, where it puts
it, and why no label may be invented). `finish.py` picks this file up automatically,
because a project's own `silk.py` beats the shared default (see finish.py's `_step`).
All this file supplies is the FACE and the characters it has been checked for.

⚠ THE LETTERING IS "Rennie Mackintosh PSG" Bold (owner, 2026-10-08) — ITC's Rennie
Mackintosh Bold with its ornamental underscore redrawn as a bar. The same face the
public-steel-guitar boards are lettered in, and deliberately the same file: the owner
supplied it from that project's `elec/fonts/` and installed it per-user.

The .otf is LICENSED. It is not in this repository and must not be committed; it has to
be INSTALLED for a build to produce the boards as ordered. Installed per-user is enough
(right-click → Install), and it resolves as the family name below.

WITHOUT IT ("fallback" is on): the board still finishes, lettered in KiCad's own stroke
font at the stroke font's sizes, and the run SAYS SO loudly. That is a correct board but
not the ordered one — labels land elsewhere and size differently, and a
`quality.connector_labels` declaration worded for this face may then read as stale.

1.5 IS MEASURED ON THIS FONT ON THIS MACHINE, NOT CHOSEN, and not inherited from the
steel guitar either — the glyph ink was rendered through pcbnew's
TransformTextToPolySet and measured:

    size   cap height   thinnest ink (the bar of '_')
    1.4    1.308 mm     0.1431 mm   FAILS JLCPCB's 0.15 mm floor
    1.5    1.401 mm     0.1533 mm   clears it, by 0.0033 mm

So 1.5 is the SMALLEST size this face can be lettered at here, and there is no smaller
size to fall back to. `_` is the thinnest glyph and this board's labels are full of it
(VBAT_RAW, PUMP_A_LO, ESP_TX_TO_PROG); the next thinnest is `I` at 0.1701 mm. That the
measurement lands on the steel guitar's own 0.153 mm is corroboration, not the source.

⚠ WHAT IT MAY PRINT, AND WHY THAT NEEDS DECLARING (quality A19). This is a DISPLAY face:
ITC drew "+" as a TH ligature and "=" as TT, with ornaments on most of the lower case —
so "+5V" has plotted, legibly and at full size, as "TH5V" on real boards while every
check passed, because the text object still said "+5V". A character table cannot see
that. Only someone looking at the drawn glyph can. The PSG file redraws "+" and "_"
plain, which is the whole reason it exists as a separate file.

`glyphs` is therefore the set LOOKED AT in this file, and its provenance is mixed, which
is worth stating rather than glossing:
  * the list is public-steel-guitar's own, checked visually by its owner in this exact
    file — and `widths` below proves the installed file IS that one;
  * additionally, all 37 characters THIS board's silk currently uses
    ("+0123456789ABCDEFGIJLMNOPQRSTUVWXYZ_r" plus space, measured off the routed board)
    were rendered here and every one produces non-empty ink.
A label needing any character outside the list stops the run rather than printing an
ornament nobody looked at.

`widths` is the file-version proof. A face that had a glyph redrawn keeps its family
name, so a machine carrying the ORIGINAL ITC file still resolves "Rennie Mackintosh PSG"
and still prints the TH ligature. The advance of "+" as a fraction of "H" is 0.97 in the
checked file and 1.42 in the one it replaces. Measured here: 0.966.
⚠ A MONOSPACE FACE WOULD MAKE THIS PROOF USELESS — every advance ratio would be 1.00 —
which is worth knowing before anyone swaps the face for a mono one.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cadkit import kicad_silk  # noqa: E402

REV = "r1"                 # bumped by hand when a board is RE-ORDERED with changed copper

SILK_FACE = {"family": "Rennie Mackintosh PSG", "bold": True, "size": 1.5,
             "fallback": True,
             "glyphs": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789r+_-/.()#%:,",
             "widths": {"+/H": 0.97}}


def silk(stem):
    try:
        with open(stem + ".board.json", encoding="utf-8") as fh:
            notes = json.load(fh)
    except OSError:
        notes = {}
    return kicad_silk.silk(stem, REV, tuple(notes.get("strip_silk", ())),
                           face=notes.get("silk_font", SILK_FACE))


if __name__ == "__main__":
    # one board per process -- see cadkit.kicad_silk.main
    _stems = [a[:-10] if a.endswith(".kicad_pcb") else a for a in sys.argv[1:]]
    for _stem in _stems:
        silk(_stem)
