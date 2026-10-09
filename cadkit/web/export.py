"""Mesh solids for the web viewer: one GLB to draw, one sidecar to MEASURE against.

    from cadkit.web import export
    export([(name, shape, (r, g, b, a)), ...], out_dir)     # -> assembly.glb, assembly.geo.json

WHY NOT cadquery's own GLTF exporter. It writes every FACE of every part as its own
primitive (37,527 of them at build #795), which the viewer then had to merge back
together, and it throws away the one thing a mesh cannot give back: what each
triangle WAS. A measure tool working on triangles can only fit a radius; working on
the kernel's own numbers it reads it. So this meshes each part itself and keeps, per
part:

  * the triangles, SORTED BY FACE, so a face is one contiguous run and a picked
    triangle names its face by a search over a few offsets (no per-vertex id);
  * each face as the kernel describes it: plane (point, outward normal), cylinder
    (axis, radius), cone, sphere, torus, or "other";
  * each edge the same way: line (two ends), circle (centre, axis, radius, start,
    sweep), or a sampled polyline;
  * which edges bound which face, so the viewer snaps to the edges and corners of
    the face under the cursor instead of searching the whole model.

The GLB carries positions and indices only. Normals are left out on purpose: a
vertex is never shared between two faces here, so the viewer's own
computeVertexNormals() gives smooth curved faces and crisp edges, and the file is a
third smaller for it.

Meshing goes through OCCT's IVtk mesher because it hands back whole numpy arrays
with a sub-shape id on every cell. Walking Poly_Triangulation node by node from
Python costs seconds per part on the big ones.

Units are millimetres in the CAD frame (Z up). The GLB's single root node turns that
to glTF's Y up, exactly as cadquery's exporter did, so the rig's pivots still apply
to the part nodes unchanged.
"""

from __future__ import annotations

import json
import pathlib
import struct

import numpy as np

# 0.1 mm of chord, 0.3 rad of angle. The ANGLE is what sets the size: a thin tube swept
# along a helix (a wound string) meshes to hundreds of thousands of triangles at 0.1 rad.
TOLERANCE = 0.1
ANGULAR = 0.3
# sampled edges (ellipses, splines): chord error of the polyline the viewer snaps to
EDGE_DEFLECTION = 0.02
FORMAT = 2


def _r(v, n=4):
    return round(float(v), n)


def _xyz(p):
    return [_r(p.X()), _r(p.Y()), _r(p.Z())]


def _face_record(face):
    """A face as the kernel describes it. Normals and axes are unit vectors."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import (GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone,
                             GeomAbs_Sphere, GeomAbs_Torus)
    from OCP.TopAbs import TopAbs_REVERSED
    ad = BRepAdaptor_Surface(face, True)
    t = ad.GetType()
    if t == GeomAbs_Plane:
        pl = ad.Plane()
        n = pl.Axis().Direction()
        s = -1.0 if face.Orientation() == TopAbs_REVERSED else 1.0
        # a point ON THE FACE, not the plane's own origin (which can be metres away)
        u = 0.5 * (ad.FirstUParameter() + ad.LastUParameter())
        v = 0.5 * (ad.FirstVParameter() + ad.LastVParameter())
        p = ad.Value(u, v) if all(abs(x) < 1e6 for x in (u, v)) else pl.Location()
        return ["p"] + _xyz(p) + [_r(s * n.X(), 6), _r(s * n.Y(), 6), _r(s * n.Z(), 6)]
    if t == GeomAbs_Cylinder:
        c = ad.Cylinder()
        a = c.Axis()
        d, o = a.Direction(), a.Location()
        v0, v1 = ad.FirstVParameter(), ad.LastVParameter()
        if not all(abs(x) < 1e6 for x in (v0, v1)):
            v0 = v1 = 0.0
        return (["c"] + _xyz(o) + [_r(d.X(), 6), _r(d.Y(), 6), _r(d.Z(), 6)]
                + [_r(c.Radius()), _r(v0), _r(v1)])
    if t == GeomAbs_Cone:
        c = ad.Cone()
        a = c.Axis()
        d, o = a.Direction(), c.Apex()
        return (["k"] + _xyz(o) + [_r(d.X(), 6), _r(d.Y(), 6), _r(d.Z(), 6)]
                + [_r(c.SemiAngle(), 6)])
    if t == GeomAbs_Sphere:
        s = ad.Sphere()
        return ["s"] + _xyz(s.Location()) + [_r(s.Radius())]
    if t == GeomAbs_Torus:
        s = ad.Torus()
        d = s.Axis().Direction()
        return (["t"] + _xyz(s.Location()) + [_r(d.X(), 6), _r(d.Y(), 6), _r(d.Z(), 6)]
                + [_r(s.MajorRadius()), _r(s.MinorRadius())])
    return ["o"]


def _edge_record(edge):
    """An edge as the kernel describes it, or None for a degenerate one."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    if BRep_Tool.Degenerated_s(edge):
        return None
    try:
        ad = BRepAdaptor_Curve(edge)
    except Exception:
        return None
    t = ad.GetType()
    u0, u1 = ad.FirstParameter(), ad.LastParameter()
    if not all(abs(x) < 1e9 for x in (u0, u1)):
        return None
    if t == GeomAbs_Line:
        return ["l"] + _xyz(ad.Value(u0)) + _xyz(ad.Value(u1))
    if t == GeomAbs_Circle:
        c = ad.Circle()
        d = c.Axis().Direction()
        return (["c"] + _xyz(c.Location()) + [_r(d.X(), 6), _r(d.Y(), 6), _r(d.Z(), 6)]
                + [_r(c.Radius())] + _xyz(ad.Value(u0)) + [_r(u1 - u0, 6)])
    try:
        g = GCPnts_QuasiUniformDeflection(ad, EDGE_DEFLECTION, u0, u1)
        pts = [g.Value(i) for i in range(1, g.NbPoints() + 1)] if g.IsDone() else []
    except Exception:
        pts = []
    if len(pts) < 2:
        pts = [ad.Value(u0), ad.Value(u1)]
    flat = []
    for p in pts:
        flat += _xyz(p)
    return ["o", flat]


