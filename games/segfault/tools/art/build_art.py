"""SEGFAULT's art: draws the wall textures, the HUD and the title / how-to / results cards with Pillow, converts the
Blender renders (art/renders, from tools/art/render_models.py) into billboards and sprites, and writes
  genart/segf_art.h / .c   the view's data: the in-game palette, 64x64 wall textures and bug billboards
                           (column-major, 8 bpp), the HUD strip and icons, the floor / ceiling column, the cards
  graphics/*.bmp + .json   Butano sprites: the blaster, the ghost phantom, the radar blip, the crosshair
  art/preview/*.png        what it all looks like, for review
The in-game palette is 64 base colours (index 0 = transparent / black) in hue ramps, repeated at four light levels:
index = level * 64 + base, level 0 bright .. 3 dark. The raycaster shades a wall column by OR-ing level << 6 into
its texels (side walls one level darker, far walls darker still). Run from the game directory:
    python tools/art/build_art.py            (the sandbox venv has Pillow)"""
import math
import os
import random
import struct
import sys

from PIL import Image, ImageDraw

GAME = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RENDERS = os.path.join(GAME, "art", "renders")
PREVIEW = os.path.join(GAME, "art", "preview")
GENART = os.path.join(GAME, "genart")
GRAPHICS = os.path.join(GAME, "graphics")
FONT_BMP = os.path.join(GAME, "fonts", "common_variable_8x8_font.bmp")
FONT_H = os.path.join(GAME, "include", "common_variable_8x8_sprite_font.h")

TEX = 64
LEVELS = (1.0, 0.72, 0.5, 0.32)
# (name, steps, darkest, brightest): 1 + 63 base colours
RAMPS = [
    ("grey", 9, (14, 14, 18), (240, 240, 244)),
    ("steel", 7, (18, 24, 34), (150, 172, 198)),
    ("green", 6, (8, 44, 18), (150, 255, 150)),
    ("amber", 6, (72, 36, 4), (255, 226, 96)),
    ("red", 6, (64, 8, 10), (255, 120, 100)),
    ("blue", 6, (8, 18, 72), (130, 200, 255)),
    ("beige", 6, (84, 70, 50), (238, 224, 196)),
    ("brown", 6, (38, 20, 10), (196, 136, 80)),
    ("purple", 6, (34, 8, 46), (226, 130, 255)),
    ("teal", 5, (4, 44, 50), (130, 255, 240)),
]


def q15(c):
    return tuple((v >> 3) << 3 for v in c)


def build_base():
    base, where = [(0, 0, 0)], {}
    for name, n, a, b in RAMPS:
        where[name] = (len(base), n)
        for i in range(n):
            t = i / (n - 1)
            # a slightly curved ramp: more steps in the darks, where a night-time server room lives
            t = t ** 1.15
            base.append(q15(tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3))))
    assert len(base) == 64, len(base)
    return base, where


BASE, WHERE = build_base()


def C(name, i):
    """Base palette index of step i (negative from the bright end) of a ramp."""
    start, n = WHERE[name]
    if i < 0:
        i += n
    return start + max(0, min(n - 1, i))


def rgb(name, i):
    return BASE[C(name, i)]


def palette256():
    pal = []
    for f in LEVELS:
        pal += [q15(tuple(int(v * f) for v in c)) for c in BASE]
    return pal


_near = {}


def nearest(c):
    """The base index (1..63) nearest to an RGB colour (weighted distance)."""
    c = tuple(c[:3])
    if c not in _near:
        best, bi = None, 1
        for i in range(1, 64):
            p = BASE[i]
            d = 2 * (c[0] - p[0]) ** 2 + 4 * (c[1] - p[1]) ** 2 + 3 * (c[2] - p[2]) ** 2
            if best is None or d < best:
                best, bi = d, i
        _near[c] = bi
    return _near[c]


def to_indices(img, alpha=True):
    """RGBA/RGB image -> list of base indices (row-major); alpha < 128 -> 0."""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    out = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            out.append(0 if alpha and a < 128 else nearest((r, g, b)))
    return out


def indices_to_image(idx, w, h, pal=None):
    pal = pal or BASE
    img = Image.new("RGB", (w, h))
    img.putdata([pal[i] for i in idx])
    return img


# ---- the 8x8 font (Butano's common variable font, vendored in fonts/) ----------------------------------------------

def load_font():
    im = Image.open(FONT_BMP)
    widths = []
    for line in open(FONT_H):
        s = line.strip()
        if s and s[0].isdigit() and "//" in s:
            widths.append(int(s.split(",")[0]))
    glyphs = {}
    glyphs[" "] = ([[0] * 8 for _ in range(8)], widths[0])
    for i in range(1, 95):                                # the sheet starts at '!': the space has no cell
        g = im.crop((0, (i - 1) * 8, 8, i * 8))
        glyphs[chr(32 + i)] = ([[g.getpixel((x, y)) for x in range(8)] for y in range(8)], widths[i])
    return glyphs


FONT = load_font()


def text_width(s, scale=1):
    return sum(FONT.get(ch, FONT["?"])[1] for ch in s) * scale


def draw_text(img, x, y, s, color, scale=1, shadow=None):
    """Draws with the 8x8 font's main colour pixels (index 14); shadow: colour for its outline pixels (12)."""
    px = img.load()
    w, h = img.size
    for ch in s:
        rows, cw = FONT.get(ch, FONT["?"])
        for gy in range(8):
            for gx in range(8):
                v = rows[gy][gx]
                col = color if v == 14 else (shadow if v == 12 else None)
                if col is None:
                    continue
                for sy in range(scale):
                    for sx in range(scale):
                        X, Y = x + gx * scale + sx, y + gy * scale + sy
                        if 0 <= X < w and 0 <= Y < h:
                            px[X, Y] = col
        x += cw * scale
    return x


