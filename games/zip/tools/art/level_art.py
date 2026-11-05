"""Draws ZIP's level background (terrain + decor) from the level grid, for tools/level/build_level.py.

The terrain is drawn from the same height masks the rules collide with (tools/level/tiles.py), so what you see is
what you stand on: a riveted metal cap along every surface (slopes included), circuit-board fill below, outlined
walls and ceilings. Decor (server racks, warning lamps, the laptop, the loop ring, the Chainlink checkered finish
and the demo-day screen) is drawn on top in its own palette banks. Kenney CC0 tiles (Pixel Platformer and its
Industrial expansion) are used for the lamp beacon and the sign; the rest is drawn here."""
import math
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(GAME, "tools", "level"))
import tiles as TL  # noqa: E402

KENNEY = os.path.join(GAME, "art", "kenney")

# Palette banks of the level BG (index 0 of each is transparent: the hall shows through).
TERRAIN = [(0, 0, 0), (16, 20, 40), (64, 72, 96), (112, 120, 144), (168, 176, 192), (224, 232, 240),
           (16, 32, 56), (24, 48, 80), (40, 72, 112), (0, 96, 112), (0, 176, 192), (136, 240, 240),
           (224, 176, 56), (248, 200, 40), (240, 72, 72), (72, 232, 120)]
DECOR = [(0, 0, 0), (16, 20, 40), (32, 36, 56), (56, 64, 88), (96, 104, 128), (160, 168, 184), (240, 240, 248),
         (0, 200, 232), (144, 240, 255), (40, 96, 200), (216, 72, 200), (104, 56, 160), (248, 136, 40),
         (72, 232, 120), (240, 72, 72), (248, 216, 72)]
FINISH = [(0, 0, 0), (16, 20, 40), (40, 90, 226), (120, 160, 248), (240, 240, 248), (160, 168, 184),
          (32, 36, 56), (56, 64, 88), (8, 12, 28), (0, 200, 232), (248, 216, 72), (216, 72, 200), (72, 232, 120),
          (96, 104, 128), (24, 56, 150), (200, 216, 255)]
BANKS = [TERRAIN, DECOR, FINISH]

# the circuit fill: a 16 x 16 pattern (world aligned) of traces and vias
CIRCUIT = [
    "................",
    ".===........o...",
    "...=........=...",
    "...=====....=...",
    ".......=....=...",
    ".......O....====",
    "................",
    "..o.............",
    "..=.......O=====",
    "..=.......=.....",
    "..====....=.....",
    ".....=....=.....",
    ".....O....O.....",
    "................",
    "=====.......o...",
    "............=...",
]


