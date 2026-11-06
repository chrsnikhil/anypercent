"""Rebound, web3 edition. Reads DevEd's untouched source (games/src/rebound), writes the new art and palettes into
the working copy (games/work/rebound), then `mod.py rebound build` makes the ROM. Rerunnable: it always starts from
the original files.

  player     the blue ball is a USDC coin on every frame: blue disc, white "$", the logo's white arcs, no face
             (each frame keeps the ball's outline, so the squash and stretch of the bounce stays)
  moneybag   the collectable is an ETH diamond, in the same glyph colours as the coins
  goony      the walking enemy is a red bear (bear market): ears on its red body
  coins      each coin is a full-size ETH diamond: in the ethereum.org glyph colours above ground (#454A75, #8A92B2),
             black and white underground and in the Forest (palettes those areas already have)
  HUD        the money counter's "$" is "Ξ"; the lives icon is a small USDC coin
  title      the big ball is the USDC logo; "DEMO" reads "USDC"

  python reskin.py [--preview DIR]"""
import math
import os
import re

import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gbgfx                                      # noqa: E402
from gbcscreen import Screen                      # noqa: E402
sys.path.insert(0, HERE)
import mainnet                                    # noqa: E402
import screens                                    # noqa: E402

SRC = "/opt/arca-sandbox/games/src/rebound"
WORK = "/opt/arca-sandbox/games/work/rebound"
WLENC = os.path.join(SRC, "Tools", "wlenc.py")


def read(rel):
    with open(os.path.join(SRC, rel), "rb") as f:
        return f.read()


def write(rel, data):
    with open(os.path.join(WORK, rel), "wb") as f:
        f.write(data)