# a tiny 3x5 font for labels on the textures
TINY = {
    "A": "010101111101101", "B": "110101110101110", "C": "011100100100011", "D": "110101101101110",
    "E": "111100110100111", "F": "111100110100100", "G": "011100101101011", "H": "101101111101101",
    "I": "111010010010111", "J": "001001001101010", "K": "101101110101101", "L": "100100100100111",
    "M": "101111111101101", "N": "110101101101101", "O": "010101101101010", "P": "110101110100100",
    "Q": "010101101110011", "R": "110101110101101", "S": "011100010001110", "T": "111010010010010",
    "U": "101101101101111", "V": "101101101101010", "W": "101101111111101", "X": "101101010101101",
    "Y": "101101010010010", "Z": "111001010100111", "0": "111101101101111", "1": "010110010010111",
    "2": "110001010100111", "3": "110001010001110", "4": "101101111001001", "5": "111100110001110",
    "6": "011100110101010", "7": "111001010010010", "8": "010101010101010", "9": "010101011001110",
    " ": "000000000000000", "-": "000000111000000", "!": "010010010000010", "?": "110001010000010",
    ":": "000010000010000", ".": "000000000000010", "/": "001001010100100", "+": "000010111010000",
    "<": "001010100010001", ">": "100010001010100", "#": "101111101111101",
}


def tiny(d, x, y, s, color):
    for ch in s:
        bits = TINY[ch]
        for i, b in enumerate(bits):
            if b == "1":
                d.point((x + i % 3, y + i // 3), fill=color)
        x += 4


def noise(img, box, colors, seed, density=1.0):
    rnd = random.Random(seed)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        for x in range(x0, x1):
            if rnd.random() < density:
                d.point((x, y), fill=rnd.choice(colors))


# ---- wall textures (64 x 64) ------------------------------------------------------------------------------------

def tex_rack():
    im = Image.new("RGB", (TEX, TEX), rgb("steel", 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 63, 3), fill=rgb("steel", 2))
    d.rectangle((0, 60, 63, 63), fill=rgb("steel", 2))
    for x0 in (1, 58):                                   # the rails, with their square holes
        d.rectangle((x0, 4, x0 + 4, 59), fill=rgb("steel", 3))
        d.line((x0, 4, x0, 59), fill=rgb("steel", 4))
        for y in range(6, 58, 4):
            d.rectangle((x0 + 1, y, x0 + 2, y + 1), fill=rgb("steel", 0))
    units = [(5, 17, "vent"), (19, 31, "drives"), (33, 45, "vent"), (47, 58, "drives")]
    rnd = random.Random(7)
    for y0, y1, kind in units:
        d.rectangle((7, y0, 56, y1), fill=rgb("steel", 2))
        d.line((7, y0, 56, y0), fill=rgb("steel", 4))
        d.line((7, y1, 56, y1), fill=rgb("steel", 0))
        if kind == "vent":
            for y in range(y0 + 2, y1 - 1, 2):
                d.line((10, y, 38, y), fill=rgb("steel", 0))
        else:
            for x in range(10, 40, 5):
                d.rectangle((x, y0 + 2, x + 3, y1 - 2), fill=rgb("steel", 1))
                d.line((x, y0 + 2, x + 3, y0 + 2), fill=rgb("steel", 3))
                d.point((x + 1, y1 - 3), fill=rgb("green", -1) if rnd.random() < 0.7 else rgb("amber", -1))
        for k, col in enumerate(("green", "amber", "blue")):     # status LEDs with a glow
            lx, ly = 44 + k * 4, (y0 + y1) // 2 - 1
            on = rnd.random() < 0.85
            if on:
                d.rectangle((lx - 1, ly - 1, lx + 2, ly + 2), fill=rgb(col, 1))
            d.rectangle((lx, ly, lx + 1, ly + 1), fill=rgb(col, -1) if on else rgb("steel", 1))
    return im


def cable_wall(seed, gap=False):
    im = Image.new("RGB", (TEX, TEX), rgb("grey", 3))
    noise(im, (0, 0, 64, 64), [rgb("grey", 2), rgb("grey", 3), rgb("grey", 3), rgb("grey", 4)], seed, 0.5)
    d = ImageDraw.Draw(im)
    for y in (16, 40):                                   # panel seams in the concrete
        d.line((0, y, 63, y), fill=rgb("grey", 2))
    d.rectangle((0, 0, 63, 5), fill=rgb("steel", 2))     # the cable tray
    d.line((0, 5, 63, 5), fill=rgb("steel", 0))
    for x in range(0, 64, 8):
        d.line((x, 0, x, 5), fill=rgb("steel", 4))
    colors = ["red", "blue", "amber", "green", "grey", "purple", "blue", "red"]
    rnd = random.Random(seed)
    xs = [6, 10, 14, 18, 40, 44, 48, 52] if not gap else [6, 10, 48, 52]
    for i, x in enumerate(xs):
        col = colors[i % len(colors)]
        phase = rnd.random() * 6
        for y in range(6, 64):
            xx = x + int(round(math.sin(y / 9.0 + phase) * 1.2))
            d.point((xx - 1, y), fill=rgb(col, 3 if col != "grey" else 2))
            d.point((xx, y), fill=rgb(col, 4 if col != "grey" else 1))
            d.point((xx + 1, y), fill=rgb(col, 1 if col != "grey" else 0))
    for y in (20, 44):                                   # cable ties
        for x0, x1 in ((4, 20), (38, 54)):
            if gap and x0 == 38:
                x0 = 46
            d.rectangle((x0, y, x1, y + 1), fill=rgb("steel", 5))
    d.rectangle((0, 60, 63, 63), fill=rgb("grey", 1))
    if gap:                                              # the secret wall: a crack and a scratched arrow
        pts = [(26, 12), (29, 20), (27, 27), (31, 35), (29, 44), (33, 52)]
        d.line(pts, fill=rgb("grey", 0), width=1)
        d.line((24, 30, 36, 30), fill=rgb("grey", 5))
        d.line((33, 27, 36, 30), fill=rgb("grey", 5))
        d.line((33, 33, 36, 30), fill=rgb("grey", 5))
    return im


def office_base(seed):
    im = Image.new("RGB", (TEX, TEX), rgb("beige", 3))
    noise(im, (0, 0, 64, 64), [rgb("beige", 3), rgb("beige", 3), rgb("beige", 2), rgb("beige", 4)], seed, 0.35)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 63, 2), fill=rgb("beige", 1))
    d.line((0, 31, 63, 31), fill=rgb("beige", 1))
    d.line((0, 32, 63, 32), fill=rgb("beige", 4))
    d.rectangle((0, 55, 63, 63), fill=rgb("brown", 2))
    d.line((0, 55, 63, 55), fill=rgb("brown", 4))
    d.line((63, 3, 63, 54), fill=rgb("beige", 2))
    return im


