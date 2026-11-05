"""games/new_game.sh: stamps games/template into a new game directory that builds from clean and passes its suite.
Run from games/ in the sandbox:  $SANDBOX/venv/bin/python -m pytest   (takes about a minute: a full ROM build)."""
import os
import re
import shutil
import subprocess

import pytest

GAMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(GAMES, "new_game.sh")
DIR = "_stamp_test_%d" % os.getpid()     # unique per run: two suites never share a stamp
TARGET = os.path.join(GAMES, DIR)
BAD = "_stamp_bad_%d" % os.getpid()


def stamp(*args):
    return subprocess.run(["bash", SCRIPT, *args], cwd=GAMES, capture_output=True, text=True)


@pytest.fixture
def stamped():
    shutil.rmtree(TARGET, ignore_errors=True)
    try:
        r = stamp("ZZST", DIR, "STAMP TEST", "ZZSC")
        assert r.returncode == 0, r.stdout + r.stderr
        yield TARGET
    finally:
        shutil.rmtree(TARGET, ignore_errors=True)


def read(*path):
    with open(os.path.join(TARGET, *path)) as f:
        return f.read()


def test_the_stamp_renames_and_carries_no_generated_files(stamped):
    make = read("Makefile")
    assert re.search(r"^TARGET\s*:=\s*%s$" % DIR, make, re.M)
    assert re.search(r"^ROMTITLE\s*:=\s*STAMP TEST$", make, re.M)
    assert re.search(r"^ROMCODE\s*:=\s*ZZSC$", make, re.M)
    assert '"ZZST"' in read("rules", "game.c") and "TMPL" not in read("rules", "game.c")
    assert '"STAMP TEST"' in read("src", "view.cpp")
    assert read("README.md").startswith("# STAMP TEST") and "`ZZST`" in read("README.md")
    for generated in ("build", "out", os.path.join("tests", "out"), "template.gba", "template.elf"):
        assert not os.path.exists(os.path.join(stamped, generated)), generated
    for root, dirs, files in os.walk(stamped):
        assert "__pycache__" not in dirs and not [f for f in files if f.endswith((".gba", ".elf", ".sav", ".o"))]
    assert os.path.exists(os.path.join(stamped, "tests", "test_generic.py"))
    with open(os.path.join(GAMES, "template", "tests", "test_generic.py")) as f:
        assert read("tests", "test_generic.py") == f.read()


def test_the_stamped_game_builds_from_clean_and_passes_its_suite(stamped):
    r = subprocess.run(["bash", "dev/pytest.sh"], cwd=stamped, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-5000:] + r.stderr[-3000:]
    assert os.path.exists(os.path.join(stamped, DIR + ".gba"))
    assert re.search(r"\d+ passed", r.stdout) and "failed" not in r.stdout


def test_it_refuses_an_existing_directory(stamped):
    r = stamp("ZZSU", DIR, "OTHER", "ZZSD")
    assert r.returncode != 0 and "exists" in r.stderr
    assert '"ZZST"' in read("rules", "game.c")


@pytest.mark.parametrize("args", [("ZZ", BAD, "T", "ZZSC"), ("ZZST", "Bad-Dir", "T", "ZZSC"),
                                  ("ZZST", BAD, "A TITLE TOO LONG", "ZZSC"),
                                  ("ZZST", BAD, "T", "Z"), ("TMPL", BAD, "T", "ZZSC"),
                                  ("ZZST", BAD, "T")])
def test_it_refuses_bad_arguments(args):
    r = stamp(*args)
    assert r.returncode != 0
    assert not os.path.exists(os.path.join(GAMES, BAD))
