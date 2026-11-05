import os

from arca_launcher import settings
from arca_launcher.__main__ import build_config
from arca_launcher.actions import Action
from arca_launcher.app import App, Config
from arca_launcher.runner import RunResult
from conftest import snapshot


class FakeRunner:
    def __init__(self, ok=True):
        self.ok, self.roms = ok, []
        self.touch_controls = None
        self.touch_at_run = []

    def run(self, rom, resume=False, states=False):
        self.roms.append(rom)
        self.touch_at_run.append(self.touch_controls)
        self.resumes = getattr(self, "resumes", []) + [(resume, states)]
        return RunResult(self.ok, 0 if self.ok else 1)


class FakeHw:
    def __init__(self, brightness_ok=False):
        self.volumes, self.brightness = [], []
        self.brightness_ok = brightness_ok
        self.powered_off = 0

    def battery_percent(self):
        return 55

    def brightness_available(self):
        return self.brightness_ok

    def power_off(self):
        self.powered_off += 1
        return True

    def set_volume(self, pct):
        self.volumes.append(pct)
        return True

    def set_brightness(self, pct):
        self.brightness.append(pct)
        return True


def make(library_dir, tmp_path, runner=None):
    cfg = Config(library_dir=library_dir, state_path=str(tmp_path / "state.json"), splash=False,
                 run_dir=str(tmp_path / "run"))
    return App(cfg, runner=runner or FakeRunner(), hw=FakeHw())


def test_quitting_with_the_home_key_is_not_a_crash(library_dir, tmp_path):
    import time
    (tmp_path / "run").mkdir()

    class Quit(FakeRunner):                                  # the PS-button daemon marks it, then ends the emulator
        def run(self, rom, **_):
            (tmp_path / "run" / "home-quit").write_text(f"{time.time()}\n")
            return RunResult(False, 143, "retroarch exited with code 143")
    app = make(library_dir, tmp_path, Quit())
    app.frame(16, [Action.A])
    assert app.nav.notice is None
    app.close()


def test_play_a_game_and_come_back(library_dir, tmp_path):
    runner = FakeRunner()
    app = make(library_dir, tmp_path, runner)
    first_display = app.display
    app.frame(16, [Action.A])                                # Alpha Quest, first A to Z
    assert runner.roms and runner.roms[0].endswith(os.path.join("built", "alpha-quest.gb"))
    assert app.display is not first_display                  # the window was handed over and reopened
    assert app.nav.selected.id == "alpha-quest" and app.nav.notice is None
    assert "alpha-quest" in settings.load(str(tmp_path / "state.json")).last_played
    app.frame(16)
    snapshot(app.display.renderer, "app-after-game")
    app.close()


def test_a_crash_shows_a_notice_for_eight_seconds(library_dir, tmp_path):
    # a crash is worth noticing: it stays longer than the 3 s of other notices (on the device it comes up as the
    # start-up splash ends, where 3 s went by unseen)
    app = make(library_dir, tmp_path, FakeRunner(ok=False))
    app.frame(16, [Action.A])
    assert app.nav.notice == "Alpha Quest closed unexpectedly"
    app.frame(5000)                              # the loop's first delta after a game spans the whole game
    assert app.nav.notice is not None
    for _ in range(78):
        app.frame(100)
    assert app.nav.notice is not None            # about 7.9 s on screen
    for _ in range(3):
        app.frame(100)
    assert app.nav.notice is None
    app.close()


def test_other_notices_still_last_three_seconds(library_dir, tmp_path):
    app = make(library_dir, tmp_path)
    app.nav.notice = "New best on Alpha Quest!"
    app.frame(16)
    for _ in range(31):
        app.frame(100)
    assert app.nav.notice is None
    app.close()


def test_volume_is_applied_and_saved(library_dir, tmp_path):
    app = make(library_dir, tmp_path)
    app.frame(16, [Action.R, Action.RIGHT])
    assert app.hw.volumes == [80, 90]
    assert settings.load(str(tmp_path / "state.json")).volume == 90
    app.close()


def test_missing_library_shows_a_message(tmp_path):
    app = make(str(tmp_path / "nowhere"), tmp_path)
    assert app.error and "No game library" in app.error
    app.frame(16, [Action.A, Action.RIGHT, Action.R])
    snapshot(app.display.renderer, "app-no-library")
    app.close()


def test_command_line():
    cfg = build_config(["--library", "/lib", "--scale", "2", "--emulator", "retroarch", "--fps"])
    assert (cfg.library_dir, cfg.scale, cfg.emulator, cfg.show_fps, cfg.fullscreen) == ("/lib", 2, "retroarch", True, False)


def test_a_direction_held_when_play_is_pressed_does_not_survive_the_game(library_dir, tmp_path):
    import pygame
    app = make(library_dir, tmp_path)
    app.inputs.translate(pygame.event.Event(pygame.JOYHATMOTION, hat=0, value=(1, 0), instance_id=0))
    app.frame(16, [Action.A])                   # thumb still on the D-pad while pressing Play
    assert app.inputs.tick(5000) == []          # its release was lost while the game ran: forget the hold
    assert app.nav.selected.id == "alpha-quest"
    app.close()


