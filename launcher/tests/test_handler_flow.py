"""Tests for PB the handler's flow engine (handler/flow.py). Every test drives a real MockSponsors
on a fake clock the test advances by hand, so the mock's delays and the engine's deadlines (read
from the call's own elapsed_ms) tick off the same milliseconds. The ledger lives in a temp dir and
is re-read from disk wherever a test checks that a change was saved."""
import os
import random

import pytest

from arca_launcher.handler.flow import CloseHandler, Flow, RaceTarget
from arca_launcher.handler.ledger import GHOST_PRICE, LISTING_DAYS, Ledger, load, owns, save
from arca_launcher.handler.mock import MockSponsors
from arca_launcher.handler.sponsors import Result
from arca_launcher.handler.states import STATES, copy_texts
from arca_launcher.handler_glue import MOCK_WALLET

TODAY = "2026-11-06"
GAME = "MDGP"


class FakeClock:
    def __init__(self):
        self.ms = 0

    def __call__(self):
        return self.ms


class SpySponsors(MockSponsors):
    """MockSponsors that remembers every call it began, so a test can answer a call the engine
    has already backed out of."""

    def __init__(self, clock_ms, **kwargs):
        super().__init__(clock_ms, **kwargs)
        self.calls = []

    def begin(self, step, payload):
        call = super().begin(step, payload)
        self.calls.append(call)
        return call

    def steps(self):
        return [call.step for call in self.calls]


class _ManualCall:
    """A sponsor call that answers only when the test sets `result` (never, if it does not)."""

    def __init__(self, clock, step):
        self._clock = clock
        self._start = clock()
        self.step = step
        self.info = {}
        self.result = None

    @property
    def elapsed_ms(self):
        return self._clock() - self._start

    def poll(self):
        return self.result


class ManualPaySponsors(SpySponsors):
    def begin(self, step, payload):
        if step != "pay":
            return super().begin(step, payload)
        call = _ManualCall(self._clock_ms, step)
        self.calls.append(call)
        return call


class RealSponsors(SpySponsors):
    mock = False


def _ctx(**over):
    ctx = {"game": "Marine Drive GP", "target": "RIA", "target_time": "1:41.27", "gap": "1.6 s",
           "rank": "7th", "new_rank": "3rd", "split": "0:42 to 0:51, -0.40 s", "board_case": "ok",
           "best_frames": 6290, "ghost_look": "the *cyan kart*", "wallet": MOCK_WALLET,
           "other_book": "ANY-2KD", "runs": 14, "sold": 0, "buyer": "ARJUN"}
    ctx.update(over)
    return ctx


class Rig:
    """One flow over a fake clock, a temp-dir ledger and a fixed day."""

    def __init__(self, tmp_path, book="ANY-7QZ", sponsors=None, ledger=None, ctx=None, **over):
        self.clock = FakeClock()
        self.sponsors = sponsors(self.clock) if sponsors else SpySponsors(self.clock)
        self.path = str(tmp_path / "handler.json")
        led = ledger if ledger is not None else Ledger(book=book)
        self.flow = Flow(self.sponsors, led, self.path, GAME, ctx if ctx is not None else _ctx(**over),
                         today=lambda: TODAY, rng=random.Random(3))

    @property
    def state(self):
        return self.flow.state.name

    def wait(self, ms, frame=100):
        """Advance the clock ms in frames, ticking the flow each frame and reading the sponsors'
        status the way the view's pills do. Returns the commands."""
        commands = []
        while ms > 0:
            step = min(frame, ms)
            self.clock.ms += step
            ms -= step
            self.sponsors.status()
            command = self.flow.tick(step)
            if command is not None:
                commands.append(command)
        return commands

    def saved(self):
        return load(self.path)


def test_a_phone_steps_qr_link_reaches_the_card(tmp_path):
    """A real adapter's phone step hands back the link its QR must carry (call.info["qr"]); the mock has none."""
    class Linked(SpySponsors):
        def begin(self, step, payload):
            call = super().begin(step, payload)
            if step == "idkit_scan":
                call.info["qr"] = "https://example.org/verify?i=1"
            return call
    rig = Rig(tmp_path / "linked", book=None, sponsors=Linked)
    rig.flow.start("book")
    rig.flow.press("cross")
    assert rig.state == "id_scan" and rig.flow.ctx["qr"] == "https://example.org/verify?i=1"
    rig = Rig(tmp_path / "mock", book=None)
    rig.flow.start("book")
    rig.flow.press("cross")
    assert rig.state == "id_scan" and rig.flow.ctx["code"] and not rig.flow.ctx["qr"]

    class LinkOnly(SpySponsors):                                  # a link and no short code: the QR still updates
        def begin(self, step, payload):
            call = super().begin(step, payload)
            if step == "idkit_scan":
                call.info.pop("code", None)
                call.info["qr"] = "https://example.org/verify?i=2"
            return call
    rig = Rig(tmp_path / "linkonly", book=None, sponsors=LinkOnly, code="OLD-123", qr="https://example.org/old")
    rig.flow.start("book")
    rig.flow.press("cross")
    assert (rig.flow.ctx["qr"], rig.flow.ctx["code"]) == ("https://example.org/verify?i=2", "")


# ---- the brief's tests ---------------------------------------------------------------------

def test_cross_walks_each_flow_to_its_success(tmp_path):
    # Record book: no book yet.
    rig = Rig(tmp_path / "book", book=None)
    rig.flow.start("book")
    assert rig.state == "s_boot"
    assert rig.flow.press("cross") is None
    assert rig.state == "id_scan"
    rig.flow.press("cross")
    assert rig.state == "id_scan"  # the phone's answer arrives on the next tick
    rig.wait(16)
    assert rig.state == "id_confirm"
    rig.flow.press("cross")
    rig.wait(16)
    assert rig.state == "id_verifying"
    rig.wait(1700)
    assert rig.state == "id_done"
    assert rig.flow.ledger.book and rig.saved().book == rig.flow.ledger.book

    # Board: buy the target's ghost, then race it.
    rig = Rig(tmp_path / "board")
    rig.flow.start("board")
    assert rig.state == "board"
    rig.flow.press("cross")
    assert rig.state == "target"
    rig.flow.press("cross")
    assert rig.state == "buy_check"
    rig.wait(1400)
    assert rig.state == "buy_pay"
    rig.wait(2000)
    assert rig.state == "buy_load"
    rig.wait(1200)
    assert rig.state == "buy_done"
    assert rig.flow.press("cross") == RaceTarget(GAME, "RIA")
    assert rig.state == "racing"
    assert rig.flow.ledger.spent == GHOST_PRICE

    # List: approve on the phone, record, publish, then back to the hub.
    rig = Rig(tmp_path / "list")
    rig.flow.start("list")
    assert rig.state == "ls_offer"
    rig.flow.press("cross")
    assert rig.state == "ls_scan"
    rig.flow.press("cross")
    rig.wait(16)
    assert rig.state == "ls_approve"
    rig.flow.press("cross")
    rig.wait(16)
    assert rig.state == "ls_record"
    rig.wait(2000)
    assert rig.state == "ls_arkiv"
    rig.wait(1400)
    assert rig.state == "ls_done"
    rig.flow.press("cross")
    assert rig.state == "hub"  # a sale only ever comes from Home (flow 4), never from Cross here
    assert [x["sold"] for x in rig.flow.ledger.listings] == [0]


def _square_cases():
    probe = MockSponsors(FakeClock())
    cases = []
    for name, state in STATES.items():
        if state.call is not None:
            # A late payment lands on buy_late whatever failure name it carries (Ruling 10b).
            cases += [(name, i, "buy_late" if o.late else o.failure)
                      for i, o in enumerate(probe.outcomes(state.call))]
        cases += [(name, i, target) for i, (_label, target) in enumerate(state.mock_outcomes)]
    return cases


def test_every_failure_state_is_reachable_with_square(tmp_path):
    cases = _square_cases()
    # 19 sponsor outcomes over six steps (approve's five twice: ls_approve, and ls_confirm for a
    # World ID approval), plus ls_cancel's own
    assert len(cases) == 25
    for n, (name, i, target) in enumerate(cases):
        rig = Rig(tmp_path / str(n))
        rig.flow.start(name)
        assert rig.state == name
        rig.flow.press("square")
        assert rig.flow.outcomes_open, name
        rig.flow.pick(i)
        assert not rig.flow.outcomes_open
        rig.wait(16)
        assert rig.state == target, (name, i)


