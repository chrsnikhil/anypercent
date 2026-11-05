"""PB on screen: the queue of lines in the model, the app's hooks (after a run, once a day) and the drawing."""
import time

import pytest

from arca_launcher.actions import Action as A
from arca_launcher.__main__ import build_config
from arca_launcher.app import App, Config
from arca_launcher.coach import MOODS, Line
from arca_launcher.model import Launch, Nav, Screen
from arca_launcher.touch import Press, Tap
from conftest import distinct_colours, snapshot
from test_app import FakeHw, FakeRunner
from test_model import GAMES

HI, BYE = Line("happy", "Hi there."), Line("serious", "Ready for a record attempt?")


# --- the model ------------------------------------------------------------------------------------------------------
def test_pb_says_lines_one_at_a_time_and_a_button_only_moves_on():
    nav = Nav(GAMES)
    nav.say([HI, BYE])
    assert nav.mascot == HI
    assert nav.apply(A.A) is None and nav.mascot == BYE           # A moved PB on; it did not launch a game
    assert nav.apply(A.B) is None and nav.mascot is None
    assert nav.apply(A.A) == Launch(nav.row[0])                   # with PB quiet, A plays again


def test_more_lines_wait_their_turn():
    nav = Nav(GAMES)
    nav.say([HI])
    nav.say([BYE])
    assert nav.mascot == HI
    nav.advance_mascot()
    assert nav.mascot == BYE


def test_a_new_line_starts_with_no_words_and_no_time():
    nav = Nav(GAMES)
    nav.say([HI])
    nav.mascot_text, nav.mascot_ms = "Hey!", 900
    nav.say([BYE]); nav.advance_mascot()
    assert nav.mascot == BYE and nav.mascot_text is None and nav.mascot_ms == 0


def test_the_sleep_clock_still_wakes_first():
    nav = Nav(GAMES)
    nav.say([HI])
    nav.stack.append(Screen.SLEEP)
    nav.apply(A.A)
    assert nav.screen is Screen.HOME and nav.mascot == HI


# --- the app --------------------------------------------------------------------------------------------------------
def make(library_dir, tmp_path, coach=True, voice=None):
    cfg = Config(library_dir=library_dir, state_path=str(tmp_path / "state.json"), splash=False,
                 run_dir=str(tmp_path / "run"), coach=coach)
    return App(cfg, runner=FakeRunner(), hw=FakeHw(), voice=voice)


def test_the_launcher_turns_pb_on_by_default_and_off_on_request():
    assert build_config([]).coach is True
    assert build_config(["--no-coach"]).coach is False


def test_the_voice_key_lives_beside_the_state_file():
    import os
    cfg = build_config(["--state", "/data/state/state.json"])
    assert cfg.coach_voice_key == os.path.join("/data/state", "coach-voice.key")
    assert build_config(["--coach-voice-key", "/k"]).coach_voice_key == "/k"


def test_pb_says_hello_once_a_day(library_dir, tmp_path):
    app = make(library_dir, tmp_path)
    assert app.nav.mascot is not None and app.nav.mascot.kind == "greeting"
    app.close()
    again = make(library_dir, tmp_path)
    assert again.nav.mascot is None
    again.close()


def test_pb_is_quiet_when_switched_off(library_dir, tmp_path):
    app = make(library_dir, tmp_path, coach=False)
    assert app.nav.mascot is None
    app.close()


def test_after_a_run_pb_says_how_it_went(library_dir, tmp_path):
    app = make(library_dir, tmp_path)
    app.nav.advance_mascot()                                     # past the hello
    rumbles = []
    app.inputs.rumble = lambda lo, hi, ms: rumbles.append(ms)

    class Bridge:
        def after(self, rom, arcade):
            return {"finished": True, "new_best": True, "time_frames": 4892, "vs_best": {"best_frames": 4986, "splits": None}}

        def history(self, gid):
            return [4892]
    app._bridge = Bridge()
    app._arcade_result("after", app.nav.games[0], {"id": "SHIP"})
    assert app.nav.mascot.kind == "new_best" and "1:21.53" in app.nav.mascot.text
    assert app.nav.notice is None and max(rumbles) >= 300
    app.close()


def test_a_bridge_without_history_still_gets_a_line(library_dir, tmp_path):
    app = make(library_dir, tmp_path)
    app.nav.advance_mascot()

    class Bridge:
        def after(self, rom, arcade):
            return {"finished": True, "new_best": True, "time_frames": 1234}
    app._bridge = Bridge()
    app._arcade_result("after", app.nav.games[0], {"id": "SHIP"})
    assert app.nav.mascot.kind == "first_finish"
    app.close()


