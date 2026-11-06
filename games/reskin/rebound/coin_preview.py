"""Preview a more detailed USDC coin for the player, against the current one: every player frame, big and at
1x on the Mainnet sky.  python coin_preview.py PLAYERTILES.2bpp OUT.png"""
import math
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import reskin                                       # noqa: E402

# the 3 sprite colours + clear: 1 outline (deep navy), 2 USDC blue, 3 white
COLOURS = {0: None, 1: (10, 26, 58), 2: (39, 117, 202), 3: (255, 255, 255)}
SKY = (20, 22, 43)

DOLLAR7 = ["..#..",                                   # 5 x 7: the logo's "$" with its stem above and below
           ".####",
           "#.#..",
           ".###.",
           "..#.#",
           "####.",
           "..#.."]


def usdc_coin_detailed(grid, outline=1, blue=2, white=3):
    """The frame as a detailed USDC coin inside the ball's own silhouette (squashed frames stay squashed):
    navy outline, a shaded rim (navy dither lower right, a white glint upper left), the logo's two white arcs,
    and a 7-tall "$"."""
    if sum(r.count(blue) for r in grid) < 20:
        return grid
    x0, y0, x1, y1 = reskin.bbox(grid)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0 + 1) / 2, (y1 - y0 + 1) / 2
    inside = [[grid[y][x] != 0 for x in range(16)] for y in range(16)]
    t = math.tan(math.radians(50))
    out = [[0] * 16 for _ in range(16)]
    for y in range(16):
        for x in range(16):
            if not inside[y][x]:
                continue
            edge = any(not (0 <= x + dx < 16 and 0 <= y + dy < 16) or not inside[y + dy][x + dx]
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            nx, ny = (x - cx) / rx, (y - cy) / ry
            r = math.hypot(nx, ny)
            ang = math.degrees(math.atan2(ny, nx))                # 90 = straight down, -90 = straight up
            if edge:
                out[y][x] = outline
            elif 0.66 <= r <= 0.86 and abs(ny) <= t * abs(nx):    # the logo's arcs, left and right
                out[y][x] = white
            elif r > 0.74 and 55 <= ang <= 125:                   # the coin's edge, seen below: solid shadow
                out[y][x] = outline
            elif 0.62 <= r <= 0.78 and -122 <= ang <= -108:         # a small glint, top left, clear of the arcs
                out[y][x] = white
            else:
                out[y][x] = blue
    h = 7 if ry >= 6.5 else 5
    rows = DOLLAR7 if h == 7 else DOLLAR7[1:6]
    gx, gy = round(cx - 2), round(cy - (h - 1) / 2)
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch == "#" and 0 <= gy + dy < 16 and 0 <= gx + dx < 16 and inside[gy + dy][gx + dx]:
                out[gy + dy][gx + dx] = white
    return out


def draw(grid, scale, bg=None):
    img = Image.new("RGB", (16 * scale, 16 * scale), bg or (40, 40, 52))
    d = ImageDraw.Draw(img)
    for y in range(16):
        for x in range(16):
            c = COLOURS[grid[y][x]]
            if c:
                d.rectangle((x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1), fill=c)
    return img


def main():
    tiles, out_path = open(sys.argv[1], "rb").read(), sys.argv[2]
    frames = reskin.frames16(tiles)
    old = [reskin.usdc_coin([r[:] for r in g]) for g in frames]
    new = [usdc_coin_detailed([r[:] for r in g]) for g in frames]
    seen, keep = set(), []
    for i, g in enumerate(frames):                            # one frame per silhouette size: round and squashed
        b = reskin.bbox(g)
        if sum(r.count(2) for r in g) >= 20 and b and (b[2] - b[0], b[3] - b[1]) not in seen:
            seen.add((b[2] - b[0], b[3] - b[1]))
            keep.append(i)
    keep = keep[:8]
    S, pad = 12, 12
    sheet = Image.new("RGB", (pad + len(keep) * (16 * S + pad), 2 * (16 * S + pad) + 120), (24, 24, 32))
    d = ImageDraw.Draw(sheet)
    for row, (name, set_) in enumerate((("now", old), ("detailed", new))):
        y = pad + row * (16 * S + pad)
        d.text((4, y - 10), name, fill=(236, 239, 255))
        for i, k in enumerate(keep):
            sheet.paste(draw(set_[k], S, SKY), (pad + i * (16 * S + pad), y))
    y = 2 * (16 * S + pad) + 8                                    # real size, then 3x like the device screen
    for row, (name, set_) in enumerate((("now", old), ("detailed", new))):
        strip = Image.new("RGB", (len(keep) * 24, 24), SKY)
        for i, k in enumerate(keep):
            strip.paste(draw(set_[k], 1, SKY), (i * 24 + 4, 4))
        sheet.paste(strip.resize((strip.width * 3, strip.height * 3), Image.NEAREST), (pad + row * (len(keep) * 72 + pad), y))
        d.text((pad + row * (len(keep) * 72 + pad), y + 76), name + " (device size)", fill=(236, 239, 255))
    sheet.save(out_path)
    print("->", out_path)


if __name__ == "__main__":
    main()
