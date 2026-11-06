"""Real ghost races for the Arkiv demo (src/sponsors/arkiv/Act.tsx, the beat after the board's query): the shipped ROM
played headless (gba_run) with RIA's ghost in its cartridge, exactly as the launcher's bridge races one
(arcade_bridge.before: the replay tool's --ghost output put in the save's GHOST section; the game draws it). RIA is
each game's shipped test log (/opt/arca-sandbox/devicecheck/<ID>.acl). The player is the real slower run the film
already uses: the recorded route with one hesitation (MDGP: make_handler_run.py, 20 frames at route frame 5989; RUSH:
make_coach.py, 45 frames at 4680). Each run is played with the ghost in the save, its log is saved by the game and
replayed by the PC tool, and the act shows only what that replay confirms.

  (WSL) cd games/zip && /opt/arca-sandbox/venv/bin/python ../../video/briefing/prep/sponsors/arkiv_ghosts.py survey
        -> video/briefing/out/sponsors/arkiv/ghost_<ID>.jpg (every 6th frame around the hesitation)
  (WSL) ... arkiv_ghosts.py make
        -> video/briefing/public/sponsors/arkiv/ghost/<ID>/NNNN.png (every 2nd frame of the window) + ghosts.json"""
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
BRIEF = os.path.abspath(os.path.join(HERE, "..", ".."))
REPO = os.path.abspath(os.path.join(BRIEF, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "games", "common", "py"))
import arcade_test as T  # noqa: E402

S = T.S
SB = "/opt/arca-sandbox"
TAIL = [0] * 60 + [T.START] + [0] * 60          # as device/make_testlogs.py: finish, then back out to save the run
# id: (route dir, rom, hesitation (route frame, frames held), window (first route frame, count), title)
GAMES = {
    "MDGP": ("games/marinedrive", "marine-drive-gp.gba", (5989, 20), (6010, 290), "MARINE DRIVE GP"),
    "RUSH": ("games/rushhour", "rush-hour.gba", (4680, 45), (4690, 300), "RUSH HOUR"),
}
EVERY = 2                                       # one image every 2 game frames (the act shows each twice)
OUT = os.path.join(BRIEF, "public", "sponsors", "arkiv", "ghost")


def keys(gid):
    d, _, (at, n), _, _ = GAMES[gid]
    with open(os.path.join(REPO, d, "tests", "routes", "full_run.keys")) as f:
        k = [int(line, 16) for line in f if line.strip()]
    return k[:at] + [0] * n + k[at:] + TAIL


def tool(gid, path, *extra):
    return subprocess.run([os.path.join(SB, "games", "arcade", gid, "arcade_replay"), path, *extra], capture_output=True, text=True, check=True)


def route_log(gid):
    """The recorded route played from a blank cartridge, as device/make_testlogs.py makes a shipped test log."""
    d = GAMES[gid][0]
    with open(os.path.join(REPO, d, "tests", "routes", "full_run.keys")) as f:
        k = [int(line, 16) for line in f if line.strip()]
    got = T.run_rom(rom(gid), k + TAIL, save_in=T.blank_save(), save_out=True)
    return bytes(S.get(bytearray(got["save"]), gid.encode("ascii"), S.RUN)[0])


def ria(gid):
    """RIA's shipped log: the replay tool's verdict and the ghost it draws (what the launcher puts in the save). With
    no copy in devicecheck, the route is played as make_testlogs.py does; the act shows it only if its replay hash
    equals the shipped log's in src/acts/check.json."""
    log = os.path.join(SB, "devicecheck", gid + ".acl")
    if not os.path.isfile(log):
        log = os.path.join(tempfile.gettempdir(), "arkiv_ria_%s.acl" % gid)
        with open(log, "wb") as f:
            f.write(route_log(gid))
    with tempfile.TemporaryDirectory() as tmp:
        g = os.path.join(tmp, "ghost.bin")
        res = json.loads(tool(gid, log, "--ghost", g).stdout)
        ghost = open(g, "rb").read()
    return res, ghost


def rom(gid):
    return os.path.join(SB, "games", "built", GAMES[gid][1])


