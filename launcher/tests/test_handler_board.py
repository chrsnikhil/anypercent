"""Tests for the mock board (handler/board.py): one real ghost (the game's shipped test log,
played by RIA) surrounded by mock runners who never sell. Field order on Row is pinned by a
controller ruling that amends the brief's own "YOU directly below RIA" claim, which contradicts
the brief's own offsets (ARJUN at log+170 sits between RIA and a YOU at log+214)."""
from arca_launcher.handler.board import (BOT, MOCK_NAMES, SELLER, Board, Row, build, build_real, humans_only, mark_you,
                                         ordinal, tier_counts)
from arca_launcher.handler.sponsors import RunRow


def test_target_is_the_log_runner_when_you_are_behind():
    board = build(6076, 6290)
    assert board.case == "ok"
    assert board.target is not None
    assert board.target.name == "RIA"
    assert board.target.sells is True
    assert board.target.listed is True

    ria_rank = next(row.rank for row in board.rows if row.name == "RIA")
    you_rank = next(row.rank for row in board.rows if row.you)
    assert you_rank > ria_rank

    arjun = next(row for row in board.rows if row.name == "ARJUN")
    assert arjun.listed is True
    assert arjun.sells is False


def test_fresh_visitor_sits_at_the_bottom_with_no_time():
    board = build(6076, None)
    assert board.case == "no_best"
    assert board.rows[-1].you is True
    assert board.rows[-1].frames is None
    assert board.target is not None
    assert board.target.name == "RIA"


def test_ahead_of_the_log_runner_means_nobody_ahead_sells():
    board = build(6076, 5900)
    assert board.case == "nobody_ahead"
    assert board.target is None
    kiran = next(row for row in board.rows if row.name == "KIRAN")
    meera = next(row for row in board.rows if row.name == "MEERA")
    assert kiran.sells is False
    assert meera.sells is False
    assert kiran.listed is False
    assert meera.listed is False


def test_no_log_means_no_board():
    board = build(None, 6000)
    assert board.case == "no_board"
    assert board.rows == ()
    assert board.target is None


def test_ranks_are_one_to_n():
    board = build(6076, 6290)
    assert [row.rank for row in board.rows] == list(range(1, len(board.rows) + 1))
    assert len(board.rows) == len(MOCK_NAMES) + 1  # the seven mock runners (one of them a bot) plus YOU


def test_tie_puts_you_above_ria_and_counts_as_nobody_ahead():
    board = build(6076, 6076)
    assert board.case == "nobody_ahead"
    assert board.target is None
    ria_rank = next(row.rank for row in board.rows if row.name == "RIA")
    you_rank = next(row.rank for row in board.rows if row.you)
    assert you_rank < ria_rank


def test_only_ria_sells_and_is_listed():
    board = build(6076, 6290)
    for row in board.rows:
        if row.name == SELLER:
            assert row.sells is True
            assert row.listed is True
        else:
            assert row.sells is False


def test_runners_slower_than_the_log_are_listed_but_do_not_sell():
    board = build(6076, 6290)
    for name in ("ARJUN", "ZOYA", "DEV"):
        row = next(r for r in board.rows if r.name == name)
        assert row.listed is True
        assert row.sells is False


def test_runners_faster_than_the_log_are_not_listed():
    board = build(6076, 6290)
    for name in ("KIRAN", "MEERA"):
        row = next(r for r in board.rows if r.name == name)
        assert row.listed is False
        assert row.sells is False


def test_you_is_never_listed_or_selling():
    board = build(6076, 6290)
    you = next(r for r in board.rows if r.you)
    assert you.listed is False
    assert you.sells is False


def test_mock_runner_frames_follow_the_offsets_from_the_log():
    board = build(6076, 6290)
    frames = {row.name: row.frames for row in board.rows}
    assert frames["KIRAN"] == 6076 - 420
    assert frames["MEERA"] == 6076 - 150
    assert frames["RIA"] == 6076
    assert frames["ARJUN"] == 6076 + 170
    assert frames["ZOYA"] == 6076 + 400
    assert frames["DEV"] == 6076 + 900


