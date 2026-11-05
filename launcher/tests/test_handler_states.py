"""Tests for the handler's state table (handler/states.py): a transcription of the mockups'
prototype (handler-states.html's `S`) amended by the plan's controller rulings. Every test here
either walks the `on` graph (so a typo'd next-state name or a dead end shows up immediately) or
scans the copy for words and names the Global Constraints ban."""
import re

import pytest

from arca_launcher.coach import MOODS
from arca_launcher.handler import BANNED_WORDS
from arca_launcher.handler.sponsors import SponsorNames
from arca_launcher.handler.states import PLACEHOLDERS, START, STATES, copy_texts
from arca_launcher.handler_glue import MOCK_WALLET

# All 41 of the prototype's own state names (handler-states.html, `s_boot` ... `home`), plus the
# eighteen new ones: the hub flow, the post-race outcomes the prototype's `racing` auto-advance
# never had to pick between (three after a bought ghost, two more after your own best), a
# fresh-visitor board, the three down-sponsor timeouts Ruling 8 split out of
# `buy_down`/`ls_record_fail`, and `buy_late` (a payment that landed after all). Plus
# `id_dup_unnamed` (a duplicate World App refused before the bridge could name its book) and
# `ls_confirm` (a listing OK asked through World ID, where the phone never shows a code).
_PROTOTYPE_STATES = {
    "s_boot", "id_scan", "id_confirm", "id_verifying", "id_done", "id_rejected", "id_expired",
    "id_dup", "id_signed", "id_nocred", "id_cancel", "id_offline",
    "board", "target", "buy_check", "buy_pay", "buy_load", "buy_done", "racing", "result",
    "buy_budget", "buy_changed", "buy_suspended", "buy_down",
    "ls_offer", "ls_scan", "ls_approve", "ls_record", "ls_arkiv", "ls_done", "sale",
    "ls_denied", "ls_cancel", "ls_late", "ls_expired", "ls_wrong", "ls_mismatch", "ls_reused",
    "ls_record_fail", "ls_world_down", "home",
}
_NEW_STATES = {
    "hub", "need_book", "no_board", "no_run", "nobody_ahead", "race_lost", "race_unfinished",
    "race_unverified", "book_view", "listings_view", "start_over",
    "board_new", "buy_check_fail", "buy_load_fail", "ls_publish_fail",
    "buy_late", "own_result", "own_again", "id_dup_unnamed", "ls_confirm",
}

# Sample values for every non-sponsor-name placeholder the table uses, so copy can be filled
# all the way to plain text (SponsorNames.fill covers {world}/{board}/{third}/{pay_rail}/
# {record_rail}; these cover the rest of states.PLACEHOLDERS). gap is a plain duration (Ruling 6:
# no sign, no "on you" -- the target/race cards add that framing themselves).
_SAMPLES = {
    "target": "RIA", "target_time": "1:43.20", "gap": "1.6 s", "rank": "6th",
    "new_rank": "5th", "run_time": "1:42.95", "price": "0.10", "budget_left": "0.80",
    "book": "ANY-7Q3", "other_book": "ANY-2KD", "code": "R4D-91X", "wallet": MOCK_WALLET,
    "buyer": "ARJUN", "ghost_look": "the *lime kart*", "split": "the hairpin",
    "game": "Marine Drive GP", "runs": 14, "sold": 3, "jti": "5e1f09ab", "listing_days": 7,
    "ghost_kept": "RIA's ghost is still yours. ", "credential": "Orb", "approve_how": "Cross to go",
    "approve_via": "World App > World ID",
}

# The prototype states whose own S entry carries a `what` (handler-states.html). A fix round
# found two of these (buy_budget, buy_changed) had lost their `what` in transcription.
_PROTOTYPE_STATES_WITH_WHAT = {
    "id_done", "id_rejected", "id_expired", "id_dup", "id_signed", "id_nocred", "id_cancel",
    "id_offline", "buy_done", "buy_budget", "buy_changed", "buy_suspended", "buy_down",
    "ls_done", "ls_denied", "ls_cancel", "ls_late", "ls_expired", "ls_wrong", "ls_mismatch",
    "ls_reused", "ls_record_fail", "ls_world_down",
}

