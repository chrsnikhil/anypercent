"""The SEGFAULT bot: plays the PC rules (out/librules.so) from power-on and records tests/routes/full_run.keys.
Each frame it picks a goal -- a bug in sight to shoot, else the nearest live bug by a BFS over the grid, the keycard
reader when it is close or the bugs are done, the secret room on the way, and last the exit terminal -- walks the
BFS path (opening doors with B), turns toward its target and fires when the target sits on the aim line.
Run from the game directory after `make -f tools.mk host`:
    /opt/arca-sandbox/venv/bin/python dev/bot.py [--out tests/routes/full_run.keys]"""
import ctypes
import math
import os
import sys
from collections import deque

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "..", "common", "py"))
sys.path.insert(0, os.path.join(GAME_DIR, "tests"))
import arcade_test as T  # noqa: E402
from conftest import tuning  # noqa: E402

A, B, START, RIGHT, LEFT, UP, DOWN, R, L = T.A, T.B, T.START, T.RIGHT, T.LEFT, T.UP, T.DOWN, T.R, T.L
ONE, HALF = 0x10000, 0x8000
W = H = 48
CELL_FLOOR, CELL_DOOR, CELL_SHELF, CELL_READER, CELL_TERMINAL, CELL_PUSH, CELL_SECRET, CELL_LOCKED = 0, 5, 6, 8, 10, 11, 12, 13
BUG_DEAD = 3
DOOR_FULL = tuning("DOOR_FRAMES")
HIT = tuning("HIT_RADIUS")

READS = {"rules_px": ctypes.c_int32, "rules_py": ctypes.c_int32, "rules_angle": ctypes.c_uint16,
         "rules_cell": ctypes.c_uint8, "rules_door_amount": ctypes.c_uint8, "rules_bug_count": ctypes.c_uint8,
         "rules_bug_x": ctypes.c_int32, "rules_bug_y": ctypes.c_int32, "rules_bug_state": ctypes.c_uint8,
         "rules_has_key": ctypes.c_uint8, "rules_secret_found": ctypes.c_uint8, "rules_health": ctypes.c_uint8,
         "rules_los": ctypes.c_uint8, "rules_scene": ctypes.c_uint8, "rules_dead_timer": ctypes.c_uint16,
         "rules_run_frames": ctypes.c_uint32, "rules_squashed": ctypes.c_uint8, "rules_trophies": ctypes.c_uint32,
         "rules_fire_cooldown": ctypes.c_uint16, "rules_deaths": ctypes.c_uint8}


def load():
    lib = T.load_lib(os.path.join(GAME_DIR, "out", "librules.so"))
    for name, rt in READS.items():
        getattr(lib, name).restype = rt
    lib.rules_los.argtypes = [ctypes.c_int32] * 4
    return lib


def wrap(a):
    return (a + 512) % 1024 - 512


def angle_to(dx, dy):
    return int(round(math.atan2(dy, dx) * 512 / math.pi)) % 1024