def shape_vertices(shape):
    """The B-rep's own corners, float32 (k,3), in the kernel's order."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape
    vm = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_VERTEX, vm)
    out = np.empty((vm.Extent(), 3), dtype=np.float32)
    for i in range(1, vm.Extent() + 1):
        p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vm.FindKey(i)))
        out[i - 1] = (p.X(), p.Y(), p.Z())
    return out


def mesh_shape(shape, tolerance=TOLERANCE, angular=ANGULAR, face_colors=None, copy=True):
    """One TopoDS_Shape -> {"pos": float32 (n,3), "tri": uint32 (m,3), "geo": {...},
    "verts": float32 (k,3) the B-rep's corners}, plus "col": uint8 (n,4) when
    `face_colors` = [(TopoDS_Face, (r, g, b) or None)] is given (a part of many colours:
    a component model).

    ⚠ THE CALLER'S SHAPE IS NOT TOUCHED: a COPY is meshed (copy=True). Meshing stores a
    triangulation ON the shape, and OCCT's bounding box then reads the triangles instead
    of the surfaces. The first version of this meshed the build's own shapes in place,
    and the sweep gate, which runs after the preview and measures by bounding box,
    turned red on ten pulleys that had not moved (build #862, 0.5 mm^3 each): chords
    where it expected circles. A viewer export must leave no trace on what it was shown.
    copy=False is for a shape nobody else holds (a model file just read), and is what
    `face_colors` needs, since it names faces of the shape as given.

    geo = {"f": [face records], "r": [tri offsets, len(f)+1], "e": [edge records],
           "fe": [[edge ids] per face]}.  Triangles are sorted by face; r[i]..r[i+1] is
    face i's run. Returns None for a shape with nothing to draw."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.IVtkOCC import IVtkOCC_Shape, IVtkOCC_ShapeMesher
    from OCP.IVtkVTK import IVtkVTK_ShapeData
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from vtkmodules.util.numpy_support import vtk_to_numpy

    if copy:
        if face_colors is not None:
            raise ValueError("face_colors names faces of the shape as given: pass copy=False")
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
        shape = BRepBuilderAPI_Copy(shape, True, False).Shape()     # geometry yes, mesh no
    BRepMesh_IncrementalMesh(shape, tolerance, False, angular, True)
    vs, sd = IVtkOCC_Shape(shape), IVtkVTK_ShapeData()
    IVtkOCC_ShapeMesher().Build(vs, sd)
    pd = sd.getVtkPolyData()
    npoly = pd.GetNumberOfPolys()
    if not npoly:
        return None
    if pd.GetNumberOfStrips():
        raise RuntimeError("the mesher returned triangle strips; this reader expects triangles")
    offs = vtk_to_numpy(pd.GetPolys().GetOffsetsArray())
    if not (np.diff(offs) == 3).all():
        raise RuntimeError("the mesher returned a polygon that is not a triangle")
    tri = vtk_to_numpy(pd.GetPolys().GetConnectivityArray()).reshape(-1, 3).astype(np.int64)
    pts = vtk_to_numpy(pd.GetPoints().GetData())
    ids = vtk_to_numpy(pd.GetCellData().GetArray("SUBSHAPE_IDS"))
    # cell ids run verts, lines, polys: the triangles' sub-shape ids are the tail
    tri_sub = ids[len(ids) - npoly:]

    fmap = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, fmap)
    emap = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, emap)

    # the mesher's sub-shape id -> our own face index (0-based, exploration order)
    sub_ids = np.unique(tri_sub)
    to_face = {}
    for sid in sub_ids:
        k = fmap.FindIndex(vs.GetSubShape(int(sid)))
        if k < 1:
            raise RuntimeError("a meshed cell names a sub-shape that is not a face")
        to_face[int(sid)] = k - 1
    tri_face = np.vectorize(to_face.get, otypes=[np.int64])(tri_sub)
    order = np.argsort(tri_face, kind="stable")
    tri, tri_face = tri[order], tri_face[order]

    # keep only the points the triangles use (the mesher also emits edge polylines)
    used, inv = np.unique(tri.ravel(), return_inverse=True)
    pos = np.ascontiguousarray(pts[used], dtype=np.float32)
    tri = inv.reshape(-1, 3).astype(np.uint32)

    nf = fmap.Extent()
    counts = np.bincount(tri_face, minlength=nf)
    runs = np.concatenate([[0], np.cumsum(counts)]).tolist()

    edges, eidx = [], {}
    for i in range(1, emap.Extent() + 1):
        rec = _edge_record(TopoDS.Edge_s(emap.FindKey(i)))
        if rec is not None:
            eidx[i] = len(edges)
            edges.append(rec)
    faces, face_edges = [], []
    for i in range(1, nf + 1):
        f = TopoDS.Face_s(fmap.FindKey(i))
        try:
            faces.append(_face_record(f))
        except Exception:
            faces.append(["o"])
        fe, ex = [], TopExp_Explorer(f, TopAbs_EDGE)
        while ex.More():
            k = eidx.get(emap.FindIndex(ex.Current()))
            if k is not None and k not in fe:
                fe.append(k)
            ex.Next()
        face_edges.append(fe)
    out = {"pos": pos, "tri": tri, "verts": shape_vertices(shape),
           "geo": {"f": faces, "r": runs, "e": edges, "fe": face_edges}}
    if face_colors is not None:
        fc = np.full((nf, 4), 255, dtype=np.uint8)
        fc[:, :3] = 150
        for face, c in face_colors:
            k = fmap.FindIndex(face)
            if k >= 1 and c is not None:
                fc[k - 1, :3] = np.clip(np.round(np.array(c) * 255.0), 0, 255)
        # ALPHA SAYS METAL (0) OR NOT (255): the model is opaque, so the channel is free,
        # and the page and the tracer read a lead's or a shell's shine from it
        from .finishes import METAL_COLOURS, METAL_TOL
        lin = fc[:, :3].astype(np.float64) / 255.0
        srgb = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * lin ** (1 / 2.4) - 0.055)
        metal = np.zeros(nf, dtype=bool)
        for m in METAL_COLOURS:
            metal |= np.abs(srgb - np.array(m)).max(axis=1) < METAL_TOL
        fc[metal, 3] = 0
        col = np.zeros((len(pos), 4), dtype=np.uint8)
        for k in range(3):
            col[tri[:, k]] = fc[tri_face]
        out["col"] = col
    return out


