"""The Hedera adapter: PB buying the ghost just ahead (x402 on Hedera testnet, paid in testnet USDC by PB's agent in
the service) and the listing's record on HCS, for real, through the World bridge's /hedera/* routes (the HTTP contract
is in docs/superpowers/specs/*-hedera-integration.md), wrapped around the Arkiv adapter, itself around World's. No
Hedera key, account or URL is on the console: it talks only to the service.

- pay: POST /hedera/buy, then the job's stage every 500 ms. PB's agent in the service runs the guards (its caps, the
  listing re-read from Arkiv, the payout account) and pays with no approval step; the step answers with the settled
  payment's transaction id, the receipt load_ghost then hands to /arkiv/ghost. A job outlives the flow's 8 s budget:
  while the flow still polls the call (it keeps it on buy_down), the job is asked on, up to its own life, so a payment
  that settles late still lands (buy_late).
- record: POST /hedera/record (the listing World approved, as publish sends it, without the log but with its log_h,
  so the service can refuse a copied run before anything goes on the topic), then its stage.
- The seller's payout account: pay_to(book) is the book's registered Hedera account as last read (GET
  /hedera/payto/{book}, in the background, kept in state_dir/hedera-payto.json). At approve_scan it is pinned for that
  listing and added to the approve_scan, approve, record and publish payloads, so World App's text, the HCS record
  and the Arkiv listing all name the same account.

All HTTP runs on one background thread with short timeouts. begin(), poll(), status() and pay_to() only read and mark
what that thread last saw, so a slow or missing service never holds up a frame. A failure is always one of the
handler's own states (states.py): an unknown failure name, a non-2xx reply or a host that does not answer is the
step's down state."""
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.parse

from arca_launcher.handler.arkiv import _HASH, _arcade, _is_key, listing_body
from arca_launcher.handler.sponsors import PAY_TO, TIMEOUT_MS, Result
from arca_launcher.handler.world import http_transport

log = logging.getLogger(__name__)

POLL_MS = 500                 # a live job's stage is asked this often
HEALTH_MS = 5000              # and /health this often, while someone is looking
PAYTO_MS = 60000              # a looked-at book's payout account is read again this often
PAYTO_RETRY_MS = 5000         # and this soon after a read that got no usable answer
IDLE_MS = 3000                # no status read, account look or poll this long: nobody is looking, ask nothing
SILENT_MS = 3000              # the service silent this long on a record's stage: not recorded
GRACE_MS = 2000               # a job this long past its life (a record: its budget) is given up
PAY_LIFE_S = 240              # a buy job's life when its start does not say (the contract's expires_s)
START_TIMEOUT_S = 3.0         # a start and its one retry both fit inside the pay step's 8 s
ASK_TIMEOUT_S = 2.0
TICK_S, IDLE_TICK_S = 0.1, 1.0
CACHE_FILE = "hedera-payto.json"
NOW_PRICE_MAX = 24            # a changed listing's price as the card shows it ("gone", "0.25 USDC")

_OWN = ("pay", "record")
_PINNED = ("approve_scan", "approve", "record", "publish")    # the payloads that carry the listing's account
_ROUTE = {"pay": "/hedera/buy", "record": "/hedera/record"}
_STAGES = {"pay": ("guard", "pay", "settle", "done"), "record": ("check", "submit", "done")}
# The handler's own failure names for each step (the spec's failure table). Anything else is the step's down state.
_FAILURES = {"pay": ("buy_budget", "buy_changed", "buy_suspended", "buy_down"),
             "record": ("ls_expired", "ls_wrong", "ls_mismatch", "ls_reused", "ls_copied", "ls_record_fail")}
_DOWN = {"pay": "buy_down", "record": "ls_record_fail"}
# A settled payment's transaction id as the facilitator's settle answers it: <fee payer>@<seconds>.<nanos>.
_TX = re.compile(r"[0-9]{1,10}\.[0-9]{1,10}\.[0-9]{1,10}@[0-9]{1,12}\.[0-9]{1,9}")
_UNSET = object()


class _Job:
    """One Hedera step the worker runs. Read and written under the owner's lock."""

    def __init__(self, step, body, now, key=None):
        self.step, self.body, self.key = step, body, key
        self.start_ms = now
        self.polled_ms = now      # its call was last polled at: a job nobody polls is not asked
        self.result = None        # the terminal Result, once the worker has one
        self.dropped = False      # a newer Hedera step replaced it: nobody asks it any more
        self.id = None            # the service's job id, once the start answered
        self.tries = 0            # starts that got no answer
        self.life_ms = None       # pay: when the service's job runs out (its start's expires_s)
        self.next_ms = now        # when the worker next works on it
        self.silent_since = None  # the first unanswered stage ask in the current run of them

    @property
    def live(self):
        return self.result is None and not self.dropped


