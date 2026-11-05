"""Cartridge save layout shared by the arcade games (mirror of arcade/src/ac_save.c)."""
import struct

SIZE, BASE = 32768, 0x0100
VERSION = 2                     # AC_SAVE_VERSION: any other version reads as unformatted
PROFILE, BEST, RUN, GHOST = 1, 2, 3, 4
TRUNCATED = 1
OFF = {PROFILE: 0x0200, BEST: 0x0240, RUN: 0x0400, GHOST: 0x3C00}
CAP = {PROFILE: 64, BEST: 32, RUN: 14336, GHOST: 16384}


def blank():
    return bytearray(b"\xff" * SIZE)


def checksum(b):
    return (0x5A5A + sum(b)) & 0xFFFF


def _header_ok(save):
    return bytes(save[BASE:BASE + 4]) == b"ACSV" and struct.unpack_from("<H", save, BASE + 4)[0] == VERSION


def fmt(save, game):
    struct.pack_into("<4sH4s", save, BASE, b"ACSV", VERSION, game)
    for s in (PROFILE, BEST, RUN, GHOST):
        struct.pack_into("<HHHHB3x", save, BASE + 10 + (s - 1) * 12, OFF[s], CAP[s], 0, 0, 0)


def put(save, sec, data, flags=0):
    if not _header_ok(save) or len(data) > CAP[sec]:
        return False
    save[OFF[sec]:OFF[sec] + len(data)] = data
    struct.pack_into("<HHHHB3x", save, BASE + 10 + (sec - 1) * 12, OFF[sec], CAP[sec], len(data), checksum(data), flags)
    return True


def get(save, game, sec):
    if not _header_ok(save) or bytes(save[BASE + 6:BASE + 10]) != game:
        return None
    off, cap, n, s, flags = struct.unpack_from("<HHHHB", save, BASE + 10 + (sec - 1) * 12)
    if off != OFF[sec] or n == 0 or n > CAP[sec]:
        return None
    data = bytes(save[off:off + n])
    return (data, flags) if checksum(data) == s else None


def profile_bytes(name, tag, trophies, seed_nonce=0):
    """Profile payload: name[12], tag[8], trophies u32, seed nonce u32, boot count u32 (0: the ROM bumps it every
    boot), 32 reserved. A non-zero nonce seeds every run (ac_seed_mix(nonce, boots)); 0 keeps the classic seed 0."""
    return struct.pack("<12s8sIII32x", name.encode("ascii")[:12], tag[:8], trophies, seed_nonce, 0)


def parse_profile_seed(b):
    """(seed nonce, boot count) of a profile payload."""
    return struct.unpack_from("<II", b, 24)


def parse_best(b):
    frames, score, trophies, final_hash = struct.unpack_from("<4I", b)
    return {"frames": frames, "score": score, "trophies": trophies, "final_hash": final_hash}


def ghost_bytes(game, source_hash, period, points):
    out = bytearray(struct.pack("<4s4sIHH", b"ACG1", game, source_hash, period, len(points)))
    for x, y, a, f in points:
        out += struct.pack("<hhBB", x, y, a, f)
    return bytes(out)


def parse_ghost(b):
    magic, game, src, period, count = struct.unpack_from("<4s4sIHH", b)
    assert magic == b"ACG1"
    pts = [struct.unpack_from("<hhBB", b, 16 + 6 * i) for i in range(count)]
    return {"game": game, "source_hash": src, "period": period, "points": [tuple(p) for p in pts]}


def parse_log_header(b):
    magic, game, ver, seed, frames, fh, score, tro = struct.unpack_from("<4s4s6I", b)
    assert magic == b"ACL1"
    return {"game": game, "rules_version": ver, "seed": seed, "frames": frames, "final_hash": fh,
            "score": score, "trophies": tro}
