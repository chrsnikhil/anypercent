"""PB the handler's flow engine: walks the state table (states.py) one screen at a time, talks to
the sponsors only through the `Sponsors` protocol (sponsors.py) and keeps the console's ledger
(ledger.py), saving it after every change.

Pure Python, driven once a frame by the app: buttons arrive through press()/pick() and time
through tick(). There is no clock of its own: a call's deadline is read from the call's own
`elapsed_ms`, the day from `today()`. A move that hands control back to the app returns a
command (RaceTarget, CloseHandler); everything else returns None.
"""
import dataclasses
import random
import time
from dataclasses import dataclass

from arca_launcher import coach
from arca_launcher.handler.board import mark_you
from arca_launcher.handler.ledger import (GHOST_PRICE, LISTING_DAYS, budget_left, buy, make_book,
                                          owns, save, start_over)
from arca_launcher.handler.sponsors import Outcome, SponsorNames
from arca_launcher.handler.states import PLACEHOLDER_RE, START, STATES


@dataclass(frozen=True)
class RaceTarget:
    """Start the game, racing this seller's ghost (None: the player's own best)."""
    game_id: str
    seller: str | None


@dataclass(frozen=True)
class CloseHandler:
    """Leave the handler screen."""


_BOARD_CASES = {"no_board": "no_board", "nobody_ahead": "nobody_ahead", "no_best": "board_new"}
# finish_race's result -> the next state, after racing a bought ghost / your own best.
_RACE_RESULTS = {"beat": "result", "lost": "race_lost", "unfinished": "race_unfinished",
                 "unverified": "race_unverified"}
_OWN_RESULTS = {"beat": "own_result", "lost": "own_again", "unfinished": "race_unfinished",
                "unverified": "race_unverified"}
_RACE_AGAIN = ("race_lost", "race_unfinished", "race_unverified", "own_again")
# Calls whose answer still matters after the player moved on: an approval (to say it was
# ignored) and a payment (the money moved). A keep_call screen listens on to these only.
_LATE_ANSWERS = ("approve", "pay")
# The hub's rows as entries, and their labels; the first two need an arcade game, the last one
# exists only in mock mode.
_HUB_ROWS = ("board", "list", "book_view", "listings_view", "start_over")
_HUB_LABELS = dict(zip(_HUB_ROWS, STATES["hub"].card["rows"]))
# A screen that needs a record book first -> where Cross on id_done / id_signed goes once the
# book is made: the purchase or the listing carries on; "My record book" has nothing left to do.
_BOOK_RETURNS = {"buy_check": "buy_check", "ls_offer": "ls_offer", "book_view": "home"}
_NAME_FIELDS = frozenset(f.name for f in dataclasses.fields(SponsorNames))
MOCK_NOW_PRICE = "0.50 USDC"   # the mock's "Price changed": a made-up new price, never a real board's


