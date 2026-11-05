"""A bot that plays SHIP IT! on the PC rules (out/librules.so through ctypes): it walks to rules_target() along
the floor the rules allow, presses A when rules_hint() offers something useful, holds A to commit, and presses
each slide's button in the pitch. Bot(so).play() plays from the title to SHIPPED (or the deadline).

sloppy=True plays like a hesitant first run: it stands still for 45 frames after every action, and for 8
frames after every 24 frames of walking. tests/test_tuning.py pins both bots' ship hours."""
import json
import os

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A, B, START, RIGHT, LEFT, UP, DOWN = 0x001, 0x002, 0x008, 0x010, 0x020, 0x040, 0x080
SC_TITLE, SC_PLAY, SC_CLEAR, SC_MISSED, SC_HOWTO, SC_NIGHTFALL, SC_DEMODAY, SC_WALKOUT = range(8)
HINT_GIVE, HINT_COMMIT = 2, 6
ITEM_CHAI, ITEM_LAPTOP = 1, 2
ROOM_HALL = 1
DIRS = [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy]
SPOT = {0: "COUNTER", 1: "HAND0", 2: "HAND1", 3: "HAND2", 4: "ROUTER", 5: "DOOR", 6: "SHELF",
        14: "HAND0", 15: "ORB", 16: "STAGE"}
SIZE = {0: (352, 240), 1: (560, 320)}                   # room -> image size in pixels


def setup(so):
    import ctypes
    u8, u16, u32, i16 = ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint32, ctypes.c_int16
    for name in ("rules_scene", "rules_carrying", "rules_hint", "rules_target", "rules_act", "rules_bug_desk",
                 "rules_room", "rules_verified", "rules_slide", "rules_stumble", "rules_hour", "rules_walkable"):
        getattr(so, name).restype = u8
    for name in ("rules_px", "rules_py", "rules_pitch_key"):
        getattr(so, name).restype = u16
    for name in ("rules_run_frames", "rules_split"):
        getattr(so, name).restype = u32
    so.rules_step.argtypes = [u16]
    so.rules_bug_desk.argtypes = [u8]
    so.rules_split.argtypes = [u8]
    so.rules_walkable.argtypes = [i16, i16]


