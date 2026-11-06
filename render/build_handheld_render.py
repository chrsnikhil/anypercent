"""
ETHGlobal Mumbai 2026 - verifiable speedrun handheld product render, rev 4.

Clean custom handheld design around the GamePi43 body envelope, plus three
full-footprint swappable magnetic sponsor rear panels (World, 0G, Arkiv).
Renders product shots with Cycles.

Revision note
-------------
Rev 1 chased fidelity to the real Waveshare GamePi43 kit (D-pad, HK key,
LED arrays, edge key rows, rotated silkscreen). Client direction for rev 2:
keep only the body envelope and the display as physical constraints and
design a clean product around them. Everything else below is therefore a
DESIGN choice, labelled as such, not a measurement of any real device.
Rev 3 (this file) touches ONLY the rear sponsor panels: the plain Arial
wordmarks are replaced with the sponsors' real logo geometry imported from
official SVG assets and raised as printed-style emblems, and the panel
subtitles are recoloured for contrast (rev 2 set the Arkiv subtitle in
Arkiv Orange on Arkiv Blue, which was near-illegible). Front face,
controls, screen content, body, lighting and cameras are untouched.
Rev 4 (this file) makes two client-directed changes and nothing else:
(1) the display grows and the bezels tighten (see the rev 4 DERIVED
entry below); control positions, emblems, panel colours, body
envelope, lighting and cameras are untouched. (2) The single
World-panel turntable becomes three frame-aligned turntables, one per
sponsor panel, rendered into turntable\\world, turntable\\0g and
turntable\\arkiv with an identical camera, pose sequence, light rig
and exposure; only the fitted rear panel changes between passes, so a
web viewer can cross-fade between the sequences at any fixed frame
index without visible drift.

Logo assets (rev 3; downloaded 2026-09-23; official sources; imported as
SVG curves via io_curve_svg, NOT traced or redrawn by hand):
  - World: orb + "World" lockup served by world.org itself,
    https://world.org/icons/worldcoin-orb-world-logo.svg
    -> assets/logos/world_logo.svg (6 closed paths, fill currentColor;
    the file's clipPath is just the viewBox rect, safe to ignore).
    The official file relies on NONZERO winding (overlapping subpaths
    in the orb, self-intersecting outline in the 'w'); Blender fills
    curves even-odd, which inverted the overlaps. The build therefore
    imports assets/logos/world_logo_flat.svg, derived mechanically from
    the official file (outlines sampled at 0.05 SVG units, nonzero fill
    resolved via polygon arrangement + winding numbers, shapely +
    svgpathtools; no redrawing). Derivation note embedded in the file.
  - 0G: official brand kit download page 0g.ai/brandkit,
    https://0g.ai/assets/681c472ba991e2e4ca164fe6_Black-OG-Logo.svg
    -> assets/logos/0g_black.svg (white variant
    https://0g.ai/assets/681c48142714d17c3e8251f5_White-OG-Logo.svg
    -> assets/logos/0g_white.svg; identical geometry, only fill differs,
    so the black file is imported and the colour comes from the material)
  - Arkiv: official logo pack linked from arkiv.network/brand,
    https://download.arkiv.network/arkiv-logo-pack.zip
    -> assets/logos/arkiv_lockup_black.svg + arkiv_lockup_white.svg
    ("[ ARKIV ]" full lockup, 7 closed paths; the pack's "[ A ]" icon
    kept as assets/logos/arkiv_icon_white.svg, unused)
Emblem treatment (DESIGN): each logo is a single joined curve, extruded
to a 0.9 mm slab buried 0.1 mm into the panel face, i.e. raised 0.8 mm
proud, crisp unbevelled edges like a moulded/printed emblem. Colours
contrast with the plate: black on the white World panel, white on the
0G purple panel, Arkiv Sand (F6F4EF, Arkiv's own on-blue pairing) on the
Arkiv Blue panel. Subtitles are kept and now use the same contrast
colour as their panel's emblem; Arkiv Orange dropped from the panels.

Dimension sources
-----------------
MEASURED (Waveshare official dimension drawing, GamePi43-size.jpg from
waveshare.com/gamepi43-us.htm, and the wiki at waveshare.com/wiki/GamePi43):
  - overall device envelope: 170.7 x 111.21 x 33.65 mm
  - screen window in the drawing: 96.30 x 56.15 mm
MEASURED (display spec): 4.3 inch 800x480 panel, 5:3
DERIVED:
  - rev 1-3 display active area 93.6 x 56.2 mm (4.3 inch diagonal at
    5:3 from 800x480; consistent with the 96.30 x 56.15 mm window in
    the drawing)
  - rev 4 display active area 99.0 x 59.4 mm, still 5:3 (4.55 inch
    class). DERIVED design change: a deliberate departure from the
    4.3 inch panel the physical build is based on, client-directed
    (noticeably larger screen, slim bezels). The nominal target was
    5 inch class, about 108 x 65 mm, which does NOT fit this body
    with the approved controls fixed: the stick trim ring inner edge
    sits at x = -53.0 (-66.5 + 13.5) and the west face-button edge at
    x = +51.4 (+66.5 - 10.5 - 4.6), leaving 104.4 mm of clear
    faceplate between controls, so a 108 mm active area would overlap
    both controls before any bezel is added. 99.0 mm active + 0.9 mm
    visible bezel per side + 1.0 mm clearance to the west button edge
    is the largest clean fit and is what this file builds (window
    pocket 100.8 x 61.2 mm; rev 2-3 used 97.5 x 59.5 mm with a
    1.95 mm bezel). Approximation, reported to the client as such.
DESIGN (client-directed rev 2 layout, landscape orientation; not measured
from any real product):
  - screen mounted LANDSCAPE in the centre, window pocket 100.8 x
    61.2 mm from rev 4 (rev 2-3: 97.5 x 59.5 mm), centre offset +6 mm
    in y to leave room for the START/SELECT pills
  - screen content drawn landscape 240x144 px, 4:3 game area (192x144)
    pillarboxed on the 5:3 panel, upright
  - one analog thumbstick on the left at (-66.5, +6): 27 mm trim ring,
    10 mm shaft, 19 mm concave cap standing 10.75 mm proud
  - four round face buttons on the right in a diamond at (+66.5, +6),
    diamond radius 10.5 mm, button dia 9.2 mm, unlabelled
  - two pill buttons (START/SELECT) 17 x 6.5 mm at (+/-13.5, -40.5),
    centred below the screen, unlabelled
  - body corner radius 6.0 mm (rev 1 used 4.0 from kit photos; 6.0 is a
    product-design choice for the unibody shell)
  - top edge only: USB-C slot centred, power pill at x = +58; no other
    edge features, no front markings of any kind
  - construction: unibody shell + thin structural inner back (1.0 mm,
    inset 2 mm, carries the screw bosses and steel discs) + full-footprint
    cosmetic rear panel 3.2 mm thick matching the body outline and corner
    radius; a 1.0 mm shadow-line reveal separates panel from shell so the
    swappable panel reads as deliberate. The inner back, not the cosmetic
    panel, is the structural closure.
  - magnets: six 6 x 2 mm discs pocketed into the panel inner face
    (rev 1 used 6 x 3; 2 mm thickness lets the pocket live inside a
    3.2 mm panel with a 1.0 mm outer wall), positions (+/-70, +/-42) and
    (0, +/-42); matching flush steel discs on the inner back
Sponsor panel colours (see report; queried 2026-09-23):
  - World: monochrome black/white brand per world.org (site is
    deliberately neutral); panel = warm off-white, black wordmark.
    SOURCED (monochrome direction), exact off-white value is a choice.
  - 0G: primary brand purple #9200E1 from the official brand kit at
    0g.ai/brandkit; panel = that purple, white wordmark. SOURCED.
  - Arkiv: Arkiv Blue #181EA9, Arkiv Orange #FE7446, Sand #F6F4EF from
    arkiv.network/brand; panel = Arkiv Blue. Rev 2 used an Orange
    sub-line, which failed on the blue; rev 3 sets emblem and sub in Sand.
  - Rev 2 wordmarks were embossed Arial Bold text; rev 3 replaces them
    with the official SVG logo geometry listed above (downloaded, not
    traced). Arial remains only in the ETHGLOBAL MUMBAI 2026 sub-line.

Run:
  & "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" \
      --background --python build_handheld_render.py -- [preview|final] [shot..]
  preview mode renders 960x540 at 32 samples into render\\preview\\ and
  includes shot s0 (straight-on front elevation for layout checking).
  turntable mode (per panel: 36 frames, 10 deg steps, 1080x1080 JPEG
  q88, frame-aligned across panels) renders turntable\\world,
  turntable\\0g and turntable\\arkiv:
  ... build_handheld_render.py -- turntable [world|0g|arkiv]
  (no panel argument renders all three; with preview, frames go to
  preview\\turntable\\<panel> at 540x540 / 32 samples instead)
"""

