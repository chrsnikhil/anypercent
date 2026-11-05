import ctypes

from conftest import U32


class Hash(ctypes.Structure):
    _fields_ = [("h", U32)]


def fnv(data):
    h = 2166136261
    for b in data:
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h


def test_hash_is_fnv1a_over_little_endian_bytes(kit):
    h = Hash()
    kit.ac_hash_begin(ctypes.byref(h))
    kit.ac_hash_u8(ctypes.byref(h), 0x12)
    kit.ac_hash_u16(ctypes.byref(h), 0x3456)
    kit.ac_hash_u32(ctypes.byref(h), 0x789ABCDE)
    kit.ac_hash_i32(ctypes.byref(h), -2)
    assert h.h == fnv(bytes([0x12, 0x56, 0x34, 0xDE, 0xBC, 0x9A, 0x78, 0xFE, 0xFF, 0xFF, 0xFF]))


def test_rng16_matches_ship_it(kit):
    x, seen = 1, set()
    for _ in range(65535):
        x2 = x ^ ((x << 7) & 0xFFFF); x2 ^= x2 >> 9; x2 ^= (x2 << 8) & 0xFFFF
        assert kit.ac_rng16(x) == x2
        seen.add(x2); x = x2
    assert len(seen) == 65535


def seed_mix(nonce, boots):
    """The reference for ac_seed_mix: 0 without a nonce (the classic, unseeded game), else xorshift32 of the FNV-1a
    hash of (nonce, boots) as little-endian u32s, a zero hash replaced by 0x9E3779B9 (so the result is never 0)."""
    if nonce == 0:
        return 0
    x = fnv(nonce.to_bytes(4, "little") + boots.to_bytes(4, "little")) or 0x9E3779B9
    x ^= (x << 13) & 0xFFFFFFFF; x ^= x >> 17; x ^= (x << 5) & 0xFFFFFFFF
    return x


def test_seed_mix_without_a_nonce_is_the_classic_seed_0(kit):
    assert [kit.ac_seed_mix(0, b) for b in (0, 1, 7, 0xFFFFFFFF)] == [0, 0, 0, 0]


def test_seed_mix_matches_the_reference(kit):
    for nonce, boots in ((1, 1), (0xDEADBEEF, 1), (0xDEADBEEF, 2), (0x12345678, 0xFFFFFFFF), (0xFFFFFFFF, 0)):
        assert kit.ac_seed_mix(nonce, boots) == seed_mix(nonce, boots)


def test_seed_mix_gives_every_boot_its_own_nonzero_seed(kit):
    seeds = [kit.ac_seed_mix(0xC0FFEE11, b) for b in range(1, 2001)]
    assert 0 not in seeds and len(set(seeds)) == 2000


def test_seed_mix_gives_every_nonce_its_own_seed(kit):
    seeds = [kit.ac_seed_mix(n, 1) for n in range(1, 2001)]
    assert 0 not in seeds and len(set(seeds)) == 2000


def test_rng32_is_xorshift32(kit):
    x = 2463534242
    for _ in range(1000):
        y = x ^ ((x << 13) & 0xFFFFFFFF); y ^= y >> 17; y ^= (y << 5) & 0xFFFFFFFF
        assert kit.ac_rng32(x) == y
        x = y
