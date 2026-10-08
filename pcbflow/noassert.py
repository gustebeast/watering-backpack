# -*- coding: utf-8 -*-
"""Importing this turns KiCad's assertion dialogs off. Import it beside pcbnew.

⚠ NO MODAL DIALOGS IN A BUILD STEP, and the rule is route.py's: "KiCad's Python is a
wxWidgets application, and a failed internal assertion pops a GUI alert -- 'Do you want
to stop the program?' -- and WAITS. On a developer's machine that is a surprise; in any
automated run it is a hang with no output and no exit code, and the whole point of this
directory is that someone can run it unattended years from now ... a pipeline that CAN
block on a dialog is a defect independent of which dialog it is."

route.py, layout.py and kicad_silk.py each said that and each called wx.DisableAsserts().
The other nine modules that load pcbnew did not, and one of those dialogs was found
sitting in front of a build -- pcb_track.cpp(387), PCB_VIA::GetWidth called without a
layer argument. So the call lives in ONE place now and every entry point imports it.

THIS DOES NOT HIDE A FAILURE. wxWidgets assertions are debug-build warnings about API
use; they do not stop the operation, they stop the OPERATOR. A real error still raises a
Python exception and still fails the step.
"""

try:
    import wx
except ImportError:                 # pragma: no cover
    # Not running inside KiCad's Python: there is no wx, so there is no dialog to
    # suppress. Stated rather than passed over, because a bare except around an import
    # is usually how a module stops doing its job silently.
    DISABLED = False
else:
    wx.DisableAsserts()
    DISABLED = True
