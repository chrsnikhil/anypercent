"""Start-up splash ("boot drop", approved option B): the wordmark slides down from above the screen,
settles, a shine sweeps across it, the tagline fades in, then the whole card fades into Home.
Any button skips straight to the fade. The game art loads behind it."""
import pygame

from .. import NAME
from . import theme

DROP_MS = 700
SHINE_START, SHINE_MS = 750, 450
TAG_START, TAG_MS = 900, 400
FADE_START, TOTAL_MS = 1900, 2200

WORD_SIZE = 110
WORD_SPACING = 0.12            # of the font size, like the mockup's letter-spacing
TAGLINE = "VERIFIABLE SPEEDRUNS"
TAG_SIZE = 14
TAG_SPACING = 0.42
SHINE = (159, 211, 255)
# the shine is drawn as three vertical strips of a tinted copy of the wordmark: (offset, width, strength)
SHINE_STRIPS = ((-26, 14, 0.45), (-12, 24, 1.0), (12, 14, 0.45))


def ease_out_cubic(x):
    return 1 - (1 - x) ** 3


class SplashTimeline:
    """Where the splash is, in milliseconds. Pure: no drawing."""

    def __init__(self):
        self.t = 0.0

    def update(self, dt_ms):
        self.t += dt_ms

    def skip(self):
        self.t = max(self.t, FADE_START)

    @property
    def drop(self):
        return ease_out_cubic(min(1.0, self.t / DROP_MS))

    @property
    def shine(self):
        x = (self.t - SHINE_START) / SHINE_MS
        return x if 0 <= x < 1 else None

    @property
    def tagline_alpha(self):
        return round(255 * min(1.0, max(0.0, (self.t - TAG_START) / TAG_MS)))

    @property
    def alpha(self):
        return round(255 * min(1.0, max(0.0, 1 - (self.t - FADE_START) / (TOTAL_MS - FADE_START))))

    @property
    def fading(self):
        return self.t >= FADE_START

    @property
    def done(self):
        return self.t >= TOTAL_MS


def spaced(font, text, color, spacing):
    """Text with extra letter spacing (pygame fonts have none)."""
    glyphs = [font.render(ch, True, color) for ch in text]
    w = sum(g.get_width() for g in glyphs) + spacing * (len(glyphs) - 1)
    out = pygame.Surface((max(1, round(w)), font.get_height()), pygame.SRCALPHA)
    x = 0.0
    for g in glyphs:
        out.blit(g, (round(x), 0))
        x += g.get_width() + spacing
    return out


class SplashView:
    def __init__(self, gfx):
        self.gfx = gfx
        self._tex = None

    def _textures(self):
        if self._tex is None:
            word_font = self.gfx.font(WORD_SIZE, "bold")
            tag_font = self.gfx.font(TAG_SIZE, "semibold")
            self._tex = (self.gfx.texture(spaced(word_font, NAME.upper(), theme.WHITE, WORD_SIZE * WORD_SPACING)),
                         self.gfx.texture(spaced(word_font, NAME.upper(), SHINE, WORD_SIZE * WORD_SPACING)),
                         self.gfx.texture(spaced(tag_font, TAGLINE, (200, 204, 214), TAG_SIZE * TAG_SPACING)))
        return self._tex

    def draw(self, timeline):
        g = self.gfx
        word, shine, tag = self._textures()
        a = timeline.alpha
        g.round_rect((0, 0, theme.W, theme.H), theme.BG, 0, alpha=a)
        wr = word.get_rect()
        final_y = theme.H // 2 - wr.h // 2 - 20
        wr.centerx = theme.W // 2
        wr.y = round(-wr.h + (final_y + wr.h) * timeline.drop)
        g.image(word, wr, a)
        if timeline.shine is not None:
            cx = wr.x - 40 + (wr.w + 80) * timeline.shine
            for offset, width, strength in SHINE_STRIPS:
                x0 = max(wr.left, round(cx + offset))
                x1 = min(wr.right, round(cx + offset + width))
                if x1 > x0:
                    src = pygame.Rect(x0 - wr.x, 0, x1 - x0, wr.h)
                    g.image(shine, pygame.Rect(x0, wr.y, x1 - x0, wr.h), a * strength, src=src)
        tr = tag.get_rect(midtop=(theme.W // 2, final_y + wr.h + 14))
        g.image(tag, tr, a * timeline.tagline_alpha / 255)