def tex_office():
    im = office_base(3)
    d = ImageDraw.Draw(im)
    d.rectangle((48, 38, 53, 46), fill=rgb("grey", 6))  # a light switch
    d.rectangle((50, 40, 51, 44), fill=rgb("grey", 4))
    d.rectangle((10, 8, 29, 26), fill=rgb("grey", 1))   # a framed poster: "SHIP IT"
    d.rectangle((11, 9, 28, 25), fill=rgb("blue", 1))
    tiny(d, 12, 11, "SHIP", rgb("amber", -1))
    tiny(d, 16, 18, "IT", rgb("amber", -1))
    return im


def tex_board():
    im = office_base(5)
    d = ImageDraw.Draw(im)
    d.rectangle((3, 6, 60, 47), fill=rgb("grey", 6))
    d.rectangle((4, 7, 59, 46), fill=rgb("grey", -1))
    d.rectangle((6, 47, 57, 49), fill=rgb("grey", 5))
    tiny(d, 7, 9, "GM", rgb("blue", 3))
    tiny(d, 7, 16, "WAGMI", rgb("green", 2))
    tiny(d, 7, 24, "FIX BUG", rgb("red", 3))
    tiny(d, 7, 32, "DEMO 9AM", rgb("red", 2))
    tiny(d, 7, 39, "0X0 SEGV", rgb("grey", 1))
    d.rectangle((38, 9, 55, 16), outline=rgb("blue", 2))    # a flow chart
    d.line((46, 17, 46, 22), fill=rgb("blue", 2))
    d.rectangle((38, 23, 55, 30), outline=rgb("blue", 2))
    d.line((44, 20, 46, 22), fill=rgb("blue", 2))
    d.line((48, 20, 46, 22), fill=rgb("blue", 2))
    tiny(d, 40, 11, "RUN", rgb("blue", 3))
    tiny(d, 40, 25, "OK?", rgb("blue", 3))
    d.rectangle((10, 48, 16, 49), fill=rgb("red", 3))  # markers on the tray
    d.rectangle((20, 48, 26, 49), fill=rgb("blue", 3))
    return im


