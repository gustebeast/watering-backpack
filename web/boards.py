"""Circuit boards in the web view with their REAL parts on them, not boxes.

The CAD draws a board as its laminate plus one box per footprint (cadkit/board_geom):
right for clearances, wrong to look at. KiCad's library has a coloured STEP model for
most of those footprints, and each board's geom.json says which model each footprint
names (cadkit/kicad_geom, "models"). This module swaps the boxes for the models IN THE
WEB EXPORT ONLY. The CAD, its gates and the STEP files are untouched.

    detail(meshed, shape_of, boards)      # cadkit.web.export calls it, given boards=

HOW A BOARD IS FOUND IN THE ASSEMBLY. Nothing records where a module put its board:
each calls BOARDS.solid(...) and moves the result as it likes. But every board also
places its LETTERING (BOARDS.ink), unmodified, and the lettering's corners are a rigid
copy of the reference's. So the pose is fitted: a part whose corner count equals a
board's reference lettering is matched to it by a registration that does not depend on
vertex order, and accepted only if every corner lands within a micron. The board's own
solid is then the part that holds the laminate's corners at that pose.

WHAT HAPPENS TO THE BOXES. A footprint gets a model only if this instance actually
draws that footprint: one of its box's top corners is in the solid, or (a board drawn
by hand) something stands on the footprint -- a package envelope of another size, a
side-entry header drawn mated, or a part of its own beside the board. The model is
KiCad's file where this machine has it and, placed by KiCad's own rule, it lands on the
footprint's F.Fab box; where KiCad's library has no file, the part is drawn by
cadkit.web.parts. What the model replaces is then cut off the board's solid. Anything
that fails keeps its box, and the run says how many did and why (set WEB_BOARDS_WHY to
have each named). A machine without KiCad's models gets the drawn parts and boxes.

A JST HEADER ALSO GETS ITS PLUG. Every XH / PH / ZH header that got a model is shown
mated: the crimp housing (XHP-n, PHR-n, ZHR-n) seated in it, a part of its own named
<board part>__<ref>_plug, so it is selected and hidden with its board like the header is
and can be picked out by name. It is Boards.plug_solid(): the same record
Boards.wire_exit() answers from, so a wire drawn to that point ends in the drawn cavity.
No plug is drawn where the project says nothing is plugged in (Boards(unmated=...)), or
where the assembly already has a part of its own standing where the plug would (a cable
drawn with its housing). And the room the CAD reserves for a mated side-entry plug -- a
block past the header's mouth, on the board's solid -- is cut away with the header's box:
it is a clearance envelope, right for the gates and not a thing to look at.

THE PLACEMENT RULE is KiCad's (pcbnew/exporters/step, getModelLocation), in the board
frame geom.json uses (centred, +Y up, underside at z = 0):
    board <- T(x, y, top ? thickness : 0) . Rz(rot) . [bottom: Rx(180)]
             . T(offset) . Rz(-rz) . Ry(-ry) . Rx(-rx) <- model
"""

from __future__ import annotations

import glob
import json
import math
import os
import pathlib
import pickle

import numpy as np

MODEL_TOLERANCE = 0.03        # chord error for a component model: parts are small
from . import parts as WP

SEP = "__"                    # <board part>__<ref> names a component's own part
LOOSE = 0.25                  # how far outside its F.Fab box a hand-drawn body may stand
ENVELOPE = 1.2                # ...and a package envelope drawn with its leads
PLUG = 9.0                    # a mated side-entry header: its plug's reach past the mouth
PLUG_PART = "_plug"           # <board part>__<ref>_plug names a header's crimp housing
PLUG_RGB = WP.CREAM           # natural nylon, like the header it is seated in
BACK = 0.8                    # ...and how far its back may stand off the F.Fab box


# ── where KiCad keeps its models ──────────────────────────────────────────────────
def _model_dirs():
    out = {}
    for k, v in os.environ.items():
        if k.startswith("KICAD") and k.endswith("_3DMODEL_DIR") and os.path.isdir(v):
            out[k] = v
    cands = (glob.glob("C:/Program Files/KiCad/*/share/kicad/3dmodels")
             + glob.glob("/usr/share/kicad/3dmodels")
             + glob.glob("/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels"))
    return out, (sorted(cands)[-1] if cands else None)


