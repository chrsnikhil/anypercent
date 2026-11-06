"""Design mockups for a proper 2048 reskin, drawn at the Game Boy Color's 160 x 144 and within its limits
(8 x 8 tiles, 8 background palettes of 4 colours, sprites for text), so whichever is picked can be built.

  A  "Ethereum"     a dark board, tiles climbing Ethereum's colours from pale lilac to deep purple and a gold
                    2048, each with the ETH diamond; title is a big pixel ETH diamond
  B  "Token ladder" each value is a different token: 2 USDC, 4 ETH, 8 LINK, 16 World, 32 Arkiv, 64 ETHGlobal,
                    then ETH tiers to a gold 2048

  python mockups.py OUT.png"""
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 160, 144
FONT = "C:/Windows/Fonts/arialbd.ttf"

NAVY, BOARD, EMPTY = (20, 22, 43), (28, 31, 58), (40, 44, 80)
WHITE, INK = (255, 255, 255), (28, 29, 51)

# values in pairs share a palette (the GBC has 8): pair = (board, light bg, dark bg, text)
ETH_RAMP = {
    2: ((236, 239, 255), INK), 4: ((192, 203, 246), INK),
    8: ((138, 146, 178), WHITE), 16: ((98, 126, 234), WHITE),
    32: ((69, 74, 117), WHITE), 64: ((123, 63, 228), WHITE),
    128: ((159, 107, 255), WHITE), 256: ((92, 46, 180), WHITE),
    512: ((60, 30, 130), WHITE), 1024: ((40, 20, 90), (255, 214, 102)),
    2048: ((255, 200, 60), INK), 4096: ((255, 140, 40), INK),
}

BOARD_DEMO = [[2, 4, 8, 16], [2048, 1024, 512, 32], [256, 128, 64, 0], [0, 4, 2, 0]]


def font(size):
    return ImageFont.truetype(FONT, size)


def crisp_text(d, xy, text, size, fill, anchor="mm"):
    """Text without antialiasing: drawn as a 1-bit mask, the way it would be as tiles."""
    f = font(size)
    l, t, r, b = d.textbbox((0, 0), text, font=f, anchor=anchor)
    m = Image.new("1", (r - l + 2, b - t + 2), 0)
    ImageDraw.Draw(m).text((-l + 1, -t + 1), text, font=f, fill=1, anchor=anchor)
    d.bitmap((xy[0] + l - 1, xy[1] + t - 1), m, fill=fill)


def diamond(d, cx, top, h, light, dark, outline=None):
    """The ETH logo, h px tall: two-tone diamond and chevron."""
    w = h * 0.6
    A, L, R, B, C = (cx, top), (cx - w / 2, top + h * 0.56), (cx + w / 2, top + h * 0.56), (cx, top + h * 0.74), \
        (cx, top + h * 0.42)
    d.polygon([A, L, C], fill=light)
    d.polygon([A, R, C], fill=dark)
    d.polygon([L, B, C], fill=dark)
    d.polygon([R, B, C], fill=light)
    L2, R2, B2, D = (cx - w / 2, top + h * 0.64), (cx + w / 2, top + h * 0.64), (cx, top + h * 0.82), (cx, top + h)
    d.polygon([L2, B2, D], fill=light)
    d.polygon([R2, B2, D], fill=dark)
    if outline:
        d.line([A, L, B, R, A], fill=outline)
        d.line([L2, D, R2, B2, L2], fill=outline)


def shade(c, k):
    return tuple(max(0, min(255, round(v * k))) for v in c)


def board_frame(img, d):
    d.rectangle((0, 0, W, H), fill=NAVY)
    d.rounded_rectangle((14, 2, 146, 134), 6, fill=BOARD)
    for r in range(4):
        for c in range(4):
            x, y = 17 + c * 32, 5 + r * 32
            d.rounded_rectangle((x, y, x + 29, y + 29), 4, fill=EMPTY)
    d.rectangle((0, 136, W, H), fill=(14, 15, 30))
    crisp_text(d, (4, 140), "Ξ", 9, (138, 146, 178), "lm")
    crisp_text(d, (12, 140), "001536", 8, WHITE, "lm")
    crisp_text(d, (156, 140), "BEST 002048", 8, (138, 146, 178), "rm")


def tile_eth(d, x, y, v):
    bg, fg = ETH_RAMP[v]
    d.rounded_rectangle((x, y, x + 29, y + 29), 4, fill=bg)
    d.rounded_rectangle((x, y + 26, x + 29, y + 29), 3, fill=shade(bg, 0.78))       # a bevel along the bottom
    d.rectangle((x + 1, y + 25, x + 28, y + 26), fill=bg)
    if v == 2048:
        diamond(d, x + 15, y + 2, 25, (255, 240, 170), (200, 130, 20), INK)
        crisp_text(d, (x + 15, y + 22), "2048", 9, INK)
        return
    diamond(d, x + 6, y + 3, 9, shade(fg, 1.0) if fg == WHITE else shade(bg, 0.55), shade(bg, 0.7) if fg == WHITE
            else shade(bg, 0.4))
    size = 15 if v < 100 else 11 if v < 1000 else 9
    crisp_text(d, (x + 16, y + 17), str(v), size, fg)


def coin(d, cx, cy, r, fill, rim):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=rim)
    d.ellipse((cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1), fill=fill)


