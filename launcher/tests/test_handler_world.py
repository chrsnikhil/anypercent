"""Tests for the World adapter (handler/world.py): PB's record book and listing approval through the World bridge's
HTTP contract (apps/world-bridge/README.md), every other step still the mock's.

Most tests run the adapter with no thread: a StubBridge stands in for the HTTP, a fake clock for time, and the test
calls work() (one round of the worker) by hand, so every stage change lands exactly when the test says. The last
few run the real thread against a real local HTTP server."""
import json
import socket
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from arca_launcher.handler import world
from arca_launcher.handler.flow import Flow
from arca_launcher.handler.ledger import GHOST_PRICE, Ledger, load
from arca_launcher.handler.mock import MockSponsors
from arca_launcher.handler.sponsors import TIMEOUT_MS, Result
from arca_launcher.handler.world import WorldSponsors

IDKIT_FAILURES = ("id_rejected", "id_expired", "id_nocred", "id_dup", "id_offline")
LISTING_FAILURES = ("ls_denied", "ls_expired", "ls_wrong", "ls_mismatch", "ls_reused", "ls_world_down")
BOOK = {"book": "ANY-K2P", "credential": "Orb", "runner_id": "3f9a0c21"}
LIST_PAYLOAD = {"game": "MDGP", "seller": None, "price": GHOST_PRICE, "book": "ANY-7QZ", "jti": None,
                "run_time": "1:42.83"}
# The stage each phone step is begun at (the stage the step before it moved past).
AT = {"idkit_scan": "scan", "idkit_confirm": "confirm", "idkit_verify": "verify", "approve_scan": "scan",
      "approve": "approve"}
FIRST = {"idkit_scan": "idkit_scan", "idkit_confirm": "idkit_scan", "idkit_verify": "idkit_scan",
         "approve_scan": "approve_scan", "approve": "approve_scan"}


class FakeClock:
    def __init__(self):
        self.ms = 0

    def __call__(self):
        return self.ms


class StubBridge:
    """The bridge's contract in memory. Each request starts at stage "scan"; a test moves the latest one with move().
    `down` makes every request fail as an unreachable bridge's would."""

    def __init__(self, expires_s=300):
        self.requests = []                     # (method, path, body), in order
        self.sessions = {}
        self.health = {"world": "ok", "idkit": True, "agentpass": True}
        self.down = False
        self.expires_s = expires_s
        self.during_start = None               # called inside a start, as if the console acted mid-request

    def __call__(self, method, path, body, timeout_s):
        self.requests.append((method, path, body))
        assert timeout_s <= 5
        if self.down:
            raise urllib.error.URLError("connection refused")
        parts = path.strip("/").split("/")
        if path == "/health":
            return dict(self.health)
        if method == "POST" and parts[1:] == ["start"]:
            if self.during_start is not None:
                self.during_start()
            sid = f"{parts[0]}-{len(self.sessions) + 1}"
            self.sessions[sid] = {"stage": "scan", "ok": None, "failure": None, "data": {}}
            return {"id": sid, "qr": "https://world.example/" + sid, "code": "K7P-2QX", "expires_s": self.expires_s}
        if method == "POST" and parts[2:] == ["cancel"]:
            return {"ok": True}
        if method == "GET" and len(parts) == 2 and parts[1] in self.sessions:
            return json.loads(json.dumps(self.sessions[parts[1]]))
        raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)

    def move(self, stage, ok=None, failure=None, data=None):
        sid = list(self.sessions)[-1]
        self.sessions[sid] = {"stage": stage, "ok": ok, "failure": failure, "data": data or {}}

    def posts(self):
        return [(path, body) for method, path, body in self.requests if method == "POST"]

    def gets(self):
        return [path for method, path, _ in self.requests if method == "GET" and path != "/health"]


def make(expires_s=300):
    clock, bridge = FakeClock(), StubBridge(expires_s)
    sponsors = WorldSponsors("http://bridge.test:8787", clock, transport=bridge, background=False, console="anypercent")
    return sponsors, clock, bridge


def step(sponsors, clock, ms=world.POLL_MS):
    """Let ms pass, read status as the view does every frame, and run one round of the worker."""
    clock.ms += ms
    sponsors.status()
    sponsors.work()


def walk_to(sponsors, clock, bridge, name):
    """Begin the request name belongs to, then walk it (and its steps) up to name. Returns name's call."""
    call = sponsors.begin(FIRST[name], LIST_PAYLOAD)
    step(sponsors, clock)
    if call.step != name:
        bridge.move(AT[name])
        step(sponsors, clock)
        assert call.poll() == Result(ok=True)
        call = sponsors.begin(name, LIST_PAYLOAD)
    assert call.poll() is None
    return call


# ---- the record book: IDKit -------------------------------------------------------------------------------------