def tex_door():
    im = Image.new("RGB", (TEX, TEX), rgb("steel", 3))
    d = ImageDraw.Draw(im)
    noise(im, (2, 2, 62, 62), [rgb("steel", 3), rgb("steel", 3), rgb("steel", 2)], 11, 0.3)
    d.rectangle((0, 0, 1, 63), fill=rgb("steel", 0))
    d.rectangle((62, 0, 63, 63), fill=rgb("steel", 0))
    d.line((2, 0, 2, 63), fill=rgb("steel", 5))
    d.rectangle((18, 7, 45, 23), fill=rgb("steel", 1))     # the window
    d.rectangle((20, 9, 43, 21), fill=rgb("blue", 0))
    d.line((22, 19, 31, 10), fill=rgb("blue", 2))
    d.line((26, 20, 34, 12), fill=rgb("blue", 1))
    for y in (29, 52):
        d.line((3, y, 60, y), fill=rgb("steel", 1))
        d.line((3, y + 1, 60, y + 1), fill=rgb("steel", 5))
    for y in range(35, 45):                               # hazard stripes
        for x in range(3, 61):
            d.point((x, y), fill=rgb("amber", -2) if ((x + y) // 4) % 2 == 0 else rgb("grey", 0))
    d.line((3, 34, 60, 34), fill=rgb("grey", 0))
    d.line((3, 45, 60, 45), fill=rgb("grey", 0))
    d.rectangle((52, 24, 56, 27), fill=rgb("steel", 0))   # the handle recess
    return im


def tex_locked():
    """The locked door: the door slab in red, with a keycard slot and a World-orb light."""
    im = tex_door()
    d = ImageDraw.Draw(im)
    for y in range(35, 45):
        for x in range(3, 61):
            d.point((x, y), fill=rgb("red", -2) if ((x + y) // 4) % 2 == 0 else rgb("grey", 0))
    d.rectangle((24, 47, 39, 58), fill=rgb("steel", 0))
    d.rectangle((25, 48, 38, 57), fill=rgb("steel", 2))
    d.ellipse((28, 49, 35, 56), fill=rgb("blue", 3))
    d.point((30, 51), fill=rgb("grey", -1))
    tiny(d, 17, 25, "KEYCARD", rgb("red", -1))
    return im


def shelf(full):
    im = Image.new("RGB", (TEX, TEX), rgb("brown", 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 63, 17), fill=rgb("steel", 1))
    sign = "green" if full else "grey"
    d.rectangle((4, 2, 59, 15), fill=rgb(sign, 1 if full else 2))
    d.rectangle((4, 2, 59, 15), outline=rgb(sign, 3 if full else 3))
    d.rectangle((9, 5, 11, 12), fill=rgb("grey", -1) if full else rgb("grey", 4))   # the health cross
    d.rectangle((7, 7, 13, 10), fill=rgb("grey", -1) if full else rgb("grey", 4))
    tiny(d, 18, 6, "ARKIV", rgb("grey", -1) if full else rgb("grey", 4))
    tiny(d, 40, 6, "+25", rgb("green", -1) if full else rgb("grey", 4))
    for x0 in (0, 59):
        d.rectangle((x0, 18, x0 + 4, 63), fill=rgb("brown", 3))
        d.line((x0, 18, x0, 63), fill=rgb("brown", 5))
    rnd = random.Random(4)
    for y in (36, 54):
        d.rectangle((5, y, 58, y + 2), fill=rgb("brown", 4))
        d.line((5, y, 58, y), fill=rgb("brown", 5))
        if not full:
            continue
        x = 7
        while x < 54:                                     # storage blocks and first-aid kits on the boards
            w = rnd.choice((6, 7, 8, 9))
            h = rnd.choice((9, 11, 13))
            if x + w > 57:
                break
            kit = rnd.random() < 0.4
            col = "grey" if kit else rnd.choice(("blue", "teal", "purple", "amber"))
            d.rectangle((x, y - h, x + w - 1, y - 1), fill=rgb(col, 4 if kit else 2))
            d.line((x, y - h, x + w - 1, y - h), fill=rgb(col, -1 if kit else 4))
            d.line((x + w - 1, y - h, x + w - 1, y - 1), fill=rgb(col, 2 if kit else 0))
            if kit:
                cx, cy = x + w // 2 - 1, y - h // 2 - 1
                d.rectangle((cx, cy - 2, cx + 1, cy + 2), fill=rgb("green", 3))
                d.rectangle((cx - 2, cy, cx + 3, cy + 1), fill=rgb("green", 3))
            x += w + 1
    return im


def orb_panel(done):
    im = office_base(9)
    d = ImageDraw.Draw(im)
    d.rectangle((8, 4, 55, 53), fill=rgb("steel", 1))
    d.rectangle((8, 4, 55, 53), outline=rgb("steel", 4))
    ring = "green" if done else "blue"
    cx, cy, r = 31.5, 23.5, 14
    for y in range(4, 54):
        for x in range(8, 56):
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy)
            if r - 0.5 < dist <= r + 1.5:
                d.point((x, y), fill=rgb(ring, -1 if dist < r + 0.5 else 2))
            elif dist <= r - 1.5:                          # the silver orb
                nx, ny = dx / r, dy / r
                nz = math.sqrt(max(0.0, 1 - nx * nx - ny * ny))
                light = max(0.0, -0.5 * nx - 0.6 * ny + 0.62 * nz)
                shade = 0.25 + 0.75 * light
                spec = max(0.0, light) ** 18
                v = min(1.0, shade + spec)
                d.point((x, y), fill=rgb("grey", int(round(v * 8))))
    d.rectangle((20, 42, 43, 44), fill=rgb("grey", 0))      # the card slot
    d.line((20, 45, 43, 45), fill=rgb("steel", 4))
    tiny(d, 16, 47, "VERIFIED" if done else "WORLD ID", rgb(ring, -1))
    return im


def tex_terminal():
    im = Image.new("RGB", (TEX, TEX), rgb("grey", 1))
    d = ImageDraw.Draw(im)
    d.rectangle((3, 3, 60, 42), fill=rgb("grey", 2))
    d.rectangle((6, 6, 57, 39), fill=rgb("blue", 0))
    for y in range(7, 40, 3):                             # scanlines
        d.line((6, y, 57, y), fill=rgb("blue", 1))
    cx, cy = 31.5, 18.5                                   # linked hexagons
    for ox in (-9, 0, 9):
        pts = [(cx + ox + 5.5 * math.cos(math.pi / 3 * k + math.pi / 6),
                cy + 5.5 * math.sin(math.pi / 3 * k + math.pi / 6)) for k in range(7)]
        d.line(pts, fill=rgb("blue", -1) if ox == 0 else rgb("blue", 3), width=1)
    tiny(d, 20, 29, "REBOOT", rgb("blue", -1))
    d.rectangle((6, 34, 57, 36), fill=rgb("blue", 1))
    d.rectangle((6, 34, 30, 36), fill=rgb("blue", 4))
    d.rectangle((4, 46, 59, 58), fill=rgb("grey", 3))      # the keyboard
    for y in range(48, 57, 3):
        for x in range(6, 58, 4):
            d.rectangle((x, y, x + 2, y + 1), fill=rgb("grey", 5))
    d.rectangle((50, 60, 53, 61), fill=rgb("red", -1))
    tiny(d, 8, 59, "BUILD", rgb("grey", 5))
    return im


TEXTURES = [  # index = the view's texture number, in CELL_* order from CELL_RACK (game.h)
    ("rack", tex_rack), ("cable", lambda: cable_wall(21)), ("office", tex_office), ("board", tex_board),
    ("door", tex_door), ("shelf", lambda: shelf(True)), ("shelf_empty", lambda: shelf(False)),
    ("reader", lambda: orb_panel(False)), ("reader_done", lambda: orb_panel(True)), ("terminal", tex_terminal),
    ("push", lambda: cable_wall(21, gap=True)), ("locked", tex_locked),
]


# ---- billboards --------------------------------------------------------------------------------------------------

def shrink(img, size):
    return img.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def bug_frames():
    names = ["walk1", "walk2", "attack", "hurt", "dead"]
    frames = {}
    for n in ("walk1", "walk2", "attack", "dead"):
        frames[n] = shrink(Image.open(os.path.join(RENDERS, "bug_%s.png" % n)), (TEX, TEX))
    hurt = frames["walk1"].copy()
    px = hurt.load()
    for y in range(TEX):
        for x in range(TEX):
            r, g, b, a = px[x, y]
            px[x, y] = (min(255, r // 2 + 150), min(255, g // 2 + 110), min(255, b // 2 + 110), a)
    frames["hurt"] = hurt
    return [(n, frames[n]) for n in names]


# ---- the HUD (240 x 32 on screen = 120 x 32 in the doubled bitmap) -------------------------------------------------

HUD_BAR = (12, 46, 10, 14)          # health bar inner: memory columns x0..x1, rows y0..y1 (rows of the HUD strip)
HUD_KEY = (54, 8)                   # key icon top-left (memory column, row), 8 x 16
HUD_RADAR = (98, 118, 2, 30)        # radar window: memory columns x0..x1 (exclusive), rows y0..y1 (exclusive)


def hud_image():
    im = Image.new("RGB", (240, 32), rgb("steel", 1))
    d = ImageDraw.Draw(im)
    d.line((0, 0, 239, 0), fill=rgb("steel", 5))
    d.line((0, 1, 239, 1), fill=rgb("steel", 3))
    d.line((0, 31, 239, 31), fill=rgb("steel", 0))
    for x in (100, 128, 190):
        d.line((x, 3, x, 29), fill=rgb("steel", 0))
        d.line((x + 1, 3, x + 1, 29), fill=rgb("steel", 3))
    # health: a cross and a bar frame (the view fills the bar)
    d.rectangle((6, 9, 17, 12), fill=rgb("red", -2))
    d.rectangle((10, 5, 13, 16), fill=rgb("red", -2))
    x0, x1, y0, y1 = HUD_BAR
    d.rectangle((x0 * 2 - 2, y0 - 2, x1 * 2 + 3, y1 + 2), fill=rgb("steel", 0))
    d.rectangle((x0 * 2 - 2, y0 - 2, x1 * 2 + 3, y1 + 2), outline=rgb("steel", 4))
    draw_text(im, 6, 21, "HP", rgb("steel", 5))
    # keycard slot frame (the view draws the card)
    kx, ky = HUD_KEY
    d.rectangle((kx * 2 - 3, ky - 3, kx * 2 + 18, ky + 18), outline=rgb("steel", 4))
    # bugs icon (a tiny bug), labels
    d.ellipse((134, 6, 145, 16), fill=rgb("purple", 2))
    d.ellipse((136, 3, 143, 8), fill=rgb("green", 1))
    d.point((138, 5), fill=rgb("red", -1))
    d.point((141, 5), fill=rgb("red", -1))
    for y in (8, 11, 14):
        d.line((131, y, 134, y - 1), fill=rgb("grey", 2))
        d.line((145, y - 1, 148, y), fill=rgb("grey", 2))
    x0r, x1r, y0r, y1r = HUD_RADAR
    d.rectangle((x0r * 2 - 2, y0r - 2, x1r * 2 + 1, y1r + 1), outline=rgb("steel", 4))
    return im


def key_icons():
    """8 x 16 memory pixels (16 x 16 on screen): the keycard slot empty and holding the World ID card."""
    off = Image.new("RGB", (16, 16), rgb("steel", 1))
    d = ImageDraw.Draw(off)
    d.rectangle((2, 3, 13, 12), outline=rgb("steel", 3))
    on = Image.new("RGB", (16, 16), rgb("steel", 1))
    d = ImageDraw.Draw(on)
    d.rectangle((1, 2, 14, 13), fill=rgb("grey", -2))
    d.rectangle((1, 2, 14, 4), fill=rgb("blue", 3))
    d.ellipse((4, 6, 9, 11), fill=rgb("grey", 5))
    d.point((5, 7), fill=rgb("grey", -1))
    d.line((10, 8, 13, 8), fill=rgb("grey", 3))
    d.line((10, 10, 12, 10), fill=rgb("grey", 3))
    return [halve(off), halve(on)]


def halve(img):
    """Screen-resolution image -> the doubled bitmap's memory resolution (half the width)."""
    w, h = img.size
    return img.resize((w // 2, h), Image.BOX)


# ---- floor and ceiling ------------------------------------------------------------------------------------------

def background_column():
    """128 rows of the view: the ceiling darkening toward the horizon, then the floor brightening toward the viewer.
    Full palette indices (level already applied)."""
    out = []
    for y in range(128):
        if y < 64:
            t = y / 63                                   # 0 at the top, 1 at the horizon
            level = min(3, int(t * 4.2))
            base = C("steel", 1) if y < 40 else C("steel", 0)
        else:
            t = (y - 64) / 63                            # 0 at the horizon, 1 at the bottom
            level = max(0, 3 - int(t * 4.2))
            base = C("grey", 2) if (y // 2) % 2 == 0 else C("grey", 1)
        out.append(level * 64 + base)
    return out


# ---- the cards (240 x 160, their own palette) -------------------------------------------------------------------

def rack_backdrop(seed, h=160):
    rnd = random.Random(seed)
    im = Image.new("RGB", (240, h), (8, 10, 16))
    d = ImageDraw.Draw(im)
    for y in range(h):                                   # a cold glow from the floor
        v = int(10 + 18 * (y / h) ** 2)
        d.line((0, y, 239, y), fill=(v // 2, v, v + 6))
    for k, x0 in enumerate(range(-6, 240, 34)):          # rows of racks in perspective-free silhouette
        top = 26 + (k % 3) * 6
        d.rectangle((x0, top, x0 + 28, h - 8), fill=(16, 20, 30))
        d.rectangle((x0 + 1, top + 1, x0 + 27, h - 9), outline=(34, 42, 58))
        for y in range(top + 6, h - 12, 6):
            d.line((x0 + 3, y, x0 + 25, y), fill=(24, 30, 44))
            if rnd.random() < 0.8:
                col = rnd.choice([(80, 255, 120), (80, 255, 120), (255, 200, 60), (90, 170, 255)])
                d.point((x0 + 22, y + 2), fill=col)
                if rnd.random() < 0.5:
                    d.point((x0 + 19, y + 2), fill=col)
    return im


def glitch_text(im, x, y, s, scale):
    """Big text with a red / cyan channel split and a few sliced rows."""
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw_text(layer, x - 2, y, s, (255, 40, 60, 255), scale)
    draw_text(layer, x + 2, y + 1, s, (40, 230, 255, 255), scale)
    draw_text(layer, x, y, s, (245, 245, 250, 255), scale, shadow=(30, 30, 40, 255))
    rnd = random.Random(3)
    for _ in range(5):                                   # slice and shift a few rows
        sy = rnd.randrange(y, y + 8 * scale - 2)
        hgt = rnd.randrange(1, 3)
        dx = rnd.choice((-4, -3, 3, 4))
        band = layer.crop((0, sy, im.size[0], sy + hgt))
        layer.paste((0, 0, 0, 0), (0, sy, im.size[0], sy + hgt))
        layer.paste(band, (dx, sy))
    im.paste(layer, (0, 0), layer)


def centred(im, y, s, color, scale=1, shadow=None):
    fits(s, scale=scale)
    draw_text(im, (240 - text_width(s, scale)) // 2, y, s, color, scale, shadow)


def title_card():
    im = rack_backdrop(1)
    bug = Image.open(os.path.join(RENDERS, "bug_attack.png")).convert("RGBA").resize((112, 112), Image.LANCZOS)
    im.paste(bug, (64, 50), bug)
    glitch_text(im, (240 - text_width("SEGFAULT", 3)) // 2, 14, "SEGFAULT", 3)
    centred(im, 40, "(core dumped)", (150, 160, 180))
    shade = Image.new("RGBA", (240, 26), (0, 0, 0, 170))
    im.paste(shade, (0, 134), shade)
    centred(im, 138, "The night before demo day,", (200, 210, 220))
    centred(im, 148, "the build server is full of bugs.", (200, 210, 220))
    return im


CARD_TEXT_W = 216                  # every line of card text fits this width (a 12 px margin each side)


def fits(s, width=CARD_TEXT_W, scale=1):
    w = text_width(s, scale)
    if w > width:
        raise SystemExit("art: card text %r is %d px wide (limit %d)" % (s, w, width))
    return w


def howto_card():
    im = rack_backdrop(2)
    shade = Image.new("RGBA", (232, 152), (4, 6, 12, 215))
    im.paste(shade, (4, 4), shade)
    d = ImageDraw.Draw(im)
    d.rectangle((4, 4, 235, 155), outline=(60, 80, 110))
    centred(im, 8, "HOW TO DEBUG", (120, 255, 150))
    white, gold, blue = (220, 225, 235), (255, 220, 110), (150, 230, 255)
    y = 22
    for line in ("Squash every bug with the blaster.", "The keycard is at the World orb reader.",
                 "It opens the locked wing and the", "Chainlink terminal: the exit."):
        fits(line)
        draw_text(im, 12, y, line, white)
        y += 10
    y += 6
    for left, right in (("UP/DOWN  walk", "L/R  strafe"), ("LEFT/RIGHT  turn", "A  fire (hold)"),
                        ("B  doors, panels", "START  pause")):
        fits(left, 104)
        fits(right, 100)
        draw_text(im, 12, y, left, gold)
        draw_text(im, 128, y, right, gold)
        y += 10
    y += 6
    for line in ("Arkiv shelves heal +25 (B).", "Not every wall is a wall."):
        fits(line)
        draw_text(im, 12, y, line, blue)
        y += 10
    centred(im, 136, "Trophies: all bugs, no damage,", (180, 150, 255))
    centred(im, 145, "under 3:00, the secret room", (180, 150, 255))
    return im


def results_card():
    im = rack_backdrop(3)
    shade = Image.new("RGBA", (216, 140), (2, 10, 8, 225))
    im.paste(shade, (12, 10), shade)
    d = ImageDraw.Draw(im)
    d.rectangle((12, 10, 227, 149), outline=(60, 160, 100))
    d.rectangle((14, 12, 225, 22), fill=(20, 60, 40))
    fits("build_server:~$ ./report", 200)
    draw_text(im, 18, 13, "build_server:~$ ./report", (140, 255, 170))
    return im


def cards():
    imgs = [title_card(), howto_card(), results_card()]
    stack = Image.new("RGB", (240, 480))
    for i, im in enumerate(imgs):
        stack.paste(im.convert("RGB"), (0, i * 160))
    q = stack.convert("RGB").quantize(255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = q.getpalette()[:255 * 3]
    pal = [(0, 0, 0)] + [q15(tuple(raw[i:i + 3])) for i in range(0, len(raw), 3)]
    pal += [(0, 0, 0)] * (256 - len(pal))
    data = [v + 1 for v in q.tobytes()]
    return imgs, pal, [data[i * 38400:(i + 1) * 38400] for i in range(3)]


# ---- Butano sprites ---------------------------------------------------------------------------------------------

def write_bmp(path, w, h, pixels, palette):
    row = (w + 3) & ~3
    data = bytearray()
    for y in range(h - 1, -1, -1):
        data += bytes(pixels[y * w:(y + 1) * w]) + b"\0" * (row - w)
    n = len(palette)
    head = struct.pack("<2sIHHI", b"BM", 14 + 40 + 4 * n + len(data), 0, 0, 14 + 40 + 4 * n)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 8, 0, len(data), 2835, 2835, n, n)
    pal = b"".join(struct.pack("<BBBB", c[2], c[1], c[0], 0) for c in palette)
    with open(path, "wb") as f:
        f.write(head + info + pal + data)


def write_sprite(name, frames, height, colors):
    """frames: RGBA images of one size; quantized together to 15 colours + transparent index 0."""
    w, h = frames[0].size
    sheet = Image.new("RGBA", (w, h * len(frames)))
    for i, fr in enumerate(frames):
        sheet.paste(fr, (0, i * h))
    alpha = sheet.getchannel("A")
    flat = Image.new("RGB", sheet.size, (0, 0, 0))
    flat.paste(sheet, (0, 0), sheet)
    q = flat.quantize(colors - 1, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = q.getpalette()[:(colors - 1) * 3]
    pal = [(255, 0, 255)] + [q15(tuple(raw[i:i + 3])) for i in range(0, len(raw), 3)]
    pal += [(0, 0, 0)] * (16 - len(pal))
    idx = q.tobytes()
    a = alpha.tobytes()
    pixels = [idx[i] + 1 if a[i] >= 128 else 0 for i in range(len(idx))]
    write_bmp(os.path.join(GRAPHICS, name + ".bmp"), w, h * len(frames), pixels, pal)
    with open(os.path.join(GRAPHICS, name + ".json"), "w", newline="\n") as f:
        f.write('{\n    "type": "sprite",\n    "height": %d,\n    "bpp_mode": "bpp_4",\n    "colors_count": 16\n}\n'
                % height)
    return indices_to_image(pixels, w, h * len(frames), pal)


def blaster_frames():
    out = []
    for pose in ("idle", "fire"):
        im = Image.open(os.path.join(RENDERS, "blaster_%s.png" % pose)).convert("RGBA")
        crop = im.crop((20, 32, 116, 128))
        crop = shrink(crop, (64, 64))
        if pose == "fire":                               # a bright muzzle flash burst above the barrel
            d = ImageDraw.Draw(crop)
            cx, cy = 34, 12
            for k in range(8):
                a = k * math.pi / 4
                d.line((cx, cy, cx + 10 * math.cos(a), cy + 7 * math.sin(a)), fill=(200, 255, 150, 255), width=2)
            d.ellipse((cx - 6, cy - 5, cx + 6, cy + 5), fill=(240, 255, 200, 255))
            d.ellipse((cx - 3, cy - 2, cx + 3, cy + 2), fill=(255, 255, 255, 255))
        out.append(crop)
    return out


def phantom_frame():
    """The ghost's world marker: the bug's silhouette as a cyan hologram, 32 x 32."""
    src = shrink(Image.open(os.path.join(RENDERS, "bug_walk1.png")), (32, 32))
    px = src.load()
    out = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    po = out.load()
    for y in range(32):
        for x in range(32):
            r, g, b, a = px[x, y]
            if a >= 128:
                v = (r + g + b) / 765
                scan = 0.75 if y % 3 == 0 else 1.0
                po[x, y] = (int((60 + 120 * v) * scan), int((200 + 55 * v) * scan), int((220 + 35 * v) * scan), 255)
    return out


def blip_frame():
    im = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((1, 1, 6, 6), fill=(80, 240, 255, 255))
    d.ellipse((3, 3, 4, 4), fill=(255, 255, 255, 255))
    return im


def crosshair_frame():
    im = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for (x, y) in ((3, 0), (3, 1), (3, 5), (3, 6), (0, 3), (1, 3), (5, 3), (6, 3)):
        d.point((x, y), fill=(140, 255, 160, 255))
    d.point((3, 3), fill=(255, 255, 255, 255))
    return im


# ---- output -----------------------------------------------------------------------------------------------------

def c_array(name, ctype, values, per_line=24):
    lines = []
    for i in range(0, len(values), per_line):
        lines.append("    " + ", ".join(str(v) for v in values[i:i + per_line]) + ",")
    return "const %s %s[%d] __attribute__((aligned(4))) = {\n%s\n};\n" % (ctype, name, len(values), "\n".join(lines))


def colmajor(idx, w, h):
    return [idx[y * w + x] for x in range(w) for y in range(h)]


def gba_colors(pal):
    return [(c[0] >> 3) | ((c[1] >> 3) << 5) | ((c[2] >> 3) << 10) for c in pal]


def main():
    for p in (PREVIEW, GENART, GRAPHICS):
        os.makedirs(p, exist_ok=True)
    errors = []
    pal = palette256()

    tex_imgs, tex_data = [], []
    for name, fn in TEXTURES:
        im = fn()
        assert im.size == (TEX, TEX)
        idx = to_indices(im, alpha=False)
        if 0 in idx:
            errors.append("texture %s uses index 0" % name)
        tex_imgs.append(indices_to_image(idx, TEX, TEX))
        tex_data += colmajor(idx, TEX, TEX)

    bug_imgs, bug_data = [], []
    for name, im in bug_frames():
        idx = to_indices(im)
        bug_imgs.append(indices_to_image(idx, TEX, TEX))
        bug_data += colmajor(idx, TEX, TEX)

    hud = halve(hud_image())
    hud_idx = to_indices(hud, alpha=False)
    keys = [to_indices(k, alpha=False) for k in key_icons()]
    bgcol = background_column()
    card_imgs, card_pal, card_data = cards()

    # sprites
    sprite_previews = [
        write_sprite("blaster", blaster_frames(), 64, 16),
        write_sprite("phantom", [phantom_frame()], 32, 16),
        write_sprite("blip", [blip_frame()], 8, 16),
        write_sprite("crosshair", [crosshair_frame()], 8, 16),
    ]
    for f in os.listdir(GRAPHICS):
        if f.startswith("dot."):
            os.remove(os.path.join(GRAPHICS, f))

    # limits
    if len(set(pal)) < 200:
        errors.append("the in-game palette collapsed to %d distinct colours" % len(set(pal)))
    if errors:
        sys.exit("art: " + "; ".join(errors))

    h = ["/* Generated by tools/art/build_art.py; do not edit. The view's art: see that script for the layout. */",
         "#ifndef SEGF_ART_H", "#define SEGF_ART_H", "#include <stdint.h>", "#ifdef __cplusplus", 'extern "C" {',
         "#endif", "",
         "#define SEGF_TEX_SIZE 64",
         "#define SEGF_TEX_COUNT %d" % len(TEXTURES),
         "#define SEGF_BUG_FRAMES 5            /* walk1, walk2, attack, hurt, dead */",
         "#define SEGF_HUD_W 120", "#define SEGF_HUD_H 32",
         "#define SEGF_HUD_BAR_X0 %d" % HUD_BAR[0], "#define SEGF_HUD_BAR_X1 %d" % HUD_BAR[1],
         "#define SEGF_HUD_BAR_Y0 %d" % HUD_BAR[2], "#define SEGF_HUD_BAR_Y1 %d" % HUD_BAR[3],
         "#define SEGF_HUD_KEY_X %d" % HUD_KEY[0], "#define SEGF_HUD_KEY_Y %d" % HUD_KEY[1],
         "#define SEGF_RADAR_X0 %d" % HUD_RADAR[0], "#define SEGF_RADAR_X1 %d" % HUD_RADAR[1],
         "#define SEGF_RADAR_Y0 %d" % HUD_RADAR[2], "#define SEGF_RADAR_Y1 %d" % HUD_RADAR[3],
         ]
    colours = {"GREEN": C("green", -2), "AMBER": C("amber", -2), "RED": C("red", -2), "BAR_BG": C("steel", 0),
               "RADAR_BG": C("grey", 0), "RADAR_WALL": C("steel", 3), "RADAR_DOOR": C("amber", 2),
               "RADAR_OPEN": C("amber", 0), "RADAR_ME": C("grey", -1), "RADAR_BUG": C("red", -1),
               "RADAR_SHELF": C("green", 3), "RADAR_READER": C("blue", -1), "RADAR_EXIT": C("teal", -1),
               "RADAR_DIR": C("green", -1), "WHITE": C("grey", -1)}
    for k, v in colours.items():
        h.append("#define SEGF_C_%s %d" % (k, v))
    h += ["",
          "extern const uint16_t segf_palette[256];      /* in-game: level * 64 + base */",
          "extern const uint16_t segf_card_palette[256]; /* the cards */",
          "extern const uint8_t segf_textures[%d];       /* [texture][x][y] */" % len(tex_data),
          "extern const uint8_t segf_bugs[%d];           /* [frame][x][y], 0 transparent */" % len(bug_data),
          "extern const uint8_t segf_hud[%d];            /* [x][y], 120 x 32 memory pixels */" % (120 * 32),
          "extern const uint8_t segf_key_icons[2][%d];   /* [off, on][x][y], 8 x 16 */" % (8 * 16),
          "extern const uint8_t segf_bg_column[128];      /* ceiling and floor, full indices */",
          "extern const uint8_t segf_cards[3][%d];       /* title, how-to, results: [y][x] 240 x 160 */" % 38400,
          "", "#ifdef __cplusplus", "}", "#endif", "#endif", ""]
    with open(os.path.join(GENART, "segf_art.h"), "w", newline="\n") as f:
        f.write("\n".join(h))
    body = ["/* Generated by tools/art/build_art.py; do not edit. */", '#include "segf_art.h"', ""]
    body.append(c_array("segf_palette", "uint16_t", gba_colors(pal), 12))
    body.append(c_array("segf_card_palette", "uint16_t", gba_colors(card_pal), 12))
    body.append(c_array("segf_textures", "uint8_t", tex_data, 32))
    body.append(c_array("segf_bugs", "uint8_t", bug_data, 32))
    body.append(c_array("segf_hud", "uint8_t", colmajor(hud_idx, 120, 32), 32))
    body.append("const uint8_t segf_key_icons[2][%d] __attribute__((aligned(4))) = {\n" % (8 * 16) + "".join(
        "    {" + ", ".join(str(v) for v in colmajor(k, 8, 16)) + "},\n" for k in keys) + "};\n")
    body.append(c_array("segf_bg_column", "uint8_t", bgcol, 32))
    body.append("const uint8_t segf_cards[3][38400] __attribute__((aligned(4))) = {\n" + "".join(
        "    {" + ",".join(str(v) for v in cd) + "},\n" for cd in card_data) + "};\n")
    with open(os.path.join(GENART, "segf_art.c"), "w", newline="\n") as f:
        f.write("\n".join(body))

    # previews
    sheet = Image.new("RGB", (TEX * len(tex_imgs), TEX * 2), (0, 0, 0))
    for i, im in enumerate(tex_imgs):
        sheet.paste(im, (i * TEX, 0))
    for i, im in enumerate(bug_imgs):
        sheet.paste(im, (i * TEX, TEX))
    sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST).save(os.path.join(PREVIEW, "textures.png"))
    hud_prev = indices_to_image(hud_idx, 120, 32).resize((480, 64), Image.NEAREST)
    hud_prev.save(os.path.join(PREVIEW, "hud.png"))
    for name, cd in zip(("title", "howto", "results"), card_data):
        im = Image.new("RGB", (240, 160))
        im.putdata([card_pal[v] for v in cd])
        im.resize((480, 320), Image.NEAREST).save(os.path.join(PREVIEW, "card_%s.png" % name))
    sp = Image.new("RGB", (64 * 4, 128), (40, 40, 60))
    x = 0
    for im in sprite_previews:
        sp.paste(im, (x, 0))
        x += 64
    sp.resize((sp.width * 3, sp.height * 3), Image.NEAREST).save(os.path.join(PREVIEW, "sprites.png"))
    print("art ok: %d textures, %d bug frames, palette %d colours" % (len(TEXTURES), len(bug_imgs), len(set(pal))))


if __name__ == "__main__":
    main()
