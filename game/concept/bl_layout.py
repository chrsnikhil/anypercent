# Act 1 office layout (Mumbai pass); exec'd by bl_scene.py, which provides bpy, sc, OUT, f(), char()
W,H=3.2,2.1
FONT="/mnt/c/Users/chrsn/Desktop/retro-handheld-ethglobal/launcher/arca_launcher/assets/fonts/Outfit-Bold.ttf"

def lin(r,g,b):  # sRGB 0-255 -> linear
    return tuple(((c/255+0.055)/1.055)**2.4 for c in (r,g,b))

def recolour(roots, table):
    for r in roots:
        for o in [r]+list(r.children_recursive):
            if o.type!='MESH': continue
            for slot in o.material_slots:
                base=slot.material.name.split('.')[0]
                if base in table:
                    m=slot.material.copy(); slot.material=m
                    v=table[base]
                    bsdf=m.node_tree.nodes["Principled BSDF"]
                    if isinstance(v,dict):
                        for k,val in v.items(): bsdf.inputs[k].default_value=val
                    else: bsdf.inputs[0].default_value=(*v,1)

def mat(name, rgb, metal=0.0, rough=0.6, emit=None, img=None):
    m=bpy.data.materials.new(name); m.use_nodes=True
    b=m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value=(*rgb,1); b.inputs["Metallic"].default_value=metal; b.inputs["Roughness"].default_value=rough
    if img:
        t=m.node_tree.nodes.new("ShaderNodeTexImage"); t.image=bpy.data.images.load(img)
        m.node_tree.links.new(t.outputs[0], b.inputs["Base Color"])
        if emit:
            m.node_tree.links.new(t.outputs[0], b.inputs["Emission Color"]); b.inputs["Emission Strength"].default_value=emit
    return m

def prim(kind, loc, rot=(0,0,0), scale=(1,1,1), material=None, **kw):
    getattr(bpy.ops.mesh, "primitive_%s_add"%kind)(location=loc, rotation=rot, **kw)
    o=bpy.context.active_object; o.scale=scale
    if material: o.data.materials.append(material)
    return o

def mumbai():
    import math
    R=math.radians
    # ETHMUMBAI banner on the left wall, above the chai counter
    cloth=mat("banner", (1,1,1), rough=0.8, emit=0.35, img=OUT+"banner.png")
    prim("plane", (0.035,1.44,0.99), rot=(R(90),0,R(90)), scale=(0.48,0.137,1), material=cloth)
    # marigold toran over the door
    orange=mat("marigold", lin(255,140,0), rough=0.7); yellow=mat("marigoldY", lin(255,200,20), rough=0.7)
    n=14
    for k in range(n+1):
        tt=k/n; y=0.16+0.68*tt; z=1.04-0.07*math.sin(math.pi*tt)
        prim("uv_sphere", (0.05,y,z), material=orange if k%2 else yellow, radius=0.032, segments=8, ring_count=6)
    for tt in (0.2,0.5,0.8):
        y=0.16+0.68*tt; z0=1.04-0.07*math.sin(math.pi*tt)
        for j in range(1,4):
            prim("uv_sphere", (0.05,y,z0-0.055*j), material=orange if j%2 else yellow, radius=0.03, segments=8, ring_count=6)
    # steel chai kettle and cutting-chai glasses on the counter
    steel=mat("steel", lin(200,205,212), metal=0.9, rough=0.25)
    prim("cylinder", (0.22,1.38,0.52), scale=(0.065,0.065,0.07), material=steel, vertices=16)
    prim("cone", (0.22,1.38,0.62), scale=(0.065,0.065,0.03), material=steel, vertices=16)
    prim("cylinder", (0.29,1.38,0.55), rot=(0,R(60),0), scale=(0.012,0.012,0.05), material=steel, vertices=8)
    tray=mat("tray", lin(150,155,160), metal=0.8, rough=0.35)
    prim("cylinder", (0.25,1.64,0.455), scale=(0.1,0.1,0.004), material=tray, vertices=20)
    chai=mat("chai", lin(196,120,58), rough=0.3)
    for dy,dx in ((-0.045,-0.03),(0.0,0.03),(0.045,-0.03)):
        prim("cylinder", (0.25+dx,1.64+dy,0.485), scale=(0.022,0.022,0.028), material=chai, vertices=10)
    # whiteboard with the build plan, back wall
    import os
    wb=mat("whiteboard", lin(255,255,255), rough=0.3, img=OUT+"whiteboard.png")
    prim("plane", (2.33,H-0.035,0.86), rot=(R(90),0,0), scale=(0.28,0.21,1), material=wb)
    frame=mat("wbframe", lin(160,168,180), metal=0.6, rough=0.4)
    prim("cube", (2.33,H-0.03,0.86), scale=(0.295,0.004,0.225), material=frame)
    # sticky notes above desk 1
    notes=[lin(255,226,90),lin(255,150,190),lin(140,230,160),lin(255,226,90),lin(140,200,255)]
    for k,(x,z) in enumerate(((0.35,0.78),(0.46,0.84),(0.57,0.76),(0.68,0.86),(0.8,0.79))):
        prim("plane", (x,H-0.035,z), rot=(R(90),0,R((k%3-1)*4)), scale=(0.035,0.035,1), material=mat("note%d"%k, notes[k], rough=0.9))
    # skyline behind the window (camera-only, casts no shadow)
    sky=mat("skyline", (1,1,1), rough=1, emit=1.0, img=OUT+"skyline_day.png")
    s=prim("plane", (1.35,H+0.15,0.7), rot=(R(90),0,0), scale=(0.75,0.5,1), material=sky)
    s.visible_shadow=False; s.visible_diffuse=False; s.visible_glossy=False

def build(f, char, anim_dev, player_rot, player_anim, with_chars=True):
    import math
    nx,ny=math.ceil(W),math.ceil(H)
    walls=dict(_defaultMat=lin(92,170,166), wood=lin(236,220,196))
    for i in range(nx):
        for j in range(ny): recolour(f("floorFull", i+0.5, j+0.5)[0], dict(wood=lin(168,72,56)))
    for i in range(nx):
        roots=f("wallWindow" if i==1 else "wall", i+0.5, H+0.02)[0]
        recolour(roots, dict(walls, glass={"Alpha":0.12, "Base Color":(1,1,1,1)}))
    for j in range(ny):
        recolour(f("wallDoorway" if j==0 else "wall", -0.02, j+0.5, rot=90)[0], walls)
    recolour(f("rugRectangle", 1.45, 0.9, 0.05)[0], dict(carpet=lin(40,52,120), carpetDarker=lin(240,160,30)))
    f("kitchenCabinet", 0.24, 1.3, rot=-90); f("kitchenCabinet", 0.24, 1.73, rot=-90)
    f("bookcaseOpen", W-0.27, H-0.14)
    for z,dx in ((0.33,-0.08),(0.61,0.06)):
        f("books", W-0.27+dx, H-0.16, z)
    f("pottedPlant", W-0.2, 0.25)
    xs=(0.78,1.56,2.34)
    seat=[lin(240,120,20),lin(40,110,200),lin(150,40,110)]
    for k,x in enumerate(xs):
        f("desk", x, H-0.72)
        f("laptop", x, H-0.74, 0.384, rot=180)
        recolour(f("chairDesk", x, H-0.28)[0], dict(carpet=seat[k]))
    mumbai()
    if with_chars:
        names=["character-male-a","character-female-b","character-male-e"]
        for k,x in enumerate(xs): char(names[k], x, H-0.3, 0, anim_dev, z=0.27)
        char("character-female-d", 1.3, 0.75, player_rot, player_anim)
