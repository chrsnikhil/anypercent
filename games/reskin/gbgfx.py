"""Game Boy graphics in and out: 2bpp tiles <-> PNG, and DevEd's WLE compression (Rebound) both ways.

Used by the web3 reskins (games/reskin/<game>/): decode the original art to look at it, draw the new art as PNGs
in the same 4 shades, encode them back to exactly the bytes the game includes.

  python gbgfx.py dump <file.2bpp|file.2bpp.wle> <out.png> [--sprite16] [--wide N]"""
import sys

from PIL import Image

SHADES = [(255, 255, 255), (170, 170, 170), (85, 85, 85), (0, 0, 0)]      # colour index 0..3, light to dark


# --- WLE (Tools/wlenc.py in ReboundGB; the decoder mirrors Engine/WLE_Decode.asm) -----------------------------

def wle_decode(data):
    out, hold, i = bytearray(), 0, 0
    while True:
        b = data[i]
        i += 1
        if b == 0xFF:
            return bytes(out)
        kind = b >> 5
        if kind == 0:                                   # literal, short
            n = (b & 31) + 1
            out += data[i:i + n]
            i += n
        elif kind == 1:                                 # literal, long
            n = ((b & 31) << 8 | data[i]) + 1
            i += 1
            out += data[i:i + n]
            i += n
        elif kind == 2:                                 # fill with the held byte
            out += bytes([hold]) * ((b & 31) + 1)
        elif kind == 3:                                 # fill with a new byte
            hold = data[i]
            i += 1
            out += bytes([hold]) * ((b & 31) + 1)
        elif kind == 4:                                 # count up from the held byte
            n = (b & 31) + 1
            out += bytes((hold + k) & 255 for k in range(n))
            hold = (hold + n) & 255
        elif kind == 5:                                 # count up from a new byte
            start = data[i]
            i += 1
            n = (b & 31) + 1
            out += bytes((start + k) & 255 for k in range(n))
            hold = (start + n) & 255
        else:                                           # copy from up to 256 bytes back
            n = (b & 63) + 1
            src = len(out) - (data[i] + 1)
            i += 1
            for k in range(n):
                out.append(out[src + k])


def wle_encode(data, wlenc_path):
    """The game's own encoder, so the bytes are what its build would make."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("wlenc", wlenc_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return bytes(mod.encodeWLE(bytearray(data)))


# --- tiles -------------------------------------------------------------------------------------------------------

def tiles_from_2bpp(data):
    """List of 8x8 tiles, each 8 rows of 8 colour indexes."""
    tiles = []
    for t in range(len(data) // 16):
        rows = []
        for y in range(8):
            lo, hi = data[t * 16 + y * 2], data[t * 16 + y * 2 + 1]
            rows.append([((lo >> (7 - x)) & 1) | (((hi >> (7 - x)) & 1) << 1) for x in range(8)])
        tiles.append(rows)
    return tiles


def tile_to_2bpp(rows):
    out = bytearray()
    for row in rows:
        lo = hi = 0
        for x, c in enumerate(row):
            lo |= (c & 1) << (7 - x)
            hi |= ((c >> 1) & 1) << (7 - x)
        out += bytes([lo, hi])
    return bytes(out)


# 16x16 objects in 8x16 sprite mode: left column (top, bottom), then right column (top, bottom)
SPRITE16_ORDER = [(0, 0), (0, 8), (8, 0), (8, 8)]


def sprites16_to_image(data, per_row=8, palette=SHADES, scale=1):
    tiles = tiles_from_2bpp(data)
    frames = len(tiles) // 4
    rows = (frames + per_row - 1) // per_row
    img = Image.new("RGB", (per_row * 16, rows * 16), (255, 0, 255))
    for f in range(frames):
        ox, oy = (f % per_row) * 16, (f // per_row) * 16
        for k, (dx, dy) in enumerate(SPRITE16_ORDER):
            for y, row in enumerate(tiles[f * 4 + k]):
                for x, c in enumerate(row):
                    img.putpixel((ox + dx + x, oy + dy + y), palette[c])
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST) if scale > 1 else img


def tiles_to_image(data, per_row=16, palette=SHADES, scale=1):
    tiles = tiles_from_2bpp(data)
    rows = (len(tiles) + per_row - 1) // per_row
    img = Image.new("RGB", (per_row * 8, rows * 8), (255, 0, 255))
    for t, tile in enumerate(tiles):
        for y, row in enumerate(tile):
            for x, c in enumerate(row):
                img.putpixel(((t % per_row) * 8 + x, (t // per_row) * 8 + y), palette[c])
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST) if scale > 1 else img


def indexes_from_image(img, palette):
    """Colour index per pixel: each pixel's nearest palette colour."""
    img = img.convert("RGB")
    def nearest(p):
        return min(range(len(palette)), key=lambda i: sum((a - b) ** 2 for a, b in zip(p, palette[i])))
    cache = {}
    out = []
    for y in range(img.height):
        row = []
        for x in range(img.width):
            p = img.getpixel((x, y))
            if p not in cache:
                cache[p] = nearest(p)
            row.append(cache[p])
        out.append(row)
    return out


def sprites16_from_indexes(grid, frames):
    """Frames laid out left to right in a 16-px-tall strip (wrapping every len(grid[0])//16 frames)."""
    per_row = len(grid[0]) // 16
    out = bytearray()
    for f in range(frames):
        ox, oy = (f % per_row) * 16, (f // per_row) * 16
        for dx, dy in SPRITE16_ORDER:
            out += tile_to_2bpp([grid[oy + dy + y][ox + dx:ox + dx + 8] for y in range(8)])
    return bytes(out)


def tiles_from_indexes(grid, count):
    per_row = len(grid[0]) // 8
    out = bytearray()
    for t in range(count):
        ox, oy = (t % per_row) * 8, (t // per_row) * 8
        out += tile_to_2bpp([grid[oy + y][ox:ox + 8] for y in range(8)])
    return bytes(out)


def main(argv):
    if len(argv) >= 3 and argv[0] == "dump":
        data = open(argv[1], "rb").read()
        if argv[1].endswith(".wle"):
            data = wle_decode(data)
        wide = int(argv[argv.index("--wide") + 1]) if "--wide" in argv else 8
        img = sprites16_to_image(data, wide) if "--sprite16" in argv else tiles_to_image(data, wide)
        img.resize((img.width * 4, img.height * 4), Image.NEAREST).save(argv[2])
        print(argv[2], img.size)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
