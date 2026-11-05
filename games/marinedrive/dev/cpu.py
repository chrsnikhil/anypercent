"""CPU use per frame over the route (g_md_cpu, 1/1000 of a frame) and lag frames: dev/cpu.py [frames]"""
import os
import sys

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "..", "common", "py"))
import arcade_test as T  # noqa: E402

with open(os.path.join(GAME_DIR, "tests", "routes", "full_run.keys")) as f:
    keys = [int(line, 16) for line in f if line.strip()]
n = int(sys.argv[1]) if len(sys.argv) > 1 else len(keys)
rows = T.run_rom(os.path.join(GAME_DIR, "marinedrive.gba"), keys[:n], watch=("g_dbg_steps", "g_md_cpu"),
                 save_in=T.blank_save())["watch"]
lags = [i for i in range(1, len(rows)) if rows[i][0] == rows[i - 1][0] and rows[i][0] > 0]
cpu = [r[1] for r in rows if r[0] > 0]
print("frames %d, lag frames %d (first %s), cpu max %.1f%% mean %.1f%%" % (
    len(rows), len(lags), lags[:10], max(cpu) / 10, sum(cpu) / len(cpu) / 10))
buckets = {}
for i, r in enumerate(rows):
    buckets.setdefault(i // 500, []).append(r[1])
print(" ".join("%d:%d" % (k * 500, max(v) // 10) for k, v in sorted(buckets.items())))
if len(sys.argv) > 2:
    a, b = int(sys.argv[2]), int(sys.argv[3])
    print(" ".join(str(r[1] // 10) for r in rows[a:b]))