_TIME_LITERAL_RE = re.compile(r"\d:\d\d\.\d\d")


def _filled(text: str) -> str:
    return SponsorNames().fill(text, **_SAMPLES)


def test_every_prototype_state_is_here():
    assert _PROTOTYPE_STATES | _NEW_STATES == set(STATES)
    assert len(STATES) == 61


def test_start_matches_the_brief():
    assert START == {"book": "s_boot", "board": "board", "list": "ls_offer", "hub": "hub"}


def test_every_transition_names_a_state():
    for name, state in STATES.items():
        for event, target in state.on.items():
            assert target in STATES, f"{name}.on[{event!r}] -> unknown state {target!r}"


def test_every_state_reaches_home():
    # A depth-first walk (frontier is a stack: last pushed, first popped) over every `on`
    # value, not just circle/cross -- a timeout or an ok chain gets there just as well.
    for start in STATES:
        seen = {start}
        frontier = [start]
        while frontier:
            current = frontier.pop()
            if current == "home":
                break
            for target in STATES[current].on.values():
                if target not in seen:
                    seen.add(target)
                    frontier.append(target)
        else:
            assert "home" in seen, f"{start} never reaches home"


def test_every_state_reaches_home_without_cross():
    # Ruling 7 (no traps): every state must still reach home using only circle presses and the
    # edges that fire on their own -- a non-phone call's on["ok"] (a phone step's "ok" needs a
    # Cross to resolve the call, so it is excluded) and on["timeout"] (every call's, phone or
    # not: a QR's own expiry is still automatic). racing has no automatic edge, only circle, and
    # that is enough: on={"circle": "home"} reaches home directly.
    for start in STATES:
        seen = {start}
        frontier = [start]
        while frontier:
            current = frontier.pop()
            if current == "home":
                break
            state = STATES[current]
            edges = []
            if "circle" in state.on:
                edges.append(state.on["circle"])
            if "timeout" in state.on:
                edges.append(state.on["timeout"])
            if "ok" in state.on and state.call is not None and not state.phone:
                edges.append(state.on["ok"])
            for target in edges:
                if target not in seen:
                    seen.add(target)
                    frontier.append(target)
        else:
            assert "home" in seen, f"{start} never reaches home without Cross"


def test_moods_are_known():
    for name, state in STATES.items():
        assert state.mood in MOODS, f"{name}.mood = {state.mood!r}"


def test_phone_states_have_a_call():
    for name, state in STATES.items():
        if state.phone:
            assert state.call is not None, f"{name} is a phone step with no call"


def test_only_the_ten_wired_steps_have_a_call():
    wired = {"id_scan": "idkit_scan", "id_confirm": "idkit_confirm", "id_verifying": "idkit_verify",
             "buy_check": "check_listing", "buy_pay": "pay", "buy_load": "load_ghost",
             "ls_scan": "approve_scan", "ls_approve": "approve", "ls_confirm": "approve", "ls_record": "record",
             "ls_arkiv": "publish"}
    for name, state in STATES.items():
        if name in wired:
            assert state.call == wired[name], name
        else:
            assert state.call is None, name


