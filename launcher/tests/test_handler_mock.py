"""Tests for the sponsor interface (handler/sponsors.py) and its mock implementation
(handler/mock.py). MockSponsors is driven by a fake clock so delays are exact, not timed."""
import ast
import re
from pathlib import Path

import pytest

from arca_launcher.handler.sponsors import STEPS, TIMEOUT_MS, Outcome, Result, SponsorNames
from arca_launcher.handler.mock import MockSponsors
from arca_launcher.handler import states

HEX8 = re.compile(r"^[0-9a-f]{8}$")
CODE = re.compile(r"^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{3}-[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{3}$")


class FakeClock:
    """A clock the test drives by hand: MockSponsors never sees a real timer."""

    def __init__(self):
        self.ms = 0

    def __call__(self):
        return self.ms


def test_steps_and_timeouts_match_the_brief():
    assert STEPS == ("status", "idkit_scan", "idkit_confirm", "idkit_verify", "check_listing", "pay",
                      "load_ghost", "approve_scan", "approve", "record", "publish", "sales")
    assert TIMEOUT_MS == {"idkit_verify": 10000, "pay": 8000, "record": 8000, "publish": 8000,
                           "check_listing": 8000, "load_ghost": 8000}


def test_sponsor_names_fill_formats_placeholders_and_extras():
    names = SponsorNames()
    assert names.world == "World" and names.board == "Arkiv" and names.third == "Hedera"
    assert names.pay_rail == "x402 on Hedera" and names.record_rail == "Hedera"
    assert (names.fill("{world} {board} {third} {pay_rail} {record_rail}")
            == "World Arkiv Hedera x402 on Hedera Hedera")
    assert names.fill("{world} says {extra}", extra="hi") == "World says hi"


def test_mock_flag_and_default_names():
    sponsors = MockSponsors(clock_ms=FakeClock())
    assert sponsors.mock is True
    assert sponsors.names == SponsorNames()


def test_timed_steps_take_the_prototype_delays():
    clock = FakeClock()
    sponsors = MockSponsors(clock_ms=clock)
    call = sponsors.begin("pay", {})
    clock.ms = 1999
    assert call.poll() is None
    clock.ms = 2000
    result = call.poll()
    assert result.ok is True
    assert HEX8.match(result.data["receipt"][5:])
    assert result.data["receipt"].startswith("mock-")


def test_each_timed_step_resolves_at_its_delay_with_its_data():
    cases = [
        ("idkit_verify", 1700, {"credential": "Selfie Check"}),
        ("check_listing", 1400, {"price": 10}),
        ("load_ghost", 1200, {}),
        ("record", 2000, {}),
        ("publish", 1400, {}),
    ]
    for step, delay_ms, data in cases:
        clock = FakeClock()
        sponsors = MockSponsors(clock_ms=clock)
        call = sponsors.begin(step, {})
        clock.ms = delay_ms - 1
        assert call.poll() is None, step
        clock.ms = delay_ms
        result = call.poll()
        assert result.ok is True, step
        assert result.data == data, step


def test_status_and_sales_resolve_at_once():
    clock = FakeClock()
    sponsors = MockSponsors(clock_ms=clock)
    result = sponsors.begin("status", {}).poll()
    assert result.ok is True
    assert result.data == {"world": "ok", "board": "ok", "third": "ok"}

    result = sponsors.begin("sales", {}).poll()
    assert result == Result(ok=True, data={"buyer": "ARJUN"})


def test_phone_steps_wait_for_cross():
    clock = FakeClock()
    sponsors = MockSponsors(clock_ms=clock)

    for step in ("idkit_scan", "idkit_confirm", "approve_scan"):
        call = sponsors.begin(step, {})
        clock.ms += 10_000_000  # time passing alone never resolves a phone step
        assert call.poll() is None, step
        sponsors.cross(call)
        assert call.poll() == Result(ok=True, data={}), step

    approve_call = sponsors.begin("approve", {})
    sponsors.cross(approve_call)
    result = approve_call.poll()
    assert result.ok is True
    assert HEX8.match(result.data["jti"])

    # cross() on a non-phone call does nothing: the step still waits for its own timer.
    clock2 = FakeClock()
    sponsors2 = MockSponsors(clock_ms=clock2)
    pay_call = sponsors2.begin("pay", {})
    sponsors2.cross(pay_call)
    assert pay_call.poll() is None


def test_force_gives_the_named_failure():
    sponsors = MockSponsors(clock_ms=FakeClock())
    call = sponsors.begin("approve", {})
    outcome = next(o for o in sponsors.outcomes("approve") if o.failure == "ls_denied")
    sponsors.force(call, outcome)
    assert call.poll() == Result(ok=False, failure="ls_denied", data={})


