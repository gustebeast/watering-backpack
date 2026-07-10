# -*- coding: utf-8 -*-
"""Shared FreeCAD live-viewer logic for all the Archive/3D CadQuery projects.

Single-window / tabbed model: ONE FreeCAD instance (the "hub") holds every
project as its own document, which FreeCAD shows as a tab in the 3D area. Each
project's STEP file is watched independently and reloaded on rebuild, preserving
that tab's camera and hidden parts. The build writing the STEP file IS the
refresh signal.

Later launches don't open new windows — they drop the project's STEP path into
an inbox directory that the hub polls, so the project appears as a new tab in
the existing window. See open_viewer.ps1.

Per project the only thing that differs is the STEP path; nothing here is
project-specific. Parts are imported as named, individually show/hide-able
solids; colours baked into the STEP (see cq_colors.py / README) are respected,
otherwise a fallback palette is applied so the model still reads apart.

Hotkeys (act on the active tab): I = isolate selected part(s), Shift+I = show all.
"""

import os
import glob
import time
import tempfile
import FreeCAD as App
import FreeCADGui as Gui
import ImportGui  # GUI importer — applies STEP-embedded colours (Import does not)
from PySide import QtCore, QtGui

# QShortcut lives in QtWidgets on Qt5/PySide2, QtGui on older shims.
try:
    from PySide import QtWidgets
    _QShortcut = QtWidgets.QShortcut
except Exception:  # pragma: no cover
    _QShortcut = QtGui.QShortcut

POLL_MS = 1000

# Fallback palette, used ONLY for assemblies whose STEP carries no colours.
PALETTE = [
    (0.85, 0.33, 0.31), (0.33, 0.55, 0.85), (0.46, 0.73, 0.40),
    (0.90, 0.67, 0.27), (0.60, 0.45, 0.75), (0.30, 0.72, 0.70),
    (0.88, 0.52, 0.72), (0.55, 0.58, 0.62), (0.72, 0.78, 0.35),
    (0.40, 0.62, 0.80), (0.82, 0.45, 0.40), (0.50, 0.70, 0.55),
]

# Hub state (module-level so the QTimer / shortcuts aren't garbage-collected).
_hub = {
    "projects": {},    # doc_name -> {"step": path, "mtime": float}
    "inbox": None,     # directory polled for new projects to open as tabs
    "timer": None,
    "shortcuts": None,
    "heartbeat": None, # file the watch loop touches each tick (liveness signal)
}


# ── colours ────────────────────────────────────────────────────────────────
def _default_shape_color():
    """FreeCAD's configured default shape colour (what an uncoloured STEP part
    lands on). Read from prefs so it tracks the user's theme, not hard-coded."""
    packed = App.ParamGet(
        "User parameter:BaseApp/Preferences/View"
    ).GetUnsigned("DefaultShapeColor", 0xCCCCCCFF)
    return (((packed >> 24) & 0xFF) / 255.0,
            ((packed >> 16) & 0xFF) / 255.0,
            ((packed >> 8) & 0xFF) / 255.0)


def _colorize(doc):
    """Respect colours baked into the STEP; only fall back to the palette for
    assemblies that carry NO colours at all (see README for the rationale)."""
    default = _default_shape_color()

    def is_default(c):
        return (abs(c[0] - default[0]) < 0.02
                and abs(c[1] - default[1]) < 0.02
                and abs(c[2] - default[2]) < 0.02)

    features = [o for o in doc.Objects
                if o.TypeId == "Part::Feature"
                and getattr(o, "ViewObject", None) is not None
                and hasattr(o.ViewObject, "ShapeColor")]

    if any(not is_default(o.ViewObject.ShapeColor) for o in features):
        return  # STEP colours are the source of truth — don't touch anything
    for i, o in enumerate(features):
        o.ViewObject.ShapeColor = PALETTE[i % len(PALETTE)]


# ── documents / tabs ─────────────────────────────────────────────────────────
def _doc_name(step_path):
    """Stable per-project document name derived from the project folder."""
    parent = os.path.basename(os.path.dirname(os.path.abspath(step_path)))
    safe = "".join(c if c.isalnum() else "_" for c in parent) or "viewer"
    return safe + "_viewer"


def _doc_view(name):
    gdoc = Gui.getDocument(name)
    return gdoc.ActiveView if gdoc else None