def test_call_states_carry_the_ruled_deadlines_and_events():
    # Ruling 8 re-points three of these timeouts to a failure state named for the step that
    # actually timed out (buy_check/buy_load no longer collapse into the "pay" step's buy_down;
    # ls_arkiv no longer collapses into the "record" step's ls_record_fail).
    expected = {
        "id_scan": (300000, "id_expired", "id_confirm"),
        "id_confirm": (300000, "id_expired", "id_verifying"),
        "id_verifying": (10000, "id_offline", "id_done"),
        "buy_check": (8000, "buy_check_fail", "buy_pay"),
        "buy_pay": (8000, "buy_down", "buy_load"),
        "buy_load": (8000, "buy_load_fail", "buy_done"),
        "ls_scan": (1200000, "ls_expired", "ls_approve"),
        "ls_approve": (1200000, "ls_expired", "ls_record"),
        "ls_confirm": (300000, "ls_expired", "ls_record"),
        "ls_record": (8000, "ls_record_fail", "ls_arkiv"),
        "ls_arkiv": (8000, "ls_publish_fail", "ls_done"),
    }
    for name, (deadline_ms, timeout_to, ok_to) in expected.items():
        state = STATES[name]
        assert state.deadline_ms == deadline_ms, name
        assert state.on["timeout"] == timeout_to, name
        assert state.on["ok"] == ok_to, name


def test_denial_events_carry_no_on_entry():
    # Reached by a sponsor's forced outcome (the failure name IS the next state), not by `on`.
    banned_events = {"deny", "expire", "nocred", "dup", "wrong", "mismatch", "reused", "scan", "approve"}
    for name, state in STATES.items():
        used = banned_events & set(state.on)
        assert not used, f"{name}.on has prototype event(s) {used}, should be ok/timeout"


def test_ls_cancel_keeps_its_call_for_a_late_approve():
    state = STATES["ls_cancel"]
    assert state.keep_call is True
    assert state.on["ok"] == "ls_late"
    assert state.on["cross"] == "ls_scan"
    assert state.on["circle"] == "home"
    assert state.mock_outcomes == (("Phone approves anyway", "ls_late"),)


def test_racing_only_has_circle_and_a_load_card():
    state = STATES["racing"]
    assert state.on == {"circle": "home"}
    assert state.card == {"t": "load", "h": "Racing {target}"}


def test_home_card_is_back_type():
    assert STATES["home"].card == {"t": "back", "h": "Back home"}


def test_down_and_busy_use_lowercase_sponsor_keys():
    for name, state in STATES.items():
        if state.down is not None:
            assert state.down in ("world", "board", "third"), name
        if state.busy is not None:
            assert state.busy in ("world", "board", "third"), name


def test_card_types_are_from_the_allowed_set():
    allowed = {"status", "qr", "wait", "load", "done", "no", "warn", "time", "back", "board",
               "target", "offer", "result", "toast", "hub", "book", "listings"}
    for name, state in STATES.items():
        assert state.card["t"] in allowed, f"{name}.card['t'] = {state.card['t']!r}"


def test_kind_is_one_of_the_three_or_blank():
    for name, state in STATES.items():
        assert state.kind in ("", "ok", "no", "warn"), name


def test_fx_is_one_of_the_two_or_blank():
    for name, state in STATES.items():
        assert state.fx in ("", "confetti", "coin"), name


def test_new_state_kinds_match_the_fix_round():
    expected = {
        "no_board": "warn", "no_run": "warn", "start_over": "warn",
        "race_unverified": "no", "nobody_ahead": "ok",
        "buy_check_fail": "no", "buy_load_fail": "no", "ls_publish_fail": "warn",
        "buy_late": "ok", "own_result": "ok", "own_again": "",
    }
    for name, kind in expected.items():
        assert STATES[name].kind == kind, name


def test_new_state_transitions_match_the_ruling():
    expected = {
        "hub": {"circle": "home"},
        "need_book": {"cross": "s_boot", "circle": "hub"},
        "no_board": {"cross": "hub", "circle": "hub"},
        "no_run": {"cross": "hub", "circle": "hub"},
        # Ruling 7: a race (fresh or a re-race) crosses into `racing`, never straight to a
        # charge -- buy_done is what racing itself crosses into once it resolves.
        "nobody_ahead": {"cross": "racing", "circle": "hub"},
        "race_lost": {"cross": "racing", "circle": "hub"},
        "race_unfinished": {"cross": "racing", "circle": "hub"},
        "race_unverified": {"cross": "racing", "circle": "hub"},
        "book_view": {"cross": "hub", "circle": "hub"},
        "listings_view": {"cross": "hub", "circle": "hub"},
        "start_over": {"cross": "hub", "circle": "hub"},
        "board_new": {"cross": "target", "circle": "hub"},
        "buy_check_fail": {"cross": "buy_check", "circle": "hub"},
        "buy_load_fail": {"cross": "buy_load", "circle": "hub"},
        "ls_publish_fail": {"cross": "ls_arkiv", "circle": "home"},
        "buy_late": {"cross": "buy_load", "circle": "hub"},
        "own_result": {"cross": "ls_offer", "circle": "hub"},
        "own_again": {"cross": "racing", "circle": "hub"},
    }
    for name, on in expected.items():
        assert STATES[name].on == on, name


