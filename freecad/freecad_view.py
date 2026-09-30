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
# ⚠ THERE IS NO PID FILE ANY MORE, AND NOTHING HERE FORCE-KILLS FREECAD.
# The hub used to record its process id so the launcher could taskkill /F /T a hub whose
# watch loop had stopped. That answered exactly one question -- "which process do I kill" --
# and the kill itself became the worst bug in the viewer: a big STEP import blocks the
# QTimer, so a healthy hub mid-reload looked wedged and got destroyed BY THE BUILD THAT
# ASKED FOR THE REFRESH, taking every open tab with it. The .busy marker stopped the
# misdiagnosis; this removes the weapon.
# What each question is actually answered by now:
#     is our watcher alive?          .heartbeat freshness
#     is it mid-load, not wedged?    .busy
#     is my tab there and current?   .status
#     open a new tab                 a request in the inbox
#     is new code in the hub yet?    .codestamp vs code_stamp() on disk
#     a wedged or stale hub          RE-RUN THE MACRO (--single-instance), in place
# A FreeCAD holding someone's unsaved work is theirs to close, not ours to kill.
_INBOX = os.path.join(tempfile.gettempdir(), "freecad_viewer_inbox")
_HEARTBEAT = os.path.join(tempfile.gettempdir(), "freecad_viewer_hub.heartbeat")
# The hub's watch loop refreshes the heartbeat every poll (~1 s). If the process
# is alive but the heartbeat is older than this, the watcher has wedged (timer
# stopped, interpreter reset, …) and would silently ignore rebuilds — so the hub
# is restarted. Generous vs both the poll period and FreeCAD's cold-boot time, so
# a healthy-but-busy hub is never killed by mistake.
_HEARTBEAT_STALE_S = 30.0
# …unless the hub has told us it is inside a blocking load (freecad_viewer's
# BUSY marker). The watch loop is a QTimer on FreeCAD's main thread, so a big
# STEP import stops the heartbeat for as long as it takes — on a large
# assembly that is comfortably past the staleness limit, and the hub was
# being killed MID-RELOAD by the very build that asked for the refresh. A
# raised marker means "not ticking on purpose". It still has a bound, so a
# load that hangs forever is not immortal.
_BUSY_MAX_S = 600.0


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


def _drop_legacy_marker():
    """Delete the pid file an older launcher left in temp. Never raises.

    Nothing here reads it any more, so this is mostly not leaving litter behind -- but it
    also makes a project whose vendored cadkit is still STALE strictly safer. That old code
    reads the marker, finds this hub's code hash different from its own, and answers by
    force-killing the process the marker names. With no marker it decides no hub is running
    and LAUNCHES one instead: a duplicate window, which the user can close, rather than a
    kill that takes unsaved work with it. Recoverable beats destructive."""
    try:
        os.remove(os.path.join(tempfile.gettempdir(), "freecad_viewer_hub.pid"))
    except OSError:
        pass


