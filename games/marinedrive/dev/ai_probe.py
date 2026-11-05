"""Diagnostics: the rivals racing alone (player idle): lap times, wall hits, off-track frames."""
import os
import sys
GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "tests"))
sys.path.insert(0, os.path.join(GAME_DIR, "..", "common", "py"))
import conftest as C  # noqa
import arcade_test as T  # noqa

lib = T.load_lib(os.path.join(GAME_DIR, "out", "librules.so"))
for name, rt in C.GETTERS:
    getattr(lib, name).restype = rt
def kart(i):
    k = C.Kart(); lib.rules_kart(i, C.ctypes.byref(k)); return k
lib.game_init(0)
C.to_race.__globals__  # noqa
for k in (8, 0, 8, 0):
    lib.game_step(k)
while lib.rules_scene() == 2:
    lib.game_step(0)
slow = [0] * 4
laps = {}
for f in range(12600):
    lib.game_step(0)
    for i in range(1, 4):
        k = kart(i)
        if k.surface == 2:
            slow[i] += 1
        if (i, k.lap) not in laps:
            laps[(i, k.lap)] = f
    if all(kart(i).finished for i in range(1, 4)):
        break
for i in range(1, 4):
    k = kart(i)
    print("rival %d: finished %d at %d (%.1f s) laps %s walls %d slow %d pos (%d,%d) wp %s" % (
        i, k.finished, k.finish_frame, k.finish_frame / 60, [laps.get((i, l)) for l in range(1, 5)], k.wall_hits,
        slow[i], k.x >> 16, k.y >> 16, k.progress // 16))

if len(sys.argv) > 1 and sys.argv[1] != "walls":
    who = int(sys.argv[1])
    lib.game_init(0)
    for k in (8, 0, 8, 0):
        lib.game_step(k)
    while lib.rules_scene() == 2:
        lib.game_step(0)
    for f in range(int(sys.argv[2])):
        lib.game_step(0)
        k = kart(who)
        if f % int(sys.argv[3]) == 0:
            print(f, "pos (%d,%d) h %d v %.2f surf %d walls %d lap %d cp %d" % (k.x >> 16, k.y >> 16, k.heading,
                  k.speed / 65536, k.surface, k.wall_hits, k.lap, k.cp))

if len(sys.argv) > 1 and sys.argv[1] == "walls":
    lib.game_init(0)
    for k in (8, 0, 8, 0):
        lib.game_step(k)
    while lib.rules_scene() == 2:
        lib.game_step(0)
    last = [0] * 4
    slowrun = [0] * 4
    for f in range(9000):
        lib.game_step(0)
        for i in range(1, 4):
            k = kart(i)
            if k.wall_hits != last[i]:
                print("f %d rival %d wall at (%d,%d) h %d v %.2f pt-sector %d" % (f, i, k.x >> 16, k.y >> 16, k.heading, k.speed / 65536, k.cp))
                last[i] = k.wall_hits
            if k.surface == 2:
                slowrun[i] += 1
            elif slowrun[i]:
                if slowrun[i] > 20:
                    print("f %d rival %d slow for %d ending at (%d,%d)" % (f, i, slowrun[i], k.x >> 16, k.y >> 16))
                slowrun[i] = 0
