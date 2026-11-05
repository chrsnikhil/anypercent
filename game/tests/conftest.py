import ctypes
import json
import os
import re
import subprocess
import sys

import pytest

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(GAME_DIR, "tests", "out")
TEMPLATE_ROM = "/opt/arca-sandbox/toolchains/butano/template/template.gba"
sys.path.insert(0, os.path.join(GAME_DIR, "tools", "art"))
sys.path.insert(0, os.path.join(GAME_DIR, "tools", "render"))
sys.path.insert(0, os.path.join(GAME_DIR, "stream"))
os.makedirs(OUT_DIR, exist_ok=True)

U8, U16, U32, I16 = ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint32, ctypes.c_int16
A, B, SELECT, START, RIGHT, LEFT, UP, DOWN = 0x001, 0x002, 0x004, 0x008, 0x010, 0x020, 0x040, 0x080
SC_TITLE, SC_PLAY, SC_CLEAR, SC_MISSED, SC_HOWTO, SC_NIGHTFALL, SC_DEMODAY, SC_WALKOUT = range(8)


def tuning(name):
    """A value from rules/tuning.h: an int, or a list of ints for a {...} table (nested tables flatten)."""
    text = open(os.path.join(GAME_DIR, "rules", "tuning.h")).read().replace("\\\n", " ")
    m = re.search(r"^#define %s +(\{[^\n]*\}|\S+)" % name, text, re.M)
    assert m, name
    nums = [int(v, 0) for v in re.findall(r"0x[0-9a-fA-F]+|\d+", m.group(1))]
    return nums if m.group(1).startswith("{") else nums[0]


def sh(*cmd):
    r = subprocess.run(cmd, cwd=GAME_DIR, capture_output=True, text=True)
    assert r.returncode == 0, " ".join(cmd) + "\n" + r.stdout[-3000:] + r.stderr[-3000:]
    return r.stdout


@pytest.fixture(scope="session")
def runner():
    sh("make", "-f", "tools.mk", "runner")
    return os.path.join(GAME_DIR, "out", "gba_run")


@pytest.fixture(scope="session")
def scene():
    with open(os.path.join(GAME_DIR, "gen", "scene_office.json")) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def lib():
    sh("make", "-f", "tools.mk", "host")
    so = ctypes.CDLL(os.path.join(GAME_DIR, "out", "librules.so"))
    for name, rt in (("rules_scene", U8), ("rules_paused", U8), ("rules_carrying", U8), ("rules_moving", U8),
                     ("rules_facing", U8), ("rules_dash_cool", U8), ("rules_hour", U8), ("rules_energy", U8),
                     ("rules_px", U16), ("rules_py", U16), ("rules_qx", U16), ("rules_qy", U16),
                     ("rules_progress", U16), ("rules_hour_frames", U16), ("rules_run_frames", U32),
                     ("rules_hash", U32), ("rules_walkable", U8), ("rules_hint", U8), ("rules_hint_dev", U8),
                     ("rules_target", U8), ("rules_clock_running", U8), ("rules_act", U8), ("rules_nightfall", U8),
                     ("rules_act_frames", U16), ("rules_bug_on", U8), ("rules_bug_x", U16), ("rules_bug_y", U16),
                     ("rules_bug_sitting", U8), ("rules_bug_desk", U8), ("rules_router_fried", U8),
                     ("rules_last_commit", U16), ("rules_commit_hold", U8), ("rules_pizza", U8),
                     ("rules_message", U8), ("rules_split", U32), ("rules_hint_arg", U8),
                     ("rules_room", U8), ("rules_demoday", U8), ("rules_walkout", U8), ("rules_verified", U8),
                     ("rules_stun", U8), ("rules_immune", U8), ("rules_crowd_count", U8), ("rules_crowd_x", U16),
                     ("rules_crowd_y", U16), ("rules_crowd_facing", U8), ("rules_slide", U8), ("rules_stumble", U8),
                     ("rules_pitch_key", U16), ("rules_clear_frames", U8), ("rules_crowd_paused", U8),
                     ("rules_crowd_gathered", U8), ("rules_grade", U8), ("record_decode", U32),
                     ("rules_crowd_standing", U8)):
        getattr(so, name).restype = rt
    so.rules_step.argtypes = [U16]
    so.rules_energy.argtypes = [U8]
    so.rules_walkable.argtypes = [I16, I16]
    so.rules_debug_place.argtypes = [U16, U16]
    so.rules_debug_energy.argtypes = [U8, U8]
    so.rules_debug_progress.argtypes = [U16]
    so.rules_debug_clock.argtypes = [U8, U16]
    for name in ("rules_bug_on", "rules_bug_x", "rules_bug_y", "rules_bug_sitting", "rules_bug_desk", "rules_split"):
        getattr(so, name).argtypes = [U8]
    so.rules_debug_act2.argtypes = [U16]
    so.rules_debug_act_frames.argtypes = [U16]
    so.rules_debug_act3.argtypes = [U8]
    so.rules_debug_verified.argtypes = [U8]
    for name in ("rules_crowd_x", "rules_crowd_y", "rules_crowd_facing", "rules_crowd_paused", "rules_crowd_gathered",
                 "rules_crowd_standing"):
        getattr(so, name).argtypes = [U8]
    return so


@pytest.fixture(scope="session")
def hall():
    with open(os.path.join(GAME_DIR, "gen", "scene_hall.json")) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def rom():
    sh("bash", "dev/build.sh")
    return os.path.join(GAME_DIR, "shipit.gba"), os.path.join(GAME_DIR, "shipit.elf")


class Game:
    """The PC rules through ctypes. `start()` presses Start on the title, then A on the how-to card."""

    def __init__(self, so):
        self.so = so
        so.rules_init()

    def step(self, buttons=0, n=1):
        for _ in range(n):
            self.so.rules_step(buttons)

    def start(self):
        self.step(START)
        self.step(0)
        self.step(A)
        self.step(0)

    def place(self, x, y):
        self.so.rules_debug_place(x, y)

    def __getattr__(self, name):
        return getattr(self.so, "rules_" + name)


@pytest.fixture
def game(lib):
    return Game(lib)
