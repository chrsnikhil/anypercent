"""The ETHGlobal Mumbai logo as pixel art: key out its cream background, box-downsample, limit the palette
and draw a 1 px cream outline so the maroon lettering reads on the dark office."""
import os

from PIL import Image, ImageFilter

GAME = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE = os.path.join(GAME, "art", "source", "ethglobal-mumbai-logo.png")
OUTLINE = (255, 236, 200, 255)
KEY_DISTANCE = 34


def load_keyed(path):
    """The logo with its background (the corner colour, and its faint pattern) made transparent, cropped."""
    src = Image.open(path).convert("RGBA")
    bg = src.getpixel((0, 0))[:3]
    px = src.load()
    for y in range(src.height):
        for x in range(src.width):
            r, g, b, _ = px[x, y]
            if max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2])) < KEY_DISTANCE:
                px[x, y] = (r, g, b, 0)
    out = Image.new("RGBA", (src.width + 2, src.height + 2), (0, 0, 0, 0))
    out.alpha_composite(src.crop(src.getchannel("A").getbbox()), (1, 1))
    return out.crop(out.getchannel("A").getbbox())


def pixelate(img, width, colours=13):
    """Box-downsample to `width` px, hard alpha, at most `colours` colours in 15-bit colour, plus the outline
    (the result is 2 px wider and taller than `width` x height)."""
    h = round(img.height * width / img.width)
    small = img.convert("RGBa").resize((width, h), Image.BOX).convert("RGBA")
    alpha = small.getchannel("A").point(lambda v: 255 if v >= 110 else 0)
    rgb = small.convert("RGB").quantize(colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    rgb = rgb.convert("RGB").point(lambda v: (v >> 3) << 3)
    art = Image.merge("RGBA", (*rgb.split(), alpha))
    ring = Image.new("L", (width + 2, h + 2), 0)
    ring.paste(alpha, (1, 1))
    ring = ring.filter(ImageFilter.MaxFilter(3))
    out = Image.new("RGBA", ring.size, (0, 0, 0, 0))
    out.paste(Image.new("RGBA", ring.size, OUTLINE), (0, 0), ring)
    out.alpha_composite(art, (1, 1))
    return out
