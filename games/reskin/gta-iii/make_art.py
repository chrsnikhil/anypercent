"""Launcher art for the GTA III app entry: our own drawing (a night skyline and the title), nothing from the game.
The game's data is the owner's own copy and stays off the repo, so the entry ships no screenshots.

  python make_art.py OUT_DIR

Writes gta-iii-tile.png (160x144, like a game frame) and gta-iii-bg.png."""
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

NIGHT, DUSK, BLOCK, WINDOW, TITLE = (12, 14, 30), (54, 40, 78), (44, 48, 80), (240, 196, 92), (236, 239, 255)
W, H, S = 160, 144, 6
FONTS = ["C:/Windows/Fonts/ariblk.ttf", "C:/Windows/Fonts/arialbd.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def font(size):
    for f in FONTS:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def tile():
    img = Image.new("RGB", (W * S, H * S), NIGHT)
    d = ImageDraw.Draw(img)
    for y in range(H * S):                                         # dusk glow along the horizon
        t = max(0.0, (y - 30 * S) / (70 * S))
        c = tuple(round(a + (b - a) * min(1.0, t)) for a, b in zip(NIGHT, DUSK))
        d.line((0, y, W * S, y), fill=c)
    rnd = random.Random(3)
    x = 0
    while x < W * S:                                               # skyline with lit windows
        bw, bh = rnd.randint(14, 28) * S, rnd.randint(30, 72) * S
        top = 100 * S - bh
        d.rectangle((x, top, x + bw - S, 100 * S), fill=BLOCK)
        for wy in range(top + 4 * S, 98 * S, 6 * S):
            for wx in range(x + 3 * S, x + bw - 4 * S, 5 * S):
                if rnd.random() < 0.35:
                    d.rectangle((wx, wy, wx + 2 * S, wy + 2 * S), fill=WINDOW)
        x += bw
    d.rectangle((0, 100 * S, W * S, H * S), fill=NIGHT)
    d.text((80 * S, 122 * S), "GTA III", font=font(22 * S), fill=TITLE, anchor="mm")
    return img.resize((W, H), Image.LANCZOS)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    t = tile()
    t.save(os.path.join(out, "gta-iii-tile.png"))
    bg = t.crop((0, 22, 160, 118)).resize((200, 120), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3))
    bg.point(lambda v: round(v * 0.35)).save(os.path.join(out, "gta-iii-bg.png"))
    print("gta-iii art in", out)


if __name__ == "__main__":
    main()
