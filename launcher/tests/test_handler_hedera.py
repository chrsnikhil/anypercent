"""Tests for the Hedera adapter (handler/hedera.py): PB's payment for a ghost (x402, paid by PB's agent in the service)
and the listing's HCS record, through the service's /hedera/* routes (the HTTP contract in
docs/superpowers/specs/*-hedera-integration.md), wrapped around the Arkiv adapter, itself around World's.

Most tests run with no thread, as test_handler_world.py and test_handler_arkiv.py do: a StubHedera stands in for the
service's /hedera/* routes and /health, the Arkiv tests' stubs for the rest of the chain, one fake clock for time, and
the test calls work() (one round of a worker) by hand. The last ones run the real thread."""
import base64
import json
import time
import urllib.error
import urllib.parse

import pytest

from arca_launcher.actions import Action as A
from arca_launcher.handler import hedera
from arca_launcher.handler.flow import Flow
from arca_launcher.handler.hedera import HederaSponsors
from arca_launcher.handler.ledger import GHOST_PRICE, Ledger, load
from arca_launcher.handler.mock import MockSponsors
from arca_launcher.handler.sponsors import TIMEOUT_MS, Result
from test_handler_arkiv import CHECKER, DONE, LIST_PAYLOAD, Rig as ArkivRig, StubService, _target_ctx, acl, sha

TX = "0.0.9185802@1762412349.000000123"           # a settled payment's id: the facilitator's fee payer @ its start
TX_SHOWN = "0.0.9185802@1762412349"               # as the receipt row shows it, the nanoseconds cut
SELLER = "0.0.5123456"                            # ANY-6PS's registered payout account
RUN, LISTING, LOG_H = "0x" + "12ab" * 16, "0x" + "34cd" * 16, "ab" * 32
ACTION = "List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC on the public board"
ACTION_TO = "List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC to 0.0.5123456 on the public board"   # the spec's own
BUY_FAILURES = ("buy_budget", "buy_changed", "buy_suspended", "buy_down")
RECORD_FAILURES = ("ls_expired", "ls_wrong", "ls_mismatch", "ls_reused", "ls_copied", "ls_record_fail")
PAID = {"receipt": TX, "hashscan": "https://hashscan.io/testnet/transaction/" + TX, "late": False}
RECORDED = {"topic": "0.0.7001234", "seq": 41, "tx": "0.0.6001234@1762412300.000000001",
            "hashscan": "https://hashscan.io/testnet/transaction/1762412301.000000002/message"}
TODAY = "2026-11-07"


def buy_payload(**over):
    """What the flow hands pay for a real target: ANY-K2Q buys ANY-6PS's listed ghost."""
    payload = {"game": "marine-drive-gp", "arcade_id": "MDGP", "title": "MARINE DRIVE GP", "seller": "ANY-6PS",
               "price": GHOST_PRICE, "book": "ANY-K2Q", "jti": None, "run_time": "1:44.83", "frames": 6290,
               "target_run": RUN, "target_listing": LISTING, "target_log_h": LOG_H, "target_frames": 6170,
               "receipt": None}
    payload.update(over)
    return payload


BUY_BODY = {"book": "ANY-K2Q", "game": "MDGP", "seller": "ANY-6PS", "listing": LISTING, "run": RUN, "log_h": LOG_H,
            "frames": 6170, "you_frames": 6290, "price_c": GHOST_PRICE}
RECORD_BODY = {"book": "ANY-6PS", "jti": "3f9c0a1b2c3d4e5f", "action": ACTION_TO, "game": "MDGP",
               "title": "MARINE DRIVE GP", "frames": 6170, "price_c": GHOST_PRICE, "pay_to": SELLER}


class StubHedera:
    """The service's /hedera/* routes and /health in memory. One buy job per (book, game, seller, run) and one record job
    per jti: a repeat start answers the same id. move() moves the latest job. payto: book -> its registered account.
    down: every request fails as an unreachable host's does; error: (status, failure) every request answers instead;
    lose: how many of the next requests time out."""

    def __init__(self):
        self.requests, self.jobs, self.ids = [], {}, {}
        self.payto = {"ANY-6PS": SELLER}
        self.health = {"world": "ok", "approvals": "agentpass", "hedera": "ok", "hedera_pay": True,
                       "hedera_record": True}
        self.down = False
        self.error = None
        self.lose = 0
        self.start = None                      # a reply every start answers instead, when set

    def __call__(self, method, path, body, timeout_s):
        self.requests.append((method, path, body))
        assert timeout_s <= 5
        if self.lose:
            self.lose -= 1
            raise TimeoutError("timed out")
        if self.down:
            raise urllib.error.URLError("connection refused")
        if self.error is not None:
            status, failure = self.error
            raise urllib.error.HTTPError(path, status, failure, {}, None)
        if (method, path) == ("GET", "/health"):
            return dict(self.health)
        parts = path.strip("/").split("/")
        if method == "GET" and parts[:2] == ["hedera", "payto"] and len(parts) == 3:
            book = urllib.parse.unquote(parts[2])
            return {"book": book, "pay_to": self.payto.get(book)}
        if method == "POST" and path in ("/hedera/buy", "/hedera/record"):
            if self.start is not None:
                return self.start
            kind = parts[1]
            key = (kind, body["book"], body["game"], body["seller"], body["run"]) if kind == "buy" else (kind,
                                                                                                         body["jti"])
            jid = self.ids.setdefault(key, ("p-" if kind == "buy" else "r-") + "%08x" % len(self.ids))
            self.jobs.setdefault(jid, {"stage": "guard" if kind == "buy" else "check", "ok": None, "failure": None,
                                       "data": {}})
            return {"id": jid, "expires_s": 240 if kind == "buy" else 120}
        if method == "GET" and len(parts) == 3 and parts[:2] in (["hedera", "buy"], ["hedera", "record"]) \
                and parts[2] in self.jobs:
            return json.loads(json.dumps(self.jobs[parts[2]]))
        raise urllib.error.HTTPError(path, 404, "unknown_id", {}, None)

    def move(self, stage, ok=None, failure=None, data=None):
        self.jobs[list(self.jobs)[-1]] = {"stage": stage, "ok": ok, "failure": failure, "data": data or {}}

    def posts(self, path=None):
        return [(p, b) for m, p, b in self.requests if m == "POST" and path in (None, p)]

    def gets(self, prefix):
        return [p for m, p, b in self.requests if m == "GET" and p.startswith(prefix)]


class PaidService(StubService):
    """The Arkiv service stub, its listed ghosts released against a settled payment's id (sales: tx -> run key)."""

    def __init__(self):
        super().__init__()
        self.sales = {}

    def __call__(self, method, path, body, timeout_s):
        if (method, path) == ("POST", "/arkiv/ghost") and body["run"] in self.ghosts:
            self.requests.append((method, path, body))
            if self.sales.get(body.get("receipt")) != body["run"]:
                raise urllib.error.HTTPError(path, 402, "payment_required", {}, None)
            log = self.ghosts[body["run"]]
            return {"log": base64.b64encode(log).decode(), "log_h": sha(log)}
        return super().__call__(method, path, body, timeout_s)


