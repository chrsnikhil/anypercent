"""
Any% product viewer: one self-contained HTML page with the assembled device in 3D and the
six printed rear panels, swapped with a magnetic snap off / snap on animation.

  python cad2/make_product_viewer.py         -> Any% Product Viewer.html (repo root)

Sources (read, never written):
  build_stl_viewer.ps1 $AssemblyManifest     colours, alpha and labels of the assembled parts
  cad2/viewer_cache/asm/asm_*.stl            decimated binary assembly meshes (device coords, mm)
  cad2/make_panel_p2s.py PANELS              the panels actually printed and their spool colours
  cad2/stl_extra/arca_panel_<kind>_<part>.stl  panel parts in PRINT position (plate bottom at z = 0)
  launcher/tests/out/home.png                launcher home screen, shown on the display

The panel z offset (print position -> assembled) is measured, not assumed: it is the shift
that lines arca_panel_world_body up with the assembly's asm_panel_world_body.
"""
import ast
import base64
import gzip
import io
import json
import os
import re
import sys

import numpy as np
import trimesh

CAD2 = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CAD2)
ASM = os.path.join(CAD2, "stl_assembly")
CACHE = os.path.join(CAD2, "viewer_cache", "asm")
EXTRA = os.path.join(CAD2, "stl_extra")
SCREEN_PNG = os.path.join(ROOT, "launcher", "tests", "out", "home.png")
OUT = os.path.join(ROOT, "Any% Product Viewer.html")
MAX_MB = 12

# Not drawn: the Pico was dropped, asm_pi is the one-mesh fit-check copy of board + parts,
# and the old asm_panel_* meshes are replaced by the six printed panels below.
SKIP = re.compile(r"^asm_(pico|pi|panel_.*|magnets_panel)$")

# Panel display names, in switcher order.
PANEL_NAMES = [
    ("world", "World"),
    ("arkiv", "Arkiv"),
    ("arc", "Arc"),
    ("chainlink", "Chainlink"),
    ("hedera", "Hedera"),
    ("ethglobal", "ETHGlobal Mumbai"),
    ("ethglobal_lockup", "ETHGlobal Mumbai lockup"),
]
MAX_BODY_FACES = 20000        # panel bodies are flat plates: decimate if larger; logos stay as printed


def manifest():
    """$AssemblyManifest rows from build_stl_viewer.ps1, in order."""
    src = open(os.path.join(ROOT, "build_stl_viewer.ps1"), encoding="utf-8").read()
    rows = re.findall(r"'(asm_\w+)'\s*=\s*@\{\s*colour\s*=\s*'(#[0-9A-Fa-f]{6})';\s*alpha\s*=\s*([\d.]+);"
                      r"\s*group\s*=\s*'([^']+)';\s*label\s*=\s*'([^']+)'", src)
    if len(rows) < 20:
        sys.exit("could not read $AssemblyManifest from build_stl_viewer.ps1")
    return [(n, c.upper(), float(a), g, lab) for n, c, a, g, lab in rows]


def panels_table():
    """PANELS from make_panel_p2s.py, evaluated from its source without importing the module."""
    src = open(os.path.join(CAD2, "make_panel_p2s.py"), encoding="utf-8").read()
    ns = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            names += [e.id for t in node.targets if isinstance(t, ast.Tuple) for e in t.elts if isinstance(e, ast.Name)]
            if set(names) & {"WHITE", "BLACK", "RED", "BLUE", "GREEN", "YELLOW", "ORANGE", "PANELS"}:
                exec(compile(ast.Module([node], []), "make_panel_p2s.py", "exec"), ns)
    return ns["PANELS"]


def stl_bytes(m):
    buf = io.BytesIO()
    m.export(buf, file_type="stl")
    return buf.getvalue()


def blob(raw):
    return base64.b64encode(gzip.compress(raw, 9)).decode()


def panel_offset():
    """Shift from print position to assembled position, checked on the World body and logo."""
    a = trimesh.load(os.path.join(ASM, "asm_panel_world_body.stl")).bounds
    p = trimesh.load(os.path.join(EXTRA, "arca_panel_world_body.stl")).bounds
    d = a - p
    if np.abs(d[:, :2]).max() > 0.01 or abs(d[0, 2] - d[1, 2]) > 0.01:
        sys.exit(f"panel bodies do not differ by a pure z shift: {d.tolist()}")
    dz = float(round(d[0, 2], 3))
    la = trimesh.load(os.path.join(ASM, "asm_panel_world_logo.stl")).bounds
    lp = trimesh.load(os.path.join(EXTRA, "arca_panel_world_logo.stl")).bounds
    if np.abs(la - lp - [[0, 0, dz]] * 2).max() > 0.02:
        sys.exit("panel logo offset does not match the body offset")
    return dz, a, p


def magnet_centres(path):
    m = trimesh.load(path)
    cs = [p.bounds.mean(0) for p in m.split(only_watertight=False)]
    return sorted([[round(float(c[0]), 2), round(float(c[1]), 2), round(float(c[2]), 2)] for c in cs])


