"""RUSH HOUR's game flow through the PC library (out/librules.so): the scenes, the clock, pause, the results and
the arcade info. Physics and entities: test_physics.py; the level: test_level.py."""
import ctypes

import arcade_test as T
from conftest import (A, B, SELECT, START, RIGHT, SC_TITLE, SC_HOWTO, SC_PLAY, SC_PAUSE, SC_RESULTS, E_BUG, E_DOOR,
                      ents, to_play, tuning)


def test_game_info(rh):
    assert T.game_id(rh) == b"RUSH"
    info = ctypes.cast(ctypes.addressof(ctypes.c_char.in_dll(rh, "GAME_INFO")), ctypes.POINTER(ctypes.c_uint8))
    version = int.from_bytes(bytes(info[4:8]), "little")
    n_trophies = info[8]
    assert (version, n_trophies) == (2, 4)          # 2: the seed starts the bugs


def _bugs(rh):
    return [(x, y, rh.rules_ent_dir(i)) for i, _, _, x, y in ents(rh, E_BUG)]


def test_the_seed_shuffles_where_the_bugs_start(rh):
    """Seed 0 is the classic level (every bug walking left from its tile); any other seed starts each bug facing a
    seeded way and a seeded distance along its patrol, on its own floor, the same way every time for that seed."""
    rh.game_init(0)
    classic = _bugs(rh)
    assert classic and all(d == -1 for _, _, d in classic)
    layouts = set()
    for seed in (0x01234567, 0xDEADBEEF, 0x5EED0001, 77):
        rh.game_init(seed)
        bugs = _bugs(rh)
        assert len(bugs) == len(classic)
        assert [y for _, y, _ in bugs] == [y for _, y, _ in classic], "a bug left its floor"
        for x, y, _ in bugs:                                    # standing on floor, inside no wall
            tx0, tx1, ty = x // 16, (x + 13) // 16, (y + 12) // 16
            assert any(rh.rules_tile(tx, ty) in (1, 2) for tx in (tx0, tx1)), "a bug starts over a gap"
        assert bugs != classic, "seed %#x changed no bug" % seed
        layouts.add(tuple(bugs))
        to_play(rh)                                             # play reloads the level: the same seeded start
        assert _bugs(rh) != classic
        rh.game_init(seed)
        assert _bugs(rh) == bugs, "the same seed must start the bugs the same way"
    assert len(layouts) == 4, "different seeds gave the same bugs"


def test_title_then_howto_then_play_by_start_or_a(rh):
    for _ in range(50):
        rh.game_step(RIGHT)
    assert rh.rules_scene() == SC_TITLE and not rh.game_ended()
    rh.game_step(START)
    assert rh.rules_scene() == SC_HOWTO
    rh.game_step(START)                 # held: not a new press
    assert rh.rules_scene() == SC_HOWTO
    rh.game_step(0)
    rh.game_step(A)
    assert rh.rules_scene() == SC_PLAY and rh.rules_run_frames() == 0
    rh.game_init(0)
    rh.game_step(A)
    rh.game_step(0)
    rh.game_step(START)
    assert rh.rules_scene() == SC_PLAY


def test_the_clock_counts_play_frames_only(rh):
    for _ in range(30):
        rh.game_step(0)
    to_play(rh)
    assert rh.rules_run_frames() == 1          # the step that entered play does not count; the next one does
    for _ in range(99):
        rh.game_step(0)
    assert rh.rules_run_frames() == 100


def test_pause_freezes_time(rh):
    keys = [START, 0, START, 0] + [RIGHT | B] * 40 + [START] + [RIGHT | A] * 50 + [START] + [RIGHT] * 20
    rh.game_init(0)
    for k in keys[:44]:
        rh.game_step(k)
    frames, x, y = rh.rules_run_frames(), rh.rules_px(), rh.rules_py()
    rh.game_step(START)
    assert rh.rules_scene() == SC_PAUSE
    for _ in range(50):
        rh.game_step(RIGHT | A)
    assert (rh.rules_run_frames(), rh.rules_px(), rh.rules_py()) == (frames, x, y)
    rh.game_step(START)
    assert rh.rules_scene() == SC_PLAY
    first = T.pc_hashes(rh, keys)
    assert first == T.pc_hashes(rh, keys), "pausing broke determinism"
    unpaused = T.pc_hashes(rh, keys[:44] + [0] * 51 + keys[95:])
    assert first[-1] != unpaused[-1], "the pause is not part of the hashed state"


