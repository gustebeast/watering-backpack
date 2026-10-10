"""The viewer page, served from this machine.

    from cadkit.web import show
    show(parts)                      # [(name, solid, colour)] -> the page, in a browser tab
    show("assembly.step")            # or the assembly file a build already wrote

`show()` meshes the parts into <project>/.webview/, tells THE server of the project
(one server for every project on this machine, on one port: started if none is running;
each project is a path under it, http://127.0.0.1:8137/p/<project>/, and a tab in the
page), and opens the page the first time. It also tells the desktop app, if that is
running (cadkit.web.desktop); with CADKIT_VIEWER=desktop the app is where it is shown. An open page watches the model's
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
import urllib.parse
import urllib.request

from .export import PAGE, export, rig_names, step_parts
from .trace import Tracer

# ONE SERVER, ONE PORT, for every project and worktree on this machine. Each project is
# a PATH under it (/p/<key>/), not a port of its own. CADKIT_VIEW_PORT moves it (checks).
PORT = int(os.environ.get("CADKIT_VIEW_PORT") or 8137)
PROTO = 2                       # what the server answers; an older one is replaced
# what the server takes from the model folder; everything else is the page's own
MODEL_FILES = ("assembly.glb", "assembly.geo.json", "rig.json", "stamp.json")


# ── the projects the server knows ─────────────────────────────────────────────────
def _store():
    """Where the list of projects is kept: the desktop app's own list
    (<home>/data/projects.json), so the app and the page show the same projects."""
    try:
        from .desktop import home
        return home() / "data" / "projects.json"
    except Exception:
        return None


def _whose(title, folder):
    """A copy of a project in a folder of its own (a worktree: public-steel-guitar-bronner
    beside public-steel-guitar) builds a model with the same title, so its tab says whose
    it is: what the folder's name has after the title ("Public Steel Guitar · bronner")."""
    name = _project_name(folder)
    want = sum(c.isalnum() for c in title or "")
    slug = lambda s: "".join(c.lower() for c in s if c.isalnum())
    if not want or not slug(name).startswith(slug(title)):
        return title
    at = next((i for i in range(len(name) + 1) if sum(c.isalnum() for c in name[:i]) == want), len(name))
    rest = name[at:].strip("-_. ")
    return "%s · %s" % (title, rest) if rest else title


def _project_name(folder):
    """A project's folder name: a model folder is <project>/.webview."""
    folder = pathlib.Path(folder)
    return folder.parent.name if folder.name.startswith(".") else folder.name


def _model_title(folder):
    """The title the model's own file gives it (asset.extras.title), or None."""
    try:
        with open(pathlib.Path(folder) / "assembly.glb", "rb") as f:
            head = f.read(20)
            n = int.from_bytes(head[12:16], "little")
            if head[:4] != b"glTF" or n > 64 << 20:
                return None
            t = json.loads(f.read(n)).get("asset", {}).get("extras", {}).get("title")
        return t.strip() or None if isinstance(t, str) else None
    except Exception:
        return None


def _mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


class _Projects:
    """key -> model folder. The list is the file's (re-read each time: the desktop app
    writes it too); the key of a project is its folder's name, made unlike any other's,
    and is written into the list so that it never changes."""

    def __init__(self, store=None):
        import threading
        self.store, self.lock = store, threading.Lock()
        self.rows, self.fresh, self.titles = [], set(), {}

    def _read(self):
        if self.store is not None:
            try:
                rows = json.loads(self.store.read_text(encoding="utf-8"))
                if isinstance(rows, list):
                    self.rows = [r for r in rows if isinstance(r, dict) and r.get("dir")]
            except Exception:
                pass
        taken, changed = {r["key"] for r in self.rows if r.get("key")}, False
        for r in self.rows:
            if not r.get("key"):
                base = "".join(c if c.isalnum() or c in "-_." else "-"
                               for c in _project_name(r["dir"]).lower()).strip("-.") or "project"
                key, n = base, 1
                while key in taken:
                    n += 1
                    key = "%s-%d" % (base, n)
                r["key"] = key
                taken.add(key)
                changed = True
        return changed

    def _write(self):
        if self.store is None:
            return
        try:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.store.with_suffix(".tmp%d" % os.getpid())
            tmp.write_text(json.dumps(self.rows, indent=2), encoding="utf-8")
            os.replace(tmp, self.store)
        except OSError:
            pass

    def _title(self, folder):
        t = _mtime(pathlib.Path(folder) / "assembly.glb")
        was = self.titles.get(folder)
        if was is None or was[0] != t:
            was = self.titles[folder] = (t, _whose(_model_title(folder), folder) if t else None)
        return was[1]

    def open(self, folder):
        """(key, first time this server hears of it)."""
        folder = str(pathlib.Path(folder).resolve())
        with self.lock:
            self._read()
            row = next((r for r in self.rows if os.path.normcase(r["dir"]) == os.path.normcase(folder)), None)
            if row is None:
                row = {"dir": folder}
                self.rows.append(row)
            row["name"] = self._title(folder) or _project_name(folder)
            row["opened"] = time.time()
            self._read_keys_only()
            self._write()
            new = row["key"] not in self.fresh
            self.fresh.add(row["key"])
            return row["key"], new

    def _read_keys_only(self):
        store, self.store = self.store, None            # (keys for the rows in hand, the file not read again)
        try:
            self._read()
        finally:
            self.store = store

    def folder(self, key):
        with self.lock:
            if not any(r.get("key") == key for r in self.rows):
                if self._read():
                    self._write()
            return next((pathlib.Path(r["dir"]) for r in self.rows if r.get("key") == key), None)

    def listing(self):
        """What the page's tab strip shows: the model's time found now, newest first."""
        with self.lock:
            if self._read():
                self._write()
            out = []
            for r in self.rows:
                d = pathlib.Path(r["dir"])
                built = _mtime(d / "assembly.glb")
                out.append({"key": r["key"], "dir": r["dir"], "folder": _project_name(d),
                            "name": (self._title(r["dir"]) if built else None) or r.get("name") or _project_name(d),
                            "built": built, "missing": built is None, "opened": r.get("opened", 0),
                            "stamp": _mtime(d / "stamp.json") or built})
            out.sort(key=lambda x: -(x["built"] or -1))
            return out


