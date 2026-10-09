"""The viewer page, served from this machine.

    from cadkit.web import show
    show(parts)                      # [(name, solid, colour)] -> the page, in a browser tab
    show("assembly.step")            # or the assembly file a build already wrote

`show()` meshes the parts into <project>/.webview/, starts a small server there if one
is not running, and opens the page the first time. An open page watches the model's
stamp and reloads it by itself, keeping the camera and whatever is hidden, so after the
first call the loop is: build, look. It never raises: trouble with the viewer must not
cost a build.

The scratch loop (cadkit.scratch) uses `scratch_export()`: every part from its BREP
file -- the lead's build, under what this worktree built itself -- and each file's MESH
kept beside it (keyed on the file's size and time), so a run meshes only what changed.

The same page is what a project publishes: `export(..., page=True)` writes it beside
the model, and that folder is a web site.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import pathlib
import pickle
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

from .export import PAGE, export, rig_names, step_parts
from .trace import Tracer

PORT = 8137
PORTS = 20                      # how many ports up from PORT a project may land on
# what the server takes from the model folder; everything else is the page's own
MODEL_FILES = ("assembly.glb", "assembly.geo.json", "rig.json", "stamp.json")


# ── the server ────────────────────────────────────────────────────────────────────
class _Handler(http.server.SimpleHTTPRequestHandler):
    model_dir = None            # set by serve()
    tracer = None               # the ray tracer behind the page's top lighting level

    def translate_path(self, path):
        name = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if name in MODEL_FILES:
            return str(self.model_dir / name)
        return super().translate_path(path)

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        name = self.path.split("?", 1)[0]
        if name == "/page.json":            # when the PAGE was last edited: it reloads itself
            return self._json({"t": PAGE.stat().st_mtime_ns})
        if name == "/where.json":           # which project this server is showing
            return self._json({"dir": str(self.model_dir)})
        if name == "/trace.json":           # can this server ray trace? (?warm: get ready)
            if self.tracer.available and "warm" in self.path:
                self.tracer.warm()
            return self._json({"available": self.tracer.available})
        super().do_GET()

    def do_POST(self):
        # ONE THING IS POSTED: a view to ray trace. Only as JSON, which another site's
        # page cannot send here without asking first, and nothing in it names a file.
        if self.path.split("?", 1)[0] != "/trace" or not self.tracer.available                 or self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self.send_error(404)
        try:
            n = int(self.headers.get("Content-Length", 0))
            if not 0 < n < 4_000_000:
                return self.send_error(400)
            body = self.tracer.picture(json.loads(self.rfile.read(n)))
        except Exception as e:
            return self.send_error(503, "ray tracing failed: %s" % str(e)[:200])
        if body is None:                    # overtaken by a newer view
            self.send_response(204)
            return self.end_headers()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


def serve(model_dir, port=PORT):
    """Serve the page with the model in `model_dir`, in the foreground."""
    _Handler.model_dir = pathlib.Path(model_dir).resolve()
    _Handler.tracer = Tracer(_Handler.model_dir)
    handler = functools.partial(_Handler, directory=str(PAGE.parent))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    print("web view: http://127.0.0.1:%d/   (model from %s)" % (port, _Handler.model_dir))
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def _listening(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _shows(port):
    """The folder the server on `port` is showing, or None if it is not one of ours."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/where.json" % port, timeout=1.0) as r:
            return pathlib.Path(json.loads(r.read())["dir"])
    except Exception:
        return None


def ensure_server(model_dir, port=PORT):
    """(url, started): the server showing `model_dir`, started if there was none. Two
    projects open at once each get a port of their own, counting up from `port`."""
    model_dir = pathlib.Path(model_dir).resolve()
    free = None
    for p in range(port, port + PORTS):
        if _listening(p):
            if _shows(p) == model_dir:
                return "http://127.0.0.1:%d/" % p, False
        elif free is None:
            free = p
    if free is None:
        raise RuntimeError("no free port in %d..%d" % (port, port + PORTS - 1))
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    package_parent = pathlib.Path(__file__).resolve().parents[2]
    subprocess.Popen([sys.executable, "-m", "cadkit.web.view", "--serve",
                      "--dir", str(model_dir), "--port", str(free)],
                     cwd=str(package_parent), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)
    for _ in range(50):
        if _listening(free):
            return "http://127.0.0.1:%d/" % free, True
        time.sleep(0.1)
    raise RuntimeError("the web view's server did not come up on port %d" % free)


