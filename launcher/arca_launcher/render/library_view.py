"""Game Library: every game, A to Z, in a five-column grid."""
import pygame

from .. import model
from . import chrome, theme
from .anim import CrossFade, Smooth
from .text import ellipsize

PITCH = theme.TILE + 34
X0 = (theme.W - (model.GRID_COLS * theme.TILE + (model.GRID_COLS - 1) * theme.TILE_GAP)) // 2
Y0 = 64
TOP, BOTTOM = 44, 34                      # the top bar and the hints strip, drawn over the grid


class LibraryView:
    def __init__(self, gfx, art):
        self.gfx, self.art = gfx, art
        self.scroll = Smooth(0, theme.SLIDE_MS)
        self.fade = CrossFade(theme.FADE_MS)
        self.visible = []                 # game indices drawn in the last frame
        self.hits = []                    # touch targets drawn in the last frame: [(rect, target)]

    def draw(self, nav, dt, status):
        g, cols = self.gfx, model.GRID_COLS
        self.scroll.set(max(0, nav.grid_index // cols - 1) * PITCH)
        self.scroll.update(dt)
        self.fade.show(nav.grid_game)
        self.fade.update(dt)
        chrome.backdrop(g, self.art, self.fade)
        self.visible = []
        self.hits = []
        view = pygame.Rect(0, TOP, theme.W, theme.H - TOP - BOTTOM)     # between the bars
        for i, game in enumerate(nav.az):
            r, c = divmod(i, cols)
            y = Y0 + r * PITCH - self.scroll.value
            if y > theme.H or y < 0:          # a row that has scrolled up under the top bar is not drawn
                continue
            self.visible.append(i)
            rect = pygame.Rect(X0 + c * (theme.TILE + theme.TILE_GAP), round(y), theme.TILE, theme.TILE)
            g.image(self.art.tile(game, theme.TILE), rect, 255 if game.rom_exists else 110)
            selected = i == nav.grid_index
            if selected:
                pad = theme.OUTLINE + 3
                g.round_rect(rect.inflate(2 * pad, 2 * pad), theme.WHITE, theme.TILE_RADIUS + pad, width=theme.OUTLINE)
            weight = "semibold" if selected else "regular"
            label = ellipsize(game.title, rect.w + 10, lambda s: g.measure(s, theme.LABEL_SIZE, weight)[0])
            g.text(label, theme.LABEL_SIZE, rect.centerx, rect.bottom + 8, weight=weight,
                   alpha=255 if selected else 200, anchor="midtop")
            half = theme.TILE_GAP // 2                  # tile, label and half of each gap; only what shows
            hit = pygame.Rect(rect.x - half, rect.y - 6, rect.w + 2 * half, PITCH).clip(view)
            if hit.h:
                self.hits.append(chrome.Hit(hit, ("grid", i), rect, theme.TILE_RADIUS))
        if not nav.az:
            g.text("No games in the library", 18, theme.W // 2, theme.H // 2, anchor="center", alpha=200)
        g.round_rect((0, 0, theme.W, TOP), theme.BG, 0, alpha=230)            # tiles scroll under the bars
        g.round_rect((0, theme.H - BOTTOM, theme.W, BOTTOM), theme.BG, 0, alpha=200)
        self.hits += chrome.top_bar(g, status, title=f"Game Library · {len(nav.az)} games", back=True)
        chrome.hints(g, [("A", "Info")] + chrome.pb_hint(nav, nav.grid_game) + [("B", "Back")])
