"""Rebound "Mainnet" (design A, owner's pick 2026-10-04): the worlds, the player and the coins.

  player   a brown bull (bull market, against the red bear): every expression frame of the ball keeps its eyes and
           shading; big horns curve out of the head and a muzzle with nostrils sits across the bottom
  coins    small USDC coins (12 px) in their 16x16 blocks: USDC blue above ground, black and white underground and
           in the Forest (the palettes those blocks use); the rarer big pickup stays the ETH diamond
  Plains   a starry navy night; the dirt is indigo chain bricks (16 x 8, bevelled, linked at the seams) and the solid
           dirt block a 16x16 chain cube; grass tops glow ETH blue; flowers are lilac crystals; signs indigo plaques
  Forest   a neon Layer 2 grove: violet night, indigo trunks, cyan canopy
  HUD      the lives icon is a little bull head; the counter's "$" stays a "$" (the coins are USDC)
Called from reskin.py, which owns reading the original source and writing the working copy."""
import math

OUT, BODY, CREAM = 1, 2, 3

# --- player: the bull ------------------------------------------------------------------------------------------

HORNS = ["oo............oo",                        # big horns curving up and out of the head
         "cco..........occ",
         "occo........occo",
         ".occo......occo.",
         "..oco......oco..",
         "...o........o..."]
MUZZLE = ["....oooooooo....",                       # rows 10 to 14, over the bottom of the face
          "...occcccccco...",
          "...ococcccoco...",
          "....occcccco....",
          ".....oooooo....."]

PLAYER_PAL = ("Pal_Player:\n    RGB 31, 0,31\n    RGB  0, 0, 0\n    RGB  0,15,31\n    RGB 31,31,31",
              "Pal_Player:     ; Any%: the brown bull (outline, hide, horns and muzzle)\n"
              "    RGB 31, 0,31\n    RGB  5, 2, 1\n    RGB 22,12, 5\n    RGB 31,29,24")


def bull(grid):
    """One player frame as the bull. 0 clear, 1 outline, 2 hide, 3 cream (eyes, horns, muzzle)."""
    if sum(r.count(BODY) for r in grid) < 20:                       # an unused placeholder frame: leave it
        return grid
    out = [r[:] for r in grid]
    for y, row in enumerate(HORNS):
        for x, ch in enumerate(row):
            if ch != "." and grid[y][x] != CREAM:                   # over the head too, never over an eye
                out[y][x] = OUT if ch == "o" else CREAM
    for dy, row in enumerate(MUZZLE):
        for x, ch in enumerate(row):
            y = 10 + dy
            if ch != "." and grid[y][x] != 0:
                out[y][x] = OUT if ch == "o" else CREAM
    return out


# --- coins: small USDC ---------------------------------------------------------------------------------------------

DOLLAR = [".###.", "#.#..", ".###.", "..#.#", ".###."]   # 5 x 5 with the stem through it


def usdc_small():
    """16x16 coin block: 0 background, 1 rim, 2 disc, 3 white (the logo's arcs and "$"). The coin is 12 px across."""
    cx, cy, r = 7.5, 7.5, 6.0
    t = math.tan(math.radians(50))
    g = [[0] * 16 for _ in range(16)]
    for y in range(16):
        for x in range(16):
            d = math.hypot(x - cx, y - cy)
            if d > r:
                continue
            nx, ny = (x - cx) / r, (y - cy) / r
            if d > r - 1.05:
                g[y][x] = 1
            elif 0.6 <= d / r <= 0.82 and abs(ny) <= t * abs(nx):
                g[y][x] = 3
            else:
                g[y][x] = 2
    for dy, row in enumerate(DOLLAR):
        for dx, ch in enumerate(row):
            if ch == "#":
                g[6 + dy][6 + dx] = 3
    g[5][8] = g[11][8] = 3                                          # the stem out of the top and bottom
    return g


def coin_tiles(tiles, ids):
    quad = [(0, 0), (8, 0), (0, 8), (8, 8)]
    g = usdc_small()
    for t, (dx, dy) in zip(ids, quad):
        tiles[t] = [g[dy + y][dx:dx + 8] for y in range(8)]


# --- Plains -----------------------------------------------------------------------------------------------------

def rgb(c):
    return "    RGB %3d>>3,%3d>>3,%3d>>3" % c


NAVY = (20, 22, 43)
PLAINS = [                                                          # the 8 BG palettes, in the source's order
    ("chain blocks (dirt)", [(14, 14, 30), (36, 38, 72), (69, 74, 117), (110, 118, 178)]),
    ("chain blocks + glowing top (dirt + grass)", [(69, 74, 117), (36, 38, 72), (98, 126, 234), (192, 203, 246)]),
    ("USDC coin (was dirt + rocks)", [NAVY, (10, 26, 58), (39, 117, 202), (255, 255, 255)]),
    ("liquidity pool (water)", [(14, 14, 30), (60, 40, 140), (120, 90, 220), (220, 210, 255)]),
    ("signs: indigo plaques, gold", [NAVY, (0, 0, 0), (69, 74, 117), (255, 214, 102)]),
    ("spikes (above ground) on the night sky", [NAVY, (136, 136, 136), (198, 198, 198), (255, 255, 255)]),
    ("lilac crystals (flowers + grass)", [NAVY, (98, 126, 234), (192, 203, 246), (255, 255, 255)]),
    ("spikes (underground) + HUD", [(0, 0, 0), (78, 78, 78), (162, 162, 162), (255, 255, 255)]),
]


