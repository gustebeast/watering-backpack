"""The ray tracer behind the viewer page. THIS FILE RUNS INSIDE BLENDER, not in Python:

    blender --background --factory-startup --python trace_blender.py

A browser cannot reach a graphics card's ray-tracing hardware; Blender's Cycles can
(OptiX), and denoises on it too. So the page keeps drawing the model itself, and when
the view has stood still it asks the local server for ONE traced picture of exactly
what it shows. The server (cadkit.web.trace) keeps this process running with the model
loaded and passes each request on.

It talks in lines of JSON: requests on stdin, one reply per request on stdout, each
reply line starting with MARK (Blender prints a good deal of its own).

    {"op": "load", "glb": path}
    {"op": "render", "out": path, "w": 1280, "h": 800, "samples": 64,
     "cam": [16 numbers], "fov": 40, "near": 1, "far": 20000,
     "hidden": [part names], "poses": {part name: [16 numbers]}, "printed": false,
     "sun": [x, y, z], "sun_strength": 2.4, "bg": [r, g, b]}
    {"op": "quit"}

Matrices are the page's own (three.js: column-major, Y up, the model turned -90 deg
about X at its root). The model is loaded here as the CAD drew it, Z up, so a page
matrix M becomes C @ M with C the turn back.
"""

import json
import struct
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

MARK = "@@trace "
C = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))      # page -> CAD
SKY_TOP, SKY_BOTTOM = (0.888, 0.913, 0.956), (0.102, 0.117, 0.138)          # linear
# a filament's colour and finish, as the page's "as printed" view has them
PRINTED = {"petg-gf": ((0.0086, 0.0091, 0.0103), 0.92),
           "pctg": ((0.0070, 0.0513, 0.0137), 0.22),
           "pctg-clear": ((0.815, 0.855, 0.888), 0.18),
           "tpu": ((0.0052, 0.0052, 0.0056), 1.0)}

CLEAR = 0.38                # how much of a clear filament is seen: the page's figure
parts = {}                  # name -> (object, plain material, filament or None)
finishes = {}               # the model's own table: finish -> (metalness, roughness)
posed = {}                  # name -> the pose it was last given, as the page sent it
mats = {}


def reply(**kw):
    sys.stdout.write(MARK + json.dumps(kw) + "\n")
    sys.stdout.flush()


# ── the model ─────────────────────────────────────────────────────────────────────
def read_glb(path):
    with open(path, "rb") as fh:
        data = fh.read()
    n = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + n])
    blob = memoryview(data)[20 + n + 8:]
    finishes.clear()
    finishes.update((doc["asset"].get("extras") or {}).get("finishes") or {})
    kinds = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
    width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}

    def acc(i):
        a = doc["accessors"][i]
        v = doc["bufferViews"][a["bufferView"]]
        w = width[a["type"]]
        arr = np.frombuffer(blob, kinds[a["componentType"]], a["count"] * w, v.get("byteOffset", 0))
        return arr.reshape(-1, w) if w > 1 else arr

    for node in doc["nodes"]:
        if "mesh" not in node:
            continue
        prim = doc["meshes"][node["mesh"]]["primitives"][0]
        at = prim["attributes"]
        mat = doc["materials"][prim["material"]]
        yield (node["name"], acc(at["POSITION"]), acc(prim["indices"]),
               acc(at["COLOR_0"]) if "COLOR_0" in at else None,
               tuple(mat["pbrMetallicRoughness"]["baseColorFactor"]),
               (node.get("extras") or {}).get("mat"))