def test_buy_down_listens_on_for_a_late_payment():
    # Ruling 10b: a payment that lands after its timeout, while buy_down is still showing,
    # moves on to buy_late instead of leaving "nothing was paid" on screen.
    state = STATES["buy_down"]
    assert state.keep_call is True
    assert state.on["ok"] == "buy_late"
    late = STATES["buy_late"]
    assert (late.steps, late.at, late.card["t"], late.card["h"]) == (
        STATES["buy_pay"].steps, 1, "done", "Payment landed late")


def test_ruling_7_states_get_a_circle_to_hub():
    for name in ("board", "id_done", "id_signed", "buy_done", "ls_done", "sale"):
        assert STATES[name].on["circle"] == "hub", name


def test_hub_card_rows_end_with_start_over():
    rows = STATES["hub"].card["rows"]
    assert rows[-1] == "Start over (mock)"
    assert len(rows) == 5


def test_prototype_states_with_what_keep_a_non_empty_what():
    for name in _PROTOTYPE_STATES_WITH_WHAT:
        assert STATES[name].card.get("what"), f"{name} should have a non-empty what"


def test_the_new_end_cards_say_what_happened_and_what_is_next():
    # The states the prototype never needed get the same detail as its own: a line under the
    # heading and label/value rows, not a bare heading and icon.
    for name in ("need_book", "no_board", "no_run", "nobody_ahead", "race_unfinished",
                 "race_unverified", "start_over"):
        card = STATES[name].card
        assert card.get("rows") and card.get("what"), name
    # A faster runner who does not sell can still be above you: you are not always on top.
    assert STATES["nobody_ahead"].card["h"] == "Nobody ahead sells"


def test_the_record_book_intro_suits_any_time_of_day():
    # "Record book needed" leads here at any hour of a booth day.
    assert not any(word in STATES["s_boot"].say for word in ("Morning", "Afternoon", "Evening"))


def test_pb_says_how_to_start_the_game_before_the_first_race():
    # Three of the five arcade games start from their title only on START, which a DualSense calls OPTIONS.
    assert "*OPTIONS*" in STATES["buy_done"].say


def test_the_listings_line_reads_right_for_one_sale():
    assert "{sold} copies" not in STATES["listings_view"].say


def test_no_banned_words():
    # copy_texts includes mock_outcomes labels (ls_cancel's "Phone approves anyway"), so this
    # covers those too, not just say/h/rows/what.
    word_re = {word: re.compile(r"\b" + re.escape(word) + r"\b") for word in BANNED_WORDS}
    for name, state in STATES.items():
        for text in copy_texts(state):
            filled = _filled(text).lower()
            for word, pattern in word_re.items():
                assert not pattern.search(filled), f"{name}: {text!r} uses banned word {word!r}"


def test_no_literal_sponsor_names():
    # "World App", "IDKit" and "Agent Pass" are World's own product names and stay literal;
    # every other mention of a sponsor must be a placeholder, so swapping a sponsor (Hedera is
    # not confirmed as the third one) is a one-line edit, not a text hunt. Scanned via
    # copy_texts, so this also covers `what` rows and `mock_outcomes` labels, not just say/h/rows.
    world_outside_app = re.compile(r"\bWorld\b(?!\s+App\b)")
    for name, state in STATES.items():
        for text in copy_texts(state):
            assert "Hedera" not in text, f"{name}: {text!r}"
            assert "Arkiv" not in text, f"{name}: {text!r}"
            assert not world_outside_app.search(text), f"{name}: {text!r}"


