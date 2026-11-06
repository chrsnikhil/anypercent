"""Launcher art for the Browser app entry (not a game, so no ROM to film): a globe tile in the launcher's
Ethereum colours, and the browser's own screenshots from the device for the info page.

  python make_art.py OUT_DIR SHOT.png [SHOT.png ...]      (shots: 800x480 grabs, drmgrab.py on the device)

Writes browser-tile.png (160x144, like a game frame), browser-shot0..2.png and browser-bg.png."""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

NAVY, LILAC, ETH, ICE = (20, 22, 43), (192, 203, 246), (98, 126, 234), (236, 239, 255)
W, H, S = 160, 144, 6
FONTS = ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def font(size):
    for f in FONTS:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def tile():
    img = Image.new("RGB", (W * S, H * S), NAVY)
    d = ImageDraw.Draw(img)
    cx, cy, r = 80 * S, 62 * S, 40 * S
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ETH)
    lw = 3 * S
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=ICE, width=lw)
    for k in (0.45, 0.8):                                          # meridians
        d.ellipse((cx - r * k, cy - r, cx + r * k, cy + r), outline=ICE, width=lw)
    d.line((cx, cy - r, cx, cy + r), fill=ICE, width=lw)
    for f in (-0.5, 0, 0.5):                                       # parallels
        y = cy + f * r
        half = (r * r - (f * r) ** 2) ** 0.5
        d.line((cx - half, y, cx + half, y), fill=ICE, width=lw)
    d.text((80 * S, 124 * S), "WEB", font=font(16 * S), fill=LILAC, anchor="mm")
    return img.resize((W, H), Image.LANCZOS)


def shot(path):
    """An 800x480 grab as a 160x144 frame: scaled to the width, centred on navy."""
    src = Image.open(path).convert("RGB")
    h = round(src.height * W / src.width)
    out = Image.new("RGB", (W, H), NAVY)
    out.paste(src.resize((W, h), Image.LANCZOS), (0, (H - h) // 2))
    return out


def main():
    out, shots = sys.argv[1], sys.argv[2:]
    os.makedirs(out, exist_ok=True)
    t = tile()
    t.save(os.path.join(out, "browser-tile.png"))
    for i, p in enumerate(shots[:3]):
        shot(p).save(os.path.join(out, f"browser-shot{i}.png"))
    bg = t.crop((0, 22, 160, 118)).resize((200, 120), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3))
    bg.point(lambda v: round(v * 0.35)).save(os.path.join(out, "browser-bg.png"))
    print("browser art in", out)


if __name__ == "__main__":
    main()