def material(key, rgba=(1, 1, 1, 1), rough=0.65, metal=0.0, vertex=False):
    if key in mats:
        return mats[key]
    m = bpy.data.materials.new(str(key))
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (rgba[0], rgba[1], rgba[2], 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Alpha"].default_value = rgba[3]
    if vertex:                                     # many colours, and metal where alpha is 0
        nt = m.node_tree
        a = nt.nodes.new("ShaderNodeAttribute")
        a.attribute_name = "Col"
        nt.links.new(a.outputs["Color"], b.inputs["Base Color"])
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        nt.links.new(a.outputs["Alpha"], inv.inputs[1])
        nt.links.new(inv.outputs[0], b.inputs["Metallic"])
        r = nt.nodes.new("ShaderNodeMapRange")
        r.inputs["To Min"].default_value, r.inputs["To Max"].default_value = 0.3, rough
        nt.links.new(a.outputs["Alpha"], r.inputs["Value"])
        nt.links.new(r.outputs["Result"], b.inputs["Roughness"])
    mats[key] = m
    return m


def load(path):
    t = time.perf_counter()
    for o in list(bpy.data.objects):
        if o.type == "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    parts.clear()
    posed.clear()
    tris = 0
    coll = bpy.context.scene.collection
    for name, pos, idx, col, rgba, filament in read_glb(path):
        me = bpy.data.meshes.new(name)
        nt = len(idx) // 3
        me.vertices.add(len(pos))
        me.vertices.foreach_set("co", pos.astype(np.float32).ravel())
        me.loops.add(nt * 3)
        me.loops.foreach_set("vertex_index", idx.astype(np.int32))
        me.polygons.add(nt)
        me.polygons.foreach_set("loop_start", np.arange(0, nt * 3, 3, dtype=np.int32))
        me.polygons.foreach_set("loop_total", np.full(nt, 3, dtype=np.int32))
        me.polygons.foreach_set("use_smooth", np.ones(nt, dtype=bool))
        if col is not None:
            a = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
            a.data.foreach_set("color", (col.astype(np.float32) / 255.0).ravel())
            plain = material("vertex", rough=0.6, vertex=True)
        else:
            metal, rough = finishes.get(filament, (0.0, 0.65))
            if str(filament).endswith("-clear"):   # a clear filament is seen through
                rgba = tuple(rgba[:3]) + (CLEAR,)
            plain = material(tuple(round(c, 4) for c in rgba) + (metal, rough), rgba, rough, metal)
        me.update()
        me.materials.append(plain)
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        parts[name] = (ob, plain, filament if col is None else None)
        tris += nt
    return dict(parts=len(parts), triangles=tris, seconds=round(time.perf_counter() - t, 2))


# ── the scene ─────────────────────────────────────────────────────────────────────
def setup():
    sc = bpy.context.scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    device = "CPU"
    for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            found = [d for d in prefs.devices if d.type == kind]
            if found:
                for d in prefs.devices:
                    d.use = d.type == kind
                device = kind
                break
        except Exception:
            continue
    cy = sc.cycles
    cy.device = "GPU" if device != "CPU" else "CPU"
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.02
    cy.max_bounces = 4
    cy.diffuse_bounces = 3
    cy.glossy_bounces = 3
    cy.caustics_reflective = cy.caustics_refractive = False
    cy.use_denoising = True
    try:
        cy.denoiser = "OPTIX" if device == "OPTIX" else "OPENIMAGEDENOISE"
    except Exception:
        pass
    sc.render.use_persistent_data = True          # the tree is kept between pictures
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 95
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "Standard"  # the page does no tone mapping
    sc.view_settings.look = "None"
    sc.display_settings.display_device = "sRGB"

    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    cam.data.sensor_fit = "VERTICAL"
    sc.collection.objects.link(cam)
    sc.camera = cam
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.angle = 0.03                         # a slightly soft shadow edge
    sc.collection.objects.link(sun)

    # the room: a sky brighter overhead; the camera itself sees the page's flat backdrop
    w = bpy.data.worlds.new("room")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = -1.0
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = SKY_BOTTOM + (1,)
    mix.inputs["B"].default_value = SKY_TOP + (1,)
    sky = nt.nodes.new("ShaderNodeBackground")
    back = nt.nodes.new("ShaderNodeBackground")
    back.name = "backdrop"
    path = nt.nodes.new("ShaderNodeLightPath")
    pick = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(geo.outputs["Incoming"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Value"])
    nt.links.new(ramp.outputs["Result"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], sky.inputs["Color"])
    nt.links.new(path.outputs["Is Camera Ray"], pick.inputs["Fac"])
    nt.links.new(sky.outputs[0], pick.inputs[1])
    nt.links.new(back.outputs[0], pick.inputs[2])
    nt.links.new(pick.outputs[0], out.inputs["Surface"])
    sc.world = w
    return device


def linear(c):
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def mat4(m):                                       # the page's 16 numbers, column-major
    return Matrix([m[0:16:4], m[1:16:4], m[2:16:4], m[3:16:4]])


def render(q):
    t = time.perf_counter()
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = int(q["w"]), int(q["h"])
    sc.cycles.samples = int(q.get("samples", 64))
    cam = sc.camera
    cam.matrix_world = C @ mat4(q["cam"])
    cam.data.angle_y = np.radians(q["fov"])
    cam.data.clip_start, cam.data.clip_end = q.get("near", 1), q.get("far", 20000)
    sun = bpy.data.objects["sun"]
    d = (C.to_3x3() @ Vector(q.get("sun", (3, 4, 2)))).normalized()   # towards the sun
    sun.rotation_euler = d.to_track_quat("Z", "Y").to_euler()     # a sun shines down its -Z
    sun.data.energy = q.get("sun_strength", 2.4)
    bg = linear(q.get("bg", (0.086, 0.094, 0.110)))
    sc.world.node_tree.nodes["backdrop"].inputs["Color"].default_value = (bg[0], bg[1], bg[2], 1)
    hidden, poses, printed = set(q.get("hidden", ())), q.get("poses", {}), bool(q.get("printed"))
    # ONLY WHAT CHANGED IS TOUCHED: whatever is touched is rebuilt on the card
    for name, (ob, plain, filament) in parts.items():
        hide = name in hidden                      # hidden from every kind of ray
        if ob.visible_camera == hide:
            for ray in ("camera", "diffuse", "glossy", "transmission", "volume_scatter", "shadow"):
                setattr(ob, "visible_" + ray, not hide)
        p = poses.get(name)
        key = tuple(round(x, 4) for x in p) if p else None
        if posed.get(name) != key:
            posed[name] = key
            ob.matrix_world = C @ mat4(p) if p else Matrix.Identity(4)
        want = plain
        if printed and filament in PRINTED:
            rgb, rough = PRINTED[filament]
            want = material("printed:" + filament,
                            rgb + (CLEAR if filament.endswith("-clear") else 1,), rough)
        if ob.data.materials[0] is not want:
            ob.data.materials[0] = want
    sc.render.filepath = q["out"]
    bpy.ops.render.render(write_still=True)
    return dict(out=q["out"], seconds=round(time.perf_counter() - t, 3))


def main():
    device = setup()
    reply(ready=True, device=device, blender=bpy.app.version_string)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            q = json.loads(line)
            if q["op"] == "quit":
                break
            r = load(q["glb"]) if q["op"] == "load" else render(q)
            reply(id=q.get("id"), ok=True, **r)
        except Exception as e:                     # one bad request must not end the process
            reply(id=None, ok=False, error="%s: %s" % (type(e).__name__, e))


main()
