"""The console's mock sponsor state: one record book, a daily coach budget, ghosts bought,
listings offered and their sales, kept in handler.json beside settings.py's state.json.

`today` is always a local-date string (YYYY-MM-DD) the caller passes in; the ledger never reads
the clock itself, so tests can cross midnight without waiting for it."""
import json
import os
import time
from dataclasses import dataclass, field

DAILY_BUDGET = 100            # USDC (testnet) cents a day
GHOST_PRICE = 10              # USDC (testnet) cents a ghost
LISTING_DAYS = 7

_BOOK_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"          # no 0/O/1/I/L: read off a console at a glance


@dataclass
class Ledger:
    book: str | None = None
    credential: str = "Selfie Check"
    spent: int = 0                                # cents spent today
    spent_day: str = ""                           # YYYY-MM-DD the above is for
    purchases: dict = field(default_factory=dict)  # "game_id:seller" -> {price, receipt, at}
    listings: list = field(default_factory=list)   # [{game, frames, price, at, sold}]
    pending_sale: dict | None = None
    targets: dict = field(default_factory=dict)    # game_id -> seller
    world_verified: bool = False                  # the real World bridge verified this book: YOU are HUMAN


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return Ledger()
    if not isinstance(data, dict):
        return Ledger()

    led = Ledger()
    if isinstance(data.get("book"), str):
        led.book = data["book"]
    if isinstance(data.get("credential"), str):
        led.credential = data["credential"]
    spent = data.get("spent")
    if isinstance(spent, int) and not isinstance(spent, bool):
        led.spent = spent
    if isinstance(data.get("spent_day"), str):
        led.spent_day = data["spent_day"]
    purchases = data.get("purchases")
    if isinstance(purchases, dict) and all(isinstance(k, str) and isinstance(v, dict) for k, v in purchases.items()):
        led.purchases = purchases
    listings = data.get("listings")
    if isinstance(listings, list) and all(isinstance(x, dict) for x in listings):
        led.listings = listings
    if isinstance(data.get("pending_sale"), dict):
        led.pending_sale = data["pending_sale"]
    targets = data.get("targets")
    if isinstance(targets, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in targets.items()):
        led.targets = targets
    led.world_verified = data.get("world_verified") is True
    return led


def save(path, ledger):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"book": ledger.book, "credential": ledger.credential, "spent": ledger.spent,
                   "spent_day": ledger.spent_day, "purchases": ledger.purchases, "listings": ledger.listings,
                   "pending_sale": ledger.pending_sale, "targets": ledger.targets,
                   "world_verified": ledger.world_verified}, f, indent=1)
    os.replace(tmp, path)


def budget_left(ledger, today):
    """Cents left to spend today, as if spent reset to 0 on any day other than spent_day."""
    spent = ledger.spent if ledger.spent_day == today else 0
    return DAILY_BUDGET - spent


def owns(ledger, game_id, seller):
    return f"{game_id}:{seller}" in ledger.purchases


def buy(ledger, game_id, seller, price, receipt, today, enforce_budget=True):
    """Charge for a ghost, idempotent per (game_id, seller). False, uncharged, if already owned
    or if price would put spent over the daily budget; True, charged and recorded, otherwise.
    enforce_budget=False records a payment that already happened (a late receipt) even past the
    budget: the money moved, so the ledger must show it."""
    key = f"{game_id}:{seller}"
    if key in ledger.purchases:
        return False
    if enforce_budget and budget_left(ledger, today) < price:
        return False
    if ledger.spent_day != today:
        ledger.spent = 0
    ledger.spent += price
    ledger.spent_day = today
    ledger.purchases[key] = {"price": price, "receipt": receipt, "at": time.time()}
    return True


def make_book(rng):
    """A fresh record book id, e.g. ANY-7QZ. rng is a random.Random-like object (uses rng.choice)."""
    return "ANY-" + "".join(rng.choice(_BOOK_CHARS) for _ in range(3))


def start_over(path):
    """For rehearsals: clear the whole mock sponsor state (record book, budget, purchases, listings)."""
    try:
        os.remove(path)
    except OSError:
        pass
    return Ledger()
