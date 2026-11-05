"""ZIP's screens and run bookkeeping (Task 1): title -> how-to -> play <-> pause -> results, the clock, GAME_INFO."""
import arcade_test as T
from conftest import A, SELECT, START, RIGHT, tuning

SC_TITLE, SC_HOWTO, SC_PLAY, SC_PAUSE, SC_RESULTS = range(5)


def to_play(g):
    g.game_step(START)
    g.game_step(0)
    g.game_step(START)


def test_game_info(g):
    assert T.game_id(g) == b"ZIPG"
    assert g.rules_n_trophies() == 4
    names = [g.rules_trophy_name(i).decode() for i in range(4)]
    assert names == ["Under 1:30", "Never lost packets", "100 packets", "Loop at full speed"]
    assert g.rules_ghost_period() == 2


def test_title_then_howto_then_play(g):
    for _ in range(50):
        g.game_step(RIGHT)
    assert g.rules_scene() == SC_TITLE and not g.game_ended()
    g.game_step(START)
    assert g.rules_scene() == SC_HOWTO
    for _ in range(20):
        g.game_step(RIGHT)
    assert g.rules_scene() == SC_HOWTO
    g.game_step(A)
    assert g.rules_scene() == SC_PLAY and g.rules_run_frames() == 0


def test_the_clock_runs_in_play(g):
    to_play(g)
    for _ in range(100):
        g.game_step(0)
    assert g.rules_run_frames() == 100


def test_pause_freezes_the_clock_and_the_player(g):
    to_play(g)
    for _ in range(10):
        g.game_step(RIGHT)
    frames, x, y = g.rules_run_frames(), g.rules_px(), g.rules_py()
    g.game_step(START)
    assert g.rules_scene() == SC_PAUSE
    for _ in range(60):
        g.game_step(RIGHT)
    assert (g.rules_run_frames(), g.rules_px(), g.rules_py()) == (frames, x, y)
    g.game_step(START)
    assert g.rules_scene() == SC_PLAY
    g.game_step(RIGHT)
    assert g.rules_run_frames() == frames + 1


def test_select_in_pause_ends_the_run_once(g):
    to_play(g)
    g.game_step(0)
    g.game_step(START)
    g.game_step(0)
    g.game_step(SELECT)
    assert g.rules_scene() == SC_RESULTS and g.game_ended() and not g.rules_finished()
    for _ in range(40):
        g.game_step(START)
        assert g.game_ended() or g.rules_scene() == SC_TITLE
    assert g.rules_scene() == SC_TITLE and not g.game_ended()


def test_results_ignore_start_at_first(g):
    to_play(g)
    g.game_step(0)
    g.game_step(START)
    g.game_step(0)
    g.game_step(SELECT)
    for _ in range(tuning("RESULTS_LOCK")):
        g.game_step(START)
        assert g.game_ended()
    g.game_step(START)
    assert g.rules_scene() == SC_TITLE and not g.game_ended()


def test_select_in_play_does_nothing(g):
    to_play(g)
    g.game_step(SELECT)
    assert g.rules_scene() == SC_PLAY


def test_hash_follows_state(g):
    keys = [START, 0, START, 0] + [RIGHT] * 20
    assert T.pc_hashes(g, keys) == T.pc_hashes(g, keys)
    assert T.pc_hashes(g, keys)[-1] != T.pc_hashes(g, keys[:-1] + [0])[-1]


def test_short_run_fixture_ends(lib, short_run):
    assert len(T.pc_run_end(lib, short_run)) == len(short_run)
    assert tuning("GHOST_PERIOD") == 2
