"""Tests for the Arkiv adapter (handler/arkiv.py): the real board, the listing check, the ghost and the listing on
Arkiv, around the World adapter; Hedera still mocked.

Most tests run the adapter with no thread, as test_handler_world.py does: a StubNode stands in for the public Arkiv
RPC (it answers only the spec's exact query strings), a StubService for the World bridge's /arkiv/* routes, a fake
clock for time, and the test calls work() (one round of the worker) by hand. The last ones run the real thread."""
import base64
import hashlib
import json
import os
import re
import struct
import time
import urllib.error

import pytest

from arca_launcher.handler import arkiv, arkiv_rpc as rpc
from arca_launcher.handler.arkiv import ArkivSponsors
from arca_launcher.handler.flow import Flow
from arca_launcher.handler.ledger import GHOST_PRICE, Ledger, load
from arca_launcher.handler.mock import MockSponsors
from arca_launcher.handler.sponsors import TIMEOUT_MS, BoardRead, Result
from arca_launcher.handler.world import WorldSponsors
from test_handler_world import StubBridge

CHECKER = "0x5b38da6a701c568545dcfcb03fcb875f56beddc4"
STRANGER = "0xab8483f64d9c6d1ecf9b849ae677dd3315835cb2"
SEASON = 1
PUBLISH_FAILURES = ("ls_expired", "ls_wrong", "ls_mismatch", "ls_reused", "ls_publish_fail")


class FakeClock:
    def __init__(self):
        self.ms = 0

    def __call__(self):
        return self.ms


def acl(seed, game=b"MDGP"):
    """A run log as far as these tests care: ACL1, the game, rules 4, then bytes of its own."""
    return b"ACL1" + game + struct.pack("<I", 4) + bytes(20) + seed.encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def key(name):
    return "0x" + hashlib.sha256(("key:" + name).encode()).hexdigest()


def _attr(name, kind, value):
    return {"name": name, "type": kind, "value": value}


class StubNode:
    """The Rabdi node's arkiv_query in memory. It answers only the spec's exact strings: each game's Q1 and Q2, and Q6
    by key; anything else fails the test. Only selected columns come back, as on the real node. ignore_pin: a node
    that skips the `$creator` filter (the look-alike comes back too); down: every request fails."""

    def __init__(self):
        self.runs, self.listings, self.queries = [], [], []
        self.down = False
        self.ignore_pin = False
        self.block = 0x3fe90

    def run(self, name, frames, log=None, plain=False, listed=False, human=True, book=True, creator=CHECKER,
            game="MDGP", price="0.1"):
        """A run row (and its listing when listed). name: its book, or with book=False an open-tier label."""
        log = log if log is not None else acl(name + str(frames))
        attrs = [_attr("arkiv.schema", "str", "anypercent.run"), _attr("game", "str", game),
                 _attr("title", "str", "MARINE DRIVE GP"), _attr("season", "i32", SEASON),
                 _attr("rules", "u64", "0x4"), _attr("frames", "u64", hex(frames)),
                 _attr("log_h", "str", sha(log)), _attr("runner", "str", (name.lower() * 4)[:16]),
                 _attr("human", "bool", human and book), _attr("tool", "str", "arcade_replay sha256:0123456789ab")]
        attrs.append(_attr("book", "str", name) if book else _attr("label", "str", name))
        if human and book:
            attrs.append(_attr("credential", "str", "Orb"))
        attrs.append(_attr("log", "bytes", "0x" + log.hex()) if plain else _attr("log_enc", "bytes", "0xabcdef"))
        entity = {"key": key(f"{creator}{name}{frames}"), "creator": creator, "expiresAt": "0x7a9812",
                  "attributes": attrs}
        self.runs.append(entity)
        if listed:
            self.listings.append({"key": key("listing" + entity["key"]), "creator": creator, "expiresAt": "0x46a1d0",
                                  "attributes": [
                                      _attr("arkiv.schema", "str", "anypercent.listing"),
                                      _attr("run", "key", entity["key"]), _attr("game", "str", game),
                                      _attr("season", "i32", SEASON), _attr("frames", "u64", hex(frames)),
                                      _attr("log_h", "str", sha(log)), _attr("price", "dec", price),
                                      _attr("seller", "str", (name.lower() * 4)[:16]), _attr("book", "str", name),
                                      _attr("human", "bool", True)]})
        return entity

    def listing_of(self, run):
        return next(x for x in self.listings if _value(x, "run") == run["key"])

    def __call__(self, method, params, timeout_s):
        assert method == "arkiv_query" and timeout_s <= 3
        text, options = params
        self.queries.append(text)
        if self.down:
            raise urllib.error.URLError("unreachable")
        for game in ("SHIP", "MDGP", "RUSH", "SEGF", "ZIPG"):
            for q, rows in ((rpc.q1(game, SEASON, CHECKER), self.runs), (rpc.q2(game, SEASON, CHECKER), self.listings)):
                if text == q:
                    assert options["limit"] == "0x64"
                    hits = sorted((e for e in rows if _value(e, "game") == game and self._pinned(e)),
                                  key=lambda e: int(_value(e, "frames"), 16))
                    return self._page(hits, options)
        m = re.fullmatch(r"arkiv\.schema = str\('(anypercent\.(?:run|listing))'\) AND \$key = key\((0x[0-9a-f]{64})\)"
                         r" AND \$creator = addr\((0x[0-9a-fA-F]{40})\)", text)
        assert m and m.group(3).lower() == CHECKER and text == rpc.q6(m.group(1), m.group(2), CHECKER), text
        rows = self.runs if m.group(1) == "anypercent.run" else self.listings
        return self._page([e for e in rows if e["key"] == m.group(2) and self._pinned(e)], options)

    def _pinned(self, entity):
        return self.ignore_pin or entity["creator"] == CHECKER

    def _page(self, entities, options):
        names = options["select"]["attributes"]
        out = [dict({k: e[k] for k in ("key", "creator", "expiresAt")},
                    attributes=[a for a in e["attributes"] if a["name"] in names]) for e in entities]
        return {"jsonrpc": "2.0", "id": 1, "result": {"data": json.loads(json.dumps(out)),
                                                      "blockNumber": hex(self.block)}}


def _value(entity, name):
    return next(a["value"] for a in entity["attributes"] if a["name"] == name)


def _name(run):
    """A run's book, or an open-tier run's label."""
    return next(a["value"] for a in run["attributes"] if a["name"] in ("book", "label"))


class StubService:
    """The World bridge's /arkiv/* routes in memory. One job per jti (a repeat POST answers the same id); the test
    moves the latest job with move(). ghosts: run key -> the plain log a listed run decrypts to, for any mock receipt
    of the right shape. down: every request fails; error: (status, failure) every request answers instead."""

    def __init__(self):
        self.requests, self.jobs, self.by_jti, self.ghosts = [], {}, {}, {}
        self.down = False
        self.error = None
        self.config = {"chain_id": 7794095, "rpc": rpc.RABDI_RPC, "explorer": "https://rabdi.explorer.arkiv.network",
                       "checker": rpc.eip55(CHECKER), "season": SEASON,
                       "schemas": {"run": "anypercent.run", "listing": "anypercent.listing"}, "price": "0.10",
                       "listing_days": 7}

    def __call__(self, method, path, body, timeout_s):
        self.requests.append((method, path, body))
        assert timeout_s <= 5
        if self.down:
            raise urllib.error.URLError("connection refused")
        if self.error is not None:
            status, failure = self.error
            raise urllib.error.HTTPError(path, status, failure, {}, None)
        if (method, path) == ("GET", "/arkiv/config"):
            return json.loads(json.dumps(self.config))
        if (method, path) == ("POST", "/arkiv/publish"):
            jid = self.by_jti.setdefault(body["jti"], f"pub{len(self.by_jti) + 1}")
            self.jobs.setdefault(jid, {"stage": "check", "ok": None, "failure": None, "data": {}})
            return {"id": jid, "expires_s": 120}
        if method == "GET" and path.startswith("/arkiv/publish/") and path.rsplit("/", 1)[1] in self.jobs:
            return json.loads(json.dumps(self.jobs[path.rsplit("/", 1)[1]]))
        if (method, path) == ("POST", "/arkiv/ghost") and body["run"] in self.ghosts:
            if not re.fullmatch(r"mock-[0-9a-f]{8}", body.get("receipt") or ""):
                raise urllib.error.HTTPError(path, 402, "payment_required", {}, None)
            log = self.ghosts[body["run"]]
            return {"log": base64.b64encode(log).decode(), "log_h": sha(log)}
        raise urllib.error.HTTPError(path, 404, "not_on_board", {}, None)

    def move(self, stage, ok=None, failure=None, data=None):
        self.jobs[list(self.jobs)[-1]] = {"stage": stage, "ok": ok, "failure": failure, "data": data or {}}

    def posts(self):
        return [(path, body) for method, path, body in self.requests if method == "POST"]


