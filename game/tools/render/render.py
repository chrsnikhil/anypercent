"""Render one SHIP IT! scene with Blender 4.0 (Cycles, CPU): the whole room image, footprints.json, and every
character frame (devs with their desk as holdouts). Normally run by `make -f tools.mk art`:
  blender -b --python-exit-code 1 -P tools/render/render.py -- --scene office --out art/renders/office
    [--only room,chars] [--samples 64] [--char-samples 32] [--quick]
"""
import argparse
import importlib
import json
import math
import os
import sys

import bpy
import mathutils
from bpy_extras.object_utils import world_to_camera_view

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import charspec  # noqa: E402
import iso  # noqa: E402

KENNEY = os.environ.get("KENNEY", "/opt/arca-sandbox/assets/kenney")
FURNITURE = os.path.join(KENNEY, "furniture-kit", "Models", "GLTF format")
CHARACTERS = os.path.join(KENNEY, "mini-characters", "Models", "GLB format")
TEXTURES = os.path.join(GAME, "art", "textures")
VARIANT = "day"             # set by --variant: day, night or dawn
NIGHT = False


def lin(rgb):
    """sRGB 0-255 -> linear 0-1 (Blender colour inputs are linear)."""
    return tuple(((c / 255 + 0.055) / 1.055) ** 2.4 for c in rgb)


def reset(samples):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy, sun.angle, sun.color = 3.0, 0.2, (1.0, 0.9, 0.78)
    so = bpy.data.objects.new("sun", sun)
    sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(42), 0, math.radians(-35))
    world = bpy.data.worlds.new("sky")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.85, 0.9, 1, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.45
    return sc


def camera(sc, ortho, target, width, height, shift=(0.0, 0.0)):
    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    cam.ortho_scale = ortho
    cam.shift_x, cam.shift_y = shift
    obj = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(obj)
    sc.camera = obj
    obj.rotation_euler = (math.radians(90 - iso.ELEV), 0, math.radians(iso.AZIM))
    back = obj.rotation_euler.to_matrix() @ mathutils.Vector((0, 0, 1))
    obj.location = mathutils.Vector(target) + back * 20
    sc.render.resolution_x, sc.render.resolution_y = width, height
    return obj


def render(sc, path):
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def world_box(objs):
    pts = []
    for o in objs:
        for c in [o] + list(o.children_recursive):
            if c.type == "MESH":
                pts += [c.matrix_world @ mathutils.Vector(b) for b in c.bound_box]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


def place(path, at, rot=0.0, scale=1.0, centre=True):
    """Import a glTF model under a pivot. With centre, the footprint is centred on (at[0], at[1])."""
    before, acts = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    roots = [o for o in new if o.parent is None]
    pivot = bpy.data.objects.new("pivot", None)
    bpy.context.scene.collection.objects.link(pivot)
    bpy.context.view_layer.update()
    cx = cy = 0.0
    if centre:
        lo, hi = world_box(roots)
        cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    for r in roots:
        r.parent = pivot
        r.location = (r.location.x - cx, r.location.y - cy, r.location.z)
    pivot.location = at
    pivot.rotation_euler = (0, 0, math.radians(rot))
    pivot.scale = (scale,) * 3
    bpy.context.view_layer.update()
    return pivot, new, [a for a in bpy.data.actions if a not in acts]


def furniture(name, at, rot=0.0):
    return place(os.path.join(FURNITURE, name + ".glb"), at, rot)


def recolour(objs, table):
    """Give the listed Kenney materials (by base name) a new sRGB colour, or a dict of BSDF input values."""
    for o in objs:
        if o.type != "MESH":
            continue
        for slot in o.material_slots:
            base = slot.material.name.split(".")[0]
            if base not in table:
                continue
            m = slot.material.copy()
            slot.material = m
            bsdf = m.node_tree.nodes["Principled BSDF"]
            value = table[base]
            if isinstance(value, dict):
                for k, v in value.items():
                    bsdf.inputs[k].default_value = v
            else:
                bsdf.inputs["Base Color"].default_value = (*lin(value), 1)


