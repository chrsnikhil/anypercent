"""The theme picker (the DualSense trick) and attract mode (the launcher left idle on Home, at a booth)."""
import math

import pygame

from .. import NAME
from ..themes import THEMES
from . import chrome, handler_art, theme
from .mascot import face_texture

ROW_Y, ROW_H, ROW_PITCH = 78, 46, 54
CYCLE_MS = 5000
BOOTH_QR = 124                                                       # px: the booth link's QR code, at most


class ThemeView:
    """Every theme as a row with its colours; the highlighted one previews on the whole screen."""

    def __init__(self, gfx):
        self.gfx = gfx
        self.hits = []

    def draw(self, nav, dt, status):
        g = self.gfx
        cur = THEMES[nav.theme_index]
        g.fill(cur.bg)
        g.text("Theme", 22, theme.MARGIN + 38, 26, weight="bold")
        g.text("Create + Options", 12, theme.W - theme.MARGIN - 38, 32, alpha=150, anchor="topright")
        self.hits = []
        for i, t in enumerate(THEMES):
            row = pygame.Rect(60, ROW_Y + i * ROW_PITCH, theme.W - 120, ROW_H)
            self.hits.append(chrome.Hit(row.inflate(0, 8), ("theme", i), row, 12))
            if i == nav.theme_index:
                g.round_rect(row, theme.WHITE, 12, alpha=26)
                g.round_rect(row.inflate(6, 6), t.accent, 15, alpha=230, width=2)
            g.text(t.name, 17, row.x + 20, row.centery, weight="semibold", anchor="midleft")
            x = row.right - 20
            for colour in (t.light, t.accent, t.panel, t.bg):      # right to left: ground, card, accent, light bar
                sw = pygame.Rect(0, 0, 26, 26)
                sw.midright = (x, row.centery)
                g.round_rect(sw, colour, 7)
                g.round_rect(sw, theme.WHITE, 7, alpha=60, width=1)
                x = sw.left - 8
            logo = chrome.sponsor_logo(g, x - 10, row.centery, 20, t.id, anchor="midright", alpha=200)
            if logo is not None:
                x = logo.left
            if t.id == nav.theme:
                g.text("Current", 12, x - 14, row.centery, alpha=170, anchor="midright")
        chrome.hints(g, [("A", "Apply"), ("B", "Close")])


CLIP_MS = 100                                                       # a clip frame every 100 ms


class AttractView:
    """The launcher as a booth display: each game in turn, big, with how to start playing."""

    def __init__(self, gfx, art):
        self.gfx = gfx
        self.art = art
        self.hits = []
        self.ms = 0

    def draw(self, nav, dt, status):
        g = self.gfx
        games = [x for x in nav.az if x.rom_exists and not x.app] or nav.az     # games: an app has no play to show
        self.ms += dt
        g.fill(theme.BG)
        if not games:
            g.text(NAME, 40, theme.W // 2, theme.H // 2, weight="bold", anchor="center")
            return
        game = games[(self.ms // CYCLE_MS) % len(games)]
        full = pygame.Rect(0, 0, theme.W, theme.H)
        bg = self.art.bg(game)
        if bg is not None:
            g.image(bg, full)
        g.round_rect(full, theme.BG, 0, alpha=150)
        g.text(NAME, 20, theme.MARGIN, 18, weight="bold")
        g.text("Retro handheld  ·  ETHGlobal Mumbai", 12, theme.MARGIN + 70, 24, alpha=170)
        chrome.sponsor_logo(g, theme.W - theme.MARGIN, 14, 26, anchor="topright")
        tile = self.art.tile(game, 216)
        if tile is not None:
            g.image(tile, pygame.Rect(70, 96, 216, 216))
        g.text("Now showing", 12, 320, 112, weight="semibold", alpha=150)
        g.text(game.title, 34, 320, 132, weight="bold")
        if game.clip:                                               # real gameplay, 10 frames a second
            shot = self.art.clip_frame(game, (self.ms // CLIP_MS) % len(game.clip))
        else:
            shot = self.art.shot(game, (self.ms // 1500) % max(1, len(game.shots)))
        target = nav.board_times.get(game.id) if nav.handler_enabled else None
        if shot is not None:
            w, h = shot.get_rect().size
            k = min((256 if target else 400) / w, 170 / h)          # beside the board card, never under it
            g.image(shot, pygame.Rect(320, 190, round(w * k), round(h * k)))
        if target is not None:
            self._board_card(*target)
        if nav.booth_url:
            self._booth_qr(nav.booth_url)
        pulse = 150 + 105 * (0.5 + 0.5 * math.sin(self.ms / 420))
        g.text("Press any button or tap to play", 18, theme.W // 2, theme.H - 52, weight="semibold",
               alpha=pulse, anchor="midtop")
        for i in range(len(games)):                                   # where the cycle is
            on = games[i] is game
            g.round_rect((theme.W // 2 - len(games) * 7 + i * 14, theme.H - 18, 8, 8), theme.ACCENT if on else theme.WHITE,
                         4, alpha=255 if on else 70)

    def _booth_qr(self, url):
        """The booth's link (booth-url.txt) as a QR code in the bottom-left corner, whole pixels a module so a
        judge's phone reads it; nothing for a link no QR code holds."""
        g = self.gfx
        try:
            surf = handler_art.tex(g, ("qr", url), lambda: handler_art.qr_surface(url), pixel_art=True)
        except ValueError:
            return
        n = surf.get_rect().w
        size = n * max(1, BOOTH_QR // n)
        box = pygame.Rect(theme.MARGIN, theme.H - 12 - size, size, size)
        g.image(surf, box)
        g.text("Scan for the project", 13, box.right + 10, box.centery, weight="semibold", alpha=200,
               anchor="midleft")

    def _board_card(self, runner, time):
        """An arcade game's run to beat (the handler's target, from its shipped test log), with PB's face."""
        g = self.gfx
        card = pygame.Rect(596, 190, 180, 170)
        g.round_rect(card, theme.WHITE, 14, alpha=26)
        x = card.x + 16
        g.text("Run to beat", 12, x, card.y + 16, weight="semibold", alpha=150)
        g.text(runner, 22, x, card.y + 38, weight="bold", color=theme.ACCENT)
        g.text(time, 34, x, card.y + 66, weight="bold")
        face = 32
        g.image(face_texture(g), pygame.Rect(x - 2, card.bottom - 16 - face, face, face))
        g.text("Race her ghost", 13, x + face + 6, card.bottom - 16 - face // 2, weight="semibold", alpha=210,
               anchor="midleft")
