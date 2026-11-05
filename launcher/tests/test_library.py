import json
import os

import pytest

from arca_launcher.library import Game, LibraryError, load_library


def test_loads_the_built_library(library_dir):
    games = load_library(library_dir)
    by = {g.id: g for g in games}
    assert len(games) == 4
    assert by["alpha-quest"].rom_exists and by["alpha-quest"].rom_origin == "built"
    assert not by["gamma"].rom_exists and by["gamma"].rom is None
    assert by["beta-blocks"].platform_name == "Game Boy Color"
    assert isinstance(by["alpha-quest"].shots, tuple) and len(by["alpha-quest"].shots) == 3


def test_missing_library_raises(tmp_path):
    with pytest.raises(LibraryError):
        load_library(str(tmp_path))


def test_corrupt_library_raises(tmp_path):
    (tmp_path / "library.json").write_text("{not json")
    with pytest.raises(LibraryError):
        load_library(str(tmp_path))


def test_bad_entries_are_skipped(tmp_path):
    (tmp_path / "library.json").write_text(json.dumps({"version": 1, "games": [
        {"id": "a", "title": "A"}, {"id": "a", "title": "Duplicate"}, {"title": "No id"}, "junk", {"id": "b", "title": "B"}]}))
    games = load_library(str(tmp_path))
    assert [g.id for g in games] == ["a", "b"]
    assert games[0] == Game(id="a", title="A")


def test_the_arcade_field_is_carried_onto_the_game(tmp_path):
    arc = {"id": "SHIP", "replay": "/x/arcade_replay"}
    (tmp_path / "library.json").write_text(json.dumps({"version": 1, "games": [
        {"id": "a", "title": "A", "arcade": arc}, {"id": "b", "title": "B", "arcade": "junk"},
        {"id": "c", "title": "C", "arcade": {"replay": "/x/arcade_replay"}}]}))     # no id: no board to name it by
    a, b, c = load_library(str(tmp_path))
    assert a.arcade == arc and b.arcade is None and c.arcade is None
    assert hash(a) is not None


def test_an_app_entry_needs_no_rom(tmp_path):
    (tmp_path / "library.json").write_text(json.dumps({"version": 1, "games": [
        {"id": "browser", "title": "Browser", "app": "browser", "platform": "App"},
        {"id": "x", "title": "X", "app": 5}]}))
    browser, x = load_library(str(tmp_path))
    assert browser.app == "browser" and browser.rom is None and browser.rom_exists and browser.rom_origin == "app"
    assert x.app is None and not x.rom_exists                    # a junk app field is no app


def test_how_to_play_is_carried_onto_the_game(tmp_path):
    how = {"goal": "Eat the ETH, do not hit the walls.", "controls": [["D-pad", "Turn"], ["Start", "Pause"]]}
    (tmp_path / "library.json").write_text(json.dumps({"version": 1, "games": [
        {"id": "a", "title": "A", "how_to": how}, {"id": "b", "title": "B", "how_to": "junk"}]}))
    a, b = load_library(str(tmp_path))
    assert a.how_to == how and b.how_to is None
    assert hash(a) is not None


def test_a_gameplay_clip_is_carried_onto_the_game(tmp_path):
    (tmp_path / "library.json").write_text(json.dumps({"version": 1, "games": [
        {"id": "a", "title": "A", "clip": ["art/a-clip-00.png", "art/a-clip-01.png"]}, {"id": "b", "title": "B"}]}))
    a, b = load_library(str(tmp_path))
    assert a.clip == ("art/a-clip-00.png", "art/a-clip-01.png") and b.clip == ()
