"""Renders ZIP's level background (graphics/level.bmp, a big regular BG, 4 bpp with palette banks per 8 x 8 cell)
from the parsed level: terrain from the collision masks, then decor, the loop ring and the finish. Called by
build_level.py; writes art/gen/level_preview.png (the whole level, half size) as well."""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(GAME, "tools", "art"))
import level_art as LA  # noqa: E402
from gbaimg import ArtError, q15, tiles_of, write_bmp, write_json  # noqa: E402

GFX = os.path.join(GAME, "graphics")
PREVIEW = os.path.join(GAME, "art", "gen")
TILE_LIMIT = 1024


def compose_image(grid, styles, things, decor):
    h, w = len(grid), len(grid[0])
    img = LA.render_terrain(grid, styles)
    for x, y, kind, arg in things:
        if kind == 8:                                           # the loop: ring centre above the floor
            LA.draw_loop_ring(img, x, y - LA_LOOP_RS, LA_LOOP_RS)
        elif kind == 7:                                         # the finish arch over the line
            LA.stamp(img, LA.deco_finish(96), x - 24, y)
        elif kind == 5:                                         # spikes: drawn in the level
            LA.stamp(img, spikes_art(), x - 8, y)
    arts = {"r": LA.deco_rack(), "l": LA.deco_lamp(), "n": LA.deco_sign(), "K": LA.deco_laptop(),
            "D": LA.deco_screen()}
    for glyph, col, row in decor:
        art = arts[glyph]
        LA.stamp(img, art, col * 16, row * 16 + 16)
    return img


LA_LOOP_RS = 64


def spikes_art():
    """Kenney Pixel Platformer's floor spikes (tiles row 3, column 8), bottom aligned on a 16 x 16 cell."""
    t = LA.kenney("pixel-platformer/tilemap_packed.png", 8, 3)
    out = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    t = t.crop((0, 0, min(16, t.width), min(16, t.height)))
    out.alpha_composite(t, ((16 - t.width) // 2, 16 - t.height))
    return out


def to_banks(img):
    """RGBA -> bpp_4_manual indices: each 8 x 8 cell takes the bank (LA.BANKS) that matches it best; cells are
    memoised by content, so the huge, repetitive level converts quickly."""
    w, h = img.size
    banks = [[q15(c) for c in b] for b in LA.BANKS]
    src = img.tobytes()
    px = bytearray(w * h)
    memo = {}
    nearest = [{} for _ in banks]
    mismatched = 0
    for cy in range(0, h, 8):
        for cx in range(0, w, 8):
            cell = b"".join(src[((cy + j) * w + cx) * 4:((cy + j) * w + cx + 8) * 4] for j in range(8))
            got = memo.get(cell)
            if got is None:
                best = None
                for bi, bank in enumerate(banks):
                    err, idx = 0, bytearray()
                    for k in range(64):
                        r, g, b, a = cell[k * 4:k * 4 + 4]
                        if a < 128:
                            idx.append(0)
                            continue
                        c = q15((r, g, b))
                        hit = nearest[bi].get(c)
                        if hit is None:
                            i = min(range(1, 16), key=lambda i: sum((bank[i][m] - c[m]) ** 2 for m in range(3)))
                            hit = (i, sum((bank[i][m] - c[m]) ** 2 for m in range(3)))
                            nearest[bi][c] = hit
                        err += hit[1]
                        idx.append(bi * 16 + hit[0])
                    if best is None or err < best[0]:
                        best = (err, bytes(v if v % 16 else 0 for v in idx))
                    if err == 0:
                        break
                got = best
                memo[cell] = got
            if got[0]:
                mismatched += 1
            for j in range(8):
                px[(cy + j) * w + cx:(cy + j) * w + cx + 8] = got[1][j * 8:j * 8 + 8]
    return px, mismatched


def build(grid, styles, things, decor):
    img = compose_image(grid, styles, things, decor)
    w, h = img.size
    px, mismatched = to_banks(img)
    n = tiles_of(px, w, h)
    if n > TILE_LIMIT:
        raise ArtError("the level background has %d unique tiles (limit %d)" % (n, TILE_LIMIT))
    flat = [q15(c) for b in LA.BANKS for c in b]
    write_bmp(os.path.join(GFX, "level.bmp"), (w, h), px, flat)
    write_json(os.path.join(GFX, "level.json"), {"type": "regular_bg", "bpp_mode": "bpp_4_manual",
                                                 "colors_count": len(flat), "big": True})
    os.makedirs(PREVIEW, exist_ok=True)
    back = Image.new("RGBA", img.size, (20, 26, 48, 255))
    back.alpha_composite(img)
    back.convert("RGB").resize((w // 2, h // 2), Image.NEAREST).save(os.path.join(PREVIEW, "level_preview.png"))
    print("level background: %d x %d px, %d unique tiles, %d cells off-palette" % (w, h, n, mismatched))
    return n
