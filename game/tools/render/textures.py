"""Custom textures for the office props (Pillow): the ETHMUMBAI banner, the whiteboard and the day skyline.
Run: python tools/render/textures.py --out art/textures"""
import argparse
import os
import random

from PIL import Image, ImageDraw, ImageFont

GAME = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONT = os.path.join(GAME, "..", "launcher", "arca_launcher", "assets", "fonts", "Outfit-Bold.ttf")


def banner():
    im = Image.new("RGB", (700, 200), (126, 58, 242))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 699, 199), outline=(255, 200, 40), width=10)
    d.text((350, 102), "ETHMUMBAI", font=ImageFont.truetype(FONT, 96), fill=(255, 255, 255), anchor="mm")
    return im


def whiteboard():
    im = Image.new("RGB", (400, 300), (250, 250, 252))
    d = ImageDraw.Draw(im)
    d.text((24, 14), "SHIP IT", font=ImageFont.truetype(FONT, 46), fill=(220, 40, 60))
    small = ImageFont.truetype(FONT, 24)
    blue, green = (30, 80, 200), (20, 150, 80)
    for x, word in ((30, "World"), (160, "Arkiv"), (290, "Arc")):
        d.rounded_rectangle((x, 120, x + 90, 174), 10, outline=blue, width=6)
        d.text((x + 12, 134), word, font=small, fill=blue)
    d.line((120, 147, 160, 147), fill=blue, width=5)
    d.line((250, 147, 290, 147), fill=blue, width=5)
    for k, length in enumerate((300, 220, 260, 150)):
        d.line((30, 210 + k * 22, 30 + length, 210 + k * 22), fill=green, width=6)
    d.text((300, 20), "36h", font=small, fill=(40, 40, 40))
    return im


def skyline_day():
    rnd = random.Random(7)
    im = Image.new("RGB", (512, 512))
    d = ImageDraw.Draw(im)
    for y in range(512):                                     # monsoon day sky: soft blue into a warm haze
        t = y / 512
        d.line((0, y, 511, y), fill=(int(150 + 80 * t), int(185 + 45 * t), int(225 + 10 * t)))
    for layer, (colour, hmin, hmax, base) in enumerate((((150, 160, 185), 80, 220, 330), ((105, 115, 145), 60, 260, 380))):
        x = 0
        while x < 512:
            w, h = rnd.randint(22, 60), rnd.randint(hmin, hmax)
            d.rectangle((x, base - h, x + w, 511), fill=colour)
            if layer == 1:
                for wy in range(base - h + 8, base, 14):
                    for wx in range(x + 5, x + w - 6, 10):
                        if rnd.random() < 0.35:
                            d.rectangle((wx, wy, wx + 4, wy + 6), fill=(215, 205, 160))
            x += w + rnd.randint(0, 6)
    d.rectangle((0, 400, 511, 511), fill=(70, 110, 140))    # the sea
    for k in range(6):
        d.line((0, 412 + k * 16, 511, 408 + k * 16), fill=(95, 140, 165), width=2)
    d.rectangle((300, 250, 310, 405), fill=(90, 95, 120))   # the sea link: a pylon, the deck, the cables
    d.rectangle((0, 395, 511, 402), fill=(90, 95, 120))
    for k in range(9):
        d.line((305, 255, 300 - 30 * k - 20, 396), fill=(200, 205, 215))
        d.line((305, 255, 310 + 30 * k + 20, 396), fill=(200, 205, 215))
    return im


def skyline_night():
    rnd = random.Random(8)
    im = Image.new("RGB", (512, 512))
    d = ImageDraw.Draw(im)
    for y in range(512):                                     # night sky: deep navy into a purple haze
        t = y / 512
        d.line((0, y, 511, y), fill=(int(12 + 40 * t), int(14 + 18 * t), int(40 + 40 * t)))
    for layer, (colour, hmin, hmax, base) in enumerate((((30, 32, 58), 80, 220, 330), ((18, 20, 38), 60, 260, 380))):
        x = 0
        while x < 512:
            w, h = rnd.randint(22, 60), rnd.randint(hmin, hmax)
            d.rectangle((x, base - h, x + w, 511), fill=colour)
            for wy in range(base - h + 8, base, 14):
                for wx in range(x + 5, x + w - 6, 10):
                    if rnd.random() < (0.25 if layer == 0 else 0.45):
                        d.rectangle((wx, wy, wx + 4, wy + 6), fill=(250, 210, 120))
            x += w + rnd.randint(0, 6)
    d.rectangle((0, 400, 511, 511), fill=(10, 16, 34))       # the sea at night
    for k in range(6):
        d.line((0, 412 + k * 16, 511, 408 + k * 16), fill=(40, 50, 80), width=2)
    d.rectangle((300, 250, 310, 405), fill=(40, 44, 70))    # the sea link, its cable lights
    d.rectangle((0, 395, 511, 402), fill=(40, 44, 70))
    for k in range(9):
        for j in range(0, 11):
            t = j / 10
            for sx in (-1, 1):
                x = 305 + sx * (30 * k + 20) * t
                d.ellipse((x - 1, 255 + 141 * t - 1, x + 1, 255 + 141 * t + 1), fill=(255, 240, 200))
    return im