class Replays:
    """The game's replay tool: the time each log (by its hash) replays to; None for a log it does not know."""

    def __init__(self):
        self.times, self.calls = {}, []

    def __call__(self, arcade_id, path):
        with open(path, "rb") as f:
            data = f.read()
        self.calls.append((arcade_id, os.path.basename(path)))
        return self.times.get(sha(data))

    def know(self, log, frames):
        self.times[sha(log)] = frames


class Rig:
    def __init__(self, tmp_path, games=("MDGP", "SHIP"), inner=None, runs_dir=None):
        self.clock, self.node, self.service, self.replays = FakeClock(), StubNode(), StubService(), Replays()
        self.runs_dir, self.state_dir = runs_dir or str(tmp_path / "runs"), str(tmp_path / "state")
        self.bridge = StubBridge()
        self.inner = inner or WorldSponsors("http://bridge.test:8787", self.clock, transport=self.bridge,
                                            background=False)
        self.sponsors = self.make(games)

    def make(self, games=("MDGP", "SHIP")):
        return ArkivSponsors(self.inner, "http://bridge.test:8787", self.node, CHECKER, SEASON, self.runs_dir,
                             self.state_dir, self.clock, transport=self.service, background=False,
                             replay=self.replays, games=games)

    def step(self, ms=arkiv.POLL_MS, look=True):
        """Let ms pass, look as PB's screen does every frame (status), and run one round of the worker."""
        self.clock.ms += ms
        if look:
            self.sponsors.status()
        self.sponsors.work()

    def prefetch(self):
        for _ in range(4):
            self.sponsors.work()

    def best(self, game, log, frames):
        os.makedirs(os.path.join(self.runs_dir, "best"), exist_ok=True)
        with open(os.path.join(self.runs_dir, "best", game + ".acl"), "wb") as f:
            f.write(log)
        with open(os.path.join(self.runs_dir, "best", game + ".json"), "w") as f:
            json.dump({"time_frames": frames, "finished": True}, f)


def target_payload(node, run, **over):
    """What the flow hands a buy step for a real target: the run, its listing, its log and time."""
    payload = {"game": "marine-drive-gp", "arcade_id": "MDGP", "title": "MARINE DRIVE GP", "seller": _name(run),
               "price": GHOST_PRICE, "book": "ANY-7QZ", "jti": None, "run_time": "1:44.83", "frames": 6290,
               "target_run": run["key"], "target_listing": next((x["key"] for x in node.listings
                                                                  if _value(x, "run") == run["key"]), None),
               "target_log_h": _value(run, "log_h"), "target_frames": int(_value(run, "frames"), 16),
               "receipt": "mock-1a2b3c4d"}
    payload.update(over)
    return payload


LIST_PAYLOAD = {"game": "marine-drive-gp", "arcade_id": "MDGP", "title": "MARINE DRIVE GP", "seller": None,
                "price": GHOST_PRICE, "book": "ANY-6PS", "jti": "3f9c0a1b2c3d4e5f", "run_time": "1:42.83",
                "frames": 6170, "target_run": None, "target_listing": None, "target_log_h": None,
                "target_frames": None, "receipt": None}
ACTION = "List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC on the public board"
DONE = {"run": "0x" + "12ab" * 16, "listing": "0x" + "34cd" * 16, "tx": "0x" + "9f" * 32}


# ---- the board: read in the background, cached, never made up ------------------------------------------------------

def test_every_arcade_board_is_read_at_start_on_the_worker(tmp_path):
    rig = Rig(tmp_path)
    rig.node.run("ANY-6PS", 6170, listed=True)
    rig.node.run("TEAM", 6300, book=False, plain=True)
    assert rig.sponsors.board("MDGP") is None                           # nothing read yet, and nothing asked here
    rig.sponsors.status()
    assert rig.node.queries == []
    rig.sponsors.work()
    assert rig.node.queries == [rpc.q1("MDGP", SEASON, CHECKER), rpc.q2("MDGP", SEASON, CHECKER)]
    rig.sponsors.work()                                                 # one game a round: then SHIP
    assert rig.node.queries[2:] == [rpc.q1("SHIP", SEASON, CHECKER), rpc.q2("SHIP", SEASON, CHECKER)]
    read = rig.sponsors.board("MDGP")
    assert isinstance(read, BoardRead) and not read.stale and read.block == 0x3fe90
    assert [(r.book or r.label, r.frames, r.listing is not None) for r in read.rows] == [("ANY-6PS", 6170, True),
                                                                                         ("TEAM", 6300, False)]
    assert rig.sponsors.board("SHIP").rows == ()
    rig.sponsors.work()
    assert len(rig.node.queries) == 4                                   # read once; nobody looked long enough since


