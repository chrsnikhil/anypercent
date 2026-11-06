"""The mock Sponsors adapter: stands in for World, Arkiv and Hedera until the event's real
code lands behind the same interface (sponsors.py). No network, no threads: every call is a
pure function of a clock the caller drives, so the flow engine can poll it every frame."""
import random

from arca_launcher.handler.sponsors import Outcome, Result, SponsorNames

# The Global Constraints' "prototype auto" delays, in ms. Steps not listed here either resolve
# at once (status, sales) or only on cross()/force() (the phone steps).
_DELAY_MS = {
    "status": 0,
    "idkit_verify": 1700,
    "check_listing": 1400,
    "pay": 2000,
    "load_ghost": 1200,
    "record": 2000,
    "publish": 1400,
    "sales": 0,
}

_PHONE_STEPS = ("idkit_scan", "idkit_confirm", "approve_scan", "approve")

# Which status pill (and "busy" tracking) a step belongs to. "status" needs none of them: it
# just reports on all three.
_SERVICE = {
    "idkit_scan": "world", "idkit_confirm": "world", "idkit_verify": "world",
    "approve_scan": "world", "approve": "world",
    "check_listing": "board", "publish": "board", "sales": "board",
    "pay": "third", "load_ghost": "third", "record": "third",
}

# A down World or Hedera fails its steps outright; a down Arkiv has no failure state of its
# own (Global Constraints: it only shows as "off" in status()), so it is absent here.
_DOWN_FAILURE = {
    "idkit_scan": "id_offline", "idkit_confirm": "id_offline", "idkit_verify": "id_offline",
    "approve_scan": "ls_world_down", "approve": "ls_world_down",
    "pay": "buy_down", "load_ghost": "buy_load_fail",
    "record": "ls_record_fail",
}

# (label template, failure state, late) per step, only for steps a player can force a named
# outcome on. Templates are filled through SponsorNames so no sponsor name is ever hard-coded
# here. "late" marks only the "Paid late" row: it shares its failure name with the plain
# "Hedera down" row above it, so the row itself (not the failure name) carries the distinction.
_OUTCOMES = {
    # "Another person's console": the only way id_taken is ever shown in a demo, under the MOCK pill (one owner, one
    # World ID: it can not happen live).
    "idkit_confirm": [("Reject", "id_rejected", False), ("Let it expire", "id_expired", False),
                       ("No Selfie Check", "id_nocred", False), ("Same person again", "id_dup", False),
                       ("Another person's console", "id_taken", False), ("{world} down", "id_offline", False)],
    "check_listing": [("Budget used up", "buy_budget", False), ("Price changed", "buy_changed", False),
                        ("Guard says no", "buy_suspended", False)],
    "pay": [("{third} down", "buy_down", False), ("Paid late", "buy_down", True)],
    "approve": [("Deny", "ls_denied", False), ("Expire", "ls_expired", False),
                ("Another {world} ID", "ls_wrong", False), ("Codes differ", "ls_mismatch", False),
                ("Reused approval", "ls_reused", False)],
    "record": [("{third} slow", "ls_record_fail", False), ("Copied run", "ls_copied", False)],
    "approve_scan": [("{world} down", "ls_world_down", False)],
}

_CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_HEX_CHARS = "0123456789abcdef"


def _random_token(rng, chars, length):
    return "".join(rng.choice(chars) for _ in range(length))


def _hex8(rng):
    return _random_token(rng, _HEX_CHARS, 8)


def _code(rng):
    return _random_token(rng, _CODE_CHARS, 3) + "-" + _random_token(rng, _CODE_CHARS, 3)


