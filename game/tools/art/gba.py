"""GBA conversion helpers: shrink the 4x renders, quantize to 15-bit colour, count tiles, write the
indexed BMPs Butano reads, and build 4 bpp sprite sheets."""
import json
import struct

from PIL import Image


class ArtError(Exception):
    """A GBA limit is broken; the build stops."""


BACKDROP = (24, 24, 40)              # palette index 0: the navy outside the room (exact in 15-bit colour)
HUD_BG, HUD_LINE, BAR_EDGE = 240, 241, 242
UI_COLOURS = {HUD_BG: (16, 16, 32), HUD_LINE: (64, 72, 104), BAR_EDGE: (120, 128, 160)}
ROOM_TILE_LIMIT = 4096


def q15(v):
    return (v >> 3) << 3


def to15(img):
    """Drop each RGB channel to 5 bits (the GBA's colour depth); alpha is kept."""
    bands = list(img.split())
    for i in range(3):
        bands[i] = bands[i].point(q15)
    return Image.merge(img.mode, bands)


def shrink(img, scale=4):
    """4x render -> GBA size, filtering with premultiplied alpha so edges do not pick up dark fringes."""
    w, h = img.size
    return img.convert("RGBa").resize((w // scale, h // scale), Image.LANCZOS).convert("RGBA")


def quantize_room(room, colours=239):
    """Quantize a GBA-size RGBA room render into one 256-entry palette: index 0 is the backdrop (every pixel
    with alpha < 128), 1..colours the scene, 240..255 reserved."""
    flat = Image.new("RGBA", room.size, BACKDROP + (255,))
    flat.alpha_composite(room)
    q = to15(flat.convert("RGB")).quantize(colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    raw = q.getpalette()[:colours * 3]
    palette = [BACKDROP] + [tuple(q15(c) for c in raw[i:i + 3]) for i in range(0, len(raw), 3)]
    palette += [(0, 0, 0)] * (256 - len(palette))
    for index, colour in UI_COLOURS.items():
        palette[index] = colour
    src, alpha = q.tobytes(), room.getchannel("A").tobytes()
    return palette, bytearray(v + 1 if alpha[i] >= 128 else 0 for i, v in enumerate(src))


def room_tiles(px, w, h):
    """Cut an index image (w, h multiples of 8) into deduplicated 64-byte 8 bpp tiles, first-seen order.
    Returns (tiles, cells): cells[cy * (w // 8) + cx] is the tile index of that 8 x 8 cell."""
    tiles, index, cells = [], {}, []
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            t = b"".join(bytes(px[(ty + r) * w + tx:(ty + r) * w + tx + 8]) for r in range(8))
            if t not in index:
                index[t] = len(tiles)
                tiles.append(t)
            cells.append(index[t])
    return tiles, cells


def unique_tiles(px, w, h):
    tiles = set()
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            tiles.add(b"".join(bytes(px[(ty + r) * w + tx:(ty + r) * w + tx + 8]) for r in range(8)))
    return len(tiles)


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


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=4)
        f.write("\n")


def sprite_sheet(frames, check_edges=True, palette=None):
    """Frames (RGBA, all the same size) -> one vertical strip with a shared 16-entry palette: index 0 is
    transparent (alpha < 128), then up to 15 colours. With check_edges, a frame with an opaque pixel on
    its border is rejected, because the art would be clipped."""
    w, h = frames[0].size
    opaque = []
    for n, fr in enumerate(frames):
        alpha, rgb = fr.getchannel("A").tobytes(), fr.convert("RGB").tobytes()
        for i in range(w * h):
            if alpha[i] >= 128:
                x, y = i % w, i // w
                if check_edges and (x in (0, w - 1) or y in (0, h - 1)):
                    raise ArtError("sprite frame %d is clipped at (%d, %d)" % (n, x, y))
                opaque.append(rgb[i * 3:i * 3 + 3])
    if not opaque:
        raise ArtError("sprite frames are empty")
    if palette is None:
        strip = to15(Image.frombytes("RGB", (len(opaque), 1), b"".join(opaque)))
        raw = strip.quantize(15, method=Image.Quantize.MEDIANCUT).getpalette()[:15 * 3]
        colours = [tuple(q15(c) for c in raw[i:i + 3]) for i in range(0, len(raw), 3)]
        palette = [(248, 0, 248)] + colours + [(0, 0, 0)] * (15 - len(colours))
    else:
        colours = list(palette[1:16])
    mapper = Image.new("P", (1, 1))
    mapper.putpalette(sum((list(colours[i % len(colours)]) for i in range(256)), []))
    pixels = bytearray()
    for fr in frames:
        idx = to15(fr.convert("RGB")).quantize(palette=mapper, dither=Image.Dither.NONE).tobytes()
        alpha = fr.getchannel("A").tobytes()
        pixels += bytes(idx[i] % len(colours) + 1 if alpha[i] >= 128 else 0 for i in range(w * h))
    return list(palette), pixels, (w, h * len(frames))