def material(name, rgb, metal=0.0, rough=0.6, texture=None, emit=0.0, pixel=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*lin(rgb), 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if texture:
        t = m.node_tree.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(os.path.join(TEXTURES, texture + ".png"))
        m.node_tree.links.new(t.outputs[0], b.inputs["Base Color"])
        if pixel:
            t.interpolation = "Closest"
            m.node_tree.links.new(t.outputs[1], b.inputs["Alpha"])
        if emit:
            m.node_tree.links.new(t.outputs[0], b.inputs["Emission Color"])
            b.inputs["Emission Strength"].default_value = emit
    return m


def prim(kind, loc, rot=(0, 0, 0), scale=(1, 1, 1), mat=None, **kw):
    getattr(bpy.ops.mesh, "primitive_%s_add" % kind)(location=loc, rotation=rot, **kw)
    o = bpy.context.active_object
    o.scale = scale
    if mat:
        o.data.materials.append(mat)
    return o


def room_shell(scene):
    w, h = scene.ROOM["w"], scene.ROOM["h"]
    nx, ny = math.ceil(w), math.ceil(h)
    walls = {"_defaultMat": scene.WALL_PAINT, "wood": scene.WALL_TRIM}
    glass = {"Alpha": 0.12, "Base Color": (1, 1, 1, 1)}
    for i in range(nx):
        for j in range(ny):
            recolour(furniture("floorFull", (i + 0.5, j + 0.5, 0))[1], {"wood": scene.FLOOR})
    for i in range(nx):
        name = "wallWindow" if i in scene.BACK_WINDOWS else "wall"
        recolour(furniture(name, (i + 0.5, h + 0.02, 0))[1], dict(walls, glass=glass))
    for j in range(ny):
        name = "wallDoorway" if j in scene.LEFT_DOORS else "wall"
        recolour(furniture(name, (-0.02, j + 0.5, 0), rot=90)[1], walls)


def prop_decal(p):
    rot = (math.radians(90), 0, math.radians(90)) if p["wall"] == "left" else (math.radians(90), 0, 0)
    sx, sy = p["size"]
    mat = material("decal_" + p["texture"], (255, 255, 255), rough=0.5, texture=p["texture"], emit=p.get("emit", 0),
                   pixel=p.get("pixel", False))
    prim("plane", p["at"], rot, (sx / 2, sy / 2, 1), mat)
    if p.get("frame"):
        x, y, z = p["at"]
        prim("cube", (x, y + 0.005, z), scale=(sx / 2 + 0.015, 0.004, sy / 2 + 0.015),
             mat=material("decal_frame", (160, 168, 180), metal=0.6, rough=0.4))


def prop_toran(p):
    orange = material("marigold", (255, 140, 0), rough=0.7)
    yellow = material("marigold_yellow", (255, 200, 20), rough=0.7)
    y0, y1 = p["y"]
    n = 14
    for k in range(n + 1):
        t = k / n
        z = p["z"] - 0.07 * math.sin(math.pi * t)
        prim("uv_sphere", (p["x"], y0 + (y1 - y0) * t, z), mat=orange if k % 2 else yellow,
             radius=0.032, segments=8, ring_count=6)
    for t in (0.2, 0.5, 0.8):
        z0 = p["z"] - 0.07 * math.sin(math.pi * t)
        for j in range(1, 4):
            prim("uv_sphere", (p["x"], y0 + (y1 - y0) * t, z0 - 0.055 * j), mat=orange if j % 2 else yellow,
                 radius=0.03, segments=8, ring_count=6)


def prop_kettle(p):
    steel = material("steel", (200, 205, 212), metal=0.9, rough=0.25)
    x, y, z = p["at"]
    prim("cylinder", (x, y, z + 0.07), scale=(0.065, 0.065, 0.07), mat=steel, vertices=16)
    prim("cone", (x, y, z + 0.17), scale=(0.065, 0.065, 0.03), mat=steel, vertices=16)
    prim("cylinder", (x + 0.07, y, z + 0.1), rot=(0, math.radians(60), 0), scale=(0.012, 0.012, 0.05),
         mat=steel, vertices=8)


def prop_chai_tray(p):
    x, y, z = p["at"]
    prim("cylinder", (x, y, z + 0.005), scale=(0.1, 0.1, 0.004),
         mat=material("tray", (150, 155, 160), metal=0.8, rough=0.35), vertices=20)
    chai = material("chai", (196, 120, 58), rough=0.3)
    for dy, dx in ((-0.045, -0.03), (0.0, 0.03), (0.045, -0.03)):
        prim("cylinder", (x + dx, y + dy, z + 0.035), scale=(0.022, 0.022, 0.028), mat=chai, vertices=10)


def prop_notes(p):
    colours = [(255, 226, 90), (255, 150, 190), (140, 230, 160), (255, 226, 90), (140, 200, 255)]
    for k, (x, z) in enumerate(p["spots"]):
        prim("plane", (x, p["y"], z), (math.radians(90), 0, math.radians((k % 3 - 1) * 4)), (0.035, 0.035, 1),
             material("note%d" % k, colours[k % len(colours)], rough=0.9))


def prop_backdrop(p):
    """The view out of the window: seen by the camera only, so it neither lights nor shades the room."""
    sx, sy = p["size"]
    texture = p["texture"] if VARIANT == "day" else p["texture"].replace("_day", "_" + VARIANT)
    o = prim("plane", p["at"], (math.radians(90), 0, 0), (sx / 2, sy / 2, 1),
             material("backdrop_" + texture, (255, 255, 255), rough=1, texture=texture, emit=1.0))
    o.visible_shadow = o.visible_diffuse = o.visible_glossy = False


def prop_router(p):
    x, y, z = p["at"]
    body = material("router", (40, 42, 52), rough=0.4)
    prim("cube", (x, y, z + 0.03), scale=(0.07, 0.11, 0.03), mat=body)
    for dy in (-0.07, 0.07):
        prim("cylinder", (x, y + dy, z + 0.12), scale=(0.008, 0.008, 0.07), mat=body, vertices=6)
    led = material("router_led", (80, 255, 120))
    led.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (0.2, 1.0, 0.4, 1)
    led.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 4.0
    for k in range(3):
        prim("cube", (x + 0.071, y - 0.04 + 0.04 * k, z + 0.035), scale=(0.004, 0.008, 0.005), mat=led)


def footprint(model, lo, hi, low=False):
    """A blocking footprint for a custom prop. Low pieces (the stage, the rope) block the feet but never hide
    the player, so the collision tool skips its drawn-over test for them."""
    return {"model": model, "min": list(lo), "max": list(hi), "block": True, "front": False, "low": low,
            "names": set()}


def prop_stage(p):
    (x0, y0), (x1, y1), h = p["from"], p["to"], p["height"]
    prim("cube", ((x0 + x1) / 2, (y0 + y1) / 2, h / 2), scale=((x1 - x0) / 2, (y1 - y0) / 2, h / 2),
         mat=material("stage", (58, 44, 40), rough=0.7))
    return [footprint("stage", (x0, y0, 0), (x1, y1, h), low=True)]


def prop_orb(p):
    x, y, z = p["at"]
    orb = material("orb", (230, 236, 255), metal=0.3, rough=0.15, emit=0.8)
    prim("uv_sphere", (x, y, z + 0.12), mat=orb, radius=0.12, segments=24, ring_count=12)
    prim("cylinder", (x, y, z + 0.01), scale=(0.1, 0.1, 0.01), mat=material("orb_base", (40, 40, 48), metal=0.6))


def prop_rope(p):
    x, (y0, y1), (g0, g1) = p["x"], p["y"], p["gate"]
    gold = material("stanchion", (220, 180, 60), metal=0.9, rough=0.3)
    red = material("rope", (170, 20, 40), rough=0.6)
    out = []
    for a, b in ((y0, g0), (g1, y1)):
        n = max(1, round((b - a) / 0.35))
        for k in range(n + 1):
            prim("cylinder", (x, a + (b - a) * k / n, 0.18), scale=(0.02, 0.02, 0.18), mat=gold, vertices=10)
        prim("cylinder", (x, (a + b) / 2, 0.3), rot=(math.radians(90), 0, 0), scale=(0.012, 0.012, (b - a) / 2),
             mat=red, vertices=8)
        out.append(footprint("rope", (x - 0.03, a, 0), (x + 0.03, b, 0.36), low=True))
    return out


def prop_person(p):
    """A standing Kenney character baked into the room (booth staff): the idle animation's first frame."""
    pivot, objs, acts = place(os.path.join(CHARACTERS, p["model"] + ".glb"), p["at"], p.get("rot", 0.0),
                              charspec.CHAR_SCALE, centre=False)
    arm = next(o for o in objs if o.type == "ARMATURE")
    arm.animation_data_create()
    arm.animation_data.action = find_action(acts, "idle")
    bpy.context.scene.frame_set(int(arm.animation_data.action.frame_range[0]))


def prop_floor_decal(p):
    sx, sy = p["size"]
    mat = material("floor_" + p["texture"], (255, 255, 255), rough=0.8, texture=p["texture"],
                   pixel=p.get("pixel", False))
    x, y = p["at"]
    prim("plane", (x, y, p.get("z", 0.055)), (0, 0, math.radians(p.get("rot", 0))), (sx / 2, sy / 2, 1), mat)   # rug height


def point_light(sc, at, watts, colour):
    light = bpy.data.lights.new("point", "POINT")
    light.energy, light.color, light.shadow_soft_size = watts, colour, 0.1
    obj = bpy.data.objects.new("point", light)
    sc.collection.objects.link(obj)
    obj.location = at


PROPS = {"router": prop_router, "decal": prop_decal, "toran": prop_toran, "kettle": prop_kettle, "chai_tray": prop_chai_tray,
         "notes": prop_notes, "backdrop": prop_backdrop, "stage": prop_stage, "orb": prop_orb, "rope": prop_rope,
         "person": prop_person, "floor_decal": prop_floor_decal}


def render_room(scene, out, samples):
    sc = reset(samples)
    room_shell(scene)
    pieces = []
    for p in scene.PIECES:
        pivot, objs, _ = furniture(p["model"], p["at"], p.get("rot", 0.0))
        if p.get("colours"):
            recolour(objs, p["colours"])
        lo, hi = world_box([pivot])
        pieces.append({"model": p["model"], "min": lo, "max": hi, "block": p.get("block", True),
                       "front": p.get("front", False), "low": p.get("low", False), "names": {o.name for o in objs}})
    for prop in scene.PROPS:
        pieces += PROPS[prop["type"]](prop) or []
    if NIGHT:
        sun = bpy.data.objects["sun"].data
        sun.energy, sun.color = 0.4, (0.6, 0.7, 1.0)
        bg = sc.world.node_tree.nodes["Background"]
        bg.inputs[0].default_value = (0.05, 0.07, 0.15, 1)
        bg.inputs[1].default_value = 0.3
        for p in scene.PIECES:
            x, y, _ = p["at"]
            if p["model"] == "lampRoundFloor":
                point_light(sc, (x, y, 1.0), 60, (1.0, 0.75, 0.45))
            elif p["model"] == "laptop":
                point_light(sc, (x, y - 0.12, 0.55), 8, (0.8, 0.9, 1.0))
    if VARIANT == "dawn":
        sun = bpy.data.objects["sun"]
        sun.data.energy, sun.data.color = 3.2, (1.0, 0.56, 0.3)
        sun.rotation_euler = (math.radians(66), 0, math.radians(-60))     # low and golden, long shadows
        bg = sc.world.node_tree.nodes["Background"]
        bg.inputs[0].default_value = (0.85, 0.55, 0.42, 1)
        bg.inputs[1].default_value = 0.5
    w, h = scene.CAMERA["size"]
    cam = camera(sc, scene.CAMERA["ortho"], scene.CAMERA["target"], w * iso.SCALE, h * iso.SCALE)
    render(sc, os.path.join(out, "room.png"))
    anchors = {}
    for name, at in scene.ANCHORS.items():
        u = world_to_camera_view(sc, cam, mathutils.Vector(at))
        anchors[name] = {"world": list(at), "screen": [u.x * w, (1 - u.y) * h]}
    footprints = {"scene": scene.NAME,
                  "camera": {"ortho": scene.CAMERA["ortho"], "target": list(scene.CAMERA["target"]), "size": [w, h]},
                  "room": scene.ROOM, "anchors": anchors,
                  "pieces": [{k: p[k] for k in ("model", "min", "max", "block", "front", "low")} for p in pieces]}
    with open(os.path.join(out, "footprints.json"), "w") as f:
        json.dump(footprints, f, indent=1)


def find_action(acts, name):
    return next(a for a in acts if a.name.rsplit("_", 1)[0] == name)


def mixed_action(base, overlay, bones, name):
    """A new action: the base action's bone curves, with `bones` taken from the overlay action instead."""
    act = bpy.data.actions.new(name)
    for src, take in ((base, lambda b: b not in bones), (overlay, lambda b: b in bones)):
        if src is None:
            continue
        for fc in src.fcurves:
            if not fc.data_path.startswith("pose.bones["):
                continue
            bone = fc.data_path.split('"')[1]
            if not take(bone):
                continue
            nf = act.fcurves.new(fc.data_path, index=fc.array_index, action_group=bone)
            nf.keyframe_points.add(len(fc.keyframe_points))
            for i, kp in enumerate(fc.keyframe_points):
                nf.keyframe_points[i].co = kp.co
                nf.keyframe_points[i].interpolation = kp.interpolation
            nf.update()
    return act


def render_character(model, anims, facings, out, samples, px_per_unit, frame, feet, holdouts=(), quick=False,
                     scale=charspec.CHAR_SCALE):
    """Render each animation frame for each facing (d, degrees) as <label>_d<d>_f<frame>.png at 4x, plus
    hands.json (the right hand in frame pixels). Holdouts (model, offset, rot) hide what stands in front."""
    os.makedirs(out, exist_ok=True)
    sc = reset(samples)
    fw, fh = frame
    big = max(fw, fh)
    shift = ((fw / 2 - feet[0]) / big, (feet[1] - fh / 2) / big)
    cam = camera(sc, big / px_per_unit, (0, 0, 0), fw * iso.SCALE, fh * iso.SCALE, shift)
    for name, offset, rot in holdouts:
        _, objs, _ = furniture(name, offset, rot)
        for o in objs:
            if o.type == "MESH":
                o.is_holdout = True
    pivot, objs, acts = place(os.path.join(CHARACTERS, model + ".glb"), (0, 0, 0), 0.0, scale, centre=False)
    arm = next(o for o in objs if o.type == "ARMATURE")
    arm.animation_data_create()
    for t in list(arm.animation_data.nla_tracks):
        arm.animation_data.nla_tracks.remove(t)
    hands = {}
    for label, base, overlay, count in anims:
        base_act = find_action(acts, base)
        arm.animation_data.action = mixed_action(base_act, find_action(acts, overlay) if overlay else None,
                                                 charspec.OVERLAY_BONES.get(overlay, set()), label)
        f0, f1 = base_act.frame_range
        for d, degrees in (facings[:1] if quick else facings):
            pivot.rotation_euler = (0, 0, math.radians(degrees))
            for f in range(1 if quick else count):
                t = f0 + (f1 - f0) * f / count
                sc.frame_set(int(t), subframe=t - int(t))
                key = "%s_d%d_f%d" % (label, d, f)
                render(sc, os.path.join(out, key + ".png"))
                bone = arm.pose.bones["arm-right"]       # Kenney arm bones point up from the shoulder:
                hand = bone.head + (bone.head - bone.tail) * 0.9       # the hand hangs a bone-length below the joint
                u = world_to_camera_view(sc, cam, arm.matrix_world @ hand)
                hands[key] = [u.x * fw, (1 - u.y) * fh]
    with open(os.path.join(out, "hands.json"), "w") as f:
        json.dump(hands, f, indent=1)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="office")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="room,chars")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--char-samples", type=int, default=32)
    ap.add_argument("--quick", action="store_true", help="first facing and first frame of each animation only")
    ap.add_argument("--variant", default="day", choices=("day", "night", "dawn"))
    a = ap.parse_args(argv)
    global VARIANT, NIGHT
    VARIANT = a.variant
    NIGHT = VARIANT == "night"
    scene = importlib.import_module("scenes." + a.scene)
    os.makedirs(a.out, exist_ok=True)
    parts = a.only.split(",")
    if "room" in parts:
        render_room(scene, a.out, a.samples)
    if "chars" in parts and VARIANT == "day" and hasattr(scene, "ATTENDEES"):
        k = scene.CAMERA["size"][0] / scene.CAMERA["ortho"]
        facings = [(d, charspec.facing_degrees(d)) for d in range(charspec.DIRS)]
        for i, model in enumerate(scene.ATTENDEES):
            render_character(model, charspec.CROWD_ANIMS, facings, os.path.join(a.out, "chars", "crowd%d" % i),
                             a.char_samples, k, charspec.CROWD_FRAME, charspec.CROWD_FEET, quick=a.quick)
    elif "chars" in parts and VARIANT == "day":
        k = scene.CAMERA["size"][0] / scene.CAMERA["ortho"]
        facings = [(d, charspec.facing_degrees(d)) for d in range(charspec.DIRS)]
        render_character(scene.PLAYER, charspec.PLAYER_ANIMS, facings, os.path.join(a.out, "chars", "player"),
                         a.char_samples, k, charspec.PLAYER_FRAME, charspec.FEET, quick=a.quick)
        for i, model in enumerate(scene.DEVS):
            render_character(model, charspec.DEV_ANIMS, [(0, scene.DEV_ROT)], os.path.join(a.out, "chars", "dev%d" % i),
                             a.char_samples, k, charspec.DEV_FRAME, charspec.DEV_FEET, scene.DEV_HOLDOUTS, a.quick,
                             charspec.DEV_SCALE)
    print("RENDER DONE")


main()
