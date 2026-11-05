"""The World adapter: PB's record book (IDKit) and listing approval (Agent Pass, or IDKit when the bridge's /health
says "approvals": "idkit"; both behind /agentpass/*) for real, through the World bridge
(apps/world-bridge; its HTTP contract is in apps/world-bridge/README.md). Every other
step is still the mock's: Arkiv and Hedera stay mocked.

All HTTP runs on one background thread with short timeouts. begin(), poll(), cancel() and status() only read and mark
what that thread last saw, so a slow or missing bridge never holds up a frame. The thread asks only while someone is
looking (PB's screen polls a call and reads status() every frame), so it goes quiet while a game runs.

One bridge request (an IDKit or Agent Pass session) carries several of the flow's steps: idkit_scan, idkit_confirm,
idkit_verify on one, approve_scan, approve on the other. Each step resolves ok once the request's stage has moved
past it, or with the request's failure at "done". A bridge that does not answer fails the step as World down."""
import json
import logging
import platform
import threading
import urllib.parse
import urllib.request

from arca_launcher.handler.mock import MockSponsors
from arca_launcher.handler.sponsors import TIMEOUT_MS, Result, SponsorNames

log = logging.getLogger(__name__)

POLL_MS = 500                 # a live request's stage is asked this often
HEALTH_MS = 5000              # and /health this often, while someone is looking
IDLE_MS = 3000                # no call polled and no status read this long: nobody is looking, ask nothing
UNREACHABLE_MS = 5000         # a live request's bridge silent this long: World is down for that step
EXPIRY_GRACE_MS = 3000        # this long past a request's own expires_s with no end from the bridge: it ran out
START_TIMEOUT_S = 5.0         # a start may wait on World's own servers
ASK_TIMEOUT_S = 2.0
ACTION_MAX = 160              # the bridge's limit on a listing's digest (World App shows it)
BOARD_TAIL = " on the public board"   # every listing approval names where the run goes
TICK_S, IDLE_TICK_S = 0.1, 1.0

_KIND = {"idkit_scan": "idkit", "idkit_confirm": "idkit", "idkit_verify": "idkit",
         "approve_scan": "agentpass", "approve": "agentpass"}
_FIRST = ("idkit_scan", "approve_scan")   # these start a new request; the steps after them follow the latest one
# The stages a step still waits through: it resolves ok once the request's stage is none of them.
_WAITS = {"idkit_scan": ("scan",), "idkit_confirm": ("scan", "confirm"), "idkit_verify": ("scan", "confirm", "verify"),
          "approve_scan": ("scan",), "approve": ("scan", "approve")}
_STAGES = {"idkit": ("scan", "confirm", "verify", "done"), "agentpass": ("scan", "approve", "done")}
# The handler's own failure names (mock.py's _OUTCOMES and _DOWN_FAILURE). Anything else the bridge says is World down.
_FAILURES = {"idkit": ("id_rejected", "id_expired", "id_nocred", "id_dup", "id_offline"),
             "agentpass": ("ls_denied", "ls_expired", "ls_wrong", "ls_mismatch", "ls_reused", "ls_world_down")}
_DOWN = {"idkit": "id_offline", "agentpass": "ls_world_down"}
_EXPIRED = {"idkit": "id_expired", "agentpass": "ls_expired"}
_CANCELLED = {"idkit": "id_cancel", "agentpass": "ls_cancel"}   # where Circle went; the flow never lands on these
# What a success must carry to be shown: the record book (one per person) or the approval's one-time id. A duplicate
# may come without its book (World App refused the second sign-up before any proof): the flow says so, unnamed.
_NEEDS = {"idkit": "book", "agentpass": "jti"}


def http_transport(bridge_url):
    """(method, path, body, timeout_s) -> the bridge's JSON reply; raises on anything else (no answer, an HTTP error
    status, not JSON). No proxy: the bridge is on this machine or across the hotspot."""
    base = bridge_url.rstrip("/")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def send(method, path, body, timeout_s):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        with opener.open(urllib.request.Request(base + path, data=data, headers=headers, method=method),
                         timeout=timeout_s) as reply:
            return json.loads(reply.read().decode("utf-8"))
    return send


