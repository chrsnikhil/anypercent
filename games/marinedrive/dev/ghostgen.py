"""MARINE DRIVE GP's BOT ghost generator: the route bot (dev/bot.py) drives the PC rules with a handicap per lap, and
each run is encoded by the kit's own recorder and checked by the real replay tools before it is kept. Run from the game
directory after `make -f tools.mk host replay splits`:
    /opt/arca-sandbox/venv/bin/python dev/ghostgen.py --out out/ghostgen/default [--set default] [--beat LOG]

A variant's plan maps a lap (1..3) to its handicaps:
    nodrift              R stripped (no drift, so no drift boosts);
    lift: N              A dropped on 1 race frame in N;
    stall: (f, n)        B alone for n frames, from fraction f of the lap's arc (kart.progress modulo the track).
Only drive() changes, so the route bot still re-reads the kart every frame and steers and brakes around the handicap.
Every run starts from seed 0, as the route does.

A log is kept only when out/arcade_replay replays it with hash_matches, complete, claims_match and finished, at the
bot's time; out/arcade_splits gives the rules' lap times for it, adding up to that time, from the same final hash; and
no two logs of the set are the same. Any failure exits non-zero and writes nothing. The set checks (at least 2
different variants lead a lap; with --beat, a faster variant on every lap of that log and 3 faster overall) only warn.

Writes OUT/v1.acl ... and OUT/manifest.json, a JSON list of {file, name, plan, frames, time, splits, log_h, tool, gen}.
The same commit, set and seed give byte-identical logs, so anyone can regenerate a listed BOT ghost and check its
log_h without buying it."""
import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "dev"))
import bot  # noqa: E402

T, C = bot.T, bot.C
A, B, R = bot.A, bot.B, bot.R
OUT = os.path.join(GAME_DIR, "out")
LIB = os.path.join(OUT, "librules.so")
REPLAY = os.path.join(OUT, "arcade_replay")
SPLITS = os.path.join(OUT, "arcade_splits")
GAME = b"MDGP"
SEED = 0                    # the route's seed
LOG_CAP = 65536             # a log that does not fit in 64 KiB is refused
FPS = 60

# The sets of variants: (name, plan). A name starts with its variant (v1 is the set's first).
SETS = {
    "default": [
        ("v1 late fade", {3: {"nodrift": True, "lift": 3}}),
        ("v2 slow start", {1: {"stall": (0.40, 60), "nodrift": True}}),
        ("v3 mid-race dip", {2: {"nodrift": True, "lift": 3}}),
        ("v4 last lap only", {1: {"nodrift": True}, 2: {"nodrift": True}}),
        ("v5 fast opener", {2: {"nodrift": True}, 3: {"nodrift": True}}),
        ("v6 steady", {1: {"nodrift": True}, 2: {"nodrift": True}, 3: {"nodrift": True}}),
    ],
}


class GenError(Exception):
    """A check failed or a tool is missing: the run keeps nothing."""


class AcRec(ctypes.Structure):
    """ac_rec (arcade/src/ac_log.h): the kit's run-log recorder."""
    _fields_ = [("buf", ctypes.POINTER(ctypes.c_uint8)), ("cap", ctypes.c_uint32), ("len", ctypes.c_uint32),
                ("frames", ctypes.c_uint32), ("last", ctypes.c_uint16), ("count", ctypes.c_uint32),
                ("full", ctypes.c_uint8), ("prev", ctypes.c_uint16)]


class GameInfo(ctypes.Structure):
    """ac_game_info (arcade/src/ac_game.h)."""
    _fields_ = [("id", ctypes.c_char * 4), ("rules_version", ctypes.c_uint32), ("n_trophies", ctypes.c_uint8),
                ("trophy_names", ctypes.c_void_p), ("ghost_period", ctypes.c_uint16)]