def tile_token(d, x, y, v):
    """Each value is a token: logo big, value small in the corner."""
    cx, cy = x + 15, y + 13
    if v == 2:                                                       # USDC
        d.rounded_rectangle((x, y, x + 29, y + 29), 4, fill=(232, 240, 255))
        coin(d, cx, cy, 10, (39, 117, 202), (20, 70, 140))
        d.arc((cx - 7, cy - 7, cx + 7, cy + 7), 120, 240, fill=WHITE)
        d.arc((cx - 7, cy - 7, cx + 7, cy + 7), -60, 60, fill=WHITE)
        crisp_text(d, (cx, cy), "$", 11, WHITE)
    elif v == 4:                                                     # ETH
        d.rounded_rectangle((x, y, x + 29, y + 29), 4, fill=(192, 203, 246))
        diamond(d, cx, y + 2, 21, (98, 126, 234), (69, 74, 117))
    elif v == 8:                                                     # Chainlink
        d.rounded_rectangle((x, y, x + 29, y + 29), 4, fill=(220, 228, 255))
        pts = [(cx, cy - 10), (cx + 9, cy - 5), (cx + 9, cy + 5), (cx, cy + 10), (cx - 9, cy + 5), (cx - 9, cy - 5)]
        d.polygon(pts, fill=(55, 91, 210))
        inner = [(cx, cy - 5), (cx + 4, cy - 2.5), (cx + 4, cy + 2.5), (cx, cy + 5), (cx - 4, cy + 2.5),
                 (cx - 4, cy - 2.5)]
        d.polygon(inner, fill=(220, 228, 255))
    elif v == 16:                                                    # World
        d.rounded_rectangle((x, y, x + 29, y + 29), 4, fill=(30, 30, 30))
        coin(d, cx, cy, 10, (30, 30, 30), WHITE)
        d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=WHITE)
        d.ellipse((cx - 5, cy - 5, cx + 8, cy + 5), fill=(30, 30, 30))
        d.rectangle((cx - 2, cy - 1, cx + 9, cy + 1), fill=WHITE)
    elif v == 32:                                                    # Arkiv
        d.rounded_rectangle((x, y, x + 29, y + 29), 4, fill=(26, 32, 140))
        crisp_text(d, (cx, cy), "[ A ]", 9, (246, 244, 239))
    elif v == 64:                                                    # ETHGlobal (the diya)
        d.rounded_rectangle((x, y, x + 29, y + 29), 4, fill=(110, 20, 50))
        d.pieslice((cx - 10, cy - 4, cx + 10, cy + 12), 0, 180, fill=(255, 133, 0))
        d.polygon([(cx, cy - 10), (cx + 4, cy - 1), (cx, cy + 3), (cx - 4, cy - 1)], fill=(255, 210, 80))
    else:                                                            # ETH tiers, then gold
        bg, fg = ETH_RAMP[v]
        d.rounded_rectangle((x, y, x + 29, y + 29), 4, fill=bg)
        diamond(d, cx, y + 2, 21, (255, 240, 170) if v >= 2048 else (236, 239, 255), shade(bg, 0.6))
    label_bg = (14, 15, 30)
    d.rectangle((x + 1, y + 22, x + 28, y + 28), fill=label_bg)
    crisp_text(d, (cx, y + 25), str(v), 7, WHITE)


def board(style):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    board_frame(img, d)
    for r, row in enumerate(BOARD_DEMO):
        for c, v in enumerate(row):
            if v:
                (tile_eth if style == "A" else tile_token)(d, 17 + c * 32, 5 + r * 32, v)
    return img


def title(style):
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    for i in range(0, 160, 12):                                      # faint diagonal grid: blocks
        d.line([(i, 0), (i - 80, 144)], fill=(26, 28, 54))
    if style == "A":
        diamond(d, 80, 8, 74, (192, 203, 246), (98, 126, 234), (255, 255, 255))
        crisp_text(d, (80, 96), "2048", 30, WHITE)
    else:
        for (x, y, k) in ((30, 30, 2), (130, 30, 8), (30, 78, 16), (130, 78, 64)):
            tile_token(d, x - 15, y - 15, k)
        diamond(d, 80, 10, 58, (192, 203, 246), (98, 126, 234), (255, 255, 255))
        crisp_text(d, (80, 88), "2048", 26, WHITE)
    crisp_text(d, (80, 113), "ANY% WEB3 EDITION", 8, (138, 146, 178))
    crisp_text(d, (80, 128), "PRESS START", 9, (255, 214, 102))
    return img


def gameover():
    img = board("A")
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((26, 48, 134, 88), 6, fill=(14, 15, 30), outline=(123, 63, 228))
    crisp_text(d, (80, 61), "REKT!", 16, (255, 120, 120))
    crisp_text(d, (80, 79), "A: mint again", 8, WHITE)
    return img


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "mockups.png"
    shots = [("A  Ethereum", [title("A"), board("A"), gameover()]),
             ("B  Token ladder", [title("B"), board("B")])]
    S = 3
    sheet = Image.new("RGB", (3 * (W * S + 16) + 16, 2 * (H * S + 40) + 16), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    for r, (name, imgs) in enumerate(shots):
        y = 16 + r * (H * S + 40)
        d.text((16, y), name, font=font(20), fill=WHITE)
        for c, im in enumerate(imgs):
            sheet.paste(im.resize((W * S, H * S), Image.NEAREST), (16 + c * (W * S + 16), y + 28))
    sheet.save(out)
    print(out)


if __name__ == "__main__":
    main()