import bpy
import bmesh
import math
import os
import sys
from math import radians, sin, cos

M = 0.001  # scene is metric metres; all model dimensions below are in mm

OUT_DIR = r"C:\Users\chrsn\Desktop\retro-handheld-ethglobal\render"
FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"
LOGO_DIR = r"C:\Users\chrsn\Desktop\retro-handheld-ethglobal\assets\logos"

# emblem treatment (see header): 0.9 mm slab buried 0.1 mm = 0.8 mm proud
EMBLEM_EXTRUDE = 0.45           # curve extrude, +/- mm about the curve plane
EMBLEM_BURY = 0.10              # mm sunk into the panel face

# ---- measured device envelope (mm) ----
DEV_W = 170.7
DEV_H = 111.21
DEV_T = 33.65
# rev 4 DERIVED display size (deliberate departure from the measured
# 4.3 inch panel; largest clean 5:3 fit between the fixed controls,
# see header): 4.55 inch class
ACT_W = 99.0    # derived active area, landscape
ACT_H = 59.4
CORNER_R = 6.0  # DESIGN

# ---- DESIGN layout (landscape frame: x right, y up, front +Z) ----
SCREEN_C = (0.0, 6.0)
WIN_W, WIN_H = 100.8, 61.2     # screen pocket: ACT + 0.9 mm bezel/side
POCKET_D = 1.8
STICK_C = (-66.5, 6.0)
STICK_RING_R = 13.5
STICK_CAP_R = 9.5
DIAMOND_C = (66.5, 6.0)
DIAMOND_R = 10.5
BTN_R = 4.6
PILL_W, PILL_H = 17.0, 6.5
PILL_Y = -40.5
PILL_XS = (-13.5, 13.5)
USBC_X = 0.0
PWR_X = 58.0

# ---- DESIGN rear panel system (mm) ----
COS_T = 3.2                     # cosmetic swappable panel thickness
INNER_INSET = 2.0               # structural inner back outline inset
INNER_T = 1.0                   # inner back thickness (reveal band height)
MAG_R = 3.0
MAG_T = 2.0
MAG_POCKET_R = 3.35
MAG_POCKET_D = 2.2              # leaves 1.0 mm outer wall in the panel
MAG_POS = [(-70, -42), (0, -42), (70, -42), (-70, 42), (0, 42), (70, 42)]

