"""RUSH HOUR's art: Kenney "Pixel Platformer" (CC0, art/kenney/) plus custom pieces drawn here (the hero's colours,
chai, the World orb, the Arkiv shelf, the venue door and Chainlink flag, the Mumbai local train tiles, the skyline and
the title card). Writes Butano BMP + JSON pairs into graphics/. The level's background map is rendered by
tools/level/build_level.py from level/level.txt with tileset() below.

Kenney tiles are 18 x 18; they are cropped to their central 16 x 16 (one pixel off each side), which keeps the
pixel art exactly crisp (a nearest-neighbour rescale would drop two uneven rows and columns).

Run from the game directory: /opt/arca-sandbox/venv/bin/python tools/art/build_art.py"""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gba4  # noqa: E402
import web3  # noqa: E402   the web3 edition's cast (bull, bears, USDC)

KEN = os.path.join(GAME, "art", "kenney", "pixel-platformer", "Tilemap")
IND = os.path.join(GAME, "art", "kenney", "pixel-platformer-industrial", "Tilemap")
GFX = os.path.join(GAME, "graphics")

SKY = (120, 184, 232)            # the backdrop behind every background (a Mumbai morning)
LEVEL_BANKS = 12                  # palette banks for the level map; the skyline gets the rest
SKYLINE_BANKS = 3

_cache = {}


def sheet(path):
    if path not in _cache:
        _cache[path] = Image.open(path).convert("RGBA")
    return _cache[path]