def test_pb_is_still_talking_after_the_game_it_is_talking_about(library_dir, tmp_path):
    """The launcher waits while a game runs, so the first frame back measures the whole game. PB's line must not
    count that wait as time on screen: on the handheld (2026-10-24) a new best's line was gone before anyone saw it."""
    app = make(library_dir, tmp_path)
    app.nav.advance_mascot()                                     # past the hello

    class Bridge:
        def after(self, rom, arcade):
            return {"finished": True, "new_best": True, "time_frames": 6490}
    app._bridge = Bridge()
    app._arcade_result("after", app.nav.games[0], {"id": "MDGP"})
    app.frame(16)                                                # the line starts
    app.frame(120_000)                                           # the frame that waited for the game (2 minutes)
    assert app.nav.mascot is not None and app.nav.mascot.kind == "first_finish"
    app.close()


def test_a_tap_moves_pb_on_and_lands_on_nothing(library_dir, tmp_path):
    app = make(library_dir, tmp_path)
    app.frame(16, touches=[Press(97, 161), Tap(97, 161)])         # on the first tile, under PB
    assert app.nav.mascot is None and app.runner.roms == []
    app.close()


def test_pb_moves_on_by_itself_after_the_line_has_been_read(library_dir, tmp_path):
    app = make(library_dir, tmp_path)
    for _ in range(300):                                         # 30 s of ordinary frames
        app.frame(100)
    assert app.nav.mascot is None
    app.close()


def test_the_words_appear_at_once_without_a_voice(library_dir, tmp_path):
    app = make(library_dir, tmp_path)
    app.frame(16)
    assert app.nav.mascot_text == app.nav.mascot.text
    app.close()


class SlowVoice:
    def __init__(self, answer):
        import concurrent.futures as cf
        self.answer, self.future = answer, cf.Future()

    def submit(self, line):
        return self.future


def test_the_voice_rewords_a_line_when_it_answers_in_time(library_dir, tmp_path):
    voice = SlowVoice("Hey hey! I'm PB.")
    app = make(library_dir, tmp_path, voice=voice)
    app.frame(16)
    assert app.nav.mascot_text is None                            # PB is thinking
    voice.future.set_result(voice.answer)
    app.frame(16)
    assert app.nav.mascot_text == "Hey hey! I'm PB."
    app.close()


def test_a_slow_or_silent_voice_falls_back_to_the_line(library_dir, tmp_path):
    voice = SlowVoice(None)
    app = make(library_dir, tmp_path, voice=voice)
    for _ in range(20):                                          # 2 s of ordinary frames, past the 1.5 s wait
        app.frame(100)
    assert app.nav.mascot_text == app.nav.mascot.text
    app.close()


# --- the drawing ----------------------------------------------------------------------------------------------------
def test_every_mood_is_a_distinct_40px_sprite():
    pygame = pytest.importorskip("pygame")
    from arca_launcher.render.mascot import sprite_surface
    sprites = {m: sprite_surface(m) for m in MOODS}
    assert all(s.get_size() == (40, 40) for s in sprites.values())
    raw = {m: pygame.image.tobytes(s, "RGBA") for m, s in sprites.items()}
    assert len(set(raw.values())) == len(MOODS)


def test_pb_is_drawn_over_home(screen):
    from arca_launcher.render.chrome import Status
    from arca_launcher.render.views import Views
    nav = Nav(screen.games)
    nav.say([Line("excited", "1:21.53! New personal best, 1.57 s faster. I replayed your log and it matches.")])
    nav.mascot_text, nav.mascot_ms = nav.mascot.text, 60000
    views = Views(screen.gfx, screen.art)
    views.draw(nav, 16, Status("9:41 PM", None))
    out = snapshot(screen.ren, "mascot-home")
    assert distinct_colours(out) > 20


def test_pb_thinking_shows_no_words_yet(screen):
    from arca_launcher.render.chrome import Status
    from arca_launcher.render.views import Views
    nav = Nav(screen.games)
    nav.say([Line("thinking", "Some words that must not show yet.")])
    views = Views(screen.gfx, screen.art)
    views.draw(nav, 16, Status("9:41 PM", None))
    snapshot(screen.ren, "mascot-thinking")
    assert views.mascot.shown == ""


def test_words_type_out_over_time(screen):
    from arca_launcher.render.mascot import MascotView
    nav = Nav(screen.games)
    nav.say([HI])
    nav.mascot_text = HI.text
    view = MascotView(screen.gfx)
    nav.mascot_ms = 0
    view.draw(nav)
    early = view.shown
    nav.mascot_ms = 60000
    view.draw(nav)
    assert len(early) < len(view.shown) == len(HI.text)