def test_only_one_row_is_you():
    board = build(6076, 6290)
    assert sum(1 for row in board.rows if row.you) == 1


def test_at_most_one_row_is_the_target():
    board = build(6076, 6290)
    assert sum(1 for row in board.rows if row.target) == 1
    target_row = next(row for row in board.rows if row.target)
    assert target_row == board.target


def test_row_field_order_matches_the_ruling():
    board = build(6076, 6290)
    row = board.rows[0]
    assert [f.name for f in __import__("dataclasses").fields(row)] == [
        "rank", "name", "frames", "you", "listed", "sells", "target", "human", "credential", "key", "listing",
    ]
    assert (row.key, row.listing) == (None, None)                      # the mock board's rows are on no chain


# ---- HUMAN: one World ID, one record book --------------------------------------------------------------------------

def test_the_mock_runners_are_human_but_the_bot_is_not():
    board = build(6076, 6290)
    rows = {row.name: row for row in board.rows}
    for name in ("KIRAN", "MEERA", "RIA", "ARJUN", "ZOYA", "DEV"):
        assert rows[name].human is True and rows[name].credential in ("Orb", "Selfie Check"), name
    bot = rows[BOT]
    assert (bot.human, bot.credential, bot.listed, bot.sells, bot.target) == (False, None, False, False, False)
    assert bot.frames == 6076 + 650 and bot.rank == rows["ZOYA"].rank + 1   # beside the human runs, on screen
    assert rows["YOU"].human is False                                   # no World proof behind the console yet


def test_with_world_real_no_made_up_runner_is_human():
    """A real World never vouches for a mock runner: only rows a World proof stands behind are HUMAN."""
    board = build(6076, 6290, mock_humans=False)
    assert not any(row.human for row in board.rows)
    assert all(row.credential is None for row in board.rows)


def test_you_are_human_only_with_a_world_proof_behind_your_book():
    board = build(6076, 6290, you_human="Orb", mock_humans=False)
    you = next(row for row in board.rows if row.you)
    assert (you.human, you.credential) == (True, "Orb")
    assert [row.name for row in board.rows if row.human] == ["YOU"]
    rows = mark_you(board.rows, None)                                   # the book is gone (Start over)
    assert not any(row.human for row in rows)
    rows = mark_you(rows, "Selfie Check")
    assert [(row.name, row.credential) for row in rows if row.human] == [("YOU", "Selfie Check")]
    assert [row.rank for row in rows] == [row.rank for row in board.rows]   # nothing else moves
    assert mark_you((), "Orb") == ()


def test_you_still_rank_where_you_did():
    board = build(6070, 6290)
    assert next(row.rank for row in board.rows if row.you) == 5
    assert board.target.name == "RIA" and board.target.rank == 3


# ---- the real board: Arkiv's run rows (build_real) ------------------------------------------------------------------

def run(name, frames, listed=False, human=None, credential=None, book=True, key=None, pay_to=None):
    """A run row as arkiv_rpc decodes it: name is the book (ANY-...) or, with book=False, an open-tier label; pay_to the
    Hedera account its listing names."""
    human = book if human is None else human
    return RunRow(key=key or "0x%064x" % (hash((name, frames)) & (2 ** 256 - 1)), game="MDGP", title="MARINE DRIVE GP",
                  frames=frames, runner=name.lower().ljust(16, "0")[:16], book=name if book else None,
                  label=None if book else name, human=human, credential=(credential or "Orb") if human else None,
                  log_h=("%064x" % frames), rules=4, expires_block=8000000,
                  listing=("0x%064x" % (frames + 1)) if listed else None, price="0.1" if listed else None,
                  pay_to=pay_to if listed else None)


ROWS = (run("ANY-K2P", 6000), run("ANY-7QZ", 6100, listed=True), run("TEAM", 6150, book=False),
        run("ANY-K2P", 6180, listed=True), run("ANY-2KD", 6200, listed=True), run("BOT-7", 6250, book=False),
        run("ANY-9MX", 6400, listed=True))


def names(board):
    return [row.name for row in board.rows]


