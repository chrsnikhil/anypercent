"""level/level.txt -> rules/level.h + rules/level_data.c (the collision grid and the entity table the rules use)
and graphics/level_bg.bmp + .json (the Butano regular background drawn under the sprites, auto-tiled per zone).

Run from the game directory: /opt/arca-sandbox/venv/bin/python tools/level/build_level.py"""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(GAME, "tools", "art"))
import build_art  # noqa: E402
import gba4  # noqa: E402

LEVEL_TXT = os.path.join(GAME, "level", "level.txt")
RULES = os.path.join(GAME, "rules")
GFX = os.path.join(GAME, "graphics")
TILE = 16
ROWS = 12

COLLISION = {".": 0, "#": 1, "X": 1, "H": 1, "=": 2, "^": 3}
DECOR = "|tsl"
ENTITIES = {"b": "E_BUG", "c": "E_CHAI", "o": "E_ORB", "k": "E_CHECK", "D": "E_DOOR"}


class LevelError(Exception):
    pass


def parse(path=LEVEL_TXT):
    """(rows, zones): rows are the 12 grid lines; zones [(first column, name)] in order."""
    rows, zones = [], []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith(";zone"):
                _, col, name = line.split()
                zones.append((int(col), name))
            elif line.startswith(";") or not line.strip():
                continue
            else:
                rows.append(line)
    if len(rows) != ROWS:
        raise LevelError("%d rows, want %d" % (len(rows), ROWS))
    w = len(rows[0])
    for r in rows:
        if len(r) != w:
            raise LevelError("ragged rows")
        for ch in r:
            if ch not in COLLISION and ch not in DECOR and ch not in ENTITIES and ch != "P":
                raise LevelError("unknown cell %r" % ch)
    if not zones or zones[0][0] != 0:
        raise LevelError("the first ;zone must start at column 0")
    return rows, zones


def zone_of(zones, c):
    name = zones[0][1]
    for col, n in zones:
        if c >= col:
            name = n
    return name


def cell(rows, c, r):
    if 0 <= r < len(rows) and 0 <= c < len(rows[0]):
        return rows[r][c]
    return "."


def collision(rows):
    return [[COLLISION.get(ch, 0) for ch in row] for row in rows]


def entities(rows):
    """[(type, tx, ty)] in column order, and the start (tx, ty)."""
    ents, start = [], None
    for c in range(len(rows[0])):
        for r in range(ROWS):
            ch = rows[r][c]
            if ch in ENTITIES:
                ents.append((ENTITIES[ch], c, r))
            elif ch == "P":
                if start:
                    raise LevelError("two starts")
                start = (c, r)
    if not start:
        raise LevelError("no start")
    if sum(1 for e in ents if e[0] == "E_DOOR") != 1:
        raise LevelError("exactly one door")
    return ents, start


def tile_name(rows, zones, c, r):
    ch = rows[r][c]
    z = zone_of(zones, c)
    v = (c * 7 + r * 3) % 4
    if ch == "#":
        return "%s_%s%d" % (z, "fill" if cell(rows, c, r - 1) == "#" else "top", v)
    if ch == "X":
        return "crate_" + z
    if ch == "=":
        left, right = cell(rows, c - 1, r) == "=", cell(rows, c + 1, r) == "="
        return "oneway_%s_%s" % (z, "m" if left and right else "l" if right else "r" if left else "m")
    if ch == "H":
        if cell(rows, c, r - 1) != "H":
            return "train_roof"
        if cell(rows, c, r + 1) != "H":
            return "train_under"
        if cell(rows, c, r - 2) != "H":
            return "train_window"
        return "train_body"
    if ch == "^":
        return "spike"
    if ch == "|":
        return "pole"
    if ch == "t":
        return "plant%d" % (c % 3)
    if ch == "s":
        return "sign"
    if ch == "l":
        return "lamp"
    return None


def render(rows, zones):
    """The level as an RGBA image, padded to multiples of 256 (Butano's big-map rule)."""
    tiles = build_art.tileset()
    w = len(rows[0]) * TILE
    img = Image.new("RGBA", ((w + 255) // 256 * 256, 256), (0, 0, 0, 0))
    for r in range(ROWS):
        for c in range(len(rows[0])):
            name = tile_name(rows, zones, c, r)
            if name is None:
                continue
            t = tiles[name]
            if name == "train_roof":
                t = t.copy()
                px = t.load()
                ends = [x for x, side in ((0, -1), (15, 1)) if cell(rows, c + side, r) != "H"]
                for x0 in ends:
                    for (dx, dy) in ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (2, 0)):
                        px[abs(x0 - dx) if x0 == 0 else x0 - dx, dy + 2] = (0, 0, 0, 0)
            img.alpha_composite(t, (c * TILE, r * TILE))
            if name == "lamp" and cell(rows, c, r - 1) == ".":
                img.alpha_composite(tiles["lamp_top"], (c * TILE, (r - 1) * TILE))
    return img


def write_rules(rows, zones):
    grid = collision(rows)
    ents, start = entities(rows)
    w = len(rows[0])
    head = ["/* GENERATED by tools/level/build_level.py from level/level.txt: do not edit. */",
            "#ifndef RH_LEVEL_H", "#define RH_LEVEL_H", "#include \"world.h\"",
            "#define LEVEL_W %d" % w, "#define LEVEL_H %d" % ROWS, "#define LEVEL_N_ENTS %d" % len(ents),
            "#define LEVEL_START_TX %d" % start[0], "#define LEVEL_START_TY %d" % start[1],
            "extern const uint8_t LEVEL_TILES[LEVEL_W * LEVEL_H];",
            "extern const rh_level_ent LEVEL_ENTS[LEVEL_N_ENTS];", "#endif", ""]
    with open(os.path.join(RULES, "level.h"), "w") as f:
        f.write("\n".join(head))
    body = ["/* GENERATED by tools/level/build_level.py from level/level.txt: do not edit. */",
            "#include \"level.h\"", "", "const uint8_t LEVEL_TILES[LEVEL_W * LEVEL_H] = {"]
    for row in grid:
        body.append("    " + ",".join(str(v) for v in row) + ",")
    body += ["};", "", "const rh_level_ent LEVEL_ENTS[LEVEL_N_ENTS] = {"]
    for kind, tx, ty in ents:
        body.append("    {%s, %d, %d}," % (kind, tx, ty))
    body += ["};", ""]
    with open(os.path.join(RULES, "level_data.c"), "w") as f:
        f.write("\n".join(body))
    return ents, start


def build():
    rows, zones = parse()
    ents, start = write_rules(rows, zones)
    banks = gba4.write_bg(GFX, "level_bg", render(rows, zones), build_art.LEVEL_BANKS, build_art.SKY)
    counts = {}
    for kind, _, _ in ents:
        counts[kind] = counts.get(kind, 0) + 1
    return {"width": len(rows[0]), "start": start, "entities": counts, "banks": banks}


if __name__ == "__main__":
    print(build())