class Bot:
    def __init__(self, lib):
        self.g = lib
        self.b_phase = 0

    # ---- the map ---------------------------------------------------------------------------------------------------
    def cell(self, x, y):
        return self.g.rules_cell(x, y)

    def walkable(self, x, y, doors=True, push=False):
        c = self.cell(x, y)
        return c in (CELL_FLOOR, CELL_SECRET) or (doors and c == CELL_DOOR) or (push and c == CELL_PUSH) or (
            doors and c == CELL_LOCKED and self.g.rules_has_key())

    def bfs(self, start, goals, push=False):
        """Path of cells from start to the first goal cell reached (goals: a set), or None."""
        prev = {start: None}
        todo = deque([start])
        while todo:
            c = todo.popleft()
            if c in goals:
                path = []
                while c is not None:
                    path.append(c)
                    c = prev[c]
                return path[::-1]
            x, y = c
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n not in prev and 0 <= n[0] < W and 0 <= n[1] < H and (
                        self.walkable(*n, push=push) or n in goals):
                    prev[n] = c
                    todo.append(n)
        return None

    def cells_of(self, kind):
        return [(x, y) for y in range(H) for x in range(W) if self.cell(x, y) == kind]

    # ---- the player ------------------------------------------------------------------------------------------------
    def me(self):
        g = self.g
        return g.rules_px(), g.rules_py(), g.rules_angle()

    def my_cell(self):
        x, y, _ = self.me()
        return (x >> 16, y >> 16)

    def live_bugs(self):
        g = self.g
        return [(i, g.rules_bug_x(i), g.rules_bug_y(i)) for i in range(g.rules_bug_count())
                if g.rules_bug_state(i) != BUG_DEAD]

    def turn_keys(self, want, a, tol=4):
        e = wrap(want - a)
        if e > tol:
            return RIGHT
        if e < -tol:
            return LEFT
        return 0

    def clear_line(self, x0, y0, x1, y1):
        """The player's body fits along the segment: the centre line and two offset lines are in sight."""
        g = self.g
        d = math.hypot(x1 - x0, y1 - y0) or 1
        ox, oy = int(-(y1 - y0) / d * 0x4800), int((x1 - x0) / d * 0x4800)
        return all(g.rules_los(x0 + sx * ox, y0 + sx * oy, x1 + sx * ox, y1 + sx * oy) for sx in (-1, 0, 1))

    def walk_path(self, path):
        """Keys to follow a BFS path: steer to the farthest of the next few cells in a clear line; open doors."""
        g = self.g
        x, y, a = self.me()
        if len(path) < 2:
            return 0
        nxt = path[1]
        if self.cell(*nxt) in (CELL_DOOR, CELL_LOCKED) and g.rules_door_amount(*nxt) < DOOR_FULL:
            # line up on the door and press B until it opens
            tx, ty = nxt[0] * ONE + HALF, nxt[1] * ONE + HALF
            want = angle_to(tx - x, ty - y)
            k = self.turn_keys(want, a, 6)
            if k:
                return k
            self.b_phase ^= 1
            return B if self.b_phase else 0
        target = nxt
        for c in path[2:5]:
            if self.cell(*c) in (CELL_DOOR, CELL_LOCKED) and g.rules_door_amount(*c) < DOOR_FULL:
                break
            if self.clear_line(x, y, c[0] * ONE + HALF, c[1] * ONE + HALF):
                target = c
            else:
                break
        tx, ty = target[0] * ONE + HALF, target[1] * ONE + HALF
        want = angle_to(tx - x, ty - y)
        e = abs(wrap(want - a))
        k = self.turn_keys(want, a, 3)
        if e < 48:
            k |= UP
        return k

    def use_panel(self, panel):
        """Walk next to a panel cell, face it and press B."""
        here = self.my_cell()
        goals = {(panel[0] + dx, panel[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                 if self.walkable(panel[0] + dx, panel[1] + dy, doors=False)}
        if here in goals:
            x, y, a = self.me()
            # stand near the middle of the cell, then face the panel's centre
            cx, cy = here[0] * ONE + HALF, here[1] * ONE + HALF
            if abs(x - cx) > 0x3000 or abs(y - cy) > 0x3000:
                want = angle_to(cx - x, cy - y)
                k = self.turn_keys(want, a, 4)
                return k | (UP if abs(wrap(want - a)) < 40 else 0)
            want = angle_to(panel[0] * ONE + HALF - x, panel[1] * ONE + HALF - y)
            k = self.turn_keys(want, a, 5)
            if k:
                return k
            self.b_phase ^= 1
            return B if self.b_phase else 0
        path = self.bfs(here, goals)
        return self.walk_path(path) if path else 0

    def fight(self):
        """A live bug in sight within range: aim and fire (keys), or None."""
        g = self.g
        x, y, a = self.me()
        best = None
        for i, bx, by in self.live_bugs():
            d = math.hypot(bx - x, by - y)
            if d < 11 * ONE and g.rules_los(x, y, bx, by) and (best is None or d < best[0]):
                best = (d, i, bx, by)
        if best is None:
            return None
        d, i, bx, by = best
        want = angle_to(bx - x, by - y)
        k = self.turn_keys(want, a, 2)
        c, s = math.cos(a * math.pi / 512), math.sin(a * math.pi / 512)
        cross = abs((bx - x) * s - (by - y) * c)
        along = (bx - x) * c + (by - y) * s
        if along > 0 and cross < HIT * 0.6:
            k |= A
        if d > 6 * ONE and abs(wrap(want - a)) < 30:
            k |= UP
        elif d < 1.6 * ONE:
            k |= DOWN
        return k

    def step_keys(self):
        g = self.g
        if g.rules_dead_timer():
            return 0
        k = self.fight()
        if k is not None:
            return k
        here = self.my_cell()
        bugs = self.live_bugs()
        reader = self.cells_of(CELL_READER)
        push = self.cells_of(CELL_PUSH)
        found = g.rules_secret_found()
        bug_path = None
        if bugs:
            bug_path = self.bfs(here, {(bx >> 16, by >> 16) for _, bx, by in bugs})
        if not found:                                    # the secret room when passing by, or at the end
            if push:
                p = self.bfs(here, set(push), push=True)
                if p and (len(p) < 10 or not bug_path):
                    return self.use_panel(push[0])
            else:
                secret = self.cells_of(CELL_SECRET)
                p = self.bfs(here, set(secret))
                if p and (len(p) < 14 or not bug_path):
                    return self.walk_path(p)
        if reader and not g.rules_has_key():             # the keycard when close, or when no bug is in reach
            p = self.bfs(here, set(reader))
            if p and (len(p) < 10 or not bug_path):
                return self.use_panel(reader[0])
        if bug_path:
            return self.walk_path(bug_path)
        return self.use_panel(self.cells_of(CELL_TERMINAL)[0])


def record(max_frames=20000):
    g = load()
    g.game_init(0)
    keys = [0] * 60 + [START, 0, START, 0]
    for k in keys:
        g.game_step(k)
    bot = Bot(g)
    while not g.game_ended() and len(keys) < max_frames:
        k = bot.step_keys()
        g.game_step(k)
        keys.append(k)
    r = T.Result()
    g.game_result(ctypes.byref(r))
    return keys, {f: getattr(r, f) for f, _ in T.Result._fields_}, g.rules_deaths()


def main():
    out = os.path.join(GAME_DIR, "tests", "routes", "full_run.keys")
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    keys, res, deaths = record()
    t = res["time_frames"]
    print("%d frames, finished %d, time %d:%05.2f, bugs %d, trophies %d, deaths %d" % (
        len(keys), res["finished"], t // 3600, (t % 3600) / 60, res["score"], res["trophies"], deaths))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="\n") as f:
        f.write("".join("%x\n" % k for k in keys))


if __name__ == "__main__":
    main()