class _Request:
    """One bridge request as the worker last saw it. Read and written under the owner's lock."""

    def __init__(self, kind, body, now):
        self.kind, self.body = kind, body
        self.started = False      # the worker took its start
        self.id = None            # the bridge's id, once the start answered
        self.code, self.qr, self.expires_s = "", "", 0
        self.expires_ms = None    # when it runs out, on the clock
        self.reply = None         # the latest {"stage", "ok", "failure", "data"}
        self.down = False         # the bridge did not answer it: every step on it is World down
        self.cancelled = False
        self.next_ms = now        # when its stage is next asked
        self.silent_since = None  # the first unanswered ask in the current run of them

    @property
    def done(self):
        return self.reply is not None and self.reply["stage"] == "done"

    @property
    def live(self):
        return self.id is not None and not (self.down or self.cancelled or self.done)


class _WorldCall:
    def __init__(self, owner, step, request):
        self._owner = owner
        self.step = step
        self._request = request
        self._start_ms = owner._clock_ms()
        self._result = None

    @property
    def elapsed_ms(self) -> int:
        return self._owner._clock_ms() - self._start_ms

    @property
    def info(self) -> dict:
        """A new request's code, link and lifetime ("" and 0 until the bridge's start answers); {} on a later step."""
        if self.step not in _FIRST:
            return {}
        with self._owner._lock:
            r = self._request
            return {"code": r.code, "qr": r.qr, "expires_s": r.expires_s}

    def poll(self) -> Result | None:
        if self._result is None:
            self._result = self._owner._answer(self)
        return self._result


class _Answered:
    """A call that answered as it began: the "status" step (this adapter's own status, not the mock's)."""
    elapsed_ms = 0

    def __init__(self, result):
        self.info = {}
        self._result = result

    def poll(self):
        return self._result


