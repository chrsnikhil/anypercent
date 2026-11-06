"""Real numbers for THE HANDLER (src/acts/Handler.tsx): "your" Marine Drive GP run on the board, beside RIA's (the
shipped test log, device/make_testlogs.py). Like make_coach.py: the recorded route with one hesitation (the player lets
go of everything for N frames, then carries on with the same inputs), searched on the PC rules so the run still
finishes, then played for real on the ROM (gba_run, from a blank cartridge) and its log replayed by the PC tool, so
both times on screen come from the tools.

  (WSL) cd games/zip && /opt/arca-sandbox/venv/bin/python ../../video/briefing/prep/make_handler_run.py [search|make]
        search: print the candidates; make (default): write public/handler/run.json from CHOICE"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "games", "common", "py"))
import arcade_test as T  # noqa: E402

S = T.S
SB = "/opt/arca-sandbox"
LIB = os.path.join(REPO, "games", "marinedrive", "out", "librules.so")
ROM = os.path.join(SB, "games", "built", "marine-drive-gp.gba")
TOOL = os.path.join(SB, "games", "arcade", "MDGP", "arcade_replay")
TESTLOG = os.path.join(SB, "devicecheck", "MDGP.acl")
OUT = os.path.join(HERE, "..", "public", "handler")
TAIL = [0] * 60 + [T.START] + [0] * 60          # as device/make_testlogs.py: finish, then back out to save the run
CHOICE = (5989, 20)                              # (frame of the route, frames held still): from a search; 30+ frames
                                                # held anywhere before the last turn leaves the route off course

with open(os.path.join(REPO, "games", "marinedrive", "tests", "routes", "full_run.keys")) as f:
    KEYS = [int(line, 16) for line in f if line.strip()]


def variant(at, n):
    return KEYS[:at] + [0] * n + KEYS[at:]


def search():
    route = T.pc_result(LIB, KEYS + TAIL)
    print("route:", route)
    for n in (20, 30, 45):
        for at in range(len(KEYS) - 1200, len(KEYS) - 60, 60):
            r = T.pc_result(LIB, variant(at, n) + TAIL)
            if r["finished"]:
                print("at %5d hold %3d -> %d frames (+%d)" % (at, n, r["time_frames"], r["time_frames"] - route["time_frames"]))


def replay(log_bytes):
    with tempfile.NamedTemporaryFile(suffix=".acl", delete=False) as f:
        f.write(log_bytes)
        path = f.name
    try:
        return json.loads(subprocess.run([TOOL, path], capture_output=True, text=True, check=True).stdout)
    finally:
        os.unlink(path)


def make():
    at, n = CHOICE
    got = T.run_rom(ROM, variant(at, n) + TAIL, save_in=T.blank_save(), save_out=True)
    log = S.get(bytearray(got["save"]), b"MDGP", S.RUN)
    assert log is not None, "no run was saved"
    run = replay(bytes(log[0]))
    with open(TESTLOG, "rb") as f:
        ria = replay(f.read())
    for r in (run, ria):
        assert r["hash_matches"] and r["complete"] and r["claims_match"] and r["finished"], r
    os.makedirs(OUT, exist_ok=True)
    out = {"choice": {"at": at, "hold": n}, "run": run, "ria": ria}
    with open(os.path.join(OUT, "run.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("run", run["time_frames"], "ria", ria["time_frames"], "->", os.path.join(OUT, "run.json"))


if __name__ == "__main__":
    search() if sys.argv[1:] == ["search"] else make()
