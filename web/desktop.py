"""The viewer as a desktop app, path traced on the graphics card.

    py -3.12 -m cadkit.web.desktop                 # this project's last-built model
    py -3.12 -m cadkit.web.desktop --dir <folder>  # another model folder
    py -3.12 -m cadkit.web.desktop --build         # (re)build the program first

ONE WINDOW, A TAB A PROJECT. The app (`cadkit/desktop`, Rust on wgpu: the card's
ray-tracing hardware through DirectX 12 or Vulkan) shows THE SAME PAGE the browser does
(`viewer/index.html`: every control, the parts list, the measure tool, the rig), laid
see-through over a path tracer that draws the picture. While anything moves the picture
is a few samples a pixel, denoised; at rest it gathers to the quality of the ray traced
lighting level's (Blender's) in a second or two, and then the card does nothing.

IT STANDS ON ITS OWN. The page is built into the program and the model is read from
the project's folder: no server, and no Python once it is installed. Start it from the
taskbar and it comes back with the tabs it had; its "+" lists every project it has
ever shown. This module is only how a project REACHES it:

  * running this makes sure the app is built, current and running, and puts this
    project's tab in front. It returns at once: the app is nobody's child.
  * a build tells it there is a new model (`notify`, called by cadkit.web.view.show):
    the project's tab reloads if it is the one shown, gets a dot if it is not. Nothing
    is opened and nothing comes forward. If the app is not running, nothing happens.
  * with CADKIT_VIEWER=desktop in the environment, show() opens the project's tab in
    the app (starting it, if it is installed) instead of a browser tab.

There is ONE of it: it listens on 127.0.0.1:8136 (`CADKIT_DESKTOP_PORT` moves that) and
answers /ping, /open?dir=..&focus=0|1 and /quit; a second start hands over and ends.

The program is built on this machine with Rust's `cargo` (rustup.rs; `CADKIT_CARGO`
names one that is not on the PATH), OUTSIDE the project and any synced folder, in
`%LOCALAPPDATA%/cadkit-desktop` (`CADKIT_DESKTOP_HOME` moves it):
    target/                 the build
    app/CadkitViewer.exe    THE PROGRAM, at a path that never changes (pin THIS one)
    data/                   what it remembers: its tabs, its projects, the window's place
It is built again when its source (or the page) is newer, and installed over the old
one: a running app is asked to quit, replaced, and started again with its tabs.
Windows only so far: the window layering is Windows'.
"""

from __future__ import annotations

import argparse
import ctypes
import glob
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse

SRC = pathlib.Path(__file__).resolve().parents[1] / "desktop"
PAGE = pathlib.Path(__file__).resolve().parent / "viewer" / "index.html"
PORT = 8136
NAME = "CadkitViewer.exe"


def port():
    try:
        return int(os.environ.get("CADKIT_DESKTOP_PORT") or PORT)
    except ValueError:
        return PORT


# ── the app's door ────────────────────────────────────────────────────────────────
def _ask(path, timeout=5.0, connect=0.3):
    """A GET through the running app's door: its JSON answer, or None if no app
    answers. Never raises, and gives up on an app that is not there in `connect` s."""
    try:
        with socket.create_connection(("127.0.0.1", port()), timeout=connect) as s:
            s.settimeout(timeout)
            s.sendall(("GET %s HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n" % path).encode())
            data = b""
            while True:
                more = s.recv(65536)
                if not more:
                    break
                data += more
        head, _, body = data.partition(b"\r\n\r\n")
        return json.loads(body) if head.startswith(b"HTTP/1.0 200") else None
    except Exception:
        return None


def ping():
    """What the running app says of itself ({app, version, pid, exe, data}), or None."""
    got = _ask("/ping", timeout=1.0)
    return got if isinstance(got, dict) and got.get("app") == "cadkit-desktop" else None


def _open(folder, focus):
    return _ask("/open?" + urllib.parse.urlencode({"dir": str(pathlib.Path(folder).resolve()),
                                                   "focus": int(bool(focus))}))


def notify(model_dir):
    """A build has written a new model into `model_dir`: the app shows it, IF IT IS
    RUNNING (its tab reloads, or gets its dot; the window does not come forward). Costs
    a third of a second at most when there is no app, and never raises."""
    try:
        got = _ask("/open?" + urllib.parse.urlencode({"dir": str(pathlib.Path(model_dir).resolve()), "focus": 0}),
                   timeout=2.0)
        return bool(got and got.get("ok"))
    except Exception:
        return False


# ── where the program lives ───────────────────────────────────────────────────────
def home():
    """The folder the program is built, installed and keeps its data in.
    CADKIT_DESKTOP_HOME says; else a running app's own (the folder above its app/);
    else %LOCALAPPDATA%/cadkit-desktop -- but a packaged Python is shown a private copy
    of AppData, and what it writes there REALLY lives under
    %LOCALAPPDATA%/Packages/<package>/LocalCache/Local: if the app is installed there
    and not in the plain place, that is where it is."""
    env = os.environ.get("CADKIT_DESKTOP_HOME")
    if env:
        return pathlib.Path(env)
    app = ping()
    if app and pathlib.Path(app.get("exe", "")).parent.name == "app":
        return pathlib.Path(app["exe"]).parent.parent
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return pathlib.Path.home() / ".cache" / "cadkit-desktop"
    plain = pathlib.Path(base) / "cadkit-desktop"
    if not (plain / "app" / NAME).exists():
        for exe in glob.glob(os.path.join(glob.escape(base), "Packages", "*", "LocalCache", "Local",
                                          "cadkit-desktop", "app", NAME)):
            return pathlib.Path(exe).parent.parent
    return plain


