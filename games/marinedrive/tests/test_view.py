"""MARINE DRIVE GP's screens in the ROM (plan Task 5): the title card, the Mode 7 race with the skyline, the countdown,
the translucent ghost drawn behind a solid player, the results card, and the frame budget (the ROM steps the rules
every frame: the generic suite checks no lag; here the CPU use with a ghost on screen)."""
import os

from PIL import Image

import arcade_test as T
from arcade_test import S
from conftest import OUT_DIR, START, load_keys

PLAY = 0x80
GRID = (113, 764, 764 // 4)          # the player's grid slot (x, y, angle / 4): rules/track_data.c md_grid[0]
PLAYER_BOX = (106, 110, 134, 140)    # the player's kart on screen (x0, y0, x1, y1)
TO_COUNTDOWN = [0] * 60 + [START, 0, START] + [0] * 60


def screen(path):
    with open(path, "rb") as f:
        return Image.frombytes("RGBA", (240, 160), f.read()).convert("RGB")


def shot(rom, frames, name, save=None):
    path = os.path.join(OUT_DIR, name + ".rgba")
    T.run_rom(rom, frames, save_in=T.blank_save() if save is None else save, shots=[(len(frames), path)])
    img = screen(path)
    img.save(os.path.join(OUT_DIR, name + ".png"))
    return img


def lime(img):
    """Pixels of the player's lime helmet."""
    return sum(1 for p in img.getdata() if p[1] > 150 and p[1] > p[0] + 20 and p[1] > p[2] + 60)


def lit(img, box=(0, 0, 240, 160), level=150):
    px = img.crop(box).tobytes()
    return sum(1 for i in range(0, len(px), 3) if min(px[i:i + 3]) > level)


def test_the_title_card(rom):
    img = shot(rom, [0] * 40, "title")
    logo = img.crop((24, 8, 216, 72))
    orange = sum(1 for p in logo.getdata() if p[0] > 200 and 60 < p[1] < 200 and p[2] < 120)
    assert orange > 400, "the MARINE DRIVE logo"
    assert lit(img, (0, 80, 240, 120)) > 150, "the tagline and PRESS START"


def test_the_race_is_mode7_under_a_skyline(rom):
    img = shot(rom, load_keys("full_run.keys")[:900], "race")
    sky = img.crop((0, 0, 240, 40))
    assert sum(1 for p in sky.getdata() if p[0] > p[2] + 20) > 800, "the dusk skyline"
    road = img.crop((60, 120, 180, 160))
    grey = sum(1 for p in road.getdata() if abs(p[0] - p[1]) < 24 and abs(p[1] - p[2]) < 24 and p[0] > 120)
    assert grey > 1500, "asphalt under the kart"
    assert lime(img.crop(PLAYER_BOX)) > 40, "the player's lime helmet"


def test_the_player_is_never_hidden_under_the_gantry(rom):
    """Crossing the line (end of lap 1 on the route): the Chainlink banner stands above the kart and goes once the
    camera reaches it; the player's lime helmet stays visible on every frame."""
    keys = load_keys("full_run.keys")
    frames = list(range(2296, 2326, 3))
    paths = [(n, os.path.join(OUT_DIR, "cross_%d.rgba" % n)) for n in frames]
    T.run_rom(rom, keys[:frames[-1]], save_in=T.blank_save(), shots=paths)
    for n, path in paths:
        assert lime(screen(path).crop(PLAYER_BOX)) > 40, "frame %d: the player is covered" % n


def test_the_countdown_shows_its_digits(rom):
    img = shot(rom, TO_COUNTDOWN, "countdown")
    digit = img.crop((96, 36, 144, 76))
    assert sum(1 for p in digit.getdata() if p[0] > 200 and p[1] > 150 and p[2] < 90) > 150, "a yellow 3"


def test_the_ghost_is_translucent(rom, game_id):
    ahead = (100, 704, GRID[2], PLAY)                    # between the front row and the line: clear of the karts
    save = T.save_with(game_id, ghost=S.ghost_bytes(game_id, 0, 4, [ahead] * 200))
    rows = T.run_rom(rom, TO_COUNTDOWN, watch=("g_dbg_ghost",), save_in=save)["watch"]
    assert rows[-1][0] == 1, "the ghost is drawn in the countdown"
    with_ghost = shot(rom, TO_COUNTDOWN, "ghost", save)
    without = shot(rom, TO_COUNTDOWN, "no_ghost")
    diff = [(a, b) for a, b in zip(with_ghost.getdata(), without.getdata()) if a != b]
    assert len(diff) > 60, "the ghost changed %d pixels" % len(diff)
    # a white helmet drawn half transparent over the grey road: lighter than the road, darker than white
    ghost_px = [a for a, b in diff if sum(a) > sum(b)]
    assert ghost_px and max(min(p) for p in ghost_px) < 225, "the ghost is drawn solid"


def test_the_player_stays_solid_over_its_ghost(rom, game_id):
    on_player = (GRID[0], GRID[1], GRID[2], PLAY)
    save = T.save_with(game_id, ghost=S.ghost_bytes(game_id, 0, 4, [on_player] * 200))
    rows = T.run_rom(rom, TO_COUNTDOWN, watch=("g_dbg_ghost",), save_in=save)["watch"]
    assert rows[-1][0] == 1, "the ghost is drawn"
    with_ghost = shot(rom, TO_COUNTDOWN, "ghost_on_player", save)
    without = shot(rom, TO_COUNTDOWN, "no_ghost")
    assert with_ghost.crop(PLAYER_BOX).tobytes() == without.crop(PLAYER_BOX).tobytes(), \
        "the ghost changed the player's pixels"


def test_the_results_card(rom):
    img = shot(rom, load_keys("full_run.keys") + [0] * 40, "results")
    badge = img.crop((88, 12, 152, 44))
    assert sum(1 for p in badge.getdata() if p[0] > 200 and p[1] > 150 and p[2] < 90) > 80, "a gold 1ST"
    assert lit(img, (0, 50, 240, 160)) > 600, "time, laps and four trophies"


def play_flag(lib, keys):
    """game_ghost()'s in-play flag after these keys from power-on."""
    lib.game_init(0)
    for k in keys:
        lib.game_step(k)
    g = T.Ghost()
    lib.game_ghost(T.ctypes.byref(g))
    return g.flags & PLAY


def test_the_frame_budget_with_a_ghost(rom, game_id, lib):
    """No lag over the route with a ghost ahead of the player (one more scaled sprite), and the race keeps a margin:
    no frame with the ghost on screen above 80% of the CPU (g_md_cpu: the previous frame's use). The first two ghost
    frames are skipped: they report the how-to -> countdown change (the how-to card's text and sprites going, the
    HUD, grid and props arriving), which reads about 90% for one frame; it never drops a frame (the no-lag assert
    below and the generic ROM-vs-PC test cover it)."""
    keys = load_keys("full_run.keys")
    track = T.pc_player(lib, keys)
    start = next(i for i in range(len(keys)) if play_flag(lib, keys[:i + 1]))
    pts = [(x, y, 0, PLAY) for x, y in track[start + 30::4]]  # half a second ahead of the player
    save = T.save_with(game_id, ghost=S.ghost_bytes(game_id, 0, 4, pts))
    rows = T.run_rom(rom, keys, watch=("g_dbg_steps", "g_md_cpu", "g_dbg_ghost"), save_in=save)["watch"]
    live = [r for r in rows if r[0] > 1]
    assert sum(1 for r in live if r[2]) > len(live) // 2
    race = [r[1] for r in rows if r[2]][2:]         # see the docstring
    assert max(race) < 800, "a race frame used %.1f%% of the CPU" % (max(race) / 10)
    lags = [i for i in range(1, len(rows)) if rows[i][0] == rows[i - 1][0] and rows[i][0] > 0]
    assert not lags, "lag at frames %s" % lags[:10]


# ---- the kart's animation (rules 4): g_md_look, the view's report of how the player's kart looks -------------------

RACE = TO_COUNTDOWN + [0] * 190                  # the countdown (180 frames), then GO
A_KEY, R_KEY, RIGHT_KEY, LEFT_KEY = 0x1, 0x100, 0x10, 0x20


def looks(rom, keys):
    rows = T.run_rom(rom, keys, watch=("g_md_look",), save_in=T.blank_save())["watch"]
    return [r[0] for r in rows]


def test_the_kart_shows_its_wheel(rom):
    keys = RACE + [A_KEY] * 50 + [A_KEY | LEFT_KEY] * 10 + [A_KEY] * 10 + [A_KEY | RIGHT_KEY] * 10
    pose = [(v >> 24) & 3 for v in looks(rom, keys)]
    n = len(RACE) + 50
    assert pose[n - 2] == 1, "straight"
    assert pose[n + 6:n + 9] == [0, 0, 0], "turning left: the left pose"
    assert pose[n + 26:n + 29] == [2, 2, 2], "turning right: the right pose"


def test_the_route_shows_the_kart_alive(rom):
    """Over the bot's route: both turned poses, a drift's hop, tyre smoke or sand dust behind the kart, a boost's
    flame, and the camera shaking at the route's one wall hit."""
    seen = looks(rom, load_keys("full_run.keys"))
    assert {(v >> 24) & 3 for v in seen} >= {0, 1, 2}
    assert any((v >> 8) & 1 for v in seen), "no drift hop"
    assert max((v >> 12) & 7 for v in seen) >= 2, "no smoke or dust"
    assert any((v >> 16) & 1 for v in seen), "no boost flame"
    assert any((v >> 20) & 1 for v in seen), "no wall shake"


# ---- racing the ghost: a cyan ghost, and the live gap to it under the place badge (g_md_gap) ------------------------

NO_GAP = 0x80000000                              # g_md_gap while no gap is shown
GAP_BOX = (176, 20, 240, 38)                     # the gap's digits on screen (right-aligned under the place badge)


def route_ghost(lib, game_id, shift):
    """(keys, save): the route, with a ghost of the route itself shift steps ahead of the player (behind if < 0)."""
    keys = load_keys("full_run.keys")
    track = T.pc_player(lib, keys)
    start = next(i for i in range(len(keys)) if play_flag(lib, keys[:i + 1]))
    pts = [(x, y, 0, PLAY) for x, y in track[start + shift::4]]
    return keys, T.save_with(game_id, ghost=S.ghost_bytes(game_id, 0, 4, pts))


def gaps(rom, keys, save):
    """g_md_gap per frame: frames the player is behind the ghost (negative: ahead), or None while none is shown."""
    rows = T.run_rom(rom, keys, watch=("g_md_gap",), save_in=save)["watch"]
    return [None if r[0] == NO_GAP else (r[0] - (1 << 32) if r[0] & 0x80000000 else r[0]) for r in rows]


def assert_gap(rom, lib, game_id, shift):
    keys, save = route_ghost(lib, game_id, shift)
    shown = [g for g in gaps(rom, keys, save) if g is not None]
    assert len(shown) > 5000, "the gap was shown on %d frames" % len(shown)
    off = [g for g in shown if abs(g - shift) > 3]
    assert len(off) < len(shown) // 20, "gap %+d frames expected; %d frames off, e.g. %s" % (shift, len(off), off[:8])


def test_the_gap_to_a_ghost_ahead_counts_against_you(rom, lib, game_id):
    assert_gap(rom, lib, game_id, 30)            # the ghost half a second ahead on the same line: +0.5


def test_the_gap_to_a_ghost_behind_counts_for_you(rom, lib, game_id):
    assert_gap(rom, lib, game_id, -30)           # half a second behind: -0.5, even with the ghost off screen


def test_the_gap_holds_when_the_ghost_stops_and_reverses(rom, lib, game_id):
    """A ghost of the route that, 10 s into the race, stands still for STOP steps, then drives back along its own line
    for BACK steps and on again (as BOT-A2, ghostgen's v2, does on lap 1 with its B-held stall): from there it is
    STOP + 2 * BACK steps behind the player on the route, on every lap after. The gap is measured along the track, so
    it reads 0 before the stop and -LOST after it, never the climbing red number a nearest-position match got stuck
    on where the ghost turned back (+33.5 at 0:54 against BOT-A2 while really 0.9 s ahead)."""
    at, stop, back = 180 + 600, 30, 45
    lost = stop + 2 * back
    keys = load_keys("full_run.keys")
    track = T.pc_player(lib, keys)
    s0 = next(i for i in range(len(keys)) if play_flag(lib, keys[:i + 1]))     # track[s0]: the first in-play step
    path = (track[s0:s0 + at] + [track[s0 + at - 1]] * stop + track[s0 + at - 1 - back:s0 + at - 1][::-1]
            + track[s0 + at - back:])
    save = T.save_with(game_id, ghost=S.ghost_bytes(game_id, 0, 4, [(x, y, 0, PLAY) for x, y in path[::4]]))
    rows = T.run_rom(rom, keys, watch=("g_md_gap", "g_dbg_steps"), save_in=save)["watch"]
    boot = next(i for i, r in enumerate(rows) if r[1])   # frames the ROM boots before its first step reads keys[boot]
    before, after = [], []
    for gap, steps in rows:
        if gap == NO_GAP:
            continue
        gap = gap - (1 << 32) if gap & 0x80000000 else gap
        j = steps + boot - (s0 + 1)              # the player's steps since play started, as the ghost's path counts
        if j < at - 8:
            before.append(gap)
        elif j > at + 8:
            after.append(gap)
    assert len(before) > 400 and len(after) > 4000, (len(before), len(after))
    off = [g for g in before if abs(g) > 3] + [g for g in after if abs(g + lost) > 3]
    assert not off, "gap 0 then %+d expected; %d frames off, e.g. %s" % (-lost, len(off), off[:8])


def test_the_gap_is_red_behind_and_green_ahead(rom, lib, game_id):
    n = 1500                                     # mid lap 1
    bare = shot(rom, load_keys("full_run.keys")[:n], "gap_none").crop(GAP_BOX)     # over the dusk sky: no ghost
    for shift, name in ((30, "gap_behind"), (-30, "gap_ahead")):
        keys, save = route_ghost(lib, game_id, shift)
        box = shot(rom, keys[:n], name, save).crop(GAP_BOX)
        new = [a for a, b in zip(box.getdata(), bare.getdata()) if a != b]
        red = sum(1 for p in new if p[0] > 180 and p[0] > p[1] + 80)
        green = sum(1 for p in new if p[1] > 180 and p[1] > p[0] + 80)
        if shift > 0:
            assert red > 25 and green < 5, (name, red, green)
        else:
            assert green > 25 and red < 5, (name, red, green)


def test_the_ghost_is_a_cyan_kart(rom, game_id):
    ahead = (100, 704, GRID[2], PLAY)
    save = T.save_with(game_id, ghost=S.ghost_bytes(game_id, 0, 4, [ahead] * 200))
    with_ghost = shot(rom, TO_COUNTDOWN, "ghost_cyan", save)
    without = shot(rom, TO_COUNTDOWN, "no_ghost")
    diff = [(a, b) for a, b in zip(with_ghost.getdata(), without.getdata()) if a != b]
    assert len(diff) > 60
    cyan = sum(1 for a, b in diff if a[2] > a[0] + 30 and a[1] > a[0] + 20)
    assert cyan > len(diff) * 2 // 3, "%d of %d ghost pixels are cyan" % (cyan, len(diff))