class Rig:
    """The whole chain over stubs, on one fake clock: Hedera (StubHedera) around Arkiv (StubNode, PaidService) around
    World (StubBridge)."""

    def __init__(self, tmp_path, inner=None, runs_dir=None):
        self.arkiv = ArkivRig(tmp_path / "arkiv", inner=inner, runs_dir=runs_dir)
        self.clock, self.node, self.bridge = self.arkiv.clock, self.arkiv.node, self.arkiv.bridge
        self.service = PaidService()
        self.arkiv.service = self.arkiv.sponsors._send = self.service
        self.hedera = StubHedera()
        self.state_dir = str(tmp_path / "state")
        self.path = str(tmp_path / "handler.json")
        self.sponsors = self.make()

    def make(self):
        return HederaSponsors(self.arkiv.sponsors, "http://bridge.test:8787", self.clock, self.state_dir,
                              transport=self.hedera, background=False)

    def step(self, call=None, ms=hedera.POLL_MS):
        """Let ms pass, look as PB's screen does every frame (status, and the call it shows), run the Hedera worker."""
        self.clock.ms += ms
        self.sponsors.status()
        if call is not None:
            call.poll()
        self.sponsors.work()

    def flow(self, book="ANY-K2Q", **ctx):
        base = {"game": "MARINE DRIVE GP", "arcade_id": "MDGP", "target": "", "board_case": "ok", "best_frames": 6290,
                "run_frames": None, "run_time": "1:44.83", "other_book": "ANY-MADE", "runs": "1", "sold": 0,
                "buyer": "", "wallet": SELLER, "target_time": "1:42.83", "gap": "2.0 s", "rank": "4th",
                "new_rank": "3rd", "ghost_look": "the *cyan kart*"}
        base.update(ctx)
        return Flow(self.sponsors, Ledger(book=book), self.path, "marine-drive-gp", base, today=lambda: TODAY)

    def wait(self, flow, ms, frame=100):
        """Frames as the app runs them: each one a round of every worker, then the flow's tick."""
        while ms > 0:
            self.clock.ms += frame
            ms -= frame
            self.sponsors.status()
            self.sponsors.work()
            self.arkiv.sponsors.work()
            self.arkiv.inner.work()
            flow.tick(frame)

    def target(self, pay_to=SELLER):
        """ANY-6PS's run, listed with her account, its ghost held by the service and known to the replay tool."""
        log = acl("6ps")
        run = self.node.run("ANY-6PS", 6170, log=log, listed=True, pay_to=pay_to)
        self.service.ghosts[run["key"]] = log
        self.arkiv.replays.know(log, 6170)
        return run


def _pay(rig, **over):
    call = rig.sponsors.begin("pay", buy_payload(**over))
    rig.sponsors.work()
    return call


def _record(rig, payload=None):
    call = rig.sponsors.begin("record", payload if payload is not None else dict(LIST_PAYLOAD, pay_to=SELLER))
    rig.sponsors.work()
    return call


# ---- pay: PB's agent buys the ghost over x402 ---------------------------------------------------------------------

def test_pay_starts_a_buy_and_follows_its_stages(tmp_path):
    rig = Rig(tmp_path)
    call = rig.sponsors.begin("pay", buy_payload())
    assert call.poll() is None and call.info == {} and rig.hedera.requests == []    # the frame never sends
    rig.sponsors.work()
    assert rig.hedera.posts() == [("/hedera/buy", BUY_BODY)]
    for stage in ("guard", "pay", "settle", "settle"):
        rig.hedera.move(stage)
        rig.step(call)
        assert call.poll() is None and rig.sponsors.status()["third"] == "busy"
    assert rig.hedera.gets("/hedera/buy/")[-1] == "/hedera/buy/p-00000000"
    rig.hedera.move("done", ok=True, data=dict(PAID, extra="never passed on"))
    rig.step(call)
    assert call.poll() == Result(ok=True, data=PAID)
    assert rig.sponsors.status()["third"] == "ok"


def test_the_buy_says_no_time_from_you_as_null(tmp_path):
    rig = Rig(tmp_path)
    _pay(rig, frames=None)
    assert rig.hedera.posts()[0][1] == dict(BUY_BODY, you_frames=None)


@pytest.mark.parametrize("failure", BUY_FAILURES)
def test_each_buy_failure_is_the_handlers_own(tmp_path, failure):
    rig = Rig(tmp_path)
    call = _pay(rig)
    data = {"now_price": "0.25 USDC"} if failure == "buy_changed" else {}
    rig.hedera.move("done", ok=False, failure=failure, data=dict(data, late_receipt="never passed on"))
    rig.step(call)
    assert call.poll() == Result(ok=False, failure=failure, data=data)


@pytest.mark.parametrize("now_price", ["gone", "0.25 USDC"])
def test_a_changed_listing_says_what_it_is_now(tmp_path, now_price):
    rig = Rig(tmp_path)
    call = _pay(rig)
    rig.hedera.move("done", ok=False, failure="buy_changed", data={"now_price": now_price})
    rig.step(call)
    assert call.poll() == Result(ok=False, failure="buy_changed", data={"now_price": now_price})


@pytest.mark.parametrize("reply", [
    {"ok": False, "failure": "rate_limited"},                        # a name the handler has no screen for
    {"ok": False, "failure": "ls_record_fail"},                      # another step's
    {"ok": False, "failure": None},
    {"ok": False, "failure": "buy_changed"},                         # a changed listing that does not say its price
    {"ok": False, "failure": "buy_changed", "data": {"now_price": "x" * 40}},
    {"ok": True, "data": {}},                                         # paid, but no receipt to show or load with
    {"ok": True, "data": {"receipt": "mock-1a2b3c4d"}},               # not a transaction id
    {"ok": True, "data": {"receipt": "0x" + "9f" * 32}},
    {"ok": "yes", "data": PAID},
])
def test_an_answer_the_handler_cannot_show_is_hedera_down(tmp_path, reply):
    rig = Rig(tmp_path)
    call = _pay(rig)
    rig.hedera.move("done", **reply)
    rig.step(call)
    assert call.poll() == Result(ok=False, failure="buy_down")


def test_a_start_with_no_answer_is_sent_once_more_with_the_same_body(tmp_path):
    rig = Rig(tmp_path)
    rig.hedera.lose = 1
    call = _pay(rig)
    assert call.poll() is None
    rig.sponsors.work()
    assert rig.hedera.posts() == [("/hedera/buy", BUY_BODY)] * 2      # the service dedupes: one job
    rig.hedera.move("done", ok=True, data=PAID)
    rig.step(call)
    assert call.poll().ok and len(rig.hedera.jobs) == 1