def test_joy_map_option_reaches_the_input_mapper(library_dir, tmp_path):
    import pygame
    cfg = build_config(["--library", library_dir, "--state", str(tmp_path / "s.json"), "--joy-map", "a=3,start=0"])
    app = App(cfg, runner=FakeRunner(), hw=FakeHw())
    assert app.inputs.translate(pygame.event.Event(pygame.JOYBUTTONDOWN, button=3, instance_id=0)) is Action.A
    assert app.inputs.translate(pygame.event.Event(pygame.JOYBUTTONDOWN, button=0, instance_id=0)) is Action.START
    app.close()


def test_the_window_is_called_any_percent(library_dir, tmp_path):
    app = make(library_dir, tmp_path)
    assert app.display.window.title == "Any%"
    app.close()


def test_the_splash_plays_once_and_a_button_skips_it_without_launching(library_dir, tmp_path):
    runner = FakeRunner()
    app = App(Config(library_dir=library_dir, state_path=str(tmp_path / "s.json")), runner=runner, hw=FakeHw())
    assert app.splash is not None
    app.frame(16)
    snapshot(app.display.renderer, "app-splash")
    app.frame(16, [Action.A])                    # skips the splash; must not also press Play
    assert runner.roms == [] and app.splash.fading
    for _ in range(10):
        app.frame(50)
    assert app.splash is None                    # faded into Home
    app.frame(16, [Action.A])
    assert len(runner.roms) == 1 and app.splash is None     # no replay after a game
    app.close()


def test_no_splash_option():
    assert build_config(["--no-splash"]).splash is False
    assert build_config([]).splash is True


class FakeBridge:
    def __init__(self, log, fail=False):
        self.log, self.fail = log, fail

    def before(self, rom, arcade):
        self.log.append(("before", rom, arcade["id"]))
        if self.fail:
            raise RuntimeError("bridge down")

    def after(self, rom, arcade):
        self.log.append(("after", rom, arcade["id"]))
        if self.fail:
            raise RuntimeError("bridge down")


class LoggingRunner(FakeRunner):
    def __init__(self, log):
        super().__init__()
        self.log = log

    def run(self, rom, **_):
        self.log.append(("run", rom))
        return super().run(rom)


def arcade_library(tmp_path):
    import json
    rom = tmp_path / "ship-it.gba"
    rom.write_bytes(b"rom")
    lib = tmp_path / "arclib"
    lib.mkdir()
    (lib / "library.json").write_text(json.dumps({"version": 1, "games": [
        {"id": "ship-it", "title": "SHIP IT!", "rom": str(rom), "arcade": {"id": "SHIP", "replay": "/x"}}]}))
    return str(lib), str(rom)


def test_an_arcade_game_goes_through_the_bridge(tmp_path):
    lib, rom = arcade_library(tmp_path)
    log = []
    cfg = Config(library_dir=lib, state_path=str(tmp_path / "state.json"), splash=False)
    app = App(cfg, runner=LoggingRunner(log), hw=FakeHw(), bridge=FakeBridge(log))
    app.frame(16, [Action.A])
    assert log == [("before", rom, "SHIP"), ("run", rom), ("after", rom, "SHIP")]
    app.close()


def test_a_failing_bridge_does_not_stop_the_launch(tmp_path):
    lib, rom = arcade_library(tmp_path)
    log = []
    cfg = Config(library_dir=lib, state_path=str(tmp_path / "state.json"), splash=False)
    app = App(cfg, runner=LoggingRunner(log), hw=FakeHw(), bridge=FakeBridge(log, fail=True))
    app.frame(16, [Action.A])
    assert ("run", rom) in log and log[-1] == ("after", rom, "SHIP")
    assert app.nav.notice is None
    app.close()


def test_a_plain_game_skips_the_bridge(library_dir, tmp_path):
    log = []
    app = App(Config(library_dir=library_dir, state_path=str(tmp_path / "s.json"), splash=False),
              runner=LoggingRunner(log), hw=FakeHw(), bridge=FakeBridge(log))
    app.frame(16, [Action.A])
    assert [e[0] for e in log] == ["run"]
    app.close()


def test_runs_dir_option():
    assert build_config([]).runs_dir == "/opt/arca-sandbox/runs"
    assert build_config(["--runs", "/r"]).runs_dir == "/r"


def test_handler_options():
    assert build_config([]).handler is True                    # PB the handler: on in the launcher
    assert build_config(["--no-handler"]).handler is False
    assert Config(library_dir="/l", state_path="/s").handler is False      # and off unless asked (tests)
    assert build_config([]).testlogs_dir == "/opt/anypercent/testlogs"
    assert build_config(["--testlogs", "/t"]).testlogs_dir == "/t"
    assert build_config([]).handler_warm is True                          # boards read in the background after start
    assert build_config(["--no-handler"]).handler_warm is False
    assert Config(library_dir="/l", state_path="/s").handler_warm is False


