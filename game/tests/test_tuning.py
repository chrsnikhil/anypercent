"""The difficulty, pinned: a good run (the route bot) and a hesitant first run (the sloppy bot) must ship inside
their hour windows, so a first-timer "just makes it" (see the milestone 3 spec)."""
import os
import sys

from conftest import GAME_DIR, SC_CLEAR

sys.path.insert(0, os.path.join(GAME_DIR, "dev"))
import bot  # noqa: E402


def ship_hour(lib, sloppy):
    b = bot.Bot(lib, sloppy=sloppy)
    b.play()
    assert lib.rules_scene() == SC_CLEAR, "the %s bot did not ship" % ("sloppy" if sloppy else "route")
    assert lib.rules_split(1) + lib.rules_split(2) + lib.rules_split(3) == lib.rules_run_frames()
    return lib.rules_hour()


def test_a_good_run_ships_between_hours_22_and_26(lib):
    assert 22 <= ship_hour(lib, False) <= 26


def test_a_sloppy_first_run_ships_between_hours_30_and_34(lib):
    assert 30 <= ship_hour(lib, True) <= 34
