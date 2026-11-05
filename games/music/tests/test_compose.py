"""The music composer (games/music/compose.py): every song must be a VGM that Butano's DMG player takes, loop
cleanly and keep to what the Game Boy sound chip can play. Run in the WSL sandbox:

    cd games/music && /opt/arca-sandbox/venv/bin/python -m pytest -q tests"""
import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import compose  # noqa: E402
import songs  # noqa: E402

ADVGM = "/opt/arca-sandbox/toolchains/butano/butano/tools/advgm"
APU_REGS = set(range(0x00, 0x17)) | set(range(0x20, 0x30))    # NR10..NR52 and wave RAM, as VGM 0xB3 offsets


def commands(vgm):
    """(offset, command bytes) for every command in the data block."""
    p = 0x34 + struct.unpack_from("<I", vgm, 0x34)[0]
    out = []
    while vgm[p] != 0x66:
        n = 3 if vgm[p] == 0xB3 else 1
        out.append((p, bytes(vgm[p:p + n])))
        p += n
    return out


@pytest.fixture(scope="module", params=sorted(songs.SONGS))
def song(request):
    return request.param, compose.vgm(songs.SONGS[request.param])


def test_the_header_is_what_butanos_converter_checks(song):
    name, vgm = song
    assert vgm[0:4] == b"Vgm "
    assert vgm[8:10] == b"\x61\x01"                                  # version 1.61
    assert vgm[0x10:0x12] == b"\x00\x00"                             # no SN76489
    assert struct.unpack_from("<I", vgm, 0x80)[0] == 4194304         # the Game Boy chip, at its clock
    assert struct.unpack_from("<I", vgm, 0x04)[0] == len(vgm) - 4    # EOF offset


def test_every_wait_is_one_frame_and_the_loop_lands_on_a_command(song):
    name, vgm = song
    cmds = commands(vgm)
    waits = [c for _, c in cmds if c[0] != 0xB3]
    assert waits and all(c == b"\x62" for c in waits)                # Butano's player counts any wait as 1 frame
    loop_at = 0x1C + struct.unpack_from("<I", vgm, 0x1C)[0]
    assert loop_at in {p for p, _ in cmds}
    frames = len(waits)
    assert struct.unpack_from("<I", vgm, 0x18)[0] == frames * 735   # total samples, at 44100 Hz
    assert struct.unpack_from("<I", vgm, 0x20)[0] == compose.loop_frames(songs.SONGS[name]) * 735


def test_only_sound_chip_registers_are_written(song):
    name, vgm = song
    assert all(c[1] in APU_REGS for _, c in commands(vgm) if c[0] == 0xB3)


def test_butanos_own_converter_takes_it(song, tmp_path):
    if not os.path.isdir(ADVGM):
        pytest.skip("Butano's advgm converter is in the WSL sandbox")
    sys.path.insert(0, ADVGM)
    import advgm_converter
    name, vgm = song
    src = tmp_path / f"{name}.vgm"
    src.write_bytes(vgm)
    advgm_converter.convert_file_binary(str(src), str(tmp_path / f"{name}.bin"))
    assert (tmp_path / f"{name}.bin").stat().st_size > 100


def test_every_bar_fills_its_sixteen_steps():
    for name, s in songs.SONGS.items():
        for section in s.sections:
            for i, bar in enumerate(section.melody):
                assert compose.bar_steps(bar) == 16, (name, section.name, i + 1)


def test_notes_stay_where_the_chip_can_play_them():
    for name, s in songs.SONGS.items():
        for note in compose.all_notes(s):
            assert 0 <= compose.freq_reg(note) <= 2047, (name, note)


def test_note_names_become_the_right_pitch():
    assert compose.midi("A4") == 69 and compose.midi("C#5") == 73 and compose.midi("Bb3") == 58
    assert compose.freq_reg("A4") == round(2048 - 131072 / 440)      # the pulse channel's 11-bit period


def test_a_bar_that_does_not_add_up_is_refused():
    with pytest.raises(ValueError):
        compose.parse_bar("C5:4 E5:4 G5:4")                          # 12 steps


def test_the_loop_plays_the_whole_song_again_from_the_top():
    s = songs.SONGS[sorted(songs.SONGS)[0]]
    assert compose.loop_frames(s) == compose.song_frames(s) - compose.intro_frames(s)