# ── the GLB ───────────────────────────────────────────────────────────────────────
def _pad4(b: bytes, fill: bytes = b"\x00") -> bytes:
    return b + fill * (-len(b) % 4)


def silk_units(done):
    """{lettering part: its board}. A board's lettering is a part of its own in the
    build (white ink), under names that follow no one rule (tee_silk_3 on tee_pcb_3,
    pogo_male_silk_top on pogo_male_board_top), so the board is found by where the
    lettering IS: the other part whose box best matches the lettering's own (overlap
    over union, both grown 1 mm so a one-face print still has a thickness). The viewer
    then selects, hides and lists the two as one."""
    boxes = {n: (m["pos"].min(0), m["pos"].max(0)) for n, m in done.items() if "__" not in n}
    out = {}
    for n, (lo, hi) in boxes.items():
        if "silk" not in n:
            continue
        best = (0.05, None)
        lo, hi = lo - 1.0, hi + 1.0
        for k, (a, b) in boxes.items():
            if "silk" in k:
                continue
            a, b = a - 1.0, b + 1.0
            inter = float(np.prod(np.clip(np.minimum(hi, b) - np.maximum(lo, a), 0.0, None)))
            if inter <= 0.0:
                continue
            iou = inter / (float(np.prod(hi - lo)) + float(np.prod(b - a)) - inter)
            if iou > best[0]:
                best = (iou, k)
        if best[1]:
            out[n] = best[1]
    return out