def terrain_colour(depth, x, y, style):
    """The colour of a solid pixel `depth` pixels below its column's surface (0 = the surface pixel)."""
    t = TERRAIN
    if depth == 0:
        return t[1]
    if depth <= 5:
        band = {1: 5, 2: 4, 3: 4, 4: 3, 5: 2}[depth]
        if x % 16 in (5, 6) and depth in (2, 3):
            return t[1] if depth == 3 else t[5]              # a rivet
        if style == "switch" and depth in (2, 3) and x % 8 in (2, 3):
            return t[15] if (x // 8) % 3 else t[13]          # switch port LEDs along the cap
        return t[band]
    if depth == 6:
        return t[1]
    if style == "switch":
        # a network switch face: rows of ports
        yy, xx = y % 16, x % 16
        if yy in (4, 5, 6, 7) and xx % 4 != 3:
            return t[1] if yy in (5, 6) and xx % 4 in (1, 2) else t[3]
        if yy == 10 and xx % 4 == 1:
            return t[15] if (x // 4 + y // 16) % 3 else t[14]
        return t[7] if yy < 12 else t[6]
    ch = CIRCUIT[y % 16][x % 16]
    deep = depth > 40
    if ch == "=":
        return t[9]
    if ch == "O":
        return t[12] if not deep else t[9]
    if ch == "o":
        return t[10]
    return t[6] if deep else t[7]


def render_terrain(grid, styles):
    """grid: rows of tile ids (tiles.TYPES); styles: rows of 'plain'/'switch'. Returns an RGBA image."""
    h, w = len(grid), len(grid[0])
    W, H = w * 16, h * 16
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = img.load()

    def solid(x, y):
        if x < 0 or x >= W or y < 0:
            return False
        if y >= H:
            return True
        tid = grid[y // 16][x // 16]
        return tid != 0 and TL.solid_px(tid, x % 16, y % 16)

    for x in range(W):
        depth = None
        for y in range(H):
            if not solid(x, y):
                depth = None
                continue
            depth = 0 if depth is None else depth + 1
            style = styles[y // 16][x // 16]
            c = terrain_colour(depth, x, y, style)
            # walls: outline the exposed side, a metal edge inside it
            if depth > 5:
                if not solid(x - 1, y) or not solid(x + 1, y):
                    c = TERRAIN[1]
                elif not solid(x - 2, y) or not solid(x + 2, y):
                    c = TERRAIN[3]
                elif not solid(x, y + 1):
                    c = TERRAIN[1]
                elif not solid(x, y + 2):
                    c = TERRAIN[2]
            px[x, y] = c + (255,)
    return img


def rgba(c):
    return tuple(c[:3]) + (255,)


def kenney(sheet, col, row, size=18):
    im = Image.open(os.path.join(KENNEY, sheet)).convert("RGBA")
    t = im.crop((col * size, row * size, col * size + size, row * size + size))
    return t.crop(t.getbbox())


# ---- decor (each returns an RGBA image; build_level places it with its bottom-left at a tile's bottom-left) --------

def deco_rack():
    """An Arkiv server rack (decor), 16 x 32."""
    c = DECOR
    img = Image.new("RGBA", (16, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 15, 31], fill=rgba(c[2]), outline=rgba(c[1]))
    d.line([1, 1, 14, 1], fill=rgba(c[4]))
    for y in range(4, 28, 4):
        d.rectangle([2, y, 13, y + 2], fill=rgba(c[3]), outline=rgba(c[1]))
        d.point((3, y + 1), fill=rgba(c[13] if y % 8 else c[7]))
        d.line([6, y + 1, 11, y + 1], fill=rgba(c[5]))
    d.line([1, 29, 14, 29], fill=rgba(c[11]))
    d.line([1, 30, 14, 30], fill=rgba(c[10]))
    return img


def deco_lamp():
    """A warning lamp on a post (Kenney Industrial beacon on top), 16 x 32."""
    img = Image.new("RGBA", (16, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = DECOR
    d.rectangle([6, 10, 9, 31], fill=rgba(c[3]), outline=rgba(c[1]))
    d.rectangle([3, 28, 12, 31], fill=rgba(c[4]), outline=rgba(c[1]))
    beacon = kenney("pixel-platformer-industrial-expansion/tilemap_packed.png", 0, 4)   # the red beacon
    img.alpha_composite(beacon, ((16 - beacon.width) // 2, max(0, 11 - beacon.height)))
    return img


def deco_sign():
    """A green status sign on a post (Kenney Industrial), cropped to its opaque box."""
    return kenney("pixel-platformer-industrial-expansion/tilemap_packed.png", 9, 4)


def deco_laptop():
    """The start: an open laptop (96 x 64) whose screen shows the packet leaving."""
    c = DECOR
    img = Image.new("RGBA", (96, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(4, 52), (92, 52), (95, 63), (0, 63)], fill=rgba(c[4]), outline=rgba(c[1]))
    d.line([6, 54, 90, 54], fill=rgba(c[5]))
    for x in range(10, 86, 6):
        d.line([x, 57, x + 3, 57], fill=rgba(c[3]))
        d.line([x + 1, 60, x + 4, 60], fill=rgba(c[3]))
    d.rectangle([10, 2, 85, 51], fill=rgba(c[3]), outline=rgba(c[1]))
    d.rectangle([14, 6, 81, 47], fill=rgba(c[1]))
    for i, y in enumerate(range(9, 44, 5)):                       # code lines
        ln = (40, 28, 52, 20, 44, 32, 24)[i % 7]
        d.line([18, y, 18 + ln, y], fill=rgba(c[7] if i % 3 else c[10]))
        d.line([18 + ln + 3, y, 18 + ln + 8, y], fill=rgba(c[13]))
    d.rectangle([62, 30, 75, 41], fill=rgba(c[7]), outline=rgba(c[8]))  # the packet icon on screen
    d.line([64, 33, 73, 33], fill=rgba(c[8]))
    d.point((47, 4), fill=rgba(c[13]))
    return img


def deco_screen():
    """The demo-day screen behind the finish, 128 x 96: a stage screen on a truss."""
    c = FINISH
    img = Image.new("RGBA", (128, 96), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for x in (10, 114):
        d.rectangle([x, 8, x + 3, 95], fill=rgba(c[13]), outline=rgba(c[1]))
        for y in range(12, 92, 8):
            d.line([x, y, x + 3, y + 4], fill=rgba(c[7]))
    d.rectangle([0, 0, 127, 63], fill=rgba(c[6]), outline=rgba(c[1]))
    d.rectangle([4, 4, 123, 59], fill=rgba(c[8]))
    # DEMO DAY in 3x5 blocks
    font = {"D": ["##.", "#.#", "#.#", "#.#", "##."], "E": ["###", "#..", "##.", "#..", "###"],
            "M": ["#.#", "###", "###", "#.#", "#.#"], "O": ["###", "#.#", "#.#", "#.#", "###"],
            "A": ["###", "#.#", "###", "#.#", "#.#"], "Y": ["#.#", "#.#", "###", ".#.", ".#."], " ": ["..."] * 5}
    x = 14
    for ch in "DEMO DAY":
        for r, line in enumerate(font[ch]):
            for k, v in enumerate(line):
                if v == "#":
                    d.rectangle([x + k * 3, 14 + r * 3, x + k * 3 + 2, 14 + r * 3 + 2], fill=rgba(c[4]))
        x += 13
    d.line([14, 34, 113, 34], fill=rgba(c[2]))
    for i in range(6):                                              # a bar chart
        hgt = (6, 10, 8, 14, 12, 18)[i]
        d.rectangle([20 + i * 14, 54 - hgt, 28 + i * 14, 54], fill=rgba(c[9] if i % 2 else c[3]))
    return img


def deco_finish(height):
    """The Chainlink checkered finish arch, 48 wide and `height` tall (bottom on the floor): two posts and a blue
    and white checkered banner with a hexagon badge."""
    c = FINISH
    img = Image.new("RGBA", (48, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for x in (0, 40):
        d.rectangle([x, 16, x + 7, height - 1], fill=rgba(c[5]), outline=rgba(c[1]))
        for y in range(20, height, 8):
            d.rectangle([x + 2, y, x + 5, y + 3], fill=rgba(c[2] if (y // 8) % 2 else c[4]))
    d.rectangle([0, 0, 47, 15], fill=rgba(c[4]), outline=rgba(c[1]))
    for yy in range(2):
        for xx in range(0, 6):
            if (xx + yy) % 2 == 0:
                d.rectangle([1 + xx * 8, 1 + yy * 7, 8 + xx * 8, 7 + yy * 7], fill=rgba(c[2]))
    hexa = [(24, 3), (29, 5), (29, 10), (24, 12), (19, 10), (19, 5)]
    d.polygon(hexa, fill=rgba(c[2]), outline=rgba(c[4]))
    return img


def draw_loop_ring(img, cx, cy, rs, thick=10):
    """The loop: a metal ring whose inner edge is the path's surface (radius rs around (cx, cy)); only the part
    above the floor line (cy + rs) is drawn."""
    px = img.load()
    t = TERRAIN
    W, H = img.size
    r2o = (rs + thick) ** 2
    for y in range(cy - rs - thick, cy + rs):
        for x in range(cx - rs - thick, cx + rs + thick + 1):
            if not (0 <= x < W and 0 <= y < H):
                continue
            dx, dy = x - cx, y - cy
            d2 = dx * dx + dy * dy
            if d2 < rs * rs or d2 >= r2o:
                continue
            dist = math.isqrt(d2)
            k = dist - rs
            if k == 0 or k == thick - 1:
                col = t[1]
            elif k == 1:
                col = t[5]
            elif k in (2, 3):
                col = t[4]
            elif k in (4, 5):
                ang = math.atan2(dy, dx)
                col = t[10] if int((ang + math.pi) * 12 / math.pi) % 2 else t[3]
            else:
                col = t[2]
            px[x, y] = col + (255,)


def stamp(img, art, left, bottom):
    img.alpha_composite(art, (left, bottom - art.height))