def test_record_book_steps_follow_one_request_stage_by_stage():
    sponsors, clock, bridge = make()
    scan = sponsors.begin("idkit_scan", {"book": None})
    assert scan.info == {"code": "", "qr": "", "expires_s": 0}         # the link is on its way
    assert scan.poll() is None
    sponsors.work()
    assert bridge.posts() == [("/idkit/start", {"console": "anypercent"})]
    assert scan.info == {"code": "K7P-2QX", "qr": "https://world.example/idkit-1", "expires_s": 300}
    step(sponsors, clock)
    assert scan.poll() is None                                          # still "scan": nobody scanned yet
    bridge.move("confirm")
    step(sponsors, clock)
    assert scan.poll() == Result(ok=True)
    confirm = sponsors.begin("idkit_confirm", {})
    assert confirm.info == {}                                           # the same request: no new code
    assert confirm.poll() is None
    bridge.move("verify")
    step(sponsors, clock)
    assert confirm.poll() == Result(ok=True)
    verify = sponsors.begin("idkit_verify", {})
    assert verify.poll() is None
    bridge.move("done", ok=True, data=BOOK)
    step(sponsors, clock)
    assert verify.poll() == Result(ok=True, data=BOOK)
    assert verify.poll() == Result(ok=True, data=BOOK)                  # forever after
    assert bridge.posts() == [("/idkit/start", {"console": "anypercent"})]   # one request, three steps
    assert set(bridge.gets()) == {"/idkit/idkit-1"}


def test_a_request_that_jumps_to_done_resolves_every_step_at_once():
    sponsors, clock, bridge = make()
    scan = sponsors.begin("idkit_scan", {})
    sponsors.work()
    bridge.move("done", ok=True, data=BOOK)
    step(sponsors, clock)
    assert scan.poll().ok
    assert sponsors.begin("idkit_confirm", {}).poll().ok
    assert sponsors.begin("idkit_verify", {}).poll() == Result(ok=True, data=BOOK)


@pytest.mark.parametrize("name", ("idkit_scan", "idkit_confirm", "idkit_verify"))
@pytest.mark.parametrize("failure", IDKIT_FAILURES)
def test_each_record_book_failure_fails_the_step_it_lands_on(name, failure):
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, name)
    data = {"book": "ANY-2KD"} if failure == "id_dup" else {}           # the same person's existing book
    bridge.move("done", ok=False, failure=failure, data=data)
    step(sponsors, clock)
    assert call.poll() == Result(ok=False, failure=failure, data=data)


@pytest.mark.parametrize("reply", [
    {"stage": "done", "ok": False, "failure": "ls_denied", "data": {}},      # a listing failure on a record book
    {"stage": "done", "ok": False, "failure": "rate_limited", "data": {}},   # a name the handler has no screen for
    {"stage": "done", "ok": False, "failure": None, "data": {}},
    {"stage": "done", "ok": True, "failure": None, "data": {"credential": "Orb"}},   # a success with no book
    {"stage": "done", "ok": False, "failure": "id_dup", "data": {}},         # a duplicate with no book to sign in to
])
def test_an_answer_the_handler_cannot_show_is_world_down(reply):
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, "idkit_verify")
    bridge.move(**reply)
    step(sponsors, clock)
    assert call.poll().failure == "id_offline"


# ---- the listing approval: Agent Pass ---------------------------------------------------------------------------

def test_listing_approval_sends_the_book_and_what_is_approved():
    sponsors, clock, bridge = make(expires_s=900)
    scan = sponsors.begin("approve_scan", LIST_PAYLOAD)
    sponsors.work()
    assert bridge.posts() == [("/agentpass/start", {"book": "ANY-7QZ",
                                                    "action": "list MDGP 1:42.83 ghost at 0.10 USDC"})]
    assert scan.info == {"code": "K7P-2QX", "qr": "https://world.example/agentpass-1", "expires_s": 900}
    for _ in range(5):                                      # the device grant only says "scan" until it ends
        step(sponsors, clock)
        assert scan.poll() is None
    bridge.move("done", ok=True, data={"jti": "5e1f0c2a"})
    step(sponsors, clock)
    assert scan.poll() == Result(ok=True, data={"jti": "5e1f0c2a"})
    approve = sponsors.begin("approve", LIST_PAYLOAD)
    assert approve.info == {}
    assert approve.poll() == Result(ok=True, data={"jti": "5e1f0c2a"})
    assert len(bridge.posts()) == 1


def test_an_approve_stage_moves_the_scan_on_first():
    sponsors, clock, bridge = make()
    scan = sponsors.begin("approve_scan", LIST_PAYLOAD)
    sponsors.work()
    bridge.move("approve")
    step(sponsors, clock)
    assert scan.poll() == Result(ok=True)
    approve = sponsors.begin("approve", LIST_PAYLOAD)
    assert approve.poll() is None
    bridge.move("done", ok=True, data={"jti": "77aa"})
    step(sponsors, clock)
    assert approve.poll() == Result(ok=True, data={"jti": "77aa"})


@pytest.mark.parametrize("name", ("approve_scan", "approve"))
@pytest.mark.parametrize("failure", LISTING_FAILURES)
def test_each_listing_failure_fails_the_step_it_lands_on(name, failure):
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, name)
    bridge.move("done", ok=False, failure=failure)
    step(sponsors, clock)
    assert call.poll() == Result(ok=False, failure=failure)


