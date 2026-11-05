import ctypes
import json
import os
import struct
import subprocess
import sys

import pytest

from conftest import KIT, U8, U16, U32, make
from test_log import Rec

sys.path.insert(0, os.path.join(KIT, "py"))
import arcade_save as S  # noqa: E402

A, B, RIGHT, UP = 0x001, 0x002, 0x010, 0x040


@pytest.fixture(scope="module")
def toy():
    so = ctypes.CDLL(make("out/libtoy.so"))
    so.game_hash.restype = U32
    so.game_step.argtypes = [U16]
    so.game_init.argtypes = [U32]
    return so


class Result(ctypes.Structure):
    _fields_ = [("finished", U8), ("frames", U32), ("score", U32), ("time_frames", U32), ("trophies", U32)]


def run_and_record(toy, inputs, seed=9, game=b"TOY1", version=3):
    """Records a toy run as a game would: the header claims the run's own score and trophies."""
    buf = (U8 * 8192)()
    rec = Rec()
    toy.ac_rec_begin(ctypes.byref(rec), buf, U32(8192), game, U32(version), U32(seed))
    toy.game_init(seed)
    for b in inputs:
        toy.ac_rec_push(ctypes.byref(rec), U16(b))
        toy.game_step(b)
    res = Result()
    toy.game_result(ctypes.byref(res))
    n = toy.ac_rec_finish(ctypes.byref(rec), U32(toy.game_hash()), U32(res.score), U32(res.trophies))
    return bytes(buf[:n]), toy.game_hash()


def inputs():
    return [RIGHT] * 50 + [A | UP] * 200 + [B] * 3 + [A] * 120


def cli(tmp_path, log, *extra):
    p = tmp_path / "run.acl"
    p.write_bytes(log)
    r = subprocess.run([make("out/arcade_replay_toy"), str(p), *extra], capture_output=True, text=True)
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else None)


def test_cli_replays_to_the_same_hash(toy, tmp_path):
    log, h = run_and_record(toy, inputs())
    code, out = cli(tmp_path, log)
    assert code == 0
    assert out["final_hash"] == h == out["claimed_hash"] and out["hash_matches"] and out["complete"]
    assert out["claims_match"]
    assert out["finished"] and out["trophies"] == 1 and out["game"] == "TOY1"


def test_a_doctored_claim_is_reported(toy, tmp_path):
    log, h = run_and_record(toy, inputs())
    bad = bytearray(log); bad[20] ^= 0xFF          # claimed final hash
    code, out = cli(tmp_path, bytes(bad))
    assert code == 0 and not out["hash_matches"]


def test_bad_header_exits_2(tmp_path):
    code, out = cli(tmp_path, b"XXXX" + bytes(40))
    assert code == 2


def test_ghost_track(toy, tmp_path):
    log, h = run_and_record(toy, inputs())
    code, _ = cli(tmp_path, log, "--ghost", str(tmp_path / "g.bin"))
    g = S.parse_ghost((tmp_path / "g.bin").read_bytes())
    assert code == 0 and g["source_hash"] == h and g["period"] == 4
    assert g["points"][0][:2] == (1, 0)                   # sampled after the first step
    assert g["points"][12][:2] == (49, 0)                 # frame 49 (0-based sample 12 = frame 12*4+1)
    assert len(g["points"]) == (len(inputs()) - 1) // 4 + 1


def test_ghost_period_grows_to_fit(toy, tmp_path):
    long = [RIGHT] * 40000 + [A] * 300
    log, _ = run_and_record(toy, long)
    code, _ = cli(tmp_path, log, "--ghost", str(tmp_path / "g.bin"))
    g = S.parse_ghost((tmp_path / "g.bin").read_bytes())
    assert g["period"] >= 16 and 16 + 6 * len(g["points"]) <= 16384


def test_a_log_of_another_game_or_rules_version_is_refused(toy, tmp_path):
    for game, version in ((b"SHIP", 3), (b"TOY1", 4)):
        log, _ = run_and_record(toy, inputs(), game=game, version=version)
        code, out = cli(tmp_path, log)
        assert code == 2 and out is None, (game, version)
        assert cli(tmp_path, log, "--ghost", str(tmp_path / "g.bin"))[0] == 2


def test_doctored_score_or_trophies_do_not_match_the_claims(toy, tmp_path):
    log, _ = run_and_record(toy, inputs() + [B])
    for off in (24, 28):                                  # claimed score, claimed trophies
        bad = bytearray(log)
        bad[off] ^= 0x40
        code, out = cli(tmp_path, bytes(bad))
        assert code == 0 and out["hash_matches"] and out["complete"] and not out["claims_match"]


def set_frames(log, frames):
    return log[:16] + struct.pack("<I", frames) + log[20:]


def test_replay_stops_at_the_header_frames(toy, tmp_path):
    log, _ = run_and_record(toy, [RIGHT] * 10)
    body_of_50, _ = run_and_record(toy, [RIGHT] * 50)
    short = set_frames(body_of_50, 10)                    # claims 10 frames, carries 50
    code, out = cli(tmp_path, short)
    assert code == 0 and out["frames"] == 10 and out["complete"]
    assert out["final_hash"] == S.parse_log_header(log)["final_hash"]
    code, _ = cli(tmp_path, short, "--ghost", str(tmp_path / "g.bin"))
    g = S.parse_ghost((tmp_path / "g.bin").read_bytes())
    assert code == 0 and len(g["points"]) == (10 - 1) // 4 + 1 and g["points"][-1][:2] == (9, 0)


def test_a_log_claiming_more_than_an_hour_is_refused(toy, tmp_path):
    log, _ = run_and_record(toy, [RIGHT] * 10)
    assert cli(tmp_path, set_frames(log, 216000))[0] == 0          # AC_MAX_FRAMES: one hour at 60 Hz
    assert cli(tmp_path, set_frames(log, 216001))[0] == 2
    assert cli(tmp_path, set_frames(log, 216001), "--ghost", str(tmp_path / "g.bin"))[0] == 2


def test_ghost_extract_sets_the_period_on_every_path(toy):
    log, _ = run_and_record(toy, [RIGHT] * 10)
    pts = (ctypes.c_uint8 * (6 * 64))()
    period = ctypes.c_uint16(0xBEEF)
    for data, want in ((b"XXXX" + bytes(40), 0), (set_frames(log, 216001), 0)):
        period.value = 0xBEEF
        buf = (U8 * len(data)).from_buffer_copy(data)
        assert toy.ac_ghost_extract(buf, U32(len(data)), U16(4), pts, U32(64), ctypes.byref(period)) == 0
        assert period.value == want
    buf = (U8 * len(log)).from_buffer_copy(log)
    assert toy.ac_ghost_extract(buf, U32(len(log)), U16(0), pts, U32(64), ctypes.byref(period)) == 0
    assert period.value == 0
