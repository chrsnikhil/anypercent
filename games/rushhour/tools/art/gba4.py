"""GBA art helpers for RUSH HOUR: 15-bit colour, indexed BMPs Butano reads, 4 bpp sprite sheets and 4 bpp
multi-palette backgrounds (Butano "bpp_4_manual": every 8 x 8 tile uses one 16-colour bank, index // 16)."""
import json
import struct

from PIL import Image


class ArtError(Exception):
    """A GBA limit is broken; the build stops."""


TRANSPARENT = (248, 0, 248)          # sprite palette index 0 (never drawn)


def q15(v):
    return (v >> 3) << 3


def c15(rgb):
    return tuple(q15(c) for c in rgb[:3])


def write_bmp(path, size, pixels, palette):
    """An uncompressed 8-bit indexed BMP whose colour table has exactly len(palette) entries."""
    w, h = size
    assert len(pixels) == w * h, (len(pixels), w, h)
    row = (w + 3) & ~3
    data = bytearray()
    for y in range(h - 1, -1, -1):
        data += bytes(pixels[y * w:(y + 1) * w]) + b"\0" * (row - w)
    offset = 14 + 40 + 4 * len(palette)
    with open(path, "wb") as f:
        f.write(b"BM" + struct.pack("<IHHI", offset + len(data), 0, 0, offset))
        f.write(struct.pack("<IiiHHIIiiII", 40, w, h, 1, 8, 0, len(data), 2835, 2835, len(palette), len(palette)))
        for r, g, b in palette:
            f.write(bytes((b, g, r, 0)))
        f.write(data)


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=4)
        f.write("\n")


def _nearest(colours, rgb):
    best, bi = None, 0
    for i, c in enumerate(colours):
        d = (c[0] - rgb[0]) ** 2 + (c[1] - rgb[1]) ** 2 + (c[2] - rgb[2]) ** 2
        if best is None or d < best:
            best, bi = d, i
    return bi


def reduce_colours(colours, n):
    """At most n colours from a list (median cut over the list, each colour counted once)."""
    colours = list(dict.fromkeys(colours))
    if len(colours) <= n:
        return colours
    strip = Image.new("RGB", (len(colours), 1))
    strip.putdata(colours)
    raw = strip.quantize(n, method=Image.Quantize.MEDIANCUT).getpalette()[:n * 3]
    return list(dict.fromkeys(c15(raw[i:i + 3]) for i in range(0, len(raw), 3)))


def sprite_sheet(frames):
    """RGBA frames (same size) -> (palette[16], pixels, (w, h * n)): a vertical strip, index 0 transparent
    (alpha < 128), then up to 15 colours shared by every frame."""
    w, h = frames[0].size
    seen = []
    for fr in frames:
        assert fr.size == (w, h)
        for p in fr.getdata():
            if p[3] >= 128:
                seen.append(c15(p))
    if not seen:
        raise ArtError("empty sprite")
    colours = reduce_colours(seen, 15)
    lookup = {}
    pixels = bytearray()
    for fr in frames:
        for p in fr.getdata():
            if p[3] < 128:
                pixels.append(0)
            else:
                k = c15(p)
                if k not in lookup:
                    lookup[k] = _nearest(colours, k) + 1
                pixels.append(lookup[k])
    palette = [TRANSPARENT] + colours + [(0, 0, 0)] * (15 - len(colours))
    return palette, pixels, (w, h * len(frames))


def write_sprite(folder, name, frames, height=None):
    palette, pixels, size = sprite_sheet(frames)
    write_bmp("%s/%s.bmp" % (folder, name), size, pixels, palette)
    write_json("%s/%s.json" % (folder, name),
               {"type": "sprite", "height": height or frames[0].size[1], "bpp_mode": "bpp_4", "colors_count": 16})
    return size


def bg4(img, max_banks, backdrop):
    """An RGBA image (w, h multiples of 8) -> (pixels, palette) for a 4 bpp multi-palette regular BG: transparent
    pixels (alpha < 128) show what is behind; each 8 x 8 tile's colours go into one of at most max_banks banks of
    15 colours (a tile with more than 15 is reduced to 15). Palette entry bank * 16 is the backdrop colour."""
    w, h = img.size
    assert w % 8 == 0 and h % 8 == 0
    data = list(img.getdata())
    tiles = []                           # (x, y, colour set)
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            cs = []
            for y in range(8):
                for x in range(8):
                    p = data[(ty + y) * w + tx + x]
                    if p[3] >= 128:
                        cs.append(c15(p))
            tiles.append((tx, ty, reduce_colours(cs, 15) if cs else []))
    banks = []                           # lists of colours
    tile_bank = {}
    order = sorted(range(len(tiles)), key=lambda i: -len(tiles[i][2]))
    for i in order:
        cs = set(tiles[i][2])
        if not cs:
            tile_bank[i] = 0
            continue
        best, bi = None, -1
        for b, bank in enumerate(banks):
            grow = len(cs - set(bank))
            if len(bank) + grow <= 15 and (best is None or grow < best):
                best, bi = grow, b
        if bi < 0:
            banks.append([])
            bi = len(banks) - 1
            if len(banks) > max_banks:
                raise ArtError("background needs more than %d palette banks" % max_banks)
        for c in tiles[i][2]:
            if c not in banks[bi]:
                banks[bi].append(c)
        tile_bank[i] = bi
    if not banks:
        banks = [[(0, 0, 0)]]
    pixels = bytearray(w * h)
    for i, (tx, ty, cs) in enumerate(tiles):
        b = tile_bank[i]
        bank = banks[b]
        cache = {}
        for y in range(8):
            for x in range(8):
                p = data[(ty + y) * w + tx + x]
                if p[3] < 128:
                    v = b * 16
                else:
                    k = c15(p)
                    if k not in cache:
                        cache[k] = b * 16 + 1 + (bank.index(k) if k in bank else _nearest(bank, k))
                    v = cache[k]
                pixels[(ty + y) * w + tx + x] = v
    palette = []
    for bank in banks:
        palette += [c15(backdrop)] + bank + [(0, 0, 0)] * (15 - len(bank))
    return pixels, palette


def write_bg(folder, name, img, max_banks, backdrop):
    pixels, palette = bg4(img, max_banks, backdrop)
    write_bmp("%s/%s.bmp" % (folder, name), img.size, pixels, palette)
    write_json("%s/%s.json" % (folder, name), {"type": "regular_bg", "bpp_mode": "bpp_4_manual"})
    return len(palette) // 16


def unique_tiles(pixels, w, h, flips=True):
    """Unique 8 x 8 tiles of an index image, counting flipped copies as one (as Butano's reduction does)."""
    seen = set()
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            rows = [bytes(pixels[(ty + y) * w + tx:(ty + y) * w + tx + 8]) for y in range(8)]
            variants = [tuple(rows)]
            if flips:
                variants += [tuple(r[::-1] for r in rows), tuple(rows[::-1]), tuple(r[::-1] for r in rows[::-1])]
            if not any(v in seen for v in variants):
                seen.add(variants[0])
    return len(seen)
