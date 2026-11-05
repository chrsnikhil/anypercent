"""MARINE DRIVE GP's sprites and the skyline BG (Butano indexed BMPs + .json in graphics/):
  kart0..3   32 x 32, 16 headings x 3 poses (wheel left, straight, right; frame = heading * 3 + pose): the
             Kenney Car Kit karts rendered by tools/render/render_karts.py
  puff       16 x 16 x 6: the kart effects: smoke (small, big), dust (small, big), the exhaust flame (two)
  palm       32 x 64 palm tree (the Marine Drive promenade)
  gantry     64 x 64 x 3: the Chainlink start/finish gantry (left post, banner, right post)
  spark      8 x 8 x 3: drift sparks (2) and the player's marker
  billboard  64 x 32: an Arkiv billboard on two posts
  orb        16 x 16 x 2: the World orb hovering over a boost pad
  place      32 x 16 x 4: 1st 2nd 3rd 4th
  speed      32 x 8 x 9: the speed bar, empty to full
  logo       64 x 32 x 6: MARINE DRIVE GP (3 x 2 sprites)
  count      64 x 32 x 4: 3 2 1 GO!
  banner     64 x 32 x 6: FINAL LAP, FINISH!, NEW BEST (two frames each)
  digits     8 x 16 x 38: white 0-9 : . for the race clock; green, then red, 0-9 . + - for the gap to the ghost
  skyline    512 x 256 regular BG (rows 0..63 used): the Mumbai skyline over Back Bay at dusk
Run from the game directory: /opt/arca-sandbox/venv/bin/python tools/art/build_sprites.py"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gbaimg  # noqa: E402

GAME = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
GFX = os.path.join(GAME, "graphics")
RENDERS = os.path.join(GAME, "art", "renders", "karts")
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
OUTLINE = (24, 24, 40)
WHITE = (255, 255, 255)
GAP_GLYPHS = "0123456789.+-"   # the gap to the ghost (src/view.cpp gap_frame)
GAP_GREEN, GAP_RED = (96, 248, 112), (255, 72, 56)
KART_FRAMES = 16
POSES = "LCR"                  # frame = heading * 3 + pose (src/view.cpp kart_frame)


def font(size, name="DejaVuSans-Bold.ttf"):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def shrink(img, factor):
    w, h = img.size
    return img.convert("RGBa").resize((w // factor, h // factor), Image.LANCZOS).convert("RGBA")


def outline(frame, colour=OUTLINE):
    """A 1 px outline (8-neighbourhood) around the opaque pixels, inside the frame."""
    a = np.array(frame.getchannel("A")) >= 128
    pad = np.pad(a, 1)
    ring = np.zeros_like(a)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ring |= pad[1 + dy:1 + dy + a.shape[0], 1 + dx:1 + dx + a.shape[1]]
    ring &= ~a
    px = np.array(frame)
    px[ring] = colour + (255,)
    px[~(a | ring), 3] = 0
    px[a, 3] = 255
    return Image.fromarray(px, "RGBA")


def write_sprite(name, frames, colours=16, keep=()):
    """frames: RGBA images of one size, stacked into a 4 bpp sheet with one palette (index 0 transparent).
    keep: colours that must be exact palette entries."""
    w, h = frames[0].size
    sheet = np.concatenate([np.array(f.convert("RGBA")) for f in frames], 0)
    opaque = sheet[:, :, 3] >= 128
    px = sheet[:, :, :3][opaque].astype(np.float32)
    pal, index = gbaimg.quantize(px, colours - 1 - len(keep))
    pal = [tuple(int(c) for c in gbaimg.q15(k)) for k in keep] + pal
    if keep:
        full = np.array(pal, np.float32)
        index = ((gbaimg.q15(px)[:, None, :].astype(np.float32) - full[None]) ** 2).sum(2).argmin(1)
    else:
        index = index.astype(np.int64)
    out = np.zeros(sheet.shape[:2], np.uint8)
    out[opaque] = index + 1
    palette = [(255, 0, 255)] + pal
    gbaimg.write_bmp8(os.path.join(GFX, name + ".bmp"), out, palette)
    with open(os.path.join(GFX, name + ".json"), "w") as f:
        json.dump({"type": "sprite", "height": h, "bpp_mode": "bpp_4", "colors_count": 16}, f, indent=4)
    return out, palette


def tint_helmets(frame, colour, strength):
    """Tints the near-white pixels (the dome helmet, which dominates the kart seen from behind) toward the kart's body
    colour, keeping their shading: from behind, the four karts would otherwise read as the same cream blob."""
    px = np.array(frame).astype(np.float32)
    rgb = px[:, :, :3]
    white = (px[:, :, 3] >= 128) & (rgb.min(2) > 140) & (rgb.max(2) - rgb.min(2) < 90)
    lum = rgb.mean(2, keepdims=True) / 255.0
    target = np.clip(colour * 1.1, 0, 255) * lum
    rgb[white] = rgb[white] * (1 - strength) + target[white[:, :, None].repeat(3, 2)].reshape(-1, 3) * strength
    px[:, :, :3] = rgb
    return Image.fromarray(px.clip(0, 255).astype(np.uint8), "RGBA")


# Helmet colours: the player's a vivid lime (recognisable at a glance), each rival its kart's body colour (picked
# by eye from the renders: the most saturated pixels are the shared orange wheel rims, so body_colour() cannot).
HELMETS = [np.array(c, np.float32) for c in ((150, 230, 60), (150, 110, 235), (245, 105, 170), (250, 200, 50))]


def karts():
    for k in range(4):
        frames = []
        for f in range(KART_FRAMES):
            for pose in POSES:
                im = Image.open(os.path.join(RENDERS, "kart%d_%02d_%s.png" % (k, f, pose))).convert("RGBA")
                frames.append(ImageEnhance.Color(shrink(im, 4)).enhance(1.6))   # 128 -> 32, livelier colours
        frames = [outline(tint_helmets(fr, HELMETS[k], 1.0)) for fr in frames]
        lit, shade = HELMETS[k], HELMETS[k] * 0.72      # exact palette entries: median cut would pale them
        write_sprite("kart%d" % k, frames, keep=[OUTLINE, tuple(int(c) for c in lit), tuple(int(c) for c in shade)])


def sparks():
    """8 x 8: two drift-spark frames (a small star, blue then gold) and the player's marker (a lime arrow)."""
    frames = []
    for colour in ((120, 200, 255, 255), (255, 220, 90, 255)):
        im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.polygon([(16, 1), (20, 12), (31, 16), (20, 20), (16, 31), (12, 20), (1, 16), (12, 12)], fill=colour)
        d.ellipse((12, 12, 20, 20), fill=(255, 255, 255, 255))
        frames.append(shrink(im, 4))
    im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    ImageDraw.Draw(im).polygon([(2, 6), (30, 6), (16, 28)], fill=(150, 230, 60, 255), outline=OUTLINE + (255,),
                               width=4)
    frames.append(shrink(im, 4))
    write_sprite("spark", frames, keep=[OUTLINE])


