"""The handler's pictures, as look A of the mockups draws them (docs/superpowers/specs/2026-10-24-pb-handler-mockups/
handler-states.html): the card icons, the waiting ring and phone, the progress bar, the fake QR code, the status
dots, the coins and the dimmed Home behind the sale toast. Each is painted once into a texture kept per renderer,
then moved by handler_fx's curves as it is drawn (t is the ms since the state began)."""
import math

import pygame

from ..qr import encode as encode_qr
from . import handler_fx as fx
from . import theme

GREEN, RED, AMBER, YELLOW = (95, 209, 122), (224, 83, 61), (255, 177, 92), (255, 211, 77)
ORANGE, SOFT, DIM, TRACK = (240, 102, 61), (201, 207, 219), (92, 99, 114), (42, 46, 56)
INK, WHITE = (11, 13, 18), theme.WHITE
OK_BG, NO_BG, WARN_BG, YOU_BG = (30, 61, 42), (61, 30, 30), (58, 42, 20), (31, 58, 92)
COIN_RIM, COIN_DARK, COIN_LIGHT, COIN_INK = (122, 90, 8), (184, 138, 18), (255, 242, 179), (90, 63, 0)

X4 = 4                                    # icons are drawn 4x and smoothed down
DASH = 120                                # the mockup's stroke-dasharray: a tick or cross draws in along its length
STRIPE = 34                               # the progress bar's stripes repeat (and run) every 34 px
BEAM_H = 26


def tex(g, key, make, pixel_art=False):
    """Textures kept per renderer (a new one is made after every game), like chrome's sponsor logos."""
    cache = g.__dict__.setdefault("_handler_tex", {})
    if key not in cache:
        if len(cache) > 64:                                  # old QR codes
            cache.clear()
        cache[key] = g.texture(make(), pixel_art=pixel_art)
    return cache[key]


def _stroke(surf, colour, points, width, closed=False):
    """A thick line through points with round caps and joins, as the mockup's SVG strokes."""
    pts = [(x * X4, y * X4) for x, y in points]
    pts += pts[:1] if closed else []
    r = width * X4 / 2
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        d = math.hypot(x2 - x1, y2 - y1) or 1
        nx, ny = -(y2 - y1) / d * r, (x2 - x1) / d * r
        pygame.draw.polygon(surf, colour, [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)])
    for p in pts:
        pygame.draw.circle(surf, colour, p, r)


def _smooth(size, ground, paint):
    """paint(surface) on a 4x canvas, then smoothed down to size. The clear pixels carry the ground's colour so
    the smoothed edges do not darken."""
    big = pygame.Surface((size[0] * X4, size[1] * X4), pygame.SRCALPHA)
    big.fill((*ground, 0))
    paint(big)
    return pygame.transform.smoothscale(big, size)


# ---- the card icons ----------------------------------------------------------------------------------------------

_GROUNDS = {"done": OK_BG, "no": NO_BG, "warn": WARN_BG, "time": TRACK, "back": TRACK}
MARK_W = 13
# The marks that draw themselves in: colour, strokes and the axis each stroke runs along one way (0 x, 1 y), so a
# cut moving along that axis follows the pen.
_DRAWN = {"done": (GREEN, (((36, 66), (56, 86), (94, 44)),), 0),
          "no": (RED, (((42, 42), (86, 86)), ((86, 42), (42, 86))), 1)}


def _reach(kind):
    """(axis, first and last pixel the mark covers along it, its longest stroke's length)."""
    _, strokes, axis = _DRAWN[kind]
    along = [p[axis] for s in strokes for p in s]
    length = max(sum(math.dist(a, b) for a, b in zip(s, s[1:])) for s in strokes)
    return axis, min(along) - MARK_W / 2, max(along) + MARK_W / 2, length


_REACH = {kind: _reach(kind) for kind in _DRAWN}


def _mark(kind, s):
    if kind in _DRAWN:
        colour, strokes, _ = _DRAWN[kind]
        for points in strokes:
            _stroke(s, colour, points, MARK_W)
    elif kind == "warn":
        _stroke(s, AMBER, [(64, 30), (64, 74)], 14)
        pygame.draw.circle(s, AMBER, (64 * X4, 96 * X4), 8 * X4)
    elif kind == "time":
        _stroke(s, SOFT, [(44, 30), (84, 30), (64, 64), (84, 98), (44, 98), (64, 64)], 8, closed=True)
        pygame.draw.polygon(s, AMBER, [(52 * X4, 92 * X4), (76 * X4, 92 * X4), (64 * X4, 76 * X4)])
    else:
        _stroke(s, SOFT, [(74, 38), (46, 64), (74, 90)], 13)


def _icon(kind, disc=True, mark=True):
    def paint(s):
        if disc:
            pygame.draw.circle(s, _GROUNDS[kind], (64 * X4, 64 * X4), 60 * X4)
        if mark:
            _mark(kind, s)
    return _smooth((128, 128), _GROUNDS[kind] if disc else _DRAWN[kind][0], paint)