def screen_rect():
    """Display window in the front shell (x0, x1, y0, y1), and the glass z."""
    shell = trimesh.load(os.path.join(ASM, "asm_front_shell.stl"))
    disp = trimesh.load(os.path.join(ASM, "asm_display.stl"))

    def front_hit(m, x, y):
        loc = np.asarray(m.ray.intersects_location(np.array([[x, y, -5.0]]), np.array([[0, 0, 1.0]]),
                                                   multiple_hits=False)[0]).reshape(-1, 3)
        return float(loc[0, 2]) if len(loc) else None

    def is_open(x, y):
        z = front_hit(shell, x, y)
        return z is None or z > 1.0

    cx, cy = 101.0, 82.0
    def edge(fixed, start, step, axis):
        v = start
        while True:
            nv = v + step
            if not (is_open(nv, fixed) if axis == "x" else is_open(fixed, nv)):
                return v
            v = nv
    x0, x1 = edge(cy, cx, -0.1, "x"), edge(cy, cx, 0.1, "x")
    y0, y1 = edge(cx, cy, -0.1, "y"), edge(cx, cy, 0.1, "y")
    glass = front_hit(disp, cx, cy)
    return [round(x0, 1), round(x1, 1), round(y0, 1), round(y1, 1)], glass


def main():
    rows = manifest()
    dz, asm_b, prt_b = panel_offset()
    print(f"panel offset: asm_panel_world_body z {asm_b[0, 2]:.2f}..{asm_b[1, 2]:.2f}, "
          f"print z {prt_b[0, 2]:.2f}..{prt_b[1, 2]:.2f} -> dz = {dz:.2f} mm "
          f"(enclosure.scad comment says z_frame_r = 38.70; the built assembly uses {dz:.2f})")

    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    parts = []
    for name, colour, alpha, group, label in rows:
        if SKIP.match(name):
            continue
        path = os.path.join(CACHE, name + ".stl")
        if not os.path.exists(path):
            print("  missing", name)
            continue
        raw = open(path, "rb").read()
        m = trimesh.load(path)
        lo = np.minimum(lo, m.bounds[0])
        hi = np.maximum(hi, m.bounds[1])
        parts.append({"name": name, "colour": colour, "alpha": alpha, "label": label,
                      "smooth": name not in ("asm_front_shell",), "blob": blob(raw)})

    # panel magnets ride with the panel: store them in panel-local coordinates (inner face at z = 0)
    pm = trimesh.load(os.path.join(CACHE, "asm_magnets_panel.stl"))
    pm.apply_translation([0, 0, -dz])
    panel_mag_blob = blob(stl_bytes(pm))

    table = panels_table()
    panels = []
    for kind, title in PANEL_NAMES:
        ps = []
        for part, cname, hx in table[kind]:
            m = trimesh.load(os.path.join(EXTRA, f"arca_panel_{kind}_{part}.stl"))
            if abs(m.bounds[0, 2]) > 0.01 and part == "body":
                sys.exit(f"{kind} body is not in print position: {m.bounds.tolist()}")
            if part == "body" and len(m.faces) > MAX_BODY_FACES:
                m = m.simplify_quadric_decimation(face_count=MAX_BODY_FACES)
            hi = np.maximum(hi, m.bounds[1] + [0, 0, dz])
            ps.append({"part": part, "colour": hx.upper(), "cname": cname, "faces": len(m.faces),
                       "blob": blob(stl_bytes(m))})
        names = []
        for p in ps:
            if p["cname"] not in names:
                names.append(p["cname"])
        panels.append({"kind": kind, "name": title, "parts": ps, "colours": names})
        print(f"  {title:26s} " + ", ".join(f"{p['part']} {p['colour']} ({p['faces']} f)" for p in ps))

    win, glass = screen_rect()
    # the window is a little larger than the panel's 108 x 64.8 mm active area (bezel chamfer):
    # centre the active area in the measured window
    cx, cy = (win[0] + win[1]) / 2, (win[2] + win[3]) / 2
    rect = [round(cx - 54, 2), round(cx + 54, 2), round(cy - 32.4, 2), round(cy + 32.4, 2)]
    print(f"shell window x {win[0]}..{win[1]}, y {win[2]}..{win[3]}, glass z {glass}; "
          f"active area x {rect[0]}..{rect[1]}, y {rect[2]}..{rect[3]}")
    screen = None
    if os.path.exists(SCREEN_PNG):
        screen = "data:image/png;base64," + base64.b64encode(open(SCREEN_PNG, "rb").read()).decode()

    data = {
        "parts": parts,
        "panels": panels,
        "panelMagnets": panel_mag_blob,
        "dz": dz,
        "magnets": [[x, y] for x, y, _ in magnet_centres(os.path.join(ASM, "asm_magnets_frame.stl"))],
        "bounds": [lo.round(2).tolist(), hi.round(2).tolist()],
        "screen": {"rect": rect, "z": glass, "img": screen},
    }
    from product_viewer_page import HTML
    html = HTML.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    mb = os.path.getsize(OUT) / 1048576
    print(OUT, f"{mb:.2f} MB")
    if mb > MAX_MB:
        sys.exit(f"page is {mb:.1f} MB, over the {MAX_MB} MB budget")


if __name__ == "__main__":
    sys.path.insert(0, CAD2)
    main()