class Bot:
    def __init__(self, so, sloppy=False):
        setup(so)
        self.so = so
        self.sloppy = sloppy
        self.keys = []
        self.first_chai = None
        self.walked = 0
        self.floors = {}
        self.fields = {}
        self.spots = {}
        for room, name in ((0, "office"), (1, "hall")):
            with open(os.path.join(GAME, "gen", "scene_%s.json" % name)) as f:
                self.spots[room] = json.load(f)["spots"]
        so.rules_init()

    def step(self, k, n=1):
        for _ in range(n):
            self.keys.append(k)
            self.so.rules_step(k)

    # -- the floor, as the rules see it -------------------------------------------------------------------

    def floor(self):
        """feet_ok for every pixel of the current room (and gate state), from rules_walkable itself."""
        so = self.so
        room = so.rules_room()
        key = (room, so.rules_verified())
        if key not in self.floors:
            w, h = SIZE[room]
            walk = bytearray(w * h)
            for y in range(h):
                for x in range(w):
                    walk[y * w + x] = so.rules_walkable(x, y)
            feet = bytearray(w * h)
            for y in range(h):
                row = y * w
                for x in range(3, w - 3):
                    feet[row + x] = walk[row + x - 3] and walk[row + x] and walk[row + x + 3]
            self.floors[key] = feet
        return self.floors[key]

    def field(self, tx, ty):
        """Breadth-first step counts to (tx, ty) over the floor (moves go one axis at a time, so a diagonal step
        needs a clear corner). Cached per room, gate state and target."""
        so = self.so
        room = so.rules_room()
        key = (room, so.rules_verified(), tx, ty)
        if key in self.fields:
            return self.fields[key]
        ok = self.floor()
        w, h = SIZE[room]
        if not ok[ty * w + tx]:
            tx, ty = min(((x - tx) ** 2 + (y - ty) ** 2, (x, y)) for y in range(h) for x in range(w) if ok[y * w + x])[1]
        d = [-1] * (w * h)
        d[ty * w + tx] = 0
        todo = [(tx, ty)]
        for x, y in todo:
            n = d[y * w + x] + 1
            for dx, dy in DIRS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and d[ny * w + nx] < 0 and ok[ny * w + nx] and (
                        ok[y * w + nx] or ok[ny * w + x]):
                    d[ny * w + nx] = n
                    todo.append((nx, ny))
        self.fields[key] = d
        return d

    # -- choices ----------------------------------------------------------------------------------------------

    def target_spot(self):
        so = self.so
        t = so.rules_target()
        spots = self.spots[so.rules_room()]
        if 8 <= t <= 13:                                   # a bug: wait for it at its desk's hand spot
            d = so.rules_bug_desk(t - 8)
            return spots["HAND%d_X" % d], spots["HAND%d_Y" % d]
        return spots[SPOT[t] + "_X"], spots[SPOT[t] + "_Y"]

    def actionable(self):
        """The hint, unless it offers chai to a dev the bot is only walking past (desk 0's hand spot is on the
        way to every desk: giving there would leave the other two dry)."""
        so = self.so
        hint = so.rules_hint()
        t = so.rules_target()
        if hint == HINT_GIVE and 1 <= t <= 3:
            spots = self.spots[0]
            x, y = spots["HAND%d_X" % (t - 1)], spots["HAND%d_Y" % (t - 1)]
            if abs(so.rules_px() - x) > 16 or abs(so.rules_py() - y) > 8:
                return 0
        return hint

    def go(self, tx, ty):
        """Walk down the target's field for up to 30 frames; stop as soon as A would do something, or on arrival.
        Each direction is scored by the worse of its two possible landings after two frames (the walk is 1.5 px
        a frame across, the laptop 1 px), plus a little for pixels already stood on (no ping-pong)."""
        so = self.so
        d = self.field(tx, ty)
        w, h = SIZE[so.rules_room()]
        slow = so.rules_carrying() == ITEM_LAPTOP
        visits = {}
        blocked = set()                                  # directions that did not move us from this pixel
        for _ in range(15):
            if self.actionable() or so.rules_scene() != SC_PLAY or so.rules_slide():
                return
            x, y = so.rules_px(), so.rules_py()
            if d[y * w + x] == 0:
                return
            visits[(x, y)] = visits.get((x, y), 0) + 1
            landings = ((2, 1), (2, 1)) if slow else ((2, 1), (3, 2))

            def score(dx, dy):
                worst = -1
                for ax, ay in ((x + lx * dx, y + ly * dy) for lx, ly in landings):
                    if not (0 <= ax < w and 0 <= ay < h) or d[ay * w + ax] < 0:
                        return None
                    worst = max(worst, d[ay * w + ax])
                lx, ly = landings[1]
                return worst + 4 * visits.get((x + lx * dx, y + ly * dy), 0)
            options = sorted((sc, dx, dy) for dx, dy in DIRS if (dx, dy) not in blocked
                             for sc in [score(dx, dy)] if sc is not None)
            if not options:                              # the last pixels to a spot: one pixel at a time
                options = sorted((d[(y + dy) * w + x + dx], dx, dy) for dx, dy in DIRS if (dx, dy) not in blocked
                                 and 0 <= x + dx < w and 0 <= y + dy < h and d[(y + dy) * w + x + dx] >= 0)
                if not options:
                    return
            _, dx, dy = options[0]
            k = (LEFT if dx < 0 else RIGHT if dx > 0 else 0) | (UP if dy < 0 else DOWN if dy > 0 else 0)
            self.step(k, 2)
            self.walked += 2
            if self.sloppy and self.walked >= 24:
                self.walked = 0
                self.step(0, 8)
            if (so.rules_px(), so.rules_py()) == (x, y):
                blocked.add((dx, dy))
            else:
                blocked.clear()

    # -- the run ----------------------------------------------------------------------------------------------

    def play(self, limit=40000):
        so = self.so
        self.step(0, 60)
        self.step(START)
        self.step(0)
        self.step(A)
        self.step(0)
        while so.rules_scene() in (SC_PLAY, SC_NIGHTFALL, SC_DEMODAY, SC_WALKOUT) and len(self.keys) < limit:
            if so.rules_scene() != SC_PLAY:
                self.step(0)
                continue
            if 1 <= so.rules_slide() <= 5:               # the pitch: each slide's button, then let go
                if so.rules_stumble():
                    self.step(0)
                else:
                    self.step(so.rules_pitch_key())
                    self.step(0)
                    if self.sloppy:
                        self.step(0, 20)
                continue
            hint = self.actionable()
            if hint == HINT_COMMIT:                      # commit: hold A through it, then let go
                self.step(A, 31)
                self.step(0)
                if self.sloppy:
                    self.step(0, 45)
                continue
            if hint:
                before = so.rules_carrying()
                self.step(A)
                self.step(0)
                if self.first_chai is None and before == ITEM_CHAI and so.rules_carrying() == 0:
                    self.first_chai = len(self.keys)
                if self.sloppy:
                    self.step(0, 45)
                continue
            n = len(self.keys)
            self.go(*self.target_spot())
            if len(self.keys) == n:
                self.step(0)                             # arrived, or waiting (a bug still crawling): let time pass
