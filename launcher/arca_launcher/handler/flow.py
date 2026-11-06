"""PB the handler's flow engine: walks the state table (states.py) one screen at a time, talks to
the sponsors only through the `Sponsors` protocol (sponsors.py) and keeps the console's ledger
(ledger.py), saving it after every change.

Pure Python, driven once a frame by the app: buttons arrive through press()/pick() and time
through tick(). There is no clock of its own: a call's deadline is read from the call's own
`elapsed_ms`, the day from `today()`. A move that hands control back to the app returns a
command (RaceTarget, OpenLink, CloseHandler); everything else returns None.

PB's scout: with the sponsors' `scouts` on, Cross on the board goes to the scout (the service
compares your laps with the listed ghosts' and picks one); its pick becomes the target and is
bought after the pick screen's `auto_ms` unless Circle stops it. The scout only chooses which
ghost: every guard runs on the purchase as before. Any scout failure but a refusal shows the
board's own target, saying the scout did not answer.

Every finished step keeps its chain ids in ctx["chain"] ([{label, value, url}], ctx["chain_i"]
the one whose QR shows): the HCS record, the Arkiv rows (a listing's: its run and listing, the
transaction this console's own wallet signed and the checker's stamp), the payment with its INTENT and
RECEIPT, and last the run's replay (the checker's for a listing, this console's for a bought
ghost; never the mock's). A url is kept only on HashScan's testnet or the Arkiv explorer the
service names. Triangle on a chain card opens the chosen row's link (OpenLink, for the app).

The real board has a cursor (never the mock's): Up and Down move it over the rows the card
draws, starting on YOU's; it follows the runner it is on (ctx["board_pick"]) through a Humans
only toggle or a new read, back on YOU's row when that runner is not shown. Triangle there opens
run_links, a chain card of that run's records: its run and listing on Arkiv, its listing's
LISTING message and payout account on HashScan, and the checker's replay (every time on the board
is the one the checker's replay gave before it stamped the run). Cross and Circle go back to the
board with its cursor where it was.

A chain card can come back after the browser took the screen (handler_glue.py): restore() before
start() lands on it as it was, its rows already in ctx, with nothing of arriving done again, and
the payment data chain_pay gave so a RECEIPT still waiting for the mirror keeps filling in.
"""
import copy
import dataclasses
import random
import time
from dataclasses import dataclass

from arca_launcher import coach
from arca_launcher.handler.board import humans_only, mark_you, ordinal
from arca_launcher.handler.ledger import (GHOST_PRICE, LISTING_DAYS, budget_left, buy, make_book,
                                          owns, save, start_over)
from arca_launcher.handler.sponsors import BOOK, HCS_MSG, PAY_TO, Outcome, SponsorNames
from arca_launcher.handler.states import PLACEHOLDER_RE, START, STATES


@dataclass(frozen=True)
class RaceTarget:
    """Start the game, racing this seller's ghost (None: the player's own best)."""
    game_id: str
    seller: str | None


@dataclass(frozen=True)
class OpenLink:
    """Open a chain row's link (HashScan's testnet or the Arkiv explorer: the flow's _allowed kept only those)."""
    url: str


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
_BOARD_STATES = ("board", "board_new")      # Cross here may scout; Square toggles Humans only
_SCOUT_FAILURES = ("buy_budget", "nobody_ahead", "buy_suspended")   # the scout's refusals: their own screens
SCOUT_DOWN = "My scout is not answering, so here is the ghost just ahead. "
# The board's target as the glue set it: what a scout's pick replaces, and Circle on the pick puts back.
_TARGET_KEYS = ("target", "target_time", "target_frames", "target_run", "target_listing", "target_log_h",
                "target_pay_to", "gap", "new_rank")
_SCOUT_KEYS = ("scout_id", "scout_reason", "scout_by", "scout_model", "scout_note", "you_laps", "it_laps",
               "scout_lap", "you_time")