def resolve_model(path, _dirs=[]):
    """A model path as the footprint writes it -> a file on this machine, or None."""
    if not _dirs:
        _dirs.append(_model_dirs())
    env, default = _dirs[0]
    p = path
    if p.startswith("${"):
        var, _, rest = p[2:].partition("}")
        base = env.get(var) or default
        if not base:
            return None
        p = base + rest
    for cand in (p, os.path.splitext(p)[0] + ".step", os.path.splitext(p)[0] + ".stp"):
        if os.path.isfile(cand) and cand.lower().endswith((".step", ".stp")):
            return cand
    return None


def library_models(name, _index={}):
    """KiCad's own model of the footprint called `name`, as a footprint would name it
    ([{file, offset, rot, scale}]), or []. For a board whose footprints name no model: one
    laid out by script from footprints that carry none, or a project's own footprint
    library. A library footprint and its model share a name, so the name finds it."""
    if not _index:
        _index[""] = None
        env, default = _model_dirs()
        for base in [default] + list(env.values()):
            for p in glob.glob(os.path.join(base, "*.3dshapes", "*.step")) if base else ():
                _index.setdefault(os.path.basename(p)[:-len(".step")], p.replace("\\", "/"))
    p = _index.get(name)
    return [{"file": p, "offset": [0.0, 0.0, 0.0], "rot": [0.0, 0.0, 0.0],
             "scale": [1.0, 1.0, 1.0]}] if p else []


def _models(f):
    """The models footprint record `f` is shown with: its own, else the library's."""
    return f.get("models") or library_models(f["fpid"].split(":")[-1])


def load_model(path):
    """A STEP model -> (compound, [(face, (r, g, b) or None)]): colours as the file
    gives them, a face's own first, else its solid's."""
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorSurf, XCAFDoc_ColorGen
    from OCP.TDF import TDF_LabelSequence
    from OCP.Quantity import Quantity_Color
    from OCP.TopoDS import TopoDS_Iterator, TopoDS_Compound
    from OCP.TopAbs import TopAbs_FACE
    from OCP.BRep import BRep_Builder
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    rd = STEPCAFControl_Reader()
    rd.SetColorMode(True)
    rd.SetNameMode(False)
    if rd.ReadFile(path) != 1:
        raise IOError("cannot read " + path)
    rd.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    free = TDF_LabelSequence()
    st.GetFreeShapes(free)
    comp, bb = TopoDS_Compound(), BRep_Builder()
    bb.MakeCompound(comp)
    cols = []

    def own(s):
        c = Quantity_Color()
        for t in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen):
            if ct.GetColor(s, t, c):
                return (c.Red(), c.Green(), c.Blue())
        return None

    def walk(s, inherited):
        c = own(s) or inherited
        if s.ShapeType() == TopAbs_FACE:
            cols.append((s, c))
            return
        it = TopoDS_Iterator(s)
        while it.More():
            walk(it.Value(), c)
            it.Next()

    for i in range(1, free.Length() + 1):
        s = st.GetShape_s(free.Value(i))
        bb.Add(comp, s)
        walk(s, None)
    return comp, cols


_MODELS = {}


def model_mesh(path):
    """mesh_shape() of a model file, with per-vertex colour; None if it will not load."""
    if path not in _MODELS:
        from .export import mesh_shape, ANGULAR
        try:
            comp, cols = load_model(path)
            _MODELS[path] = mesh_shape(comp, MODEL_TOLERANCE, ANGULAR, face_colors=cols, copy=False)
        except Exception as exc:
            print("web boards: %s will not load (%s)" % (os.path.basename(path), exc))
            _MODELS[path] = None
    return _MODELS[path]