def _model_dir(root=None):
    """<project>/.webview, made if missing and kept out of git by its own ignore file."""
    out = pathlib.Path(root or os.getcwd()) / ".webview"
    out.mkdir(parents=True, exist_ok=True)
    ign = out / ".gitignore"
    if not ign.exists():
        ign.write_text("*\n")
    return out


def _open(url, started, open_browser):
    print("web view: %s%s" % (url, "" if started else "   (an open page reloads itself)"))
    if started and open_browser:
        import webbrowser
        webbrowser.open(url)


# ── show(): a build's parts, or its assembly file ─────────────────────────────────
def show(source, root=None, title=None, open_browser=True, port=PORT, **export_kw):
    """Put `source` in the viewer: [(name, solid, colour)] or the path of an assembly
    STEP. `root` is the project folder (default: the folder the STEP is in, else the
    working directory). Further
    keywords go to cadkit.web.export (boards=, materials=, extras= ...). Returns True
    when the page has the new model; never raises."""
    try:
        is_file = isinstance(source, (str, os.PathLike))
        if root is None and is_file:
            root = pathlib.Path(source).resolve().parent
        out = _model_dir(root)
        parts = step_parts(source) if is_file else list(source)
        extras = dict(export_kw.pop("extras", None) or {})
        if title:
            extras.setdefault("title", title)
        export_kw.setdefault("cache_dir", out / "boards")
        export(parts, out, extras=extras, **export_kw)
        (out / "stamp.json").write_text(json.dumps({"t": time.time(), "parts": len(parts)}))
        url, started = ensure_server(out, port)
        _open(url, started, open_browser)
        return True
    except Exception as exc:                          # the viewer never costs a build
        print("[web view] not refreshed: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return False


def show_exported(folder, root=None, open_browser=True, port=PORT):
    """Put a folder export() ALREADY WROTE in the local viewer -- the site a build is
    about to publish, say -- so the model is meshed once, not once per place it is
    looked at. Returns True when the page has it; never raises."""
    try:
        folder, out = pathlib.Path(folder), _model_dir(root)
        n = 0
        for name in MODEL_FILES[:-1]:
            if (folder / name).exists():
                shutil.copyfile(folder / name, out / (name + ".tmp"))
                os.replace(out / (name + ".tmp"), out / name)
                n += 1
        (out / "stamp.json").write_text(json.dumps({"t": time.time(), "files": n}))
        url, started = ensure_server(out, port)
        _open(url, started, open_browser)
        return True
    except Exception as exc:                          # the viewer never costs a build
        print("[web view] not refreshed: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return False


# ── the scratch loop: one part fresh, the rest from the cache ─────────────────────
def _colors(out, names, resolver):
    """{name: (r, g, b, a)}, remembered between runs: a project's colour resolver can
    cost its whole build module's import, so only an unknown name pays for it.
    `resolver` is name -> colour, or a zero-argument function returning one."""
    path = out / "colors.json"
    known = json.loads(path.read_text()) if path.exists() else {}
    missing = [n for n in names if n not in known]
    if missing and resolver is not None:
        try:
            import inspect
            if not inspect.signature(resolver).parameters:
                print("web view: %d part(s) with no remembered colour -- loading the "
                      "project's colours for them (once)" % len(missing))
                resolver = resolver()
        except (TypeError, ValueError):
            pass
        for n in missing:
            try:
                c = resolver(n)
                known[n] = list(c.toTuple() if hasattr(c, "toTuple") else c)
            except Exception:
                known[n] = [0.8, 0.8, 0.8, 1.0]
        path.write_text(json.dumps(known))
    return {n: tuple(known.get(n, (0.8, 0.8, 0.8, 1.0))) for n in names}


def _cached_mesh(brep, taken, whole):
    """[(piece name, mesh)] of a cached part (export.pieces says when a part is
    several), itself cached BESIDE the part on the file's size and time: so the meshes
    of the lead's build are made once, by whichever worktree first looks, for all."""
    from ..scratch import read_brep
    from .export import mesh_shape, pieces, TOLERANCE, ANGULAR, FORMAT
    st = brep.stat()
    key = (st.st_size, st.st_mtime_ns, TOLERANCE, ANGULAR, FORMAT, "pieces", brep.stem in whole)
    f = brep.parent / "mesh" / (brep.stem + ".pkl")
    if f.exists():
        try:
            k, m = pickle.loads(f.read_bytes())
            if k == key:
                return m
        except Exception:
            pass
    m = [(n, mesh_shape(s)) for n, s in
         pieces(brep.stem, read_brep(brep).wrapped, taken, whole)]
    m = [(n, x) for n, x in m if x is not None]
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name("%s.%d.tmp" % (f.name, os.getpid()))
        tmp.write_bytes(pickle.dumps((key, m), protocol=pickle.HIGHEST_PROTOCOL))
        os.replace(tmp, f)
    except OSError:
        pass                                  # two worktrees at once: either's will do
    return m


def _piece(brep, name, taken, whole):
    from ..scratch import read_brep
    from .export import pieces
    return dict(pieces(brep.stem, read_brep(brep).wrapped, taken, whole))[name]


def scratch_export(view, describe=None, colors=None, rig=None, refresh_rig=False, **export_kw):
    """Export a cadkit.scratch.ScratchView's model for the page: every part from its
    BREP file (view.files(): the lead's build under what this worktree built itself),
    each file's mesh remembered beside it. `describe` is view.describe(), for the
    page's status line; `colors` the project's colour resolver (see _colors); `rig` an
    optional function(path) that writes the animation rig. Returns the model folder."""
    out = _model_dir(view.root)
    t0 = time.time()
    files = view.files()
    if not files:
        raise SystemExit("web view: nothing to show -- no shared cache and none of your own")
    # THE RIG FIRST: it names the parts that move, and a part that moves must stay one
    # part however many solids it is drawn as (export.pieces).
    if rig is not None and (refresh_rig or not (out / "rig.json").exists()):
        try:
            rig(out / "rig.json")
        except Exception as exc:
            print("web view: no animation rig (%s) -- the page shows the model still" % exc)
    meshed, solids, base = {}, {}, {}             # base: a piece's part, for its colour
    taken = set(files)
    whole = rig_names(out / "rig.json")
    for part, f in files.items():
        for n, m in _cached_mesh(f, taken, whole):
            meshed[n], base[n] = m, part
            solids[n] = (lambda p=f, k=n: _piece(p, k, taken, whole))
    cols = _colors(out, sorted(set(base.values())), colors if colors is not None else view.colors)
    export_kw.setdefault("cache_dir", out / "boards")
    export([(n, solids[n], cols[base[n]]) for n in meshed], out, meshed=meshed, whole=whole,
           parents={n: p for n, p in base.items() if n != p}, **export_kw)
    stamp = dict(describe or view.describe(), t=time.time(), scratch=True, parts=len(meshed))
    stamp.pop("own_names", None)
    (out / "stamp.json").write_text(json.dumps(stamp))
    print("web view: %d parts in %.1f s" % (len(meshed), time.time() - t0))
    return out


def scratch_show(view, open_browser=True, port=PORT, **kw):
    """scratch_export(), then the page. Never raises."""
    try:
        out = scratch_export(view, **kw)
        url, started = ensure_server(out, port)
        _open(url, started, open_browser)
        return True
    except SystemExit:
        raise
    except Exception as exc:
        print("[web view] not refreshed: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="the cadkit web viewer's local server")
    ap.add_argument("--serve", action="store_true", help="serve --dir in the foreground")
    ap.add_argument("--dir", default=None, help="the model folder (default: ./.webview)")
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args(argv)
    model_dir = pathlib.Path(a.dir) if a.dir else _model_dir()
    if a.serve:
        serve(model_dir, a.port)
        return 0
    url, started = ensure_server(model_dir, a.port)
    _open(url, started, True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
