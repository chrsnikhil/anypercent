"""Navigation state for the launcher. Pure logic: no pygame, no files, no clock.

apply(action) changes the state and may return a command for the app to carry out:
Launch(game), SetVolume(value), SetBrightness(value), SetTouchControls(on), OpenHub(game), Sleep(),
Wake() or PowerOff()."""
from dataclasses import dataclass
from enum import Enum

from .actions import Action
from .handler.flow import CloseHandler
from .themes import THEMES
from .library import Game


CRASHED = " closed unexpectedly"         # a crash notice ends with this (it stays up longer: render/theme.py)


class Screen(Enum):
    HOME = "home"
    LIBRARY = "library"
    INFO = "info"
    SETTINGS = "settings"
    ABOUT = "about"
    GAMEPAD = "gamepad"                  # what each controller button does
    HEALTH = "health"                    # temperature, power, storage, recent crashes
    THEMES = "themes"                    # the theme picker (the DualSense trick)
    HANDLER = "handler"                  # PB the handler: the sponsor console (handler/flow.py)
    ATTRACT = "attract"                  # booth display after a minute idle on Home
    SLEEP = "sleep"                      # screen dimmed to a clock; any button or touch wakes it


@dataclass(frozen=True)
class Launch:
    game: Game
    resume: bool = False                 # start from the game's saved place (Continue), not afresh


@dataclass(frozen=True)
class SetVolume:
    value: int


@dataclass(frozen=True)
class SetBrightness:
    value: int


@dataclass(frozen=True)
class SetTouchControls:
    on: bool


@dataclass(frozen=True)
class SetTheme:
    theme: str


@dataclass(frozen=True)
class OpenHub:
    """Triangle on the focused game: open its hub (the handler, Task 11 builds the Flow). None
    on a non-arcade tile or the Game Library tile; the app decides what that opens."""
    game: Game | None


@dataclass(frozen=True)
class Sleep:
    """Dim the screen to the sleep clock."""


@dataclass(frozen=True)
class Wake:
    """Back from the sleep clock."""


@dataclass(frozen=True)
class Visitor:
    """Attract mode ended: someone (likely new to the console) picked it up."""


@dataclass(frozen=True)
class PowerOff:
    """Shut the device down (confirmed: the second press on Power off)."""


LIBRARY_TILE = None                  # the Game Library tile at the end of the home row
GRID_COLS = 5
# controls: on-screen controls in games. Sleep and Power off sit at the bottom, Power off last.
SETTINGS_ROWS = ("volume", "brightness", "gamepad", "controls", "about", "health", "sleep", "power")   # gamepad: the button map
STEP = 10
MIN_BRIGHTNESS = 10
# HANDLER: which buttons reach the flow, and as what event (Action.press -> Flow.press())
_HANDLER_PRESSES = {Action.A: "cross", Action.B: "circle", Action.X: "square",
                     Action.UP: "up", Action.DOWN: "down"}