def test_paid_late_forces_buy_down_with_a_late_receipt():
    # Picked the same way the flow engine will: find the outcome row whose late flag is set,
    # not by comparing a label string (two rows on "pay" share the failure name "buy_down").
    sponsors = MockSponsors(clock_ms=FakeClock())
    call = sponsors.begin("pay", {})
    late_outcome = next(o for o in sponsors.outcomes("pay") if o.late)
    assert late_outcome.label == "Paid late"
    assert late_outcome.failure == "buy_down"
    sponsors.force(call, late_outcome)
    result = call.poll()
    assert result.ok is False
    assert result.failure == "buy_down"
    assert result.data["late_receipt"].startswith("mock-")
    assert HEX8.match(result.data["late_receipt"][5:])

    # The sibling row, same failure name, carries no late receipt.
    clock = FakeClock()
    sponsors2 = MockSponsors(clock_ms=clock)
    call2 = sponsors2.begin("pay", {})
    plain_outcome = next(o for o in sponsors2.outcomes("pay") if not o.late)
    assert plain_outcome.failure == "buy_down"
    sponsors2.force(call2, plain_outcome)
    assert call2.poll() == Result(ok=False, failure="buy_down", data={})


def test_a_down_service_fails_its_steps():
    clock = FakeClock()
    sponsors = MockSponsors(clock_ms=clock)

    sponsors.set_down("world", True)
    assert sponsors.status()["world"] == "off"
    assert sponsors.begin("idkit_scan", {}).poll() == Result(ok=False, failure="id_offline", data={})
    assert sponsors.begin("idkit_confirm", {}).poll() == Result(ok=False, failure="id_offline", data={})
    assert sponsors.begin("idkit_verify", {}).poll() == Result(ok=False, failure="id_offline", data={})
    assert sponsors.begin("approve_scan", {}).poll() == Result(ok=False, failure="ls_world_down", data={})
    assert sponsors.begin("approve", {}).poll() == Result(ok=False, failure="ls_world_down", data={})
    sponsors.set_down("world", False)

    sponsors.set_down("third", True)
    assert sponsors.status()["third"] == "off"
    assert sponsors.begin("pay", {}).poll() == Result(ok=False, failure="buy_down", data={})
    assert sponsors.begin("load_ghost", {}).poll() == Result(ok=False, failure="buy_load_fail", data={})
    assert sponsors.begin("record", {}).poll() == Result(ok=False, failure="ls_record_fail", data={})
    sponsors.set_down("third", False)

    # The board has no failure state of its own: its steps still succeed when it is "off".
    sponsors.set_down("board", True)
    assert sponsors.status()["board"] == "off"
    clock.ms = 0
    call = sponsors.begin("check_listing", {})
    clock.ms = 1400
    result = call.poll()
    assert result.ok is True
    assert result.data == {"price": 10}


def test_down_overrides_a_waiting_phone_step():
    sponsors = MockSponsors(clock_ms=FakeClock())
    call = sponsors.begin("approve", {})
    sponsors.set_down("world", True)
    assert call.poll() == Result(ok=False, failure="ls_world_down", data={})
    sponsors.cross(call)  # too late: the call already resolved down
    assert call.poll().failure == "ls_world_down"


def test_status_reports_busy_while_a_timed_call_is_in_flight():
    clock = FakeClock()
    sponsors = MockSponsors(clock_ms=clock)
    sponsors.begin("pay", {})
    assert sponsors.status()["third"] == "busy"
    clock.ms = 2000
    assert sponsors.status()["third"] == "ok"


def test_status_never_resolves_a_call():
    # Ruling 11: status() peeks. Polling would cache the timed call's success, and a Square
    # outcome forced on it afterwards would be silently ignored.
    clock = FakeClock()
    sponsors = MockSponsors(clock_ms=clock)
    call = sponsors.begin("pay", {})
    for ms in range(0, 2600, 100):
        clock.ms = ms
        sponsors.status()
    assert sponsors.status()["third"] == "ok"  # its delay has passed: no longer busy
    down = next(o for o in sponsors.outcomes("pay") if not o.late)
    sponsors.force(call, down)
    assert call.poll() == Result(ok=False, failure="buy_down", data={})


def test_a_waiting_phone_step_never_makes_its_service_busy():
    # A phone call waits for minutes, or is kept after Circle: only a timed call shows busy. The
    # state table's own `busy` field pulses a pill where a step needs it.
    clock = FakeClock()
    sponsors = MockSponsors(clock_ms=clock)
    for step in ("idkit_scan", "idkit_confirm", "approve_scan", "approve"):
        sponsors.begin(step, {})
        assert sponsors.status()["world"] == "ok", step
    sponsors.begin("idkit_verify", {})
    assert sponsors.status()["world"] == "busy"
    clock.ms = 1700
    assert sponsors.status()["world"] == "ok"


