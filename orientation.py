# -*- coding: utf-8 -*-
"""cadkit.orientation — ONE declaration of how each printed part meets the bed.

A part's build direction is a fact about the part, and until now every project
stated it TWICE, independently, with nothing checking the two agreed:

  * at EXPORT, as a rotation in the project's ``PRINT_ROT`` table, and
  * at every JOINT the part takes part in, as a ``PrintSpec(facing=...)``
    word ('up'/'down'/'side'/'axial') the author worked out in their head by
    mapping the joint's local axes onto the global ones — the mapping usually
    survives only as a comment beside the call.

Here the part declares its bed face ONCE, as a `PrintOrientation`, and both
consumers read it: `cadkit.step_export.print_pose` poses the STEP with it, and
`facing_for()` derives the joinery word from it plus the joint SITE. They can
no longer disagree, and the local→global mapping is arithmetic instead of
comment.

WHY IT IS REQUIRED, NOT DEFAULTED (cable-spool #1070): export used to read the
table with ``PRINT_ROT.get(name)``, so a MISSING entry and a deliberate "this
models as printed" were the same thing — ``None``. A TPU pin shipped standing
on its end, a 5.9:1 tower, because nobody had ever declared its bed face and
nothing could tell. An omission and a claim are different, so every printed
part must now carry an orientation, and "as modelled" is spelled out.

    from cadkit.orientation import PrintOrientation as PO

    PRINT_ORIENTATION = {
        "lid":    PO("flip", "modelled top is the bed — the slots print clean"),
        "frame":  PO(None, "models as printed"),
        "lever":  PO(((1, 0, 0), -90), "stands on its +y outer face"),
    }

UNCONFIRMED ORIENTATIONS carry `confirmed=False`. That is a RED FLAG, not a
shrug: it means somebody (often an agent migrating a project) made a
best-effort call about a part they had not studied. Any agent that touches
such a part must settle the bed face with the user and set `confirmed=True`
BEFORE doing anything else to it — see `unconfirmed()` and the AGENTS.md rule.

Self-test: ``python -m cadkit.orientation``.
"""

import math

__all__ = ["PrintOrientation", "JointSite", "facing_for", "require_declared",
           "unconfirmed"]

_EPS = 1e-6
_PARALLEL = 0.999          # |dot| above this counts as axis-aligned


# ── small vector helpers (kept local: this module must import cleanly with
#    no CadQuery, so bead/joinery tooling and plain scripts can both use it)
def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    if n < _EPS:
        raise ValueError("direction vector is zero-length: %r" % (v,))
    return tuple(c / n for c in v)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _rotate(v, axis, deg):
    """Rodrigues: `v` turned `deg` about `axis` (right-handed)."""
    k = _unit(axis)
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    kv = _cross(k, v)
    kd = _dot(k, v)
    return tuple(v[i] * c + kv[i] * s + k[i] * kd * (1.0 - c) for i in range(3))