class Nav:
    def __init__(self, games, last_played=None, volume=80, brightness=100, brightness_available=True,
                 touch_controls=False, theme="anypercent"):
        self.games = list(games)
        self.last_played = dict(last_played or {})
        self.az = sorted(self.games, key=lambda x: x.title.casefold())
        self.row = self._build_row()
        self.stack = [Screen.HOME]
        self.row_index = 0
        self.home_focus = "tiles"
        self.button_index = 0
        self.grid_index = 0
        self.info_game = None
        self.shot_index = 0
        self.settings_index = 0
        self.volume = volume
        self.brightness = brightness
        self.brightness_available = brightness_available
        self.touch_controls = touch_controls
        self.notice = None
        self.pressed = None               # the touch target under a finger that is still down (drawn pressed)
        self.armed = False                # lifting that finger acts on it
        self.power_armed = False          # Power off was pressed once: a second press shuts down
        self.theme = theme                # themes.THEMES id
        self.theme_index = 0              # the highlighted row in the theme picker
        self.resumable = set()            # ids of games with a saved place: Continue / Restart (set by the app)
        self.osd = None                   # ("volume" | "brightness", percent): the level bar, after a PS + D-pad step
        self.health = {}                  # Device health readings (hw.health), refreshed by the app while shown
        self.crashes = []                 # recent crashes [(when, title, detail)], newest first
        self.mascot = None                # the coach.Line PB is saying: any button or tap moves PB on
        self.mascot_text = None           # the words shown for it (its own or the voice's); None while PB thinks
        self.mascot_ms = 0                # how long the words have been on screen (kept by the app, for typing)
        self._said = []                   # PB's lines waiting their turn
        self.mascot_seq = 0               # counts PB's lines, so the app knows a new one started
        self.handler = None                # the open or last-open Flow (handler/flow.py); kept past close_handler
        self.handler_enabled = False       # PB the handler is on (set by the app): arcade games get a PB button
        self.board_times = {}              # game id -> (runner, "1:41.17"): the handler's run to beat, for attract mode
        self.booth_url = None              # a web link attract mode shows as a QR code (booth-url.txt), or None

    # derived ----------------------------------------------------------------
    def can_resume(self, game):
        return game is not None and game.id in self.resumable

    def home_buttons(self):
        """The buttons beside the selected tile: Continue, Restart, ... when it has a saved place, else Play, ...;
        an arcade game also gets PB (his hub: the board, the next run to beat, listing) when the handler is on, the
        way in by touch as well as Triangle."""
        if self.selected is None:
            return ["Open"]
        if self.can_resume(self.selected):
            return ["Continue", "Restart", "..."]
        if self.handler_enabled and self.selected.arcade:
            return ["Play", "PB", "..."]
        return ["Play", "..."]

    @property
    def screen(self):
        return self.stack[-1]

    @property
    def tab(self):
        return "settings" if self.stack[0] is Screen.SETTINGS else "games"

    @property
    def selected(self):
        """The game under the home selection, or None on the Game Library tile."""
        return self.row[self.row_index]

    @property
    def grid_game(self):
        return self.az[self.grid_index] if self.az else None

    def _build_row(self):
        played = sorted((x for x in self.games if x.id in self.last_played), key=lambda x: -self.last_played[x.id])
        rest = [x for x in self.az if x.id not in self.last_played]
        return played + rest + [LIBRARY_TILE]

    # events from the app ------------------------------------------------------
    def played(self, game_id, when):
        """A game was launched: it moves to the front of the row, stays selected, and Home is shown."""
        self.last_played[game_id] = when
        self.row = self._build_row()
        self.row_index = next((i for i, x in enumerate(self.row) if x is not None and x.id == game_id), 0)
        self.home_focus = "tiles"
        self.stack = [Screen.HOME]

    def game_finished(self, ok, title=None):
        if not ok:
            self.notice = f"{title or 'The game'}{CRASHED}"

    def clear_notice(self):
        self.notice = None

    def say(self, lines):
        """PB says these after anything it is already saying."""
        self._said.extend(lines)
        if self.mascot is None:
            self.advance_mascot()

    def advance_mascot(self):
        """PB's next line, or quiet when there is none."""
        self.mascot = self._said.pop(0) if self._said else None
        self.mascot_text, self.mascot_ms = None, 0
        self.mascot_seq += 1

    def open_handler(self, flow, entry):
        """Open HANDLER on a new flow, started at entry ("book", "board", "list", "hub", or a
        state name). Returns the command flow.start(entry) produces, after the same CloseHandler
        handling as apply (so an entry that resolves straight back to Home closes at once)."""
        self.handler = flow
        self.stack.append(Screen.HANDLER)
        return self._handler_command(flow.start(entry))

    def resume_handler(self):
        """Bring the existing handler flow back on screen, without starting it again (the app
        calls this after a race finishes, so the flow's seller snapshot is not reset)."""
        if self.handler is None:
            return None
        self.stack.append(Screen.HANDLER)

    def close_handler(self):
        """Pop back to the screen under HANDLER. Keeps self.handler: the app may resume it, and
        replaces it the next time it opens one."""
        self.stack.pop()

    def _handler_command(self, command):
        """A CloseHandler from the flow closes the screen and is swallowed; anything else (a
        RaceTarget) passes through to the caller."""
        if isinstance(command, CloseHandler):
            self.close_handler()
            return None
        return command

    # input ----------------------------------------------------------------------
    def apply(self, action):
        if self.screen in (Screen.SLEEP, Screen.ATTRACT):
            return self.wake()
        if self.screen is Screen.HANDLER:
            return self._handler(action)
        if self.mascot is not None:       # PB is talking: a button moves PB on, and does nothing else
            self.advance_mascot()
            return None
        if action is Action.THEMES:
            if self.screen is not Screen.THEMES:
                self.theme_index = next((i for i, t in enumerate(THEMES) if t.id == self.theme), 0)
                self.stack.append(Screen.THEMES)
            return None
        if self.screen is Screen.THEMES:
            return self._themes(action)
        if action in (Action.L, Action.R) and len(self.stack) == 1:
            self.stack = [Screen.SETTINGS if action is Action.R else Screen.HOME]
            return None
        return {Screen.HOME: self._home, Screen.LIBRARY: self._library, Screen.INFO: self._info,
                Screen.SETTINGS: self._settings, Screen.ABOUT: self._about, Screen.GAMEPAD: self._about,
                Screen.HEALTH: self._about}[self.screen](action)

    def wake(self):
        """Leave the sleep clock or attract mode (any button or touch): Wake() after sleep, Visitor() after attract
        mode, else None."""
        if self.screen not in (Screen.SLEEP, Screen.ATTRACT):
            return None
        was = self.stack.pop()
        return Wake() if was is Screen.SLEEP else Visitor()

    def attract(self):
        """Start attract mode, from Home only. True if it started."""
        if self.stack != [Screen.HOME]:
            return False
        self.stack.append(Screen.ATTRACT)
        return True

    def _themes(self, a):
        if a is Action.UP:
            self.theme_index = max(0, self.theme_index - 1)
        elif a is Action.DOWN:
            self.theme_index = min(len(THEMES) - 1, self.theme_index + 1)
        elif a is Action.A:
            return self._pick_theme(self.theme_index)
        elif a is Action.B:
            self.stack.pop()
        return None

    def _pick_theme(self, i):
        self.theme_index = i
        self.theme = THEMES[i].id
        self.stack.pop()
        return SetTheme(self.theme)

    def _launch(self, game, resume=None):
        """resume None: Continue when the game has a saved place."""
        if game is None:
            return None
        if not game.rom_exists:
            self.notice = f"{game.title}: ROM file missing"
            return None
        return Launch(game, self.can_resume(game) if resume is None else resume)

    def _open_info(self, game):
        if game is not None:
            self.info_game, self.shot_index = game, 0
            self.stack.append(Screen.INFO)

    def _home(self, a):
        if a is Action.Y:
            return OpenHub(self.selected)
        if self.home_focus == "tiles":
            if a is Action.LEFT:
                self.row_index = max(0, self.row_index - 1)
            elif a is Action.RIGHT:
                self.row_index = min(len(self.row) - 1, self.row_index + 1)
            elif a is Action.DOWN:
                self.home_focus, self.button_index = "buttons", 0
            elif a is Action.A:
                return self._activate(0)
            elif a is Action.START:
                self._open_info(self.selected)
            return None
        buttons = len(self.home_buttons())
        if a is Action.LEFT:
            self.button_index = max(0, self.button_index - 1)
        elif a is Action.RIGHT:
            self.button_index = min(buttons - 1, self.button_index + 1)
        elif a in (Action.UP, Action.B):
            self.home_focus = "tiles"
        elif a is Action.A:
            return self._activate(self.button_index)
        elif a is Action.START:
            self._open_info(self.selected)
        return None

    def _activate(self, button):
        if self.selected is None:
            self.stack.append(Screen.LIBRARY)
            return None
        buttons = self.home_buttons()
        if not 0 <= button < len(buttons):      # a tap begun on a button the newly selected game does not have
            return None
        label = buttons[button]
        if label == "...":
            self._open_info(self.selected)
            return None
        if label == "PB":
            return OpenHub(self.selected)
        return self._launch(self.selected, resume=label == "Continue")

    def _library(self, a):
        if a is Action.Y:
            return OpenHub(self.grid_game)
        n, c, i = len(self.az), GRID_COLS, self.grid_index
        if a is Action.LEFT and i % c > 0:
            i -= 1
        elif a is Action.RIGHT and i % c < c - 1 and i + 1 < n:
            i += 1
        elif a is Action.UP and i - c >= 0:
            i -= c
        elif a is Action.DOWN and i + c < n:
            i += c
        elif a is Action.DOWN and n and i // c < (n - 1) // c:
            i = n - 1
        elif a in (Action.A, Action.START) and n:
            self._open_info(self.az[i])
        elif a is Action.B:
            self.stack.pop()
        self.grid_index = i
        return None

    def _info(self, a):
        if a is Action.Y:
            return OpenHub(self.info_game)
        shots = len(self.info_game.shots) or 1
        if a is Action.LEFT:
            self.shot_index = (self.shot_index - 1) % shots
        elif a is Action.RIGHT:
            self.shot_index = (self.shot_index + 1) % shots
        elif a is Action.A:
            return self._launch(self.info_game)
        elif a is Action.B:
            self.stack.pop()
        return None

    def _settings(self, a):
        row = SETTINGS_ROWS[self.settings_index]
        if not (row == "power" and a is Action.A):
            self.power_armed = False                   # anything but a second A cancels a pending power off
        if a is Action.UP:
            self.settings_index = max(0, self.settings_index - 1)
        elif a is Action.DOWN:
            self.settings_index = min(len(SETTINGS_ROWS) - 1, self.settings_index + 1)
        elif row == "controls" and a is Action.A:
            return self._toggle_controls()
        elif row == "controls" and a in (Action.LEFT, Action.RIGHT):
            on = a is Action.RIGHT                 # right is On, left is Off: a held, repeating D-pad cannot flip it
            if on != self.touch_controls:
                return self._toggle_controls()
        elif a in (Action.LEFT, Action.RIGHT):
            d = STEP if a is Action.RIGHT else -STEP
            if row == "volume":
                v = min(100, max(0, self.volume + d))
                if v != self.volume:
                    self.volume = v
                    return SetVolume(v)
            elif row == "brightness" and self.brightness_available:
                v = min(100, max(MIN_BRIGHTNESS, self.brightness + d))
                if v != self.brightness:
                    self.brightness = v
                    return SetBrightness(v)
        elif a is Action.A and row == "about":
            self.stack.append(Screen.ABOUT)
        elif a is Action.A and row == "gamepad":
            self.stack.append(Screen.GAMEPAD)
        elif a is Action.A and row == "health":
            self.stack.append(Screen.HEALTH)
        elif a is Action.A and row == "sleep":
            self.stack.append(Screen.SLEEP)
            return Sleep()
        elif a is Action.A and row == "power":
            if self.power_armed:
                self.power_armed = False
                return PowerOff()
            self.power_armed = True
        elif a is Action.B:
            self.stack = [Screen.HOME]
        return None

    def _toggle_controls(self):
        self.touch_controls = not self.touch_controls
        return SetTouchControls(self.touch_controls)

    def _about(self, a):
        if a is Action.B:
            self.stack.pop()
        return None

    def _handler(self, a):
        event = _HANDLER_PRESSES.get(a)
        return self._handler_command(self.handler.press(event)) if event else None

    # touch ------------------------------------------------------------------------------------------------------
    def tap(self, target):
        """A tap on what the views drew there: ("tile", i), ("button", i), ("tab", name), ("grid", i), ("play",),
        ("shot",), ("card",), ("setting", i), ("slider", i, fraction 0..1), ("switch", i), ("back",),
        ("handler", "cross" | "circle" | "square"[, where]), ("handler", "pick", i), ("handler", "row", i), or None
        for empty space. (where only tells two drawn Cross targets apart, for the pressed look.)
        Each does what the buttons would: a tap selects, a tap on what is already selected is A."""
        kind, arg = (target[0], target[1] if len(target) > 1 else None) if target else (None, None)
        if self.screen in (Screen.SLEEP, Screen.ATTRACT):
            return self.wake()
        if self.screen is Screen.THEMES:
            if kind == "theme" and 0 <= arg < len(THEMES):
                return self._pick_theme(arg)
            self.stack.pop()                                   # anywhere else closes it
            return None
        power_row = SETTINGS_ROWS.index("power")
        if not (kind == "setting" and arg == power_row and self.settings_index == power_row):
            self.power_armed = False                   # a tap anywhere but the selected Power off row cancels it
        if kind == "tab" and len(self.stack) == 1:
            self.stack = [Screen.SETTINGS if arg == "settings" else Screen.HOME]
            return None
        if kind == "back" and len(self.stack) > 1:
            return self.apply(Action.B)
        s = self.screen
        if s is Screen.HOME and kind == "tile" and 0 <= arg < len(self.row):
            if arg == self.row_index:
                self.home_focus = "tiles"
                return self._activate(0)
            self.row_index, self.home_focus = arg, "tiles"
        elif s is Screen.HOME and kind == "button":
            return self._activate(arg)
        elif s is Screen.LIBRARY and kind == "grid" and 0 <= arg < len(self.az):
            if arg == self.grid_index:
                return self.apply(Action.A)
            self.grid_index = arg
        elif s is Screen.INFO:
            if kind == "play":
                return self.apply(Action.A)
            if kind == "shot":
                return self.apply(Action.RIGHT)
            if kind is None:                                   # outside the card closes it
                return self.apply(Action.B)
        elif s is Screen.SETTINGS and kind == "setting" and 0 <= arg < len(SETTINGS_ROWS):
            if arg != self.settings_index:
                self.settings_index = arg
            elif SETTINGS_ROWS[arg] in ("about", "gamepad", "controls", "sleep", "power"):
                return self.apply(Action.A)
        elif s is Screen.SETTINGS and kind == "switch" and 0 <= arg < len(SETTINGS_ROWS):
            self.settings_index = arg                          # a switch flips at once, selected or not
            return self._toggle_controls()
        elif s is Screen.SETTINGS and kind == "slider":
            return self.slide(arg, target[2])
        elif s is Screen.HANDLER and kind == "handler":
            if arg in ("cross", "circle", "square"):
                return self._handler_command(self.handler.press(arg))
            if arg == "pick":
                return self._handler_command(self.handler.pick(target[2]))
            if arg == "row":
                self.handler.hub_index = target[2]
                return self._handler_command(self.handler.pick(target[2]))
        return None

    def slide(self, row, fraction):
        """Set settings slider `row` to `fraction` (0..1) of its range, in steps of 10; selects its row."""
        self.settings_index = row
        v = round(min(1.0, max(0.0, fraction)) * 100 / STEP) * STEP
        if SETTINGS_ROWS[row] == "volume" and v != self.volume:
            self.volume = v
            return SetVolume(v)
        if SETTINGS_ROWS[row] == "brightness" and self.brightness_available:
            v = max(MIN_BRIGHTNESS, v)
            if v != self.brightness:
                self.brightness = v
                return SetBrightness(v)
        return None

    def swipe(self, cols, rows):
        """A flick, in whole tiles: cols > 0 moves the selection right (the finger went left), rows > 0 down.
        Home scrolls its row, the Game Library its grid, a game's info page its screenshots (one per flick)."""
        s = self.screen
        moves = []
        if s is Screen.HOME and cols:
            self.home_focus = "tiles"
            moves = [Action.RIGHT if cols > 0 else Action.LEFT] * abs(cols)
        elif s is Screen.LIBRARY:
            moves = ([Action.RIGHT if cols > 0 else Action.LEFT] * abs(cols)
                     + [Action.DOWN if rows > 0 else Action.UP] * abs(rows))
        elif s is Screen.INFO and cols:
            moves = [Action.RIGHT if cols > 0 else Action.LEFT]
        for a in moves:
            self.apply(a)
        return None

    # a finger down, then up: tiles select the instant it lands; everything else acts when it lifts ---------------
    def press(self, target):
        """A finger landed on target (as for tap). A tile that was not selected is selected now and lifting does
        nothing more; the selected tile, a button or empty space is drawn pressed and acts on release(). A slider
        is set at once."""
        self.pressed, self.armed = target, True
        kind = target[0] if target else None
        arg = target[1] if target and len(target) > 1 else None
        s = self.screen
        if s is Screen.HOME and kind == "tile" and 0 <= arg < len(self.row) and arg != self.row_index:
            self.row_index, self.home_focus, self.armed = arg, "tiles", False
        elif s is Screen.LIBRARY and kind == "grid" and 0 <= arg < len(self.az) and arg != self.grid_index:
            self.grid_index, self.armed = arg, False
        elif s is Screen.SETTINGS and kind == "slider":
            self.armed = False
            return self.slide(arg, target[2])
        return None

    def release(self):
        """The finger lifted where it landed (a tap)."""
        target, armed = self.pressed, self.armed
        self.cancel_press()
        return self.tap(target) if armed else None

    def cancel_press(self):
        """The finger moved away (a drag), or its release was lost: nothing acts."""
        self.pressed, self.armed = None, False

    def select_row(self, i):
        """Select Home row position i (clamped): a drag has moved the row under the finger."""
        if self.row:
            self.row_index = min(len(self.row) - 1, max(0, i))
            self.home_focus = "tiles"

    def drag_grid(self, origin, cols, rows):
        """Select the grid tile cols across and rows down from origin, where the drag began; a row end stops it and
        a row past the short last one lands on the last game (as the D-pad does)."""
        n, c = len(self.az), GRID_COLS
        if not n:
            return
        r0, c0 = divmod(origin, c)
        r = min((n - 1) // c, max(0, r0 + rows))
        self.grid_index = min(n - 1, r * c + min(c - 1, max(0, c0 + cols)))
