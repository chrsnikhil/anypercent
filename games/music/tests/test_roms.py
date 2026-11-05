"""Every arcade ROM plays its theme: records the built ROM headless (tools/gba_audio.c on libmgba) and checks the
sound is there from the first seconds, at a sane level, steady, and never clipping. Needs the WSL sandbox (libmgba)
and the five ROMs built; skips otherwise."""
import math
import os
import struct
import subprocess
import wave

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
MUSIC = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(MUSIC))
MGBA = os.environ.get("MGBA", "/opt/arca-sandbox/toolchains/mgba-src")
ROMS = {"SHIP": "game/shipit.gba", "RUSH": "games/rushhour/rushhour.gba", "ZIPG": "games/zip/zip.gba",
        "MDGP": "games/marinedrive/marinedrive.gba", "SEGF": "games/segfault/segfault.gba"}


@pytest.fixture(scope="module")
def recorder(tmp_path_factory):
    lib = os.path.join(MGBA, "build", "libmgba.a")
    if not os.path.exists(lib):
        pytest.skip("libmgba is in the WSL sandbox")
    exe = str(tmp_path_factory.mktemp("rec") / "gba_audio")
    subprocess.run(["gcc", "-O2", "-o", exe, os.path.join(MUSIC, "tools", "gba_audio.c"), "-I%s/include" % MGBA,
                    "-I%s/build/include" % MGBA, lib, "-lm", "-lpthread"], check=True, capture_output=True)
    return exe


def levels(path):
    w = wave.open(path)
    n, r = w.getnframes(), w.getframerate()
    x = struct.unpack(f"<{n * 2}h", w.readframes(n))
    mono = [(x[i] + x[i + 1]) / 2 for i in range(0, len(x), 2)]
    secs = [mono[i:i + r] for i in range(0, len(mono) - r + 1, r)]
    return [math.sqrt(sum(v * v for v in s) / len(s)) / 32768 for s in secs], max(abs(v) for v in x) / 32768


@pytest.mark.parametrize("gid", sorted(ROMS))
def test_the_rom_plays_its_theme(recorder, tmp_path, gid):
    rom = os.path.join(REPO, ROMS[gid])
    if not os.path.exists(rom):
        pytest.skip(f"{rom} not built")
    out = str(tmp_path / f"{gid}.wav")
    subprocess.run([recorder, rom, "600", out], check=True, capture_output=True)    # 10 s, no keys pressed
    rms, peak = levels(out)
    assert min(rms[1:]) > 0.02, f"{gid}: silent stretches {rms}"                      # music from the second second on
    assert max(rms) < 0.2 and peak < 0.9, f"{gid}: too loud (rms {max(rms):.3f}, peak {peak:.2f})"
