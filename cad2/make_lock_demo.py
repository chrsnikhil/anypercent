"""
Any% switch lock demo: how a tactile switch goes into the ribbed switch plate, and how the
cap, plate and screws lock the button stack together. One self-contained HTML page.

  python cad2/make_lock_demo.py      -> Any% Switch Lock.html (repo root)

Geometry: cad2/stl_demo (real parts exported from enclosure.scad in device coordinates,
the ABXY corner of the shell cut from stl_assembly/asm_front_shell.stl).
"""
import base64
import gzip
import io
import json
import os

import numpy as np
import trimesh

CAD2 = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CAD2)
DEMO = os.path.join(CAD2, "stl_demo")
OUT = os.path.join(ROOT, "Any% Switch Lock.html")

# enclosure.scad values (device mm; z = 0 is the front face, +z toward the back)
DIM = {
    "t_face": 2.4, "cap_t": 1.6, "cap_proud": 2.0, "cap_gap": 0.15, "cap_float": 0.8,
    "z_cap_back": 4.0, "z_sw_tip": 4.15, "z_plate_f": 4.8, "z_sw_floor": 5.65, "z_plate_r": 9.15,
    "z_legs": 12.65, "sw_size": 6.0, "sw_pocket": 6.30, "sw_rib": 0.30, "sw_rib_w": 1.2, "sw_mouth": 0.5,
    "sw_travel": 0.25, "sw_plunger_d": 3.5, "sw_lead_clr": 4.2, "face_cap_d": 9.0, "flange_d": 12.0,
    "hole_d": 9.4, "rib_x": 1.6,
}
CAPS = {"a": (11.0, 82.0), "x": (20.5, 91.5), "y": (30.0, 82.0), "b": (20.5, 72.5)}


def blob(mesh):
    buf = io.BytesIO()
    mesh.export(buf, file_type="stl")
    return base64.b64encode(gzip.compress(buf.getvalue(), 9)).decode()


def load(name):
    return trimesh.load(os.path.join(DEMO, name + ".stl"))


def main():
    shell = load("shell").slice_plane((0, 0, 14.0), (0, 0, -1), cap=True)   # walls cut down so the stack shows
    screws = load("screws").split(only_watertight=False)
    groups = {}
    for part in screws:                       # one screw = every body within 4 mm of its axis
        c = part.bounds.mean(0)[:2]
        key = next((k for k in groups if np.hypot(*(np.array(k) - c)) < 4), tuple(c))
        groups.setdefault(key, []).append(part)
    screw_meshes = [trimesh.util.concatenate(v) for v in groups.values()]
    parts = [{"id": "shell", "blob": blob(shell)},
             {"id": "plate", "blob": blob(load("plate_old"))}]
    for k in CAPS:
        parts.append({"id": f"cap_{k}", "blob": blob(load(f"cap_{k}"))})
        parts.append({"id": f"sw_{k}", "blob": blob(load(f"sw_{k}"))})
    for i, m in enumerate(screw_meshes):
        parts.append({"id": f"screw_{i}", "blob": blob(m), "axis": [float(x) for x in m.bounds.mean(0)[:2]]})
    data = {"dim": DIM, "caps": CAPS, "parts": parts}
    from lock_demo_page import PAGE
    html = PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(OUT, f"{os.path.getsize(OUT) / 1024:.0f} kB, {len(screw_meshes)} screws")


if __name__ == "__main__":
    main()
