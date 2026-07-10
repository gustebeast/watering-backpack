"""`python -m cadkit.freecad ...` -> the viewer CLI (opens a STEP; also handles --set-path)."""
import sys

from .freecad_view import _cli

sys.exit(_cli())