def test_cross_spam_during_paying_changes_nothing(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("board")
    rig.flow.press("cross")
    rig.flow.press("cross")
    rig.wait(1400)
    assert rig.state == "buy_pay"
    rig.wait(1000)
    assert rig.flow.in_flight
    for _ in range(20):
        assert rig.flow.press("cross") is None
    assert rig.state == "buy_pay"
    assert rig.flow.ledger.spent == 0
    assert rig.sponsors.steps().count("pay") == 1
    rig.wait(1000)
    assert rig.state == "buy_load"
    assert rig.flow.ledger.spent == GHOST_PRICE
    assert rig.saved().spent == GHOST_PRICE


def test_circle_is_ignored_in_flight_and_works_on_phone_steps(tmp_path):
    rig = Rig(tmp_path / "pay")
    rig.flow.start("buy_pay")
    assert rig.flow.press("circle") is None
    assert rig.state == "buy_pay"
    rig.flow.start("id_verifying")
    assert rig.flow.press("circle") is None
    assert rig.state == "id_verifying"

    rig = Rig(tmp_path / "phone")
    rig.flow.start("id_scan")
    assert not rig.flow.in_flight
    rig.flow.press("circle")
    assert rig.state == "id_cancel"
    rig.flow.start("ls_scan")
    rig.flow.press("circle")
    assert rig.state == "ls_cancel"

    # A phone answer that lands after Circle is dropped.
    rig.flow.start("id_confirm")
    call = rig.sponsors.calls[-1]
    rig.flow.press("circle")
    assert rig.state == "id_cancel"
    rig.sponsors.cross(call)
    rig.wait(500)
    assert rig.state == "id_cancel"


def test_late_approval_after_circle_goes_to_ls_late(tmp_path):
    rig = Rig(tmp_path / "kept")
    rig.flow.start("ls_approve")
    call = rig.sponsors.calls[-1]
    rig.flow.press("circle")
    assert rig.state == "ls_cancel"
    rig.wait(500)
    assert rig.state == "ls_cancel"
    rig.sponsors.cross(call)  # the phone approves anyway
    rig.wait(16)
    assert rig.state == "ls_late"

    # A kept call that fails instead is ignored.
    rig = Rig(tmp_path / "denied")
    rig.flow.start("ls_approve")
    call = rig.sponsors.calls[-1]
    rig.flow.press("circle")
    rig.sponsors.force(call, rig.sponsors.outcomes("approve")[0])
    rig.wait(16)
    assert rig.state == "ls_cancel"

    # Only an approve call is listened to: a scan answered after Circle on ls_scan is not one.
    rig = Rig(tmp_path / "scan")
    rig.flow.start("ls_scan")
    call = rig.sponsors.calls[-1]
    rig.flow.press("circle")
    assert rig.state == "ls_cancel"
    rig.sponsors.cross(call)
    rig.wait(500)
    assert rig.state == "ls_cancel"

    # In mock mode the same thing is one Square pick away.
    rig = Rig(tmp_path / "square")
    rig.flow.start("ls_approve")
    rig.flow.press("circle")
    rig.flow.press("square")
    assert rig.flow.outcomes == [("Phone approves anyway", "ls_late")]
    rig.flow.press("cross")
    assert rig.state == "ls_late"


def test_a_silent_payment_times_out_into_buy_down(tmp_path):
    rig = Rig(tmp_path, sponsors=ManualPaySponsors)
    rig.flow.start("board")
    rig.flow.press("cross")
    rig.flow.press("cross")
    rig.wait(1400)
    assert rig.state == "buy_pay"
    rig.wait(7999)
    assert rig.state == "buy_pay"
    rig.wait(1)
    assert rig.state == "buy_down"
    assert rig.flow.ledger.spent == 0
    assert rig.flow.ledger.purchases == {}


def _force(rig, pick_late):
    rig.flow.press("square")
    rows = rig.flow.outcomes
    index = next(i for i, o in enumerate(rig.sponsors.outcomes("pay")) if o.late == pick_late)
    assert rows[index][1] == "buy_down"
    rig.flow.pick(index)
    rig.wait(16)


def test_a_late_payment_is_charged_once(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("buy_check")
    rig.wait(1400)
    _force(rig, pick_late=True)
    # Ruling 10b: a late receipt never leaves "nothing was paid" on screen.
    assert rig.state == "buy_late"
    assert rig.flow.line == ("Hedera was slow, but your 0.10 USDC for RIA's ghost did land. It is "
                             "yours. Cross to load it.")
    assert rig.flow.ledger.spent == GHOST_PRICE
    receipt = rig.flow.ledger.purchases[f"{GAME}:RIA"]["receipt"]
    assert receipt.startswith("mock-")
    assert rig.flow.ctx["receipt"] == receipt
    assert rig.saved().spent == GHOST_PRICE

    # Circle leaves with the ghost owned; coming back loads it with no second charge.
    rig.flow.press("circle")
    assert rig.state == "hub"
    assert owns(rig.flow.ledger, GAME, "RIA")
    rig.flow.pick(0)
    rig.flow.press("cross")
    rig.flow.press("cross")
    assert rig.state == "buy_load"

    # A second late report for the same ghost charges nothing and keeps the first receipt.
    rig.flow.start("buy_pay")
    _force(rig, pick_late=True)
    assert rig.state == "buy_late"
    assert rig.flow.ledger.spent == GHOST_PRICE
    assert rig.flow.ledger.purchases[f"{GAME}:RIA"]["receipt"] == receipt
    assert rig.flow.ctx["receipt"] == receipt
    rig.flow.press("cross")
    assert rig.state == "buy_load"
    assert rig.flow.ledger.spent == GHOST_PRICE

    # The plain "down" row carries no receipt and charges nothing.
    rig = Rig(tmp_path / "plain")
    rig.flow.start("buy_pay")
    _force(rig, pick_late=False)
    assert rig.state == "buy_down"
    assert rig.flow.ledger.spent == 0
    rig.wait(500)
    assert rig.state == "buy_down"  # the kept call's plain failure is not a late payment


def test_a_kept_pay_call_answering_late_on_buy_down_goes_to_buy_late(tmp_path):
    for n, answer in enumerate((Result(ok=True, data={"receipt": "late-1"}),
                                Result(ok=False, failure="buy_down", data={"late_receipt": "late-1"}))):
        rig = Rig(tmp_path / str(n), sponsors=ManualPaySponsors)
        rig.flow.start("buy_check")
        rig.wait(1400)
        call = rig.sponsors.calls[-1]
        rig.wait(8000)
        assert rig.state == "buy_down"
        assert rig.flow.ledger.spent == 0
        rig.wait(3000)
        call.result = answer
        rig.wait(16)
        assert rig.state == "buy_late", answer
        assert rig.flow.ledger.spent == GHOST_PRICE
        assert rig.flow.ledger.purchases[f"{GAME}:RIA"]["receipt"] == "late-1"
        rig.wait(1000)
        assert rig.flow.ledger.spent == GHOST_PRICE
        rig.flow.press("cross")
        assert rig.state == "buy_load"
        assert rig.flow.ledger.spent == GHOST_PRICE

    # Once the player has left buy_down, a late answer is no longer listened to.
    rig = Rig(tmp_path / "left", sponsors=ManualPaySponsors)
    rig.flow.start("buy_pay")
    call = rig.sponsors.calls[-1]
    rig.wait(8000)
    rig.flow.press("cross")
    assert rig.state == "board"
    call.result = Result(ok=True, data={"receipt": "late-2"})
    rig.wait(500)
    assert rig.state == "board"
    assert rig.flow.ledger.spent == 0


def test_a_late_receipt_past_the_budget_is_still_recorded(tmp_path):
    rig = Rig(tmp_path, ledger=Ledger(book="ANY-7QZ", spent=95, spent_day=TODAY))
    rig.flow.start("buy_pay")
    _force(rig, pick_late=True)
    assert rig.state == "buy_late"
    assert rig.flow.ledger.spent == 95 + GHOST_PRICE
    assert owns(rig.flow.ledger, GAME, "RIA")
    assert rig.saved().spent == 95 + GHOST_PRICE
    assert rig.flow.ctx["budget_left"] == "0.00"


class HederaRealSponsors(ManualPaySponsors):
    """Hedera real (its pay answers only when the test says, with a real transaction id); the rest the mock's."""

    def mocked(self, service):
        return service != "third"


TX = "0.0.9185802@1762412349.000000123"


def _what(flow):
    return {flow.fill(label): flow.fill(value) for label, value in flow.state.card["what"]}


def test_the_receipt_row_says_mock_receipt_until_hedera_is_real(tmp_path):
    rig = Rig(tmp_path)                                                  # all mocked
    rig.flow.start("buy_check")
    rig.wait(1400 + 2000 + 1200)
    assert rig.state == "buy_done" and rig.flow.ledger.purchases[f"{GAME}:RIA"]["receipt"].startswith("mock-")
    assert _what(rig.flow)["Receipt"] == rig.flow.ctx["receipt_text"] == "mock receipt"
    rig = Rig(tmp_path / "real", sponsors=HederaRealSponsors)
    rig.flow.start("buy_check")
    rig.wait(1400)
    rig.sponsors.calls[-1].result = Result(ok=True, data={"receipt": TX})
    rig.wait(16)
    assert rig.state == "buy_load"
    rig.wait(1200)
    assert rig.state == "buy_done"
    assert _what(rig.flow)["Receipt"] == "0.0.9185802@1762412349"     # the payment's own id, its nanoseconds cut


def test_a_late_payments_receipt_row_is_its_transaction_id(tmp_path):
    rig = Rig(tmp_path, sponsors=HederaRealSponsors)
    rig.flow.start("buy_pay")
    call = rig.sponsors.calls[-1]
    rig.wait(8000)
    assert rig.state == "buy_down"
    call.result = Result(ok=True, data={"receipt": TX})
    rig.wait(16)
    assert rig.state == "buy_late" and _what(rig.flow)["Receipt"] == "0.0.9185802@1762412349"


def test_a_ghost_bought_before_shows_its_own_receipt(tmp_path):
    for receipt, shown in ((TX, "0.0.9185802@1762412349"), ("0.0.7162784@1762412000.5", "0.0.7162784@1762412000"),
                           ("odd-receipt", "odd-receipt")):
        bought = {f"{GAME}:RIA": {"price": GHOST_PRICE, "receipt": receipt, "at": 0}}
        rig = Rig(tmp_path / shown, sponsors=HederaRealSponsors, ledger=Ledger(book="ANY-7QZ", purchases=bought))
        rig.flow.start("target")
        rig.flow.press("cross")
        assert rig.state == "buy_load"                                  # owned: no check, no charge
        rig.wait(1200)
        assert rig.state == "buy_done" and _what(rig.flow)["Receipt"] == shown, receipt


def test_square_picks_survive_the_status_pills(tmp_path):
    # Ruling 11: the view reads status() every frame; that must never resolve the call under an
    # open outcome list, or a pick made after the mock's delay would be ignored.
    cases = (("buy_pay", "Hedera down", "buy_down"), ("buy_check", "Price changed", "buy_changed"),
             ("ls_record", "Hedera slow", "ls_record_fail"))
    for name, label, target in cases:
        rig = Rig(tmp_path / name)
        rig.flow.start(name)
        rig.wait(200)
        rig.flow.press("square")
        rig.wait(2500, frame=16)
        index = [row_label for row_label, _state in rig.flow.outcomes].index(label)
        rig.flow.pick(index)
        rig.wait(16)
        assert rig.state == target, name
        rig.wait(500)
        assert rig.state == target, name
        assert rig.flow.ledger.spent == 0


def _owned_ledger():
    return Ledger(book="ANY-7QZ", spent=GHOST_PRICE, spent_day=TODAY,
                  purchases={f"{GAME}:RIA": {"price": GHOST_PRICE, "receipt": "mock-1", "at": 0}})


def test_owned_ghost_is_not_charged_again(tmp_path):
    rig = Rig(tmp_path / "check", ledger=_owned_ledger())
    rig.flow.start("board")
    rig.flow.press("cross")
    rig.flow.press("cross")
    assert rig.state == "buy_load"  # no listing check, no payment
    assert rig.sponsors.steps() == ["load_ghost"]
    rig.wait(1200)
    assert rig.state == "buy_done"
    assert rig.flow.ledger.spent == GHOST_PRICE

    # A payment that does come back ok for an owned ghost still charges nothing.
    rig = Rig(tmp_path / "pay", ledger=_owned_ledger())
    rig.flow.start("buy_pay")
    rig.wait(2000)
    assert rig.state == "buy_load"
    assert rig.flow.ledger.spent == GHOST_PRICE


def test_no_book_means_need_book_first(tmp_path):
    rig = Rig(tmp_path, book=None)
    rig.flow.start("board")
    assert rig.state == "board"  # the board can be viewed without a book
    rig.flow.press("cross")
    rig.flow.press("cross")
    assert rig.state == "need_book"
    assert rig.sponsors.calls == []
    rig.flow.press("cross")
    assert rig.state == "s_boot"

    rig.flow.start("list")
    assert rig.state == "need_book"
    rig.flow.start("hub")
    rig.flow.pick(2)
    assert rig.state == "need_book"


def test_over_budget_goes_to_buy_budget(tmp_path):
    rig = Rig(tmp_path, ledger=Ledger(book="ANY-7QZ", spent=95, spent_day=TODAY))
    rig.flow.start("board")
    rig.flow.press("cross")
    rig.flow.press("cross")
    assert rig.state == "buy_budget"
    assert rig.sponsors.calls == []
    assert rig.flow.ledger.spent == 95

    # Yesterday's spending does not count today.
    rig = Rig(tmp_path / "yesterday", ledger=Ledger(book="ANY-7QZ", spent=100, spent_day="2026-11-05"))
    rig.flow.start("target")
    rig.flow.press("cross")
    assert rig.state == "buy_check"


def test_lines_are_filled_and_carry_no_braces(tmp_path):
    # Stronger than "every state these tests reach": every state in the table, with a full
    # context and with an empty one (a missing placeholder fills as "", never a brace).
    for n, make_ctx in enumerate((_ctx, dict)):
        for name in STATES:
            rig = Rig(tmp_path / f"{n}-{name}", ctx=make_ctx())
            rig.flow.start(name)
            line = rig.flow.line
            assert "{" not in line and "}" not in line, (name, line)
            for text in copy_texts(rig.flow.state):
                filled = rig.flow.fill(text)
                assert "{" not in filled and "}" not in filled, (name, text, filled)
    rig = Rig(tmp_path / "emphasis")
    rig.flow.start("board")
    assert rig.flow.line == ("Here is the *Marine Drive GP* board. You are 7th. *RIA* is 1.6 s "
                             "ahead. Beat that run and 3rd is yours.")


# ---- one per numbered ruling that changes behaviour ----------------------------------------

def test_r1_deadlines_use_the_calls_own_clock(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("id_scan")
    rig.clock.ms += 299999
    rig.flow.tick(0)
    assert rig.state == "id_scan"
    rig.clock.ms += 1
    rig.flow.tick(0)  # no frame time at all: the call's elapsed_ms alone decides
    assert rig.state == "id_expired"

    rig.flow.start("ls_approve")
    rig.wait(1199900, frame=100000)
    assert rig.state == "ls_approve"
    rig.wait(100)
    assert rig.state == "ls_expired"


def test_r2_the_engine_fills_its_own_context(tmp_path):
    rig = Rig(tmp_path)
    ctx = rig.flow.ctx
    assert ctx["price"] == "0.10"
    assert ctx["budget_left"] == "1.00"
    assert ctx["book"] == "ANY-7QZ"
    assert ctx["listing_days"] == LISTING_DAYS

    rig.flow.start("id_scan")
    code = rig.sponsors.calls[-1].info["code"]
    assert ctx["code"] == code
    rig.flow.press("cross")
    rig.wait(16)
    assert rig.state == "id_confirm"
    assert rig.flow.fill(rig.flow.state.card["rows"][2]) == f"Code *{code}*"

    rig.flow.start("buy_pay")
    rig.wait(2000)
    assert ctx["receipt"] == rig.flow.ledger.purchases[f"{GAME}:RIA"]["receipt"]
    assert ctx["budget_left"] == "0.90"

    rig.flow.start("ls_approve")
    rig.flow.press("cross")
    rig.wait(16)
    assert rig.state == "ls_record"
    assert ctx["jti"] == rig.sponsors.calls[-2].poll().data["jti"]

    assert rig.flow.fill("{world} pays {nobody_set_this}.") == "World pays ."
    ctx["target"] = None
    assert rig.flow.fill("[{target}]") == "[]"


def test_r3_board_entry_follows_the_board_case(tmp_path):
    expected = {"no_board": "no_board", "nobody_ahead": "nobody_ahead", "no_best": "board_new",
                "ok": "board", None: "board"}
    for case, state in expected.items():
        rig = Rig(tmp_path / str(case), board_case=case)
        rig.flow.start("board")
        assert rig.state == state, case
    # The same routing applies to every edge that leads to the board.
    rig = Rig(tmp_path / "edge", board_case="no_best")
    rig.flow.start("target")
    rig.flow.press("circle")
    assert rig.state == "board_new"


def test_r3_list_entry_needs_a_run_then_a_book(tmp_path):
    rig = Rig(tmp_path / "norun", book=None, best_frames=None)
    rig.flow.start("list")
    assert rig.state == "no_run"
    rig = Rig(tmp_path / "nobook", book=None)
    rig.flow.start("list")
    assert rig.state == "need_book"
    rig = Rig(tmp_path / "ok")
    rig.flow.start("list")
    assert rig.state == "ls_offer"
    rig.flow.start("book")
    assert rig.state == "s_boot"


def test_r3_hub_rows_and_cursor(tmp_path):
    rig = Rig(tmp_path / "mock")
    rig.flow.start("hub")
    for _ in range(9):
        rig.flow.press("down")
    assert rig.flow.hub_index == 4
    rig.flow.press("cross")
    assert rig.state == "start_over"
    rig.flow.start("hub")
    for _ in range(9):
        rig.flow.press("up")
    assert rig.flow.hub_index == 0
    rig.flow.press("cross")
    assert rig.state == "board"

    rows = {0: "board", 1: "ls_offer", 2: "book_view", 3: "listings_view", 4: "start_over"}
    for i, state in rows.items():
        rig.flow.start("hub")
        rig.flow.pick(i)
        assert rig.state == state, i
    rig.flow.start("hub")
    assert rig.flow.pick(5) is None
    assert rig.state == "hub"

    # Row 4 exists only in mock mode.
    rig = Rig(tmp_path / "real", sponsors=RealSponsors)
    rig.flow.start("hub")
    for _ in range(9):
        rig.flow.press("down")
    assert rig.flow.hub_index == 3
    rig.flow.pick(4)
    assert rig.state == "hub"


def test_r4_record_book_effects_are_saved(tmp_path):
    rig = Rig(tmp_path / "new", book=None, ledger=Ledger(credential="old"))
    rig.flow.start("id_verifying")
    rig.wait(1700)
    assert rig.state == "id_done"
    book = rig.flow.ledger.book
    assert book.startswith("ANY-")
    assert rig.flow.ledger.credential == "Selfie Check"
    assert rig.saved().book == book and rig.saved().credential == "Selfie Check"
    assert rig.flow.ctx["book"] == book

    # A book that already exists is kept.
    rig = Rig(tmp_path / "keep")
    rig.flow.start("id_verifying")
    rig.wait(1700)
    assert rig.flow.ledger.book == "ANY-7QZ"

    rig = Rig(tmp_path / "signed", book=None)
    rig.flow.start("id_dup")
    rig.flow.press("cross")
    assert rig.state == "id_signed"
    assert rig.flow.ledger.book == "ANY-2KD"
    assert rig.saved().book == "ANY-2KD"


def test_r4_a_listing_is_recorded_when_listed(tmp_path):
    rig = Rig(tmp_path, run_frames=6100)
    rig.flow.start("ls_arkiv")
    rig.wait(1400)
    assert rig.state == "ls_done"
    (listing,) = rig.flow.ledger.listings
    assert listing["game"] == GAME
    assert listing["frames"] == 6100
    assert listing["price"] == GHOST_PRICE
    assert listing["sold"] == 0
    assert isinstance(listing["at"], float)
    assert rig.saved().listings == rig.flow.ledger.listings


def test_r4_start_over_clears_the_ledger_and_returns_to_the_hub(tmp_path):
    rig = Rig(tmp_path, ledger=_owned_ledger())
    save(rig.path, rig.flow.ledger)
    rig.flow.start("hub")
    rig.flow.pick(4)
    assert rig.state == "start_over"
    rig.flow.press("circle")
    assert rig.state == "hub"
    assert rig.flow.ledger.book == "ANY-7QZ"
    rig.flow.pick(4)
    rig.flow.press("cross")
    assert rig.state == "hub"
    assert rig.flow.ledger == Ledger()
    assert rig.flow.ctx["book"] == ""
    assert not os.path.exists(rig.path)


def test_r5_racing_returns_a_race_target_and_remembers_it(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("buy_done")
    assert rig.flow.press("cross") == RaceTarget(GAME, "RIA")
    assert rig.flow.ledger.targets == {GAME: "RIA"}
    assert rig.saved().targets == {GAME: "RIA"}

    rig.flow.finish_race("lost", 6400)
    assert rig.state == "race_lost"
    assert rig.flow.ctx["run_frames"] == 6400
    assert rig.flow.ctx["run_time"] == "1:46.67"
    assert rig.flow.press("cross") == RaceTarget(GAME, "RIA")  # racing again is free
    assert rig.flow.ledger.spent == 0

    for result, state in (("beat", "result"), ("unfinished", "race_unfinished"),
                          ("unverified", "race_unverified")):
        rig.flow.finish_race(result, 6000 if result == "beat" else None)
        assert rig.state == state
    assert rig.flow.ctx["run_time"] == ""
    rig.flow.finish_race("unfinished", None)
    assert rig.flow.line == "No time this run. RIA's ghost is still yours. Cross to race again."


def _no_empty_names(line):
    return "  " not in line and not line.startswith("'s") and " 's" not in line


def test_r5_racing_your_own_best_has_its_own_results(tmp_path):
    # Ruling 12: no seller means no "{target}" to name, so the results are about your best.
    rig = Rig(tmp_path, board_case="nobody_ahead", target=None)
    rig.flow.start("board")
    assert rig.state == "nobody_ahead"
    assert rig.flow.press("cross") == RaceTarget(GAME, None)
    assert rig.flow.ledger.targets == {}

    rig.flow.finish_race("beat", 6000)
    assert rig.state == "own_result"
    assert rig.flow.line == "*1:40.00!* A new best. Cross to list it so others can race you."
    rig.flow.press("cross")
    assert rig.state == "ls_offer"

    rig.flow.finish_race("lost", 6500)
    assert rig.state == "own_again"
    assert rig.flow.line == "*1:48.33*. Your best stands. Cross to race it again."
    rig.flow.ctx["target"] = "RIA"  # whatever the app puts here, a re-race keeps its own seller
    assert rig.flow.press("cross") == RaceTarget(GAME, None)

    expected = {"unfinished": ("race_unfinished", "No time this run. Cross to race again."),
                "unverified": ("race_unverified", None)}
    for result, (state, line) in expected.items():
        rig.flow.finish_race(result, None)
        assert rig.state == state
        assert line is None or rig.flow.line == line
    for result in ("beat", "lost", "unfinished", "unverified"):
        rig.flow.finish_race(result, 6100)
        assert _no_empty_names(rig.flow.line), (result, rig.flow.line)


def test_m2_the_seller_is_fixed_when_the_purchase_starts(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("target")
    rig.flow.press("cross")
    assert rig.state == "buy_check"
    rig.flow.ctx["target"] = "MEERA"  # the app's context changing mid-purchase changes nothing
    rig.wait(1400)
    rig.wait(2000)
    assert rig.state == "buy_load"
    assert list(rig.flow.ledger.purchases) == [f"{GAME}:RIA"]
    rig.wait(1200)
    assert rig.flow.press("cross") == RaceTarget(GAME, "RIA")
    assert rig.flow.ledger.targets == {GAME: "RIA"}


def test_r6_home_closes_the_handler(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("hub")
    assert rig.flow.press("circle") == CloseHandler()
    assert rig.state == "home"
    rig.flow.start("ls_approve")
    rig.flow.press("circle")
    assert rig.flow.press("circle") == CloseHandler()


def test_m5_start_returns_the_command_its_entry_produced(tmp_path):
    rig = Rig(tmp_path)
    assert rig.flow.start("hub") is None
    assert rig.flow.start("home") == CloseHandler()
    assert rig.flow.start("racing") == RaceTarget(GAME, "RIA")


def test_r8_square_list_moves_picks_and_closes(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("id_confirm")
    rig.flow.press("square")
    assert rig.flow.outcomes_open
    assert [label for label, _state in rig.flow.outcomes] == [
        "Reject", "Let it expire", "No Selfie Check", "Same person again", "Another person's console", "World down"]
    rig.flow.press("up")
    assert rig.flow.outcome_index == 0
    for _ in range(9):
        rig.flow.press("down")
    assert rig.flow.outcome_index == 5
    rig.flow.press("up")
    rig.flow.press("circle")
    assert not rig.flow.outcomes_open
    assert rig.state == "id_confirm"  # Circle closed the list, it did not back out
    rig.flow.press("square")
    assert rig.flow.outcome_index == 0
    rig.flow.press("down")
    rig.flow.press("cross")
    rig.wait(16)
    assert rig.state == "id_expired"

    # No outcome list where a step has none, and none at all outside mock mode.
    rig.flow.start("id_scan")
    rig.flow.press("square")
    assert not rig.flow.outcomes_open
    rig = Rig(tmp_path / "real", sponsors=RealSponsors)
    rig.flow.start("buy_pay")
    rig.flow.press("square")
    assert not rig.flow.outcomes_open


def test_r8_nothing_else_happens_while_the_list_is_open(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("buy_pay")
    rig.flow.press("square")  # a step in flight can still be broken on purpose in mock mode
    assert rig.flow.outcomes_open
    rig.wait(9000)  # past the mock delay and the deadline: nothing lands while the list is open
    assert rig.state == "buy_pay"
    assert rig.flow.ledger.spent == 0
    rig.flow.press("circle")
    rig.wait(16)
    assert rig.state == "buy_load"  # the payment had landed; it wins over the deadline

    # A state-level row (no call to force) lands at once.
    rig.flow.start("ls_cancel")
    rig.flow.press("square")
    assert rig.flow.press("cross") is None
    assert rig.state == "ls_late"


def test_r9_in_flight_is_only_a_running_non_phone_call(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("buy_check")
    assert rig.flow.in_flight
    rig.wait(1400)
    assert rig.state == "buy_pay" and rig.flow.in_flight
    rig.flow.start("ls_scan")
    assert not rig.flow.in_flight
    rig.flow.start("board")
    assert not rig.flow.in_flight


def test_r11_ms_in_state_counts_up_and_resets_on_entry(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("buy_check")
    assert rig.flow.ms_in_state == 0
    rig.wait(1000)
    assert rig.flow.ms_in_state == 1000
    rig.wait(400)
    assert rig.state == "buy_pay"
    assert rig.flow.ms_in_state == 0
    rig.wait(300)
    assert rig.flow.ms_in_state == 300


def test_r12_ls_record_shows_the_approval_and_listing_days(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("ls_approve")
    rig.flow.press("cross")
    rig.wait(16)
    jti = rig.flow.ctx["jti"]
    rows = [rig.flow.fill(row) for row in rig.flow.state.card["rows"]]
    assert rows == [f"Approval *{jti}* used once", f"Listing for {LISTING_DAYS} days"]


def test_r12_timeout_fail_states_carry_a_step_strip():
    def strip(name):
        state = STATES[name]
        return state.steps, state.at, state.fail, state.halt

    buy = STATES["buy_pay"].steps
    ls = STATES["ls_record"].steps
    assert strip("buy_check_fail") == (buy, 0, True, False)
    assert strip("buy_load_fail") == (buy, 2, True, False)
    assert strip("ls_publish_fail") == (ls, 3, False, True)


# ---- the final review's fixes (Rulings 17 and 18) ------------------------------------------

def _make_a_book(rig):
    """From s_boot, Cross through World App's two phone steps and the check, to id_done."""
    assert rig.state == "s_boot"
    rig.flow.press("cross")
    rig.flow.press("cross")
    rig.wait(16)
    rig.flow.press("cross")
    rig.wait(16)
    rig.wait(1700)
    assert rig.state == "id_done" and rig.flow.ledger.book


def test_the_record_book_flow_returns_to_what_needed_it(tmp_path):
    # List: "List my best run" needed a book; once it is made, Cross goes back to the listing.
    rig = Rig(tmp_path / "list", book=None)
    rig.flow.start("hub")
    rig.flow.pick(1)
    assert rig.state == "need_book"
    rig.flow.press("cross")
    _make_a_book(rig)
    rig.flow.press("cross")
    assert rig.state == "ls_offer"

    # Buy: the purchase carries on with its listing check.
    rig = Rig(tmp_path / "buy", book=None)
    rig.flow.start("board")
    rig.flow.press("cross")
    rig.flow.press("cross")
    assert rig.state == "need_book"
    rig.flow.press("cross")
    _make_a_book(rig)
    rig.flow.press("cross")
    assert rig.state == "buy_check" and rig.sponsors.steps()[-1] == "check_listing"
    rig.wait(1400)
    assert rig.state == "buy_pay"

    # The first-launch offer and the hub's "My record book" row: back Home.
    rig = Rig(tmp_path / "offer", book=None)
    rig.flow.start("book")
    _make_a_book(rig)
    assert rig.flow.press("cross") == CloseHandler()
    assert rig.state == "home"
    rig = Rig(tmp_path / "row", book=None)
    rig.flow.start("hub")
    rig.flow.pick(2)
    rig.flow.press("cross")
    _make_a_book(rig)
    assert rig.flow.press("cross") == CloseHandler()

    # Signing in to the book a World ID already has returns the same way.
    rig = Rig(tmp_path / "signed", book=None)
    rig.flow.start("hub")
    rig.flow.pick(1)
    rig.flow.press("cross")
    rig.flow.press("cross")
    rig.flow.press("cross")
    rig.wait(16)
    assert rig.state == "id_confirm"
    rig.flow.press("square")
    rig.flow.pick([label for label, _state in rig.flow.outcomes].index("Same person again"))
    rig.wait(16)
    rig.flow.press("cross")
    assert rig.state == "id_signed"
    rig.flow.press("cross")
    assert rig.state == "ls_offer"

    # Nothing remembered (opened straight on the screen): the hub.
    rig = Rig(tmp_path / "none")
    rig.flow.start("id_done")
    rig.flow.press("cross")
    assert rig.state == "hub"


def test_backing_out_of_a_phone_step_leaves_no_service_busy(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("id_scan")
    rig.flow.press("circle")
    assert rig.state == "id_cancel"
    assert rig.sponsors.status()["world"] == "ok"
    rig.flow.start("ls_approve")
    rig.flow.press("circle")
    assert rig.state == "ls_cancel"  # its approve call is kept for a late answer
    rig.wait(500)
    assert rig.sponsors.status()["world"] == "ok"
    rig.flow.start("buy_pay")
    rig.wait(1000)
    assert rig.sponsors.status()["third"] == "busy"


def test_busy_is_a_state_with_a_call_or_a_kept_call(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("hub")
    assert not rig.flow.busy
    rig.flow.start("buy_pay")
    assert rig.flow.busy
    rig.wait(2000)
    assert rig.state == "buy_load" and rig.flow.busy
    for name in ("id_scan", "id_confirm", "ls_scan", "ls_approve"):
        rig.flow.start(name)  # a phone step: not in flight, but a visitor may be in World App
        assert not rig.flow.in_flight and rig.flow.busy, name
    rig.flow.press("circle")
    assert rig.state == "ls_cancel" and rig.flow.busy
    rig.flow.press("circle")
    assert not rig.flow.busy


def test_a_hub_with_no_arcade_game_has_only_the_book_rows(tmp_path):
    rig = Rig(tmp_path / "mock", arcade=False)
    rig.flow.start("hub")
    assert rig.flow.hub_count == 3
    assert rig.flow.hub_rows == ("My record book", "My listings", "Start over (mock)")
    for _ in range(9):
        rig.flow.press("down")
    assert rig.flow.hub_index == 2
    rows = {0: "book_view", 1: "listings_view", 2: "start_over"}
    for i, state in rows.items():
        rig.flow.start("hub")
        rig.flow.pick(i)
        assert rig.state == state, i
    rig.flow.start("hub")
    assert rig.flow.pick(3) is None and rig.state == "hub"

    rig = Rig(tmp_path / "real", sponsors=RealSponsors, arcade=False)
    rig.flow.start("hub")
    assert rig.flow.hub_rows == ("My record book", "My listings")
    rig = Rig(tmp_path / "arcade")
    assert rig.flow.arcade and rig.flow.hub_count == 5
    assert rig.flow.hub_rows == STATES["hub"].card["rows"]


# ---- what a real board needs from the flow (the Arkiv adapter) ------------------------------------------------------

def test_a_changed_listing_names_its_new_price(tmp_path):
    """The mock's "Price changed" makes its price up; a real board says what the listing says now."""
    rig = Rig(tmp_path / "mock")
    rig.flow.start("buy_check")
    rig.flow.press("square")
    rig.flow.pick([label for label, _ in rig.flow.outcomes].index("Price changed"))
    rig.wait(16)
    assert rig.state == "buy_changed" and rig.flow.ctx["now_price"] == "0.50 USDC"
    assert "Price was 0.10, now *0.50 USDC*" == rig.flow.fill(rig.flow.state.card["rows"][0])
    for now in ("gone", "0.25 USDC"):
        class Changed(SpySponsors):
            def begin(self, step, payload, now=now):
                call = super().begin(step, payload)
                if step == "check_listing":
                    call._result = Result(ok=False, failure="buy_changed", data={"now_price": now})
                return call
        rig = Rig(tmp_path / now, sponsors=Changed)
        rig.flow.start("buy_check")
        rig.wait(16)
        assert rig.state == "buy_changed" and rig.flow.ctx["now_price"] == now
        assert now in rig.flow.line and rig.flow.ledger.spent == 0


def test_the_payload_names_a_real_target_and_the_run_to_list(tmp_path):
    run, listing, log_h = "0x" + "ab" * 32, "0x" + "cd" * 32, "ef" * 32
    rig = Rig(tmp_path, ledger=_owned_ledger(), arcade_id="MDGP", target_run=run, target_listing=listing,
              target_log_h=log_h, target_frames=6070, run_frames=None, best_frames=6290)
    rig.flow.start("buy_check")                                   # RIA's ghost is owned: straight to the load
    payload = rig.sponsors.calls[-1].payload
    assert rig.sponsors.steps() == ["load_ghost"]
    target = (payload["target_run"], payload["target_listing"], payload["target_log_h"], payload["target_frames"])
    assert target == (run, listing, log_h, 6070)
    assert (payload["arcade_id"], payload["frames"], payload["receipt"]) == ("MDGP", 6290, "mock-1")
    rig.flow.ctx["run_frames"] = 6000                              # a run just raced is what a listing is about
    assert rig.flow._payload()["frames"] == 6000


def test_a_loaded_real_ghost_is_kept_for_the_race(tmp_path):
    class Real(SpySponsors):
        def begin(self, step, payload):
            call = super().begin(step, payload)
            if step == "load_ghost":
                call._result = Result(ok=True, data={"ghost_log": "/runs/ghosts/ef.acl"})
            return call
    rig = Rig(tmp_path, sponsors=Real, ledger=_owned_ledger())
    rig.flow.start("buy_load")
    rig.wait(16)
    assert rig.state == "buy_done" and rig.flow.ctx["ghost_log"] == "/runs/ghosts/ef.acl"


def test_a_real_listing_keeps_its_rows_and_the_mocks_names_none(tmp_path):
    rows = {"run": "0x" + "12" * 32, "listing": "0x" + "34" * 32, "tx": "0x" + "56" * 32}

    class Real(SpySponsors):
        def begin(self, step, payload):
            call = super().begin(step, payload)
            if step == "publish":
                call._result = Result(ok=True, data=rows)
            return call
    rig = Rig(tmp_path / "real", sponsors=Real, run_frames=6100)
    rig.flow.start("ls_arkiv")
    rig.wait(16)
    (entry,) = rig.saved().listings
    assert (entry["run"], entry["listing"], entry["frames"]) == (rows["run"], rows["listing"], 6100)
    assert "tx" not in entry
    rig = Rig(tmp_path / "mock", run_frames=6100)
    rig.flow.start("ls_arkiv")
    rig.wait(1400)
    (entry,) = rig.saved().listings
    assert "run" not in entry and "listing" not in entry


# ---- PB's scout, the auto buy, Humans only, chain ids on screen ----------------------------------------------------

LISTING_KEY, RUN_KEY, LOG_H = "0x" + "23bf" * 15 + "af44", "0x" + "12ab" * 16, "ab" * 32
HOUSE = "0.0.7700001"
PICK = {"scout": "s-1a2b3c4d", "seller": "BOT-A2", "label": "BOT-A2", "book": None, "listing": LISTING_KEY,
        "run": RUN_KEY, "log_h": LOG_H, "frames": 6236, "time": "1:43.93", "it": (2248, 1994, 1994),
        "you": (2140, 2165, 2109), "you_frames": 6414, "you_time": "1:46.90", "lap": 2,
        "reason": "You lose 2.85 s in lap 2: BOT-A2 runs it in 33.23 s, you in 36.08 s.", "by": "model",
        "model": "openai/gpt-oss-120b", "note": None, "pay_to": HOUSE, "human": False}


class ScoutSponsors(SpySponsors):
    """The mock with a scout: its "scout" call answers what `scout_answer` says (None: never)."""
    scouts = True
    scout_answer = Result(ok=True, data=PICK)

    def begin(self, step, payload):
        if step != "scout":
            return super().begin(step, payload)
        call = _ManualCall(self._clock_ms, step)
        call.payload = payload
        call.result = type(self).scout_answer
        self.calls.append(call)
        return call


def _scout_rig(tmp_path, answer=None, **over):
    class Answer(ScoutSponsors):
        scout_answer = answer if answer is not None else Result(ok=True, data=PICK)
    ctx = dict(best_frames=6414, arcade_id="MDGP", target="ANY-9MX", target_time="1:45.80", target_frames=6348,
               target_run="0x" + "77" * 32, target_listing="0x" + "88" * 32, target_log_h="cd" * 32,
               target_pay_to="0.0.6009900", gap="1.1 s", new_rank="2nd")
    ctx.update(over)
    return Rig(tmp_path, book="ANY-6PS", sponsors=Answer, **ctx)


def test_cross_on_the_board_scouts_only_with_a_scout_a_best_and_a_book(tmp_path):
    rig = _scout_rig(tmp_path / "scout")
    rig.flow.start("board")
    rig.flow.press("cross")
    assert rig.state == "scout" and rig.sponsors.steps()[-1] == "scout"
    payload = rig.sponsors.calls[-1].payload
    assert (payload["book"], payload["arcade_id"], payload["frames"], payload["price"]) == ("ANY-6PS", "MDGP", 6414,
                                                                                             GHOST_PRICE)
    for name, rig in (("no scout", Rig(tmp_path / "none", book="ANY-6PS")),
                      ("no best", _scout_rig(tmp_path / "nobest", best_frames=None, board_case="no_best")),
                      ("no book", Rig(tmp_path / "nobook", book=None, sponsors=ScoutSponsors))):
        rig.flow.start("board")
        rig.flow.press("cross")
        assert rig.state == "target", name
    rig = _scout_rig(tmp_path / "direct")                          # only from the board: never from "look again"
    rig.flow.start("buy_changed")
    rig.flow.press("cross")
    assert rig.state == "target"


def test_the_scouts_pick_becomes_the_target(tmp_path):
    rig = _scout_rig(tmp_path, board_rows=_rows_with("BOT-A2", 2))
    rig.flow.start("board")
    rig.flow.press("cross")
    rig.wait(16)
    assert rig.state == "scout_pick"
    ctx = rig.flow.ctx
    assert (ctx["target"], ctx["target_time"], ctx["target_frames"], ctx["target_run"], ctx["target_listing"],
            ctx["target_log_h"], ctx["target_pay_to"]) == ("BOT-A2", "1:43.93", 6236, RUN_KEY, LISTING_KEY, LOG_H,
                                                           HOUSE)
    assert (ctx["scout_id"], ctx["scout_reason"], ctx["scout_model"], ctx["scout_note"]) == (
        "s-1a2b3c4d", PICK["reason"], "openai/gpt-oss-120b", None)
    assert (ctx["you_laps"], ctx["it_laps"], ctx["scout_lap"]) == ((2140, 2165, 2109), (2248, 1994, 1994), 2)
    assert ctx["scout_by"] == "Picked by openai/gpt-oss-120b on Groq"
    assert (ctx["gap"], ctx["new_rank"], ctx["you_time"]) == ("3.0 s", "2nd", "1:46.90")
    assert rig.flow._seller == "BOT-A2"
    assert rig.flow.line == ("My scout picked *BOT-A2*. You lose 2.85 s in lap 2: BOT-A2 runs it in 33.23 s, you in "
                             "36.08 s. Buying in a moment; Circle stops me.")
    assert rig.flow.fill("{payee}") == "the house account " + HOUSE


def _rows_with(name, rank):
    from arca_launcher.handler.board import Row
    return (Row(rank=1, name="ANY-K2P", frames=6000, you=False, listed=False, sells=False, target=False),
            Row(rank=rank, name=name, frames=6236, you=False, listed=True, sells=True, target=False),
            Row(rank=3, name="YOU", frames=6414, you=True, listed=False, sells=False, target=False))


def test_the_rules_pick_says_so(tmp_path):
    rule = dict(PICK, by="rule", model=None, note="the model did not answer in 6 s", lap=None,
                reason="BOT-A6 is the listed ghost just ahead of you: 1:45.42 against your 1:46.90.", seller="BOT-A6",
                label="BOT-A6")
    rig = _scout_rig(tmp_path, answer=Result(ok=True, data=rule))
    rig.flow.start("board")
    rig.flow.press("cross")
    rig.wait(16)
    assert rig.state == "scout_pick"
    assert rig.flow.ctx["scout_by"] == "Picked by PB's rule: the ghost just ahead (the model did not answer in 6 s)"
    rig = _scout_rig(tmp_path / "nonote", answer=Result(ok=True, data=dict(rule, note=None)))
    rig.flow.start("board")
    rig.flow.press("cross")
    rig.wait(16)
    assert rig.flow.ctx["scout_by"] == "Picked by PB's rule: the ghost just ahead"


def test_the_pick_buys_by_itself_after_four_seconds(tmp_path):
    rig = _scout_rig(tmp_path)
    rig.flow.start("board")
    rig.flow.press("cross")
    rig.wait(16)
    assert rig.state == "scout_pick"
    rig.wait(3900)
    assert rig.state == "scout_pick"
    rig.wait(100)
    assert rig.state == "buy_check"
    payload = rig.sponsors.calls[-1].payload
    assert (payload["seller"], payload["target_run"], payload["target_listing"], payload["target_log_h"],
            payload["target_frames"], payload["scout_id"]) == ("BOT-A2", RUN_KEY, LISTING_KEY, LOG_H, 6236,
                                                               "s-1a2b3c4d")
    rig.wait(1400 + 2000 + 1200)
    assert rig.state == "buy_done" and list(rig.flow.ledger.purchases) == [f"{GAME}:BOT-A2"]


def test_cross_buys_now_and_circle_stops_it(tmp_path):
    rig = _scout_rig(tmp_path / "cross")
    rig.flow.start("board")
    rig.flow.press("cross")
    rig.wait(16)
    rig.flow.press("cross")
    assert rig.state == "buy_check"
    rig = _scout_rig(tmp_path / "circle")
    rig.flow.start("board")
    rig.flow.press("cross")
    rig.wait(16)
    rig.wait(2000)
    rig.flow.press("circle")
    assert rig.state == "board"
    assert rig.flow.ctx["target"] == "ANY-9MX" and rig.flow.ctx["target_pay_to"] == "0.0.6009900"   # the board's again
    assert rig.flow.ctx["scout_id"] is None
    rig.wait(8000)
    assert rig.state == "board" and rig.flow.ledger.spent == 0
    rig = _scout_rig(tmp_path / "list")                            # the Square list open: nothing moves under it
    rig.flow.start("scout_pick")
    rig.flow.outcomes_open = True
    rig.wait(5000)
    assert rig.state == "scout_pick"


@pytest.mark.parametrize("answer, state", [
    (Result(ok=False, failure="buy_budget"), "buy_budget"),
    (Result(ok=False, failure="nobody_ahead"), "nobody_ahead"),
    (Result(ok=False, failure="buy_suspended", data={"why": "console_not_linked"}), "buy_suspended"),
    (Result(ok=False, failure="buy_down"), "target"),
    (Result(ok=False, failure="something_else"), "target"),
    (Result(ok=True, data={}), "target"),                          # an answer it can not show: the board's own target
])
def test_each_scout_failure_lands_on_its_screen(tmp_path, answer, state):
    rig = _scout_rig(tmp_path, answer=answer)
    rig.flow.start("board")
    rig.flow.press("cross")
    rig.wait(16)
    assert rig.state == state
    if state == "target":
        assert rig.flow.ctx["target"] == "ANY-9MX"
        assert rig.flow.line.startswith("My scout is not answering, so here is the ghost just ahead. Next run to beat")
    if state == "buy_suspended":
        assert rig.flow.ctx["refused_why"] == "this console is not linked to ANY-6PS"
        assert rig.flow.line == ("ANY-9MX's listing did not pass my checks (this console is not linked to ANY-6PS), "
                                 "so I paid nothing.")


def test_a_scout_that_never_answers_times_out_to_the_boards_target(tmp_path):
    class Silent(ScoutSponsors):
        scout_answer = None
    rig = Rig(tmp_path, book="ANY-6PS", sponsors=Silent, best_frames=6414)
    rig.flow.start("board")
    rig.flow.press("cross")
    assert rig.state == "scout"
    rig.wait(11900)
    assert rig.state == "scout"
    rig.wait(100)
    assert rig.state == "target" and rig.flow.ctx["scout_down"]
    rig.flow.press("circle")
    rig.flow.press("cross")
    assert rig.state == "scout" and rig.flow.ctx["scout_down"] == ""   # a new look: no old excuse


def test_a_target_reached_without_the_scout_says_nothing_of_it(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("board")
    rig.flow.press("cross")
    assert rig.state == "target" and rig.flow.line.startswith("Next run to beat: *RIA")


@pytest.mark.parametrize("why, text", [
    ("own_book", "that is your own book"), ("run_changed", "the run changed"), ("no_pay_to", "no payout account"),
    ("cannot_receive", "the account can not take USDC"), ("payto_402", "the paywall named another account"),
    ("not_for_sale", "not for sale"), ("not_house", "a BOT listing must pay the house"),
    ("console_not_linked", "this console is not linked to ANY-7QZ"), ("made_up", "the listing did not check out"),
    (None, "the listing did not check out"),
])
def test_a_guard_refusal_says_why(tmp_path, why, text):
    class Refused(ManualPaySponsors):
        pass
    rig = Rig(tmp_path, sponsors=Refused)
    rig.flow.start("buy_pay")
    rig.sponsors.calls[-1].result = Result(ok=False, failure="buy_suspended", data={"why": why} if why else {})
    rig.wait(16)
    assert rig.state == "buy_suspended" and rig.flow.ctx["refused_why"] == text
    assert rig.flow.fill(rig.flow.state.card["rows"][0]) == "PB's guard said no: " + text


def test_square_on_the_board_toggles_humans_only_and_nowhere_else(tmp_path):
    for case, name in (("ok", "board"), ("no_best", "board_new")):
        rig = Rig(tmp_path / name, board_case=case)
        rig.flow.start("board")
        assert rig.state == name and not rig.flow.ctx.get("humans_only")
        rig.flow.press("square")
        assert rig.flow.ctx["humans_only"] is True and not rig.flow.outcomes_open
        rig.flow.press("square")
        assert rig.flow.ctx["humans_only"] is False
    rig.flow.start("buy_pay")                                      # a call state: the mock list, as before
    rig.flow.press("square")
    assert rig.flow.outcomes_open and rig.flow.ctx["humans_only"] is False


def test_humans_only_never_changes_the_target(tmp_path):
    rig = Rig(tmp_path)
    rig.flow.start("board")
    rig.flow.press("square")
    rig.flow.press("cross")
    assert rig.state == "target" and rig.flow.ctx["target"] == "RIA"


class ChainSponsors(HederaRealSponsors):
    """Hedera and Arkiv real: pay answers when the test says (the chain ids with it), record and publish at once."""
    explorer_origin = "https://rabdi.explorer.arkiv.network"

    def __init__(self, clock_ms, **kwargs):
        super().__init__(clock_ms, **kwargs)
        self.update = None

    def mocked(self, service):
        return service == "world"

    def begin(self, step, payload):
        call = super().begin(step, payload)
        if step == "record":
            call._result = Result(ok=True, data={"topic": "0.0.11332437", "seq": 41,
                                                 "tx": "0.0.6421420@1793929992.000000001",
                                                 "hashscan": "https://hashscan.io/testnet/transaction/0.0.6421420-"
                                                             "1793929992-000000001"})
        elif step == "publish":
            tx, run, listing = "0x5c1d" + "00" * 28 + "9e02", "0x" + "12" * 32, "0x23bf" + "00" * 28 + "af44"
            call._result = Result(ok=True, data={"run": run, "listing": listing, "tx": tx, "explorer": {
                "tx": "https://rabdi.explorer.arkiv.network/tx/" + tx,
                "listing": "https://rabdi.explorer.arkiv.network/entity/" + listing,
                "run": "https://evil.example/entity/" + run}})
        return call

    def chain_update(self):
        return self.update


PAID = {"receipt": TX, "hashscan": "https://hashscan.io/testnet/transaction/0.0.9185802-1762412349-000000123",
        "late": False, "intent": {"seq": 7, "tx": "0.0.9185802@1762412340.000000001",
                                  "hashscan": "https://hashscan.io/testnet/transaction/0.0.9185802-1762412340-000000001"},
        "receipt_msg": None}


def test_a_paid_ghost_shows_intent_payment_and_receipt_and_the_receipt_fills_in(tmp_path):
    rig = Rig(tmp_path, sponsors=ChainSponsors)
    rig.flow.start("buy_check")
    assert rig.flow.ctx["chain"] == []
    rig.wait(1400)
    rig.sponsors.calls[-1].result = Result(ok=True, data=PAID)
    rig.wait(16)
    rig.wait(1200)
    assert rig.state == "buy_done"
    assert rig.flow.ctx["chain"] == [
        {"label": "Hedera INTENT #7", "value": "tx 0.0.9185802@1762412340", "url": PAID["intent"]["hashscan"]},
        {"label": "Paid 0.10 USDC", "value": "tx 0.0.9185802@1762412349", "url": PAID["hashscan"]},
        {"label": "Hedera RECEIPT", "value": "waiting for the mirror", "url": None}]
    assert rig.flow.ctx["chain_i"] == 1                            # the payment's own QR first
    rig.sponsors.update = {"receipt": "another", "intent": None, "receipt_msg": {"seq": 99}}
    rig.wait(100)
    assert rig.flow.ctx["chain"][2]["value"] == "waiting for the mirror"   # another payment's: not this one's
    rig.sponsors.update = {"receipt": TX, "intent": PAID["intent"], "receipt_msg": {
        "seq": 8, "tx": "0.0.9185802@1762412360.000000001",
        "hashscan": "https://hashscan.io/testnet/transaction/0.0.9185802-1762412360-000000001"}}
    rig.wait(100)
    assert rig.flow.ctx["chain"][2] == {"label": "Hedera RECEIPT #8", "value": "tx 0.0.9185802@1762412360",
                                        "url": "https://hashscan.io/testnet/transaction/0.0.9185802-1762412360-"
                                               "000000001"}
    rig.sponsors.update = None
    for press, i in (("down", 2), ("down", 0), ("up", 2), ("up", 1)):
        rig.flow.press(press)
        assert rig.flow.ctx["chain_i"] == i, press
    rig.flow.start("buy_check")
    assert rig.flow.ctx["chain"] == []                             # a new purchase starts clean


def test_a_listing_shows_its_hcs_record_and_its_arkiv_rows(tmp_path):
    rig = Rig(tmp_path, sponsors=ChainSponsors, run_frames=6100)
    rig.flow._jti = "3f9c0a1b2c3d4e5f"
    rig.flow.start("ls_record")
    rig.wait(16)
    assert rig.state == "ls_arkiv"
    assert "Recorded: Hedera LISTING #41" in [rig.flow.fill(r) for r in rig.flow.state.card["rows"]]
    rig.wait(16)
    assert rig.state == "ls_done"
    assert rig.flow.ctx["chain"] == [
        {"label": "Hedera LISTING #41", "value": "topic 0.0.11332437 · tx 0.0.6421420@1793929992",
         "url": "https://hashscan.io/testnet/transaction/0.0.6421420-1793929992-000000001"},
        {"label": "Arkiv listing", "value": "0x23bf…af44",
         "url": "https://rabdi.explorer.arkiv.network/entity/0x23bf" + "00" * 28 + "af44"},
        {"label": "Arkiv tx", "value": "0x5c1d…9e02",
         "url": "https://rabdi.explorer.arkiv.network/tx/0x5c1d" + "00" * 28 + "9e02"}]
    rig.flow.start("ls_scan")
    assert rig.flow.ctx["chain"] == []


def test_only_explorer_links_on_the_allowed_origins_are_kept(tmp_path):
    class Elsewhere(ChainSponsors):
        explorer_origin = None                                     # /arkiv/config not read: no Arkiv link drawn
    rig = Rig(tmp_path, sponsors=Elsewhere, run_frames=6100)
    rig.flow.start("ls_arkiv")
    rig.wait(16)
    assert [row["url"] for row in rig.flow.ctx["chain"]] == [None, None]
    assert [row["label"] for row in rig.flow.ctx["chain"]] == ["Arkiv listing", "Arkiv tx"]
    rig = Rig(tmp_path / "links", sponsors=ChainSponsors)
    for url, ok in (("https://hashscan.io/testnet/transaction/x", True), ("https://hashscan.io/mainnet/x", False),
                    ("https://rabdi.explorer.arkiv.network/tx/0x1", True),
                    ("https://rabdi.explorer.arkiv.network.evil.example/x", False),
                    ("http://hashscan.io/testnet/x", False), ("https://hashscan.io/testnet/a b", False), (None, False),
                    (7, False)):
        assert (rig.flow._allowed(url) is not None) is ok, url


def test_the_mock_shows_no_chain_ids(tmp_path):
    rig = Rig(tmp_path / "buy")
    rig.flow.start("buy_check")
    rig.wait(1400 + 2000 + 1200)
    assert rig.state == "buy_done" and rig.flow.ctx["chain"] == []
    rig = Rig(tmp_path / "list", run_frames=6100)
    rig.flow.start("ls_record")
    rig.wait(2000)
    assert rig.state == "ls_arkiv" and rig.flow.ctx["record_line"] == "Recorded"
    rig.wait(1400)
    assert rig.state == "ls_done" and rig.flow.ctx["chain"] == []


def test_the_payee_is_the_sellers_account_or_the_house(tmp_path):
    rig = Rig(tmp_path, target="ANY-4HJ", target_pay_to="0.0.6007788")
    assert rig.flow.fill("{payee}") == "ANY-4HJ's account 0.0.6007788"
    rig.flow.ctx.update(target="BOT-A2", target_pay_to=HOUSE)
    assert rig.flow.fill("{payee}") == "the house account " + HOUSE
    rig.flow.ctx.update(target="RIA", target_pay_to=None)          # the mock board's seller
    assert rig.flow.fill("{payee}") == "RIA's record book"
    rig.flow.ctx.update(target="", target_pay_to=None)
    assert rig.flow.fill("{payee}") == ""


def test_id_taken_names_the_book_world_said(tmp_path):
    class Taken(SpySponsors):
        def begin(self, step, payload):
            call = super().begin(step, payload)
            if step == "idkit_verify":
                call._result = Result(ok=False, failure="id_taken", data={"book": "ANY-6PS", "console": "C-7QZP"})
            return call
    rig = Rig(tmp_path, book=None, sponsors=Taken)
    rig.flow.start("id_verifying")
    rig.wait(16)
    assert rig.state == "id_taken" and rig.flow.ctx["other_book"] == "ANY-6PS" and rig.flow.ledger.book is None
    rig = Rig(tmp_path / "mock", book=None)                        # the mock's: whatever the context made up
    rig.flow.start("id_confirm")
    rig.flow.press("square")
    rig.flow.pick([label for label, _ in rig.flow.outcomes].index("Another person's console"))
    rig.wait(16)
    assert rig.state == "id_taken" and rig.flow.ctx["other_book"] == "ANY-2KD"


def test_a_new_record_book_shows_the_consoles_tag(tmp_path):
    class Bound(SpySponsors):
        def begin(self, step, payload):
            call = super().begin(step, payload)
            if step == "idkit_verify":
                call._result = Result(ok=True, data={"book": "ANY-6PS", "credential": "Orb", "console": "C-7QZP"})
            return call
    rig = Rig(tmp_path, book=None, sponsors=Bound)
    rig.flow.start("id_verifying")
    rig.wait(16)
    assert rig.state == "id_done" and rig.flow.ctx["console_tag"] == "C-7QZP"
    assert ("Console", "C-7QZP") in [(rig.flow.fill(a), rig.flow.fill(b)) for a, b in rig.flow.state.card["what"]]


def test_the_words_the_flow_and_cards_add_keep_the_copy_rules():
    """Strings built outside the state table (the scout's by-line and excuse, the guard's reasons, the chain rows, the
    new cards' own words) follow the same rules: no banned word, no her or she, nothing that bans a person."""
    import re
    from arca_launcher.handler import BANNED_WORDS
    from arca_launcher import app as A
    from arca_launcher.handler import flow as F
    from arca_launcher.render import handler_cards as C, handler_view as V
    texts = [F.SCOUT_DOWN, F.REFUSED_ELSE, F.NO_BOOK_LINE, *F.REFUSED_WHY.values(), "Picked by PB's rule: the ghost just ahead",
             f"Picked by openai/gpt-oss-120b on {F.GROQ}", "waiting for the mirror", "Recorded", C.BOT_LEGEND,
             C.HUMAN_LEGEND, "Scout's pick", "No record book on this console", "Humans only", "All runners",
             "Next QR", "linked to ANY-6PS", "not linked yet", "released", "HOUSE", F.REPLAYED_CHECKER,
             F.REPLAYED_HERE, "1:42.83 = 6170 frames · end 225d59fd", "1:43.93 = 6236 frames, same as the board",
             "1:43.93 = 6236 frames, checked when first loaded", "Pick", "On chain", "Arkiv run", "Arkiv listing",
             "Hedera LISTING #41", "topic 0.0.11332437", "1:43.93 = 6236 frames", "Pays 0.0.7700001",
             "the house account", "ANY-6PS's account", "BOT-A2's 1:43.93 run", "Open link", "Next", *A.HANDOFF,
             "The browser could not start", "Opened in a window", "Links open on the handheld or the laptop"]
    assert all(text in inspect_source(A) for text in texts[-3:])
    assert "Humans only" in inspect_source(V) and "Scout's pick" in inspect_source(C)
    assert "On chain" in inspect_source(V) and "the house account" in inspect_source(F)
    for text in texts:
        low = text.lower()
        for word in BANNED_WORDS:
            assert not re.search(r"\b" + re.escape(word) + r"\b", low), (text, word)
        assert not re.search(r"\b(her|she|fraud|void|suspended|ban)\b", low), text


def inspect_source(module):
    import inspect
    return inspect.getsource(module)


# ---- Triangle opens a chain row's link; the replays as rows; a chain card brought back after the browser -------------

ARKIV_RUN = "https://rabdi.explorer.arkiv.network/entity/" + RUN_KEY
CHECKED = {"frames": 6170, "final_hash": 576543229}
HASHSCAN_URL = "https://hashscan.io/testnet/transaction/0.0.9185802-1762412349-000000123"


class ReplaySponsors(ChainSponsors):
    """ChainSponsors whose publish says the checker's replay and names the run on the allowed explorer, and whose
    load_ghost (a real target) answers at once with this console's replay and the run's link."""
    loaded = {"ghost_log": "/runs/ghosts/ab.acl", "replayed": 6236, "explorer": {"run": ARKIV_RUN}}

    def begin(self, step, payload):
        call = super().begin(step, payload)
        if step == "publish":
            data = dict(call._result.data, replay=CHECKED)
            data["explorer"] = dict(data["explorer"], run=ARKIV_RUN)
            call._result = Result(ok=True, data=data)
        elif step == "load_ghost":
            call._result = Result(ok=True, data=self.loaded)
        return call


def _listed(tmp_path, sponsors=ReplaySponsors):
    rig = Rig(tmp_path, sponsors=sponsors, run_frames=6170)
    rig.flow._jti = "3f9c0a1b2c3d4e5f"
    rig.flow.start("ls_record")
    rig.wait(16)
    rig.wait(16)
    assert rig.state == "ls_done"
    return rig


def _bought(tmp_path, sponsors=ReplaySponsors, receipt_msg=None, **ctx):
    rig = Rig(tmp_path, sponsors=sponsors, target="BOT-A2", target_time="1:43.93", target_frames=6236,
              target_run=RUN_KEY, target_listing=LISTING_KEY, target_log_h=LOG_H, **ctx)
    rig.flow.start("buy_check")
    rig.wait(1400)
    rig.sponsors.calls[-1].result = Result(ok=True, data=dict(PAID, receipt_msg=receipt_msg))
    rig.wait(16)
    rig.wait(16)
    assert rig.state == "buy_done"
    return rig


def test_triangle_opens_the_chosen_rows_link_on_a_chain_card(tmp_path):
    from arca_launcher.handler.flow import OpenLink
    rig = _listed(tmp_path)
    rows = list(rig.flow.ctx["chain"])
    assert rig.flow.ctx["chain_i"] == 0
    assert rig.flow.press("triangle") == OpenLink(rows[0]["url"])
    rig.flow.press("down")
    assert rig.flow.press("triangle") == OpenLink(rows[1]["url"])
    assert rig.state == "ls_done"                                   # nothing else moves
    rig.flow.ctx["chain"][1] = dict(rows[1], url=None)              # a row with no link: nothing to open
    assert rig.flow.press("triangle") is None
    rig.flow.ctx["chain_i"] = 99                                    # as the card clamps it: the last row
    assert rig.flow.press("triangle") == OpenLink(rows[-1]["url"])
    rig.flow.ctx["chain"] = []
    assert rig.flow.press("triangle") is None
    for name in ("hub", "board", "target", "buy_suspended"):        # not a chain card
        rig = Rig(tmp_path / name, chain=[{"label": "x", "value": "y", "url": HASHSCAN_URL}])
        rig.flow.start(name)
        assert rig.flow.press("triangle") is None, name
    rig = _bought(tmp_path / "bought")
    assert rig.flow.press("triangle") == OpenLink(PAID["hashscan"])  # the payment's own row, chosen first


def test_a_listing_ends_with_the_checkers_replay(tmp_path):
    rig = _listed(tmp_path)
    assert rig.flow.ctx["chain"][-1] == {"label": "Replayed by the checker",
                                         "value": "1:42.83 = 6170 frames · end 225d59fd", "url": ARKIV_RUN}
    assert [row["label"] for row in rig.flow.ctx["chain"]] == ["Hedera LISTING #41", "Arkiv listing", "Arkiv tx",
                                                                "Replayed by the checker"]

    class Elsewhere(ReplaySponsors):
        explorer_origin = None
    rig = _listed(tmp_path / "elsewhere", Elsewhere)
    assert rig.flow.ctx["chain"][-1]["url"] is None                  # the row stays, its link is not drawn

    class Unreplayed(ChainSponsors):                                 # the approval's record answered: no replay
        pass
    rig = _listed(tmp_path / "none", Unreplayed)
    assert "Replayed by the checker" not in [row["label"] for row in rig.flow.ctx["chain"]]


def test_a_purchase_ends_with_this_consoles_replay_and_keeps_it_as_the_receipt_fills_in(tmp_path):
    rig = _bought(tmp_path)
    here = {"label": "Replayed on this console", "value": "1:43.93 = 6236 frames, same as the board",
            "url": ARKIV_RUN}
    assert [row["label"] for row in rig.flow.ctx["chain"]] == ["Hedera INTENT #7", "Paid 0.10 USDC", "Hedera RECEIPT",
                                                                "Replayed on this console"]
    assert rig.flow.ctx["chain"][-1] == here and rig.flow.ctx["chain_i"] == 1
    rig.sponsors.update = {"receipt": TX, "intent": PAID["intent"], "receipt_msg": {
        "seq": 8, "tx": "0.0.9185802@1762412360.000000001",
        "hashscan": "https://hashscan.io/testnet/transaction/0.0.9185802-1762412360-000000001"}}
    rig.wait(100)
    assert [row["label"] for row in rig.flow.ctx["chain"]] == ["Hedera INTENT #7", "Paid 0.10 USDC",
                                                                "Hedera RECEIPT #8", "Replayed on this console"]
    assert rig.flow.ctx["chain"][-1] == here

    class Cached(ReplaySponsors):
        loaded = {"ghost_log": "/runs/ghosts/ab.acl", "replayed": 6236, "replay_cached": True}
    rig = _bought(tmp_path / "cached", Cached)
    assert rig.flow.ctx["chain"][-1] == {"label": "Replayed on this console",
                                         "value": "1:43.93 = 6236 frames, checked when first loaded", "url": None}

    class Odd(ReplaySponsors):
        loaded = {"ghost_log": "/runs/ghosts/ab.acl", "replayed": "6236"}
    rig = _bought(tmp_path / "odd", Odd)
    assert "Replayed on this console" not in [row["label"] for row in rig.flow.ctx["chain"]]


def test_loading_again_never_says_the_replay_twice(tmp_path):
    rig = _bought(tmp_path)
    rig.flow.start("buy_load")                                       # buy_load_fail's Cross: the load again
    rig.wait(16)
    labels = [row["label"] for row in rig.flow.ctx["chain"]]
    assert rig.state == "buy_done" and labels.count("Replayed on this console") == 1
    assert labels[-1] == "Replayed on this console"
    rig.flow.start("buy_check")
    assert rig.flow.ctx["chain"] == []                               # a new purchase starts clean


def test_the_mock_board_adds_no_replay_rows(tmp_path):
    class MockBoard(HederaRealSponsors):                             # Hedera real, the board the mock's
        def begin(self, step, payload):
            call = super().begin(step, payload)
            if step == "load_ghost":
                call._result = Result(ok=True, data={"ghost_log": "/x.acl", "replayed": 6070})
            elif step == "publish":
                call._result = Result(ok=True, data={"replay": CHECKED})
            return call
    rig = Rig(tmp_path, sponsors=MockBoard)
    rig.flow.start("buy_check")
    rig.wait(1400)
    rig.sponsors.calls[-1].result = Result(ok=True, data=PAID)
    rig.wait(16)
    rig.wait(16)
    assert rig.state == "buy_done"
    assert [row["label"] for row in rig.flow.ctx["chain"]] == ["Hedera INTENT #7", "Paid 0.10 USDC", "Hedera RECEIPT"]
    rig = Rig(tmp_path / "list", sponsors=MockBoard, run_frames=6100)
    rig.flow.start("ls_arkiv")
    rig.wait(16)
    assert rig.state == "ls_done" and rig.flow.ctx["chain"] == []


def _round_trip(flow):
    """The context as the resume file keeps it: every top-level value that is JSON."""
    import json
    out = {}
    for key, value in flow.ctx.items():
        try:
            out[key] = json.loads(json.dumps(value))
        except (TypeError, ValueError):
            pass
    return out


def _restored(rig, state=None, chain_pay="same"):
    import json
    pay = rig.flow.chain_pay if chain_pay == "same" else chain_pay
    flow = Flow(rig.sponsors, load(rig.path), rig.path, GAME, _round_trip(rig.flow), today=lambda: TODAY)
    flow.restore(json.loads(json.dumps(pay)))
    assert flow.start(state or rig.state) is None
    return flow


def test_a_listing_card_brought_back_after_the_browser_is_as_it_was(tmp_path):
    rig = _listed(tmp_path)
    rig.flow.press("down")
    rig.flow.press("down")
    before = (list(rig.flow.ctx["chain"]), rig.flow.ctx["chain_i"], rig.flow.line)
    assert len(rig.saved().listings) == 1
    flow = _restored(rig)
    assert flow.state.name == "ls_done" and flow.ms_in_state == 0
    assert (flow.ctx["chain"], flow.ctx["chain_i"], flow.line) == before
    assert len(flow.ledger.listings) == 1 and len(rig.saved().listings) == 1   # arriving wrote nothing again
    assert rig.flow.chain_pay is None and flow.chain_pay is None
    assert flow.press("cross") is None and flow.state.name == "hub"


def test_a_purchase_brought_back_keeps_filling_its_receipt_and_still_races_the_ghost(tmp_path):
    rig = _bought(tmp_path)
    pay = rig.flow.chain_pay
    assert pay["receipt"] == TX and pay["receipt_msg"] is None
    pay["receipt"] = "changed"                                       # a copy: the flow's own stays
    assert rig.flow.chain_pay["receipt"] == TX
    before = (list(rig.flow.ctx["chain"]), rig.flow.ctx["chain_i"], rig.flow.line)
    spent = rig.saved().spent
    flow = _restored(rig)
    assert flow.state.name == "buy_done"
    assert (flow.ctx["chain"], flow.ctx["chain_i"], flow.line) == before
    assert flow.chain_pay == rig.flow.chain_pay and load(rig.path).spent == spent
    rig.sponsors.update = {"receipt": TX, "intent": PAID["intent"], "receipt_msg": {
        "seq": 8, "tx": "0.0.9185802@1762412360.000000001",
        "hashscan": "https://hashscan.io/testnet/transaction/0.0.9185802-1762412360-000000001"}}
    flow.tick(100)
    assert [row["label"] for row in flow.ctx["chain"]] == ["Hedera INTENT #7", "Paid 0.10 USDC", "Hedera RECEIPT #8",
                                                           "Replayed on this console"]
    assert flow.press("cross") == RaceTarget(GAME, "BOT-A2")         # Cross still races the bought ghost
    assert load(rig.path).spent == spent                             # never paid twice


@pytest.mark.parametrize("pay", [None, "x", {}, {"receipt": 5}, {"receipt": ""}, ["receipt"]])
def test_a_restore_with_no_usable_payment_data_still_lands_and_refreshes_nothing(tmp_path, pay):
    rig = _bought(tmp_path)
    before = list(rig.flow.ctx["chain"])
    flow = _restored(rig, chain_pay=pay)
    assert flow.state.name == "buy_done" and flow.chain_pay is None and flow.ctx["chain"] == before
    rig.sponsors.update = {"receipt": TX, "receipt_msg": {"seq": 8, "tx": "0.0.1@2", "hashscan": None}}
    flow.tick(100)
    assert flow.ctx["chain"] == before


def test_a_restore_counts_for_one_start_only(tmp_path):
    rig = _listed(tmp_path)
    flow = _restored(rig)
    flow.start("ls_done")                                            # a fresh start after it: arriving counts again
    assert len(flow.ledger.listings) == 2


# ---- the real board's cursor, and a board run's records on chain (run_links) -----------------------------------------

ENTITY = "https://rabdi.explorer.arkiv.network/entity/"
BOT_KEY, BOT_LISTING, MINE = "0x" + "b0a2" * 16, "0x" + "1a2b" * 16, "0x" + "08e7" * 16
MSG = "0.0.11332437/41"


class LinkSponsors(RealSponsors):
    """Every sponsor real, the explorer named: entity_link builds a row's link as the Arkiv adapter does."""
    explorer_origin = "https://rabdi.explorer.arkiv.network"

    def entity_link(self, key):
        return ENTITY + key.lower()


def _real_board(best=6414):
    """The real board as build_real makes it, YOU's book ANY-6PS: BOT-A2 listed by the house with its LISTING message on
    Hedera (1st), TEAM's run with no listing (2nd), YOU's own listed run (3rd), ANY-9MX listed before payout accounts
    and messages (4th)."""
    import dataclasses
    from arca_launcher.handler.board import build_real
    from test_handler_board import run
    rows = (run("BOT-A2", 6236, book=False, listed=True, key=BOT_KEY, pay_to=HOUSE, hcs=MSG),
            run("TEAM", 6300, book=False), run("ANY-6PS", 6414, listed=True, key=MINE, pay_to="0.0.9473064"),
            run("ANY-9MX", 6500, listed=True))
    rows = (dataclasses.replace(rows[0], listing=BOT_LISTING),) + rows[1:]
    return build_real(rows, best, "ANY-6PS", "Orb", need_pay_to=True).rows


def _on_board(tmp_path, sponsors=LinkSponsors, **ctx):
    base = dict(board_rows=_real_board(), board_case="ok", best_frames=6414)
    base.update(ctx)
    rig = Rig(tmp_path, book="ANY-6PS", sponsors=sponsors, **base)
    rig.flow.start("board")
    return rig


def _picked(flow):
    row = flow.board_row
    return row.name if row is not None else None


def test_the_real_board_has_a_cursor_that_starts_on_you_and_stays_on_the_rows(tmp_path):
    rig = _on_board(tmp_path)
    flow = rig.flow
    assert rig.state == "board" and flow.board_cursor == 2 and _picked(flow) == "YOU"
    for press, name in (("up", "TEAM"), ("up", "BOT-A2"), ("up", "BOT-A2"), ("down", "TEAM"), ("down", "YOU"),
                        ("down", "ANY-9MX"), ("down", "ANY-9MX")):
        assert flow.press(press) is None and _picked(flow) == name, press
    flow.press("square")                                            # Humans only: YOU and ANY-9MX shown
    assert [row.name for row in flow.board_shown] == ["YOU", "ANY-9MX"] and flow.board_cursor == 1
    flow.press("up")
    assert _picked(flow) == "YOU"
    flow.press("square")
    flow.press("up")
    assert _picked(flow) == "TEAM"
    flow.press("square")                                            # its row hidden: YOU's, never off the rows
    assert _picked(flow) == "YOU" and flow.board_cursor == 0
    flow.press("square")
    assert _picked(flow) == "TEAM"                                  # shown again: the runner picked
    flow.ctx["board_rows"] = tuple(r for r in _real_board() if r.name != "TEAM")   # a new read without that runner
    assert _picked(flow) == "YOU" and flow.board_cursor == 1
    flow.ctx["board_rows"] = ()
    assert flow.board_cursor is None and flow.board_row is None
    assert flow.press("down") is None and flow.press("triangle") is None and rig.state == "board"
    flow.ctx["board_rows"] = _real_board()
    flow.press("up")
    flow.press("circle")                                            # the hub
    assert flow.state.name == "hub" and flow.board_cursor is None
    flow.pick(0)                                                    # the board again: a new look starts on YOU
    assert rig.state == "board" and _picked(flow) == "YOU"
    rig = _on_board(tmp_path / "new", board_case="no_best")         # board_new has it too
    assert rig.state == "board_new" and _picked(rig.flow) == "YOU"
    rig.flow.press("up")
    assert _picked(rig.flow) == "TEAM"


def test_the_mock_board_has_no_cursor_and_triangle_does_nothing(tmp_path):
    from arca_launcher.handler.board import build
    rig = Rig(tmp_path, board_rows=build(6070, 6290).rows)
    rig.flow.start("board")
    assert rig.flow.board_cursor is None and rig.flow.board_row is None
    for press in ("up", "down", "triangle"):
        assert rig.flow.press(press) is None and rig.state == "board", press


def test_triangle_on_a_board_row_shows_that_runs_records_on_chain(tmp_path):
    from arca_launcher.handler.flow import OpenLink
    rig = _on_board(tmp_path)
    flow = rig.flow
    flow.press("up")
    flow.press("up")
    assert flow.press("triangle") is None and rig.state == "run_links"
    assert flow.ctx["links_run"] == "BOT-A2's 1:43.93 run" and flow.ctx["chain_i"] == 0
    assert flow.ctx["chain"] == [
        {"label": "Arkiv run", "value": "0xb0a2…b0a2", "url": ENTITY + BOT_KEY},
        {"label": "Arkiv listing", "value": "0x1a2b…1a2b", "url": ENTITY + BOT_LISTING},
        {"label": "Hedera LISTING #41", "value": "topic 0.0.11332437",
         "url": "https://hashscan.io/testnet/topic/0.0.11332437"},
        {"label": "Replayed by the checker", "value": "1:43.93 = 6236 frames", "url": ENTITY + BOT_KEY},
        {"label": "Pays 0.0.7700001", "value": "the house account",
         "url": "https://hashscan.io/testnet/account/0.0.7700001"}]
    assert flow.fill(flow.state.card["h"]) == "BOT-A2's 1:43.93 run"
    flow.press("down")
    assert flow.press("triangle") == OpenLink(ENTITY + BOT_LISTING)
    flow.press("up")
    flow.press("up")                                                # Up and Down go round, as on any chain card
    assert flow.press("triangle") == OpenLink("https://hashscan.io/testnet/account/0.0.7700001")
    assert flow.press("circle") is None and rig.state == "board" and _picked(flow) == "BOT-A2"   # the same cursor
    flow.press("down")
    flow.press("down")
    flow.press("triangle")
    assert flow.ctx["links_run"] == "ANY-6PS's 1:46.90 run"         # YOU's row: the book's run
    assert [(r["label"], r["value"]) for r in flow.ctx["chain"]] == [
        ("Arkiv run", "0x08e7…08e7"), ("Arkiv listing", "0x0000…190f"),
        ("Replayed by the checker", "1:46.90 = 6414 frames"), ("Pays 0.0.9473064", "ANY-6PS's account")]
    assert flow.press("cross") is None and rig.state == "board" and _picked(flow) == "YOU"   # Cross: as Circle
    flow.press("up")
    flow.press("triangle")                                          # TEAM: a run with no listing
    assert [r["label"] for r in flow.ctx["chain"]] == ["Arkiv run", "Replayed by the checker"]
    flow.press("circle")
    flow.press("down")
    flow.press("down")
    flow.press("triangle")                                          # ANY-9MX: listed with no account, no message
    assert [r["label"] for r in flow.ctx["chain"]] == ["Arkiv run", "Arkiv listing", "Replayed by the checker"]


def test_a_row_on_no_chain_opens_nothing_and_links_wait_for_the_explorer(tmp_path):
    rig = _on_board(tmp_path, board_rows=_real_board(best=6000))   # YOU's local best: not on the board yet
    assert _picked(rig.flow) == "YOU" and rig.flow.board_row.key is None
    assert rig.flow.press("triangle") is None and rig.state == "board"

    class NoExplorer(RealSponsors):                                 # /arkiv/config not read: no Arkiv link
        explorer_origin = None
    rig = _on_board(tmp_path / "plain", sponsors=NoExplorer)
    rig.flow.press("up")
    rig.flow.press("up")
    rig.flow.press("triangle")
    assert rig.state == "run_links"
    assert [r["url"] for r in rig.flow.ctx["chain"]] == [None, None, "https://hashscan.io/testnet/topic/0.0.11332437",
                                                         None, "https://hashscan.io/testnet/account/0.0.7700001"]

    class Elsewhere(LinkSponsors):                                  # a link off the allowed explorer is never drawn
        def entity_link(self, key):
            return "https://evil.example/entity/" + key
    rig = _on_board(tmp_path / "evil", sponsors=Elsewhere)
    rig.flow.press("triangle")
    assert [r["url"] for r in rig.flow.ctx["chain"]] == [None, None, None,
                                                         "https://hashscan.io/testnet/account/0.0.9473064"]


def test_run_links_never_takes_a_payments_late_receipt_and_comes_back_after_the_browser(tmp_path):
    rig = _bought(tmp_path)
    assert rig.flow.chain_pay is not None
    rig.flow.press("circle")                                        # the hub, then the real board
    rig.flow.ctx.update(board_rows=_real_board(), board_case="ok")
    rig.flow.pick(0)
    rig.flow.press("up")
    rig.flow.press("up")
    rig.flow.press("triangle")
    assert rig.state == "run_links" and rig.flow.chain_pay is None
    rows = list(rig.flow.ctx["chain"])
    rig.sponsors.update = {"receipt": TX, "intent": PAID["intent"], "receipt_msg": {
        "seq": 8, "tx": "0.0.9185802@1762412360.000000001",
        "hashscan": "https://hashscan.io/testnet/transaction/0.0.9185802-1762412360-000000001"}}
    rig.wait(200)
    assert rig.flow.ctx["chain"] == rows                            # the purchase's rows never come back over it
    rig.flow.press("down")
    flow = _restored(rig)
    assert flow.state.name == "run_links" and flow.ctx["chain"] == rows and flow.ctx["chain_i"] == 1
    assert flow.line == rig.flow.line and "BOT-A2's 1:43.93 run" in flow.line
    flow.ctx["board_rows"] = _real_board()                          # the glue builds the board again
    flow.press("circle")
    assert flow.state.name == "board" and _picked(flow) == "BOT-A2"
