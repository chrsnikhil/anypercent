"""The real numbers behind THE CHECK (src/acts/Check.tsx): the PC replay tool run on each game's device-check log,
its exact stdout, the log's size and how long the check took on this laptop.

  (WSL) /opt/arca-sandbox/venv/bin/python video/briefing/prep/make_check.py   -> video/briefing/src/acts/check.json

Each check runs 5 times and the median wall time (process start to exit) is kept."""
import json
import os
import statistics
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SB = "/opt/arca-sandbox"
out = []
for gid in ("RUSH", "ZIPG", "MDGP", "SEGF", "SHIP"):           # the film's run first; SHIP's check run misses its deadline
    tool, log = f"{SB}/games/arcade/{gid}/arcade_replay", f"{SB}/devicecheck/{gid}.acl"
    times, stdout = [], None
    for _ in range(5):
        t = time.perf_counter()
        r = subprocess.run([tool, log], capture_output=True, text=True, check=True)
        times.append(time.perf_counter() - t)
        stdout = r.stdout.strip()
    v = json.loads(stdout)
    assert v["hash_matches"] and v["complete"] and v["claims_match"], gid
    out.append({"game": gid, "cmd": f"./arcade_replay {gid}.acl", "stdout": stdout, "bytes": os.path.getsize(log),
                "ms": round(statistics.median(times) * 1000, 1), "frames": v["frames"], "hash": "%08X" % v["final_hash"]})
    print(gid, out[-1]["bytes"], "B", out[-1]["ms"], "ms", out[-1]["hash"])
with open(os.path.join(HERE, "..", "src", "acts", "check.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1)
