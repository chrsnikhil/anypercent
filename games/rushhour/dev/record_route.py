"""Records tests/routes/full_run.keys: the bot (dev/bot.py) plays the PC rules from power-on to the venue door.
Run from the game directory after `make -f tools.mk host`:
    /opt/arca-sandbox/venv/bin/python dev/record_route.py [-v]
The route starts with 60 idle frames: the ROM boots during the first few, and its lost frames must be idle."""
import os
import sys
import time

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME, "dev"))
import bot  # noqa: E402

t0 = time.time()
keys, skipped = bot.play(os.path.join(GAME, "out", "librules.so"), verbose="-v" in sys.argv)
with open(os.path.join(GAME, "tests", "routes", "full_run.keys"), "w") as f:
    f.write("".join("%x\n" % k for k in keys))
lib = bot.Sim(os.path.join(GAME, "out", "librules.so")).lib
res = bot.T.pc_result(lib, keys)
print("%d frames, run %d frames (%d:%05.2f), chai %d, trophies %s, skipped %d targets, %.0f s" % (
    len(keys), res["time_frames"], res["time_frames"] // 3600, res["time_frames"] % 3600 / 60.0, res["score"],
    bin(res["trophies"]), len(skipped), time.time() - t0))
