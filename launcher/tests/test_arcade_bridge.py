import json
import os
import struct
import sys

import pytest

from arca_launcher.arcade_bridge import Bridge

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "arcade", "py"))
import arcade_save as S  # noqa: E402


def log_bytes(final_hash=0x1234, frames=10, trophies=1, rules_version=1):
    return (struct.pack("<4s4s6I", b"ACL1", b"SHIP", rules_version, 0, frames, final_hash, 0, trophies)
            + b"\x01\x00\x0a")


BAD_HASH, BAD_CLAIMS, OTHER_GAME, SLOW, UNFINISHED = 0xBAD, 0xC1A, 0x0DD, 0x5104, 0xF15


class FakeReplay:
    """Stands in for arcade_replay: a log's claimed hash picks the verdict (BAD_HASH: the hash does not match,
    BAD_CLAIMS: its score/trophies claims do not, OTHER_GAME: the tool reports another game, SLOW: the tool times
    out, UNFINISHED: the run is reported unfinished); otherwise the run is verified and reports the header's
    trophies."""
    def __init__(self):
        self.calls, self.timeouts = [], []

    def __call__(self, cmd, capture_output=True, text=True, timeout=None):
        self.calls.append(cmd)
        self.timeouts.append(timeout)
        data = open(cmd[1], "rb").read()
        h = S.parse_log_header(data)
        if h["final_hash"] == SLOW:
            import subprocess
            raise subprocess.TimeoutExpired(cmd, timeout)
        if "--ghost" in cmd:                 # a steady run to the right, one sample every 4 frames, all in play
            pts = [(i * 10, 2, 0, 0x80) for i in range(max(2, h["frames"] // 4))]
            open(cmd[3], "wb").write(S.ghost_bytes(b"SHIP", h["final_hash"], 4, pts))
        out = {"game": "ZIP_" if h["final_hash"] == OTHER_GAME else "SHIP", "frames": h["frames"],
               "final_hash": h["final_hash"], "claimed_hash": h["final_hash"],
               "hash_matches": h["final_hash"] != BAD_HASH, "complete": True,
               "claims_match": h["final_hash"] != BAD_CLAIMS, "finished": h["final_hash"] != UNFINISHED,
               "score": 0, "time_frames": h["frames"], "trophies": h["trophies"]}
        return type("R", (), {"returncode": 0, "stdout": json.dumps(out)})()


ARC = {"id": "SHIP", "replay": "/fake/arcade_replay"}


def write_run(rom, log, flags=0):
    sav = rom.with_suffix(".sav")
    save = bytearray(sav.read_bytes()) if sav.exists() else S.blank()
    if bytes(save[0x100:0x104]) != b"ACSV" or struct.unpack_from("<H", save, 0x104)[0] != S.VERSION:
        S.fmt(save, b"SHIP")
    assert S.put(save, S.RUN, log, flags)
    sav.write_bytes(bytes(save))


@pytest.fixture
def env(tmp_path):
    rom = tmp_path / "ship-it.gba"
    rom.write_bytes(b"rom")
    return rom, tmp_path / "runs", FakeReplay()


def test_before_writes_the_profile_and_keeps_the_legacy_area(env):
    rom, runs, rp = env
    legacy = bytearray(S.blank()); legacy[0:8] = b"SI\x10\x00\x00\x00\x00\x00"
    rom.with_suffix(".sav").write_bytes(bytes(legacy))
    Bridge(str(runs), "CHRIS", b"TAG00001", rp).before(str(rom), ARC)
    save = bytearray(rom.with_suffix(".sav").read_bytes())
    assert save[0:8] == legacy[0:8]
    prof, _ = S.get(save, b"SHIP", S.PROFILE)
    assert prof[:5] == b"CHRIS"


def test_before_seeds_every_launch_with_a_fresh_nonce(env):
    """Each launch writes a new non-zero seed nonce and a zero boot count into the profile: the ROM mixes them into
    a fresh seed every boot (arcade/src/ac_rng.h ac_seed_mix), so no two runs play the same."""
    rom, runs, rp = env
    bridge = Bridge(str(runs), "CHRIS", b"TAG00001", rp)
    seen = set()
    for _ in range(8):
        save = bytearray(rom.with_suffix(".sav").read_bytes()) if rom.with_suffix(".sav").exists() else S.blank()
        if bytes(save[0x100:0x104]) == b"ACSV":                    # a boot bumped the count since the last launch
            prof, _ = S.get(save, b"SHIP", S.PROFILE)
            bumped = bytearray(prof)
            struct.pack_into("<I", bumped, 28, 5)
            S.put(save, S.PROFILE, bytes(bumped))
            rom.with_suffix(".sav").write_bytes(bytes(save))
        bridge.before(str(rom), ARC)
        prof, _ = S.get(bytearray(rom.with_suffix(".sav").read_bytes()), b"SHIP", S.PROFILE)
        nonce, boots = S.parse_profile_seed(prof)
        assert nonce != 0 and boots == 0
        seen.add(nonce)
    assert len(seen) == 8, "a launch reused a seed nonce"


def test_before_reformats_an_old_version_table(env):
    rom, runs, rp = env
    old = S.blank()
    struct.pack_into("<4sH4s", old, 0x100, b"ACSV", 1, b"SHIP")
    rom.with_suffix(".sav").write_bytes(bytes(old))
    Bridge(str(runs), "CHRIS", b"TAG00001", rp).before(str(rom), ARC)
    assert S.get(bytearray(rom.with_suffix(".sav").read_bytes()), b"SHIP", S.PROFILE) is not None


def test_after_queues_a_verified_run_and_sets_the_best(env):
    rom, runs, rp = env
    write_run(rom, log_bytes(0x1234, 500))
    res = Bridge(str(runs), replay_runner=rp).after(str(rom), ARC)
    assert res["final_hash"] == 0x1234
    assert (runs / "queue" / "SHIP-00001234.acl").exists() and (runs / "best" / "SHIP.acl").exists()
    queued = json.loads((runs / "queue" / "SHIP-00001234.json").read_text())
    assert queued["rom"] == str(rom) and queued["hash_matches"] is True
    assert res["new_best"] is True                       # the first finished run is a best


def test_after_without_a_save_or_a_run_is_none(env):
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    assert b.after(str(rom), ARC) is None
    b.before(str(rom), ARC)
    assert b.after(str(rom), ARC) is None
    assert rp.calls == []


def test_bridge_rejects_a_doctored_log(env):
    rom, runs, rp = env
    write_run(rom, log_bytes(0xBAD))
    assert Bridge(str(runs), replay_runner=rp).after(str(rom), ARC) is None
    assert not (runs / "queue").exists() or not os.listdir(runs / "queue")


def test_bridge_rejects_a_truncated_log(env):
    rom, runs, rp = env
    write_run(rom, log_bytes(0x1234), flags=S.TRUNCATED)
    assert Bridge(str(runs), replay_runner=rp).after(str(rom), ARC) is None


def test_bridge_does_not_requeue_the_same_run(env):
    rom, runs, rp = env
    write_run(rom, log_bytes(0x1234))
    b = Bridge(str(runs), replay_runner=rp)
    assert b.after(str(rom), ARC) is not None
    assert b.after(str(rom), ARC) is None


def test_before_puts_a_ghost_from_the_best(env):
    rom, runs, rp = env
    write_run(rom, log_bytes(0x1234, 500))
    b = Bridge(str(runs), replay_runner=rp)
    b.after(str(rom), ARC)
    b.before(str(rom), ARC)
    g, _ = S.get(bytearray(rom.with_suffix(".sav").read_bytes()), b"SHIP", S.GHOST)
    assert S.parse_ghost(g)["source_hash"] == 0x1234


def test_a_slower_run_does_not_replace_the_best(env):
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    write_run(rom, log_bytes(0x1, 500)); b.after(str(rom), ARC)
    write_run(rom, log_bytes(0x2, 900)); b.after(str(rom), ARC)
    assert S.parse_log_header((runs / "best" / "SHIP.acl").read_bytes())["final_hash"] == 0x1


def test_a_faster_run_replaces_the_best(env):
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    write_run(rom, log_bytes(0x1, 900)); b.after(str(rom), ARC)
    write_run(rom, log_bytes(0x2, 500)); b.after(str(rom), ARC)
    assert S.parse_log_header((runs / "best" / "SHIP.acl").read_bytes())["final_hash"] == 0x2
    assert json.loads((runs / "best" / "SHIP.json").read_text())["time_frames"] == 500


def test_a_best_from_older_rules_is_replaced_by_the_next_finished_run(env):
    """The replay tool only opens logs of its own rules version, so a best kept before a rules update can never be
    a ghost again: the first finished run under the new rules replaces it, even a slower one."""
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    write_run(rom, log_bytes(0x1, 500, rules_version=1)); b.after(str(rom), ARC)
    write_run(rom, log_bytes(0x2, 900, rules_version=2)); res = b.after(str(rom), ARC)
    assert res["new_best"] is True
    assert S.parse_log_header((runs / "best" / "SHIP.acl").read_bytes())["final_hash"] == 0x2
    write_run(rom, log_bytes(0x3, 950, rules_version=2)); b.after(str(rom), ARC)
    assert S.parse_log_header((runs / "best" / "SHIP.acl").read_bytes())["final_hash"] == 0x2



def queued(runs):
    return sorted(os.listdir(runs / "queue")) if (runs / "queue").exists() else []


def test_bridge_rejects_mismatched_claims_or_another_games_log(env):
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    for h in (BAD_CLAIMS, OTHER_GAME):
        write_run(rom, log_bytes(h, 500))
        assert b.after(str(rom), ARC) is None, hex(h)
    assert queued(runs) == [] and not (runs / "best").exists()


def test_the_replay_tool_runs_with_a_timeout(env):
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    write_run(rom, log_bytes(0x1234, 500))
    b.after(str(rom), ARC)
    b.before(str(rom), ARC)                                  # replays the best for its ghost
    assert len(rp.timeouts) == 2 and rp.timeouts == [60, 60]
    write_run(rom, log_bytes(SLOW, 400))
    assert b.after(str(rom), ARC) is None                    # a replay that times out verifies nothing
    assert queued(runs) == ["SHIP-00001234.acl", "SHIP-00001234.json"]


def test_a_ghost_replay_timeout_still_writes_the_profile(env):
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    write_run(rom, log_bytes(0x1234, 500))
    b.after(str(rom), ARC)
    (runs / "best" / "SHIP.acl").write_bytes(log_bytes(SLOW, 500))     # its ghost replay will time out
    b.before(str(rom), ARC)
    save = bytearray(rom.with_suffix(".sav").read_bytes())
    assert S.get(save, b"SHIP", S.PROFILE) is not None


def test_a_submitted_run_is_not_queued_again(env):
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    write_run(rom, log_bytes(0x1234, 500))
    assert b.after(str(rom), ARC) is not None
    assert (runs / "seen" / "SHIP-00001234").exists()
    for name in queued(runs):                                # the queue was submitted and emptied
        os.remove(runs / "queue" / name)
    assert b.after(str(rom), ARC) is None
    assert queued(runs) == []


def test_profile_trophies_are_the_or_of_every_verified_run(env):
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    write_run(rom, log_bytes(0x1, 500, trophies=0b0001)); b.after(str(rom), ARC)     # the best (fastest)
    write_run(rom, log_bytes(0x2, 900, trophies=0b0100)); b.after(str(rom), ARC)     # slower, another trophy
    write_run(rom, log_bytes(BAD_HASH, 900, trophies=0b1000)); b.after(str(rom), ARC)   # not verified: no trophy
    b.before(str(rom), ARC)
    prof, _ = S.get(bytearray(rom.with_suffix(".sav").read_bytes()), b"SHIP", S.PROFILE)
    assert struct.unpack_from("<I", prof, 20)[0] == 0b0101


def test_retroarch_saves_are_the_srm_next_to_the_rom(env):
    rom, runs, rp = env
    srm = rom.with_suffix(".srm")
    big = bytearray(S.blank()) + bytes(range(256)) * 128      # a 64 KB save: 32 KB of SRAM and a tail
    big[0:8] = b"SI\x10\x00\x00\x00\x00\x00"
    srm.write_bytes(bytes(big))
    b = Bridge(str(runs), "CHRIS", b"TAG00001", rp, emulator="retroarch")
    b.before(str(rom), ARC)
    after = srm.read_bytes()
    assert len(after) == len(big) and after[S.SIZE:] == bytes(big[S.SIZE:]) and after[0:8] == bytes(big[0:8])
    assert S.get(bytearray(after), b"SHIP", S.PROFILE)[0][:5] == b"CHRIS"
    assert not rom.with_suffix(".sav").exists()
    save = bytearray(after)
    assert S.put(save, S.RUN, log_bytes(0x1234, 500))
    srm.write_bytes(bytes(save))
    assert b.after(str(rom), ARC)["final_hash"] == 0x1234


def test_a_save_shorter_than_32_kb_is_replaced(env):
    rom, runs, rp = env
    rom.with_suffix(".sav").write_bytes(b"\x00" * 100)
    Bridge(str(runs), replay_runner=rp).before(str(rom), ARC)
    assert len(rom.with_suffix(".sav").read_bytes()) == S.SIZE


def test_after_compares_a_run_with_the_best_before_it(env):
    """The coach's facts: the best's time and where this run lost against its ghost, measured against the best this
    run is compared with (for a new best, the one it replaced)."""
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    write_run(rom, log_bytes(0x1, 500)); first = b.after(str(rom), ARC)
    assert first["vs_best"] == {"best_frames": None, "splits": None}
    write_run(rom, log_bytes(0x2, 900)); slower = b.after(str(rom), ARC)
    assert slower["vs_best"]["best_frames"] == 500 and slower["vs_best"]["splits"]["mode"] == "distance"
    write_run(rom, log_bytes(0x3, 400)); faster = b.after(str(rom), ARC)
    assert faster["new_best"] is True and faster["vs_best"]["best_frames"] == 500


def test_after_tells_the_comparison_whether_the_run_finished(env, monkeypatch):
    from arca_launcher import coach
    seen = []
    monkeypatch.setattr(coach, "compare", lambda run, best, finished=False: seen.append(finished))
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    write_run(rom, log_bytes(0x1, 500)); b.after(str(rom), ARC)
    write_run(rom, log_bytes(0x2, 900)); b.after(str(rom), ARC)
    assert seen == [True]                                 # FakeReplay reports every run finished


def test_the_comparison_is_never_stored(env):
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    write_run(rom, log_bytes(0x1, 900)); b.after(str(rom), ARC)
    write_run(rom, log_bytes(0x2, 500)); b.after(str(rom), ARC)
    stored = [p for d in ("queue", "best", "seen") for p in (runs / d).iterdir() if p.suffix != ".acl"]
    assert stored and all("vs_best" not in p.read_text() for p in stored)


def test_a_best_from_older_rules_is_no_yardstick(env):
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    write_run(rom, log_bytes(0x1, 500, rules_version=1)); b.after(str(rom), ARC)
    write_run(rom, log_bytes(0x2, 900, rules_version=2))
    assert b.after(str(rom), ARC)["vs_best"]["best_frames"] is None


def test_a_comparison_that_fails_never_loses_the_run(env):
    rom, runs, rp = env

    def no_ghosts(cmd, **kw):
        if "--ghost" in cmd:
            raise OSError("replay tool gone")
        return rp(cmd, **kw)
    b = Bridge(str(runs), replay_runner=no_ghosts)
    write_run(rom, log_bytes(0x1, 500)); b.after(str(rom), ARC)
    write_run(rom, log_bytes(0x2, 900)); res = b.after(str(rom), ARC)
    assert res["vs_best"] == {"best_frames": 500, "splits": None}
    assert (runs / "queue" / "SHIP-00000002.acl").exists()


def test_history_is_the_recent_finished_times_oldest_first(env):
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    for h, frames in ((0x1, 500), (0x2, 520), (0x3, 510)):
        write_run(rom, log_bytes(h, frames)); b.after(str(rom), ARC)
    assert b.history("SHIP") == [500, 520, 510]
    assert b.history("SHIP", n=2) == [520, 510]
    assert b.history("ZIPG") == []


def test_before_writes_a_given_ghost_instead_of_the_best(env):
    rom, runs, rp = env
    write_run(rom, log_bytes(0x1234, 500))
    b = Bridge(str(runs), replay_runner=rp)
    b.after(str(rom), ARC)                     # leaves a best log that before() would otherwise replay for a ghost
    rp.calls.clear()
    given = S.ghost_bytes(b"SHIP", 0x9999, 4, [(0, 2, 0, 0x80)])
    b.before(str(rom), ARC, ghost=given)
    assert rp.calls == []                      # the best's ghost was never replayed
    save = bytearray(rom.with_suffix(".sav").read_bytes())
    g, _ = S.get(save, b"SHIP", S.GHOST)
    assert g == given


def test_ghost_bytes_is_none_when_the_tool_fails(env):
    rom, runs, rp = env
    log = runs / "log.acl"
    runs.mkdir(parents=True, exist_ok=True)
    log.write_bytes(log_bytes(SLOW, 400))
    b = Bridge(str(runs), replay_runner=rp)
    assert b.ghost_bytes(ARC, str(log)) is None


def test_log_time_reads_time_frames(env):
    rom, runs, rp = env
    log = runs / "log.acl"
    runs.mkdir(parents=True, exist_ok=True)
    log.write_bytes(log_bytes(0x1234, 500))
    b = Bridge(str(runs), replay_runner=rp)
    assert b.log_time(ARC, str(log)) == 500


def test_log_time_is_none_for_unfinished(env):
    rom, runs, rp = env
    log = runs / "log.acl"
    runs.mkdir(parents=True, exist_ok=True)
    log.write_bytes(log_bytes(UNFINISHED, 500))
    b = Bridge(str(runs), replay_runner=rp)
    assert b.log_time(ARC, str(log)) is None


def test_log_time_is_none_for_a_missing_log(env):
    rom, runs, rp = env
    b = Bridge(str(runs), replay_runner=rp)
    assert b.log_time(ARC, str(runs / "no-such.acl")) is None
    assert rp.calls == []