def test_the_booth_link_comes_from_a_file_beside_the_state(library_dir, tmp_path):
    """booth-url.txt (set over SSH at the event): attract mode shows it as a QR code. No file, or not a web link,
    no QR."""
    app = make(library_dir, tmp_path)
    assert app.nav.booth_url is None
    app.close()
    (tmp_path / "booth-url.txt").write_text("https://ethglobal.com/showcase/any-percent\n")
    app = make(library_dir, tmp_path)
    assert app.nav.booth_url == "https://ethglobal.com/showcase/any-percent"
    app.close()
    (tmp_path / "booth-url.txt").write_text("rm -rf /\n")
    app = make(library_dir, tmp_path)
    assert app.nav.booth_url is None
    app.close()


def test_a_crash_still_closes_the_app(monkeypatch):
    """Closing drops the background replays still queued: a crashed launcher exits at once, so systemd restarts it
    without waiting for them."""
    import pytest
    from arca_launcher import __main__ as main_module
    closed = []

    class Crashing:
        def __init__(self, cfg):
            pass

        def run(self):
            raise RuntimeError("a frame went wrong")

        def close(self):
            closed.append(True)
    monkeypatch.setattr(main_module, "App", Crashing)
    with pytest.raises(RuntimeError):
        main_module.main([])
    assert closed == [True]



def test_the_bridge_follows_the_emulator(tmp_path):
    lib, rom = arcade_library(tmp_path)
    log = []
    cfg = Config(library_dir=lib, state_path=str(tmp_path / "state.json"), splash=False, emulator="retroarch",
                 runs_dir=str(tmp_path / "runs"))
    app = App(cfg, runner=LoggingRunner(log), hw=FakeHw())
    app.frame(16, [Action.A])
    assert ("run", rom) in log
    assert os.path.exists(rom[:-4] + ".srm") and not os.path.exists(rom[:-4] + ".sav")   # RetroArch's save file
    app.close()


# touch ------------------------------------------------------------------------------------------------------------

