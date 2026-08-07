# -*- coding: utf-8 -*-
"""cadkit.bead_check — the shared bead-grid audit engine.

Walks every module-level UPPERCASE numeric constant in a project's constants
package and reports the ones whose printed lengths are off the bead grid
(cadkit.printing documents the rule and its three legitimate exemptions).
Same division of labour as cadkit.overlap_check: this module is the engine,
each project ships a thin `tools/check_beads.py` that supplies its package,
its default nozzle and an EXEMPTION table with a written reason per entry.

THE TWO TESTS (conflating them is why a naive checker is useless):

  BARE LITERAL   (WALL_T = 2.0)         -> the VALUE must be on the grid.
  DERIVED        (Y_HI = AXLE_Y + 3.0)  -> the OFFSETS must be on the grid.
                                           The RESULT usually is not, and must
                                           not be forced to be: it inherits a
                                           hardware or domain datum, and what
                                           the printer cares about is the
                                           material you ADDED — the +3.0.

So a derived constant passes iff every numeric literal in its expression is
on-grid (or exempt), whatever the result evaluates to. Corollary: an off-grid
derived value usually means a PARENT is off-grid — or is a stale spelled copy
of a datum that moved, which the audits keep finding (see printing.py).

WHAT IS AUTOMATICALLY SKIPPED, no exemption needed:
  * counts and angles by NAME: an `N_` prefix, or any of NON_LENGTH's
    substrings (COUNT, TURNS, _DEG, ANGLE, TEETH, THROW, ...)
  * STRUCTURAL literals: the /2 of a centre-line, 90/180/270/360 degrees,
    0 and 1 — arithmetic, not material
  * the coefficient of an `n * BEAD` product (BEAD_NAMES): `13 * BEAD` states
    a length in the grid's own unit, so the 13 is a COUNT — flagging it would
    reject the very idiom the grid is written in
  * a module's own NOZZLE_D (it IS the grid; declaring one also grades that
    module against its own finer grid — the grid is a property of the PART)

DRIVER SHAPE (see the pedal-steel's tools/check_beads.py for a full example):

    from cadkit import bead_check
    EXEMPT = {}
    def _ex(cat, **kv):     # "mod__NAME" pins an entry to one module
        for k, v in kv.items():
            EXEMPT[k.replace("__", ".")] = (cat, v)
    _ex("hardware",  MOTOR_SQ="NEMA17 body 42.3 sq", ...)
    _ex("clearance", FIT_CLR="slip fit", ...)
    _ex("musical",   MOUNTING_SPAN="scale length", ...)
    if __name__ == "__main__":
        raise SystemExit(bead_check.cli(
            src=pathlib.Path(__file__).resolve().parent.parent / "src",
            package="src", exempt=EXEMPT, default_nozzle=0.8))

Keep every reason SPECIFIC — "it's hardware" is not a reason, "MR85 bearing
OD" is. Categories are free-form; the conventional four are hardware /
clearance / musical (domain) / layout (where purchased parts sit, tuned knobs
pinned by asserts, rib-comb stations and the like).
"""

from __future__ import annotations

import argparse
import ast
import importlib
import pathlib

from .printing import on_grid

# Literals that are never a length, so the grid does not apply: array indices,
# the /2 of a centre-line, 360 degrees of a circle, unit scale factors.
STRUCTURAL = {0.0, 1.0, 2.0, 90.0, 180.0, 270.0, 360.0}

# Names that ARE the bead: `13 * BEAD` states a length in grid units, so the
# 13 is a COUNT, not a length to check.
BEAD_NAMES = {"BEAD", "B", "NOZZLE_D", "MIN_WALL"}

# Constants that are not lengths at all, by name substring. An `N_` PREFIX is
# also treated as a count (N_PEDALS, N_SLOTS) — see _is_length_name.
NON_LENGTH = ("N_STRINGS", "N_TEETH", "SEGMENTS", "COUNT", "_N", "TURNS",
              "_DEG", "ANGLE", "TEETH", "THROW")