def write_glb(parts, out: pathlib.Path, extras=None, units=None, mats=None) -> None:
    """parts = [(name, pos float32 (n,3), tri uint32 (m,3), (r, g, b, a), col)]: `col`
    is None, or uint8 (n,4) per-vertex colour (linear, as glTF's COLOR_0), and then the
    part's material is plain white under it."""
    buf = bytearray()
    views, accessors, meshes, nodes, materials, mat_ix = [], [], [], [], [], {}

    def view(data: bytes, target):
        while len(buf) % 4:
            buf.append(0)
        views.append({"buffer": 0, "byteOffset": len(buf), "byteLength": len(data),
                      "target": target})
        buf.extend(data)
        return len(views) - 1

    for name, pos, tri, rgba, col in parts:
        key = (1.0, 1.0, 1.0, 1.0) if col is not None else tuple(round(float(c), 4) for c in rgba)
        if key not in mat_ix:
            mat_ix[key] = len(materials)
            m = {"pbrMetallicRoughness": {"baseColorFactor": list(key),
                                          "metallicFactor": 0.0, "roughnessFactor": 0.65},
                 "doubleSided": True}
            if key[3] < 0.999:
                m["alphaMode"] = "BLEND"
            materials.append(m)
        small = len(pos) < 65536
        idx = tri.astype(np.uint16 if small else np.uint32)
        vp = view(pos.astype("<f4").tobytes(), 34962)
        vi = view(idx.tobytes(), 34963)
        accessors.append({"bufferView": vp, "componentType": 5126, "count": int(len(pos)),
                          "type": "VEC3", "min": pos.min(axis=0).tolist(),
                          "max": pos.max(axis=0).tolist()})
        accessors.append({"bufferView": vi, "componentType": 5123 if small else 5125,
                          "count": int(idx.size), "type": "SCALAR"})
        attrs = {"POSITION": len(accessors) - 2}
        ia = len(accessors) - 1
        if col is not None:
            vc = view(np.ascontiguousarray(col, dtype=np.uint8).tobytes(), 34962)
            accessors.append({"bufferView": vc, "componentType": 5121, "normalized": True,
                              "count": int(len(col)), "type": "VEC4"})
            attrs["COLOR_0"] = len(accessors) - 1
        meshes.append({"primitives": [{"attributes": attrs, "indices": ia,
                                       "material": mat_ix[key]}]})
        nodes.append({"name": name, "mesh": len(meshes) - 1})
        ex = {}
        if units and name in units:                # what it is selected and hidden with
            ex["unit"] = units[name]
        if mats and mats.get(name):                # its filament, or what else it is made of
            ex["mat"] = mats[name]
        if ex:
            nodes[-1]["extras"] = ex
    # CAD Z-up -> glTF Y-up at the one root, as cadquery's exporter did
    s = 0.7071067811865476
    root = {"name": "assembly", "rotation": [-s, 0.0, 0.0, s],
            "children": list(range(len(nodes)))}
    nodes.append(root)
    gltf = {"asset": {"version": "2.0", "generator": "cadkit.web"},
            "scene": 0, "scenes": [{"nodes": [len(nodes) - 1]}],
            "nodes": nodes, "meshes": meshes, "materials": materials,
            "accessors": accessors, "bufferViews": views,
            "buffers": [{"byteLength": len(buf)}]}
    from .finishes import FINISHES
    gltf["asset"]["extras"] = dict(extras or {}, finishes=FINISHES)
    js = _pad4(json.dumps(gltf, separators=(",", ":")).encode(), b" ")
    bn = _pad4(bytes(buf))
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(bn)))
        fh.write(struct.pack("<I4s", len(js), b"JSON"))
        fh.write(js)
        fh.write(struct.pack("<I4s", len(bn), b"BIN\x00"))
        fh.write(bn)


