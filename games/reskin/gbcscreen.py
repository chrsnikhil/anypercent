"""A Game Boy Color full-screen picture (Rebound's title): tiles in two VRAM banks + tile map + attribute map +
palettes <-> one PNG. Editing the picture and writing it back keeps the map and attributes; only the tiles under
changed pixels are rewritten, and a tile shared with an unchanged spot gets a free slot of its own."""
from gbgfx import tiles_from_2bpp, tile_to_2bpp

W, H = 20, 18


def palettes(pal_bytes):
    out = []
    for p in range(len(pal_bytes) // 8):
        cols = []
        for c in range(4):
            v = pal_bytes[p * 8 + c * 2] | pal_bytes[p * 8 + c * 2 + 1] << 8
            cols.append(tuple(round(((v >> s) & 31) * 255 / 31) for s in (0, 5, 10)))
        out.append(cols)
    return out


class Screen:
    def __init__(self, bank0, bank1, tmap, attr, pal_bytes, map_width=None):
        self.banks = [tiles_from_2bpp(bank0), tiles_from_2bpp(bank1)]
        self.stride = map_width or (len(tmap) // H)
        self.tmap, self.attr = bytearray(tmap), bytearray(attr)
        self.pals = palettes(pal_bytes)

    def cell(self, cx, cy):
        i = cy * self.stride + cx
        a = self.attr[i]
        return self.tmap[i], (a >> 3) & 1, a & 7, bool(a & 0x20), bool(a & 0x40)   # tile, bank, pal, xflip, yflip

    def tile_pixels(self, cx, cy):
        t, bank, pal, xf, yf = self.cell(cx, cy)
        rows = [r[:] for r in self.banks[bank][t]]
        if xf:
            rows = [r[::-1] for r in rows]
        if yf:
            rows = rows[::-1]
        return rows, pal

    def image(self):
        from PIL import Image
        img = Image.new("RGB", (W * 8, H * 8))
        for cy in range(H):
            for cx in range(W):
                rows, pal = self.tile_pixels(cx, cy)
                for y, row in enumerate(rows):
                    for x, c in enumerate(row):
                        img.putpixel((cx * 8 + x, cy * 8 + y), self.pals[pal][c])
        return img

    def users(self):
        """(bank, tile) -> map cells that show it."""
        u = {}
        for cy in range(H):
            for cx in range(W):
                t, bank, *_ = self.cell(cx, cy)
                u.setdefault((bank, t), []).append((cx, cy))
        return u

    def apply(self, img, spare=()):
        """Write an edited picture back: each changed cell gets its new pixels as colour indexes of the cell's own
        palette (nearest colour). A changed cell whose tile is shared moves to a free tile: an unused one in its
        bank, else one of `spare` [(bank, tile index)] (the attribute map follows the bank). Returns the cells
        changed."""
        changed = []
        users = self.users()
        free = {b: [(b, t) for t in range(len(self.banks[b])) if (b, t) not in users] for b in (0, 1)}
        spare = list(spare)
        for cy in range(H):
            for cx in range(W):
                old, pal = self.tile_pixels(cx, cy)
                cols = self.pals[pal]
                new = [[min(range(4), key=lambda k: sum((a - b) ** 2 for a, b in zip(img.getpixel((cx * 8 + x,
                       cy * 8 + y)), cols[k]))) for x in range(8)] for y in range(8)]
                if new == old:
                    continue
                t, bank, _, xf, yf = self.cell(cx, cy)
                if xf:
                    new = [r[::-1] for r in new]
                if yf:
                    new = new[::-1]
                if len(users[(bank, t)]) > 1:                      # shared: move this cell to a free tile
                    if free[bank]:
                        bank2, t2 = free[bank].pop(0)
                    elif spare:
                        bank2, t2 = spare.pop(0)
                    else:
                        raise RuntimeError(f"no free tile for cell {cx},{cy}")
                    users[(bank, t)].remove((cx, cy))
                    users[(bank2, t2)] = [(cx, cy)]
                    i = cy * self.stride + cx
                    self.tmap[i] = t2
                    self.attr[i] = (self.attr[i] & ~0x08) | (0x08 if bank2 else 0)
                    while len(self.banks[bank2]) <= t2:
                        self.banks[bank2].append([[0] * 8 for _ in range(8)])
                    bank, t = bank2, t2
                self.banks[bank][t] = new
                changed.append((cx, cy))
        return changed

    def tiles_bytes(self, bank):
        return b"".join(tile_to_2bpp(t) for t in self.banks[bank])
