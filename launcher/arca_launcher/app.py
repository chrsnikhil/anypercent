"""The launcher loop: input -> navigation model -> views.

While a game runs the launcher closes its window: on the Pi (KMS/DRM, no desktop) only one
program can own the display, and the sandbox does the same so both behave alike."""
import logging
import math
import os
import signal
import time
from dataclasses import dataclass

import pygame
from pygame._sdl2.video import Renderer, Window

from . import NAME, coach, exits, levels, settings
from .hw import APP_SERVICES
from .hw import Hardware
from .input import Inputs
from .library import LibraryError, load_library
from . import themes
from .handler.arkiv_rpc import RABDI_RPC
from .handler.flow import RaceTarget
from .handler.mock import MockSponsors
from .handler_glue import HandlerGlue
from .model import (CRASHED, Launch, Nav, OpenHub, PowerOff, Screen, SetBrightness, SetTheme, SetTouchControls,
                    SetVolume, Sleep, Visitor, Wake)
from .render import theme
from .render.art import Art
from .render.chrome import Status
from .render.gfx import Gfx
from .render.splash import SplashTimeline
from .render.views import Views
from .runner import Runner, state_path
from .touch import SWIPE_MIN, Press, Swipe, Tap, Touch, flick

LIBRARY_HELP = "Build it by running  bash run.sh launcher  in the sandbox folder."
MAX_DT = 100                                       # ms
PITCH_X = theme.TILE + theme.TILE_GAP              # px of finger travel per tile: the Home row's and the grid's spacing
PITCH_Y = theme.TILE + 34                          # the grid's row pitch (library_view.PITCH)
OVERSCROLL = 0.4                                   # tiles the row may be dragged past either end
SLEEP_BRIGHTNESS = 5                               # backlight percent behind the sleep clock
SLEEP_FPS = 5                                      # the clock only needs a few frames a second
WARNING_EVERY = 10                                 # seconds between asking the firmware about power and heat
IDLE_FPS = 30                                      # nothing pressed for a while: half the frames, less heat
IDLE_FPS_AFTER_MS = 4000
ATTRACT_MS = 60000                                 # idle on Home this long and it becomes a booth display
HANDLER_IDLE_MS = 180000                           # idle on PB's screens this long, no call live: back Home
log = logging.getLogger(__name__)


def make_sponsors(cfg, replay=None, games=None):
    """PB's sponsors: World for real through its bridge when one is given, and Arkiv for real too when the checker it
    pins every board read to is given as well (the bridge is also the service Arkiv's listings and listed ghosts go
    through), and Hedera for real on top of both when asked for (cfg.hedera: PB's payments and the listing's record go
    through the same bridge). Hedera asked for without both stays mocked, and the log says why. Neither: every sponsor
    mocked. replay(arcade_id, log_path) times a log with the game's replay tool; games are the arcade ids whose boards
    are read at start."""
    def clock_ms():
        return int(time.monotonic() * 1000)
    if cfg.hedera and not (cfg.world_bridge and cfg.arkiv_checker):
        missing = " and ".join(name for name, value in (("--world-bridge", cfg.world_bridge),
                                                        ("--arkiv-checker", cfg.arkiv_checker)) if not value)
        log.warning("Hedera stays mocked: it runs only on real World and Arkiv (%s not given)", missing)
    if cfg.world_bridge:
        from .handler.world import WorldSponsors
        world = WorldSponsors(cfg.world_bridge, clock_ms)
        if not cfg.arkiv_checker:
            return world
        from .handler.arkiv import ARCADE_GAMES, ArkivSponsors
        state_dir = os.path.dirname(cfg.state_path) or "."
        arkiv = ArkivSponsors(world, cfg.world_bridge, cfg.arkiv_rpc, cfg.arkiv_checker, cfg.arkiv_season,
                              cfg.runs_dir, state_dir, clock_ms, replay=replay,
                              games=ARCADE_GAMES if games is None else games)
        if not cfg.hedera:
            return arkiv
        from .handler.hedera import HederaSponsors
        return HederaSponsors(arkiv, cfg.world_bridge, clock_ms, state_dir)
    return MockSponsors(clock_ms)