def test_an_approval_with_no_jti_or_a_record_book_failure_is_world_down():
    for reply in ({"ok": True, "data": {}}, {"ok": False, "failure": "id_dup", "data": {"book": "ANY-2KD"}}):
        sponsors, clock, bridge = make()
        call = walk_to(sponsors, clock, bridge, "approve")
        bridge.move("done", **reply)
        step(sponsors, clock)
        assert call.poll().failure == "ls_world_down"


# ---- an unreachable bridge, slow answers and expiry -------------------------------------------------------------

@pytest.mark.parametrize("first, down", [("idkit_scan", "id_offline"), ("approve_scan", "ls_world_down")])
def test_a_bridge_that_does_not_answer_a_start_is_world_down(first, down):
    sponsors, clock, bridge = make()
    bridge.down = True
    call = sponsors.begin(first, LIST_PAYLOAD)
    assert call.poll() is None                                          # nothing asked yet: no verdict either
    sponsors.work()
    assert call.poll() == Result(ok=False, failure=down)
    assert sponsors.status()["world"] == "off"


@pytest.mark.parametrize("name, down", [("idkit_confirm", "id_offline"), ("idkit_verify", "id_offline"),
                                        ("approve", "ls_world_down")])
def test_a_bridge_gone_quiet_mid_request_is_world_down_after_a_grace(name, down):
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, name)
    bridge.down = True
    step(sponsors, clock)                                               # the first unanswered ask starts the grace
    assert call.poll() is None
    assert sponsors.status()["world"] == "off"
    for _ in range(world.UNREACHABLE_MS // world.POLL_MS - 1):
        step(sponsors, clock)
        assert call.poll() is None
    step(sponsors, clock)
    assert call.poll() == Result(ok=False, failure=down)


def test_a_short_blip_is_forgiven():
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, "idkit_confirm")
    bridge.down = True
    for _ in range(4):
        step(sponsors, clock)
    bridge.down = False
    step(sponsors, clock)
    for _ in range(world.UNREACHABLE_MS // world.POLL_MS + 2):         # the grace starts over after an answer
        step(sponsors, clock)
    assert call.poll() is None
    bridge.move("verify")
    step(sponsors, clock)
    assert call.poll() == Result(ok=True)


def test_a_reply_off_the_contract_counts_as_no_answer():
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, "idkit_confirm")
    bridge.move("approve")                                              # an Agent Pass stage on an IDKit request
    for _ in range(world.UNREACHABLE_MS // world.POLL_MS + 1):
        step(sponsors, clock)
    assert call.poll() == Result(ok=False, failure="id_offline")


@pytest.mark.parametrize("start", [None, {"id": "x", "qr": "q", "code": "c"}, {"id": "", "qr": "q", "code": "c",
                                                                              "expires_s": 300}])
def test_a_start_reply_off_the_contract_is_world_down(start):
    sponsors, clock, bridge = make()
    sponsors._send = lambda method, path, body, timeout_s: start if path.endswith("/start") else {"world": "ok"}
    call = sponsors.begin("idkit_scan", {})
    sponsors.work()
    assert call.poll() == Result(ok=False, failure="id_offline")


@pytest.mark.parametrize("first, expired", [("idkit_scan", "id_expired"), ("approve_scan", "ls_expired")])
def test_a_request_past_its_own_expiry_runs_out(first, expired):
    sponsors, clock, bridge = make(expires_s=30)
    call = sponsors.begin(first, LIST_PAYLOAD)
    sponsors.work()
    clock.ms += 30000 + world.EXPIRY_GRACE_MS - 1
    assert call.poll() is None
    clock.ms += 1
    assert call.poll() == Result(ok=False, failure=expired)


def test_a_slow_bridge_times_out_world_verify_in_the_flow(tmp_path):
    rig = WorldRig(tmp_path)
    rig.to("id_verifying")
    rig.wait(TIMEOUT_MS["idkit_verify"] - 500)
    assert rig.state == "id_verifying"
    rig.wait(500)
    assert rig.state == "id_offline"


# ---- Circle, Cross and late answers -----------------------------------------------------------------------------

def test_circle_on_an_approval_cancels_it_on_the_bridge_and_ignores_a_late_ok():
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, "approve")
    sponsors.cancel(call)
    assert call.poll() == Result(ok=False, failure="ls_cancel")
    sponsors.work()
    assert bridge.posts()[-1] == ("/agentpass/agentpass-1/cancel", {})
    asked = len(bridge.gets())
    bridge.move("done", ok=True, data={"jti": "late"})
    for _ in range(4):
        step(sponsors, clock)
    assert call.poll() == Result(ok=False, failure="ls_cancel")
    assert len(bridge.gets()) == asked                                  # a cancelled request is never asked again
    assert sum(path.endswith("/cancel") for path, _ in bridge.posts()) == 1