def cell(path, index, size, cols):
    x, y = (index % cols) * size, (index // cols) * size
    return sheet(path).crop((x, y, x + size, y + size))


def k16(index):
    """A Pixel Platformer tile (18 px, 20 per row) cropped to 16 x 16."""
    return cell(os.path.join(KEN, "tilemap_packed.png"), index, 18, 20).crop((1, 1, 17, 17))


def i16(index):
    """An industrial-expansion tile (18 px, 16 per row) cropped to 16 x 16."""
    return cell(os.path.join(IND, "tilemap_packed.png"), index, 18, 16).crop((1, 1, 17, 17))


def char(index):
    """A Pixel Platformer character (24 px, 9 per row)."""
    return cell(os.path.join(KEN, "tilemap-characters_packed.png"), index, 24, 9)


def blank(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def rect(d, x0, y0, x1, y1, c):
    d.rectangle((x0, y0, x1, y1), fill=c + (255,))


def px(d, x, y, c):
    d.point((x, y), fill=c + (255,))


# ---- level tiles -------------------------------------------------------------------------------------------------

MAROON, MAROON_D, CREAM, CREAM_D = (136, 32, 48), (88, 16, 32), (240, 208, 96), (200, 160, 64)
ROOF, ROOF_L, ROOF_D, GLASS, GLASS_L = (152, 160, 168), (200, 208, 216), (96, 104, 112), (40, 56, 88), (96, 128, 168)
IRON, IRON_D = (64, 64, 72), (32, 32, 40)


def train_tile(kind):
    """Mumbai local train carriage pieces (custom): roof, window, body, under (wheels); each 16 x 16."""
    im = blank(16, 16)
    d = ImageDraw.Draw(im)
    if kind == "roof":
        rect(d, 0, 4, 15, 15, CREAM)
        rect(d, 0, 2, 15, 6, ROOF)
        rect(d, 0, 2, 15, 2, ROOF_L)
        rect(d, 0, 7, 15, 7, ROOF_D)
        rect(d, 0, 12, 15, 15, CREAM_D)
        rect(d, 3, 10, 12, 15, GLASS)
        rect(d, 4, 11, 6, 12, GLASS_L)
    elif kind == "window":
        rect(d, 0, 0, 15, 15, CREAM)
        rect(d, 3, 0, 12, 7, GLASS)
        for x in (5, 8, 11):
            rect(d, x, 0, x, 7, ROOF_D)
        rect(d, 0, 9, 15, 10, CREAM_D)
        rect(d, 0, 11, 15, 15, MAROON)
    elif kind == "body":
        rect(d, 0, 0, 15, 15, MAROON)
        rect(d, 0, 7, 15, 7, MAROON_D)
        px(d, 3, 3, CREAM_D)
        px(d, 12, 3, CREAM_D)
    elif kind == "under":
        rect(d, 0, 0, 15, 8, MAROON)
        rect(d, 0, 8, 15, 9, MAROON_D)
        rect(d, 0, 10, 15, 11, IRON)
        for cx in (4, 12):
            d.ellipse((cx - 3, 9, cx + 3, 15), fill=IRON_D + (255,))
            px(d, cx, 12, ROOF)
    return im


def track_tile(top):
    """Ballast, sleepers and a rail (the train zone's ground); top: with the rail."""
    im = blank(16, 16)
    d = ImageDraw.Draw(im)
    rect(d, 0, 0, 15, 15, (112, 96, 88))
    for (x, y) in ((2, 6), (9, 3), (13, 10), (5, 12), (11, 14), (1, 1), (7, 9)):
        px(d, x, y, (152, 136, 120))
        px(d, (x + 3) % 16, (y + 5) % 16, (80, 64, 64))
    if top:
        rect(d, 0, 0, 15, 4, (96, 64, 48))
        rect(d, 0, 0, 15, 1, (184, 184, 192))
        rect(d, 0, 2, 15, 2, (104, 104, 112))
        for x in (2, 10):
            rect(d, x, 3, x + 3, 5, (72, 48, 40))
    return im


def gantry_tile(end):
    """A steel footbridge over the tracks (one-way), end: 0 middle, -1 left end, 1 right end."""
    im = blank(16, 16)
    d = ImageDraw.Draw(im)
    rect(d, 0, 0, 15, 3, (88, 96, 112))
    rect(d, 0, 0, 15, 0, (168, 176, 192))
    rect(d, 0, 4, 15, 4, (48, 52, 64))
    for x in range(0, 16, 4):
        d.line((x, 5, x + 3, 8), fill=(72, 80, 96, 255))
    if end == -1:
        rect(d, 0, 0, 1, 15, (72, 80, 96))
    if end == 1:
        rect(d, 14, 0, 15, 15, (72, 80, 96))
    return im


def tileset():
    """{name: 16 x 16 RGBA} for build_level.py. Variants end in a digit."""
    t = {}
    for n, i in enumerate((1, 2, 1, 2)):
        t["street_top%d" % n] = i16(i)          # grey kerb over earth
    for n, i in enumerate((32, 33, 34, 35)):
        t["street_fill%d" % n] = i16(i)
    for n, i in enumerate((41, 42, 41, 42)):
        t["market_top%d" % n] = k16(i)          # sandy top
    for n, i in enumerate((121, 122, 121, 123)):
        t["market_fill%d" % n] = k16(i)
    for n in range(4):
        t["train_top%d" % n] = track_tile(True)
        t["train_fill%d" % n] = track_tile(False)
    t["crate_street"] = k16(26)
    t["crate_market"] = k16(29)
    t["crate_train"] = i16(62)
    t["oneway_street_l"], t["oneway_street_m"], t["oneway_street_r"] = i16(87), i16(88), i16(90)
    t["oneway_market_l"], t["oneway_market_m"], t["oneway_market_r"] = k16(12), k16(13), k16(15)
    t["oneway_train_l"], t["oneway_train_m"], t["oneway_train_r"] = gantry_tile(-1), gantry_tile(0), gantry_tile(1)
    t["spike"] = k16(68)
    for kind in ("roof", "window", "body", "under"):
        t["train_" + kind] = train_tile(kind)
    t["pole"] = k16(52)
    t["plant0"], t["plant1"], t["plant2"] = k16(124), k16(125), k16(126)
    t["sign"] = k16(88)
    t["lamp_top"], t["lamp"] = i16(42), i16(58)
    return t


# ---- sprites -----------------------------------------------------------------------------------------------------

def recolour_hero(im):
    """Kenney's green character -> RUSH HOUR's hero: a saffron hoodie (greens become oranges)."""
    out = im.copy()
    pxs = out.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = pxs[x, y]
            if a and g > r + 16 and g > b:
                k = g / 255.0
                pxs[x, y] = (min(255, int(255 * k + 40)), int(150 * k), int(40 * k), a)
    return out


def on32(im, dx=0, dy=0):
    """A 24 x 24 character centred on a 32 x 32 sprite, feet on row 27 (shifted by dx, dy)."""
    c = blank(32, 32)
    c.alpha_composite(im, (4 + dx, 4 + dy))
    return c


def hero_frames():
    """Web3 edition: the bull in the saffron hoodie (tools/art/web3.py). Idle, run, jump, fall, out."""
    return [on32(f) for f in web3.bull_frames()]


def kenney_hero_frames():
    a, b = recolour_hero(char(0)), recolour_hero(char(1))
    dead = a.transpose(Image.FLIP_TOP_BOTTOM)
    return [on32(a), on32(b), on32(b, 0, -1), on32(a, 0, 0), on32(dead, 0, 2)]    # idle, run, jump, fall, dead


def bug_frames():
    """Web3 edition: the bugs are bears (bear market). Two steps, stomped."""
    return [on32(f) for f in web3.bear_frames()]


def kenney_bug_frames():
    a, b = char(15), char(16)
    squash = a.resize((24, 10), Image.NEAREST)
    s = blank(24, 24)
    s.alpha_composite(squash, (0, 14))
    return [on32(a), on32(b), on32(s)]


def chai_frames():
    """A clay kulhad of cutting chai, steam curling (4 frames)."""
    frames = []
    clay, clay_d, clay_l, tea, tea_l, steam = (192, 96, 56), (136, 64, 40), (224, 136, 88), (168, 112, 64), \
        (208, 160, 104), (240, 240, 248)
    for f in range(4):
        im = blank(16, 16)
        d = ImageDraw.Draw(im)
        # a small round-bellied clay cup, wide mouth, chai at the brim
        d.polygon([(3, 8), (12, 8), (11, 13), (9, 14), (6, 14), (4, 13)], fill=clay + (255,))
        d.line((12, 8, 11, 13), fill=clay_d + (255,))
        d.line((11, 13, 9, 14), fill=clay_d + (255,))
        rect(d, 6, 14, 9, 14, clay_d)
        rect(d, 2, 7, 13, 7, clay_l)
        rect(d, 3, 8, 12, 8, tea)
        rect(d, 4, 8, 6, 8, tea_l)
        px(d, 4, 10, clay_l)
        px(d, 5, 11, clay_l)
        # two curls of steam rising and swaying
        for base, phase in ((5, 0), (9, 2)):
            for k in range(5):
                y = 6 - k
                sway = ((k + f + phase) // 2) % 2
                if (k + f + phase) % 5 != 4:
                    px(d, base + sway, y, steam)
        frames.append(im)
    return frames


def orb_frames():
    """The World orb: a silver sphere with its dark ring, a glint going round (4 frames)."""
    frames = []
    for f in range(4):
        im = blank(16, 16)
        d = ImageDraw.Draw(im)
        d.ellipse((1, 1, 14, 14), fill=(232, 236, 244, 255), outline=(120, 128, 144, 255))
        d.ellipse((4, 4, 11, 11), outline=(24, 24, 32, 255))
        d.ellipse((5, 5, 10, 10), outline=(24, 24, 32, 255))
        rect(d, 7, 7, 8, 8, (24, 24, 32))
        glint = ((3, 4), (4, 3), (11, 3), (12, 4))
        gx, gy = [(3, 3), (11, 3), (12, 11), (3, 11)][f]
        px(d, gx, gy, (255, 255, 255))
        px(d, gx + 1, gy, (255, 255, 255))
        del glint
        frames.append(im)
    return frames


def shelf_frames():
    """The Arkiv shelf (a checkpoint): a data shelf with a flag; off, on, on-waving (16 x 32)."""
    frames = []
    wood, wood_d = (120, 80, 48), (80, 48, 32)
    books = [(64, 160, 232), (232, 88, 88), (240, 200, 72), (120, 200, 104), (184, 120, 216)]
    for f in range(3):
        im = blank(16, 32)
        d = ImageDraw.Draw(im)
        rect(d, 1, 12, 14, 31, wood_d)
        rect(d, 2, 13, 13, 30, (48, 32, 24))
        for row, y in enumerate((14, 20, 26)):
            rect(d, 1, y + 5, 14, y + 5, wood)
            for k in range(5):
                c = books[(k + row * 2) % 5]
                h = 4 - ((k + row) % 2)
                rect(d, 3 + k * 2, y + 5 - h, 3 + k * 2, y + 4, c)
        rect(d, 1, 12, 14, 12, wood)
        rect(d, 1, 31, 14, 31, wood)
        rect(d, 13, 1, 13, 11, (200, 200, 208))
        if f == 0:
            d.polygon([(12, 7), (7, 9), (12, 11)], fill=(128, 128, 136, 255))
        else:
            wave = f == 2
            flag = (168, 232, 48)
            d.polygon([(12, 1), (5, 2 + wave), (5, 5 + wave), (12, 6)], fill=flag + (255,))
            px(d, 8, 3 + wave, (40, 72, 16))
        frames.append(im)
    return frames


def door_frame():
    """The ETHGlobal Mumbai venue door (32 x 64): an arch with glass doors and a lime REG sign."""
    im = blank(32, 64)
    d = ImageDraw.Draw(im)
    stone, stone_d, stone_l = (224, 200, 160), (168, 136, 104), (248, 232, 200)
    rect(d, 0, 20, 31, 63, stone)
    d.pieslice((0, 4, 31, 36), 180, 360, fill=stone + (255,))
    d.arc((0, 4, 31, 36), 180, 360, fill=stone_d + (255,))
    d.pieslice((5, 12, 26, 32), 180, 360, fill=(40, 48, 88, 255))
    rect(d, 5, 22, 26, 63, (40, 48, 88))
    rect(d, 7, 30, 15, 63, (96, 160, 200))
    rect(d, 16, 30, 24, 63, (96, 160, 200))
    rect(d, 15, 30, 16, 63, (40, 48, 88))
    rect(d, 8, 31, 9, 40, (200, 232, 248))
    rect(d, 17, 31, 18, 40, (200, 232, 248))
    rect(d, 13, 45, 13, 50, (240, 200, 72))
    rect(d, 18, 45, 18, 50, (240, 200, 72))
    rect(d, 0, 20, 1, 63, stone_d)
    rect(d, 30, 20, 31, 63, stone_d)
    rect(d, 2, 20, 2, 63, stone_l)
    rect(d, 6, 22, 25, 28, (168, 232, 48))
    # "REG" in 3 x 5 pixels
    glyphs = {"R": ["110", "101", "110", "101", "101"], "E": ["111", "100", "110", "100", "111"],
              "G": ["011", "100", "101", "101", "011"]}
    for n, ch in enumerate("REG"):
        for y, row in enumerate(glyphs[ch]):
            for x, v in enumerate(row):
                if v == "1":
                    px(d, 10 + n * 4 + x, 23 + y, (24, 40, 16))
    return im


def flag_frames():
    """The Chainlink referee flag: a white hexagon ring on Chainlink blue, waving (2 frames, 16 x 16)."""
    frames = []
    blue, white = (55, 91, 210), (248, 248, 255)
    for f in range(2):
        im = blank(16, 16)
        d = ImageDraw.Draw(im)
        rect(d, 1, 0, 1, 15, (216, 216, 224))
        d.polygon([(2, 1), (14, 1 + f), (14, 10 + f), (2, 10)], fill=blue + (255,))
        cx, cy = 8, 5 + f
        hexagon = [(cx, cy - 3), (cx + 3, cy - 2), (cx + 3, cy + 1), (cx, cy + 3), (cx - 3, cy + 1), (cx - 3, cy - 2)]
        d.polygon(hexagon, fill=white + (255,))
        d.polygon([(cx, cy - 1), (cx + 1, cy - 1), (cx + 1, cy), (cx, cy + 1), (cx - 1, cy), (cx - 1, cy - 1)],
                  fill=blue + (255,))
        frames.append(im)
    return frames


def hud_frames():
    """16 x 16 HUD icons: heart, empty heart, chai, shield."""
    shield = blank(16, 16)
    d = ImageDraw.Draw(shield)
    d.ellipse((2, 2, 13, 13), fill=(232, 236, 244, 255), outline=(96, 104, 120, 255))
    d.ellipse((5, 5, 10, 10), outline=(24, 24, 32, 255))
    return [k16(44), k16(46), web3.usdc_icon(), shield]


def glow_frames():
    """The shield: a dotted lime ring round the hero (32 x 32, 2 frames): unlike anything else on screen."""
    frames = []
    for f in range(2):
        im = blank(32, 32)
        d = ImageDraw.Draw(im)
        d.ellipse((3, 3, 28, 29), outline=(168, 232, 48, 255))
        d.ellipse((4, 4, 27, 28), outline=(96, 176, 32, 255))
        pxs = im.load()
        for y in range(32):
            for x in range(32):
                if pxs[x, y][3] and (x + y + f) % 3 == 0:
                    pxs[x, y] = (0, 0, 0, 0)
        frames.append(im)
    return frames


# ---- backgrounds -------------------------------------------------------------------------------------------------

def skyline_image(w, h, horizon, seed=7, title=False):
    """A Mumbai skyline (custom): layered towers with lit windows, the Gateway of India, the Taj's dome and the
    sea link's cables, over a transparent sky (the backdrop colour shows through) or, for the title, a dawn sky."""
    im = blank(w, h)
    d = ImageDraw.Draw(im)
    if title:
        bands = [(40, 48, 104), (64, 64, 128), (104, 80, 144), (160, 96, 144), (216, 120, 128), (240, 160, 112),
                 (248, 200, 128)]
        bh = horizon // len(bands) + 1
        for i, c in enumerate(bands):
            rect(d, 0, i * bh, w - 1, min(horizon, (i + 1) * bh), c)
        d.ellipse((150, horizon - 34, 190, horizon + 6), fill=(255, 232, 160, 255))
    else:
        for i, c in enumerate([(136, 196, 236), (152, 204, 236), (176, 216, 236), (200, 224, 232)]):
            y0 = horizon - 64 + i * 16
            rect(d, 0, y0, w - 1, y0 + 15, c)
    far, near, lit = (112, 136, 168), (72, 88, 120), (248, 224, 136)
    if title:
        far, near = (96, 72, 120), (48, 40, 80)
    state = seed

    def rnd(n):
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return (state >> 8) % n
    x = 0
    while x < w:                                   # far towers
        bw, bh = 14 + rnd(20), 30 + rnd(50)
        rect(d, x, horizon - bh, x + bw - 1, horizon, far)
        x += bw + rnd(6)
    x = 0
    while x < w:                                   # near towers with windows
        bw, bh = 18 + rnd(22), 18 + rnd(36)
        rect(d, x, horizon - bh, x + bw - 1, horizon, near)
        for wy in range(horizon - bh + 4, horizon - 3, 6):
            for wx in range(x + 3, x + bw - 3, 5):
                if rnd(3) == 0:
                    rect(d, wx, wy, wx + 1, wy + 2, lit)
        x += bw + 4 + rnd(24)
    # the Gateway of India
    gx = w // 2 - 70 if title else 40
    g = (200, 160, 112) if not title else (88, 56, 88)
    gd = (160, 120, 88) if not title else (64, 40, 72)
    rect(d, gx, horizon - 40, gx + 44, horizon, g)
    d.pieslice((gx + 14, horizon - 30, gx + 30, horizon - 14), 180, 360, fill=gd + (255,))
    rect(d, gx + 14, horizon - 22, gx + 30, horizon, gd)
    for tx in (gx, gx + 36):
        rect(d, tx, horizon - 50, tx + 8, horizon - 40, g)
        d.pieslice((tx, horizon - 56, tx + 8, horizon - 46), 180, 360, fill=g + (255,))
    rect(d, gx + 18, horizon - 50, gx + 26, horizon - 40, g)
    d.pieslice((gx + 16, horizon - 58, gx + 28, horizon - 44), 180, 360, fill=g + (255,))
    # the Taj's red dome
    tx = gx + 60
    rect(d, tx, horizon - 36, tx + 40, horizon, (224, 208, 184) if not title else (80, 56, 96))
    d.pieslice((tx + 12, horizon - 52, tx + 28, horizon - 28), 180, 360,
               fill=((184, 72, 56) if not title else (120, 48, 72)) + (255,))
    for wx in range(tx + 3, tx + 38, 6):
        rect(d, wx, horizon - 30, wx + 2, horizon - 26, lit)
        rect(d, wx, horizon - 20, wx + 2, horizon - 16, lit)
    # the sea link
    sx = w - 150 if title else w - 180
    pylon = (216, 216, 224) if not title else (72, 64, 104)
    rect(d, sx, horizon - 12, sx + 140, horizon - 10, pylon)
    for p in (sx + 40, sx + 100):
        rect(d, p, horizon - 60, p + 2, horizon - 10, pylon)
        for k in range(1, 7):
            d.line((p + 1, horizon - 58 + k * 3, p + 1 - k * 6, horizon - 11), fill=pylon + (255,))
            d.line((p + 1, horizon - 58 + k * 3, p + 1 + k * 6, horizon - 11), fill=pylon + (255,))
    if title:
        rect(d, 0, horizon + 1, w - 1, h - 1, (32, 40, 88))
        for y in range(horizon + 3, h, 4):
            for x in range((y * 7) % 11, w, 11 + (y % 5)):
                rect(d, x, y, x + 3, y, (88, 96, 160))
        for y in range(horizon + 2, h, 3):
            rect(d, 162 + (y % 3), y, 178 - (y % 4), y, (248, 200, 128))
    return im


BIG = {  # 5 x 7 capitals for the title
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    " ": ["00000"] * 7,
}


def big_text(d, text, x, y, scale, fill, outline, shadow):
    def cells():
        for n, ch in enumerate(text):
            for r, row in enumerate(BIG[ch]):
                for c, v in enumerate(row):
                    if v == "1":
                        yield x + (n * 6 + c) * scale, y + r * scale
    for cx, cy in cells():
        rect(d, cx + 3, cy + 3, cx + scale + 2, cy + scale + 2, shadow)
    for cx, cy in cells():
        rect(d, cx - 2, cy - 2, cx + scale + 1, cy + scale + 1, outline)
    for cx, cy in cells():
        rect(d, cx, cy, cx + scale - 1, cy + scale - 1, fill)
        rect(d, cx, cy, cx + scale - 1, cy, (255, 248, 200))


def title_image():
    im = skyline_image(256, 256, 118, seed=11, title=True)
    full = Image.new("RGBA", (256, 256), (32, 40, 88, 255))
    full.alpha_composite(im)
    d = ImageDraw.Draw(full)
    big_text(d, "RUSH HOUR", 13, 16, 4, (248, 208, 64), (40, 24, 56), (24, 16, 40))
    # a local train crossing on the bridge line
    for n in range(4):
        x0 = 6 + n * 42
        rect(d, x0, 104, x0 + 38, 116, (136, 32, 48))
        rect(d, x0, 100, x0 + 38, 104, (240, 208, 96))
        for wx in range(x0 + 3, x0 + 36, 7):
            rect(d, wx, 101, wx + 3, 103, (40, 56, 88))
    rect(d, 0, 117, 255, 118, (24, 24, 32))
    return full


def card_image():
    """The how-to / results / pause panel: a framed dark card (transparent round it)."""
    im = blank(256, 256)
    d = ImageDraw.Draw(im)
    rect(d, 12, 8, 227, 151, (24, 24, 48))
    d.rectangle((12, 8, 227, 151), outline=(168, 232, 48, 255))
    d.rectangle((14, 10, 225, 149), outline=(64, 72, 120, 255))
    return im


FONT_PALETTE = [(0, 255, 0), (49, 65, 95), (108, 56, 90), (176, 50, 67), (225, 57, 57), (96, 97, 97), (73, 101, 130),
                (240, 101, 70), (98, 131, 191), (97, 142, 188), (255, 146, 83), (134, 184, 165), (0, 0, 0),
                (188, 193, 195), (255, 255, 255), (15, 0, 0)]      # Butano's 8x8 font: 14 is the ink, 12 the edge


def write_text_palette(name, ink):
    """A sprite palette for the font with another ink colour (the sprite text generator's accent)."""
    pal = [gba4.c15(c) for c in FONT_PALETTE]
    pal[14] = gba4.c15(ink)
    gba4.write_bmp("%s/%s.bmp" % (GFX, name), (8, 8), bytes(64), pal)
    gba4.write_json("%s/%s.json" % (GFX, name), {"type": "sprite_palette", "bpp_mode": "bpp_4", "colors_count": 16})


def build():
    os.makedirs(GFX, exist_ok=True)
    write_text_palette("text_gold", (248, 208, 64))
    write_text_palette("text_dim", (128, 136, 160))
    write_text_palette("text_lime", (168, 232, 48))
    gba4.write_sprite(GFX, "hero", hero_frames())
    gba4.write_sprite(GFX, "bug", bug_frames())
    gba4.write_sprite(GFX, "chai", web3.usdc_frames())         # web3 edition: the pickups are USDC
    gba4.write_sprite(GFX, "orb", orb_frames())
    gba4.write_sprite(GFX, "shelf", shelf_frames())
    gba4.write_sprite(GFX, "door", [door_frame()])
    gba4.write_sprite(GFX, "flag", flag_frames())
    gba4.write_sprite(GFX, "hud", hud_frames())
    gba4.write_sprite(GFX, "glow", glow_frames())
    gba4.write_bg(GFX, "skyline", skyline_image(512, 256, 200), SKYLINE_BANKS, SKY)
    gba4.write_bg(GFX, "title", title_image(), 12, (32, 40, 88))
    gba4.write_bg(GFX, "card", card_image(), 1, SKY)


if __name__ == "__main__":
    build()
    print("art written to", GFX)
