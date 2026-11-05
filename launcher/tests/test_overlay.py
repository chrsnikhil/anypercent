"""The on-screen controls overlay (device/overlay/make_overlay.py): RetroArch overlay art and hitboxes."""
import importlib.util
import os

import pytest
from PIL import Image

from conftest import LAUNCHER_DIR

SCRIPT = os.path.join(os.path.dirname(LAUNCHER_DIR), "device", "overlay", "make_overlay.py")
W, H = 800, 480
GAME = (40, 760)                                   # a GBA game's picture: 720 px wide, centred


@pytest.fixture(scope="module")
def mo():
    spec = importlib.util.spec_from_file_location("make_overlay", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def made(mo, tmp_path_factory):
    out = tmp_path_factory.mktemp("overlay")
    mo.write(str(out))
    cfg = {}
    for line in (out / "gamepad.cfg").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"')
    with Image.open(out / "gamepad.png") as img:
        return out, cfg, img.convert("RGBA")


def descs(cfg):
    """(buttons, cx, cy, shape, rx, ry) in panel pixels, from the normalized cfg."""
    out = []
    for i in range(int(cfg["overlay0_descs"])):
        name, x, y, shape, rx, ry = [s.strip() for s in cfg[f"overlay0_desc{i}"].split(",")]
        out.append((frozenset(name.split("|")), float(x) * W, float(y) * H, shape, float(rx) * W, float(ry) * H))
    return out


def drawn(alpha):
    """Pixels of an alpha channel that are not fully transparent."""
    return alpha.size[0] * alpha.size[1] - alpha.histogram()[0]


def pressed(cfg, x, y):
    """What RetroArch presses for a finger at (x, y): every desc whose hitbox holds it."""
    hit = set()
    for names, cx, cy, shape, rx, ry in descs(cfg):
        dx, dy = (x - cx) / rx, (y - cy) / ry
        if (shape == "rect" and abs(dx) <= 1 and abs(dy) <= 1) or (shape == "radial" and dx * dx + dy * dy <= 1):
            hit |= names
    return hit


def test_one_full_screen_normalized_overlay(made):
    out, cfg, img = made
    assert cfg["overlays"] == "1" and cfg["overlay0_overlay"] == "gamepad.png"
    assert cfg["overlay0_full_screen"] == "true" and cfg["overlay0_normalized"] == "true"
    assert img.size == (W, H)


def test_every_gba_button_is_there(made):
    _, cfg, _ = made
    names = set().union(*(d[0] for d in descs(cfg)))
    assert names == {"up", "down", "left", "right", "a", "b", "l", "r", "start", "select"}


def test_hitboxes_stay_on_screen(made):
    _, cfg, _ = made
    for names, cx, cy, shape, rx, ry in descs(cfg):
        assert shape in ("rect", "radial") and rx > 0 and ry > 0, names
        assert -1 <= cx - rx and cx + rx <= W + 1 and -1 <= cy - ry and cy + ry <= H + 1, names


def test_dpad_bottom_left_with_diagonals_and_a_dead_centre(mo, made):
    _, cfg, _ = made
    x, y, step = mo.DPAD[0], mo.DPAD[1], mo.DPAD_CELL
    assert x < 160 and y > H / 2
    assert pressed(cfg, x, y) == set()
    assert pressed(cfg, x + step, y) == {"right"} and pressed(cfg, x - step, y) == {"left"}
    assert pressed(cfg, x, y - step) == {"up"} and pressed(cfg, x, y + step) == {"down"}
    assert pressed(cfg, x + step, y - step) == {"up", "right"}
    assert pressed(cfg, x - step, y + step) == {"down", "left"}


def test_a_and_b_bottom_right_a_further_right_and_higher(mo, made):
    _, cfg, _ = made
    ax, ay = mo.BUTTON_A
    bx, by = mo.BUTTON_B
    assert ax > bx > W / 2 and ay < by and ay > H / 2
    assert pressed(cfg, ax, ay) == {"a"} and pressed(cfg, bx, by) == {"b"}


def test_shoulders_on_top_start_select_at_the_bottom_centre(mo, made):
    _, cfg, _ = made
    assert pressed(cfg, 30, 15) == {"l"} and pressed(cfg, W - 30, 15) == {"r"}
    sx, sy = mo.START
    ex, ey = mo.SELECT
    assert pressed(cfg, sx, sy) == {"start"} and pressed(cfg, ex, ey) == {"select"}
    assert ex < W / 2 < sx and sy > H - 40
    assert pressed(cfg, W / 2, H / 2) == set()                   # the middle of the game is never a button


def test_each_button_is_drawn_where_it_is_hit_and_the_middle_is_clear(mo, made):
    _, cfg, img = made
    for xy in (mo.BUTTON_A, mo.BUTTON_B, mo.START, mo.SELECT, (30, 15), (W - 30, 15),
               (mo.DPAD[0] + mo.DPAD_CELL, mo.DPAD[1])):
        assert img.getpixel((int(xy[0]), int(xy[1])))[3] > 0, xy
    assert img.getpixel((W // 2, H // 2))[3] == 0


def test_covers_little_of_the_game(made):
    _, _, img = made
    alpha = img.crop((GAME[0], 0, GAME[1], H)).getchannel("A")
    covered = drawn(alpha) / ((GAME[1] - GAME[0]) * H)
    assert covered < 0.12, covered


def test_the_checked_in_files_are_current(mo, made):
    out, _, _ = made
    here = os.path.dirname(SCRIPT)
    with open(os.path.join(here, "gamepad.cfg")) as f:
        assert (out / "gamepad.cfg").read_text() == f.read()
    with Image.open(out / "gamepad.png") as a, Image.open(os.path.join(here, "gamepad.png")) as b:
        made_alpha, kept_alpha = a.convert("RGBA").getchannel("A"), b.convert("RGBA").getchannel("A")
    assert kept_alpha.size == made_alpha.size
    n = [drawn(im) for im in (made_alpha, kept_alpha)]
    assert abs(n[0] - n[1]) <= 0.01 * n[0]            # the same art (font rendering may differ a little)