def test_circle_before_the_start_was_sent_sends_nothing():
    sponsors, clock, bridge = make()
    call = sponsors.begin("approve_scan", LIST_PAYLOAD)
    sponsors.cancel(call)
    sponsors.work()
    assert bridge.posts() == []
    assert call.poll() == Result(ok=False, failure="ls_cancel")


def test_circle_while_the_start_is_on_its_way_still_cancels_it():
    sponsors, clock, bridge = make()
    call = sponsors.begin("approve_scan", LIST_PAYLOAD)
    bridge.during_start = lambda: sponsors.cancel(call)
    sponsors.work()
    sponsors.work()
    assert [path for path, _ in bridge.posts()] == ["/agentpass/start", "/agentpass/agentpass-1/cancel"]


def test_circle_on_a_record_book_ignores_its_late_answer():
    """The contract has no IDKit cancel: the request is only dropped here, never asked again."""
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, "idkit_confirm")
    sponsors.cancel(call)
    assert call.poll() == Result(ok=False, failure="id_cancel")
    asked = len(bridge.gets())
    bridge.move("done", ok=True, data=BOOK)
    step(sponsors, clock)
    assert call.poll() == Result(ok=False, failure="id_cancel")
    assert len(bridge.gets()) == asked and bridge.posts() == [("/idkit/start", {"console": "anypercent"})]


def test_cancel_after_an_answer_changes_nothing():
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, "approve")
    bridge.move("done", ok=True, data={"jti": "5e1f"})
    step(sponsors, clock)
    assert call.poll().ok
    sponsors.cancel(call)
    sponsors.work()
    assert call.poll() == Result(ok=True, data={"jti": "5e1f"})
    assert not any(path.endswith("/cancel") for path, _ in bridge.posts())


def test_a_new_request_cancels_the_open_one():
    sponsors, clock, bridge = make()
    old = sponsors.begin("approve_scan", LIST_PAYLOAD)
    sponsors.work()
    new = sponsors.begin("approve_scan", LIST_PAYLOAD)
    sponsors.work()
    assert [path for path, _ in bridge.posts()] == ["/agentpass/start", "/agentpass/agentpass-1/cancel",
                                                    "/agentpass/start"]
    assert old.poll() == Result(ok=False, failure="ls_cancel")
    assert new.info["qr"] == "https://world.example/agentpass-2"


def test_cross_does_nothing_on_a_real_phone_step():
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, "approve")
    sponsors.cross(call)
    step(sponsors, clock)
    assert call.poll() is None


# ---- the frame never waits, the worker goes quiet ---------------------------------------------------------------

def test_only_the_worker_talks_to_the_bridge():
    sponsors, clock, bridge = make()
    call = sponsors.begin("approve_scan", LIST_PAYLOAD)
    for _ in range(3):
        sponsors.status()
        call.poll()
        call.info
    sponsors.cross(call)
    sponsors.cancel(call)
    sponsors.begin("pay", {}).poll()
    assert bridge.requests == []


def test_nobody_looking_means_no_asking():
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, "idkit_confirm")
    clock.ms += world.IDLE_MS                                           # a game started: no status, no poll
    before = len(bridge.requests)
    for _ in range(20):
        clock.ms += world.HEALTH_MS
        sponsors.work()
    assert len(bridge.requests) == before
    call.poll()                                                         # back on PB's screen
    sponsors.work()
    assert len(bridge.requests) > before


def test_health_is_asked_every_few_seconds_while_looked_at():
    sponsors, clock, bridge = make()
    assert sponsors.status()["world"] == "busy"                         # not heard from yet: still checking
    sponsors.work()
    assert sponsors.status()["world"] == "ok"
    bridge.health = {"world": "off", "idkit": False, "agentpass": False}
    step(sponsors, clock, world.HEALTH_MS - 1)
    assert sponsors.status()["world"] == "ok"
    step(sponsors, clock, 1)
    assert sponsors.status()["world"] == "off"
    bridge.health = {"world": "ok", "idkit": True, "agentpass": True}
    step(sponsors, clock, world.HEALTH_MS)
    assert sponsors.status()["world"] == "ok"
    bridge.down = True
    step(sponsors, clock, world.HEALTH_MS)
    assert sponsors.status()["world"] == "off"


def test_world_is_busy_while_its_check_runs():
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, "idkit_verify")
    assert sponsors.status()["world"] == "busy"
    clock.ms += TIMEOUT_MS["idkit_verify"]                              # the flow gave up on it: not busy forever
    assert sponsors.status()["world"] == "ok"
    call = walk_to(sponsors, clock, bridge, "idkit_verify")
    bridge.move("done", ok=True, data=BOOK)
    step(sponsors, clock)
    call.poll()
    assert sponsors.status()["world"] == "ok"


# ---- the mocked rest, and the honest MOCK pill ------------------------------------------------------------------

def test_world_is_real_the_rest_still_mocked():
    sponsors, clock, bridge = make()
    assert sponsors.mock is True                                        # Arkiv and Hedera: Square and Start over stay
    assert [sponsors.mocked(s) for s in ("world", "board", "third")] == [False, True, True]
    mock = MockSponsors(clock)
    assert [mock.mocked(s) for s in ("world", "board", "third")] == [True, True, True]
    for name in ("idkit_scan", "idkit_confirm", "approve_scan", "approve"):
        assert sponsors.outcomes(name) == []
    assert sponsors.outcomes("pay") == mock.outcomes("pay")
    assert sponsors.outcomes("record") == mock.outcomes("record")


