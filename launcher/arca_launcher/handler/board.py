"""The mock board around the one real ghost: each game has exactly one real ghost (its shipped
test log), shown as one mock runner (RIA) at the log's real time. The other five mock runners
are offsets from that same log; only RIA's ghost can ever be bought in mock mode, so "listed"
(shown on the board as selling) and "sells" (actually purchasable) are tracked separately."""
from dataclasses import dataclass

MOCK_NAMES = ("KIRAN", "MEERA", "RIA", "ARJUN", "ZOYA", "DEV")
SELLER = "RIA"  # the log runner: the only ghost that can be bought in mock mode

# Offsets from the log's own frame count. Runners ahead of this list (KIRAN, MEERA) are faster
# than the log; runners after it (ARJUN, ZOYA, DEV) are slower.
_OFFSETS = {"KIRAN": -420, "MEERA": -150, "RIA": 0, "ARJUN": 170, "ZOYA": 400, "DEV": 900}

_SLOWER_THAN_LOG = ("ARJUN", "ZOYA", "DEV")


@dataclass(frozen=True)
class Row:
    rank: int
    name: str
    frames: int | None
    you: bool
    listed: bool
    sells: bool
    target: bool


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
    return False, False  # faster than the log, or YOU: never shown as selling


def build(log_frames: int | None, best_frames: int | None) -> Board:
    if log_frames is None:
        return Board(rows=(), target=None, case="no_board")

    entries = []
    for name in MOCK_NAMES:
        listed, sells = _listed_and_sells(name)
        entries.append((name, log_frames + _OFFSETS[name], False, listed, sells))
    entries.append(("YOU", best_frames, True, False, False))

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
            target=(name == is_target_name))
        for rank, (name, frames, you, listed, sells) in enumerate(entries, start=1)
    )
    target = next((row for row in rows if row.target), None)
    return Board(rows=rows, target=target, case=case)
