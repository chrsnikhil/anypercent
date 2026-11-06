"""The Arkiv adapter: PB's board, listing check, ghost and listing for real on Arkiv's Rabdi testnet (the spec:
docs/superpowers/specs/*-arkiv-integration.md, Part B), wrapped around the World adapter, which keeps World's own
steps. Hedera's steps (pay, record) stay the mock's here; with Hedera real, the Hedera adapter (hedera.py) wraps this
one and runs them.

- Reads go straight to the public Arkiv RPC (arkiv_rpc.py: Q1, Q2 and Q6, every one pinned to our checker's
  `$creator`): the board, check_listing and a plain ghost. No key on the console, nothing of ours in the way.
- Two steps need our service, on the World bridge's /arkiv/* routes: publish (the checker replays the run and writes its
  run and listing rows, after a World approval) and a listed ghost (its key never leaves the service).
- sales never reports a sale: real sales arrive with Hedera, and a real board shows no made-up ones.
- A run row's lap times (splits) come with it and are kept in the cache; a listing is a person's (book) or the house's
  BOT ghost (label). The explorer's origin comes from the service's /arkiv/config: only links there are ever drawn.

All network work and every replay runs on one background thread. begin(), poll(), status() and board() only read and
mark what that thread last saw, so a slow or missing Arkiv never holds up a frame. The thread reads every arcade game's
board once at start, then the open game's every 15 s while someone is looking. Boards are kept in memory and in
state_dir/arkiv-boards.json with each read's block, so an outage still shows the last board read, marked stale.

A failure is always one of the handler's own states (states.py): an unknown failure name, a non-2xx reply or a host
that does not answer is the step's down state."""
import base64
import binascii
import dataclasses
import hashlib
import json
import logging
import os
import re
import threading
import urllib.parse
from decimal import Decimal

from arca_launcher.handler import arkiv_rpc
from arca_launcher.handler.ledger import GHOST_PRICE
from arca_launcher.handler.sponsors import PAY_TO, TIMEOUT_MS, BoardRead, Result, RunRow
from arca_launcher.handler.world import _digest, _pay_to, _title, http_transport

log = logging.getLogger(__name__)

ARCADE_GAMES = ("SHIP", "MDGP", "RUSH", "SEGF", "ZIPG")
REFRESH_MS = 15000            # the open game's board is read again this often, while someone is looking
IDLE_MS = 3000                # no status read, board look or poll this long: nobody is looking
POLL_MS = 500                 # a publish's stage is asked this often
SILENT_MS = 3000              # the service silent this long on a publish's stage: not listed
GRACE_MS = 2000               # a step still running this long past its budget is given up (the flow already has)
CONFIG_RETRY_MS = 60000       # the service's /arkiv/config, asked again this often until it answers once
START_TIMEOUT_S = 5.0         # the publish start carries the run's log
ASK_TIMEOUT_S = 3.0
TICK_S, IDLE_TICK_S = 0.1, 1.0
CACHE_FILE = "arkiv-boards.json"
LOG_MIN, LOG_MAX = 32, 64 * 1024      # a run log's size, as the service takes it

_OWN = ("check_listing", "publish", "sales")   # and load_ghost, when its payload names a real target (target_run)
_DOWN = {"check_listing": "buy_check_fail", "load_ghost": "buy_load_fail", "publish": "ls_publish_fail"}
_PUBLISH_FAILURES = ("ls_expired", "ls_wrong", "ls_mismatch", "ls_reused", "ls_copied", "ls_publish_fail")
_STAGES = ("check", "write", "done")
_GAME = re.compile(r"[A-Z0-9]{4}")
_KEY = re.compile(r"0x[0-9a-f]{64}")
_HASH = re.compile(r"[0-9a-f]{64}")
# RunRow's fields as the cache file holds them: (type, may be None).
_ROW_FIELDS = {"key": (str, False), "game": (str, False), "title": (str, False), "frames": (int, False),
               "runner": (str, False), "book": (str, True), "label": (str, True), "human": (bool, False),
               "credential": (str, True), "log_h": (str, False), "rules": (int, False),
               "expires_block": (int, False), "listing": (str, True), "price": (str, True), "pay_to": (str, True),
               "splits": (list, True)}
