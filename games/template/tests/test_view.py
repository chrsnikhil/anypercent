"""The template's screens in the ROM: the title shows its text, and the ghost is drawn half transparent."""
import os

from PIL import Image

import arcade_test as T
from arcade_test import S
from conftest import OUT_DIR, START, load_keys, tuning


def screen(path):
    with open(path, "rb") as f:
        return Image.frombytes("RGBA", (240, 160), f.read()).convert("RGB")


def test_the_title_shows_text(rom):
    shot = os.path.join(OUT_DIR, "title.rgba")
    T.run_rom(rom, [0] * 30, shots=[(30, shot)])
    img = screen(shot)
    img.save(os.path.join(OUT_DIR, "title.png"))
    px = img.tobytes()
    lit = sum(1 for i in range(0, len(px), 3) if min(px[i:i + 3]) > 150)
    assert lit > 100, lit


def test_the_ghost_is_half_transparent(rom, game_id):
    gx, gy = 100, 40                                    # a ghost parked away from the dot
    save = T.save_with(game_id, ghost=S.ghost_bytes(game_id, 0, 4, [(gx, gy, 0, 0)] * 50))
    shot = os.path.join(OUT_DIR, "ghost.rgba")
    frames = [0] * 60 + [START] + [0] * 20
    rows = T.run_rom(rom, frames, watch=("g_dbg_ghost",), save_in=save, shots=[(len(frames), shot)])["watch"]
    assert rows[-2][0] == 1
    img = screen(shot)
    img.save(os.path.join(OUT_DIR, "ghost.png"))
    ghost = img.getpixel((gx + 4, gy + 4))              # the dot's fill colour, blended with the background
    bg = img.getpixel((gx + 20, gy + 4))
    dot = img.getpixel((16 + 4, 76 + 4))                # the player's dot at its start, drawn solid
    assert dot[0] > 200 and dot[1] > 180, dot
    assert bg[0] < 40 and bg[1] < 40, bg
    for c in range(3):
        lo, hi = sorted((bg[c], dot[c]))
        assert lo + (hi - lo) // 4 <= ghost[c] <= hi - (hi - lo) // 4 or hi - lo < 16, (ghost, dot, bg)


def test_the_player_stays_solid_over_its_ghost(rom, game_id):
    # The GBA blends a half-transparent sprite with the backgrounds only, never with another sprite, so a ghost
    # drawn in front of the dot would wash it out where they overlap. With the ghost parked exactly on the dot
    # (same place, for several frames running), the dot's box must look the same as with no ghost at all.
    frames = [0] * 60 + [START] + [0] * 20               # boot, start play, sit still at the start position
    x, y, size = tuning("START_X"), tuning("START_Y"), tuning("DOT_SIZE")
    save = T.save_with(game_id, ghost=S.ghost_bytes(game_id, 0, 4, [(x, y, 0, 0)] * 2000))
    hidden_path = os.path.join(OUT_DIR, "ghost_hidden.rgba")
    shown_path = os.path.join(OUT_DIR, "ghost_on_dot.rgba")
    T.run_rom(rom, frames, save_in=T.blank_save(), shots=[(len(frames), hidden_path)])
    rows = T.run_rom(rom, frames, watch=("g_dbg_ghost",), save_in=save, shots=[(len(frames), shown_path)])["watch"]
    assert rows[-1][0] == 1, "the ghost was not drawn"
    hidden, shown = screen(hidden_path), screen(shown_path)
    box = (x, y, x + size, y + size)
    assert list(hidden.crop(box).getdata()) == list(shown.crop(box).getdata()), \
        "the ghost shows through (or over) the dot"


def test_the_results_are_shown(rom):
    shot = os.path.join(OUT_DIR, "results.rgba")
    frames = load_keys("demo.keys") + [0] * 30
    T.run_rom(rom, frames, save_in=T.blank_save(), shots=[(len(frames), shot)])
    img = screen(shot)
    img.save(os.path.join(OUT_DIR, "results.png"))
    px = img.tobytes()
    assert sum(1 for i in range(0, len(px), 3) if min(px[i:i + 3]) > 150) > 200
