"""cadkit.web -- the assembly viewer: a web page, not an application.

    from cadkit.web import show
    show(parts)                  # [(name, solid, colour)], or the path of an assembly STEP

opens the project's model in a browser tab and keeps that tab current: each later
`show()` (or scratch render) is picked up by the open page, which reloads the model and
keeps the camera and whatever is hidden. `show()` never raises -- viewer trouble cannot
break a build.

What the page does: orbit, select / hide / isolate (with undo), a parts list, a section
cut, axis views, and a MEASURE tool that reads the kernel's own numbers (distance,
angle, radius, between corners, edges, axes and faces) rather than fitting triangles.
Shadows and occlusion follow what is shown, and step down by themselves on a device
that cannot hold 60 fps. A project with circuit boards gets real part models on them;
one that names its filaments gets an as-printed view; one that writes a rig file gets
its mechanism animated.

    export   mesh parts into assembly.glb + assembly.geo.json (page=True adds the page,
             which makes the folder a publishable web site)
    show     export into <project>/.webview/ and serve it locally (show_exported: a
             folder export() already wrote, without meshing it again)
    view     the local server, and the scratch loop's export
    boards   real part models on circuit boards (KiCad's library, or parts drawn here)
    parts    the parts KiCad has no model for, drawn from footprint and datasheet
"""

from .export import (ANGULAR, FORMAT, PAGE, TOLERANCE, export, mesh_shape, pieces,
                     rig_names, silk_units, step_parts, write_glb)
from .view import (PORT, ensure_server, scratch_export, scratch_show, serve, show,
                   show_exported)

__all__ = ["show", "show_exported", "export", "scratch_show", "scratch_export", "serve", "ensure_server",
           "mesh_shape", "pieces", "write_glb", "step_parts", "rig_names", "silk_units",
           "PAGE", "PORT", "TOLERANCE", "ANGULAR", "FORMAT"]
