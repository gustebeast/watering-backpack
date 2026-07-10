# -*- coding: utf-8 -*-
"""Project-facing entry point: "here's my STEP, make sure it's viewable."

A build script calls exactly one verb:

    from cadkit.freecad import show
    ...
    show(str(OUT / "assembly.step"))     # at the end of the build

and this module handles everything on the outside (CPython) side:

  - hub window already running?  -> hand it this project to open as a tab
                                    (a no-op if that project is already a tab)
  - hub not running?             -> launch FreeCAD and open this as the first tab

Whether the tab then needs *updating* is decided automatically inside FreeCAD by
the hub's file-watcher (freecad_viewer.py): a rebuilt STEP reloads its own tab.
So a project never reasons about windows, tabs, or refreshes — there is one verb.

`show()` never raises: viewer trouble must never break a build.
"""

import os
import sys
import glob
import time
import uuid
import shutil
import tempfile
import subprocess

# FreeCAD is resolved PER-MACHINE (never committed): explicit arg > FREECAD_EXE env >
# cached config file > auto-discovery (cached on first success). This keeps the repo
# portable — pull it on a fresh machine and the first show() finds FreeCAD and remembers
# where it is; a machine without FreeCAD gets a clear "go install it" message. See
# _freecad_exe / _discover_freecad / the --set-path CLI.
FREECAD_DOWNLOAD_URL = "https://www.freecad.org/downloads.php"

_HERE = os.path.dirname(os.path.abspath(__file__))
_MACRO = os.path.join(_HERE, "view.FCMacro")
_MARKER = os.path.join(tempfile.gettempdir(), "freecad_viewer_hub.pid")
_INBOX = os.path.join(tempfile.gettempdir(), "freecad_viewer_inbox")
_HEARTBEAT = os.path.join(tempfile.gettempdir(), "freecad_viewer_hub.heartbeat")
# The hub's watch loop refreshes the heartbeat every poll (~1 s). If the process
# is alive but the heartbeat is older than this, the watcher has wedged (timer
# stopped, interpreter reset, …) and would silently ignore rebuilds — so the hub
# is restarted. Generous vs both the poll period and FreeCAD's cold-boot time, so
# a healthy-but-busy hub is never killed by mistake.
_HEARTBEAT_STALE_S = 30.0


def _config_path():
    """Per-user cadkit config file holding the FreeCAD executable path — machine-local,
    OUTSIDE any repo (so it's never committed). %APPDATA%\\cadkit on Windows,
    $XDG_CONFIG_HOME (or ~/.config) elsewhere."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "cadkit", "freecad.path")


def _read_config():
    try:
        p = open(_config_path(), encoding="utf-8").read().strip()
        return p or None
    except OSError:
        return None


def _write_config(exe):
    """Remember the resolved FreeCAD path so later runs skip discovery. Never raises."""
    try:
        cfg = _config_path()
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
        with open(cfg, "w", encoding="utf-8") as f:
            f.write(exe)
    except OSError:
        pass


def _discover_freecad():
    """Best-effort search of the usual install locations for this OS. Returns an existing
    executable path (highest version first), or None. Never raises."""
    cands = []
    if os.name == "nt":
        roots = [os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(os.path.join(local, "Programs"))
        for root in roots:
            if root:
                cands += sorted(glob.glob(os.path.join(root, "FreeCAD*", "bin", "freecad.exe")),
                                reverse=True)
    elif sys.platform == "darwin":
        cands += sorted(glob.glob("/Applications/FreeCAD*.app/Contents/MacOS/FreeCAD"), reverse=True)
        cands += sorted(glob.glob(os.path.expanduser(
            "~/Applications/FreeCAD*.app/Contents/MacOS/FreeCAD")), reverse=True)
    else:  # linux / other unix
        cands += sorted(glob.glob(os.path.expanduser("~/Applications/FreeCAD*.AppImage")), reverse=True)
        cands += ["/usr/bin/freecad", "/usr/local/bin/freecad"]
    for name in ("freecad", "freecadcmd", "FreeCAD"):
        w = shutil.which(name)
        if w:
            cands.append(w)
    for exe in cands:
        if exe and os.path.exists(exe):
            return exe
    return None


def _freecad_exe(override=None):
    """Resolve the FreeCAD executable, or None if it can't be found (cascade above)."""
    if override:
        return override
    env = os.environ.get("FREECAD_EXE")
    if env:
        return env
    cached = _read_config()
    if cached and os.path.exists(cached):
        return cached
    found = _discover_freecad()
    if found:
        _write_config(found)          # cache it — instant next time
    return found


def _hub_running():
    """Return True if the marker points at a live freecad process. The image-name
    check guards against a recycled PID now belonging to some other program."""
    try:
        pid = int(open(_MARKER).read().strip())
    except (OSError, ValueError):
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "PID eq %d" % pid, "/NH", "/FO", "CSV"],
            capture_output=True, text=True, timeout=10).stdout.lower()
    except Exception:
        return False
    return ("freecad" in out) and (str(pid) in out)


def _heartbeat_age():
    """Seconds since the hub last ticked, or None if there is no heartbeat file."""
    try:
        return max(0.0, time.time() - os.path.getmtime(_HEARTBEAT))
    except OSError:
        return None