class WorldSponsors:
    """Sponsors with World for real through its bridge, Arkiv and Hedera still mocked."""

    mock = True     # Arkiv and Hedera still are: their Square outcome lists and "Start over (mock)" stay

    def __init__(self, bridge_url, clock_ms, names=SponsorNames(), *, transport=None, background=True, console=None):
        self.names = names
        self._clock_ms = clock_ms
        self._mock = MockSponsors(clock_ms, names)
        self._send = transport or http_transport(bridge_url)
        self._console = console or platform.node() or "anypercent"
        self._lock = threading.Lock()
        self._request = None       # the latest request; a new one drops (and cancels) the one before it
        self._cancels = []         # dropped Agent Pass requests the bridge still has to hear about
        self._health = None        # "ok" | "off" from /health; None until it first answers
        self._health_due = None    # when /health is next asked (None: at once)
        self.approvals = "agentpass"   # /health's "approvals"; an older bridge (or none yet) says nothing: Agent Pass
        self._wanted_ms = clock_ms()
        self._verify = None        # the latest idkit_verify call: World shows busy while it runs
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        if background:
            self._thread = threading.Thread(target=self._run, name="world-bridge", daemon=True)
            self._thread.start()

    # ---- the Sponsors protocol (the frame's side: never waits on the bridge) -----------------------------------------

    def mocked(self, service: str) -> bool:
        return service != "world"

    def status(self) -> dict[str, str]:
        out = self._mock.status()
        with self._lock:
            self._look()
            world = self._health or "busy"          # not heard from yet: still checking
            if world == "ok" and self._verifying():
                world = "busy"
        out["world"] = world
        return out

    def board(self, game_id: str, look: bool = True):
        """Arkiv is still mocked here: no real board."""
        return None

    def begin(self, step: str, payload: dict):
        kind = _KIND.get(step)
        if kind is None:
            if step == "status":
                return _Answered(Result(ok=True, data=self.status()))
            return self._mock.begin(step, payload)
        with self._lock:
            self._look()
            now = self._clock_ms()
            if step in _FIRST:
                self._drop(self._request)
                self._request = _Request(kind, self._start_body(step, payload), now)
            request = self._request
            if request is None or request.kind != kind:   # a later step with no request to follow: World down
                request = _Request(kind, None, now)
                request.down = True
            call = _WorldCall(self, step, request)
            if step == "idkit_verify":
                self._verify = call
        self._wake.set()
        return call

    def cross(self, call) -> None:
        if not isinstance(call, _WorldCall):        # a real phone answers on the phone, never on Cross
            self._mock.cross(call)

    def cancel(self, call) -> None:
        if not isinstance(call, _WorldCall):
            self._mock.cancel(call)
            return
        if call._result is not None:
            return
        call._result = Result(ok=False, failure=_CANCELLED[call._request.kind])
        with self._lock:
            self._drop(call._request)
        self._wake.set()

    def outcomes(self, step: str):
        return [] if step in _KIND else self._mock.outcomes(step)

    def force(self, call, outcome) -> None:
        if not isinstance(call, _WorldCall):
            self._mock.force(call, outcome)

    def close(self) -> None:
        """Stop the worker. It is a daemon thread: one stuck in a request never holds the launcher's exit."""
        self._stop.set()
        self._wake.set()

    # ---- the worker's side -------------------------------------------------------------------------------------------

    def work(self):
        """One round of HTTP: cancels the bridge still has to hear, a request's start, the live request's stage and
        /health when due. The background thread calls it in a loop; a test calls it by hand."""
        now = self._clock_ms()
        with self._lock:
            cancels, self._cancels = self._cancels, []
            r = self._request
            start = r if r is not None and not (r.started or r.cancelled or r.down) else None
            if start is not None:
                start.started = True
            looking = now - self._wanted_ms < IDLE_MS
            ask = r if looking and r is not None and r.live and now >= r.next_ms else None
            health = self._health_due is None or (looking and now >= self._health_due)
        for dropped in cancels:
            if dropped.id is not None:              # never started, or its start failed: nothing to cancel
                self._call_bridge("POST", f"/agentpass/{_quote(dropped.id)}/cancel", {}, ASK_TIMEOUT_S)
        if start is not None:
            self._start(start)
        if ask is not None:
            self._ask(ask)
        if health:
            reply = self._call_bridge("GET", "/health", None, ASK_TIMEOUT_S)
            with self._lock:
                self._health = "ok" if isinstance(reply, dict) and reply.get("world") == "ok" else "off"
                self._health_due = self._clock_ms() + HEALTH_MS
                if isinstance(reply, dict):        # no answer: the last word on approvals stands
                    said = reply.get("approvals")
                    self.approvals = said if said in ("idkit", "agentpass") else "agentpass"

    def _run(self):
        while not self._stop.is_set():
            try:
                self.work()
            except Exception:                       # never let the thread die: the next round tries again
                log.exception("World bridge worker")
            with self._lock:
                idle = self._clock_ms() - self._wanted_ms >= IDLE_MS
            self._wake.wait(IDLE_TICK_S if idle else TICK_S)
            self._wake.clear()

    def _call_bridge(self, method, path, body, timeout_s):
        """The bridge's reply, or None when it did not give one (World then shows off until /health says ok)."""
        try:
            return self._send(method, path, body, timeout_s)
        except Exception as e:                      # no answer, an error status, not JSON
            with self._lock:
                was, self._health = self._health, "off"
            if was != "off":                        # once an outage, and never an id, a code or a link
                log.info("World bridge not answering (%s /%s: %s)", method, path.split("/")[1], type(e).__name__)
            return None

    def _start(self, r):
        reply = self._call_bridge("POST", f"/{r.kind}/start", r.body, START_TIMEOUT_S)
        ok = (isinstance(reply, dict) and isinstance(reply.get("id"), str) and reply["id"]
              and isinstance(reply.get("qr"), str) and isinstance(reply.get("code"), str)
              and type(reply.get("expires_s")) is int and reply["expires_s"] > 0)
        now = self._clock_ms()
        with self._lock:
            if not ok:
                r.down = True
                return
            r.id, r.qr, r.code, r.expires_s = reply["id"], reply["qr"], reply["code"], reply["expires_s"]
            r.expires_ms = now + 1000 * r.expires_s
            r.next_ms = now

    def _ask(self, r):
        reply = self._call_bridge("GET", f"/{r.kind}/{_quote(r.id)}", None, ASK_TIMEOUT_S)
        reply = _checked(r.kind, reply)
        now = self._clock_ms()
        with self._lock:
            r.next_ms = now + POLL_MS
            if reply is not None:
                r.reply, r.silent_since = reply, None
            elif r.silent_since is None:
                r.silent_since = now
            elif now - r.silent_since >= UNREACHABLE_MS:
                r.down = True

    # ---- under the lock ----------------------------------------------------------------------------------------------

    def _look(self):
        """Someone is looking: the worker asks again (at once, if it had gone quiet)."""
        now = self._clock_ms()
        if now - self._wanted_ms >= IDLE_MS:
            self._wake.set()
        self._wanted_ms = now

    def _drop(self, r):
        """Stop following r; an open Agent Pass request is cancelled on the bridge (IDKit has no cancel)."""
        if r is None or r.cancelled or r.down or r.done:
            return
        r.cancelled = True
        if r.kind == "agentpass":
            self._cancels.append(r)

    def _verifying(self):
        call = self._verify
        return (call is not None and call._result is None and call._request is self._request
                and not (call._request.down or call._request.cancelled or call._request.done)
                and call.elapsed_ms < TIMEOUT_MS["idkit_verify"])

    def _answer(self, call):
        r, kind = call._request, call._request.kind
        with self._lock:
            self._look()
            if r.cancelled:
                return Result(ok=False, failure=_CANCELLED[kind])
            if r.down:
                return Result(ok=False, failure=_DOWN[kind])
            if r.done:
                return _outcome(kind, r.reply)
            if r.expires_ms is not None and self._clock_ms() >= r.expires_ms + EXPIRY_GRACE_MS:
                return Result(ok=False, failure=_EXPIRED[kind])
            if r.reply is not None and r.reply["stage"] not in _WAITS[call.step]:
                return Result(ok=True)
            return None

    def _start_body(self, step, payload):
        if step == "idkit_scan":
            return {"console": self._console}
        return {"book": payload.get("book") or "", "action": _digest(payload)}


