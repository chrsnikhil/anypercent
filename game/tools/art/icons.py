"""Small sprites drawn in code, all in one fixed 16-colour palette (UI_PALETTE) so they share one hardware
sprite palette: the "!" bubble, the chai glass, target arrows, the A-prompt pill, energy meters, the HUD
strip and the ship bar."""
import os

from PIL import Image, ImageDraw, ImageFont

UI_PALETTE = [(248, 0, 248), (16, 16, 32), (64, 72, 104), (248, 248, 248), (232, 48, 64), (248, 208, 64),
              (120, 216, 120), (176, 240, 176), (40, 44, 72), (200, 120, 56), (216, 224, 232), (248, 160, 40),
              (120, 128, 160), (96, 32, 48), (32, 32, 56), (168, 176, 200)]
DARK, LINE, WHITE, RED, YELLOW, GREEN, SHINE, TROUGH, CHAI, GLASS, ORANGE, EDGE = (
    UI_PALETTE[i] + (255,) for i in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12))


def _frame(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def icons():
    """16 x 16: 0 bubble "!", 1 chai glass, 2 arrow down (over a target), 3 left, 4 right, 5 up (screen edge),
    6 laptop, 7 A button, 8 B button (the pitch's slide buttons)."""
    bubble = _frame(16, 16)
    d = ImageDraw.Draw(bubble)
    d.rounded_rectangle((2, 1, 13, 11), 3, fill=WHITE, outline=DARK)
    d.polygon([(6, 11), (9, 11), (7, 14)], fill=WHITE, outline=DARK)
    d.rectangle((7, 3, 8, 7), fill=RED)
    d.rectangle((7, 9, 8, 9), fill=RED)
    cup = _frame(16, 16)
    d = ImageDraw.Draw(cup)
    d.rectangle((6, 5, 9, 11), fill=GLASS)
    d.rectangle((6, 7, 9, 11), fill=CHAI)
    d.line((6, 5, 9, 5), fill=WHITE)
    arrows = []
    for points in ([(2, 3), (13, 3), (7, 13), (8, 13)],        # down
                   [(12, 2), (12, 13), (2, 7), (2, 8)],        # left
                   [(3, 2), (3, 13), (13, 7), (13, 8)],        # right
                   [(2, 12), (13, 12), (7, 2), (8, 2)]):       # up
        a = _frame(16, 16)
        ImageDraw.Draw(a).polygon(points, fill=YELLOW, outline=DARK)
        arrows.append(a)
    laptop = _frame(16, 16)
    d = ImageDraw.Draw(laptop)
    d.rectangle((3, 3, 12, 9), fill=EDGE, outline=DARK)
    d.rectangle((4, 4, 11, 8), fill=GLASS)
    d.rectangle((2, 10, 13, 12), fill=LINE, outline=DARK)
    button_a = _frame(16, 16)
    d = ImageDraw.Draw(button_a)
    d.ellipse((1, 1, 14, 14), fill=RED, outline=DARK)
    d.line((5, 12, 7, 4), fill=WHITE)
    d.line((8, 4, 10, 12), fill=WHITE)
    d.line((6, 9, 9, 9), fill=WHITE)
    button_b = _frame(16, 16)
    d = ImageDraw.Draw(button_b)
    d.ellipse((1, 1, 14, 14), fill=YELLOW, outline=DARK)
    d.line((5, 4, 5, 11), fill=DARK)
    d.rectangle((5, 4, 9, 7), outline=DARK)
    d.rectangle((5, 7, 10, 11), outline=DARK)
    return [bubble, cup] + arrows + [laptop, button_a, button_b]


def gate():
    """32 x 16: the hall's rope gate (two stanchions and a sagging red rope), shown until the World scan."""
    im = _frame(32, 16)
    d = ImageDraw.Draw(im)
    for x in (2, 28):
        d.rectangle((x, 3, x + 1, 14), fill=YELLOW)
        d.rectangle((x - 1, 13, x + 2, 14), fill=YELLOW)
    d.line([(3, 6), (9, 8), (16, 9), (22, 8), (28, 6)], fill=RED, width=2)
    return im


def pill():
    """64 x 32 (the GBA has no 64 x 16 sprite): the 16 px dark prompt pill in rows 8-23, with a red A button
    at its left; the words are sprite text on top."""
    im = _frame(64, 32)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 9, 63, 22), 6, fill=DARK, outline=WHITE)
    d.ellipse((2, 11, 10, 19), fill=RED)
    d.line((4, 17, 5, 13), fill=WHITE)
    d.line((7, 13, 8, 17), fill=WHITE)
    d.line((5, 16, 7, 16), fill=WHITE)
    return im


def meter():
    """12 frames of 32 x 8: a 22 px energy bar; frame k fills 2k px, green above half, yellow above a fifth."""
    frames = []
    for k in range(12):
        im = _frame(32, 8)
        d = ImageDraw.Draw(im)
        d.rectangle((4, 2, 27, 6), fill=DARK)
        fill = 2 * k
        colour = GREEN if fill > 11 else YELLOW if fill > 4 else RED
        if fill:
            d.rectangle((5, 3, 4 + fill, 5), fill=colour)
        frames.append(im)
    return frames


def hud_strip():
    """64 x 32: the HUD background. Rows 0-7 are clear, row 8 is the top line, rows 9-31 are dark."""
    im = _frame(64, 32)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 8, 63, 31), fill=DARK)
    d.line((0, 8, 63, 8), fill=LINE)
    return im


def hud_bar():
    """9 frames of 8 x 8: frame k has k columns filled. Eight side by side make the 64 px bar."""
    frames = []
    for k in range(9):
        im = _frame(8, 8)
        d = ImageDraw.Draw(im)
        d.rectangle((0, 1, 7, 6), fill=TROUGH)
        if k:
            d.rectangle((0, 1, k - 1, 6), fill=GREEN)
            d.line((0, 1, k - 1, 1), fill=SHINE)
        frames.append(im)
    return frames