# ── the server ────────────────────────────────────────────────────────────────────
class _Handler(http.server.BaseHTTPRequestHandler):
    projects = None             # set by serve()
    pinned = None               # serve(model_dir): that one model at the root, as a published site has it
    tracers = {}                # model folder -> the ray tracer behind the page's top lighting level
    dev_page = None             # /dev/...: the page from this file instead (work on the page itself)
    protocol_version = "HTTP/1.0"

    def _send(self, code, kind, body):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, "application/json", json.dumps(obj).encode())

    def _file(self, path, kind):
        try:
            with open(path, "rb") as f:
                size = os.fstat(f.fileno()).st_size
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(size))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                shutil.copyfileobj(f, self.wfile, 1 << 20)
        except OSError:
            self.send_error(404)

    def _own(self):
        """Is this one of cadkit's own callers (or typed into the address bar)? A page of
        another site can make a browser send a GET here; a browser says so, and it is
        not answered: only /open, /dev and /quit change anything, and only these ask."""
        site = self.headers.get("Sec-Fetch-Site")
        return site in (None, "none", "same-origin") and (self.headers.get("Origin") is None or site == "same-origin")

    def _tracer(self, folder):
        t = self.tracers.get(folder)
        if t is None:
            t = self.tracers[folder] = Tracer(folder)
        return t

    def _where(self, path):
        """(model folder or None, the name asked for there, the page file) of a path."""
        dev = path.startswith("/dev/") and self.dev_page is not None
        page = self.dev_page if dev else PAGE
        if path.startswith("/dev/"):
            path = path[4:]
        if path.startswith("/p/"):
            key, _, name = path[3:].partition("/")
            return self.projects.folder(key), name, page
        return self.pinned, path.lstrip("/"), page

    def do_GET(self):
        path, _, query = self.path.partition("?")
        q = dict(urllib.parse.parse_qsl(query))
        if path in ("/open", "/dev", "/quit"):
            if not self._own():
                return self._json({"error": "not for web pages"}, 403)
            if path == "/quit":
                self._json({"ok": True})
                import threading
                return threading.Thread(target=self.server.shutdown, daemon=True).start()
            if path == "/dev":
                page = pathlib.Path(q.get("page", ""))
                if not (page.is_absolute() and page.is_file() and page.suffix == ".html"):
                    return self._json({"error": "not a page file: %s" % page}, 400)
                type(self).dev_page = page
                return self._json({"ok": True, "page": str(page)})
            folder = pathlib.Path(q.get("dir", ""))
            if not (folder.is_absolute() and (folder / "assembly.glb").is_file()):
                return self._json({"error": "no model (assembly.glb) in %s" % folder}, 400)
            key, new = self.projects.open(folder)
            return self._json({"key": key, "new": new, "path": "/p/%s/" % key})
        if path in ("/projects.json", "/dev/projects.json"):
            return self._json({"proto": PROTO, "projects": self.projects.listing()})
        folder, name, page = self._where(path)
        if folder is None:
            if path == "/where.json":       # which server this is (ensure_server asks)
                return self._json({"server": "cadkit.web.view", "proto": PROTO, "page": str(PAGE),
                                   "page_t": PAGE.stat().st_mtime_ns, "pid": os.getpid()})
            if path in ("/", "/dev/", "/index.html"):
                # an old address (the server's root): the project opened last
                rows = sorted(self.projects.listing(), key=lambda r: -r["opened"])
                rows = [r for r in rows if not r["missing"]]
                if rows:
                    self.send_response(302)
                    self.send_header("Location", "%sp/%s/" % ("/dev/" if path == "/dev/" else "/", rows[0]["key"]))
                    self.send_header("Content-Length", "0")
                    return self.end_headers()
                return self._send(200, "text/html; charset=utf-8",
                                  b"<body style='background:#16181c;color:#c9ced6;font:14px system-ui;padding:24px'>"
                                  b"cadkit viewer: no project has shown itself here yet (a build's show() does)")
            return self.send_error(404)
        if name in ("", "index.html"):
            return self._file(page, "text/html; charset=utf-8")
        if name == "page.json":             # when the PAGE was last edited: it reloads itself
            return self._json({"t": page.stat().st_mtime_ns})
        if name == "where.json":            # which project this address is showing
            return self._json({"dir": str(folder), "page": str(page), "proto": PROTO,
                               "page_t": page.stat().st_mtime_ns, "pid": os.getpid(), "pinned": folder == self.pinned})
        if name == "trace.json":            # can this server ray trace? (?warm: get ready)
            t = self._tracer(folder)
            if t.available and "warm" in query:
                t.warm()
            return self._json({"available": t.available})
        if name in MODEL_FILES:
            return self._file(folder / name, "model/gltf-binary" if name.endswith(".glb") else "application/json")
        self.send_error(404)

    do_HEAD = do_GET

    def do_POST(self):
        # ONE THING IS POSTED: a view to ray trace. Only as JSON, which another site's
        # page cannot send here without asking first, and nothing in it names a file.
        folder, name, _ = self._where(self.path.split("?", 1)[0])
        if name != "trace" or folder is None or not self._tracer(folder).available \
                or self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self.send_error(404)
        try:
            n = int(self.headers.get("Content-Length", 0))
            if not 0 < n < 4_000_000:
                return self.send_error(400)
            body = self._tracer(folder).picture(json.loads(self.rfile.read(n)))
        except Exception as e:
            return self.send_error(503, "ray tracing failed: %s" % str(e)[:200])
        if body is None:                    # overtaken by a newer view
            self.send_response(204)
            return self.end_headers()
        self._send(200, "image/jpeg", body)

    def log_message(self, fmt, *args):
        pass


