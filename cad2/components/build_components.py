"""
Real-component models for the ARCA handheld assembly view and fit checks.

Every bought part gets a mesh in its OWN local frame, written to
cad2/components/<name>.stl. enclosure.scad imports these and places them, so
positions stay defined in exactly one place (the .scad), and the fit checks
test the real shapes instead of the old bounding-box proxies.

Sources
  display_waveshare_5in_dsi  OFFICIAL Waveshare 3D model
                             (files.waveshare.com .../5inch_DSI_LCD_3D_Drawing.zip)
                             with its 8 optional M2.5 standoffs removed -- this
                             enclosure clamps the display with printed pucks and
                             the corner standoffs would hit the Pi.
  pico                       OFFICIAL Raspberry Pi Pico-R3 STEP (RP-008311-DS-1)
  pi3bplus                   built here from the official mechanical drawing
                             RP-008337-DS-2 (no official 3B+ STEP is published).
                             Connector overhangs are read off the drawing.
  everything else            built here from datasheet / catalogue dimensions.
                             Values the client must caliper are read from
                             enclosure.scad ([MEASURE] tags there), so changing
                             the .scad and re-running this keeps them in step.

Local frames (all mm)
  display   origin on the glass FRONT at the active-area centre, +z REARWARD,
            x mirrored so that it drops straight into device coordinates
            (the device's +x runs to the player's LEFT when seen from the
            front). Glass front z 0, PCB rear z 9.0, rear parts to z 14.7.
  pi3bplus  board frame of the drawing: x = bx 0..85 (microSD edge -> USB edge),
            y = by 0..56 (GPIO edge -> power/HDMI/AV edge), z 0 = PCB underside,
            components on top from z = 1.6. Underside parts at z < 0.
  pico      board in xy (21 x 51), z 0..1 PCB, parts on +z, USB at the y = 51 end.
  switch    6x6 tactile, z 0 = seating plane (leg side), body 0..3.5, plunger
            tip at z = sw_actuator_h, legs down to z -3.5.
  screw_m3x8  ISO 7380 button head, bearing face at z 0, head +z, shank -z.
  insert_m3   knurled heat-set insert, z 0..5, top at z 5.
  magnet    6 x 3 disc, z 0..3.
  bank      x 0..bank_w, y 0..bank_h, z 0..bank_t, Type-C port on the x = 0 short end.
  speaker   x 0..70, y 0..30, z 0..16, front (drivers) at z 0.
  pam8403   x 0..pam_w, y 0..pam_h, z 0 = PCB underside.
  heatsink_soc / heatsink_lan  base on z 0, fins up.

Run:  python cad2/components/build_components.py
"""
import math
import os
import re
import sys

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))
CAD2 = os.path.dirname(HERE)
VENDOR = os.path.join(CAD2, "vendor")
SRC = open(os.path.join(CAD2, "enclosure.scad"), encoding="utf-8").read()


def P(name, default):
    """Read a numeric top-level parameter from enclosure.scad."""
    m = re.search(r"^\s*" + re.escape(name) + r"\s*=\s*([-0-9.]+)\s*;", SRC, re.M)
    return float(m.group(1)) if m else float(default)


SW_ACT = P("sw_actuator_h", 5.0)
BANK_W, BANK_H, BANK_T = P("bank_w", 106), P("bank_h", 69), P("bank_t", 14.5)
PAM_W, PAM_H = P("pam_w", 21), P("pam_h", 18)
HS_H = P("heatsink_h", 6)
PI_SD_BY = P("pi_sd_by", 28)


