"""ZIP's art limits (Task 2): every sprite is a 4 bpp sheet with at most 16 colours and a valid GBA size, every
background fits Butano's regular-BG limits, and the art build is reproducible from its sources."""
import hashlib
import json
import os
import subprocess
import sys

import pytest

from conftest import GAME_DIR

sys.path.insert(0, os.path.join(GAME_DIR, "tools", "art"))
import gbaimg  # noqa: E402

GFX = os.path.join(GAME_DIR, "graphics")
SPRITES = {"zip": (32, 32), "trail": (32, 16), "packet": (16, 16), "spring": (16, 16), "booster": (32, 32),
           "bug": (16, 16), "rack": (16, 32), "icons": (16, 16)}
BGS = ("hall", "title", "panel")
VALID = {(8, 8), (16, 16), (32, 32), (64, 64), (16, 8), (32, 8), (32, 16), (64, 32), (8, 16), (8, 32), (16, 32),
         (32, 64)}


def load(name):
    with open(os.path.join(GFX, name + ".json")) as f:
        info = json.load(f)
    size, px, pal = gbaimg.read_bmp(os.path.join(GFX, name + ".bmp"))
    return info, size, px, pal


@pytest.mark.parametrize("name", sorted(SPRITES))
def test_sprite_sheets_are_4bpp_with_valid_frames(name):
    info, (w, h), px, pal = load(name)
    assert info["type"] == "sprite" and info["bpp_mode"] == "bpp_4" and len(pal) == 16
    assert max(px) < 16
    assert (w, info["height"]) == SPRITES[name] and (w, info["height"]) in VALID and h % info["height"] == 0


@pytest.mark.parametrize("name", BGS)
def test_backgrounds_fit(name):
    info, (w, h), px, pal = load(name)
    assert info["type"] == "regular_bg" and info["bpp_mode"] == "bpp_4_manual"
    assert w % 256 == 0 and h % 256 == 0 and len(pal) <= 256
    assert gbaimg.tiles_of(px, w, h) <= 512
    for cy in range(0, h, 8):                  # every 8 x 8 cell uses one 16-colour bank
        for cx in range(0, w, 8):
            banks = {px[(cy + j) * w + cx + i] // 16 for j in range(8) for i in range(8) if px[(cy + j) * w + cx + i]}
            assert len(banks) <= 1, (name, cx, cy, banks)


def test_zip_has_every_pose():
    info, (w, h), _, _ = load("zip")
    import build_art
    assert h // info["height"] == len(build_art.ZIP_FRAMES) == 21


def test_the_art_build_is_reproducible(tmp_path):
    names = sorted(set(SPRITES) | set(BGS))
    before = {n: hashlib.sha1(open(os.path.join(GFX, n + ".bmp"), "rb").read()).hexdigest() for n in names}
    r = subprocess.run([sys.executable, os.path.join(GAME_DIR, "tools", "art", "build_art.py")], cwd=GAME_DIR,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    after = {n: hashlib.sha1(open(os.path.join(GFX, n + ".bmp"), "rb").read()).hexdigest() for n in names}
    assert before == after
