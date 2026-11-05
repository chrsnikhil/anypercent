"""GBA image helpers for MARINE DRIVE GP's art tools: 15-bit colour, palette quantisation, indexed BMPs for Butano."""
import numpy as np
from PIL import Image


def q15(rgb):
    """0..255 channels -> the GBA's 5-bit levels (kept as 0..248 multiples of 8), rounding to nearest."""
    return (np.clip(np.round(np.asarray(rgb, np.float32) / 8.0), 0, 31) * 8).astype(np.uint8)


def quantize(pixels, colours):
    """pixels [N, 3] (0..255) -> (palette [(r, g, b)] of at most `colours`, index [N]). Median cut, no dither."""
    px = q15(pixels)
    uniq, inv = np.unique(px.reshape(-1, 3), axis=0, return_inverse=True)
    inv = inv.ravel()
    if len(uniq) <= colours:
        return [tuple(int(c) for c in u) for u in uniq], inv.astype(np.uint8)
    im = Image.fromarray(uniq.reshape(1, -1, 3), "RGB")
    q = im.quantize(colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = q.getpalette()[:colours * 3]
    pal = [tuple(int(c) for c in q15(raw[i:i + 3])) for i in range(0, len(raw), 3)]
    return pal, np.array(q.getdata(), np.uint8)[inv]


def write_bmp8(path, index, palette, colours=256):
    """An 8 bpp indexed BMP (what Butano's grit reads): index [H, W] uint8, palette padded to 256 entries."""
    im = Image.fromarray(np.asarray(index, np.uint8), "P")
    pal = list(palette) + [(0, 0, 0)] * (256 - len(palette))
    im.putpalette([c for rgb in pal for c in rgb])
    im.save(path)