def test_every_other_step_goes_to_the_mock():
    sponsors, clock, bridge = make()
    pay = sponsors.begin("pay", {"game": "MDGP", "seller": "RIA"})
    assert sponsors.status()["third"] == "busy"
    clock.ms += 2000
    assert pay.poll().ok and pay.poll().data["receipt"].startswith("mock-")
    record = sponsors.begin("record", {})
    sponsors.force(record, sponsors.outcomes("record")[0])
    assert record.poll() == Result(ok=False, failure="ls_record_fail")
    assert sponsors.begin("sales", {}).poll().data == {"buyer": "ARJUN"}
    assert bridge.requests == []
    sponsors.work()
    status = sponsors.begin("status", {}).poll()
    assert status.ok and status.data == sponsors.status() and status.data["world"] == "ok"


def test_force_on_a_world_step_is_ignored():
    sponsors, clock, bridge = make()
    call = walk_to(sponsors, clock, bridge, "approve")
    sponsors.force(call, MockSponsors(clock).outcomes("approve")[0])
    assert call.poll() is None


# ---- through the flow -------------------------------------------------------------------------------------------

CTX = {"game": "Marine Drive GP", "target": "RIA", "board_case": "ok", "best_frames": 6290, "run_time": "1:42.83",
       "other_book": "ANY-MADE", "runs": "3", "sold": 0, "buyer": "", "wallet": "0xDE40...0000"}


class WorldRig:
    """A Flow on WorldSponsors over a StubBridge; wait() runs frames the way the app does, a worker round in each."""

    def __init__(self, tmp_path, book=None, expires_s=300):
        self.sponsors, self.clock, self.bridge = make(expires_s)
        self.path = str(tmp_path / "handler.json")
        self.flow = Flow(self.sponsors, Ledger(book=book), self.path, "MDGP", dict(CTX), today=lambda: "2026-11-06")

    @property
    def state(self):
        return self.flow.state.name

    def wait(self, ms, frame=100):
        while ms > 0:
            self.clock.ms += min(frame, ms)
            ms -= frame
            self.sponsors.status()
            self.sponsors.work()
            self.flow.tick(frame)

    def to(self, name):
        """Walk the record book from its start to name."""
        self.flow.start("book")
        self.flow.press("cross")
        self.wait(500)
        for stage, state in (("confirm", "id_confirm"), ("verify", "id_verifying")):
            if self.state == name:
                return
            self.bridge.move(stage)
            self.wait(500)
            assert self.state == state


def test_the_record_book_comes_from_world(tmp_path):
    rig = WorldRig(tmp_path)
    rig.flow.ctx.update(code="OLD-111", qr="https://world.example/old")
    rig.flow.start("book")
    rig.flow.press("cross")
    assert rig.state == "id_scan"
    assert (rig.flow.ctx["code"], rig.flow.ctx["qr"]) == ("", "")      # never the last request's code or link
    rig.wait(100)
    assert rig.flow.ctx["qr"] == "https://world.example/idkit-1" and rig.flow.ctx["code"] == "K7P-2QX"
    assert rig.flow.ctx["expires_s"] == 300
    rig.flow.press("cross")                                             # Cross can not stand in for the phone
    rig.wait(1000)
    assert rig.state == "id_scan"
    rig.bridge.move("confirm")
    rig.wait(500)
    assert rig.state == "id_confirm" and rig.flow.ctx["code"] == "K7P-2QX"
    rig.bridge.move("verify")
    rig.wait(500)
    assert rig.state == "id_verifying"
    rig.bridge.move("done", ok=True, data=BOOK)
    rig.wait(500)
    assert rig.state == "id_done"
    assert rig.flow.ledger.book == "ANY-K2P" and rig.flow.ledger.credential == "Orb"
    assert load(rig.path).book == "ANY-K2P"


def test_the_same_person_again_signs_in_to_their_book(tmp_path):
    rig = WorldRig(tmp_path)
    rig.to("id_verifying")
    rig.bridge.move("done", ok=False, failure="id_dup", data={"book": "ANY-2KD"})
    rig.wait(500)
    assert rig.state == "id_dup" and rig.flow.ctx["other_book"] == "ANY-2KD"
    rig.flow.press("cross")
    assert rig.state == "id_signed" and rig.flow.ledger.book == "ANY-2KD"


@pytest.mark.parametrize("failure", ("id_rejected", "id_expired", "id_nocred", "id_offline"))
def test_a_record_book_failure_lands_on_its_screen(tmp_path, failure):
    rig = WorldRig(tmp_path)
    rig.to("id_confirm")
    rig.bridge.move("done", ok=False, failure=failure)
    rig.wait(500)
    assert rig.state == failure and rig.flow.ledger.book is None


