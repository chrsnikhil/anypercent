"""ZIP's screens in the ROM (Task 5): the title card, Zip drawn where the rules put him, the results card with
trophies, the ghost half transparent, and the player solid over his own ghost. Screenshots land in tests/out."""
import os
import struct

from PIL import Image

import arcade_test as T
from arcade_test import S
from conftest import OUT_DIR, ROUTE, START, load_keys

PLAY = [0] * 60 + [START, 0, START]


def screen(path):
    with open(path, "rb") as f:
        return Image.frombytes("RGBA", (240, 160), f.read()).convert("RGB")


def shoot(rom, frames, name, save_in=None, watch=()):
    shot = os.path.join(OUT_DIR, name + ".rgba")
    got = T.run_rom(rom, frames, watch=watch, save_in=T.blank_save() if save_in is None else save_in,
                    shots=[(len(frames), shot)])
    img = screen(shot)
    img.save(os.path.join(OUT_DIR, name + ".png"))
    return img, got["watch"]


def xy(v):
    return struct.unpack("<hh", struct.pack("<HH", v >> 16, v & 0xFFFF))


def cyan(p):
    return p[2] > 170 and p[1] > 120 and p[0] < 90


def count(img, box, pred):
    x0, y0, x1, y1 = box
    return sum(1 for y in range(max(0, y0), min(160, y1)) for x in range(max(0, x0), min(240, x1))
               if pred(img.getpixel((x, y))))


def test_the_title_card(rom):
    img, _ = shoot(rom, [0] * 70, "title")
    assert count(img, (0, 0, 240, 100), cyan) > 600, "the ZIP logo"
    assert count(img, (0, 100, 240, 160), lambda p: min(p) > 200) > 100, "the title text"


def test_the_how_to_card(rom):
    img, _ = shoot(rom, [0] * 60 + [START] + [0] * 20, "howto")
    assert count(img, (0, 0, 240, 160), lambda p: min(p) > 200) > 1000


def test_zip_is_drawn_where_the_rules_put_him(rom):
    frames = load_keys(ROUTE)[:420]
    img, rows = shoot(rom, frames, "midrun", watch=("g_dbg_player_xy", "g_dbg_cam_xy"))
    px, py = xy(rows[-1][0])
    cx, cy = xy(rows[-1][1])
    sx, sy = px - cx, py - cy
    assert 0 <= sx < 240 and 0 <= sy < 160, (sx, sy)
    assert count(img, (sx - 10, sy - 12, sx + 10, sy + 8), cyan) >= 25


def test_the_results_card(rom):
    img, _ = shoot(rom, load_keys(ROUTE) + [0] * 40, "results")
    assert count(img, (0, 0, 240, 40), lambda p: min(p) > 200) > 80, "DEMO DAY!"
    gold = count(img, (0, 60, 120, 160), lambda p: p[0] > 200 and p[1] > 150 and p[2] < 90)
    assert gold > 60, "the bot's four trophies are drawn gold (%d px)" % gold


def start_xy(lib):
    return T.pc_player(lib, PLAY)[-1]


def test_the_ghost_is_half_transparent(rom, lib, game_id):
    x, y = start_xy(lib)
    gx, gy = x + 56, y - 24                          # parked in the air ahead of Zip
    ghost = S.ghost_bytes(game_id, 0, 2, [(gx, gy, 0, 0x80)] * 200)
    frames = PLAY + [0] * 30
    with_g, rows = shoot(rom, frames, "ghost", save_in=T.save_with(game_id, ghost=ghost),
                         watch=("g_dbg_ghost", "g_dbg_cam_xy"))
    without, _ = shoot(rom, frames, "noghost")
    assert rows[-1][0] == 1, "the ghost was not drawn"
    cx, cy = xy(rows[-1][1])
    box = (gx - cx - 10, gy - cy - 12, gx - cx + 10, gy - cy + 8)
    changed = [(with_g.getpixel((i, j)), without.getpixel((i, j)))
               for j in range(box[1], box[3]) for i in range(box[0], box[2])
               if with_g.getpixel((i, j)) != without.getpixel((i, j))]
    assert len(changed) > 60, len(changed)
    blended = [g for g, b in changed if b[2] < g[2] < 200 and g[0] < 100]
    assert len(blended) > 20, "the ghost's body is not half transparent"
    assert not any(cyan(g) and g[2] > 220 for g, _ in changed), "a ghost pixel is drawn solid"


def test_the_player_stays_solid_over_its_ghost(rom, lib, game_id):
    x, y = start_xy(lib)
    ghost = S.ghost_bytes(game_id, 0, 2, [(x, y, 0, 0x80)] * 200)
    frames = PLAY + [0] * 30
    over, rows = shoot(rom, frames, "ghost_on_player", save_in=T.save_with(game_id, ghost=ghost),
                       watch=("g_dbg_ghost", "g_dbg_cam_xy"))
    alone, _ = shoot(rom, frames, "player_alone")
    assert rows[-1][0] == 1, "the ghost was not drawn"
    cx, cy = xy(rows[-1][1])
    sx, sy = x - cx, y - cy
    body = [(i, j) for j in range(sy - 12, sy + 12) for i in range(sx - 12, sx + 12)
            if 0 <= i < 240 and 0 <= j < 160 and cyan(alone.getpixel((i, j)))]
    assert len(body) > 40, len(body)
    differ = [(i, j) for i, j in body if over.getpixel((i, j)) != alone.getpixel((i, j))]
    assert not differ, "the ghost shows through the player at %s" % differ[:5]