def icon(g, kind, rect, t):
    """A card's icon (done, no, warn, time, back) in the 128 px rect: it pops in, a tick or cross draws itself in,
    the hourglass keeps turning over."""
    s = fx.pop(t)
    alpha = 255 * min(1.0, (s - 0.2) / 0.8)
    box = pygame.Rect(0, 0, round(rect.w * s), round(rect.h * s))
    box.center = rect.center
    if kind not in _DRAWN:
        g.image(tex(g, kind, lambda: _icon(kind)), box, alpha, angle=fx.hourglass(t) if kind == "time" else 0)
        return
    g.image(tex(g, (kind, "disc"), lambda: _icon(kind, mark=False)), box, alpha)
    axis, first, last, length = _REACH[kind]
    shown = min(1.0, fx.draw_progress(t) * DASH / length)
    if shown <= 0:
        return
    n = min(128, math.ceil(first + (last - first) * shown))
    src = pygame.Rect(0, 0, n, 128) if axis == 0 else pygame.Rect(0, 0, 128, n)
    dst = (pygame.Rect(box.x, box.y, round(n * s), box.h) if axis == 0
           else pygame.Rect(box.x, box.y, box.w, round(n * s)))
    g.image(tex(g, (kind, "mark"), lambda: _icon(kind, disc=False)), dst, alpha, src=src)