def test_no_game_specific_literals():
    # Ruling 6: per-run values are placeholders, not the prototype's illustrative demo data.
    # "Marine Drive" is always {game}; a HashScan-style id or a literal run time (h:mm.ss) would
    # both be false claims the handler cannot actually back once a different game or a real run
    # is behind the screen.
    for name, state in STATES.items():
        for text in copy_texts(state):
            assert "Marine Drive" not in text, f"{name}: {text!r}"
            assert "HashScan" not in text, f"{name}: {text!r}"
            assert not _TIME_LITERAL_RE.search(text), f"{name}: {text!r}"


def test_placeholders_all_fill_with_no_braces_left():
    for name, state in STATES.items():
        for text in copy_texts(state):
            filled = _filled(text)
            assert "{" not in filled and "}" not in filled, f"{name}: {text!r} -> {filled!r}"


def test_placeholders_constant_matches_what_the_table_uses():
    expected = {
        "world", "board", "third", "pay_rail", "record_rail", "target", "target_time", "gap",
        "rank", "new_rank", "run_time", "price", "budget_left", "book", "other_book", "code",
        "wallet", "buyer", "ghost_look", "split", "game", "runs", "sold", "jti", "listing_days",
        "ghost_kept", "credential", "approve_how", "approve_via",
    }
    assert PLACEHOLDERS == expected


def test_listed_and_the_record_book_cross_to_the_hub_by_default():
    # Ruling 17: Cross on "Listed" never fakes a sale (a sale only comes from Home), and the
    # record-book flow's Cross goes where the flow engine remembers, else the hub.
    assert STATES["ls_done"].on == {"cross": "hub", "circle": "hub"}
    for name in ("id_done", "id_signed"):
        assert STATES[name].on == {"cross": "hub", "circle": "hub"}, name
        assert "board" not in STATES[name].say, name
    no_board = STATES["no_board"]
    assert no_board.say == "There is no board for *{game}* yet. Pick a game on Home and press Triangle."
    assert no_board.card["h"] == "No board yet"


def test_failure_copy_promises_no_retry_the_mock_never_makes():
    # Ruling 18: nothing retries in the background or later on its own; Cross is the retry.
    record, publish, down = STATES["ls_record_fail"], STATES["ls_publish_fail"], STATES["buy_down"]
    assert record.say == ("You approved, but {record_rail} is not answering, so nothing is listed yet. "
                          "Cross to try again.")
    assert record.card["what"] == (("Listed", "not yet"), ("Your approval", "kept for this listing"),
                                   ("Next", "Cross tries again"))
    assert publish.say == ("Your listing is recorded on {record_rail}, but {board} is not answering. "
                           "Cross to try listing again.")
    assert publish.card["what"] == (("Listed", "not yet"), ("Next", "Cross tries again"))
    assert down.say == ("{third} is not answering, so *nothing was paid*. Race your own best for now, "
                        "or try again later.")
    assert dict(down.card["what"])["Next"] == "try again later"
    for name, state in STATES.items():
        for text in copy_texts(state):
            for promise in ("background", "keep trying", "I will try", "Retrying"):
                assert promise not in text, (name, text)


def test_mock_load_ghost_down_failure_matches_buy_load_fail():
    # mock.py's _DOWN_FAILURE must point at a real state; this is the one Finding 6 fixed.
    from arca_launcher.handler.mock import MockSponsors

    class _FixedClock:
        def __call__(self):
            return 0

    sponsors = MockSponsors(clock_ms=_FixedClock())
    sponsors.set_down("third", True)
    result = sponsors.begin("load_ghost", {}).poll()
    assert result.ok is False
    assert result.failure == "buy_load_fail"
    assert result.failure in STATES
