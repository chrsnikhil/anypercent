"""Art limits: the generated view data (genart/segf_art.c) and the Butano sprites (graphics/) fit what the view and
the GBA expect, and the level passes its validator."""
import os
import re
import subprocess
import sys

from PIL import Image

from conftest import GAME_DIR

GEN = os.path.join(GAME_DIR, "genart", "segf_art.c")
HDR = os.path.join(GAME_DIR, "genart", "segf_art.h")


def arrays():
    text = open(GEN).read()
    out = {}
    for m in re.finditer(r"const \w+ (\w+)(\[[^=]*\])[^=]*= \{(.*?)\n\};", text, re.S):
        out[m.group(1)] = [int(v) for v in re.findall(r"-?\d+", m.group(3))]
    return out


def define(name):
    return int(re.search(r"#define %s (\d+)" % name, open(HDR).read()).group(1))


def test_palette_is_four_light_levels_of_64_colours():
    pal = arrays()["segf_palette"]
    assert len(pal) == 256 and all(0 <= c < 0x8000 for c in pal)
    for base in range(64):
        rgb = [((pal[lv * 64 + base] >> s) & 31) for lv in range(4) for s in (0, 5, 10)]
        for lv in range(3):                                  # each level no brighter than the one before
            assert all(rgb[(lv + 1) * 3 + k] <= rgb[lv * 3 + k] for k in range(3)), base
    assert len(arrays()["segf_card_palette"]) == 256


def test_textures_and_billboards_fit_the_base_colours():
    a = arrays()
    n, size = define("SEGF_TEX_COUNT"), define("SEGF_TEX_SIZE")
    assert size == 64 and n == 12
    tex = a["segf_textures"]
    assert len(tex) == n * size * size
    assert all(1 <= v < 64 for v in tex), "a texture uses index 0 or a shaded index (the view ORs the light level in)"
    bugs = a["segf_bugs"]
    assert len(bugs) == define("SEGF_BUG_FRAMES") * size * size and all(0 <= v < 64 for v in bugs)
    for f in range(define("SEGF_BUG_FRAMES")):
        frame = bugs[f * 4096:(f + 1) * 4096]
        assert 300 < sum(1 for v in frame if v) < 4096, "frame %d is empty or has no transparency" % f
    assert len(a["segf_hud"]) == 120 * 32 and len(a["segf_bg_column"]) == 128


def test_sprites_are_4bpp_and_small():
    total = 0
    for name, (w, h) in {"blaster": (64, 128), "phantom": (32, 32), "blip": (8, 8), "crosshair": (8, 8)}.items():
        im = Image.open(os.path.join(GAME_DIR, "graphics", name + ".bmp"))
        assert im.mode == "P" and im.size == (w, h), (name, im.size)
        assert max(im.tobytes()) < 16, name
        total += w * h // 64
    assert total <= 512 - 64 - 128, "%d sprite tiles of art leave too little for text" % total


def test_the_level_validates():
    r = subprocess.run([sys.executable, os.path.join(GAME_DIR, "tools", "level", "build_level.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