def frames16(data):
    """16x16 sprite frames as 16 rows of colour indexes."""
    tiles = gbgfx.tiles_from_2bpp(data)
    out = []
    for f in range(len(tiles) // 4):
        grid = [[0] * 16 for _ in range(16)]
        for k, (dx, dy) in enumerate(gbgfx.SPRITE16_ORDER):
            for y, row in enumerate(tiles[f * 4 + k]):
                for x, c in enumerate(row):
                    grid[dy + y][dx + x] = c
        out.append(grid)
    return out


def bytes16(frames):
    out = bytearray()
    for g in frames:
        for dx, dy in gbgfx.SPRITE16_ORDER:
            out += gbgfx.tile_to_2bpp([g[dy + y][dx:dx + 8] for y in range(8)])
    return bytes(out)


def bbox(g):
    pts = [(x, y) for y in range(16) for x in range(16) if g[y][x]]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# --- USDC coin: the player, every frame ----------------------------------------------------------------------------

DOLLAR = [".####", "#.#..", ".###.", "..#.#", "####."]               # 5 x 5, white; the stem added above and below


def usdc_coin(grid, outline=1, blue=2, white=3):
    """The frame redrawn as a USDC coin inside the ball's own silhouette (squashed frames stay squashed)."""
    if sum(r.count(blue) for r in grid) < 20:                     # an unused placeholder frame: leave it
        return grid
    x0, y0, x1, y1 = bbox(grid)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0 + 1) / 2, (y1 - y0 + 1) / 2
    inside = [[grid[y][x] != 0 for x in range(16)] for y in range(16)]
    t = math.tan(math.radians(50))
    out = [[0] * 16 for _ in range(16)]
    for y in range(16):
        for x in range(16):
            if not inside[y][x]:
                continue
            edge = any(not (0 <= x + dx < 16 and 0 <= y + dy < 16) or not inside[y + dy][x + dx]
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            nx, ny = (x - cx) / rx, (y - cy) / ry
            r = math.hypot(nx, ny)
            if edge:
                out[y][x] = outline
            elif 0.66 <= r <= 0.86 and abs(ny) <= t * abs(nx):    # the logo's arcs, left and right
                out[y][x] = white
            else:
                out[y][x] = blue
    gx, gy = round(cx - 2), round(cy - 2)                        # "$" in the middle, with its stem if there is room
    for dy, row in enumerate(DOLLAR):
        for dx, ch in enumerate(row):
            if ch == "#" and 0 <= gy + dy < 16 and inside[gy + dy][gx + dx]:
                out[gy + dy][gx + dx] = white
    for sy in (gy - 1, gy + 5):
        if 0 <= sy < 16 and inside[sy][gx + 2] and out[sy][gx + 2] == blue and ry >= 6:
            out[sy][gx + 2] = white
    return out


# --- ETH diamond -------------------------------------------------------------------------------------------------

def eth_diamond():
    """16x16: 0 clear, 1 outline, 2 mid facets, 3 light facets."""
    S = 8
    img = Image.new("L", (16 * S, 16 * S), 0)
    d = ImageDraw.Draw(img)
    P = lambda *pts: [(x * S, y * S) for x, y in pts]
    A, L, R, B, C = (8, 0.6), (3, 8.4), (13, 8.4), (8, 10.8), (8, 6.4)
    d.polygon(P(A, L, C), fill=3)
    d.polygon(P(A, R, C), fill=2)
    d.polygon(P(L, B, C), fill=2)
    d.polygon(P(R, B, C), fill=3)
    L2, R2, B2, D = (3, 9.8), (13, 9.8), (8, 12.4), (8, 15.4)
    d.polygon(P(L2, B2, D), fill=3)
    d.polygon(P(R2, B2, D), fill=2)
    grid = [[0] * 16 for _ in range(16)]
    for y in range(16):
        for x in range(16):
            votes = {}
            for sy in range(S):
                for sx in range(S):
                    v = img.getpixel((x * S + sx, y * S + sy))
                    votes[v] = votes.get(v, 0) + 1
            v, n = max(votes.items(), key=lambda kv: kv[1])
            grid[y][x] = v if v and n * 2 >= S * S * 0.5 else (max((k for k in votes if k), default=0)
                                                               if sum(n for k, n in votes.items() if k) * 2 > S * S
                                                               else 0)
    out = [row[:] for row in grid]                                  # a 1-px dark outline, outside the shape
    for y in range(16):
        for x in range(16):
            if grid[y][x] == 0 and any(0 <= y + dy < 16 and 0 <= x + dx < 16 and grid[y + dy][x + dx]
                                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                out[y][x] = 1
    return out


# --- bear ears on the goony ----------------------------------------------------------------------------------------

def bear(grid, outline, fur):
    b = bbox(grid)
    if b is None:
        return grid
    x0, y0, x1, y1 = b
    top = y0
    row = [x for x in range(16) if grid[top + 1][x]] if top + 1 < 16 else []
    if not row:
        return grid
    left, right = min(row), max(row)
    for ex in (left + 1, right - 2):                               # two round ears, 2x2 fur in a rounded rim
        fur_px = [(ex, top - 2), (ex + 1, top - 2), (ex, top - 1), (ex + 1, top - 1)]
        rim = [(ex, top - 3), (ex + 1, top - 3), (ex - 1, top - 2), (ex + 2, top - 2), (ex - 1, top - 1),
               (ex + 2, top - 1)]
        for x, y in rim:
            if 0 <= x < 16 and 0 <= y < 16 and grid[y][x] == 0:
                grid[y][x] = outline
        for x, y in fur_px:
            if 0 <= x < 16 and 0 <= y < 16:
                grid[y][x] = fur
    return grid


def shift_down(grid, n):
    return [[0] * 16 for _ in range(n)] + [r[:] for r in grid[:16 - n]]


# --- coins: the gold coin's "$" is an ETH diamond ---------------------------------------------------------------

COINS = {                                                          # tileset file -> each coin's tiles (TL, TR, BL, BR)
    "GFX/Tilesets/PlainsTiles.2bpp": [(0x30, 0x31, 0x32, 0x33), (0x48, 0x49, 0x4A, 0x4B)],   # coin, underground coin
    "GFX/Tilesets/ForestTiles.2bpp": [(94, 95, 112, 113)],         # block 0x2a in Forest.blk
}


def eth_coin(tiles, ids):
    """The coin's 16x16 block becomes the ETH diamond (eth_diamond: 0 background, 1 outline, 2 mid, 3 light). The
    coin blocks are moved to palettes laid out the same way (see COIN_PALETTES)."""
    quad = [(0, 0), (8, 0), (0, 8), (8, 8)]
    g = eth_diamond()
    for t, (dx, dy) in zip(ids, quad):
        tiles[t] = [g[dy + y][dx:dx + 8] for y in range(8)]


# Plains BG palette 2 ("dirt + rocks") becomes Ethereum's colours; the two rock blocks that used it move to palette 0
# (plain dirt: their pebbles turn dark brown). The coin blocks then point at it; the underground coin at palette 7
# (black, greys, white) and the Forest coin at Forest palette 0 (forest green, greys, white): black-and-white ETH.
ETH_PLAINS = """    ; dirt + rocks -> ETH coin (the ethereum.org glyph: #454A75 and #8A92B2 facets, navy outline)
    RGB 128>>3,160>>3,255>>3
    RGB  20>>3, 22>>3, 48>>3
    RGB  69>>3, 74>>3,117>>3
    RGB 138>>3,146>>3,178>>3"""
ROCKS_PLAINS = """    ; dirt + rocks
    RGB 111>>3,111>>3,111>>3
    RGB 192>>3,192>>3,192>>3
    RGB 139>>3, 64>>3,  0>>3
    RGB 176>>3, 80>>3,  0>>3"""
COIN_BLOCKS = {"coin": "%00000010", "underground coin": "%00000111", "middle (rocks 1)": "%00000000",
               "middle (rocks 2)": "%00000000"}
FOREST_COIN_BLOCK = 0x2A


def coin_palettes():
    # (the coin palette itself is written by mainnet.plains_palettes: Plains palette 2)
    ts = read("Data/Tilesets.asm").decode()
    a, b = ts.index("Tileset_Plains"), ts.index('section "Forest tileset')
    seg = ts[a:b]
    for name, attr in COIN_BLOCKS.items():
        i = seg.index("; " + name + "\n")
        j = seg.index("\n", seg.index("\n", seg.index("\n", i) + 1) + 1)   # the comment and its two db rows
        block = seg[i:j]
        new = re.sub(r"%0000[01]{4}", lambda m: m.group(0)[:-3] + attr[-3:], block)
        seg = seg[:i] + new + seg[j:]
    write("Data/Tilesets.asm", (ts[:a] + seg + ts[b:]).encode())
    blk = bytearray(read("GFX/Tilesets/Forest.blk"))
    for k in range(1, 8, 2):
        blk[FOREST_COIN_BLOCK * 8 + k] &= ~7 & 0xFF                 # Forest palette 0
    write("GFX/Tilesets/Forest.blk", bytes(blk))


# --- HUD: "$" -> "Ξ" ---------------------------------------------------------------------------------------------

def xi_tile(dollar):
    """Ξ in the "$" tile's own colours and rows."""
    counts = {}
    for r in dollar:
        for c in r:
            counts[c] = counts.get(c, 0) + 1
    bg = max(counts, key=counts.get)
    ink = [c for c in counts if c != bg]
    fg = max(ink, key=lambda c: counts[c])
    rows = [y for y in range(8) if any(c != bg for c in dollar[y])]
    top, bottom = min(rows), max(rows)
    mid = (top + bottom) // 2
    out = [[bg] * 8 for _ in range(8)]
    for x in range(1, 6):
        out[top][x] = out[bottom][x] = fg
    for x in range(2, 5):
        out[mid][x] = fg
    return out


COIN_ICON = [                                                      # 8 x 8: a disc with "$" cut out of it
    "..####..",
    ".##..##.",
    "##.####.",
    "###..###",
    "#####.##",
    ".##..##.",
    "..####..",
    "........",
]


def coin_icon(xi):
    """The lives icon (the ball's face) as a small USDC coin, in the HUD's ink and paper (taken from the Ξ tile)."""
    counts = {}
    for row in xi:
        for c in row:
            counts[c] = counts.get(c, 0) + 1
    paper = max(counts, key=counts.get)
    ink = next(c for c in counts if c != paper)
    return [[ink if ch == "#" else paper for ch in row] for row in COIN_ICON]


# --- title ---------------------------------------------------------------------------------------------------------

BALL_SHADES = {(25, 82, 140), (25, 58, 90)}                         # the old ball's shaded blues (not the sky's)
BALL = (117, 92, 29)                                               # the title's big ball: centre and radius
BADGE = (144, 46, 47)                                              # where "DEMO" sat: centre and slant, degrees
PRESS_START = range(0x27, 0x30)                                    # bank-1 tiles the PRESS START sprite owns


def components(mask, w, h):
    seen, out = set(), []
    for y in range(h):
        for x in range(w):
            if mask[y][x] and (x, y) not in seen:
                stack, comp = [(x, y)], []
                seen.add((x, y))
                while stack:
                    px, py = stack.pop()
                    comp.append((px, py))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                        nx, ny = px + dx, py + dy
                        if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] and (nx, ny) not in seen:
                            seen.add((nx, ny))
                            stack.append((nx, ny))
                out.append(comp)
    return out


def badge(text, angle):
    """White text on a slant, as a mask: drawn 4x large in a bold face, turned, scaled down, thresholded."""
    from PIL import ImageFont
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
    big = Image.new("L", (200, 200), 0)
    ImageDraw.Draw(big).text((100, 100), text, font=font, fill=255, anchor="mm")
    big = big.rotate(angle, resample=Image.BICUBIC)
    small = big.resize((50, 50), Image.BOX)
    return [[small.getpixel((x, y)) > 110 for x in range(50)] for y in range(50)]


def usdc_logo(img, cx, cy, r):
    """The USDC logo drawn over the ball: blue disc, navy rim, white arcs and "$" (sampled 4x4 per pixel, so the
    shapes are clean once each cell takes its nearest palette colours)."""
    from PIL import ImageFont
    blue, rim, white = (0, 115, 230), (25, 49, 82), (255, 255, 255)
    S = 4
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", round(r * 1.25 * S))
    glyph = Image.new("L", ((2 * r + 2) * S, (2 * r + 2) * S), 0)
    ImageDraw.Draw(glyph).text(((r + 1) * S, (r + 1) * S), "$", font=font, fill=255, anchor="mm")
    t = math.tan(math.radians(52))
    px = img.load()
    for y in range(cy - r - 1, cy + r + 2):
        for x in range(cx - r - 1, cx + r + 2):
            votes = {}
            for sy in range(S):
                for sx in range(S):
                    fx, fy = x + (sx + 0.5) / S - 0.5, y + (sy + 0.5) / S - 0.5
                    nx, ny = (fx - cx) / r, (fy - cy) / r
                    d = math.hypot(nx, ny)
                    if d > 1:
                        c = None
                    elif d > 0.93:
                        c = rim
                    elif 0.70 <= d <= 0.84 and abs(ny) <= t * abs(nx):
                        c = white
                    elif glyph.getpixel((int((fx - cx + r + 1) * S), int((fy - cy + r + 1) * S))) > 128:
                        c = white
                    else:
                        c = blue
                    votes[c] = votes.get(c, 0) + 1
            c = max(votes, key=votes.get)
            if c is not None:
                px[x, y] = c
    for y in range(cy - r - 6, cy + r + 7):                       # the old ball was a little larger and dithered:
        for x in range(cx - r - 6, cx + r + 7):                   # its shading outside the logo becomes the navy
            if 0 <= x < 160 and 0 <= y < 144 and r < math.hypot(x - cx, y - cy) <= r + 6 and px[x, y] in BALL_SHADES:
                px[x, y] = rim


TITLE_BULL = (96, 72, 3)                                          # the bull on the title: left, top, scale (48 px)
TITLE_NAVY = (25, 49, 82)                                          # the title's lower background as Screen.image()
                                                                   # draws it (5-bit 24,48,80), before the recolour


def title_bull(img):
    """The old ball erased to the navy and the big bull drawn where it was. Returns the cells the bull covers (they
    get their own palette: navy, outline, hide, cream)."""
    cx, cy, r = BALL
    px = img.load()
    for y in range(144):
        for x in range(160):
            d = math.hypot(x - cx, y - cy)
            if (d <= r + 1 or (d <= r + 6 and px[x, y] in BALL_SHADES)
                    or (d <= r + 5 and x > cx - 10 and px[x, y] == (0, 115, 230))):   # its rim, clear of the banner
                px[x, y] = TITLE_NAVY
    x0, y0, s = TITLE_BULL
    grid = screens.bull_grid(SRC, "Idle")
    screens.paste_bull(img, grid, x0, y0, s, [TITLE_NAVY] + screens.BULL[1:])
    cells = {((x0 + x * s + dx) // 8, (y0 + y * s + dy) // 8) for y in range(16) for x in range(16) if grid[y][x]
             for dx in range(s) for dy in range(s)}
    for cx8, cy8 in cells:                                          # a bull cell may hold only the navy besides the bull
        for y in range(cy8 * 8, cy8 * 8 + 8):
            for x in range(cx8 * 8, cx8 * 8 + 8):
                assert px[x, y] in [TITLE_NAVY] + screens.BULL[1:], (cx8, cy8, px[x, y])
    return cells


def title(img):
    """The big bull where the ball was, and "WEB3" where "DEMO" was. img: the title as RGB, 160x144, edited in place.
    Returns the bull's cells."""
    cells = title_bull(img)
    px = img.load()
    white = (255, 255, 255)
    # erase DEMO: the small bright shapes on the navy, right of the logo
    bx, by, angle = BADGE
    region = (bx - 22, by - 14, bx + 16, by + 14)
    navy = px[region[2] - 1, region[3] - 1]
    mask = [[region[0] <= x < region[2] and region[1] <= y < region[3] and sum(px[x, y]) > 600
             for x in range(160)] for y in range(144)]
    for comp in components(mask, 160, 144):
        if len(comp) < 60:                                         # letters; the logo is one big shape
            for x, y in comp:
                px[x, y] = navy
    m = badge("WEB3", angle)
    for y in range(50):
        for x in range(50):
            if m[y][x]:
                X, Y = bx - 25 + x, by - 25 + y
                if 0 <= X < 160 and 0 <= Y < 144 and px[X, Y][0] < 100 and (X // 8, Y // 8) not in cells:
                    px[X, Y] = white
    return cells


def title_files(preview=None):
    r = lambda f: gbgfx.wle_decode(read("GFX/Screens/" + f))
    s = Screen(r("TitleScreen_Block1.2bpp.wle"), r("TitleScreen_Block2.2bpp.wle"), r("TitleScreen.til.wle"),
               r("TitleScreen.atr.wle"), read("GFX/Screens/TitleScreen.pal"))
    before = s.image()
    img = before.copy()
    cells = title(img)
    s.pals.append([TITLE_NAVY] + screens.BULL[1:])                 # palette 7: the bull (the loader now reads 8)
    for cx8, cy8 in cells:
        i = cy8 * s.stride + cx8
        s.attr[i] = (s.attr[i] & ~7) | 7
    assert len(s.banks[1]) == PRESS_START.start                    # the title's bank-1 tiles end where the sprite's begin
    changed = s.apply(img, [(1, t) for t in range(PRESS_START.stop, 256)])
    pal = screens.recolour_pal(read("GFX/Screens/TitleScreen.pal"), screens.TITLE_MAP)
    write("GFX/Screens/TitleScreen.pal", pal + screens.pal_bytes([[screens.NAVY] + screens.BULL[1:]]))
    menus = read("Engine/GameModes/TitleAndMenus.asm").decode()
    load = "    ld      hl,Pal_TitleScreen\n    ld      b,7\n"
    assert load in menus
    write("Engine/GameModes/TitleAndMenus.asm", menus.replace(load, load.replace("b,7", "b,8"), 1).encode())
    press = gbgfx.tiles_from_2bpp(read("GFX/Sprites/PressStart.2bpp"))
    for i in PRESS_START:                                          # its slots hold its own tiles (it is copied over them)
        if i < len(s.banks[1]):
            s.banks[1][i] = press[i - PRESS_START.start]
    for name, data in (("TitleScreen_Block1.2bpp.wle", s.tiles_bytes(0)), ("TitleScreen_Block2.2bpp.wle",
                       s.tiles_bytes(1)), ("TitleScreen.til.wle", bytes(s.tmap)), ("TitleScreen.atr.wle",
                       bytes(s.attr))):
        write("GFX/Screens/" + name, gbgfx.wle_encode(data, WLENC))
    if preview:
        side = Image.new("RGB", (320, 144))
        side.paste(before, (0, 0))
        side.paste(s.image(), (160, 0))
        side.resize((960, 432), Image.NEAREST).save(os.path.join(preview, "title.png"))
    return len(changed), len(s.banks[1])


def main():
    preview = sys.argv[sys.argv.index("--preview") + 1] if "--preview" in sys.argv else None
    if preview:
        os.makedirs(preview, exist_ok=True)

    # player: the brown bull (Mainnet, 2026-10-04; it was a USDC coin, now the coins are)
    player = frames16(read("GFX/PlayerTiles.2bpp"))
    player = [mainnet.bull([r[:] for r in g]) for g in player]
    write("GFX/PlayerTiles.2bpp", bytes16(player))

    # moneybag -> ETH diamond (OBJ palette 7: the coins' glyph colours)
    eth = eth_diamond()
    write("GFX/Sprites/Moneybag.2bpp", bytes16([eth]))

    # goony -> bear
    goony = frames16(read("GFX/Sprites/Goony/Goony.2bpp"))
    bears = []
    for g in goony:
        b = bbox(g)
        if b and b[1] < 3:
            g = shift_down(g, 3 - b[1])
        bears.append(bear([r[:] for r in g], outline=1, fur=2))
    write("GFX/Sprites/Goony/Goony.2bpp", bytes16(bears))

    # coins: small USDC; the Plains tileset also becomes chain bricks under a starry sky
    for rel, coins in COINS.items():
        tiles = gbgfx.tiles_from_2bpp(read(rel))
        if "Plains" in rel:
            mainnet.plains_tiles(tiles)
        for ids in coins:
            mainnet.coin_tiles(tiles, ids)
        data = b"".join(gbgfx.tile_to_2bpp(t) for t in tiles)
        write(rel, data)
        write(rel + ".wle", gbgfx.wle_encode(data, WLENC))

    # HUD: the lives icon is a little bull; the counter keeps its "$" (the coins are USDC)
    hud = gbgfx.tiles_from_2bpp(read("GFX/HUD.2bpp"))
    hud[0] = mainnet.bull_icon(hud[1])
    hud_bytes = b"".join(gbgfx.tile_to_2bpp(t) for t in hud)
    write("GFX/HUD.2bpp", hud_bytes)
    write("GFX/HUD.2bpp.wle", gbgfx.wle_encode(hud_bytes, WLENC))

    # palettes: an object's palette ID is its OBJ palette, and the level loads Pal_PlainsObjects entry k into OBJ
    # palette k+1 (so the goony's ID 2 is entry 1, red already). Entry 6 (OBJ 7, used by nothing) becomes the ETH glyph colours,
    # for the moneybag.
    pal = read("Data/Palettes.asm").decode()
    objs = pal.index("Pal_PlainsObjects:")
    head, body = pal[:objs], pal[objs:]
    grays = "    RGB 31, 0,31\n    RGB  0, 0, 0\n    RGB 10,10,10\n    RGB 20,20,20"
    assert grays in body
    body = body.replace(grays, "    RGB 31, 0,31\n    RGB  2, 3, 6\n    RGB  8, 9,14\n    RGB 17,18,22", 1)   # the ETH pickup
    pal = mainnet.plains_palettes(head + body)
    assert mainnet.PLAYER_PAL[0] in pal
    pal = pal.replace(*mainnet.PLAYER_PAL, 1)
    write("Data/Palettes.asm", pal.encode())
    write("GFX/Tilesets/Forest.pal", mainnet.forest_pal(read("GFX/Tilesets/Forest.pal")))
    obj = read("Engine/Object.asm").decode()
    a = "BANK(Anim_Default),Anim_Default,1 ; COLLECTABLE_MONEYBAG"
    assert a in obj
    write("Engine/Object.asm", obj.replace(a, "BANK(Anim_Default),Anim_Default,7 ; COLLECTABLE_MONEYBAG (ETH)").encode())
    coin_palettes()                                                # after the OBJ palettes: it edits the same file

    cells, bank1 = title_files(preview)
    print(f"title: {cells} cells redrawn, bank 1 now {bank1} tiles")

    # the other screens: game over and the end drawn fresh, the DevEd splash recoloured
    for name, make in (("GameOver", screens.game_over), ("EndScreen", screens.end_screen)):
        img, pals = make(SRC)
        tiles, tmap, attr = screens.encode(img, pals)
        pals = (pals + [pals[0]] * 6)[:6]                          # the loader reads 6
        for ext, data in ((".2bpp.wle", tiles), (".til.wle", tmap), (".atr.wle", attr)):
            write("GFX/Screens/" + name + ext, gbgfx.wle_encode(data, WLENC))
        write("GFX/Screens/" + name + ".pal", screens.pal_bytes(pals))
        print(f"{name}: {len(tiles) // 16} tiles")
        if preview:
            img.resize((480, 432), Image.NEAREST).save(os.path.join(preview, name + ".png"))
    write("GFX/Screens/DevEdPresents.pal", screens.recolour_pal(read("GFX/Screens/DevEdPresents.pal"),
                                                                  screens.SPLASH_MAP))

    if preview:
        os.makedirs(preview, exist_ok=True)
        pal_player = [(255, 0, 255), (0, 0, 0), (0, 123, 255), (255, 255, 255)]
        gbgfx.sprites16_to_image(bytes16(player), 16, pal_player, 4).save(os.path.join(preview, "player.png"))
        gbgfx.sprites16_to_image(bytes16([eth]), 1, [(128, 160, 255), (33, 33, 99), (99, 123, 239), (206, 222, 255)],
                                 8).save(os.path.join(preview, "eth.png"))
        gbgfx.sprites16_to_image(bytes16(bears), 9, [(128, 160, 255), (0, 0, 0), (206, 41, 33), (255, 255, 255)],
                                 6).save(os.path.join(preview, "bear.png"))
        gbgfx.tiles_to_image(hud_bytes, 14, gbgfx.SHADES[::-1], 6).save(os.path.join(preview, "hud.png"))
    print("rebound reskinned")


if __name__ == "__main__":
    main()
