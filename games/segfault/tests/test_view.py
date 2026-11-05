"""SEGFAULT's screens in the ROM: the title, the raycast view with its HUD, the ghost's translucent phantom, the
results, the frame rate the plan asks for (30 views a second on average in play, never more than 3 frames for
one view) and the sprite-tile budget
of a bitmap mode (only the upper 512 sprite tiles exist; keep 64 spare)."""
import os

from PIL import Image

import arcade_test as T
from arcade_test import S
from conftest import OUT_DIR, START, UP, load_keys

PLAY = [0] * 60 + [START, 0, START, 0]          # boot, title, how-to: in play at the start, facing north


def screen(path):
    with open(path, "rb") as f:
        return Image.frombytes("RGBA", (240, 160), f.read()).convert("RGB")


def colours(img):
    b = img.tobytes()
    return {b[i:i + 3] for i in range(0, len(b), 3)}


def lit(img, box=(0, 0, 240, 160), level=150):
    px = img.crop(box).tobytes()
    return sum(1 for i in range(0, len(px), 3) if min(px[i:i + 3]) > level)


def shot(rom, frames, name, save_in=None, watch=()):
    path = os.path.join(OUT_DIR, name + ".rgba")
    got = T.run_rom(rom, frames, save_in=T.blank_save() if save_in is None else save_in, watch=watch,
                    shots=[(len(frames), path)])
    img = screen(path)
    img.save(os.path.join(OUT_DIR, name + ".png"))
    return img, got["watch"]


def test_the_title_shows_text(rom):
    img, _ = shot(rom, [0] * 30, "title")
    assert lit(img) > 400


def test_the_view_draws_walls_floor_and_the_hud(rom):
    img, _ = shot(rom, PLAY + [0] * 20, "view")
    view = img.crop((0, 0, 240, 128))
    assert len(colours(view)) > 20, "the 3D view is flat"
    top, bottom = img.getpixel((120, 2)), img.getpixel((120, 125))
    assert top != bottom, "ceiling and floor share a colour"
    hud = img.crop((0, 128, 240, 160))
    assert len(colours(hud)) > 6 and lit(img, (0, 128, 240, 160)) > 20, "no HUD numbers"
    # the doubled columns: every even/odd screen column pair is identical in the view
    assert all(img.getpixel((2 * x, y)) == img.getpixel((2 * x + 1, y)) for x in range(40) for y in (30, 64, 110))


def test_the_ghost_phantom_is_half_transparent(rom, game_id):
    start = (5 * 16 + 8, 39 * 16 + 8)                    # three tiles ahead of the start, in the start office
    frames = PLAY + [0] * 20
    save = T.save_with(game_id, ghost=S.ghost_bytes(game_id, 0, 4, [(start[0], start[1], 0, 0x80)] * 60))
    with_ghost, rows = shot(rom, frames, "ghost", save_in=save, watch=("g_dbg_ghost",))
    assert rows[-1][0] == 1
    without, _ = shot(rom, frames, "noghost")
    changed = [(x, y) for x in range(96, 144) for y in range(40, 110)
               if with_ghost.getpixel((x, y)) != without.getpixel((x, y))]
    assert len(changed) > 60, "the phantom was not drawn in front of the player"
    # translucent: the changed pixels still carry the view behind them (not one flat sprite colour)
    assert len({without.getpixel(p) for p in changed}) > 3
    assert len({with_ghost.getpixel(p) for p in changed}) > 3


def test_wall_textures_are_not_mirrored(rom):
    """The route ends facing the Chainlink terminal from a step away: its "REBOOT" label must read left to right.
    The first glyph, R, has a full-height left stroke; mirrored, the first glyph would be a T (one pixel high)."""
    keys = load_keys("full_run.keys")
    img, _ = shot(rom, keys[:-2], "terminal")
    w, h = img.size
    bright = [[(lambda p: p[0] > 110 and p[1] > 180 and p[2] > 230)(img.getpixel((x, y))) for x in range(w)]
              for y in range(128)]
    rows = [y for y in range(128) if any(bright[y])]
    groups, cur = [], [rows[0]]
    for y in rows[1:]:
        if y - cur[-1] > 2:
            groups.append(cur)
            cur = []
        cur.append(y)
    groups.append(cur)
    text = groups[-1]                                   # the label: the lowest bright band (the hexagons are above)
    assert len(text) >= 10, groups
    left = min(x for y in text for x in range(w) if bright[y][x])
    stroke = sum(1 for y in text if bright[y][left] or bright[y][left + 1])
    assert stroke >= 0.6 * len(text), "the terminal's label is mirrored (first glyph %d of %d rows high)" % (
        stroke, len(text))


def test_the_results_are_shown(rom):
    img, _ = shot(rom, load_keys("full_run.keys") + [0] * 40, "results")
    assert lit(img, (0, 0, 240, 160)) > 300


