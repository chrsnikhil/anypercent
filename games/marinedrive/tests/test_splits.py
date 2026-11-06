"""out/arcade_splits (tools/arcade_splits.c): the same replay as arcade_replay, then the player's lap times from the
rules, as one JSON line. The route log is the shipped one when the sandbox has it (devicecheck/MDGP.acl, which
replays tests/routes/full_run.keys) and the same route encoded here with the kit's recorder."""
import json
import os
import struct
import subprocess
import sys

import pytest

from conftest import GAME_DIR, SELECT, START, T, load_keys

sys.path.insert(0, os.path.join(GAME_DIR, "dev"))
import ghostgen as G  # noqa: E402

DEVICECHECK = "/opt/arca-sandbox/devicecheck"
ROUTE_LAPS = [2087, 1995, 1994]


def run(tool, log, tmp_path, name="run.acl"):
    """(exit code, stdout, stderr) of the tool on the log (bytes)."""
    path = os.path.join(str(tmp_path), name)
    with open(path, "wb") as f:
        f.write(log)
    r = subprocess.run([tool, path], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def splits_of(tool, log, tmp_path):
    code, out, err = run(tool, log, tmp_path)
    assert code == 0, err
    lines = out.splitlines()
    assert len(lines) == 1, out
    return json.loads(lines[0])


def rules_laps(lib, log):
    """The completed laps' times (rules_lap_frames, non-zero) the PC rules give for the log's buttons and seed."""
    seed, frames = struct.unpack_from("<II", log, 12)
    lib.game_init(seed)
    for k in T.decode_log(log)[:frames]:
        lib.game_step(k)
    return [t for t in (lib.rules_lap_frames(i) for i in (1, 2, 3)) if t]


def shipped(name):
    path = os.path.join(DEVICECHECK, name)
    if not os.path.exists(path):
        pytest.skip("%s is not in this sandbox" % path)
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture(scope="module")
def rec(lib):
    """out/librules.so with the recorder's signatures (ghostgen.load)."""
    return G.load(lib)


@pytest.fixture(scope="module")
def route_log(rec):
    """tests/routes/full_run.keys up to the end of the run, encoded by the kit's recorder from seed 0."""
    return G.record(rec, T.pc_run_end(rec, load_keys("full_run.keys")))


@pytest.mark.parametrize("which", ["shipped", "recorded"])
def test_the_route_log_gives_its_three_laps(which, rec, route_log, replay_tool, splits_tool, tmp_path):
    log = shipped("MDGP.acl") if which == "shipped" else route_log
    got = splits_of(splits_tool, log, tmp_path)
    rep = T.replay(replay_tool, log)
    assert rep["hash_matches"] and rep["complete"] and rep["finished"]
    assert got == {"game": "MDGP", "kind": "lap", "splits": ROUTE_LAPS, "time_frames": 6076, "finished": True,
                   "final_hash": rep["final_hash"]}
    assert sum(got["splits"]) == got["time_frames"] == rep["time_frames"]
    assert got["splits"] == rules_laps(rec, log)


def test_the_json_line_is_exact(route_log, replay_tool, splits_tool, tmp_path):
    code, out, err = run(splits_tool, route_log, tmp_path)
    assert code == 0 and err == ""
    final_hash = T.replay(replay_tool, route_log)["final_hash"]
    assert out == ('{"game":"MDGP","kind":"lap","splits":[2087,1995,1994],"time_frames":6076,"finished":true,'
                   '"final_hash":%d}\n' % final_hash)


def test_the_seeded_unfinished_log_gives_no_laps(rec, replay_tool, splits_tool, tmp_path):
    """The device check's seeded run: 1500 route frames under a seed nonce, then quit, before lap 1 was done."""
    log = shipped("MDGP.seeded.acl")
    got = splits_of(splits_tool, log, tmp_path)
    rep = T.replay(replay_tool, log)
    assert struct.unpack_from("<I", log, 12)[0] != 0
    assert got["finished"] is False and got["splits"] == [] == rules_laps(rec, log)
    assert got["time_frames"] == rep["time_frames"] and got["final_hash"] == rep["final_hash"]


def test_a_run_quit_in_lap_2_gives_lap_1_only(rec, replay_tool, splits_tool, tmp_path):
    keys = load_keys("full_run.keys")
    rec.game_init(0)
    for i, k in enumerate(keys):
        rec.game_step(k)
        if rec.rules_lap_frames(1):
            break
    quit_run = T.pc_run_end(rec, keys[:i + 300] + [START, 0, SELECT] + [0] * 3000)
    log = G.record(rec, quit_run)
    got = splits_of(splits_tool, log, tmp_path)
    rep = T.replay(replay_tool, log)
    assert rep["hash_matches"] and rep["complete"] and rep["claims_match"] and not rep["finished"]
    assert got["finished"] is False
    assert got["splits"] == [ROUTE_LAPS[0]] == rules_laps(rec, log)
    assert got["time_frames"] == rep["time_frames"] and got["final_hash"] == rep["final_hash"]


def test_another_games_log_exits_2(route_log, replay_tool, splits_tool, tmp_path):
    rush = bytearray(route_log)
    rush[4:8] = b"RUSH"
    for log in (bytes(rush), b"NOPE" + route_log[4:], route_log[:20]):
        code, out, err = run(splits_tool, log, tmp_path)
        assert (code, out) == (2, "") and err.strip()
        assert run(replay_tool, log, tmp_path)[0] == 2        # as arcade_replay does


def test_the_shipped_rush_log_exits_2(splits_tool, tmp_path):
    code, out, err = run(splits_tool, shipped("RUSH.acl"), tmp_path)
    assert (code, out) == (2, "") and err.strip()


def test_usage_and_a_missing_file_exit_2(splits_tool, tmp_path):
    for cmd in ([splits_tool], [splits_tool, os.path.join(str(tmp_path), "none.acl")]):
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert (r.returncode, r.stdout) == (2, "") and r.stderr.strip()