def _is_length_name(name: str, non_length=NON_LENGTH) -> bool:
    return not (name.startswith("N_") or any(k in name for k in non_length))


def _is_bead_unit(node: ast.AST, bead_names=BEAD_NAMES) -> bool:
    return (isinstance(node, ast.Name) and node.id in bead_names) or (
        isinstance(node, ast.Attribute) and node.attr in bead_names)


def _offsets(node: ast.AST, structural=STRUCTURAL, bead_names=BEAD_NAMES) -> list:
    """Numeric literals in an expression that act as LENGTHS.

    STRUCTURAL literals and the coefficients of `n * BEAD` products are
    skipped (see module docstring); everything else in a geometry expression
    is an offset someone chose, and is fair game."""
    skip = set()

    def _skip_subtree(sub: ast.AST) -> None:
        # the whole operand, not just a bare Constant: `-13 * B` parses as
        # UnaryOp(13) * B, so skipping only the top node still leaves the 13
        for k in ast.walk(sub):
            skip.add(id(k))

    for n in ast.walk(node):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult):
            if _is_bead_unit(n.right, bead_names):
                _skip_subtree(n.left)
            if _is_bead_unit(n.left, bead_names):
                _skip_subtree(n.right)
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) \
           and not isinstance(n.value, bool) and id(n) not in skip:
            if abs(float(n.value)) not in structural:
                out.append(float(n.value))
    return out


def module_nozzle(package: str, mod_name: str, default: float) -> float:
    """This module's nozzle: its own NOZZLE_D if it declares one, else the
    project default. THE GRID IS A PROPERTY OF THE PART (user) — a part whose
    detail is finer than a bead can resolve prints finer and is graded on ITS
    grid (the pedal-steel's belt clamp: GT2 teeth at 0.2)."""
    mod = importlib.import_module(package + "." + mod_name)
    n = getattr(mod, "NOZZLE_D", None)
    if isinstance(n, (int, float)) and not isinstance(n, bool) and n > 0:
        return float(n)
    return float(default)


def module_constants(src: pathlib.Path, package: str, mod_name: str,
                     non_length=NON_LENGTH):
    """(name, value, line, kind, offsets) per module-level UPPERCASE constant.

    kind is 'literal' (RHS is a bare number -> check the value) or 'derived'
    (RHS references something -> check the offsets it adds to that something).
    Tuple assignments are NOT walked — a known blind spot, kept on purpose:
    they are overwhelmingly hardware footprints and coordinate pairs."""
    text = (src / (mod_name + ".py")).read_text(encoding="utf-8")
    mod = importlib.import_module(package + "." + mod_name)
    out = []
    for node in ast.parse(text).body:
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if not (isinstance(t, ast.Name) and t.id.isupper()):
                continue
            v = getattr(mod, t.id, None)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            if not _is_length_name(t.id, non_length):    # a count or an angle
                continue
            bare = isinstance(node.value, ast.Constant) or (
                isinstance(node.value, ast.UnaryOp)
                and isinstance(node.value.operand, ast.Constant))
            kind = "literal" if bare else "derived"
            out.append((t.id, float(v), node.lineno, kind,
                        [] if bare else _offsets(node.value)))
    return out