FRONT_Z = DEV_T / 2.0            # 16.825
BACK_Z = -DEV_T / 2.0
PANEL_TOP_Z = BACK_Z + COS_T     # -13.625 cosmetic panel inner face
SHELL_BOT_Z = PANEL_TOP_Z + 0.025 + INNER_T  # -12.6 shell bottom face

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
PREVIEW = "preview" in args
TURNTABLE = "turntable" in args
SHOT_FILTER = [a for a in args if a not in ("preview", "final", "turntable")]

# ----------------------------------------------------------------------------
# scene reset and render settings
# ----------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
if TURNTABLE:
    scene.render.resolution_x = 540 if PREVIEW else 1080
    scene.render.resolution_y = 540 if PREVIEW else 1080
    scene.cycles.samples = 32 if PREVIEW else 128
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.quality = 88
else:
    scene.render.resolution_x = 960 if PREVIEW else 1920
    scene.render.resolution_y = 540 if PREVIEW else 1080
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.cycles.samples = 32 if PREVIEW else 256
scene.cycles.use_adaptive_sampling = True
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 8
scene.cycles.transmission_bounces = 10
scene.cycles.transparent_max_bounces = 10
scene.cycles.caustics_reflective = False
scene.cycles.caustics_refractive = False
try:
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
except Exception:
    pass
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0

# GPU if available
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for dev_type in ("OPTIX", "CUDA", "NONE"):
        try:
            prefs.compute_device_type = dev_type
            break
        except Exception:
            continue
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    if prefs.compute_device_type != "NONE":
        scene.cycles.device = "GPU"
        print("Cycles device:", prefs.compute_device_type)
except Exception as e:
    print("GPU setup failed, using CPU:", e)

col = bpy.context.collection

# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def link(obj):
    col.objects.link(obj)
    return obj

def new_empty(name, loc=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    return link(e)

def set_active(obj):
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)

def shade_smooth(obj, angle=35):
    set_active(obj)
    try:
        bpy.ops.object.shade_auto_smooth(angle=radians(angle))
    except Exception:
        try:
            bpy.ops.object.shade_smooth()
        except Exception:
            pass

def add_bevel(obj, width_mm=0.35, segments=2):
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width = width_mm * M
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = radians(40)

def rounded_rect_pts(w, h, r, seg=7):
    pts = []
    cx, cy = w / 2 - r, h / 2 - r
    corners = [
        (cx, -cy, -90), (cx, cy, 0), (-cx, cy, 90), (-cx, -cy, 180),
    ]
    for ccx, ccy, a0 in corners:
        for i in range(seg + 1):
            a = radians(a0 + 90.0 * i / seg)
            pts.append((ccx + r * cos(a), ccy + r * sin(a)))
    return pts

def make_rounded_box(name, w, h, t, r=3.0, z0=0.0, loc=(0, 0, 0), seg=7):
    """Rounded-rectangle prism. w,h in XY (mm), thickness t along Z starting
    at z0 (mm, in the object's local frame). loc is the object location (mm)."""
    bm = bmesh.new()
    verts = [bm.verts.new((x * M, y * M, z0 * M)) for x, y in
             rounded_rect_pts(w, h, r, seg)]
    face = bm.faces.new(verts)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    new_verts = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=new_verts, vec=(0, 0, t * M))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (loc[0] * M, loc[1] * M, loc[2] * M)
    return link(obj)

def make_box(name, sx, sy, sz, loc=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx * M, sy * M, sz * M)
    obj.location = (loc[0] * M, loc[1] * M, loc[2] * M)
    bpy.ops.object.transform_apply(scale=True)
    return obj

def make_cyl(name, r, depth, loc=(0, 0, 0), rot=(0, 0, 0), verts=64):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=r * M, depth=depth * M,
        location=(loc[0] * M, loc[1] * M, loc[2] * M),
        rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    return obj

def make_lathe(name, profile, loc=(0, 0, 0), steps=96):
    """Solid of revolution around local Z. profile is a list of (radius_mm,
    z_mm) pairs running rim-to-rim; radius 0 points close the poles."""
    bm = bmesh.new()
    verts = [bm.verts.new((r * M, 0.0, z * M)) for r, z in profile]
    edges = [bm.edges.new((verts[i], verts[i + 1]))
             for i in range(len(verts) - 1)]
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(0, 0, 1),
                   angle=2 * math.pi, steps=steps, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (loc[0] * M, loc[1] * M, loc[2] * M)
    return link(obj)

def make_sphere(name, r, loc=(0, 0, 0), scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=r * M, segments=48, ring_count=24,
        location=(loc[0] * M, loc[1] * M, loc[2] * M))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    return obj

def boolean_cut(target, cutter):
    mod = target.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    mod.solver = "EXACT"
    set_active(target)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)

def make_text(name, body, size_mm, extrude_mm, loc=(0, 0, 0), rot=(0, 0, 0)):
    cu = bpy.data.curves.new(name, type="FONT")
    cu.body = body
    try:
        cu.font = bpy.data.fonts.load(FONT_PATH)
    except Exception:
        pass
    cu.size = size_mm * M
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = extrude_mm * M / 2.0
    cu.bevel_depth = 0.05 * M if extrude_mm > 0.1 else 0.0
    obj = bpy.data.objects.new(name, cu)
    obj.location = (loc[0] * M, loc[1] * M, loc[2] * M)
    obj.rotation_euler = rot
    return link(obj)

