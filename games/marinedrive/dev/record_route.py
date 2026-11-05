"""Records tests/routes/demo.keys: a tiny bot plays the PC rules (out/librules.so) from power-on, steering the dot
straight at the goal. Run from the game directory after `make -f tools.mk host`:
    /opt/arca-sandbox/venv/bin/python dev/record_route.py
The route starts with 60 idle frames: the ROM boots during the first few, and its lost frames must be idle."""
import os
import sys

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "..", "common", "py"))
sys.path.insert(0, os.path.join(GAME_DIR, "tests"))
import arcade_test as T  # noqa: E402
from conftest import tuning  # noqa: E402

lib = T.load_lib(os.path.join(GAME_DIR, "out", "librules.so"))
lib.rules_x.restype = lib.rules_y.restype = T.ctypes.c_int16
keys = [0] * 60 + [T.START]
lib.game_init(0)
for k in keys:
    lib.game_step(k)
gx, gy = tuning("GOAL_X"), tuning("GOAL_Y")
while not lib.game_ended():
    x, y = lib.rules_x(), lib.rules_y()
    k = (T.RIGHT if x < gx else T.LEFT if x > gx else 0) | (T.DOWN if y < gy else T.UP if y > gy else 0)
    lib.game_step(k)
    keys.append(k)
with open(os.path.join(GAME_DIR, "tests", "routes", "demo.keys"), "w") as f:
    f.write("".join("%x\n" % k for k in keys))
print("%d frames" % len(keys))