class _HederaCall:
    def __init__(self, owner, job):
        self._owner, self._job = owner, job
        self.step = job.step
        self.info = {}            # never a phone step: no code, no link

    @property
    def elapsed_ms(self) -> int:
        return self._owner._clock_ms() - self._job.start_ms

    def poll(self) -> Result | None:
        with self._owner._lock:
            self._owner._look()
            self._job.polled_ms = self._owner._clock_ms()
            return self._job.result


class _Answered:
    """A call that answered as it began: "status" (this adapter's own) and a ghost already paid for."""
    elapsed_ms = 0

    def __init__(self, result):
        self.info = {}
        self._result = result

    def poll(self):
        return self._result


class HederaSponsors:
    """Sponsors with Hedera for real, around inner (the Arkiv adapter over the World adapter: the app wires this one
    only when both are real). service_url: the World bridge, which also runs PB's agent and the HCS record; transport:
    its (method, path, body, timeout_s) as world.http_transport; state_dir: where the payout accounts last read are
    kept."""

    def __init__(self, inner, service_url, clock_ms, state_dir, transport=None, background=True):
        self._inner = inner
        self._send = transport or http_transport(service_url)
        self._clock_ms = clock_ms
        self._state_dir = state_dir
        self._lock = threading.Lock()
        self._job = None           # the latest Hedera step
        self._paid = {}            # (book, game, seller, run) -> the receipt its settled payment gave
        self._health = None        # "ok" | "off" from /health; None until it first answers
        self._health_due = None    # when /health is next asked (None: at once)
        self._accounts = {}        # book -> its registered payout account (None: it has none), as last read
        self._account_due = {}     # book -> when its account is next read
        self._wanted_book = None   # the book whose account someone last looked at
        self._pin = None           # (book, account): what the listing being approved names, from approve_scan on
        self._wanted_ms = clock_ms()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._load_cache()
        self._thread = None
        if background:
            self._thread = threading.Thread(target=self._run, name="hedera", daemon=True)
            self._thread.start()

    # ---- the Sponsors protocol (the frame's side: never waits on the service) ----------------------------------------

    @property
    def names(self):
        return self._inner.names

    @property
    def approvals(self):
        return self._inner.approvals

    @property
    def mock(self):
        """Hedera is real; Square's lists and "Start over (mock)" stay only while World or Arkiv is still mocked."""
        return self._inner.mocked("world") or self._inner.mocked("board")

    def mocked(self, service: str) -> bool:
        return False if service == "third" else self._inner.mocked(service)

    def status(self) -> dict[str, str]:
        out = dict(self._inner.status())
        with self._lock:
            self._look()
            third = self._health or "busy"          # not heard from yet: still checking
            if third == "ok" and self._busy():
                third = "busy"
        out["third"] = third
        return out

    def board(self, game_id: str, look: bool = True):
        return self._inner.board(game_id, look)

    def pay_to(self, book):
        """Where book's sales go: its registered Hedera account (a `0.0.N` id), None when it has none or none was read
        yet. While a listing for book is being approved, the account pinned for it: what World App shows. Asks the
        service in the background on first use, then every PAYTO_MS while someone keeps asking."""
        if not (isinstance(book, str) and book):
            return None
        with self._lock:
            self._look()
            self._wanted_book = book
            if self._clock_ms() >= self._account_due.get(book, 0):
                self._wake.set()
            if self._pin is not None and self._pin[0] == book:
                return self._pin[1]
            return self._accounts.get(book)

    def begin(self, step: str, payload: dict):
        if step == "status":
            return _Answered(Result(ok=True, data=self.status()))
        if step in _PINNED:
            payload = self._pinned(step, payload)
        if step not in _OWN:
            return self._inner.begin(step, payload)
        key, body = _buy(payload) if step == "pay" else (None, listing_body(payload))
        if body is None:
            log.info("Hedera %s: the payload lacks what the service needs", step)
        with self._lock:
            self._look()
            if key is not None and key in self._paid:  # paid already: never twice, the earlier receipt
                return _Answered(Result(ok=True, data={"receipt": self._paid[key]}))
            if self._job is not None:
                self._job.dropped = True               # the flow has one call at a time: the old one is left behind
            self._job = _Job(step, body, self._clock_ms(), key)
            if body is None:
                self._job.result = Result(ok=False, failure=_DOWN[step])
            call = _HederaCall(self, self._job)
        self._wake.set()
        return call

    def cross(self, call) -> None:
        if not isinstance(call, (_HederaCall, _Answered)):
            self._inner.cross(call)

    def cancel(self, call) -> None:
        """A payment or a record is never cancelled from the console (neither is a phone step)."""
        if not isinstance(call, (_HederaCall, _Answered)):
            self._inner.cancel(call)

    def outcomes(self, step: str):
        return [] if step in _OWN else self._inner.outcomes(step)

    def force(self, call, outcome) -> None:
        if not isinstance(call, (_HederaCall, _Answered)):
            self._inner.force(call, outcome)

    def close(self) -> None:
        """Stop the worker (a daemon thread: one stuck in a request never holds the launcher's exit), and inner's."""
        self._stop.set()
        self._wake.set()
        close = getattr(self._inner, "close", None)
        if close is not None:
            close()

    # ---- the worker's side -------------------------------------------------------------------------------------------

    def work(self):
        """One round: the live job's next action when it is due (its start, or its stage while its call is polled),
        the looked-at book's payout account when due, and /health when due. The background thread calls it in a loop;
        a test calls it by hand."""
        now = self._clock_ms()
        with self._lock:
            looking = now - self._wanted_ms < IDLE_MS
            job = self._job if self._job is not None and self._job.live else None
            book = self._wanted_book
            book = book if looking and book is not None and now >= self._account_due.get(book, 0) else None
            health = self._health_due is None or (looking and now >= self._health_due)
        if job is not None:
            self._work_on(job, now)
        if book is not None:
            self._read_account(book)
        if health:
            self._read_health()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.work()
            except Exception:                           # never let the thread die: the next round tries again
                log.exception("Hedera worker")
            with self._lock:
                idle = self._clock_ms() - self._wanted_ms >= IDLE_MS and not self._busy()
            self._wake.wait(IDLE_TICK_S if idle else TICK_S)
            self._wake.clear()

    def _work_on(self, job, now):
        if job.step == "record" and now - job.start_ms >= TIMEOUT_MS["record"] + GRACE_MS:
            self._finish(job, Result(ok=False, failure="ls_record_fail"))     # the flow gave up on it long ago
            return
        if job.life_ms is not None and now >= job.life_ms + GRACE_MS:
            log.info("Hedera %s: the service's job ran out with no end", job.step)
            self._finish(job, Result(ok=False, failure=_DOWN[job.step]))
            return
        with self._lock:
            due = now >= job.next_ms and (job.id is None or now - job.polled_ms < IDLE_MS)
        if not due:
            return
        if job.id is None:
            self._start(job)
        else:
            self._ask(job)

    def _start(self, job):
        """The job's start. One that gets no answer is sent once more, the same body (the service dedupes it); a
        refusal (a non-2xx reply) or a reply off the contract is the step's down state at once. A record's body gains
        the run's log_h here, on the worker (it reads the log from disk), for the service's copy check."""
        if job.step == "record" and "log_h" not in job.body:
            log_h = self._log_hash(job.body)
            if log_h is not None:
                job.body = dict(job.body, log_h=log_h)
        try:
            reply = self._send("POST", _ROUTE[job.step], job.body, START_TIMEOUT_S)
        except urllib.error.HTTPError as e:             # answered, and refused: bad_body, not configured, unavailable
            log.info("Hedera %s refused (HTTP %s)", job.step, e.code)
            self._finish(job, Result(ok=False, failure=_DOWN[job.step]))
            return
        except Exception as e:                          # no answer
            self._silent(e)
            with self._lock:
                job.tries += 1
                again = job.tries < 2
                job.next_ms = self._clock_ms()
            if not again:
                self._finish(job, Result(ok=False, failure=_DOWN[job.step]))
            return
        if not (isinstance(reply, dict) and isinstance(reply.get("id"), str) and reply["id"]):
            self._finish(job, Result(ok=False, failure=_DOWN[job.step]))
            return
        life = reply.get("expires_s")
        life = life if type(life) is int and 0 < life <= 600 else PAY_LIFE_S
        now = self._clock_ms()
        with self._lock:
            job.id = reply["id"]
            job.next_ms = now + POLL_MS
            if job.step == "pay":
                job.life_ms = now + 1000 * life

    def _ask(self, job):
        """The job's stage. A non-2xx reply is the step's down state; silence is waited out: a record's for SILENT_MS,
        a payment's for its whole life (it may still settle, and the flow keeps its call for that)."""
        try:
            reply = _checked(job.step, self._send("GET", f"{_ROUTE[job.step]}/{_quote(job.id)}", None,
                                                  ASK_TIMEOUT_S))
        except urllib.error.HTTPError as e:
            log.info("Hedera %s job not answered (HTTP %s)", job.step, e.code)
            self._finish(job, Result(ok=False, failure=_DOWN[job.step]))
            return
        except Exception as e:
            self._silent(e)
            reply = None
        now = self._clock_ms()
        with self._lock:
            job.next_ms = now + POLL_MS
            if reply is None:
                if job.silent_since is None:
                    job.silent_since = now
                gave_up = job.step == "record" and now - job.silent_since >= SILENT_MS
            else:
                job.silent_since, gave_up = None, False
        if gave_up:
            self._finish(job, Result(ok=False, failure="ls_record_fail"))
        elif reply is not None and reply["stage"] == "done":
            self._finish(job, _outcome(job.step, reply))

    def _log_hash(self, body):
        """The run's log_h from the Arkiv adapter (inner), or None when it has none (then the record goes without)."""
        hash_of = getattr(self._inner, "run_log_hash", None)
        if hash_of is None:
            return None
        try:
            log_h = hash_of(body["game"], body["frames"])
        except Exception:
            log.exception("Hedera record: hashing the run's log")
            return None
        return log_h if isinstance(log_h, str) and _HASH.fullmatch(log_h) else None

    def _finish(self, job, result):
        with self._lock:
            if job.result is not None:
                return
            job.result = result
            if result.ok and job.step == "pay" and job.key is not None:
                self._paid[job.key] = result.data["receipt"]
        if result.ok and job.step == "pay":
            log.info("Hedera paid %s for %s's %s ghost: %s%s", job.body["book"], job.body["seller"], job.body["game"],
                     result.data["receipt"], " (late)" if result.data.get("late") else "")
        elif result.ok:
            log.info("Hedera recorded %s's listing: topic %s message %s", job.body["book"], result.data.get("topic"),
                     result.data.get("seq"))
        else:
            log.info("Hedera %s: %s", job.step, result.failure)

    def _silent(self, e):
        """The service did not answer: Hedera shows off until /health says ok. Said once an outage."""
        with self._lock:
            was, self._health = self._health, "off"
        if was != "off":
            log.info("Hedera service not answering (%s)", type(e).__name__)

    def _read_account(self, book):
        try:
            reply = self._send("GET", f"/hedera/payto/{_quote(book)}", None, ASK_TIMEOUT_S)
        except Exception:                               # not up, or Hedera not configured: the last word stands
            reply = None
        account = reply.get("pay_to") if isinstance(reply, dict) else _UNSET
        usable = (isinstance(reply, dict) and reply.get("book") == book
                  and (account is None or (isinstance(account, str) and PAY_TO.fullmatch(account))))
        now = self._clock_ms()
        with self._lock:
            if not usable:
                self._account_due[book] = now + PAYTO_RETRY_MS
                return
            changed = self._accounts.get(book, _UNSET) != account
            self._accounts[book] = account
            self._account_due[book] = now + PAYTO_MS
        if changed:
            log.info("Hedera: %s's sales go to %s", book, account or "no account yet")
            self._save_cache()

    def _read_health(self):
        try:
            reply = self._send("GET", "/health", None, ASK_TIMEOUT_S)
        except Exception:
            reply = None
        health = ("ok" if isinstance(reply, dict) and reply.get("hedera") == "ok" and reply.get("hedera_pay") is True
                  else "off")
        with self._lock:
            was, self._health = self._health, health
            self._health_due = self._clock_ms() + HEALTH_MS
        if health != was:
            log.info("Hedera %s", "ready to pay" if health == "ok" else "can not pay right now (/health)")

    # ---- the payout account pinned for a listing ---------------------------------------------------------------------

    def _pinned(self, step, payload):
        """payload with the account its listing names (pay_to): pinned at approve_scan from the book's account as last
        read, the same one for the approve, record and publish that follow, whatever a later read says."""
        book = payload.get("book")
        with self._lock:
            if step == "approve_scan":
                self._pin = (book, self._accounts.get(book) if isinstance(book, str) and book else None)
                pinned = True
            else:
                pinned = False
            pin = self._pin
        if pinned:
            log.info("Hedera: listing for %s pays %s", book, pin[1] or "no account (not for sale)")
        if pin is None or pin[0] != book:
            return payload
        return dict(payload, pay_to=pin[1])

    # ---- the accounts' cache -----------------------------------------------------------------------------------------

    def _cache_path(self):
        return os.path.join(self._state_dir or ".", CACHE_FILE)

    def _load_cache(self):
        """The accounts last read, until a read of their own replaces them (each is read again on first use)."""
        try:
            with open(self._cache_path(), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        accounts = data.get("accounts") if isinstance(data, dict) else None
        if not isinstance(accounts, dict):
            return
        for book, account in accounts.items():
            if isinstance(book, str) and book and (account is None or (isinstance(account, str)
                                                                       and PAY_TO.fullmatch(account))):
                self._accounts[book] = account

    def _save_cache(self):
        with self._lock:
            data = {"v": 1, "accounts": dict(self._accounts)}
        path = self._cache_path()
        try:
            os.makedirs(self._state_dir or ".", exist_ok=True)
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(path + ".tmp", path)
        except OSError as e:
            log.warning("Hedera accounts not saved (%s)", type(e).__name__)

    # ---- under the lock ----------------------------------------------------------------------------------------------

    def _look(self):
        """Someone is looking: the worker asks again (at once, if it had gone quiet)."""
        now = self._clock_ms()
        if now - self._wanted_ms >= IDLE_MS:
            self._wake.set()
        self._wanted_ms = now

    def _busy(self):
        """A Hedera step runs and its call is still polled (a kept payment nobody watches any more is not busy)."""
        job = self._job
        return job is not None and job.live and self._clock_ms() - job.polled_ms < IDLE_MS


def _buy(p):
    """(the purchase's key, the contract's POST /hedera/buy body) for a pay payload, or (None, None) when it does not
    name a real target: the buyer's book, the arcade game, the seller, her listing, run, log and time, and the price."""
    game, book, seller = _arcade(p), p.get("book"), p.get("seller")
    listing, run, log_h = p.get("target_listing"), p.get("target_run"), p.get("target_log_h")
    frames, you, price = p.get("target_frames"), p.get("frames"), p.get("price")
    if not (game and isinstance(book, str) and book and isinstance(seller, str) and seller and _is_key(listing)
            and _is_key(run) and isinstance(log_h, str) and _HASH.fullmatch(log_h) and type(frames) is int
            and type(price) is int):
        return None, None
    body = {"book": book, "game": game, "seller": seller, "listing": listing.lower(), "run": run.lower(),
            "log_h": log_h, "frames": frames, "you_frames": you if type(you) is int else None, "price_c": price}
    return (book, game, seller, run.lower()), body


def _quote(text):
    return urllib.parse.quote(text, safe="")


def _checked(step, reply):
    """A job's GET reply in the contract's shape, or None (counted as no answer)."""
    if not isinstance(reply, dict) or reply.get("stage") not in _STAGES[step]:
        return None
    data = reply.get("data")
    return {"stage": reply["stage"], "ok": reply.get("ok"), "failure": reply.get("failure"),
            "data": dict(data) if isinstance(data, dict) else {}}


def _outcome(step, reply):
    """A done job as the step's Result. A failure the handler has no screen for, a changed listing that does not say
    its price now, or a payment without its transaction id is the step's down state: the console never makes one up.
    Only the fields a screen or load_ghost uses are kept."""
    data = reply["data"]
    if reply["ok"] is not True:
        failure = reply["failure"]
        if failure not in _FAILURES[step]:
            return Result(ok=False, failure=_DOWN[step])
        if failure != "buy_changed":
            return Result(ok=False, failure=failure)
        now_price = data.get("now_price")
        if not (isinstance(now_price, str) and 0 < len(now_price) <= NOW_PRICE_MAX and now_price.isprintable()):
            return Result(ok=False, failure="buy_down")
        return Result(ok=False, failure=failure, data={"now_price": now_price})
    if step == "pay":
        receipt = data.get("receipt")
        if not (isinstance(receipt, str) and _TX.fullmatch(receipt)):
            return Result(ok=False, failure="buy_down")
        out = {"receipt": receipt, "late": data.get("late") is True}
        if isinstance(data.get("hashscan"), str) and data["hashscan"].startswith("https://hashscan.io/"):
            out["hashscan"] = data["hashscan"]
        return Result(ok=True, data=out)
    out = {name: data[name] for name in ("topic", "tx", "hashscan") if isinstance(data.get(name), str)}
    if type(data.get("seq")) is int:
        out["seq"] = data["seq"]
    return Result(ok=True, data=out)