def _ring():
    """The waiting ring: grey, its top quarter yellow (the mockup's border-top)."""
    def paint(s):
        c, outer, width = (64 * X4, 64 * X4), 64 * X4, 12 * X4
        pygame.draw.circle(s, TRACK, c, outer, width)
        arc = pygame.Surface(s.get_size(), pygame.SRCALPHA)
        wedge = [c] + [(c[0] + 2 * outer * math.cos(math.radians(a)), c[1] - 2 * outer * math.sin(math.radians(a)))
                       for a in range(45, 136, 5)]
        pygame.draw.polygon(arc, YELLOW, wedge)
        band = pygame.Surface(s.get_size(), pygame.SRCALPHA)
        pygame.draw.circle(band, (255, 255, 255, 255), c, outer, width)
        arc.blit(band, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        s.blit(arc, (0, 0))
    return _smooth((128, 128), TRACK, paint)


def ring(g, rect, t):
    """The waiting ring in the 128 px rect, turning once a second."""
    g.image(tex(g, "ring", _ring), rect, angle=fx.spin(t))


def _phone():
    """The phone glyph of the wait card: an outline with its home bar (the mockup's .phoneglyph)."""
    def paint(s):
        pygame.draw.rect(s, SOFT, (0, 0, 44 * X4, 54 * X4), width=4 * X4, border_radius=8 * X4)
        pygame.draw.rect(s, SOFT, (16 * X4, 42 * X4, 12 * X4, 4 * X4), border_radius=2 * X4)
    return _smooth((44, 54), SOFT, paint)


def phone(g, rect, t):
    """The phone glyph in its 44 x 54 rect, buzzing now and then."""
    g.image(tex(g, "phone", _phone), rect, angle=fx.buzz(t))


def _tick():
    return _smooth((12, 10), GREEN, lambda s: _stroke(s, GREEN, [(1.6, 5.2), (4.6, 8.2), (10.4, 1.8)], 2.6))


def tick(g, x, y, t=None):
    """The green tick of a done step, 12 x 10 at (x, y), popping in t ms after its state began (None: at rest)."""
    s = 1.0 if t is None else fx.tick_pop(t)
    r = pygame.Rect(0, 0, round(12 * s), round(10 * s))
    r.center = (x + 6, y + 5)
    g.image(tex(g, "tick", _tick), r, 255 * min(1.0, (s - 0.2) / 0.8))


# ---- the QR code and the progress bar ----------------------------------------------------------------------------

QUIET = 4                                 # light modules round a QR code, as the standard asks


def qr_surface(text):
    """A real QR code of text (qr.py), one pixel a module, with its quiet zone. Level M for a short text (the mock's
    code), L for a link: fewer, bigger modules, and nothing on a screen gets scratched. ValueError if it cannot fit."""
    modules = encode_qr(text, "M" if len(text.encode("utf-8")) <= 60 else "L")
    n = len(modules) + 2 * QUIET
    surf = pygame.Surface((n, n))
    surf.fill(WHITE)
    for y, row in enumerate(modules):
        for x, dark in enumerate(row):
            if dark:
                surf.set_at((x + QUIET, y + QUIET), INK)
    return surf


def _beam(w):
    """The scan beam: orange, clear at its edges and 0.55 opaque in its middle (the mockup's .beam gradient)."""
    surf = pygame.Surface((w, BEAM_H), pygame.SRCALPHA)
    for y in range(BEAM_H):
        pygame.draw.line(surf, (*ORANGE, round(140 * (1 - abs(2 * (y + 0.5) / BEAM_H - 1)))), (0, y), (w - 1, y))
    return surf


def qr(g, text, rect, t, beam=True):
    """The QR code of text, as large as whole pixels per module allow in rect (crisp, so a phone reads it), centred,
    a scan beam sweeping down it and back (beam=False: none, for a dense link scanned off the screen). Nothing for a
    text no QR code holds: the card still shows the code. Returns the code's box, or None."""
    try:
        surf = tex(g, ("qr", text), lambda: qr_surface(text), pixel_art=True)
    except ValueError:
        return None
    n = surf.get_rect().w
    size = n * max(1, rect.w // n)
    box = pygame.Rect(0, 0, size, size)
    box.center = rect.center
    g.image(surf, box)
    if not beam:
        return box
    y = box.y + round((box.h - BEAM_H) * fx.beam(t))
    g.image(tex(g, ("beam", box.w), lambda: _beam(box.w)), pygame.Rect(box.x, y, box.w, BEAM_H))
    return box


def _stripes(w, h):
    """The progress bar's fill: yellow and orange diagonal stripes, 17 px each across."""
    tile = pygame.Surface((STRIPE, h))
    for x in range(STRIPE):
        for y in range(h):
            tile.set_at((x, y), YELLOW if (x - y) % STRIPE < STRIPE // 2 else ORANGE)
    surf = pygame.Surface((w, h))
    for x in range(0, w, STRIPE):
        surf.blit(tile, (x, 0))
    return surf


def _ends(size, ground):
    """ground everywhere but a bar with round ends: laid over the stripes, it rounds their ends as the track's."""
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill((*ground, 255))
    pygame.draw.rect(surf, (0, 0, 0, 0), surf.get_rect(), border_radius=size[1] // 2)
    return surf


def progress(g, track, t, ground, k):
    """The load card's bar in track, k (0..1) full, its stripes running right. ground is the card's colour around
    it."""
    g.round_rect(track, TRACK, track.h // 2)
    w = round(track.w * k)
    if w > 0:                                                # one wide texture, read from a moving offset
        stripes = tex(g, ("stripes", track.w, track.h), lambda: _stripes(track.w + STRIPE, track.h))
        u = STRIPE - round(fx.stripes(t))
        g.image(stripes, pygame.Rect(track.x, track.y, w, track.h), src=pygame.Rect(u, 0, w, track.h))
    g.image(tex(g, ("ends", track.size, ground), lambda: _ends(track.size, ground)), track)


def _bar(size, colour):
    surf = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(surf, (*colour, 255), surf.get_rect(), border_radius=size[1] // 2)
    return surf


def meter(g, track, k, colour):
    """A bar k (0..1) full along track: one rounded bar in colour, cut short from the right, so a bar that shrinks
    every second needs no new texture."""
    w = round(track.w * k)
    if w > 0:
        bar = tex(g, ("meter", track.size, colour), lambda: _bar(track.size, colour))
        g.image(bar, pygame.Rect(track.x, track.y, w, track.h), src=pygame.Rect(0, 0, w, track.h))


# ---- the status dots, the coins, Home --------------------------------------------------------------------------

def dot(g, x, y, state, t):
    """A service's 9 px dot at (x, y): green when ready, amber and pulsing when busy, red and blinking when it is
    not answering."""
    r = pygame.Rect(x, y, 9, 9)
    if state == "busy":
        s = fx.pulse(t)
        size = round(9 * s)
        g.round_rect(r.inflate(size - 9, size - 9), YELLOW, size // 2, alpha=255 * (1 - 0.4 * (s - 1) / 0.7))
    elif state == "off":
        g.round_rect(r, RED, 4, alpha=255 if fx.blink(t) else 51)
    else:
        g.round_rect(r, GREEN, 4)


def coin(g, cx, cy):
    """A gold coin centred on (cx, cy): filled circles from its rim in to a highlight up and to the left (the
    mockup's radial gradient, in steps), and a "$"."""
    for r, colour, off in ((23, COIN_RIM, 0), (20, COIN_DARK, 0), (15, YELLOW, -2), (6, COIN_LIGHT, -6)):
        g.round_rect((cx + off - r, cy + off - r, 2 * r, 2 * r), colour, r)
    g.text("$", 18, cx, cy, weight="pixel", color=COIN_INK, anchor="center")


def _home(size):
    """Home, dimmed behind the sale toast: the mockup's orange-to-purple stand-in."""
    top_left, bottom_right = (240, 138, 36, 255), (107, 42, 143, 255)
    mid = tuple((a + b) // 2 for a, b in zip(top_left, bottom_right))
    corners = pygame.Surface((2, 2), pygame.SRCALPHA)
    for xy, c in (((0, 0), top_left), ((1, 0), mid), ((0, 1), mid), ((1, 1), bottom_right)):
        corners.set_at(xy, c)
    out = pygame.transform.smoothscale(corners, size)       # a 135 degree gradient, as the mockup's
    mask = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=10)
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return out


def home(g, rect, alpha=115):
    """Home behind the sale toast, dimmed."""
    g.image(tex(g, ("home", rect.size), lambda: _home(rect.size)), rect, alpha=alpha)
