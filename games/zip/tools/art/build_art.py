"""Builds ZIP's sprites and backgrounds into graphics/ (indexed BMP + Butano JSON). Run from the game directory:
    python tools/art/build_art.py
Sources: Kenney CC0 packs in art/kenney/ (tools/art/fetch_kenney.sh copies them from games/_kenney) and the custom
art drawn here (Zip, packets, springs, the World-orb booster, the Arkiv rack checkpoint, the hall, the title).
The level background (terrain + decor) is built by tools/level/build_level.py from level/level.txt with
tools/art/level_art.py. Everything is deterministic (no randomness without a fixed seed)."""
import math
import os
import random
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from gbaimg import ArtError, index_image, q15, save_sprite, tiles_of, write_bmp, write_json  # noqa: E402

GFX = os.path.join(GAME, "graphics")
KENNEY = os.path.join(GAME, "art", "kenney")
PREVIEW = os.path.join(GAME, "art", "gen")

# ---- palettes (RGB; index 0 = transparent) ------------------------------------------------------------------------
T = (0, 0, 0)
OUT = (16, 24, 56)
ZIP_PAL = [T, OUT, (0, 104, 168), (0, 176, 232), (104, 224, 248), (248, 248, 248), (24, 24, 40), (232, 64, 88),
           (144, 32, 56), (48, 56, 96), (248, 224, 96), (232, 80, 200), (184, 240, 255), (0, 144, 200), (96, 104, 136)]
PACKET_PAL = [T, (8, 48, 32), (40, 160, 72), (136, 232, 80), (216, 248, 120), (248, 248, 232), (24, 104, 56)]
SPRING_PAL = [T, OUT, (64, 72, 96), (120, 128, 152), (184, 192, 208), (248, 200, 40), (248, 240, 136),
              (176, 120, 16), (232, 56, 56), (248, 144, 136), (144, 24, 40), (240, 240, 248)]
ORB_PAL = [T, OUT, (72, 80, 104), (128, 136, 160), (184, 192, 208), (232, 236, 244), (255, 255, 255),
           (32, 36, 48), (0, 200, 232), (144, 240, 255), (0, 112, 160), (248, 216, 72)]
RACK_PAL = [T, OUT, (40, 44, 64), (64, 72, 96), (104, 112, 136), (160, 168, 184), (232, 64, 72), (120, 32, 40),
            (72, 232, 120), (24, 120, 64), (120, 88, 232), (200, 184, 255), (248, 248, 248)]
ICON_PAL = [T, OUT, (40, 160, 72), (136, 232, 80), (216, 248, 120), (248, 248, 232), (200, 144, 24), (248, 200, 40),
            (248, 240, 160), (96, 104, 136), (160, 168, 184), (0, 176, 232), (104, 224, 248)]
TRAIL_PAL = [T, (0, 104, 168), (0, 176, 232), (104, 224, 248), (200, 248, 255)]


def canvas(w, h):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def rgba(c):
    return tuple(c[:3]) + (255,)


# ---- Zip ----------------------------------------------------------------------------------------------------------
# 32 x 32 frames drawn around the rules' centre (16, 16): the feet reach y = 25 (BODY_H 10 below the centre).
ZIP_FRAMES = ["stand0", "stand1", "walk0", "walk1", "walk2", "walk3", "run0", "run1", "run2", "run3",
              "dash0", "dash1", "dash2", "dash3", "roll0", "roll1", "roll2", "roll3", "spring", "hurt", "fall"]


