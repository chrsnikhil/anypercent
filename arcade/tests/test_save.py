import ctypes
import os
import sys

from conftest import KIT, U8, U32

sys.path.insert(0, os.path.join(KIT, "py"))
import arcade_save as S  # noqa: E402


def cbuf(b):
    return (U8 * len(b)).from_buffer_copy(bytes(b))


def c_get(kit, save, game, sec):
    n, fl = U32(), U8()
    kit.ac_save_get.restype = ctypes.c_void_p
    p = kit.ac_save_get(save, game, sec, ctypes.byref(n), ctypes.byref(fl))
    return None if not p else (ctypes.string_at(p, n.value), fl.value)


def test_blank_and_zero_saves_have_no_sections(kit):
    for fill in (0xFF, 0x00):
        raw = bytes([fill]) * S.SIZE
        for sec in (S.PROFILE, S.BEST, S.RUN, S.GHOST):
            assert S.get(bytearray(raw), b"SHIP", sec) is None
            assert c_get(kit, cbuf(raw), b"SHIP", sec) is None


def test_c_writes_python_reads(kit):
    save = cbuf(S.blank())
    kit.ac_save_format(save, b"SHIP")
    payload = bytes(range(200))
    assert kit.ac_save_put(save, S.RUN, cbuf(payload), U32(200), U8(S.TRUNCATED)) == 1
    assert S.get(bytearray(save), b"SHIP", S.RUN) == (payload, S.TRUNCATED)
    assert bytes(save)[:0x100] == b"\xff" * 0x100          # legacy area untouched


def test_python_writes_c_reads(kit):
    save = S.blank()
    S.fmt(save, b"ZIP_")
    prof = S.profile_bytes("CHRIS", b"12345678", 5)
    assert S.put(save, S.PROFILE, prof)
    assert c_get(kit, cbuf(save), b"ZIP_", S.PROFILE) == (prof, 0)


def test_profile_carries_the_seed_nonce_and_a_zero_boot_count():
    prof = S.profile_bytes("CHRIS", b"12345678", 5, seed_nonce=0xDEADBEEF)
    assert len(prof) == 64
    assert prof[:24] == S.profile_bytes("CHRIS", b"12345678", 5)[:24]      # name, tag, trophies unchanged
    assert S.parse_profile_seed(prof) == (0xDEADBEEF, 0)
    assert S.parse_profile_seed(S.profile_bytes("CHRIS", b"12345678", 5)) == (0, 0)   # no nonce: classic seed 0


def test_wrong_game_or_bad_checksum_reads_absent(kit):
    save = S.blank()
    S.fmt(save, b"SHIP")
    S.put(save, S.BEST, bytes(32))
    assert S.get(save, b"ZIP_", S.BEST) is None
    save[S.OFF[S.BEST]] ^= 1
    assert S.get(save, b"SHIP", S.BEST) is None
    assert c_get(kit, cbuf(save), b"SHIP", S.BEST) is None


def test_oversize_section_is_refused(kit):
    save = cbuf(S.blank())
    kit.ac_save_format(save, b"SHIP")
    big = bytes(S.CAP[S.RUN] + 1)
    assert kit.ac_save_put(save, S.RUN, cbuf(big), U32(len(big)), U8(0)) == 0
    assert not S.put(bytearray(save), S.RUN, big)


def test_ghost_round_trip():
    pts = [(i * 3 - 100, -i, i % 256, i & 1) for i in range(500)]
    b = S.ghost_bytes(b"SHIP", 0xDEADBEEF, 4, pts)
    g = S.parse_ghost(b)
    assert g["game"] == b"SHIP" and g["source_hash"] == 0xDEADBEEF and g["period"] == 4 and g["points"] == pts


