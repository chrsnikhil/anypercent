"""The console's id (handler/console_id.py): a random id in a file beside the ledger, made once, kept across restarts,
one per --state directory, and never written to a log."""
import logging
import os
import stat

from arca_launcher.handler import console_id
from arca_launcher.handler.console_id import CONSOLE_RE, load_or_create


def test_it_is_made_once_and_kept(tmp_path):
    first = load_or_create(str(tmp_path))
    assert CONSOLE_RE.fullmatch(first) and len(first) == 32
    assert (tmp_path / "console-id").read_text(encoding="ascii").strip() == first
    assert load_or_create(str(tmp_path)) == first                    # a restart: the same console


def test_the_file_is_the_owners_alone(tmp_path):
    load_or_create(str(tmp_path))
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(tmp_path / "console-id").st_mode) == 0o600


def test_two_state_dirs_are_two_consoles(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert load_or_create(str(a)) != load_or_create(str(b))
    assert (a / "console-id").exists() and (b / "console-id").exists()


def test_a_damaged_file_is_replaced_by_a_fresh_id(tmp_path):
    (tmp_path / "console-id").write_text("not an id\n", encoding="ascii")
    made = load_or_create(str(tmp_path))
    assert CONSOLE_RE.fullmatch(made) and load_or_create(str(tmp_path)) == made


def test_the_id_is_never_logged(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "console-id").write_text("short", encoding="ascii")
    made = load_or_create(str(tmp_path / "x"))
    again = load_or_create(str(tmp_path / "y"))
    assert made not in caplog.text and again not in caplog.text


def test_an_unwritable_dir_still_gives_an_id_for_this_run(tmp_path, monkeypatch):
    def refuse(*a, **kw):
        raise OSError("read-only")
    monkeypatch.setattr(console_id.os, "open", refuse)
    made = load_or_create(str(tmp_path / "ro"))
    assert CONSOLE_RE.fullmatch(made)
