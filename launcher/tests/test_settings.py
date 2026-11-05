import json

from arca_launcher import settings
from arca_launcher.settings import Prefs


def test_round_trip(tmp_path):
    path = str(tmp_path / "state" / "state.json")
    settings.save(path, Prefs(volume=30, brightness=60, last_played={"a": 5.0}))
    p = settings.load(path)
    assert (p.volume, p.brightness, p.last_played) == (30, 60, {"a": 5.0})


def test_missing_file_gives_defaults(tmp_path):
    assert settings.load(str(tmp_path / "nope.json")) == Prefs()


def test_corrupt_file_gives_defaults(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{oops")
    assert settings.load(str(path)) == Prefs()


def test_values_are_clamped_and_junk_dropped(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"volume": 250, "brightness": 0, "last_played": {"a": 3, "b": "x", "c": True}}))
    p = settings.load(str(path))
    assert p.volume == 100 and p.brightness == 10
    assert p.last_played == {"a": 3.0}


def test_wrong_types_give_defaults(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"volume": "loud", "brightness": None, "last_played": []}))
    assert settings.load(str(path)) == Prefs()


def test_on_screen_controls_default_off_and_round_trip(tmp_path):
    assert Prefs().touch_controls is False
    path = str(tmp_path / "state.json")
    settings.save(path, Prefs(touch_controls=True))
    assert settings.load(path).touch_controls is True
    settings.save(path, Prefs())
    assert settings.load(path).touch_controls is False


def test_on_screen_controls_junk_gives_off(tmp_path):
    path = tmp_path / "state.json"
    for junk in ("yes", 1, None, [True]):
        path.write_text(json.dumps({"touch_controls": junk}))
        assert settings.load(str(path)).touch_controls is False


def test_theme_round_trips_and_junk_gives_the_default(tmp_path):
    from arca_launcher import settings
    path = str(tmp_path / "s.json")
    p = settings.Prefs()
    assert p.theme == "anypercent"
    p.theme = "chainlink"
    settings.save(path, p)
    assert settings.load(path).theme == "chainlink"
    import json
    json.dump({"theme": 42}, open(path, "w"))
    assert settings.load(path).theme == "anypercent"
    json.dump({"theme": "no-such-theme"}, open(path, "w"))
    assert settings.load(path).theme == "anypercent"


def test_the_day_the_record_book_was_offered_round_trips(tmp_path):
    path = str(tmp_path / "s.json")
    assert Prefs().handler_offered == ""
    settings.save(path, Prefs(handler_offered="2026-11-06"))
    assert settings.load(path).handler_offered == "2026-11-06"
    (tmp_path / "s.json").write_text(json.dumps({"handler_offered": 42}))
    assert settings.load(path).handler_offered == ""