# The chain card's screens: Up and Down pick a row's QR. run_links: a board run's records (Triangle on the board).
CHAIN_STATES = ("ls_done", "buy_done", "buy_late", "run_links")
REPLAYED_CHECKER = "Replayed by the checker"   # a listing's last chain row: the checker's replay before it stamped
REPLAYED_HERE = "Replayed on this console"     # a purchase's: this console's replay of the ghost it loaded
SIGNED_HERE = "Signed by this console"         # a listing's: the transaction this console's own wallet sent
STAMPED = "Stamped by the checker"             # and the checker's stamp of the run, linked to its transaction
HASHSCAN = "https://hashscan.io/testnet/"
LINK_MAX = 300
GROQ = "Groq"                  # where the scout's model runs, as its by-line says
# PB's guard refused a purchase: data.why on buy_suspended, as the refusal's card says it.
REFUSED_WHY = {"own_book": "that is your own book", "run_changed": "the run changed",
               "no_pay_to": "no payout account", "cannot_receive": "the account can not take USDC",
               "payto_402": "the paywall named another account", "not_for_sale": "not for sale",
               "not_house": "a BOT listing must pay the house",
               "console_not_linked": "this console is not linked to {book}"}
REFUSED_ELSE = "the listing did not check out"
NO_BOOK_LINE = "This console has no record book now. Its runs stay on the board."


