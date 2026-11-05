"""PB on screen: a 40 x 40 pixel ghost with six moods, in a dungeon-crawler dialogue (portrait above the box, name tag,
words typing out, a blinking arrow when done). The sprite is drawn by code, the same way as the approved mockup
(Any% Coach Mascot.html), so there is no art file to keep in step with it."""
import pygame

from ..coach import MOODS, NAME
from . import theme
from .text import plain, wrap_rich

N = 40
BODY, SHADE, DEEP, HI = (0xD6, 0xF1, 0xFF), (0xA6, 0xD6, 0xF2), (0x7F, 0xB8, 0xDE), (0xFF, 0xFF, 0xFF)
LINE, BAND, BAND_D, CHEEK, EYE = (0x1F, 0x3A, 0x5C), (0xF0, 0x8A, 0x24), (0xB2, 0x5E, 0x10), (0xFF, 0x9F, 0xB6), (0x16, 0x20, 0x3A)
WHITE, TONGUE, STAR, SWEAT = (0xFF, 0xFF, 0xFF), (0xFF, 0x7A, 0x8A), (0xFF, 0xD3, 0x4D), (0x8F, 0xD0, 0xFF)
FRAME, FRAME_MID, NAME_COL = (0xE6, 0xEF, 0xFF), (0x4F, 0x6B, 0xB0), (0xFF, 0xB1, 0x5C)
PORTRAIT = pygame.Rect(30, 182, 132, 132)
BOX = pygame.Rect(24, 326, 752, 132)
TEXT_SIZE, LINE_H, PAD = 31, 34, 26
FACE = (20, 20)


def _body():
    g = [[None] * N for _ in range(N)]
    for y in range(N):
        for x in range(N):
            cx, cy = x + 0.5, y + 0.5
            inside = (cy <= 18 and (cx - 20) ** 2 + (cy - 18) ** 2 <= 13.6 ** 2) or (18 < cy <= 31 and 6.6 <= cx <= 33.4)
            if not inside and 31 < cy <= 36:
                inside = any((cx - c) ** 2 + (cy - 31) ** 2 <= 4.7 ** 2 for c in (11, 20, 29))
            if not inside:
                continue
            c = BODY
            if cx > 27 or cy > 29:
                c = SHADE
            if cx > 31 or cy > 33:
                c = DEEP
            if (cx - 13.5) ** 2 + (cy - 10.5) ** 2 <= 5:
                c = HI
            g[y][x] = c
    for x in range(7, 34):                                  # the runner's headband, its knot flying behind
        for y, c in ((9, BAND), (10, BAND), (11, BAND_D)):
            if g[y][x]:
                g[y][x] = c
    for x, y in ((34, 9), (35, 9), (36, 8), (37, 8), (34, 10), (35, 11), (36, 11), (37, 12)):
        g[y][x] = BAND
    return g


def _outline(g):
    out = [row[:] for row in g]
    for y in range(N):
        for x in range(N):
            if g[y][x] is None and any(0 <= y + dy < N and 0 <= x + dx < N and g[y + dy][x + dx] is not None
                                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                out[y][x] = LINE
    return out


def _face(g, mood, blink=False):
    fx, fy = FACE

    def put(x, y, c):
        if 0 <= x < N and 0 <= y < N:
            g[y][x] = c

    def eye(ex, side):
        p = lambda dx, dy, c: put(ex + dx, fy + dy, c)
        if blink and mood != "excited":                     # shut: a short line (star eyes never shut)
            p(0, 0, EYE)
            p(1, 0, EYE)
            return
        if mood == "happy":
            for dx, dy in ((-1, 0), (0, -1), (1, -1), (2, 0)):
                p(dx, dy, EYE)
            return
        if mood == "excited":
            for dx, dy in ((0, -2), (-1, -1), (1, -1), (0, 0), (-2, -1), (2, -1)):
                p(dx, dy, STAR)
            p(0, -1, WHITE)
            return
        for dy in range(-1, (2 if mood == "worried" else 3) - 1):
            p(0, dy, EYE)
            p(1, dy, EYE)
        p(1 if (mood == "thinking" and side > 0) else 0, -1, WHITE)
        if mood == "serious":                               # brows down towards the middle
            p(-1 if side > 0 else 2, -3, EYE); p(0, -3, EYE); p(1, -3, EYE); p(2 if side > 0 else -1, -2, EYE)
        if mood == "worried":                               # brows up towards the middle
            p(2 if side > 0 else -1, -3, EYE); p(0, -3, EYE); p(1, -3, EYE); p(-1 if side > 0 else 2, -2, EYE)
        if mood == "thinking" and side > 0:                 # one brow raised
            for dx, dy in ((-1, -3), (0, -4), (1, -4), (2, -3)):
                p(dx, dy, EYE)

    eye(fx - 5, -1)
    eye(fx + 4, 1)
    m = lambda dx, dy, c: put(fx + dx, fy + 4 + dy, c)
    if mood == "normal":
        for dx, dy in ((-2, 0), (-1, 1), (0, 1), (1, 1), (2, 0)):
            m(dx, dy, EYE)
    elif mood in ("happy", "excited"):
        w = 2 if mood == "happy" else 3
        for i in range(-w, w + 1):
            m(i, 0, EYE)
        m(-w, 1, EYE); m(w, 1, EYE)
        for i in range(-w + 1, w):
            m(i, 1, TONGUE); m(i, 2, EYE)
    elif mood == "thinking":
        m(1, 1, EYE); m(2, 1, EYE); m(3, 0, EYE)
    elif mood == "serious":
        for i in range(-2, 3):
            m(i, 1, EYE)
    elif mood == "worried":
        for dx, dy in ((-2, 1), (-1, 0), (0, 1), (1, 0), (2, 1)):
            m(dx, dy, EYE)
        for dx, dy in ((9, -3), (9, -2), (10, -2), (9, -1), (10, -1)):
            put(fx + dx, fy + dy, SWEAT)
    if mood in ("normal", "happy", "excited"):
        for dx in (-9, -8, 7, 8):
            put(fx + dx, fy + 3, CHEEK)


def sprite_surface(mood, blink=False):
    """PB in a mood (coach.MOODS), eyes shut when blink, as a 40 x 40 surface with a transparent background."""
    g = _outline(_body())
    _face(g, mood if mood in MOODS else "normal", blink)
    surf = pygame.Surface((N, N), pygame.SRCALPHA)
    for y in range(N):
        for x in range(N):
            if g[y][x] is not None:
                surf.set_at((x, y), (*g[y][x], 255))
    return surf


def face_texture(gfx, mood="happy"):
    """PB's sprite in a mood as a texture, made once for this gfx: Home's PB button, attract mode's board card."""
    cache = gfx.__dict__.setdefault("_pb_faces", {})
    if mood not in cache:
        cache[mood] = gfx.texture(sprite_surface(mood), pixel_art=True)
    return cache[mood]


def _gradient(size, top, bottom, radius):
    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)
    for y in range(h):
        k = y / max(1, h - 1)
        pygame.draw.line(surf, [round(a + (b - a) * k) for a, b in zip(top, bottom)] + [255], (0, y), (w - 1, y))
    mask = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return surf