def box(x0, y0, z0, x1, y1, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def cyl(r, z0, z1, x=0, y=0):
    return cq.Workplane("XY").circle(r).extrude(z1 - z0).translate((x, y, z0))


def save(shape, name, tol=0.05):
    path = os.path.join(HERE, name + ".stl")
    if isinstance(shape, cq.Workplane):
        shape = shape.val() if len(shape.vals()) == 1 else cq.Compound.makeCompound(
            [v for v in shape.vals()])
    cq.exporters.export(shape, path, tolerance=tol, angularTolerance=0.25)
    bb = shape.BoundingBox()
    print(f"  {name:28s} {os.path.getsize(path)/1024:8.0f} kB   "
          f"x {bb.xmin:7.2f}..{bb.xmax:7.2f}  y {bb.ymin:7.2f}..{bb.ymax:7.2f}  "
          f"z {bb.zmin:6.2f}..{bb.zmax:6.2f}")


def solids_to_volume(solids, tol=0.05):
    """Vendor STEPs tessellate into touching/overlapping solids that share
    vertices, which is not a closed volume and breaks every boolean fit check.
    Mesh each solid on its own, fall back to its convex hull if a solid does
    not close (tiny SMD parts), then union them into ONE watertight mesh."""
    import trimesh
    meshes, hulls = [], 0
    for v in solids:
        verts, tris = v.tessellate(tol, 0.3)
        if not tris:
            continue
        m = trimesh.Trimesh([(p.x, p.y, p.z) for p in verts], tris, process=True)
        if not m.is_watertight:
            m.merge_vertices(); m.fill_holes()
        if not m.is_watertight or m.volume <= 0:
            m = m.convex_hull; hulls += 1
        meshes.append(m)
    out = trimesh.boolean.union(meshes, engine="manifold")
    print(f"    {len(meshes)} solids -> 1 volume ({hulls} replaced by hulls), watertight={out.is_watertight}")
    return out


def save_mesh(m, name):
    path = os.path.join(HERE, name + ".stl")
    m.export(path)
    lo, hi = m.bounds
    print(f"  {name:28s} {os.path.getsize(path)/1024:8.0f} kB   "
          f"x {lo[0]:7.2f}..{hi[0]:7.2f}  y {lo[1]:7.2f}..{hi[1]:7.2f}  z {lo[2]:6.2f}..{hi[2]:6.2f}")


def union_all(parts):
    out = parts[0]
    for p in parts[1:]:
        out = out.union(p)
    return out


# ---------------------------------------------------------------- display
def build_display():
    s = cq.importers.importStep(os.path.join(VENDOR, "5inch-dsi-lcd_asm.stp"))
    keep = []
    dropped = 0
    for v in s.solids().vals():
        b = v.BoundingBox()
        # the 8 hex standoffs: 5.5 across flats, hang 4.0 behind the PCB
        if abs(b.xlen - 5.5) < 0.2 and abs(b.ylen - 5.5) < 0.2 and b.zmin < -7.0:
            dropped += 1
            continue
        keep.append(v)
    assert dropped == 8, f"expected 8 standoffs, found {dropped}"
    zfront = cq.Compound.makeCompound(keep).BoundingBox().zmax   # glass front, +5.40
    # vendor: front at +z, VA centre at the origin. Rotate 180 deg about y
    # (x -> -x, z -> -z) and put the glass front on z = 0.
    keep = [v.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), 180).translate(cq.Vector(0, 0, zfront))
            for v in keep]
    save_mesh(solids_to_volume(keep, 0.08), "display_waveshare_5in_dsi")


# ------------------------------------------------------------------- pico
def build_pico():
    s = cq.importers.importStep(os.path.join(VENDOR, "Pico-R3.step"))
    # vendor: board in xz, length along -z, thickness along y (PCB y -0.5..0.5)
    # -> rotate +90 about x maps (x, y, z) -> (x, -z, y)
    sol = [v.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 90).translate(cq.Vector(0, 0, 0.5))
           for v in s.solids().vals()]
    save_mesh(solids_to_volume(sol, 0.05), "pico")