def race(gid, save):
    """The slower run played with RIA's ghost in the cartridge; its saved log replayed by the PC tool."""
    got = T.run_rom(rom(gid), keys(gid), save_in=save, save_out=True)
    log = S.get(bytearray(got["save"]), gid.encode("ascii"), S.RUN)
    assert log is not None, "no run was saved"
    with tempfile.NamedTemporaryFile(suffix=".acl", delete=False) as f:
        f.write(bytes(log[0]))
        path = f.name
    try:
        return json.loads(tool(gid, path).stdout)
    finally:
        os.unlink(path)


def shots(gid, save, frames):
    out = []
    k = keys(gid)
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(0, len(frames), 16):              # gba_run takes at most 16 --shot per run
            chunk = frames[i:i + 16]
            pairs = [(fr, os.path.join(tmp, f"{fr}.raw")) for fr in chunk]
            T.run_rom(rom(gid), k[: max(chunk) + 1], shots=pairs, save_in=save)
            out += [(fr, Image.frombytes("RGBA", (240, 160), open(p, "rb").read()).convert("RGB")) for fr, p in pairs]
    return out


def search(gid="SEGF"):                         # Segfault: its hesitation runs finish on the PC rules but save no run on the ROM, so it is not shown
    d = GAMES[gid][0]
    lib = os.path.join(REPO, d, "out", "librules.so")
    with open(os.path.join(REPO, d, "tests", "routes", "full_run.keys")) as f:
        k = [int(line, 16) for line in f if line.strip()]
    base = T.pc_result(lib, k + TAIL)
    print("route:", base)
    for n in (30, 45, 60):
        for at in range(len(k) - 1500, len(k) - 60, 60):
            r = T.pc_result(lib, k[:at] + [0] * n + k[at:] + TAIL)
            if r["finished"]:
                print("at %5d hold %3d -> %d frames (+%d)" % (at, n, r["time_frames"], r["time_frames"] - base["time_frames"]))


def survey():
    dst = os.path.join(BRIEF, "out", "sponsors", "arkiv")
    os.makedirs(dst, exist_ok=True)
    for gid, (_, _, (at, n), _, _) in GAMES.items():
        _, ghost = ria(gid)
        save = T.save_with(gid.encode("ascii"), ghost=ghost)
        imgs = shots(gid, save, list(range(at - 120, at + 240, 6)))
        cols = 10
        sheet = Image.new("RGB", (cols * 240, ((len(imgs) + cols - 1) // cols) * 160))
        d = ImageDraw.Draw(sheet)
        for i, (fr, im) in enumerate(imgs):
            x, y = (i % cols) * 240, (i // cols) * 160
            sheet.paste(im, (x, y))
            d.text((x + 3, y + 3), str(fr), fill=(255, 255, 0))
        sheet.save(os.path.join(dst, f"ghost_{gid}.jpg"), quality=85)
        print(gid, "hold at", at, "for", n, "->", len(imgs), "shots")


def make():
    index = {}
    for gid, (_, _, (at, n), (first, count), title) in GAMES.items():
        r, ghost = ria(gid)
        save = T.save_with(gid.encode("ascii"), ghost=ghost)
        you = race(gid, save)
        for v in (r, you):
            assert v["hash_matches"] and v["complete"] and v["claims_match"] and v["finished"], v
        d = os.path.join(OUT, gid)
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
        imgs = shots(gid, save, list(range(first, first + count, EVERY)))
        for i, (_, im) in enumerate(imgs):
            im.save(os.path.join(d, "%04d.png" % i))
        index[gid] = {"title": title, "ria_frames": r["time_frames"], "ria_hash": "%08X" % r["final_hash"],
                      "you_frames": you["time_frames"], "you_hash": "%08X" % you["final_hash"],
                      "gap_frames": you["time_frames"] - r["time_frames"], "hold": {"at": at, "frames": n},
                      "window": {"first": first, "count": count, "every": EVERY}, "images": len(imgs), "ghost_bytes": len(ghost)}
        print(gid, index[gid])
    with open(os.path.join(OUT, "ghosts.json"), "w") as f:
        json.dump(index, f, indent=1)


if __name__ == "__main__":
    {"survey": survey, "make": make, "search": search}[sys.argv[1] if len(sys.argv) > 1 else "make"]()