def built():
    return home() / "target" / "release" / ("desk.exe" if os.name == "nt" else "desk")


def program():
    """THE program: the path a taskbar pin points at. It never changes."""
    return home() / "app" / NAME


def _newest_source():
    # (the page is built INTO the program: a newer page is a newer program)
    return max(f.stat().st_mtime for f in [SRC / "Cargo.toml", SRC / "Cargo.lock", SRC / "build.rs",
                                           SRC / "icon.ico", PAGE, *(SRC / "src").iterdir()])


def stale():
    exe = built()
    return not exe.exists() or exe.stat().st_mtime < _newest_source()


def find_cargo():
    """(cargo, extra environment), or (None, {})."""
    env = os.environ.get("CADKIT_CARGO")
    if env and os.path.isfile(env):
        return env, {}
    found = shutil.which("cargo")
    if found:
        return found, {}
    # a toolchain kept to itself beside the build (rustup with --no-modify-path)
    roots = [home(), home().parent / "cadkit-rt"]
    if os.environ.get("LOCALAPPDATA"):
        roots.append(pathlib.Path(os.environ["LOCALAPPDATA"]) / "cadkit-rt")
    for root in roots:
        exe = root / "cargo" / "bin" / ("cargo.exe" if os.name == "nt" else "cargo")
        if exe.exists():
            return str(exe), {"CARGO_HOME": str(root / "cargo"), "RUSTUP_HOME": str(root / "rustup"),
                              "PATH": str(exe.parent) + os.pathsep + os.environ.get("PATH", "")}
    return None, {}


def build():
    cargo, extra = find_cargo()
    if cargo is None:
        raise SystemExit("cadkit desktop: Rust's cargo was not found. Install Rust (https://rustup.rs), "
                         "or set CADKIT_CARGO to a cargo executable, and run this again.")
    home().mkdir(parents=True, exist_ok=True)
    print("cadkit desktop: building (the first build takes a few minutes)")
    sys.stdout.flush()
    r = subprocess.run([cargo, "build", "--release", "--manifest-path", str(SRC / "Cargo.toml"),
                        "--target-dir", str(home() / "target")], env={**os.environ, **extra})
    if r.returncode != 0:
        raise SystemExit("cadkit desktop: the build failed")


def quit_app(wait=10.0):
    """Ask the running app to end (it saves its tabs and its place), and wait for it."""
    if ping() is None:
        return True
    _ask("/quit")
    end = time.time() + wait
    while time.time() < end:
        if ping() is None:
            return True
        time.sleep(0.1)
    return False


def install():
    """The built program put at its lasting path, app/CadkitViewer.exe, if what is
    there is not it. A running app is in the way of that (a running file cannot be
    replaced): it is asked to quit first. Returns (installed anew, an app was quit)."""
    src, dst = built(), program()
    if dst.exists() and (dst.stat().st_size, int(dst.stat().st_mtime)) == (src.stat().st_size, int(src.stat().st_mtime)):
        return False, False
    was = ping() is not None
    if was:
        print("cadkit desktop: the program has changed -- the app comes back on the new one, with its tabs")
        if not quit_app():
            raise SystemExit("cadkit desktop: the running app did not end; close it and run this again")
    dst.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(50):                               # (the file is let go a moment after the app ends)
        try:
            shutil.copy2(src, dst)
            break
        except PermissionError:
            time.sleep(0.1)
    else:
        raise SystemExit("cadkit desktop: %s is in use and could not be replaced" % dst)
    print("cadkit desktop: installed %s" % dst)
    return True, was


def start(*args):
    """Start the app (it is nobody's child: what started it is free to end)."""
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(program()), *args], cwd=str(program().parent), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)


def open_project(model_dir, focus=True, launch=True):
    """`model_dir`'s tab in the app: opened in the running one (and, with `focus`, shown
    and brought in front), else in one started for it, if the program is installed and
    `launch` says so. True: the app has it. Never raises."""
    try:
        app = ping()
        if app is not None:
            if focus and os.name == "nt":             # this process may come in front: the app is given that
                ctypes.windll.user32.AllowSetForegroundWindow(int(app.get("pid", 0)))
            got = _open(model_dir, focus)
            return bool(got and got.get("ok"))
        if launch and program().exists():
            start("--open", str(pathlib.Path(model_dir).resolve()))
            return True
    except Exception:
        pass
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="the cadkit viewer as a desktop app")
    ap.add_argument("--dir", default=None, help="the model folder (default: ./.webview)")
    ap.add_argument("--build", action="store_true", help="build the program even if it is current")
    a = ap.parse_args(argv)
    if os.name != "nt":
        raise SystemExit("cadkit desktop: Windows only so far")
    if a.build or stale():
        build()
    anew, was_running = install()
    folder = pathlib.Path(a.dir) if a.dir else pathlib.Path(os.getcwd()) / ".webview"
    has_model = (folder / "assembly.glb").exists()
    if not has_model:
        print("cadkit desktop: no model in %s (build the project, and it shows itself)" % folder)
    app = ping()
    if app is None:
        start(*(["--open", str(folder.resolve())] if has_model else []))
        print("cadkit desktop: started %s" % program())
    else:
        ctypes.windll.user32.AllowSetForegroundWindow(int(app.get("pid", 0)))
        got = _open(folder, True) if has_model else _ask("/open?focus=1")
        if has_model and not (got and got.get("ok")):
            raise SystemExit("cadkit desktop: the app did not open %s: %s" % (folder, got and got.get("error")))
        print("cadkit desktop: %s" % ("its tab is in front" if has_model else "the app is in front"))


if __name__ == "__main__":
    main(sys.argv[1:])
