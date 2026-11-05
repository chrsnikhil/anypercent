"""Tests for the mock board (handler/board.py): one real ghost (the game's shipped test log,
played by RIA) surrounded by mock runners who never sell. Field order on Row is pinned by a
controller ruling that amends the brief's own "YOU directly below RIA" claim, which contradicts
the brief's own offsets (ARJUN at log+170 sits between RIA and a YOU at log+214)."""
from arca_launcher.handler.board import MOCK_NAMES, SELLER, Board, Row, build


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
    assert len(board.rows) == len(MOCK_NAMES) + 1  # the six mock runners plus YOU


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
        "rank", "name", "frames", "you", "listed", "sells", "target",
    ]
