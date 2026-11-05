"""Test helpers shared by every arcade game (games/<game>/tests). Import from a game's conftest:

    sys.path.insert(0, os.path.join(GAME_DIR, "..", "common", "py"))
    import arcade_test as T

Frames are lists of GBA key masks, one per emulator frame (arcade/src/ac_buttons.h bits). The ROM exports the g_dbg_*
symbols of games/common/src/arcade_runtime.cpp (and g_dbg_sprite_tiles from its main.cpp); the PC library
(out/librules.so) exports the game_* interface of arcade/src/ac_game.h plus game_ended()."""
import ctypes
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
COMMON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(COMMON))
OUT = os.path.join(COMMON, "out")
RUNNER_SRC = os.path.join(REPO, "game", "tools", "gba_run", "gba_run.c")
MGBA = os.environ.get("MGBA", "/opt/arca-sandbox/toolchains/mgba-src")
NM = "/opt/wonderful/toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-nm"
SAVE_SIZE = 32768

sys.path.insert(0, os.path.join(REPO, "arcade", "py"))
import arcade_save as S  # noqa: E402,F401  (re-exported: T.S.get, T.S.put, ...)

A, B, SELECT, START, RIGHT, LEFT, UP, DOWN, R, L = (1 << i for i in range(10))


# ---- tools -----------------------------------------------------------------------------------------------------

def build_runner():
    """Compiles game/tools/gba_run/gba_run.c (SHIP IT!'s headless runner on the static libmgba) to
    games/common/out/gba_run once, with game/tools.mk's command. Safe when several games' suites run at once: the
    binary is built under a temporary name and renamed into place."""
    exe = os.path.join(OUT, "gba_run")
    deps = [RUNNER_SRC, os.path.join(MGBA, "build", "libmgba.a")]
    if os.path.exists(exe) and all(os.path.getmtime(exe) >= os.path.getmtime(d) for d in deps if os.path.exists(d)):
        return exe
    os.makedirs(OUT, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="gba_run.", dir=OUT)
    os.close(fd)
    try:
        cmd = ["gcc", "-O2", "-o", tmp, RUNNER_SRC, "-I%s/include" % MGBA, "-I%s/build/include" % MGBA,
               "%s/build/libmgba.a" % MGBA, "-lm", "-lpthread"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, " ".join(cmd) + "\n" + r.stderr[-3000:]
        os.chmod(tmp, 0o755)
        os.replace(tmp, exe)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return exe


_symbol_cache = {}


def symbols(elf, *names):
    """{name: address} for the named ELF symbols (arm-none-eabi-nm). A missing symbol fails with its name."""
    key = (elf, os.path.getmtime(elf))
    if key not in _symbol_cache:
        out = subprocess.run([NM, elf], capture_output=True, text=True, check=True).stdout
        table = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 3:
                table[parts[2]] = int(parts[0], 16)
        _symbol_cache[key] = table
    table = _symbol_cache[key]
    missing = [n for n in names if n not in table]
    assert not missing, "%s does not export %s" % (elf, ", ".join(missing))
    return {n: table[n] for n in names}


def keys_script(frames):
    """gba_run's script text: "<keys hex> <count>" lines, one per run of identical masks."""
    lines, i = [], 0
    while i < len(frames):
        j = i
        while j < len(frames) and frames[j] == frames[i]:
            j += 1
        lines.append("%x %d\n" % (frames[i] & 0x3FF, j - i))
        i = j
    return "".join(lines)


def run_rom(rom, frames, watch=(), save_in=None, save_out=None, shots=()):
    """Runs the ROM headless for len(frames) frames. watch: symbol names (read from the .elf next to the ROM),
    returned per frame as {"watch": [[values in watch order] per frame]}. save_in: bytes (or a path) loaded as
    cartridge memory first; save_out: True to return the save memory after the last frame as "save" (None if the
    game never wrote any), or a path to write it to as well. shots: (frame, path) pairs, raw 240 x 160 RGBA at the
    end of that 1-based frame."""
    elf = os.path.splitext(rom)[0] + ".elf"
    runner = build_runner()
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "keys.txt")
        with open(script, "w") as f:
            f.write(keys_script(frames))
        cmd = [runner, rom, script]
        if watch:
            addrs = symbols(elf, *watch)
            cmd += ["--watch", ",".join("%x" % addrs[n] for n in watch)]
        if save_in is not None:
            if isinstance(save_in, (bytes, bytearray)):
                path = os.path.join(tmp, "in.sav")
                with open(path, "wb") as f:
                    f.write(bytes(save_in))
                save_in = path
            cmd += ["--save-in", str(save_in)]
        out_path = None
        if save_out:
            out_path = str(save_out) if save_out is not True else os.path.join(tmp, "out.sav")
            if os.path.exists(out_path):
                os.remove(out_path)
            cmd += ["--save-out", out_path]
        for frame, path in shots:
            cmd += ["--shot", str(frame), str(path)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, " ".join(cmd) + "\n" + r.stderr[-3000:]
        rows = [[int(v, 16) for v in line.split()[1:]] for line in r.stdout.splitlines()]
        save = None
        if out_path and os.path.exists(out_path):
            with open(out_path, "rb") as f:
                save = f.read()
        return {"watch": rows if watch else [], "save": save}


# ---- the PC library ----------------------------------------------------------------------------------------------

def load_lib(lib):
    """A ctypes handle on out/librules.so (a path) with the game_* signatures set; a handle is returned as is."""
    if not isinstance(lib, (str, os.PathLike)):
        return lib
    so = ctypes.CDLL(os.path.abspath(str(lib)))
    so.game_init.argtypes = [ctypes.c_uint32]
    so.game_step.argtypes = [ctypes.c_uint16]
    so.game_hash.restype = ctypes.c_uint32
    so.game_ended.restype = ctypes.c_uint8
    so.ac_seed_mix.restype = ctypes.c_uint32            # the kit is linked in (arcade/src/ac_rng.c)
    so.ac_seed_mix.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    return so


class Ghost(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int16), ("y", ctypes.c_int16), ("angle", ctypes.c_uint8), ("flags", ctypes.c_uint8)]