def test_recorder_caps_and_marks_truncated(kit):
    from test_log import Rec
    buf = (U8 * 64)()
    rec = Rec()
    kit.ac_rec_begin(ctypes.byref(rec), buf, U32(64), b"TOY1", U32(1), U32(0))
    for i in range(1000):
        kit.ac_rec_push(ctypes.byref(rec), ctypes.c_uint16(i % 7))
    n = kit.ac_rec_finish(ctypes.byref(rec), U32(0), U32(0), U32(0))
    assert rec.full == 1 and n <= 64
    h = S.parse_log_header(bytes(buf[:n]))
    assert h["frames"] < 1000


def test_run_and_ghost_layout(kit):
    assert (S.OFF[S.RUN], S.CAP[S.RUN], S.OFF[S.GHOST], S.CAP[S.GHOST]) == (0x0400, 14336, 0x3C00, 16384)
    assert S.OFF[S.GHOST] + S.CAP[S.GHOST] <= S.SIZE
    save = cbuf(S.blank())
    kit.ac_save_format(save, b"SHIP")
    run = bytes(range(256)) * 56                        # exactly the RUN cap
    assert kit.ac_save_put(save, S.RUN, cbuf(run), U32(len(run)), U8(0)) == 1
    img = bytearray(save)
    assert S.get(img, b"SHIP", S.RUN) == (run, 0)
    assert bytes(img[0x0400:0x0400 + len(run)]) == run
    g = S.ghost_bytes(b"SHIP", 1, 4, [(1, 2, 3, 4)])
    assert kit.ac_save_put(save, S.GHOST, cbuf(g), U32(len(g)), U8(0)) == 1
    assert bytes(bytearray(save)[0x3C00:0x3C00 + len(g)]) == g


def test_the_save_header_is_version_2(kit):
    save = cbuf(S.blank())
    kit.ac_save_format(save, b"SHIP")
    img = bytearray(save)
    assert bytes(img[S.BASE:S.BASE + 6]) == b"ACSV\x02\x00" and S.VERSION == 2
    py = S.blank()
    S.fmt(py, b"SHIP")
    assert py == img                                    # C and Python format the same image


def test_a_version_1_image_reads_absent_and_refuses_writes(kit):
    save = S.blank()
    S.fmt(save, b"SHIP")
    assert S.put(save, S.BEST, bytes(32))
    save[S.BASE + 4] = 1                                # the same table under the old version
    assert S.get(save, b"SHIP", S.BEST) is None and not S.put(save, S.BEST, bytes(32))
    c = cbuf(save)
    assert c_get(kit, c, b"SHIP", S.BEST) is None
    assert kit.ac_save_put(c, S.BEST, cbuf(bytes(32)), U32(32), U8(0)) == 0


def test_commit_publishes_a_payload_already_in_place(kit):
    save = cbuf(S.blank())
    kit.ac_save_format(save, b"SHIP")
    payload = bytes((i * 7) & 0xFF for i in range(3000))
    ctypes.memmove(ctypes.addressof(save) + S.OFF[S.RUN], payload, len(payload))
    assert c_get(kit, save, b"SHIP", S.RUN) is None                 # written but not committed
    kit.ac_save_sum.restype = ctypes.c_uint16
    s = kit.ac_save_sum(cbuf(payload), U32(len(payload)))
    assert s == S.checksum(payload)
    assert kit.ac_save_commit(save, S.RUN, U32(len(payload)), ctypes.c_uint16(s), U8(S.TRUNCATED)) == 1
    assert c_get(kit, save, b"SHIP", S.RUN) == (payload, S.TRUNCATED)
    assert S.get(bytearray(save), b"SHIP", S.RUN) == (payload, S.TRUNCATED)
    assert kit.ac_save_commit(save, S.RUN, U32(S.CAP[S.RUN] + 1), ctypes.c_uint16(0), U8(0)) == 0   # over the cap
    assert kit.ac_save_commit(save, 5, U32(1), ctypes.c_uint16(0), U8(0)) == 0                      # no such section
    blank = cbuf(S.blank())
    assert kit.ac_save_commit(blank, S.RUN, U32(1), ctypes.c_uint16(0), U8(0)) == 0                 # no header
