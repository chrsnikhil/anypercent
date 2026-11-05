"""qr.py against the standard's own numbers: data capacity per version and level, the version a payload needs, the
finder and timing patterns, and format information that is a valid BCH code word naming the level. (Decoding by a real
reader is checked outside the suite: see qr.py's docstring.)"""
import hashlib

import pytest

from arca_launcher import qr


def test_data_capacity_matches_the_standard():
    for version, want in ((1, (19, 16, 13, 9)), (10, (274, 216, 154, 122)), (40, (2956, 2334, 1666, 1276))):
        assert tuple(qr.data_codewords(version, ecc) for ecc in qr.ECC_LEVELS) == want, version


def test_the_smallest_version_that_holds_the_bytes_is_used():
    assert len(qr.encode("x" * 14, "M")) == 21                    # version 1-M holds 14 bytes
    assert len(qr.encode("x" * 15, "M")) == 25
    assert len(qr.encode("x" * 17, "L")) == 21
    assert len(qr.encode("x" * 2953, "L")) == 177                 # version 40-L, the largest of all
    with pytest.raises(ValueError):
        qr.encode("x" * 2954, "L")
    with pytest.raises(ValueError):
        qr.encode("x", "Z")


def test_utf8_text_counts_its_bytes():
    assert qr.encode("é" * 7, "M") == qr.encode("é".encode() * 7, "M")
    assert len(qr.encode("é" * 7, "M")) == 21 and len(qr.encode("é" * 8, "M")) == 25


def _finder_at(m, x0, y0):
    return all(m[y0 + dy][x0 + dx] == (max(abs(dx - 3), abs(dy - 3)) != 2) for dy in range(7) for dx in range(7))


def test_finders_timing_and_format_information():
    for text, ecc in (("ANY% MOCK CODE 6P3-7QB", "M"), ("https://example.org/" + "a" * 120, "L"), ("hi", "H")):
        m = qr.encode(text, ecc)
        n = len(m)
        assert (n - 17) % 4 == 0
        assert _finder_at(m, 0, 0) and _finder_at(m, n - 7, 0) and _finder_at(m, 0, n - 7)
        assert [m[6][x] for x in range(8, n - 8)] == [x % 2 == 0 for x in range(8, n - 8)]
        assert m[n - 8][8], "the dark module"
        bits = [m[i][8] for i in range(6)] + [m[7][8], m[8][8], m[8][7]] + [m[8][14 - i] for i in range(9, 15)]
        word = sum(1 << i for i, b in enumerate(bits) if b) ^ 0x5412
        rem = word >> 10
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        assert word & 0x3FF == rem & 0x3FF, "not a BCH code word"
        assert word >> 13 == {"L": 1, "M": 0, "Q": 3, "H": 2}[ecc]
        second = [m[8][n - 1 - i] for i in range(8)] + [m[n - 15 + i][8] for i in range(8, 15)]
        assert second == [(word ^ 0x5412) >> i & 1 == 1 for i in range(15)], "the two copies agree"


def test_the_same_text_gives_the_same_code():
    """Pinned once zxing-cpp decoded it and its Reed-Solomon blocks checked out (qr.py's docstring)."""
    m = qr.encode("ANY% MOCK CODE 6P3-7QB", "M")
    digest = hashlib.sha256("".join("1" if c else "0" for row in m for c in row).encode()).hexdigest()
    assert digest == PINNED


PINNED = "3ad2fd3e096c16f5a604543d300a2a93c00085aff545dbf29908b05b54591e9d"