def test_two_starts_with_no_answer_are_hedera_down(tmp_path):
    rig = Rig(tmp_path)
    rig.hedera.down = True
    call = _pay(rig)
    assert call.poll() is None
    rig.sponsors.work()
    assert call.poll() == Result(ok=False, failure="buy_down")
    assert len(rig.hedera.posts()) == 2 and rig.sponsors.status()["third"] == "off"
    rig.sponsors.work()
    assert len(rig.hedera.posts()) == 2                               # never a third


@pytest.mark.parametrize("error", [(400, "bad_body"), (503, "hedera_not_configured"), (503, "hedera_unavailable")])
def test_a_refused_start_is_hedera_down_with_no_retry(tmp_path, error):
    rig = Rig(tmp_path)
    rig.hedera.error = error
    call = _pay(rig)
    assert call.poll() == Result(ok=False, failure="buy_down") and len(rig.hedera.posts()) == 1


@pytest.mark.parametrize("start", [{"expires_s": 240}, {"id": "", "expires_s": 240}, ["p-1"], "nonsense"])
def test_a_start_off_the_contract_is_hedera_down(tmp_path, start):
    rig = Rig(tmp_path)
    rig.hedera.start = start
    assert _pay(rig).poll() == Result(ok=False, failure="buy_down")


@pytest.mark.parametrize("over", [{"target_run": None}, {"target_listing": "0x12"}, {"target_log_h": "../x"},
                                  {"target_frames": None}, {"book": None}, {"seller": None}, {"arcade_id": None},
                                  {"price": "0.10"}])
def test_a_purchase_with_no_real_target_is_hedera_down_and_sends_nothing(tmp_path, over):
    rig = Rig(tmp_path)
    call = rig.sponsors.begin("pay", buy_payload(**over))
    assert call.poll() == Result(ok=False, failure="buy_down")
    rig.sponsors.work()
    assert rig.hedera.posts() == []


def test_a_service_silent_mid_payment_is_waited_out(tmp_path):
    """The money may still move: a silent service is asked on (the flow shows Hedera down after its 8 s)."""
    rig = Rig(tmp_path)
    call = _pay(rig)
    rig.hedera.down = True
    for _ in range(60):                                              # 30 s of silence
        rig.step(call)
        assert call.poll() is None
    assert rig.sponsors.status()["third"] == "off"
    rig.hedera.down = False
    rig.hedera.move("done", ok=True, data=dict(PAID, late=True))
    rig.step(call)
    assert call.poll() == Result(ok=True, data=dict(PAID, late=True))


def test_a_job_the_service_no_longer_knows_is_hedera_down(tmp_path):
    rig = Rig(tmp_path)
    call = _pay(rig)
    rig.hedera.jobs.clear()                                          # GET answers 404 unknown_id
    rig.step(call)
    assert call.poll() == Result(ok=False, failure="buy_down")