def chai_sign():
    im = Image.new("RGB", (800, 200), (255, 200, 40))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 799, 199), outline=(118, 20, 50), width=10)
    d.text((400, 100), "CUTTING CHAI", font=ImageFont.truetype(FONT, 110), fill=(118, 20, 50), anchor="mm")
    return im


def logo_wall():
    """The pixel logo for the wall, 8x nearest-upscaled so Blender samples crisp pixels."""
    import sys
    sys.path.insert(0, os.path.join(GAME, "tools", "art"))
    import logo
    art = logo.pixelate(logo.load_keyed(logo.SOURCE), 92)
    return art.resize((art.width * 8, art.height * 8), Image.NEAREST)


def skyline_dawn():
    """The day skyline under a sunrise: a peach wash and a low sun."""
    im = skyline_day().convert("RGB")
    wash = Image.new("RGB", im.size)
    d = ImageDraw.Draw(wash)
    for y in range(im.height):
        t = y / (im.height - 1)
        d.line((0, y, im.width, y), fill=(255, int(150 + 60 * t), int(110 + 40 * t)))
    im = Image.blend(im, wash, 0.45)
    d = ImageDraw.Draw(im)
    r = im.width // 16
    cx, cy = int(im.width * 0.7), int(im.height * 0.55)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 230, 170))
    return im


def _sponsor(text, bg, fg):
    im = Image.new("RGB", (900, 300), bg)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 899, 299), outline=fg, width=12)
    d.text((450, 150), text, font=ImageFont.truetype(FONT, 150), fill=fg, anchor="mm")
    return im


def banner_arkiv():
    return _sponsor("ARKIV", (20, 24, 40), (120, 230, 200))


def banner_arc():
    return _sponsor("ARC", (250, 250, 250), (30, 30, 30))


def banner_world():
    return _sponsor("WORLD", (0, 0, 0), (255, 255, 255))


def stage_screen():
    im = Image.new("RGB", (1000, 560), (16, 20, 48))
    d = ImageDraw.Draw(im)
    d.text((500, 70), "ETHGlobal MUMBAI", font=ImageFont.truetype(FONT, 56), fill=(248, 208, 64), anchor="mm")
    d.rectangle((60, 130, 940, 500), outline=(56, 64, 110), width=6)    # the slide area: the game draws the slides
    return im


def banner_demo():
    im = Image.new("RGB", (1100, 160), (118, 20, 50))
    d = ImageDraw.Draw(im)
    d.text((550, 80), "DEMO DAY", font=ImageFont.truetype(FONT, 110), fill=(255, 200, 40), anchor="mm")
    return im


def stage_strip():
    im = Image.new("RGB", (60, 1300), (30, 30, 40))
    d = ImageDraw.Draw(im)
    for y in range(0, 1300, 120):
        d.rectangle((0, y, 59, y + 59), fill=(248, 208, 64))
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for name, make in (("banner", banner), ("whiteboard", whiteboard), ("skyline_day", skyline_day),
                       ("chai_sign", chai_sign), ("logo_wall", logo_wall),
                       ("skyline_night", skyline_night), ("skyline_dawn", skyline_dawn),
                       ("banner_arkiv", banner_arkiv), ("banner_arc", banner_arc), ("banner_world", banner_world),
                       ("stage_screen", stage_screen), ("banner_demo", banner_demo), ("stage_strip", stage_strip)):
        make().save(os.path.join(a.out, name + ".png"))


if __name__ == "__main__":
    main()
