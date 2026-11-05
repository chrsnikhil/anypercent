"""The level (level/level.txt): its shape and contents, the generated files being up to date, and the bot finishing
it within the pinned time."""
import os
import subprocess
import sys

import pytest

import arcade_test as T
from conftest import GAME_DIR, E_BUG, E_CHAI, E_CHECK, E_DOOR, E_ORB, ents, load_keys, tuning

sys.path.insert(0, os.path.join(GAME_DIR, "tools", "level"))
sys.path.insert(0, os.path.join(GAME_DIR, "dev"))
import build_level  # noqa: E402

GENERATED = ("rules/level.h", "rules/level_data.c", "graphics/level_bg.bmp", "graphics/level_bg.json")


def test_level_shape_and_contents(rh):
    rows, zones = build_level.parse()
    assert len(rows) == 12 and [z[1] for z in zones] == ["street", "market", "train"]
    assert 150 <= len(rows[0]) <= 420
    kinds = [t for _, t, _, _, _ in ents(rh)]
    assert kinds.count(E_CHAI) == 40 == rh.rules_chai_total()
    assert 10 <= kinds.count(E_BUG) <= 14
    assert kinds.count(E_CHECK) == 2 and kinds.count(E_ORB) == 1 and kinds.count(E_DOOR) == 1
    assert (rh.rules_level_w(), rh.rules_level_h()) == (len(rows[0]), 12)


def test_every_zone_has_its_features():
    rows, zones = build_level.parse()
    bounds = [z[0] for z in zones] + [len(rows[0])]
    for n, (c0, c1) in enumerate(zip(bounds, bounds[1:])):
        part = "".join(r[c0:c1] for r in rows)
        assert part.count("b") >= 2 and part.count("c") >= 8, zones[n]
    street, market, train = ("".join(r[a:b] for r in rows) for a, b in zip(bounds, bounds[1:]))
    assert "=" in street and "^" in street
    assert market.count("=") >= 30, "the market is about awnings"
    assert "H" in train and "=" in train


def test_entities_stand_in_empty_cells_on_something():
    rows, _ = build_level.parse()
    for c in range(len(rows[0])):
        for r in range(12):
            ch = rows[r][c]
            if ch in "bkDP":
                below = rows[r + 1][c] if r < 11 else "."
                assert below in "#XH=", "%s at (%d, %d) stands on %r" % (ch, c, r, below)


def test_generated_files_are_up_to_date():
    before = {}
    for rel in GENERATED:
        with open(os.path.join(GAME_DIR, rel), "rb") as f:
            before[rel] = f.read()
    subprocess.run([sys.executable, os.path.join(GAME_DIR, "tools", "level", "build_level.py")], check=True,
                   cwd=GAME_DIR, capture_output=True)
    for rel in GENERATED:
        with open(os.path.join(GAME_DIR, rel), "rb") as f:
            assert f.read() == before[rel], rel + " is stale: run tools/level/build_level.py"


def test_the_map_draws_every_solid_tile():
    from PIL import Image
    rows, _ = build_level.parse()
    img = Image.open(os.path.join(GAME_DIR, "graphics", "level_bg.bmp"))
    px = img.load()
    for c in range(len(rows[0])):
        for r in range(12):
            if rows[r][c] in "#XH=^":
                assert any(px[c * 16 + x, r * 16 + y] % 16 for x in range(16) for y in range(16)), (c, r)


def test_level_is_completable_by_the_bot(rh):
    keys = load_keys("full_run.keys")
    assert keys[:60] == [0] * 60
    res = T.pc_result(rh, keys)
    assert res["finished"] and rh.game_ended()
    assert T.pc_run_end(rh, keys) == keys, "the route runs on after the door"
    assert res["score"] == 40 and res["trophies"] & 2 and res["trophies"] & 4, res


def test_tuning(rh):
    """The bot (a careful, walking first-timer's pace) finishes within 1:10-2:00: adjust the level, not this."""
    res = T.pc_result(rh, load_keys("full_run.keys"))
    assert 70 * 60 <= res["time_frames"] <= 120 * 60, res["time_frames"] / 60.0
    assert res["time_frames"] < tuning("UNDER_FRAMES")


@pytest.mark.slow
def test_the_route_is_the_bots(lib):
    import bot
    keys, skipped = bot.play(lib)
    assert not skipped
    assert keys == load_keys("full_run.keys"), "re-record: dev/record_route.py"