def load(lib=LIB):
    """out/librules.so (a path or a handle) with the game_*, rules_* and recorder signatures set."""
    lib = T.load_lib(lib)
    for name, rt in C.GETTERS:
        getattr(lib, name).restype = rt
    lib.rules_lap_frames.argtypes = [ctypes.c_int]
    lib.rules_lap_frames.restype = ctypes.c_uint32
    rec = ctypes.POINTER(AcRec)
    lib.ac_rec_begin.argtypes = [rec, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_char_p,
                                 ctypes.c_uint32, ctypes.c_uint32]
    lib.ac_rec_begin.restype = None
    lib.ac_rec_push.argtypes = [rec, ctypes.c_uint16]
    lib.ac_rec_push.restype = None
    lib.ac_rec_finish.argtypes = [rec, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
    lib.ac_rec_finish.restype = ctypes.c_uint32
    return lib


def record(lib, keys, seed=SEED, cap=LOG_CAP):
    """The run log of keys played from game_init(seed), encoded by the kit's recorder: ac_rec_push for each frame as
    game_step runs it, then ac_rec_finish with the game's final hash, score and trophies. A log the recorder marked
    full (it did not fit in cap bytes) is refused."""
    info = GameInfo.in_dll(lib, "GAME_INFO")
    if info.id != GAME:
        raise GenError("out/librules.so is %r, not %r" % (info.id, GAME))
    buf = (ctypes.c_uint8 * cap)()
    rec = AcRec()
    lib.ac_rec_begin(ctypes.byref(rec), buf, cap, GAME, info.rules_version, seed)
    lib.game_init(seed)
    for k in keys:
        lib.game_step(k)
        lib.ac_rec_push(ctypes.byref(rec), k)
    res = T.Result()
    lib.game_result(ctypes.byref(res))
    n = lib.ac_rec_finish(ctypes.byref(rec), lib.game_hash(), res.score, res.trophies)
    if rec.full:
        raise GenError("the log is full: %d frames do not fit in %d bytes" % (len(keys), cap))
    return ctypes.string_at(buf, n)


class HandicapBot(bot.Bot):
    """The route bot with a handicap per lap. plan: {lap: {"nodrift": True, "lift": N, "stall": (fraction, frames)}}
    (any of the three; a lap left out drives as the route bot)."""

    def __init__(self, lib, plan):
        super().__init__(lib)
        self.plan = {int(lap): h for lap, h in plan.items()}
        self.track = lib.rules_track_len() * 16          # one lap of kart.progress (1/16 px)
        self.frame = 0                                    # race frames driven, for lift
        self.stall_left = {}                              # lap -> stall frames left, once its stall began

    def drive(self):
        keys = super().drive()
        k = self.kart(0)
        h = self.plan.get(k.lap, {})
        self.frame += 1
        if "stall" in h:
            fraction, frames = h["stall"]
            if k.lap not in self.stall_left and (k.progress % self.track) / self.track >= fraction:
                self.stall_left[k.lap] = frames
            if self.stall_left.get(k.lap, 0) > 0:
                self.stall_left[k.lap] -= 1
                return B
        if h.get("lift") and self.frame % h["lift"] == 0:
            keys &= ~A
        if h.get("nodrift"):
            keys &= ~R
        return keys


def clock(frames):
    """A time in frames as m:ss.cc at 60 fps (centiseconds rounded)."""
    cs = round(frames * 100 / FPS)
    return "%d:%02d.%02d" % (cs // 6000, cs // 100 % 60, cs % 100)


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def tool_json(tool, path):
    """The one JSON line a replay tool prints for a log; a non-zero exit or no JSON is a GenError."""
    r = subprocess.run([tool, path], capture_output=True, text=True)
    if r.returncode != 0:
        raise GenError("%s %s exited %d: %s" % (os.path.basename(tool), os.path.basename(path), r.returncode,
                                                  r.stderr.strip()))
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise GenError("%s %s printed no JSON: %r" % (os.path.basename(tool), os.path.basename(path), r.stdout))


def git_head():
    """HEAD's short hash, for the gen string."""
    r = subprocess.run(["git", "-c", "safe.directory=*", "rev-parse", "--short", "HEAD"], cwd=GAME_DIR,
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise GenError("cannot read the git commit: %s" % r.stderr.strip())
    return r.stdout.strip()


def run_variant(lib, plan):
    """One variant from power-on: (keys, laps, time_frames, final hash). The run must end and finish."""
    b = HandicapBot(lib, plan)
    keys = b.run()
    if not lib.game_ended():
        raise GenError("the run never ended (%d frames)" % len(keys))
    res = T.Result()
    lib.game_result(ctypes.byref(res))
    if not res.finished:
        raise GenError("the run did not finish (%d race frames)" % res.time_frames)
    laps = [lib.rules_lap_frames(i) for i in range(1, C.tuning("LAPS") + 1)]
    return keys, laps, res.time_frames, lib.game_hash()


def check(path, time_frames, laps):
    """The real tools on a kept log: arcade_replay's checks all hold at the bot's time, and arcade_splits gives the
    rules' laps, adding up to that time, from the same final hash."""
    name = os.path.basename(path)
    rep = tool_json(REPLAY, path)
    bad = [k for k in ("hash_matches", "complete", "claims_match", "finished") if rep.get(k) is not True]
    if bad:
        raise GenError("arcade_replay %s: %s not true" % (name, ", ".join(bad)))
    if rep.get("time_frames") != time_frames:
        raise GenError("arcade_replay %s: time %s, the bot's %d" % (name, rep.get("time_frames"), time_frames))
    spl = tool_json(SPLITS, path)
    if spl.get("game") != GAME.decode() or spl.get("kind") != "lap" or spl.get("splits") != laps:
        raise GenError("arcade_splits %s: %s, the rules' laps %s" % (name, spl.get("splits"), laps))
    if sum(spl["splits"]) != rep["time_frames"] or spl.get("time_frames") != rep["time_frames"]:
        raise GenError("arcade_splits %s: the laps add up to %d, not %d" % (name, sum(spl["splits"]),
                                                                            rep["time_frames"]))
    if spl.get("final_hash") != rep.get("final_hash"):
        raise GenError("arcade_splits %s: final hash %s, arcade_replay's %s" % (name, spl.get("final_hash"),
                                                                                rep.get("final_hash")))


def generate(lib, variants, stage, tool, head):
    """Drives, encodes and checks every variant into the stage directory; returns the manifest rows."""
    rows = []
    for i, (name, plan) in enumerate(variants, 1):
        keys, laps, time_frames, final_hash = run_variant(lib, plan)
        log = record(lib, keys)
        if T.S.parse_log_header(log)["final_hash"] != final_hash:
            raise GenError("%s: the recorded log's final hash is not the bot run's" % name)
        path = os.path.join(stage, "v%d.acl" % i)
        with open(path, "wb") as f:
            f.write(log)
        check(path, time_frames, laps)
        rows.append({"file": "v%d.acl" % i, "name": name,
                     "plan": {str(lap): {k: list(v) if isinstance(v, tuple) else v for k, v in h.items()}
                              for lap, h in plan.items()},
                     "frames": time_frames, "time": clock(time_frames), "splits": laps,
                     "log_h": hashlib.sha256(log).hexdigest(), "tool": tool,
                     "gen": "ghostgen v%d seed %d @%s" % (i, SEED, head)})
    seen = {}
    for r in rows:
        if r["log_h"] in seen:
            raise GenError("%s and %s are the same log (sha256 %s)" % (seen[r["log_h"]], r["name"], r["log_h"][:12]))
        seen[r["log_h"]] = r["name"]
    return rows


def set_warnings(rows, beat=None):
    """The set checks, as warnings (they never fail a run): at least 2 different variants lead a lap and no one
    variant leads them all (ties lead together); with beat ({splits, time_frames} of a finished log), every lap has a
    variant faster than beat's lap and at least 3 variants are faster overall."""
    out = []
    laps = range(len(rows[0]["splits"]))
    leaders = [{r["name"] for r in rows if r["splits"][k] == min(x["splits"][k] for x in rows)} for k in laps]
    every = set.intersection(*leaders)
    if every:
        out.append("one variant leads every lap (%s)" % ", ".join(sorted(every)))
    if beat:
        for k, t in enumerate(beat["splits"]):
            if not any(r["splits"][k] < t for r in rows):
                out.append("lap %d: no variant is faster than %d" % (k + 1, t))
        n = sum(r["frames"] < beat["time_frames"] for r in rows)
        if n < 3:
            out.append("%d variants are faster overall than %d (want 3)" % (n, beat["time_frames"]))
    return out


def table(rows):
    """The printed table: variant, name, laps, frames, time, sha256 prefix, gen."""
    lines = ["%-7s %-18s %-16s %6s %8s  %-12s  %s" % ("variant", "name", "laps (frames)", "frames", "time",
                                                       "sha256", "gen")]
    for r in rows:
        lines.append("%-7s %-18s %-16s %6d %8s  %-12s  %s" % (
            r["file"][:-4], r["name"], " ".join(map(str, r["splits"])), r["frames"], r["time"], r["log_h"][:12],
            r["gen"]))
    return "\n".join(lines)


def beat_table(rows, beat):
    """Each lap and the total against the --beat log: the beat's time and the variants faster than it."""
    lines = ["%-7s %6s  %s" % ("beat", "frames", "faster variants")]
    for k, t in enumerate(beat["splits"]):
        lines.append("%-7s %6d  %s" % ("lap %d" % (k + 1), t,
                                       " ".join(r["file"][:-4] for r in rows if r["splits"][k] < t) or "-"))
    lines.append("%-7s %6d  %s" % ("total", beat["time_frames"],
                                   " ".join(r["file"][:-4] for r in rows if r["frames"] < beat["time_frames"]) or "-"))
    return "\n".join(lines)


def read_beat(path):
    """{splits, time_frames} of a finished log, from arcade_splits."""
    spl = tool_json(SPLITS, path)
    if not spl.get("finished") or len(spl.get("splits", [])) != C.tuning("LAPS"):
        raise GenError("--beat %s: the run did not finish" % path)
    return {"splits": spl["splits"], "time_frames": spl["time_frames"]}


def replaceable(out):
    """Whether out may be replaced: it is missing, empty, or an earlier ghostgen output (a manifest and logs only)."""
    if not os.path.exists(out):
        return True
    if not os.path.isdir(out):
        return False
    names = os.listdir(out)
    return not names or "manifest.json" in names and all(
        (n == "manifest.json" or n.endswith(".acl")) and os.path.isfile(os.path.join(out, n)) for n in names)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate checked BOT ghosts for MARINE DRIVE GP.")
    ap.add_argument("--set", default="default", choices=sorted(SETS))
    ap.add_argument("--out", help="the output directory (default out/ghostgen/SET)")
    ap.add_argument("--beat", metavar="LOG", help="a finished log the set should beat (warns only)")
    a = ap.parse_args(argv)
    out = os.path.abspath(a.out or os.path.join(OUT, "ghostgen", a.set))
    stage = None
    try:
        for path in (LIB, REPLAY, SPLITS):
            if not os.path.exists(path):
                raise GenError("%s is missing: run `make -f tools.mk host replay splits` first" % path)
        if not replaceable(out):
            raise GenError("%s exists and is not a ghostgen output; not replacing it" % out)
        beat = read_beat(a.beat) if a.beat else None
        tool = "arcade_replay sha256:" + sha256_file(REPLAY)[:12]
        head = git_head()
        lib = load(LIB)
        stage = tempfile.mkdtemp(prefix="ghostgen.")
        rows = generate(lib, SETS[a.set], stage, tool, head)
        with open(os.path.join(stage, "manifest.json"), "w") as f:
            json.dump(rows, f, indent=2)
            f.write("\n")
        if os.path.isdir(out):
            for n in os.listdir(out):
                os.remove(os.path.join(out, n))
        os.makedirs(out, exist_ok=True)
        for n in [r["file"] for r in rows] + ["manifest.json"]:
            shutil.copyfile(os.path.join(stage, n), os.path.join(out, n))
    except GenError as e:
        print("ghostgen: %s; nothing kept" % e, file=sys.stderr)
        return 1
    finally:
        if stage:
            shutil.rmtree(stage, ignore_errors=True)
    print(table(rows))
    if beat:
        print()
        print(beat_table(rows, beat))
    for w in set_warnings(rows, beat):
        print("warning: " + w)
    print("wrote %d logs and %s" % (len(rows), os.path.join(out, "manifest.json")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