class MascotView:
    def __init__(self, gfx):
        self.gfx = gfx
        self._sprites, self._tex = {}, {}
        self.shown = ""                         # the words on screen in the last frame drawn (for tests)

    def _sprite(self, mood, blink=False):
        key = (mood, blink and mood != "excited")
        if key not in self._sprites:
            self._sprites[key] = self.gfx.texture(sprite_surface(*key), pixel_art=True)
        return self._sprites[key]

    def _once(self, key, make):
        if key not in self._tex:
            self._tex[key] = self.gfx.texture(make())
        return self._tex[key]

    def _arrow(self):
        def make():
            s = pygame.Surface((16, 10), pygame.SRCALPHA)
            pygame.draw.polygon(s, (255, 255, 255, 255), [(0, 0), (15, 0), (7, 9)])
            return s
        return self._once("arrow", make)

    def draw(self, nav):
        if nav.mascot is None:
            self.shown = ""
            return
        self.draw_line(nav.mascot.mood, nav.mascot_text, nav.mascot_ms)

    def draw_line(self, mood, text, ms, bob=0.0, blink=False):
        """PB's portrait and box, `text` typing out `ms` after it started (None: PB is still thinking). *Emphasis*
        marks are not drawn: those words are in the name tag's amber. The handler moves the portrait: bob is its dy
        in px (it floats and hops), blink shuts PB's eyes."""
        self.shown = ""
        g = self.gfx
        portrait = PORTRAIT.move(0, round(bob))
        g.round_rect(portrait.inflate(12, 12), FRAME, 8)
        g.image(self._once("portrait", lambda: _gradient(PORTRAIT.size, (0x3A, 0x5A, 0x96), (0x1D, 0x2C, 0x52), 2)), portrait)
        g.image(self._sprite(mood, blink), portrait.inflate(-12, -12))
        g.round_rect(BOX.inflate(8, 8), FRAME, 12)
        g.round_rect(BOX.inflate(2, 2), FRAME_MID, 10)
        g.image(self._once("box", lambda: _gradient((BOX.w - 4, BOX.h - 4), (0x26, 0x38, 0x6A), (0x11, 0x1A, 0x36), 8)),
                BOX.inflate(-4, -4))
        tag = pygame.Rect(BOX.x + 156, BOX.y - 22, 130, 30)
        g.round_rect(tag, FRAME, 6)
        g.round_rect(tag.inflate(-6, -6), (0x26, 0x38, 0x6A), 4)
        g.text(NAME, 24, tag.centerx, tag.centery, weight="pixel", color=NAME_COL, anchor="center")
        if text is None:                        # the voice is still thinking
            g.text("." * (1 + ms // 300 % 3), TEXT_SIZE, BOX.x + PAD, BOX.y + 20, weight="pixel")
            return
        measure = lambda s: g.measure(s, TEXT_SIZE, "pixel")[0]
        n, shown = int(ms * theme.MASCOT_CPS / 1000), []
        for i, runs in enumerate(wrap_rich(text, BOX.w - 2 * PAD - 20, measure, max_lines=3)):
            line = "".join(t for t, _ in runs)
            k = max(0, min(len(line), n))
            n -= len(line) + 1
            if k == 0:
                break
            x, left = BOX.x + PAD, k
            for t, emph in runs:                # each run in its colour, the one still typing clipped
                if left <= 0:
                    break
                g.text(t, TEXT_SIZE, x, BOX.y + 20 + i * LINE_H, weight="pixel", color=NAME_COL if emph else WHITE,
                       clip_w=None if left >= len(t) else measure(t[:left]))
                x += measure(t)
                left -= len(t)
            shown.append(line[:k])
        self.shown = " ".join(shown)
        if self.shown == " ".join(plain(text).split()) and ms // 400 % 2 == 0:
            g.image(self._arrow(), pygame.Rect(BOX.right - 36, BOX.bottom - 26, 16, 10))