def test_circle_on_the_record_book_backs_out_and_a_fresh_code_is_a_new_request(tmp_path):
    rig = WorldRig(tmp_path)
    rig.to("id_confirm")
    rig.flow.press("circle")
    assert rig.state == "id_cancel"
    rig.bridge.move("done", ok=True, data=BOOK)                         # the phone confirms anyway
    rig.wait(1000)
    assert rig.state == "id_cancel" and rig.flow.ledger.book is None
    rig.flow.press("cross")
    rig.wait(100)
    assert rig.state == "id_scan" and rig.flow.ctx["qr"] == "https://world.example/idkit-2"


def test_an_unreachable_bridge_is_world_down_on_screen(tmp_path):
    rig = WorldRig(tmp_path)
    rig.bridge.down = True
    rig.flow.start("book")
    rig.flow.press("cross")
    rig.wait(100)
    assert rig.state == "id_offline"
    rig = WorldRig(tmp_path, book="ANY-7QZ")
    rig.bridge.down = True
    rig.flow.start("list")
    rig.flow.press("cross")
    rig.wait(100)
    assert rig.state == "ls_world_down"


def test_a_listing_approved_on_world_lists_through_the_mocked_rest(tmp_path):
    rig = WorldRig(tmp_path, book="ANY-7QZ", expires_s=600)
    rig.flow.start("list")
    rig.flow.press("cross")
    rig.wait(100)
    assert rig.state == "ls_scan" and rig.flow.ctx["qr"] == "https://world.example/agentpass-1"
    assert rig.bridge.posts() == [("/agentpass/start", {"book": "ANY-7QZ",
                                                        "action": "list MDGP 1:42.83 ghost at 0.10 USDC"})]
    rig.bridge.move("done", ok=True, data={"jti": "5e1f0c2a"})
    rig.wait(500)
    assert rig.state == "ls_record" and rig.flow.ctx["jti"] == "5e1f0c2a"
    rig.wait(2000)                                                      # Hedera's record: mocked
    assert rig.state == "ls_arkiv"
    rig.wait(1400)                                                      # Arkiv's listing: mocked
    assert rig.state == "ls_done" and len(load(rig.path).listings) == 1


@pytest.mark.parametrize("failure", LISTING_FAILURES)
def test_a_listing_failure_lands_on_its_screen(tmp_path, failure):
    rig = WorldRig(tmp_path, book="ANY-7QZ")
    rig.flow.start("list")
    rig.flow.press("cross")
    rig.wait(500)
    rig.bridge.move("done", ok=False, failure=failure)
    rig.wait(500)
    assert rig.state == failure and rig.flow.ledger.listings == []


def test_circle_always_wins_over_a_late_approval(tmp_path):
    rig = WorldRig(tmp_path, book="ANY-7QZ")
    rig.flow.start("list")
    rig.flow.press("cross")
    rig.wait(500)
    rig.bridge.move("approve")
    rig.wait(500)
    assert rig.state == "ls_approve"
    rig.flow.press("circle")
    assert rig.state == "ls_cancel"
    rig.wait(100)
    assert ("/agentpass/agentpass-1/cancel", {}) in rig.bridge.posts()
    rig.bridge.move("done", ok=True, data={"jti": "late"})
    rig.wait(2000)
    assert rig.state == "ls_cancel" and not rig.flow.busy               # never ls_late: nothing listens any more
    assert rig.flow.ledger.listings == []


def test_a_code_that_runs_out_on_the_console_is_cancelled_on_the_bridge(tmp_path):
    rig = WorldRig(tmp_path, book="ANY-7QZ", expires_s=3600)
    rig.flow.start("list")
    rig.flow.press("cross")
    rig.wait(rig.flow.state.deadline_ms, frame=1000)
    assert rig.state == "ls_expired"
    rig.wait(100)
    assert ("/agentpass/agentpass-1/cancel", {}) in rig.bridge.posts()


def test_square_offers_no_fake_world_answers(tmp_path):
    rig = WorldRig(tmp_path, book="ANY-7QZ")
    rig.flow.start("list")
    rig.flow.press("cross")
    rig.wait(100)
    rig.flow.press("square")
    assert not rig.flow.outcomes_open and rig.flow.mock_rows() == []    # ls_scan: World's own
    rig.flow.press("circle")
    assert rig.state == "ls_cancel"
    assert rig.flow.mock_rows() == []                                   # no "Phone approves anyway" for a real phone
    rig.flow.start("ls_record")                                         # Hedera's step: still mocked
    assert [o.failure for o in rig.flow.mock_rows()] == ["ls_record_fail"]
    rig.flow.start("hub")
    assert rig.flow.hub_rows[-1] == "Start over (mock)"


# ---- the screens ------------------------------------------------------------------------------------------------

def _drawn(screen, monkeypatch):
    """Every (string, x) gfx.text draws from now on."""
    drawn, real = [], screen.gfx.text

    def spy(s, *a, **kw):
        drawn.append((s, a[1] if len(a) > 1 else kw.get("x")))
        return real(s, *a, **kw)
    monkeypatch.setattr(screen.gfx, "text", spy)
    return drawn