# ------------------------------------------------------------ Pi 3 B+
def build_pi():
    T = 1.6
    L, Wd, R = 85.0, 56.0, 3.0
    pcb = (cq.Workplane("XY").rect(L, Wd, centered=False).extrude(T)
           .edges("|Z").fillet(R))
    for hx, hy in [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]:
        pcb = pcb.cut(cyl(1.375, -1, T + 1, hx, hy))
    top = T
    parts = []
    # 40-pin GPIO: black base 2.5 tall + 40 square pins to 8.5
    parts.append(box(7.11, 1.04, top, 57.94, 6.04, top + 2.5))
    for i in range(20):
        for j in range(2):
            x = 8.33 + i * 2.54
            y = 2.27 + j * 2.54
            parts.append(box(x - 0.32, y - 0.32, top, x + 0.32, y + 0.32, top + 8.5))
    # PoE header, 2x2
    parts.append(box(58.9, 7.4, top, 63.9, 12.4, top + 2.5))
    for x in (60.13, 62.67):
        for y in (8.63, 11.17):
            parts.append(box(x - 0.32, y - 0.32, top, x + 0.32, y + 0.32, top + 8.5))
    # SoC with the 3B+ heat spreader
    parts.append(box(20.0, 17.5, top, 34.0, 31.5, top + 1.4))
    # LAN7515
    parts.append(box(55.0, 24.5, top, 64.0, 33.5, top + 1.0))
    # wireless module can (CYW43455) left of the SoC
    parts.append(box(4.0, 8.0, top, 15.0, 17.5, top + 1.6))
    # PMIC and a spread of passives so the board reads as a board
    parts.append(box(14.0, 38.0, top, 21.0, 45.0, top + 1.0))
    for x, y in [(38, 12), (41, 12), (44, 12), (47, 16), (38, 35), (42, 40), (24, 40), (27, 46)]:
        parts.append(box(x, y, top, x + 1.6, y + 0.8, top + 0.6))
    # DSI (left edge) and CSI (by the HDMI) FPC sockets, 5.5 tall
    parts.append(box(0.35, 16.81, top, 5.82, 39.22, top + 5.5))
    parts.append(box(43.3, 34.6, top, 46.7, 56.0 - 0.5, top + 5.5))
    # micro-USB power: 7.5 wide, 3.0 tall, 1.5 past the board edge
    parts.append(box(10.62 - 3.75, 56 - 5.0, top, 10.62 + 3.75, 56 + 1.21, top + 3.0)
                 .cut(box(10.62 - 3.4, 56 - 3.0, top + 0.3, 10.62 + 3.4, 56 + 1.3, top + 2.4)))
    # full-size HDMI: 15.0 wide, 6.5 tall, 1.8 past the edge, trapezoid mouth
    hd = box(32.03 - 7.24, 56 - 11.5, top, 32.03 + 7.24, 56 + 1.48, top + 6.5)
    mouth = (cq.Workplane("XZ").polyline([(-7.0, 0.6), (7.0, 0.6), (7.0, 4.4),
                                          (5.6, 5.9), (-5.6, 5.9), (-7.0, 4.4)]).close()
             .extrude(-9.0).translate((32.03, 56 + 1.58, top)))
    parts.append(hd.cut(mouth))
    # 3.5 mm AV jack: body 7 x 12.5 x 6, barrel 6 dia to 3.0 past the edge
    parts.append(box(53.53 - 3.5, 56 - 12.5, top, 53.53 + 3.5, 56, top + 6.0))
    barrel = (cq.Workplane("XZ").circle(3.0).extrude(-2.51)
              .translate((53.53, 56.0, top + 3.0)))
    barrel = barrel.cut(cq.Workplane("XZ").circle(1.8).extrude(-2.7)
                        .translate((53.53, 56.1, top + 3.0)))
    parts.append(barrel)
    # two USB-A stacks: 17.3 deep, 1.6 past the edge, 16 tall, two mouths each
    for y0, y1 in [(2.44, 15.57), (20.42, 33.59)]:
        st = box(69.27, y0, top, 86.98, y1, top + 16.0)
        st = st.union(box(86.49, y0 - 0.76, top + 1.0, 86.98, y1 + 0.8, top + 15.0))   # flange tabs
        for zc in (top + 4.0, top + 12.0):
            st = st.cut(box(78.0, y0 + 0.6, zc - 2.6, 87.1, y1 - 0.6, zc + 2.6))
            st = st.union(box(78.0, y0 + 1.2, zc - 1.9, 86.6, y1 - 1.2, zc - 0.3))  # tongue
        parts.append(st)
    # RJ45: 21.3 deep, 2.0 past the edge, 13.5 tall, latch mouth
    rj = box(65.65, 38.02, top, 86.98, 53.51, top + 13.5)
    rj = rj.cut(box(72.0, 40.3, top + 1.5, 87.1, 51.3, top + 10.5))
    rj = rj.cut(box(72.0, 43.5, top + 10.4, 87.1, 48.1, top + 12.3))
    parts.append(rj)
    # UNDERSIDE: microSD socket + card, and the LPDDR2 RAM under the SoC
    sd0 = PI_SD_BY - 6.5
    parts.append(box(0.0, sd0, -1.2, 12.0, sd0 + 13.0, 0.0))
    # through-hole pins and pegs under the USB stacks and the RJ45
    parts.append(box(70.0, 2.9, -1.8, 84.0, 33.1, 0.0))
    parts.append(box(67.0, 38.6, -1.8, 84.0, 52.9, 0.0))
    parts.append(box(-2.5, PI_SD_BY - 5.5, -1.0, 1.0, PI_SD_BY + 5.5, -0.2))  # card lip
    parts.append(box(21.0, 18.5, -1.0, 33.0, 30.5, 0.0))
    # through-hole stubs of the GPIO header under the board
    parts.append(box(7.6, 1.5, -1.8, 57.4, 5.6, 0.0))

    conn = parts[0]
    for p in parts[1:]:
        conn = conn.union(p)
    save(pcb.union(conn), "pi3bplus", tol=0.05)   # fit checks
    save(pcb, "pi3bplus_pcb", tol=0.05)           # viewer colours: board ...
    save(conn.cut(pcb), "pi3bplus_parts", tol=0.05)  # ... and everything on it