def _kill_hub():
    """Force a wedged hub process down and clear its markers so the next launch
    starts a clean one. Never raises."""
    try:
        pid = int(open(_MARKER).read().strip())
    except (OSError, ValueError):
        pid = None
    if pid is not None:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                               capture_output=True, timeout=10)
            else:
                os.kill(pid, 9)
        except Exception:
            pass
    for p in (_MARKER, _HEARTBEAT):
        try:
            os.remove(p)
        except OSError:
            pass


def _resolve_step(step_path=None, project=None):
    """Absolute STEP path. With no explicit step, look in the project folder:
    prefer assembly.step, else the single top-level *.step."""
    if step_path:
        return os.path.abspath(step_path)
    proj = os.path.abspath(project or os.getcwd())
    cand = os.path.join(proj, "assembly.step")
    if os.path.exists(cand):
        return cand
    steps = glob.glob(os.path.join(proj, "*.step"))
    if len(steps) == 1:
        return steps[0]
    if not steps:
        raise FileNotFoundError("no .step in %s - build it first or pass a step path" % proj)
    raise ValueError("multiple .step files in %s - pass an explicit step path" % proj)


def show(step_path=None, project=None, freecad_exe=None):
    """Make a STEP viewable in the shared FreeCAD hub (open a tab, launching the
    hub window first if needed). Returns True if a viewer is up/queued, False on
    any handled problem. Never raises."""
    try:
        step = _resolve_step(step_path, project)
        if not os.path.exists(step):
            print("[freecad] %s not found - skipping viewer" % step, file=sys.stderr)
            return False
        os.makedirs(_INBOX, exist_ok=True)

        if _hub_running():
            age = _heartbeat_age()
            if age is not None and age <= _HEARTBEAT_STALE_S:
                # Hub alive and ticking — hand it the project as a tab. One file
                # per request (unique name) so concurrent builds never clobber
                # each other; the hub opens it, or ignores it if that project is
                # already a tab, then deletes it.
                req = os.path.join(_INBOX, uuid.uuid4().hex + ".txt")
                with open(req, "w", encoding="utf-8") as f:
                    f.write(step)
                return True
            # Process is alive but its watch loop has stopped (stale/absent
            # heartbeat): dropped requests would pile up unseen — the exact bug
            # this guards against. Tear it down and relaunch a working one.
            why = "no heartbeat" if age is None else "%.0fs since last tick" % age
            print("[freecad] hub watcher unresponsive (%s) - restarting viewer" % why,
                  file=sys.stderr)
            _kill_hub()

        # No (working) hub: start one. Clear stale requests so a previous session's
        # tabs don't resurrect, then launch FreeCAD with this project as the first tab.
        for f in glob.glob(os.path.join(_INBOX, "*.txt")):
            try:
                os.remove(f)
            except OSError:
                pass
        exe = _freecad_exe(freecad_exe)
        if not exe or not os.path.exists(exe):
            print("[freecad] FreeCAD not found. Install it from %s, then point cadkit at it once:\n"
                  "          py -m cadkit.freecad --set-path \"<path to the freecad executable>\"\n"
                  "          (or set the FREECAD_EXE environment variable). Skipping viewer."
                  % FREECAD_DOWNLOAD_URL, file=sys.stderr)
            return False
        env = dict(os.environ, FREECAD_VIEW_STEP=step, FREECAD_VIEW_INBOX=_INBOX,
                   FREECAD_VIEW_HEARTBEAT=_HEARTBEAT, FREECAD_VIEW_MACRO_DIR=_HERE)
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen([exe, _MACRO], env=env, close_fds=True, creationflags=flags)
        with open(_MARKER, "w") as f:
            f.write(str(proc.pid))
        # Stamp an initial heartbeat so a build that lands during FreeCAD's boot
        # doesn't mistake the not-yet-ticking hub for a wedged one; the hub takes
        # over refreshing it once its watch loop starts.
        try:
            with open(_HEARTBEAT, "w") as f:
                f.write(str(time.time()))
        except OSError:
            pass
        return True
    except Exception as e:                                   # never break a build
        print("[freecad] viewer skipped: %s" % e, file=sys.stderr)
        return False


def _cli(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="cadkit.freecad",
        description="Make a project's STEP viewable in the shared FreeCAD hub.")
    ap.add_argument("--project", help="project folder (default: current directory)")
    ap.add_argument("--step", help="explicit STEP file (overrides --project)")
    ap.add_argument("--freecad", help="path to the FreeCAD executable (this run only)")
    ap.add_argument("--set-path", metavar="EXE",
                    help="save the FreeCAD executable path to the cadkit config and exit")
    a = ap.parse_args(argv)
    if a.set_path:
        exe = os.path.abspath(os.path.expanduser(a.set_path))
        if not os.path.exists(exe):
            print("warning: %s does not exist (saving anyway)" % exe, file=sys.stderr)
        _write_config(exe)
        print("saved FreeCAD path -> %s" % _config_path())
        return 0
    return 0 if show(step_path=a.step, project=a.project, freecad_exe=a.freecad) else 1


if __name__ == "__main__":
    sys.exit(_cli())
