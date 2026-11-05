"""Pieces every screen shares: backdrop, top bar, button hints, notices, the sponsor logo."""
import os
from dataclasses import dataclass

import pygame

from . import theme
from .text import ellipsize


@dataclass(frozen=True)
class Status:
    clock: str
    battery: int | None = None
    wifi: int | None = None           # 1..100 signal, 0 not connected, None no Wi-Fi hardware
    warning: str | None = None        # "Low power", "Too hot" or "Hot" from the Pi's firmware
    pad: int | None = None            # the connected controller's battery percent
    temp: int | None = None           # SoC degrees C: shown with a heat warning


@dataclass(frozen=True)
class Hit:
    """A touch target as drawn: `rect` takes the finger (larger than the drawing), `shape` and `radius` are what was
    drawn (for the pressed look; None for none), `bar` a slider's bar (a tap carries where along it, 0..1)."""
    rect: pygame.Rect
    target: tuple
    shape: pygame.Rect | None = None
    radius: int = 0
    bar: pygame.Rect | None = None


def pressed(gfx, hit):
    """The pressed look: a light wash over the target and a ring around it, while the finger is down."""
    gfx.round_rect(hit.shape, theme.WHITE, hit.radius, alpha=60)
    gfx.round_rect(hit.shape.inflate(6, 6), theme.WHITE, hit.radius + 3, alpha=210, width=2)


def backdrop(gfx, art, fade):
    """Theme colour, then the selected game's blurred background, fading in over the previous one."""
    gfx.fill(theme.BG)
    full = pygame.Rect(0, 0, theme.W, theme.H)
    prev = art.bg(fade.prev) if fade.prev is not None else None
    cur = art.bg(fade.cur) if fade.cur is not None else None
    if prev is not None:
        gfx.image(prev, full)
    if cur is not None:
        gfx.image(cur, full, 255 * fade.t)
    if theme.TINT:
        gfx.round_rect(full, theme.BG, 0, alpha=theme.TINT)     # the theme's colour over the game's art


ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def sponsor_logo(gfx, x, y, h, theme_id=None, anchor="topleft", alpha=230):
    """The theme's sponsor logo, h pixels tall, placed by its anchor corner; returns its Rect, or None for a theme
    without one (Any%). Textures are kept per renderer (a new one is made after every game)."""
    from ..themes import get
    t = get(theme_id or theme.CURRENT)
    if not t.logo:
        return None
    cache = gfx.__dict__.setdefault("_logos", {})
    if t.logo not in cache:
        try:
            cache[t.logo] = gfx.texture(pygame.image.load(os.path.join(ASSETS, t.logo)))
        except (pygame.error, FileNotFoundError):
            cache[t.logo] = None
    tex = cache[t.logo]
    if tex is None:
        return None
    w = round(tex.width * h / tex.height)
    gap = round(h * 0.4)
    label_w = 0
    if t.label:
        label_w = gap + gfx.text(t.name, round(h * 0.8), -1000, -1000, weight="bold").w   # measure off screen
    r = pygame.Rect(0, 0, w + label_w, h)
    setattr(r, anchor, (round(x), round(y)))
    gfx.image(tex, pygame.Rect(r.x, r.y, w, h), alpha)
    if t.label:
        gfx.text(t.name, round(h * 0.8), r.x + w + gap, r.centery, weight="bold", alpha=alpha, anchor="midleft")
    return r


WARN = (255, 190, 60)                                                   # power / heat warnings, on every theme

BACK_ARROW = pygame.Rect(theme.MARGIN - 4, theme.TOP_Y - 6, 30, 30)     # the drawn back button, top left
BACK_HIT = pygame.Rect(0, 0, BACK_ARROW.right + 30, 52)                 # finger-sized, reaching the screen corner


def _thermometer(gfx, box):
    """A small thermometer in the warning colour: stem and bulb."""
    cx = box.centerx
    gfx.round_rect((cx - 1, box.y + 1, 3, box.h - 6), WARN, 1)
    gfx.round_rect((cx - 3, box.bottom - 7, 7, 7), WARN, 3)


