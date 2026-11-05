"""RUSH HOUR, web3 edition: the cast redrawn in the shared Any% look (the bull from Rebound, bears for the bear
market, USDC to collect). Pixel art drawn in code at the sprites' real sizes; build_art.py uses these.

  bull_frames()   24 x 24: the hero, a bull in RUSH HOUR's saffron hoodie (idle, run, jump, fall, out)
  bear_frames()   24 x 24: the walking enemy, a red bear (two steps, stomped flat)
  usdc_frames()   16 x 16: the pickup, a USDC coin turning (4 frames)
  usdc_icon()     16 x 16: the HUD's coin counter icon

  python web3.py OUT.png     a preview sheet at 6x"""
import sys

from PIL import Image, ImageDraw

OUT = (40, 20, 12)                                      # outline
HIDE, HIDE_D = (176, 96, 40), (128, 64, 26)             # the bull's brown, and its shade
CREAM, HORN = (250, 232, 196), (238, 226, 200)
HOOD, HOOD_D, HOOD_L = (255, 150, 40), (204, 100, 20), (255, 196, 110)   # RUSH HOUR's saffron hoodie
JEANS, SHOE = (48, 64, 120), (32, 32, 40)
BEAR, BEAR_D, BEAR_L, BEAR_OUT = (196, 52, 44), (140, 32, 30), (236, 112, 96), (52, 14, 14)
USDC, USDC_D, USDC_L, WHITE = (39, 117, 202), (16, 60, 130), (120, 180, 240), (255, 255, 255)


def blank(w=24, h=24):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def _p(d, pts, c):
    for x, y in pts:
        d.point((x, y), fill=c + (255,))


def _r(d, x0, y0, x1, y1, c):
    d.rectangle((x0, y0, x1, y1), fill=c + (255,))


