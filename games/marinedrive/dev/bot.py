"""MARINE DRIVE GP's route bot: plays the PC rules (out/librules.so) from power-on and writes
tests/routes/full_run.keys (one hex key mask per frame). Run from the game directory after `make -f tools.mk host`:
    /opt/arca-sandbox/venv/bin/python dev/bot.py [--out PATH] [--quiet]

It drives like a decent player: it steers at a point on the centre line ahead (further at speed) in a lane it picks
(the boost pads' lane before a pad, away from a rival just ahead), brakes for the corners ahead from their radius,
and drifts through the long corners (R held from the corner's entry, released for the boost once charged)."""
import argparse
import ctypes
import math
import os
import sys

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "..", "common", "py"))
sys.path.insert(0, os.path.join(GAME_DIR, "tests"))
sys.path.insert(0, os.path.join(GAME_DIR, "tools", "art"))
import arcade_test as T  # noqa: E402
import conftest as C  # noqa: E402
import track_data as D  # noqa: E402

A, B, START, RIGHT, LEFT, R = T.A, T.B, T.START, T.RIGHT, T.LEFT, 0x100
ONE = 65536


class Bot:
    def __init__(self, lib):
        self.lib = lib
        for name, rt in C.GETTERS:
            getattr(lib, name).restype = rt
        self.pts = C.centre_points(lib)
        self.n = len(self.pts)
        self.top = C.tuning("TOP_ROAD") / ONE
        self.omega = C.tuning("STEER") * 2 * math.pi / 1024
        self.radius = [self._radius(i) for i in range(self.n)]
        lib.rules_lap_frames.restype = ctypes.c_uint32
        self.pads = [(arc // 8, lat) for arc, lat in D.PADS]
        self.pt = None
        self.keys = []

    def _radius(self, i, span=4):
        p = self.pts
        a, b, c = p[(i - span) % self.n], p[i], p[(i + span) % self.n]
        t1 = (b[0] - a[0], b[1] - a[1])
        t2 = (c[0] - b[0], c[1] - b[1])
        ang = math.atan2(t1[0] * t2[1] - t1[1] * t2[0], t1[0] * t2[0] + t1[1] * t2[1])
        return span * 8 / abs(ang) if abs(ang) > 1e-6 else 1e9

    def kart(self, i):
        k = C.Kart()
        self.lib.rules_kart(i, ctypes.byref(k))
        return k

    def step(self, keys):
        self.lib.game_step(keys)
        self.keys.append(keys)

    def nearest(self, x, y):
        if self.pt is None:
            self.pt = min(range(self.n), key=lambda i: (self.pts[i][0] - x) ** 2 + (self.pts[i][1] - y) ** 2)
        best = self.pt
        for d in range(-6, 7):
            i = (self.pt + d) % self.n
            if (self.pts[i][0] - x) ** 2 + (self.pts[i][1] - y) ** 2 < (self.pts[best][0] - x) ** 2 + (
                    self.pts[best][1] - y) ** 2:
                best = i
        self.pt = best
        return best

    def lane_point(self, j, lane):
        a, b = self.pts[(j - 1) % self.n], self.pts[(j + 1) % self.n]
        nx, ny = -(b[1] - a[1]), b[0] - a[0]
        ln = math.hypot(nx, ny) or 1
        return self.pts[j][0] + lane * nx / ln, self.pts[j][1] + lane * ny / ln

    def lane_for(self, pt, me):
        lane = 0.0
        for p, lat in self.pads:                           # line up for a pad ahead
            ahead = (p - pt) % self.n
            if ahead < 30:
                lane = float(lat)
        for i in range(1, 4):                              # a rival just ahead in our lane: pass on the other side
            k = self.kart(i)
            dx, dy = k.x / ONE - me[0], k.y / ONE - me[1]
            d = math.hypot(dx, dy)
            if d < 40:
                h = math.atan2(me[3], me[2])
                along = dx * math.cos(h) + dy * math.sin(h)
                side = -dx * math.sin(h) + dy * math.cos(h)
                if along > 0:
                    lane = -14.0 if side > 0 else 14.0
        return lane

    def drive(self):
        """One race frame's keys."""
        k = self.kart(0)
        x, y = k.x / ONE, k.y / ONE
        v = k.speed / ONE
        pt = self.nearest(x, y)
        h = k.heading * 2 * math.pi / 1024
        lane = self.lane_for(pt, (x, y, math.cos(h), math.sin(h)))
        look = 5 + int(2 * max(v, 0))
        tx, ty = self.lane_point((pt + look) % self.n, lane)
        want = math.atan2(ty - y, tx - x)
        diff = (want - h + math.pi) % (2 * math.pi) - math.pi
        diff_steps = diff * 1024 / (2 * math.pi)
        # the tightest corner in the braking distance ahead sets the speed
        target = self.top * 1.6
        for j in range(0, 40):
            r = self.radius[(pt + j) % self.n]
            vmax = 0.95 * self.omega * r
            # distance to reach it at the brake rate (0x2000 / frame)
            dist = j * 8
            reach = math.sqrt(vmax * vmax + 2 * 0.125 * dist)
            target = min(target, reach)
        keys = 0
        drifting = k.drift != 0
        corner = min(self.radius[(pt + j) % self.n] for j in range(4, 24))
        turn = self._turn(pt)
        if drifting:
            into = 1 if k.drift == 2 else -1
            want_turn = diff_steps * into
            if want_turn > 10:
                keys |= RIGHT if into > 0 else LEFT
            elif want_turn < -2:
                keys |= LEFT if into > 0 else RIGHT
            keeps = corner < 260 and want_turn > -12
            if keeps or k.drift_charge < C.tuning("DRIFT_CHARGE") and want_turn > -8:
                keys |= R
            keys |= A
            return keys
        if diff_steps > 3:
            keys |= RIGHT
        elif diff_steps < -3:
            keys |= LEFT
        if v < target:
            keys |= A
        elif v > target + 0.15:
            keys |= B
        # start a drift at the entry of a long corner, at speed, turning its way
        if 70 < corner < 220 and v > C.tuning("DRIFT_MIN_SPEED") / ONE + 0.3 and turn != 0 and \
                abs(diff_steps) > 6 and (turn > 0) == (diff_steps > 0) and self._long(pt):
            keys = A | R | (RIGHT if turn > 0 else LEFT)
        return keys

    def _turn(self, pt):
        a, b, c = self.pts[pt], self.pts[(pt + 10) % self.n], self.pts[(pt + 20) % self.n]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        return 1 if cr > 0 else -1 if cr < 0 else 0

    def _long(self, pt):
        """The corner ahead keeps turning one way for at least ~50 frames of travel."""
        sign = self._turn(pt)
        span = 0
        for j in range(0, 30, 2):
            if self._turn((pt + j) % self.n) != sign or self.radius[(pt + j) % self.n] > 400:
                break
            span += 2
        return span >= 16

    def run(self, max_frames=20000):
        self.lib.game_init(0)
        for k in [0] * 60 + [START, 0, START, 0]:
            self.step(k)
        while self.lib.rules_scene() == C.SC_COUNTDOWN:
            self.step(A if self.lib.rules_countdown() < 20 else 0)
        while self.lib.rules_scene() in (C.SC_RACE,) and len(self.keys) < max_frames:
            self.step(self.drive())
        while not self.lib.game_ended() and len(self.keys) < max_frames:
            self.step(0)
        return self.keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(GAME_DIR, "tests", "routes", "full_run.keys"))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    lib = T.load_lib(os.path.join(GAME_DIR, "out", "librules.so"))
    bot = Bot(lib)
    keys = bot.run()
    res = T.pc_result(lib, keys)
    k = bot.kart(0)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        f.write("".join("%x\n" % v for v in keys))
    if not a.quiet:
        laps = [lib.rules_lap_frames(i) for i in range(1, 4)]
        print("%d frames; finished %d place %d time %d (%.2f s) laps %s trophies %d walls %d" % (
            len(keys), res["finished"], res["score"], res["time_frames"], res["time_frames"] / 60,
            [round(t / 60, 2) for t in laps], res["trophies"], k.wall_hits))


if __name__ == "__main__":
    main()