# ── small rigid-transform kit (4x4, column vectors) ───────────────────────────────
def _T(x, y, z):
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def _R(axis, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    i, j = {"x": (1, 2), "y": (2, 0), "z": (0, 1)}[axis]
    m[i, i], m[i, j], m[j, i], m[j, j] = c, -s, s, c
    return m


def footprint_matrix(f, model, thickness):
    ox, oy, oz = model["offset"]
    rx, ry, rz = model["rot"]
    m = _T(f["x"], f["y"], 0.0 if f["side"] == "B" else thickness) @ _R("z", f["rot"])
    if f["side"] == "B":
        m = m @ _R("x", 180.0)
    return m @ _T(ox, oy, oz) @ _R("z", -rz) @ _R("y", -ry) @ _R("x", -rx)


def _apply(m, pts):
    return pts @ m[:3, :3].T + m[:3, 3]


# ── finding a board in the assembly ───────────────────────────────────────────────
def _frames(P, k=3):
    """Candidate frames of a point set, built from points a rigid motion cannot move
    relative to the rest: the centroid, a point far from it, and a point far from that.
    Several candidates, because "the farthest" is a tie on a symmetric layout and
    float32 noise picks a different winner each side."""
    c = P.mean(0)
    d = np.linalg.norm(P - c, axis=1)
    out = []
    for i in np.argsort(-d)[:k]:
        a1 = P[i]
        d1 = np.linalg.norm(P - a1, axis=1)
        for j in np.argsort(-d1)[:k]:
            x = a1 - c
            z = np.cross(x, P[j] - c)
            if np.linalg.norm(x) < 1e-6 or np.linalg.norm(z) < 1e-6:
                continue
            x, z = x / np.linalg.norm(x), z / np.linalg.norm(z)
            m = np.eye(4)
            m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x, np.cross(z, x), z, c
            out.append(m)
    return out


def _nearest(A, B):
    """For each row of A the index of the nearest row of B (brute force, in slices)."""
    out = np.empty(len(A), dtype=np.int64)
    for s in range(0, len(A), 512):
        d = ((A[s:s + 512, None, :] - B[None, :, :]) ** 2).sum(-1)
        out[s:s + 512] = d.argmin(1)
    return out


def fit_pose(ref, pts, tol=2e-3):
    """The proper rigid motion taking `ref` onto `pts` (the same corners, in any order),
    or None. A first guess from matching frames, each corner paired with its nearest
    under that guess, then the least-squares motion for the pairing; accepted only if
    the pairing is one-to-one and every corner lands within `tol`."""
    if len(ref) != len(pts) or len(ref) < 4:
        return None
    ref, pts = np.asarray(ref, dtype=float), np.asarray(pts, dtype=float)
    fa = _frames(ref, 1)
    if not fa:
        return None
    inv_a = np.linalg.inv(fa[0])
    for fb in _frames(pts):
        guess = fb @ inv_a
        moved = _apply(guess, ref)
        idx = _nearest(moved, pts)
        if len(np.unique(idx)) != len(idx) or np.abs(moved - pts[idx]).max() > 0.05:
            continue
        A, B = ref, pts[idx]
        ca, cb = A.mean(0), B.mean(0)
        U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
        if np.linalg.det(Vt.T @ U.T) < 0:
            continue                   # a mirror image is not this board
        R = Vt.T @ U.T
        t = cb - R @ ca
        if np.abs(A @ R.T + t - B).max() > tol:
            continue
        m = np.eye(4)
        m[:3, :3], m[:3, 3] = R, t
        return m
    return None


def _reference_inks(boards, cache_dir):
    """{(board, refs): corner array} for every board with a part there is a model for
    (KiCad's, or one drawn by cadkit.web.parts), cached on the geom file's time (drawing
    the lettering costs seconds a board)."""
    from .export import shape_vertices, _topods
    out = {}
    geom_dir = pathlib.Path(boards.geom_dir)
    if cache_dir is not None:
        pathlib.Path(cache_dir).mkdir(parents=True, exist_ok=True)
    for path in sorted(geom_dir.glob("*.geom.json")):
        board = path.name[:-len(".geom.json")]
        g = json.loads(path.read_text(encoding="utf-8"))
        if not any(_models(f) or WP.knows(f["fpid"].split(":")[-1]) for f in g["footprints"]):
            continue
        cf = pathlib.Path(cache_dir) / (board + ".ink.pkl") if cache_dir is not None else None
        key = (path.stat().st_size, path.stat().st_mtime_ns)
        got = None
        if cf is not None and cf.exists():
            try:
                k, got = pickle.loads(cf.read_bytes())
                if k != key:
                    got = None
            except Exception:
                got = None
        if got is None:
            got = {}
            for refs in (True, False):
                try:
                    got[refs] = shape_vertices(_topods(boards.ink(board, refs=refs)))
                except Exception:
                    pass
            if cf is not None:
                cf.write_bytes(pickle.dumps((key, got)))
        for refs, v in got.items():
            out[(board, refs)] = v
    return out


def _own_part(f, h, t, pose, panel, edge=None):
    """A part drawn by cadkit.web.parts, meshed where it stands: a mesh_shape() result
    with per-vertex colour, or None when there is no generator for it (or it fails: a
    box is a complete model, so this never costs the export)."""
    from .export import mesh_shape, ANGULAR
    from OCP.gp import gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.TopoDS import TopoDS_Compound
    from OCP.BRep import BRep_Builder
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    try:
        parts = WP.build(f, h, t, panel, edge)
        if not parts:
            return None
        R, tr = pose[:3, :3], pose[:3, 3]
        trsf = gp_Trsf()
        trsf.SetValues(R[0, 0], R[0, 1], R[0, 2], tr[0], R[1, 0], R[1, 1], R[1, 2], tr[1],
                       R[2, 0], R[2, 1], R[2, 2], tr[2])
        comp, bb, cols = TopoDS_Compound(), BRep_Builder(), []
        bb.MakeCompound(comp)
        boxes = [s.BoundingBox() for s, _ in parts]                 # in the board's frame
        lo = (min(b.xmin for b in boxes), min(b.ymin for b in boxes), min(b.zmin for b in boxes))
        hi = (max(b.xmax for b in boxes), max(b.ymax for b in boxes), max(b.zmax for b in boxes))
        for s, rgb in parts:
            placed = BRepBuilderAPI_Transform(s.wrapped, trsf, True).Shape()
            bb.Add(comp, placed)
            lin = tuple(c ** 2.2 for c in rgb)          # glTF vertex colour is linear
            ex = TopExp_Explorer(placed, TopAbs_FACE)
            while ex.More():
                cols.append((ex.Current(), lin))
                ex.Next()
        return mesh_shape(comp, MODEL_TOLERANCE, ANGULAR, face_colors=cols, copy=False), (lo, hi)
    except Exception as exc:
        print("web boards: %s (%s) could not be drawn: %s" % (f["ref"], f["fpid"], exc))
        return None


def _plug_part(boards, board, ref, pose):
    """The crimp housing seated in JST header `ref` (Boards.plug_solid), meshed where the
    board is: a mesh_shape() result of ONE colour (the export gives it PLUG_RGB and the
    nylon finish), or None for a part there is no housing for."""
    from .export import mesh_shape, ANGULAR, _topods
    from OCP.gp import gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    try:
        solid = boards.plug_solid(board, ref)
        if solid is None:
            return None
        R, tr = pose[:3, :3], pose[:3, 3]
        trsf = gp_Trsf()
        trsf.SetValues(R[0, 0], R[0, 1], R[0, 2], tr[0], R[1, 0], R[1, 1], R[1, 2], tr[1],
                       R[2, 0], R[2, 1], R[2, 2], tr[2])
        placed = BRepBuilderAPI_Transform(_topods(solid), trsf, True).Shape()
        return mesh_shape(placed, MODEL_TOLERANCE, ANGULAR, copy=False)
    except Exception as exc:
        print("web boards: %s %s -- its plug could not be drawn: %s" % (board, ref, exc))
        return None


def _has(points, p, tol=0.01):
    return bool((np.abs(points - p).max(axis=1) < tol).any()) if len(points) else False


def detail(meshed, shape_of, boards, cache_dir=None, log=print):
    """Swap footprint boxes for KiCad's models.

    meshed   {name: mesh_shape() result}, edited in place: a board's solid is re-meshed
             without the boxes that got a model, and each model is added as its own part
             named <board part>__<ref>.
    shape_of name -> the part's solid (cq.Workplane / cq.Shape / TopoDS_Shape); called
             only for the few board solids that have to be cut.
    Returns {model key: geo record} for the sidecar's shared table."""
    import cadquery as cq
    from .export import mesh_shape, _topods
    models_geo = {}
    if _model_dirs()[1] is None and not _model_dirs()[0]:
        log("web boards: KiCad's 3D models are not on this machine -- boards keep their boxes")
        return models_geo
    inks = _reference_inks(boards, cache_dir)
    if not inks:
        return models_geo
    panel = getattr(boards, "PANEL", None) or {}
    geom_dir = pathlib.Path(boards.geom_dir)
    by_count = {}
    for key, v in inks.items():
        by_count.setdefault(len(v), []).append(key)
    found = []                                   # (board, pose, ink part)
    for name, m in meshed.items():
        v = m.get("verts")
        if v is None or len(v) not in by_count:
            continue
        for board, refs in by_count[len(v)]:
            pose = fit_pose(inks[(board, refs)], v.astype(float))
            if pose is not None:
                found.append((board, pose, name))
                break
    stats = {"boards": 0, "models": 0, "kept": {}, "plugs": 0, "theirs": 0}
    why = bool(os.environ.get("WEB_BOARDS_WHY"))
    # every part's box, to tell a plug the project already draws from an empty header
    boxes_of = {n: (m["pos"].min(0), m["pos"].max(0)) for n, m in meshed.items()
                if SEP not in n and len(m.get("pos", ())) and "inst" not in m}

    def keep(why):
        stats["kept"][why] = stats["kept"].get(why, 0) + 1

    used = set(n for _, _, n in found)
    per_board, counts = [], {}
    for board, pose, ink_name in found:
        g = json.loads((geom_dir / (board + ".geom.json")).read_text(encoding="utf-8"))
        t = g["thickness_mm"]
        poly = g.get("outline_poly") or [(-g["outline_mm"][0] / 2, -g["outline_mm"][1] / 2),
                                         (g["outline_mm"][0] / 2, -g["outline_mm"][1] / 2),
                                         (g["outline_mm"][0] / 2, g["outline_mm"][1] / 2),
                                         (-g["outline_mm"][0] / 2, g["outline_mm"][1] / 2)]
        corners = _apply(pose, np.array([(x, y, z) for x, y in poly for z in (0.0, t)]))
        edge = (min(p[0] for p in poly), max(p[0] for p in poly),
                min(p[1] for p in poly), max(p[1] for p in poly))
        centre = _apply(pose, np.array([[0.0, 0.0, t / 2.0]]))[0]
        solid_name, best = None, 0.0
        for name, m in meshed.items():
            if name in used or SEP in name or m.get("verts") is None:
                continue
            lo, hi = m["pos"].min(0) - 0.01, m["pos"].max(0) + 0.01
            if not ((centre >= lo).all() and (centre <= hi).all()):
                continue
            v = m["verts"]
            share = sum(_has(v, c) for c in corners) / len(corners)
            if share > best:
                solid_name, best = name, share
        if solid_name is None or best < 0.5:
            keep("no solid found for the board at %s" % ink_name)
            continue
        per_board.append("%s<-%s" % (solid_name, board))
        used.add(solid_name)
        sv = meshed[solid_name]["verts"]
        local = _apply(np.linalg.inv(pose), sv.astype(float))    # the solid's corners, board frame
        cut, added, drawn = [], 0, 0

        def mate(f, h, on_board=True):
            """Header `f` got its model: clear the room the CAD reserved for its plug off
            the board's solid, and seat the plug itself."""
            try:
                rec = boards.plug(board, f["ref"]) if hasattr(boards, "plug") else None
            except Exception as exc:
                log("web boards: %s %s -- no plug (%s)" % (solid_name, f["ref"], exc))
                return
            if rec is None:
                return
            if rec["side"] and on_board:
                # THE MATED ENVELOPE, past the mouth: as wide as the header, as far as any
                # project reserves (PLUG), from the board's face up. A board drawn by hand
                # unions one such block per connector into ONE solid along a row, and its
                # corners then say nothing about where one connector's part of it ends --
                # so the room is cleared by where the routed board says the mouth is
                fx0, fx1, fy0, fy1 = f["fab"]
                ox, oy = rec["out"][0], rec["out"][1]
                # (`face` is the mouth's place along `out`; 0.02 back from it, so no
                # skin of the block is left standing on the header's own cut)
                face, sgn = rec["face"], (ox if abs(ox) > 0.5 else oy)
                a, b = sorted((sgn * (face - 0.02), sgn * (face + PLUG)))
                if abs(ox) > 0.5:
                    bx0, bx1, by0, by1 = a, b, fy0 - 0.5, fy1 + 0.5
                else:
                    bx0, bx1, by0, by1 = fx0 - 0.5, fx1 + 0.5, a, b
                top = max(h or 0.0, 8.0)
                cut.append((bx0, bx1, by0, by1) + ((-top - 0.05, -0.005) if f["side"] == "B"
                                                    else (t + 0.005, t + top + 0.05)))
            if (board, f["ref"]) in getattr(boards, "UNMATED", ()):
                return
            pm = _plug_part(boards, board, f["ref"], pose)
            if pm is None:
                return
            # IS THE PLUG ALREADY THERE? A project that draws a cable with its housing has
            # a part standing where this one would: something about a plug's size that
            # fills most of the room the plug takes OUTSIDE its header (a project draws
            # its housing in front of the mouth, not down in the pocket) and is as broad
            # as the housing there, along the row and across it -- which a wire that ends
            # in the plug is not, though its box can cover the same room.
            lo, hi = pm["pos"].min(0), pm["pos"].max(0)
            whole = float(np.prod(hi - lo))
            out_w = pose[:3, :3] @ np.array(rec["out"])
            back = float((_apply(pose, np.array([rec["o"]]))[0] * out_w).sum())
            shown = pm["pos"][(pm["pos"].astype(float) @ out_w) > back - rec["proud"] - 0.01]
            lo, hi = shown.min(0), shown.max(0)
            vol = float(np.prod(hi - lo))
            across = [pose[:3, :3] @ np.array(rec[k]) for k in ("row", "up")]
            need = [float(np.ptp(shown.astype(float) @ a)) for a in across]
            for cand, (clo, chi) in boxes_of.items():
                if cand in used or cand == solid_name:
                    continue
                both = float(np.prod(np.clip(np.minimum(hi, chi) - np.maximum(lo, clo), 0.0, None)))
                if both > 0.5 * vol and float(np.prod(chi - clo)) < 8.0 * whole:
                    q = meshed[cand]["pos"].astype(float)
                    q = q[((q > lo - 0.2) & (q < hi + 0.2)).all(axis=1)]
                    if len(q) < 4 or any(float(np.ptp(q @ a)) < 0.7 * n for a, n in zip(across, need)):
                        continue
                    # the assembly has its own part where the plug goes: that is the plug
                    stats["theirs"] += 1
                    if why:
                        log("  plug is the project's: %s %s <- %s" % (solid_name, f["ref"], cand))
                    return
            meshed[solid_name + SEP + f["ref"] + PLUG_PART] = pm
            stats["plugs"] += 1
        for f in g["footprints"]:
            ms = _models(f)
            if not f.get("fab") or not (ms or WP.knows(f["fpid"].split(":")[-1])):
                continue
            x0, x1, y0, y1 = f["fab"]
            back = f["side"] == "B"
            # how tall this instance drew it: a top corner of its box, found in the solid
            h = None
            for cx in (x0, x1):
                for cy in (y0, y1):
                    col = local[(np.abs(local[:, 0] - cx) < 0.01) & (np.abs(local[:, 1] - cy) < 0.01), 2]
                    col = col[col < -0.01] if back else col[col > t + 0.01]
                    if len(col):
                        h = max(h or 0.0, float(np.abs(col - (0.0 if back else t)).max()))
            if h is None:
                # NOT A BOX ON THE F.FAB OUTLINE. Boards drawn by hand stand a part where
                # and how big their own tables say: a package envelope that takes in the
                # leads (optical), or a side-entry header drawn MATED, its plug's reach
                # past the mouth included (the lever boards, the tee). Look for what
                # stands on this footprint, in widening steps.
                name = f["fpid"].split(":")[-1]
                above = local[(local[:, 2] < -0.01) if back else (local[:, 2] > t + 0.01)]

                def within(gx0, gx1, gy0, gy1):
                    return above[(above[:, 0] > gx0) & (above[:, 0] < gx1)
                                 & (above[:, 1] > gy0) & (above[:, 1] < gy1)]

                on = within(x0 - LOOSE, x1 + LOOSE, y0 - LOOSE, y1 + LOOSE)
                if len(on) < 4 and WP.side_entry(name):
                    mx, my = WP.mouth(f, panel, edge)
                    on = within(x0 - (PLUG if mx < 0 else BACK), x1 + (PLUG if mx > 0 else BACK),
                                y0 - (PLUG if my < 0 else BACK), y1 + (PLUG if my > 0 else BACK))
                    on = on if len(on) >= 2 else on[:0]
                elif len(on) < 4:
                    # one box, centred on the footprint, of another size
                    wide = within(x0 - ENVELOPE, x1 + ENVELOPE, y0 - ENVELOPE, y1 + ENVELOPE)
                    if len(wide):
                        top = wide[np.abs(np.abs(wide[:, 2]) - np.abs(wide[:, 2]).max()) < 0.01]
                        cx, cy = (top[:, 0].min() + top[:, 0].max()) / 2, (top[:, 1].min() + top[:, 1].max()) / 2
                        if (len(top) >= 4 and abs(cx - (x0 + x1) / 2) < max(0.35, 0.12 * (x1 - x0))
                                and abs(cy - (y0 + y1) / 2) < max(0.35, 0.12 * (y1 - y0))):
                            on = top
                if len(on) < 2 and WP.side_entry(name) and WP.knows(name):
                    # drawn as a PART OF ITS OWN beside the board (the leg joint boards):
                    # that part becomes the model, under its own name
                    mx, my = WP.mouth(f, panel, edge)
                    gx0, gx1 = x0 - (PLUG if mx < 0 else BACK), x1 + (PLUG if mx > 0 else BACK)
                    gy0, gy1 = y0 - (PLUG if my < 0 else BACK), y1 + (PLUG if my > 0 else BACK)
                    inv = np.linalg.inv(pose)
                    best = None
                    for cand, cm in meshed.items():
                        if cand in used or SEP in cand or "silk" in cand or "inst" in cm:
                            continue
                        lo, hi = cm["pos"].min(0), cm["pos"].max(0)
                        if np.linalg.norm((lo + hi) / 2 - centre) > 60.0:
                            continue
                        q = _apply(inv, cm["pos"].astype(float))
                        lo, hi = q.min(0), q.max(0)
                        foot = (hi[2] if back else lo[2]) - (0.0 if back else t)
                        if (lo[0] > gx0 and hi[0] < gx1 and lo[1] > gy0 and hi[1] < gy1
                                and abs(foot) < 0.3):
                            size = float(np.prod(hi - lo))
                            if best is None or size > best[0]:
                                best = (size, cand, float(-lo[2] if back else hi[2] - t))
                    own = _own_part(f, best[2], t, pose, panel, edge) if best else None
                    if own is not None:
                        meshed[best[1]] = own[0]
                        used.add(best[1])
                        stats["models"] += 1
                        stats["drawn"] = stats.get("drawn", 0) + 1
                        mate(f, best[2], on_board=False)
                        continue
                if len(on) < 2:
                    keep("not drawn on this instance")
                    if os.environ.get("WEB_BOARDS_WHY"):
                        log("  not drawn: %s %s %s" % (solid_name, f["ref"], name))
                    continue
                h = float(np.abs(on[:, 2] - (0.0 if back else t)).max())
                x0, x1 = min(x0, float(on[:, 0].min())), max(x1, float(on[:, 0].max()))
                y0, y1 = min(y0, float(on[:, 1].min())), max(y1, float(on[:, 1].max()))
            model = ms[0] if ms else None
            path = None
            if model:
                if any(abs(s - 1.0) > 1e-6 for s in model["scale"]):
                    keep("scaled model")
                    continue
                path = resolve_model(model["file"])
                same = WP.SAME_BODY.get(os.path.basename(model["file"]))
                if path is None and same:               # the same body under another name
                    path = resolve_model("${KICAD10_3DMODEL_DIR}/" + same)
            if path is None:
                # no file anywhere: the part drawn here (cadkit.web.parts)
                own = _own_part(f, h, t, pose, panel, edge)
                if own is None:
                    keep("no model in KiCad's library here, none drawn in web_parts")
                    continue
                own, (lo, hi) = own
                meshed[solid_name + SEP + f["ref"]] = own
                added += 1
                drawn += 1
                # what comes away is everything the drawn part covers: a panel
                # connector's nose and nut stand outside its F.Fab box
                z0, z1 = ((min(lo[2], -h) - 0.05, -0.005) if back
                          else (t + 0.005, max(hi[2], t + h) + 0.05))
                cut.append((min(x0, lo[0]) - 0.02, max(x1, hi[0]) + 0.02,
                            min(y0, lo[1]) - 0.02, max(y1, hi[1]) + 0.02, z0, z1))
                mate(f, h)
                continue
            mm = model_mesh(path)
            if mm is None:
                keep("model would not load")
                continue
            fm = footprint_matrix(f, model, t)
            p = _apply(fm, mm["pos"].astype(float))
            lo, hi = p.min(0), p.max(0)
            cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
            fx, fy = (f["fab"][0] + f["fab"][1]) / 2, (f["fab"][2] + f["fab"][3]) / 2
            slack_x = max(1.0, 0.5 * (x1 - x0))
            slack_y = max(1.0, 0.5 * (y1 - y0))
            if abs(cx - fx) > slack_x or abs(cy - fy) > slack_y:
                keep("model does not land on its footprint")
                continue
            full = pose @ fm
            key = os.path.basename(path)
            models_geo[key] = mm["geo"]
            meshed[solid_name + SEP + f["ref"]] = {
                "pos": _apply(full, mm["pos"].astype(float)).astype(np.float32),
                "tri": mm["tri"], "col": mm.get("col"),
                "inst": {"i": key, "m": [round(float(x), 6) for x in full[:3].ravel()]}}
            added += 1
            z0, z1 = (-h - 0.05, -0.005) if back else (t + 0.005, t + h + 0.05)
            cut.append((x0 - 0.02, x1 + 0.02, y0 - 0.02, y1 + 0.02, z0, z1))
            if f.get("tht"):
                a0, a1, b0, b1 = f["tht"]
                cut.append((a0 - 0.02, a1 + 0.02, b0 - 0.02, b1 + 0.02,
                            (t + 0.005, t + 30.0) if back else (-30.0, -0.005)))
            mate(f, h)
        counts[board] = counts.get(board, [0, 0])
        counts[board][0] += 1
        counts[board][1] += added
        if not added:
            continue
        try:
            # CUTTERS THAT OVERLAP ONE ANOTHER ARE CUT ONE AT A TIME. Given a compound of
            # overlapping boxes OCCT returns a VALID solid with only some of them taken
            # out, and nothing about it says so: a tee came back 367 mm3 lighter where
            # 3350 should have gone, and its headers stood inside blocks of board-green
            # (a header's own box, its tails' box and its plug's room all overlap). So
            # the boxes that touch nothing else go as one compound, the rest singly.
            norm = [(c[0], c[1], c[2], c[3], c[4][0], c[4][1]) if len(c) == 5 else tuple(c)
                    for c in cut]

            def apart(p, q):
                return (p[1] <= q[0] or q[1] <= p[0] or p[3] <= q[2] or q[3] <= p[2]
                        or p[5] <= q[4] or q[5] <= p[4])

            free = [c for i, c in enumerate(norm)
                    if all(apart(c, q) for j, q in enumerate(norm) if j != i)]
            singly = [c for c in norm if c not in free]
            R, tr = pose[:3, :3], pose[:3, 3]
            from OCP.gp import gp_Trsf
            trsf = gp_Trsf()
            trsf.SetValues(R[0, 0], R[0, 1], R[0, 2], tr[0], R[1, 0], R[1, 1], R[1, 2], tr[1],
                           R[2, 0], R[2, 1], R[2, 2], tr[2])
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform

            def placed_box(c):
                x0, x1, y0, y1, z0, z1 = c
                b = cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0).translate(
                    ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)).val()
                return cq.Shape.cast(BRepBuilderAPI_Transform(b.wrapped, trsf, True).Shape())

            # a COPY is cut: OCCT writes to a boolean's operands, and the gates key their
            # pair caches on the caller's shape byte for byte
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
            solid = cq.Shape.cast(BRepBuilderAPI_Copy(_topods(shape_of(solid_name)), True, False).Shape())
            v0 = solid.Volume()
            trimmed = solid
            if free:
                tool = cq.Compound.makeCompound([placed_box(c) for c in free])
                nxt = solid.cut(tool)
                if nxt.isValid() and nxt.Volume() <= v0 + 1e-6:
                    trimmed = nxt
                else:
                    singly = free + singly
            for c in singly:
                nxt = trimmed.cut(placed_box(c))
                if nxt.isValid() and nxt.Volume() <= trimmed.Volume() + 1e-6:
                    trimmed = nxt
            if trimmed.Volume() > v0 - 1e-3:
                log("web boards: %s -- nothing came away under its models" % solid_name)
            new = mesh_shape(trimmed.wrapped)
            if new is not None:
                meshed[solid_name] = new
        except Exception as exc:
            log("web boards: %s kept its boxes under the models (%s)" % (solid_name, exc))
        stats["boards"] += 1
        stats["models"] += added
        stats["drawn"] = stats.get("drawn", 0) + drawn
    kept = "; ".join("%d %s" % (n, w) for w, n in sorted(stats["kept"].items())) or "none"
    log("web boards: %d board(s) carry %d part model(s), %d of them drawn here [%s]; boxes kept: %s"
        % (stats["boards"], stats["models"], stats.get("drawn", 0),
           ", ".join("%s x%d: %d" % (b, n, k) for b, (n, k) in sorted(counts.items())), kept))
    log("web boards: %d JST plug(s) seated in their headers%s"
        % (stats["plugs"], ", %d more are parts of the project's own" % stats["theirs"]
           if stats["theirs"] else ""))
    return models_geo
