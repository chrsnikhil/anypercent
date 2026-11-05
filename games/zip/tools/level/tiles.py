"""ZIP's terrain tiles, shared by the art (tools/art/build_art.py draws them from these masks) and the level build
(tools/level/build_level.py writes the masks and angles into gen/level.c for the rules). One tile is 16 x 16 px.

A height mask is 16 heights, one per pixel column (left to right): the column is solid from its bottom up to that
height (0 = empty column, 16 = full). Angles are 0-255 per turn, positive = the surface rises to the right."""

TILE = 16

# id: (glyph, name, mask, angle). Id 0 is empty; ids are the values in gen/level.c's tile grid.
TYPES = [
    (".", "empty", [0] * 16, 0),
    ("#", "full", [16] * 16, 0),
    ("H", "switch", [16] * 16, 0),                               # a network-switch block: solid like '#'
    ("/", "up45", [i + 1 for i in range(16)], 32),
    ("\\", "down45", [16 - i for i in range(16)], 256 - 32),
    ("a", "up22lo", [i // 2 + 1 for i in range(16)], 16),         # a 22.5-degree rise spans two tiles: a then b
    ("b", "up22hi", [i // 2 + 9 for i in range(16)], 16),
    ("c", "down22hi", [16 - i // 2 for i in range(16)], 256 - 16),  # a 22.5-degree fall: c then d
    ("d", "down22lo", [8 - i // 2 for i in range(16)], 256 - 16),
]

GLYPH_TO_ID = {t[0]: i for i, t in enumerate(TYPES)}
SOLID_GLYPHS = set(GLYPH_TO_ID) - {"."}


def mask(tid):
    return TYPES[tid][2]


def angle(tid):
    return TYPES[tid][3]


def solid_px(tid, x, y):
    """Is pixel (x, y) of this tile (0..15, y down) solid?"""
    return y >= TILE - TYPES[tid][2][x]