LINK_MAX = 300                # an explorer link's length, as the service builds them (an Arkiv tx's is about 106)
_ORIGIN = re.compile(r"https://[a-z0-9.-]{1,200}(:[0-9]{1,5})?")


class _Job:
    """One Arkiv step the worker runs. Read and written under the owner's lock."""

    def __init__(self, step, payload, now):
        self.step, self.payload = step, payload
        self.start_ms = now
        self.result = None        # the terminal Result, once the worker has one
        self.dropped = False      # a newer step replaced it: nobody asks it any more
        self.id = None            # publish: the service's job id, once the start answered
        self.started = False      # publish: the start was sent
        self.next_ms = now        # when the worker next works on it
        self.silent_since = None  # publish: the first unanswered stage ask in the current run of them

    @property
    def live(self):
        return self.result is None and not self.dropped


class _ArkivCall:
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
            return self._job.result


class _Answered:
    """A call that answered as it began: "status" (this adapter's own) and "sales" (never a sale)."""
    elapsed_ms = 0

    def __init__(self, result):
        self.info = {}
        self._result = result

    def poll(self):
        return self._result


class ArkivSponsors:
    """Sponsors with Arkiv for real, around inner (the World adapter, or the mock): World as inner has it, Hedera still
    mocked. rpc: the Arkiv RPC's URL, or a (method, params, timeout_s) transport; transport: the service's, as
    world.http_transport; replay(arcade_id, log_path) -> the time the game's replay tool gives that log (None: it does
    not finish, or the tool failed); games: the arcade ids whose boards are read at start."""

    mock = True     # Hedera still is: its Square outcome lists and "Start over (mock)" stay

    def __init__(self, inner, service_url, rpc, checker, season, runs_dir, state_dir, clock_ms, transport=None,
                 background=True, replay=None, games=ARCADE_GAMES):
        self._inner = inner
        self._send = transport or http_transport(service_url)
        self._rpc = rpc if callable(rpc) else arkiv_rpc.rpc_transport(rpc)
        self._checker = arkiv_rpc.checker_address(checker)
        arkiv_rpc.q1("MDGP", season, self._checker)      # a season no query takes fails here, not on every read
        self._season = season
        self._runs_dir, self._state_dir = runs_dir, state_dir
        self._clock_ms = clock_ms
        self._replay = replay
        self._games = tuple(dict.fromkeys(g for g in games if isinstance(g, str) and _GAME.fullmatch(g)))
        self._lock = threading.Lock()
        self._reads = {}           # arcade id -> its BoardRead
        self._tried = set()        # arcade ids read, or tried, since start
        self._due = {}             # arcade id -> when its board is next read
        self._open = None          # the game whose board someone looks at
        self._rpc_ok = None        # the last Arkiv read: True answered, False failed, None none yet
        self._job = None           # the latest Arkiv step
        self._config_due = 0       # when /arkiv/config is next asked; None once it answered
        self.pin_differs = None    # what the service's /arkiv/config says that this console's pin does not (or None)
        self.explorer_origin = None   # the Arkiv explorer's https origin /arkiv/config names: links there may be drawn
        self._wanted_ms = clock_ms()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._load_cache()
        self._thread = None
        if background:
            self._thread = threading.Thread(target=self._run, name="arkiv", daemon=True)
            self._thread.start()

    # ---- the Sponsors protocol (the frame's side: never waits on Arkiv or the service) -------------------------------

    @property
    def names(self):
        return self._inner.names

    @property
    def approvals(self):
        return self._inner.approvals

    scouts = False  # PB's scout runs only with Hedera real (hedera.py)

    def mocked(self, service: str) -> bool:
        return False if service == "board" else self._inner.mocked(service)

    @property
    def console_id(self):
        """This console's id, World's (None while World is mocked)."""
        return getattr(self._inner, "console_id", None)

    def console_state(self):
        """This console's binding, as World's bridge last said it (None while World is mocked)."""
        read = getattr(self._inner, "console_state", None)
        return read() if read is not None else None

    def chain_update(self):
        """Hedera's late chain ids: the Hedera adapter's. Here there are none."""
        return None

    def status(self) -> dict[str, str]:
        out = dict(self._inner.status())
        with self._lock:
            self._look()
            busy = self._job is not None and self._job.live
            out["board"] = "off" if self._rpc_ok is False else "busy" if busy else "ok"
        return out

    def board(self, game_id: str, look: bool = True):
        with self._lock:
            if look and isinstance(game_id, str) and _GAME.fullmatch(game_id):
                self._look()
                self._open = game_id
                if self._clock_ms() >= self._due.get(game_id, 0):
                    self._wake.set()
            return self._reads.get(game_id)

    def begin(self, step: str, payload: dict):
        if step == "status":
            return _Answered(Result(ok=True, data=self.status()))
        if step == "sales":
            return _Answered(Result(ok=False))         # a real board never makes a sale up
        if step not in _OWN and not (step == "load_ghost" and payload.get("target_run")):
            return self._inner.begin(step, payload)
        with self._lock:
            self._look()
            if self._job is not None:
                self._job.dropped = True               # the flow has one call at a time: the old one is left behind
            self._job = _Job(step, dict(payload), self._clock_ms())
            call = _ArkivCall(self, self._job)
        self._wake.set()
        return call

    def cross(self, call) -> None:
        if not isinstance(call, _ArkivCall):
            self._inner.cross(call)

    def cancel(self, call) -> None:
        if not isinstance(call, _ArkivCall):
            self._inner.cancel(call)

    def outcomes(self, step: str):
        return [] if step in _OWN else self._inner.outcomes(step)

    def force(self, call, outcome) -> None:
        if not isinstance(call, _ArkivCall):
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
        """One round: the live step's next action when it is due, else one board read when one is due (every arcade
        game once at start, then the open game every REFRESH_MS while someone looks), else the service's config check
        once. The background thread calls it in a loop; a test calls it by hand."""
        now = self._clock_ms()
        with self._lock:
            job = self._job if self._job is not None and self._job.live else None
            game = self._due_game(now) if job is None else None
            config = job is None and game is None and self._config_due is not None and now >= self._config_due
        if job is not None:
            if now - job.start_ms >= TIMEOUT_MS[job.step] + GRACE_MS:
                self._finish(job, Result(ok=False, failure=_DOWN[job.step]))
            elif now >= job.next_ms:
                self._step(job)
        elif game is not None:
            self._read_board(game)
        elif config:
            self._check_config()

    def _check_config(self):
        """The service's GET /arkiv/config, only to warn when this console's pin (checker, season) is not the one its
        rows are written under: those rows would never show on this board. Never changes the pin itself."""
        try:
            reply = self._send("GET", "/arkiv/config", None, ASK_TIMEOUT_S)
        except Exception:                               # not up yet: ask again later
            with self._lock:
                self._config_due = self._clock_ms() + CONFIG_RETRY_MS
            return
        differs = []
        if not isinstance(reply, dict):
            differs.append("no config")
        else:
            try:
                if arkiv_rpc.checker_address(reply.get("checker")) != self._checker:
                    differs.append(f"checker {reply.get('checker')}")
            except ValueError:
                differs.append("no checker")
            if reply.get("season") != self._season:
                differs.append(f"season {reply.get('season')!r}")
        origin = _explorer_origin(reply) if isinstance(reply, dict) else None
        with self._lock:
            self._config_due = None
            self.pin_differs = ", ".join(differs) or None
            self.explorer_origin = origin
        if differs:
            log.warning("Arkiv: the service writes under %s, but this console reads %s season %s: its listings "
                        "will not show on this board", self.pin_differs, arkiv_rpc.eip55(self._checker), self._season)

    def _run(self):
        while not self._stop.is_set():
            try:
                self.work()
            except Exception:                           # never let the thread die: the next round tries again
                log.exception("Arkiv worker")
            with self._lock:
                now = self._clock_ms()
                idle = (now - self._wanted_ms >= IDLE_MS and not (self._job is not None and self._job.live)
                        and all(g in self._tried for g in self._games))
            self._wake.wait(IDLE_TICK_S if idle else TICK_S)
            self._wake.clear()

    def _due_game(self, now):
        """Under the lock: the board to read now, or None. The board someone is looking at comes first, then any not
        read since start."""
        game = self._open
        if (game is not None and now - self._wanted_ms < IDLE_MS
                and (game not in self._tried or now >= self._due.get(game, 0))):
            return game
        return next((game for game in self._games if game not in self._tried), None)

    def _read_board(self, game):
        try:
            rows, block, dropped = arkiv_rpc.read_board(self._rpc, game, self._season, self._checker)
        except (arkiv_rpc.RpcError, ValueError) as e:
            with self._lock:
                self._tried.add(game)
                self._due[game] = self._clock_ms() + REFRESH_MS
                old = self._reads.get(game)
                if old is not None and not old.stale:
                    self._reads[game] = dataclasses.replace(old, stale=True)
                self._read_failed(e)
            return
        with self._lock:
            self._tried.add(game)
            self._due[game] = self._clock_ms() + REFRESH_MS
            old = self._reads.get(game)
            same = old is not None and old.rows == rows
            # Nothing new on the board: the same rows object, so the frame side has nothing to rebuild, and the
            # cache file nothing to rewrite.
            self._reads[game] = BoardRead(rows=old.rows if same else rows, block=block, stale=False)
            self._rpc_ok = True
        if dropped:
            log.info("Arkiv %s board: %d rows dropped (not our checker's, or misfit)", game, dropped)
        if not same:
            self._save_cache()

    def _read_failed(self, e):
        """Under the lock: an Arkiv read failed. Said once an outage, never with a key or a receipt."""
        if self._rpc_ok is not False:
            log.info("Arkiv not answering (%s)", type(e).__name__)
        self._rpc_ok = False

    def _rpc_read(self, read, *args, **kwargs):
        """read(rpc, *args) for a step; (row or None, True) when Arkiv answered, (None, False) when it did not."""
        try:
            row = read(self._rpc, *args, **kwargs)
        except (arkiv_rpc.RpcError, ValueError) as e:
            with self._lock:
                self._read_failed(e)
            return None, False
        with self._lock:
            self._rpc_ok = True
        return row, True

    def _step(self, job):
        try:
            result = {"check_listing": self._check, "load_ghost": self._load, "publish": self._publish}[job.step](job)
        except Exception:                               # a bug, a full disk: the step's down state, never a crash
            log.exception("Arkiv %s", job.step)
            result = Result(ok=False, failure=_DOWN[job.step])
        if result is not None:
            self._finish(job, result)

    def _finish(self, job, result):
        with self._lock:
            if job.result is None:
                job.result = result

    # ---- check_listing: the listing and its run, re-read from Arkiv --------------------------------------------------

    def _check(self, job):
        p = job.payload
        listing_key, run_key, log_h = p.get("target_listing"), p.get("target_run"), p.get("target_log_h")
        if not (_is_key(listing_key) and _is_key(run_key)):
            return Result(ok=False, failure="buy_check_fail")
        listing, answered = self._rpc_read(arkiv_rpc.read_listing, listing_key, self._checker)
        if not answered:
            return Result(ok=False, failure="buy_check_fail")
        if listing is None:
            self._refresh(p)
            return Result(ok=False, failure="buy_changed", data={"now_price": "gone"})
        price = Decimal(listing["price"])
        if price * 100 != GHOST_PRICE:
            self._refresh(p)
            return Result(ok=False, failure="buy_changed", data={"now_price": f"{_price(price)} USDC"})
        if listing["run"] != run_key.lower():
            return Result(ok=False, failure="buy_suspended")
        run, answered = self._rpc_read(arkiv_rpc.read_run, run_key, self._checker)
        if not answered:
            return Result(ok=False, failure="buy_check_fail")
        if run is None or run["log_h"] != listing["log_h"] or (log_h is not None and run["log_h"] != log_h):
            self._refresh(p)
            return Result(ok=False, failure="buy_suspended")
        return Result(ok=True, data={"price": GHOST_PRICE})

    def _refresh(self, payload):
        """The board under a purchase or a listing changed: read it again at the next chance, looked at or not."""
        game = _arcade(payload)
        if game is not None:
            with self._lock:
                self._due[game] = 0
                self._tried.discard(game)

    # ---- load_ghost: the log from the row (plain) or the service (listed), checked against the row -------------------

    def _load(self, job):
        p = job.payload
        run_key, log_h, game = p.get("target_run"), p.get("target_log_h"), _arcade(p)
        fail = Result(ok=False, failure="buy_load_fail")
        if not (_is_key(run_key) and isinstance(log_h, str) and _HASH.fullmatch(log_h) and game):
            return fail
        path = os.path.join(self._runs_dir, "ghosts", log_h + ".acl")
        if _file_hash(path) == log_h:                   # checked and replayed when it was written: no network
            return Result(ok=True, data={"ghost_log": path})
        run, _ = self._rpc_read(arkiv_rpc.read_run, run_key, self._checker, with_log=True)
        frames = p.get("target_frames")
        if run is None or run["log_h"] != log_h or (type(frames) is int and run["frames"] != frames):
            return fail
        data = run["log"] if run["log"] is not None else self._listed_ghost(run_key, p.get("receipt"))
        if data is None or not LOG_MIN <= len(data) <= LOG_MAX or hashlib.sha256(data).hexdigest() != log_h:
            return fail
        os.makedirs(os.path.dirname(path), exist_ok=True)
        part = path + ".part"
        with open(part, "wb") as f:
            f.write(data)
        try:
            replayed = self._replayed(game, part)
            if replayed != run["frames"]:
                log.info("Arkiv ghost for %s: the replay says %s, the row %s", game, replayed, run["frames"])
                return fail
            os.replace(part, path)
        finally:
            if os.path.exists(part):
                os.unlink(part)
        return Result(ok=True, data={"ghost_log": path})

    def _listed_ghost(self, run_key, receipt):
        """A listed run's plain log from the service (it holds the key), against the payment receipt; None if not."""
        if not isinstance(receipt, str) or not receipt:
            return None
        try:
            reply = self._send("POST", "/arkiv/ghost", {"run": run_key.lower(), "receipt": receipt}, ASK_TIMEOUT_S)
        except Exception as e:                          # no answer, an error status (402, 404, 503), not JSON
            log.info("Arkiv ghost not served (%s)", type(e).__name__)
            return None
        text = reply.get("log") if isinstance(reply, dict) else None
        if not isinstance(text, str):
            return None
        try:
            return base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError):
            return None

    def _replayed(self, game, path):
        if self._replay is None:                        # nothing to check the time with: not loaded
            return None
        try:
            frames = self._replay(game, path)
        except Exception:
            log.exception("Arkiv ghost replay for %s", game)
            return None
        return frames if type(frames) is int else None

    # ---- publish: the service replays the run and writes its rows ----------------------------------------------------

    def _publish(self, job):
        now = self._clock_ms()
        if not job.started:
            job.started = True
            body = self._publish_body(job.payload)
            if body is None:
                return Result(ok=False, failure="ls_publish_fail")
            try:
                reply = self._send("POST", "/arkiv/publish", body, START_TIMEOUT_S)
            except Exception as e:                      # no answer, an error status, not JSON
                log.info("Arkiv publish not taken (%s)", type(e).__name__)
                return Result(ok=False, failure="ls_publish_fail")
            if not (isinstance(reply, dict) and isinstance(reply.get("id"), str) and reply["id"]):
                return Result(ok=False, failure="ls_publish_fail")
            with self._lock:
                job.id, job.next_ms = reply["id"], self._clock_ms() + POLL_MS
            return None
        try:
            reply = _checked(self._send("GET", f"/arkiv/publish/{urllib.parse.quote(job.id, safe='')}", None,
                                        ASK_TIMEOUT_S))
        except Exception:
            reply = None
        with self._lock:
            job.next_ms = now + POLL_MS
            if reply is None:
                if job.silent_since is None:
                    job.silent_since = now
                elif now - job.silent_since >= SILENT_MS:
                    return Result(ok=False, failure="ls_publish_fail")
                return None
            job.silent_since = None
        if reply["stage"] != "done":
            return None
        result = _published(reply)
        if result.ok:
            log.info("Arkiv listed %s: run %s listing %s", job.payload.get("run_time"), result.data["run"][:10],
                     result.data["listing"][:10])
            self._refresh(job.payload)
        return result

    def _publish_body(self, p):
        """The contract's POST /arkiv/publish body, or None when the run's log is not on this console: listing_body
        and the run's log."""
        body = listing_body(p)
        if body is None:
            return None
        path = self.run_log_path(body["game"], body["frames"])
        if path is None:
            log.info("Arkiv publish: no %s log of %d frames on this console", body["game"], body["frames"])
            return None
        with open(path, "rb") as f:
            data = f.read(LOG_MAX + 1)
        if not LOG_MIN <= len(data) <= LOG_MAX:
            return None
        return dict(body, log=base64.b64encode(data).decode("ascii"))

    def run_log_hash(self, game, frames):
        """sha256 (hex) of this console's log of game's run of frames, as publish would send it; None if it is not here.
        It reads the disk: only a worker thread calls it (the Hedera record's copy check), never a frame."""
        path = self.run_log_path(game, frames)
        if path is None:
            return None
        try:
            with open(path, "rb") as f:
                data = f.read(LOG_MAX + 1)
        except OSError:
            return None
        return hashlib.sha256(data).hexdigest() if LOG_MIN <= len(data) <= LOG_MAX else None

    def run_log_path(self, game, frames):
        """runs_dir/best/<ID>.acl when that best is this time, else the queued run of this time; None if neither. It
        reads the disk: only a worker thread calls it (publish, the record's copy check, the scout), never a frame."""
        best = os.path.join(self._runs_dir, "best", game)
        if _time_frames(best + ".json") == frames and os.path.isfile(best + ".acl"):
            return best + ".acl"
        queue = os.path.join(self._runs_dir, "queue")
        try:
            names = sorted(os.listdir(queue))
        except OSError:
            return None
        for name in names:
            stem = os.path.join(queue, name[:-len(".json")])
            if (name.startswith(game + "-") and name.endswith(".json") and _time_frames(stem + ".json") == frames
                    and os.path.isfile(stem + ".acl")):
                return stem + ".acl"
        return None

    # ---- the board cache ---------------------------------------------------------------------------------------------

    def _cache_path(self):
        return os.path.join(self._state_dir, CACHE_FILE)

    def _load_cache(self):
        """The boards last read, shown stale until a read of their own: only ones read for this checker and season."""
        try:
            with open(self._cache_path(), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if not (isinstance(data, dict) and data.get("checker") == self._checker and data.get("season") == self._season
                and isinstance(data.get("boards"), dict)):
            return
        for game, board in data["boards"].items():
            if not (isinstance(game, str) and _GAME.fullmatch(game) and isinstance(board, dict)
                    and type(board.get("block")) is int and isinstance(board.get("rows"), list)):
                continue
            rows = tuple(_cached_row(row) for row in board["rows"])
            if all(row is not None and row.game == game for row in rows):
                self._reads[game] = BoardRead(rows=rows, block=board["block"], stale=True)

    def _save_cache(self):
        """The boards to state_dir, on the worker, only after a read that changed one; a row is copied field by field
        (dataclasses.asdict deep-copies, too slow on a Pi), and the lock is held only to take the reads."""
        with self._lock:
            reads = list(self._reads.items())
        boards = {game: {"block": read.block, "rows": [{name: getattr(row, name) for name in _ROW_FIELDS}
                                                       for row in read.rows]}
                  for game, read in reads}
        data = {"v": 1, "checker": self._checker, "season": self._season, "boards": boards}
        path = self._cache_path()
        try:
            os.makedirs(self._state_dir or ".", exist_ok=True)
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(path + ".tmp", path)
        except OSError as e:
            log.warning("Arkiv board cache not saved (%s)", type(e).__name__)

    # ---- under the lock ----------------------------------------------------------------------------------------------

    def _look(self):
        """Someone is looking: the worker asks again (at once, if it had gone quiet)."""
        now = self._clock_ms()
        if now - self._wanted_ms >= IDLE_MS:
            self._wake.set()
        self._wanted_ms = now


def listing_body(p):
    """What the service is told about a World-approved listing (POST /arkiv/publish without its log, and POST
    /hedera/record as it is), or None when the payload lacks any of it. action is the very digest World App showed
    (world._digest of the same payload), so it hashes to what was approved; pay_to, the seller's Hedera account the
    approval named, only when it named one."""
    game, frames, price = _arcade(p), p.get("frames"), p.get("price")
    if not (game and type(frames) is int and type(price) is int and isinstance(p.get("book"), str)
            and isinstance(p.get("jti"), str) and p["book"] and p["jti"]):
        return None
    body = {"book": p["book"], "jti": p["jti"], "action": _digest(p), "game": game, "title": _title(p),
            "frames": frames, "price_c": price}
    account = _pay_to(p)
    if account is not None:
        body["pay_to"] = account
    return body


def _is_key(value):
    return isinstance(value, str) and _KEY.fullmatch(value.lower()) is not None


def _arcade(payload):
    """The arcade id a payload is about (the flow's own game id is the library's)."""
    for value in (payload.get("arcade_id"), payload.get("game")):
        if isinstance(value, str) and _GAME.fullmatch(value):
            return value
    return None


def _price(price):
    """A listing's price as PB says it: two decimals, more only when it has them ("0.50", "0.105")."""
    return f"{price:.2f}" if price == price.quantize(Decimal("0.01")) else format(price.normalize(), "f")


def _file_hash(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read(LOG_MAX + 1)).hexdigest()
    except OSError:
        return None


def _time_frames(path):
    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f).get("time_frames")
    except (OSError, ValueError, AttributeError):
        return None
    return value if type(value) is int else None


