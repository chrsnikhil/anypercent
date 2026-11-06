"""Attract-mode clips: about 3 seconds of real gameplay per lineup game, 30 frames at 10 a second, for the launcher's
booth display (build_library.py --clips-from games/clips puts them in the library).

  arcade games   their verified full-run routes (tests/routes/full_run.keys), replayed headless from a point in
                 the middle of the run (gba_run, raw 240 x 160 frames), with the ghost of the game's shipped test
                 log (the same run, device/make_testlogs.py) started GHOST_LEAD frames ahead, so the clip shows
                 what PB's races look like: her ghost just in front (in Marine Drive GP with the live gap)
  Game Boy       a short scripted play in mGBA (games/reskin/shoot.py)

  /opt/arca-sandbox/venv/bin/python games/clips/make_clips.py [id ...]     (in the WSL sandbox)
Writes games/clips/<id>/<id>-clip-00..29.png and games/clips/sheet.png (every clip's frames, to look at)."""
import os
import subprocess
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "games", "common", "py"))
sys.path.insert(0, os.path.join(REPO, "games", "reskin"))
BUILT = "/opt/arca-sandbox/games/built"
FRAMES, EVERY = 30, 6                                               # 30 frames, one every 6 game frames: 10 fps

# arcade game: (ROM, route, where in the run the clip starts, 0..1, arcade id)
ARCADE = {
    "ship-it": ("ship-it.gba", "game/tests/routes/full_run.keys", 0.31, "SHIP"),
    "rush-hour": ("rush-hour.gba", "games/rushhour/tests/routes/full_run.keys", 0.40, "RUSH"),
    "zip": ("zip.gba", "games/zip/tests/routes/full_run.keys", 0.45, "ZIPG"),
    "marine-drive-gp": ("marine-drive-gp.gba", "games/marinedrive/tests/routes/full_run.keys", 0.30, "MDGP"),
    "segfault": ("segfault.gba", "games/segfault/tests/routes/full_run.keys", 0.40, "SEGF"),
}
GHOST_LEAD = 30                                                     # frames her ghost starts ahead of the route
TESTLOGS, TOOLS = "/opt/arca-sandbox/devicecheck", "/opt/arca-sandbox/games/arcade"
# Game Boy game: (ROM, shoot.py script, first clip frame)
GB = {
    "snake": ("snake.gb", "start@300," + ",".join(f"{d}@{900 + i * 40}" for i, d in
                                                 enumerate(["up", "right", "down", "left"] * 12)), 1000),
    "2048gb": ("2048gb.gb", "start@300,start@420," + ",".join(f"{d}@{600 + i * 18}" for i, d in
                                                            enumerate(["left", "down", "right", "down"] * 20)), 640),
    "rebound": ("rebound.gbc", "start@1500,start@1700,a@1900:2400,right@2100:2700,a@2500:2900", 2150),
}


def lead_ghost(gid):
    """The ghost of gid's shipped test log, started GHOST_LEAD frames ahead: the in-play samples just after its
    first one are dropped (the runtime anchors a ghost there). The same run as the route, so it rides just in front
    of the player. None without a test log or replay tool."""
    import arcade_test as T
    log, tool = os.path.join(TESTLOGS, gid + ".acl"), os.path.join(TOOLS, gid, "arcade_replay")
    if not (os.path.isfile(log) and os.path.isfile(tool)):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "ghost.acg")
        subprocess.run([tool, log, "--ghost", out], check=True, capture_output=True)
        with open(out, "rb") as f:
            g = T.S.parse_ghost(f.read())
    pts = g["points"]
    first = next((i for i, p in enumerate(pts) if p[3] & 0x80), None)
    if first is None:
        return None
    drop = max(1, round(GHOST_LEAD / g["period"]))
    return T.S.ghost_bytes(gid.encode(), g["source_hash"], g["period"], pts[:first] + pts[first + drop:])


def arcade_clip(rom, route, at, gid):
    import arcade_test as T
    ghost = lead_ghost(gid)
    save = T.save_with(gid.encode(), ghost=ghost) if ghost else None   # the classic seed: the route stays on course
    keys = [int(line, 16) for line in open(os.path.join(REPO, route)) if line.strip()]
    start = int(len(keys) * at)
    want = [start + 1 + i * EVERY for i in range(FRAMES)]
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for batch in (want[:15], want[15:]):                        # gba_run takes 16 shots a run
            shots = [(f, os.path.join(tmp, f"{f}.rgba")) for f in batch]
            T.run_rom(os.path.join(BUILT, rom), keys[:max(batch) + 1], save_in=save, shots=shots)
            for _, path in shots:
                out.append(Image.frombytes("RGBA", (240, 160), open(path, "rb").read()).convert("RGB"))
    return out


def gb_clip(rom, script, first):
    import shoot
    want = [first + i * EVERY for i in range(FRAMES)]
    got = shoot.shoot(os.path.join(BUILT, rom), shoot.parse(script), want)
    return [got[f].convert("RGB") for f in want]


def main(ids):
    sheet_rows = []
    for gid in ids or list(ARCADE) + list(GB):
        frames = arcade_clip(*ARCADE[gid]) if gid in ARCADE else gb_clip(*GB[gid])
        d = os.path.join(HERE, gid)
        os.makedirs(d, exist_ok=True)
        for old in os.listdir(d):
            os.remove(os.path.join(d, old))
        for i, im in enumerate(frames):
            im.save(os.path.join(d, f"{gid}-clip-{i:02d}.png"))
        sheet_rows.append(frames[::5])                              # every 5th frame, to look at
        print(gid, len(frames), "frames", frames[0].size, flush=True)
    w = max(sum(f.width + 4 for f in row) for row in sheet_rows)
    sheet = Image.new("RGB", (w, sum(max(f.height for f in row) + 4 for row in sheet_rows)), (24, 24, 32))
    y = 0
    for row in sheet_rows:
        x = 0
        for f in row:
            sheet.paste(f, (x, y))
            x += f.width + 4
        y += max(f.height for f in row) + 4
    sheet.save(os.path.join(HERE, "sheet.png"))


if __name__ == "__main__":
    main(sys.argv[1:])
