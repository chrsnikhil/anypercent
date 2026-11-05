"""MARINE DRIVE GP's scenes (plan Task 1): title -> how-to -> countdown (3-2-1-GO, 180 frames) -> race <-> pause ->
results, the countdown locking the controls, pause freezing everything, retiring, and GAME_INFO."""
import ctypes

import arcade_test as T
from conftest import (A, B, LEFT, RIGHT, SELECT, START, SC_COUNTDOWN, SC_HOWTO, SC_PAUSE, SC_RACE, SC_RESULTS,
                      SC_TITLE, to_race, tuning)


class Info(ctypes.Structure):
    _fields_ = [("id", ctypes.c_char * 4), ("rules_version", ctypes.c_uint32), ("n_trophies", ctypes.c_uint8),
                ("trophy_names", ctypes.POINTER(ctypes.c_char_p)), ("ghost_period", ctypes.c_uint16)]


def test_game_info(lib):
    info = Info.in_dll(lib, "GAME_INFO")
    assert info.id == b"MDGP" and info.rules_version == 4 and info.ghost_period == 4    # 4: the handling
    names = [info.trophy_names[i].decode() for i in range(info.n_trophies)]
    assert names == ["Win", "Under 2:15", "Clean lap", "Three drift boosts in one lap"]


def test_the_title_waits_for_start_then_the_howto_card(g):
    for k in (A, B, RIGHT, SELECT, 0) * 20:
        g.game_step(k)
    assert g.rules_scene() == SC_TITLE and not g.game_ended()
    g.game_step(START)
    assert g.rules_scene() == SC_HOWTO
    g.game_step(START)                      # held: not a new press
    assert g.rules_scene() == SC_HOWTO
    g.game_step(0)
    g.game_step(A)                          # A also leaves the how-to card
    assert g.rules_scene() == SC_COUNTDOWN and g.rules_countdown() == tuning("COUNTDOWN_FRAMES")


def test_the_countdown_lasts_180_frames_and_locks_the_controls(g):
    for k in (START, 0, START):
        g.game_step(k)
    starts = [(g.kart(i).x, g.kart(i).y, g.kart(i).heading) for i in range(4)]
    n = 0
    while g.rules_scene() == SC_COUNTDOWN:
        g.game_step(A | RIGHT)
        n += 1
    assert n == 180 == tuning("COUNTDOWN_FRAMES")
    assert g.rules_scene() == SC_RACE and g.rules_race_frames() == 0
    assert [(g.kart(i).x, g.kart(i).y, g.kart(i).heading) for i in range(4)] == starts
    g.game_step(A)
    assert g.rules_race_frames() == 1 and g.kart(0).speed > 0


def test_pause_freezes_the_race_and_start_resumes(g):
    to_race(g)
    for _ in range(30):
        g.game_step(A)
    before = [(g.kart(i).x, g.kart(i).y, g.kart(i).speed) for i in range(4)]
    frames = g.rules_race_frames()
    g.game_step(START)
    assert g.rules_scene() == SC_PAUSE
    for _ in range(60):
        g.game_step(A | LEFT)
    assert g.rules_race_frames() == frames
    assert [(g.kart(i).x, g.kart(i).y, g.kart(i).speed) for i in range(4)] == before
    g.game_step(0)
    g.game_step(START)
    assert g.rules_scene() == SC_RACE


def test_pause_in_the_countdown_returns_to_the_countdown(g):
    for k in (START, 0, START, 0, 0, 0):
        g.game_step(k)
    left = g.rules_countdown()
    g.game_step(START)
    assert g.rules_scene() == SC_PAUSE
    for _ in range(20):
        g.game_step(0)
    g.game_step(START)
    assert g.rules_scene() == SC_COUNTDOWN and g.rules_countdown() == left


def test_retire_from_pause_ends_the_run_unfinished_and_start_leaves(g):
    to_race(g)
    g.game_step(START)
    g.game_step(SELECT)
    assert g.rules_scene() == SC_RESULTS and g.game_ended() and not g.rules_finished()
    assert g.rules_trophies() == 0
    g.game_init(0)
    to_race(g)
    g.game_step(START)
    g.game_step(SELECT)
    for _ in range(10):
        g.game_step(0)
    assert g.game_ended()
    g.game_step(START)
    assert not g.game_ended() and g.rules_scene() == SC_TITLE


def test_game_ended_rises_once(g):
    to_race(g)
    ended = []
    for k in [START, SELECT] + [0] * 5 + [START] + [0] * 5:
        g.game_step(k)
        ended.append(g.game_ended())
    rises = sum(1 for a, b in zip([0] + ended, ended) if b and not a)
    assert rises == 1


def test_the_hash_follows_the_state(g):
    keys = [START, 0, START] + [0] * 180 + [A] * 20
    assert T.pc_hashes(g, keys) == T.pc_hashes(g, keys)
    assert T.pc_hashes(g, keys)[-1] != T.pc_hashes(g, keys[:-1] + [A | RIGHT])[-1]


def test_game_init_resets_everything(g):
    """arcade_replay calls game_init twice in one process and the tests share one library: a second game_init after
    a race must give exactly a fresh process's hashes (debug hooks included: the freeze mask)."""
    import subprocess
    import sys
    keys = [START, 0, START] + [0] * 180 + [A] * 120 + [A | RIGHT] * 40
    fresh = subprocess.run([sys.executable, "-c", (
        "import sys; sys.path.insert(0, %r); import arcade_test as T; "
        "print(T.pc_hashes(T.load_lib(%r), %r))") % (T.__file__.rsplit("/", 1)[0], g._name, keys)],
        capture_output=True, text=True, check=True).stdout.strip()
    g.game_init(0)
    for k in keys + [A | B] * 300:
        g.game_step(k)
    g.rules_debug_freeze(0xF)
    g.rules_debug_place(1, 500, 92, 0)
    assert str(T.pc_hashes(g, keys)) == fresh