def test_the_open_game_is_read_again_every_15_s_while_someone_looks(tmp_path):
    rig = Rig(tmp_path)
    rig.prefetch()
    rig.sponsors.board("MDGP")                                          # PB opened Marine Drive GP's board
    asked = len(rig.node.queries)
    for _ in range(arkiv.REFRESH_MS // arkiv.POLL_MS - 1):
        rig.step()
        assert len(rig.node.queries) == asked
    rig.node.run("ANY-K2P", 6000, listed=True)                          # a new run lands meanwhile
    rig.step()
    assert rig.node.queries[asked:] == [rpc.q1("MDGP", SEASON, CHECKER), rpc.q2("MDGP", SEASON, CHECKER)]
    assert [r.book for r in rig.sponsors.board("MDGP").rows] == ["ANY-K2P"]
    asked = len(rig.node.queries)
    rig.clock.ms += arkiv.IDLE_MS + arkiv.REFRESH_MS                    # a game is running: nobody looks
    for _ in range(5):
        rig.sponsors.work()
    assert len(rig.node.queries) == asked


def test_the_board_someone_opens_is_read_before_the_rest(tmp_path):
    rig = Rig(tmp_path)
    rig.sponsors.board("SHIP")                                          # PB opened during the start-up reads
    rig.sponsors.work()
    assert rig.node.queries == [rpc.q1("SHIP", SEASON, CHECKER), rpc.q2("SHIP", SEASON, CHECKER)]
    rig.sponsors.work()
    assert rig.node.queries[2:] == [rpc.q1("MDGP", SEASON, CHECKER), rpc.q2("MDGP", SEASON, CHECKER)]


def test_a_glance_reads_nothing_new(tmp_path):
    """Attract mode's run to beat glances at every board: that never makes one the open game."""
    rig = Rig(tmp_path)
    rig.prefetch()
    asked = len(rig.node.queries)
    for _ in range(40):
        rig.clock.ms += 1000
        rig.sponsors.board("SHIP", look=False)
        rig.sponsors.work()
    assert len(rig.node.queries) == asked


def test_rows_another_wallet_wrote_never_reach_the_board(tmp_path):
    """The look-alike demo: a stranger's well-formed row 10 s faster, under the owner's own book. The pinned query
    leaves it out; a node that skipped the pin would hand it over, and the console still drops it."""
    rig = Rig(tmp_path)
    rig.node.run("ANY-6PS", 6170, listed=True)
    rig.node.run("ANY-6PS", 5570, listed=True, creator=STRANGER)
    rig.node.ignore_pin = True
    rig.prefetch()
    rows = rig.sponsors.board("MDGP").rows
    assert [(r.book, r.frames) for r in rows] == [("ANY-6PS", 6170)]
    assert rig.sponsors.status()["board"] == "ok"


def test_an_outage_keeps_the_last_board_read_marked_stale(tmp_path):
    rig = Rig(tmp_path)
    rig.node.run("ANY-6PS", 6170, listed=True)
    rig.prefetch()
    assert rig.sponsors.status()["board"] == "ok"
    rig.node.down = True
    rig.sponsors.board("MDGP")
    rig.step(arkiv.REFRESH_MS)
    read = rig.sponsors.board("MDGP")
    assert read.stale and [r.book for r in read.rows] == ["ANY-6PS"]
    assert rig.sponsors.status()["board"] == "off"
    rig.node.down = False
    rig.step(arkiv.REFRESH_MS)
    assert not rig.sponsors.board("MDGP").stale and rig.sponsors.status()["board"] == "ok"


def test_the_board_survives_a_restart_with_arkiv_down(tmp_path):
    rig = Rig(tmp_path)
    rig.node.run("ANY-6PS", 6170, listed=True)
    rig.node.run("TEAM", 6300, book=False, plain=True)
    rig.prefetch()
    first = rig.sponsors.board("MDGP")
    with open(os.path.join(rig.state_dir, arkiv.CACHE_FILE), encoding="utf-8") as f:
        cached = json.load(f)
    assert cached["checker"] == CHECKER and cached["boards"]["MDGP"]["block"] == 0x3fe90
    rig.node.down = True
    again = rig.make()                                                  # the launcher started again, offline
    read = again.board("MDGP")
    assert read.stale and read.rows == first.rows and read.block == first.block
    again.work()
    assert again.board("MDGP").rows == first.rows and again.status()["board"] == "off"


@pytest.mark.parametrize("change", ["checker", "season", "garbage", "a bad row"])
def test_a_cache_that_is_not_this_boards_is_not_shown(tmp_path, change):
    rig = Rig(tmp_path)
    rig.node.run("ANY-6PS", 6170, listed=True)
    rig.prefetch()
    path = os.path.join(rig.state_dir, arkiv.CACHE_FILE)
    with open(path, encoding="utf-8") as f:
        cached = json.load(f)
    if change == "checker":
        cached["checker"] = STRANGER
    elif change == "season":
        cached["season"] = 2
    elif change == "a bad row":
        cached["boards"]["MDGP"]["rows"][0]["log_h"] = "../../x"
    with open(path, "w", encoding="utf-8") as f:
        f.write("not json" if change == "garbage" else json.dumps(cached))
    assert rig.make().board("MDGP") is None


# ---- the service's /arkiv/config: a warning when the pins differ, nothing more ------------------------------------

def test_the_services_config_is_asked_once_after_the_boards(tmp_path, caplog):
    rig = Rig(tmp_path)
    rig.prefetch()
    assert [r for r in rig.service.requests if r[1] == "/arkiv/config"] == [("GET", "/arkiv/config", None)]
    assert rig.sponsors.pin_differs is None and "will not show" not in caplog.text
    for _ in range(5):
        rig.step(arkiv.CONFIG_RETRY_MS)
    assert len([r for r in rig.service.requests if r[1] == "/arkiv/config"]) == 1


@pytest.mark.parametrize("change, said", [({"checker": STRANGER}, "checker " + STRANGER), ({"season": 2}, "season 2"),
                                          ({"checker": None}, "no checker")])
def test_a_service_writing_under_another_pin_is_warned_about(tmp_path, caplog, change, said):
    rig = Rig(tmp_path)
    rig.service.config.update(change)
    rig.prefetch()
    assert rig.sponsors.pin_differs == said and "will not show on this board" in caplog.text
    assert rig.sponsors._checker == CHECKER and rig.sponsors._season == SEASON   # the console's pin stands


def test_a_service_not_up_yet_is_asked_again_later(tmp_path):
    rig = Rig(tmp_path)
    rig.service.down = True
    rig.prefetch()
    asked = len(rig.service.requests)
    rig.step(arkiv.CONFIG_RETRY_MS - arkiv.POLL_MS, look=False)
    assert len(rig.service.requests) == asked
    rig.service.down = False
    rig.step(arkiv.POLL_MS, look=False)
    assert rig.service.requests[-1] == ("GET", "/arkiv/config", None) and rig.sponsors.pin_differs is None


# ---- check_listing: re-read the listing and its run straight from Arkiv ---------------------------------------------

def _check(rig, payload):
    call = rig.sponsors.begin("check_listing", payload)
    assert call.poll() is None and call.info == {}
    rig.sponsors.work()
    return call.poll()


def test_a_live_listing_at_the_price_checks_out(tmp_path):
    rig = Rig(tmp_path)
    run = rig.node.run("ANY-2KD", 6200, listed=True)
    asked = len(rig.node.queries)
    assert _check(rig, target_payload(rig.node, run)) == Result(ok=True, data={"price": GHOST_PRICE})
    listing = rig.node.listing_of(run)
    assert rig.node.queries[asked:] == [rpc.q6(rpc.LISTING_SCHEMA, listing["key"], CHECKER),
                                        rpc.q6(rpc.RUN_SCHEMA, run["key"], CHECKER)]


def test_a_listing_that_is_gone_changed(tmp_path):
    rig = Rig(tmp_path)
    run = rig.node.run("ANY-2KD", 6200, listed=True)
    payload = target_payload(rig.node, run)
    rig.node.listings.clear()                                           # it ran out, or was deleted
    assert _check(rig, payload) == Result(ok=False, failure="buy_changed", data={"now_price": "gone"})


@pytest.mark.parametrize("price, shown", [("0.5", "0.50 USDC"), ("0.25", "0.25 USDC"), ("0.105", "0.105 USDC")])
def test_a_listing_at_another_price_changed(tmp_path, price, shown):
    rig = Rig(tmp_path)
    run = rig.node.run("ANY-2KD", 6200, listed=True, price=price)
    assert _check(rig, target_payload(rig.node, run)) == Result(ok=False, failure="buy_changed",
                                                                data={"now_price": shown})
    rig.node.listings.clear()
    run = rig.node.run("ANY-3PQ", 6210, listed=True, price="0.10")       # 0.10 is the price, however it is written
    assert _check(rig, target_payload(rig.node, run)).ok


@pytest.mark.parametrize("what", ["gone", "a stranger's", "another log"])
def test_a_run_that_is_not_the_listed_one_is_suspended(tmp_path, what):
    rig = Rig(tmp_path)
    run = rig.node.run("ANY-2KD", 6200, listed=True)
    payload = target_payload(rig.node, run)
    if what == "gone":
        rig.node.runs.clear()
    elif what == "a stranger's":
        run["creator"] = STRANGER
        rig.node.ignore_pin = True
    else:
        payload["target_log_h"] = sha(b"another run")
    assert _check(rig, payload) == Result(ok=False, failure="buy_suspended")


def test_arkiv_down_or_a_bad_reply_is_a_failed_check(tmp_path):
    rig = Rig(tmp_path)
    run = rig.node.run("ANY-2KD", 6200, listed=True)
    rig.node.down = True
    assert _check(rig, target_payload(rig.node, run)) == Result(ok=False, failure="buy_check_fail")
    assert rig.sponsors.status()["board"] == "off"
    rig.node.down = False
    rig.sponsors._rpc = lambda method, params, timeout_s: {"jsonrpc": "2.0", "id": 1, "result": "nonsense"}
    assert _check(rig, target_payload(rig.node, run)) == Result(ok=False, failure="buy_check_fail")
    assert _check(rig, target_payload(rig.node, run, target_listing=None)).failure == "buy_check_fail"


def test_a_changed_listing_reads_its_board_again(tmp_path):
    rig = Rig(tmp_path)
    run = rig.node.run("ANY-2KD", 6200, listed=True)
    rig.prefetch()
    payload = target_payload(rig.node, run)
    rig.node.listings.clear()
    _check(rig, payload)
    asked = len(rig.node.queries)
    rig.step()
    assert rig.node.queries[asked:] == [rpc.q1("MDGP", SEASON, CHECKER), rpc.q2("MDGP", SEASON, CHECKER)]
    assert rig.sponsors.board("MDGP").rows[0].listing is None


# ---- load_ghost: from the row (plain) or the service (listed), checked against the row -------------------------------

def _load(rig, payload):
    call = rig.sponsors.begin("load_ghost", payload)
    assert call.poll() is None
    rig.sponsors.work()
    return call.poll()


def _ghost_file(rig, log):
    return os.path.join(rig.runs_dir, "ghosts", sha(log) + ".acl")


def test_a_plain_ghost_comes_straight_from_its_row(tmp_path):
    rig = Rig(tmp_path)
    log = acl("team")
    run = rig.node.run("TEAM", 6300, log=log, plain=True, book=False)
    rig.replays.know(log, 6300)
    result = _load(rig, target_payload(rig.node, run, target_listing=None))
    assert result == Result(ok=True, data={"ghost_log": _ghost_file(rig, log)})
    with open(_ghost_file(rig, log), "rb") as f:
        assert f.read() == log
    assert rig.replays.calls == [("MDGP", sha(log) + ".acl.part")]
    assert rig.node.queries[-1] == rpc.q6(rpc.RUN_SCHEMA, run["key"], CHECKER)
    assert rig.service.requests == []                                   # nothing of ours in the read path


def test_a_listed_ghost_comes_from_the_service_with_the_receipt(tmp_path):
    rig = Rig(tmp_path)
    log = acl("2kd")
    run = rig.node.run("ANY-2KD", 6200, log=log, listed=True)
    rig.service.ghosts[run["key"]] = log
    rig.replays.know(log, 6200)
    result = _load(rig, target_payload(rig.node, run))
    assert result == Result(ok=True, data={"ghost_log": _ghost_file(rig, log)})
    assert rig.service.posts() == [("/arkiv/ghost", {"run": run["key"], "receipt": "mock-1a2b3c4d"})]


@pytest.mark.parametrize("what", ["another log from the service", "a replay that disagrees", "a replay that fails",
                                  "no receipt", "payment refused", "the service down", "arkiv down", "the run gone",
                                  "a short log", "not base64"])
def test_a_ghost_that_does_not_check_out_never_loads(tmp_path, what):
    rig = Rig(tmp_path)
    log = acl("2kd")
    run = rig.node.run("ANY-2KD", 6200, log=log, listed=True)
    rig.service.ghosts[run["key"]] = log
    rig.replays.know(log, 6200)
    payload = target_payload(rig.node, run)
    if what == "another log from the service":
        rig.service.ghosts[run["key"]] = acl("someone else")
        rig.replays.know(acl("someone else"), 6200)
    elif what == "a replay that disagrees":
        rig.replays.know(log, 6100)
    elif what == "a replay that fails":
        rig.replays.times.clear()
    elif what == "no receipt":
        payload["receipt"] = None
    elif what == "payment refused":
        payload["receipt"] = "receipt-from-elsewhere"
    elif what == "the service down":
        rig.service.down = True
    elif what == "arkiv down":
        rig.node.down = True
    elif what == "the run gone":
        rig.node.runs.clear()
    elif what == "a short log":
        rig.service.ghosts[run["key"]] = b"ACL1MDGP"
    elif what == "not base64":
        rig.service.ghosts.clear()
        rig.service.__class__ = type("Odd", (StubService,), {"__call__": lambda self, m, p, b, t: {"log": "%%%"}})
    assert _load(rig, payload) == Result(ok=False, failure="buy_load_fail"), what
    assert not os.path.exists(os.path.join(rig.runs_dir, "ghosts", sha(log) + ".acl"))
    leftovers = os.listdir(os.path.join(rig.runs_dir, "ghosts")) if os.path.isdir(
        os.path.join(rig.runs_dir, "ghosts")) else []
    assert leftovers == []


def test_a_ghost_already_here_loads_with_no_network(tmp_path):
    rig = Rig(tmp_path)
    log = acl("2kd")
    run = rig.node.run("ANY-2KD", 6200, log=log, listed=True)
    rig.service.ghosts[run["key"]] = log
    rig.replays.know(log, 6200)
    payload = target_payload(rig.node, run)
    assert _load(rig, payload).ok
    rig.node.down = rig.service.down = True
    assert _load(rig, payload) == Result(ok=True, data={"ghost_log": _ghost_file(rig, log)})
    with open(_ghost_file(rig, log), "wb") as f:                        # a file that is not that log any more
        f.write(acl("tampered"))
    assert _load(rig, payload).failure == "buy_load_fail"


def test_a_mock_target_is_still_the_mocks(tmp_path):
    rig = Rig(tmp_path)
    call = rig.sponsors.begin("load_ghost", dict(LIST_PAYLOAD, seller="RIA"))   # no target_run: the mock's ghost
    rig.clock.ms += 1200
    assert call.poll() == Result(ok=True)
    assert rig.node.queries == [] and rig.service.requests == []


# ---- publish: through the service, which replays and writes ---------------------------------------------------------

def _publish(rig, payload=LIST_PAYLOAD):
    call = rig.sponsors.begin("publish", payload)
    rig.sponsors.work()
    return call


def test_publish_sends_the_run_and_follows_its_stages(tmp_path):
    rig = Rig(tmp_path)
    log = acl("6ps")
    rig.best("MDGP", log, 6170)
    call = rig.sponsors.begin("publish", LIST_PAYLOAD)
    assert call.poll() is None and rig.service.requests == []           # the frame never sends
    assert rig.sponsors.status()["board"] == "busy"
    rig.sponsors.work()
    assert rig.service.posts() == [("/arkiv/publish", {
        "book": "ANY-6PS", "jti": "3f9c0a1b2c3d4e5f", "action": ACTION, "game": "MDGP", "title": "MARINE DRIVE GP",
        "frames": 6170, "price_c": 10, "log": base64.b64encode(log).decode()})]
    for stage in ("check", "check", "write"):
        rig.service.move(stage)
        rig.step()
        assert call.poll() is None and rig.sponsors.status()["board"] == "busy"
    assert rig.service.requests[-1] == ("GET", "/arkiv/publish/pub1", None)
    rig.service.move("done", ok=True, data=DONE)
    rig.step()
    assert call.poll() == Result(ok=True, data=DONE)
    assert rig.sponsors.status()["board"] == "ok"


def test_the_action_is_the_approved_digest(tmp_path):
    from arca_launcher.handler.world import _digest
    assert _digest(LIST_PAYLOAD) == ACTION                              # what World App showed, to the character
    assert len(ACTION) <= 160


def test_publish_finds_the_run_in_the_queue_when_it_is_not_the_best(tmp_path):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("best"), 6100)
    queue = os.path.join(rig.runs_dir, "queue")
    os.makedirs(queue)
    for name, frames in (("MDGP-0000beef", 6250), ("MDGP-0000cafe", 6170), ("SHIP-0000cafe", 6170)):
        with open(os.path.join(queue, name + ".acl"), "wb") as f:
            f.write(acl(name))
        with open(os.path.join(queue, name + ".json"), "w") as f:
            json.dump({"time_frames": frames}, f)
    _publish(rig)
    assert rig.service.posts()[0][1]["log"] == base64.b64encode(acl("MDGP-0000cafe")).decode()


