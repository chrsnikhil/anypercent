"""Rebound "Mainnet" full screens, drawn fresh: game over ("REKT", the sad bull) and the end screen ("MAINNET", the
bull's win face, USDC coins). Also the bull for the title, and a palette recolour for the DevEd splash.

A screen is designed as a 160x144 picture in which every 8x8 cell uses the colours of one palette (at most 6: the
loaders read 6); encode() turns it into the game's files: 2bpp tiles (deduplicated, at most 256), tile map,
attribute map (palette per cell) and palettes."""
import math
import os

from PIL import Image, ImageDraw, ImageFont

import mainnet

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
NAVY = (20, 22, 43)
LILAC, ETH, INDIGO, WHITE = (192, 203, 246), (98, 126, 234), (69, 74, 117), (255, 255, 255)
BULL = [NAVY, (40, 20, 12), (176, 96, 40), (250, 232, 196)]
USDC = [NAVY, (10, 26, 58), (39, 117, 202), WHITE]


# --- the encoder ---------------------------------------------------------------------------------------------------

def pal_bytes(pals):
    out = bytearray()
    for p in pals:
        for r, g, b in p:
            v = (r >> 3) | (g >> 3) << 5 | (b >> 3) << 10
            out += bytes((v & 0xFF, v >> 8))
    return bytes(out)


def encode(img, pals):
    """img: 160x144 RGB using only palette colours, each cell within one palette. Returns (tiles 2bpp, map, attr)."""
    import gbgfx
    px = img.load()
    tiles, index, tmap, attr = [], {}, bytearray(), bytearray()
    for cy in range(18):
        for cx in range(20):
            cell = [px[cx * 8 + x, cy * 8 + y] for y in range(8) for x in range(8)]
            fits = [p for p, cols in enumerate(pals) if all(c in cols for c in cell)]
            if not fits:
                raise ValueError(f"cell {cx},{cy} has colours {sorted(set(cell))} that fit no palette")
            p = fits[0]
            t = tuple(pals[p].index(c) for c in cell)
            if t not in index:
                index[t] = len(tiles)
                tiles.append([list(t[y * 8:y * 8 + 8]) for y in range(8)])
            tmap.append(index[t])
            attr.append(p)
    if len(tiles) > 256:
        raise ValueError(f"{len(tiles)} tiles, the screen holds 256")
    return b"".join(gbgfx.tile_to_2bpp(t) for t in tiles), bytes(tmap), bytes(attr)


# --- a 5x7 pixel font (capitals, digits, a few marks) -----------------------------------------------------------

GLYPHS = {
    "A": ".###.#...##...#######...##...##...#", "B": "####.#...#####.#...##...##...#####.",
    "C": ".###.#...##....#....#....#...#.###.", "D": "####.#...##...##...##...##...#####.",
    "E": "######....####.#....#....#....#####", "F": "######....####.#....#....#....#....",
    "G": ".###.#...##....#.####...##...#.####", "H": "#...##...#######...##...##...##...#",
    "I": ".###...#....#....#....#....#...###.", "K": "#...##..#.#.#..##...#.#..#..#.#...#",
    "L": "#....#....#....#....#....#....#####", "M": "#...###.###.#.##...##...##...##...#",
    "N": "#...###..##.#.##..###...##...##...#", "O": ".###.#...##...##...##...##...#.###.",
    "P": "####.#...##...#####.#....#....#....", "R": "####.#...##...#####.#.#..#..#.#...#",
    "S": ".#####....#.....###.....#....#####.", "T": "#####..#....#....#....#....#....#..",
    "U": "#...##...##...##...##...##...#.###.", "W": "#...##...##...##.#.##.#.##.#.#.#.#.",
    "Y": "#...##...#.#.#...#....#....#....#..", "G2": "", " ": "." * 35,
    "!": "..#....#....#....#....#.........#..", "'": "..#....#.........................",
    "%": "##..###..#...#...#...#...#..###..##", "3": "####.....#...#...##......##...#.###.",
}
GLYPHS = {k: v for k, v in GLYPHS.items() if len(v) == 35}


