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
to the quality of the ray traced lighting level's (Blender's) in well under a second,
and then the card does nothing.

The program is built on this machine the first time, with Rust's `cargo` (rustup.rs),
and kept OUTSIDE the project and any synced folder: `%LOCALAPPDATA%/cadkit-desktop` on
Windows, `~/.cache/cadkit-desktop` elsewhere (`CADKIT_DESKTOP_HOME` moves it). It is
built again when its source is newer. `CADKIT_CARGO` names a cargo that is not on the
PATH. Windows only so far: the window layering is Windows'.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys

SRC = pathlib.Path(__file__).resolve().parents[1] / "desktop"


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
    state = home() / "window.json"
    rest = [x for x in a.rest if x != "--"]
    print("cadkit desktop: %s" % url)
    subprocess.Popen([str(program()), url, "--state", str(state), *rest], cwd=str(home()))


if __name__ == "__main__":
    main(sys.argv[1:])
