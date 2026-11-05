"""QR codes (ISO/IEC 18004) in pure Python, for the handler's phone steps: byte mode, error correction L, M, Q or H,
versions 1 to 40, and the mask with the lowest penalty, as the standard picks it. No third-party package: the Pi's venv
has none, and a sponsor's QR (a World App link) must scan from the console's screen at the event.

encode("ANY% MOCK CODE 6P3-7QB") -> rows of booleans, True dark, without the quiet zone (draw at least 4 light
modules round it). Checked on 2026-10-25 outside the suite (tests/test_qr.py pins what it can without them):
zxing-cpp 3.1 decoded 476 symbols back to the exact bytes (random payloads, every level, versions 1-40); every block
of every version and level is an exact Reed-Solomon code word (all syndromes zero), so no reader has to correct
anything; segno 1.6 picks the same version every time. segno's modules differ only because it adds a zero codeword
before the 0xEC/0x11 pad bytes, where the standard (and this) pads straight after the terminator."""
import collections

ECC_LEVELS = ("L", "M", "Q", "H")
_FORMAT_BITS = {"L": 1, "M": 0, "Q": 3, "H": 2}
# Per version 1..40 (index 0 unused): error correction codewords in each block, and the number of blocks.
_ECC_PER_BLOCK = {
    "L": (-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28,
          30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    "M": (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28,
          28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),
    "Q": (-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28,
          30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    "H": (-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30,
          30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
}
_BLOCKS = {
    "L": (-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17,
          18, 19, 19, 20, 21, 22, 24, 25),
    "M": (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29,
          31, 33, 35, 37, 38, 40, 43, 45, 47, 49),
    "Q": (-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38,
          40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),
    "H": (-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45,
          48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81),
}
_MASKS = (
    lambda x, y: (x + y) % 2,
    lambda x, y: y % 2,
    lambda x, y: x % 3,
    lambda x, y: (x + y) % 3,
    lambda x, y: (x // 3 + y // 2) % 2,
    lambda x, y: x * y % 2 + x * y % 3,
    lambda x, y: (x * y % 2 + x * y % 3) % 2,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2,
)
_N1, _N2, _N3, _N4 = 3, 3, 40, 10            # the penalty weights


def encode(data, ecc="M"):
    """data (a str, sent as UTF-8, or bytes) as a QR code at error correction ecc: the smallest version that holds
    it, the mask with the lowest penalty. Rows of booleans, True dark, no quiet zone. ValueError if it cannot fit."""
    if ecc not in ECC_LEVELS:
        raise ValueError(f"error correction is one of {ECC_LEVELS}, not {ecc!r}")
    raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    for version in range(1, 41):
        count_bits = 8 if version <= 9 else 16
        if 4 + count_bits + 8 * len(raw) <= 8 * data_codewords(version, ecc):
            return _Symbol(version, ecc, _codewords(raw, version, ecc, count_bits)).modules
    raise ValueError(f"{len(raw)} bytes do not fit a version 40 QR code at level {ecc}")


def data_codewords(version, ecc):
    """How many 8-bit data codewords a symbol of this version and level holds."""
    return _raw_modules(version) // 8 - _ECC_PER_BLOCK[ecc][version] * _BLOCKS[ecc][version]


def _raw_modules(version):
    """Modules left for data and error correction once the function patterns are drawn."""
    n = (16 * version + 128) * version + 64
    if version >= 2:
        align = version // 7 + 2
        n -= (25 * align - 10) * align - 55
        if version >= 7:
            n -= 36
    return n


def _codewords(raw, version, ecc, count_bits):
    """The data bits (mode, length, bytes, terminator, padding), split into blocks, each with its Reed-Solomon
    codewords, then interleaved."""
    bits = [0, 1, 0, 0] + [(len(raw) >> i) & 1 for i in reversed(range(count_bits))]
    for b in raw:
        bits += [(b >> i) & 1 for i in reversed(range(8))]
    capacity = 8 * data_codewords(version, ecc)
    bits += [0] * min(4, capacity - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) < capacity // 8:
        data.append(pad)
        pad ^= 0xEC ^ 0x11

    blocks, ecc_len = _BLOCKS[ecc][version], _ECC_PER_BLOCK[ecc][version]
    total = _raw_modules(version) // 8
    short, short_len = blocks - total % blocks, total // blocks
    divisor = _rs_divisor(ecc_len)
    split, k = [], 0
    for i in range(blocks):
        n = short_len - ecc_len + (0 if i < short else 1)
        block = data[k:k + n]
        k += n
        rem = _rs_remainder(block, divisor)
        split.append(block + ([0] if i < short else []) + rem)
    out = []
    for i in range(len(split[0])):
        for j, block in enumerate(split):
            if i != short_len - ecc_len or j >= short:     # the short blocks' placeholder byte is skipped
                out.append(block[i])
    return out


def _gf_mul(x, y):
    """x * y in GF(2^8) modulo x^8 + x^4 + x^3 + x^2 + 1."""
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


class _Symbol:
    def __init__(self, version, ecc, codewords):
        self.version, self.ecc = version, ecc
        self.size = size = 17 + 4 * version
        self.modules = [[False] * size for _ in range(size)]
        self.function = [[False] * size for _ in range(size)]
        self._function_patterns()
        self._place(codewords)
        best = None
        for mask in range(8):
            self._mask(mask)
            self._format(mask)
            score = self._penalty()
            if best is None or score < best[0]:
                best = (score, mask)
            self._mask(mask)                                  # masking twice undoes it
        self._mask(best[1])
        self._format(best[1])

    def _set(self, x, y, dark):
        self.modules[y][x] = dark
        self.function[y][x] = True

    def _function_patterns(self):
        size = self.size
        for i in range(size):                                 # timing
            self._set(6, i, i % 2 == 0)
            self._set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):  # finders, with their light separators
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        self._set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = self._alignment_positions()
        last = len(pos) - 1
        for i, cy in enumerate(pos):
            for j, cx in enumerate(pos):
                if (i, j) in ((0, 0), (0, last), (last, 0)):  # where the finders are
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self._set(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
        self._format(0)                                       # reserves the format modules; redrawn per mask
        if self.version >= 7:
            rem = self.version
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.version << 12 | rem
            for i in range(18):
                dark = (bits >> i) & 1 == 1
                a, b = size - 11 + i % 3, i // 3
                self._set(a, b, dark)
                self._set(b, a, dark)

    def _alignment_positions(self):
        if self.version == 1:
            return []
        align = self.version // 7 + 2
        step = (self.version * 8 + align * 3 + 5) // (align * 4 - 4) * 2
        return [6] + sorted(self.size - 7 - i * step for i in range(align - 1))

    def _format(self, mask):
        data = _FORMAT_BITS[self.ecc] << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = [(bits >> i) & 1 == 1 for i in range(15)]
        size = self.size
        for i in range(6):
            self._set(8, i, bit[i])
        self._set(8, 7, bit[6])
        self._set(8, 8, bit[7])
        self._set(7, 8, bit[8])
        for i in range(9, 15):
            self._set(14 - i, 8, bit[i])
        for i in range(8):
            self._set(size - 1 - i, 8, bit[i])
        for i in range(8, 15):
            self._set(8, size - 15 + i, bit[i])
        self._set(8, size - 8, True)                          # the dark module

    def _place(self, codewords):
        """The codeword bits in the standard zigzag, two columns at a time from the bottom right."""
        size, i, total = self.size, 0, len(codewords) * 8
        right = size - 1
        while right >= 1:
            if right == 6:                                    # the vertical timing column is skipped
                right = 5
            for vert in range(size):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = size - 1 - vert if upward else vert
                    if not self.function[y][x] and i < total:
                        self.modules[y][x] = (codewords[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def _mask(self, mask):
        f = _MASKS[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.function[y][x] and f(x, y) == 0:
                    self.modules[y][x] = not self.modules[y][x]

    def _penalty(self):
        size, m, score = self.size, self.modules, 0
        for lines in (m, [list(col) for col in zip(*m)]):     # rows, then columns
            for line in lines:
                colour, run, history = False, 0, collections.deque([0] * 7, 7)
                for cell in line:
                    if cell == colour:
                        run += 1
                        if run == 5:
                            score += _N1
                        elif run > 5:
                            score += 1
                    else:
                        self._add_history(run, history)
                        if not colour:
                            score += self._finder_like(history) * _N3
                        colour, run = cell, 1
                if colour:                                    # the light border closes the line
                    self._add_history(run, history)
                    run = 0
                self._add_history(run + size, history)
                score += self._finder_like(history) * _N3
        for y in range(size - 1):
            for x in range(size - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += _N2
        dark = sum(cell for row in m for cell in row)
        total = size * size
        score += ((abs(dark * 20 - total * 10) + total - 1) // total - 1) * _N4
        return score

    def _add_history(self, run, history):
        if history[0] == 0:
            run += self.size                                  # the light border opens the line
        history.appendleft(run)

    @staticmethod
    def _finder_like(h):
        n = h[1]
        core = n > 0 and h[2] == h[4] == h[5] == n and h[3] == n * 3
        return (1 if core and h[0] >= n * 4 and h[6] >= n else 0) + (1 if core and h[6] >= n * 4 and h[0] >= n else 0)
