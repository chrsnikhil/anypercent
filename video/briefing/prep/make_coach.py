"""PB's real numbers for THE COACH (src/acts/Coach.tsx): a second, slower Rush Hour run, played on the shipped ROM;
both runs replayed by the PC tool; their ghosts compared by the launcher's own coach.compare(); PB's line from the
launcher's own coach.after_run(), exactly as arcade_bridge.after() feeds it.

The slower run is the recorded route (tests/routes/full_run.keys) with one hesitation: at one moment the player lets go
of everything for N frames, then carries on with the same inputs. The moment and N are searched on the PC rules
(librules.so) so the run still finishes; the run that is kept is then played for real on the ROM (gba_run, from a blank
cartridge) and its log replayed, so every number on screen comes from the tools.

  (WSL) cd games/zip && /opt/arca-sandbox/venv/bin/python ../../video/briefing/prep/make_coach.py [search|make]
        search: print the candidates; make (default): build public/coach/coach.json from the chosen one"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "games", "common", "py"))
sys.path.insert(0, os.path.join(REPO, "launcher"))
import arcade_test as T  # noqa: E402
from arca_launcher import coach  # noqa: E402

S = T.S
SB = "/opt/arca-sandbox"
LIB = os.path.join(REPO, "games", "rushhour", "out", "librules.so")
ROM = os.path.join(SB, "games", "built", "rush-hour.gba")
TOOL = os.path.join(SB, "games", "arcade", "RUSH", "arcade_replay")
OUT = os.path.join(HERE, "..", "public", "coach")
TAIL = [0] * 60 + [T.START] + [0] * 60          # as device/make_testlogs.py: finish, then back out to save the run
CHOICE = (4680, 45)                             # (frame of the route, frames held still): from a search; the route
                                                # only has slack after its last hazard, so the hesitation is near the line

with open(os.path.join(REPO, "games", "rushhour", "tests", "routes", "full_run.keys")) as f:
    KEYS = [int(line, 16) for line in f if line.strip()]


def variant(at, n):
    return KEYS[:at] + [0] * n + KEYS[at:]


def search():
    best = T.pc_result(LIB, KEYS + TAIL)
    print("route:", best)
    for n in (45, 60, 90, 120):
        for at in range(400, len(KEYS) - 200, 100):
            r = T.pc_result(LIB, variant(at, n) + TAIL)
            if r["finished"]:
                print("at %5d hold %3d -> %d frames (+%d)" % (at, n, r["time_frames"], r["time_frames"] - best["time_frames"]))


def play(keys):
    """The ROM played headless from a blank cartridge: the RUN section's log (bytes)."""
    got = T.run_rom(ROM, keys, save_in=T.blank_save(), save_out=True)
    log = S.get(bytearray(got["save"]), b"RUSH", S.RUN)
    assert log is not None, "no run was saved"
    return bytes(log[0])


def replayed(log, name):
    """The tool's JSON verdict and the ghost it draws, for a log kept at public/coach/<name>.acl."""
    path = os.path.join(OUT, name + ".acl")
    with open(path, "wb") as f:
        f.write(log)
    with tempfile.TemporaryDirectory() as tmp:
        g = os.path.join(tmp, "ghost.bin")
        r = subprocess.run([TOOL, path, "--ghost", g], capture_output=True, text=True, check=True)
        with open(g, "rb") as fh:
            ghost = S.parse_ghost(fh.read())
    return json.loads(r.stdout), ghost


def make():
    os.makedirs(OUT, exist_ok=True)
    best_res, best_ghost = replayed(play(KEYS + TAIL), "best")
    run_res, run_ghost = replayed(play(variant(*CHOICE) + TAIL), "run")
    for r in (best_res, run_res):
        assert r["hash_matches"] and r["complete"] and r["claims_match"] and r["finished"], r
    # what arcade_bridge.after() hands the coach: the verified result, the best's time, the two ghosts compared
    res = dict(run_res, new_best=False,
               vs_best={"best_frames": best_res["time_frames"], "splits": coach.compare(run_ghost, best_ghost, finished=True)})
    lines = coach.after_run("Rush Hour", res)
    track = lambda g: [[p[0], p[1], p[3]] for p in g["points"]]
    out = {"hold": {"at": CHOICE[0], "frames": CHOICE[1]},
           "best": {k: best_res[k] for k in ("time_frames", "frames", "final_hash")},
           "run": {k: run_res[k] for k in ("time_frames", "frames", "final_hash")},
           "best_log": "best.acl", "run_log": "run.acl",
           "best_bytes": os.path.getsize(os.path.join(OUT, "best.acl")), "run_bytes": os.path.getsize(os.path.join(OUT, "run.acl")),
           "splits": res["vs_best"]["splits"], "period": best_ghost["period"],
           "best_track": track(best_ghost), "run_track": track(run_ghost),
           "lines": [{"mood": ln.mood, "text": ln.text, "kind": ln.kind} for ln in lines]}
    with open(os.path.join(OUT, "coach.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: v for k, v in out.items() if not k.endswith("_track")}, indent=1))


if __name__ == "__main__":
    {"search": search, "make": make}[sys.argv[1] if len(sys.argv) > 1 else "make"]()
