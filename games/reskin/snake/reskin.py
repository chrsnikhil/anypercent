"""Snake, web3 edition: "Ethereum night" (mockups.py, design A). Yvar de Goffau's GB Snake (WTFPL) already runs in
Game Boy Color with its own palettes, so this is new palettes, redrawn art and new words, with the game's code left
as it is apart from the palette data, two title strings and the bonus basket's palette number.

  palettes  0 the field and snake: navy, a dim star, ETH blue, a lilac outline
            1 the walls: purple and slate chain blocks       2 the USDC coin (and one HUD icon): blues and white
            3 the HUD, the food: navy, gold, grey-lilac, lilac 4 the Chainlink bonus: Chainlink blues
  art       grass is a faint star; walls are chain blocks (the brick hatch becomes a block grid); the apple is a gold
            ETH diamond; the bonus basket a USDC coin, the cherry a Chainlink hexagon
  words     GAME OVER reads REKT!, PAUSE reads HODL!, READY? reads WAGMI?; the title's GAMEBOY reads WEB3 EDITION

Reads the untouched source (games/src/snake), writes the working copy (games/work/snake): shapes.bmp (the art, as
the author keeps it) and shapes.bin (what the game includes), main.asm. Then `mod.py snake build`.

  python reskin.py [--preview DIR]"""
import math
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gbgfx                                      # noqa: E402

SRC = "/opt/arca-sandbox/games/src/snake"
WORK = "/opt/arca-sandbox/games/work/snake"

# --- the tile sheet: shapes.bmp is 16 x 24 tiles; tile k is the k-th 8x8 cell, row-major -------------------------
# BG codes use $8800 addressing: code c < $80 is tile 256 + c, c >= $80 is tile c. Sprite codes are tile c.

GREYS = [(255, 255, 255), (170, 170, 170), (85, 85, 85), (0, 0, 0)]   # colour index 0..3 as gbpack.py reads them


def bg(code):
    return 256 + code if code < 0x80 else code