def test_a_job_past_its_own_life_is_hedera_down(tmp_path):
    rig = Rig(tmp_path)
    call = _pay(rig)
    rig.hedera.move("settle")
    for _ in range(240 // 10):
        rig.step(call, 10000)
        assert call.poll() is None
    rig.step(call, hedera.GRACE_MS)
    assert call.poll() == Result(ok=False, failure="buy_down")


def test_a_job_nobody_polls_is_not_asked(tmp_path):
    rig = Rig(tmp_path)
    call = _pay(rig)
    rig.step(call)
    asked = len(rig.hedera.gets("/hedera/buy/"))
    rig.clock.ms += hedera.IDLE_MS                                   # the player left: the flow polls it no more
    for _ in range(10):
        rig.clock.ms += hedera.POLL_MS
        rig.sponsors.work()
    assert len(rig.hedera.gets("/hedera/buy/")) == asked
    assert rig.sponsors.status()["third"] == "ok"                    # not busy: nobody waits on it
    rig.step(call)
    assert len(rig.hedera.gets("/hedera/buy/")) == asked + 1


def test_a_ghost_paid_for_is_never_paid_twice(tmp_path):
    rig = Rig(tmp_path)
    call = _pay(rig)
    rig.hedera.move("done", ok=True, data=PAID)
    rig.step(call)
    again = rig.sponsors.begin("pay", buy_payload())
    assert again.poll() == Result(ok=True, data={"receipt": TX})       # the earlier receipt, at once
    rig.sponsors.work()
    assert len(rig.hedera.posts()) == 1
    _pay(rig, target_run="0x" + "56ef" * 16)                           # her run listed again: another purchase
    assert len(rig.hedera.posts()) == 2


# ---- record: the World-approved listing on HCS ---------------------------------------------------------------------

def test_record_sends_the_approved_listing_and_follows_its_stages(tmp_path):
    rig = Rig(tmp_path)
    call = rig.sponsors.begin("record", dict(LIST_PAYLOAD, pay_to=SELLER))
    assert call.poll() is None and rig.hedera.requests == []
    rig.sponsors.work()
    assert rig.hedera.posts() == [("/hedera/record", RECORD_BODY)]  # the publish body without its log
    for stage in ("check", "submit"):
        rig.hedera.move(stage)
        rig.step(call)
        assert call.poll() is None and rig.sponsors.status()["third"] == "busy"
    rig.hedera.move("done", ok=True, data=RECORDED)
    rig.step(call)
    assert call.poll() == Result(ok=True, data=RECORDED)


def test_record_names_the_runs_log_by_its_hash_for_the_copy_check(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    log = acl("v8q")
    rig.arkiv.best("MDGP", log, 6170)
    hashed = []
    real = rig.arkiv.sponsors.run_log_hash
    monkeypatch.setattr(rig.arkiv.sponsors, "run_log_hash", lambda *a: hashed.append(a) or real(*a))
    call = rig.sponsors.begin("record", dict(LIST_PAYLOAD, pay_to=SELLER))
    assert hashed == [] and rig.hedera.requests == []               # begin never reads the disk: the worker does
    rig.sponsors.work()
    assert hashed == [("MDGP", 6170)]
    assert rig.hedera.posts() == [("/hedera/record", dict(RECORD_BODY, log_h=sha(log)))]
    assert call.poll() is None


def test_a_run_whose_log_is_not_here_is_recorded_without_a_hash(tmp_path):
    rig = Rig(tmp_path)
    rig.arkiv.best("MDGP", acl("v8q"), 6290)                         # a best, but not this time
    _record(rig)
    assert rig.hedera.posts() == [("/hedera/record", RECORD_BODY)]


@pytest.mark.parametrize("failure", RECORD_FAILURES)
def test_each_record_failure_is_the_handlers_own(tmp_path, failure):
    rig = Rig(tmp_path)
    call = _record(rig)
    rig.hedera.move("done", ok=False, failure=failure)
    rig.step(call)
    assert call.poll() == Result(ok=False, failure=failure)


@pytest.mark.parametrize("reply", [{"ok": False, "failure": "rate_limited"}, {"ok": False, "failure": "buy_down"},
                                   {"ok": False, "failure": "ls_denied"}, {"ok": False, "failure": None},
                                   {"ok": None, "data": RECORDED}])
def test_a_record_answer_the_handler_cannot_show_is_not_recorded(tmp_path, reply):
    rig = Rig(tmp_path)
    call = _record(rig)
    rig.hedera.move("done", **reply)
    rig.step(call)
    assert call.poll() == Result(ok=False, failure="ls_record_fail")


@pytest.mark.parametrize("what", ["down", "503", "400", "a start off the contract", "no approval id", "no time"])
def test_a_service_that_does_not_take_the_record_is_not_recorded(tmp_path, what):
    rig = Rig(tmp_path)
    payload = dict(LIST_PAYLOAD, pay_to=SELLER)
    if what == "down":
        rig.hedera.down = True
    elif what == "a start off the contract":
        rig.hedera.start = {"expires_s": 120}
    elif what == "no approval id":
        payload["jti"] = None
    elif what == "no time":
        payload["frames"] = None
    else:
        rig.hedera.error = (int(what), "ls_record_fail")
    call = _record(rig, payload)
    rig.sponsors.work()
    assert call.poll() == Result(ok=False, failure="ls_record_fail")


def test_a_service_gone_quiet_mid_record_is_not_recorded_after_a_grace(tmp_path):
    rig = Rig(tmp_path)
    call = _record(rig)
    rig.hedera.down = True
    for _ in range(hedera.SILENT_MS // hedera.POLL_MS):
        rig.step(call)
        assert call.poll() is None
    rig.step(call)
    assert call.poll() == Result(ok=False, failure="ls_record_fail")


def test_a_record_long_past_its_budget_is_given_up(tmp_path):
    rig = Rig(tmp_path)
    call = _record(rig)
    for _ in range((TIMEOUT_MS["record"] + hedera.GRACE_MS) // hedera.POLL_MS):
        rig.step(call)                                              # the service keeps saying "check"
    assert call.poll() == Result(ok=False, failure="ls_record_fail")


def test_a_record_retry_uses_the_same_approval(tmp_path):
    rig = Rig(tmp_path)
    _record(rig)
    again = _record(rig)                                            # Cross on "Approved, Hedera is slow"
    assert [body["jti"] for _, body in rig.hedera.posts()] == ["3f9c0a1b2c3d4e5f"] * 2 and len(rig.hedera.jobs) == 1
    rig.hedera.move("done", ok=True, data=RECORDED)
    rig.step(again)
    assert again.poll().ok


# ---- the seller's payout account: read in the background, pinned for a listing ------------------------------------

def test_a_books_account_is_read_in_the_background_and_kept(tmp_path):
    rig = Rig(tmp_path)
    assert rig.sponsors.pay_to("ANY-6PS") is None and rig.hedera.requests == []
    rig.sponsors.work()
    assert rig.hedera.gets("/hedera/payto/") == ["/hedera/payto/ANY-6PS"]
    assert rig.sponsors.pay_to("ANY-6PS") == SELLER
    for _ in range(hedera.PAYTO_MS // 1000 - 1):                     # looked at, read again only after a minute
        rig.clock.ms += 1000
        rig.sponsors.pay_to("ANY-6PS")
        rig.sponsors.work()
    assert len(rig.hedera.gets("/hedera/payto/")) == 1
    rig.hedera.payto["ANY-6PS"] = "0.0.777"
    rig.clock.ms += 1000
    rig.sponsors.pay_to("ANY-6PS")
    rig.sponsors.work()
    assert rig.sponsors.pay_to("ANY-6PS") == "0.0.777"
    assert rig.make().pay_to("ANY-6PS") == "0.0.777"                 # the launcher started again: kept on disk
    assert rig.sponsors.pay_to("ANY-K2Q") is None                    # no account registered
    rig.sponsors.work()
    assert rig.sponsors.pay_to("ANY-K2Q") is None and rig.hedera.gets("/hedera/payto/")[-1] == "/hedera/payto/ANY-K2Q"
    assert rig.sponsors.pay_to(None) is None and rig.sponsors.pay_to("") is None


@pytest.mark.parametrize("reply", [{"book": "ANY-K2Q", "pay_to": SELLER}, {"book": "ANY-6PS", "pay_to": "0x" + "ab" * 20},
                                   {"book": "ANY-6PS", "pay_to": 5123456}, "nonsense", None])
def test_an_account_reply_off_the_contract_is_never_taken(tmp_path, reply):
    rig = Rig(tmp_path)
    rig.sponsors.pay_to("ANY-6PS")
    rig.sponsors.work()
    def odd(self, method, path, body, timeout_s):
        if "payto" not in path:
            return StubHedera.__call__(self, method, path, body, timeout_s)
        self.requests.append((method, path, body))
        return reply
    rig.hedera.__class__ = type("Odd", (StubHedera,), {"__call__": odd})
    rig.hedera.payto["ANY-6PS"] = "0.0.777"
    rig.clock.ms += hedera.PAYTO_MS
    rig.sponsors.pay_to("ANY-6PS")
    rig.sponsors.work()
    assert rig.sponsors.pay_to("ANY-6PS") == SELLER                   # the last word stands
    asked = len(rig.hedera.gets("/hedera/payto/"))
    rig.clock.ms += hedera.PAYTO_RETRY_MS                             # and it is asked again soon
    rig.sponsors.pay_to("ANY-6PS")
    rig.sponsors.work()
    assert len(rig.hedera.gets("/hedera/payto/")) == asked + 1


def test_a_service_down_keeps_the_last_account_and_nobody_looking_asks_nothing(tmp_path):
    rig = Rig(tmp_path)
    rig.sponsors.pay_to("ANY-6PS")
    rig.sponsors.work()
    rig.hedera.down = True
    rig.clock.ms += hedera.PAYTO_MS
    assert rig.sponsors.pay_to("ANY-6PS") == SELLER
    rig.sponsors.work()
    assert rig.sponsors.pay_to("ANY-6PS") == SELLER
    rig.hedera.down = False
    rig.clock.ms += hedera.IDLE_MS + hedera.PAYTO_MS                 # a game runs: nobody looks
    asked = len(rig.hedera.requests)
    for _ in range(5):
        rig.clock.ms += hedera.HEALTH_MS
        rig.sponsors.work()
    assert len(rig.hedera.requests) == asked


def _spy(monkeypatch, sponsors):
    """Every (step, payload) sponsors.begin is handed from now on."""
    seen, real = [], sponsors.begin

    def begin(step, payload):
        seen.append((step, dict(payload)))
        return real(step, payload)
    monkeypatch.setattr(sponsors, "begin", begin)
    return seen


def test_the_account_is_pinned_at_approve_scan_and_named_alike_in_all_four_payloads(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    rig.arkiv.best("MDGP", acl("6ps"), 6170)
    seen = _spy(monkeypatch, rig.arkiv.sponsors)
    rig.sponsors.pay_to("ANY-6PS")                                   # the hub asked, well before the listing
    rig.sponsors.work()
    rig.sponsors.begin("approve_scan", LIST_PAYLOAD)
    rig.arkiv.inner.work()
    assert rig.bridge.posts() == [("/agentpass/start", {"book": "ANY-6PS", "action": ACTION_TO})]   # World App's text
    rig.hedera.payto["ANY-6PS"] = "0.0.777"                           # the registry changes mid-listing
    rig.clock.ms += hedera.PAYTO_MS
    rig.sponsors.pay_to("ANY-6PS")
    rig.sponsors.work()
    assert rig.sponsors.pay_to("ANY-6PS") == SELLER                   # the listing's screens: what World App shows
    rig.sponsors.begin("approve", LIST_PAYLOAD)
    _record(rig, LIST_PAYLOAD)
    rig.sponsors.begin("publish", LIST_PAYLOAD)
    rig.arkiv.sponsors.work()
    assert rig.hedera.posts("/hedera/record") == [("/hedera/record", dict(RECORD_BODY, log_h=sha(acl("6ps"))))]
    (path, body), = rig.service.posts()
    assert path == "/arkiv/publish" and body["action"] == ACTION_TO and body["pay_to"] == SELLER
    assert [(step, payload["pay_to"]) for step, payload in seen] == [("approve_scan", SELLER), ("approve", SELLER),
                                                                      ("publish", SELLER)]
    rig.sponsors.begin("approve_scan", LIST_PAYLOAD)                   # the next listing pins afresh
    assert rig.sponsors.pay_to("ANY-6PS") == "0.0.777" and seen[-1][1]["pay_to"] == "0.0.777"


def test_a_book_with_no_account_lists_naming_none(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    rig.arkiv.best("MDGP", acl("6ps"), 6170)
    payload = dict(LIST_PAYLOAD, book="ANY-7QZ")
    rig.sponsors.pay_to("ANY-7QZ")
    rig.sponsors.work()
    rig.sponsors.begin("approve_scan", payload)
    rig.arkiv.inner.work()
    assert rig.bridge.posts()[-1][1]["action"] == ACTION
    _record(rig, payload)
    rig.sponsors.begin("publish", payload)
    rig.arkiv.sponsors.work()
    assert "pay_to" not in rig.hedera.posts()[0][1] and rig.hedera.posts()[0][1]["action"] == ACTION
    assert "pay_to" not in rig.service.posts()[0][1] and rig.service.posts()[0][1]["action"] == ACTION


def test_an_account_not_read_yet_pins_none(tmp_path):
    """The service never answered before the approval: World App names no account, and neither does anything after."""
    rig = Rig(tmp_path)
    rig.sponsors.begin("approve_scan", LIST_PAYLOAD)
    rig.arkiv.inner.work()
    assert rig.bridge.posts()[-1][1]["action"] == ACTION
    rig.sponsors.pay_to("ANY-6PS")
    rig.sponsors.work()
    assert rig.sponsors.pay_to("ANY-6PS") is None                    # this listing's screens say none too
    _record(rig, LIST_PAYLOAD)
    (path, body), = rig.hedera.posts()
    assert path == "/hedera/record" and "pay_to" not in body and body["action"] == ACTION


# ---- flags, the pill, and the frame never waits ----------------------------------------------------------------------

def test_hedera_is_real_on_top_of_real_world_and_arkiv(tmp_path):
    rig = Rig(tmp_path)
    s = rig.sponsors
    assert [s.mocked(x) for x in ("world", "board", "third")] == [False, False, False]
    assert s.mock is False                                          # no Square lists, no "Start over (mock)"
    assert s.outcomes("pay") == [] and s.outcomes("record") == [] and s.outcomes("check_listing") == []
    assert s.names is rig.arkiv.inner.names
    rig.bridge.health["approvals"] = "idkit"
    rig.arkiv.inner.work()
    assert s.approvals == "idkit"
    mocked = Rig(tmp_path / "mocked", inner=MockSponsors(rig.clock)).sponsors
    assert [mocked.mocked(x) for x in ("world", "board", "third")] == [True, False, False] and mocked.mock is True


def test_the_hedera_pill_follows_health_and_a_running_job(tmp_path):
    rig = Rig(tmp_path)
    s = rig.sponsors
    assert s.status()["third"] == "busy"                             # not heard from yet: still checking
    s.work()
    assert s.status()["third"] == "ok"
    for change in ({"hedera_pay": False}, {"hedera": "off"}, {"hedera_pay": None}):
        rig.hedera.health.update(change)
        rig.step(ms=hedera.HEALTH_MS)
        assert s.status()["third"] == "off", change
        rig.hedera.health.update(hedera="ok", hedera_pay=True)
        rig.step(ms=hedera.HEALTH_MS)
        assert s.status()["third"] == "ok"
    rig.hedera.down = True
    rig.step(ms=hedera.HEALTH_MS)
    assert s.status()["third"] == "off"
    rig.hedera.down = False
    rig.step(ms=hedera.HEALTH_MS)
    call = _pay(rig)
    assert s.status()["third"] == "busy"
    rig.hedera.move("done", ok=True, data=PAID)
    rig.step(call)
    assert s.status()["third"] == "ok"
    status = s.begin("status", {}).poll()
    assert status.ok and status.data == s.status() and set(status.data) == {"world", "board", "third"}


def test_only_the_worker_talks_to_the_service(tmp_path):
    rig = Rig(tmp_path)
    calls = [rig.sponsors.begin("pay", buy_payload()), rig.sponsors.begin("record", LIST_PAYLOAD)]
    for _ in range(3):
        rig.sponsors.status()
        rig.sponsors.pay_to("ANY-6PS")
        rig.sponsors.board("MDGP")
        for call in calls:
            call.poll()
            call.info
            rig.sponsors.cross(call)
            rig.sponsors.cancel(call)
            rig.sponsors.force(call, MockSponsors(rig.clock).outcomes("pay")[0])
    assert rig.hedera.requests == [] and calls[1].poll() is None


def test_every_other_step_is_the_inner_adapters(tmp_path):
    rig = Rig(tmp_path)
    run = rig.target()
    rig.arkiv.prefetch()
    assert [r.pay_to for r in rig.sponsors.board("MDGP").rows] == [SELLER]
    check = rig.sponsors.begin("check_listing", buy_payload(target_run=run["key"], target_listing=rig.node.listing_of(
        run)["key"], target_log_h=sha(acl("6ps"))))
    rig.arkiv.sponsors.work()
    assert check.poll() == Result(ok=True, data={"price": GHOST_PRICE})
    assert rig.sponsors.begin("sales", {"game": "marine-drive-gp"}).poll() == Result(ok=False)   # never a made-up sale
    assert rig.hedera.requests == []


# ---- through the flow ----------------------------------------------------------------------------------------------

def test_buying_pays_on_hedera_then_loads_her_ghost_with_the_transaction_id(tmp_path):
    rig = Rig(tmp_path)
    run = rig.target()
    flow = rig.flow(**_target_ctx(rig.node, run))
    flow.start("target")
    flow.press("cross")
    assert flow.state.name == "buy_check"
    rig.wait(flow, 100)
    assert flow.state.name == "buy_pay" and flow.mock_rows() == []    # no fake Hedera answers under Square
    rig.wait(flow, 100)
    (path, body), = rig.hedera.posts()
    assert body == {"book": "ANY-K2Q", "game": "MDGP", "seller": "ANY-6PS", "listing": rig.node.listing_of(run)["key"],
                    "run": run["key"], "log_h": sha(acl("6ps")), "frames": 6170, "you_frames": 6290, "price_c": 10}
    for stage in ("pay", "settle"):
        rig.hedera.move(stage)
        rig.wait(flow, 500)
        assert flow.state.name == "buy_pay"
    rig.hedera.move("done", ok=True, data=PAID)
    rig.service.sales[TX] = run["key"]
    rig.wait(flow, 600)
    assert flow.state.name in ("buy_load", "buy_done")
    rig.wait(flow, 200)
    assert flow.state.name == "buy_done"
    assert flow.ledger.purchases["marine-drive-gp:ANY-6PS"]["receipt"] == TX and flow.ledger.spent == GHOST_PRICE
    assert ("/arkiv/ghost", {"run": run["key"], "receipt": TX}) in rig.service.posts()
    what = {flow.fill(a): flow.fill(b) for a, b in flow.state.card["what"]}
    assert what["Receipt"] == TX_SHOWN and what["Paid"] == "0.10 USDC to ANY-6PS"


def test_a_payment_settled_past_the_budget_lands_late_and_loads(tmp_path):
    rig = Rig(tmp_path)
    run = rig.target()
    flow = rig.flow(**_target_ctx(rig.node, run))
    flow.start("buy_pay")
    rig.wait(flow, 100)
    rig.hedera.move("settle")
    rig.wait(flow, TIMEOUT_MS["pay"])
    assert flow.state.name == "buy_down" and flow.busy and flow.ledger.spent == 0    # kept: it may still land
    asked = len(rig.hedera.gets("/hedera/buy/"))
    rig.wait(flow, 30000)
    assert flow.state.name == "buy_down" and len(rig.hedera.gets("/hedera/buy/")) > asked   # still asked
    rig.hedera.move("done", ok=True, data=dict(PAID, late=True))    # the agent found it on the mirror node
    rig.service.sales[TX] = run["key"]
    rig.wait(flow, 600)
    assert flow.state.name == "buy_late" and flow.ledger.spent == GHOST_PRICE
    assert load(rig.path).purchases["marine-drive-gp:ANY-6PS"]["receipt"] == TX
    what = {flow.fill(a): flow.fill(b) for a, b in flow.state.card["what"]}
    assert what["Receipt"] == TX_SHOWN
    flow.press("cross")
    rig.wait(flow, 200)
    assert flow.state.name == "buy_done" and ("/arkiv/ghost", {"run": run["key"], "receipt": TX}) in \
        rig.service.posts()


def test_a_payment_that_never_lands_stays_nothing_paid(tmp_path):
    for ending in ("buy_down", "its life"):
        rig = Rig(tmp_path / ending)
        flow = rig.flow(**_target_ctx(rig.node, rig.target()))
        flow.start("buy_pay")
        rig.wait(flow, TIMEOUT_MS["pay"] + 100)
        assert flow.state.name == "buy_down"
        if ending == "buy_down":                                     # nothing, checked twice: facilitator and mirror
            rig.hedera.move("done", ok=False, failure="buy_down")
            rig.wait(flow, 600)
        else:
            rig.hedera.move("settle")
            rig.wait(flow, 240000, frame=1000)
        assert flow.state.name == "buy_down" and not flow.busy and flow.ledger.spent == 0, ending
        assert flow.ledger.purchases == {}


@pytest.mark.parametrize("failure, data", [("buy_budget", {}), ("buy_changed", {"now_price": "0.25 USDC"}),
                                           ("buy_changed", {"now_price": "gone"}), ("buy_suspended", {}),
                                           ("buy_down", {})])
def test_each_refusal_lands_on_its_screen_and_pays_nothing(tmp_path, failure, data):
    rig = Rig(tmp_path)
    flow = rig.flow(**_target_ctx(rig.node, rig.target()))
    flow.start("buy_pay")
    rig.wait(flow, 100)
    rig.hedera.move("done", ok=False, failure=failure, data=data)
    rig.wait(flow, 600)
    assert flow.state.name == failure and flow.ledger.spent == 0 and flow.ledger.purchases == {}
    if data:
        assert flow.ctx["now_price"] == data["now_price"]
        assert f"now *{data['now_price']}*" in flow.fill(flow.state.card["rows"][0])


def test_a_listing_is_recorded_then_listed_naming_the_same_account(tmp_path):
    rig = Rig(tmp_path)
    rig.arkiv.best("MDGP", acl("6ps"), 6170)
    flow = rig.flow(book="ANY-6PS", best_frames=6170, run_time="1:42.83")
    rig.sponsors.pay_to("ANY-6PS")
    rig.sponsors.work()
    flow.start("list")
    flow.press("cross")
    rig.wait(flow, 100)
    assert flow.state.name == "ls_scan" and rig.bridge.posts()[-1][1]["action"] == ACTION_TO
    rig.bridge.move("done", ok=True, data={"jti": "3f9c0a1b2c3d4e5f"})   # an Agent Pass grant: straight to done
    rig.wait(flow, 600)
    assert flow.state.name == "ls_record"
    assert rig.hedera.posts("/hedera/record") == [("/hedera/record", dict(RECORD_BODY, log_h=sha(acl("6ps"))))]
    rig.hedera.move("done", ok=True, data=RECORDED)
    rig.wait(flow, 600)
    assert flow.state.name == "ls_arkiv"
    body = rig.service.posts()[-1][1]
    assert (body["action"], body["pay_to"], body["jti"]) == (ACTION_TO, SELLER, "3f9c0a1b2c3d4e5f")
    rig.service.move("done", ok=True, data=DONE)
    rig.wait(flow, 600)
    assert flow.state.name == "ls_done" and len(load(rig.path).listings) == 1


@pytest.mark.parametrize("failure", RECORD_FAILURES)
def test_a_record_failure_lands_on_its_screen(tmp_path, failure):
    rig = Rig(tmp_path)
    flow = rig.flow(book="ANY-6PS", best_frames=6170, run_time="1:42.83")
    flow._jti = "3f9c0a1b2c3d4e5f"
    flow.start("ls_record")
    rig.wait(flow, 100)
    rig.hedera.move("done", ok=False, failure=failure)
    rig.wait(flow, 600)
    assert flow.state.name == failure and flow.ledger.listings == []


def test_a_copied_run_is_refused_at_the_record_and_never_published(tmp_path):
    rig = Rig(tmp_path)
    rig.arkiv.best("MDGP", acl("6ps"), 6170)                         # another window's save: the same log
    flow = rig.flow(book="ANY-V8Q", best_frames=6170, run_time="1:42.83")
    flow._jti = "3f9c0a1b2c3d4e5f"
    flow.start("ls_record")
    rig.wait(flow, 100)
    assert rig.hedera.posts("/hedera/record")[0][1]["log_h"] == sha(acl("6ps"))
    rig.hedera.move("done", ok=False, failure="ls_copied")
    rig.wait(flow, 600)
    assert flow.state.name == "ls_copied" and flow.ledger.listings == []
    assert rig.service.posts() == []                                 # no publish follows
    flow.press("cross")
    assert flow.state.name == "hub"


def test_a_slow_record_times_out_and_cross_records_it_on_the_same_approval(tmp_path):
    rig = Rig(tmp_path)
    rig.arkiv.best("MDGP", acl("6ps"), 6170)                         # so the listing goes on to publish it
    flow = rig.flow(book="ANY-6PS", best_frames=6170, run_time="1:42.83")
    flow._jti = "3f9c0a1b2c3d4e5f"
    flow.start("ls_record")
    rig.wait(flow, TIMEOUT_MS["record"])
    assert flow.state.name == "ls_record_fail"
    rig.hedera.move("done", ok=True, data=RECORDED)                  # it landed after all: the retry reuses it
    flow.press("cross")
    rig.wait(flow, 600)
    assert flow.state.name == "ls_arkiv"
    assert [b["jti"] for _, b in rig.hedera.posts("/hedera/record")] == ["3f9c0a1b2c3d4e5f"] * 2


def test_no_square_and_no_start_over_with_all_three_real(tmp_path):
    rig = Rig(tmp_path)
    flow = rig.flow(**_target_ctx(rig.node, rig.target()))
    for state in ("buy_pay", "buy_down", "ls_record", "ls_cancel", "hub"):
        flow.start(state)
        assert flow.mock_rows() == [], state
    assert "Start over (mock)" not in flow.hub_rows and flow.hub_count == 4


# ---- the glue: the launcher with all three real ----------------------------------------------------------------------

@pytest.fixture
def apps():
    made = []
    yield made
    for app in made:
        try:
            app.close()
        except Exception:
            pass


def hedera_app(apps, tmp_path, book="ANY-6PS", hedera_real=True):
    """The real App (test_handler_app's library, fake bridge and runner) on HederaSponsors over the chain's stubs. The
    board from a 6290 best: K2P 6000 (not listed), TEAM 6150 (open tier), 4HJ 6180 (listed with an account), 2KD 6200
    (listed with none), the console's own ANY-6PS 6350 (listed with SELLER), 9MX 6400 (listed with an account)."""
    from arca_launcher.app import App, Config
    from arca_launcher.handler import ledger as L
    from test_app import FakeHw, FakeRunner
    from test_handler_app import Bridge, library, write_best
    L.save(str(tmp_path / "handler.json"), L.Ledger(book=book))
    runs = str(tmp_path / "runs")
    write_best(runs, 6290)
    testlogs = tmp_path / "testlogs"
    testlogs.mkdir()
    (testlogs / "MDGP.acl").write_bytes(b"log")
    bridge = Bridge()
    bridge.runs_dir = runs
    rig = Rig(tmp_path / "chain", runs_dir=runs)
    rig.node.run("ANY-K2P", 6000)
    rig.node.run("TEAM", 6150, book=False, plain=True)
    rig.node.run("ANY-4HJ", 6180, listed=True, pay_to="0.0.6007788")
    rig.node.run("ANY-2KD", 6200, listed=True)
    rig.node.run("ANY-6PS", 6350, listed=True, pay_to=SELLER)
    rig.node.run("ANY-9MX", 6400, listed=True, pay_to="0.0.6009900")
    cfg = Config(library_dir=library(tmp_path), state_path=str(tmp_path / "state.json"), splash=False,
                 run_dir=str(tmp_path / "run"), runs_dir=runs, testlogs_dir=str(testlogs), handler=True)
    app = App(cfg, runner=FakeRunner(), hw=FakeHw(), bridge=bridge,
              sponsors=rig.sponsors if hedera_real else rig.arkiv.sponsors)
    apps.append(app)
    rig.arkiv.prefetch()
    return app, rig


def test_the_hub_names_the_books_hedera_account(apps, tmp_path):
    app, rig = hedera_app(apps, tmp_path)
    app.frame(16, [A.Y])
    flow = app.nav.handler
    assert flow.ctx["wallet"] == "no Hedera account yet" and rig.hedera.requests == []   # asked, not answered yet
    rig.sponsors.work()
    assert rig.hedera.gets("/hedera/payto/") == ["/hedera/payto/ANY-6PS"]
    app.frame(16)
    assert flow.ctx["wallet"] == SELLER
    flow.start("ls_offer")
    app.frame(16)
    assert flow.ctx["wallet"] == SELLER and flow.fill("{wallet}") == SELLER
    app, rig = hedera_app(apps, tmp_path / "none", book="ANY-7QZ")  # a book with no account registered
    app.frame(16, [A.Y])
    rig.sponsors.work()
    app.frame(16)
    assert app.nav.handler.ctx["wallet"] == "no Hedera account yet"


def test_with_hedera_real_the_target_is_a_listing_that_names_an_account(apps, tmp_path):
    app, rig = hedera_app(apps, tmp_path)
    app.frame(16, [A.Y])
    ctx = app.nav.handler.ctx
    assert (ctx["target"], ctx["target_frames"]) == ("ANY-4HJ", 6180)  # 2KD's listing names no account: not for sale
    rows = {r.name: r for r in ctx["board_rows"]}
    assert rows["ANY-2KD"].listed and not rows["ANY-2KD"].sells
    app, rig = hedera_app(apps, tmp_path / "mocked", hedera_real=False)   # Hedera mocked: any listing sells
    app.frame(16, [A.Y])
    assert app.nav.handler.ctx["target"] == "ANY-2KD" and app.nav.handler.ctx["wallet"] != SELLER


# ---- the screens ----------------------------------------------------------------------------------------------------

def _drawn(screen, monkeypatch):
    drawn, real = [], screen.gfx.text

    def spy(s, *a, **kw):
        drawn.append(s)
        return real(s, *a, **kw)
    monkeypatch.setattr(screen.gfx, "text", spy)
    return drawn


SCREENS = ("buy_pay", "buy_done", "buy_late", "buy_down", "ls_offer", "ls_scan", "ls_record", "ls_done")


def _real_flow(rig, name):
    """A flow on all three real, sitting in state name, with ANY-4HJ's ghost bought for TX and ANY-6PS's account read."""
    rig.sponsors.pay_to("ANY-6PS")
    rig.sponsors.work()
    rig.arkiv.inner.work()
    flow = rig.flow(book="ANY-6PS", target="ANY-4HJ", target_time="1:43.00", wallet=SELLER, run_time="1:42.83",
                    receipt=TX)
    flow.ledger.purchases["marine-drive-gp:ANY-4HJ"] = {"price": GHOST_PRICE, "receipt": TX, "at": 0}
    flow.ledger.spent, flow.ledger.spent_day = GHOST_PRICE, TODAY
    flow.start(name)
    flow.ctx.update(code="K7P-2QX", qr="https://world.example/agentpass-1", expires_s=900)
    flow.ms_in_state = 60000
    return flow


def test_with_all_three_real_no_mock_pill_or_tag_is_drawn(screen, tmp_path, monkeypatch):
    from test_handler_view import show
    drawn = _drawn(screen, monkeypatch)
    rig = Rig(tmp_path)
    for name in ("hub",) + SCREENS:
        drawn.clear()
        nav, views = show(screen, _real_flow(rig, name))
        assert "MOCK" not in drawn and "mock receipt" not in drawn, name
        assert not any(h.target == ("handler", "square") for h in views.hits), name
        assert "Start over (mock)" not in drawn


def test_the_buy_and_listing_screens_with_hedera_real_and_all_mock(screen, tmp_path, monkeypatch):
    """Drawn to tests/out/handler_hedera_<state>.png (all three real, stub data) beside
    tests/out/handler_hedera_mock_<state>.png (every sponsor mocked), for a look."""
    from conftest import snapshot
    from test_handler_view import make_flow, show
    from arca_launcher.render import handler_cards, handler_view, text
    cut, real_ellipsize = [], text.ellipsize

    def ellipsize(s, width, measure):
        out = real_ellipsize(s, width, measure)
        if out != s:
            cut.append(s)
        return out
    for module in (text, handler_cards, handler_view):
        monkeypatch.setattr(module, "ellipsize", ellipsize)
    drawn = _drawn(screen, monkeypatch)
    rig = Rig(tmp_path)
    for name in SCREENS:
        drawn.clear()
        show(screen, _real_flow(rig, name), frames=2)
        snapshot(screen.ren, f"handler_hedera_{name}")
        if name in ("buy_done", "buy_late"):
            assert TX_SHOWN in drawn and "mock receipt" not in drawn, name
        if name in ("ls_offer", "ls_scan", "ls_done"):
            assert SELLER in drawn, name
        show(screen, make_flow(tmp_path, name), frames=2)
        snapshot(screen.ren, f"handler_hedera_mock_{name}")
    for name in ("ls_offer", "ls_scan", "ls_done"):                  # a book with no account registered
        drawn.clear()
        flow = _real_flow(rig, name)
        flow.ctx["wallet"] = "no Hedera account yet"
        show(screen, flow, frames=2)
        snapshot(screen.ren, f"handler_hedera_{name}_no_account")
        assert any("no Hedera account yet" in s for s in drawn), name
    assert cut == []                                                 # the receipt and the account fit, uncut


# ---- the real thing: a thread ----------------------------------------------------------------------------------------

class SlowHedera(StubHedera):
    def __call__(self, method, path, body, timeout_s):
        time.sleep(0.3)
        return super().__call__(method, path, body, timeout_s)


def test_a_slow_service_never_holds_up_a_frame(tmp_path):
    rig = Rig(tmp_path)
    service = SlowHedera()
    sponsors = HederaSponsors(rig.arkiv.sponsors, "http://bridge.test:8787", lambda: int(time.monotonic() * 1000),
                              str(tmp_path / "state"), transport=service)
    try:
        worst, call = 0.0, None
        end = time.monotonic() + 5
        while time.monotonic() < end and (call is None or call.poll() is None):
            t0 = time.monotonic()
            sponsors.status()
            sponsors.pay_to("ANY-6PS")
            if call is None:
                call = sponsors.begin("pay", buy_payload())
            call.poll()
            if service.jobs and service.jobs[list(service.jobs)[-1]]["stage"] != "done":
                service.move("done", ok=True, data=PAID)
            worst = max(worst, time.monotonic() - t0)
            time.sleep(0.01)
        assert worst < 0.05
        assert call.poll() == Result(ok=True, data=PAID)
        assert sponsors.pay_to("ANY-6PS") == SELLER
    finally:
        sponsors.close()
    end = time.monotonic() + 3
    while sponsors._thread.is_alive() and time.monotonic() < end:
        time.sleep(0.05)
    assert not sponsors._thread.is_alive()


# ---- wiring: --hedera / ARCA_HEDERA ----------------------------------------------------------------------------------

def test_the_flag_or_the_variable_turns_hedera_on(monkeypatch):
    from arca_launcher.__main__ import build_config
    monkeypatch.delenv("ARCA_HEDERA", raising=False)
    assert build_config([]).hedera is False
    assert build_config(["--hedera"]).hedera is True
    for value, on in (("1", True), ("0", False), ("", False), ("yes", True)):
        monkeypatch.setenv("ARCA_HEDERA", value)
        assert build_config([]).hedera is on, value


def test_hedera_is_real_only_on_real_world_and_arkiv(tmp_path, caplog):
    from arca_launcher.app import Config, make_sponsors
    from arca_launcher.handler.arkiv import ArkivSponsors
    from arca_launcher.handler.world import WorldSponsors
    base = dict(library_dir="/lib", state_path=str(tmp_path / "s.json"), runs_dir=str(tmp_path / "runs"), hedera=True)
    made = []
    try:
        s = make_sponsors(Config(**base))
        assert type(s) is MockSponsors and s.mocked("third")
        assert "Hedera stays mocked" in caplog.text and "--world-bridge and --arkiv-checker not given" in caplog.text
        caplog.clear()
        s = make_sponsors(Config(**base, world_bridge="http://127.0.0.1:9"))
        made.append(s)
        assert type(s) is WorldSponsors and s.mocked("third") and "--arkiv-checker not given" in caplog.text
        caplog.clear()
        s = make_sponsors(Config(**base, world_bridge="http://127.0.0.1:9", arkiv_checker=CHECKER,
                                 arkiv_rpc="http://127.0.0.1:9"), games=("MDGP",))
        made.append(s)
        assert type(s) is HederaSponsors and type(s._inner) is ArkivSponsors and "Hedera stays" not in caplog.text
        assert not any(s.mocked(x) for x in ("world", "board", "third")) and s.mock is False
        assert s._state_dir == str(tmp_path) and s._thread.is_alive()
        s = make_sponsors(Config(**dict(base, hedera=False), world_bridge="http://127.0.0.1:9", arkiv_checker=CHECKER,
                                 arkiv_rpc="http://127.0.0.1:9"), games=("MDGP",))
        made.append(s)
        assert type(s) is ArkivSponsors and s.mocked("third")        # not asked for: the mock's, as before
    finally:
        for s in made:
            s.close()