class PrintOrientation:
    """How ONE printed part meets the bed.

    `rot` uses the vocabulary `print_pose` already took, so migrating a
    project's PRINT_ROT table is mechanical:

      None          the part models in its print orientation
      "flip"        180° about X — the modelled TOP face is the bed
      (axis, deg)   anything else, about the origin

    `why` is the reason, in the author's words — it is the part of the
    declaration a reader actually needs ("stands on its head", "the slots
    print clean this way"). Required: a bed face with no reason behind it is
    how the wrong one survives review.

    `confirmed` False means the orientation is a BEST GUESS that nobody has
    checked against the real part. See the module docstring.
    """

    __slots__ = ("rot", "why", "confirmed")

    def __init__(self, rot, why, confirmed=True):
        if rot is not None and rot != "flip":
            try:
                axis, deg = rot
                _unit(axis)
                float(deg)
            except Exception:
                raise ValueError(
                    "rot must be None, 'flip' or (axis, degrees); got %r"
                    % (rot,))
        if not (why and str(why).strip()):
            raise ValueError("a PrintOrientation needs a reason (`why`)")
        self.rot, self.why, self.confirmed = rot, str(why), bool(confirmed)

    @classmethod
    def from_build_dir(cls, build_dir, why, confirmed=True):
        """Declare the BUILD DIRECTION and let the rotation follow.

        Some projects think in directions, not rotations, and rightly: the
        build direction is what the geometry cares about, so it ends up read
        by hole cutters and overhang relief and written into comments ("this
        face is the bed and the part builds toward -Y"). Stating the rotation
        as well then duplicates it. The guitar project kept BOTH, plus a
        hand-rolled Rodrigues assert to stop them drifting — this makes the
        duplicate derived instead, so there is nothing left to drift.

        The rotation is the MINIMAL one taking `build_dir` to +Z. It is not
        unique — any spin about Z afterwards also lands the same face on the
        bed — but the spin only moves the part around on the plate, which
        `print_pose` then re-centres anyway. All six of the guitar's
        hand-written rotations come back out of this exactly.
        """
        v = _unit(build_dir)
        d = _dot(v, (0.0, 0.0, 1.0))
        if d > _PARALLEL:
            return cls(None, why, confirmed)
        if d < -_PARALLEL:
            return cls("flip", why, confirmed)
        axis = _cross(v, (0.0, 0.0, 1.0))
        return cls((_unit(axis), math.degrees(math.acos(max(-1.0,
                                                            min(1.0, d))))),
                   why, confirmed)

    # the rotation print_pose applies, as (axis, degrees) or None
    def _as_axis_deg(self):
        if self.rot is None:
            return None
        return ((1.0, 0.0, 0.0), 180.0) if self.rot == "flip" else self.rot

    @property
    def build_dir(self):
        """The BUILD direction, in the part's own (modelled) coordinates.

        print_pose turns the part by `rot`, so the modelled direction that
        ends up pointing at the sky — the one layers stack along — is the
        INVERSE rotation applied to +Z. 'flip' therefore builds along the
        part's −Z: its modelled top is on the bed.
        """
        ad = self._as_axis_deg()
        if ad is None:
            return (0.0, 0.0, 1.0)
        axis, deg = ad
        return _unit(_rotate((0.0, 0.0, 1.0), axis, -float(deg)))

    def __repr__(self):
        mark = "" if self.confirmed else ", UNCONFIRMED"
        return "PrintOrientation(%r, %r%s)" % (self.rot, self.why, mark)


class JointSite:
    """WHERE a joint sits, in the frame the parts are MODELLED in.

    Two directions, both of which the author already knows and today writes
    in a comment:

      `install_dir`  the direction the mortise host travels to go on
      `normal`       the mating plane's normal — the joint's local +Z

    From these plus each host's PrintOrientation, `facing_for()` derives the
    joinery word, so the local→global mapping is never done by hand.
    """

    __slots__ = ("install_dir", "normal")

    def __init__(self, install_dir, normal):
        self.install_dir = _unit(install_dir)
        self.normal = _unit(normal)

    @property
    def along_normal(self):
        """True when the install runs along the mating normal — the library's
        install='±z' family, where the profile prints as vertical walls."""
        return abs(_dot(self.install_dir, self.normal)) > _PARALLEL

    def __repr__(self):
        return "JointSite(install_dir=%r, normal=%r)" % (self.install_dir,
                                                         self.normal)


def facing_for(orientation, site):
    """The joinery `facing` word for a host with `orientation` at `site`.

    Returns 'up', 'down', 'side' or 'axial' — the values `PrintSpec` takes.
    Raises ValueError when the site and the part's build direction are not
    axis-aligned with each other, or land on a case the library has no word
    for; both are real findings, not inconveniences, so they are loud.
    """
    b = orientation.build_dir
    n, i = site.normal, site.install_dir

    if site.along_normal:
        # install ∥ the mating normal: the library's '±z' family. Both hosts
        # build along that axis and 'up'/'down' already say which way; there
        # is no 'axial' here (see PrintSpec's note).
        d = _dot(b, n)
        if d > _PARALLEL:
            return "up"
        if d < -_PARALLEL:
            return "down"
        raise ValueError(
            "an install-along-normal joint needs its hosts building along "
            "that normal; this one builds across it (dot %.3f). Either the "
            "site's normal is wrong or this part cannot take this joint." % d)

    # x-family: install ⊥ normal.
    d_i = _dot(b, i)
    if abs(d_i) > _PARALLEL:
        return "axial"          # builds along the slide — every face a wall
    d_n = _dot(b, n)
    if d_n > _PARALLEL:
        return "up"
    if d_n < -_PARALLEL:
        return "down"
    y = _cross(n, i)            # the joint's local +Y
    d_y = _dot(b, y)
    if d_y > _PARALLEL:
        return "side"
    if d_y < -_PARALLEL:
        raise ValueError(
            "this host builds along the joint's local −Y, which the library "
            "has no word for ('side' is −Y→+Y only). Flip the site's normal "
            "or install_dir so the joint's frame follows the print.")
    raise ValueError(
        "the part's build direction is not aligned with any of the joint's "
        "axes (build %r vs install %r, normal %r) — one of the three is "
        "wrong." % (b, i, n))