def test_one_row_per_runner_the_fastest_kept():
    board = build_real(ROWS, 6290, None, None)
    assert names(board) == ["ANY-K2P", "ANY-7QZ", "TEAM", "ANY-2KD", "BOT-7", "YOU", "ANY-9MX"]
    k2p = board.rows[0]
    assert (k2p.frames, k2p.listed, k2p.sells) == (6000, False, False)  # her fastest is not listed; her slower one was
    assert [row.rank for row in board.rows] == list(range(1, 8))
    assert all(row.key for row in board.rows if not row.you)


def test_the_target_is_the_listed_run_just_ahead_of_you():
    board = build_real(ROWS, 6290, None, None)
    assert board.case == "ok" and board.target.name == "ANY-2KD" and board.target.frames == 6200
    assert board.target.listing == ROWS[4].listing and board.target.key == ROWS[4].key
    assert [row.name for row in board.rows if row.target] == ["ANY-2KD"]
    assert [row.name for row in board.rows if row.sells] == ["ANY-7QZ", "ANY-2KD", "ANY-9MX"]
    assert build_real(ROWS, 6150, None, None).target.name == "ANY-7QZ"   # TEAM is ahead, but sells no ghost
    assert build_real(ROWS, 6200, None, None).target.name == "ANY-7QZ"   # a tie is not ahead


def test_a_new_visitor_races_the_slowest_listed_run():
    board = build_real(ROWS, None, None, None)
    assert board.case == "no_best" and board.target.name == "ANY-9MX"
    assert board.rows[-1].you and board.rows[-1].frames is None


def test_nobody_ahead_and_no_board():
    assert build_real(ROWS, 6050, None, None).case == "nobody_ahead"
    assert build_real(ROWS, 6050, None, None).target is None
    unlisted = tuple(r for r in ROWS if not r.listing)
    assert build_real(unlisted, 6290, None, None).case == "nobody_ahead"
    assert build_real(unlisted, None, None, None).case == "nobody_ahead"   # nothing to buy: race your own
    empty = build_real((), 6290, "ANY-7QZ", "Orb")
    assert (empty.case, empty.rows, empty.target) == ("no_board", (), None)


def test_you_are_the_better_of_your_local_best_and_your_own_row():
    board = build_real(ROWS, 6290, "ANY-7QZ", "Orb")                   # your book's run (6100) beats the local best
    you = next(row for row in board.rows if row.you)
    assert names(board).count("ANY-7QZ") == 0 and you.frames == 6100 and you.rank == 2
    assert (you.listed, you.sells, you.key) == (True, False, ROWS[1].key)   # your own listing: never yours to buy
    assert board.case == "nobody_ahead"                                  # K2P's 6000 is not listed
    board = build_real(ROWS, 5900, "ANY-7QZ", "Orb")                   # a local best faster than the board
    you = board.rows[0]
    assert you.you and you.frames == 5900 and not you.listed and you.key is None
    assert names(board).count("ANY-7QZ") == 0


def test_human_comes_from_the_rows():
    board = build_real(ROWS, 6290, None, None)
    rows = {row.name: row for row in board.rows}
    assert [name for name, row in rows.items() if row.human] == ["ANY-K2P", "ANY-7QZ", "ANY-2KD", "ANY-9MX"]
    assert rows["ANY-2KD"].credential == "Orb" and rows["TEAM"].credential is None and not rows["BOT-7"].human
    assert not rows["YOU"].human                                         # no World proof behind the console's book
    plain = (run("ANY-5RT", 6000, human=False),)                         # a booked row that says not human: not human
    assert not build_real(plain, 6290, None, None).rows[0].human
    you = next(r for r in build_real(ROWS, 6290, "ANY-4HJ", "Orb").rows if r.you)
    assert (you.human, you.credential) == (True, "Orb")                  # a real World proof behind the book
    you = next(r for r in build_real(ROWS, 6290, "ANY-7QZ", None).rows if r.you)
    assert (you.human, you.credential) == (True, "Orb")                  # your own row says so


def test_rows_from_arkiv_are_never_mock_runners():
    board = build_real(ROWS, 6290, None, None)
    assert not set(names(board)) & (set(MOCK_NAMES) - {BOT})             # BOT-7 here is a real open-tier label