def _freecad_running():
    """Is there a FreeCAD process at all? True / False / None when it cannot be told.

    By IMAGE NAME, with no stored pid -- which is all the launcher needs, because the
    question is no longer "which process do I kill" but "do I launch, or talk to what is
    already there". Whether that FreeCAD is a HEALTHY hub is a separate question, answered
    by the heartbeat; whether it is OUR hub at all does not matter, because every response
    from here on is non-destructive.

    None (cannot tell) is distinct from False on purpose: treating "I could not run
    tasklist" as "nothing is running" would spawn a second FreeCAD every build."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq freecad.exe", "/NH", "/FO", "CSV"],
                capture_output=True, text=True, timeout=10).stdout.lower()
            return "freecad.exe" in out
        r = subprocess.run(["pgrep", "-f", "[Ff]reeCAD"],
                           capture_output=True, text=True, timeout=10)
        return bool(r.stdout.strip())
    except Exception:
        return None


def _busy_age():
    """Seconds since the hub raised its BUSY marker, or None if it is not
    inside a blocking load."""
    try:
        return max(0.0, time.time() - os.path.getmtime(_HEARTBEAT + ".busy"))
    except OSError:
        return None


def _heartbeat_age():
    """Seconds since the hub last ticked, or None if there is no heartbeat file."""
    try:
        return max(0.0, time.time() - os.path.getmtime(_HEARTBEAT))
    except OSError:
        return None


def _code_stamp():
    """The hash the hub stamps when it starts: freecad_viewer.py + view.FCMacro.

    Must stay byte-identical to freecad_viewer.code_stamp() -- same files, same order.
    Both are in the stamp because BOTH are now updatable in place: re-running the macro
    executes the macro from disk and reloads the viewer module."""
    import hashlib
    h = hashlib.sha1()
    for name in ("freecad_viewer.py", "view.FCMacro"):
        try:
            with open(os.path.join(_HERE, name), "rb") as f:
                h.update(f.read())
        except OSError:
            pass
    return h.hexdigest()


def _code_is_stale():
    """True if the running hub is executing DIFFERENT code than the copy on disk.

    Compared by CONTENT hash, never mtime: propagating cadkit rewrites every vendored file,
    so identical bytes get a fresh mtime -- and comparing timestamps meant every propagate
    declared a healthy hub stale and closed every open tab (user, 2026-09-07).

    An unknown or absent stamp reads as NOT stale. That used to matter a great deal, because
    the answer to "stale" was a force-kill; now the answer is a macro re-run, so a false
    positive costs a reload instead of a window full of tabs."""
    try:
        running = open(_HEARTBEAT + ".codestamp").read().strip()
    except OSError:
        return False
    if not running:
        return False
    on_disk = _code_stamp()
    if len(running) != len(on_disk):
        return False      # a stamp from an older format: not a reason to act
    return on_disk != running


def _refresh_hub(exe, step):
    """Push the on-disk code into the RUNNING FreeCAD, and rebuild its watch loop.

    `freecad.exe --single-instance <macro>` executes the macro inside the already-running
    instance -- measured, not assumed: the process count stays at 1 and the hub's codestamp
    is rewritten, which only happens inside start_hub(). FreeCAD reads the macro from disk
    each time, and the macro reloads freecad_viewer, so this lands both files.

    That single call is the replacement for _kill_hub() in BOTH of the situations that used
    to justify one:
      - the hub predates the code on disk  -> the reload replaces it
      - its watch loop has stopped         -> shutdown() + reload builds a fresh QTimer
    Nothing is killed, no tab closes, and a FreeCAD holding unsaved work is left alone.

    Spawned DETACHED and never waited on: show() must not be able to stall a build, and the
    outcome is observable next build through the heartbeat and codestamp anyway. Returns
    True if the request was launched, False if it could not be."""
    if not exe or not os.path.exists(exe):
        return False
    try:
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        # The full environment, not just the macro dir: --single-instance runs the macro
        # inside the EXISTING process (using THAT process's env), but if that process has
        # exited since we read the process table, the same call LAUNCHES FreeCAD -- and
        # then this env is the one the macro reads. Correct either way.
        env = dict(os.environ, FREECAD_VIEW_STEP=step, FREECAD_VIEW_INBOX=_INBOX,
                   FREECAD_VIEW_HEARTBEAT=_HEARTBEAT, FREECAD_VIEW_MACRO_DIR=_HERE)
        subprocess.Popen([exe, "--single-instance", _MACRO], env=env,
                         close_fds=True, creationflags=flags)
        return True
    except Exception:
        return False


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
    any handled problem. Never raises.

    Opening a tab is all this does — it never brings the window forward or
    changes which tab is showing (user). There is no flag for that any more."""
    try:
        step = _resolve_step(step_path, project)
        if not os.path.exists(step):
            print("[freecad] %s not found - skipping viewer" % step, file=sys.stderr)
            return False
        os.makedirs(_INBOX, exist_ok=True)
        _drop_legacy_marker()

        exe = _freecad_exe(freecad_exe)
        running = _freecad_running()
        if running is None:
            # Cannot tell from the process table. Fall back to the heartbeat: a fresh one
            # is positive proof a hub is up, and treating "unknown" as "nothing running"
            # would spawn a second FreeCAD on every build.
            running = _heartbeat_age() is not None and _heartbeat_age() <= _HEARTBEAT_STALE_S

        if running:
            age = _heartbeat_age()
            why = None
            if _code_is_stale():
                why = "is running older viewer code"
            elif age is None:
                why = "has no heartbeat"
            elif age > _HEARTBEAT_STALE_S:
                busy = _busy_age()
                if busy is not None and busy <= _BUSY_MAX_S:
                    why = None          # loading, not wedged — leave it alone
                else:
                    why = "watcher unresponsive (%.0fs since last tick)" % age

            # The request goes in FIRST, either way. The hub drains the inbox on every tick
            # AND inside start_hub, so this is picked up whether the hub is already healthy
            # or is about to be refreshed below — and if the refresh fails, the request
            # simply waits there for whenever the hub next ticks. Nothing is lost.
            req = os.path.join(_INBOX, uuid.uuid4().hex + ".txt")
            with open(req, "w", encoding="utf-8") as f:
                f.write(step)
            if why is None:
                return True

            # Two ways a live hub is still useless -- its watch loop has stopped, or it
            # predates the code on disk -- and ONE non-destructive answer to both: re-run
            # the macro inside that same process. It reloads the viewer module and rebuilds
            # the watch loop, so no window closes and no tab is lost. This used to be a
            # taskkill /F /T, which is how a mid-reload hub got destroyed by the very build
            # that wanted the refresh.
            if _refresh_hub(exe, step):
                print("[freecad] hub %s - reloading it in place" % why, file=sys.stderr)
                return True
            print("[freecad] hub %s and could not be reloaded (FreeCAD not found). "
                  "Your tab may be stale; close FreeCAD to get a fresh hub."
                  % why, file=sys.stderr)
            return False

        # No (working) hub: start one. Clear stale requests so a previous session's
        # tabs don't resurrect, then launch FreeCAD with this project as the first tab.
        for f in glob.glob(os.path.join(_INBOX, "*.txt")):
            try:
                os.remove(f)
            except OSError:
                pass
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
        subprocess.Popen([exe, _MACRO], env=env, close_fds=True, creationflags=flags)
        # Nothing records the pid: see the note by _INBOX. Liveness is the heartbeat.
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
