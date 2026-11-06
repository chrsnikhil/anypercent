"""Preview the player as a bull (bull market, against the red bear enemy): every one of the ball's expression frames
keeps its eyes and shading; horns go in the empty top corners and a muzzle with nostrils across the bottom.
Two colourways.   python bull_preview.py PLAYERTILES.2bpp OUT.png"""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import reskin                                       # noqa: E402

OUT, BODY, CREAM = 1, 2, 3                          # the sprite's 3 colours (0 is clear)

HORNS = ["oo............oo",                        # big horns curving up and out of the head
         "cco..........occ",
         "occo........occo",
         ".occo......occo.",
         "..oco......oco..",
         "...o........o..."]
MUZZLE = ["....oooooooo....",                       # rows 10 to 14, over the bottom of the face
          "...occcccccco...",
          "...ococcccoco...",
          "....occcccco....",
          ".....oooooo....."]

COLOURWAYS = {
    "bull (brown)": {OUT: (40, 20, 12), BODY: (176, 96, 40), CREAM: (250, 232, 196)},
    "bull (green, bull market)": {OUT: (8, 48, 28), BODY: (30, 170, 90), CREAM: (240, 250, 230)},
}
SKY = (20, 22, 43)


def bull(grid):
    if sum(r.count(BODY) for r in grid) < 20:
        return grid
    out = [r[:] for r in grid]
    for y, row in enumerate(HORNS):
        for x, ch in enumerate(row):
            if ch != "." and grid[y][x] != CREAM:            # over the head too, never over an eye
                out[y][x] = OUT if ch == "o" else CREAM
    for dy, row in enumerate(MUZZLE):
        for x, ch in enumerate(row):
            y = 10 + dy
            if ch != "." and grid[y][x] != 0:
                out[y][x] = OUT if ch == "o" else CREAM
    return out


def draw(grid, scale, pal, bg):
    img = Image.new("RGB", (16 * scale, 16 * scale), bg)
    d = ImageDraw.Draw(img)
    for y in range(16):
        for x in range(16):
            v = grid[y][x]
            if v:
                d.rectangle((x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1), fill=pal[v])
    return img


def main():
    frames = reskin.frames16(open(sys.argv[1], "rb").read())
    keep = [i for i, g in enumerate(frames) if sum(r.count(BODY) for r in g) >= 20]
    S, pad = 8, 8
    rows = len(COLOURWAYS)
    sheet = Image.new("RGB", (pad + len(keep) * (16 * S + pad), rows * (16 * S + pad + 14) + 90), (24, 24, 32))
    d = ImageDraw.Draw(sheet)
    for r, (name, pal) in enumerate(COLOURWAYS.items()):
        y = pad + 12 + r * (16 * S + pad + 14)
        d.text((pad, y - 12), name, fill=(236, 239, 255))
        for i, k in enumerate(keep):
            sheet.paste(draw(bull(frames[k]), S, pal, SKY), (pad + i * (16 * S + pad), y))
        strip = Image.new("RGB", (6 * 24, 24), SKY)                 # device size (x3), with the red bear's colour
        for i, k in enumerate(keep[:6]):
            strip.paste(draw(bull(frames[k]), 1, pal, SKY), (i * 24 + 4, 4))
        sheet.paste(strip.resize((strip.width * 3, strip.height * 3), Image.NEAREST),
                    (pad + r * (6 * 72 + 2 * pad), rows * (16 * S + pad + 14) + 12))
    sheet.save(sys.argv[2])
    print("->", sys.argv[2], len(keep), "frames")


if __name__ == "__main__":
    main()
