"""SHIP IT!'s seed: seed 0 is the classic run; any other seed shifts act 2's timetable (each bug's spawn, each router
fry, the pizza) a little, in order, and the devs' starting energy, so a run recorded for one seed plays out
differently on another. The ROM takes its seed from the launcher's profile (src/runlog.cpp) and records it."""
import ctypes
import os
import struct
import sys

from conftest import GAME_DIR, U32
from test_arcade import FULL, MISSED, SETTLE, play, replay

sys.path.insert(0, os.path.join(GAME_DIR, "..", "arcade", "py"))
import arcade_save as S  # noqa: E402

BUG_COUNT, FRY_COUNT, DEVS = 18, 6, 3
N_SCHED = BUG_COUNT + FRY_COUNT + 1 + DEVS          # bugs, fries, pizza, starting energies
NONCE = 0x5EED1234
SEEDS = (0x01234567, 0xDEADBEEF, 0x5EED0001, 77)


class Result(ctypes.Structure):
    _fields_ = [("finished", ctypes.c_uint8), ("frames", ctypes.c_uint32), ("score", ctypes.c_uint32),
                ("time_frames", ctypes.c_uint32), ("trophies", ctypes.c_uint32)]


def schedule(lib, seed=None):
    lib.rules_schedule.restype = ctypes.c_uint16
    lib.rules_init_seeded.argtypes = [U32]
    if seed is None:
        lib.rules_init()
    else:
        lib.rules_init_seeded(seed)
    return [lib.rules_schedule(k) for k in range(N_SCHED)]


def result(lib, keys, seed):
    lib.game_init.argtypes = [U32]
    lib.game_init(seed)
    for k in keys:
        lib.game_step(k)
    r = Result()
    lib.game_result(ctypes.byref(r))
    return (r.finished, r.time_frames, r.score, r.trophies)


def test_game_info_rules_version_is_2(lib):
    data = (ctypes.c_uint8 * 8).in_dll(lib, "GAME_INFO")
    assert bytes(data[:4]) == b"SHIP" and int.from_bytes(bytes(data[4:8]), "little") == 2   # 2: the seed


def test_the_seed_shifts_the_act_two_timetable(lib):
    classic = schedule(lib)
    assert schedule(lib, 0) == classic, "seed 0 must be the classic timetable"
    tables = set()
    for seed in SEEDS:
        sched = schedule(lib, seed)
        assert sched != classic, "seed %#x changed nothing" % seed
        assert schedule(lib, seed) == sched, "the same seed must give the same timetable"
        bugs, fries = sched[:BUG_COUNT], sched[BUG_COUNT:BUG_COUNT + FRY_COUNT]
        assert bugs == sorted(set(bugs)) and fries == sorted(set(fries)), "the order of events changed"
        for a, b in zip(sched[:BUG_COUNT + FRY_COUNT + 1], classic):
            assert abs(a - b) <= 180, "an event moved too far"
        for a, b in zip(sched[-DEVS:], classic[-DEVS:]):
            assert 1 <= a <= 255 and abs(a - b) <= 24, "a starting energy moved too far"
        tables.add(tuple(sched))
    assert len(tables) == len(SEEDS), "different seeds gave the same timetable"


def test_a_recording_does_not_survive_other_seeds(lib):
    keys = FULL[:-len(SETTLE)]
    classic = result(lib, keys, 0)
    assert classic[0], "the classic route must ship"
    lib.ac_seed_mix.restype = U32
    lib.ac_seed_mix.argtypes = [U32, U32]
    seeds = [lib.ac_seed_mix(NONCE, b) for b in range(1, 101)]
    survived = sum(1 for sd in seeds if result(lib, keys, sd) == classic)
    print("recording survives %d of 100 seeds" % survived)
    assert survived <= 10


def test_a_seeded_profile_seeds_the_rom_run_and_it_replays(rom, runner, lib, tmp_path):
    save = S.blank()
    S.fmt(save, b"SHIP")
    assert S.put(save, S.PROFILE, S.profile_bytes("SEED", b"\0" * 8, 0, seed_nonce=NONCE))
    path = tmp_path / "seeded.sav"
    path.write_bytes(bytes(save))
    out, first, written = play(runner, MISSED, tmp_path, path)
    assert written == 1
    lib.ac_seed_mix.restype = U32
    lib.ac_seed_mix.argtypes = [U32, U32]
    want = lib.ac_seed_mix(NONCE, 1)
    log, _ = S.get(out, b"SHIP", S.RUN)
    head = S.parse_log_header(log)
    assert head["seed"] == want and want != 0, "the ROM did not record its seed"
    res = replay(tmp_path, log)
    assert res["hash_matches"] and res["complete"], res
    prof, _ = S.get(out, b"SHIP", S.PROFILE)
    assert S.parse_profile_seed(prof) == (NONCE, 1), "the boot count was not written back"
    assert struct.unpack_from("<I", prof, 20)[0] == 0 and prof[:4] == b"SEED"