def import_logo_curve(name, svg_file, target_w_mm):
    """Import an official logo SVG as one joined, filled, extruded curve.
    Returns the object with its origin at the bounding-box centre and its
    footprint scaled to target_w_mm wide, or None if the import failed or
    produced empty geometry (caller falls back to a text wordmark)."""
    path = os.path.join(LOGO_DIR, svg_file)
    if not os.path.exists(path):
        print("LOGO MISSING:", path)
        return None
    before = set(bpy.data.objects)
    try:
        bpy.ops.import_curve.svg(filepath=path)
    except Exception as e1:
        try:
            bpy.ops.preferences.addon_enable(module="io_curve_svg")
            bpy.ops.import_curve.svg(filepath=path)
        except Exception as e2:
            print("LOGO IMPORT FAILED:", svg_file, "|", e1, "|", e2)
            return None
    new = [o for o in bpy.data.objects
           if o not in before and o.type == "CURVE"]
    if not new:
        print("LOGO IMPORT EMPTY:", svg_file)
        return None
    set_active(new[0])
    for o in new:
        o.select_set(True)
    if len(new) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    cu = obj.data
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.extrude = EMBLEM_EXTRUDE * M
    cu.bevel_depth = 0.0           # crisp printed edge, no rounding
    for sp in cu.splines:
        sp.material_index = 0      # single contrast material for all paths
    set_active(obj)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    span_x = obj.dimensions.x
    if span_x < 1e-9:
        print("LOGO IMPORT DEGENERATE:", svg_file)
        bpy.data.objects.remove(obj, do_unlink=True)
        return None
    s = (target_w_mm * M) / span_x
    # uniform object scale stays live: transform_apply is rejected for 2D
    # curves in Blender 5.2, and a live uniform scale renders identically
    obj.scale = (s, s, s)
    bpy.context.view_layer.update()
    print("logo %s: %s -> %.1f x %.1f mm" %
          (name, svg_file, obj.dimensions.x / M, obj.dimensions.y / M))
    return obj

# ----------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------
def set_in(node, key, val):
    if key in node.inputs:
        node.inputs[key].default_value = val

def mat_pbr(name, color, rough=0.4, metal=0.0, transmission=0.0,
            ior=1.45, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    set_in(b, "Base Color", (*color, 1.0))
    set_in(b, "Roughness", rough)
    set_in(b, "Metallic", metal)
    set_in(b, "IOR", ior)
    set_in(b, "Transmission Weight", transmission)
    set_in(b, "Coat Weight", coat)
    return m

MAT_BODY = mat_pbr("body_charcoal", (0.028, 0.028, 0.031), rough=0.5, coat=0.12)
MAT_INNER = mat_pbr("inner_back", (0.012, 0.012, 0.013), rough=0.7)
MAT_BTN = mat_pbr("btn_bone", (0.60, 0.585, 0.55), rough=0.32, coat=0.3)
MAT_STICK = mat_pbr("stick_dark", (0.045, 0.045, 0.05), rough=0.42, coat=0.2)
MAT_TRIM = mat_pbr("trim_dark", (0.014, 0.014, 0.016), rough=0.55)
MAT_METAL = mat_pbr("port_metal", (0.60, 0.60, 0.62), rough=0.32, metal=1.0)
MAT_STEEL = mat_pbr("disc_steel", (0.62, 0.62, 0.62), rough=0.38, metal=1.0)
MAT_MAGNET = mat_pbr("magnet_nickel", (0.68, 0.68, 0.66), rough=0.18, metal=1.0)
MAT_BEZEL = mat_pbr("lcd_bezel", (0.008, 0.008, 0.008), rough=0.08, coat=0.4)
MAT_HOLE = mat_pbr("hole_dark", (0.004, 0.004, 0.004), rough=0.6)
MAT_FLOOR = mat_pbr("floor", (0.38, 0.38, 0.395), rough=0.35)
MAT_WALL = mat_pbr("wall", (0.30, 0.30, 0.315), rough=0.8)

# sponsor panel colours, sRGB hex converted to linear (see header)
LIN_0G_PURPLE = (0.2875, 0.0, 0.7529)     # 9200E1, 0g.ai/brandkit
LIN_ARKIV_BLUE = (0.0091, 0.0148, 0.3966)  # 181EA9, arkiv.network/brand
LIN_ARKIV_SAND = (0.9215, 0.9046, 0.8631)  # F6F4EF
# rev 2 also used Arkiv Orange FE7446 for the Arkiv sub-line; dropped in
# rev 3 for contrast (orange on Arkiv Blue was near-illegible)

# per panel: (plate, emblem+subtitle contrast colour); subtitle always
# matches the emblem colour in rev 3
MAT_PANEL = {
    "world": (mat_pbr("panel_world", (0.86, 0.85, 0.825), rough=0.55),
              mat_pbr("panel_world_txt", (0.012, 0.012, 0.013), rough=0.5)),
    "0g": (mat_pbr("panel_0g", LIN_0G_PURPLE, rough=0.55),
           mat_pbr("panel_0g_txt", (0.90, 0.90, 0.90), rough=0.45)),
    "arkiv": (mat_pbr("panel_arkiv", LIN_ARKIV_BLUE, rough=0.55),
              mat_pbr("panel_arkiv_txt", LIN_ARKIV_SAND, rough=0.45)),
}

def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)

