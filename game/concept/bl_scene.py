import bpy, math, mathutils, sys
F="/opt/arca-sandbox/assets/kenney/furniture-kit/Models/GLTF format/"
C="/opt/arca-sandbox/assets/kenney/mini-characters/Models/GLB format/"
OUT="/mnt/c/Users/chrsn/AppData/Local/Temp/claude/c--Users-chrsn-Desktop-ARCA/f03de88a-2f73-42cb-b30a-3e537b5caf2a/scratchpad/render/"
W,H=3.2,2.1
bpy.ops.wm.read_factory_settings(use_empty=True)
sc=bpy.context.scene

def bbox(objs):
    pts=[]
    for o in objs:
        for c in [o]+list(o.children_recursive):
            if c.type=='MESH': pts+=[c.matrix_world@mathutils.Vector(b) for b in c.bound_box]
    return [min(v[i] for v in pts) for i in range(3)],[max(v[i] for v in pts) for i in range(3)]

def place(path, x, y, z=0, rot=0, scale=1.0, center=True):
    before=set(bpy.data.objects); acts=set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    new=[o for o in bpy.data.objects if o not in before]
    roots=[o for o in new if o.parent is None]
    piv=bpy.data.objects.new("piv",None); sc.collection.objects.link(piv)
    bpy.context.view_layer.update()
    if center:
        mn,mx=bbox(roots); cx,cy=(mn[0]+mx[0])/2,(mn[1]+mx[1])/2
    else: cx=cy=0
    for r in roots:
        r.parent=piv; r.location=(r.location.x-cx, r.location.y-cy, r.location.z)
    piv.location=(x,y,z); piv.rotation_euler=(0,0,math.radians(rot)); piv.scale=(scale,)*3
    return roots, [a for a in bpy.data.actions if a not in acts]

def f(n,*a,**k): return place(F+n+".glb",*a,**k)

def char(n, x, y, rot, anim, z=0, scale=0.8):
    roots, acts = place(C+n+".glb", x, y, z, rot, scale, center=False)
    for o in bpy.data.objects:
        if o.type=='ARMATURE' and o in [c for r in roots for c in [r]+list(r.children_recursive)]:
            act=[a for a in acts if a.name.rsplit("_",1)[0]==anim]
            o.animation_data_create(); o.animation_data.action=act[0]
            for t in list(o.animation_data.nla_tracks): o.animation_data.nla_tracks.remove(t)

def tint(prefix, rgb):
    pass

exec(open(OUT+"../bl_layout.py").read())
build(f, char, "sit", 45, "holding-right")
sc.frame_set(12)

cam=bpy.data.cameras.new("cam"); cam.type='ORTHO'; cam.ortho_scale=3.8
co=bpy.data.objects.new("cam",cam); sc.collection.objects.link(co); sc.camera=co
co.rotation_euler=(math.radians(90-26.565),0,math.radians(45))
d=co.rotation_euler.to_matrix()@mathutils.Vector((0,0,1))
co.location=mathutils.Vector((W/2+0.05,H/2-0.05,0.66))+d*20
sun=bpy.data.lights.new("sun",'SUN'); sun.energy=3.0; sun.angle=0.2
so=bpy.data.objects.new("sun",sun); sc.collection.objects.link(so); so.rotation_euler=(math.radians(42),0,math.radians(-35)); sun.color=(1.0,0.9,0.78)
wo=bpy.data.worlds.new("w"); sc.world=wo; wo.use_nodes=True
bg=wo.node_tree.nodes["Background"]; bg.inputs[0].default_value=(0.85,0.9,1,1); bg.inputs[1].default_value=0.45
sc.render.engine='CYCLES'; sc.cycles.samples=64; sc.cycles.use_denoising=False; sc.cycles.device='CPU'
sc.render.film_transparent=True; sc.view_settings.view_transform='AgX'; sc.view_settings.look='AgX - Punchy'
sc.render.resolution_x=960; sc.render.resolution_y=640
sc.render.filepath=OUT+"office_hi.png"
bpy.ops.render.render(write_still=True)
print("RENDERED")