def test_qr_steps_carry_a_code_and_expiry_in_info():
    sponsors = MockSponsors(clock_ms=FakeClock(), seed=1)
    scan = sponsors.begin("idkit_scan", {})
    assert CODE.match(scan.info["code"])
    assert scan.info["expires_s"] == 300

    approve_scan = sponsors.begin("approve_scan", {})
    assert CODE.match(approve_scan.info["code"])
    assert approve_scan.info["expires_s"] == 1200

    # Steps that are not a QR screen carry no code.
    assert sponsors.begin("idkit_confirm", {}).info == {}
    assert sponsors.begin("pay", {}).info == {}
    assert sponsors.begin("status", {}).info == {}


def test_mock_sponsors_seed_is_deterministic():
    a = MockSponsors(clock_ms=FakeClock(), seed=7)
    b = MockSponsors(clock_ms=FakeClock(), seed=7)
    assert a.begin("idkit_scan", {}).info["code"] == b.begin("idkit_scan", {}).info["code"]


def test_outcomes_match_the_brief_per_step():
    sponsors = MockSponsors(clock_ms=FakeClock())
    assert sponsors.outcomes("idkit_confirm") == [
        Outcome("Reject", "id_rejected"), Outcome("Let it expire", "id_expired"),
        Outcome("No Selfie Check", "id_nocred"), Outcome("Same person again", "id_dup"),
        Outcome("World down", "id_offline"),
    ]
    assert sponsors.outcomes("check_listing") == [
        Outcome("Budget used up", "buy_budget"), Outcome("Price changed", "buy_changed"),
        Outcome("Sales suspended", "buy_suspended"),
    ]
    assert sponsors.outcomes("pay") == [Outcome("Hedera down", "buy_down"),
                                         Outcome("Paid late", "buy_down", late=True)]
    assert sponsors.outcomes("approve") == [
        Outcome("Deny", "ls_denied"), Outcome("Expire", "ls_expired"),
        Outcome("Another World ID", "ls_wrong"), Outcome("Codes differ", "ls_mismatch"),
        Outcome("Reused approval", "ls_reused"),
    ]
    assert sponsors.outcomes("record") == [Outcome("Hedera slow", "ls_record_fail")]
    assert sponsors.outcomes("approve_scan") == [Outcome("World down", "ls_world_down")]
    for step in ("status", "idkit_scan", "idkit_verify", "publish", "sales", "load_ghost"):
        assert sponsors.outcomes(step) == [], step


def test_outcomes_use_the_sponsor_names_table():
    names = SponsorNames(world="W", board="B", third="T", pay_rail="PR", record_rail="RR")
    sponsors = MockSponsors(clock_ms=FakeClock(), names=names)
    assert Outcome("T down", "buy_down") in sponsors.outcomes("pay")
    assert Outcome("W down", "id_offline") in sponsors.outcomes("idkit_confirm")
    assert Outcome("T slow", "ls_record_fail") in sponsors.outcomes("record")


def test_outcome_lists_name_existing_failures():
    sponsors = MockSponsors(clock_ms=FakeClock())
    for step in STEPS:
        for o in sponsors.outcomes(step):
            assert o.failure in states.STATES, (step, o.label, o.failure)


BANNED_MODULES = {"socket", "urllib", "http", "requests", "httpx", "web3", "hedera", "hiero", "idkit"}


def test_handler_code_has_no_network_or_sponsor_imports():
    launcher_dir = Path(__file__).resolve().parent.parent
    root = launcher_dir / "arca_launcher"
    paths = sorted((root / "handler").rglob("*.py")) + sorted((root / "render").glob("handler*.py"))
    paths = [p for p in paths if p.name not in REAL_ADAPTERS]   # the real adapters: the test below
    assert paths, "expected at least handler/*.py to exist by this point in the plan"
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for name in names:
                first = name.split(".")[0]
                assert first not in BANNED_MODULES, f"{path} imports banned module {name}"


# The real adapters, and the standard library each may use: World's bridge (world.py), Arkiv's public RPC and our
# service (arkiv_rpc.py, arkiv.py), and Hedera through our service only (hedera.py: no Hedera SDK, key or account on
# the console).
REAL_ADAPTERS = {
    "world.py": {"json", "logging", "platform", "threading", "urllib", "arca_launcher"},
    "arkiv_rpc.py": {"functools", "json", "re", "time", "urllib", "arca_launcher"},
    "arkiv.py": {"base64", "binascii", "dataclasses", "decimal", "hashlib", "json", "logging", "os", "re",
                 "threading", "urllib", "arca_launcher"},
    "hedera.py": {"json", "logging", "os", "re", "threading", "urllib", "arca_launcher"},
}


def test_the_real_adapters_talk_http_with_the_standard_library_only():
    """The real adapters reach their bridge, Arkiv's RPC and our service with urllib on their own threads: the Pi's
    venv has no package beyond pygame, and no sponsor SDK runs on the console."""
    for name, allowed in REAL_ADAPTERS.items():
        path = Path(__file__).resolve().parent.parent / "arca_launcher" / "handler" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        firsts = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                firsts.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                firsts.add(node.module.split(".")[0])
        assert firsts <= allowed, (name, firsts - allowed)
