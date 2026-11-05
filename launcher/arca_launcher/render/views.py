"""Picks the view for the current screen, and draws the full-screen cards."""
import pygame

from .. import NAME
from ..model import Screen
from . import chrome, theme
from .home import HomeView
from .info import InfoView
from .library_view import LibraryView
from .mascot import MascotView
from .settings_view import SettingsView
from .sleep_view import SleepView
from .booth_views import AttractView, ThemeView
from .handler_view import HandlerView
from .splash import SplashView
from .text import ellipsize, wrap

# The DualSense in a game (the Controller page's "In games" column): shown while one loads, since its title screen
# says PRESS START and the pad has no Start.
GAME_PAD = [("START", "Start"), ("A", "A"), ("B", "B"), ("", "Hold PS: back to the launcher")]


class Views:
    def __init__(self, gfx, art):
        self.gfx = gfx
        self.art = art
        self.splash = SplashView(gfx)
        self.home = HomeView(gfx, art)
        self.library = LibraryView(gfx, art)
        self.info = InfoView(gfx, art)
        self.settings = SettingsView(gfx)
        self.sleep = SleepView(gfx)
        self.themes = ThemeView(gfx)
        self.attract = AttractView(gfx, art)
        self.handler = HandlerView(gfx)
        self.mascot = MascotView(gfx)
        self.hits = []                    # the drawn screen's touch targets, topmost last

    def draw(self, nav, dt, status):
        view = {Screen.HOME: self.home, Screen.LIBRARY: self.library, Screen.INFO: self.info,
                Screen.SLEEP: self.sleep, Screen.THEMES: self.themes, Screen.ATTRACT: self.attract,
                Screen.HANDLER: self.handler}.get(nav.screen, self.settings)
        view.draw(nav, dt, status)
        self.hits = view.hits
        if nav.pressed is not None:
            for h in self.hits:
                if h.target == nav.pressed and h.shape is not None:
                    chrome.pressed(self.gfx, h)
                    break
        # HANDLER draws its own PB, saying the flow's line
        if nav.mascot is not None and nav.screen not in (Screen.SLEEP, Screen.ATTRACT, Screen.HANDLER):
            self.mascot.draw(nav)
        if nav.notice:
            chrome.toast(self.gfx, nav.notice)
        if nav.osd:
            chrome.level_bar(self.gfx, *nav.osd)

    def hit(self, x, y):
        """What a tap at logical (x, y) landed on in the last frame drawn, as a model.Nav.tap target; None if nothing.
        A slider target carries where along the bar it was tapped, 0..1."""
        for h in reversed(self.hits):
            if h.rect.collidepoint(x, y):
                if h.bar is not None:
                    return h.target + (self.along(h.bar, x),)
                return h.target
        return None

    def slider_bar(self, row):
        """The drawn bar of settings slider `row`, for a finger dragging along it."""
        return next((h.bar for h in self.hits if h.target == ("slider", row)), None)

    @staticmethod
    def along(bar, x):
        return (x - bar.x) / bar.w

    def starting(self, game):
        g = self.gfx
        g.fill(theme.BG)
        card = pygame.Rect(0, 0, 440, 120)
        card.center = (theme.W // 2, theme.H // 2)
        g.round_rect(card, theme.PANEL, 16)
        g.text("Starting", 13, card.centerx, card.y + 28, weight="semibold", alpha=160, anchor="midtop")
        title = ellipsize(game.title, card.w - 40, lambda s: g.measure(s, 24, "bold")[0])
        g.text(title, 24, card.centerx, card.y + 52, weight="bold", anchor="midtop")
        if not game.app:                           # the title screen says START: a DualSense calls it OPTIONS
            g.text("In the game", 12, card.centerx, card.bottom + 22, weight="semibold", alpha=150, anchor="midtop")
            right = card.centerx + chrome.hints_width(g, GAME_PAD) // 2
            chrome.hints(g, GAME_PAD, bottom=card.bottom + 66, right=right)

    def message(self, title, body, status):
        self.hits = []
        g = self.gfx
        g.fill(theme.BG)
        chrome.top_bar(g, status, title=NAME)
        y = g.text(title, 22, theme.W // 2, 170, weight="bold", anchor="midtop").bottom + 12
        for line in wrap(body, 560, lambda s: g.measure(s, 15)[0], max_lines=4):
            y = g.text(line, 15, theme.W // 2, y, anchor="midtop", alpha=200).bottom + 2
