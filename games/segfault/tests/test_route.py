"""The finishing route (dev/bot.py -> tests/routes/full_run.keys) and the level's tuning it pins."""
import os
import subprocess
import sys
import tempfile

import arcade_test as T
from conftest import GAME_DIR, load_keys


def test_tuning(lib):
    """The bot squashes all 25 bugs, finds the secret room and reboots the build server in 1:15-2:30 (the
    controller's band for a near-optimal scripted player on the 48 x 48 level; humans take longer)."""
    keys = load_keys("full_run.keys")
    assert keys[:60] == [0] * 60
    res = T.pc_result(lib, T.pc_run_end(lib, keys))
    assert res["finished"] and res["score"] == 25, res
    assert res["trophies"] & (1 | 4 | 8) == (1 | 4 | 8), res          # all bugs, under 3:00, the secret room
    assert 75 * 60 <= res["time_frames"] <= 150 * 60, res


def test_the_bot_reproduces_the_route(lib):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "route.keys")
        subprocess.run([sys.executable, os.path.join(GAME_DIR, "dev", "bot.py"), "--out", out], check=True,
                       capture_output=True)
        with open(out) as f:
            assert [int(x, 16) for x in f if x.strip()] == load_keys("full_run.keys")
