"""Tests for PB the handler's flow engine (handler/flow.py). Every test drives a real MockSponsors
on a fake clock the test advances by hand, so the mock's delays and the engine's deadlines (read
from the call's own elapsed_ms) tick off the same milliseconds. The ledger lives in a temp dir and
is re-read from disk wherever a test checks that a change was saved."""
import os
import random

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
    # 18 sponsor outcomes over six steps (approve's five twice: ls_approve, and ls_confirm for a
    # World ID approval), plus ls_cancel's own
    assert len(cases) == 24
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
    assert rig.flow.line == ("Hedera was slow, but your payment to RIA did land. Her ghost is "
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
                             "ahead. Beat her and 3rd is yours.")


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
        "Reject", "Let it expire", "No Selfie Check", "Same person again", "World down"]
    rig.flow.press("up")
    assert rig.flow.outcome_index == 0
    for _ in range(9):
        rig.flow.press("down")
    assert rig.flow.outcome_index == 4
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
