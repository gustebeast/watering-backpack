# -*- coding: utf-8 -*-
"""cadkit.lazy — a module's solids, built when first USED rather than when imported.

A part module usually ends by building its parts:

    housing = _housing()
    lever = _lever()

which is right for the full build, and wrong for everyone else: a module that imports
this one for a DIMENSION pays for every solid in it, on every run. On the pedal steel,
`src.chassis` reads the knee lever's mounting stations and waited 30 s for a housing,
a lever and an axle it never looks at -- and so did every scratch view of every part
that touches the chassis.

    from cadkit.lazy import lazy

    housing = lazy(_housing)                 # built on first use, then kept
    housing_r = lazy(_housing, right=True)

Nothing that uses `housing` changes. It IS a cq.Workplane to isinstance, and every
attribute, method and operator goes to the real solid, which is built once, the first
time anything needs it, and is the same object ever after. So the same solids come
out, in whatever order they are first needed; the only thing that moves is WHEN the
time is spent. Importing the name, `hasattr`, `dir` and merely LOOKING UP a method
(`housing.val`) do not build it; calling the method, or reading its data, does.

WHAT TO KEEP IN MIND. A builder's own asserts now run when the part is first used, not
at import. The full build uses every part, so nothing goes unchecked there; a tool
that imports a module precisely to have its checks run must say so: `build_all(module)`
builds every lazy solid in it (a project's scratch view does this for the module its
scope names). `built(x)` says whether a solid exists yet; `real(x)` hands over the
plain Workplane.
"""

from __future__ import annotations

import cadquery as cq

__all__ = ["lazy", "real", "built", "build_all"]

_OWN = ("_lazy_build", "_lazy_value", "_lazy_get", "__class__", "__reduce_ex__")


class _Lazy(cq.Workplane):
    def __init__(self, build):                       # deliberately NOT Workplane.__init__
        object.__setattr__(self, "_lazy_build", build)
        object.__setattr__(self, "_lazy_value", None)

    def _lazy_get(self):
        value = object.__getattribute__(self, "_lazy_value")
        if value is None:
            value = object.__getattribute__(self, "_lazy_build")()
            object.__setattr__(self, "_lazy_value", value)
            object.__setattr__(self, "_lazy_build", None)
        return value

    def __getattribute__(self, name):
        if name in _OWN:
            return object.__getattribute__(self, name)
        get = object.__getattribute__(self, "_lazy_get")
        # a METHOD is handed over without building: asking whether the part has a
        # .val (hasattr, the way everything here tells a solid from a list) is free
        if object.__getattribute__(self, "_lazy_value") is None and name in _METHODS:
            return lambda *a, **k: getattr(get(), name)(*a, **k)
        return getattr(get(), name)

    def __dir__(self):
        return dir(cq.Workplane)

    def __reduce_ex__(self, protocol):               # pickled, it is the plain solid
        return (real, (self._lazy_get(),))

    def __setattr__(self, name, value):
        setattr(self._lazy_get(), name, value)

    def __repr__(self):
        v = object.__getattribute__(self, "_lazy_value")
        return "<lazy %s>" % ("(not built yet)" if v is None else repr(v))


_METHODS = frozenset(n for n, v in vars(cq.Workplane).items()
                     if callable(v) and not n.startswith("__"))


def lazy(builder, *args, **kwargs):
    """A stand-in for `builder(*args, **kwargs)` that calls it on first use."""
    return _Lazy(lambda: builder(*args, **kwargs))


def real(obj):
    """The plain object behind a lazy one (building it if need be); anything else as is."""
    return obj._lazy_get() if isinstance(obj, _Lazy) else obj


def build_all(module) -> int:
    """Build every lazy solid `module` holds, so every check its builders carry has
    run. Returns how many there are."""
    mine = [v for v in vars(module).values() if isinstance(v, _Lazy)]
    for v in mine:
        v._lazy_get()
    return len(mine)


def built(obj) -> bool:
    """False only for a lazy solid nothing has asked for yet."""
    return not isinstance(obj, _Lazy) or object.__getattribute__(obj, "_lazy_value") is not None
