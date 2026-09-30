# -*- coding: utf-8 -*-
"""Shared FreeCAD live-viewer logic for CadQuery 3D-printing projects.

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

# How close two mtimes have to be to count as the same file. A rebuild moves an mtime by
# seconds, so this only ever absorbs REPRESENTATION loss -- and that loss was real: mtimes
# carry sub-microsecond digits on NTFS, and .status used to round them to 6 decimal places.
# Adoption then stamped the rounded value, it compared unequal to the true mtime, and every
# adopted tab RE-IMPORTED ITS STEP on the next tick -- exactly the 100 MB-per-tab cost that
# adopting from .status exists to avoid. Caught by running test_hub.py from a vendored copy,
# where the mtime happened to have digits the canonical checkout's did not.
_MTIME_EPS = 1e-6

# Fallback palette, used ONLY for assemblies whose STEP carries no colours.
PALETTE = [
    (0.85, 0.33, 0.31), (0.33, 0.55, 0.85), (0.46, 0.73, 0.40),
    (0.90, 0.67, 0.27), (0.60, 0.45, 0.75), (0.30, 0.72, 0.70),
    (0.88, 0.52, 0.72), (0.55, 0.58, 0.62), (0.72, 0.78, 0.35),
    (0.40, 0.62, 0.80), (0.82, 0.45, 0.40), (0.50, 0.70, 0.55),
]

# Hub state (module-level so the QTimer / shortcuts aren't garbage-collected).
_hub = {
    "inbox": None,     # directory polled for new projects to open as tabs
    "timer": None,
    "shortcuts": None,
    "heartbeat": None, # file the watch loop touches each tick (liveness signal)
}

# Transient per-tab state ONLY: the mtime/size stability check below. Losing it costs one
# extra poll and nothing else, which is why it may live in module memory while provenance
# (what a tab was loaded from) may NOT -- see _stamp_doc.
_pending = {}


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


# ── provenance: the DOCUMENT is the record, not a dict ──────────────────────
# The three Meta keys a tab carries. Namespaced because Meta is a shared, user-visible
# document property -- FreeCAD itself and other tools may put their own keys there.
_META_STEP = "cadkit_step"
_META_MTIME = "cadkit_mtime"
_META_SIZE = "cadkit_size"


def _stamp_doc(doc, step, mtime, size):
    """Record on the DOCUMENT what this tab was loaded from.

    ⚠ THIS REPLACES A MODULE-LEVEL DICT, AND THAT IS THE WHOLE POINT. The hub used to keep
    `_hub["projects"]` = name -> {step, mtime}, a second copy of the truth that drifted from
    it in BOTH directions: close a tab by hand and the dict still listed it, and reloading
    this module threw the dict away while every tab stayed open. A document that carries its
    own source cannot disagree with itself, a closed tab simply is NOT in
    App.listDocuments(), and -- the reason this had to come first -- NEW CODE CAN TAKE OVER
    RUNNING TABS WITHOUT RE-IMPORTING ONE OF THEM. That is what makes the code-update path
    (re-run the macro, reload this module) cheap enough to use instead of killing FreeCAD.

    ⚠ doc.Meta IS COPY-ON-READ: mutating what it hands back changes nothing, so the whole
    dict must be reassigned. Verified headlessly against FreeCAD 1.1.1 (freecadcmd), together
    with the fact that the keys survive a save/reopen -- which matters because these
    documents ARE saved, to a throwaway temp path (see _open_project)."""
    m = dict(doc.Meta or {})
    m[_META_STEP] = os.path.abspath(step)
    m[_META_MTIME] = repr(float(mtime))
    m[_META_SIZE] = str(int(size))
    doc.Meta = m


def _doc_prov(doc):
    """This tab's {step, mtime, size}, or None if it is not one of ours.

    Anything unparseable reads as NOT ours rather than raising: a hand-edited or
    foreign Meta must never be able to stop the watch loop."""
    try:
        m = doc.Meta or {}
        step = m.get(_META_STEP)
        if not step:
            return None
        return {"step": step,
                "mtime": float(m.get(_META_MTIME) or 0.0),
                "size": int(m.get(_META_SIZE) or -1)}
    except Exception:
        return None


def _tracked():
    """Every open document that carries our stamp: name -> provenance.

    This is the replacement for iterating `_hub["projects"]`. It is read from FreeCAD each
    time rather than cached, so a tab the user closed is gone the moment they close it and
    there is no bookkeeping to forget."""
    out = {}
    try:
        names = list(App.listDocuments().keys())
    except Exception:
        return out
    for name in names:
        doc = _get_doc(name)
        if doc is None:
            continue
        prov = _doc_prov(doc)
        if prov is not None:
            out[name] = prov
    return out


def _open_project(step):
    """Open `step` as a new document/tab. No-op if already open."""
    step = os.path.abspath(step)
    if not os.path.exists(step):
        return None
    name = _doc_name(step)
    doc = _get_doc(name)
    if doc is not None:
        # Already a tab. If it carries NO stamp it predates this code (or its Meta was
        # lost), so ADOPT it rather than opening a duplicate -- stamped with mtime 0 so the
        # watch loop sees it as out of date and refreshes it exactly once. Adopting is what
        # lets a hub that has been running for days pick up this change without the user
        # losing a single tab.
        if _doc_prov(doc) is None:
            _stamp_doc(doc, step, 0.0, -1)
            _write_status()
        return doc

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
    _stamp_doc(doc, step, os.path.getmtime(step), os.path.getsize(step))
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
    doc = _get_doc(name)
    if doc is None:
        _pending.pop(name, None)      # user closed the tab mid-poll
        return
    info = _doc_prov(doc)
    if info is None:
        return                        # not ours (any more)
    # Re-stat immediately before the import and stamp THOSE numbers afterwards, so the
    # recorded mtime is the one actually read rather than the one the caller measured a
    # tick earlier. A stamp that runs ahead of the bytes would skip the next rebuild.
    try:
        m, sz = os.path.getmtime(info["step"]), os.path.getsize(info["step"])
    except OSError:
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
    _stamp_doc(doc, info["step"], m, sz)

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
    """Open any projects queued by later launcher calls (one file per request).

    NEVER touches the window or the active tab. The hub used to be able to raise
    itself and switch to the requested tab, which meant a background rebuild could
    yank the user off whatever they were reading. That was narrowed once, to only
    fire for launcher-initiated opens, and is now GONE entirely (user): opening a
    tab and looking at a tab are separate things, and only the user does the
    second. The setActiveDocument calls that remain in _open_project /
    _reload_project are the opposite of this — they RESTORE the tab you were on
    after FreeCAD moves you off it, and removing them would reintroduce exactly
    the switching this deletes."""
    inbox = _hub["inbox"]
    if not inbox or not os.path.isdir(inbox):
        return
    for f in sorted(glob.glob(os.path.join(inbox, "*.txt"))):
        try:
            # utf-8-sig so a BOM (e.g. from PowerShell Set-Content) is stripped.
            step = (open(f, encoding="utf-8-sig").read().splitlines() or [""])[0].strip()
        except OSError:
            continue
        if step:
            # ⚠ RAISE BUSY AROUND THIS. Opening a project is a blocking STEP import on
            # FreeCAD's main thread, so it stops the heartbeat for as long as it takes --
            # 35 s for a 128 MB assembly, measured. Without the marker that is
            # indistinguishable from a wedged watcher, and a build landing in that window
            # acts on the misdiagnosis. It used to act by FORCE-KILLING the hub mid-import,
            # which is the crash this marker was introduced for; the reload path makes the
            # consequence milder, not correct. start_hub's initial open and _tick's reload
            # were already marked -- this was the one blocking load that was not.
            _write_busy("open " + os.path.basename(step))
            try:
                _open_project(step)
            finally:
                _clear_busy()
        try:
            os.remove(f)            # processed (or already open) — drop the request
        except OSError:
            pass


def _write_heartbeat():
    """Touch the heartbeat file so the build-side launcher can tell this watch
    loop is still ticking. A live process with a STALE heartbeat means the hub
    has wedged, and the launcher reloads it in place (see freecad_view._refresh_hub)."""
    path = _hub.get("heartbeat")
    if not path:
        return
    try:
        with open(path, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def _write_busy(what):
    """Raise a BUSY marker while the hub is inside a blocking load.

    The watch loop is a QTimer on FreeCAD's MAIN thread, so importing a big
    STEP stops it dead — a 40 s assembly means 40 s with no heartbeat, which
    is indistinguishable from a wedged watcher and got healthy hubs killed
    mid-reload (the launcher restarts anything stale). The marker says "not
    ticking ON PURPOSE, and since when"; freecad_view.show() honours it.
    Cleared in a finally, so a failed load can never leave it raised."""
    path = _hub.get("heartbeat")
    if not path:
        return
    try:
        with open(path + ".busy", "w") as f:
            f.write("%.6f %s" % (time.time(), what))
    except OSError:
        pass


def _clear_busy():
    path = _hub.get("heartbeat")
    if not path:
        return
    try:
        os.remove(path + ".busy")
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
            for name, info in _tracked().items():
                f.write("%s %s %s\n" % (name, repr(float(info["mtime"])), info["step"]))
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
    for name, info in _tracked().items():
        try:
            m = os.path.getmtime(info["step"])
            sz = os.path.getsize(info["step"])
        except OSError:
            continue
        if abs(m - info["mtime"]) <= _MTIME_EPS:
            _pending.pop(name, None)
            continue
        # A big STEP takes seconds to write; importing mid-write reads a
        # truncated file. Only reload once mtime+size have been STABLE for a
        # full tick, and only consume the mtime after the reload SUCCEEDS —
        # a failed attempt is retried on the next tick, never silently dropped.
        if _pending.get(name) != (m, sz):
            _pending[name] = (m, sz)
            continue
        try:
            _write_busy("reload " + name)
            try:
                _reload_project(name)   # stamps the new mtime itself, on success only
            finally:
                _clear_busy()
            _pending.pop(name, None)
            _write_status()
            App.Console.PrintMessage("[viewer] reloaded %s\n" % name)
        except Exception as e:
            _pending.pop(name, None)    # re-arm the stability check, then retry
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
def _adopt_from_status():
    """Re-adopt tabs an OLDER hub was watching, using the .status file it left behind.

    ⚠ WITHOUT THIS, UPDATING THE CODE SILENTLY ORPHANS EVERY OPEN TAB. A hub from before
    the provenance change has documents with no stamp, so _tracked() does not see them and
    the watch loop quietly stops following them -- the tab still looks fine and simply never
    refreshes again, which is the worst kind of failure this module can have. _open_project
    adopts a tab when a build next asks for that project, but that is LAZY: until then the
    user's open tabs are unwatched.

    .status is exactly the missing record -- the old hub wrote '<doc> <mtime> <step>' for
    every project it had loaded -- so a code update reconnects to its own tabs from it.

    Stamped with the mtime the OLD hub recorded, not 0: that hub really had loaded those
    bytes, so there is nothing to re-import. Re-importing instead would cost a 100 MB STEP
    reload per tab on every code update, for nothing."""
    path = _hub.get("heartbeat")
    if not path:
        return 0
    try:
        lines = open(path + ".status", encoding="utf-8").read().splitlines()
    except OSError:
        return 0
    n = 0
    for line in lines:
        parts = line.split(" ", 2)
        if len(parts) != 3:
            continue
        name, mtime, step = parts[0], parts[1], parts[2].strip()
        doc = _get_doc(name)
        if doc is None or _doc_prov(doc) is not None:
            continue                      # closed, or already carries its own record
        try:
            m = float(mtime)
        except ValueError:
            m = 0.0
        try:
            sz = os.path.getsize(step)
            disk = os.path.getmtime(step)
        except OSError:
            sz, disk = -1, None
        # Snap to the file's ACTUAL mtime when the recorded one is the same instant, so the
        # stamp is exact and the watch loop sees no change. Without this, any rounding in
        # .status costs a full re-import of every adopted tab.
        if disk is not None and abs(disk - m) <= _MTIME_EPS:
            m = disk
        _stamp_doc(doc, step, m, sz)
        n += 1
    if n:
        App.Console.PrintMessage("[viewer] adopted %d tab(s) from the previous hub\n" % n)
    return n


def shutdown():
    """Detach this module's live Qt objects so a RELOADED copy can take over cleanly.

    view.FCMacro calls this immediately before importlib.reload. Two things must go or the
    hub ends up with duplicates: the QTimer (two timers means two polls a second, and the
    OLD one goes on running OLD code -- which is exactly the bug the reload exists to fix),
    and the shortcuts (two QShortcut objects on one key sequence is ambiguous in Qt, and one
    of them silently wins).

    ⚠ NOTHING ELSE NEEDS UNDOING, AND THAT IS THE POINT OF THE PROVENANCE CHANGE. The tabs
    stay open and carry their own source path, so a reload re-imports no geometry and the
    user loses no camera, no hidden parts and no tab. Before documents were self-describing
    this call would have had to be a restart.

    Never raises: a half-detached hub is strictly worse than a stale object."""
    t = _hub.get("timer")
    if t is not None:
        try:
            t.stop()
        except Exception:
            pass
    _hub["timer"] = None
    for sc in (_hub.get("shortcuts") or []):
        try:
            sc.setEnabled(False)
            sc.setParent(None)      # drop it off the main window, not just disable it
        except Exception:
            pass
    _hub["shortcuts"] = None


def code_stamp():
    """A hash of the code the hub RUNS: this module plus the macro that loads it.

    Both matter and both are now fixable in place. Re-running view.FCMacro through
    FreeCAD's --single-instance executes the macro FROM DISK (so macro edits land) and the
    macro reloads this module (so viewer edits land). One mechanism, no restart, no kill --
    which is why the launcher compares this stamp instead of owning a process id.

    Hashes CONTENT, never mtime: propagating cadkit rewrites every vendored file, so
    identical bytes get a fresh mtime. Comparing timestamps once read as "stale" and killed
    a healthy hub, taking every open tab with it (user, 2026-09-07)."""
    import hashlib
    h = hashlib.sha1()
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("freecad_viewer.py", "view.FCMacro"):
        try:
            with open(os.path.join(here, name), "rb") as f:
                h.update(f.read())
        except OSError:
            pass
    return h.hexdigest()


def start_hub(inbox_dir=None, initial_step=None):
    """Start (or top up) the hub: open the initial project, drain the inbox,
    and begin watching every open project for rebuilds."""
    if inbox_dir:
        _hub["inbox"] = os.path.abspath(inbox_dir)
    _hub["heartbeat"] = (os.environ.get("FREECAD_VIEW_HEARTBEAT")
                         or os.path.join(tempfile.gettempdir(), "freecad_viewer_hub.heartbeat"))
    # Stamp the code THIS process is running. FreeCAD executes the macro once, at launch,
    # and keeps the imported viewer module in memory -- so editing either changes nothing
    # for a hub that is already up. That bit us: a hub from the 28th went on raising its
    # window for two days after the behaviour was narrowed and then deleted, because
    # neither version ever ran.
    # The launcher compares this stamp against code_stamp() on disk. It used to answer a
    # mismatch by KILLING the process; it now answers by re-running the macro through
    # --single-instance, which reloads this module in place (see view.FCMacro). Same
    # detection, no force-kill, no lost tabs.
    try:
        with open(_hub["heartbeat"] + ".codestamp", "w") as _f:
            _f.write(code_stamp())
    except Exception:
        pass
    _write_heartbeat()   # stamp immediately so the launcher sees a live hub at once
    # Reconnect to tabs a previous hub was watching BEFORE anything else looks at the
    # tracked set, so a code reload never leaves an open tab unwatched.
    _adopt_from_status()

    App.ParamGet("User parameter:BaseApp/Preferences/View").SetInt("AntiAliasing", 3)
    # Read-only viewer: turn off FreeCAD's auto-recovery so an unclean exit
    # (force-kill, crash, reboot) never nags with the Document Recovery dialog.
    # The tabs are disposable STEP imports — there's nothing to recover.
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetBool("AutoSaveEnabled", False)

    if initial_step:
        _write_busy("open " + os.path.basename(initial_step))
        try:
            _open_project(initial_step)
        finally:
            _clear_busy()
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
        % (len(_tracked()), _hub["inbox"])
    )


def start(step_path):
    """Backwards-compatible single-project entry (delegates to the hub)."""
    start_hub(inbox_dir=os.environ.get("FREECAD_VIEW_INBOX") or None,
              initial_step=step_path)
