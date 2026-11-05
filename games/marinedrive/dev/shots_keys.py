"""Screenshots after custom key sequences: dev/shots_keys.py NAME -> tests/out/k_<name>.png. Sequences below."""
import os
import sys

from PIL import Image

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "..", "common", "py"))
import arcade_test as T  # noqa: E402

A, B, START, SELECT, RIGHT, LEFT, R = 1, 2, 8, 4, 0x10, 0x20, 0x100
with open(os.path.join(GAME_DIR, "tests", "routes", "full_run.keys")) as f:
    route = [int(line, 16) for line in f if line.strip()]
race = [0] * 60 + [START, 0, START] + [0] * 181
SEQ = {
    "howto": [0] * 60 + [START] + [0] * 30,
    "pause": race + [A] * 200 + [START] + [0] * 10,
    "drift": race + [A] * 60 + [A | R | LEFT] + [A | R | RIGHT] * 50,
    "pack": race + [A] * 100,
    "reverse": race + [B] * 116,
    "retire": race + [A] * 60 + [START, 0, SELECT] + [0] * 30,
    "wall": race + [A | LEFT] * 90,
}
names = sys.argv[1:] or list(SEQ)
for n in names:
    keys = SEQ[n]
    path = os.path.join(GAME_DIR, "tests", "out", "k_%s.rgba" % n)
    T.run_rom(os.path.join(GAME_DIR, "marinedrive.gba"), keys, save_in=T.blank_save(), shots=[(len(keys), path)])
    with open(path, "rb") as f:
        Image.frombytes("RGBA", (240, 160), f.read()).convert("RGB").resize((480, 320), Image.NEAREST).save(
            path[:-5] + ".png")
    os.remove(path)
print("ok")
