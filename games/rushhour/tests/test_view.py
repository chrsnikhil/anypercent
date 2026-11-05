"""RUSH HOUR's screens in the ROM: the title, the how-to card, the hero drawn where the rules put it, pause, the
results card, and the ghost (translucent, and always behind the hero)."""
import os
import struct

from PIL import Image

import arcade_test as T
from arcade_test import S
from conftest import OUT_DIR, SELECT, START, load_keys, typed

TITLE_FRAMES = [0] * 60
HOWTO = [0] * 60 + [START] + [0] * 30


def screen(path):
    with open(path, "rb") as f:
        return Image.frombytes("RGBA", (240, 160), f.read()).convert("RGB")


def shot(rom, frames, name, save=None, watch=()):
    path = os.path.join(OUT_DIR, name + ".rgba")
    got = T.run_rom(rom, frames, watch=watch, save_in=T.blank_save() if save is None else save,
                    shots=[(len(frames), path)])
    img = screen(path)
    img.save(os.path.join(OUT_DIR, name + ".png"))
    return img, got["watch"]


def lit(img, threshold=150):
    px = img.tobytes()
    return sum(1 for i in range(0, len(px), 3) if min(px[i:i + 3]) > threshold)


def colours(img):
    return len(set(img.getdata()))


def xy(v):
    return struct.unpack("<hh", struct.pack("<HH", v >> 16, v & 0xFFFF))


def orange(p):
    return p[0] > 200 and 80 <= p[1] <= 200 and p[2] < 110


def test_the_title_card(rom):
    img, _ = shot(rom, TITLE_FRAMES, "title")
    assert lit(img) > 300 and colours(img) > 12
    top = img.crop((0, 0, 240, 60))
    assert sum(1 for p in top.getdata() if p[0] > 200 and p[1] > 160 and p[2] < 120) > 400, "no RUSH HOUR lettering"


def test_the_howto_card(rom):
    img, _ = shot(rom, HOWTO, "howto")
    border = img.getpixel((12, 60))
    assert border[1] > 200 and border[2] < 100, border               # the card's lime frame
    assert lit(img.crop((20, 12, 220, 150))) > 600, "the how-to text is missing"


def test_the_hero_is_drawn_where_the_rules_put_it(rom):
    keys = load_keys("full_run.keys")
    for n, frame in enumerate((400, 1500, 3000, 4400)):
        img, rows = shot(rom, keys[:frame], "play%d" % n, watch=("g_dbg_player_xy", "g_dbg_camera_xy"))
        (px, py), (cx, cy) = xy(rows[-1][0]), xy(rows[-1][1])
        sx, sy = px + 6 - cx, py + 7 - cy
        assert 0 <= sx < 240 and 0 <= sy < 160, (sx, sy)
        box = [img.getpixel((x, y)) for x in range(max(0, sx - 6), min(240, sx + 6))
               for y in range(max(0, sy - 8), min(160, sy + 6))]
        assert sum(1 for p in box if orange(p)) >= 8, "no hero at (%d, %d) on frame %d" % (sx, sy, frame)


def test_pause_dims_the_level_and_shows_the_menu(rom):
    keys = load_keys("full_run.keys")[:300]
    playing, _ = shot(rom, keys, "unpaused")
    paused, _ = shot(rom, keys + [START] + [0] * 20, "paused")
    assert sum(paused.getpixel((x, 150))[2] for x in range(0, 240, 8)) < \
        sum(playing.getpixel((x, 150))[2] for x in range(0, 240, 8)) * 0.7, "the level is not dimmed"
    assert lit(paused.crop((60, 50, 180, 110))) > 100, "no pause menu text"


def test_giving_up_shows_the_results(rom):
    img, _ = shot(rom, [0] * 60 + [START, 0, START, 0, START, 0, SELECT] + [0] * 30, "gave_up")
    assert lit(img.crop((20, 12, 220, 150))) > 300