def _rgba(color):
    if color is None:
        return (0.8, 0.8, 0.8, 1.0)
    if hasattr(color, "toTuple"):
        color = color.toTuple()
    c = tuple(float(x) for x in color)
    return c if len(c) == 4 else c + (1.0,)


def _topods(obj):
    """A cq.Workplane / cq.Shape / TopoDS_Shape -> one TopoDS_Shape."""
    if hasattr(obj, "vals"):
        import cadquery as cq
        vals = [v for v in obj.vals() if isinstance(v, cq.Shape)]
        if len(vals) == 1:
            return vals[0].wrapped
        return cq.Compound.makeCompound(vals).wrapped
    return getattr(obj, "wrapped", obj)


def pieces(name, shape, taken=(), whole=()):
    """[(piece name, shape)]: a part drawn as several separate solids (a row of
    bearings and their rod) becomes one part per solid, <name>_0 .. <name>_N, so each can
    be picked, hidden and measured by itself. It stays whole when it is one solid, when
    it has faces outside any solid, when it is named in `whole` (the rig moves parts by
    name) or when a piece's name is already somebody's (`taken`)."""
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE
    from OCP.TopoDS import TopoDS
    one = [(name, shape)]
    if name in whole:
        return one
    out, ex = [], TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        out.append(TopoDS.Solid_s(ex.Current()))
        ex.Next()
    if len(out) < 2 or TopExp_Explorer(shape, TopAbs_FACE, TopAbs_SOLID).More():
        return one
    names = ["%s_%d" % (name, i) for i in range(len(out))]
    if any(n in taken for n in names):
        return one
    return list(zip(names, out))


def rig_names(path):
    """Every string in a rig file: the part names the animation moves (and more, which
    costs nothing). Empty when there is no rig yet."""
    out = set()

    def walk(v):
        if isinstance(v, str):
            out.add(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    try:
        walk(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))
    except Exception:
        pass
    return out


PAGE = pathlib.Path(__file__).resolve().parent / "viewer" / "index.html"


def step_parts(path):
    """[(name, shape, colour)] out of an assembly STEP file as cadquery writes one: each
    named, coloured part, where it stands. For a project that still hands the viewer its
    assembly.step; a project that has the parts in memory passes them and skips the
    file. A STEP that is ONE PART and no assembly (a single-part project's only output)
    is that part, named after the file."""
    import cadquery as cq
    try:
        asm = cq.Assembly.importStep(str(path))
    except ValueError:                               # "does not contain an assembly"
        import pathlib
        return [(pathlib.Path(path).stem, cq.importers.importStep(str(path)), (0.8, 0.8, 0.8, 1.0))]
    out, seen = [], {}
    for name, node in asm.traverse():
        shapes = [s for s in getattr(node, "shapes", []) if s is not None]
        if not shapes:
            continue
        loc, p = node.loc, node.parent
        while p is not None:
            loc, p = p.loc * loc, p.parent
        shape = cq.Compound.makeCompound(shapes).moved(loc) if len(shapes) > 1 else shapes[0].moved(loc)
        base = name.split("/")[-1] or "part"
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            base = "%s_%d" % (base, seen[base] - 1)
        out.append((base, shape, node.color or (0.8, 0.8, 0.8, 1.0)))
    return out