def build_heatsinks():
    def sink(w, d, h, fins):
        base = box(0, 0, 0, w, d, 1.6)
        pitch = w / fins
        for i in range(fins):
            x = i * pitch + pitch * 0.2
            base = base.union(box(x, 0, 1.6, x + pitch * 0.6, d, h))
        return base
    save(sink(14.0, 14.0, HS_H, 5), "heatsink_soc")
    save(sink(9.0, 9.0, min(HS_H, 5.0), 3), "heatsink_lan")


# ------------------------------------------------------------ switches
def build_switch():
    body = box(-3.0, -3.0, 0.0, 3.0, 3.0, 3.1)
    cover = box(-3.0, -3.0, 3.1, 3.0, 3.0, 3.5)
    boss = cyl(1.75, 3.5, SW_ACT)
    legs = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * 3.25, sy * 2.25
            legs.append(box(x - 0.35, y - 0.35, -3.5, x + 0.35, y + 0.35, 0.6))
            legs.append(box(min(sx * 3.0, sx * 3.6), y - 0.35, 0.3,
                            max(sx * 3.0, sx * 3.6), y + 0.35, 0.8))
    sw = union_all([body, cover, boss] + legs)
    save(sw, "tactile_6x6")


# ------------------------------------------------------------- fasteners
def build_screw():
    # ISO 7380 M3: dk 5.7, k 1.65, hex s 2.0, shank 3.0 x 8
    head = (cq.Workplane("XY").circle(2.85).extrude(0.5)
            .faces(">Z").workplane().circle(2.85).workplane(offset=1.15).circle(1.6).loft())
    head = head.cut(cq.Workplane("XY").polygon(6, 2.0 / math.cos(math.pi / 6))
                    .extrude(1.2).translate((0, 0, 0.6)))
    shank = cyl(1.5, -8.0, 0.0)
    for i in range(6):                       # a few thread rings: reads as a screw,
        z = -7.4 + i * 1.2                   # stays light in the viewer
        shank = shank.cut(cyl(1.5, z, z + 0.3).cut(cyl(1.25, z - 0.1, z + 0.4)))
    save(union_all([head, shank]), "screw_m3x8", tol=0.08)