def zip_body(d, dx=0, dy=0, eyes="open", squash=0):
    c = ZIP_PAL
    x0, y0, x1, y1 = 8 + dx, 5 + dy + squash, 23 + dx, 19 + dy
    d.rounded_rectangle([x0, y0, x1, y1], radius=4, fill=rgba(c[3]), outline=rgba(c[1]))
    d.line([x0 + 3, y0 + 1, x1 - 3, y0 + 1], fill=rgba(c[12]))             # top shine
    d.line([x0 + 1, y0 + 3, x0 + 1, y1 - 3], fill=rgba(c[4]))              # left edge light
    d.line([x0 + 3, y1 - 1, x1 - 3, y1 - 1], fill=rgba(c[2]))              # bottom shade
    d.line([x1 - 1, y0 + 3, x1 - 1, y1 - 3], fill=rgba(c[13]))
    # the packet header: a bright band with bits
    hy = y0 + 3
    d.rectangle([x0 + 1, hy, x1 - 1, hy + 1], fill=rgba(c[9]))
    for i, bx in enumerate(range(x0 + 2, x1 - 1, 2)):
        d.point((bx, hy), fill=rgba(c[10] if i % 3 else c[5]))
    ey = y0 + 7
    if eyes == "open":
        for ex in (x0 + 7, x0 + 11):
            d.rectangle([ex, ey, ex + 2, ey + 4], fill=rgba(c[5]))
            d.rectangle([ex + 1, ey + 1, ex + 2, ey + 3], fill=rgba(c[6]))
            d.point((ex + 2, ey + 1), fill=rgba(c[5]))
    elif eyes == "up":
        for ex in (x0 + 7, x0 + 11):
            d.rectangle([ex, ey - 1, ex + 2, ey + 3], fill=rgba(c[5]))
            d.rectangle([ex + 1, ey - 1, ex + 2, ey], fill=rgba(c[6]))
    elif eyes == "x":
        for ex in (x0 + 6, x0 + 11):
            d.line([ex, ey, ex + 3, ey + 3], fill=rgba(c[6]))
            d.line([ex, ey + 3, ex + 3, ey], fill=rgba(c[6]))
    elif eyes == "blink":
        for ex in (x0 + 7, x0 + 11):
            d.line([ex, ey + 3, ex + 2, ey + 3], fill=rgba(c[6]))
    # a small grin
    if eyes in ("open", "up"):
        d.line([x0 + 9, y1 - 3, x0 + 12, y1 - 3], fill=rgba(c[1]))


def zip_leg(d, hip, foot, shoe_dx=1):
    c = ZIP_PAL
    d.line([hip, foot], fill=rgba(c[14]), width=2)
    fx, fy = foot
    d.rectangle([fx - 1, fy - 1, fx + 2 + shoe_dx, fy + 1], fill=rgba(c[7]), outline=rgba(c[8]))
    d.point((fx, fy - 1), fill=rgba(c[5]))


def zip_frame(name):
    img, d = canvas(32, 32)
    c = ZIP_PAL
    if name.startswith("stand"):
        zip_leg(d, (13, 20), (13, 24))
        zip_leg(d, (18, 20), (18, 24))
        zip_body(d, eyes="blink" if name == "stand1" else "open")
    elif name.startswith("walk"):
        k = int(name[-1])
        feet = [((11, 24), (19, 23)), ((13, 24), (17, 24)), ((19, 23), (11, 24)), ((17, 24), (13, 24))][k]
        bob = 1 if k in (1, 3) else 0
        zip_leg(d, (13, 20), feet[0])
        zip_leg(d, (18, 20), feet[1])
        zip_body(d, dy=bob)
    elif name.startswith("run"):
        k = int(name[-1])
        feet = [((9, 23), (21, 22)), ((13, 24), (18, 21)), ((21, 22), (9, 23)), ((18, 21), (13, 24))][k]
        zip_leg(d, (13, 20), feet[0], 2)
        zip_leg(d, (18, 20), feet[1], 2)
        zip_body(d, dx=1, dy=k % 2)
    elif name.startswith("dash"):
        k = int(name[-1])
        # the legs become a spinning wheel
        d.ellipse([9, 18, 23, 26], outline=rgba(c[7]))
        for j in range(4):
            a = (k * 22.5 + j * 90) * math.pi / 180
            d.line([16, 22, 16 + round(6 * math.cos(a)), 22 + round(3.5 * math.sin(a))], fill=rgba(c[8]))
        d.arc([9, 18, 23, 26], 20 + k * 30, 110 + k * 30, fill=rgba(c[5]))
        zip_body(d, dx=2, dy=-1)
        d.line([4, 9, 7, 9], fill=rgba(c[4]))
        d.line([3, 13, 7, 13], fill=rgba(c[4]))
    elif name.startswith("roll"):
        k = int(name[-1])
        d.ellipse([7, 7, 25, 25], fill=rgba(c[3]), outline=rgba(c[1]))
        d.ellipse([9, 9, 23, 23], outline=rgba(c[13]))
        for j in range(3):
            a0 = k * 30 + j * 120
            d.arc([9, 9, 23, 23], a0, a0 + 50, fill=rgba(c[12]))
        a = k * 30 * math.pi / 180
        d.line([16 + round(6 * math.cos(a)), 16 + round(6 * math.sin(a)),
                16 - round(6 * math.cos(a)), 16 - round(6 * math.sin(a))], fill=rgba(c[9]))
        d.point((16, 16), fill=rgba(c[10]))
    elif name == "spring":
        zip_leg(d, (13, 20), (12, 25))
        zip_leg(d, (18, 20), (19, 25))
        zip_body(d, dy=-2, eyes="up", squash=-1)
        d.line([6, 8, 6, 12], fill=rgba(c[4]))
        d.line([26, 8, 26, 12], fill=rgba(c[4]))
    elif name == "hurt":
        zip_leg(d, (12, 20), (9, 22))
        zip_leg(d, (19, 20), (22, 21))
        zip_body(d, eyes="x")
    elif name == "fall":
        zip_leg(d, (13, 20), (10, 24))
        zip_leg(d, (18, 20), (21, 24))
        zip_body(d, eyes="open")
    return img


