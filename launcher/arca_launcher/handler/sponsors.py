"""The sponsor interface: the shapes every mocked step and outcome travels through. The real
World, Arkiv and Hedera adapters built at the hackathon implement this same protocol so the
flow engine and views never change; this module holds no behaviour, only the types.
"""
import re
from dataclasses import dataclass, field
from typing import Protocol

# A seller's Hedera account as a listing names it: a plain `0.0.N` id, the only form x402 pays (never an EVM alias).
PAY_TO = re.compile(r"0\.0\.[0-9]{1,10}")
# A listing's LISTING message on Hedera as its row names it (hcs): "<topic>/<seq>", as the web board reads it.
HCS_MSG = re.compile(r"(0\.0\.[0-9]{1,10})/([0-9]{1,20})")
BOOK = re.compile(r"ANY-[A-Z0-9]{3,8}")              # a record book's id, as the bridge makes them
HOUSE_LABEL = re.compile(r"BOT-[A-Z]{1,2}[1-8]")     # a house BOT ghost's label: a program's run, never a person's


@dataclass(frozen=True)
class SponsorNames:
    """One small table copy pulls sponsor names and rails from, so swapping a sponsor (Hedera
    is not confirmed as the third one) is a one-line edit, not a text hunt."""
    world: str = "World"
    board: str = "Arkiv"
    third: str = "Hedera"
    pay_rail: str = "x402 on Hedera"
    record_rail: str = "Hedera"

    def fill(self, text: str, **extra) -> str:
        return text.format(world=self.world, board=self.board, third=self.third,
                            pay_rail=self.pay_rail, record_rail=self.record_rail, **extra)


STEPS = ("status", "idkit_scan", "idkit_confirm", "idkit_verify", "check_listing", "pay", "load_ghost",
         "approve_scan", "approve", "record", "publish", "sales", "scout")

# Real-adapter timeouts the flow engine enforces (Global Constraints). Phone steps have none
# here: their deadline is the QR's own expiry, carried on Call.info["expires_s"].
TIMEOUT_MS = {"idkit_verify": 10000, "pay": 8000, "record": 8000, "publish": 8000,
              "check_listing": 8000, "load_ghost": 8000, "scout": 12000}


@dataclass(frozen=True)
class Result:
    ok: bool
    failure: str | None = None
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Outcome:
    """One row of a step's outcome list (Square), already filled through SponsorNames.
    `late` marks the "Paid late" row on `pay`: forcing it carries a late receipt even though
    its failure name ("buy_down") is shared with the plain "Hedera down" row, so the failure
    name alone can never tell the two apart."""
    label: str
    failure: str
    late: bool = False


@dataclass(frozen=True)
class RunRow:
    """One checked run on Arkiv's board: an `anypercent.run` row our checker created, with its live listing when it
    has one. book is the record book (None on an open-tier row, which carries a label instead); human and credential
    are the row's own fields, the only source of a HUMAN badge. expires_block is the row's `$expiresAt`; price is
    the listing's price in USDC as Arkiv holds it (a decimal string such as "0.1"); pay_to the seller's Hedera account
    the listing names (PAY_TO), None on a listing written without one: listed, but not for sale. splits: the run's lap
    times in frames (s1..s4 on its row: MDGP's laps), only when they add up to its frames; None on a row without. hcs:
    the listing's LISTING message on Hedera (HCS_MSG, "<topic>/<seq>"), None on a listing written without one."""
    key: str
    game: str
    title: str
    frames: int
    runner: str
    book: str | None
    label: str | None
    human: bool
    credential: str | None
    log_h: str
    rules: int
    expires_block: int
    listing: str | None = None
    price: str | None = None
    pay_to: str | None = None
    splits: tuple[int, ...] | None = None
    hcs: str | None = None


@dataclass(frozen=True)
class BoardRead:
    """One game's board as last read from Arkiv: its run rows fastest first and the block they were read at. stale:
    the rows come from the console's cache, because the latest read failed or none has finished since start."""
    rows: tuple[RunRow, ...]
    block: int
    stale: bool = False


class Call(Protocol):
    """One in-flight (or already resolved) sponsor step. A phone step's info carries "code" (the short code the
    console shows and the phone repeats), "expires_s" and, from a real adapter, "qr": the link its QR encodes."""
    elapsed_ms: int
    info: dict

    def poll(self) -> Result | None:
        """None while in flight; the terminal Result once resolved, forever after."""
        ...


class Sponsors(Protocol):
    mock: bool              # any service still mocked: Square's lists and "Start over (mock)" stay
    names: SponsorNames
    approvals: str          # how World asks for a listing OK: "agentpass" (a device code) or "idkit"
    scouts: bool            # PB's scout picks the ghost to buy (the "scout" step): Hedera real and the service says so
    explorer_origin: str | None   # Arkiv's explorer (https://host) as the service names it: its links may be drawn

    def console_state(self) -> dict | None:
        """This console's binding as World's bridge last said it: {"tag", "book", "state", "credential"} (state
        "bound" | "unbound" | "released"); None while mocked or never answered."""
        ...

    def chain_update(self) -> dict | None:
        """The finished payment's chain ids as the service last said them ({"intent", "receipt_msg"}: its HCS messages,
        which land after the payment), asked again in the background while someone looks; None if none."""
        ...

    def mocked(self, service: str) -> bool:
        """"world" | "board" | "third": is that service still mocked? Its pill and QR say so."""
        ...

    def status(self) -> dict[str, str]:
        """"world" | "board" | "third" -> "ok" | "busy" | "off"."""
        ...

    def board(self, game_id: str, look: bool = True) -> BoardRead | None:
        """The arcade game's real board as last read (Arkiv); None while the board is mocked, or never read. look:
        someone is looking at this game's board, so a real adapter keeps it fresh (False: a glance, e.g. attract
        mode's run to beat)."""
        ...

    def begin(self, step: str, payload: dict) -> Call:
        """Start one step. An adapter must never pay the same (game, seller) twice: a repeat
        begin('pay') for a pair it already paid returns the earlier receipt."""
        ...

    def cross(self, call: Call) -> None:
        """The player's Cross on a phone step. The mock resolves it; real adapters ignore it."""
        ...

    def cancel(self, call: Call) -> None:
        """The flow left a phone step (Circle, or its code ran out). A real adapter cancels the
        request where its service can and ignores any later answer: Circle on the console always
        wins. A call that already answered keeps its answer."""
        ...

    def outcomes(self, step: str) -> list[Outcome]:
        """Square's outcome list for this step. Only meaningful when mock."""
        ...

    def force(self, call: Call, outcome: Outcome) -> None:
        """Mock only: resolve call as if the player had picked this outcome (one of the rows
        `outcomes(step)` returned)."""
        ...
