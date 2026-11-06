"""Known run logs for checking the device's arm64 replay tools, made in the WSL sandbox with the x86 tools.

  cd games/zip && /opt/arca-sandbox/venv/bin/python ../../device/make_testlogs.py

Every game's tests/routes/full_run.keys (SHIP's in game/tests/routes) played headless (gba_run) on the shipped ROM
from a blank cartridge, then the RUN section taken out of the save: a finished run, so it is also PB the handler's
board time and target ghost for that game (the launcher's --testlogs). Each game also gets a seeded run
(<ID>.seeded): the ROM booted with a launcher-style profile carrying a seed nonce, some of the route played under that
seed, then quit from the pause menu (SHIP's: its first chai, then the 36-hour clock left to run out, a missed
deadline), so the device check also proves the arm64 tools replay seeded and unfinished runs exactly as the x86 ones
do.
Writes /opt/arca-sandbox/devicecheck/<name>.acl and <name>.x86.json (the x86 tool's JSON)."""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "games", "common", "py"))
import arcade_test as T  # noqa: E402

S = T.S
SB = "/opt/arca-sandbox"
OUT = os.path.join(SB, "devicecheck")
GAMES = [("rushhour", "RUSH", "rush-hour.gba"), ("zip", "ZIPG", "zip.gba"),
         ("marinedrive", "MDGP", "marine-drive-gp.gba"), ("segfault", "SEGF", "segfault.gba")]
# quitting from play: pause, then give up (SEGFAULT's pause menu: down to Quit, then A)
QUIT = {"RUSH": [T.START, 0, T.SELECT], "ZIPG": [T.START, 0, T.SELECT], "MDGP": [T.START, 0, T.SELECT],
        "SEGF": [T.START, 0, T.DOWN, 0, T.A]}
SEED_NONCE = 0x5EED1234
SEEDED_PLAY = 1500                      # route frames played under the seed before quitting


def keep(name, log):
    gid = name.split(".")[0]
    path = os.path.join(OUT, name + ".acl")
    with open(path, "wb") as f:
        f.write(log)
    r = subprocess.run([os.path.join(SB, "games", "arcade", gid, "arcade_replay"), path], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)
    assert res["hash_matches"] and res["complete"] and res["claims_match"], res
    with open(os.path.join(OUT, name + ".x86.json"), "w") as f:
        f.write(r.stdout)
    print(name, "seed=%08x" % S.parse_log_header(log)["seed"], r.stdout.strip())


def seeded_save(gid):
    return T.save_with(gid.encode(), profile=S.profile_bytes("CHECK", b"\0" * 8, 0, seed_nonce=SEED_NONCE))


def run_log(rom, frames, save_in, gid):
    got = T.run_rom(os.path.join(SB, "games", "built", rom), frames, save_in=save_in, save_out=True)
    log = S.get(bytearray(got["save"]), gid.encode(), S.RUN)
    assert log is not None, "%s: no run was saved" % gid
    return log[0]


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(REPO, "game", "tests", "routes", "full_run.keys")) as f:
        shipped = [int(line, 16) for line in f if line.strip()]
    keep("SHIP", run_log("ship-it.gba", shipped + [0] * 60 + [T.START] + [0] * 60, T.blank_save(), "SHIP"))
    with open(os.path.join(REPO, "game", "tests", "routes", "first_chai.keys")) as f:
        missed = [int(line, 16) for line in f if line.strip()] + [0] * (36 * 450) + [0] * 60
    keep("SHIP.seeded", run_log("ship-it.gba", missed, seeded_save("SHIP"), "SHIP"))
    for d, gid, rom in GAMES:
        with open(os.path.join(REPO, "games", d, "tests", "routes", "full_run.keys")) as f:
            keys = [int(line, 16) for line in f if line.strip()]
        keep(gid, run_log(rom, keys + [0] * 60 + [T.START] + [0] * 60, T.blank_save(), gid))
        seeded = keys[:SEEDED_PLAY] + [0] * 10 + QUIT[gid] + [0] * 120
        keep(gid + ".seeded", run_log(rom, seeded, seeded_save(gid), gid))


if __name__ == "__main__":
    main()
