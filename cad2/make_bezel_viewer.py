"""3D viewer: the display bezel fitted over Waveshare's own model of the screen (50H-800480-IPS-CT).

  python cad2/make_bezel_viewer.py      -> Any% Bezel Viewer.html (repo root)
Meshes: cad2/stl_demo/bezel/ (glass, lcd from the vendor STEP; bezel_fitted from display_bezel.scad)."""
import base64
import gzip
import io
import json
import os

import trimesh

CAD2 = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CAD2)
SRC = os.path.join(CAD2, "stl_demo", "bezel")
FACE_Z = -1.75                                    # the LCD back plate in the model = the shell face


def blob(path, dz=0.0):
    m = trimesh.load(path)
    m.apply_translation([0, 0, dz])
    buf = io.BytesIO()
    m.export(buf, file_type="stl")
    return base64.b64encode(gzip.compress(buf.getvalue(), 9)).decode()


def main():
    home = os.path.join(ROOT, "launcher", "tests", "out", "home.png")
    shot = "data:image/png;base64," + base64.b64encode(open(home, "rb").read()).decode() if os.path.exists(home) else ""
    data = {
        "parts": [
            {"id": "bezel", "label": "Bezel (black PLA)", "colour": "#1c1d20", "blob": blob(os.path.join(SRC, "bezel_fitted.stl"), FACE_Z)},
            {"id": "glass", "label": "Touch glass 127.70 x 87.45", "colour": "#0b0c0e", "blob": blob(os.path.join(SRC, "glass.stl"))},
            {"id": "lcd", "label": "LCD module 120.70 x 75.80", "colour": "#8c9299", "blob": blob(os.path.join(SRC, "lcd.stl"))},
        ],
        "face_z": FACE_Z, "shot": shot,
    }
    from bezel_viewer_page import PAGE
    out = os.path.join(ROOT, "Any% Bezel Viewer.html")
    open(out, "w", encoding="utf-8").write(PAGE.replace("__DATA__", json.dumps(data)))
    print(out, f"{os.path.getsize(out) / 1024:.0f} kB")


if __name__ == "__main__":
    main()