def text(draw, x, y, s, colour, scale=1, spacing=1):
    """Pixel text, left edge x, top y. Returns the width drawn."""
    cx = x
    for ch in s.upper():
        g = GLYPHS.get(ch, GLYPHS[" "])
        for i, c in enumerate(g):
            if c == "#":
                gx, gy = cx + (i % 5) * scale, y + (i // 5) * scale
                draw.rectangle((gx, gy, gx + scale - 1, gy + scale - 1), fill=colour)
        cx += (5 + spacing) * scale
    return cx - x - spacing * scale


def text_width(s, scale=1, spacing=1):
    return len(s) * (5 + spacing) * scale - spacing * scale


def centred(draw, y, s, colour, scale=1, shadow=None):
    w = text_width(s, scale)
    x = (160 - w) // 2
    if shadow:
        text(draw, x + scale, y + scale, s, shadow, scale)
    text(draw, x, y, s, colour, scale)


def snap(v):
    return (v // 8) * 8


# --- the bull, big --------------------------------------------------------------------------------------------

def bull_grid(src, frame):
    """A player frame from the source PNGs (GFX/Player/<frame>.png) as the bull: 0 clear .. 3 cream."""
    im = Image.open(os.path.join(src, "GFX", "Player", frame + ".png")).convert("RGB")
    lut = {(0, 0, 0): 1, (255, 255, 255): 3, (0, 139, 255): 2, (0, 116, 224): 2}
    g = [[lut.get(im.getpixel((x, y)), 0) for x in range(16)] for y in range(16)]
    return mainnet.bull(g)


def paste_bull(img, grid, x0, y0, scale, pal=BULL):
    d = ImageDraw.Draw(img)
    for y in range(16):
        for x in range(16):
            v = grid[y][x]
            if v:
                d.rectangle((x0 + x * scale, y0 + y * scale, x0 + x * scale + scale - 1, y0 + y * scale + scale - 1),
                            fill=pal[v])


def big_text(img, cx, cy, s, size, colour, shadow):
    """Bold capitals from a TrueType face, thresholded to pixels, with a 2 px drop shadow."""
    m = Image.new("L", (160, 60), 0)
    ImageDraw.Draw(m).text((80, 30), s, font=ImageFont.truetype(FONT_BOLD, size), fill=255, anchor="mm")
    px = img.load()
    for dx, dy, c in ((2, 2, shadow), (0, 0, colour)):
        for y in range(60):
            for x in range(160):
                if m.getpixel((x, y)) > 120:
                    X, Y = cx - 80 + x + dx, cy - 30 + y + dy
                    if 0 <= X < 160 and 0 <= Y < 144:
                        px[X, Y] = c


# --- game over ------------------------------------------------------------------------------------------------

def game_over(src):
    """REKT in red, the sad bull, "THE BEAR GOT YOU"."""
    RED, DARKRED = (235, 64, 64), (110, 20, 40)
    pals = [[NAVY, RED, DARKRED, WHITE], BULL, [NAVY, LILAC, ETH, INDIGO]]
    img = Image.new("RGB", (160, 144), NAVY)
    d = ImageDraw.Draw(img)
    big_text(img, 80, 24, "REKT", 30, RED, DARKRED)
    paste_bull(img, bull_grid(src, "Sad"), 56, 56, 3)               # 48 px, cells 7..12 x 7..12: bull palette only
    centred(d, 112, "THE BEAR GOT YOU", LILAC)
    centred(d, 124, "PRESS START", ETH)
    return img, pals


# --- the end ---------------------------------------------------------------------------------------------------

def end_screen(src):
    """MAINNET, the bull's win face between two USDC coins, thanks."""
    pals = [[NAVY, LILAC, ETH, WHITE], BULL, USDC]
    img = Image.new("RGB", (160, 144), NAVY)
    d = ImageDraw.Draw(img)
    for i, (x, y) in enumerate(((12, 6), (140, 14), (30, 98), (128, 104), (8, 132), (150, 130), (70, 4), (100, 12))):
        d.point((x, y), fill=LILAC if i % 2 else ETH)               # a few stars
    big_text(img, 80, 26, "MAINNET", 22, LILAC, ETH)
    paste_bull(img, bull_grid(src, "Win"), 56, 48, 3)
    coin = mainnet.usdc_small()                                     # two USDC coins at 2x, in their own cells
    for x0 in (16, 112):
        for y in range(16):
            for x in range(16):
                v = coin[y][x]
                if v:
                    d.rectangle((x0 + x * 2, 56 + y * 2, x0 + x * 2 + 1, 56 + y * 2 + 1), fill=USDC[v])
    centred(d, 104, "YOU MADE IT", WHITE)
    centred(d, 118, "THANKS FOR PLAYING", LILAC)
    return img, pals


# --- recolours ----------------------------------------------------------------------------------------------------

SPLASH_MAP = {(24, 80, 136): (36, 38, 72), (24, 72, 112): (20, 22, 43), (8, 88, 160): (69, 74, 117),
              (0, 104, 200): (98, 126, 234), (200, 224, 248): LILAC}
TITLE_MAP = {(24, 48, 80): NAVY, (24, 56, 88): (36, 38, 72), (24, 80, 136): INDIGO, (0, 112, 224): ETH,
             (168, 192, 232): LILAC}


def recolour_pal(data, mapping):
    out = bytearray(data)
    for i in range(0, len(data), 2):
        v = data[i] | data[i + 1] << 8
        c = ((v & 31) * 8, ((v >> 5) & 31) * 8, ((v >> 10) & 31) * 8)
        if c in mapping:
            r, g, b = (k >> 3 for k in mapping[c])
            v = r | g << 5 | b << 10
            out[i], out[i + 1] = v & 0xFF, v >> 8
    return bytes(out)