def _import_into(doc, step):
    """Replace a document's contents with a fresh import of `step`, keeping each
    part a separate named solid and applying colour rules."""
    App.ParamGet(
        "User parameter:BaseApp/Preferences/Mod/Part/STEP"
    ).SetBool("ReadShapeCompoundMode", False)
    # Remove by name, re-checking existence each time: deleting a parent (e.g. an
    # App::Part group and its Origin children) cascades, so a captured object ref
    # can already be dead by the time we reach it.
    for name in [o.Name for o in doc.Objects]:
        if doc.getObject(name) is not None:
            doc.removeObject(name)
    ImportGui.insert(step, doc.Name)
    doc.recompute()
    _colorize(doc)


def _get_doc(name):
    """App.getDocument(name) but returns None if the document is closed
    (FreeCAD raises NameError in that case, which is the real-world signal
    that the user closed the tab)."""
    try:
        return App.getDocument(name)
    except NameError:
        return None


def _open_project(step):
    """Open `step` as a new document/tab. No-op if already open."""
    step = os.path.abspath(step)
    if not os.path.exists(step):
        return None
    name = _doc_name(step)
    if name in _hub["projects"]:
        doc = _get_doc(name)
        if doc is not None:
            return doc
        # User closed the tab — drop the stale entry and fall through to reopen.
        _hub["projects"].pop(name, None)

    prev = App.ActiveDocument  # so opening a tab during a background poll...
    doc = App.newDocument(name)            # ...becomes active here (new tab)
    # FreeCAD 1.1's STEP importer (ImportGui.insert) pops a modal "Save As" dialog when the target doc
    # has never been saved -- which wedges the hub on every build. Give the (empty) doc a throwaway
    # FileName in temp up front: the save is instant, the import then runs silently, and auto-save is off
    # so this file is never rewritten. The tab still shows normally; it's just associated with a path.
    try:
        doc.saveAs(os.path.join(tempfile.gettempdir(), name + ".FCStd"))
    except Exception:
        pass
    _import_into(doc, step)
    _hub["projects"][name] = {"step": step, "mtime": os.path.getmtime(step)}
    _write_status()

    view = _doc_view(name)
    if view is not None:
        view.viewIsometric()
        Gui.SendMsgToActiveView("ViewFit")
    # A brand-new tab is fine to leave focused; but if this open happened while
    # the user was on another tab during a poll, don't yank them away.
    if prev is not None and prev.Name != name:
        App.setActiveDocument(prev.Name)
    return doc


def _reload_project(name):
    """Re-import a tracked project's STEP, preserving its tab's camera + hidden
    parts and without stealing the user's currently-focused tab."""
    info = _hub["projects"].get(name)
    if info is None:
        return
    doc = _get_doc(name)
    if doc is None:
        _hub["projects"].pop(name, None)
        return

    hidden = {o.Label for o in doc.Objects
              if getattr(o, "ViewObject", None) is not None
              and not o.ViewObject.Visibility}
    view = _doc_view(name)
    cam = None
    if view is not None:
        try:
            cam = view.getCamera()
        except Exception:
            cam = None

    prev = App.ActiveDocument
    _import_into(doc, step=info["step"])

    for o in doc.Objects:
        if o.Label in hidden and getattr(o, "ViewObject", None) is not None:
            o.ViewObject.Visibility = False

    view = _doc_view(name)
    if view is not None and cam is not None:
        try:
            view.setCamera(cam)
        except Exception:
            pass
    if prev is not None and _get_doc(prev.Name) is not None:
        App.setActiveDocument(prev.Name)


def _scan_inbox():
    """Open any projects queued by later launcher calls (one file per request)."""
    inbox = _hub["inbox"]
    if not inbox or not os.path.isdir(inbox):
        return
    for f in sorted(glob.glob(os.path.join(inbox, "*.txt"))):
        try:
            # utf-8-sig so a BOM (e.g. from PowerShell Set-Content) is stripped.
            step = open(f, encoding="utf-8-sig").read().strip()
        except OSError:
            continue
        if step:
            _open_project(step)
        try:
            os.remove(f)            # processed (or already open) — drop the request
        except OSError:
            pass


