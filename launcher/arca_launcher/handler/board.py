"""The board PB shows: the real one from Arkiv's run rows (build_real) when Arkiv is real, else the mock one (build).

The mock board around the one real ghost: each game has exactly one real ghost (its shipped
test log), shown as one mock runner (RIA) at the log's real time. The other mock runners are
offsets from that same log; only RIA's ghost can ever be bought in mock mode, so "listed"
(shown on the board as selling) and "sells" (actually purchasable) are tracked separately.

HUMAN: a run whose record book World verified (one World ID, one record book) carries `human`
and, when known, the credential World checked. The real board (Arkiv) will carry the same
attribute on each run row, written by the checker from the book's World status. Here the mock
runners are human (one scripted bot, with no book, is not) only while World itself is mocked:
a real World never vouches for a made-up runner. YOU are human only with a real World proof
behind the console's record book (`mark_you`)."""
import dataclasses
from dataclasses import dataclass

BOT = "BOT-7"   # a scripted run: replay-verified like any other, but no record book, so not human
MOCK_NAMES = ("KIRAN", "MEERA", "RIA", "ARJUN", "ZOYA", "DEV", BOT)
SELLER = "RIA"  # the log runner: the only ghost that can be bought in mock mode

# Offsets from the log's own frame count. Runners ahead of this list (KIRAN, MEERA) are faster
# than the log; runners after it (ARJUN, ZOYA, DEV, the bot) are slower. The bot sits among the
# runs just behind a typical YOU, so the board's window shows it beside the human ones.
_OFFSETS = {"KIRAN": -420, "MEERA": -150, "RIA": 0, "ARJUN": 170, "ZOYA": 400, BOT: 650, "DEV": 900}

_SLOWER_THAN_LOG = ("ARJUN", "ZOYA", "DEV")

# The credential World checked for each mock runner's book; the bot has no book.
_MOCK_HUMANS = {"KIRAN": "Orb", "MEERA": "Selfie Check", "RIA": "Orb", "ARJUN": "Selfie Check", "ZOYA": "Orb",
                "DEV": "Orb"}


@dataclass(frozen=True)
class Row:
    rank: int
    name: str
    frames: int | None
    you: bool
    listed: bool
    sells: bool
    target: bool
    human: bool = False             # a World-verified record book stands behind this run
    credential: str | None = None   # what World checked ("Orb", "Selfie Check"), when known
    key: str | None = None          # the real board's run row on Arkiv (None: a mock runner, or YOU's local best)
    listing: str | None = None      # the live listing that offers this run's ghost, on the real board


@dataclass(frozen=True)
class Board:
    rows: tuple[Row, ...]
    target: Row | None
    case: str


def _listed_and_sells(name: str) -> tuple[bool, bool]:
    if name == SELLER:
        return True, True
    if name in _SLOWER_THAN_LOG:
        return True, False
    return False, False  # faster than the log, the bot (no book to list with), or YOU: never selling


def build(log_frames: int | None, best_frames: int | None, you_human: str | None = None,
          mock_humans: bool = True) -> Board:
    """you_human: the credential World checked for the console's record book, when a real World
    proof stands behind it (else None: YOU are not human). mock_humans: the mock runners carry
    their HUMAN marks; the caller passes False once World is real."""
    if log_frames is None:
        return Board(rows=(), target=None, case="no_board")

    entries = []
    for name in MOCK_NAMES:
        listed, sells = _listed_and_sells(name)
        credential = _MOCK_HUMANS.get(name) if mock_humans else None
        entries.append((name, log_frames + _OFFSETS[name], False, listed, sells, credential))
    entries.append(("YOU", best_frames, True, False, False, None))

    # Stable sort by frames; a tie between YOU and a mock runner puts YOU first. YOU with no
    # best time sorts last, since no mock runner's frame count is infinite.
    entries.sort(key=lambda e: (e[1] if e[1] is not None else float("inf"), 0 if e[2] else 1))

    if best_frames is None:
        case = "no_best"
        is_target_name = SELLER
    elif best_frames > log_frames:
        case = "ok"
        is_target_name = SELLER
    else:
        case = "nobody_ahead"
        is_target_name = None

    rows = tuple(
        Row(rank=rank, name=name, frames=frames, you=you, listed=listed, sells=sells,
            target=(name == is_target_name), human=credential is not None, credential=credential)
        for rank, (name, frames, you, listed, sells, credential) in enumerate(entries, start=1)
    )
    rows = mark_you(rows, you_human)
    target = next((row for row in rows if row.target), None)
    return Board(rows=rows, target=target, case=case)


def build_real(rows, best_frames: int | None, you_book: str | None, you_human: str | None) -> Board:
    """The board from Arkiv's run rows (sponsors.RunRow, fastest first as Q1 reads them), the spec's way:

    - one row per runner (a book, or an open-tier label): the first, which is the fastest;
    - listed: a live listing offers that run; sells: listed and not YOU;
    - YOU: the better of the local best and YOU's own row on Arkiv (book == you_book);
    - the target: the listed run with the largest time below YOU's (no time from YOU: the slowest listed run); none
      ahead is "nobody_ahead"; no run rows at all is "no_board".

    HUMAN and its credential come from each row's own fields. YOU's come from YOU's own row when the board shows it,
    else from you_human (the credential World checked for the console's book, with a real World proof behind it)."""
    if not rows:
        return Board(rows=(), target=None, case="no_board")
    mine, others, seen = None, [], set()
    for run in sorted(rows, key=lambda r: r.frames):        # stable: Q1's own order among equal times
        if you_book is not None and run.book == you_book:
            mine = mine or run
            continue
        name = run.book or run.label
        if name not in seen:
            seen.add(name)
            others.append(run)
    you_run = mine if mine is not None and (best_frames is None or mine.frames <= best_frames) else None
    you_frames = you_run.frames if you_run is not None else best_frames

    target = None
    for run in others:                                      # fastest first: the last that qualifies is the target
        if run.listing is not None and (you_frames is None or run.frames < you_frames):
            target = run
    case = "nobody_ahead" if target is None else "no_best" if you_frames is None else "ok"

    entries = [(run.book or run.label, run.frames, False, run) for run in others]
    entries.append(("YOU", you_frames, True, you_run))
    entries.sort(key=lambda e: (e[1] if e[1] is not None else float("inf"), 0 if e[2] else 1))
    out = []
    for rank, (name, frames, you, run) in enumerate(entries, start=1):
        listed = run is not None and run.listing is not None
        if you and run is None:
            human, credential = you_human is not None, you_human
        else:
            human, credential = run.human, run.credential if run.human else None
        out.append(Row(rank=rank, name=name, frames=frames, you=you, listed=listed, sells=listed and not you,
                       target=run is not None and run is target, human=human, credential=credential,
                       key=run.key if run is not None else None, listing=run.listing if run is not None else None))
    rows_out = tuple(out)
    return Board(rows=rows_out, target=next((row for row in rows_out if row.target), None), case=case)


def mark_you(rows, you_human: str | None):
    """rows with YOU's HUMAN mark set from the console's record book: the credential World checked
    when a real World proof stands behind it, else None (not human). Nothing else changes."""
    return tuple(dataclasses.replace(row, human=you_human is not None, credential=you_human) if row.you else row
                 for row in rows)