class Flow:
    """One handler session. `game` is the arcade game id (purchases, listings and targets are
    keyed by it); `ctx` is the public dict of placeholder values: the app fills the run and
    board ones, the engine adds code, qr, expires_s, jti (the mock's only: a real approval's id
    is never shown), book, credential, price, budget_left, receipt, listing_days, approve_how,
    approve_via and ghost_kept (and other_book, when World names the book a duplicate owns),
    now_price (a changed listing's price) and ghost_log (a real target's checked log).

    Read-only for the view and the app: state, line, ms_in_state, in_flight, busy, arcade,
    outcomes_open, outcomes ((label, state) rows), outcome_index, hub_index, hub_rows,
    hub_count and mock_rows()."""

    def __init__(self, sponsors, ledger, ledger_path, game, ctx, today, rng=None):
        self.sponsors = sponsors
        self.ledger = ledger
        self.ledger_path = ledger_path
        self.game = game
        self.ctx = ctx
        self.today = today
        self.rng = rng if rng is not None else random.Random()
        self.state = STATES["hub"]
        self.ms_in_state = 0
        self.outcomes_open = False
        self.outcomes: list[tuple[str, str]] = []
        self.outcome_index = 0
        self.hub_index = 0
        self._rows: list[Outcome] = []
        self._call = None      # the sponsor call the current state began
        self._kept = None      # (step, call) a keep_call state still listens to
        self._seller = None    # whose ghost is being bought or raced; None: your own best
        self._after_book = None  # where the record-book flow returns (_BOOK_RETURNS); None: hub
        self._jti = None       # the listing approval's one-time id, for the record step
        self._world_dup = None  # the book World named for a duplicate: signing in to it is World-verified
        self._sync()

    # ---- what the view reads ---------------------------------------------------------------

    @property
    def in_flight(self) -> bool:
        """A non-phone call is running: it cannot be skipped or cancelled, only finish or time out."""
        return self._call is not None and not self.state.phone

    @property
    def busy(self) -> bool:
        """This screen has a call (timed, or a phone step a visitor may still be on), or a kept
        call may still answer: the app must not close it for idleness."""
        return self.state.call is not None or self._kept is not None

    @property
    def line(self) -> str:
        return self.fill(self.state.say)

    @property
    def arcade(self) -> bool:
        """False for a game with no board (not an arcade game, or the Game Library tile)."""
        return bool(self.ctx.get("arcade", True))

    @property
    def hub_rows(self) -> tuple[str, ...]:
        """The hub card's row labels, in pick() order."""
        return tuple(_HUB_LABELS[entry] for entry in self._hub_entries())

    @property
    def hub_count(self) -> int:
        return len(self._hub_entries())

    def _hub_entries(self):
        rows = _HUB_ROWS if self.arcade else _HUB_ROWS[2:]  # no board to race, no run to list
        return rows if self.sponsors.mock else rows[:-1]

    def fill(self, text: str) -> str:
        """Fill {placeholders} from ctx and the sponsor names; a missing or None value fills as
        "". *Emphasis* marks are kept for the view."""
        extra = {}
        for name in set(PLACEHOLDER_RE.findall(text)) - _NAME_FIELDS:
            value = self.ctx.get(name)
            extra[name] = "" if value is None else value
        return self.sponsors.names.fill(text, **extra)

    # ---- what the app and the controller call ----------------------------------------------

    def start(self, entry: str):
        """Open at an entry ("book", "board", "list", "hub") or straight at a state name.
        Returns the command that entry produced, as press() does."""
        self._call = None
        self._seller = self.ctx.get("target") or None
        self._after_book = "home" if entry == "book" else None  # the day's offer: back Home after
        return self._enter(self._entry(entry))

    def press(self, event: str):
        if self.outcomes_open:
            return self._press_in_list(event)
        if event in ("up", "down"):
            if self.state.name == "hub":
                move = -1 if event == "up" else 1
                self.hub_index = max(0, min(self.hub_count - 1, self.hub_index + move))
            return None
        if event == "square":
            # Mock only, and allowed mid-call: the in-flight steps' outcomes (a sponsor down, a
            # changed listing, a late payment) can only be reached while their call runs.
            self._open_list()
            return None
        if self.in_flight:
            return None
        if event == "cross":
            if self.state.name == "hub":
                return self.pick(self.hub_index)
            if self.state.phone:
                self.sponsors.cross(self._call)  # the answer lands on a later tick()
                return None
            if self.state.name == "start_over":
                self.ledger = start_over(self.ledger_path)
        target = self.state.on.get(event)
        if event == "cross" and self.state.name in ("id_done", "id_signed") and self._after_book:
            target, self._after_book = self._after_book, None
        return self._enter(target) if target else None

    def pick(self, i: int):
        """Choose row i of the open outcome list, else row i of the hub."""
        if self.outcomes_open:
            if not 0 <= i < len(self._rows):
                return None
            outcome = self._rows[i]
            self._close_list()
            if self._call is not None:
                self.sponsors.force(self._call, outcome)  # lands on the next tick()
                return None
            return self._enter(outcome.failure)
        if self.state.name == "hub" and 0 <= i < self.hub_count:
            self.hub_index = i
            return self._enter(self._entry(self._hub_entries()[i]))
        return None

    def tick(self, dt_ms: int):
        self.ms_in_state += dt_ms
        if self.outcomes_open:
            return None
        if self._call is not None:
            self._show_request()  # a real adapter's code and link arrive a moment after begin()
            result = self._call.poll()
            if result is not None:
                return self._land(result)
            deadline = self.state.deadline_ms
            if deadline is not None and self._call.elapsed_ms >= deadline:
                return self._enter(self.state.on["timeout"])
        elif self._kept is not None:
            step, call = self._kept
            result = call.poll()
            if result is not None:
                self._kept = None
                return self._late_answer(step, result)
        return None

    def finish_race(self, result: str, run_frames: int | None) -> None:
        """The race the last RaceTarget started is over. The app updates ctx (gap, new_rank)
        before calling this."""
        self.ctx["run_frames"] = run_frames
        self.ctx["run_time"] = coach.fmt_time(run_frames) if run_frames is not None else ""
        self.ctx["ghost_kept"] = f"{self._seller}'s ghost is still yours. " if self._seller else ""
        self._enter((_RACE_RESULTS if self._seller else _OWN_RESULTS)[result])

    # ---- moving between states -------------------------------------------------------------

    def _entry(self, entry):
        if entry == "list" and self.ctx.get("best_frames") is None:
            return "no_run"
        return START.get(entry, entry)

    def _route(self, name):
        """Screens that look at the ledger or the board first, and may land somewhere else."""
        if name == "board":
            return _BOARD_CASES.get(self.ctx.get("board_case"), "board")
        if name in _BOOK_RETURNS and self.ledger.book is None:
            self._after_book = _BOOK_RETURNS[name]
            return "need_book"
        if name == "ls_approve" and self.sponsors.approvals == "idkit":
            return "ls_confirm"  # World ID's phone shows no code to check: tap Confirm
        if name == "buy_check":
            # The seller is fixed here for the whole purchase and the race after it.
            self._seller = self.ctx.get("target") or None
            if owns(self.ledger, self.game, self._seller):
                return "buy_load"  # already paid for: no check, no charge
            if budget_left(self.ledger, self.today()) < GHOST_PRICE:
                return "buy_budget"
        return name

    def _enter(self, name, data=None):
        name = self._route(name)
        previous = self.state.name
        if self.state.phone and self._call is not None:
            self.sponsors.cancel(self._call)  # leaving a phone step: Circle wins over a late answer
        listens = (STATES[name].keep_call and self._call is not None
                   and self.state.call in _LATE_ANSWERS)
        self._kept = (self.state.call, self._call) if listens else None
        self._call = None
        self.state = STATES[name]
        self.ms_in_state = 0
        self._close_list()
        command = self._arrive(name, previous, data or {})
        if self.state.call is not None:
            self._call = self.sponsors.begin(self.state.call, self._payload())
            self._show_request()
        self._sync()
        return command

    def _show_request(self):
        """A call whose info names a code or link is a new phone request: never the last one's
        code or link, even while a real adapter's are still on their way ("")."""
        info = self._call.info or {}
        if "code" in info or "qr" in info:
            self.ctx["code"] = info.get("code") or ""
            self.ctx["qr"] = info.get("qr") or ""          # a real adapter's link for its QR; "" draws the code
            self.ctx["expires_s"] = info.get("expires_s") or 0   # the request's own lifetime; 0: the screen's

    def _arrive(self, name, previous, data):
        """The ledger effects and commands of entering a state."""
        led = self.ledger
        if name == "id_done":
            if data.get("book"):              # a real record book: World's, one per person
                led.book = data["book"]
            elif led.book is None:
                led.book = make_book(self.rng)
            led.credential = data.get("credential", led.credential)
            # HUMAN on the board only with a real World proof behind the book, never the mock's.
            led.world_verified = bool(data.get("book")) and not self.sponsors.mocked("world")
            self._save()
        elif name == "id_dup" and data.get("book"):
            self.ctx["other_book"] = data["book"]   # the book that person already owns, not a made-up one
            self._world_dup = data["book"]
        elif name == "id_signed":
            led.book = self.ctx.get("other_book") or make_book(self.rng)
            led.world_verified = led.book == self._world_dup and not self.sponsors.mocked("world")
            if led.world_verified:
                led.credential = "World ID"   # World matched the person; which credential, it did not say
            self._save()
        elif name == "ls_done":
            listing = {"game": self.game, "frames": self._run_frames(), "price": GHOST_PRICE, "at": time.time(),
                       "sold": 0}
            for row in ("run", "listing"):          # a real board's rows (Arkiv keys); the mock names none
                if data.get(row):
                    listing[row] = data[row]
            led.listings.append(listing)
            self._save()
        elif name == "buy_changed":
            # What the listing says now: a real board's price, or "gone"; the mock's made-up change.
            self.ctx["now_price"] = data.get("now_price") or MOCK_NOW_PRICE
        elif name == "racing":
            if previous == "nobody_ahead":
                self._seller = None
            if self._seller:
                led.targets[self.game] = self._seller
                self._save()
            return RaceTarget(self.game, self._seller)
        elif name == "home":
            return CloseHandler()
        return None

    def _land(self, result):
        """A call's result arrived: follow on["ok"] or the named failure."""
        step, data = self.state.call, result.data or {}
        if step == "pay" and data.get("late_receipt"):
            # The money moved, whatever the failure says: record it and show it, never "nothing
            # was paid".
            self._charge(data["late_receipt"], late=True)
            return self._enter("buy_late", data)
        nxt = self.state.on["ok"] if result.ok else result.failure
        if nxt not in STATES:
            nxt = self.state.on["timeout"]  # an adapter naming a state the table lacks
        if nxt == "id_dup" and not data.get("book") and not self.sponsors.mocked("world"):
            nxt = "id_dup_unnamed"          # World App refused before any book could be named
        if result.ok and step == "approve":
            self._jti = data.get("jti", "")
            # On screen only the mock's made-up id: a real approval's id is never shown.
            self.ctx["jti"] = self._jti if self.sponsors.mocked("world") else ""
        if result.ok and step == "load_ghost" and data.get("ghost_log"):
            self.ctx["ghost_log"] = data["ghost_log"]   # a real target's log, checked: what the race draws her from
        if result.ok and step == "pay":
            charged = self._charge(data.get("receipt", ""))
            if not charged and not owns(self.ledger, self.game, self._seller):
                # Unreachable through the table: buy_check already sent an owned ghost to
                # buy_load and an empty budget to buy_budget. Kept so a ghost that was neither
                # paid for nor owned is never handed over.
                nxt = "buy_budget"
        return self._enter(nxt, data)

    def _late_answer(self, step, result):
        """A kept call answered after the player moved on. A late approval is only reported as
        ignored (on["ok"]: ls_late); a payment that did land is recorded (on["ok"]: buy_late)."""
        data = result.data or {}
        if step == "pay":
            receipt = data.get("late_receipt") or (data.get("receipt") if result.ok else None)
            if not receipt:
                return None
            self._charge(receipt, late=True)
        elif not result.ok:
            return None
        return self._enter(self.state.on["ok"])

    def _charge(self, receipt, late=False) -> bool:
        """Record the purchase of the seller's ghost. A late receipt is money that already
        moved, so it is recorded even past the daily budget; never twice for one ghost."""
        if not buy(self.ledger, self.game, self._seller, GHOST_PRICE, receipt, self.today(),
                   enforce_budget=not late):
            return False
        self.ctx["receipt"] = receipt
        self._save()
        return True

    # ---- the Square list ---------------------------------------------------------------------

    def mock_rows(self) -> list[Outcome]:
        """What Square lists here: the call's mock outcomes, else the state's own rows (a phone's
        late answer: only while World is mocked). None when nothing is mocked."""
        if not self.sponsors.mock:
            return []
        if self.state.call is not None:
            return list(self.sponsors.outcomes(self.state.call))
        if not self.sponsors.mocked("world"):
            return []
        return [Outcome(self.fill(label), name) for label, name in self.state.mock_outcomes]

    def _open_list(self):
        rows = self.mock_rows()
        if rows:
            self._rows = rows
            self.outcomes = [(o.label, o.failure) for o in rows]
            self.outcome_index = 0
            self.outcomes_open = True

    def _close_list(self):
        self.outcomes_open = False
        self.outcomes = []
        self._rows = []
        self.outcome_index = 0

    def _press_in_list(self, event):
        if event in ("up", "down"):
            move = -1 if event == "up" else 1
            self.outcome_index = max(0, min(len(self._rows) - 1, self.outcome_index + move))
        elif event == "cross":
            return self.pick(self.outcome_index)
        elif event == "circle":
            self._close_list()
        return None

    # ---- the ledger and the context --------------------------------------------------------

    def _save(self):
        save(self.ledger_path, self.ledger)
        self._sync()

    def _sync(self):
        self.ctx["book"] = self.ledger.book or ""
        self.ctx["price"] = "%.2f" % (GHOST_PRICE / 100)
        # A late receipt may take spending past the budget; show that as none left, not negative.
        self.ctx["budget_left"] = "%.2f" % (max(0, budget_left(self.ledger, self.today())) / 100)
        self.ctx["listing_days"] = LISTING_DAYS
        self.ctx["credential"] = self.ledger.credential or "World ID"   # what World checked: Orb, Selfie Check
        # A real phone answers on the phone; only the mock's Cross stands in for it.
        self.ctx["approve_how"] = "Cross to go" if self.sponsors.mocked("world") else "Approve on your phone"
        # Where World App asks for a listing OK: World ID when the bridge runs approvals on IDKit.
        self.ctx["approve_via"] = ("World App > World ID" if self.sponsors.approvals == "idkit"
                                   else "World App > Agent Pass")
        if self.ctx.get("board_rows"):   # YOU are HUMAN on the board only with a real World proof
            led = self.ledger
            self.ctx["board_rows"] = mark_you(self.ctx["board_rows"],
                                              led.credential if led.book and led.world_verified else None)

    def _run_frames(self):
        """The run a listing is about: the one just raced, else the best."""
        frames = self.ctx.get("run_frames")
        return self.ctx.get("best_frames") if frames is None else frames

    def _payload(self):
        """What a real adapter needs to know to run the step; the mock ignores it. `title` is the
        game's name as people read it (World App shows it on a listing approval); `arcade_id` the
        arcade game's id (runs and boards are named by it); `frames` the run a listing is about.
        A real board's target names its run, listing, log and time; `receipt` is what was paid
        for her ghost (a listed ghost's key is released against it)."""
        bought = self.ledger.purchases.get(f"{self.game}:{self._seller}") or {}
        return {"game": self.game, "title": self.ctx.get("game"), "seller": self._seller,
                "price": GHOST_PRICE, "book": self.ledger.book, "jti": self._jti,
                "run_time": self.ctx.get("run_time"), "frames": self._run_frames(),
                "arcade_id": self.ctx.get("arcade_id"), "target_run": self.ctx.get("target_run"),
                "target_listing": self.ctx.get("target_listing"),
                "target_log_h": self.ctx.get("target_log_h"),
                "target_frames": self.ctx.get("target_frames"),
                "receipt": bought.get("receipt") or self.ctx.get("receipt")}