def puffs():
    """16 x 16: smoke (small, big) and dust (small, big) puffs left behind the rear wheels, and two exhaust flames."""
    frames = []
    for fill in ((236, 236, 242, 255), (210, 172, 112, 255)):          # tyre smoke, then sand dust
        for r in (9, 15):
            im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            for cx, cy, rr in ((32 - r // 2, 36, r), (32 + r // 2, 36, r), (32, 30 - r // 3, r + 2)):
                d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=fill)
            frames.append(shrink(im, 4))
    for h in (30, 40):                                                   # the flame points back, at the camera
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.polygon([(20, 6), (44, 6), (32, 6 + h)], fill=(255, 140, 30, 255))
        d.polygon([(26, 6), (38, 6), (32, 6 + h * 2 // 3)], fill=(255, 235, 130, 255))
        frames.append(shrink(im, 4))
    write_sprite("puff", frames)


def palm():
    im = Image.new("RGBA", (128, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    trunk = [(60 + int(6 * np.sin(y / 40.0)), y) for y in range(96, 252, 4)]
    for i, (x, y) in enumerate(trunk):
        c = (150, 104, 60) if (i // 2) % 2 else (122, 84, 50)
        d.ellipse((x - 8, y - 5, x + 8, y + 5), fill=c + (255,))
    cx, cy = 62, 92
    fronds = [(-1.0, 0.1), (-0.8, -0.5), (-0.3, -0.9), (0.3, -0.95), (0.8, -0.5), (1.0, 0.15), (-0.6, 0.55), (0.6, 0.6)]
    for fx, fy in fronds:
        for t in np.linspace(0, 1, 26):
            x = cx + fx * 58 * t
            y = cy + fy * 40 * t + 30 * t * t
            r = 9 * (1 - t) + 3
            c = (46, 150, 70) if fy < 0 else (32, 118, 58)
            d.ellipse((x - r, y - r * 0.6, x + r, y + r * 0.6), fill=c + (255,))
    d.ellipse((cx - 10, cy - 6, cx + 10, cy + 10), fill=(110, 74, 40, 255))
    write_sprite("palm", [outline(shrink(im, 4))])


def text_image(text, size, fill, stroke=4, stroke_fill=OUTLINE, name="DejaVuSans-Bold.ttf"):
    f = font(size, name)
    box = f.getbbox(text, stroke_width=stroke)
    im = Image.new("RGBA", (box[2] - box[0] + 4, box[3] - box[1] + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - box[0], 2 - box[1]), text, font=f, fill=fill, stroke_width=stroke,
                            stroke_fill=stroke_fill)
    return im


def fit(im, w, h):
    """Scale an RGBA image to fit w x h (keeping aspect), centred on a transparent w x h canvas."""
    s = min(w / im.width, h / im.height)
    small = im.convert("RGBa").resize((max(1, int(im.width * s)), max(1, int(im.height * s))),
                                      Image.LANCZOS).convert("RGBA")
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(small, ((w - small.width) // 2, (h - small.height) // 2))
    return out


def gantry():
    """The Chainlink gantry at 4x: a banner on two posts, cut into three 64 x 64 frames (left post, banner, right
    post). The frames stand on the ground: the banner fills the top 24 rows (at 1x), the posts run down to the
    bottom, so at the view's gantry scale the banner's underside is 25 px above the road, clear over the karts."""
    W, H = 768, 256
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    blue, white = (55, 91, 210, 255), (245, 245, 250, 255)
    d.rectangle((0, 0, 40, H - 1), fill=(180, 186, 200, 255), outline=OUTLINE + (255,), width=4)
    d.rectangle((W - 41, 0, W - 1, H - 1), fill=(180, 186, 200, 255), outline=OUTLINE + (255,), width=4)
    d.rectangle((36, 6, W - 37, 70), fill=blue, outline=OUTLINE + (255,), width=5)
    for x in range(40, W - 40, 24):                  # checkered band under the banner
        for r, y in enumerate((70, 82)):
            c = white if ((x // 24) + r) % 2 else (20, 20, 24, 255)
            d.rectangle((x, y, x + 23, y + 11), fill=c)
    hx, hy, R = 120, 38, 26                          # the Chainlink hexagon mark
    pts = [(hx + R * np.cos(np.pi / 6 + k * np.pi / 3), hy + R * np.sin(np.pi / 6 + k * np.pi / 3)) for k in range(6)]
    d.polygon(pts, outline=white, width=9)
    t = text_image("CHAINLINK", 44, white, stroke=0)
    im.alpha_composite(t, (170, 38 - t.height // 2))
    t = text_image("FINISH", 40, (255, 220, 90, 255), stroke=0)
    im.alpha_composite(t, (W - 60 - t.width, 38 - t.height // 2))
    small = outline(shrink(im, 4))                   # 192 x 64
    frames = [small.crop((64 * i, 0, 64 * i + 64, 64)) for i in range(3)]
    write_sprite("gantry", frames, keep=[OUTLINE])


def billboard():
    W, H = 256, 128
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x in (40, W - 48):
        d.rectangle((x, 60, x + 8, H - 1), fill=(90, 90, 100, 255))
    d.rounded_rectangle((4, 4, W - 5, 84), 10, fill=(250, 214, 64, 255), outline=OUTLINE + (255,), width=5)
    # the Arkiv mark: a stack of three offset blocks (storage), then the name
    for i in range(3):
        d.rectangle((22 + i * 6, 20 + i * 18, 58 + i * 6, 32 + i * 18), fill=(24, 24, 40, 255))
    t = text_image("ARKIV", 44, (24, 24, 40, 255), stroke=0)
    im.alpha_composite(t, (84, 44 - t.height // 2))
    write_sprite("billboard", [outline(shrink(im, 4))], keep=[OUTLINE])


def orb():
    frames = []
    for glow in (0, 1):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        g = 30 if glow else 27
        d.ellipse((32 - g, 32 - g, 32 + g, 32 + g), fill=(120, 200, 255, 255))
        d.ellipse((8, 8, 56, 56), fill=(236, 240, 248, 255))
        d.ellipse((18, 18, 46, 46), fill=(20, 24, 40, 255))
        d.ellipse((25, 25, 39, 39), fill=(250, 250, 255, 255))
        d.ellipse((14, 12, 26, 22), fill=(255, 255, 255, 255))
        frames.append(outline(shrink(im, 4)))
    write_sprite("orb", frames, keep=[OUTLINE])


def places():
    frames = []
    for i, (n, suf) in enumerate((("1", "ST"), ("2", "ND"), ("3", "RD"), ("4", "TH"))):
        colour = [(255, 214, 40, 255), (220, 226, 236, 255), (230, 150, 80, 255), (170, 180, 200, 255)][i]
        im = Image.new("RGBA", (128, 64), (0, 0, 0, 0))
        big = text_image(n, 64, colour, stroke=5, name="DejaVuSans-BoldOblique.ttf")
        small = text_image(suf, 30, colour, stroke=4, name="DejaVuSans-BoldOblique.ttf")
        x = (128 - big.width - small.width) // 2
        im.alpha_composite(big, (x, (64 - big.height) // 2))
        im.alpha_composite(small, (x + big.width - 2, 4))
        frames.append(shrink(im, 4))
    write_sprite("place", frames, keep=[OUTLINE, (255, 214, 40), (220, 226, 236), (230, 150, 80), (170, 180, 200)])


def speed():
    frames = []
    for level in range(9):
        im = Image.new("RGBA", (32, 8), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 1, 31, 6), fill=OUTLINE + (255,))
        for s in range(8):
            x = 1 + s * 4 - (0 if s < 7 else 0)
            c = (70, 80, 110) if s >= level else [(80, 220, 120), (80, 220, 120), (120, 230, 90), (180, 230, 70),
                                                   (230, 220, 60), (250, 170, 50), (250, 110, 40), (250, 60, 60)][s]
            d.rectangle((x, 2, x + 2, 5), fill=c + (255,))
        frames.append(im)
    write_sprite("speed", frames, keep=[OUTLINE])


def countdown():
    """3, 2, 1, GO! as 64 x 32 frames."""
    frames = []
    for i, word in enumerate(("3", "2", "1", "GO!")):
        colour = (255, 214, 40, 255) if i < 3 else (90, 230, 120, 255)
        im = Image.new("RGBA", (256, 128), (0, 0, 0, 0))
        t = text_image(word, 120, colour, stroke=10, name="DejaVuSans-BoldOblique.ttf")
        im.alpha_composite(fit(t, 250, 124), (3, 2))
        frames.append(shrink(im, 4))
    write_sprite("count", frames, keep=[OUTLINE])


def banners():
    """FINAL LAP and FINISH! (and NEW BEST), each 128 x 32 cut into two 64 x 32 frames."""
    frames = []
    for word, colour in (("FINAL LAP", (255, 214, 40, 255)), ("FINISH!", (255, 255, 255, 255)),
                         ("NEW BEST", (90, 230, 120, 255))):
        im = Image.new("RGBA", (512, 128), (0, 0, 0, 0))
        t = text_image(word, 96, colour, stroke=10, name="DejaVuSans-BoldOblique.ttf")
        im.alpha_composite(fit(t, 500, 120), (6, 4))
        small = shrink(im, 4)
        frames += [small.crop((0, 0, 64, 32)), small.crop((64, 0, 128, 32))]
    write_sprite("banner", frames, keep=[OUTLINE])


def digits():
    """The race clock's glyphs, 8 x 16: white 0-9, ':' and '.' (one sprite per character, swapped as the time runs);
    then the gap to the ghost's 0-9, '.', '+' and '-' in green (ahead), then in red (behind). One palette for all:
    the gap must not take a sprite palette of its own."""
    frames = []
    f = font(50, "DejaVuSansCondensed-Bold.ttf")
    top = f.getbbox("0", stroke_width=6)[1]
    for chars, fill in (("0123456789:.", WHITE), (GAP_GLYPHS, GAP_GREEN), (GAP_GLYPHS, GAP_RED)):
        for ch in chars:
            im = Image.new("RGBA", (32, 64), (0, 0, 0, 0))
            box = f.getbbox(ch, stroke_width=6)
            x = (32 - (box[2] - box[0])) // 2 - box[0]
            ImageDraw.Draw(im).text((x, 4 - top), ch, font=f, fill=fill + (255,), stroke_width=6,
                                    stroke_fill=OUTLINE)       # one baseline for every glyph
            frames.append(shrink(im, 4))
    write_sprite("digits", frames, keep=[OUTLINE, WHITE, GAP_GREEN, GAP_RED])


def logo():
    """MARINE DRIVE over GP, 192 x 64 at 1x, cut into 3 x 2 sprites of 64 x 32."""
    im = Image.new("RGBA", (768, 256), (0, 0, 0, 0))
    top = text_image("MARINE DRIVE", 118, (255, 244, 214, 255), stroke=10, name="DejaVuSansCondensed-BoldOblique.ttf")
    top = top.resize((min(760, top.width), top.height))
    im.alpha_composite(top, ((768 - top.width) // 2, 0))
    # a sunset gradient on the letters
    px = np.array(im)
    a = px[:, :, 3] > 0
    letters = a & (px[:, :, 0] > 200) & (px[:, :, 2] > 150)
    ys = np.nonzero(letters)[0]
    if len(ys):
        t = (np.arange(256) - ys.min()) / max(1, ys.max() - ys.min())
        grad = np.stack([255 - 10 * t, 214 - 110 * t, 90 - 30 * t], 1).clip(0, 255)
        yy = np.nonzero(letters)
        px[yy[0], yy[1], :3] = grad[yy[0]]
    im = Image.fromarray(px)
    gp = text_image("GP", 110, (80, 200, 255, 255), stroke=10, name="DejaVuSans-BoldOblique.ttf")
    im.alpha_composite(gp, ((768 - gp.width) // 2, 134))
    small = shrink(im, 4)                            # 192 x 64
    small = outline(small)
    frames = [small.crop((64 * c, 32 * r, 64 * c + 64, 32 * r + 32)) for r in range(2) for c in range(3)]
    write_sprite("logo", frames, keep=[OUTLINE])


def skyline():
    """Back Bay at dusk: a sky gradient, the Malabar Hill and Nariman Point skylines, the lit Necklace.
    512 x 256 regular BG, 16 colours; only rows 0..HORIZON_ROWS - 1 are drawn (the rest is transparent)."""
    W, rows = 512, 64
    sky = [(252, 196, 120), (246, 160, 110), (226, 124, 120), (170, 100, 140), (104, 80, 140), (60, 56, 110)]
    im = Image.new("RGB", (W, rows), sky[-1])
    d = ImageDraw.Draw(im)
    band = [0, 10, 18, 25, 31, 38, 64]
    for i, c in enumerate(reversed(sky)):
        d.rectangle((0, band[i], W, band[i + 1]), fill=c)
    rng = np.random.default_rng(3)
    far, near, lit = (86, 70, 120), (44, 38, 72), (255, 220, 120)
    x = 0
    while x < W:                                      # far towers
        w = int(rng.integers(10, 26))
        h = int(rng.integers(8, 26))
        d.rectangle((x, rows - 14 - h, x + w, rows - 14), fill=far)
        x += w + int(rng.integers(0, 6))
    x = 0
    while x < W:                                      # near art deco blocks with windows
        w = int(rng.integers(14, 34))
        h = int(rng.integers(4, 18))
        top = rows - 10 - h
        d.rectangle((x, top, x + w, rows - 8), fill=near)
        if rng.random() < 0.3:
            d.rectangle((x + w // 2 - 2, top - 4, x + w // 2 + 2, top), fill=near)
        for wy in range(top + 2, rows - 10, 3):
            for wx in range(x + 2, x + w - 1, 3):
                if rng.random() < 0.25:
                    d.point((wx, wy), fill=lit)
        x += w + int(rng.integers(1, 5))
    d.rectangle((0, rows - 8, W, rows), fill=(40, 90, 150))             # the bay
    for x in range(0, W, 5):                                            # the Queen's Necklace: street lights
        d.point((x, rows - 8), fill=lit)
    img = np.zeros((256, W, 4), np.uint8)
    img[:rows, :, :3] = np.array(im)
    img[:rows, :, 3] = 255
    opaque = img[:, :, 3] > 0
    pal, index = gbaimg.quantize(img[:, :, :3][opaque].astype(np.float32), 15)
    out = np.zeros((256, W), np.uint8)
    out[opaque] = index + 1
    gbaimg.write_bmp8(os.path.join(GFX, "skyline.bmp"), out, [(255, 0, 255)] + pal)
    with open(os.path.join(GFX, "skyline.json"), "w") as f:
        json.dump({"type": "regular_bg", "bpp_mode": "bpp_4", "colors_count": 16}, f, indent=4)
    Image.fromarray(img[:rows, :, :3]).save(os.path.join(GAME, "tests", "out", "skyline.png"))


if __name__ == "__main__":
    os.makedirs(os.path.join(GAME, "tests", "out"), exist_ok=True)
    karts()
    puffs()
    sparks()
    palm()
    gantry()
    billboard()
    orb()
    places()
    speed()
    logo()
    countdown()
    banners()
    digits()
    skyline()
    print("sprites written")