# ---- with Hedera real: PB pays only the account a listing names ----------------------------------------------------

PAYS = (run("ANY-K2P", 6000), run("ANY-7QZ", 6100, listed=True, pay_to="0.0.7001"), run("TEAM", 6150, book=False),
        run("ANY-2KD", 6200, listed=True), run("ANY-9MX", 6400, listed=True, pay_to="0.0.9001"))


def test_a_listing_without_an_account_shows_listed_but_never_sells():
    board = build_real(PAYS, 6290, None, None, need_pay_to=True)
    rows = {row.name: row for row in board.rows}
    assert (rows["ANY-2KD"].listed, rows["ANY-2KD"].sells, rows["ANY-2KD"].target) == (True, False, False)
    assert [row.name for row in board.rows if row.sells] == ["ANY-7QZ", "ANY-9MX"]
    assert board.case == "ok" and board.target.name == "ANY-7QZ"        # 2KD is closer, but nobody can pay her
    assert build_real(PAYS, 6290, None, None).target.name == "ANY-2KD"  # Hedera mocked: any listing sells, as before
    assert build_real(PAYS, None, None, None, need_pay_to=True).target.name == "ANY-9MX"   # the slowest that sells
    unpaid = tuple(r for r in PAYS if r.pay_to is None)
    board = build_real(unpaid, 6290, None, None, need_pay_to=True)
    assert board.case == "nobody_ahead" and board.target is None and any(row.listed for row in board.rows)
    assert names(build_real(PAYS, 6290, None, None, need_pay_to=True)) == names(build_real(PAYS, 6290, None, None))


def test_your_own_listing_with_an_account_is_still_never_yours_to_buy():
    board = build_real(PAYS, 6290, "ANY-7QZ", "Orb", need_pay_to=True)
    you = next(row for row in board.rows if row.you)
    assert (you.frames, you.listed, you.sells, you.target) == (6100, True, False, False)
    assert board.case == "nobody_ahead"                                 # K2P's 6000 is not listed


# ---- tiers: HUMAN, BOT, OPEN; Humans only ----------------------------------------------------------------------------

def test_every_row_has_a_tier_and_a_bot_is_never_human():
    rows = ROWS + (run("BOT-A2", 6230, book=False, listed=True, human=True, pay_to="0.0.7700001"),)
    board = build_real(rows, 6290, "ANY-6PS", "Orb")
    tiers = {row.name: row.tier for row in board.rows}
    assert tiers == {"ANY-K2P": "human", "ANY-7QZ": "human", "TEAM": "open", "ANY-2KD": "human", "BOT-A2": "bot",
                     "BOT-7": "bot", "YOU": "human", "ANY-9MX": "human"}
    bot = next(row for row in board.rows if row.name == "BOT-A2")
    assert not bot.human and bot.credential is None and bot.sells    # its row said human: still never HUMAN
    assert tier_counts(board.rows) == {"human": 5, "bot": 2, "open": 1}
    you = next(row for row in build_real(rows, 6290, None, None).rows if row.you)
    assert you.tier == "open"                                        # YOU without a World proof behind the book


def test_humans_only_keeps_you_and_the_human_rows_and_never_moves_the_target():
    board = build_real(ROWS + (run("BOT-A2", 6230, book=False, listed=True),), 6290, None, None)
    shown = humans_only(board.rows)
    assert [row.name for row in shown] == ["ANY-K2P", "ANY-7QZ", "ANY-2KD", "YOU", "ANY-9MX"]
    assert [row.rank for row in shown] == [1, 2, 4, 7, 8]            # the full board's places
    assert board.target.name == "BOT-A2"                             # the target is the full board's
    mock = build(6070, 6290)
    assert [row.name for row in humans_only(mock.rows)] == ["KIRAN", "MEERA", "RIA", "ARJUN", "YOU", "ZOYA", "DEV"]
    assert tier_counts(mock.rows) == {"human": 6, "bot": 1, "open": 1}


def test_ordinal():
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101, 111)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "101st", "111th"]
    assert ordinal(None) == ""
