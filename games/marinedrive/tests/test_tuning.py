"""Race tuning and the route (plan Task 4): the rivals finish on their own, clean, in a bounded time; the bot's
route (tests/routes/full_run.keys) wins; and the route is exactly what dev/bot.py plays today (so any change to the
rules' feel shows up here and the route is re-recorded)."""
import os
import sys

import arcade_test as T
from conftest import GAME_DIR, SC_COUNTDOWN, START, load_keys, tuning

sys.path.insert(0, os.path.join(GAME_DIR, "dev"))
import bot as BOT  # noqa: E402

LIMIT = 210 * 60                  # 3:30


def test_rivals_finish_alone(g):
    for k in (START, 0, START, 0):
        g.game_step(k)
    while g.rules_scene() == SC_COUNTDOWN:
        g.game_step(0)
    off = [0] * 4
    for _ in range(LIMIT):
        g.game_step(0)                              # the player never moves
        for i in range(1, 4):
            if g.kart(i).surface not in (0, 1, 4):  # road, curb, boost pad
                off[i] += 1
        if all(g.kart(i).finished for i in range(1, 4)):
            break
    for i in range(1, 4):
        k = g.kart(i)
        assert k.finished and k.finish_frame <= LIMIT, "rival %d" % i
        assert k.wall_hits == 0 and off[i] == 0, "rival %d: %d wall hits, %d frames off the track" % (
            i, k.wall_hits, off[i])
    times = sorted(g.kart(i).finish_frame for i in range(1, 4))
    assert 110 * 60 <= times[0] and times[-1] <= 130 * 60, times


def test_the_route_wins_with_every_trophy(lib):
    keys = load_keys("full_run.keys")
    assert keys[:60] == [0] * 60
    end = T.pc_run_end(lib, keys)
    assert len(end) == len(keys), "the route runs past the end of the race"
    res = T.pc_result(lib, keys)
    assert res["finished"] and res["score"] == 1
    assert 95 * 60 <= res["time_frames"] <= 150 * 60, res["time_frames"] / 60.0
    assert res["time_frames"] <= tuning("FAST_FRAMES")
    assert res["trophies"] == 15


def test_the_route_is_what_the_bot_drives(lib):
    bot = BOT.Bot(lib)
    assert bot.run() == load_keys("full_run.keys"), "rules or bot changed: re-record with dev/bot.py"