def test_frame_rate_and_sprite_tiles_over_the_route(rom):
    keys = load_keys("full_run.keys")
    rows = T.run_rom(rom, keys, watch=("g_dbg_views", "g_dbg_sprite_tiles", "g_dbg_steps"))["watch"]
    play = [i for i in range(len(rows)) if rows[i][2] >= 64]     # in play after the title and how-to presses
    views = rows[play[-1]][0] - rows[play[0]][0]
    fps = views * 60 / len(play)
    print("views %d over %d play frames: %.1f fps" % (views, len(play), fps))
    assert fps >= 30, "%.1f views a second" % fps
    flips = [i for i in play[1:] if rows[i][0] != rows[i - 1][0]]
    gap = max(b - a for a, b in zip(flips, flips[1:]))
    print("worst gap between views: %d frames" % gap)
    assert gap <= 3, "a view took %d frames" % gap
    assert max(r[1] for r in rows) <= 512 - 64 + 512, "sprite tiles over the bitmap-mode budget"


def _rules_lib(lib):
    import ctypes
    import test_rules as TR
    for name, rt in TR.READS.items():
        getattr(lib, name).restype = rt
    lib.rules_los.argtypes = [ctypes.c_int32] * 4
    return lib


def _in_sight(lib):
    """The bugs (live or dead) the rules put in the field of view: more than 0.8 tiles ahead, within the view's
    width, with a clear line of sight; {bug: depth in tiles}."""
    import math
    v = {}
    if lib.rules_scene() == 2 and not lib.rules_dead_timer():
        px, py, a = lib.rules_px(), lib.rules_py(), lib.rules_angle()
        dx, dy = math.cos(a * math.pi / 512), math.sin(a * math.pi / 512)
        for i in range(lib.rules_bug_count()):
            bx, by = lib.rules_bug_x(i), lib.rules_bug_y(i)
            rx, ry = (bx - px) / 65536, (by - py) / 65536
            depth, lat = rx * dx + ry * dy, -rx * dy + ry * dx
            if depth > 0.8 and abs(lat / depth) < 0.55 and lib.rules_los(px, py, bx, by):
                v[i] = depth
    return v


def _views_missing(rom, lib, keys):
    """Runs keys in the ROM and on the PC. For every view the ROM flipped (at step s; it was started at step s-3 at
    the earliest), the bugs in sight during all of steps s-3..s-1 must have reached the page (g_dbg_drawn).
    Returns ({bug: [depth of each view it was expected in]}, {bug: [steps of the views it was missing from]})."""
    rows = T.run_rom(rom, keys, watch=("g_dbg_steps", "g_dbg_views", "g_dbg_drawn"))["watch"]
    start = next(i for i, r in enumerate(rows) if r[0] == 1)
    lib.game_init(0)
    vis = [{}]
    for k in keys[start:]:
        lib.game_step(k)
        vis.append(_in_sight(lib))
    checked, missed = {}, {}
    for f in range(1, len(rows)):
        s, views, drawn = rows[f]
        if views == rows[f - 1][1] or s < 5 or s >= len(vis):
            continue
        want = set.intersection(*[set(vis[j]) for j in range(s - 3, s)])
        for i in want:
            checked.setdefault(i, []).append(vis[s - 1][i])
            if not drawn >> i & 1:
                missed.setdefault(i, []).append(s)
    return checked, missed


def test_every_bug_in_sight_is_drawn(rom, lib):
    """Owner play-test: bugs "spawn in magically". Over the route, every live or dead bug that the rules put in the
    field of view with a clear line of sight during the steps a view was built from must be in that view."""
    checked, missed = _views_missing(rom, _rules_lib(lib), load_keys("full_run.keys"))
    assert sum(len(v) for v in checked.values()) > 500
    assert len(checked) == 25, "every bug of the level is in sight at some point of the route"
    assert not missed, "bugs in sight but not drawn: %s" % {i: v[:3] for i, v in missed.items()}


APPROACH_BUG = 16      # the east corridor's bug at (43, 25): the 17th bug of the map


def approach_keys(lib):
    """The route to the south end of the east corridor (the door at (43, 33) just opened, facing north), then north
    until bug 16, 8 tiles up the corridor, sees the player and wakes; then standing still while it walks all the way
    down the corridor to the player."""
    g = _rules_lib(lib)
    keys = load_keys("full_run.keys")[:1950]
    g.game_init(0)
    for k in keys:
        g.game_step(k)
    for _ in range(60):
        if g.rules_bug_state(APPROACH_BUG):
            break
        keys.append(UP)
        g.game_step(UP)
    assert g.rules_bug_state(APPROACH_BUG) == 1, "the corridor bug did not wake"
    return keys + [0] * 160


def test_an_approaching_bug_is_drawn_in_every_view(rom, lib):
    """Owner play-test: bugs "spawn in magically". A bug walking toward the player down a straight corridor, in the
    field of view and not occluded, must be in every view from 8 tiles away until it reaches the player."""
    checked, missed = _views_missing(rom, _rules_lib(lib), approach_keys(lib))
    depths = checked.get(APPROACH_BUG, [])
    assert len(depths) >= 40 and max(depths) > 7 and min(depths) < 1.5, depths
    assert APPROACH_BUG not in missed, "the approaching bug was missing from %d of %d views (steps %s...)" % (
        len(missed[APPROACH_BUG]), len(depths), missed[APPROACH_BUG][:5])
