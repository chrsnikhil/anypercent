"""ZIP's level (Task 4): level/level.txt builds into gen/ and graphics/level.bmp consistently, has its sections'
landmarks, fits the GBA limits, and the bot's route finishes it in time with the loop taken at full speed."""
import filecmp
import os
import shutil
import subprocess
import sys

import pytest

import arcade_test as T
from conftest import GAME_DIR, ROUTE, load_keys, tuning

sys.path.insert(0, os.path.join(GAME_DIR, "tools", "level"))
sys.path.insert(0, os.path.join(GAME_DIR, "tools", "art"))
import build_level as BL  # noqa: E402
import gbaimg  # noqa: E402

PY = sys.executable


@pytest.fixture(scope="module")
def parsed():
    return BL.parse(BL.read_level())


def test_the_generated_level_matches_level_txt(tmp_path):
    saved = tmp_path / "gen"
    shutil.copytree(os.path.join(GAME_DIR, "gen"), saved)
    r = subprocess.run([PY, "tools/level/build_level.py", "--no-bg"], cwd=GAME_DIR, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for name in ("level.c", "level.h", "zip_tiles.c"):
        assert filecmp.cmp(saved / name, os.path.join(GAME_DIR, "gen", name), shallow=False), name


def test_level_size_and_landmarks(parsed):
    grid, styles, things, start, decor = parsed
    h, w = len(grid), len(grid[0])
    assert h == 32 and w % 16 == 0 and w * 16 <= 16384
    kinds = [t[2] for t in things]
    assert kinds.count(BL.THINGS["C"]) == 1, "one checkpoint"
    assert kinds.count(BL.THINGS["F"]) == 1 and kinds.count(BL.THINGS["L"]) == 1
    assert 150 <= kinds.count(0) <= 400, kinds.count(0)
    assert {g for g, _, _ in decor} >= set("rlnKD")
    fx = next(t[0] for t in things if t[2] == BL.THINGS["F"])
    assert w * 16 - fx >= 30 * 16, "room to run out past the finish"


def test_the_loop_has_room(parsed):
    grid, _, things, _, _ = parsed
    lx, ly = next((t[0], t[1]) for t in things if t[2] == BL.THINGS["L"])
    col, floor_row = lx // 16, ly // 16
    for c in range(col - 6, col + 7):
        assert grid[floor_row][c] == 1, "flat floor under the loop at column %d" % c
        for r in range(floor_row - 10, floor_row):
            assert grid[r][c] == 0, "the loop's space is blocked at (%d, %d)" % (c, r)


def test_the_level_background_fits():
    size, px, pal = gbaimg.read_bmp(os.path.join(GAME_DIR, "graphics", "level.bmp"))
    w, h = size
    grid, _, _, _, _ = BL.parse(BL.read_level())
    assert (w, h) == (len(grid[0]) * 16, len(grid) * 16)
    assert gbaimg.tiles_of(px, w, h) <= 1024
    assert len(pal) <= 64


def test_the_bot_route_finishes_in_time_cleanly(lib):
    keys = load_keys(ROUTE)
    assert keys[:60] == [0] * 60
    run = T.pc_run_end(lib, keys)
    res = T.pc_result(lib, run)
    assert res["finished"]
    lo, hi = tuning("BOT_MIN_FRAMES"), tuning("BOT_MAX_FRAMES")
    assert lo <= res["time_frames"] <= hi, res["time_frames"] / 60.0
    assert res["trophies"] & 8, "the bot takes the loop at full speed"
    assert res["trophies"] == 15, res["trophies"]


def test_build_refuses_more_things_than_the_rules_hold():
    rows = ["." * 600 for _ in range(3)] + ["#" * 600]
    rows[2] = "P" + "o" * 520 + rows[2][521:]
    with pytest.raises(BL.LevelError):
        BL.parse(rows)


def test_build_refuses_a_bug_without_a_patrol_range(monkeypatch):
    rows = ["." * 20, "P...e" + "." * 15, "#" * 20]
    BL.parse(rows)
    monkeypatch.setattr(BL, "BUG_RANGE", 0)
    with pytest.raises(BL.LevelError):
        BL.parse(rows)