def nearest(x):
    """Round half away from zero (Python's round() goes to even), so both directions feel the same."""
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


@dataclass
class Finger:
    """A finger that is down, from its Press to its Tap or Swipe."""
    slider: int | None = None                      # it landed on this settings slider: the slider follows it
    dragging: bool = False
    base: float = 0.0                              # the Home row's position when the drag began
    origin: int = 0                                # the grid selection when the drag began
    swallowed: bool = False                        # it skipped the splash: it does nothing else
    woke: bool = False                             # it woke the sleep clock or attract mode: its lift leaves PB be


@dataclass
class Config:
    library_dir: str
    state_path: str
    emulator: str = "mgba"
    retroarch_core: str | None = None
    retroarch_cfg: str | None = None
    scale: int = 1
    fullscreen: bool = False
    show_fps: bool = False
    joy_map: dict | None = None                    # joystick button number -> Action; None = the default contract
    splash: bool = True
    runs_dir: str = "/opt/arca-sandbox/runs"       # arcade games: verified runs queue and best logs
    overlay: str | None = None                     # RetroArch overlay .cfg for the on-screen controls setting
    haptics: str | None = None                     # ALSA pcm for game audio + rumble (device/asoundrc)
    run_dir: str = exits.RUN_DIR                   # how the last game or app ended (PS-button quit, app crash)
    coach: bool = False                            # PB, the coach (on in the launcher: __main__; off in tests)
    coach_voice_key: str | None = None             # a file with an Anthropic API key: PB's optional voice
    handler: bool = False                          # PB the handler, Triangle (on in the launcher; off in tests)
    handler_warm: bool = False                     # read every arcade game's board in the background after start
    testlogs_dir: str = "/opt/anypercent/testlogs"  # each arcade game's shipped test log: the handler's target ghost
    world_bridge: str | None = None                # the World bridge's URL: World for real (None: every sponsor mocked)
    arkiv_checker: str | None = None               # with world_bridge: Arkiv for real, reads pinned to this $creator
    arkiv_rpc: str = RABDI_RPC                     # Arkiv's public RPC: no access key on the console
    arkiv_season: int = 1
    hedera: bool = False                           # with world_bridge and arkiv_checker: Hedera for real (pay, record)


class Display:
    """Window, renderer, textures and views. Made on start and again after every game."""

    def __init__(self, cfg):
        os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "linear")
        pygame.display.init()
        pygame.font.init()
        self.window = Window(NAME, size=(theme.W * cfg.scale, theme.H * cfg.scale), fullscreen=cfg.fullscreen)
        self.renderer = Renderer(self.window, vsync=True)
        self.renderer.logical_size = (theme.W, theme.H)
        self.gfx = Gfx(self.renderer)
        self.views = Views(self.gfx, Art(self.gfx, cfg.library_dir))
        pygame.key.set_repeat(300, 80)
        if cfg.fullscreen:
            pygame.mouse.set_visible(False)   # the device is touch + buttons: no pointer on the panel

    def close(self):
        """Safe twice: a launch closes it before the game, and a crash before the next one opens closes it again."""
        if self.window is None:
            return
        self.views = self.gfx = self.renderer = None
        self.window.destroy()
        self.window = None
        pygame.display.quit()


