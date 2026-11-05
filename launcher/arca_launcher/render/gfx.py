"""Drawing on the GPU renderer: text, rounded shapes and images, all cached as textures."""
import os
from contextlib import contextmanager

import pygame
from pygame._sdl2.video import Texture

from . import theme

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")
FONT_FILES = {"regular": "Outfit-Regular.ttf", "semibold": "Outfit-SemiBold.ttf", "bold": "Outfit-Bold.ttf",
              "pixel": "Jersey10-Regular.ttf"}                 # PB's dialogue: clear pixel digits
CACHE_LIMIT = 400


@contextmanager
def scale_quality(mode):
    """SDL fixes a texture's scaling filter when the texture is created: 'nearest' keeps
    pixel art sharp, 'linear' keeps text and blurred backgrounds smooth."""
    old = os.environ.get("SDL_RENDER_SCALE_QUALITY")
    os.environ["SDL_RENDER_SCALE_QUALITY"] = mode
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("SDL_RENDER_SCALE_QUALITY", None)
        else:
            os.environ["SDL_RENDER_SCALE_QUALITY"] = old


class Gfx:
    def __init__(self, renderer):
        self.r = renderer
        self._fonts = {}
        self._text = {}
        self._shapes = {}
        self._dx = self._dy = 0
        self._fade = 1.0

    def texture(self, surface, pixel_art=False):
        with scale_quality("nearest" if pixel_art else "linear"):
            return Texture.from_surface(self.r, surface)

    def font(self, size, weight="regular"):
        key = (size, weight)
        if key not in self._fonts:
            path = os.path.join(FONT_DIR, FONT_FILES[weight])
            self._fonts[key] = pygame.font.Font(path if os.path.exists(path) else None, size)
        return self._fonts[key]

    def measure(self, s, size, weight="regular"):
        return self.font(size, weight).size(s)

    def fill(self, color):
        self.r.draw_color = (*color, 255)
        self.r.clear()

    @contextmanager
    def moved(self, dx=0, dy=0, alpha=255):
        """Everything drawn inside lands (dx, dy) away and alpha/255 as opaque, on top of any move around it: a card
        sliding in, rows fading up. Touch targets are not moved."""
        old = self._dx, self._dy, self._fade
        self._dx, self._dy, self._fade = old[0] + dx, old[1] + dy, old[2] * alpha / 255
        try:
            yield
        finally:
            self._dx, self._dy, self._fade = old

    def image(self, tex, rect, alpha=255, src=None, angle=0.0):
        """angle: turned clockwise about its centre, in degrees."""
        rect = pygame.Rect(rect)
        if self._dx or self._dy:
            rect.move_ip(round(self._dx), round(self._dy))
        tex.alpha = max(0, min(255, int(alpha * self._fade)))
        if angle:
            tex.draw(srcrect=src, dstrect=rect, angle=angle)
        else:
            tex.draw(srcrect=src, dstrect=rect)

    def text_texture(self, s, size, weight="regular", color=theme.WHITE):
        """The texture of s as text() draws it, made once."""
        key = (s, size, weight, color)
        tex = self._text.get(key)
        if tex is None:
            if len(self._text) > CACHE_LIMIT:
                self._text.clear()
            tex = self._text[key] = self.texture(self.font(size, weight).render(s, True, color))
        return tex

    def text(self, s, size, x, y, weight="regular", color=theme.WHITE, alpha=255, anchor="topleft", clip_w=None):
        """clip_w: draw only the left clip_w pixels (words typing out), from the same cached texture."""
        if not s:
            return pygame.Rect(round(x), round(y), 0, 0)
        tex = self.text_texture(s, size, weight, color)
        rect = tex.get_rect()
        setattr(rect, anchor, (round(x), round(y)))
        if clip_w is None:
            self.image(tex, rect, alpha)
        elif clip_w > 0:
            w = min(rect.w, int(clip_w))
            self.image(tex, pygame.Rect(rect.x, rect.y, w, rect.h), alpha, src=pygame.Rect(0, 0, w, rect.h))
        return rect

    def line(self, a, b, color):
        self.r.draw_color = (*color, 255)
        dx, dy = round(self._dx), round(self._dy)
        self.r.draw_line((a[0] + dx, a[1] + dy), (b[0] + dx, b[1] + dy))

    def pad_glyph(self, name, size, color=theme.WHITE):
        """A DualSense face button's symbol, "cross", "circle", "square" or "triangle", size px square, made once."""
        key = ("pad", name, size, color)
        tex = self._shapes.get(key)
        if tex is None:
            k = 4                                          # drawn 4x and scaled down: smooth edges
            s = size * k
            surf = pygame.Surface((s, s), pygame.SRCALPHA)
            ink, clear, w = (*color, 255), (0, 0, 0, 0), s * 0.15     # draw writes, never blends: clear cuts holes
            if name == "cross":
                for a, b in (((0, 0), (s, s)), ((s, 0), (0, s))):
                    d = pygame.Vector2(b) - pygame.Vector2(a)
                    n = pygame.Vector2(-d.y, d.x).normalize() * w / 2
                    a, b = pygame.Vector2(a) + d * 0.12, pygame.Vector2(a) + d * 0.88
                    pygame.draw.polygon(surf, ink, [a + n, b + n, b - n, a - n])
            elif name == "circle":
                pygame.draw.circle(surf, ink, (s / 2, s / 2), s * 0.46)
                pygame.draw.circle(surf, clear, (s / 2, s / 2), s * 0.46 - w)
            elif name == "square":
                pygame.draw.rect(surf, ink, (s * 0.08, s * 0.08, s * 0.84, s * 0.84))
                pygame.draw.rect(surf, clear, (s * 0.08 + w, s * 0.08 + w, s * 0.84 - 2 * w, s * 0.84 - 2 * w))
            else:                                          # triangle, point up, its centroid at the centre
                c, r = pygame.Vector2(s / 2, s * 0.56), s * 0.5
                pts = [c + pygame.Vector2(0, -r).rotate(120 * i) for i in range(3)]
                pygame.draw.polygon(surf, ink, pts)
                inner = (r / 2 - w) / (r / 2)              # the inradius is r/2: inset every side by w
                pygame.draw.polygon(surf, clear, [c + (p - c) * inner for p in pts])
            tex = self._shapes[key] = self.texture(pygame.transform.smoothscale(surf, (size, size)))
        return tex

    def round_rect(self, rect, color, radius, alpha=255, width=0, angle=0.0):
        rect = pygame.Rect(rect)
        if rect.w <= 0 or rect.h <= 0:
            return rect
        key = (rect.size, color, radius, width)
        tex = self._shapes.get(key)
        if tex is None:
            if len(self._shapes) > CACHE_LIMIT:
                self._shapes.clear()
            surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(surf, (*color, 255), surf.get_rect(), width=width, border_radius=radius)
            tex = self._shapes[key] = self.texture(surf)
        self.image(tex, rect, alpha, angle=angle)
        return rect
