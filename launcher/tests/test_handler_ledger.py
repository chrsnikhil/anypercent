import json
import re

from arca_launcher.handler import ledger
from arca_launcher.handler.ledger import Ledger


def test_round_trip(tmp_path):
    path = str(tmp_path / "handler.json")
    led = Ledger(book="ANY-7QZ", credential="Selfie Check", spent=20, spent_day="2026-11-05",
                 purchases={"ship:RIA": {"price": 10, "receipt": "mock-1", "at": 123.0}},
                 listings=[{"game": "ship", "frames": 900, "price": 10, "at": 123.0, "sold": 0}],
                 pending_sale={"game": "ship", "buyer": "KIRAN"},
                 targets={"ship": "RIA"})
    ledger.save(path, led)
    loaded = ledger.load(path)
    assert loaded == led


def test_budget_resets_at_midnight(tmp_path):
    led = Ledger(spent=100, spent_day="2026-11-05")
    assert ledger.budget_left(led, "2026-11-06") == 100


def test_buy_charges_once_per_ghost(tmp_path):
    led = Ledger()
    today = "2026-11-05"
    assert ledger.buy(led, "ship", "RIA", 10, "mock-1", today) is True
    assert led.spent == 10
    assert ledger.buy(led, "ship", "RIA", 10, "mock-2", today) is False
    assert led.spent == 10


def test_buy_refuses_past_budget(tmp_path):
    today = "2026-11-05"
    led = Ledger(spent=95, spent_day=today)
    assert ledger.buy(led, "ship", "RIA", 10, "mock-1", today) is False
    assert led.spent == 95
    assert ledger.owns(led, "ship", "RIA") is False


def test_a_late_receipt_is_recorded_past_the_budget():
    # The money already moved, so the ledger must show it; still never twice for one ghost.
    today = "2026-11-05"
    led = Ledger(spent=95, spent_day=today)
    assert ledger.buy(led, "ship", "RIA", 10, "late-1", today, enforce_budget=False) is True
    assert led.spent == 105
    assert ledger.owns(led, "ship", "RIA") is True
    assert ledger.buy(led, "ship", "RIA", 10, "late-2", today, enforce_budget=False) is False
    assert led.spent == 105
    assert led.purchases["ship:RIA"]["receipt"] == "late-1"


def test_corrupt_or_foreign_ledger_loads_empty(tmp_path):
    for content in (b"\x00{", json.dumps([1, 2, 3]).encode(), json.dumps({"book": 7}).encode()):
        path = tmp_path / "handler.json"
        path.write_bytes(content)
        assert ledger.load(str(path)) == Ledger()


def test_start_over_removes_the_file(tmp_path):
    path = tmp_path / "handler.json"
    ledger.save(str(path), Ledger(book="ANY-7QZ"))
    assert path.exists()
    result = ledger.start_over(str(path))
    assert not path.exists()
    assert result == Ledger()


def test_book_ids_look_right():
    class FixedRng:
        def choice(self, seq):
            return seq[0]

    book = ledger.make_book(FixedRng())
    assert re.match(r"^ANY-[A-HJ-NP-Z2-9]{3}$", book)


def test_banned_words():
    from arca_launcher.handler import BANNED_WORDS
    assert BANNED_WORDS == ("prove", "proof", "verified human", "earn", "win", "wins", "cash out",
                             "prize", "staked", "bounty", "human ghost")


def test_a_world_verified_book_is_remembered(tmp_path):
    """Only a record book the real World bridge verified makes YOU a HUMAN on the board."""
    path = str(tmp_path / "handler.json")
    assert Ledger().world_verified is False
    ledger.save(path, Ledger(book="ANY-6PS", credential="Orb", world_verified=True))
    assert ledger.load(path).world_verified is True
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"book": "ANY-6PS", "world_verified": "yes"}, f)   # anything but a real true: not verified
    assert ledger.load(path).world_verified is False