def run(src: pathlib.Path, package: str, exempt: dict, default_nozzle: float,
        only=None, show_all: bool = False, non_length=NON_LENGTH) -> int:
    """Audit every module in `src`; print the report; return the finding count.

    exempt: {name_or_dotted_name: (category, reason)} — a bare name matches in
    EVERY module; "mod.NAME" pins it to one."""

    def classify(name, mod):
        return exempt.get("%s.%s" % (mod, name)) or exempt.get(name)

    mods = sorted(p.stem for p in src.glob("*.py") if p.stem != "__init__")
    if only:
        want = {s.strip() for s in only.split(",")} if isinstance(only, str) else set(only)
        mods = [m for m in mods if m in want]

    findings, exempted = [], []
    n_on = n_tot = 0

    nozzles = {}
    for m in mods:
        nz = nozzles[m] = module_nozzle(package, m, default_nozzle)
        for name, v, line, kind, offs in module_constants(src, package, m, non_length):
            if name == "NOZZLE_D":       # the grid itself, not a length on it
                continue
            n_tot += 1
            cat = classify(name, m)
            if kind == "literal":
                bad = [] if on_grid(v, nz) else [v]
            else:
                # derived: the RESULT may sit anywhere (it inherits a musical
                # or hardware datum); what must be on-grid is what we ADDED
                bad = [o for o in offs if not on_grid(o, nz)]
            if not bad:
                n_on += 1
                continue
            if cat:
                exempted.append((m, name, v, cat[0], cat[1]))
                continue
            for o in bad:
                findings.append((m, name, line, kind, o))

    print("bead grid = %.2f mm (project default nozzle)" % default_nozzle)
    fine = {m: n for m, n in nozzles.items() if abs(n - default_nozzle) > 1e-9}
    if fine:
        print("per-part grids: " + ", ".join(
            "%s %.2f" % (m, n) for m, n in sorted(fine.items())))
    print("%d module constants: %d clean, %d exempt, %d with OFF-GRID lengths"
          % (n_tot, n_on, len(exempted),
             len({(f[0], f[1]) for f in findings})))

    if show_all and exempted:
        print("\nexempt (off-grid on purpose):")
        for m, name, v, cat, why in sorted(exempted):
            print("  %-9s %-22s %9.3f  %-9s %s" % (m, name, v, cat, why))

    if findings:
        print("\nOFF GRID -- snap these, or add an exemption with a reason.")
        print("('derived' shows the OFFSET at fault, not the constant's value.)")
        cur = None
        for m, name, line, kind, o in sorted(findings):
            if m != cur:
                print("\n  -- %s/%s.py --" % (src.name, m))
                cur = m
            nz = nozzles[m]
            b = abs(o) / nz
            print("    :%-4d %-24s %-8s %9.3f = %6.2f beads -> %.2f or %.2f"
                  % (line, name, kind, o, b, int(b) * nz, (int(b) + 1) * nz))
    else:
        print("\nclean: every printed length is a whole number of beads.")
    return len({(f[0], f[1]) for f in findings})


def cli(src: pathlib.Path, package: str, exempt: dict, default_nozzle: float,
        argv=None, non_length=NON_LENGTH) -> int:
    """argparse wrapper for a project's thin tools/check_beads.py driver."""
    ap = argparse.ArgumentParser(
        description="bead-grid audit (cadkit.bead_check engine)")
    ap.add_argument("--all", action="store_true", help="list exempt constants too")
    ap.add_argument("--only", help="comma-separated module names")
    a = ap.parse_args(argv)
    return run(src, package, exempt, default_nozzle,
               only=a.only, show_all=a.all, non_length=non_length)


if __name__ == "__main__":
    # engine self-test: pure-AST pieces (no project import needed)
    def _expr(src):
        return ast.parse(src, mode="eval").body

    assert _offsets(_expr("AXLE_Y + 3.0")) == [3.0]
    assert _offsets(_expr("X / 2 + 180")) == []          # structural
    assert _offsets(_expr("13 * BEAD")) == []            # count of beads
    assert _offsets(_expr("-13 * B + 1.75")) == [1.75]   # UnaryOp coefficient skipped
    assert _offsets(_expr("D.BEAD * 9 - 0.3")) == [0.3]  # Attribute bead unit
    assert _is_length_name("WALL_T") and _is_length_name("HS_Z")
    assert not _is_length_name("N_PEDALS")               # N_ prefix = count
    assert not _is_length_name("THROW_V")                # an angle
    assert not _is_length_name("CARRIAGE_NOM_Z"), \
        "known quirk: _N substring — document, don't rely on it"
    print("cadkit.bead_check self-test OK")
