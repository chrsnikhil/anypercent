"""The launcher art for a reskinned game, from mGBA frames (shoot.py --big), in build_library.py's format:
<id>-tile.png (a native 160x144 frame), <id>-shot0..2.png, <id>-bg.png (blurred, darkened).

  python make_art.py <id> <out art dir> --tile title.png --shots a.png b.png c.png [--bg b.png]

Frames may be any whole multiple of 160x144 (shoot.py saves 3x); they are scaled back to native."""
import argparse
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "launcher", "tools"))
from build_library import FRAME_H, FRAME_W, make_bg   # noqa: E402


def native(path):
    img = Image.open(path).convert("RGB")
    if img.size != (FRAME_W, FRAME_H):
        img = img.resize((FRAME_W, FRAME_H), Image.NEAREST)
    return img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("id")
    p.add_argument("out")
    p.add_argument("--tile", required=True)
    p.add_argument("--shots", nargs="+", required=True)
    p.add_argument("--bg")
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    native(a.tile).save(os.path.join(a.out, f"{a.id}-tile.png"))
    for i, s in enumerate(a.shots[:3]):
        native(s).save(os.path.join(a.out, f"{a.id}-shot{i}.png"))
    make_bg(native(a.bg or a.shots[0])).save(os.path.join(a.out, f"{a.id}-bg.png"))
    print("art for", a.id, "in", a.out)


if __name__ == "__main__":
    main()