class Flow:
    """One handler session. `game` is the arcade game id (purchases, listings and targets are
    keyed by it); `ctx` is the public dict of placeholder values: the app fills the run and
    board ones, the engine adds code, qr, expires_s, jti (the mock's only: a real approval's id
    is never shown), book, credential, price, budget_left, receipt, receipt_text (the receipt as
    the card shows it), listing_days, approve_how,
    approve_via and ghost_kept (and other_book, when World names the book a duplicate owns),
    now_price (a changed listing's price) and ghost_log (a real target's checked log).

    Read-only for the view and the app: state, line, ms_in_state, in_flight, busy, arcade,
    outcomes_open, outcomes ((label, state) rows), outcome_index, hub_index, hub_rows,
    hub_count, board_shown, board_cursor, board_row and mock_rows()."""

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
        self._board_target = None   # the board's target fields while a scout's pick stands in for them
        self._chain_pay = None      # the payment the chain rows show (its data), for the late HCS ids
        self._restored = False      # restore(): the next start() lands on a chain card as it was
        ctx.setdefault("chain", [])
        ctx.setdefault("chain_i", 0)
        ctx.setdefault("humans_only", False)
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
        if self.state.name == "book_view" and not self.ledger.book:
            return NO_BOOK_LINE              # released while shown: the console's book went (the glue followed it)
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

    @property
    def board_shown(self):
        """The board's rows as its card draws them: with Humans only, the human tier's and YOU's."""
        rows = tuple(self.ctx.get("board_rows") or ())
        return humans_only(rows) if self.ctx.get("humans_only") else rows

    @property
    def board_cursor(self):
        """The real board's chosen row as an index into board_shown, or None: off the board, on the mock board (no
        cursor there) or with no rows. The row of the runner ctx["board_pick"] names while it is shown, else YOU's,
        else the first: a toggle or a new read never leaves the cursor off the rows."""
        rows = self.board_shown
        if not rows or self.state.name not in _BOARD_STATES or self.sponsors.mocked("board"):
            return None
        pick = self.ctx.get("board_pick")
        return next((i for i, row in enumerate(rows) if row.name == pick),
                    next((i for i, row in enumerate(rows) if row.you), 0))

    @property
    def board_row(self):
        """The real board's chosen row (board_cursor's), or None."""
        i = self.board_cursor
        return None if i is None else self.board_shown[i]

    def fill(self, text: str) -> str:
        """Fill {placeholders} from ctx and the sponsor names; a missing or None value fills as
        "". *Emphasis* marks are kept for the view. {payee} is worked out from the target as it is
        now: a BOT's house account, else the seller's own."""
        extra = {}
        for name in set(PLACEHOLDER_RE.findall(text)) - _NAME_FIELDS:
            value = self._payee() if name == "payee" else self.ctx.get(name)
            extra[name] = "" if value is None else value
        return self.sponsors.names.fill(text, **extra)

    def _payee(self):
        """Who a purchase of the target pays: "the house account 0.0.N" for a BOT ghost, "ANY-4HJ's account 0.0.N"
        for a person's listing, "RIA's record book" on the mock board (no account named)."""
        target, pay_to = self.ctx.get("target") or "", self.ctx.get("target_pay_to")
        if not target:
            return ""
        if target.startswith("BOT-"):
            return f"the house account {pay_to}" if pay_to else "the house account"
        return f"{target}'s account {pay_to}" if pay_to else f"{target}'s record book"

    # ---- what the app and the controller call ----------------------------------------------

    def start(self, entry: str):
        """Open at an entry ("book", "board", "list", "hub") or straight at a state name.
        Returns the command that entry produced, as press() does. Right after restore(), a chain
        card is shown as it was: nothing of arriving at it is done again (a listing is never
        written twice)."""
        self._call = None
        self._seller = self.ctx.get("target") or None
        self._after_book = "home" if entry == "book" else None  # the day's offer: back Home after
        restored, self._restored = self._restored, False
        if restored and entry in CHAIN_STATES:
            return self._enter(entry, arrive=False)
        return self._enter(self._entry(entry))

    def restore(self, chain_pay=None):
        """Before start(): the chain card it starts at was on screen before the browser took it
        (handler_glue.py), its rows and chain_i are in ctx already. chain_pay is what chain_pay
        said then (a payment's receipt and its HCS messages), so a RECEIPT still waiting for the
        mirror keeps filling in; anything else is no payment. Counts for the next start() only."""
        self._restored = True
        usable = isinstance(chain_pay, dict) and isinstance(chain_pay.get("receipt"), str) and chain_pay["receipt"]
        self._chain_pay = copy.deepcopy(chain_pay) if usable else None

    @property
    def chain_pay(self):
        """The payment the chain rows show (a copy of its data, for restore()), or None."""
        return copy.deepcopy(self._chain_pay)

    def press(self, event: str):
        if self.outcomes_open:
            return self._press_in_list(event)
        if event in ("up", "down"):
            move = -1 if event == "up" else 1
            if self.state.name == "hub":
                self.hub_index = max(0, min(self.hub_count - 1, self.hub_index + move))
            elif self.state.name in CHAIN_STATES and self.ctx["chain"]:
                self.ctx["chain_i"] = (self.ctx.get("chain_i", 0) + move) % len(self.ctx["chain"])
            elif self.board_cursor is not None:      # the real board: the cursor, held to the rows
                rows = self.board_shown
                self.ctx["board_pick"] = rows[max(0, min(len(rows) - 1, self.board_cursor + move))].name
            return None
        if event == "square":
            if self.state.name in _BOARD_STATES:     # Humans only: the board hides non-human rows (YOU stay)
                self.ctx["humans_only"] = not self.ctx.get("humans_only")
                return None
            # Mock only, and allowed mid-call: the in-flight steps' outcomes (a sponsor down, a
            # changed listing, a late payment) can only be reached while their call runs.
            self._open_list()
            return None
        if self.in_flight:
            return None
        if event == "triangle":
            return self._open_run_links() if self.state.name in _BOARD_STATES else self._open_link()
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
        auto = self.state.auto_ms
        if auto is not None and self.ms_in_state >= auto and "auto" in self.state.on:
            return self._enter(self.state.on["auto"])
        if self._chain_pay is not None and self.state.name in CHAIN_STATES:
            self._chain_refresh()
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
        if name == "target" and self.state.name in _BOARD_STATES and self._scouts():
            return "scout"
        if name in _BOOK_RETURNS and self.ledger.book is None:
            self._after_book = _BOOK_RETURNS[name]
            return "need_book"
        if name == "ls_approve" and self.sponsors.approvals == "idkit":
            return "ls_confirm"  # World ID's phone shows no code to check: tap Confirm
        if name == "buy_check":
            # The seller is fixed here for the whole purchase and the race after it.
            self._seller = self.ctx.get("target") or None
            self._board_target = None            # a scout's pick, if any, is the purchase now
            self._clear_chain()
            if owns(self.ledger, self.game, self._seller):
                return "buy_load"  # already paid for: no check, no charge
            if budget_left(self.ledger, self.today()) < GHOST_PRICE:
                return "buy_budget"
        return name

    def _scouts(self):
        """The scout picks the ghost: the sponsors run one, and there is a best of YOU's to compare and a book."""
        return (bool(getattr(self.sponsors, "scouts", False)) and self.ctx.get("best_frames") is not None
                and bool(self.ledger.book))

    def _enter(self, name, data=None, arrive=True):
        """arrive=False: only show the state (a restored chain card), none of _arrive's effects."""
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
        command = self._arrive(name, previous, data or {}) if arrive else None
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
        if name in _BOARD_STATES:                         # a new look: no pick and no excuse from before
            self.ctx["scout_down"] = ""
            self.ctx.update(dict.fromkeys(_SCOUT_KEYS))
            if previous == "scout_pick" and self._board_target is not None:
                self.ctx.update(self._board_target)       # Circle on the pick: the board's own target again
            self._board_target = None
            if previous != "run_links":                   # back from a run's records: the cursor where it was
                self.ctx["board_pick"] = None
        elif name == "scout":
            self.ctx["scout_down"] = ""
            self.ctx.update(dict.fromkeys(_SCOUT_KEYS))
        elif name == "target":
            self.ctx["scout_down"] = SCOUT_DOWN if previous == "scout" else ""
        elif name == "ls_scan":
            self._clear_chain()
            self.ctx["record_line"] = ""
        elif name == "id_taken":
            if isinstance(data.get("book"), str) and BOOK.fullmatch(data["book"]):
                self.ctx["other_book"] = data["book"]   # whose console it is, as World's bridge said
        elif name == "buy_suspended":
            why = REFUSED_WHY.get(data.get("why"), REFUSED_ELSE)
            self.ctx["refused_why"] = why.format(book=led.book or "your record book")
        if name == "id_done":
            if isinstance(data.get("console"), str):
                self.ctx["console_tag"] = data["console"]
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
        if step == "scout":
            if result.ok:
                nxt = "scout_pick" if self._picked(data) else self.state.on["timeout"]
            else:
                nxt = result.failure if result.failure in _SCOUT_FAILURES else self.state.on["timeout"]
        if result.ok and step == "record":
            self._chain_record(data)
        if result.ok and step == "publish":
            self._chain_publish(data)
        if result.ok and step == "load_ghost" and data.get("ghost_log"):
            self.ctx["ghost_log"] = data["ghost_log"]   # a real target's log, checked: what the race draws it from
        if result.ok and step == "load_ghost":
            self._chain_replayed(data)
        if result.ok and step == "pay":
            charged = self._charge(data.get("receipt", ""))
            if not charged and not owns(self.ledger, self.game, self._seller):
                # Unreachable through the table: buy_check already sent an owned ghost to
                # buy_load and an empty budget to buy_budget. Kept so a ghost that was neither
                # paid for nor owned is never handed over.
                nxt = "buy_budget"
            else:
                self._chain_paid(data)
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
            if result.ok:
                self._chain_paid(data)
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

    # ---- the scout's pick ------------------------------------------------------------------------

    def _picked(self, data):
        """The scout's pick (the adapter's checked answer) as the target: True when it named one to buy. The board's
        own target is kept to put back if Circle stops the purchase."""
        need = ("scout", "seller", "listing", "run", "log_h", "frames", "time", "reason", "by")
        if not all(data.get(key) for key in need) or type(data["frames"]) is not int:
            return False
        if self._board_target is None:
            self._board_target = {key: self.ctx.get(key) for key in _TARGET_KEYS}
        seller, you = data["seller"], data.get("you_frames")
        rank = next((row.rank for row in self.ctx.get("board_rows") or () if row.name == seller and not row.you), None)
        self.ctx.update(target=seller, target_time=data["time"], target_frames=data["frames"],
                        target_run=data["run"], target_listing=data["listing"], target_log_h=data["log_h"],
                        target_pay_to=data.get("pay_to"), new_rank=ordinal(rank),
                        gap="%.1f s" % ((you - data["frames"]) / 60) if type(you) is int and you > data["frames"]
                        else "",
                        scout_id=data["scout"], scout_reason=data["reason"], scout_model=data.get("model"),
                        scout_note=data.get("note"), you_laps=data.get("you"), it_laps=data.get("it"),
                        scout_lap=data.get("lap"), you_time=data.get("you_time"),
                        scout_by=self._by_line(data))
        self._seller = seller
        return True

    @staticmethod
    def _by_line(data):
        if data["by"] == "model" and data.get("model"):
            return f"Picked by {data['model']} on {GROQ}"
        note = data.get("note")
        return "Picked by PB's rule: the ghost just ahead" + (f" ({note})" if note else "")

    # ---- the chain ids of the finished steps -----------------------------------------------------

    def _allowed(self, url):
        """url when the console may draw it as a QR code: HashScan's testnet, or the Arkiv explorer the service's
        /arkiv/config named. None otherwise (the row shows its text only)."""
        if not (isinstance(url, str) and len(url) <= LINK_MAX and url.isprintable() and " " not in url):
            return None
        origin = getattr(self.sponsors, "explorer_origin", None)
        if url.startswith(HASHSCAN) or (isinstance(origin, str) and origin and url.startswith(origin + "/")):
            return url
        return None

    def _row(self, label, value, url=None):
        return {"label": label, "value": value, "url": self._allowed(url)}

    def _clear_chain(self):
        self.ctx["chain"], self.ctx["chain_i"] = [], 0
        self._chain_pay = None

    def _chain_record(self, data):
        """The listing's HCS record: "Hedera LISTING #41" / "topic 0.0.N · tx 0.0.N@s"; "Recorded" while mocked."""
        third = self.sponsors.names.third
        if self.sponsors.mocked("third"):
            self.ctx["record_line"] = "Recorded"
            return
        seq = data.get("seq")
        label = f"{third} LISTING #{seq}" if type(seq) is int else f"{third} LISTING"
        self.ctx["record_line"] = "Recorded: " + label
        parts = [f"topic {data['topic']}" if isinstance(data.get("topic"), str) else "",
                 f"tx {_tx_id(data['tx'])}" if isinstance(data.get("tx"), str) else ""]
        self.ctx["chain"] = [self._row(label, " \u00b7 ".join(x for x in parts if x), data.get("hashscan"))]
        self.ctx["chain_i"] = 0

    def _chain_publish(self, data):
        """The Arkiv rows: the run's and the listing's entity keys, the transaction this console's own wallet signed
        ("Signed by this console", "tx 0x5c1d…9e02") and the checker's stamp of the run ("Stamped by the checker",
        "0x7e3a…01b2 · tx 0x44d0…aa19", linked to the stamp's transaction), each with its explorer link; then, when
        the service replayed the run for this listing, the checker's replay ("1:42.83 = 6170 frames · end 225d59fd":
        its time and the game's final hash), linked to the run."""
        if self.sponsors.mocked("board"):
            return
        board, links = self.sponsors.names.board, data.get("explorer") or {}
        rows = [self._row(f"{board} {name}", _short(data[name]), links.get(name))
                for name in ("run", "listing") if isinstance(data.get(name), str)]
        if isinstance(data.get("tx"), str):
            rows.append(self._row(SIGNED_HERE, "tx " + _short(data["tx"]), links.get("tx")))
        if isinstance(data.get("stamp"), str):
            stamp_tx = data.get("stamp_tx")
            value = _short(data["stamp"]) + (f" \u00b7 tx {_short(stamp_tx)}" if isinstance(stamp_tx, str) else "")
            rows.append(self._row(STAMPED, value, links.get("stamp_tx") or links.get("stamp")))
        replay = data.get("replay")
        if isinstance(replay, dict) and _frames(replay.get("frames")):
            frames, end = replay["frames"], replay.get("final_hash")
            if type(end) is int and 0 <= end <= 0xFFFFFFFF:
                rows.append(self._row(REPLAYED_CHECKER, "%s = %d frames \u00b7 end %08x"
                                      % (coach.fmt_time(frames), frames, end), links.get("run")))
        self.ctx["chain"] = list(self.ctx.get("chain") or []) + rows

    def _chain_replayed(self, data):
        """This console's replay of the ghost it loaded, last on the chain card: "1:43.93 = 6236 frames, same as the
        board" ("checked when first loaded" for a log replayed when it was first loaded), linked to the run. Never
        twice, never the mock's."""
        frames = data.get("replayed")
        if self.sponsors.mocked("board") or not _frames(frames):
            return
        how = "checked when first loaded" if data.get("replay_cached") else "same as the board"
        links = data.get("explorer") if isinstance(data.get("explorer"), dict) else {}
        row = self._row(REPLAYED_HERE, f"{coach.fmt_time(frames)} = {frames} frames, {how}", links.get("run"))
        self.ctx["chain"] = [r for r in self.ctx.get("chain") or () if r.get("label") != REPLAYED_HERE] + [row]

    def _chain_paid(self, data):
        """The payment's rows: its INTENT on HCS, the payment itself, its RECEIPT (late: "waiting for the mirror"
        until chain_update() has it)."""
        if self.sponsors.mocked("third") or not data.get("receipt"):
            return
        self._chain_pay = dict(data)
        self._chain_pay_rows()
        rows = self.ctx["chain"]
        self.ctx["chain_i"] = next((i for i, row in enumerate(rows) if row["label"].startswith("Paid")), 0)

    def _chain_pay_rows(self):
        data, third = self._chain_pay, self.sponsors.names.third
        rows = []
        intent = data.get("intent")
        if isinstance(intent, dict):
            rows.append(self._msg_row(f"{third} INTENT", intent))
        rows.append(self._row("Paid %.2f USDC" % (GHOST_PRICE / 100), "tx " + _tx_id(data["receipt"]),
                              data.get("hashscan")))
        if "receipt_msg" in data:
            msg = data["receipt_msg"]
            rows.append(self._msg_row(f"{third} RECEIPT", msg) if isinstance(msg, dict)
                        else self._row(f"{third} RECEIPT", "waiting for the mirror"))
        # This console's replay of the ghost stays last, as the RECEIPT fills in above it.
        rows += [r for r in self.ctx.get("chain") or () if r.get("label") == REPLAYED_HERE][-1:]
        self.ctx["chain"] = rows
        self.ctx["chain_i"] = min(self.ctx.get("chain_i", 0), len(rows) - 1)

    def _open_link(self):
        """Triangle on a chain card: the chosen row's link (chain_i held to the rows, as the card draws it), or None
        for a row with none."""
        rows = self.ctx.get("chain") or []
        if self.state.name not in CHAIN_STATES or not rows:
            return None
        url = rows[max(0, min(len(rows) - 1, int(self.ctx.get("chain_i") or 0)))].get("url")
        return OpenLink(url) if isinstance(url, str) and url else None

    def _open_run_links(self):
        """Triangle on the real board: the chosen run's records as the run_links chain card ("BOT-A2's 1:43.93 run"),
        its first row chosen. None for a row on no chain (YOU's best not on the board yet) and on the mock board. A
        payment's chain rows go (_clear_chain), so a RECEIPT still filling in never lands on this card."""
        row = self.board_row
        if row is None or not isinstance(row.key, str) or not _frames(row.frames):
            return None
        rows = self._run_rows(row)
        self._clear_chain()
        self.ctx.update(chain=rows, chain_i=0, links_run=f"{row.owner or row.name}'s {coach.fmt_time(row.frames)} run")
        return self._enter("run_links")

    def _run_rows(self, row):
        """A board run's records, each only when the row has it: its run and its listing on Arkiv (their explorer
        pages, built by the Arkiv adapter from /arkiv/config: entity_link), the listing's LISTING message on Hedera
        (hcs "<topic>/<seq>": the topic on HashScan; a BOT run's is its batch's HOUSE message), the checker's replay
        (the run's time is the one it gave before it stamped the run: linked to the run) and the account the listing
        pays (on HashScan)."""
        names = self.sponsors.names
        link = getattr(self.sponsors, "entity_link", None) or (lambda key: None)
        run = link(row.key)
        rows = [self._row(f"{names.board} run", _short(row.key), run)]
        if isinstance(row.listing, str):
            rows.append(self._row(f"{names.board} listing", _short(row.listing), link(row.listing)))
        message = HCS_MSG.fullmatch(row.hcs) if isinstance(row.hcs, str) else None
        if message is not None:
            topic, seq = message.groups()
            kind = "HOUSE" if row.tier == "bot" else "LISTING"     # a BOT run's message is its batch's HOUSE approval
            rows.append(self._row(f"{names.third} {kind} #{int(seq)}", f"topic {topic}", f"{HASHSCAN}topic/{topic}"))
        rows.append(self._row(REPLAYED_CHECKER, f"{coach.fmt_time(row.frames)} = {row.frames} frames", run))
        if isinstance(row.pay_to, str) and PAY_TO.fullmatch(row.pay_to):
            whose = "the house account" if row.tier == "bot" else f"{row.owner or row.name}'s account"
            rows.append(self._row(f"Pays {row.pay_to}", whose, f"{HASHSCAN}account/{row.pay_to}"))
        return rows

    def _msg_row(self, label, msg):
        seq, tx = msg.get("seq"), msg.get("tx")
        return self._row(f"{label} #{seq}" if type(seq) is int else label,
                         "tx " + _tx_id(tx) if isinstance(tx, str) else "", msg.get("hashscan"))

    def _chain_refresh(self):
        """The payment's HCS messages as the adapter last read them: the RECEIPT lands after the payment."""
        update = getattr(self.sponsors, "chain_update", lambda: None)()
        if not isinstance(update, dict) or update.get("receipt") != self._chain_pay.get("receipt"):
            return
        fresh = {key: update[key] for key in ("intent", "receipt_msg") if key in update}
        if all(self._chain_pay.get(key) == value for key, value in fresh.items()):
            return
        self._chain_pay.update(fresh)
        self._chain_pay_rows()

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
        self.ctx["receipt_text"] = self._receipt_text()
        if self.ctx.get("board_rows"):   # YOU are HUMAN on the board only with a real World proof
            led = self.ledger
            self.ctx["board_rows"] = mark_you(self.ctx["board_rows"],
                                              led.credential if led.book and led.world_verified else None)

    def refresh(self):
        """The ledger changed outside the flow (the glue followed the console's binding): the context follows it."""
        self._sync()

    def _receipt_text(self):
        """The receipt row of a bought ghost: "mock receipt" while Hedera is mocked (the mock's ids stand for no
        payment), else the payment's own transaction id as HashScan finds it, its nanoseconds cut
        ("0.0.9185802@1762412349")."""
        if self.sponsors.mocked("third"):
            return "mock receipt"
        bought = self.ledger.purchases.get(f"{self.game}:{self._seller}") or {}
        return _tx_id(str(bought.get("receipt") or self.ctx.get("receipt") or ""))

    def _run_frames(self):
        """The run a listing is about: the one just raced, else the best."""
        frames = self.ctx.get("run_frames")
        return self.ctx.get("best_frames") if frames is None else frames

    def _payload(self):
        """What a real adapter needs to know to run the step; the mock ignores it. `title` is the
        game's name as people read it (World App shows it on a listing approval); `arcade_id` the
        arcade game's id (runs and boards are named by it); `frames` the run a listing is about.
        A real board's target names its run, listing, log and time; `receipt` is what was paid
        for the ghost (a listed ghost's key is released against it); `scout_id` the scout's pick this purchase
        follows, if any (INTENT on HCS then says which model picked it and why)."""
        bought = self.ledger.purchases.get(f"{self.game}:{self._seller}") or {}
        return {"game": self.game, "title": self.ctx.get("game"), "seller": self._seller,
                "price": GHOST_PRICE, "book": self.ledger.book, "jti": self._jti,
                "run_time": self.ctx.get("run_time"), "frames": self._run_frames(),
                "best_frames": self.ctx.get("best_frames"),
                "arcade_id": self.ctx.get("arcade_id"), "target_run": self.ctx.get("target_run"),
                "target_listing": self.ctx.get("target_listing"),
                "target_log_h": self.ctx.get("target_log_h"),
                "target_frames": self.ctx.get("target_frames"), "scout_id": self.ctx.get("scout_id"),
                "receipt": bought.get("receipt") or self.ctx.get("receipt")}


def _tx_id(text):
    """A Hedera transaction id as HashScan finds it, its nanoseconds cut ("0.0.9185802@1762412349")."""
    account, at, when = text.partition("@")
    return account + at + when.split(".")[0] if at else text


def _frames(value):
    """A replay's time: a positive whole number of frames."""
    return type(value) is int and value > 0


def _short(key):
    """An Arkiv key or hash as "0x23bf\u2026af44"."""
    return key[:6] + "\u2026" + key[-4:] if len(key) > 12 else key
