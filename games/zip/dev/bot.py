"""Records tests/routes/full_run.keys: a bot plays ZIP's real level on the PC rules (out/librules.so) from power-on.
Run from the game directory after `make -f tools.mk host`:
    /opt/arca-sandbox/venv/bin/python dev/bot.py
It mostly holds Right. Every frame it looks ahead (game snapshots, PC library only): if holding Right for the next
LOOKAHEAD frames gets it hit, respawned or stuck, it searches jumps (delay, hold length) and picks the one that gets
furthest cleanly. Level hints ('; bot roll <col>' in level/level.txt) make it roll down the hill into the loop at
full speed. The route starts with 60 idle frames (the ROM boots during the first few and drops their keys)."""
import ctypes
import os
import sys

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "..", "common", "py"))
sys.path.insert(0, os.path.join(GAME_DIR, "tests"))
import arcade_test as T  # noqa: E402
from zipsim import A, DOWN, RIGHT, START, setup  # noqa: E402

LOOKAHEAD = 100
ROUTE = os.path.join(GAME_DIR, "tests", "routes", "full_run.keys")


def hints():
    out = []
    with open(os.path.join(GAME_DIR, "level", "level.txt")) as f:
        for line in f:
            if line.startswith("; bot "):
                _, _, action, col = line.split()
                out.append((action, int(col)))
    return out


class Bot:
    def __init__(self, lib):
        self.lib = setup(T.load_lib(lib))
        self.lib.game_snapshot_size.restype = ctypes.c_int
        self.size = self.lib.game_snapshot_size()
        self.keys = []
        self.lib.zip_level_reset()
        self.lib.game_init(0)

    def snap(self):
        buf = ctypes.create_string_buffer(self.size)
        self.lib.game_save(buf)
        return buf

    def load(self, buf):
        self.lib.game_load(buf)

    @property
    def w(self):
        return self.lib.world().contents

    def press(self, k):
        self.lib.game_step(k)
        self.keys.append(k)

    def trial(self, plan):
        """Plays plan (a list of keys) from a snapshot and restores it; returns (clean, progress score)."""
        buf = self.snap()
        w0 = self.w
        hits, resp, w0x = w0.hits, w0.respawns, w0.x
        best_x = w0.x
        for k in plan:
            self.lib.game_step(k)
            w = self.w
            best_x = max(best_x, w.x)
            if self.lib.rules_finished():
                self.load(buf)
                return True, 1 << 30, 1 << 30
        w = self.w
        clean = w.hits == hits and w.respawns == resp
        score = w.x + w.packets * 16 * 256
        progress = best_x - w0x
        self.load(buf)
        return clean, score, progress

    def choose(self):
        """The keys for the next frames: Right, or a jump plan when Right alone runs into trouble."""
        default = [RIGHT] * LOOKAHEAD
        clean, score0, progress = self.trial(default)
        stuck = progress < 64 * 256 and not self.lib.rules_finished()
        if clean and not stuck:
            return [RIGHT]
        best = None
        for delay in (0, 2, 4, 6, 8, 12, 16, 20, 26, 32):
            for hold in (4, 10, 18, 30):
                plan = [RIGHT] * delay + [RIGHT | A] * hold + [RIGHT] * (LOOKAHEAD - delay - hold)
                ok, sc, prog = self.trial(plan)
                if ok and prog >= 64 * 256 and (best is None or sc > best[0]):
                    best = (sc, plan)
            if best is not None and delay >= 8:
                break
        if best is None:
            return [RIGHT]
        plan = best[1]
        # commit up to the end of the jump
        n = next(i for i in range(len(plan) - 1, -1, -1) if plan[i] & A) + 1
        return plan[:n]


def record():
    lib_path = os.path.join(GAME_DIR, "out", "librules.so")
    bot = Bot(lib_path)
    for k in [0] * 60 + [START, 0, START]:
        bot.press(k)
    todo = sorted(hints(), key=lambda h: h[1])
    rolling_until = None
    while not bot.lib.game_ended():
        w = bot.w
        col = (w.x >> 8) // 16
        if todo and col >= todo[0][1]:
            action, c = todo.pop(0)
            if action == "roll":
                bot.press(DOWN)
                rolling_until = c + 24
                continue
            if action == "jump":
                for _ in range(24):
                    bot.press(RIGHT | A)
                continue
        if rolling_until is not None:
            if (w.rolling or w.mode == 2) and col < rolling_until:
                bot.press(0)
                continue
            rolling_until = None
        if bot.lib.rules_finished():
            bot.press(RIGHT)
            continue
        for k in bot.choose():
            bot.press(k)
            if bot.lib.game_ended():
                break
        if len(bot.keys) > 60 * 60 * 5:
            raise SystemExit("the bot did not finish in 5 minutes (x=%d)" % (bot.w.x >> 8))
    with open(ROUTE, "w") as f:
        f.write("".join("%x\n" % k for k in bot.keys))
    r = T.pc_result(lib_path, bot.keys)
    print("%d frames; time %.2f s; packets %d; trophies %d; hits %d" % (
        len(bot.keys), r["time_frames"] / 60.0, r["score"], r["trophies"], bot.w.hits))


if __name__ == "__main__":
    record()
