"""The viewer as a desktop window, path traced on the graphics card.

    py -3.12 -m cadkit.web.desktop                 # this project's last-built model
    py -3.12 -m cadkit.web.desktop --dir <folder>  # another model folder
    py -3.12 -m cadkit.web.desktop --build         # (re)build the program, then run

The window shows THE SAME PAGE the browser does (`viewer/index.html`), served by the
same local server: every control, the parts list, the measure tool, the rig. Only the
picture is somebody else's. The page is laid see-through over a path tracer
(`cadkit/desktop`, Rust on wgpu: the card's ray-tracing hardware through DirectX 12 or
Vulkan) and tells it what the picture is of; it draws the model itself only in a browser.
While anything moves the picture is a few samples a pixel, denoised; at rest it gathers
to the quality of the ray traced lighting level's (Blender's) in a second or two, and
then the card does nothing.

IT IS KEPT CURRENT IN PLACE, as a browser tab is. A model built again appears in the open
window (the page watches the server's stamp, as in a browser), and so does an edit to the
page. Running this again for a model whose window is open brings that window forward
instead of opening another; and if the PROGRAM has changed since that window was started,
it is built, the window is closed and it comes back where it was, on the same view (the
page keeps its camera, hidden parts and section between runs of a window).

The program is built on this machine the first time, with Rust's `cargo` (rustup.rs),
and kept OUTSIDE the project and any synced folder: `%LOCALAPPDATA%/cadkit-desktop` on
Windows (`CADKIT_DESKTOP_HOME` moves it). It is built again when its source is newer.
Each window runs a COPY of the built program (`run/`), so a build never has to replace a
file that is running. `CADKIT_CARGO` names a cargo that is not on the PATH. Windows only
so far: the window layering is Windows'.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

SRC = pathlib.Path(__file__).resolve().parents[1] / "desktop"
WM_CLOSE, SW_RESTORE = 0x0010, 9


def home():
    env = os.environ.get("CADKIT_DESKTOP_HOME")
    if env:
        return pathlib.Path(env)
    base = os.environ.get("LOCALAPPDATA")
    return (pathlib.Path(base) if base else pathlib.Path.home() / ".cache") / "cadkit-desktop"


def program():
    return home() / "target" / "release" / ("desk.exe" if os.name == "nt" else "desk")


def _newest_source():
    return max(f.stat().st_mtime for f in [SRC / "Cargo.toml", SRC / "Cargo.lock",
                                           *(SRC / "src").iterdir()])


def stale():
    exe = program()
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
    for root in (home(), home().parent / "cadkit-rt"):
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
    r = subprocess.run([cargo, "build", "--release", "--manifest-path", str(SRC / "Cargo.toml"),
                        "--target-dir", str(home() / "target")], env={**os.environ, **extra})
    if r.returncode != 0:
        raise SystemExit("cadkit desktop: the build failed")


def running_copy():
    """The copy of the built program a window runs: run/desk-<when built>.exe. Older
    copies nothing is running any more are cleared away (one that IS running cannot be
    deleted, which is how it is told)."""
    exe = program()
    run = home() / "run"
    run.mkdir(parents=True, exist_ok=True)
    mine = run / ("desk-%d.exe" % exe.stat().st_mtime_ns)
    for old in run.glob("desk-*.exe"):
        if old != mine:
            try:
                old.unlink()
            except OSError:
                pass
    if not mine.exists():
        shutil.copy2(exe, mine)
    return mine


# ── the windows that are open: {url: {"pid", "exe"}} ───────────────────────────────
def _registry():
    return home() / "windows.json"


def _image(pid):
    """The program file process `pid` is running, or None if there is no such process."""
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, int(pid))            # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf, n = ctypes.create_unicode_buffer(1024), ctypes.c_ulong(1024)
        return buf.value if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else None
    finally:
        k.CloseHandle(h)


def _same(a, b):
    return os.path.normcase(os.path.basename(a)) == os.path.normcase(os.path.basename(b))


def open_windows():
    """{url: {"pid", "exe"}} of the windows still open, the registry tidied to match."""
    try:
        was = json.loads(_registry().read_text())
    except Exception:
        was = {}
    now = {}
    for url, w in was.items():
        img = _image(w.get("pid", 0))
        # by the file's NAME: a packaged Python is shown its folders under other paths
        if img and _same(img, w.get("exe", "")):
            now[url] = w
    if now != was:
        _registry().write_text(json.dumps(now))
    return now


def _windows_of(pid):
    u, found = ctypes.windll.user32, []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def each(hwnd, _):
        owner = ctypes.c_ulong()
        u.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(owner))
        if owner.value == pid and u.IsWindowVisible(ctypes.c_void_p(hwnd)) \
                and not u.GetWindow(ctypes.c_void_p(hwnd), 4):       # GW_OWNER: a top window of its own
            found.append(hwnd)
        return True
    u.EnumWindows(each, None)
    return found


def bring_forward(pid):
    u = ctypes.windll.user32
    for hwnd in _windows_of(pid):
        if u.IsIconic(ctypes.c_void_p(hwnd)):
            u.ShowWindow(ctypes.c_void_p(hwnd), SW_RESTORE)
        u.SetForegroundWindow(ctypes.c_void_p(hwnd))


def close(pid, wait=8.0):
    """Ask the window to close (it saves its place), and wait for the program to end."""
    u = ctypes.windll.user32
    for hwnd in _windows_of(pid):
        u.PostMessageW(ctypes.c_void_p(hwnd), WM_CLOSE, None, None)
    end = time.time() + wait
    while time.time() < end:
        if _image(pid) is None:
            return True
        time.sleep(0.1)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="the cadkit viewer as a desktop window")
    ap.add_argument("--dir", default=None, help="the model folder (default: ./.webview)")
    ap.add_argument("--build", action="store_true", help="build the program even if it is current")
    ap.add_argument("rest", nargs=argparse.REMAINDER, help="passed to the program (after --)")
    a = ap.parse_args(argv)
    if os.name != "nt":
        raise SystemExit("cadkit desktop: Windows only so far")
    if a.build or stale():
        build()
    from .view import PORT, _model_dir, ensure_server
    folder = pathlib.Path(a.dir) if a.dir else _model_dir()
    if not (folder / "assembly.glb").exists():
        raise SystemExit("cadkit desktop: no model in %s -- build the project first" % folder)
    url, _ = ensure_server(folder, PORT, same_page=True)
    exe = running_copy()
    rest = [x for x in a.rest if x != "--"]
    wins = open_windows()
    w = wins.get(url)
    if w and not rest:
        if _same(w["exe"], str(exe)):
            bring_forward(w["pid"])
            print("cadkit desktop: %s is open already (a model built again shows in it by itself)" % url)
            return
        print("cadkit desktop: the program has changed -- the window comes back on the new one")
        if not close(w["pid"]):
            raise SystemExit("cadkit desktop: the open window did not close; close it and run this again")
    port = url.rstrip("/").rsplit(":", 1)[-1]
    print("cadkit desktop: %s" % url)
    p = subprocess.Popen([str(exe), url, "--state", str(home() / ("window-%s.json" % port)),
                          "--data", str(home() / "webview" / port), *rest], cwd=str(home()),
                         # a window is nobody's child: what started it is free to end
                         **({} if rest else dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                 stderr=subprocess.DEVNULL)))
    if not rest:
        wins = open_windows()
        wins[url] = {"pid": p.pid, "exe": str(exe)}
        _registry().write_text(json.dumps(wins))


if __name__ == "__main__":
    main(sys.argv[1:])
