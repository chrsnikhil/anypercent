"""Render the sponsor logos for the launcher's themes: arca_launcher/assets/logo-<theme id>.png, white on
transparent at 64 px tall (the launcher scales them down), so they read on every theme's dark ground.

  pip install resvg-py pillow
  python launcher/tools/make_sponsor_logos.py"""
import io
import os

import resvg_py
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ASSETS = os.path.join(REPO, "launcher", "arca_launcher", "assets")
HEIGHT = 64

LOGOS = {                                   # theme id -> source SVG (the same art as the printed panels)
    "world": "assets/logos/world_logo.svg",
    "arkiv": "assets/logos/arkiv_lockup_white.svg",
    "hedera": "cad2/logos/hedera.svg",
    "ethglobal": "cad2/logos/ethglobal_mumbai_logomark.svg",
}


def render(path):
    png = bytes(resvg_py.svg_to_bytes(svg_path=path, height=HEIGHT * 4))
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    img = img.crop(img.getbbox())                                  # no empty margin
    w = round(img.width * HEIGHT / img.height)
    img = img.resize((w, HEIGHT), Image.LANCZOS)
    white = Image.new("RGBA", img.size, (255, 255, 255, 0))
    white.putalpha(img.getchannel("A"))                            # one colour: white, the art's own shape
    return white


def main():
    os.makedirs(ASSETS, exist_ok=True)
    for theme_id, src in LOGOS.items():
        img = render(os.path.join(REPO, src))
        out = os.path.join(ASSETS, f"logo-{theme_id}.png")
        img.save(out)
        print(out, img.size)


if __name__ == "__main__":
    main()