def _title(payload):
    """The game's name as the digest shows it: its title, or its id when there is none; one printable line."""
    return _printable(payload.get("title")) or _printable(payload.get("game"))


def _digest(payload):
    """What World App shows the person approving a listing: "List Marine Drive GP 1:42.83 ghost for 0.10 USDC on the
    public board" (the approval says where the run goes: Arkiv's public board). The game's title (its id only when
    there is none), no control characters, and within the bridge's ACTION_MAX (counted in UTF-16 units, as the
    bridge's JavaScript does): a long title gives way, never the price or the board."""
    tail = " ".join(x for x in (_printable(payload.get("run_time")), "ghost") if x)
    if isinstance(payload.get("price"), int):
        tail += " for %.2f USDC" % (payload["price"] / 100)
    tail += BOARD_TAIL
    title = _title(payload)
    room = ACTION_MAX - _units(f"List  {tail}")
    if _units(title) > room:
        while title and _units(title) > room - 3:
            title = title[:-1]
        title = title.rstrip() + "..."
    return " ".join(x for x in ("List", title, tail) if x)


def _printable(value):
    """value as one line: control characters become spaces, runs of spaces one."""
    text = "" if value is None else str(value)
    return " ".join("".join(" " if ord(ch) < 32 or ord(ch) == 127 else ch for ch in text).split())


def _units(text):
    return len(text.encode("utf-16-le")) // 2


def _quote(request_id):
    return urllib.parse.quote(request_id, safe="")


def _checked(kind, reply):
    """The bridge's GET reply in the contract's shape, or None (counted as no answer)."""
    if not isinstance(reply, dict) or reply.get("stage") not in _STAGES[kind]:
        return None
    data = reply.get("data")
    return {"stage": reply["stage"], "ok": reply.get("ok"), "failure": reply.get("failure"),
            "data": dict(data) if isinstance(data, dict) else {}}


def _outcome(kind, reply):
    """A done request as the step's Result. A failure the handler has no screen for, or a success missing what its
    screen shows (a book, an approval id), is World down: the console never makes either up."""
    data = reply["data"]
    if reply["ok"] is not True:
        if reply["failure"] not in _FAILURES[kind]:
            return Result(ok=False, failure=_DOWN[kind])
        return Result(ok=False, failure=reply["failure"], data=dict(data))
    if not (isinstance(data.get(_NEEDS[kind]), str) and data[_NEEDS[kind]]):
        return Result(ok=False, failure=_DOWN[kind])
    return Result(ok=True, data=dict(data))
