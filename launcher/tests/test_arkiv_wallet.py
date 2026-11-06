"""The console's Arkiv wallet (handler/arkiv_wallet.py): its key made once on the device (0600, 64 hex digits, a valid
secp256k1 key), one per --state directory, never replaced once it holds anything and never logged; its address asked
of the signer once, kept beside the key with a fingerprint of it, and logged once."""
import logging
import os
import stat

import pytest

from arca_launcher.handler import arkiv_wallet
from arca_launcher.handler.arkiv_sign import SignError
from arca_launcher.handler.arkiv_wallet import ADDRESS_FILE, FILE, address, key_file

SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
ADDR = "0x" + "1a2b" * 10
OTHER = "0x" + "9f3e" * 10


class FakeSigner:
    def __init__(self, answer=ADDR, error=None):
        self.answer, self.error, self.asked = answer, error, []

    def address(self, path):
        self.asked.append(path)
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture(autouse=True)
def fresh_log():
    arkiv_wallet._logged.clear()
    yield
    arkiv_wallet._logged.clear()


def read(path):
    with open(path, encoding="ascii") as f:
        return f.read()


# ---- the key --------------------------------------------------------------------------------------------------------

def test_the_key_is_made_once_as_64_hex_and_kept(tmp_path):
    path = key_file(str(tmp_path))
    assert path == os.path.join(str(tmp_path), FILE)
    text = read(path)
    assert len(text.strip()) == 64 and all(c in "0123456789abcdef" for c in text.strip())
    assert 0 < int(text, 16) < SECP256K1_N
    assert key_file(str(tmp_path)) == path and read(path) == text            # a restart: the same wallet


def test_the_key_file_is_the_owners_alone(tmp_path):
    path = key_file(str(tmp_path))
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_a_key_left_readable_by_others_is_closed_again(tmp_path):
    path = key_file(str(tmp_path))
    if os.name != "posix":
        pytest.skip("modes are POSIX")
    os.chmod(path, 0o644)
    assert key_file(str(tmp_path)) == path
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_two_state_dirs_are_two_wallets(tmp_path):
    a, b = key_file(str(tmp_path / "a")), key_file(str(tmp_path / "b"))
    assert read(a) != read(b)


def test_a_key_file_that_holds_anything_else_is_never_replaced(tmp_path, caplog):
    path = tmp_path / FILE
    path.write_text("not a key, but maybe the owner's\n", encoding="ascii")
    caplog.set_level(logging.WARNING)
    assert key_file(str(tmp_path)) == str(path)
    assert path.read_text(encoding="ascii") == "not a key, but maybe the owner's\n"
    assert "never replaced" in caplog.text


def test_an_empty_key_file_from_an_interrupted_start_is_made_again(tmp_path):
    path = tmp_path / FILE
    path.write_text("", encoding="ascii")
    assert key_file(str(tmp_path)) == str(path)
    assert len(path.read_text(encoding="ascii").strip()) == 64


def test_a_key_with_0x_is_kept_as_it_is(tmp_path):
    path = tmp_path / FILE
    path.write_text("0x" + "ab" * 32 + "\n", encoding="ascii")
    key_file(str(tmp_path))
    assert path.read_text(encoding="ascii") == "0x" + "ab" * 32 + "\n"


def test_an_unwritable_dir_gives_the_path_and_no_crash(tmp_path, monkeypatch, caplog):
    def refuse(*a, **kw):
        raise OSError("read-only")
    monkeypatch.setattr(arkiv_wallet.os, "open", refuse)
    caplog.set_level(logging.WARNING)
    path = key_file(str(tmp_path / "ro"))
    assert path == os.path.join(str(tmp_path / "ro"), FILE) and not os.path.exists(path)
    assert "not saved" in caplog.text
    signer = FakeSigner()
    assert address(str(tmp_path / "ro"), signer) is None and signer.asked == []


def test_the_key_is_never_logged(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    path = key_file(str(tmp_path))
    address(str(tmp_path), FakeSigner())
    key = read(path).strip()
    assert key not in caplog.text and key[:16] not in caplog.text


# ---- the address ----------------------------------------------------------------------------------------------------

def test_the_address_is_asked_once_and_kept(tmp_path):
    signer = FakeSigner(answer=ADDR.upper().replace("0X", "0x"))
    assert address(str(tmp_path), signer) == ADDR
    assert signer.asked == [os.path.join(str(tmp_path), FILE)]
    assert address(str(tmp_path), signer) == ADDR and len(signer.asked) == 1
    cached = read(tmp_path / ADDRESS_FILE)
    assert cached.startswith(ADDR + " ")
    assert read(tmp_path / FILE).strip() not in cached                       # the key never goes in it


def test_a_new_key_is_never_shown_with_the_old_address(tmp_path):
    first = FakeSigner(answer=ADDR)
    assert address(str(tmp_path), first) == ADDR
    os.unlink(tmp_path / FILE)                                                # the owner removed the key: a new wallet
    second = FakeSigner(answer=OTHER)
    assert address(str(tmp_path), second) == OTHER and len(second.asked) == 1
    assert read(tmp_path / ADDRESS_FILE).startswith(OTHER + " ")


def test_a_damaged_address_file_is_asked_again(tmp_path):
    key_file(str(tmp_path))
    (tmp_path / ADDRESS_FILE).write_text("rubbish\n", encoding="ascii")
    signer = FakeSigner()
    assert address(str(tmp_path), signer) == ADDR and len(signer.asked) == 1


@pytest.mark.parametrize("kind", ["no_node", "no_key", "bad_reply"])
def test_a_signer_that_cannot_answer_gives_none_and_caches_nothing(tmp_path, caplog, kind):
    caplog.set_level(logging.WARNING)
    assert address(str(tmp_path), FakeSigner(error=SignError(kind, "x"))) is None
    assert not (tmp_path / ADDRESS_FILE).exists()
    assert kind in caplog.text


def test_a_signer_that_breaks_its_contract_never_crashes_the_console(tmp_path):
    assert address(str(tmp_path), FakeSigner(error=RuntimeError("boom"))) is None
    assert address(str(tmp_path), FakeSigner(answer="0x1234")) is None
    assert address(str(tmp_path), FakeSigner(answer=None)) is None
    assert not (tmp_path / ADDRESS_FILE).exists()


def test_a_key_file_that_is_no_key_has_no_address(tmp_path):
    (tmp_path / FILE).write_text("nope\n", encoding="ascii")
    signer = FakeSigner()
    assert address(str(tmp_path), signer) is None and signer.asked == []


def test_the_address_is_logged_once(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    signer = FakeSigner()
    address(str(tmp_path), signer)
    address(str(tmp_path), signer)
    assert caplog.text.count(ADDR) == 1