PURPLE, EYE = UI_PALETTE[13] + (255,), RED
RAIN = UI_PALETTE[15] + (255,)


def bug():
    """16 x 16 x 3: a green-and-purple glitch bug with a red eye; frames 0-1 crawl, 2 is squashed."""
    frames = []
    for k in range(3):
        im = _frame(16, 16)
        d = ImageDraw.Draw(im)
        if k < 2:
            d.ellipse((4, 5, 11, 12), fill=GREEN, outline=DARK)
            d.rectangle((6, 6, 9, 11), fill=PURPLE)
            d.point((9, 7), fill=EYE)
            for leg, dx in ((6, -1 if k else 1), (9, 1 if k else -1)):
                d.line((leg, 12, leg + dx, 14), fill=DARK)
                d.line((leg, 5, leg - dx, 3), fill=DARK)
        else:
            d.ellipse((3, 10, 12, 13), fill=GREEN, outline=DARK)
            d.line((5, 11, 10, 11), fill=PURPLE)
        frames.append(im)
    return frames


def spark():
    """16 x 16 x 2: router sparks."""
    frames = []
    for pts in (((8, 2), (6, 7), (9, 7), (7, 13)), ((4, 4), (8, 8), (11, 5), (9, 12))):
        im = _frame(16, 16)
        d = ImageDraw.Draw(im)
        d.line(pts, fill=YELLOW, width=2)
        d.point((pts[0][0] + 1, pts[0][1]), fill=WHITE)
        frames.append(im)
    return frames


def pizza():
    """32 x 32: a pizza box with steam, at the door."""
    im = _frame(32, 32)
    d = ImageDraw.Draw(im)
    d.polygon([(4, 20), (16, 14), (28, 20), (16, 26)], fill=CHAI, outline=DARK)       # lid
    d.polygon([(4, 20), (16, 26), (16, 29), (4, 23)], fill=ORANGE, outline=DARK)      # front
    d.polygon([(16, 26), (28, 20), (28, 23), (16, 29)], fill=CHAI, outline=DARK)
    d.ellipse((13, 18, 19, 21), fill=RED)
    for x in (11, 16, 21):
        d.arc((x - 2, 4, x + 2, 12), 90, 270, fill=WHITE)
    return im


def rain():
    """16 x 32 x 3: rain streaks for a window, shifting down each frame."""
    frames = []
    for k in range(3):
        im = _frame(16, 32)
        d = ImageDraw.Draw(im)
        for x, y in ((2, 3), (6, 14), (10, 7), (13, 20), (4, 25)):
            yy = (y + 7 * k) % 28
            d.line((x, yy, x - 1, yy + 3), fill=RAIN)
        frames.append(im)
    return frames


FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "launcher", "arca_launcher", "assets",
                    "fonts", "Outfit-Bold.ttf")


def card():
    """64 x 32 x 9: the results card as a 9-slice (TL, T, TR, L, C, R, BL, B, BR), dark with a 2 px border."""
    frames = []
    for row in range(3):
        for col in range(3):
            im = _frame(64, 32)
            d = ImageDraw.Draw(im)
            d.rectangle((0, 0, 63, 31), fill=DARK)
            if row == 0:
                d.rectangle((0, 0, 63, 1), fill=LINE)
            if row == 2:
                d.rectangle((0, 30, 63, 31), fill=LINE)
            if col == 0:
                d.rectangle((0, 0, 1, 31), fill=LINE)
            if col == 2:
                d.rectangle((62, 0, 63, 31), fill=LINE)
            for cx, cy in ((0, 0), (63, 0), (0, 31), (63, 31)):         # round the card's outer corners
                if (cx == 0) == (col == 0) and (cy == 0) == (row == 0) and (col != 1) and (row != 1):
                    for k in range(3):
                        im.putpixel((abs(cx - k), cy), (0, 0, 0, 0))
                        im.putpixel((cx, abs(cy - k)), (0, 0, 0, 0))
            frames.append(im)
    return frames


def confetti():
    """8 x 8 x 4: confetti pieces in four colours (frames 1 and 3 turned a quarter)."""
    frames = []
    for k, colour in enumerate((RED, YELLOW, GREEN, ORANGE)):
        im = _frame(8, 8)
        box = (2, 3, 5, 4) if k % 2 == 0 else (3, 2, 4, 5)
        ImageDraw.Draw(im).rectangle(box, fill=colour)
        frames.append(im)
    return frames


def flash():
    """64 x 32: the stage screen's white flash on a correct slide."""
    im = _frame(64, 32)
    ImageDraw.Draw(im).rectangle((0, 0, 63, 31), fill=WHITE)
    return im


def spot():
    """64 x 32: the spotlight pool under the pitching player (drawn half transparent)."""
    im = _frame(64, 32)
    ImageDraw.Draw(im).ellipse((4, 8, 59, 27), fill=SHINE)
    return im


def grades():
    """32 x 32 x 5: the grade letters S A B C F, outlined."""
    font = ImageFont.truetype(FONT, 30)
    frames = []
    for letter, colour in (("S", YELLOW), ("A", GREEN), ("B", EDGE), ("C", GLASS), ("F", RED)):
        im = _frame(32, 32)
        d = ImageDraw.Draw(im)
        d.fontmode = "1"                                            # no antialiasing: palette colours only
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            d.text((16 + dx, 16 + dy), letter, font=font, fill=DARK, anchor="mm")
        d.text((16, 16), letter, font=font, fill=colour, anchor="mm")
        frames.append(im)
    return frames