def _world_flow(tmp_path, state):
    rig = WorldRig(tmp_path, book="ANY-7QZ")
    rig.flow.start(state)
    rig.wait(100)
    rig.flow.ms_in_state = 60000
    return rig.flow


def test_the_pills_say_which_sponsors_are_mocked(screen, tmp_path, monkeypatch):
    from test_handler_view import make_flow, show
    drawn = _drawn(screen, monkeypatch)
    nav, views = show(screen, _world_flow(tmp_path, "ls_scan"))
    x = {s: x for s, x in reversed(drawn)}                              # each string's first x
    tags = [x for s, x in drawn if s == "MOCK"]
    assert len(tags) == 2                                               # Arkiv's and Hedera's, none on World or the QR
    assert x["World"] < x["Arkiv"] < tags[0] < x["Hedera"] < tags[1]
    squares = [h for h in views.hits if h.target == ("handler", "square")]
    assert len(squares) == 2 and all(views.hit(*h.shape.center) == ("handler", "square") for h in squares)
    drawn.clear()
    nav, views = show(screen, make_flow(tmp_path, "ls_scan"))          # all mocked: one MOCK pill, as before
    x = {s: x for s, x in reversed(drawn)}
    squares = [h for h in views.hits if h.target == ("handler", "square")]
    assert len(squares) == 1 and squares[0].shape.x > x["Hedera"]
    assert len([s for s, _ in drawn if s == "MOCK"]) == 2              # the pill, and the QR's own tag


def test_the_qr_is_worlds_link_with_no_mock_tag(screen, tmp_path, monkeypatch):
    from arca_launcher.render import handler_art
    from arca_launcher.render.handler_cards import qr_box
    from arca_launcher.render.handler_view import CARD, STRIP_H
    from test_handler_view import AMBER, has_colour, show
    seen = []
    real = handler_art.qr_surface
    monkeypatch.setattr(handler_art, "qr_surface", lambda text: (seen.append(text), real(text))[1])
    content = CARD.copy()
    content.h -= STRIP_H
    for state, link in (("id_scan", "https://world.example/idkit-1"), ("ls_scan", "https://world.example/agentpass-1")):
        show(screen, _world_flow(tmp_path / state, state))
        assert seen[-1] == link
        assert not has_colour(screen.ren.to_surface(), qr_box(content).inflate(16, 16), AMBER)


def test_no_qr_while_the_link_is_on_its_way(screen, tmp_path, monkeypatch):
    from arca_launcher.render import handler_art
    from test_handler_view import show
    seen = []
    monkeypatch.setattr(handler_art, "qr_surface", lambda text: seen.append(text))
    rig = WorldRig(tmp_path)
    rig.flow.start("id_scan")
    show(screen, rig.flow)
    assert seen == []


def test_the_countdown_is_the_requests_own(tmp_path):
    from arca_launcher.render.handler_view import HandlerView
    rig = WorldRig(tmp_path, book="ANY-7QZ", expires_s=600)
    rig.flow.start("ls_scan")
    spec = HandlerView._spec(None, rig.flow)
    assert spec["total_ms"] == rig.flow.state.deadline_ms               # no answer yet: the screen's own
    rig.wait(100)
    spec = HandlerView._spec(None, rig.flow)
    assert spec["total_ms"] == 600000 and spec["mock"] is False


# ---- the real thing: a thread and HTTP --------------------------------------------------------------------------