def require_declared(names, table, what="part"):
    """Every name in `names` must have an entry in `table`, and `table` must
    carry nothing else. Raises AssertionError naming BOTH faults.

    The point is that an omission and an explicit "models as printed" stop
    being the same thing (#1070), and that a renamed part cannot leave a
    stale orientation behind that silently matches nobody.
    """
    names, keys = set(names), set(table)
    missing, stale = names - keys, keys - names
    if missing or stale:
        bits = []
        if missing:
            bits.append("%s(s) with no declared print orientation: %s"
                        % (what, ", ".join(sorted(missing))))
        if stale:
            bits.append("orientation declared for unknown %s(s): %s"
                        % (what, ", ".join(sorted(stale))))
        raise AssertionError("; ".join(bits))
    return True


def unconfirmed(table):
    """The names in `table` whose orientation is still a guess — sorted.

    A project's build should SAY these out loud on every run. An agent that
    is about to work on one has to settle it with the user first.
    """
    return sorted(n for n, o in table.items() if not o.confirmed)


def _self_test():
    import itertools

    po = PrintOrientation
    # build_dir
    assert po(None, "x").build_dir == (0.0, 0.0, 1.0)
    bd = po("flip", "x").build_dir
    assert abs(bd[2] + 1.0) < 1e-9, bd
    bd = po(((1, 0, 0), -90), "x").build_dir       # bed = its +y face
    assert abs(bd[1] + 1.0) < 1e-9, bd             # so it builds along −Y
    bd = po(((0, 1, 0), -90), "x").build_dir
    assert abs(bd[0] - 1.0) < 1e-9, bd             # builds along part +X

    # from_build_dir is the inverse of build_dir, for every axis and diagonal
    _S2 = 1.0 / math.sqrt(2.0)
    for v in ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0),
              (0, -1, 0), (-_S2, -_S2, 0.0), (_S2, 0.0, _S2)):
        got = po.from_build_dir(v, "round trip").build_dir
        assert all(abs(got[i] - _unit(v)[i]) < 1e-9 for i in range(3)),             "from_build_dir(%r).build_dir came back %r" % (v, got)
    # and it reproduces the guitar's own hand-written rotations, which are
    # print-proven — this is the check that let that project delete its
    # duplicate table rather than keep asserting against it
    for v, want in (((0, -1, 0), ((1, 0, 0), -90)),
                    ((-_S2, -_S2, 0.0), ((-1, 1, 0), 90)),
                    ((1, 0, 0), ((0, 1, 0), -90)),
                    ((0, 0, 1), None),
                    ((0, 1, 0), ((1, 0, 0), 90))):
        got = po.from_build_dir(v, "guitar").build_dir
        ref = po(want, "guitar").build_dir
        assert all(abs(got[i] - ref[i]) < 1e-9 for i in range(3)), (v, want)

    # facing, x-family: install −y, mating normal +z (the spool's horn rail)
    site = JointSite(install_dir=(0, -1, 0), normal=(0, 0, 1))
    assert not site.along_normal
    assert facing_for(po(None, "x"), site) == "up"
    assert facing_for(po("flip", "x"), site) == "down"
    assert facing_for(po(((0, 1, 0), -90), "x"), site) == "side"   # builds +X
    assert facing_for(po(((1, 0, 0), 90), "x"), site) == "axial"   # builds −Y

    # z-family: install along the normal
    zsite = JointSite(install_dir=(0, 0, 1), normal=(0, 0, 1))
    assert zsite.along_normal
    assert facing_for(po(None, "x"), zsite) == "up"
    assert facing_for(po("flip", "x"), zsite) == "down"
    for bad in (((1, 0, 0), -90), ((0, 1, 0), -90)):
        try:
            facing_for(po(bad, "x"), zsite)
        except ValueError:
            pass
        else:
            raise AssertionError("z-family sideways build should raise")

    # the vocabulary gap is loud, not silent
    try:
        facing_for(po(((0, 1, 0), 90), "x"), site)     # builds −X = local −Y
    except ValueError as e:
        assert "no word" in str(e)
    else:
        raise AssertionError("local −Y build should raise")

    # require_declared names both faults
    try:
        require_declared({"a", "b"}, {"a": po(None, "x"), "c": po(None, "x")})
    except AssertionError as e:
        assert "b" in str(e) and "c" in str(e), e
    else:
        raise AssertionError("require_declared should have raised")

    # a reason is not optional
    for bad in ("", None, "   "):
        try:
            po(None, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("empty `why` should raise")

    assert unconfirmed({"a": po(None, "x"),
                        "b": po(None, "x", confirmed=False)}) == ["b"]
    print("cadkit.orientation: all self-tests pass")


if __name__ == "__main__":
    _self_test()