class Result(ctypes.Structure):
    _fields_ = [("finished", ctypes.c_uint8), ("frames", ctypes.c_uint32), ("score", ctypes.c_uint32),
                ("time_frames", ctypes.c_uint32), ("trophies", ctypes.c_uint32)]


def game_id(lib):
    """GAME_INFO.id as bytes (the first field of ac_game_info)."""
    return bytes((ctypes.c_char * 4).in_dll(load_lib(lib), "GAME_INFO").raw)


def pc_hashes(lib, frames, seed=0):
    """game_init(seed), then game_step + game_hash for each frame: the hash after every step."""
    so = load_lib(lib)
    so.game_init(seed)
    out = []
    for k in frames:
        so.game_step(k)
        out.append(so.game_hash())
    return out


def pc_player(lib, frames, seed=0):
    """game_ghost() (x, y) after every step from game_init(seed)."""
    so = load_lib(lib)
    so.game_init(seed)
    g, out = Ghost(), []
    for k in frames:
        so.game_step(k)
        so.game_ghost(ctypes.byref(g))
        out.append((g.x, g.y))
    return out


def pc_ghosts(lib, frames, seed=0):
    """game_ghost() (x, y, angle, flags) after every step from game_init(seed)."""
    so = load_lib(lib)
    so.game_init(seed)
    g, out = Ghost(), []
    for k in frames:
        so.game_step(k)
        so.game_ghost(ctypes.byref(g))
        out.append((g.x, g.y, g.angle, g.flags))
    return out


# ---- the ghost, as games/common/src/arcade_runtime.cpp draws it -------------------------------------------------

GHOST_PLAY = 0x80        # game_ghost() flags bit: the player is in play (the ghost aligns on it)


def ghost_anchor(points, period):
    """The ghost step (steps of the recorded run since its boot) of its first sample in play, k * period + 1, or None
    when no sample has GHOST_PLAY (the ghost is then indexed by steps since boot)."""
    k = next((i for i, p in enumerate(points) if p[3] & GHOST_PLAY), None)
    return None if k is None else k * period + 1


def ghost_step(step, live, anchor):
    """The ghost step shown at `step` (steps since boot) of a run whose first in-play step is `live`: step itself
    when the ghost is unaligned; anchor + (step - live) from the live step on; None before (no ghost)."""
    if anchor is None:
        return step if step > 0 else None
    if live is None or step < live:
        return None
    return anchor + (step - live)


def _cdiv(n, d):
    q = abs(n) // d
    return q if n >= 0 else -q


def ghost_expected(points, period, g):
    """(x, y) of the ghost at ghost step g >= 1: sample i = (g - 1) // period, t = (g - 1) % period, a + (b - a) * t /
    period per axis with C truncation toward zero, or a when the flags (without GHOST_PLAY) differ; the last sample
    from there on."""
    i = (g - 1) // period
    if i >= len(points) - 1:
        return tuple(points[-1][:2])
    a, b = points[i], points[i + 1]
    if (a[3] & 0x7F) != (b[3] & 0x7F):
        return tuple(a[:2])
    t = (g - 1) % period

    def s16(v):
        return (v + 0x8000) % 0x10000 - 0x8000
    return (s16(a[0] + _cdiv((b[0] - a[0]) * t, period)), s16(a[1] + _cdiv((b[1] - a[1]) * t, period)))