class App:
    def __init__(self, cfg, runner=None, hw=None, bridge=None, voice=None, sponsors=None):
        self.cfg = cfg
        self._bridge = bridge
        self.voice = voice if voice is not None else self._load_voice(cfg)
        self._mascot_seq, self._mascot_ms, self._voice_future = -1, 0, None
        self.hw = hw or Hardware()
        self.runner = runner or Runner(cfg.emulator, cfg.retroarch_core, cfg.retroarch_cfg,
                                       fullscreen=cfg.fullscreen, audio_sync=cfg.fullscreen, overlay=cfg.overlay,
                                       haptics=cfg.haptics)
        self.prefs = settings.load(cfg.state_path)
        self.runner.touch_controls = self.prefs.touch_controls
        try:
            games, self.error = load_library(cfg.library_dir), None
        except LibraryError as e:
            games, self.error = [], str(e)
        self.nav = Nav(games, self.prefs.last_played, self.prefs.volume, self.prefs.brightness,
                       self.hw.brightness_available(), self.prefs.touch_controls, self.prefs.theme)
        self.nav.handler_enabled = cfg.handler     # arcade games get a PB button beside Play: the hub by touch
        self.nav.booth_url = self._booth_url()
        self.light = themes.apply(self.prefs.theme).light
        if sponsors is None:
            arcades = [g.arcade["id"] for g in games if g.arcade]
            sponsors = make_sponsors(cfg, replay=self._replay_time, games=arcades)
        self.sponsors = sponsors
        self.handler = HandlerGlue(self) if cfg.handler else None       # feeds nav.handler, the open flow
        self._find_saved_places()
        self._report_app_exit(games)
        self.idle_ms = 0
        self.handler_idle_ms = 0                   # idle on PB's screens, in capped frame time
        self._back_from_game = False               # the next frame's time is the game's, not idle time
        self._pads = -1
        self._levels_seen, self._osd, self._osd_ms = 0.0, None, 0
        self._sync_levels(show=False)              # steps taken on the controller while a game or app ran
        self.hw.set_volume(self.nav.volume)
        if self.nav.brightness_available:
            self.hw.set_brightness(self.nav.brightness)
        pygame.joystick.init()
        self.inputs = Inputs(cfg.joy_map)
        self.touch = Touch()
        self.finger = None                         # a Finger while one is down
        self.display = Display(cfg)
        self.inputs.scan()                         # pads already connected (their device-added event is lost)
        self._light_up()
        self._notice, self._notice_ms = None, 0
        self._status, self._status_at = None, -1.0
        self._warning, self._warning_at = None, -WARNING_EVERY
        self.quitting = False
        # systemd stops the launcher with SIGTERM. SDL would turn it into a QUIT event, and one that arrives while a
        # game runs used to be dropped with the game's leftover input (a 90 s wait for SIGKILL). A flag cannot be.
        for sig in (signal.SIGTERM, signal.SIGHUP):
            try:
                signal.signal(sig, self._stop)
            except ValueError:                     # not the main thread (never on the device)
                pass
        self.splash = SplashTimeline() if cfg.splash else None     # plays once, at start-up
        if self.splash is None:
            self._greet()
        if self.handler is not None and cfg.handler_warm:
            self.handler.warm_up()                 # last: a start that fails above leaves no replay to wait for

    @staticmethod
    def _load_voice(cfg):
        """PB's optional voice, when the coach is on and a key file exists; else None (PB's own words)."""
        if not (cfg.coach and cfg.coach_voice_key and os.path.isfile(cfg.coach_voice_key)):
            return None
        try:
            from .coach_voice import Voice
            return Voice.from_key_file(cfg.coach_voice_key)
        except Exception:
            log.exception("PB's voice is off")
            return None

    def _greet(self):
        """PB says hello on the day's first start; with no record book the handler offers one after it."""
        today = time.strftime("%Y-%m-%d")
        if self.cfg.coach and self.prefs.coach_greeted != today:
            self.nav.say([coach.greeting()])
            self.prefs.coach_greeted = today
            settings.save(self.cfg.state_path, self.prefs)
        if self.handler is not None:
            self.handler.offer_book(today)

    @property
    def bridge(self):
        """The arcade bridge, made on first use."""
        if self._bridge is None:
            from .arcade_bridge import Bridge
            self._bridge = Bridge(self.cfg.runs_dir, emulator=self.cfg.emulator)   # .sav or RetroArch's .srm
        return self._bridge

    def _replay_time(self, arcade_id, log_path):
        """A log's finished time from its arcade game's replay tool (None: unfinished, no such game, the tool failed).
        The Arkiv adapter's worker checks a bought ghost with it, off the main thread."""
        arcade = next((g.arcade for g in self.nav.games if g.arcade and g.arcade.get("id") == arcade_id), None)
        return self.bridge.log_time(arcade, log_path) if arcade is not None else None

    @property
    def state_dir(self):
        """Where the settings live (on /data when read-only): the crash log goes beside them."""
        return os.path.dirname(self.cfg.state_path) or "."

    def _booth_url(self):
        """The first line of booth-url.txt beside the settings (set over SSH at the event, e.g. the project's
        showcase page) when it is a web link: attract mode shows it as a QR code. None otherwise."""
        try:
            with open(os.path.join(self.state_dir, "booth-url.txt"), encoding="utf-8") as f:
                url = f.readline().strip()
        except (OSError, ValueError):
            return None
        return url if url.startswith(("https://", "http://")) and len(url) <= 300 else None

    def _sync_levels(self, show):
        """Take up a volume or brightness step made with PS + D-pad (the home key already set the hardware): keep it
        as the setting, and show the bar when it happens while the launcher is on screen."""
        lv = levels.read(self.cfg.run_dir)
        if lv is None or lv["changed"] <= self._levels_seen:
            return
        self._levels_seen = lv["changed"]
        kind = "volume" if lv["volume"] != self.nav.volume else "brightness" if lv["brightness"] != self.nav.brightness else None
        self.nav.volume = self.prefs.volume = lv["volume"]
        self.nav.brightness = self.prefs.brightness = lv["brightness"]
        settings.save(self.cfg.state_path, self.prefs)
        if show and kind:
            self.nav.osd = (kind, lv[kind])

    def _find_saved_places(self):
        """Games RetroArch left a place for when they quit (<rom>.state.auto): they offer Continue. Arcade games
        never: a state would let a verified run be rewound."""
        self.nav.resumable = {g.id for g in self.nav.games
                              if g.rom and not g.arcade and not g.app and os.path.exists(state_path(g.rom))}

    def _report_app_exit(self, games):
        """An app (GTA III, the browser) runs as its own service and the launcher starts again after it: if it
        crashed, say so now. One the PS button closed was asked for."""
        e = exits.app_exit(self.cfg.run_dir)
        asked = exits.home_quit(self.cfg.run_dir, time.time())
        if e is None or e.ok or asked:
            return
        title = next((g.title for g in games if g.app and APP_SERVICES.get(g.app) == e.unit), "The app")
        log.warning("%s ended: %s %s %s", e.unit, e.result, e.code, e.status)
        exits.log_crash(self.state_dir, time.time(), title, f"{e.result} {e.code} {e.status}")
        self.nav.game_finished(False, title)

    def target_fps(self):
        if self.sleeping:
            return SLEEP_FPS
        if self.nav.screen is Screen.HANDLER:      # its cards animate on their own: never idle
            return 60
        return IDLE_FPS if self.idle_ms >= IDLE_FPS_AFTER_MS or self.nav.screen is Screen.ATTRACT else 60

    def _stop(self, *_):
        self.quitting = True

    def status(self):
        now = time.time()
        if now - self._status_at >= 1:
            self._sync_levels(show=True)
            if self.nav.screen is Screen.HEALTH:          # the Device health screen: live readings
                self.nav.health = getattr(self.hw, "health", lambda **_: {})()
                self.nav.crashes = exits.crashes(self.state_dir)
            if now - self._warning_at >= WARNING_EVERY:
                self._warning = getattr(self.hw, "power_warning", lambda: None)()
                self._warning_at = now
            temp = getattr(self.hw, "temperature", lambda: None)() if self._warning else None
            self._status = Status(time.strftime("%I:%M %p").lstrip("0"), self.hw.battery_percent(),
                                  getattr(self.hw, "wifi", lambda: None)(), self._warning,
                                  getattr(self.hw, "controller_battery", lambda: None)(), temp)
            self._status_at = now
        return self._status

    def _light_up(self):
        """Light bar in the theme colour whenever the set of pads changes (a pad connected later gets it too)."""
        n = len(self.inputs.controllers)
        if n != self._pads:
            self._pads = n
            setter = getattr(self.hw, "set_lightbar", None)
            if setter is not None:
                setter(self.light)
        self.nav.pad_battery = getattr(self.hw, "controller_battery", lambda: None)() if n else None

    @property
    def sleeping(self):
        return self.nav.screen is Screen.SLEEP

    def handle(self, action):
        self._carry_out(self.nav.apply(action))

    def handle_touch(self, g):
        """Answer a finger the moment it lands (tiles select, buttons look pressed), follow it while it drags (the
        Home row moves with it, the grid and sliders step), and act when it lifts (a tap on the selected tile or a
        button; a flick carries on one or two tiles)."""
        if self.sleeping or self.nav.screen is Screen.ATTRACT:   # a touch only wakes it; its lift taps nothing
            if isinstance(g, Press):
                self.finger = Finger(swallowed=True, woke=True)
            self._carry_out(self.nav.wake())
            return
        if self.nav.mascot is not None and self.nav.screen is not Screen.HANDLER:   # PB is talking: a tap moves PB on
            if isinstance(g, Press):
                self.finger = Finger(swallowed=True)
            elif isinstance(g, (Tap, Swipe)):
                woke = self.finger is not None and self.finger.woke
                self.finger = None
                if not woke:                       # the lift of the finger that woke attract mode keeps PB's hello
                    self.nav.advance_mascot()
            return
        if isinstance(g, Press):
            target = self.display.views.hit(g.x, g.y)
            self.finger = Finger(slider=target[1] if target and target[0] == "slider" else None)
            self._carry_out(self.nav.press(target))
            return
        if self.finger is None:                    # its press was not seen (lost, or a test): press where it began
            self.handle_touch(Press(g.x, g.y) if isinstance(g, Tap) else Press(g.x0, g.y0))
        f = self.finger
        if isinstance(g, (Tap, Swipe)):
            self.finger = None
        if f.swallowed:
            return
        if isinstance(g, Tap):
            self._carry_out(self.nav.release())
            return
        if not f.dragging:                         # past the slop: whatever it landed on is not pressed any more
            f.dragging = True
            f.base, f.origin = self.display.views.home.position, self.nav.grid_index
            if f.slider is None:
                self.nav.cancel_press()
        self._follow(f, g, final=isinstance(g, Swipe))
        if isinstance(g, Swipe):
            self.nav.cancel_press()

    def _follow(self, f, g, final):
        views, s = self.display.views, self.nav.screen
        if f.slider is not None:
            bar = views.slider_bar(f.slider)
            if bar is not None and s is Screen.SETTINGS:
                self._carry_out(self.nav.slide(f.slider, views.along(bar, g.x0 + g.dx)))
        elif s is Screen.HOME and g.dy == 0:
            last = len(self.nav.row) - 1
            pos = min((last + OVERSCROLL) * PITCH_X, max(-OVERSCROLL * PITCH_X, f.base - g.dx))
            views.home.hold(pos)
            i = nearest(pos / PITCH_X)
            if final:
                views.home.release()               # eases from where the finger left it to the selected tile
                i += flick(g.vx)
            self.nav.select_row(i)
        elif s is Screen.LIBRARY:
            cols, rows = nearest(-g.dx / PITCH_X), nearest(-g.dy / PITCH_Y)
            if final:
                cols, rows = cols + flick(g.vx), rows + flick(g.vy)
            self.nav.drag_grid(f.origin, cols, rows)
        elif s is Screen.INFO and final and g.dx:
            n = flick(g.vx) or (-1 if g.dx > 0 else 1) * (abs(g.dx) >= SWIPE_MIN)
            if n:
                self.nav.swipe(1 if n > 0 else -1, 0)

    def _carry_out(self, cmd):
        if isinstance(cmd, Launch):
            self.launch(cmd.game, cmd.resume)
        elif isinstance(cmd, SetVolume):
            self.hw.set_volume(cmd.value)
            self.prefs.volume = cmd.value
            settings.save(self.cfg.state_path, self.prefs)
        elif isinstance(cmd, SetBrightness):
            self.hw.set_brightness(cmd.value)
            self.prefs.brightness = cmd.value
            settings.save(self.cfg.state_path, self.prefs)
        elif isinstance(cmd, SetTouchControls):
            self.runner.touch_controls = cmd.on
            self.prefs.touch_controls = cmd.on
            settings.save(self.cfg.state_path, self.prefs)
        elif isinstance(cmd, Sleep):
            if self.nav.brightness_available:
                self.hw.set_brightness(SLEEP_BRIGHTNESS)
        elif isinstance(cmd, Wake):
            if self.nav.brightness_available:
                self.hw.set_brightness(self.nav.brightness)
        elif isinstance(cmd, Visitor):
            if self.cfg.coach:                     # someone new at the booth: PB says who he is and where to start
                self.nav.say([coach.visitor(self.handler is not None)])
        elif isinstance(cmd, PowerOff):
            self.power_off()
        elif isinstance(cmd, SetTheme):
            t = themes.apply(cmd.theme)
            self.prefs.theme = t.id
            settings.save(self.cfg.state_path, self.prefs)
            self.light, self._pads = t.light, -1
            self._light_up()
            self.inputs.rumble(0.35, 0.35, 90)
        elif isinstance(cmd, OpenHub):
            if self.handler is not None:
                self._carry_out(self.handler.open(cmd.game))
        elif isinstance(cmd, RaceTarget):
            if self.handler is not None:
                self.handler.race_target(cmd)

    def power_off(self):
        """Save everything, say so on screen, then shut down. In the sandbox it only shows a notice."""
        settings.save(self.cfg.state_path, self.prefs)
        self.display.views.message("Shutting down", "It is safe to unplug the power once the screen goes dark.",
                                   self.status())
        self.display.renderer.present()
        if not self.hw.power_off():
            self.nav.notice = "Power off works on the handheld only"

    def launch(self, game, resume=False, ghost=None):
        """ghost: raced instead of the best run's (an arcade game; the handler's target)."""
        self.inputs.rumble(0.25, 0.25, 70)
        self.idle_ms = self.handler_idle_ms = 0
        self.display.views.starting(game)
        self.display.renderer.present()
        if self.handler is not None:
            self.handler.settle()                  # a comparison still running ends first: the game or app gets the CPU
        if game.app:                               # an app (the browser): its service replaces the launcher
            self.nav.played(game.id, time.time())
            self.prefs.last_played[game.id] = time.time()
            settings.save(self.cfg.state_path, self.prefs)
            if not getattr(self.hw, "start_app", lambda name: False)(game.app):
                self.nav.notice = f"{game.title} could not start"
            return
        now = time.time()
        self.nav.played(game.id, now)
        self.prefs.last_played[game.id] = now
        settings.save(self.cfg.state_path, self.prefs)
        self.display.close()
        if game.arcade:
            self._arcade("before", game, ghost)
        # on-screen controls only when the setting is on and no controller is connected (a DualSense hides them)
        self.runner.touch_controls = self.prefs.touch_controls and not self.inputs.pad_connected
        states = not game.arcade                                    # keep the place on quit; never for verified runs
        result = self.runner.run(game.rom, resume=resume and states, states=states)
        self._find_saved_places()
        res = self._arcade("after", game) if game.arcade else None
        asked = exits.home_quit(self.cfg.run_dir, time.time())     # the PS button ended it: no crash
        if not result.ok and not asked:
            log.warning("%s ended badly: %s", game.id, result.error)
            exits.log_crash(self.state_dir, time.time(), game.title, result.error)
        self.nav.game_finished(result.ok or asked, game.title)
        if self.handler is not None:
            self.handler.game_over(game, res, result.ok, asked)
        self.display = Display(self.cfg)
        if pygame.event.peek(pygame.QUIT):         # a stop request while the game ran is kept
            self.quitting = True
        pygame.event.clear()                       # drop anything pressed while the game ran
        self.inputs.reset()                        # and any direction held when Play was pressed
        self.inputs.scan()                         # and pick up a pad that connected while the game ran
        self.touch.reset()                         # and a touch whose release the game got
        self.finger = None
        self.nav.cancel_press()
        self._back_from_game = True

    def _arcade(self, step, game, ghost=None):
        """Profile and ghost into the save before an arcade game, its verified run out after. Never blocks a launch.
        ghost (before only) replaces the best run's."""
        return self._arcade_result(step, game, game.arcade, ghost)

    def _arcade_result(self, step, game, arcade, ghost=None):
        try:
            extra = {"ghost": ghost} if ghost is not None else {}
            res = getattr(self.bridge, step)(game.rom, arcade, **extra)
        except Exception:
            log.exception("arcade bridge %s failed for %s", step, game.id)
            return None
        if step == "after" and isinstance(res, dict):
            if res.get("new_best"):
                self.inputs.rumble(1.0, 1.0, 400)
            if self.handler is not None and self.handler.racing:
                pass                               # the handler's result screen says how it went
            elif self.cfg.coach:
                self.nav.say(coach.after_run(game.title, res, self._history(arcade)))
            elif res.get("new_best"):
                self.nav.notice = f"New best on {game.title}!"
        return res

    def _history(self, arcade):
        try:
            history = getattr(self._bridge, "history", None)
            return list(history(arcade["id"])) if history else []
        except Exception:
            log.exception("run history unavailable")
            return []

    def _time_mascot(self, dt):
        """Time PB's line: ask the voice (if any) to reword it, wait for it a moment, type the words, then move on."""
        if self.nav.screen is Screen.HANDLER:      # the flow moves PB's line on there, not time
            return
        line = self.nav.mascot
        if self.nav.mascot_seq != self._mascot_seq:            # a new line (or quiet)
            self._mascot_seq, self._mascot_ms, self._voice_future = self.nav.mascot_seq, 0, None
            if line is not None and self.voice is not None:
                try:
                    self._voice_future = self.voice.submit(line)
                except Exception:
                    log.exception("PB's voice failed")
            if line is not None and self._voice_future is None:
                self.nav.mascot_text = line.text
        elif line is not None:
            self._mascot_ms += dt
        if line is None:
            return
        if self.nav.mascot_text is None:
            f, said = self._voice_future, None
            if f is not None and f.done():
                try:
                    said = f.result()
                except Exception:
                    said = None
            if f is None or f.done() or self._mascot_ms >= theme.VOICE_WAIT_MS:
                self.nav.mascot_text, self._mascot_ms = said or line.text, 0
        elif self._mascot_ms >= len(self.nav.mascot_text) * 1000 / theme.MASCOT_CPS + theme.MASCOT_HOLD_MS:
            self.nav.advance_mascot()
            return
        self.nav.mascot_ms = self._mascot_ms

    def frame(self, dt, actions=(), touches=()):
        raw_dt = dt                                # real time passing, for attract mode's idle timer
        dt = min(dt, MAX_DT)                       # a stalled frame (a game just ran) counts as one short frame
        if self.splash is not None:
            for t in touches:                      # a finger that skips the splash does nothing else, even later
                if isinstance(t, Press):
                    self.finger = Finger(swallowed=True)
                elif isinstance(t, (Tap, Swipe)):
                    self.finger = None
            return self._splash_frame(dt, list(actions) + list(touches))
        self._light_up()
        if actions or touches:
            self.idle_ms = self.handler_idle_ms = 0
        else:
            # the first frame after a game measures the whole game: it is not idle time, or every game over a minute
            # would come back to the booth display instead of Home and PB's word on the run
            self.idle_ms += dt if self._back_from_game else raw_dt
            # PB's screens count capped time: the first frame after a race carries the whole race, and must not
            # close the result the player came back to see.
            self.handler_idle_ms = self.handler_idle_ms + dt if self.nav.screen is Screen.HANDLER else 0
            waiting = self.nav.mascot is not None or (self.handler is not None and self.handler.pending is not None)
            if self.idle_ms >= ATTRACT_MS and not self.error and not waiting and self.nav.attract():
                self.idle_ms = 0
            elif (self.handler_idle_ms >= HANDLER_IDLE_MS and self.nav.screen is Screen.HANDLER
                  and not self.nav.handler.busy):
                self.nav.close_handler()           # a booth left on PB: Home, where attract mode takes over
        self._back_from_game = False
        for a in actions:
            self.handle(a)
        for t in touches:
            if not self.error:
                self.handle_touch(t)
        if self.nav.notice != self._notice:
            self._notice, self._notice_ms = self.nav.notice, 0
        elif self._notice:
            self._notice_ms += dt
            limit = theme.CRASH_NOTICE_MS if self._notice.endswith(CRASHED) else theme.NOTICE_MS
            if self._notice_ms >= limit:
                self.nav.clear_notice()
                self._notice = None
        self._time_mascot(dt)                      # not raw_dt: the frame after a game measures the whole game
        if self.handler is not None:
            self._carry_out(self.handler.frame(dt))
        if self.nav.osd != self._osd:
            self._osd, self._osd_ms = self.nav.osd, 0
        elif self._osd:
            self._osd_ms += dt
            if self._osd_ms >= theme.OSD_MS:
                self.nav.osd = self._osd = None
        self._draw_screen(dt)
        self.display.renderer.present()

    def _draw_screen(self, dt):
        if self.error:
            self.display.views.message("No game library", f"{self.error}. {LIBRARY_HELP}", self.status())
        else:
            self.display.views.draw(self.nav, dt, self.status())

    def _splash_frame(self, dt, actions):
        """The start-up splash. Any button or touch skips to its fade and is not passed on (it must not press Play)."""
        if actions:
            self.splash.skip()
        self.splash.update(dt)
        views = self.display.views
        if self.splash.fading:
            self._draw_screen(dt)                  # Home underneath, the splash fading out on top
        else:
            views.art.warm(self.nav.row[:-1], budget=4)
        views.splash.draw(self.splash)
        self.display.renderer.present()
        if self.splash.done:
            self.splash = None
            self._greet()

    def poll(self, events):
        """Events -> (quit?, button actions, touch gestures)."""
        actions, touches = [], []
        for ev in events:
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE
                                          and not self.cfg.fullscreen):
                return True, actions, touches
            a = self.inputs.translate(ev)
            if a is not None:
                actions.append(a)
            t = self.touch.translate(ev)
            if t is not None:
                touches.append(t)
        return False, actions, touches

    def run(self):
        clock = pygame.time.Clock()
        frames, since = 0, time.time()
        while True:
            dt = clock.tick(self.target_fps())
            quit_, actions, touches = self.poll(pygame.event.get())
            if quit_ or self.quitting:
                self.close()
                return 0
            actions += self.inputs.tick(dt)
            self.frame(dt, actions, touches)
            frames += 1
            if self.cfg.show_fps and time.time() - since >= 5:
                print(f"fps {frames / (time.time() - since):.1f}", flush=True)
                frames, since = 0, time.time()

    def close(self):
        """Safe twice and after a crash: the background replays stop, the window closes, the settings are saved,
        each step run even when one before it fails (the first failure is raised after)."""
        failed = None
        for step in (self._close_handler, self._close_display, lambda: settings.save(self.cfg.state_path, self.prefs)):
            try:
                step()
            except Exception as e:
                log.exception("closing")
                failed = failed or e
        if failed is not None:
            raise failed

    def _close_handler(self):
        if self.handler is not None:
            self.handler.close()
        close = getattr(getattr(self, "sponsors", None), "close", None)   # the World bridge's worker thread
        if close is not None:
            close()

    def _close_display(self):
        display, self.display = self.display, None
        if display is not None:
            display.close()
