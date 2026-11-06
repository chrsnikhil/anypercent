"""Mockups for reskinning the 5 arcade games, from real gameplay frames (games/clips/<id>/): each frame recoloured in
two directions, next to the original.

  A  Mainnet night   the look Rebound, Snake and 2048 share: scenery on a navy -> indigo -> ETH blue -> lilac ramp
  B  Testnet neon    scenery on near-black with cyan and magenta neon highlights
In both, gameplay accents keep their meaning: strong reds (danger, hearts) and golds/yellows (collectibles, flags)
stay as they are, so the games read the same.

  python arcade_mockups.py OUT.png"""
import colorsys
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
GAMES = [("ship-it", "SHIP IT!", 8), ("rush-hour", "RUSH HOUR", 6), ("zip", "ZIP", 10),
         ("marine-drive-gp", "MARINE DRIVE GP", 12), ("segfault", "SEGFAULT", 24)]
RAMPS = {
    "A  Mainnet night": [(14, 14, 30), (20, 22, 43), (36, 38, 72), (69, 74, 117), (98, 126, 234), (192, 203, 246),
                         (255, 255, 255)],
    "B  Testnet neon": [(8, 6, 16), (22, 14, 40), (52, 20, 90), (130, 40, 170), (0, 200, 220), (160, 250, 255),
                        (255, 255, 255)],
}


def keep(r, g, b):
    """Accents that carry meaning: saturated reds, golds and yellows stay."""
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return s > 0.55 and v > 0.45 and (h < 0.04 or h > 0.95 or 0.09 < h < 0.18)


def ramp_colour(ramp, lum):
    x = lum * (len(ramp) - 1)
    i = min(len(ramp) - 2, int(x))
    t = x - i
    a, b = ramp[i], ramp[i + 1]
    return tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3))


def recolour(img, ramp):
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b = px[x, y]
            if keep(r, g, b):
                continue
            lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            px[x, y] = ramp_colour(ramp, min(1.0, lum * 1.1))
    return out


def main(out_path):
    S, gap, label_w = 2, 8, 150
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 14) if os.name == "nt" else ImageFont.load_default()
    frames = [Image.open(os.path.join(HERE, gid, f"{gid}-clip-{n:02d}.png")).convert("RGB") for gid, _, n in GAMES]
    fw, fh = max(f.width for f in frames) * S, max(f.height for f in frames) * S
    cols = ["Now"] + list(RAMPS)
    sheet = Image.new("RGB", (label_w + len(cols) * (fw + gap) + gap, 30 + len(GAMES) * (fh + gap) + gap), (24, 24, 32))
    d = ImageDraw.Draw(sheet)
    for c, name in enumerate(cols):
        d.text((label_w + gap + c * (fw + gap), 8), name, font=font, fill=(236, 239, 255))
    for r, ((gid, title, _), f) in enumerate(zip(GAMES, frames)):
        y = 30 + r * (fh + gap)
        d.text((10, y + fh // 2 - 8), title, font=font, fill=(236, 239, 255))
        for c, img in enumerate([f] + [recolour(f, ramp) for ramp in RAMPS.values()]):
            sheet.paste(img.resize((img.width * S, img.height * S), Image.NEAREST), (label_w + gap + c * (fw + gap), y))
    sheet.save(out_path)
    print("->", out_path)


if __name__ == "__main__":
    main(sys.argv[1])