def _write_heartbeat():
    """Touch the heartbeat file so the build-side launcher can tell this watch
    loop is still ticking. A live process with a STALE heartbeat means the hub
    has wedged, and the launcher will restart it (see freecad_view._kill_hub)."""
    path = _hub.get("heartbeat")
    if not path:
        return
    try:
        with open(path, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def _write_status():
    """Write a per-project '<doc> <loaded_mtime>' status file next to the
    heartbeat, AFTER each successful (re)load — lets the build side verify the
    tab actually shows the file on disk (a live heartbeat only proves the
    watcher ticks, not that reloads succeed)."""
    path = _hub.get("heartbeat")
    if not path:
        return
    try:
        with open(path + ".status", "w") as f:
            for name, info in _hub["projects"].items():
                f.write("%s %.6f %s\n" % (name, info["mtime"], info["step"]))
    except OSError:
        pass


def _tick():
    # Heartbeat FIRST and unconditionally: it must keep refreshing even if a
    # reload below throws, so a transient import error never looks like a dead
    # hub. Everything else is wrapped so one bad tick can't stop the timer.
    _write_heartbeat()
    try:
        _scan_inbox()
    except Exception as e:
        App.Console.PrintError("[viewer] inbox scan failed: %s\n" % e)
    for name, info in list(_hub["projects"].items()):
        try:
            m = os.path.getmtime(info["step"])
            sz = os.path.getsize(info["step"])
        except OSError:
            continue
        if m == info["mtime"]:
            info.pop("pending", None)
            continue
        # A big STEP takes seconds to write; importing mid-write reads a
        # truncated file. Only reload once mtime+size have been STABLE for a
        # full tick, and only consume the mtime after the reload SUCCEEDS —
        # a failed attempt is retried on the next tick, never silently dropped.
        if info.get("pending") != (m, sz):
            info["pending"] = (m, sz)
            continue
        try:
            _reload_project(name)
            info["mtime"] = m
            info.pop("pending", None)
            _write_status()
            App.Console.PrintMessage("[viewer] reloaded %s\n" % name)
        except Exception as e:
            info.pop("pending", None)   # re-arm the stability check, then retry
            App.Console.PrintError("[viewer] reload %s failed (will retry): %s\n"
                                   % (name, e))


# ── isolate / show-all hotkeys (act on the active tab) ───────────────────────
def _viewer_doc():
    return App.activeDocument()


def _isolate():
    doc = _viewer_doc()
    if doc is None:
        return
    keep = {o.Name for o in Gui.Selection.getSelection()
            if getattr(o, "Document", None) is doc}
    if not keep:
        return
    for o in doc.Objects:
        if o.TypeId == "Part::Feature" and getattr(o, "ViewObject", None) is not None:
            o.ViewObject.Visibility = (o.Name in keep)


def _show_all():
    doc = _viewer_doc()
    if doc is None:
        return
    for o in doc.Objects:
        if o.TypeId == "Part::Feature" and getattr(o, "ViewObject", None) is not None:
            o.ViewObject.Visibility = True


def _measure():
    """Launch FreeCAD's unified Measure tool (point/edge/plane distances)."""
    try:
        Gui.runCommand("Std_Measure")
    except Exception:
        pass


def _install_shortcuts():
    mw = Gui.getMainWindow()
    if mw is None or _hub.get("shortcuts"):
        return
    shortcuts = []
    for keys, fn in (("I", _isolate), ("Shift+I", _show_all), ("M", _measure)):
        sc = _QShortcut(QtGui.QKeySequence(keys), mw)
        sc.setContext(QtCore.Qt.ApplicationShortcut)
        sc.activated.connect(fn)
        shortcuts.append(sc)
    _hub["shortcuts"] = shortcuts


# ── entry points ─────────────────────────────────────────────────────────────
def start_hub(inbox_dir=None, initial_step=None):
    """Start (or top up) the hub: open the initial project, drain the inbox,
    and begin watching every open project for rebuilds."""
    if inbox_dir:
        _hub["inbox"] = os.path.abspath(inbox_dir)
    _hub["heartbeat"] = (os.environ.get("FREECAD_VIEW_HEARTBEAT")
                         or os.path.join(tempfile.gettempdir(), "freecad_viewer_hub.heartbeat"))
    _write_heartbeat()   # stamp immediately so the launcher sees a live hub at once

    App.ParamGet("User parameter:BaseApp/Preferences/View").SetInt("AntiAliasing", 3)
    # Read-only viewer: turn off FreeCAD's auto-recovery so an unclean exit
    # (force-kill, crash, reboot) never nags with the Document Recovery dialog.
    # The tabs are disposable STEP imports — there's nothing to recover.
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetBool("AutoSaveEnabled", False)

    if initial_step:
        _open_project(initial_step)
    _scan_inbox()

    if _hub["timer"] is None:
        timer = QtCore.QTimer()
        timer.timeout.connect(_tick)
        timer.start(POLL_MS)
        _hub["timer"] = timer

    _install_shortcuts()
    App.Console.PrintMessage(
        "[viewer] hub watching %d project(s), inbox=%s  "
        "[I = isolate, Shift+I = show all, M = measure]\n"
        % (len(_hub["projects"]), _hub["inbox"])
    )


def start(step_path):
    """Backwards-compatible single-project entry (delegates to the hub)."""
    start_hub(inbox_dir=os.environ.get("FREECAD_VIEW_INBOX") or None,
              initial_step=step_path)
