"""The real inputs under each game's reel footage, for the reel's live input log (src/acts/GameReel.tsx).

  python video/briefing/prep/reel_keys.py   -> video/briefing/src/acts/reel.json

REEL is the five windows the reel shows; capture_gameplay.py window <ID> <FIRST> 480 reel captured the same ones.
Each entry keeps LEAD frames of input before the window, so the scrolling log is full from the first frame."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DIRS = {"SHIP": "game", "RUSH": "games/rushhour", "ZIPG": "games/zip", "MDGP": "games/marinedrive", "SEGF": "games/segfault"}
REEL = [("SHIP", 5560), ("RUSH", 3600), ("ZIPG", 760), ("MDGP", 248), ("SEGF", 2296)]
COUNT, LEAD = 480, 150

out = {}
for gid, first in REEL:
    with open(os.path.join(REPO, DIRS[gid], "tests", "routes", "full_run.keys")) as f:
        keys = [int(line, 16) for line in f if line.strip()]
    out[gid] = {"first": first, "total": len(keys), "lead": LEAD, "keys": keys[first - LEAD: first + COUNT]}
    print(gid, first, len(keys), "held frames in window:", sum(1 for k in out[gid]["keys"][LEAD:] if k))
with open(os.path.join(HERE, "..", "src", "acts", "reel.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, separators=(",", ":"))