def _outline(im):
    """A 1 px dark outline round everything drawn (the cast's pixel-art edge)."""
    src = im.copy()
    a = src.load()
    out = im.load()
    for y in range(im.height):
        for x in range(im.width):
            if a[x, y][3]:
                continue
            if any(0 <= x + dx < im.width and 0 <= y + dy < im.height and a[x + dy * 0 + dx, y + dy][3]
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                out[x, y] = OUT + (255,)
    return im


def _bull_head(d, x, y):
    """The head, its top-left at (x, y): 12 wide, horns out to the sides."""
    d.ellipse((x, y + 2, x + 11, y + 11), fill=HIDE + (255,))
    _r(d, x + 2, y + 1, x + 9, y + 3, HIDE)                                   # brow
    for side in (-1, 1):                                                      # horns: 2 px thick, curving up
        cx = x + (0 if side < 0 else 11)
        _p(d, [(cx + side * a, y + b) for a, b in ((0, 3), (1, 3), (1, 2), (2, 2), (2, 1), (3, 1), (3, 0))], HORN)
    d.ellipse((x + 2, y + 7, x + 9, y + 11), fill=CREAM + (255,))            # muzzle
    _p(d, [(x + 4, y + 9), (x + 7, y + 9)], OUT)                              # nostrils
    _p(d, [(x + 3, y + 5), (x + 8, y + 5)], OUT)                              # eyes
    _p(d, [(x + 3, y + 4), (x + 8, y + 4)], WHITE)                            # their shine
    _r(d, x + 1, y + 6, x + 1, y + 7, HIDE_D)
    _r(d, x + 10, y + 6, x + 10, y + 7, HIDE_D)


def _bull_body(d, x, y, legs):
    """Hoodie torso from (x, y), then legs: legs is a list of (dx, length) leg offsets under the hips."""
    _r(d, x, y, x + 9, y + 6, HOOD)                                           # hoodie
    _r(d, x, y + 6, x + 9, y + 6, HOOD_D)                                     # its hem
    _r(d, x + 4, y + 1, x + 5, y + 4, HOOD_L)                                 # zip and strings
    _r(d, x - 2, y + 1, x - 1, y + 5, HOOD)                                   # arms in the sleeves
    _r(d, x + 10, y + 1, x + 11, y + 5, HOOD)
    _p(d, [(x - 2, y + 6), (x + 11, y + 6)], HIDE)                            # hooves for hands
    for dx, n in legs:
        _r(d, x + dx, y + 7, x + dx + 2, y + 7 + n, JEANS)
        _r(d, x + dx, y + 8 + n, x + dx + 3, y + 8 + n, SHOE)


def bull_frames():
    """idle, run, jump, fall, out (upside down), each 24 x 24, feet on the bottom row like the old hero."""
    frames = []
    for legs, dy in (([(1, 3), (6, 3)], 0),                  # idle: standing, shoes on the bottom row
                     ([(-1, 2), (8, 3)], 0),                 # run: stride
                     ([(1, 2), (6, 2)], 0),                  # jump: knees up
                     ([(0, 3), (7, 2)], 0)):                 # fall: legs reaching
        im = blank()
        d = ImageDraw.Draw(im)
        _bull_head(d, 6, 1 + dy)
        _bull_body(d, 7, 12 + dy, legs)
        frames.append(_outline(im))
    frames.append(frames[0].transpose(Image.FLIP_TOP_BOTTOM))
    return frames


def bear_frames():
    """Two walking steps and the stomped flat frame, 24 x 24, the bear facing left (the old bug's way)."""
    frames = []
    for step in (0, 1):
        im = blank()
        d = ImageDraw.Draw(im)
        d.ellipse((5, 9, 21, 20), fill=BEAR + (255,))                         # body
        d.ellipse((1, 6, 11, 15), fill=BEAR + (255,))                         # head
        d.ellipse((2, 4, 5, 7), fill=BEAR + (255,))                           # ears
        d.ellipse((7, 4, 10, 7), fill=BEAR + (255,))
        _p(d, [(3, 5), (8, 5)], BEAR_D)
        d.ellipse((0, 10, 5, 14), fill=BEAR_L + (255,))                       # snout
        _p(d, [(0, 11)], BEAR_OUT)                                            # nose
        _p(d, [(4, 9)], BEAR_OUT)                                             # eye, a little cross
        _p(d, [(5, 8), (5, 10)], BEAR_D)
        _r(d, 10, 11, 18, 12, BEAR_L)                                         # the light along its back
        a, b = (7, 15) if step == 0 else (9, 13)
        for lx in (a, b, 17 if step == 0 else 19):                            # legs mid-step
            _r(d, lx, 19, lx + 2, 22, BEAR_D)
        frames.append(_outline(im))
    flat = frames[0].resize((24, 9), Image.NEAREST)
    s = blank()
    s.alpha_composite(flat, (0, 14))
    frames.append(s)
    return frames


def _coin(w):
    """A USDC coin seen from the side as it turns: w is its width on screen (12 face on, down to 2 edge on)."""
    im = blank(16, 16)
    d = ImageDraw.Draw(im)
    x0 = 8 - w // 2
    d.ellipse((x0, 2, x0 + w - 1, 13), fill=USDC + (255,), outline=USDC_D + (255,))
    if w >= 8:                                                                # the face: "$" and the logo's arcs
        cx = x0 + w // 2
        _p(d, [(cx, 4), (cx, 11)], WHITE)                                     # the stem out of the "$"
        _p(d, [(cx - 1, 5), (cx, 5), (cx + 1, 5), (cx - 1, 6), (cx - 1, 7), (cx, 7), (cx + 1, 7),
               (cx + 1, 8), (cx + 1, 9), (cx, 9), (cx - 1, 9), (cx, 6), (cx, 8), (cx, 10)], WHITE)
        if w >= 12:
            _p(d, [(x0 + 2, 6), (x0 + 2, 7), (x0 + 2, 8), (x0 + 2, 9), (x0 + 3, 5), (x0 + 3, 10)], WHITE)
            _p(d, [(x0 + w - 3, 6), (x0 + w - 3, 7), (x0 + w - 3, 8), (x0 + w - 3, 9), (x0 + w - 4, 5),
                   (x0 + w - 4, 10)], WHITE)
        _p(d, [(x0 + 2, 3)], USDC_L)                                          # a glint
    else:
        _r(d, x0, 3, x0 + w - 1, 12, USDC_L if w <= 3 else USDC)
    return im


def usdc_frames():
    return [_coin(12), _coin(8), _coin(3), _coin(8)]


def usdc_icon():
    return _coin(12)


def preview(path):
    rows = [bull_frames(), bear_frames(), usdc_frames()]
    S = 6
    w = max(sum(f.width * S + 8 for f in r) for r in rows)
    h = sum(max(f.height for f in r) * S + 8 for r in rows)
    sheet = Image.new("RGB", (w, h), (88, 140, 220))                         # RUSH HOUR's sky behind them
    y = 0
    for r in rows:
        x = 0
        for f in r:
            sheet.paste(f.resize((f.width * S, f.height * S), Image.NEAREST), (x, y), f.resize((f.width * S, f.height * S), Image.NEAREST))
            x += f.width * S + 8
        y += max(f.height for f in r) * S + 8
    sheet.save(path)


if __name__ == "__main__":
    preview(sys.argv[1])
