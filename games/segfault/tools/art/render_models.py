"""Renders SEGFAULT's 3D billboards with Blender 4.0 (Cycles, CPU) into art/renders/ (RGBA PNGs, transparent):
  bug_walk1, bug_walk2, bug_attack, bug_dead: a procedural bug built from primitives (shell, thorax, head, glowing
      eyes, mandibles, six jointed legs), seen from the front, a little above;
  blaster_idle, blaster_fire: Kenney's blaster-j (Blaster Kit, CC0) from behind, first person.
tools/art/build_art.py turns these into the game's palette. Run from the game directory:
  blender -b --python-exit-code 1 -P tools/art/render_models.py -- [--samples 48]"""
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(GAME, "art", "renders")
BLASTER = os.path.join(GAME, "art", "kenney", "blaster-kit", "blaster-j.glb")
SAMPLES = int(sys.argv[sys.argv.index("--samples") + 1]) if "--samples" in sys.argv else 48


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = False
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    world = bpy.data.worlds.new("w")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.2, 0.25, 0.3, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.35
    return sc


def light(sc, name, kind, energy, rot, color=(1, 1, 1), loc=(0, 0, 5), size=1.0):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    if kind == "SUN":
        ld.angle = 0.3
    else:
        ld.shadow_soft_size = size
    ob = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    return ob


def camera(sc, loc, target, lens=50, ortho=None):
    cd = bpy.data.cameras.new("cam")
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    else:
        cd.lens = lens
    ob = bpy.data.objects.new("cam", cd)
    sc.collection.objects.link(ob)
    ob.location = loc
    d = [t - l for t, l in zip(target, loc)]
    import mathutils
    ob.rotation_euler = mathutils.Vector(d).to_track_quat("-Z", "Y").to_euler()
    sc.camera = ob
    return ob


def mat(name, color, rough=0.4, metal=0.0, emit=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    if emit:
        p.inputs["Emission Color"].default_value = (*emit, 1)
        p.inputs["Emission Strength"].default_value = strength
    return m


def sphere(name, loc, scale, material, seg=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=seg // 2, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = scale
    bpy.ops.object.shade_smooth()
    ob.data.materials.append(material)
    return ob


def rod(name, a, b, radius, material):
    """A cylinder from point a to point b."""
    import mathutils
    va, vb = mathutils.Vector(a), mathutils.Vector(b)
    d = vb - va
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=radius, depth=d.length, location=(va + vb) / 2)
    ob = bpy.context.active_object
    ob.name = name
    ob.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    bpy.ops.object.shade_smooth()
    ob.data.materials.append(material)
    sphere(name + "_j", b, (radius * 1.2,) * 3, material, seg=8)
    return ob


def render(sc, name, size):
    sc.render.resolution_x = sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.render.filepath = os.path.join(OUT, name + ".png")
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    bpy.ops.render.render(write_still=True)


def build_bug(pose):
    """pose: walk1, walk2, attack, dead. The bug faces -Y (toward the camera)."""
    shell = mat("shell", (0.28, 0.05, 0.36), rough=0.25, metal=0.3)
    stripe = mat("stripe", (0.1, 0.9, 0.3), rough=0.5, emit=(0.1, 1.0, 0.35), strength=2.5)
    dark = mat("dark", (0.05, 0.07, 0.06), rough=0.5)
    thorax_m = mat("thorax", (0.08, 0.25, 0.12), rough=0.3, metal=0.2)
    eye_on = 6.0 if pose == "attack" else (0.0 if pose == "dead" else 3.5)
    eye = mat("eye", (1.0, 0.1, 0.05), rough=0.2, emit=(1.0, 0.08, 0.02), strength=eye_on)
    leg_m = mat("leg", (0.12, 0.1, 0.14), rough=0.5, metal=0.2)
    squash = 0.35 if pose == "dead" else 1.0
    lunge = -0.25 if pose == "attack" else 0.0
    z0 = 0.2 if pose == "dead" else 0.62
    sphere("abdomen", (0, 0.55, z0 + 0.05), (0.62, 0.8, 0.45 * squash), shell)
    for k in range(3):                                   # glowing code stripes across the shell
        y = 0.25 + k * 0.28
        bpy.ops.mesh.primitive_torus_add(major_radius=0.5 - k * 0.07, minor_radius=0.025,
                                         location=(0, y, z0 + 0.05 + 0.18 * squash))
        t = bpy.context.active_object
        t.rotation_euler = (math.radians(90 - 15 * k), 0, 0)
        t.scale = (1.0, 1.0, 0.6 * squash)
        t.data.materials.append(stripe)
    sphere("thorax", (0, -0.2 + lunge * 0.4, z0), (0.42, 0.36, 0.32 * squash), thorax_m)
    hy, hz = -0.62 + lunge, z0 + (0.02 if pose != "dead" else -0.05)
    sphere("head", (0, hy, hz), (0.3, 0.28, 0.25 * squash), dark)
    for sx in (-1, 1):
        sphere("eye", (sx * 0.13, hy - 0.22, hz + 0.08 * squash), (0.09, 0.07, 0.08 * squash), eye)
        spread = 0.22 if pose == "attack" else 0.1
        rod("mand", (sx * 0.1, hy - 0.2, hz - 0.1 * squash), (sx * spread, hy - 0.5, hz - 0.12 * squash), 0.035,
            leg_m)
        if pose != "dead":
            rod("ant", (sx * 0.08, hy - 0.1, hz + 0.18), (sx * 0.35, hy - 0.4, hz + 0.75), 0.018, leg_m)
    for side in (-1, 1):
        for k, y in enumerate((-0.35, -0.1, 0.15)):
            phase = (k + (0 if side > 0 else 1)) % 2
            if pose == "walk2":
                phase = 1 - phase
            swing = (0.15 if phase else -0.15) if pose in ("walk1", "walk2") else 0.0
            if pose == "dead":
                knee = (side * 0.8, y * 1.6, 0.12)
                foot = (side * 1.3, y * 2.2 + 0.1, 0.02)
            else:
                knee = (side * 0.75, y + swing, z0 + 0.35 + (0.08 if phase else 0.0))
                foot = (side * 1.05, y + swing * 2 - 0.1, 0.0)
            rod("femur", (side * 0.3, y * 0.6, z0), knee, 0.045, leg_m)
            rod("tibia", knee, foot, 0.035, leg_m)
    if pose == "dead":                                   # a puddle of green goo
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=1.1, depth=0.02, location=(0, 0.1, 0.01))
        goo = bpy.context.active_object
        goo.scale = (1.2, 0.8, 1)
        goo.data.materials.append(mat("goo", (0.2, 0.9, 0.2), rough=0.1, emit=(0.1, 0.8, 0.2), strength=0.8))


