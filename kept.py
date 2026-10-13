# -*- coding: utf-8 -*-
"""cadkit.kept — a solid that is drawn once and then read, until something it is made
from changes.

A bought part is the same solid in every build: a toothed belt, a threaded rod, a ball
bearing. Drawing it costs seconds each time and tells nobody anything new.

    from cadkit.kept import kept

    belt = kept(C.belt, motor_xyz, screw_xyz, upper, p, x0, x1, end_a, end_b, tooth)

is `C.belt(...)`, drawn the first time and read from a file after that.

WHAT MAKES A KEPT SOLID THE RIGHT ONE. Its file is named by a hash of everything the
solid can depend on, so a solid whose inputs changed is simply not found, and is drawn:

  * the function's name and every argument, exactly (floats to their last bit);
  * the source text of the module the function is in, and of EVERY module that module
    imports, and those they import, as far as they lie in the project (its vendored
    cadkit included) -- a dimension changed three imports away is a different hash;
  * the versions of cadquery and its kernel.

So the arguments must be plain data (numbers, strings, tuples, lists, dicts of them).
Given anything else the solid is just drawn, every time, and nothing is kept. What the
hash cannot see is state read from OUTSIDE the source: an environment variable, a file.
A function that reads such a thing must not be kept.

The first build draws the solid, writes it, and hands back the solid READ from that
file -- the very one every later build gets -- so a build that drew and a build that
read give the same model, to the byte.

The files live in `.kept/` at the project's root, which ignores itself in git. Deleting
the folder costs one slow build. CADKIT_KEPT=0 draws everything.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import os
import pathlib
import sys

import cadquery as cq

__all__ = ["kept", "tally"]

_SRC = {}                                   # module name -> (hash of its closure) | None
_TALLY = {"read": 0, "drawn": 0, "plain": 0}
_PLAIN = (int, float, str, bool, type(None))


def _root(path: pathlib.Path) -> pathlib.Path:
    """The project a file belongs to: the nearest folder above it holding a `cadkit`."""
    for up in path.resolve().parents:
        if (up / "cadkit").is_dir() or up.name == "cadkit" and (up / "kept.py").is_file():
            return up
    return path.resolve().parent


def _imports(name: str, file: pathlib.Path):
    """Names of the modules `file` imports, anywhere in it (inside functions too)."""
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return
    package = name if file.name == "__init__.py" else name.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom):
            try:
                base = importlib.util.resolve_name("." * node.level + (node.module or ""),
                                                   package) if node.level else node.module
            except (ImportError, ValueError):
                continue
            if not base:
                continue
            yield base
            for a in node.names:                      # `from . import dimensions`
                yield base + "." + a.name


def _file(name: str):
    mod = sys.modules.get(name)
    f = getattr(mod, "__file__", None)
    if f is None and mod is None:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError, AttributeError):
            spec = None
        f = spec.origin if spec is not None and spec.has_location else None
    return pathlib.Path(f) if f and str(f).endswith(".py") else None


def _closure(name: str):
    """sha1 over the source of module `name` and of every project module it reaches."""
    if name in _SRC:
        return _SRC[name]
    start = _file(name)
    if start is None:
        _SRC[name] = None
        return None
    root = _root(start)
    seen, todo = {}, [name]
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        f = _file(n)
        if f is None:
            continue
        try:
            f.resolve().relative_to(root)
        except ValueError:
            continue                                  # not the project's: versions cover it
        seen[n] = f
        todo.extend(_imports(n, f))
    h = hashlib.sha1()
    for n in sorted(seen):
        h.update(n.encode())
        h.update(seen[n].read_bytes().replace(b"\r\n", b"\n"))
    _SRC[name] = (h.hexdigest(), root)
    return _SRC[name]


def _plain(x) -> bool:
    if isinstance(x, _PLAIN):
        return True
    if isinstance(x, (tuple, list)):
        return all(_plain(v) for v in x)
    if isinstance(x, dict):
        return all(isinstance(k, _PLAIN) and _plain(v) for k, v in x.items())
    return False


def _versions() -> str:
    import OCP
    return "%s|%s" % (getattr(cq, "__version__", "?"), getattr(OCP, "__version__", "?"))


def kept(make, *args, **kw) -> cq.Workplane:
    """`make(*args, **kw)`, a cq.Workplane of ONE solid: read from `.kept/` if it has
    been drawn with exactly these arguments and this source, drawn and kept if not."""
    src = _closure(getattr(make, "__module__", "") or "")
    if (os.environ.get("CADKIT_KEPT") == "0" or src is None
            or not _plain(args) or not _plain(kw)):
        _TALLY["plain"] += 1
        return make(*args, **kw)
    digest, root = src
    key = hashlib.sha1(repr((make.__module__, make.__qualname__, args, sorted(kw.items()),
                             digest, _versions())).encode()).hexdigest()
    folder = root / ".kept"
    path = folder / (key + ".brep")
    if not path.is_file():
        made = make(*args, **kw)
        vals = [v for v in made.vals() if isinstance(v, cq.Shape)]
        if len(vals) != 1:
            _TALLY["plain"] += 1
            return made
        folder.mkdir(exist_ok=True)
        ignore = folder / ".gitignore"
        if not ignore.exists():
            ignore.write_text("*\n")
        buf = io.BytesIO()
        vals[0].exportBrep(buf)
        tmp = path.with_suffix(".%d.tmp" % os.getpid())
        tmp.write_bytes(buf.getvalue())
        try:
            os.replace(tmp, path)
        except OSError:                               # another build wrote the same solid
            tmp.unlink(missing_ok=True)
        _TALLY["drawn"] += 1
    else:
        _TALLY["read"] += 1
    return cq.Workplane(obj=cq.Shape.importBrep(io.BytesIO(path.read_bytes())))


def tally() -> str:
    """One line for a build's log: how many kept solids were read and how many drawn."""
    return "kept solids: %(read)d read, %(drawn)d drawn, %(plain)d not kept" % _TALLY
