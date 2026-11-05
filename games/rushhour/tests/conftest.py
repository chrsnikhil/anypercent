"""Fixtures for this game's tests. tests/test_generic.py (identical in every arcade game) needs only the fixtures
marked GENERIC below; change them when you stamp a new game, never test_generic.py itself."""
import ctypes
import os
import re
import subprocess
import sys

import pytest

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTES = os.path.join(GAME_DIR, "tests", "routes")
OUT_DIR = os.path.join(GAME_DIR, "tests", "out")
sys.path.insert(0, os.path.join(GAME_DIR, "..", "common", "py"))
os.makedirs(OUT_DIR, exist_ok=True)

import arcade_test as T  # noqa: E402

A, B, SELECT, START, RIGHT, LEFT, UP, DOWN = T.A, T.B, T.SELECT, T.START, T.RIGHT, T.LEFT, T.UP, T.DOWN


def sh(*cmd):
    r = subprocess.run(cmd, cwd=GAME_DIR, capture_output=True, text=True)
    assert r.returncode == 0, " ".join(cmd) + "\n" + r.stdout[-3000:] + r.stderr[-3000:]
    return r.stdout


def target():
    """The ROM's base name: TARGET in the Makefile."""
    with open(os.path.join(GAME_DIR, "Makefile")) as f:
        return re.search(r"^TARGET\s*:=\s*(\S+)", f.read(), re.M).group(1)


def tuning(name):
    """An integer #define from rules/tuning.h."""
    with open(os.path.join(GAME_DIR, "rules", "tuning.h")) as f:
        m = re.search(r"^#define %s\s+\(?(-?(?:0x[0-9a-fA-F]+|\d+))" % name, f.read(), re.M)
    assert m, name
    return int(m.group(1), 0)


def load_keys(name):
    """A route: one hex key mask per line."""
    with open(os.path.join(ROUTES, name)) as f:
        return [int(line, 16) for line in f if line.strip()]


# ---- GENERIC: the fixtures tests/test_generic.py uses -------------------------------------------------------------

@pytest.fixture(scope="session")
def rom():
    """The built ROM (built once per session with dev/build.sh)."""
    sh("bash", "dev/build.sh")
    return os.path.join(GAME_DIR, target() + ".gba")


@pytest.fixture(scope="session")
def elf(rom):
    return os.path.splitext(rom)[0] + ".elf"


@pytest.fixture(scope="session")
def lib():
    """out/librules.so: the rules and the kit for the PC (make -f tools.mk host)."""
    sh("make", "-f", "tools.mk", "host")
    return T.load_lib(os.path.join(GAME_DIR, "out", "librules.so"))


@pytest.fixture(scope="session")
def replay_tool():
    sh("make", "-f", "tools.mk", "replay")
    return os.path.join(GAME_DIR, "out", "arcade_replay")


@pytest.fixture(scope="session")
def game_id(lib):
    return T.game_id(lib)


@pytest.fixture(scope="session")
def route_frames():
    """The scripted route, from power-on: it must finish (or end) the run; test_generic adds the frames after."""
    return load_keys("full_run.keys")


@pytest.fixture(scope="session")
def route_finished():
    """Whether the route's run counts as finished (game_result().finished)."""
    return True


@pytest.fixture(scope="session")
def short_run():
    """The quickest end from power-on: title -> how-to -> play, pause (Start), give up (Select)."""
    return [0] * 60 + [START, 0, START, 0, START, 0, SELECT]


@pytest.fixture(scope="session")
def leave_results():
    """The buttons that leave the results screen (one press)."""
    return START


# ---- this game's own -------------------------------------------------------------------------------------------

_C = ctypes
READS = {
    "rules_scene": _C.c_uint8, "rules_steps": _C.c_uint32, "rules_run_frames": _C.c_uint32,
    "rules_finished": _C.c_uint8, "rules_trophies": _C.c_uint32, "rules_px": _C.c_int16, "rules_py": _C.c_int16,
    "rules_vx": _C.c_int32, "rules_vy": _C.c_int32, "rules_on_ground": _C.c_uint8, "rules_facing_left": _C.c_uint8,
    "rules_pose": _C.c_uint8, "rules_hp": _C.c_uint8, "rules_shield": _C.c_uint8, "rules_invuln": _C.c_uint8,
    "rules_dead": _C.c_uint8, "rules_chai": _C.c_uint16, "rules_chai_total": _C.c_uint16,
    "rules_lives_lost": _C.c_uint16, "rules_damaged": _C.c_uint8, "rules_touched_checkpoint": _C.c_uint8,
    "rules_level_w": _C.c_uint16, "rules_level_h": _C.c_uint16, "rules_tile": _C.c_uint8,
    "rules_ent_count": _C.c_uint16, "rules_ent_type": _C.c_uint8, "rules_ent_state": _C.c_uint8,
    "rules_ent_x": _C.c_int16, "rules_ent_y": _C.c_int16, "rules_ent_dir": _C.c_int8, "rules_ent_timer": _C.c_uint8,
}
SC_TITLE, SC_HOWTO, SC_PLAY, SC_PAUSE, SC_RESULTS = range(5)
T_EMPTY, T_SOLID, T_ONEWAY, T_SPIKE = range(4)
E_BUG, E_CHAI, E_ORB, E_CHECK, E_DOOR = range(1, 6)
ES_LIVE, ES_GONE, ES_SQUASHED, ES_ON = range(4)


def typed(lib):
    """The rules library with every rules_* read's restype set."""
    for name, rt in READS.items():
        getattr(lib, name).restype = rt
    lib.rules_debug_velocity.argtypes = [_C.c_int32, _C.c_int32]
    lib.rules_debug_run_frames.argtypes = [_C.c_uint32]
    return lib


def to_play(lib):
    """From game_init: title -> how-to -> play."""
    lib.game_step(START)
    lib.game_step(0)
    lib.game_step(START)
    lib.game_step(0)
    assert lib.rules_scene() == SC_PLAY


def ents(lib, kind=None):
    """[(index, type, state, x, y)] of the level's entities (of one type)."""
    out = []
    for i in range(lib.rules_ent_count()):
        t = lib.rules_ent_type(i)
        if kind is None or t == kind:
            out.append((i, t, lib.rules_ent_state(i), lib.rules_ent_x(i), lib.rules_ent_y(i)))
    return out


class Arena:
    """A test map for the rules: rows of text ('.' empty, '#' solid, '=' one-way, '^' spike) held alive for ctypes."""

    def __init__(self, lib, rows):
        self.w, self.h = len(rows[0]), len(rows)
        codes = {".": T_EMPTY, "#": T_SOLID, "=": T_ONEWAY, "^": T_SPIKE}
        self.buf = (_C.c_uint8 * (self.w * self.h))(*[codes[c] for row in rows for c in row])
        lib.rules_debug_map(self.buf, self.w, self.h)


@pytest.fixture
def rh(lib):
    """The rules, typed, after game_init(0)."""
    typed(lib)
    lib.game_init(0)
    return lib
