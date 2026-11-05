"""Game info: screenshots, credits and licences (the credits GAME_LIST.md promises on the device)."""
import re

import pygame

from . import chrome, theme
from .anim import CrossFade
from .text import wrap

# games.json's how-to cards name the GBA's buttons; the console's pad is a DualSense (the Controller page's map).
PAD_NAMES = {"A": "Cross", "B": "Circle", "Start": "OPTIONS", "Select": "Create", "L": "L1", "R": "R1"}


def pad_key(key):
    """A how-to key in the GBA's names as the DualSense says it: "R + steer" -> "R1 + steer", "B (hold)" ->
    "Circle (hold)"."""
    return re.sub(r"\b(A|B|L|R|Start|Select)\b", lambda m: PAD_NAMES[m.group(1)], key)


COL_X = 384
COL_W = theme.W - COL_X - theme.MARGIN
ORIGIN = {"built": "Built from source in the sandbox", "author": "The author's published ROM",
          "missing": "Missing: the ROM file is not there"}


def _strip_scheme(url):
    for p in ("https://", "http://"):
        if url.startswith(p):
            return url[len(p):]
    return url


class InfoView:
    def __init__(self, gfx, art):
        self.gfx, self.art = gfx, art
        self.fade = CrossFade(theme.FADE_MS)
        self.hits = []                    # touch targets; a tap on none of them (outside the card) closes it

    def draw(self, nav, dt, status):
        g, game = self.gfx, nav.info_game
        self.fade.show(game)
        self.fade.update(dt)
        chrome.backdrop(g, self.art, self.fade)
        top = chrome.top_bar(g, status, title="Game info", back=True)
        frame = pygame.Rect(theme.MARGIN, 58, 336, 304)
        g.round_rect(frame, theme.PANEL, 12, alpha=235)
        shot = self.art.shot(game, nav.shot_index)
        if shot is not None:
            g.image(shot, pygame.Rect(frame.x + 8, frame.y + 8, 320, 288))
        else:
            g.text("No screenshot", 14, frame.centerx, frame.centery, anchor="center", alpha=150)
        n = len(game.shots)
        if n > 1:
            for i in range(n):
                cx = frame.centerx + round((i - (n - 1) / 2) * 16)
                g.round_rect((cx - 4, frame.bottom + 12, 8, 8), theme.WHITE, 4, alpha=255 if i == nav.shot_index else 90)
        play = pygame.Rect(COL_X, theme.DETAILS_BOTTOM - theme.PLAY_H, theme.PLAY_W, theme.PLAY_H)
        self._column(game, play.top - 16)
        g.round_rect(play, theme.WHITE, theme.PLAY_H // 2, alpha=255 if game.rom_exists else 90)
        verb = "Continue" if nav.can_resume(game) else "Play"
        g.text(verb, 16, play.centerx, play.centery, weight="bold", color=theme.BLACK, anchor="center")
        pad = theme.OUTLINE + 3
        g.round_rect(play.inflate(2 * pad, 2 * pad), theme.WHITE, theme.PLAY_H // 2 + pad, width=theme.OUTLINE)
        items = ([("←→", "Screens")] if n > 1 else []) + [("A", verb)] + chrome.pb_hint(nav, game) + [("B", "Back")]
        chrome.hints(g, items)
        column = pygame.Rect(COL_X - 12, frame.y, COL_W + 12, play.bottom - frame.y)
        self.hits = [chrome.Hit(frame.inflate(0, 8).union(frame.move(0, 30)), ("shot",), frame, 12),   # with dots
                     chrome.Hit(column, ("card",)),
                     chrome.Hit(play.inflate(12, 12), ("play",), play, theme.PLAY_H // 2)] + top

    def _column(self, game, limit):
        g = self.gfx
        x, y = COL_X, 58
        for line in wrap(game.title, COL_W, lambda s: g.measure(s, theme.TITLE_SIZE, "bold")[0], max_lines=2):
            y = g.text(line, theme.TITLE_SIZE, x, y, weight="bold").bottom
        y += 10
        if game.how_to:
            y = self._how_to(game.how_to, x, y) + 6
        art = "Same as the code" if game.asset_license.strip().lower() == "same as code" else game.asset_license
        rows = [("By", game.authors, 1), ("Genre", " · ".join(p for p in (game.genre, game.platform_name) if p), 1),
                ("Code licence", game.code_license, 1), ("Art licence", art, 2),
                ("Source", _strip_scheme(game.source), 1), ("ROM", ORIGIN[game.rom_origin if game.rom_exists else "missing"], 1)]
        for label, value, lines in rows:
            if not value:
                continue
            if y + 34 > limit:
                break
            y = g.text(label.upper(), 11, x, y, weight="semibold", alpha=150).bottom + 1
            for line in wrap(value, COL_W, lambda s: g.measure(s, 15)[0], max_lines=lines):
                y = g.text(line, 15, x, y).bottom
            y += 8

    def _how_to(self, how, x, y):
        """The how-to-play card: the goal in a sentence or two, then each control as a key pill and what it does."""
        g = self.gfx
        y = g.text("HOW TO PLAY", 11, x, y, weight="semibold", alpha=150).bottom + 2
        for line in wrap(how.get("goal") or "", COL_W, lambda s: g.measure(s, 14)[0], max_lines=3):
            y = g.text(line, 14, x, y).bottom
        y += 6
        for key, action in (how.get("controls") or [])[:6]:
            glyph = chrome.PAD_GLYPHS.get(key) if key in ("A", "B") else None      # a lone face button: its symbol
            word = pad_key(key)
            pill = pygame.Rect(x, y, 26 if glyph else max(26, g.measure(word, 10, "bold")[0] + 12), 18)
            g.round_rect(pill, theme.WHITE, 9, alpha=64)
            if glyph:
                g.image(g.pad_glyph(glyph, 10), pygame.Rect(pill.centerx - 5, pill.centery - 5, 10, 10))
            else:
                g.text(word, 10, pill.centerx, pill.centery, weight="bold", anchor="center")
            g.text(action, 13, pill.right + 8, pill.centery, anchor="midleft", alpha=220)
            y = pill.bottom + 4
        return y
