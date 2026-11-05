"""Render MARINE DRIVE GP's kart sprites from the Kenney Car Kit kart models with Blender 4.0 (Cycles, CPU):
16 headings per kart, each in three steering poses, seen from 30 degrees above the ground, orthographic, at 4x size
(128 x 128 per frame). Frame i shows the kart turned i * 22.5 degrees clockwise (seen from above) from "driving away
from the camera"; pose L / C / R: the kart yawed YAW_DEG into the turn (so a turn reads from behind, where the player sees its own kart
all race), the front wheels turned STEER_DEG, the driver leaning LEAN_DEG into the turn and the body rolling ROLL_DEG
out of it (written kart<k>_<ii>_<L|C|R>.png; C is the plain render, so --poses L,R can reuse kart<k>_<ii>.png).
    blender -b --python-exit-code 1 -P tools/render/render_karts.py -- --out art/renders/karts [--samples 24]
tools/art/build_sprites.py shrinks, quantizes and packs them."""
import argparse
import math
import os
import sys

import bpy
import mathutils

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
MODELS = os.path.join(GAME, "art", "kenney", "car-kit")
KARTS = ["kart-oopi", "kart-oobi", "kart-oodi", "kart-ooli"]    # player, rival 1, 2, 3
FRAMES = 16
ELEV = 30.0
SIZE = 128
STEER_DEG, LEAN_DEG, ROLL_DEG, YAW_DEG = 28.0, 16.0, 5.0, 12.0
# (name, sign): sign +1 turns left. The model's front is -Y: +Z rotation points the wheels to the driver's left (+X),
# +Y rotation leans the top toward +X (the driver's left).
POSES = (("L", 1), ("C", 0), ("R", -1))


def reset(samples):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "Standard"
    sc.render.resolution_x = sc.render.resolution_y = SIZE
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy, sun.angle = 3.2, 0.3
    so = bpy.data.objects.new("sun", sun)
    sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(35), math.radians(-20), math.radians(-30))
    world = bpy.data.worlds.new("sky")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.93, 1, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    cam.ortho_scale = 3.0
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    el = math.radians(ELEV)
    co.rotation_euler = (math.radians(90) - el, 0, 0)
    co.location = (0, -20 * math.cos(el), 20 * math.sin(el) + 0.55)
    return sc


def load(name):
    """The kart under one empty pivot, centred on its footprint, scaled to 2 units long, front along +Y."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(MODELS, name + ".glb"))
    objs = [o for o in bpy.data.objects if o not in before]
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ mathutils.Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    lo = mathutils.Vector([min(p[i] for p in pts) for i in range(3)])
    hi = mathutils.Vector([max(p[i] for p in pts) for i in range(3)])
    size = max(hi.x - lo.x, hi.y - lo.y)
    pivot = bpy.data.objects.new("pivot", None)
    bpy.context.scene.collection.objects.link(pivot)
    centre = mathutils.Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    for o in objs:
        if o.parent is None:
            o.location -= centre
            o.parent = pivot
    pivot.scale = (2.0 / size,) * 3
    return pivot


def pose(sign):
    """Steering pose on the kart's own parts only (never the pivot, which holds the heading): the body yawed into the
    turn about Z and rolled out of it about Y, the front wheels about Z, the driver about Y (into the turn)."""
    for o in bpy.data.objects:
        if not (o.name.startswith("wheel-front") or o.name == "character" or o.name.startswith("kart-")):
            continue
        base = o.get("rest")
        if base is None:
            o.rotation_mode = "XYZ"                 # the glTF importer leaves quaternions, which ignore rotation_euler
            o["rest"] = list(o.rotation_euler)
            base = o["rest"]
        r = list(base)
        if o.name.startswith("wheel-front"):
            r[2] = base[2] + math.radians(STEER_DEG) * sign
        elif o.name == "character":
            r[1] = base[1] + math.radians(LEAN_DEG) * sign
        else:
            r[1] = base[1] - math.radians(ROLL_DEG) * sign
            r[2] = base[2] + math.radians(YAW_DEG) * sign
        o.rotation_euler = r


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(GAME, "art", "renders", "karts"))
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--base", type=float, default=180.0, help="yaw that makes the model drive away (+Y)")
    ap.add_argument("--only", default="")
    ap.add_argument("--poses", default="L,C,R", help="which poses to render (C equals the plain kart<k>_<ii>.png)")
    ap.add_argument("--headings", default="", help="comma list of heading frames (default: all 16)")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    for k, name in enumerate(KARTS):
        if a.only and str(k) not in a.only.split(","):
            continue
        sc = reset(a.samples)
        pivot = load(name)
        for f in range(FRAMES):
            if a.headings and str(f) not in a.headings.split(","):
                continue
            pivot.rotation_euler = (0, 0, math.radians(a.base - f * 360.0 / FRAMES))
            for tag, sign in POSES:
                if tag not in a.poses.split(","):
                    continue
                pose(sign)
                sc.render.filepath = os.path.join(a.out, "kart%d_%02d_%s.png" % (k, f, tag))
                bpy.ops.render.render(write_still=True)


main()