def _bolt(gfx, box):
    """A small lightning bolt in the warning colour (power)."""
    x, y, h = box.x + 1, box.y + 1, box.h - 2
    mid = y + h // 2
    for dx in range(2):
        gfx.line((x + 5 + dx, y), (x + 1 + dx, mid), WARN)
        gfx.line((x + 1 + dx, mid), (x + 6 + dx, mid), WARN)
        gfx.line((x + 6 + dx, mid), (x + 2 + dx, y + h), WARN)


def top_bar(gfx, status, tab=None, title=None, back=False):
    """Tabs (or a title, with a back arrow on inner screens), clock and battery.
    Returns its touch targets: Hits for ("tab", key) or ("back",)."""
    x, y = theme.MARGIN, theme.TOP_Y
    hits = []
    if back:
        gfx.round_rect(BACK_ARROW, theme.WHITE, BACK_ARROW.h // 2, alpha=46)
        gfx.text("←", 16, BACK_ARROW.centerx, BACK_ARROW.centery, weight="bold", anchor="center")
        hits.append(Hit(BACK_HIT, ("back",), BACK_ARROW, BACK_ARROW.h // 2))
        x = BACK_ARROW.right + 12
    if title is not None:
        gfx.text(title, theme.TAB_SIZE, x, y, weight="bold")
    else:
        for name, key in (("Games", "games"), ("Settings", "settings")):
            active = key == tab
            r = gfx.text(name, theme.TAB_SIZE, x, y, weight="bold" if active else "regular", alpha=255 if active else 150)
            if active:
                gfx.round_rect((r.x, r.bottom + 3, r.w, 2), theme.ACCENT, 1)
            pad = theme.TAB_GAP // 2
            hits.append(Hit(pygame.Rect(r.x - pad, 0, r.w + 2 * pad, r.bottom + 14), ("tab", key),
                            r.inflate(14, 8), 8))
            x = r.right + theme.TAB_GAP
    right = theme.W - theme.MARGIN
    if status.battery is not None:
        body = pygame.Rect(right - 26, y + 3, 26, 12)
        gfx.round_rect(body, theme.WHITE, 3, alpha=220, width=2)
        gfx.round_rect((body.x + 3, body.y + 3, max(1, round(20 * status.battery / 100)), 6), theme.WHITE, 1)
        right = body.x - 12
    if status.wifi is not None:
        lit = 0 if not status.wifi else min(4, 1 + status.wifi // 25)
        for i in range(4):                                         # signal bars, short to tall
            h = 4 + 3 * i
            gfx.round_rect((right - 22 + i * 6, y + 15 - h, 4, h), theme.WHITE, 1, alpha=220 if i < lit else 60)
        right -= 22 + 10
        if not status.wifi:
            r = gfx.text("No Wi-Fi", 12, right, y + 2, weight="semibold", alpha=200, anchor="topright")
            right = r.x - 12
    if status.pad is not None:                                     # the controller and its charge
        r = gfx.text(f"{status.pad}%", 12, right, y + 2, weight="semibold", alpha=220, anchor="topright")
        body = pygame.Rect(r.x - 6 - 20, y + 3, 20, 11)
        gfx.round_rect(body, theme.WHITE, 5, alpha=220, width=2)
        for cx in (body.x + 6, body.right - 6):
            gfx.round_rect((cx - 1, body.y + 4, 3, 3), theme.WHITE, 1, alpha=220)
        right = body.x - 12
    if status.warning:
        hot = status.warning != "Low power"
        label = f"{status.warning} {status.temp}°C" if hot and status.temp is not None else status.warning
        r = gfx.text(label, 12, right - 9, y + 2, weight="bold", color=WARN, anchor="topright")
        icon = pygame.Rect(r.x - 4 - 8, r.y, 8, r.h)
        (_thermometer if hot else _bolt)(gfx, icon)
        pill = r.union(icon).inflate(18, 6)
        gfx.round_rect(pill, WARN, pill.h // 2, alpha=220, width=2)
        right = pill.x - 12
    gfx.text(status.clock, theme.TAB_SIZE, right, y, anchor="topright", alpha=220)
    return hits


# The only pad is a DualSense, so a hint names its buttons, whichever letter the screen uses for the action.
PAD_GLYPHS = {"A": "cross", "X": "cross", "B": "circle", "O": "circle", "S": "square", "Y": "triangle"}
PAD_WORDS = {"START": "OPTIONS", "L R": "L1 R1"}


def pb_hint(nav, game):
    """Triangle opens PB's hub for any game; the hint names it where PB has a board to show, an arcade game."""
    return [("Y", "PB")] if getattr(nav, "handler_enabled", False) and game is not None and game.arcade else []


def _pill_w(gfx, key):
    return 18 if key in PAD_GLYPHS else max(18, gfx.measure(PAD_WORDS.get(key, key), 9, "bold")[0] + 10)


def hints_width(gfx, items):
    """How wide hints() draws items, to centre a row of them."""
    return max(0, sum(gfx.measure(label, theme.HINT_SIZE)[0] + (5 + _pill_w(gfx, key) if key else 0) + 14
                      for key, label in items) - 14)


def hints(gfx, items, bottom=theme.H - 12, right=theme.W - theme.MARGIN):
    """Button hints ending at right (the bottom right by default), e.g. [("A", "Play"), ("B", "Back")]; an empty key is
    a label alone. A face button (PAD_GLYPHS) is drawn as the DualSense's own symbol. Returns the leftmost hint's left
    edge."""
    x = right
    for key, label in reversed(items):
        r = gfx.text(label, theme.HINT_SIZE, x, bottom, anchor="bottomright", alpha=160)
        if not key:
            x = r.left - 14
            continue
        glyph, word = PAD_GLYPHS.get(key), PAD_WORDS.get(key, key)
        pill = pygame.Rect(0, 0, _pill_w(gfx, key), 18)
        pill.midright = (r.left - 5, r.centery)
        gfx.round_rect(pill, theme.WHITE, 9, alpha=64)
        if glyph:
            gfx.image(gfx.pad_glyph(glyph, 10), pygame.Rect(pill.centerx - 5, pill.centery - 5, 10, 10))
        else:
            gfx.text(word, 9, pill.centerx, pill.centery, weight="bold", anchor="center")
        x = pill.left - 14
    return x + 14


TOAST_MAX_W = theme.W - 300 - theme.MARGIN       # the strip left of the button hints


def level_bar(gfx, kind, value):
    """The volume or brightness bar, top centre, after a PS + D-pad step on the controller."""
    rect = pygame.Rect(0, 0, 300, 44)
    rect.midtop = (theme.W // 2, 50)
    gfx.round_rect(rect, (44, 46, 56), 14, alpha=245)
    label = "Volume" if kind == "volume" else "Brightness"
    gfx.text(label, 13, rect.x + 16, rect.centery, weight="bold", anchor="midleft")
    gfx.text(f"{value}%", 13, rect.right - 16, rect.centery, weight="semibold", anchor="midright")
    track = pygame.Rect(rect.x + 104, rect.centery - 3, rect.w - 104 - 60, 6)
    gfx.round_rect(track, theme.WHITE, 3, alpha=60)
    if value:
        gfx.round_rect((track.x, track.y, max(6, round(track.w * value / 100)), track.h), theme.ACCENT, 3)
    return rect


def toast(gfx, message):
    """A notice in the free strip along the bottom left, below the Play button row."""
    message = ellipsize(message, TOAST_MAX_W - 28, lambda s: gfx.measure(s, 13)[0])
    rect = pygame.Rect(0, 0, gfx.measure(message, 13)[0] + 28, 30)
    rect.bottomleft = (theme.MARGIN, theme.H - 6)
    gfx.round_rect(rect, (44, 46, 56), 10, alpha=245)
    gfx.text(message, 13, rect.centerx, rect.centery, anchor="center")
    return rect
