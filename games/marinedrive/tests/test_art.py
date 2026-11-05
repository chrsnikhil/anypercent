"""Art limits (plan Task 2): the Mode 7 track is one 1024 x 1024 affine map of at most 256 unique 8 bpp tiles and
one palette that leaves room for the skyline's; the rules' surface map is the one the art was painted from; the
circuit keeps a wall between its corridors; sprites are 4 bpp sheets of legal GBA sizes."""
import json
import os
import re
import sys

import numpy as np
import pytest
from PIL import Image

from conftest import GAME_DIR

sys.path.insert(0, os.path.join(GAME_DIR, "tools", "art"))
import track_data as D  # noqa: E402
import track_geom as G  # noqa: E402

GFX = os.path.join(GAME_DIR, "graphics")
# karts: 16 headings x 3 wheel poses (left, centre, right), frame = heading * 3 + pose
SPRITES = {"kart0": (32, 32, 48), "kart1": (32, 32, 48), "kart2": (32, 32, 48), "kart3": (32, 32, 48),
           "palm": (32, 64, 1), "gantry": (64, 64, 3), "spark": (8, 8, 3), "billboard": (64, 32, 1), "orb": (16, 16, 2),
           "place": (32, 16, 4), "speed": (32, 8, 9), "logo": (64, 32, 6),
           "count": (64, 32, 4), "banner": (64, 32, 6), "digits": (8, 16, 38), "puff": (16, 16, 6)}
SHAPES = {(8, 8), (16, 16), (32, 32), (64, 64), (16, 8), (32, 8), (32, 16), (64, 32), (8, 16), (8, 32), (16, 32),
          (32, 64)}


def cells_from_c():
    with open(os.path.join(GAME_DIR, "rules", "track_data.c")) as f:
        src = f.read()
    body = re.search(r"md_cells\[[^]]*\] = \{(.*?)\};", src, re.S).group(1)
    return np.array([int(v) for v in re.findall(r"\d+", body)], np.uint8).reshape(G.CELLS, G.CELLS)


@pytest.fixture(scope="module")
def track():
    im = Image.open(os.path.join(GFX, "track.bmp"))
    assert im.mode == "P"
    return np.array(im)


def test_track_is_one_1024_affine_map_of_at_most_256_tiles(track):
    assert track.shape == (1024, 1024)
    tiles = track.reshape(128, 8, 128, 8).transpose(0, 2, 1, 3).reshape(-1, 64)
    assert len(np.unique(tiles, axis=0)) <= 250          # grit rejects a full 256


def test_track_palette_leaves_the_skyline_a_slot(track):
    with open(os.path.join(GFX, "track.json")) as f:
        info = json.load(f)
    assert info["type"] == "affine_bg"
    count = int(info["colors_count"])
    assert count % 16 == 0 and count <= 224 and track.max() < count


def test_the_rules_surface_map_is_the_painted_one():
    pts, _ = G.centre_line()
    assert (cells_from_c() == D.surface_map(pts)).all(), "rules/track_data.c is stale: run tools/art/build_track.py"


def test_the_circuit_keeps_walls_between_corridors_and_off_the_edge():
    pts, total = G.centre_line()
    assert G.check(pts, total) == []
    cells = cells_from_c()
    assert (cells[0, :] == D.SURF_WALL).all() and (cells[-1, :] == D.SURF_WALL).all()
    assert (cells[:, 0] == D.SURF_WALL).all() and (cells[:, -1] == D.SURF_WALL).all()


def test_the_sea_is_transparent_and_the_road_is_not(track):
    cells = cells_from_c()
    road = np.kron(cells == D.SURF_ROAD, np.ones((8, 8), bool))
    assert (track[road] != 0).all(), "a road pixel uses the transparent index"
    assert (track == 0).mean() > 0.2, "little sea"


def test_boost_pads_sit_on_the_road():
    cells = cells_from_c()
    assert (cells == D.SURF_BOOST).sum() == 4 * len(D.PADS)


@pytest.mark.parametrize("name", sorted(SPRITES))
def test_sprite_sheets_are_4bpp_legal_shapes(name):
    w, h, frames = SPRITES[name]
    with open(os.path.join(GFX, name + ".json")) as f:
        info = json.load(f)
    im = Image.open(os.path.join(GFX, name + ".bmp"))
    assert info["type"] == "sprite" and info["height"] == h and info["bpp_mode"] == "bpp_4"
    assert (w, h) in SHAPES
    assert im.size == (w, h * frames)
    assert np.array(im).max() < 16


def test_skyline_is_one_16_colour_bg():
    im = Image.open(os.path.join(GFX, "skyline.bmp"))
    with open(os.path.join(GFX, "skyline.json")) as f:
        info = json.load(f)
    assert info["type"] == "regular_bg" and info["bpp_mode"] == "bpp_4"
    assert im.size == (512, 256) and np.array(im).max() < 16


def test_the_karts_differ_from_behind():
    """Seen from behind with the wheel straight (frame 1) the four karts' helmets have four clearly different
    colours."""
    means = []
    for k in range(4):
        im = Image.open(os.path.join(GFX, "kart%d.bmp" % k))
        idx = np.array(im)[32:64]
        pal = np.array(im.getpalette()[:48]).reshape(16, 3)
        px = pal[idx[idx > 0]].astype(float)
        bright = px[px.max(1) > 150]
        means.append(bright.mean(0))
    for a in range(4):
        for b in range(a + 1, 4):
            assert np.abs(means[a] - means[b]).max() > 40, (a, b, means[a], means[b])
