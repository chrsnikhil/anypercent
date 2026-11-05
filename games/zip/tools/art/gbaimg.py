"""GBA image helpers for ZIP's art: 15-bit colours, indexed BMPs for Butano, JSON, palette mapping, tile counting."""
import json
import struct

from PIL import Image


class ArtError(Exception):
    """A GBA limit is broken; the build stops."""


def q15(c):
    """An RGB colour exactly representable in the GBA's 15-bit colour."""
    return tuple((v >> 3) << 3 for v in c[:3])


def write_bmp(path, size, pixels, palette):
    """An uncompressed 8-bit indexed BMP whose colour table has exactly len(palette) entries."""
    w, h = size
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


def read_bmp(path):
    """(size, pixel indices, palette) of a BMP written by write_bmp."""
    with open(path, "rb") as f:
        d = f.read()
    offset = struct.unpack_from("<I", d, 10)[0]
    w, h = struct.unpack_from("<ii", d, 18)
    n = struct.unpack_from("<I", d, 46)[0]
    pal = [(d[54 + 4 * i + 2], d[54 + 4 * i + 1], d[54 + 4 * i]) for i in range(n)]
    row = (w + 3) & ~3
    px = bytearray()
    for y in range(h - 1, -1, -1):
        px += d[offset + y * row:offset + y * row + w]
    return (w, h), bytes(px), pal


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=4)
        f.write("\n")


def index_image(img, palette, transparent=0):
    """RGBA image -> indices into palette (a list of RGB, q15 values): alpha < 128 -> transparent, else the exact or
    nearest colour among palette[1:]."""
    img = img.convert("RGBA")
    cache, out = {}, bytearray()
    for r, g, b, a in (img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata()):
        if a < 128:
            out.append(transparent)
            continue
        c = q15((r, g, b))
        if c not in cache:
            cache[c] = min(range(1, len(palette)),
                           key=lambda i: sum((palette[i][k] - c[k]) ** 2 for k in range(3)))
        out.append(cache[c])
    return out


def save_sprite(path, frames, palette, height=None):
    """A vertical strip of equal RGBA frames as a 4 bpp sprite sheet (palette: 16 RGB, index 0 transparent)."""
    if len(palette) > 16:
        raise ArtError("%s: %d colours" % (path, len(palette)))
    w, h = frames[0].size
    sheet = Image.new("RGBA", (w, h * len(frames)), (0, 0, 0, 0))
    for i, fr in enumerate(frames):
        if fr.size != (w, h):
            raise ArtError("%s: frame %d is %s" % (path, i, fr.size))
        sheet.alpha_composite(fr.convert("RGBA"), (0, i * h))
    pal = [q15(c) for c in palette] + [(0, 0, 0)] * (16 - len(palette))
    write_bmp(path, sheet.size, index_image(sheet, pal), pal)
    write_json(path[:-4] + ".json", {"type": "sprite", "height": height or h, "bpp_mode": "bpp_4", "colors_count": 16})
    return sheet


def tiles_of(px, w, h, flips=True):
    """The distinct 8 x 8 tiles of an index image (dedup also by h/v flip if flips)."""
    seen = set()
    count = 0
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            rows = [bytes(px[(ty + r) * w + tx:(ty + r) * w + tx + 8]) for r in range(8)]
            t = b"".join(rows)
            if t in seen:
                continue
            count += 1
            seen.add(t)
            if flips:
                hf = b"".join(r[::-1] for r in rows)
                vf = b"".join(rows[::-1])
                hvf = b"".join(r[::-1] for r in rows[::-1])
                seen.update((hf, vf, hvf))
    return count
