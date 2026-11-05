"""Fixtures for this game's tests. tests/test_generic.py (identical in every arcade game) needs only the fixtures
marked GENERIC below; change them when you stamp a new game, never test_generic.py itself."""
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

A, B, SELECT, START, RIGHT, LEFT, UP, DOWN, R, L = T.A, T.B, T.SELECT, T.START, T.RIGHT, T.LEFT, T.UP, T.DOWN, T.R, T.L


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
    """The quickest way to end a run from power-on: boot, title, how-to, pause, Quit."""
    return [0] * 60 + [START, 0, START, 0, START, 0, DOWN, 0, A]


@pytest.fixture(scope="session")
def leave_results():
    """The buttons that leave the results screen (one press)."""
    return START


# ---- this game's own -------------------------------------------------------------------------------------------

@pytest.fixture
def game(lib):
    lib.game_init(0)
    return lib