def _cached_row(row):
    """A RunRow from the cache file, or None when the entry is not one. A row cached before listings named a payout
    account has no pay_to: not for sale; one cached before lap times, or with laps that do not add up, has none."""
    if isinstance(row, dict) and "pay_to" not in row:
        row = dict(row, pay_to=None)
    if isinstance(row, dict):
        laps = row.get("splits")
        good = (isinstance(laps, list) and 0 < len(laps) <= 4 and all(type(x) is int and x > 0 for x in laps)
                and sum(laps) == row.get("frames"))
        row = dict(row, splits=laps if good else None)
    if not isinstance(row, dict) or set(row) != set(_ROW_FIELDS):
        return None
    for name, (kind, optional) in _ROW_FIELDS.items():
        value = row[name]
        if not ((value is None and optional) or type(value) is kind):
            return None
    if not (_KEY.fullmatch(row["key"]) and _HASH.fullmatch(row["log_h"]) and _GAME.fullmatch(row["game"])
            and (row["listing"] is None or _KEY.fullmatch(row["listing"])) and (row["book"] or row["label"])
            and (row["pay_to"] is None or PAY_TO.fullmatch(row["pay_to"]))):
        return None
    return RunRow(**dict(row, splits=tuple(row["splits"]) if row["splits"] is not None else None))


