"""The sponsor interface: the shapes every mocked step and outcome travels through. The real
World, Arkiv and Hedera adapters built at the hackathon implement this same protocol so the
flow engine and views never change; this module holds no behaviour, only the types.
"""
from dataclasses import dataclass, field
from typing import Protocol


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
         "approve_scan", "approve", "record", "publish", "sales")

# Real-adapter timeouts the flow engine enforces (Global Constraints). Phone steps have none
# here: their deadline is the QR's own expiry, carried on Call.info["expires_s"].
TIMEOUT_MS = {"idkit_verify": 10000, "pay": 8000, "record": 8000, "publish": 8000,
              "check_listing": 8000, "load_ghost": 8000}


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

    def mocked(self, service: str) -> bool:
        """"world" | "board" | "third": is that service still mocked? Its pill and QR say so."""
        ...

    def status(self) -> dict[str, str]:
        """"world" | "board" | "third" -> "ok" | "busy" | "off"."""
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