def export(parts, out_dir, stem="assembly", extras=None, meshed=None, quiet=False,
           boards=None, cache_dir=None, materials=None, whole=None, page=False,
           units=None, parents=None):
    """Write <stem>.glb and <stem>.geo.json into out_dir.

    parts     = [(name, solid, colour)]; solid is a cq.Workplane / cq.Shape /
                TopoDS_Shape (or, with `meshed`, a function returning one: it is called
                only if the part has to be re-cut), colour a cq.Color or an
                (r, g, b[, a]) tuple. THE SOLIDS ARE NOT TOUCHED: every mesh is of a copy.
    extras    = facts for the page, written into the file: "title", "subtitle", "build".
    meshed    = optional {name: mesh_shape() result} to reuse (the local view's cache).
    boards    = the project's cadkit.board_geom.Boards (or a zero-argument function
                returning it, if importing it is dear), if it has circuit boards: each
                board's footprint boxes are swapped for KiCad's own part models, or one
                drawn by cadkit.web.parts (cadkit.web.boards says how, and what it
                leaves alone). `cache_dir` keeps what that needs between runs.
    materials = optional name -> what the part is made of: the filament a printed part
                is printed in ("petg-gf" | "pctg" | ..., for the page's as-printed
                view), or a bought part's finish, one of cadkit.web.finishes.FINISHES
                ("steel", "brass", "rubber", ...), which it is always shown with.
    units     = optional name -> the part it is ONE THING with, or None: a print in two
                filaments is two parts here (deck base and deck colour) and one object
                on the printer, so the page selects, hides and lists them as one. The
                solids of one part are one thing without being told.
    parents   = optional {piece name: its part's name}, for pieces split by the caller.
    whole     = names that must stay one part though drawn as several solids (see
                pieces()); by default the names in the rig file beside the output.
    page      = True also writes the viewer page beside the model (index.html), which
                is what a folder published as a web site needs.
    Returns (glb path, sidecar path, {name: mesh})."""
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if whole is None:
        whole = rig_names(out_dir / "rig.json")
    done, colors, solids = {}, {}, {}
    parents = dict(parents or {})
    taken = {p[0] for p in parts}
    for part_name, solid, color in parts:
        if part_name in done or part_name in solids:
            raise ValueError("two parts are both named %r: the viewer addresses parts by name" % part_name)
        if (meshed or {}).get(part_name) is not None:
            split = [(part_name, solid)]
        else:
            split = pieces(part_name, _topods(solid), taken, whole)
        for name, piece in split:
            if name != part_name:
                parents[name] = part_name
            solids[name] = piece
            m = (meshed or {}).get(name)
            if m is None:
                m = mesh_shape(_topods(piece))
            if m is None:
                continue
            done[name] = m
            colors[name] = _rgba(color)
    models = {}
    if boards is not None:
        try:
            from .boards import detail, SEP
            if callable(boards):
                boards = boards()
            models = detail(done, lambda n: solids[n]() if callable(solids[n]) else solids[n],
                            boards, cache_dir)
            for n in done:
                if n not in colors:
                    colors[n] = colors.get(n.split(SEP)[0], (0.8, 0.8, 0.8, 1.0))
        except Exception as exc:          # the boxes are a complete model: never fail the export
            print("web boards: skipped (%s: %s) -- boards keep their boxes"
                  % (type(exc).__name__, exc))
            done = {n: m for n, m in done.items() if n in colors}
    glb_parts, geo = [], {}
    for name, m in done.items():
        glb_parts.append((name, m["pos"], m["tri"], colors[name], m.get("col")))
        geo[name] = m["inst"] if "inst" in m else m["geo"]
    glb = out_dir / (stem + ".glb")
    side = out_dir / (stem + ".geo.json")
    mats = None
    if materials is not None:
        try:
            mats = {n: materials(n) for n in done if "__" not in n}
        except Exception as exc:             # the as-printed view is an extra
            print("web export: no print materials (%s)" % exc)
    # WHAT EACH PART IS ONE THING WITH: its part if it is one solid of several, then
    # whatever the project says that part belongs to; lettering goes with its board
    one = {}
    for n in done:
        if "__" in n:
            continue
        part = parents.get(n, n)
        try:
            said = units(part) if units is not None else None
        except Exception:
            said = None
        if said or part != n:
            one[n] = said or part
    for ink, board in silk_units(done).items():
        one[ink] = one.get(board, board)
    write_glb(glb_parts, glb, extras=extras, units=one, mats=mats)
    side.write_text(json.dumps({"format": FORMAT, "units": "mm", "parts": geo, "models": models},
                               separators=(",", ":")))
    if page:
        text = PAGE.read_bytes()
        dst = out_dir / "index.html"
        if not dst.exists() or dst.read_bytes() != text:
            dst.write_bytes(text)
    if not quiet:
        ntri = sum(len(p[2]) for p in glb_parts)
        nfc = sum(len(g["f"]) for g in geo.values() if "f" in g)
        print("wrote %s (%d parts, %d triangles, %.1f MB) and %s (%d faces, %.1f MB)"
              % (glb.name, len(glb_parts), ntri, glb.stat().st_size / 1e6,
                 side.name, nfc, side.stat().st_size / 1e6))
    return glb, side, done
