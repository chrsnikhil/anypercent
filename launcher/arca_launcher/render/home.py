"""Home: the PS5-style row of big tiles (approved layout C)."""
import pygame

from . import chrome, theme
from .anim import CrossFade, Smooth
from .mascot import face_texture
from .text import ellipsize

ORIGIN = {"built": "built from source", "author": "author's ROM", "missing": "ROM missing", "app": "app"}
DOT3 = "···"


class HomeView:
    def __init__(self, gfx, art):
        self.gfx, self.art = gfx, art
        self.sizes = []
        self.scroll = Smooth(0, theme.SLIDE_MS)
        self.fade = CrossFade(theme.FADE_MS)
        self._row_ids = None
        self.visible = []                 # row positions drawn in the last frame
        self.play_rect = None             # where the Play (or Open) button was drawn
        self.more_rect = None             # where the ... button was drawn
        self.hits = []                    # touch targets drawn in the last frame: [chrome.Hit]
        self.held = None                  # while a finger drags the row: its scroll position, in px

    @property
    def position(self):
        """The row's scroll position as drawn."""
        return self.scroll.value if self.held is None else self.held

    def hold(self, pos):
        """Draw the row at scroll position pos (under a dragging finger) until release()."""
        self.held = pos

    def release(self):
        """The finger lifted: ease from where it left the row to the selected tile, without a jump."""
        if self.held is not None:
            self.scroll.value, self.held = float(self.held), None

    def _sync(self, nav):
        ids = [x.id if x is not None else None for x in nav.row]
        if ids != self._row_ids:          # new or reordered row (a game was played): jump, don't slide
            self._row_ids = ids
            self.sizes = [Smooth(theme.TILE, theme.SLIDE_MS) for _ in ids]
            self.sizes[nav.row_index].set(theme.TILE_BIG, snap=True)
            self.scroll.set(nav.row_index * (theme.TILE + theme.TILE_GAP), snap=True)
        for i, s in enumerate(self.sizes):
            s.set(theme.TILE_BIG if i == nav.row_index else theme.TILE)
        self.scroll.set(nav.row_index * (theme.TILE + theme.TILE_GAP))

    def draw(self, nav, dt, status):
        self._sync(nav)
        for s in self.sizes:
            s.update(dt)
        self.scroll.update(dt)
        self.fade.show(nav.selected)
        self.fade.update(dt)
        chrome.backdrop(self.gfx, self.art, self.fade)
        self.hits = chrome.top_bar(self.gfx, status, tab="games")
        self._row(nav)
        self._details(nav)
        chrome.sponsor_logo(self.gfx, theme.MARGIN, theme.H - 10, 24, anchor="bottomleft")
        chrome.hints(self.gfx, self._hints(nav))

    def _row(self, nav):
        g = self.gfx
        x = theme.MARGIN - self.position
        self.visible = []
        for i, game in enumerate(nav.row):
            size = self.sizes[i].value
            if x > theme.W:
                break
            if x + size >= theme.MARGIN:      # a tile that has scrolled off the left leaves no sliver behind
                self.visible.append(i)
                selected = i == nav.row_index
                rect = pygame.Rect(round(x), round(theme.ROW_Y + (theme.TILE_BIG - size) / 2), round(size), round(size))
                want = theme.TILE_BIG if selected else theme.TILE
                tex = self.art.library_tile(want) if game is None else self.art.tile(game, want)
                g.image(tex, rect, 255 if game is None or game.rom_exists else 110)
                if selected and nav.home_focus == "tiles":
                    pad = theme.OUTLINE + 3
                    g.round_rect(rect.inflate(2 * pad, 2 * pad), theme.WHITE, theme.TILE_RADIUS + pad, width=theme.OUTLINE)
                weight = "semibold" if selected else "regular"
                label = ellipsize("Game Library" if game is None else game.title, rect.w + 10,
                                  lambda s: g.measure(s, theme.LABEL_SIZE, weight)[0])
                g.text(label, theme.LABEL_SIZE, rect.centerx, rect.bottom + 8, weight=weight,
                       alpha=255 if selected else 200, anchor="midtop")
                half = theme.TILE_GAP // 2                  # the gap is split between neighbours; the label counts
                self.hits.append(chrome.Hit(pygame.Rect(rect.x - half, theme.ROW_Y - 8, rect.w + 2 * half,
                                                        theme.TILE_BIG + 40), ("tile", i), rect, theme.TILE_RADIUS))
            x += size + theme.TILE_GAP

    def _details(self, nav):
        g = self.gfx
        game = nav.selected
        if game is None:
            title, meta, buttons, playable = "Game Library", f"All {len(nav.az)} games, A to Z", ["Open"], True
        else:
            origin = ORIGIN[game.rom_origin if game.rom_exists else "missing"]
            title = game.title
            meta = " · ".join(p for p in (game.authors, game.genre, origin) if p)
            buttons = [DOT3 if b == "..." else b for b in nav.home_buttons()]
            playable = game.rom_exists
        bottom = theme.DETAILS_BOTTOM
        title = ellipsize(title, 420, lambda s: g.measure(s, theme.TITLE_SIZE, "bold")[0])
        meta = ellipsize(meta, 420, lambda s: g.measure(s, theme.META_SIZE)[0])
        mr = g.text(meta, theme.META_SIZE, theme.MARGIN, bottom, anchor="bottomleft", alpha=200)
        tr = g.text(title, theme.TITLE_SIZE, theme.MARGIN, mr.top - 2, weight="bold", anchor="bottomleft")
        x = theme.MARGIN + max(tr.w, mr.w) + 26
        for i, label in enumerate(buttons):
            if i == 0:
                rect = pygame.Rect(x, bottom - theme.PLAY_H, theme.PLAY_W, theme.PLAY_H)
                g.round_rect(rect, theme.WHITE, theme.PLAY_H // 2, alpha=255 if playable else 90)
                g.text(label, 16, rect.centerx, rect.centery, weight="bold", color=theme.BLACK, anchor="center")
                self.play_rect = rect
            elif label == "PB":                        # PB's hub: his face, so the pill reads as the mascot
                face = 26
                w = face + 6 + g.measure(label, 14, "bold")[0] + 28
                rect = pygame.Rect(x, bottom - theme.MORE_D, w, theme.MORE_D)
                g.round_rect(rect, theme.WHITE, theme.MORE_D // 2, alpha=46)
                g.image(face_texture(g), pygame.Rect(rect.x + 12, rect.centery - face // 2, face, face))
                g.text(label, 14, rect.x + 12 + face + 6, rect.centery, weight="bold", anchor="midleft")
            elif label != DOT3:                        # Restart: a quieter pill beside Continue
                w = g.measure(label, 14, "bold")[0] + 32
                rect = pygame.Rect(x, bottom - theme.MORE_D, w, theme.MORE_D)
                g.round_rect(rect, theme.WHITE, theme.MORE_D // 2, alpha=46)
                g.text(label, 14, rect.centerx, rect.centery, weight="bold", anchor="center")
            else:
                rect = pygame.Rect(x, bottom - theme.MORE_D, theme.MORE_D, theme.MORE_D)
                g.round_rect(rect, theme.WHITE, theme.MORE_D // 2, alpha=46)
                for dx in (-9, 0, 9):                  # three drawn dots: font middots are too small in Outfit
                    g.round_rect((rect.centerx + dx - 3, rect.centery - 3, 6, 6), theme.WHITE, 3)
                self.more_rect = rect
            if nav.home_focus == "buttons" and i == nav.button_index:
                pad = theme.OUTLINE + 3
                g.round_rect(rect.inflate(2 * pad, 2 * pad), theme.WHITE, rect.h // 2 + pad, width=theme.OUTLINE)
            self.hits.append(chrome.Hit(rect.inflate(10, 12), ("button", i), rect, rect.h // 2))
            x = rect.right + 12

    @staticmethod
    def _hints(nav):
        if nav.home_focus == "buttons":
            return [("A", "Select"), ("B", "Back")]
        if nav.selected is None:
            return [("A", "Open"), ("L R", "Tabs")]
        return ([("A", "Continue" if nav.can_resume(nav.selected) else "Play")] + chrome.pb_hint(nav, nav.selected)
                + [("START", "Info"), ("L R", "Tabs")])