def test_tap_a_tile_then_tap_it_again_to_play(library_dir, tmp_path):
    from arca_launcher.render import theme
    from arca_launcher.touch import Tap
    runner = FakeRunner()
    app = make(library_dir, tmp_path, runner)
    for _ in range(30):
        app.frame(16)
    second = (theme.MARGIN + theme.TILE_BIG + theme.TILE_GAP + theme.TILE // 2, theme.ROW_Y + theme.TILE_BIG // 2)
    app.frame(16, touches=[Tap(*second)])
    assert app.nav.row_index == 1 and runner.roms == []
    for _ in range(30):
        app.frame(16)                                         # the row slides: the selected tile is first on screen
    app.frame(16, touches=[Tap(theme.MARGIN + theme.TILE_BIG // 2, theme.ROW_Y + theme.TILE_BIG // 2)])
    assert len(runner.roms) == 1 and runner.roms[0].endswith("beta-blocks.gbc")
    app.close()


def test_swipe_scrolls_the_home_row(library_dir, tmp_path):
    from arca_launcher.touch import Swipe
    app = make(library_dir, tmp_path)
    app.frame(16)
    app.frame(16, touches=[Swipe(-290, 0, 600, 160)])        # about two tiles of travel, finger moving left
    assert app.nav.row_index == 2
    app.frame(16, touches=[Swipe(140, 0, 200, 160)])
    assert app.nav.row_index == 1
    app.close()


def test_settings_slider_tap_applies_and_saves_the_volume(library_dir, tmp_path):
    from arca_launcher.touch import Tap
    app = make(library_dir, tmp_path)
    app.frame(16, [Action.R])
    bar = app.display.views.settings.bars[0]
    app.frame(16, touches=[Tap(bar.x + bar.w // 2, bar.centery)])
    assert app.hw.volumes[-1] == 50
    assert settings.load(str(tmp_path / "state.json")).volume == 50
    app.close()


def test_a_tap_skips_the_splash_without_launching(library_dir, tmp_path):
    from arca_launcher.touch import Tap
    runner = FakeRunner()
    app = App(Config(library_dir=library_dir, state_path=str(tmp_path / "s.json")), runner=runner, hw=FakeHw())
    app.frame(16)
    app.frame(16, touches=[Tap(97, 161)])                     # right on the first tile under the splash
    assert runner.roms == [] and app.splash.fading
    app.close()


def test_poll_turns_events_into_actions_and_touches_once_each(library_dir, tmp_path):
    import pygame
    from arca_launcher.touch import Press, Tap
    app = make(library_dir, tmp_path)
    E = pygame.event.Event
    events = [E(pygame.KEYDOWN, key=pygame.K_RIGHT, mod=0, unicode="", scancode=0),
              E(pygame.FINGERDOWN, touch_id=3, finger_id=0, x=0.5, y=0.5, dx=0.0, dy=0.0, pressure=1.0),
              E(pygame.MOUSEBUTTONDOWN, pos=(400, 240), button=1, touch=True),
              E(pygame.FINGERUP, touch_id=3, finger_id=0, x=0.5, y=0.5, dx=0.0, dy=0.0, pressure=1.0),
              E(pygame.MOUSEBUTTONUP, pos=(400, 240), button=1, touch=True)]
    quit_, actions, touches = app.poll(events)
    assert not quit_ and actions == [Action.RIGHT] and touches == [Press(400, 240), Tap(400, 240)]
    assert app.poll([E(pygame.QUIT)])[0]
    app.close()


def test_a_touch_held_when_a_game_starts_does_not_survive_it(library_dir, tmp_path):
    import pygame
    app = make(library_dir, tmp_path)
    app.frame(16)
    E = pygame.event.Event
    app.poll([E(pygame.FINGERDOWN, touch_id=3, finger_id=0, x=0.9, y=0.9, dx=0.0, dy=0.0, pressure=1.0)])
    app.frame(16, [Action.A])                                 # a game ran while that finger was down
    _, _, touches = app.poll([E(pygame.FINGERUP, touch_id=3, finger_id=0, x=0.9, y=0.9, dx=0.0, dy=0.0,
                                pressure=1.0)])
    assert touches == []
    app.close()


# instant touch: act on the finger landing, follow it while it moves ----------------------------------------------

def home_ready(library_dir, tmp_path, runner=None):
    app = make(library_dir, tmp_path, runner)
    for _ in range(30):
        app.frame(16)
    return app


def tile_centre(i=0):
    from arca_launcher.render import theme
    x = theme.MARGIN + theme.TILE_BIG // 2 if i == 0 else \
        theme.MARGIN + theme.TILE_BIG + theme.TILE_GAP + (i - 1) * (theme.TILE + theme.TILE_GAP) + theme.TILE // 2
    return x, theme.ROW_Y + theme.TILE_BIG // 2


def test_a_tile_is_selected_the_moment_the_finger_lands(library_dir, tmp_path):
    from arca_launcher.touch import Press, Tap
    runner = FakeRunner()
    app = home_ready(library_dir, tmp_path, runner)
    app.frame(16, touches=[Press(*tile_centre(1))])
    assert app.nav.row_index == 1                               # before the finger lifts
    app.frame(16, touches=[Tap(*tile_centre(1))])
    assert runner.roms == []                                    # it was not selected when the finger landed
    for _ in range(30):
        app.frame(16)
    app.frame(16, touches=[Press(*tile_centre(0))])
    assert runner.roms == [] and app.nav.pressed == ("tile", 1)   # pressed: launches on release
    app.frame(16, touches=[Tap(*tile_centre(0))])
    assert len(runner.roms) == 1 and runner.roms[0].endswith("beta-blocks.gbc")
    app.close()


def test_a_drag_that_starts_on_the_selected_tile_never_launches(library_dir, tmp_path):
    from arca_launcher.touch import Drag, Press, Swipe
    runner = FakeRunner()
    app = home_ready(library_dir, tmp_path, runner)
    x, y = tile_centre(0)
    app.frame(16, touches=[Press(x, y)])
    app.frame(16, touches=[Drag(-20, 0, x, y)])
    assert app.nav.pressed is None
    app.frame(16, touches=[Drag(-5, 0, x, y), Swipe(-5, 0, x, y)])     # and came back: still no launch
    assert runner.roms == [] and app.nav.row_index == 0
    app.close()


def test_the_home_row_follows_the_finger_and_the_selection_moves_during_the_drag(library_dir, tmp_path):
    from arca_launcher.touch import Drag, Press, Swipe
    app = home_ready(library_dir, tmp_path)
    home = app.display.views.home
    app.frame(16, touches=[Press(600, 330)])                    # below the tiles: nothing under the finger
    app.frame(16, touches=[Drag(-100, 0, 600, 330)])
    assert home.held == 100 and app.nav.row_index == 1          # past half a tile: the next one is selected
    app.frame(16, touches=[Drag(-300, 0, 600, 330)])
    assert home.held == 300 and app.nav.row_index == 2
    app.frame(16, touches=[Drag(-250, 0, 600, 330)])
    assert app.nav.row_index == 2
    app.frame(16, touches=[Swipe(-250, 0, 600, 330)])
    assert home.held is None and app.nav.row_index == 2
    assert 240 < home.scroll.value < 260                       # eases on from where the finger left it
    app.close()


def test_a_flick_goes_further_and_a_slow_short_drag_snaps_back(library_dir, tmp_path):
    from arca_launcher.touch import Drag, Press, Swipe
    app = home_ready(library_dir, tmp_path)
    for vx, want in ((0.0, 0), (-0.8, 1), (-2.0, 2)):
        start = app.nav.row_index
        app.frame(16, touches=[Press(600, 330), Drag(-60, 0, 600, 330), Swipe(-60, 0, 600, 330, vx, 0.0)])
        assert app.nav.row_index - start == want, vx
        for _ in range(30):
            app.frame(16)
    app.close()


def test_the_library_grid_steps_while_the_finger_moves(library_dir, tmp_path):
    from dataclasses import replace
    from arca_launcher.library import load_library
    from arca_launcher.model import Screen
    from arca_launcher.touch import Drag, Press, Swipe
    app = home_ready(library_dir, tmp_path)
    games = load_library(library_dir)
    app.nav = type(app.nav)([replace(games[0], id=f"g{i:02d}", title=f"Game {i:02d}") for i in range(12)])
    app.nav.stack.append(Screen.LIBRARY)
    for _ in range(3):
        app.frame(16)
    app.frame(16, touches=[Press(770, 300), Drag(0, -160, 770, 300)])     # right of the grid: no tile there
    assert app.nav.grid_index == 5                              # one row down while still dragging
    app.frame(16, touches=[Drag(0, -320, 770, 300)])
    assert app.nav.grid_index == 10
    app.frame(16, touches=[Swipe(0, -320, 770, 300)])
    assert app.nav.grid_index == 10 and app.nav.screen is Screen.LIBRARY
    app.close()


def test_a_slider_follows_the_finger(library_dir, tmp_path):
    from arca_launcher.touch import Drag, Press, Swipe
    app = make(library_dir, tmp_path)
    app.frame(16, [Action.R])
    bar = app.display.views.settings.bars[0]
    x, y = bar.x + bar.w // 2, bar.centery
    app.frame(16, touches=[Press(x, y)])
    assert app.hw.volumes[-1] == 50
    app.frame(16, touches=[Drag(round(bar.w * 0.3), 0, x, y)])
    assert app.hw.volumes[-1] == 80
    app.frame(16, touches=[Drag(-bar.w, 0, x, y), Swipe(-bar.w, 0, x, y)])
    assert app.hw.volumes[-1] == 0 and settings.load(str(tmp_path / "state.json")).volume == 0
    app.close()


def test_buttons_act_on_release_and_not_when_dragged_off(library_dir, tmp_path):
    from arca_launcher.model import Screen
    from arca_launcher.render import theme
    from arca_launcher.touch import Drag, Press, Swipe, Tap
    app = home_ready(library_dir, tmp_path)
    tab = (theme.MARGIN + 90, theme.TOP_Y + 8)
    app.frame(16, touches=[Press(*tab)])
    assert app.nav.screen is Screen.HOME and app.nav.pressed == ("tab", "settings")
    app.frame(16, touches=[Tap(*tab)])
    assert app.nav.screen is Screen.SETTINGS
    games = (theme.MARGIN + 10, theme.TOP_Y + 8)
    app.frame(16, touches=[Press(*games), Drag(0, 100, *games), Swipe(0, 100, *games)])
    assert app.nav.screen is Screen.SETTINGS
    app.close()


def test_a_finger_that_skips_the_splash_does_nothing_when_it_lifts(library_dir, tmp_path):
    from arca_launcher.touch import Press, Tap
    runner = FakeRunner()
    app = App(Config(library_dir=library_dir, state_path=str(tmp_path / "s.json")), runner=runner, hw=FakeHw())
    app.frame(16)
    app.frame(16, touches=[Press(*tile_centre(0))])
    assert app.splash.fading
    for _ in range(40):
        app.frame(50)
    assert app.splash is None
    app.frame(16, touches=[Tap(*tile_centre(0))])               # held through the fade, then lifted on the tile
    assert runner.roms == [] and app.nav.pressed is None
    app.frame(16, touches=[Press(*tile_centre(0)), Tap(*tile_centre(0))])
    assert len(runner.roms) == 1                                # the next touch works as usual
    app.close()


def test_on_screen_controls_start_off_and_the_runner_is_told(library_dir, tmp_path):
    runner = FakeRunner()
    app = make(library_dir, tmp_path, runner)
    assert app.nav.touch_controls is False and runner.touch_controls is False
    app.close()


def test_on_screen_controls_setting_is_saved_and_reaches_the_runner(library_dir, tmp_path):
    from arca_launcher.model import SETTINGS_ROWS
    runner = FakeRunner()
    app = make(library_dir, tmp_path, runner)
    app.frame(16, [Action.R] + [Action.DOWN] * SETTINGS_ROWS.index("controls") + [Action.A])
    assert runner.touch_controls is True
    assert settings.load(str(tmp_path / "state.json")).touch_controls is True
    app.close()
    again = FakeRunner()
    app = make(library_dir, tmp_path, again)                  # remembered across restarts
    assert app.nav.touch_controls is True and again.touch_controls is True
    app.frame(16, [Action.R] + [Action.DOWN] * SETTINGS_ROWS.index("controls") + [Action.LEFT])        # left is Off
    assert again.touch_controls is False and settings.load(str(tmp_path / "state.json")).touch_controls is False
    app.close()


def test_on_screen_controls_switch_tap(library_dir, tmp_path):
    from arca_launcher.model import SETTINGS_ROWS
    from arca_launcher.touch import Tap
    runner = FakeRunner()
    app = make(library_dir, tmp_path, runner)
    app.frame(16, [Action.R])
    sw = app.display.views.settings.switches[SETTINGS_ROWS.index("controls")]
    app.frame(16, touches=[Tap(sw.centerx, sw.centery)])
    assert runner.touch_controls is True and settings.load(str(tmp_path / "state.json")).touch_controls is True
    app.close()


def test_the_runner_gets_the_overlay_path(library_dir, tmp_path):
    cfg = build_config(["--library", library_dir, "--state", str(tmp_path / "s.json"), "--emulator", "retroarch",
                        "--overlay", "/x/gamepad.cfg"])
    assert cfg.overlay == "/x/gamepad.cfg"
    app = App(cfg, hw=FakeHw())
    assert app.runner.overlay == "/x/gamepad.cfg" and app.runner.touch_controls is False
    app.close()
    assert build_config([]).overlay == "/opt/anypercent/overlays/gamepad.cfg"


def settings_row(app, key):
    from arca_launcher.model import SETTINGS_ROWS
    app.frame(16, [Action.R])
    while SETTINGS_ROWS[app.nav.settings_index] != key:
        app.frame(16, [Action.DOWN])


def test_power_off_saves_settings_then_shuts_down(library_dir, tmp_path):
    app = make(library_dir, tmp_path)
    settings_row(app, "power")
    app.frame(16, [Action.A])
    assert app.hw.powered_off == 0                         # the first press only asks
    app.frame(16, [Action.A])
    assert app.hw.powered_off == 1
    assert os.path.exists(str(tmp_path / "state.json"))
    app.close()


def test_sleep_dims_the_backlight_and_wake_restores_it(library_dir, tmp_path):
    cfg = Config(library_dir=library_dir, state_path=str(tmp_path / "state.json"), splash=False)
    app = App(cfg, runner=FakeRunner(), hw=FakeHw(brightness_ok=True))
    settings_row(app, "sleep")
    app.frame(16, [Action.A])
    assert app.sleeping and app.hw.brightness[-1] < app.nav.brightness
    app.frame(16, [Action.B])
    assert not app.sleeping and app.hw.brightness[-1] == app.nav.brightness
    app.close()


def test_a_touch_wakes_from_sleep_and_does_nothing_else(library_dir, tmp_path):
    from arca_launcher.touch import Press, Tap
    app = make(library_dir, tmp_path)
    settings_row(app, "sleep")
    app.frame(16, [Action.A])
    index = app.nav.settings_index
    app.frame(16, touches=[Press(400, 300)])
    assert not app.sleeping
    app.frame(16, touches=[Tap(400, 300)])                 # its lift must not tap whatever is under it
    assert app.nav.settings_index == index and app.hw.powered_off == 0
    app.close()


def test_on_screen_controls_stay_hidden_while_a_controller_is_connected(library_dir, tmp_path):
    runner = FakeRunner()
    app = make(library_dir, tmp_path, runner)
    app.prefs.touch_controls = app.nav.touch_controls = True
    app.runner.touch_controls = True
    app.inputs.controllers[7] = object()                   # a DualSense paired
    app.frame(16, [Action.A])
    assert runner.touch_at_run[-1] is False
    app.inputs.controllers.clear()                          # unpaired: the overlay comes back
    app.frame(16, [Action.A])
    assert runner.touch_at_run[-1] is True
    app.close()



class PadHw(FakeHw):
    def __init__(self):
        super().__init__()
        self.lightbar = []

    def set_lightbar(self, rgb):
        self.lightbar.append(tuple(rgb))
        return True

    def controller_battery(self):
        return 77


def test_picking_a_theme_saves_it_colours_the_light_bar_and_rumbles(library_dir, tmp_path):
    from arca_launcher.render import theme
    from arca_launcher.themes import THEMES
    cfg = Config(library_dir=library_dir, state_path=str(tmp_path / "state.json"), splash=False)
    app = App(cfg, runner=FakeRunner(), hw=PadHw())
    rumbles = []
    app.inputs.rumble = lambda lo, hi, ms: rumbles.append(ms)
    app.frame(16, [Action.THEMES, Action.DOWN, Action.A])
    picked = THEMES[1]
    assert settings.load(str(tmp_path / "state.json")).theme == picked.id
    assert theme.BG == picked.bg and app.hw.lightbar[-1] == picked.light and rumbles
    app.close()
    again = App(cfg, runner=FakeRunner(), hw=PadHw())         # restored at start, light bar included
    assert theme.BG == picked.bg and again.hw.lightbar[-1] == picked.light
    again.frame(16, [Action.THEMES, Action.A])                # back to the first theme for the other tests
    again.close()


def test_a_minute_idle_on_home_starts_attract_mode_and_a_button_ends_it(library_dir, tmp_path):
    from arca_launcher.app import ATTRACT_MS
    from arca_launcher.model import Screen
    app = make(library_dir, tmp_path)
    for _ in range(ATTRACT_MS // 1000 + 1):
        app.frame(1000)
    assert app.nav.screen is Screen.ATTRACT
    app.frame(16, [Action.A])
    assert app.nav.screen is Screen.HOME and app.runner.roms == []          # woke up, launched nothing
    app.close()


def test_coming_back_from_a_long_game_is_not_idle_time(library_dir, tmp_path):
    """The first frame after a game measures the whole game (clock.tick): it must not count toward attract mode, or
    every game over a minute long would come back to the booth display instead of Home (and PB's word on the run)."""
    from arca_launcher.app import ATTRACT_MS
    from arca_launcher.model import Screen
    app = make(library_dir, tmp_path)
    app.frame(16, [Action.A])                                 # Play the selected game
    assert app.runner.roms
    app.frame(ATTRACT_MS * 3)                                 # the frame the game's three minutes land in
    assert app.nav.screen is Screen.HOME
    for _ in range(ATTRACT_MS // 1000 + 1):                   # a real idle minute afterwards still starts it
        app.frame(1000)
    assert app.nav.screen is Screen.ATTRACT
    app.close()


def test_attract_mode_waits_while_pb_is_talking(library_dir, tmp_path):
    from arca_launcher.app import ATTRACT_MS
    from arca_launcher.coach import Line
    from arca_launcher.model import Screen
    app = make(library_dir, tmp_path)
    app.nav.say([Line("happy", "Nice run! Your best is now 1:44.83.")])
    for _ in range(ATTRACT_MS // 1000 + 1):
        app.frame(1000)
        if app.nav.mascot is not None:
            assert app.nav.screen is Screen.HOME, "attract mode covered PB mid-line"
    app.close()


def test_a_new_best_rumbles_and_says_so(library_dir, tmp_path):
    runner = FakeRunner()
    app = make(library_dir, tmp_path, runner)
    rumbles = []
    app.inputs.rumble = lambda lo, hi, ms: rumbles.append(ms)

    class Bridge:
        def before(self, rom, arcade):
            pass

        def after(self, rom, arcade):
            return {"finished": True, "new_best": True, "time_frames": 1234}
    app._bridge = Bridge()
    app._arcade_result("after", app.nav.games[0], {"id": "SHIP"})
    assert app.nav.notice and "best" in app.nav.notice.lower() and max(rumbles) >= 300
    app.close()



class HealthHw(FakeHw):
    def wifi(self):
        return 0

    def power_warning(self):
        return "Low power"


def test_status_carries_wifi_and_the_power_warning(library_dir, tmp_path):
    cfg = Config(library_dir=library_dir, state_path=str(tmp_path / "state.json"), splash=False)
    app = App(cfg, runner=FakeRunner(), hw=HealthHw())
    s = app.status()
    assert s.wifi == 0 and s.warning == "Low power"
    app.close()


def test_a_stop_request_during_a_game_is_not_lost(library_dir, tmp_path):
    import os
    import signal

    class StoppedRunner(FakeRunner):
        def run(self, rom, **_):
            os.kill(os.getpid(), signal.SIGTERM)                   # systemd stopping the service mid-game
            return super().run(rom)
    app = make(library_dir, tmp_path, StoppedRunner())
    app.launch(app.nav.games[0])
    assert app.quitting
    assert app.run() == 0                                          # and the loop leaves at once


def test_sigterm_asks_the_launcher_to_stop(library_dir, tmp_path):
    import os
    import signal
    app = make(library_dir, tmp_path)
    os.kill(os.getpid(), signal.SIGTERM)
    assert app.quitting
    assert app.run() == 0



def test_haptics_option():
    assert build_config(["--haptics", "anypercent_haptics"]).haptics == "anypercent_haptics"
    assert build_config([]).haptics is None


def test_status_carries_the_controller_battery(library_dir, tmp_path):
    cfg = Config(library_dir=library_dir, state_path=str(tmp_path / "state.json"), splash=False)
    app = App(cfg, runner=FakeRunner(), hw=PadHw())
    assert app.status().pad == 77
    app.close()


def test_the_launcher_slows_down_when_nothing_moves(library_dir, tmp_path):
    from arca_launcher.app import IDLE_FPS, IDLE_FPS_AFTER_MS
    app = make(library_dir, tmp_path)
    assert app.target_fps() == 60
    app.frame(IDLE_FPS_AFTER_MS + 100)
    assert app.target_fps() == IDLE_FPS < 60
    app.frame(16, [Action.RIGHT])
    assert app.target_fps() == 60
    app.close()


class AppHw(FakeHw):
    def __init__(self):
        super().__init__()
        self.started = []

    def start_app(self, name):
        self.started.append(name)
        return True


def test_playing_an_app_starts_it_instead_of_a_rom(tmp_path):
    import json
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "library.json").write_text(json.dumps({"version": 1, "games": [
        {"id": "browser", "title": "Browser", "app": "browser", "platform": "App", "genre": "Web browser"}]}))
    runner = FakeRunner()
    app = App(Config(library_dir=str(lib), state_path=str(tmp_path / "s.json"), splash=False), runner=runner, hw=AppHw())
    assert app.nav.selected.id == "browser"
    app.frame(16, [Action.A])
    assert app.hw.started == ["browser"] and runner.roms == []
    app.frame(16)                                                # the Home screen still draws (the app's subtitle)
    app.close()


def _browser_library(tmp_path):
    import json
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "library.json").write_text(json.dumps({"version": 1, "games": [
        {"id": "browser", "title": "Browser", "app": "browser", "platform": "App", "genre": "Web browser"}]}))
    return str(lib)


def test_an_app_that_crashed_is_reported_when_the_launcher_comes_back(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "app-exit").write_text("anypercent-browser exit-code exited 139\n")   # left by the app's service
    cfg = Config(library_dir=_browser_library(tmp_path), state_path=str(tmp_path / "s.json"), splash=False,
                 run_dir=str(run))
    app = App(cfg, runner=FakeRunner(), hw=AppHw())
    assert app.nav.notice == "Browser closed unexpectedly"
    assert not (run / "app-exit").exists()
    app.close()


def test_an_app_closed_the_normal_way_says_nothing(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "app-exit").write_text("anypercent-browser success exited 0\n")
    cfg = Config(library_dir=_browser_library(tmp_path), state_path=str(tmp_path / "s.json"), splash=False,
                 run_dir=str(run))
    app = App(cfg, runner=FakeRunner(), hw=AppHw())
    assert app.nav.notice is None
    app.close()


def _first_game(library_dir):
    from arca_launcher.library import load_library
    return min(load_library(library_dir), key=lambda g: g.title.casefold())


def test_a_game_with_a_saved_place_continues_and_keeps_saving(library_dir, tmp_path):
    from arca_launcher.runner import state_path
    g = _first_game(library_dir)
    open(state_path(g.rom), "w").close()                   # RetroArch left it when the game last quit
    runner = FakeRunner()
    app = make(library_dir, tmp_path, runner)
    assert g.id in app.nav.resumable
    app.frame(16, [Action.A])
    assert runner.resumes == [(True, True)]                # Continue, and save the place again on quit
    app.close()


def test_a_game_without_one_starts_afresh_but_saves_its_place(library_dir, tmp_path):
    runner = FakeRunner()
    app = make(library_dir, tmp_path, runner)
    assert not app.nav.resumable
    app.frame(16, [Action.A])
    assert runner.resumes == [(False, True)]
    app.close()


def test_the_place_a_game_saved_shows_up_after_it_quits(library_dir, tmp_path):
    from arca_launcher.runner import state_path
    g = _first_game(library_dir)

    class Saves(FakeRunner):
        def run(self, rom, resume=False, states=False):
            open(state_path(rom), "w").close()
            return super().run(rom, resume, states)
    app = make(library_dir, tmp_path, Saves())
    app.frame(16, [Action.A])
    assert g.id in app.nav.resumable
    app.close()


def _levels(tmp_path, volume, brightness, changed):
    import json
    run = tmp_path / "run"
    run.mkdir(exist_ok=True)
    (run / "levels").write_text(json.dumps({"volume": volume, "brightness": brightness, "changed": changed}))


def test_a_volume_step_from_the_controller_is_shown_and_kept(library_dir, tmp_path):
    app = make(library_dir, tmp_path)
    _levels(tmp_path, 50, app.nav.brightness, changed=1000.0)          # PS + D-pad up, via the home key
    app._status_at = -1.0
    app.frame(16)
    assert app.nav.volume == 50
    assert settings.load(str(tmp_path / "state.json")).volume == 50
    assert app.nav.osd == ("volume", 50)
    for _ in range(20):
        app.frame(100)
    assert app.nav.osd is None                                          # the bar fades after a moment
    app.close()


def test_a_brightness_step_shows_the_brightness_bar(library_dir, tmp_path):
    app = make(library_dir, tmp_path)
    _levels(tmp_path, app.nav.volume, 40, changed=1000.0)
    app._status_at = -1.0
    app.frame(16)
    assert app.nav.brightness == 40 and app.nav.osd == ("brightness", 40)
    app.close()


def test_steps_taken_while_a_game_ran_are_kept_at_start(library_dir, tmp_path):
    _levels(tmp_path, 30, 60, changed=1000.0)
    app = make(library_dir, tmp_path)
    assert (app.nav.volume, app.nav.brightness) == (30, 60)
    assert app.hw.volumes[-1] == 30                                     # not reset to the old setting
    assert app.nav.osd is None                                          # no bar for a change made elsewhere
    app.close()


def test_a_crash_goes_into_the_crash_log(library_dir, tmp_path):
    from arca_launcher import exits
    app = make(library_dir, tmp_path, FakeRunner(ok=False))
    app.frame(16, [Action.A])
    rows = exits.crashes(str(tmp_path))                                 # beside the settings file
    assert rows and rows[0][1] == "Alpha Quest"
    app.close()


def test_the_health_screen_gets_live_readings(library_dir, tmp_path):
    from arca_launcher.model import SETTINGS_ROWS, Screen

    class HealthyHw(FakeHw):
        def health(self, **_):
            return {"cpu_mhz": 1400, "uptime_s": 60, "disks": [("Card", 1000)], "since_boot": []}
    cfg = Config(library_dir=library_dir, state_path=str(tmp_path / "state.json"), splash=False,
                 run_dir=str(tmp_path / "run"))
    app = App(cfg, runner=FakeRunner(), hw=HealthyHw())
    app.nav.stack = [Screen.SETTINGS, Screen.HEALTH]
    app._status_at = -1.0
    app.frame(16)
    assert app.nav.health["cpu_mhz"] == 1400 and app.nav.crashes == []
    app.close()