def test_no_log_for_that_time_lists_nothing(tmp_path):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("best"), 6100)
    call = _publish(rig)
    assert call.poll() == Result(ok=False, failure="ls_publish_fail") and rig.service.requests == []


@pytest.mark.parametrize("failure", PUBLISH_FAILURES)
def test_each_publish_failure_is_the_handlers_own(tmp_path, failure):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    call = _publish(rig)
    rig.service.move("done", ok=False, failure=failure)
    rig.step()
    assert call.poll() == Result(ok=False, failure=failure)


@pytest.mark.parametrize("reply", [
    {"stage": "done", "ok": False, "failure": "rate_limited", "data": {}},      # no screen for it
    {"stage": "done", "ok": False, "failure": "buy_load_fail", "data": {}},     # another step's
    {"stage": "done", "ok": False, "failure": None, "data": {}},
    {"stage": "done", "ok": True, "failure": None, "data": {"run": DONE["run"]}},
    {"stage": "done", "ok": True, "failure": None, "data": dict(DONE, listing="0x12")},
])
def test_an_answer_the_handler_cannot_show_is_not_listed(tmp_path, reply):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    call = _publish(rig)
    rig.service.move(**reply)
    rig.step()
    assert call.poll() == Result(ok=False, failure="ls_publish_fail")