def pc_run_end(lib, frames, seed=0):
    """The frames the PC rules (from game_init(seed)) consume up to and including the step where game_ended() rises."""
    so = load_lib(lib)
    so.game_init(seed)
    for i, k in enumerate(frames):
        so.game_step(k)
        if so.game_ended():
            return frames[:i + 1]
    raise AssertionError("the run never ended (game_ended() stayed 0 over %d frames)" % len(frames))


def pc_result(lib, frames, seed=0):
    so = load_lib(lib)
    so.game_init(seed)
    for k in frames:
        so.game_step(k)
    r = Result()
    so.game_result(ctypes.byref(r))
    return {f: getattr(r, f) for f, _ in Result._fields_}


# ---- the ROM against the PC --------------------------------------------------------------------------------------

def boots(steps):
    """Indices of the frames holding the first game step after each boot (power-on, then every reset)."""
    return [i for i, s in enumerate(steps) if s == 1 and (i == 0 or steps[i - 1] != 1)]


def assert_rom_matches_pc(rom, elf, lib, frames, save_in=None):
    """Every game step the ROM takes has the PC library's hash for the same buttons. One step every frame after
    boot (no lag); a reset (leaving the results) restarts the PC rules at the ROM's next first step, from
    game_init(the seed that boot picked, g_dbg_seed). Returns the number of steps compared."""
    del elf                                         # the ROM's .elf sits next to it (run_rom reads it)
    rows = run_rom(rom, frames, watch=("g_dbg_steps", "g_dbg_hash", "g_dbg_seed"), save_in=save_in)["watch"]
    so = load_lib(lib)
    last, live, compared = 0, False, 0
    for i, (steps, h, seed) in enumerate(rows):
        if steps == 0:
            live, last = False, 0
            continue
        if steps == last:
            later = [r[0] for r in rows[i + 1:i + 4]]
            assert not later or later[0] < last or later[0] in (0, 1), \
                "frame %d: no game step (lag) at step %d" % (i, steps)
            continue                                # the frame the ROM reset in: its step was discarded
        if not live or steps < last:
            assert steps == 1, "frame %d: the boot ran %d game steps at once" % (i, steps)
            so.game_init(seed)
            live = True
        else:
            assert steps == last + 1, "frame %d ran %d game steps" % (i, steps - last)
        so.game_step(frames[i])
        want = so.game_hash()
        assert h == want, "frame %d, step %d: ROM hash %08x, PC %08x" % (i, steps, h, want)
        last = steps
        compared += 1
    assert compared, "the ROM never stepped the game"
    return compared


# ---- saves and logs ----------------------------------------------------------------------------------------------

def blank_save():
    """A blank cartridge (all 0xFF), as bytes."""
    return bytes(S.blank())


def save_with(game, ghost=None, best=None, profile=None, run=None):
    """A formatted save for game (4 bytes) holding the given section payloads."""
    save = S.blank()
    S.fmt(save, game)
    for sec, data in ((S.GHOST, ghost), (S.BEST, best), (S.PROFILE, profile), (S.RUN, run)):
        if data is not None:
            assert S.put(save, sec, data), "section %d does not fit" % sec
    return bytes(save)


def decode_log(log):
    """The per-frame buttons of a run log body (arcade/src/ac_log.h)."""
    keys, pos, buttons = [], 32, 0
    while pos < len(log):
        v = shift = 0
        while True:
            b = log[pos]
            pos += 1
            v |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                break
        if v & 1:
            count, buttons = v >> 1, log[pos] | log[pos + 1] << 8
            pos += 2
        else:
            count, buttons = v >> 5, buttons ^ (1 << ((v >> 1) & 15))
        keys += [buttons] * count
    return keys


def replay(tool, log, ghost_out=None):
    """Runs out/arcade_replay on the log; returns its JSON. ghost_out: a path for --ghost."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run.acl")
        with open(path, "wb") as f:
            f.write(bytes(log))
        cmd = [tool, path] + (["--ghost", str(ghost_out)] if ghost_out else [])
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, " ".join(cmd) + "\n" + r.stderr
        return json.loads(r.stdout)


def ghost_of(tool, log):
    """The ghost track (GHOST payload bytes) the launcher would write for this log."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "ghost.bin")
        replay(tool, log, out)
        with open(out, "rb") as f:
            return f.read()