def serve(model_dir=None, port=PORT):
    """The server, in the foreground. Without `model_dir`: THE server, every project a
    path under it (/p/<key>/), told of each by ensure_server. With one: that model
    alone at the root, as a published folder has it (the desktop program's checks)."""
    _Handler.projects = _Projects(None if model_dir else _store())
    if model_dir:
        _Handler.pinned = pathlib.Path(model_dir).resolve()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print("web view: http://127.0.0.1:%d/   (%s)" % (port, "model from %s" % _Handler.pinned if model_dir else "every project"))
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def _listening(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _ask(port, path, timeout=2.0):
    """A GET to the server on `port`: its JSON answer, or None."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _stop(port, info):
    """Have the cadkit server on `port` end, and wait until the port is free."""
    if info.get("proto", 0) >= 2 and not info.get("pinned") and "dir" not in info:
        _ask(port, "/quit")
    elif os.name == "nt":
        # a server from before there was one for all: it has no way to be asked. It said
        # it is cadkit's (where.json); the process listening there is ended.
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            f = line.split()
            if len(f) >= 5 and f[1] == "127.0.0.1:%d" % port and f[3] == "LISTENING" and f[4].isdigit():
                subprocess.run(["taskkill", "/PID", f[4], "/F"], capture_output=True)
    for _ in range(50):
        if not _listening(port):
            return True
        time.sleep(0.1)
    return False


def ensure_server(model_dir, port=PORT, same_page=False, restart=False):
    """(url, new): `model_dir` shown by THE server, which is started only if none is
    running; otherwise this project JOINS it. `new`: the server had not shown this
    project before (so: open a browser tab for it). There is one port; nothing walks
    to another. A server that answers there but is not up to this cadkit is replaced:
    one from before (a port a project), one of an older protocol, one whose page is
    older than this cadkit's -- or, with `same_page`, is not this cadkit's very page."""
    model_dir = pathlib.Path(model_dir).resolve()
    info = _ask(port, "/where.json") if _listening(port) else None
    if info is not None:
        old = info.get("proto", 0) < PROTO or "dir" in info
        if not old and pathlib.Path(info.get("page", "")) != PAGE:
            try:
                theirs = pathlib.Path(info["page"]).read_bytes()
            except OSError:
                theirs = None
            if theirs != PAGE.read_bytes():
                if same_page or info.get("page_t", 0) < PAGE.stat().st_mtime_ns:
                    old = True
                else:
                    print("web view: the server shows the page of %s, which is newer than this cadkit's "
                          "(`py -m cadkit.web.view --restart` serves this one)" % info["page"])
        if old or restart:
            if not _stop(port, info):
                raise RuntimeError("the older web view server on port %d did not end" % port)
            info = None
    elif _listening(port):
        raise RuntimeError("port %d is held by something that is not cadkit's web view" % port)
    if info is None:
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        package_parent = pathlib.Path(__file__).resolve().parents[2]
        subprocess.Popen([sys.executable, "-m", "cadkit.web.view", "--serve", "--port", str(port)],
                         cwd=str(package_parent), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=flags, close_fds=True)
        for _ in range(50):
            if _listening(port):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("the web view's server did not come up on port %d" % port)
    got = _ask(port, "/open?" + urllib.parse.urlencode({"dir": str(model_dir)}), timeout=5.0)
    if not got or "key" not in got:
        raise RuntimeError("the web view's server did not take %s: %s" % (model_dir, got))
    return "http://127.0.0.1:%d%s" % (port, got["path"]), bool(got["new"])


def _model_dir(root=None):
    """<project>/.webview, made if missing and kept out of git by its own ignore file."""
    out = pathlib.Path(root or os.getcwd()) / ".webview"
    out.mkdir(parents=True, exist_ok=True)
    ign = out / ".gitignore"
    if not ign.exists():
        ign.write_text("*\n")
    return out


def _desktop(out):
    """The desktop app is told the model in `out` is new (it shows it in the project's
    tab, if it is running). True: it is ALSO where the project is to be looked at
    (CADKIT_VIEWER=desktop), so no browser tab is opened. Never raises, never waits."""
    try:
        from . import desktop
        if os.environ.get("CADKIT_VIEWER", "").lower() == "desktop":
            return desktop.open_project(out, focus=False, launch=True)
        desktop.notify(out)
    except Exception:
        pass
    return False


def _open(url, new, open_browser, out=None):
    """Say where the model is. A BUILD NEVER OPENS A BROWSER TAB (`out` given: it prints
    the address, and an open page or the desktop app's tab takes the new model by itself)
    unless CADKIT_VIEWER=browser asks for one; `py -m cadkit.web.view`, run by hand, does."""
    in_app = _desktop(out) if out is not None else False
    print("web view: %s%s" % (url, "   (in the desktop app)" if in_app else "   (an open page reloads itself)"))
    if out is not None and os.environ.get("CADKIT_VIEWER") != "browser":
        return
    if new and open_browser and not in_app:
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
        _open(url, started, open_browser, out)
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
        _open(url, started, open_browser, out)
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
    # WHOSE VIEW THIS IS, AND WHICH OF THEIRS: a model has the lead's build number, and
    # on top of that build each agent exports its own part again and again. So a scratch
    # view is named "build #880 + bronner 14": the 14th this worktree has made. The page
    # shows it, small, and it is how to tell that the view on screen is the latest one.
    try:
        from ..agents import current_agent
        seq = out / "scratch_n.txt"
        n = (int(seq.read_text()) if seq.exists() else 0) + 1
        seq.write_text(str(n))
        stamp.update(agent=current_agent(cwd=getattr(view, "root", None)), n=n)
    except Exception:
        pass
    (out / "stamp.json").write_text(json.dumps(stamp))
    print("web view: %d parts in %.1f s" % (len(meshed), time.time() - t0))
    return out


def scratch_show(view, open_browser=True, port=PORT, **kw):
    """scratch_export(), then the page. Never raises."""
    try:
        out = scratch_export(view, **kw)
        url, started = ensure_server(out, port)
        _open(url, started, open_browser, out)
        return True
    except SystemExit:
        raise
    except Exception as exc:
        print("[web view] not refreshed: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="the cadkit web viewer's local server")
    ap.add_argument("--serve", action="store_true",
                    help="the server, in the foreground (with --dir: that one model, at the root)")
    ap.add_argument("--dir", default=None, help="the model folder (default: ./.webview)")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--restart", action="store_true",
                    help="end the running server and start this cadkit's in its place")
    ap.add_argument("--dev", action="store_true",
                    help="work on the page: the same server shows THIS cadkit's page file under /dev/, "
                         "reloading it on every edit")
    a = ap.parse_args(argv)
    if a.serve:
        serve(a.dir, a.port)
        return 0
    model_dir = pathlib.Path(a.dir) if a.dir else _model_dir()
    url, new = ensure_server(model_dir, a.port, restart=a.restart)
    if a.dev:
        got = _ask(a.port, "/dev?" + urllib.parse.urlencode({"page": str(PAGE)}))
        if not got or not got.get("ok"):
            raise SystemExit("web view: the server did not take the page: %s" % got)
        url = url.replace("/p/", "/dev/p/", 1)
        new = True
    _open(url, new, True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