class _Call:
    """One begun step. Resolution is computed lazily from the clock (timed steps) or set once
    by cross()/force() (phone steps and forced failures); once resolved, the Result is cached
    so repeated polling (and random data inside it) never changes after the fact."""

    def __init__(self, owner, step, payload, info):
        self._owner = owner
        self.step = step
        self.payload = payload
        self.info = info
        self._start_ms = owner._clock_ms()
        self._result = None

    @property
    def elapsed_ms(self) -> int:
        return self._owner._clock_ms() - self._start_ms

    def poll(self) -> Result | None:
        if self._result is not None:
            return self._result
        if self._resolve_if_down():
            return self._result
        if self.step in _PHONE_STEPS:
            return None  # only cross() or force() resolve a phone step
        if self.elapsed_ms < _DELAY_MS.get(self.step, 0):
            return None
        self._result = self._owner._success(self.step)
        return self._result

    def waiting(self) -> bool:
        """Still in flight, judged by peeking: never polls, so it never resolves (and caches) a
        timed call that a Square outcome may still be forced onto."""
        if self._result is not None:
            return False
        if self.step in _PHONE_STEPS:
            return True
        return self.elapsed_ms < _DELAY_MS.get(self.step, 0)

    def _resolve_if_down(self) -> bool:
        """World or Hedera being down overrides any other resolution, timed or phone. Arkiv
        being down never fails a call. Returns True once this call is resolved this way."""
        service = _SERVICE.get(self.step)
        if service in ("world", "third") and self._owner._down[service]:
            self._result = Result(ok=False, failure=_DOWN_FAILURE[self.step])
            return True
        return False


class MockSponsors:
    """Sponsors, mocked. clock_ms is read on every poll, never cached, so a fake clock the
    caller advances by hand drives the whole thing deterministically."""

    mock = True
    approvals = "agentpass"  # the mock's listing OK reads as Agent Pass's device code
    scouts = False           # no scout: the mock's target is the board's ghost just ahead
    explorer_origin = None   # no explorer links: the mock writes nothing anywhere

    def __init__(self, clock_ms, names=SponsorNames(), seed=0):
        self._clock_ms = clock_ms
        self.names = names
        self._rng = random.Random(seed)
        self._down = {"world": False, "board": False, "third": False}
        self._active = {"world": None, "board": None, "third": None}

    def mocked(self, service: str) -> bool:
        return self.mock  # all three (a test's stand-in for a real adapter sets mock False: none)

    def status(self) -> dict[str, str]:
        """A service is "busy" only while a timed call of its own runs. A phone call can wait for
        minutes, or be kept after the player backed out, so it never counts: the state table's
        `busy` field drives the pulse for any step that needs one."""
        out = {}
        for service in ("world", "board", "third"):
            if self._down[service]:
                out[service] = "off"
            else:
                active = self._active[service]
                timed = active is not None and active.step not in _PHONE_STEPS
                out[service] = "busy" if timed and active.waiting() else "ok"
        return out

    def board(self, game_id: str, look: bool = True):
        """No real board: the glue draws the mock one around the game's test log."""
        return None

    def console_state(self):
        """No bridge, so no binding: the ledger is the console's own."""
        return None

    def chain_update(self):
        """No chain: the mock's receipts stand for no payment."""
        return None

    def set_down(self, service: str, down: bool) -> None:
        self._down[service] = down

    def begin(self, step: str, payload: dict):
        if step == "idkit_scan":
            info = {"code": _code(self._rng), "expires_s": 300}
        elif step == "approve_scan":
            info = {"code": _code(self._rng), "expires_s": 1200}
        else:
            info = {}
        call = _Call(self, step, payload, info)
        service = _SERVICE.get(step)
        if service is not None:
            self._active[service] = call
        return call

    def cross(self, call) -> None:
        if call.step not in _PHONE_STEPS or call._result is not None:
            return
        if call._resolve_if_down():
            return
        if call.step == "approve":
            call._result = Result(ok=True, data={"jti": _hex8(self._rng)})
        else:
            call._result = Result(ok=True, data={})

    def cancel(self, call) -> None:
        """Nothing to tell: no phone ever saw the mock's code. A kept call stays open, so its
        Square outcome can still land late."""

    def outcomes(self, step: str) -> list[Outcome]:
        return [Outcome(self.names.fill(label), failure, late)
                for label, failure, late in _OUTCOMES.get(step, [])]

    def force(self, call, outcome: Outcome) -> None:
        if call._result is not None:
            return
        data = {"late_receipt": "mock-" + _hex8(self._rng)} if outcome.late else {}
        call._result = Result(ok=False, failure=outcome.failure, data=data)

    def _success(self, step: str) -> Result:
        if step == "status":
            return Result(ok=True, data=self.status())
        if step == "sales":
            return Result(ok=True, data={"buyer": "ARJUN"})
        if step == "idkit_verify":
            return Result(ok=True, data={"credential": "Selfie Check"})
        if step == "check_listing":
            return Result(ok=True, data={"price": 10})
        if step == "pay":
            return Result(ok=True, data={"receipt": "mock-" + _hex8(self._rng)})
        return Result(ok=True, data={})
