"""Screenshots of the ROM over the route: dev/shots.py FRAME [FRAME...] -> tests/out/shot_<frame>.png
(frames are 1-based over tests/routes/full_run.keys, then idle)."""
import os
import sys

from PIL import Image

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "..", "common", "py"))
import arcade_test as T  # noqa: E402

OUT = os.path.join(GAME_DIR, "tests", "out")
frames_at = [int(a) for a in sys.argv[1:]]
with open(os.path.join(GAME_DIR, "tests", "routes", "full_run.keys")) as f:
    keys = [int(line, 16) for line in f if line.strip()]
keys = keys + [0] * max(0, max(frames_at) - len(keys))
shots = [(n, os.path.join(OUT, "shot_%d.rgba" % n)) for n in frames_at]
T.run_rom(os.path.join(GAME_DIR, "marinedrive.gba"), keys[:max(frames_at)], save_in=T.blank_save(), shots=shots)
for n, path in shots:
    with open(path, "rb") as f:
        Image.frombytes("RGBA", (240, 160), f.read()).convert("RGB").resize((480, 320), Image.NEAREST).save(
            path[:-5] + ".png")
    os.remove(path)
print("ok")
