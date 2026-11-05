"""Record the test routes on the PC rules with the route bot (dev/bot.py):
  tests/routes/full_run.keys     from the title through all three acts to SHIPPED
  tests/routes/first_chai.keys   the same run up to the first chai delivery (the clock starts then)
Re-run after any change to the layout or the tuning:
  (in the sandbox, from game/) source dev/env.sh; $SANDBOX/venv/bin/python dev/record_route.py"""
import ctypes
import os
import sys

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME, "tests"))
sys.path.insert(0, os.path.join(GAME, "dev"))
from conftest import SC_CLEAR, sh  # noqa: E402
import bot  # noqa: E402

sh("make", "-f", "tools.mk", "host")
so = ctypes.CDLL(os.path.join(GAME, "out", "librules.so"))
b = bot.Bot(so)
b.play()
assert so.rules_scene() == SC_CLEAR and so.rules_act() == 3, "the bot did not ship"
assert b.first_chai is not None
routes = os.path.join(GAME, "tests", "routes")
os.makedirs(routes, exist_ok=True)
with open(os.path.join(routes, "full_run.keys"), "w") as f:
    f.write("".join("%x\n" % k for k in b.keys))
with open(os.path.join(routes, "first_chai.keys"), "w") as f:
    f.write("".join("%x\n" % k for k in b.keys[:b.first_chai]))
for old in ("act1_clear.keys", "act2_clear.keys"):
    if os.path.exists(os.path.join(routes, old)):
        os.remove(os.path.join(routes, old))
print("full_run.keys: %d frames, shipped at hour %d" % (len(b.keys), so.rules_hour()))
print("first_chai.keys: %d frames" % b.first_chai)