def build_insert():
    ins = cyl(2.2, 0, 5.0)
    for k in range(3):
        z = 0.5 + k * 1.6
        ins = ins.cut(cyl(2.3, z, z + 0.5).cut(cyl(1.95, z - 0.1, z + 0.6)))
    ins = ins.cut(cyl(1.3, -0.1, 5.1))
    save(ins, "insert_m3")


def build_magnet():
    save(cyl(3.0, 0, 3.0).edges().chamfer(0.2), "magnet_6x3")


# ------------------------------------------------------ bank, speaker, amp
def build_bank():
    b = (cq.Workplane("XY").rect(BANK_W, BANK_H, centered=False).extrude(BANK_T)
         .edges("|Z").fillet(9.0).edges().fillet(2.5))
    # Type-C port on the x = 0 short end (listing photos; exact offset along
    # the end unpublished, so centred here)
    b = b.cut(box(-0.1, BANK_H / 2 - 4.6, BANK_T / 2 - 1.7,
                  7.0, BANK_H / 2 + 4.6, BANK_T / 2 + 1.7).edges("|X").fillet(1.5))
    # MagSafe ring on the back face (z 0)
    b = b.cut(cyl(28.0, -0.1, 0.4, BANK_W / 2, BANK_H / 2).cut(cyl(26.5, -0.2, 0.5, BANK_W / 2, BANK_H / 2)))
    # status LEDs and button on the top edge
    for i in range(4):
        b = b.cut(cyl(0.6, BANK_T - 0.3, BANK_T + 0.1, BANK_W / 2 - 6 + i * 4, BANK_H - 8))
    save(b, "power_bank")


def build_speaker():
    w, h, t = 70.0, 30.0, 16.0
    sp = (cq.Workplane("XY").rect(w, h, centered=False).extrude(t)
          .edges("|Z").fillet(2.0))
    for cx in (w * 0.28, w * 0.72):          # two drivers behind a grille
        sp = sp.cut(cyl(11.5, -0.1, 1.2, cx, h / 2))
        for dx in range(-9, 10, 3):
            for dy in range(-9, 10, 3):
                if dx * dx + dy * dy < 100:
                    sp = sp.union(cyl(0.9, 0.0, 1.2, cx + dx, h / 2 + dy))
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = w / 2 + sx * 31.5, h / 2 + sy * 12.0
            sp = sp.cut(cyl(1.6, -0.1, t + 0.1, x, y))
    sp = sp.union(box(w / 2 - 4, h - 0.1, t - 5, w / 2 + 4, h + 3.0, t - 1))  # lead grommet
    save(sp, "speaker_fit0502")


def build_pam():
    pcb = box(0, 0, 0, 21.0, 18.0, 1.2)
    chip = box(5.5, 6.0, 1.2, 15.5, 10.0, 2.7)
    parts = [pcb, chip]
    for x in (2.0, 4.54, 7.08, 13.9, 16.44, 18.98):     # wire pads / pin header
        parts.append(box(x - 0.9, 14.5, 1.2, x + 0.9, 16.5, 1.4))
    for x, y in [(3, 3), (17, 3), (3, 9), (17, 9)]:
        parts.append(box(x, y, 1.2, x + 1.6, y + 0.8, 2.0))
    save(union_all(parts), "pam8403_mini")


def main():
    os.makedirs(HERE, exist_ok=True)
    only = set(sys.argv[1:])
    jobs = [("display", build_display), ("pico", build_pico), ("pi", build_pi),
            ("heatsinks", build_heatsinks), ("switch", build_switch),
            ("screw", build_screw), ("insert", build_insert), ("magnet", build_magnet),
            ("bank", build_bank), ("speaker", build_speaker), ("pam", build_pam)]
    print(f"switch actuator {SW_ACT} mm, bank {BANK_W} x {BANK_H} x {BANK_T}, "
          f"heatsink {HS_H} mm  (from enclosure.scad)")
    for name, fn in jobs:
        if only and name not in only:
            continue
        fn()


if __name__ == "__main__":
    main()
