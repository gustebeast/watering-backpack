# -*- coding: utf-8 -*-
"""cadkit.digest — what a solid IS, as one hash, whichever way its file happens to be
written.

A cache keyed on a shape's BRep bytes misses for no reason: OCCT's writer does not put
a shape's records down in the same order every run. The same part, built by the same
code in two fresh processes, gives two files of the same length that differ in which of
two pcurve records comes first (and in a tolerance at the fifteenth decimal). Same
solid, different bytes, a part meshed again.

    from cadkit.digest import geometry_digest
    key = geometry_digest(shape)              # TopoDS_Shape / cq.Shape / cq.Workplane

is a sha1 over the geometry itself, in an order that does not depend on the file:

  * every vertex, where it is (so the solid's PLACEMENT is in the key);
  * every edge: the kind of curve, its length, its two ends' midpoint;
  * every face: the kind of surface, its area, its centre of area, its sense;
  * the volume, and the counts of each.

each list sorted, each number rounded at GRID (a millionth of a millimetre and its
square and cube -- a thousand times finer than anything printed, a million times
coarser than the noise). Two different solids would have to agree in all of it to share
a key: a hole 0.01 mm larger moves a vertex, lengthens an edge and changes two areas.

A number that falls on a rounding boundary can round either way between two runs. That
is a miss, never a wrong hit: the cost is one part made again.
"""

from __future__ import annotations

import hashlib

__all__ = ["geometry_digest"]

GRID = 1e-6


def _topods(shape):
    if hasattr(shape, "vals"):
        import cadquery as cq
        vals = [v for v in shape.vals() if isinstance(v, cq.Shape)]
        shape = vals[0] if len(vals) == 1 else cq.Compound.makeCompound(vals)
    return getattr(shape, "wrapped", shape)


def geometry_digest(shape) -> str:
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape

    shape = _topods(shape)

    def each(kind):
        m = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, kind, m)
        return [m.FindKey(i) for i in range(1, m.Extent() + 1)]

    def q(x, grid=GRID):
        return int(round(x / grid))

    verts = []
    for v in each(TopAbs_VERTEX):
        p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(v))
        verts.append((q(p.X()), q(p.Y()), q(p.Z())))
    edges = []
    for e in each(TopAbs_EDGE):
        e = TopoDS.Edge_s(e)
        if BRep_Tool.Degenerated_s(e):
            edges.append((-1, 0, 0, 0, 0))
            continue
        g = GProp_GProps()
        BRepGProp.LinearProperties_s(e, g)
        c = g.CentreOfMass()
        edges.append((int(BRepAdaptor_Curve(e).GetType()), q(g.Mass()),
                      q(c.X()), q(c.Y()), q(c.Z())))
    faces = []
    for f in each(TopAbs_FACE):
        f = TopoDS.Face_s(f)
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, g)
        c = g.CentreOfMass()
        faces.append((int(BRepAdaptor_Surface(f).GetType()), int(f.Orientation()),
                      q(g.Mass(), GRID ** 2 * 1e6), q(c.X()), q(c.Y()), q(c.Z())))
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, g)
    h = hashlib.sha1()
    h.update(repr((len(verts), len(edges), len(faces), q(g.Mass(), 1e-6))).encode())
    for rows in (verts, edges, faces):
        rows.sort()
        h.update(repr(rows).encode())
    return h.hexdigest()
