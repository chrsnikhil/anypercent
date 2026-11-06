"""dev/ghostgen.py: the route bot with a handicap per lap, each run encoded by the kit's recorder and checked by the
real replay tools. The default set is run twice as the owner runs it (two processes at once, the second with
--beat), so both runs and their logs can be compared."""
import ctypes
import hashlib
import json
import os
import re
import struct
import subprocess
import sys

import pytest

from conftest import GAME_DIR, Kart, SC_RACE, T, load_keys

sys.path.insert(0, os.path.join(GAME_DIR, "dev"))
import ghostgen as G  # noqa: E402

B, R = T.B, 0x100
# The spec's table: each variant's laps in frames (the bot is deterministic, so a drift means the rules or the bot
# changed).
TABLE = {
    "v1 late fade": [2087, 1995, 2088],
    "v2 slow start": [2248, 1994, 1994],
    "v3 mid-race dip": [2087, 2088, 1994],
    "v4 last lap only": [2168, 2078, 1994],
    "v5 fast opener": [2087, 2080, 2077],
    "v6 steady": [2168, 2078, 2079],
}
PLANS = {
    "v1 late fade": {"3": {"nodrift": True, "lift": 3}},
    "v2 slow start": {"1": {"stall": [0.4, 60], "nodrift": True}},
    "v3 mid-race dip": {"2": {"nodrift": True, "lift": 3}},
    "v4 last lap only": {"1": {"nodrift": True}, "2": {"nodrift": True}},
    "v5 fast opener": {"2": {"nodrift": True}, "3": {"nodrift": True}},
    "v6 steady": {"1": {"nodrift": True}, "2": {"nodrift": True}, "3": {"nodrift": True}},
}
FIELDS = ["file", "name", "plan", "frames", "time", "splits", "log_h", "tool", "gen"]


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def git_head():
    return subprocess.run(["git", "-c", "safe.directory=*", "rev-parse", "--short", "HEAD"], cwd=GAME_DIR,
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture(scope="module")
def rec(lib):
    return G.load(lib)


@pytest.fixture(scope="module")
def route_log(rec):
    return G.record(rec, T.pc_run_end(rec, load_keys("full_run.keys")))


@pytest.fixture(scope="module")
def runs(lib, replay_tool, splits_tool, route_log, tmp_path_factory):
    """[(out dir, manifest, stdout)] of two runs of the default set; the second has --beat on the route log."""
    base = tmp_path_factory.mktemp("ghostgen")
    beat = str(base / "route.acl")
    with open(beat, "wb") as f:
        f.write(route_log)
    outs = [str(base / "one" / "default"), str(base / "two" / "default")]
    cmds = [[sys.executable, "dev/ghostgen.py", "--out", outs[0]],
            [sys.executable, "dev/ghostgen.py", "--out", outs[1], "--set", "default", "--beat", beat]]
    procs = [subprocess.Popen(c, cwd=GAME_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for c in cmds]
    got = []
    for out, p in zip(outs, procs):
        stdout, stderr = p.communicate(timeout=600)
        assert p.returncode == 0, stdout + stderr
        with open(os.path.join(out, "manifest.json")) as f:
            got.append((out, json.load(f), stdout))
    return got


def logs(run):
    out, manifest, _ = run
    for row in manifest:
        with open(os.path.join(out, row["file"]), "rb") as f:
            yield row, f.read()


def test_the_default_set_is_six_finished_logs_the_real_tool_replays(runs, replay_tool):
    out, manifest, _ = runs[0]
    assert [r["file"] for r in manifest] == ["v%d.acl" % i for i in range(1, 7)]
    assert [r["name"] for r in manifest] == list(TABLE)
    assert sorted(os.listdir(out)) == sorted(["manifest.json"] + [r["file"] for r in manifest])
    assert os.listdir(os.path.dirname(out)) == ["default"]                  # no staging left beside it
    for row, log in logs(runs[0]):
        rep = T.replay(replay_tool, log)
        assert rep["game"] == "MDGP" and struct.unpack_from("<I", log, 12)[0] == 0          # seed 0
        assert rep["hash_matches"] and rep["complete"] and rep["claims_match"] and rep["finished"], row["name"]
        assert rep["time_frames"] == row["frames"] == sum(row["splits"])
        assert len(log) <= 65536


def test_the_sha256_values_are_distinct_and_are_log_h(runs):
    hashes = [hashlib.sha256(log).hexdigest() for _, log in logs(runs[0])]
    assert len(set(hashes)) == len(hashes) == 6
    assert hashes == [r["log_h"] for r in runs[0][1]]


def test_the_splits_are_the_rules_lap_times(runs, rec, replay_tool, splits_tool, tmp_path):
    for row, log in logs(runs[0]):
        path = str(tmp_path / row["file"])
        with open(path, "wb") as f:
            f.write(log)
        got = json.loads(subprocess.run([splits_tool, path], capture_output=True, text=True, check=True).stdout)
        rep = T.replay(replay_tool, log)
        rec.game_init(0)
        for k in T.decode_log(log):
            rec.game_step(k)
        laps = [rec.rules_lap_frames(i) for i in (1, 2, 3)]
        assert got["splits"] == row["splits"] == laps and all(laps), row["name"]
        assert sum(got["splits"]) == got["time_frames"] == rep["time_frames"]
        assert got["final_hash"] == rep["final_hash"] and got["finished"] is True


def test_two_runs_are_byte_identical(runs):
    (out1, m1, _), (out2, m2, _) = runs
    assert m1 == m2
    for row in m1:
        with open(os.path.join(out1, row["file"]), "rb") as a, open(os.path.join(out2, row["file"]), "rb") as b:
            assert a.read() == b.read(), row["file"]
    with open(os.path.join(out1, "manifest.json"), "rb") as a, open(os.path.join(out2, "manifest.json"), "rb") as b:
        assert a.read() == b.read()


def test_at_least_two_variants_lead_a_lap(runs):
    manifest = runs[0][1]
    leaders = [{r["name"] for r in manifest if r["splits"][k] == min(x["splits"][k] for x in manifest)}
               for k in range(3)]
    assert len(set().union(*leaders)) >= 2
    assert not set.intersection(*leaders), "one variant leads every lap"
    assert not [w for w in G.set_warnings(manifest) if "lead" in w]


def test_the_laps_match_the_spec_table(runs):
    for row in runs[0][1]:
        want = TABLE[row["name"]]
        assert all(abs(a - b) <= 3 for a, b in zip(row["splits"], want)), (row["name"], row["splits"], want)
        assert len(row["splits"]) == 3


def test_the_manifest_rows(runs, replay_tool):
    head = git_head()
    tool = "arcade_replay sha256:" + sha256(replay_tool)[:12]
    for i, row in enumerate(runs[0][1], 1):
        assert list(row) == FIELDS
        assert row["plan"] == PLANS[row["name"]]
        assert row["tool"] == tool
        assert row["gen"] == "ghostgen v%d seed 0 @%s" % (i, head)
        assert re.fullmatch(r"ghostgen v\d seed 0 @[0-9a-f]{7,40}", row["gen"])
        assert row["time"] == G.clock(row["frames"])


def test_the_clock_is_m_ss_cc_at_60_fps():
    assert [G.clock(f) for f in (6076, 6170, 6169, 6414, 0, 3599, 3600, 36000)] == [
        "1:41.27", "1:42.83", "1:42.82", "1:46.90", "0:00.00", "0:59.98", "1:00.00", "10:00.00"]


def test_the_printed_table_has_every_variant_and_gen(runs):
    _, manifest, stdout = runs[0]
    for row in manifest:
        line = next((l for l in stdout.splitlines() if l.startswith(row["file"][:-4] + " ")), "")
        for part in (row["name"], " ".join(map(str, row["splits"])), str(row["frames"]), row["time"],
                     row["log_h"][:12], row["gen"]):
            assert part in line, (part, line)
    assert "warning" not in stdout


def expected_warnings(manifest, beat_splits, beat_time):
    want = ["lap %d: no variant is faster than %d" % (k + 1, t) for k, t in enumerate(beat_splits)
            if min(r["splits"][k] for r in manifest) >= t]
    n = sum(r["frames"] < beat_time for r in manifest)
    return want + (["%d variants are faster overall than %d (want 3)" % (n, beat_time)] if n < 3 else [])


def test_beat_warns_and_never_fails(runs):
    """The second run beat the route log (faster than every variant overall): it warned and still kept every log."""
    manifest, stdout = runs[1][1], runs[1][2]
    want = expected_warnings(manifest, [2087, 1995, 1994], 6076)
    assert "0 variants are faster overall than 6076 (want 3)" in want and len(want) >= 2
    assert [l[len("warning: "):] for l in stdout.splitlines() if l.startswith("warning: ")] == want
    owner = {"splits": [2140, 2165, 2109], "time_frames": 6414}         # ANY-6PS's listed run
    assert G.set_warnings(manifest, owner) == []
    times = sorted(r["frames"] for r in manifest)
    close = {"splits": [min(r["splits"][0] for r in manifest), 9999, 9999], "time_frames": times[1] + 1}
    assert G.set_warnings(manifest, close) == expected_warnings(manifest, close["splits"], times[1] + 1)
    assert len(G.set_warnings(manifest, close)) == 2


def test_the_plans_take_effect(runs, rec):
    """No R in a nodrift lap, R in every other lap (the bot drifts each lap), and v2's 60-frame stall in lap 1."""
    for row, log in logs(runs[0]):
        nodrift = {int(lap) for lap, h in row["plan"].items() if h.get("nodrift")}
        drifted, b_runs, run_len = set(), [], 0
        rec.game_init(0)
        for k in T.decode_log(log):
            kart = Kart()
            rec.rules_kart(0, ctypes.byref(kart))
            if rec.rules_scene() == SC_RACE and k & R:
                drifted.add(kart.lap)
            run_len = run_len + 1 if k == B else 0
            if run_len == 60:
                b_runs.append(kart.lap)
            rec.game_step(k)
        assert drifted == {1, 2, 3} - nodrift, row["name"]
        assert b_runs == ([1] if "stall" in row["plan"].get("1", {}) else []), row["name"]


def test_the_recorder_refuses_a_full_log(rec):
    with pytest.raises(G.GenError, match="full"):
        G.record(rec, load_keys("full_run.keys"), cap=64)


def test_a_failed_check_keeps_nothing(monkeypatch, tmp_path, lib, replay_tool, splits_tool):
    """Two equal plans give two equal logs: the distinct-sha256 check fails, the run exits non-zero, nothing is
    written."""
    monkeypatch.setitem(G.SETS, "twins", [("t1 twin", {"3": {"nodrift": True}}), ("t2 twin", {"3": {"nodrift": True}})])
    parent = tmp_path / "ghostgen"
    assert G.main(["--out", str(parent / "twins"), "--set", "twins"]) != 0
    assert not parent.exists() or not list(parent.iterdir())


def test_an_out_dir_that_is_not_a_ghostgen_output_is_left_alone(tmp_path, lib, replay_tool, splits_tool):
    out = tmp_path / "mine"
    out.mkdir()
    (out / "notes.txt").write_text("keep me")
    assert G.main(["--out", str(out)]) != 0
    assert os.listdir(str(out)) == ["notes.txt"] and (out / "notes.txt").read_text() == "keep me"
