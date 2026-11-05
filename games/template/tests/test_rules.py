"""The template's own rules, through the PC library (out/librules.so). A stamped game replaces this file with tests
of its rules; test_generic.py stays."""
import ctypes

import pytest

import arcade_test as T
from conftest import SELECT, START, RIGHT, LEFT, UP, DOWN, load_keys, tuning


@pytest.fixture
def g(lib):
    for name, rt in (("rules_scene", ctypes.c_uint8), ("rules_paused", ctypes.c_uint8), ("rules_x", ctypes.c_int16),
                     ("rules_y", ctypes.c_int16), ("rules_run_frames", ctypes.c_uint32),
                     ("rules_finished", ctypes.c_uint8), ("rules_trophies", ctypes.c_uint32)):
        getattr(lib, name).restype = rt
    lib.game_init(0)
    return lib


def play(g):
    g.game_step(START)
    g.game_step(0)


def test_the_title_waits_for_start(g):
    for _ in range(100):
        g.game_step(RIGHT)
    assert g.rules_scene() == 0 and not g.game_ended()
    g.game_step(START)
    assert g.rules_scene() == 1 and (g.rules_x(), g.rules_y()) == (tuning("START_X"), tuning("START_Y"))


def test_the_dpad_moves_the_dot_and_the_field_holds_it(g):
    play(g)
    x0, y0 = g.rules_x(), g.rules_y()
    for _ in range(5):
        g.game_step(RIGHT | DOWN)
    assert (g.rules_x(), g.rules_y()) == (x0 + 5, y0 + 5)
    for _ in range(400):
        g.game_step(LEFT | UP)
    assert (g.rules_x(), g.rules_y()) == (0, tuning("FIELD_TOP"))


def test_start_pauses_and_nothing_moves(g):
    play(g)
    frames = g.rules_run_frames()
    g.game_step(START)
    for _ in range(30):
        g.game_step(RIGHT)
    assert g.rules_paused() and g.rules_run_frames() == frames and g.rules_x() == tuning("START_X")
    g.game_step(START)
    assert not g.rules_paused()


def test_select_ends_the_run_unfinished_and_start_leaves_the_results(g):
    play(g)
    g.game_step(SELECT)
    assert g.game_ended() and not g.rules_finished() and g.rules_trophies() == 0
    g.game_step(0)
    g.game_step(START)
    assert not g.game_ended() and g.rules_scene() == 0


def test_the_demo_route_reaches_the_goal_with_both_trophies(g):
    res = T.pc_result(g, T.pc_run_end(g, load_keys("demo.keys")))
    assert res["finished"] and res["trophies"] == 3 and res["time_frames"] <= tuning("FAST_FRAMES")


def test_a_slow_run_reaches_the_goal_without_the_fast_trophy(g):
    keys = [START, 0] + [0] * tuning("FAST_FRAMES") + [x for x in load_keys("demo.keys")[61:]]
    res = T.pc_result(g, T.pc_run_end(g, keys))
    assert res["finished"] and res["trophies"] == 1


def test_the_seed_moves_the_goal(g):
    """Seed 0 keeps the classic goal; any other seed puts it somewhere in the goal region, the same place every time
    for that seed (a stamped game replaces this with what its own seed changes)."""
    g.rules_goal_x.restype = g.rules_goal_y.restype = ctypes.c_int16
    g.game_init(0)
    assert (g.rules_goal_x(), g.rules_goal_y()) == (tuning("GOAL_X"), tuning("GOAL_Y"))
    goals = set()
    for seed in (0x01234567, 0xDEADBEEF, 0x5EED0001, 77):
        g.game_init(seed)
        goal = (g.rules_goal_x(), g.rules_goal_y())
        assert tuning("GOAL_MIN_X") <= goal[0] <= tuning("GOAL_MAX_X")
        assert tuning("GOAL_MIN_Y") <= goal[1] <= tuning("GOAL_MAX_Y")
        g.game_init(seed)
        assert (g.rules_goal_x(), g.rules_goal_y()) == goal
        goals.add(goal)
    assert len(goals) == 4 and (tuning("GOAL_X"), tuning("GOAL_Y")) not in goals


def test_the_hash_follows_the_state(g):
    keys = [START, 0] + [RIGHT] * 10
    assert T.pc_hashes(g, keys) == T.pc_hashes(g, keys)
    assert T.pc_hashes(g, keys)[-1] != T.pc_hashes(g, keys[:-1] + [DOWN])[-1]
