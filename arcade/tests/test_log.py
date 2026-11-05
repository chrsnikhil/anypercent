import ctypes
import random
import struct

from conftest import U8, U16, U32

CAP = 4096


class Header(ctypes.Structure):
    _fields_ = [("magic", U8 * 4), ("game", U8 * 4), ("rules_version", U32), ("seed", U32), ("frames", U32),
                ("final_hash", U32), ("score", U32), ("trophies", U32)]


class Rec(ctypes.Structure):
    _fields_ = [("buf", ctypes.POINTER(U8)), ("cap", U32), ("len", U32), ("frames", U32), ("last", U16),
                ("count", U32), ("full", U8), ("prev", U16)]


class Reader(ctypes.Structure):
    _fields_ = [("buf", ctypes.POINTER(U8)), ("len", U32), ("pos", U32), ("left", U32), ("buttons", U16)]


def record(kit, frames, cap=CAP):
    buf = (U8 * cap)()
    rec = Rec()
    kit.ac_rec_begin(ctypes.byref(rec), buf, U32(cap), b"TOY1", U32(3), U32(42))
    for b in frames:
        kit.ac_rec_push(ctypes.byref(rec), U16(b))
    n = kit.ac_rec_finish(ctypes.byref(rec), U32(0xCAFEBABE), U32(7), U32(5))
    return bytes(buf[:n]), rec


def replay(kit, data):
    buf = (U8 * len(data)).from_buffer_copy(data)
    rd = Reader()
    assert kit.ac_log_open(ctypes.byref(rd), buf, U32(len(data))) == 1
    out = []
    b = U16()
    while kit.ac_log_next(ctypes.byref(rd), ctypes.byref(b)):
        out.append(b.value)
    return out


def test_header_layout(kit):
    data, _ = record(kit, [1, 1, 2])
    magic, game, ver, seed, frames, fh, score, tro = struct.unpack("<4s4s6I", data[:32])
    assert (magic, game, ver, seed, frames, fh, score, tro) == (b"ACL1", b"TOY1", 3, 42, 3, 0xCAFEBABE, 7, 5)


def test_round_trip_random_inputs(kit):
    rnd = random.Random(1)
    frames, b = [], 0
    for _ in range(12000):
        if rnd.random() < 0.05:
            b = rnd.randrange(0, 1024)
        frames.append(b)
    data, rec = record(kit, frames, cap=8192)
    assert rec.full == 0
    assert replay(kit, data) == frames
    assert len(data) < 3000


def test_log_masks_high_button_bits(kit):
    a, _ = record(kit, [0x001, 0xFC01, 0x0401])
    b, _ = record(kit, [0x001, 0x001, 0x001])
    assert a == b


def test_long_runs_use_varints(kit):
    data, _ = record(kit, [5] * 100000)
    assert replay(kit, data) == [5] * 100000
    assert len(data) <= 32 + 2 + 3


def test_bad_magic_is_rejected(kit):
    data, _ = record(kit, [1])
    bad = bytearray(data); bad[0] = ord("X")
    buf = (U8 * len(bad)).from_buffer_copy(bytes(bad))
    assert kit.ac_log_open(ctypes.byref(Reader()), buf, U32(len(bad))) == 0


def body(data):
    return data[32:]


def varint(v):
    out = bytearray()
    while v >= 0x80:
        out.append(v & 0x7F | 0x80)
        v >>= 7
    return bytes(out + bytes([v]))


def test_one_bit_changes_are_toggle_tokens(kit):
    # From 0, [1, 1] is bit 0 toggled (count 2: V = 2 << 5 | 0 << 1 = 64); 3 is bit 1 toggled (V = 1 << 5 | 1 << 1
    # = 34); 0 differs from 3 in two bits: a set token (V = 1 << 1 | 1 = 3, then 0x0000).
    data, _ = record(kit, [1, 1, 3, 0])
    assert body(data) == bytes([64, 34, 3, 0, 0])
    assert replay(kit, data) == [1, 1, 3, 0]


def test_toggle_counts_use_varints(kit):
    data, _ = record(kit, [0] + [0x200] * 1000)
    # the first run has no change from 0: a set token (V = 3, 00 00); then bit 9 toggled x1000: V = 1000 << 5 | 9 << 1
    assert body(data) == bytes([3, 0, 0]) + varint(1000 << 5 | 9 << 1)
    assert replay(kit, data) == [0] + [0x200] * 1000


def test_reader_rejects_bad_tokens(kit):
    head, _ = record(kit, [])
    head = head[:32]
    for tok in (bytes([10 << 1 | 1 << 5]),      # toggle of bit 10
                bytes([1 << 1]),                # toggle with count 0
                bytes([1, 5, 0])):              # set with count 0
        assert replay(kit, head + bytes([3, 1, 0]) + tok) == [1]


def test_a_truncated_log_decodes_to_its_header_frames(kit):
    rnd = random.Random(7)
    frames = [rnd.randrange(0, 1024) for _ in range(5000)]
    for cap in (64, 100, 257, 1000):
        data, rec = record(kit, frames, cap=cap)
        assert rec.full == 1 and len(data) <= cap
        got = replay(kit, data)
        assert len(got) == struct.unpack_from("<I", data, 16)[0] and got == frames[:len(got)]


def test_reader_rejects_non_minimal_varints_and_high_button_bits(kit):
    head = record(kit, [])[0][:32]
    ok = bytes([3, 1, 0])                                 # set x1: buttons 1
    assert replay(kit, head + ok + bytes([64])) == [1, 0, 0]        # toggle bit 0 x2: minimal, accepted
    assert replay(kit, head + ok + bytes([64 | 0x80, 0])) == [1]    # the same value in two bytes
    assert replay(kit, head + ok + bytes([0x83, 0x80, 0])) == [1]   # a set token padded to three bytes
    assert replay(kit, head + ok + bytes([3, 0, 0x04])) == [1]      # set token with button bit 10
    assert replay(kit, head + ok + bytes([3, 0, 0x80])) == [1]      # set token with button bit 15