def build_zip():
    frames = [zip_frame(n) for n in ZIP_FRAMES]
    return save_sprite(os.path.join(GFX, "zip.bmp"), frames, ZIP_PAL)


def build_trail():
    frames = []
    for k, length in enumerate((10, 16, 24)):
        img, d = canvas(32, 16)
        for j, (y, col) in enumerate(((5, 2), (8, 3), (11, 2))):
            ln = length - (j % 2) * 4
            d.line([31 - ln, y, 31, y], fill=rgba(TRAIL_PAL[col]))
            d.line([31 - ln // 2, y, 31, y], fill=rgba(TRAIL_PAL[col + 1]))
        frames.append(img)
    return save_sprite(os.path.join(GFX, "trail.bmp"), frames, TRAIL_PAL)


# ---- packets, springs, booster, bug, rack, icons ------------------------------------------------------------------

def packet_frame(k):
    """A spinning data diamond: widths 7, 5, 1, 5 half-widths."""
    img, d = canvas(16, 16)
    c = PACKET_PAL
    hw = (6, 4, 1, 4)[k]
    pts = [(8, 2), (8 + hw, 8), (8, 14), (8 - hw, 8)] if hw > 1 else [(8, 2), (9, 8), (8, 14), (7, 8)]
    d.polygon(pts, fill=rgba(c[3]), outline=rgba(c[1]))
    if hw > 1:
        d.polygon([(8, 4), (8 + hw - 2, 8), (8, 12), (8 - hw + 2, 8)], fill=rgba(c[4]))
        d.line([8, 5, 8, 11], fill=rgba(c[5]))
        d.point((8 - hw + 2, 8), fill=rgba(c[5]))
    else:
        d.line([8, 3, 8, 13], fill=rgba(c[4]))
    return img


def build_packet():
    return save_sprite(os.path.join(GFX, "packet.bmp"), [packet_frame(k) for k in range(4)], PACKET_PAL)


def spring_frame(red, state):
    """16 x 16; the base sits on the frame bottom. state 0 idle, 1 compressed, 2 extended."""
    img, d = canvas(16, 16)
    c = SPRING_PAL
    top, light, dark = (c[8], c[9], c[10]) if red else (c[5], c[6], c[7])
    d.rectangle([1, 13, 14, 15], fill=rgba(c[3]), outline=rgba(c[1]))
    d.line([2, 13, 13, 13], fill=rgba(c[4]))
    coil_top = {0: 8, 1: 11, 2: 3}[state]
    for y in range(coil_top + 3, 13, 2):
        d.line([4, y, 11, y], fill=rgba(c[2]))
        d.line([4, y + 1, 11, y + 1], fill=rgba(c[4]))
    d.rectangle([0, coil_top, 15, coil_top + 3], fill=rgba(top), outline=rgba(c[1]))
    d.line([1, coil_top + 1, 14, coil_top + 1], fill=rgba(light))
    d.line([1, coil_top + 3, 14, coil_top + 3], fill=rgba(dark))
    return img


def build_spring():
    frames = [spring_frame(red, st) for red in (0, 1) for st in (0, 1, 2)]
    return save_sprite(os.path.join(GFX, "spring.bmp"), frames, SPRING_PAL)


def booster_frame(k):
    """The World-orb booster gate, 32 x 32, sitting on the frame bottom: a chrome orb on a pedestal between two
    chevron posts. k: chevron phase."""
    img, d = canvas(32, 32)
    c = ORB_PAL
    d.rectangle([2, 27, 29, 31], fill=rgba(c[2]), outline=rgba(c[1]))
    d.line([3, 28, 28, 28], fill=rgba(c[3]))
    d.rectangle([12, 22, 19, 27], fill=rgba(c[3]), outline=rgba(c[1]))
    d.ellipse([7, 3, 24, 20], fill=rgba(c[4]), outline=rgba(c[1]))
    d.ellipse([9, 5, 22, 18], fill=rgba(c[5]))
    d.ellipse([11, 7, 20, 16], fill=rgba(c[7]))                      # the dark iris
    d.ellipse([13, 9, 18, 14], outline=rgba(c[3]))
    d.point((12, 7), fill=rgba(c[6]))
    d.line([10, 6, 12, 6], fill=rgba(c[6]))
    for j in range(3):                                                # >>> chevrons on the base, cycling
        col = c[9] if (j == k % 3) else c[8]
        x = 5 + j * 8
        d.line([x, 29, x + 2, 30, x, 31][:4], fill=rgba(col))
        d.line([x, 29, x + 2, 30], fill=rgba(col))
        d.line([x + 2, 30, x, 31], fill=rgba(col))
    ring = c[8] if k % 2 == 0 else c[9]
    d.arc([5, 1, 26, 22], 200, 340, fill=rgba(ring))
    return img


def build_booster():
    return save_sprite(os.path.join(GFX, "booster.bmp"), [booster_frame(k) for k in range(3)], ORB_PAL)


def kenney_tile(sheet, col, row, size=18):
    im = Image.open(os.path.join(KENNEY, sheet)).convert("RGBA")
    return im.crop((col * size, row * size, col * size + size, row * size + size))


def fit16(tile):
    """Crop a Kenney tile to its opaque box and centre it on a 16 x 16 frame, bottom aligned (never scaled)."""
    box = tile.getbbox()
    t = tile.crop(box)
    if t.width > 16 or t.height > 16:
        t = t.crop((0, 0, min(16, t.width), min(16, t.height)))
    out = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    out.alpha_composite(t, ((16 - t.width) // 2, 16 - t.height))
    return out


def build_bug():
    """The bug: Kenney Pixel Platformer's spiked crawler (characters row 1, columns 6 and 7), recoloured purple-red
    with a green 'glitch' eye so it reads as a software bug on the dark hall."""
    frames = []
    for col in (6, 7):
        t = kenney_tile("pixel-platformer/tilemap-characters_packed.png", col, 1, 24)
        frames.append(fit16(t))
    colours = {}
    for fr in frames:
        for p in fr.convert("RGBA").get_flattened_data() if hasattr(fr, "get_flattened_data") else fr.getdata():
            if p[3] >= 128:
                colours[q15(p)] = colours.get(q15(p), 0) + 1
    pal = [T] + sorted(colours, key=lambda c: -colours[c])[:15]
    return save_sprite(os.path.join(GFX, "bug.bmp"), frames, pal)


def rack_frame(on):
    """The Arkiv server rack checkpoint, 16 x 32, sitting on the frame bottom; the top lamp is red (off) or green."""
    img, d = canvas(16, 32)
    c = RACK_PAL
    d.rectangle([1, 4, 14, 31], fill=rgba(c[2]), outline=rgba(c[1]))
    d.line([2, 5, 13, 5], fill=rgba(c[4]))
    for y in range(8, 29, 4):
        d.rectangle([3, y, 12, y + 2], fill=rgba(c[3]), outline=rgba(c[1]))
        d.point((4, y + 1), fill=rgba(c[8] if on else c[9]))
        d.point((6, y + 1), fill=rgba(c[10] if (y // 4) % 2 else c[9]))
        d.line([8, y + 1, 11, y + 1], fill=rgba(c[5]))
    lamp, glow = (c[8], c[12]) if on else (c[6], c[7])
    d.rectangle([5, 0, 10, 3], fill=rgba(lamp), outline=rgba(c[1]))
    d.point((6, 1), fill=rgba(glow if on else c[5]))
    d.line([2, 30, 13, 30], fill=rgba(c[11]))                         # the Arkiv purple base strip
    return img


def build_rack():
    return save_sprite(os.path.join(GFX, "rack.bmp"), [rack_frame(0), rack_frame(1)], RACK_PAL)


def icon_frames():
    c = ICON_PAL
    out = []
    img, d = canvas(16, 16)                                           # 0: packet (HUD)
    d.polygon([(8, 1), (14, 8), (8, 15), (2, 8)], fill=rgba(c[3]), outline=rgba(c[1]))
    d.polygon([(8, 4), (11, 8), (8, 12), (5, 8)], fill=rgba(c[4]))
    d.line([8, 5, 8, 11], fill=rgba(c[5]))
    out.append(img)
    img, d = canvas(16, 16)                                           # 1: clock
    d.ellipse([1, 1, 14, 14], fill=rgba(c[12]), outline=rgba(c[1]))
    d.ellipse([3, 3, 12, 12], fill=rgba(c[5]))
    d.line([8, 8, 8, 4], fill=rgba(c[1]))
    d.line([8, 8, 11, 8], fill=rgba(c[1]))
    out.append(img)
    for got in (1, 0):                                                # 2: trophy earned, 3: not earned
        img, d = canvas(16, 16)
        body, light, dark = (c[7], c[8], c[6]) if got else (c[9], c[10], c[1])
        d.rectangle([4, 2, 11, 7], fill=rgba(body), outline=rgba(c[1]))
        d.ellipse([3, 4, 12, 10], fill=rgba(body), outline=rgba(c[1]))
        d.rectangle([4, 2, 11, 6], fill=rgba(body))
        d.line([5, 3, 5, 7], fill=rgba(light))
        d.arc([0, 2, 5, 8], 90, 270, fill=rgba(dark))
        d.arc([10, 2, 15, 8], 270, 90, fill=rgba(dark))
        d.rectangle([7, 10, 8, 12], fill=rgba(dark))
        d.rectangle([4, 12, 11, 14], fill=rgba(body), outline=rgba(c[1]))
        out.append(img)
    return out


def build_icons():
    return save_sprite(os.path.join(GFX, "icons.bmp"), icon_frames(), ICON_PAL)


# ---- backgrounds --------------------------------------------------------------------------------------------------
HALL_PAL = [(8, 8, 24), (16, 20, 40), (24, 32, 56), (32, 44, 72), (40, 56, 88), (56, 72, 112), (0, 88, 112),
            (0, 160, 184), (72, 216, 120), (216, 72, 88), (248, 200, 72), (120, 96, 200), (20, 26, 48),
            (48, 64, 100), (12, 14, 32), (136, 232, 248)]


def hall_image():
    """The parallax server hall, 512 x 256, tiled horizontally: a far row of rack silhouettes with LED dots, cable
    trays above, a floor glow below. Only whole 8 x 8 blocks of LEDs so the tile count stays low."""
    rnd = random.Random(7)
    img = Image.new("RGB", (512, 256), HALL_PAL[0])
    d = ImageDraw.Draw(img)
    for y in range(256):                                              # vertical gradient bands (8 px, tile aligned)
        band = y // 32
        col = HALL_PAL[(0, 14, 14, 1, 1, 12, 12, 1)[band]]
        d.line([0, y, 511, y], fill=col)
    # cable trays near the top
    for y in (24, 40):
        d.rectangle([0, y, 511, y + 3], fill=HALL_PAL[2])
        d.line([0, y, 511, y], fill=HALL_PAL[3])
        for x in range(0, 512, 32):
            d.rectangle([x + 14, y - 16, x + 17, y], fill=HALL_PAL[2])
    # two rows of racks (back row darker, higher)
    for row, (top, bottom, body, edge) in enumerate(((72, 200, 1, 2), (104, 232, 12, 3))):
        x = 0 if row == 0 else 16
        while x < 512:
            w = 48
            d.rectangle([x, top, x + w - 9, bottom], fill=HALL_PAL[body])
            d.line([x, top, x + w - 9, top], fill=HALL_PAL[edge])
            d.line([x, top, x, bottom], fill=HALL_PAL[edge])
            for y in range(top + 8, bottom - 8, 8):
                d.line([x + 3, y, x + w - 12, y], fill=HALL_PAL[edge])
                if row == 1:
                    for lx in range(x + 4, x + w - 12, 8):
                        r = rnd.random()
                        if r < 0.35:
                            colr = HALL_PAL[(7, 8, 7, 9, 10, 15)[rnd.randrange(6)]]
                            d.point((lx, y + 3), fill=colr)
                            d.point((lx + 2, y + 3), fill=HALL_PAL[6])
            x += w
    d.rectangle([0, 232, 511, 255], fill=HALL_PAL[1])
    d.line([0, 232, 511, 232], fill=HALL_PAL[6])
    for x in range(0, 512, 16):
        d.line([x, 240, x + 8, 240], fill=HALL_PAL[13])
    return img


def save_bg(path, img, palettes, bpp4=True):
    """A regular BG from an RGB image: each 8 x 8 cell uses the palette bank (of palettes, each <= 16 colours with
    index 0 transparent / backdrop) that matches it best; written as a bpp_4_manual BMP."""
    w, h = img.size
    banks = [[q15(c) for c in p] + [(0, 0, 0)] * (16 - len(p)) for p in palettes]
    flat = [c for b in banks for c in b]
    src = img.convert("RGBA").load()
    px = bytearray(w * h)
    for cy in range(0, h, 8):
        for cx in range(0, w, 8):
            cell = [src[cx + i, cy + j] for j in range(8) for i in range(8)]
            best, best_err, best_idx = 0, None, None
            for bi, bank in enumerate(banks):
                err, idx = 0, []
                for p in cell:
                    if p[3] < 128:
                        idx.append(0)
                        continue
                    c = q15(p)
                    k = min(range(1, 16), key=lambda i: sum((bank[i][m] - c[m]) ** 2 for m in range(3)))
                    err += sum((bank[k][m] - c[m]) ** 2 for m in range(3))
                    idx.append(k)
                if best_err is None or err < best_err:
                    best, best_err, best_idx = bi, err, idx
                if err == 0:
                    break
            for n, v in enumerate(best_idx):
                px[(cy + n // 8) * w + cx + n % 8] = (best * 16 + v) if v else 0
    write_bmp(path, (w, h), px, flat)
    write_json(path[:-4] + ".json", {"type": "regular_bg", "bpp_mode": "bpp_4_manual", "colors_count": len(flat)})
    return px


def build_hall():
    img = hall_image()
    pal = [c for c in HALL_PAL]
    # index 0 of the bank is transparent in a BG; the hall is opaque, so shift: bank 0 = [unused] + 15 colours
    bank = [(0, 0, 0)] + pal[:15]
    px = save_bg(os.path.join(GFX, "hall.bmp"), img, [bank])
    return px, img


# ---- the title card -----------------------------------------------------------------------------------------------
LOGO_FONT = {  # 5 x 7 blocks per letter
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "I": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
}
TITLE_PAL = [(0, 0, 0), (16, 24, 56), (0, 104, 168), (0, 176, 232), (104, 224, 248), (248, 248, 248),
             (248, 224, 96), (232, 80, 200), (8, 8, 24), (24, 32, 56), (40, 56, 88), (136, 232, 80), (232, 64, 88),
             (72, 216, 120), (184, 240, 255), (0, 144, 200)]


def title_image():
    """256 x 256 (the screen is the top-left 240 x 160): the hall, a speed-lined band and a big ZIP logo, with Zip
    running (2x)."""
    img = hall_image().crop((0, 48, 256, 304)).convert("RGBA")
    base = Image.new("RGBA", (256, 256), (8, 8, 24, 255))
    base.alpha_composite(img)
    d = ImageDraw.Draw(base)
    d.rectangle([0, 24, 255, 96], fill=rgba(TITLE_PAL[1]))
    rnd = random.Random(3)
    for y in range(28, 94, 4):                                          # speed lines
        x = rnd.randrange(0, 200)
        d.line([x, y, x + rnd.randrange(16, 56), y], fill=rgba(TITLE_PAL[2 if y % 8 else 15]))
    d.line([0, 24, 255, 24], fill=rgba(TITLE_PAL[3]))
    d.line([0, 96, 255, 96], fill=rgba(TITLE_PAL[3]))
    # the logo: 8 px blocks, italic (each row shifted), cyan with a white top and a dark drop shadow
    bx, by, s = 40, 32, 8
    for li, ch in enumerate("ZIP"):
        rows = LOGO_FONT[ch]
        for r, line in enumerate(rows):
            for k, v in enumerate(line):
                if v != "#":
                    continue
                x = bx + li * 48 + k * s + (6 - r) * 2
                y = by + r * s
                d.rectangle([x + 3, y + 3, x + s + 2, y + s + 2], fill=rgba(TITLE_PAL[8]))
        for r, line in enumerate(rows):
            for k, v in enumerate(line):
                if v != "#":
                    continue
                x = bx + li * 48 + k * s + (6 - r) * 2
                y = by + r * s
                d.rectangle([x, y, x + s - 1, y + s - 1], fill=rgba(TITLE_PAL[3]))
                d.line([x, y, x + s - 1, y], fill=rgba(TITLE_PAL[14] if r < 2 else TITLE_PAL[4]))
                d.line([x, y + s - 1, x + s - 1, y + s - 1], fill=rgba(TITLE_PAL[15]))
    # Zip, 2x, bursting from the right of the logo
    z = zip_frame("dash1").resize((64, 64), Image.NEAREST)
    base.alpha_composite(z, (176, 60))
    for y in (78, 88, 98):
        d.line([120, y, 176, y], fill=rgba(TITLE_PAL[4]))
    return base


def build_title():
    img = title_image()
    bank0 = [(0, 0, 0)] + TITLE_PAL[1:]
    bank1 = [(0, 0, 0)] + HALL_PAL[:15]
    px = save_bg(os.path.join(GFX, "title.bmp"), img, [bank0, bank1])
    return px, img


def build_panel():
    """The how-to and results card background: the hall dimmed, with a framed dark panel (256 x 256)."""
    img = hall_image().crop((128, 48, 384, 304)).convert("RGBA")
    base = Image.new("RGBA", (256, 256), (8, 8, 24, 255))
    base.alpha_composite(img)
    d = ImageDraw.Draw(base)
    d.rectangle([12, 8, 227, 151], fill=rgba(TITLE_PAL[8]), outline=rgba(TITLE_PAL[3]))
    d.rectangle([14, 10, 225, 149], outline=rgba(TITLE_PAL[1]))
    d.rectangle([12, 8, 227, 30], fill=rgba(TITLE_PAL[1]), outline=rgba(TITLE_PAL[3]))
    for x in range(20, 220, 12):
        d.point((x, 150), fill=rgba(TITLE_PAL[15]))
    bank0 = [(0, 0, 0)] + TITLE_PAL[1:]
    bank1 = [(0, 0, 0)] + HALL_PAL[:15]
    px = save_bg(os.path.join(GFX, "panel.bmp"), base, [bank0, bank1])
    return px, base


def main():
    os.makedirs(GFX, exist_ok=True)
    os.makedirs(PREVIEW, exist_ok=True)
    sheets = {"zip": build_zip(), "trail": build_trail(), "packet": build_packet(), "spring": build_spring(),
              "booster": build_booster(), "bug": build_bug(), "rack": build_rack(), "icons": build_icons()}
    report = []
    for name in ("hall", "title", "panel"):
        px, img = {"hall": build_hall, "title": build_title, "panel": build_panel}[name]()
        n = tiles_of(px, img.width, img.height)
        report.append("%s: %d tiles" % (name, n))
        if n > 1024:
            raise ArtError("%s has %d tiles" % (name, n))
        img.convert("RGB").save(os.path.join(PREVIEW, name + ".png"))
    for name, sheet in sheets.items():
        big = sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST)
        bg = Image.new("RGBA", big.size, (40, 48, 72, 255))
        bg.alpha_composite(big)
        bg.convert("RGB").save(os.path.join(PREVIEW, name + ".png"))
    print("\n".join(report))


if __name__ == "__main__":
    main()