# --- screen UI texture: landscape pixel-art platformer, 4:3 pillarboxed ---
def build_screen_image():
    W, H = 240, 144
    X0, X1 = 24, 216            # 4:3 game area (192x144) on the 5:3 panel
    px = [0.0] * (W * H * 4)

    def rect(x0, y0, x1, y1, c):
        for y in range(max(0, y0), min(H, y1)):
            base = y * W
            for x in range(max(0, x0), min(W, x1)):
                i = (base + x) * 4
                px[i], px[i + 1], px[i + 2], px[i + 3] = c[0], c[1], c[2], 1.0

    rect(0, 0, W, H, (0.006, 0.006, 0.008))                    # pillar bars
    rect(X0, 0, X1, H, (0.40, 0.63, 0.96))                     # sky
    rect(X0, 132, X1, 144, (0.05, 0.06, 0.13))                 # HUD bar (top)
    for k in range(4):                                          # HUD hearts
        g = 0.9 if k < 3 else 0.35
        rect(X0 + 6 + k * 9, 135, X0 + 13 + k * 9, 141, (0.9 * g, 0.1, 0.15))
    for k in range(3):                                          # HUD timer
        rect(X1 - 40 + k * 12, 135, X1 - 31 + k * 12, 141, (0.96, 0.96, 0.9))
    rect(X0 + 16, 108, X0 + 46, 116, (0.97, 0.97, 0.98))       # clouds
    rect(X0 + 24, 114, X0 + 40, 120, (0.97, 0.97, 0.98))
    rect(X0 + 118, 96, X0 + 152, 104, (0.97, 0.97, 0.98))
    # ground bricks (rows 0..18)
    for y in range(0, 18):
        for x in range(X0, X1):
            c = (0.45, 0.27, 0.13)
            if y % 6 == 5 or (x + (y // 6) * 6) % 12 == 11:
                c = (0.28, 0.15, 0.07)
            i = (y * W + x) * 4
            px[i], px[i + 1], px[i + 2], px[i + 3] = c[0], c[1], c[2], 1.0
    # staggered platforms climbing left to right
    rect(X0 + 34, 44, X0 + 78, 50, (0.62, 0.36, 0.15))
    rect(X0 + 96, 66, X0 + 140, 72, (0.62, 0.36, 0.15))
    rect(X0 + 148, 88, X0 + 186, 94, (0.62, 0.36, 0.15))
    for cx, cy in [(X0 + 52, 56), (X0 + 114, 78), (X0 + 163, 100),
                   (X0 + 88, 28)]:                              # coins
        rect(cx, cy, cx + 6, cy + 6, (0.98, 0.83, 0.05))
    # hero on the ground, left side
    hx = X0 + 30
    rect(hx, 18, hx + 8, 24, (0.12, 0.2, 0.7))                  # legs
    rect(hx, 24, hx + 8, 30, (0.95, 0.72, 0.5))                 # face
    rect(hx, 30, hx + 8, 34, (0.85, 0.08, 0.08))                # cap
    # goal flag, right side
    fx = X1 - 18
    rect(fx, 18, fx + 3, 104, (0.10, 0.62, 0.22))               # pole
    rect(fx - 16, 88, fx, 100, (0.4, 0.9, 0.2))                 # flag
    rect(fx - 4, 18, fx + 7, 24, (0.55, 0.33, 0.14))            # base block

    img = bpy.data.images.new("screen_ui", width=W, height=H, alpha=False)
    img.pixels[:] = px
    img.pack()
    return img

def mat_screen():
    m = bpy.data.materials.new("screen_emissive")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = build_screen_image()
    tex.interpolation = "Closest"
    em.inputs["Strength"].default_value = 8.0
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m

MAT_SCREEN = mat_screen()

# ----------------------------------------------------------------------------
# device build (local frame: X width, Y height, Z thickness, front = +Z)
# clean layout: stick LEFT, landscape screen CENTRE, diamond RIGHT,
# START/SELECT pills below the screen; no markings anywhere
# ----------------------------------------------------------------------------
device_root = new_empty("device_root")
device_objs = []

def dev(obj, mat=None, bevel=0.35, smooth=None):
    if mat:
        assign(obj, mat)
    if bevel:
        add_bevel(obj, bevel)
    if smooth:
        shade_smooth(obj, smooth)
    obj.parent = device_root
    device_objs.append(obj)
    return obj

# unibody shell (front + sides, down to the reveal line) with screen pocket
shell = make_rounded_box("shell", DEV_W, DEV_H, FRONT_Z - SHELL_BOT_Z,
                         CORNER_R, z0=SHELL_BOT_Z)
pocket = make_rounded_box("pocket_cut", WIN_W, WIN_H, 6.0, 2.0,
                          z0=FRONT_Z - POCKET_D,
                          loc=(SCREEN_C[0], SCREEN_C[1], 0))
boolean_cut(shell, pocket)
dev(shell, MAT_BODY, bevel=0.6)

# structural inner back: inset slab that actually closes the device;
# carries flush steel discs as the magnet counterparts
inner = make_rounded_box("inner_back", DEV_W - 2 * INNER_INSET,
                         DEV_H - 2 * INNER_INSET, INNER_T,
                         max(CORNER_R - INNER_INSET, 1.5),
                         z0=PANEL_TOP_Z + 0.025)
dev(inner, MAT_INNER, bevel=0.2)
for i, (mx, my) in enumerate(MAG_POS):
    d = make_cyl("steel_disc_%d" % i, 3.5, 0.8,
                 loc=(mx, my, PANEL_TOP_Z + 0.025 + 0.35))
    dev(d, MAT_STEEL, bevel=0.15, smooth=35)

# LCD stack in the pocket: black bezel plate, emissive active area (landscape)
bez = make_rounded_box("lcd_bezel", WIN_W - 0.3, WIN_H - 0.3, 0.5, 1.8,
                       z0=FRONT_Z - POCKET_D + 0.05,
                       loc=(SCREEN_C[0], SCREEN_C[1], 0))
dev(bez, MAT_BEZEL, bevel=0.1)
bpy.ops.mesh.primitive_plane_add(size=1)
screen = bpy.context.active_object
screen.name = "screen_active"
screen.scale = (ACT_W * M, ACT_H * M, 1)
screen.location = (SCREEN_C[0] * M, SCREEN_C[1] * M,
                   (FRONT_Z - POCKET_D + 0.62) * M)
bpy.ops.object.transform_apply(scale=True)
dev(screen, MAT_SCREEN, bevel=0)

# analog thumbstick, left: trim ring, gaiter dome, shaft, concave cap
ring = make_cyl("stick_ring", STICK_RING_R, 1.0,
                loc=(STICK_C[0], STICK_C[1], FRONT_Z))
dev(ring, MAT_TRIM, bevel=0.3, smooth=35)
gait = make_sphere("stick_gaiter", 8.5,
                   loc=(STICK_C[0], STICK_C[1], FRONT_Z + 0.3),
                   scale=(1, 1, 0.45))
dev(gait, MAT_TRIM, bevel=0, smooth=35)
shaft = make_cyl("stick_shaft", 5.0, 7.0,
                 loc=(STICK_C[0], STICK_C[1], FRONT_Z + 3.5))
dev(shaft, MAT_STICK, bevel=0.4, smooth=35)
# concave cap as a lathe profile (boolean dish shaded badly): rim at
# +11.1, dish centre at +10.0, so the dish is 1.1 mm deep across 19 mm
cap = make_lathe("stick_cap", [
    (0.0, FRONT_Z + 10.0),
    (2.8, FRONT_Z + 10.12),
    (5.5, FRONT_Z + 10.45),
    (7.8, FRONT_Z + 10.9),
    (8.9, FRONT_Z + 11.1),
    (STICK_CAP_R, FRONT_Z + 10.85),
    (STICK_CAP_R, FRONT_Z + 7.0),
    (8.6, FRONT_Z + 6.4),
    (0.0, FRONT_Z + 6.4),
], loc=(STICK_C[0], STICK_C[1], 0))
dev(cap, MAT_STICK, bevel=0, smooth=30)

# four round face buttons in a diamond, right; unlabelled
for nm, dx, dy in (("btn_n", 0, DIAMOND_R), ("btn_s", 0, -DIAMOND_R),
                   ("btn_w", -DIAMOND_R, 0), ("btn_e", DIAMOND_R, 0)):
    b = make_cyl(nm, BTN_R, 4.0,
                 loc=(DIAMOND_C[0] + dx, DIAMOND_C[1] + dy, FRONT_Z + 0.6))
    dev(b, MAT_BTN, bevel=0.9, smooth=35)

# START / SELECT pills, centred below the screen; unlabelled
for i, px_ in enumerate(PILL_XS):
    p = make_rounded_box("pill_%d" % i, PILL_W, PILL_H, 2.8,
                         PILL_H / 2 - 0.05, z0=FRONT_Z - 0.6,
                         loc=(px_, PILL_Y, 0))
    dev(p, MAT_BTN, bevel=0.6)

# top edge: USB-C slot and power pill; the only edge features
usbc = make_rounded_box("usbc_slot", 9.2, 3.4, 2.4, 1.6, z0=0,
                        loc=(USBC_X, DEV_H / 2 + 0.4, 1.5))
usbc.rotation_euler = (radians(90), 0, 0)
dev(usbc, MAT_HOLE, bevel=0.15)
tongue = make_box("usbc_tongue", 6.4, 0.6, 0.7,
                  loc=(USBC_X, DEV_H / 2 - 0.6, 1.5))
dev(tongue, MAT_METAL, bevel=0.1)
pwr = make_rounded_box("power_pill", 10.0, 3.0, 1.6, 1.45, z0=0,
                       loc=(PWR_X, DEV_H / 2 + 0.55, 1.5))
pwr.rotation_euler = (radians(90), 0, 0)
dev(pwr, MAT_BTN, bevel=0.4)

# ----------------------------------------------------------------------------
# sponsor rear panels: full footprint, magnet pockets on the inner face
# panel local frame: slab centred on z, +z face carries the wordmark (outer),
# -z face is the inner face with the pocketed magnets
# ----------------------------------------------------------------------------
def build_panel(key, logo_svg, logo_w_mm, fallback_text, fallback_size,
                logo_y=6.0, sub_size=4.0):
    base_m, txt_m = MAT_PANEL[key]
    root = new_empty("panel_%s_root" % key)
    objs = []
    slab = make_rounded_box("panel_%s" % key, DEV_W, DEV_H, COS_T,
                            CORNER_R, z0=-COS_T / 2)
    for hi, (mx, my) in enumerate(MAG_POS):
        cutter = make_cyl("pcut_%s_%d" % (key, hi), MAG_POCKET_R, 4.0,
                          loc=(mx, my, -COS_T / 2 + MAG_POCKET_D - 2.0),
                          verts=48)
        boolean_cut(slab, cutter)
    assign(slab, base_m)
    add_bevel(slab, 0.5)
    slab.parent = root
    objs.append(slab)
    # raised emblem from official logo SVG; text wordmark only as fallback
    emblem = import_logo_curve("panel_%s_logo" % key, logo_svg, logo_w_mm)
    if emblem is not None:
        assign(emblem, txt_m)
        emblem.location = (0, logo_y * M,
                           (COS_T / 2 - EMBLEM_BURY + EMBLEM_EXTRUDE) * M)
        emblem.parent = root
        objs.append(emblem)
    else:
        print("FALLBACK WORDMARK for", key)
        txt = make_text("panel_%s_txt" % key, fallback_text, fallback_size,
                        0.7, loc=(0, 4, COS_T / 2 + 0.30))
        assign(txt, txt_m)
        txt.parent = root
        objs.append(txt)
    sub = make_text("panel_%s_sub" % key, "ETHGLOBAL MUMBAI 2026", sub_size,
                    0.5, loc=(0, -26, COS_T / 2 + 0.22))
    assign(sub, txt_m)
    sub.parent = root
    objs.append(sub)
    # magnets recessed 0.2 mm below the pocket rim
    for i, (mx, my) in enumerate(MAG_POS):
        # pocket floor is at -COS_T/2 + MAG_POCKET_D; the magnet face sits
        # 0.4 mm below the panel inner face so the pocket reads in renders
        # (the 0.2 mm it buries into the pocket floor is invisible)
        mag = make_cyl("mag_%s_%d" % (key, i), MAG_R, MAG_T,
                       loc=(mx, my,
                            -COS_T / 2 + MAG_POCKET_D - MAG_T / 2 + 0.2),
                       verts=48)
        assign(mag, MAT_MAGNET)
        add_bevel(mag, 0.15)
        shade_smooth(mag, 35)
        mag.parent = root
        objs.append(mag)
    return root, objs

panel_world_root, panel_world_objs = build_panel(
    "world", "world_logo_flat.svg", 100.0, "World", 30)
panel_0g_root, panel_0g_objs = build_panel(
    "0g", "0g_black.svg", 66.0, "0G", 40)
# Arkiv emblem at 76 mm, not 100: in the approved shot-3 lineup framing a
# wider lockup runs its left bracket behind the 0G plate (100 mm hid the
# whole bracket, 86 mm still clipped half of it); 76 mm clears it with a
# few mm to spare while staying comfortably sized on the plate
panel_arkiv_root, panel_arkiv_objs = build_panel(
    "arkiv", "arkiv_lockup_black.svg", 76.0, "[ ARKIV ]", 21)

# loose magnet props for the detail shot
prop_objs = []
for i, (px_, py_) in enumerate([(50, -62), (62, -52)]):
    pm = make_cyl("prop_mag_%d" % i, MAG_R, MAG_T, loc=(px_, py_, MAG_T / 2))
    assign(pm, MAT_MAGNET)
    add_bevel(pm, 0.15)
    shade_smooth(pm, 35)
    prop_objs.append(pm)
pw = make_cyl("prop_disc", 3.5, 0.8, loc=(40, -70, 0.4))
assign(pw, MAT_STEEL)
add_bevel(pw, 0.15)
shade_smooth(pw, 35)
prop_objs.append(pw)

# ----------------------------------------------------------------------------
# studio: floor, wall, lights, cameras
# ----------------------------------------------------------------------------
floor = make_box("floor", 4000, 4000, 10, loc=(0, 0, -5.01))
assign(floor, MAT_FLOOR)
wall = make_box("wall", 4000, 10, 4000, loc=(0, 1100, 1900))
assign(wall, MAT_WALL)

world = bpy.data.worlds.new("studio_world")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.55, 0.56, 0.6, 1.0)
bg.inputs["Strength"].default_value = 0.10
scene.world = world

def add_light(name, loc, power, size, target):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.size = size
    lo = bpy.data.objects.new(name, ld)
    lo.location = loc
    link(lo)
    con = lo.constraints.new("TRACK_TO")
    con.target = target
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return lo

aim = new_empty("light_aim", (0, 0, 0.05))
add_light("key", (-0.45, -0.50, 0.55), 20, 0.45, aim)
add_light("fill", (0.55, -0.35, 0.28), 7, 0.6, aim)
add_light("rim", (0.10, 0.55, 0.50), 22, 0.30, aim)
add_light("top", (0.0, -0.05, 0.85), 5, 0.8, aim)
scene.view_settings.exposure = -1.1

def add_camera(name, loc, target_loc, lens, fstop):
    tgt = new_empty(name + "_tgt", target_loc)
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.dof.use_dof = True
    cd.dof.focus_object = tgt
    cd.dof.aperture_fstop = fstop
    cam = bpy.data.objects.new(name, cd)
    cam.location = loc
    link(cam)
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return cam, tgt

cam0, tgt0 = add_camera("cam_layout", (0, -0.55, 0.0556), (0, 0, 0.0556), 70, 16)
cam1, tgt1 = add_camera("cam_hero", (-0.22, -0.40, 0.22), (0, 0, 0.054), 60, 11)
cam2, tgt2 = add_camera("cam_rear", (0.26, -0.42, 0.26), (0, 0, 0.054), 60, 11)
cam3, tgt3 = add_camera("cam_lineup", (0.045, -0.71, 0.225), (0.045, 0, 0.048), 36, 13)
cam4, tgt4 = add_camera("cam_detail", (-0.115, -0.25, 0.175), (-0.005, -0.008, 0.001), 48, 13)
# preview-only: straight-on elevation of the three panels for emblem checks
cam5, tgt5 = add_camera("cam_panels", (0, -1.05, 0.0556), (0, 0, 0.0556), 60, 16)

# ----------------------------------------------------------------------------
# shot management
# ----------------------------------------------------------------------------
ALL_GROUPS = {
    "device": device_objs,
    "world": panel_world_objs,
    "0g": panel_0g_objs,
    "arkiv": panel_arkiv_objs,
    "props": prop_objs,
}

def show_only(names):
    for gname, objs in ALL_GROUPS.items():
        hide = gname not in names
        for o in objs:
            o.hide_render = hide
            o.hide_viewport = hide

from mathutils import Matrix

def pose_device(rz_deg, x=0.0):
    device_root.location = (x, 0, DEV_H / 2 * M + 0.0001)
    device_root.rotation_euler = (radians(90), 0, radians(rz_deg))

def pose_panel_attached(root=None):
    """Fit a panel onto the device rear (device local frame)."""
    root = root or panel_world_root
    root.parent = device_root
    root.matrix_parent_inverse = Matrix.Identity(4)
    root.location = (0, 0, (BACK_Z + COS_T / 2) * M)
    root.rotation_euler = (0, radians(180), 0)

def pose_panel_standing(root, x, y, yaw_deg, lean_deg=13):
    root.parent = None
    root.location = (x, y, (DEV_H / 2 * cos(radians(lean_deg)) + 0.3) * M)
    root.rotation_euler = (radians(90 - lean_deg), 0, radians(yaw_deg))

def render(shot_name, cam):
    scene.camera = cam
    base = OUT_DIR + ("\\preview" if PREVIEW else "")
    os.makedirs(base, exist_ok=True)
    scene.render.filepath = base + "\\" + shot_name + ".png"
    print("rendering", shot_name)
    bpy.ops.render.render(write_still=True)

def want(shot):
    if TURNTABLE:
        return False
    return not SHOT_FILTER or shot in SHOT_FILTER

# shot 0 (preview only): straight-on front elevation for layout checking
if PREVIEW and want("s0"):
    show_only(["device", "world"])
    pose_device(0)
    pose_panel_attached(panel_world_root)
    render("00_layout_check", cam0)

# shot 1: hero front three-quarter
if want("s1"):
    show_only(["device", "world"])
    pose_device(4)
    pose_panel_attached(panel_world_root)
    render("01_hero_front_three_quarter", cam1)

# shot 2: rear three-quarter, World panel fitted
if want("s2"):
    show_only(["device", "world"])
    pose_device(195)
    pose_panel_attached(panel_world_root)
    render("02_rear_world_plate_attached", cam2)

# shot 3: device plus all three sponsor panels standing beside it
if want("s3"):
    show_only(["device", "world", "0g", "arkiv"])
    pose_device(12, x=-0.20)
    pose_panel_standing(panel_world_root, 0.000, -0.030, -5)
    pose_panel_standing(panel_0g_root, 0.140, 0.012, -11)
    pose_panel_standing(panel_arkiv_root, 0.280, 0.058, -17)
    render("03_sponsor_plates_lineup", cam3)

# shot 4: panel inner face up, pocketed magnets visible
if want("s4"):
    show_only(["arkiv", "props"])
    panel_arkiv_root.parent = None
    panel_arkiv_root.location = (0, 0, 2.4 * M)
    panel_arkiv_root.rotation_euler = (radians(180), 0, radians(15))
    render("04_plate_rear_magnets", cam4)

# shot 5 (preview only): all three panels upright, straight on, for
# checking emblem geometry, centring, scale and contrast
if PREVIEW and want("s5"):
    show_only(["world", "0g", "arkiv"])
    for root, x in ((panel_world_root, -0.185), (panel_0g_root, 0.0),
                    (panel_arkiv_root, 0.185)):
        root.parent = None
        root.location = (x, 0, DEV_H / 2 * M + 0.0002)
        root.rotation_euler = (radians(90), 0, 0)
    render("05_panel_elevation_check", cam5)

# ----------------------------------------------------------------------------
# turntable: three frame-aligned 36-frame sequences, one per sponsor panel,
# 10 degree steps, fixed light rig, rotating device. The camera is created
# ONCE and every sequence replays the identical pose list, so frame N shows
# the identical angle, position and lighting in all three sequences; the
# only difference is which rear panel is parented onto the device. The web
# viewer cross-fades between sequences at a fixed frame index.
# ----------------------------------------------------------------------------
if TURNTABLE:
    ELEV = radians(15)
    DIST = 0.44
    cam_tt, tgt_tt = add_camera(
        "cam_turntable",
        (0, -DIST * cos(ELEV), DEV_H / 2 * M + DIST * sin(ELEV)),
        (0, 0, DEV_H / 2 * M), 50, 11)
    cam_tt.data.dof.use_dof = False
    scene.camera = cam_tt
    tt_base = OUT_DIR + ("\\preview\\turntable" if PREVIEW else "\\turntable")
    panels = [("world", panel_world_root), ("0g", panel_0g_root),
              ("arkiv", panel_arkiv_root)]
    if SHOT_FILTER:
        panels = [(k, r) for k, r in panels if k in SHOT_FILTER]
    for key, root in panels:
        show_only(["device", key])
        pose_panel_attached(root)
        tt_dir = tt_base + "\\" + key
        os.makedirs(tt_dir, exist_ok=True)
        for i in range(36):
            pose_device(i * 10)
            scene.render.filepath = tt_dir + "\\frame_%03d" % i
            print("rendering turntable", key, "frame", i)
            bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath=OUT_DIR + "\\handheld.blend")
print("done")
