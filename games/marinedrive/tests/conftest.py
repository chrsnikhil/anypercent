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
R, L = 0x100, 0x200
SC_TITLE, SC_HOWTO, SC_COUNTDOWN, SC_RACE, SC_PAUSE, SC_FINISH, SC_RESULTS = range(7)


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
    """The quickest way to end a run from power-on (quit or die at once): boot, leave the title, end."""
    return [0] * 60 + [START, 0, START, 0, START, 0, SELECT]      # title, how-to, pause in the countdown, retire


@pytest.fixture(scope="session")
def leave_results():
    """The buttons that leave the results screen (one press)."""
    return START


# ---- this game's own -------------------------------------------------------------------------------------------

@pytest.fixture(scope="session")
def splits_tool():
    """out/arcade_splits: arcade_replay's replay, then the player's lap times (make -f tools.mk splits)."""
    sh("make", "-f", "tools.mk", "splits")
    return os.path.join(GAME_DIR, "out", "arcade_splits")


class Kart(ctypes.Structure):
    """md_kart (rules/game.h)."""
    _fields_ = [("x", ctypes.c_int32), ("y", ctypes.c_int32), ("vx", ctypes.c_int32), ("vy", ctypes.c_int32),
                ("speed", ctypes.c_int32), ("progress", ctypes.c_int32), ("finish_frame", ctypes.c_uint32),
                ("heading", ctypes.c_uint16), ("drift_charge", ctypes.c_uint16), ("boost", ctypes.c_uint16),
                ("wall_hits", ctypes.c_uint16), ("lap", ctypes.c_uint8), ("cp", ctypes.c_uint8),
                ("surface", ctypes.c_uint8), ("drift", ctypes.c_uint8), ("finished", ctypes.c_uint8),
                ("place", ctypes.c_uint8), ("lap_boosts", ctypes.c_uint8), ("lap_clean", ctypes.c_uint8),
                ("steer", ctypes.c_int8)]


GETTERS = (("rules_scene", ctypes.c_uint8), ("rules_countdown", ctypes.c_uint16),
           ("rules_race_frames", ctypes.c_uint32), ("rules_finished", ctypes.c_uint8),
           ("rules_trophies", ctypes.c_uint32), ("rules_placement", ctypes.c_uint8),
           ("rules_surface_at", ctypes.c_uint8), ("rules_sector_at", ctypes.c_uint8),
           ("rules_track_len", ctypes.c_int32), ("rules_n_waypoints", ctypes.c_uint8))


@pytest.fixture
def g(lib):
    """The rules, initialised, with this game's reads typed. g.kart(i) -> Kart."""
    for name, rt in GETTERS:
        getattr(lib, name).restype = rt
    lib.rules_surface_at.argtypes = [ctypes.c_int32, ctypes.c_int32]
    lib.rules_debug_place.argtypes = [ctypes.c_int, ctypes.c_int32, ctypes.c_int32, ctypes.c_uint16]
    lib.rules_debug_move.argtypes = [ctypes.c_int, ctypes.c_int32, ctypes.c_int32]
    lib.rules_debug_set.argtypes = [ctypes.c_int, ctypes.c_int32, ctypes.c_uint8, ctypes.c_uint8]
    lib.rules_debug_freeze.argtypes = [ctypes.c_uint8]
    lib.rules_order.restype = ctypes.c_uint8
    lib.rules_events.restype = ctypes.c_uint8
    lib.rules_lap_frames.restype = ctypes.c_uint32
    lib.rules_sector_at.argtypes = [ctypes.c_int32, ctypes.c_int32]

    def kart(i):
        k = Kart()
        lib.rules_kart(i, ctypes.byref(k))
        return k
    lib.kart = kart
    lib.game_init(0)
    return lib


def centre_points(lib):
    """The rules' centre line (md_points) as [(x, y)]."""
    n = ctypes.c_int32.in_dll(lib, "md_track_points").value
    arr = (ctypes.c_int16 * (2 * n)).in_dll(lib, "md_points")
    return [(arr[2 * i], arr[2 * i + 1]) for i in range(n)]


def to_race(g):
    """From game_init: title -> how-to -> the countdown, run out; returns with the race live (scene RACE)."""
    for k in (START, 0, START, 0):
        g.game_step(k)
    while g.rules_scene() == SC_COUNTDOWN:
        g.game_step(0)
    assert g.rules_scene() == SC_RACE