@pytest.mark.parametrize("what", ["down", "503", "400", "a start off the contract"])
def test_a_service_that_does_not_take_the_run_is_not_listed(tmp_path, what):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    if what == "down":
        rig.service.down = True
    elif what == "a start off the contract":
        rig.service.__class__ = type("Odd", (StubService,), {"__call__": lambda self, m, p, b, t: {"expires_s": 120}})
    else:
        rig.service.error = (int(what), "ls_publish_fail")
    call = _publish(rig)
    assert call.poll() == Result(ok=False, failure="ls_publish_fail")


def test_a_service_gone_quiet_mid_publish_is_not_listed_after_a_grace(tmp_path):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    call = _publish(rig)
    rig.service.down = True
    for _ in range(arkiv.SILENT_MS // arkiv.POLL_MS):
        rig.step()
        assert call.poll() is None
    rig.step()
    assert call.poll() == Result(ok=False, failure="ls_publish_fail")


def test_a_short_blip_mid_publish_is_forgiven(tmp_path):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    call = _publish(rig)
    rig.service.down = True
    rig.step()
    rig.step()
    rig.service.down = False
    rig.service.move("done", ok=True, data=DONE)
    rig.step()
    assert call.poll() == Result(ok=True, data=DONE)


def test_a_retry_after_a_failed_write_uses_the_same_approval(tmp_path):
    """The 8 s budget can run out while the service replays and writes: Cross on "not listed yet" publishes again
    with the same jti, and the service answers the same job."""
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    first = _publish(rig)
    rig.service.move("write")
    rig.step()
    again = _publish(rig)                                               # the flow gave up and the player retried
    assert [body["jti"] for path, body in rig.service.posts()] == ["3f9c0a1b2c3d4e5f"] * 2
    rig.service.move("done", ok=True, data=DONE)
    rig.step()
    assert again.poll() == Result(ok=True, data=DONE)
    assert first.poll() is None                                         # the old call is dropped: nobody asks it
    assert [p for m, p, b in rig.service.requests if m == "GET"][-1] == "/arkiv/publish/pub1"


def test_a_step_long_past_its_budget_is_given_up(tmp_path):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    call = _publish(rig)
    for _ in range((TIMEOUT_MS["publish"] + arkiv.GRACE_MS) // arkiv.POLL_MS):
        rig.step()                                                      # the service keeps saying "check"
    assert call.poll() == Result(ok=False, failure="ls_publish_fail")
    assert rig.sponsors.status()["board"] == "ok"


# ---- no made-up sales, honest pills, the frame never waits ---------------------------------------------------------

def test_a_real_board_never_reports_a_sale(tmp_path):
    rig = Rig(tmp_path)
    for _ in range(3):
        assert rig.sponsors.begin("sales", {"game": "marine-drive-gp"}).poll() == Result(ok=False)
    assert rig.node.queries == [] and rig.service.requests == []


def test_arkiv_is_real_world_too_hedera_still_mocked(tmp_path):
    rig = Rig(tmp_path)
    s = rig.sponsors
    assert s.mock is True                                               # Hedera: Square and Start over stay
    assert [s.mocked(x) for x in ("world", "board", "third")] == [False, False, True]
    for step in ("check_listing", "publish", "sales", "load_ghost"):
        assert s.outcomes(step) == []
    assert s.outcomes("pay") == MockSponsors(rig.clock).outcomes("pay")
    assert s.outcomes("approve") == []                                  # World's own
    assert s.names is rig.inner.names
    rig.bridge.health["approvals"] = "idkit"
    rig.inner.work()
    assert s.approvals == "idkit"                                       # what the World bridge says


def test_with_mocked_world_only_arkiv_is_real(tmp_path):
    rig = Rig(tmp_path, inner=MockSponsors(lambda: 0))
    assert [rig.sponsors.mocked(x) for x in ("world", "board", "third")] == [True, False, True]


def test_status_keeps_world_and_hedera_and_says_arkivs_own(tmp_path):
    rig = Rig(tmp_path)
    rig.inner.work()
    pay = rig.sponsors.begin("pay", {"game": "MDGP", "seller": "ANY-2KD"})
    out = rig.sponsors.status()
    assert (out["world"], out["board"], out["third"]) == ("ok", "ok", "busy")
    rig.clock.ms += 2000
    assert pay.poll().ok and rig.sponsors.status()["third"] == "ok"
    status = rig.sponsors.begin("status", {}).poll()
    assert status.ok and status.data == rig.sponsors.status()


def test_only_the_worker_talks_to_arkiv_and_the_service(tmp_path):
    rig = Rig(tmp_path)
    run = rig.node.run("ANY-2KD", 6200, listed=True)
    rig.best("MDGP", acl("6ps"), 6170)
    calls = [rig.sponsors.begin(step, payload) for step, payload in (
        ("check_listing", target_payload(rig.node, run)), ("load_ghost", target_payload(rig.node, run)),
        ("publish", LIST_PAYLOAD))]
    for _ in range(3):
        rig.sponsors.status()
        rig.sponsors.board("MDGP")
        for call in calls:
            call.poll()
            call.info
        rig.sponsors.cross(calls[0])
        rig.sponsors.cancel(calls[0])
        rig.sponsors.force(calls[0], MockSponsors(rig.clock).outcomes("check_listing")[0])
    assert rig.node.queries == [] and rig.service.requests == [] and rig.replays.calls == []
    assert all(call.poll() is None for call in calls)


def test_force_cross_and_cancel_still_reach_the_mocked_rest(tmp_path):
    rig = Rig(tmp_path)
    record = rig.sponsors.begin("record", {})
    rig.sponsors.force(record, rig.sponsors.outcomes("record")[0])
    assert record.poll() == Result(ok=False, failure="ls_record_fail")


# ---- through the flow -------------------------------------------------------------------------------------------

def _flow(rig, book="ANY-7QZ", **ctx):
    base = {"game": "MARINE DRIVE GP", "arcade_id": "MDGP", "target": "", "board_case": "ok", "best_frames": 6290,
            "run_frames": None, "run_time": "1:44.83", "other_book": "ANY-MADE", "runs": "1", "sold": 0,
            "buyer": "", "wallet": "0xDE40...0000"}
    base.update(ctx)
    return Flow(rig.sponsors, Ledger(book=book), str(rig.runs_dir + "-handler.json"), "marine-drive-gp", base,
                today=lambda: "2026-11-07")


def _wait(rig, flow, ms, frame=100):
    while ms > 0:
        rig.clock.ms += frame
        ms -= frame
        rig.sponsors.status()
        rig.sponsors.work()
        rig.inner.work()
        flow.tick(frame)


def _target_ctx(node, run):
    p = target_payload(node, run)
    return {"target": _name(run), "target_time": "1:43.33", "target_frames": p["target_frames"],
            "target_run": p["target_run"], "target_listing": p["target_listing"], "target_log_h": p["target_log_h"]}


def test_buying_a_real_target_checks_arkiv_pays_the_mock_and_loads_her_ghost(tmp_path):
    rig = Rig(tmp_path)
    log = acl("2kd")
    run = rig.node.run("ANY-2KD", 6200, log=log, listed=True)
    rig.service.ghosts[run["key"]] = log
    rig.replays.know(log, 6200)
    flow = _flow(rig, **_target_ctx(rig.node, run))
    flow.start("target")
    flow.press("cross")
    assert flow.state.name == "buy_check"
    _wait(rig, flow, 100)
    assert flow.state.name == "buy_pay"                                 # Hedera: still the mock
    _wait(rig, flow, 2000)
    assert flow.state.name == "buy_load"
    _wait(rig, flow, 100)
    assert flow.state.name == "buy_done" and flow.ctx["ghost_log"] == _ghost_file(rig, log)
    receipt = flow.ledger.purchases["marine-drive-gp:ANY-2KD"]["receipt"]
    assert rig.service.posts() == [("/arkiv/ghost", {"run": run["key"], "receipt": receipt})]


def test_a_ghost_bought_before_loads_with_its_own_receipt(tmp_path):
    rig = Rig(tmp_path)
    log = acl("2kd")
    run = rig.node.run("ANY-2KD", 6200, log=log, listed=True)
    rig.service.ghosts[run["key"]] = log
    rig.replays.know(log, 6200)
    flow = _flow(rig, **_target_ctx(rig.node, run))
    flow.ledger.purchases["marine-drive-gp:ANY-2KD"] = {"price": 10, "receipt": "mock-0badf00d", "at": 1.0}
    flow.start("target")
    flow.press("cross")
    assert flow.state.name == "buy_load"                                # owned: no check, no charge
    _wait(rig, flow, 100)
    assert flow.state.name == "buy_done"
    assert rig.service.posts() == [("/arkiv/ghost", {"run": run["key"], "receipt": "mock-0badf00d"})]


def test_a_changed_listing_says_its_new_price(tmp_path):
    rig = Rig(tmp_path)
    run = rig.node.run("ANY-2KD", 6200, listed=True, price="0.5")
    flow = _flow(rig, **_target_ctx(rig.node, run))
    flow.start("target")
    flow.press("cross")
    _wait(rig, flow, 100)
    assert flow.state.name == "buy_changed" and flow.ctx["now_price"] == "0.50 USDC"
    shown = [flow.line] + [flow.fill(t) for t in flow.state.card["rows"]]
    assert "Price was 0.10, now *0.50 USDC*" in shown and "0.50 USDC" in flow.line
    assert flow.ledger.spent == 0
    rig.node.listings.clear()
    flow.press("cross")                                                 # look again: the target, then the check
    flow.press("cross")
    _wait(rig, flow, 100)
    assert flow.state.name == "buy_changed" and flow.ctx["now_price"] == "gone"
    assert "now *gone*" in flow.fill(flow.state.card["rows"][0])


def test_listing_a_run_publishes_it_and_keeps_its_rows(tmp_path):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    flow = _flow(rig, book="ANY-6PS", best_frames=6170, run_time="1:42.83")
    flow._jti = "3f9c0a1b2c3d4e5f"                                      # World approved it, Hedera recorded it
    flow.start("ls_arkiv")
    _wait(rig, flow, 100)
    assert rig.service.posts()[0][1]["action"] == ACTION and rig.service.posts()[0][1]["jti"] == "3f9c0a1b2c3d4e5f"
    rig.service.move("done", ok=True, data=DONE)
    _wait(rig, flow, 500)
    assert flow.state.name == "ls_done"
    (entry,) = load(flow.ledger_path).listings
    assert (entry["run"], entry["listing"], entry["frames"], entry["game"]) == (DONE["run"], DONE["listing"], 6170,
                                                                                "marine-drive-gp")


@pytest.mark.parametrize("failure", PUBLISH_FAILURES)
def test_a_publish_failure_lands_on_its_screen(tmp_path, failure):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    flow = _flow(rig, book="ANY-6PS", best_frames=6170, run_time="1:42.83")
    flow._jti = "3f9c0a1b2c3d4e5f"
    flow.start("ls_arkiv")
    _wait(rig, flow, 100)
    rig.service.move("done", ok=False, failure=failure)
    _wait(rig, flow, 500)
    assert flow.state.name == failure and flow.ledger.listings == []


def test_a_slow_publish_times_out_and_cross_lists_it_on_the_same_approval(tmp_path):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    flow = _flow(rig, book="ANY-6PS", best_frames=6170, run_time="1:42.83")
    flow._jti = "3f9c0a1b2c3d4e5f"
    flow.start("ls_arkiv")
    _wait(rig, flow, 100)                                               # the run is sent
    rig.service.move("write")                                           # and the write takes longer than the budget
    _wait(rig, flow, TIMEOUT_MS["publish"] - 100)
    assert flow.state.name == "ls_publish_fail"
    rig.service.move("done", ok=True, data=DONE)
    flow.press("cross")
    _wait(rig, flow, 700)
    assert flow.state.name == "ls_done"
    assert [b["jti"] for p, b in rig.service.posts()] == ["3f9c0a1b2c3d4e5f"] * 2


def test_square_offers_no_fake_arkiv_answers(tmp_path):
    rig = Rig(tmp_path)
    run = rig.node.run("ANY-2KD", 6200, listed=True)
    flow = _flow(rig, **_target_ctx(rig.node, run))
    flow.start("buy_check")
    assert flow.mock_rows() == []
    flow.start("ls_arkiv")
    assert flow.mock_rows() == []
    flow.start("buy_pay")
    assert [o.failure for o in flow.mock_rows()] == ["buy_down", "buy_down"]   # Hedera's: still mocked
    flow.start("hub")
    assert flow.hub_rows[-1] == "Start over (mock)"


def test_a_mock_sale_from_before_is_never_told_on_a_real_board(apps, tmp_path):
    """The mock counted a sale in an earlier session and PB never told it: on a real board it stays untold."""
    from arca_launcher.handler import ledger as L
    from arca_launcher.model import Screen
    path = str(tmp_path / "handler.json")
    L.save(path, L.Ledger(book="ANY-7QZ", pending_sale={"game": "marine-drive-gp", "buyer": "ARJUN", "frames": 6100}))
    app, rig, bridge = arkiv_app(apps, tmp_path, book=None)
    app.frame(16)
    assert app.handler.pending is None and app.nav.screen is Screen.HOME
    assert L.load(path).pending_sale is not None                        # kept for a mocked run again


def test_no_sale_ever_lands_on_a_real_board(tmp_path):
    from test_handler_app import GAME, make
    old = {"game": GAME, "frames": 6100, "price": 10, "at": time.time() - 120, "sold": 0}
    app = make(tmp_path, listings=[old])
    app.sponsors = Rig(tmp_path / "arkiv").sponsors
    app.handler.game_over(None, None, True, False)                      # back Home from a game: the mock sold here
    assert app.handler.pending is None and app.handler.ledger.listings[0]["sold"] == 0
    app.close()


# ---- the glue: the launcher on a real board --------------------------------------------------------------------------

BEST = 6290                                                             # the player's best (test_handler_app's)


@pytest.fixture
def apps():
    made = []
    yield made
    for app in made:
        try:
            app.close()
        except Exception:
            pass


def arkiv_app(apps, tmp_path, book="ANY-7QZ", best=BEST, warm=False):
    """The real App (test_handler_app's library, fake bridge and runner) on ArkivSponsors over a StubNode: the same
    runs_dir for the app and the adapter, as in the launcher. The board: K2P 6000 (not listed), TEAM 6150 (open tier),
    2KD 6200 (listed: the target from a 6290 best), the console's own book at 6350 (listed), 9MX 6400 (listed)."""
    from arca_launcher.app import App, Config
    from arca_launcher.handler import ledger as L
    from test_app import FakeHw, FakeRunner
    from test_handler_app import Bridge, library, write_best
    if book:
        L.save(str(tmp_path / "handler.json"), L.Ledger(book=book))
    runs = str(tmp_path / "runs")
    if best is not None:
        write_best(runs, best)
    testlogs = tmp_path / "testlogs"
    testlogs.mkdir()
    (testlogs / "MDGP.acl").write_bytes(b"log")
    bridge = Bridge()
    bridge.runs_dir = runs
    rig = Rig(tmp_path / "arkiv", runs_dir=runs)
    log = acl("2kd")
    rig.node.run("ANY-K2P", 6000)
    rig.node.run("TEAM", 6150, book=False, plain=True)
    rig.target = rig.node.run("ANY-2KD", 6200, log=log, listed=True)
    rig.node.run("ANY-7QZ", 6350, listed=True)
    rig.node.run("ANY-9MX", 6400, listed=True)
    rig.service.ghosts[rig.target["key"]] = log
    rig.replays.know(log, 6200)
    rig.log = log
    cfg = Config(library_dir=library(tmp_path), state_path=str(tmp_path / "state.json"), splash=False,
                 run_dir=str(tmp_path / "run"), runs_dir=runs, testlogs_dir=str(testlogs), handler=True,
                 handler_warm=warm)
    app = App(cfg, runner=FakeRunner(), hw=FakeHw(), bridge=bridge, sponsors=rig.sponsors)
    apps.append(app)
    return app, rig, bridge


def _replays_of_the_test_log(bridge):
    return [c for c in bridge.calls if c[0] in ("log_time", "ghost_bytes") and c[1].endswith("testlogs/MDGP.acl")]


def test_the_hub_shows_arkivs_board_never_the_mock_runners(apps, tmp_path):
    from arca_launcher.actions import Action as A
    from arca_launcher.coach import fmt_time
    app, rig, bridge = arkiv_app(apps, tmp_path)
    rig.prefetch()
    app.frame(16, [A.Y])
    ctx = app.nav.handler.ctx
    assert [r.name for r in ctx["board_rows"]] == ["ANY-K2P", "TEAM", "ANY-2KD", "YOU", "ANY-9MX"]
    assert [r.name for r in ctx["board_rows"] if r.human] == ["ANY-K2P", "ANY-2KD", "ANY-9MX"]   # from the rows
    assert (ctx["board_case"], ctx["target"], ctx["target_time"], ctx["target_frames"]) == ("ok", "ANY-2KD",
                                                                                             fmt_time(6200), 6200)
    assert (ctx["target_run"], ctx["target_listing"], ctx["target_log_h"]) == (
        rig.target["key"], rig.node.listing_of(rig.target)["key"], sha(rig.log))
    assert (ctx["gap"], ctx["rank"], ctx["new_rank"], ctx["runs"], ctx["arcade_id"]) == ("1.5 s", "4th", "3rd", "1",
                                                                                          "MDGP")
    assert ctx["split"] == "" and _replays_of_the_test_log(bridge) == []   # no test log behind a real board


def test_before_the_first_read_there_is_no_board_then_it_arrives(apps, tmp_path):
    from arca_launcher.actions import Action as A
    app, rig, bridge = arkiv_app(apps, tmp_path)
    app.frame(16, [A.Y])
    flow = app.nav.handler
    assert (flow.ctx["board_case"], flow.ctx["board_rows"], flow.ctx["target"]) == ("no_board", (), "")
    rig.prefetch()                                                      # the worker's first read lands
    app.frame(16)
    assert flow.state.name == "hub" and flow.ctx["target"] == "ANY-2KD" and flow.ctx["board_case"] == "ok"
    app.frame(16, [A.A])
    assert flow.state.name == "board"


def _buy(app, rig):
    from arca_launcher.actions import Action as A
    app.frame(16, [A.Y])
    app.frame(16, [A.A])                                                # the board
    app.frame(16, [A.A])                                                # her run
    app.frame(16, [A.A])                                                # buy it: the listing check (Arkiv)
    flow = app.nav.handler
    assert flow.state.name == "buy_check"
    rig.sponsors.work()
    app.frame(16)
    assert flow.state.name == "buy_pay"                                 # Hedera: the mock's
    rig.clock.ms += 2000
    app.frame(16)
    assert flow.state.name == "buy_load"
    rig.sponsors.work()                                                 # her ghost from the service, checked
    app.frame(16)
    assert flow.state.name == "buy_done"
    return flow


def test_racing_a_real_target_races_her_checked_log_against_her_time(apps, tmp_path):
    from arca_launcher.actions import Action as A
    app, rig, bridge = arkiv_app(apps, tmp_path)
    rig.prefetch()
    bridge.results = [{"finished": True, "time_frames": 6150, "new_best": True},
                      {"finished": True, "time_frames": 6250, "new_best": False}]
    flow = _buy(app, rig)
    ghost_log = os.path.join(app.cfg.runs_dir, "ghosts", sha(rig.log) + ".acl")
    assert flow.ctx["ghost_log"] == ghost_log
    app.frame(16, [A.A])                                                # race her
    assert ("ghost_bytes", ghost_log) in bridge.calls and ("before", str(tmp_path / "marine-drive-gp.gba"), b"G") \
        in bridge.calls
    assert _replays_of_the_test_log(bridge) == []                       # never the test log in her place
    assert flow.state.name == "result" and flow.ctx["gap"] == "0.8 s"   # 6150 beats her 6200
    assert flow.ctx["rank"] == "4th" and flow.ctx["new_rank"] == "2nd"   # ahead of TEAM's 6150 on a tie


def test_losing_to_a_real_target_is_judged_on_her_rows_time(apps, tmp_path):
    from arca_launcher.actions import Action as A
    app, rig, bridge = arkiv_app(apps, tmp_path)
    rig.prefetch()
    bridge.results = [{"finished": True, "time_frames": 6250, "new_best": True},      # a new best, but not her
                      {"finished": True, "time_frames": 6260, "new_best": False}]
    flow = _buy(app, rig)
    app.frame(16, [A.A])
    assert flow.state.name == "race_lost" and flow.ctx["gap"] == "0.8 s"
    app.frame(16, [A.A])                                                # again: her ghost is drawn once
    assert flow.state.name == "race_lost"
    assert len([c for c in bridge.calls if c[0] == "ghost_bytes"]) == 1


def test_a_real_target_whose_log_is_not_here_is_never_raced(apps, tmp_path):
    from arca_launcher.actions import Action as A
    app, rig, bridge = arkiv_app(apps, tmp_path)
    rig.prefetch()
    flow = _buy(app, rig)
    os.remove(flow.ctx["ghost_log"])                                    # gone from the console since
    app.frame(16, [A.A])
    assert flow.state.name == "race_unfinished" and app.runner.roms == []
    assert app.nav.notice == "ANY-2KD's ghost could not be loaded"
    assert _replays_of_the_test_log(bridge) == []


def test_where_she_is_faster_waits_for_her_log(apps, tmp_path):
    from arca_launcher.actions import Action as A
    app, rig, bridge = arkiv_app(apps, tmp_path)
    rig.prefetch()
    app.frame(16, [A.Y])
    assert app.nav.handler.ctx["split"] == "" and not any(c[0] == "ghost" for c in bridge.calls)
    app.frame(16, [A.B])
    _buy(app, rig)                                                      # her log is on the console now
    app.frame(16, [A.B])                                                # the hub
    app.frame(16, [A.B])                                                # Home
    app.frame(16, [A.Y])
    app.handler.settle()
    assert sorted(c[1] for c in bridge.calls if c[0] == "ghost") == ["best", "log"]


def _a_second(app):
    from arca_launcher.app import MAX_DT
    from arca_launcher.handler_glue import BOARD_TIMES_MS
    for _ in range(BOARD_TIMES_MS // MAX_DT + 1):
        app.frame(MAX_DT)


def test_attract_mode_and_the_record_book_read_the_real_board(apps, tmp_path):
    from arca_launcher.coach import fmt_time
    from test_handler_app import GAME
    app, rig, bridge = arkiv_app(apps, tmp_path, warm=True)
    assert _replays_of_the_test_log(bridge) == []                       # no warm-up of the test logs
    assert app.nav.board_times == {}
    rig.prefetch()
    _a_second(app)
    assert app.nav.board_times == {GAME: ("ANY-2KD", fmt_time(6200))}   # the fastest run with a ghost listed
    assert app.handler._context(None)["runs"] == "1"                    # ANY-7QZ's row
    rig.node.listings.clear()
    rig.sponsors._refresh({"arcade_id": "MDGP"})
    rig.sponsors.work()
    _a_second(app)
    assert app.nav.board_times == {}                                    # nothing listed: no run to beat
    app.handler.game_over(None, None, True, False)
    assert _replays_of_the_test_log(bridge) == []


# ---- the screens ------------------------------------------------------------------------------------------------

def test_only_hedera_carries_a_mock_tag(screen, tmp_path, monkeypatch):
    from test_handler_view import show
    from test_handler_world import _drawn
    rig = Rig(tmp_path)
    drawn = _drawn(screen, monkeypatch)
    flow = _flow(rig)
    flow.start("hub")
    flow.ms_in_state = 60000
    nav, views = show(screen, flow)
    x = {s: x for s, x in reversed(drawn)}
    tags = [x for s, x in drawn if s == "MOCK"]
    assert len(tags) == 1 and x["World"] < x["Arkiv"] < x["Hedera"] < tags[0]
    squares = [h for h in views.hits if h.target == ("handler", "square")]
    assert len(squares) == 1


def test_the_real_board_draws_books_and_human_from_the_rows(screen, tmp_path, monkeypatch):
    from arca_launcher.handler.board import build_real
    from test_handler_view import show
    from test_handler_world import _drawn
    rig = Rig(tmp_path)
    for name, frames, listed in (("ANY-K2P", 6000, False), ("ANY-7QZ", 6100, True), ("TEAM", 6150, None),
                                 ("ANY-2KD", 6200, True), ("BOT-7", 6250, None), ("ANY-9MX", 6400, True)):
        rig.node.run(name, frames, listed=bool(listed), book=listed is not None, plain=listed is None)
    rig.prefetch()
    board = build_real(rig.sponsors.board("MDGP").rows, 6290, None, None)
    drawn = _drawn(screen, monkeypatch)
    flow = _flow(rig, board_rows=board.rows, board_case=board.case, target=board.target.name)
    flow.start("board")
    flow.ms_in_state = 60000
    show(screen, flow)
    from conftest import snapshot
    snapshot(screen.ren, "handler_board_arkiv")
    texts = [s for s, _ in drawn]
    assert "ANY-2KD" in texts and "TEAM" in texts and "BOT-7" in texts
    assert not {"KIRAN", "MEERA", "RIA", "ARJUN", "ZOYA", "DEV"} & set(texts)
    assert texts.count("HUMAN") == 1 + len([r for r in board.rows if r.human and texts.count(r.name)])


# ---- the real thing: a thread ----------------------------------------------------------------------------------------

class SlowNode(StubNode):
    def __call__(self, method, params, timeout_s):
        time.sleep(0.3)
        return super().__call__(method, params, timeout_s)


def test_a_slow_arkiv_never_holds_up_a_frame(tmp_path):
    rig = Rig(tmp_path)
    rig.node = SlowNode()
    run = rig.node.run("ANY-2KD", 6200, listed=True)
    sponsors = ArkivSponsors(rig.inner, "http://bridge.test:8787", rig.node, CHECKER, SEASON, rig.runs_dir,
                             rig.state_dir, lambda: int(time.monotonic() * 1000), transport=rig.service,
                             replay=rig.replays, games=("MDGP", "SHIP"))
    try:
        worst = 0.0
        call = None
        end = time.monotonic() + 3
        while time.monotonic() < end and (call is None or call.poll() is None):
            t0 = time.monotonic()
            sponsors.status()
            sponsors.board("MDGP")
            if call is None and sponsors.board("SHIP") is not None:
                call = sponsors.begin("check_listing", target_payload(rig.node, run))
            if call is not None:
                call.poll()
            worst = max(worst, time.monotonic() - t0)
            time.sleep(0.01)
        assert worst < 0.05
        assert call is not None and call.poll() == Result(ok=True, data={"price": GHOST_PRICE})
        assert [r.book for r in sponsors.board("MDGP").rows] == ["ANY-2KD"]
    finally:
        sponsors.close()
    end = time.monotonic() + 3
    while sponsors._thread.is_alive() and time.monotonic() < end:
        time.sleep(0.05)
    assert not sponsors._thread.is_alive()


# ---- wiring: --arkiv-checker / ARCA_ARKIV_CHECKER --------------------------------------------------------------------

def test_the_flags_or_the_variables_pick_arkiv(monkeypatch):
    from arca_launcher.__main__ import build_config
    for name in ("ARCA_WORLD_BRIDGE", "ARCA_ARKIV_CHECKER", "ARCA_ARKIV_RPC", "ARCA_ARKIV_SEASON"):
        monkeypatch.delenv(name, raising=False)
    cfg = build_config([])
    assert (cfg.arkiv_checker, cfg.arkiv_rpc, cfg.arkiv_season) == (None, rpc.RABDI_RPC, 1)
    cfg = build_config(["--arkiv-checker", "0x5B38Da6a701c568545dCfcB03FcB875f56beddC4", "--arkiv-season", "2",
                        "--arkiv-rpc", "http://127.0.0.1:8545"])
    assert (cfg.arkiv_checker, cfg.arkiv_rpc, cfg.arkiv_season) == (CHECKER, "http://127.0.0.1:8545", 2)
    monkeypatch.setenv("ARCA_ARKIV_CHECKER", CHECKER)
    monkeypatch.setenv("ARCA_ARKIV_SEASON", "3")
    cfg = build_config([])
    assert (cfg.arkiv_checker, cfg.arkiv_season) == (CHECKER, 3)
    with pytest.raises(SystemExit):
        build_config(["--arkiv-checker", "0x1234"])                     # a typo never runs a board pinned to nobody


def test_arkiv_is_real_only_with_the_bridge_and_the_checker(tmp_path):
    from arca_launcher.app import Config, make_sponsors
    base = dict(library_dir="/lib", state_path=str(tmp_path / "s.json"), runs_dir=str(tmp_path / "runs"))
    made = []
    try:
        s = make_sponsors(Config(**base, arkiv_checker=CHECKER))
        assert type(s) is MockSponsors                                  # no bridge: no service, every sponsor mocked
        s = make_sponsors(Config(**base, world_bridge="http://127.0.0.1:9"))
        made.append(s)
        assert type(s) is WorldSponsors and s.mocked("board")
        s = make_sponsors(Config(**base, world_bridge="http://127.0.0.1:9", arkiv_checker=CHECKER, arkiv_season=2,
                                 arkiv_rpc="http://127.0.0.1:9"), games=("MDGP",))
        made.append(s)
        assert type(s) is ArkivSponsors and not s.mocked("board") and not s.mocked("world") and s.mocked("third")
        assert s._checker == CHECKER and s._season == 2 and s._games == ("MDGP",)
        assert s._state_dir == str(tmp_path) and s._runs_dir == str(tmp_path / "runs")
    finally:
        for s in made:
            s.close()


def test_the_app_wires_the_replay_tool_and_the_library_games(tmp_path):
    from arca_launcher.app import App, Config
    from test_app import FakeHw, FakeRunner
    from test_handler_app import Bridge, library
    cfg = Config(library_dir=library(tmp_path, zip_game=True), state_path=str(tmp_path / "state.json"),
                 splash=False, run_dir=str(tmp_path / "run"), runs_dir=str(tmp_path / "runs"), handler=True,
                 world_bridge="http://127.0.0.1:9", arkiv_checker=CHECKER, arkiv_rpc="http://127.0.0.1:9")
    bridge = Bridge(log_frames=6170)
    app = App(cfg, runner=FakeRunner(), hw=FakeHw(), bridge=bridge)
    try:
        assert isinstance(app.sponsors, ArkivSponsors) and set(app.sponsors._games) == {"MDGP", "ZIPG"}
        assert app.sponsors._replay("MDGP", "/tmp/x.acl") == 6170
        assert ("log_time", "/tmp/x.acl") in bridge.calls
        assert app.sponsors._replay("NOPE", "/tmp/x.acl") is None
    finally:
        app.close()
    end = time.monotonic() + 3
    while app.sponsors._thread.is_alive() and time.monotonic() < end:
        time.sleep(0.05)
    assert not app.sponsors._thread.is_alive()