def load_sheet():
    im = Image.open(os.path.join(SRC, "shapes.bmp")).convert("RGB")
    tiles = []
    for k in range(384):
        x0, y0 = (k % 16) * 8, (k // 16) * 8
        rows = []
        for y in range(8):
            row = []
            for x in range(8):
                v = sum(im.getpixel((x0 + x, y0 + y))) / 3                 # gbpack.py's thresholds
                row.append(3 if v < 64 else 2 if v < 128 else 1 if v < 192 else 0)
            rows.append(row)
        tiles.append(rows)
    return tiles


def save_sheet(tiles):
    im = Image.new("RGB", (128, 192))
    for k, rows in enumerate(tiles):
        for y, row in enumerate(rows):
            for x, c in enumerate(row):
                im.putpixel(((k % 16) * 8 + x, (k // 16) * 8 + y), GREYS[c])
    im.save(os.path.join(WORK, "shapes.bmp"))
    data = b"".join(gbgfx.tile_to_2bpp(t) for t in tiles)
    with open(os.path.join(WORK, "shapes.bin"), "wb") as f:
        f.write(data)
    return im


def raster(draw, size=8, S=8):
    """A size x size tile from a drawing function(draw, scale) in colour indexes 1..3 on 0."""
    big = Image.new("P", (size * S, size * S), 0)
    draw(ImageDraw.Draw(big), S)
    out = []
    for y in range(size):
        row = []
        for x in range(size):
            votes = {}
            for sy in range(S):
                for sx in range(S):
                    v = big.getpixel((x * S + sx, y * S + sy))
                    votes[v] = votes.get(v, 0) + 1
            row.append(max(votes, key=votes.get))
        out.append(row)
    return out


def outline(rows, ink=3):
    """A 1-px outline in `ink` round every non-background pixel (8-neighbour)."""
    out = [r[:] for r in rows]
    for y in range(8):
        for x in range(8):
            if rows[y][x] == 0 and any(0 <= y + dy < 8 and 0 <= x + dx < 8 and rows[y + dy][x + dx]
                                       for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                out[y][x] = ink
    return out


ETH_PIXELS = [                                                     # hand-drawn, 5 wide x 8 tall like the logo:
    "...1....",                                                    # gold left facets (1), grey-lilac right (2),
    "..112...",                                                    # the diamond, then its tip in the chevron
    ".11122..",
    ".11122..",
    "..112...",
    ".1.1.2..",
    "..1.2...",
    "...1....",
]


def eth_tile():
    """The ETH diamond, 8x8, as the food: no outline, so the shape reads at this size."""
    return [[int(c) if c != "." else 0 for c in row] for row in ETH_PIXELS]


def usdc_tile():
    """The USDC coin, 8x8: blue disc (1), dark rim (2), white "$" (3)."""
    rows = [[0] * 8 for _ in range(8)]
    for y in range(8):
        for x in range(8):
            r = math.hypot(x - 3.5, y - 3.5)
            if r <= 3.7:
                rows[y][x] = 2 if r > 2.8 else 1
    dollar = [".#.", "##.", ".#.", ".##", ".#."]
    for gy, row in enumerate(dollar):
        for gx, ch in enumerate(row):
            if ch == "#":
                rows[1 + gy][2 + gx] = 3
    for gx in (1, 6):                                               # the logo's arcs, at the sides
        for gy in (3, 4):
            rows[gy][gx] = 3
    return rows


LINK_PIXELS = [                                                    # the Chainlink logo: a pointy-top hexagon ring,
    "...11...",                                                    # Chainlink blue (1) with a darker inner edge
    ".111111.",                                                    # (2), hollow in the middle
    "112..211",
    "12....21",
    "12....21",
    "112..211",
    ".111111.",
    "...11...",
]


def link_tile():
    """The Chainlink bonus, 8x8."""
    return [[int(c) if c != "." else 0 for c in row] for row in LINK_PIXELS]


def star_tile():
    """The grass: a faint star, so the empty field reads as a night sky."""
    rows = [[0] * 8 for _ in range(8)]
    for x, y in ((3, 2), (2, 3), (3, 3), (4, 3), (3, 4)):
        rows[y][x] = 1
    return rows


def chain_block(rows):
    """A wall piece's brick hatch becomes chain blocks: its inner pixels (the two middle colours) become 4x4 blocks
    with a dark seam; the outline (3) and empty (0) pixels stay."""
    out = [r[:] for r in rows]
    for y in range(8):
        for x in range(8):
            if rows[y][x] in (1, 2):
                out[y][x] = 2 if (x % 4 == 3 or y % 4 == 3) else 1
    return out


# --- words: the HUD messages, 8 tiles (64 px) each, drawn from the game's own letters ----------------------------

def glyph(tiles, ch):
    """A letter from the game's font as columns of pixels, its blank side columns trimmed."""
    if ch == "!":
        return [[0, 3, 3, 3, 3, 0, 3, 0]] * 2                       # a bold bar and dot, as columns
    rows = tiles[bg(ord(ch))]
    cols = [[rows[y][x] for y in range(8)] for x in range(8)]
    while cols and not any(cols[0]):
        cols.pop(0)
    while cols and not any(cols[-1]):
        cols.pop()
    return cols


def word_tiles(tiles, text, width):
    """text set in the game's font, 1 px apart, centred in width px; returns width//8 tiles."""
    cols = []
    for i, ch in enumerate(text):
        if i:
            cols.append([0] * 8)
        cols.extend([[0] * 8] * 3 if ch == " " else glyph(tiles, ch))
    assert len(cols) <= width, f"{text!r} is {len(cols)} px, more than {width}"
    pad = (width - len(cols)) // 2
    cols = [[0] * 8] * pad + cols + [[0] * 8] * (width - len(cols) - pad)
    return [[[cols[t * 8 + x][y] for x in range(8)] for y in range(8)] for t in range(width // 8)]


MESSAGES = [(0x60, "REKT!", 64), (0x68, "HODL!", 48), (0x70, "WAGMI?", 48)]   # code, word, px (the rest is "+GO")


# --- palettes -----------------------------------------------------------------------------------------------------

NAVY = (20, 22, 43)
PALETTES = [
    [NAVY, (40, 44, 80), (98, 126, 234), (192, 203, 246)],         # 0 field, snake
    [NAVY, (123, 63, 228), (69, 74, 117), (192, 203, 246)],        # 1 walls
    [NAVY, (39, 117, 202), (20, 70, 140), (255, 255, 255)],        # 2 USDC
    [NAVY, (255, 214, 102), (138, 146, 178), (192, 203, 246)],     # 3 HUD, food
    [NAVY, (55, 91, 210), (30, 50, 130), (192, 203, 246)],         # 4 Chainlink bonus
]


def palette_asm():
    out = ["gColors", "\t\t;gggrrrrr,\t -bbbbbgg   (Any% web3 edition: Ethereum night)"]
    for n, pal in enumerate(PALETTES):
        out.append(f"gPal{n}")
        for r, g, b in pal:
            v = round(r * 31 / 255) | round(g * 31 / 255) << 5 | round(b * 31 / 255) << 10
            out.append(f"\tdb\t%{v & 0xFF:08b},\t%{v >> 8:08b}")
    return "\n".join(out) + "\n"


def patch_asm():
    src = open(os.path.join(SRC, "main.asm"), encoding="latin-1").read()

    def swap(a, b, count=1):
        nonlocal src
        assert src.count(a) == count, (a[:70], src.count(a))
        src = src.replace(a, b)

    # the palettes: everything from gColors to the first blank line after gPal4's last colour
    a = src.index("gColors\n")
    b = src.index("gPal4\n", a)
    b = src.index("\n\n", b)
    src = src[:a] + palette_asm() + src[b + 1:]
    # the title: GAMEBOY -> WEB3 EDITION (centred in 20 columns)
    swap('db\t" "," "," "," "," ","G","A","M","E","B","O","Y"," "," "," "," "," "," "," "',
         'db\t" "," "," "," ","W","E","B","3"," ","E","D","I","T","I","O","N"," "," "," "," "')
    # the basket is now a USDC coin: palette 2 (blue) where the game gives it palette 3
    swap("""	ld	A,	$FC		;make it a basket
	ld	[o_bonuschr],	A
	ld	A,	$3
	ld	[o_bonusattr],	A""", """	ld	A,	$FC		;make it a basket (a USDC coin)
	ld	[o_bonuschr],	A
	ld	A,	$2
	ld	[o_bonusattr],	A""")
    swap("""	ld	A,	$3	;set bonus color to grey
	ld	[o_bonusattr],	A""", """	ld	A,	$2	;set bonus color to USDC blue
	ld	[o_bonusattr],	A""")
    # ...and at start and restart, where it reuses a 3 already in A (A is reloaded right after)
    for before in ("\tldh\t[m_rstcnt],\tA\n", "\tldh\t[a_error],\tA\n"):
        swap(before + "\tld\t[o_bonusattr],\tA\n",
             before + "\tld\tA,\t$2\t;the bonus starts as the USDC coin: palette 2\n\tld\t[o_bonusattr],\tA\n")
    # the food's cell has the food's palette (3). The game gives a cell the snake's palette (0) two steps behind
    # the head, so the head was drawn in the food's colours for a moment (noise, once the colours differ this
    # much). When the head enters the food's cell, give that cell palette 0 at once (only that cell: a wall the
    # snake dies on keeps its colours).
    eat = "\tld\tA,\t[HL]\t;lookup what we are eating\n\tldh\t[v_eating],\tA\n"
    swap(eat, eat + "\tcp\tA,\tgAPPLE\t\t;Any%: entering the food's cell? it takes the snake's palette at once\n"
                    "\tjr\tNZ,\t.notfood\n"
                    "\tld\tA,\t1\n\tldh\t[$FF4F],A\n\txor\tA\n\tld\t[HL],\tA\n\tldh\t[$FF4F],A\n"
                    ".notfood\n")
    return src


def main():
    preview = sys.argv[sys.argv.index("--preview") + 1] if "--preview" in sys.argv else None
    orig_bin = open(os.path.join(SRC, "shapes.bin"), "rb").read()
    tiles = load_sheet()
    assert b"".join(gbgfx.tile_to_2bpp(t) for t in tiles) == orig_bin, "shapes.bmp no longer packs to shapes.bin"

    tiles[bg(0x40)] = star_tile()
    tiles[bg(0x0C)] = eth_tile()
    tiles[0xFC] = usdc_tile()
    tiles[0xFD] = link_tile()
    for code in range(0x10, 0x1C):
        tiles[bg(code)] = chain_block(tiles[bg(code)])
    for code in (0x6E, 0x6F, 0x76, 0x77):                          # "+GO": dark letters on its (now gold) box
        t = tiles[bg(code)]
        first = 1 if code in (0x6E, 0x76) else 0                   # column 0 of the first tile is the "+" arrow
        tiles[bg(code)] = [[0 if (c == 3 and x >= first) else c for x, c in enumerate(row)] for row in t]
    for code, text, width in MESSAGES:
        for i, t in enumerate(word_tiles(tiles, text, width)):
            tiles[bg(code + i)] = t

    im = save_sheet(tiles)
    open(os.path.join(WORK, "main.asm"), "w", encoding="latin-1", newline="\n").write(patch_asm())
    if preview:
        os.makedirs(preview, exist_ok=True)
        im.resize((im.width * 4, im.height * 4), Image.NEAREST).save(os.path.join(preview, "shapes.png"))
    print("snake reskinned")


if __name__ == "__main__":
    main()