def _checked(reply):
    """GET /arkiv/publish/{id}'s reply in the contract's shape, or None (counted as no answer)."""
    if not isinstance(reply, dict) or reply.get("stage") not in _STAGES:
        return None
    data = reply.get("data")
    return {"stage": reply["stage"], "ok": reply.get("ok"), "failure": reply.get("failure"),
            "data": dict(data) if isinstance(data, dict) else {}}


def _published(reply):
    """A done publish as the step's Result. A failure the handler has no screen for, or a success without both row
    keys and the transaction, is "not listed yet": the console never shows a listing it cannot name."""
    if reply["ok"] is not True:
        failure = reply["failure"]
        return Result(ok=False, failure=failure if failure in _PUBLISH_FAILURES else "ls_publish_fail")
    data = reply["data"]
    keys = [data.get(name) for name in ("run", "listing", "tx")]
    if not all(isinstance(value, str) and _KEY.fullmatch(value.lower()) for value in keys):
        return Result(ok=False, failure="ls_publish_fail")
    out = {"run": keys[0].lower(), "listing": keys[1].lower(), "tx": keys[2].lower()}
    links = data.get("explorer")
    if isinstance(links, dict):                     # the service's explorer links: drawn only on the allowed origin
        links = {name: links[name] for name in ("tx", "run", "listing") if _link(links.get(name))}
        if links:
            out["explorer"] = links
    return Result(ok=True, data=out)


def _link(value):
    """An https link short enough to draw as a QR code, one printable line."""
    return (isinstance(value, str) and value.startswith("https://") and len(value) <= LINK_MAX
            and value.isprintable() and " " not in value)


def _explorer_origin(config):
    """The Arkiv explorer's https origin from /arkiv/config's two link templates (explorer_tx, explorer_entity): None
    when neither is an https link, or the two name different hosts."""
    origins = set()
    for name in ("explorer_tx", "explorer_entity"):
        value = config.get(name)
        if value is None:
            continue
        m = _ORIGIN.match(value) if isinstance(value, str) else None
        if m is None or value[m.end():m.end() + 1] not in ("/", ""):
            return None
        origins.add(m.group(0))
    return origins.pop() if len(origins) == 1 else None