def plains_palettes(pal_asm):
    """Pal_Plains rewritten whole (it runs up to Pal_Forest; Pal_PlainsObjects is earlier in the file)."""
    a = pal_asm.index("Pal_Plains:")
    b = pal_asm.index("Pal_Forest:", a)
    body = "Pal_Plains:     ; Any%: Mainnet\n"
    for name, cols in PLAINS:
        body += "    ; " + name + "\n" + "\n".join(rgb(c) for c in cols) + "\n"
    return pal_asm[:a] + body + "\n" + pal_asm[b:]


# which column of a 16-wide block each dirt tile sits in (from Data/Tilesets.asm); None = used in both
LEFT = {0x13, 0x15, 0x17, 0x18, 0x19, 0x1B, 0x1D, 0x22, 0x10, 0x1F}
RIGHT = {0x14, 0x16, 0x1A, 0x1C, 0x20, 0x21, 0x12, 0x1E}
BOTH = {0x11}
PAL0_DIRT = {0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x20, 0x21, 0x22}
PAL1_TOPS = {0x10, 0x11, 0x12, 0x1E, 0x1F}
CUBE = (0x44, 0x45, 0x46, 0x47)                                     # the solid dirt block: TL, TR, BL, BR


def brick(xg, y):
    """A 16 x 8 chain brick, in palette 0 indexes: 3 bevel light (top, left), 1 bevel dark (bottom, right),
    2 face; a link (light) crossing the left and right seams at mid-height."""
    if y in (3, 4) and xg in (0, 1, 14, 15):
        return 3
    if y == 0 or xg == 0:
        return 3
    if y == 7 or xg == 15:
        return 1
    return 2


def chain_cube(x, y):
    """The 16x16 solid block: a bevelled cube with an inset line and an ETH diamond on its face."""
    if y == 0 or x == 0:
        return 3
    if y == 15 or x == 15:
        return 1
    if (x in (3, 12) and 3 <= y <= 12) or (y in (3, 12) and 3 <= x <= 12):
        return 1
    if abs(x - 7.5) + abs(y - 7.5) * 0.75 <= 2.6:
        return 3
    return 2


STARS = {0x01: [(2, 5, 1)]}                                         # one dim star per 16x16 sky block: more and it
                                                                    # reads as a grid ($00 is also the tall grass)


def plains_tiles(tiles):
    for t in PAL0_DIRT:                                             # dirt pixels (1..3) become bricks; black stays
        col = 0 if t in LEFT else 8
        tiles[t] = [[brick(x + col, y) if c else 0 for x, c in enumerate(row)] for y, row in enumerate(tiles[t])]
    for t in PAL1_TOPS:                                             # grass tops: their dirt (0, 1) becomes brick
        col = 0 if t in LEFT else 8
        new = []
        for y, row in enumerate(tiles[t]):
            out = []
            for x, c in enumerate(row):
                if c in (0, 1):
                    edge = y == 7 or (t not in BOTH and x + col == 15)
                    out.append(1 if edge else 0)
                else:
                    out.append(c)                                   # 2, 3: the grass, now the glowing edge
            new.append(out)
        tiles[t] = new
    for t, (dx, dy) in zip(CUBE, [(0, 0), (8, 0), (0, 8), (8, 8)]):
        tiles[t] = [[chain_cube(x + dx, y + dy) for x in range(8)] for y in range(8)]
    for t, pts in STARS.items():
        if all(c == 0 for row in tiles[t] for c in row):
            for x, y, c in pts:
                tiles[t][y][x] = c
    return tiles


# --- Forest -------------------------------------------------------------------------------------------------------

FOREST_MAP = {(40, 72, 0): (30, 18, 52),                            # night violet
              (176, 72, 0): (69, 74, 117), (64, 24, 0): (36, 38, 72), (120, 56, 0): (69, 74, 117),   # trunks
              (80, 152, 0): (0, 205, 220), (104, 160, 64): (110, 230, 240),                          # canopy
              (192, 136, 96): (138, 146, 178)}


def forest_pal(data):
    out = bytearray(data)
    for i in range(0, len(data), 2):
        v = data[i] | data[i + 1] << 8
        c = ((v & 31) * 8, ((v >> 5) & 31) * 8, ((v >> 10) & 31) * 8)
        if c in FOREST_MAP:
            r, g, b = (k >> 3 for k in FOREST_MAP[c])
            v = r | g << 5 | b << 10
            out[i], out[i + 1] = v & 0xFF, v >> 8
    return bytes(out)


# --- HUD: lives icon --------------------------------------------------------------------------------------------

BULL_ICON = ["#......#",
             "##....##",
             ".######.",
             ".#.##.#.",
             ".######.",
             "..#..#..",
             "..####..",
             "........"]


def bull_icon(dollar):
    """The lives icon as a little bull head, in the "$" tile's ink and paper."""
    counts = {}
    for row in dollar:
        for c in row:
            counts[c] = counts.get(c, 0) + 1
    paper = max(counts, key=counts.get)
    ink = max((c for c in counts if c != paper), key=lambda c: counts[c])
    return [[ink if ch == "#" else paper for ch in row] for row in BULL_ICON]