def test_select_in_pause_gives_up(rh):
    to_play(rh)
    rh.game_step(START)
    rh.game_step(0)
    rh.game_step(SELECT)
    assert rh.rules_scene() == SC_RESULTS and rh.game_ended() and not rh.rules_finished()
    assert rh.rules_trophies() == 0


def test_select_in_play_does_nothing(rh):
    to_play(rh)
    rh.game_step(SELECT)
    assert rh.rules_scene() == SC_PLAY


def test_reaching_the_door_shows_the_results(rh):
    to_play(rh)
    for _ in range(10):
        rh.game_step(0)
    (_, _, _, dx, dy), = ents(rh, E_DOOR)
    rh.rules_debug_place(dx + 8, dy + 16)
    rh.game_step(0)
    assert rh.rules_scene() == SC_RESULTS and rh.rules_finished() and rh.game_ended()
    frames = rh.rules_run_frames()
    r = T.Result()
    rh.game_result(ctypes.byref(r))
    assert r.finished == 1 and r.time_frames == frames == 12 and r.frames == rh.rules_steps()
    assert r.score == rh.rules_chai()
    for _ in range(100):
        rh.game_step(RIGHT)
    assert rh.rules_run_frames() == frames, "the clock ran on the results"


def test_game_ended_holds_until_start_then_falls_once(rh):
    to_play(rh)
    (_, _, _, dx, dy), = ents(rh, E_DOOR)
    rh.rules_debug_place(dx + 8, dy + 16)
    rh.game_step(0)
    seen = []
    for k in [0, A, 0, RIGHT, 0, START]:
        rh.game_step(k)
        seen.append(rh.game_ended())
    assert seen == [1] * 5 + [0]
    assert rh.rules_scene() == SC_TITLE


def test_under_two_minutes_trophy(rh):
    for clock, want in ((tuning("UNDER_FRAMES") - 2, True), (tuning("UNDER_FRAMES"), False)):
        rh.game_init(0)
        to_play(rh)
        (_, _, _, dx, dy), = ents(rh, E_DOOR)
        rh.rules_debug_run_frames(clock)
        rh.rules_debug_place(dx + 8, dy + 16)
        rh.game_step(0)
        assert rh.rules_finished()
        assert bool(rh.rules_trophies() & 1) == want, (clock, rh.rules_run_frames())


def test_time_up_ends_the_run_before_the_log_limit(rh):
    to_play(rh)
    rh.rules_debug_run_frames(tuning("TIME_UP_FRAMES") - 2)
    rh.game_step(RIGHT)
    assert rh.rules_scene() == SC_PLAY
    rh.game_step(RIGHT)
    assert rh.rules_scene() == SC_RESULTS and rh.game_ended() and not rh.rules_finished()
    assert tuning("TIME_UP_FRAMES") < 216000 - 3600, "leave room under AC_MAX_FRAMES for the title and how-to"


def test_game_init_resets_everything(rh):
    import subprocess
    import sys
    fresh = int(subprocess.run([sys.executable, "-c", (
        "import sys; sys.path.insert(0, %r); import arcade_test as T; "
        "l = T.load_lib(%r); l.game_init(0); print(l.game_hash())") % (
        T.__file__.rsplit("/", 1)[0], __import__("os").path.join(
            __import__("conftest").GAME_DIR, "out", "librules.so"))],
        capture_output=True, text=True, check=True).stdout)
    from conftest import LEFT
    to_play(rh)
    for _ in range(120):
        rh.game_step(LEFT | A)
    assert rh.rules_facing_left()
    rh.game_init(0)
    assert rh.game_hash() == fresh and not rh.rules_facing_left()
