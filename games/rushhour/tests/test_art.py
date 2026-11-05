"""The generated art obeys Butano's formats and the GBA's limits (tools/art/build_art.py, build_level.py)."""
import glob
import json
import os
import struct

import pytest

from conftest import GAME_DIR

GFX = os.path.join(GAME_DIR, "graphics")
SHAPES = {(8, 8), (16, 16), (32, 32), (64, 64), (16, 8), (32, 8), (32, 16), (64, 32), (8, 16), (8, 32), (16, 32),
          (32, 64)}
SPRITES = ("hero", "bug", "chai", "orb", "shelf", "door", "flag", "hud", "glow")
BGS = ("skyline", "title", "card", "level_bg")
BG_BANKS = 16                       # 4 bpp palette banks on screen at once (level + skyline + card)


def read_bmp(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:2] == b"BM"
    offset = struct.unpack_from("<I", data, 10)[0]
    _, w, h, _, bpp, comp, _, _, _, used, _ = struct.unpack_from("<IiiHHIIiiII", data, 14)
    assert bpp == 8 and comp == 0, (path, bpp, comp)
    row = (w + 3) & ~3
    px = bytearray()
    for y in range(h - 1, -1, -1):
        px += data[offset + y * row:offset + y * row + w]
    return w, h, used, px


def item(name):
    with open(os.path.join(GFX, name + ".json")) as f:
        return json.load(f)


def test_every_graphic_has_its_json():
    bmps = {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(GFX, "*.bmp"))}
    jsons = {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(GFX, "*.json"))}
    assert bmps == jsons
    assert set(SPRITES) | set(BGS) <= bmps, sorted(set(SPRITES) | set(BGS) - bmps)


@pytest.mark.parametrize("name", SPRITES)
def test_sprites_fit_their_shapes(name):
    w, h, used, px = read_bmp(os.path.join(GFX, name + ".bmp"))
    info = item(name)
    assert info["type"] == "sprite" and info["bpp_mode"] == "bpp_4" and used == 16
    fh = info["height"]
    assert (w, fh) in SHAPES and h % fh == 0, (w, h, fh)
    assert max(px) < 16
    for f in range(h // fh):
        assert any(px[f * fh * w:(f + 1) * fh * w]), "frame %d of %s is empty" % (f, name)


@pytest.mark.parametrize("name", BGS)
def test_backgrounds_are_4bpp_banked_and_within_limits(name):
    w, h, used, px = read_bmp(os.path.join(GFX, name + ".bmp"))
    info = item(name)
    assert info["type"] == "regular_bg" and info["bpp_mode"] == "bpp_4_manual"
    assert w % 256 == 0 and h % 256 == 0 and w <= 16384 and h <= 16384
    assert used % 16 == 0 and used <= 256
    unique = set()
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            rows = [bytes(px[(ty + y) * w + tx:(ty + y) * w + tx + 8]) for y in range(8)]
            banks = {v // 16 for r in rows for v in r}
            assert len(banks) == 1, "tile (%d, %d) of %s mixes palette banks %s" % (tx, ty, name, banks)
            assert max(banks) < used // 16
            unique.add(tuple(rows))
    assert len(unique) <= 1024, "%s has %d unique tiles" % (name, len(unique))


def test_backgrounds_shown_together_fit_the_palette():
    banks = {n: read_bmp(os.path.join(GFX, n + ".bmp"))[2] // 16 for n in BGS}
    assert banks["level_bg"] + banks["skyline"] + banks["card"] <= BG_BANKS, banks
    assert banks["title"] + banks["card"] <= BG_BANKS, banks
