"""arca_launcher/exits.py: how the last game or app ended, from the marks left in /run/anypercent."""
from arca_launcher import exits


def test_a_fresh_home_key_mark_counts_once(tmp_path):
    (tmp_path / "home-quit").write_text("1000.0\n")
    assert exits.home_quit(str(tmp_path), now=1010.0)
    assert not (tmp_path / "home-quit").exists()
    assert not exits.home_quit(str(tmp_path), now=1010.0)


def test_an_old_home_key_mark_does_not_count(tmp_path):
    (tmp_path / "home-quit").write_text("1000.0\n")
    assert not exits.home_quit(str(tmp_path), now=1000.0 + exits.HOME_QUIT_MAX_AGE + 1)
    assert not (tmp_path / "home-quit").exists()


def test_no_mark_and_no_folder_are_fine(tmp_path):
    assert not exits.home_quit(str(tmp_path / "missing"), now=0)
    assert exits.app_exit(str(tmp_path / "missing")) is None


def test_an_app_exit_is_read_once(tmp_path):
    (tmp_path / "app-exit").write_text("anypercent-gta3 exit-code exited 139\n")
    e = exits.app_exit(str(tmp_path))
    assert e == exits.AppExit("anypercent-gta3.service", "exit-code", "exited", "139")
    assert not e.ok
    assert exits.app_exit(str(tmp_path)) is None


def test_an_app_stopped_on_request_ended_fine(tmp_path):
    (tmp_path / "app-exit").write_text("anypercent-browser success killed TERM\n")
    assert exits.app_exit(str(tmp_path)).ok


def test_a_garbled_mark_is_ignored(tmp_path):
    (tmp_path / "app-exit").write_text("\n")
    assert exits.app_exit(str(tmp_path)) is None


def test_crashes_are_logged_and_listed_newest_first(tmp_path):
    exits.log_crash(str(tmp_path), 1000.0, "Snake", "retroarch exited with code 139")
    exits.log_crash(str(tmp_path), 2000.0, "GTA III", "exit-code exited 139")
    rows = exits.crashes(str(tmp_path))
    assert [r[1] for r in rows] == ["GTA III", "Snake"]
    assert rows[0][2] == "exit-code exited 139"


def test_the_crash_log_keeps_only_the_last_twenty(tmp_path):
    for i in range(30):
        exits.log_crash(str(tmp_path), float(i), f"G{i}", "x")
    rows = exits.crashes(str(tmp_path), n=100)
    assert len(rows) == 20 and rows[0][1] == "G29"


def test_no_crash_log_is_no_crashes(tmp_path):
    assert exits.crashes(str(tmp_path / "none")) == []