def bugs():
    for pose in ("walk1", "walk2", "attack", "dead"):
        sc = reset()
        build_bug(pose)
        light(sc, "key", "SUN", 3.5, (50, 0, 25), (1.0, 0.95, 0.9))
        light(sc, "rim", "AREA", 250, (-70, 0, 180), (0.3, 0.8, 1.0), loc=(0, 3, 2.5), size=2)
        camera(sc, (0, -3.1, 2.3), (0, 0.1, 0.42), lens=50)
        render(sc, "bug_" + pose, 128)


def blasters():
    import mathutils
    for pose in ("idle", "fire"):
        sc = reset()
        sc.world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
        bpy.ops.import_scene.gltf(filepath=BLASTER)
        objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        pts = [o.matrix_world @ mathutils.Vector(v) for o in objs for v in o.bound_box]
        lo = [min(p[k] for p in pts) for k in range(3)]
        hi = [max(p[k] for p in pts) for k in range(3)]
        # the kit's muzzles point along +Y; the camera sits behind the grip, a little left and above, looking
        # along the barrel: the first-person view of a gun held in the right hand
        light(sc, "key", "SUN", 4.5, (35, 0, -20), (1.0, 0.97, 0.92))
        light(sc, "fill", "SUN", 1.5, (70, 0, 160), (0.5, 0.8, 1.0))
        if pose == "fire":
            fl = mat("flash", (1, 1, 0.6), emit=(0.55, 1.0, 0.45), strength=14.0)
            sphere("flash", (0, hi[1] + 0.07, hi[2] - 0.08), (0.09, 0.06, 0.09), fl)
            light(sc, "muzzle", "POINT", 20, (0, 0, 0), (0.6, 1.0, 0.5), loc=(0, hi[1], hi[2]), size=0.1)
        camera(sc, (-0.10, lo[1] - 0.2, hi[2] + 0.1), (0.02, hi[1] + 0.5, lo[2] + 0.1), lens=24)
        render(sc, "blaster_" + pose, 128)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    bugs()
    blasters()