class _Bridge(BaseHTTPRequestHandler):
    """The contract over real HTTP; the test moves `stage` and can slow every start down."""
    stage = {"stage": "scan", "ok": None, "failure": None, "data": {}}
    start_delay_s = 0.0
    cancelled = []

    def log_message(self, *args):
        pass

    def _reply(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            return self._reply(200, {"world": "ok", "idkit": True, "agentpass": True})
        if self.path == "/idkit/r1":
            return self._reply(200, type(self).stage)
        return self._reply(404, {"error": "no such request"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"null")
        if self.path == "/idkit/start" and body == {"console": "anypercent"}:
            time.sleep(type(self).start_delay_s)
            return self._reply(200, {"id": "r1", "qr": "https://world.example/r1", "code": "K7P-2QX", "expires_s": 300})
        if self.path.endswith("/cancel"):
            type(self).cancelled.append(self.path)
            return self._reply(200, {"ok": True})
        return self._reply(500, {"error": "bad request"})


@pytest.fixture
def http_bridge(monkeypatch):
    monkeypatch.setattr(world, "POLL_MS", 50)
    monkeypatch.setattr(_Bridge, "stage", {"stage": "scan", "ok": None, "failure": None, "data": {}})
    monkeypatch.setattr(_Bridge, "start_delay_s", 0.0)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Bridge)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    made = []

    def sponsors():
        s = WorldSponsors(f"http://127.0.0.1:{server.server_address[1]}/", lambda: int(time.monotonic() * 1000),
                          console="anypercent")
        made.append(s)
        return s
    yield sponsors
    for s in made:
        s.close()
    server.shutdown()
    server.server_close()


def _until(check, call=None, sponsors=None, timeout_s=5.0):
    """Poll like the app's frames do until check() holds."""
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if sponsors is not None:
            sponsors.status()
        if call is not None:
            call.poll()
        if check():
            return True
        time.sleep(0.01)
    return False


def test_a_real_bridge_over_http(http_bridge):
    sponsors = http_bridge()
    scan = sponsors.begin("idkit_scan", {})
    assert _until(lambda: scan.info["qr"], scan, sponsors)
    assert scan.info == {"code": "K7P-2QX", "qr": "https://world.example/r1", "expires_s": 300}
    assert _until(lambda: sponsors.status()["world"] == "ok", scan, sponsors)
    _Bridge.stage = {"stage": "verify", "ok": None, "failure": None, "data": {}}
    assert _until(lambda: scan.poll() is not None, scan, sponsors) and scan.poll().ok
    verify = sponsors.begin("idkit_verify", {})
    _Bridge.stage = {"stage": "done", "ok": True, "failure": None, "data": BOOK}
    assert _until(lambda: verify.poll() is not None, verify, sponsors)
    assert verify.poll() == Result(ok=True, data=BOOK)


def test_a_slow_bridge_never_holds_up_a_frame(http_bridge):
    _Bridge.start_delay_s = 1.0
    sponsors = http_bridge()
    t0 = time.monotonic()
    scan = sponsors.begin("idkit_scan", {})
    worst = time.monotonic() - t0
    for _ in range(30):                                                 # frames while the start is held up
        t0 = time.monotonic()
        scan.poll()
        sponsors.status()
        scan.info
        worst = max(worst, time.monotonic() - t0)
        time.sleep(0.01)
    assert worst < 0.05 and scan.poll() is None
    assert _until(lambda: scan.info["qr"], scan, sponsors)


def test_a_bridge_error_status_is_world_down(http_bridge):
    sponsors = http_bridge()
    approve = sponsors.begin("approve_scan", LIST_PAYLOAD)              # /agentpass/start: a 500 here
    assert _until(lambda: approve.poll() is not None, approve, sponsors)
    assert approve.poll() == Result(ok=False, failure="ls_world_down")


def test_nothing_listening_is_world_down():
    with socket.socket() as s:                                          # a port nobody listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    sponsors = WorldSponsors(f"http://127.0.0.1:{port}", lambda: int(time.monotonic() * 1000))
    try:
        scan = sponsors.begin("idkit_scan", {})
        assert _until(lambda: scan.poll() is not None, scan, sponsors)
        assert scan.poll() == Result(ok=False, failure="id_offline")
        assert _until(lambda: sponsors.status()["world"] == "off", scan, sponsors)
    finally:
        sponsors.close()


def test_close_stops_the_worker(http_bridge):
    sponsors = http_bridge()
    sponsors.close()
    assert _until(lambda: not sponsors._thread.is_alive(), timeout_s=3)


# ---- wiring: --world-bridge / ARCA_WORLD_BRIDGE -----------------------------------------------------------------

def test_the_flag_or_the_variable_picks_the_bridge(monkeypatch):
    from arca_launcher.__main__ import build_config
    monkeypatch.delenv("ARCA_WORLD_BRIDGE", raising=False)
    assert build_config([]).world_bridge is None
    assert build_config(["--world-bridge", "http://127.0.0.1:8787"]).world_bridge == "http://127.0.0.1:8787"
    monkeypatch.setenv("ARCA_WORLD_BRIDGE", "http://192.168.137.1:8787")
    assert build_config([]).world_bridge == "http://192.168.137.1:8787"
    assert build_config(["--world-bridge", "http://10.0.0.2:8787"]).world_bridge == "http://10.0.0.2:8787"
    monkeypatch.setenv("ARCA_WORLD_BRIDGE", "")
    assert build_config([]).world_bridge is None


def test_no_bridge_is_todays_mock(tmp_path):
    from arca_launcher.app import Config, make_sponsors
    sponsors = make_sponsors(Config(library_dir="/lib", state_path=str(tmp_path / "s.json")))
    assert type(sponsors) is MockSponsors and sponsors.mock and sponsors.mocked("world")


def test_the_app_runs_world_through_a_bridge_and_stops_it_on_close(tmp_path):
    from arca_launcher.app import App, Config
    from test_app import FakeHw, FakeRunner
    from test_handler_app import Bridge, library
    cfg = Config(library_dir=library(tmp_path), state_path=str(tmp_path / "state.json"), splash=False,
                 run_dir=str(tmp_path / "run"), runs_dir=str(tmp_path / "runs"), handler=True,
                 world_bridge="http://127.0.0.1:9")
    app = App(cfg, runner=FakeRunner(), hw=FakeHw(), bridge=Bridge())
    try:
        assert isinstance(app.sponsors, WorldSponsors) and app.sponsors._thread.is_alive()
    finally:
        app.close()
    assert _until(lambda: not app.sponsors._thread.is_alive(), timeout_s=3)