def test_the_results_card_at_the_end_of_the_route(rom):
    img, _ = shot(rom, load_keys("full_run.keys") + [0] * 40, "results")
    border = img.getpixel((12, 60))
    assert border[1] > 200 and border[2] < 100, border
    assert lit(img.crop((20, 12, 220, 150))) > 400
    gold = sum(1 for p in img.crop((20, 12, 220, 150)).getdata() if p[0] > 200 and p[1] > 160 and p[2] < 120)
    assert gold > 150, "no gold title / trophy lines"


def ghost_save(rom, lib, game_id, frames, dx=0):
    """A ghost track parked on the ROM's player after `frames` (shifted dx px): every sample is that pose. The ROM
    drops its first few frames while it boots, so the PC rules replay the frames the ROM really stepped."""
    import ctypes
    rows = T.run_rom(rom, frames, watch=("g_dbg_steps",))["watch"]
    skipped = len(frames) - rows[-1][0]
    lib = typed(lib)
    lib.game_init(0)
    for k in frames[skipped:]:
        lib.game_step(k)
    g = T.Ghost()
    lib.game_ghost(ctypes.byref(g))
    pts = [(g.x + dx, g.y, g.angle, g.flags)] * 2000
    return T.save_with(game_id, ghost=S.ghost_bytes(game_id, 0, 4, pts)), (g.x, g.y)


def test_the_hero_stays_solid_over_its_ghost(rom, lib, game_id):
    frames = load_keys("full_run.keys")[:700] + [0] * 40      # standing still: the screen lags the rules a frame
    save, _ = ghost_save(rom, lib, game_id, frames)
    alone, _ = shot(rom, frames, "no_ghost")
    over, rows = shot(rom, frames, "ghost_under_hero", save=save, watch=("g_dbg_ghost",))
    assert rows[-1][0] == 1, "the ghost was not drawn"
    assert list(alone.getdata()) == list(over.getdata()), "the ghost shows through (or over) the hero"


def test_the_ghost_is_half_transparent(rom, lib, game_id):
    frames = load_keys("full_run.keys")[:700] + [0] * 40
    save, (gx, gy) = ghost_save(rom, lib, game_id, frames, dx=-40)
    img, rows = shot(rom, frames, "ghost", save=save, watch=("g_dbg_ghost", "g_dbg_camera_xy", "g_dbg_player_xy"))
    alone, _ = shot(rom, frames, "no_ghost")
    assert rows[-1][0] == 1
    cx, cy = xy(rows[-1][1])
    sx, sy = gx - 40 + 6 - cx, gy + 7 - cy
    changed = [(img.getpixel((x, y)), alone.getpixel((x, y))) for x in range(sx - 6, sx + 6)
               for y in range(sy - 8, sy + 6) if img.getpixel((x, y)) != alone.getpixel((x, y))]
    assert len(changed) > 20, "no ghost drawn"
    solid = sum(1 for g, _ in changed if orange(g))
    assert solid < len(changed) // 4, "the ghost is drawn solid, not blended"


def test_hits_deaths_and_respawns_keep_rom_and_pc_in_step(rom, elf, lib):
    """A clumsy run (hopping right into bugs, spikes and pits) steps once a frame with the PC's hashes."""
    from conftest import A, RIGHT
    frames = [0] * 60 + [START, 0, START, 0] + [RIGHT | (A if i % 40 < 20 else 0) for i in range(1500)]
    frames += [START, 0, SELECT] + [0] * 30
    rh = typed(lib)
    rh.game_init(0)
    hurt = died = False
    for k in frames:
        rh.game_step(k)
        hurt = hurt or rh.rules_invuln() > 0
        died = died or rh.rules_dead() > 0
    assert hurt and died, "the clumsy run should get hurt and die"
    assert T.assert_rom_matches_pc(rom, elf, lib, frames) > 1000
