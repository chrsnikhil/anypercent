"""Colour mockups for the Snake reskin, made by recolouring real mGBA frames of the game: the game already runs in
Game Boy Color with its own palettes (0 playfield and snake, 1 walls, 2 blue icon, 3 header bar, food, bonus), so a
mockup is each original colour mapped to its new one, plus the new art drawn in.

  A  "Ethereum night"  navy board with a dot grid, ETH-blue snake with lilac outline, purple chain blocks, a gold
                       ETH diamond to eat, a navy HUD with white text
  B  "Ethereum day"    the light ethereum.org look: off-white board, deep purple snake, slate blocks, gold food

  python mockups.py FRAMES_DIR OUT.png      (FRAMES_DIR has o-200.png title, o-700.png and o-1100.png play)"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = "C:/Windows/Fonts/arialbd.ttf"

# original colours, by palette: c0 white and c3 black are shared by all
ORIG = {
    "bg": (255, 255, 255), "outline": (0, 0, 0),
    "grass": (99, 222, 66), "snake_dark": (33, 107, 49),           # palette 0
    "wall_light": (189, 181, 16), "wall_dark": (123, 49, 8),       # palette 1
    "hud_light": (123, 123, 123), "hud_dark": (57, 57, 57),        # palette 3
    "icon_light": (24, 189, 239), "icon_dark": (0, 57, 189),       # palette 2
}

SCHEMES = {
    "A  Ethereum night": {
        "bg": (20, 22, 43), "outline": (192, 203, 246),
        "grass": (40, 44, 80), "snake_dark": (98, 126, 234),
        "wall_light": (123, 63, 228), "wall_dark": (69, 74, 117),
        "hud_light": (255, 214, 102), "hud_dark": (138, 146, 178),
        "icon_light": (192, 203, 246), "icon_dark": (98, 126, 234),
    },
    "B  Ethereum day": {
        "bg": (246, 244, 239), "outline": (28, 29, 51),
        "grass": (226, 224, 236), "snake_dark": (92, 46, 180),
        "wall_light": (138, 146, 178), "wall_dark": (69, 74, 117),
        "hud_light": (255, 200, 60), "hud_dark": (98, 126, 234),
        "icon_light": (192, 203, 246), "icon_dark": (98, 126, 234),
    },
}


def recolour(img, scheme):
    lut = {ORIG[k]: scheme[k] for k in ORIG}
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            px[x, y] = lut.get(px[x, y], px[x, y])
    return out


def diamond(d, cx, top, h, light, dark, outline):
    w = h * 0.6
    A, L, R, B, C = (cx, top), (cx - w / 2, top + h * .56), (cx + w / 2, top + h * .56), (cx, top + h * .74), \
        (cx, top + h * .42)
    d.polygon([A, L, C], fill=light)
    d.polygon([A, R, C], fill=dark)
    d.polygon([L, B, C], fill=dark)
    d.polygon([R, B, C], fill=light)
    L2, R2, B2, D = (cx - w / 2, top + h * .64), (cx + w / 2, top + h * .64), (cx, top + h * .82), (cx, top + h)
    d.polygon([L2, B2, D], fill=light)
    d.polygon([R2, B2, D], fill=dark)
    d.line([A, L, B, R, A], fill=outline)
    d.line([L2, D, R2, B2, L2], fill=outline)


def crisp(d, xy, text, size, fill, anchor="mm"):
    f = ImageFont.truetype(FONT, size)
    l, t, r, b = d.textbbox((0, 0), text, font=f, anchor=anchor)
    m = Image.new("1", (r - l + 2, b - t + 2), 0)
    ImageDraw.Draw(m).text((-l + 1, -t + 1), text, font=f, fill=1, anchor=anchor)
    d.bitmap((xy[0] + l - 1, xy[1] + t - 1), m, fill=fill)


def dress(img, scheme, kind):
    """The new art the recolour can't show: the ETH diamond to eat, the titles, a status word."""
    d = ImageDraw.Draw(img)
    s = scheme
    if kind == "title":
        d.rectangle((0, 0, 160, 12), fill=s["bg"])
        crisp(d, (80, 6), "ANY% WEB3 EDITION", 8, s["outline"])
        d.rectangle((0, 44, 160, 56), fill=s["bg"])
        crisp(d, (80, 50), "EAT THE ETH  -  YDG 2017", 7, s["outline"])
        diamond(d, 80, 66, 30, s["hud_light"], s["wall_light"], s["outline"])
    else:
        diamond(d, 112, 56, 13, s["hud_light"], s["wall_dark"], s["outline"])
        if kind == "over":
            d.rectangle((40, 134, 112, 143), fill=s["bg"])
            crisp(d, (76, 139), "REKT!", 8, s["outline"])
    return img


def main():
    frames, out = sys.argv[1], sys.argv[2]
    src = {k: Image.open(os.path.join(frames, f"o-{n}.png")).resize((160, 144), Image.NEAREST).convert("RGB")
           for k, n in (("title", 200), ("play", 700), ("over", 1100))}
    S = 3
    sheet = Image.new("RGB", (3 * (160 * S + 16) + 16, 2 * (144 * S + 40) + 16), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    for r, (name, scheme) in enumerate(SCHEMES.items()):
        y = 16 + r * (144 * S + 40)
        d.text((16, y), name, font=ImageFont.truetype(FONT, 20), fill=(255, 255, 255))
        for c, kind in enumerate(("title", "play", "over")):
            im = dress(recolour(src[kind], scheme), scheme, kind)
            sheet.paste(im.resize((160 * S, 144 * S), Image.NEAREST), (16 + c * (160 * S + 16), y + 28))
    sheet.save(out)
    print(out)


if __name__ == "__main__":
    main()
