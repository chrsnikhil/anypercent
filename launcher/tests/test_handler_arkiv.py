"""Tests for the Arkiv adapter (handler/arkiv.py): the real board, the listing check, the ghost and the listing on
Arkiv, around the World adapter; Hedera still mocked.

Most tests run the adapter with no thread, as test_handler_world.py does: a StubNode stands in for the public Arkiv
RPC (it answers only the exact query strings the readers send: the checker's stamps, then each stamped wallet's runs
and listings), a StubService for the World bridge's /arkiv/* routes (the publish job's stages, its "sign" issue and
`written`), a FakeSigner for the console's own signer, a fake clock for time, and the test calls work() (one round of
the worker) by hand. The last ones run the real thread."""
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
from arca_launcher.handler.arkiv_sign import SignError
from arca_launcher.handler.flow import Flow
from arca_launcher.handler.ledger import GHOST_PRICE, Ledger, load
from arca_launcher.handler.mock import MockSponsors
from arca_launcher.handler.sponsors import TIMEOUT_MS, BoardRead, Result
from arca_launcher.handler.world import WorldSponsors
from test_handler_world import StubBridge

CHECKER = "0x5b38da6a701c568545dcfcb03fcb875f56beddc4"
WALLET = "0x1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b9f3e"       # the consoles' wallet: it creates their runs and listings
STRANGER = "0xab8483f64d9c6d1ecf9b849ae677dd3315835cb2"
SEASON = 1
PUBLISH_FAILURES = ("ls_expired", "ls_wrong", "ls_mismatch", "ls_reused", "ls_copied", "ls_not_linked",
                    "ls_publish_fail")


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


def board_reads(game, *owners):
    """The queries one board read sends: the checker's stamps, then each stamped wallet's runs and listings."""
    out = [rpc.q_stamps(game, SEASON, CHECKER)]
    for owner in owners:
        out += [rpc.q1(game, SEASON, owner), rpc.q2(game, SEASON, owner)]
    return out


class StubNode:
    """The Rabdi node's arkiv_query in memory. It answers only the readers' exact strings: each game's stamps (pinned to
    the checker), a wallet's runs and listings of a game (pinned to it), a run by key (pinned to a wallet), a run's
    stamp and a listing by key (no pin); anything else fails the test. Only selected columns come back, as on the real
    node, and a row's current owner when the read selects it (its creator, unless the test gave the entity an
    "owner"). ignore_pin: a node that skips every `$creator` filter (look-alikes come back too); down: every request
    fails."""

    def __init__(self):
        self.runs, self.listings, self.stamps, self.queries = [], [], [], []
        self.down = False
        self.ignore_pin = False
        self.block = 0x3fe90

    def run(self, name, frames, log=None, listed=False, human=True, book=True, creator=WALLET, game="MDGP",
            price="0.1", pay_to=None, splits=None, hcs=None, stamped=True, console=None):
        """A run row created by creator's wallet (and its listing when listed), stamped by the checker naming console
        (creator by default) unless stamped is False. name: its book, or with book=False the house's BOT label.
        pay_to: the seller's Hedera account the listing names (None: a listing written without one). splits: its lap
        times (s1.., split_kind "lap"). hcs: the listing's LISTING message ("<topic>/<seq>"). Its ghost is encrypted
        (log_enc): every ghost is a listed one, served by the service."""
        log = log if log is not None else acl(name + str(frames))
        attrs = [_attr("arkiv.schema", "str", "anypercent.run"), _attr("game", "str", game),
                 _attr("title", "str", "MARINE DRIVE GP"), _attr("season", "i32", SEASON),
                 _attr("rules", "u64", "0x4"), _attr("frames", "u64", hex(frames)),
                 _attr("log_h", "str", sha(log)), _attr("runner", "str", (name.lower() * 4)[:16]),
                 _attr("human", "bool", human and book), _attr("tool", "str", "arcade_replay sha256:0123456789ab"),
                 _attr("log_enc", "bytes", "0xabcdef")]
        attrs.append(_attr("book", "str", name) if book else _attr("label", "str", name))
        if human and book:
            attrs.append(_attr("credential", "str", "Orb"))
        if splits:
            attrs += [_attr(f"s{i}", "u64", hex(lap)) for i, lap in enumerate(splits, start=1)]
            attrs.append(_attr("split_kind", "str", "lap"))
        entity = {"key": key(f"{creator}{name}{frames}"), "creator": creator, "expiresAt": "0x7a9812",
                  "attributes": attrs}
        self.runs.append(entity)
        if stamped:
            copied = [a for a in attrs if a["name"] in ("game", "season", "frames", "log_h", "book", "label", "human",
                                                         "s1", "s2", "s3", "s4", "split_kind")]
            self.stamps.append({"key": key("stamp" + entity["key"]), "creator": CHECKER, "expiresAt": "0x7a9812",
                                "attributes": [_attr("arkiv.schema", "str", "anypercent.stamp"),
                                               _attr("run", "bytes32", entity["key"]),
                                               _attr("console", "str", console or creator)] + copied})
        if listed:
            self.listings.append({"key": key("listing" + entity["key"]), "creator": creator, "expiresAt": "0x46a1d0",
                                  "attributes": [
                                      _attr("arkiv.schema", "str", "anypercent.listing"),
                                      _attr("run", "bytes32", entity["key"]), _attr("game", "str", game),
                                      _attr("season", "i32", SEASON), _attr("frames", "u64", hex(frames)),
                                      _attr("log_h", "str", sha(log)), _attr("price", "dec", price),
                                      _attr("seller", "str", (name.lower() * 4)[:16]),
                                      _attr("book" if book else "label", "str", name),
                                      _attr("human", "bool", human and book)]
                                  + ([_attr("pay_to", "str", pay_to)] if pay_to is not None else [])
                                  + ([_attr("hcs", "str", hcs)] if hcs is not None else [])})
        return entity

    def listing_of(self, run):
        return next(x for x in self.listings if _value(x, "run") == run["key"])

    def stamp_of(self, run):
        return next(x for x in self.stamps if _value(x, "run") == run["key"])

    def __call__(self, method, params, timeout_s):
        assert method == "arkiv_query" and timeout_s <= 3
        text, options = params
        self.queries.append(text)
        if self.down:
            raise urllib.error.URLError("unreachable")
        m = re.fullmatch(r"arkiv\.schema = str\('anypercent\.(stamp|run|listing)'\) AND game = str\('([A-Z0-9]{4})'\)"
                         r" AND season = i32\(1\) AND \$creator = addr\((0x[0-9a-fA-F]{40})\) ORDER BY frames:u64 ASC",
                         text)
        if m:
            kind, game, pin = m.group(1), m.group(2), m.group(3).lower()
            query = {"stamp": rpc.q_stamps, "run": rpc.q1, "listing": rpc.q2}[kind]
            assert text == query(game, SEASON, pin), text
            assert kind != "stamp" or pin == CHECKER, text
            assert options["limit"] == "0x64"
            rows = {"stamp": self.stamps, "run": self.runs, "listing": self.listings}[kind]
            hits = sorted((e for e in rows if _value(e, "game") == game and self._pinned(e, pin)),
                          key=lambda e: int(_value(e, "frames"), 16))
            return self._page(hits, options)
        m = re.fullmatch(r"arkiv\.schema = str\('anypercent\.stamp'\) AND run = key\((0x[0-9a-f]{64})\)"
                         r" AND \$creator = addr\((0x[0-9a-fA-F]{40})\)", text)
        if m:
            assert text == rpc.q_stamp_for_run(m.group(1), CHECKER), text
            return self._page([e for e in self.stamps if _value(e, "run") == m.group(1)
                               and self._pinned(e, CHECKER)], options)
        m = re.fullmatch(r"arkiv\.schema = str\('anypercent\.run'\) AND \$key = key\((0x[0-9a-f]{64})\)"
                         r" AND \$creator = addr\((0x[0-9a-fA-F]{40})\)", text)
        if m:
            pin = m.group(2).lower()
            assert text == rpc.q6(rpc.RUN_SCHEMA, m.group(1), pin), text
            return self._page([e for e in self.runs if e["key"] == m.group(1) and self._pinned(e, pin)], options)
        m = re.fullmatch(r"arkiv\.schema = str\('anypercent\.listing'\) AND \$key = key\((0x[0-9a-f]{64})\)", text)
        assert m and text == rpc.q6_listing(m.group(1)), text
        return self._page([e for e in self.listings if e["key"] == m.group(1)], options)

    def _pinned(self, entity, pin):
        return self.ignore_pin or entity["creator"] == pin

    def _page(self, entities, options):
        names = options["select"]["attributes"]
        assert "log" not in names and "log_enc" not in names              # no reader selects a ghost
        owner = {"owner": True} if options["select"].get("owner") else {}
        out = [dict({k: e[k] for k in ("key", "creator", "expiresAt")},
                    **{k: e.get("owner", e["creator"]) for k in owner},
                    attributes=[a for a in e["attributes"] if a["name"] in names]) for e in entities]
        return {"jsonrpc": "2.0", "id": 1, "result": {"data": json.loads(json.dumps(out)),
                                                      "blockNumber": hex(self.block)}}


def _value(entity, name):
    return next(a["value"] for a in entity["attributes"] if a["name"] == name)


def _name(run):
    """A run's book, or a BOT run's label."""
    return next(a["value"] for a in run["attributes"] if a["name"] in ("book", "label"))


class StubService:
    """The World bridge's /arkiv/* routes in memory. One job per jti (a repeat POST answers the same id, the job back at
    "check" unless it is done ok); the test moves the latest job with move(); `written` moves it to "write" unless
    stay_at_sign. ghosts: run key -> the plain log a listed run decrypts to, for any mock receipt of the right shape.
    down: every request fails; error: (status, failure) every request answers instead; written_error: the same for
    `written` only (a status, or an exception to raise)."""

    def __init__(self):
        self.requests, self.jobs, self.by_jti, self.ghosts = [], {}, {}, {}
        self.minted = 0
        self.down = False
        self.error = None
        self.written_error = None
        self.stay_at_sign = False
        self.config = {"chain_id": 7794095, "rpc": rpc.RABDI_RPC, "explorer": "https://rabdi.explorer.arkiv.network",
                       "checker": rpc.eip55(CHECKER), "season": SEASON,
                       "schemas": {"run": "anypercent.run", "listing": "anypercent.listing",
                                   "stamp": "anypercent.stamp"}, "price": "0.10", "listing_days": 7}

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
            if body["jti"] not in self.by_jti:                         # a new job id; a forgotten job gets another
                self.minted += 1
                self.by_jti[body["jti"]] = f"pub{self.minted}"
            jid = self.by_jti[body["jti"]]
            job = self.jobs.get(jid)
            if job is None or not (job["stage"] == "done" and job["ok"]):
                self.jobs[jid] = {"stage": "check", "ok": None, "failure": None, "data": {}}
            return {"id": jid, "expires_s": 120}
        parts = path.split("/")
        if method == "POST" and len(parts) == 5 and parts[4] == "written" and parts[3] in self.jobs:
            if isinstance(self.written_error, Exception):
                raise self.written_error
            if self.written_error is not None:
                raise urllib.error.HTTPError(path, self.written_error, "not_signing", {}, None)
            if not self.stay_at_sign:
                self.jobs[parts[3]] = {"stage": "write", "ok": None, "failure": None, "data": {}}
            return {"ok": True}
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

    def posts(self, path=None):
        return [(p, body) for method, p, body in self.requests if method == "POST" and path in (None, p)]

    def written(self):
        return [(p, body) for method, p, body in self.requests if method == "POST" and p.endswith("/written")]


class FakeSigner:
    """arkiv_sign.Signer as publish uses it: every write is recorded and answers `reply` (DONE's tx and keys; a relist
    names its run_key back), or raises `error` (a SignError)."""

    def __init__(self):
        self.calls, self.error = [], None
        self.reply = {"tx": DONE["tx"], "run": DONE["run"], "listing": DONE["listing"]}

    def write(self, key_file, rpc_url, chain_id, run, listing, timeout_s=90, run_key=None, replaces=None):
        self.calls.append({"key_file": key_file, "rpc": rpc_url, "chain_id": chain_id, "run": run, "listing": listing,
                           "timeout_s": timeout_s, "run_key": run_key, "replaces": replaces})
        if self.error is not None:
            raise self.error
        return dict(self.reply, run=run_key) if run_key else dict(self.reply)


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
        self.signer = FakeSigner()
        self.runs_dir, self.state_dir = runs_dir or str(tmp_path / "runs"), str(tmp_path / "state")
        self.bridge = StubBridge()
        self.inner = inner or WorldSponsors("http://bridge.test:8787", self.clock, transport=self.bridge,
                                            background=False)
        self.sponsors = self.make(games)

    def make(self, games=("MDGP", "SHIP")):
        return ArkivSponsors(self.inner, "http://bridge.test:8787", self.node, CHECKER, SEASON, self.runs_dir,
                             self.state_dir, self.clock, transport=self.service, background=False,
                             replay=self.replays, games=games, signer=self.signer)

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
DONE = {"run": "0x" + "12ab" * 16, "listing": "0x" + "34cd" * 16, "tx": "0x" + "9f" * 32,
        "stamp": "0x" + "56ef" * 16, "stamp_tx": "0x" + "7a" * 32}


def issue(log, frames=6170, book="ANY-6PS", price="0.1", pay_to=None, relist=False, run=None, listing=None):
    """What the bridge issues at stage "sign" for LIST_PAYLOAD's run (SpecJSON): the run (its ghost encrypted) and its
    listing, exactly as the console must find them; a relist issues the listing only, naming the stamped run's key.
    run, listing: values to change in either."""
    run_values = {"game": "MDGP", "title": "MARINE DRIVE GP", "season": SEASON, "rules": 4, "frames": frames,
                  "log_h": sha(log), "runner": "0123456789abcdef", "book": book, "human": True, "credential": "Orb",
                  "tool": "arcade_replay sha256:0123456789ab", "log_enc": {"$bytes": "q83v"}}
    listing_values = {"game": "MDGP", "season": SEASON, "frames": frames, "log_h": sha(log), "price": price,
                      "seller": "0123456789abcdef", "book": book, "human": True}
    if pay_to is not None:
        listing_values["pay_to"] = pay_to
    run_values.update(run or {})
    listing_values.update(listing or {})
    for values in (run_values, listing_values):
        for name in [name for name, value in values.items() if value is None]:
            del values[name]
    flags = {"readonly": True, "permissionlessExtension": True}
    return {"chain_id": 7794095, "rpc": rpc.RABDI_RPC,
            "run": None if relist else {"values": run_values, "flags": flags,
                                        "expiry": {"kind": "atDate", "date": {"$date": "2027-01-30T00:00:00.000Z"},
                                                   "atLeastDays": 1}},
            "run_key": DONE["run"] if relist else None,
            "listing": {"values": listing_values, "flags": {"readonly": True, "permissionlessExtension": False},
                        "expiry": {"kind": "days", "days": 7}},
            "replaces": None}


# ---- the board: read in the background, cached, never made up ------------------------------------------------------

def test_every_arcade_board_is_read_at_start_on_the_worker(tmp_path):
    rig = Rig(tmp_path)
    rig.node.run("ANY-6PS", 6170, listed=True)
    rig.node.run("BOT-A1", 6300, book=False)
    assert rig.sponsors.board("MDGP") is None                           # nothing read yet, and nothing asked here
    rig.sponsors.status()
    assert rig.node.queries == []
    rig.sponsors.work()
    assert rig.node.queries == board_reads("MDGP", WALLET)             # the stamps, then the wallet they name
    rig.sponsors.work()                                                 # one game a round: then SHIP
    assert rig.node.queries[3:] == board_reads("SHIP")                  # no stamp: nothing more to read
    read = rig.sponsors.board("MDGP")
    assert isinstance(read, BoardRead) and not read.stale and read.block == 0x3fe90
    assert [(r.book or r.label, r.frames, r.listing is not None) for r in read.rows] == [("ANY-6PS", 6170, True),
                                                                                         ("BOT-A1", 6300, False)]
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
    assert rig.node.queries[asked:] == board_reads("MDGP", WALLET)
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
    assert rig.node.queries == board_reads("SHIP")
    rig.sponsors.work()
    assert rig.node.queries[1:] == board_reads("MDGP")


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
    """The look-alike demo: a stranger's well-formed row 10 s faster, under the owner's own book. No checker stamp names
    it: a node that skipped every pin would hand it over, and the console still leaves it off. So is a stamped run that
    another wallet wrote than the one its stamp names."""
    rig = Rig(tmp_path)
    rig.node.run("ANY-6PS", 6170, listed=True)
    rig.node.run("ANY-6PS", 5570, listed=True, creator=STRANGER, stamped=False)
    rig.node.run("ANY-6PS", 5000, listed=True, creator=STRANGER, console=WALLET)
    rig.node.run("ANY-6PS", 4900, listed=True)["owner"] = STRANGER      # stamped, then given away
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
    rig.node.run("BOT-A1", 6300, book=False)
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


@pytest.mark.parametrize("change", ["checker", "season", "garbage", "a bad row", "a bad account", "before stamps"])
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
    elif change == "a bad account":
        cached["boards"]["MDGP"]["rows"][0]["pay_to"] = "0x12"
    elif change == "before stamps":
        cached["v"] = 1                                                 # the checker's own rows: they count for nothing
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
    run_reads = [rpc.q_stamp_for_run(run["key"], CHECKER), rpc.q6(rpc.RUN_SCHEMA, run["key"], WALLET)]
    assert rig.node.queries[asked:] == [rpc.q6_listing(listing["key"])] + run_reads + run_reads


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


def test_a_listing_of_another_run_than_the_boards_is_suspended(tmp_path):
    rig = Rig(tmp_path)
    run = rig.node.run("ANY-2KD", 6200, listed=True)
    payload = target_payload(rig.node, run)
    payload["target_log_h"] = sha(b"another run")
    assert _check(rig, payload) == Result(ok=False, failure="buy_suspended")


@pytest.mark.parametrize("what", ["the run gone", "the run a stranger's", "the run given away", "its stamp gone",
                                  "the listing given away"])
def test_a_listing_whose_run_does_not_count_is_gone_to_the_buyer(tmp_path, what):
    """A listing counts only for a run that counts (stamped, its owner's), and only while its owner holds it."""
    rig = Rig(tmp_path)
    run = rig.node.run("ANY-2KD", 6200, listed=True)
    payload = target_payload(rig.node, run)
    if what == "the run gone":
        rig.node.runs.clear()
    elif what == "the run a stranger's":
        run["creator"] = STRANGER
        rig.node.ignore_pin = True
    elif what == "the run given away":
        run["owner"] = STRANGER
    elif what == "its stamp gone":
        rig.node.stamps.clear()
    else:
        rig.node.listing_of(run)["owner"] = STRANGER
    assert _check(rig, payload) == Result(ok=False, failure="buy_changed", data={"now_price": "gone"}), what


def test_a_strangers_listing_of_a_stamped_run_is_gone_to_the_buyer(tmp_path):
    """A listing counts only from the run's owner: a stranger's copy (any price, any account) is never paid."""
    rig = Rig(tmp_path)
    run = rig.node.run("ANY-2KD", 6200, listed=True)
    rig.node.listing_of(run)["creator"] = STRANGER
    assert _check(rig, target_payload(rig.node, run)) == Result(ok=False, failure="buy_changed",
                                                                data={"now_price": "gone"})


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
    assert rig.node.queries[asked:] == board_reads("MDGP", WALLET)
    assert rig.sponsors.board("MDGP").rows[0].listing is None


# ---- load_ghost: from the service (listed ghosts only), checked against the stamped run ------------------------------

def _load(rig, payload):
    call = rig.sponsors.begin("load_ghost", payload)
    assert call.poll() is None
    rig.sponsors.work()
    return call.poll()


def _ghost_file(rig, log):
    return os.path.join(rig.runs_dir, "ghosts", sha(log) + ".acl")


def test_no_ghost_comes_from_a_row_and_none_of_an_unstamped_run(tmp_path):
    """The open tier is retired: no row carries a plain log to read (no reader even selects one), so a ghost comes
    only from the service, against a payment, and only for a run a checker stamp names."""
    rig = Rig(tmp_path)
    log = acl("2kd")
    run = rig.node.run("ANY-2KD", 6200, log=log)
    rig.service.ghosts[run["key"]] = log
    rig.replays.know(log, 6200)
    assert _load(rig, target_payload(rig.node, run, target_listing=None, receipt=None)).failure == "buy_load_fail"
    assert rig.node.queries == [rpc.q_stamp_for_run(run["key"], CHECKER), rpc.q6(rpc.RUN_SCHEMA, run["key"], WALLET)]
    rig.node.stamps.clear()
    assert _load(rig, target_payload(rig.node, run, target_listing=None)).failure == "buy_load_fail"
    assert rig.service.posts() == [] and not os.path.exists(_ghost_file(rig, log))


def test_a_listed_ghost_comes_from_the_service_with_the_receipt(tmp_path):
    rig = Rig(tmp_path)
    log = acl("2kd")
    run = rig.node.run("ANY-2KD", 6200, log=log, listed=True)
    rig.service.ghosts[run["key"]] = log
    rig.replays.know(log, 6200)
    result = _load(rig, target_payload(rig.node, run))
    assert result == Result(ok=True, data={"ghost_log": _ghost_file(rig, log), "replayed": 6200})
    assert rig.service.posts() == [("/arkiv/ghost", {"run": run["key"], "receipt": "mock-1a2b3c4d"})]
    with open(_ghost_file(rig, log), "rb") as f:
        assert f.read() == log
    assert rig.replays.calls == [("MDGP", sha(log) + ".acl.part")]


@pytest.mark.parametrize("what", ["another log from the service", "a replay that disagrees", "a replay that fails",
                                  "no receipt", "payment refused", "the service down", "arkiv down", "the run gone",
                                  "its stamp gone", "a short log", "not base64"])
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
    elif what == "its stamp gone":
        rig.node.stamps.clear()
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
    # Checked and replayed when it was first loaded: the row's time, said so, and no replay now.
    calls = len(rig.replays.calls)
    assert _load(rig, payload) == Result(ok=True, data={"ghost_log": _ghost_file(rig, log), "replayed": 6200,
                                                        "replay_cached": True})
    assert len(rig.replays.calls) == calls
    assert _load(rig, dict(payload, target_frames=None)) == Result(ok=True, data={"ghost_log": _ghost_file(rig, log)})
    with open(_ghost_file(rig, log), "wb") as f:                        # a file that is not that log any more
        f.write(acl("tampered"))
    assert _load(rig, payload).failure == "buy_load_fail"


def test_a_mock_target_is_still_the_mocks(tmp_path):
    rig = Rig(tmp_path)
    call = rig.sponsors.begin("load_ghost", dict(LIST_PAYLOAD, seller="RIA"))   # no target_run: the mock's ghost
    rig.clock.ms += 1200
    assert call.poll() == Result(ok=True)
    assert rig.node.queries == [] and rig.service.requests == []


# ---- publish: the service checks and issues, this console signs from its own wallet, the checker stamps -------------

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


def test_publish_names_the_account_the_approval_named(tmp_path):
    """With Hedera real the listing's payload carries the seller's account (pinned at approve_scan): the action is the
    digest World App showed with it, and the body sends it for the listing row. Anything but a plain account: none."""
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    _publish(rig, dict(LIST_PAYLOAD, pay_to="0.0.5123456"))
    body = rig.service.posts()[0][1]
    assert body["pay_to"] == "0.0.5123456"
    assert body["action"] == "List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC to 0.0.5123456 on the public board"
    for bad in (None, "0x" + "ab" * 20, "0.0.12345678901"):
        rig = Rig(tmp_path / str(bad))
        rig.best("MDGP", acl("6ps"), 6170)
        _publish(rig, dict(LIST_PAYLOAD, pay_to=bad))
        body = rig.service.posts()[0][1]
        assert "pay_to" not in body and body["action"] == ACTION, bad


def test_the_board_reads_the_account_each_listing_pays(tmp_path):
    rig = Rig(tmp_path)
    rig.node.run("ANY-6PS", 6170, listed=True, pay_to="0.0.5123456")
    rig.node.run("ANY-2KD", 6200, listed=True)                          # listed before payout accounts: none
    rig.node.run("ANY-9MX", 6250, listed=True, pay_to="0x" + "ab" * 20)  # an EVM alias: the listing is a misfit
    rig.prefetch()
    rows = rig.sponsors.board("MDGP").rows
    assert [(r.book, r.listing is not None, r.pay_to) for r in rows] == [
        ("ANY-6PS", True, "0.0.5123456"), ("ANY-2KD", True, None), ("ANY-9MX", False, None)]
    rig.node.down = True
    assert rig.make().board("MDGP").rows == rows                        # the cache keeps the accounts too


def test_a_board_cached_before_payout_accounts_still_shows(tmp_path):
    rig = Rig(tmp_path)
    rig.node.run("ANY-6PS", 6170, listed=True)
    rig.prefetch()
    path = os.path.join(rig.state_dir, arkiv.CACHE_FILE)
    with open(path, encoding="utf-8") as f:
        cached = json.load(f)
    for row in cached["boards"]["MDGP"]["rows"]:
        del row["pay_to"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cached, f)
    read = rig.make().board("MDGP")
    assert read.stale and read.rows[0].listing is not None and read.rows[0].pay_to is None


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
    {"stage": "done", "ok": True, "failure": None, "data": dict(DONE, stamp=None)},    # unstamped: on no board
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
    runs_dir for the app and the adapter, as in the launcher. The board: K2P 6000 (not listed), BOT-T1 6150 (the
    house's, not listed), 2KD 6200 (listed: the target from a 6290 best), the console's own book at 6350 (listed), 9MX
    6400 (listed)."""
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
    rig.node.run("BOT-T1", 6150, book=False)
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
    assert [r.name for r in ctx["board_rows"]] == ["ANY-K2P", "BOT-T1", "ANY-2KD", "YOU", "ANY-9MX"]
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
    assert flow.ctx["rank"] == "4th" and flow.ctx["new_rank"] == "2nd"   # ahead of BOT-T1's 6150 on a tie


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


# ---- the frame path: never the network, a hash or a decode, and cheap ------------------------------------------------
# The launcher draws at 60 fps on a Pi 3B+: whatever a frame calls on the adapter must be a read of state the worker
# prepared. These fail if a frame-side call reaches Arkiv or the service, hashes (Keccak, EIP-55), decodes a page,
# rebuilds a board nothing changed on, or simply gets slow.

FRAME_BUDGET_MS = 0.25          # mean per frame for every frame-side call together (about 0.01 ms measured)


def _full_board(rig, games=("MDGP", "SHIP")):
    """100 runs a game, a third of them listed: a full page for every read."""
    for game in games:
        for i in range(100):
            rig.node.run("ANY-%03d" % i, 6000 + 7 * i, listed=i % 3 == 0, game=game)


class Counted:
    def __init__(self, real=None):
        self.real, self.calls = real, 0

    def __call__(self, *a, **kw):
        self.calls += 1
        return self.real(*a, **kw) if self.real is not None else None


def test_frame_side_calls_only_read_prepared_state(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    _full_board(rig)
    rig.prefetch()
    run = rig.node.runs[0]
    pending = rig.sponsors.begin("check_listing", target_payload(rig.node, run))   # in flight: the worker owns it
    asked, sent = len(rig.node.queries), len(rig.service.requests)
    rpc.eip55.cache_clear()
    counters = {name: Counted(getattr(rpc, name)) for name in ("keccak256", "decode_runs", "decode_listings",
                                                               "decode_stamps", "join_board", "read_board",
                                                               "read_listing", "read_run", "read_stamp")}
    for name, counter in counters.items():
        monkeypatch.setattr(rpc, name, counter)
    frames = 2000
    t = time.perf_counter()
    for _ in range(frames):                                             # what PB's screens call each frame
        rig.sponsors.status()
        rig.sponsors.board("MDGP")
        for game in ("SHIP", "MDGP", "RUSH"):
            rig.sponsors.board(game, look=False)                        # attract mode's glance
        pending.poll()
        rig.sponsors.mocked("board")
        rig.sponsors.outcomes("pay")
        rig.sponsors.begin("sales", {}).poll()
    per_frame = (time.perf_counter() - t) * 1000 / frames
    assert {name: c.calls for name, c in counters.items()} == dict.fromkeys(counters, 0)
    assert (len(rig.node.queries), len(rig.service.requests)) == (asked, sent)
    assert per_frame < FRAME_BUDGET_MS, f"{per_frame:.3f} ms of adapter calls a frame"


def test_each_address_is_hashed_once_never_per_read(tmp_path, monkeypatch):
    """The checker and the console wallet its stamps name each go into queries in EIP-55 form: hashed once each."""
    rpc.eip55.cache_clear()
    keccak = Counted(rpc.keccak256)
    monkeypatch.setattr(rpc, "keccak256", keccak)
    rig = Rig(tmp_path)
    _full_board(rig, games=("MDGP",))
    for _ in range(5):
        rig.prefetch()
        rig.step(arkiv.REFRESH_MS)
    run = rig.node.runs[0]
    _check(rig, target_payload(rig.node, run))
    assert keccak.calls == 2


def test_a_refresh_with_nothing_new_rebuilds_and_rewrites_nothing(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    _full_board(rig, games=("MDGP",))
    rig.prefetch()
    first = rig.sponsors.board("MDGP")
    saves = Counted(rig.sponsors._save_cache)
    monkeypatch.setattr(rig.sponsors, "_save_cache", saves)
    rig.step(arkiv.REFRESH_MS)
    again = rig.sponsors.board("MDGP")
    assert again.rows is first.rows and saves.calls == 0                 # the same rows object: nothing to redo
    rig.node.run("ANY-NEW", 5000, listed=True)
    rig.step(arkiv.REFRESH_MS)
    assert rig.sponsors.board("MDGP").rows is not first.rows and saves.calls == 1
    rig.node.down = True
    rig.step(arkiv.REFRESH_MS)
    stale = rig.sponsors.board("MDGP")
    assert stale.stale and saves.calls == 1                             # an outage: marked stale, nothing written


def test_a_page_is_decoded_in_slices_that_let_the_frame_loop_in(monkeypatch):
    yields = []
    monkeypatch.setattr(rpc.time, "sleep", lambda s: yields.append(s))
    node = StubNode()
    for i in range(100):
        node.run("ANY-%03d" % i, 6000 + i, listed=True)
    rows, block, dropped = rpc.read_board(node, "MDGP", SEASON, CHECKER)
    assert len(rows) == 100 and dropped == 0
    assert yields == [0] * (3 * (99 // rpc.YIELD_EVERY))           # every 20 rows of each page: the GIL is let go


def test_the_glue_rebuilds_the_board_only_when_its_rows_change(apps, tmp_path, monkeypatch):
    from arca_launcher.actions import Action as A
    from arca_launcher.handler import board as board_module
    app, rig, bridge = arkiv_app(apps, tmp_path)
    _full_board(rig, games=("MDGP",))
    rig.prefetch()
    app.frame(16, [A.Y])
    app.frame(16, [A.A])                                                # the board screen: refreshed while looked at
    flow = app.nav.handler
    assert flow.state.name == "board" and len(flow.ctx["board_rows"]) > 100
    builds = Counted(board_module.build_real)
    monkeypatch.setattr(board_module, "build_real", builds)
    asked = len(rig.node.queries)
    frames, spent = 0, 0.0
    for refresh in range(3):                                            # three refreshes with nothing new
        rig.step(arkiv.REFRESH_MS)
        for _ in range(100):
            t = time.perf_counter()
            app.handler.frame(16)
            spent += time.perf_counter() - t
            frames += 1
    assert len(rig.node.queries) == asked + 9                           # read three times, by the worker only
    assert builds.calls == 0 and spent * 1000 / frames < FRAME_BUDGET_MS * 4
    rig.node.run("ANY-NEW", 5000, listed=True)                          # a new run: built once, then shown
    rig.step(arkiv.REFRESH_MS)
    for _ in range(50):
        app.handler.frame(16)
    assert builds.calls == 1 and flow.ctx["board_rows"][0].name == "ANY-NEW"


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
    for name, frames, listed in (("ANY-K2P", 6000, False), ("ANY-7QZ", 6100, True), ("BOT-T1", 6150, None),
                                 ("ANY-2KD", 6200, True), ("BOT-A7", 6250, None), ("ANY-9MX", 6400, True)):
        rig.node.run(name, frames, listed=bool(listed), book=listed is not None)
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
    assert "ANY-2KD" in texts and "BOT-T1" in texts and "BOT-A7" in texts
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


# ---- splits, the house's BOT ghosts, the console, the explorer -------------------------------------------------------

def test_the_board_carries_lap_times_and_bot_ghosts_and_the_cache_keeps_them(tmp_path):
    rig = Rig(tmp_path)
    rig.node.run("BOT-A2", 6236, book=False, listed=True, pay_to="0.0.7700001", splits=(2248, 1994, 1994))
    rig.node.run("ANY-6PS", 6414, listed=True, pay_to="0.0.9473064", splits=(2140, 2165, 2109))
    rig.node.run("ANY-K2P", 6500)                                       # a row from before splits
    rig.prefetch()
    rows = rig.sponsors.board("MDGP").rows
    assert [(r.book or r.label, r.human, r.splits, r.pay_to) for r in rows] == [
        ("BOT-A2", False, (2248, 1994, 1994), "0.0.7700001"), ("ANY-6PS", True, (2140, 2165, 2109), "0.0.9473064"),
        ("ANY-K2P", True, None, None)]
    rig.node.down = True
    assert rig.make().board("MDGP").rows == rows                        # the cache keeps the laps


def test_a_board_cached_before_splits_still_shows(tmp_path):
    rig = Rig(tmp_path)
    rig.node.run("ANY-6PS", 6170, listed=True)
    rig.prefetch()
    path = os.path.join(rig.state_dir, arkiv.CACHE_FILE)
    with open(path, encoding="utf-8") as f:
        cached = json.load(f)
    for row in cached["boards"]["MDGP"]["rows"]:
        del row["splits"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cached, f)
    read = rig.make().board("MDGP")
    assert read.stale and read.rows[0].splits is None and read.rows[0].book == "ANY-6PS"
    cached["boards"]["MDGP"]["rows"][0]["splits"] = [1, "x"]           # laps that do not check out: left off
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cached, f)
    assert rig.make().board("MDGP").rows[0].splits is None


def test_the_runs_log_path_is_public_for_the_scout(tmp_path):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6414)
    assert rig.sponsors.run_log_path("MDGP", 6414) == os.path.join(rig.runs_dir, "best", "MDGP.acl")
    assert rig.sponsors.run_log_path("MDGP", 6000) is None


def test_the_console_is_worlds_and_arkiv_has_no_scout_or_chain(tmp_path):
    from test_handler_world import CONSOLE, ConsoleBridge
    bridge = ConsoleBridge()
    bridge.console = {"tag": "C-7QZP", "book": "ANY-6PS", "state": "bound", "credential": "Orb"}
    world = WorldSponsors("http://bridge.test:8787", FakeClock(), transport=bridge, background=False, console=CONSOLE)
    rig = Rig(tmp_path, inner=world)
    world.work()
    assert rig.sponsors.console_id == CONSOLE and rig.sponsors.console_state()["book"] == "ANY-6PS"
    assert rig.sponsors.scouts is False and rig.sponsors.chain_update() is None
    mocked = Rig(tmp_path / "mock", inner=MockSponsors(FakeClock()))
    assert mocked.sponsors.console_id is None and mocked.sponsors.console_state() is None


def test_the_explorers_origin_comes_from_the_services_config(tmp_path):
    rig = Rig(tmp_path)
    assert rig.sponsors.explorer_origin is None                         # not asked yet: no Arkiv link is drawn
    rig.service.config.update(explorer_tx="https://rabdi.explorer.arkiv.network/tx/{tx}",
                              explorer_entity="https://rabdi.explorer.arkiv.network/entity/{key}")
    rig.prefetch()
    assert rig.sponsors.explorer_origin == "https://rabdi.explorer.arkiv.network"
    for n, odd in enumerate(({"explorer_tx": "http://plain.example/tx/{tx}"}, {"explorer_tx": "javascript:alert(1)"},
                             {"explorer_tx": None}, {"explorer_tx": "https://a.example/tx/{tx}",
                                                     "explorer_entity": "https://b.example/entity/{key}"})):
        rig = Rig(tmp_path / str(n))
        rig.service.config.update(dict({"explorer_entity": None}, **odd))
        rig.prefetch()
        assert rig.sponsors.explorer_origin is None, odd


def test_a_listing_names_its_explorer_links(tmp_path):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    call = _publish(rig)
    links = {"tx": "https://rabdi.explorer.arkiv.network/tx/" + DONE["tx"],
             "run": "https://rabdi.explorer.arkiv.network/entity/" + DONE["run"],
             "listing": "https://rabdi.explorer.arkiv.network/entity/" + DONE["listing"],
             "stamp": "https://rabdi.explorer.arkiv.network/entity/" + DONE["stamp"],
             "stamp_tx": "https://rabdi.explorer.arkiv.network/tx/" + DONE["stamp_tx"]}
    rig.service.move("done", ok=True, data=dict(DONE, explorer=dict(links, extra="never passed on")))
    rig.step()
    assert call.poll() == Result(ok=True, data=dict(DONE, explorer=links))
    rig = Rig(tmp_path / "odd")
    rig.best("MDGP", acl("6ps"), 6170)
    call = _publish(rig)
    rig.service.move("done", ok=True, data=dict(DONE, explorer={"tx": 7, "run": "x" * 600, "listing": None,
                                                                "stamp": "http://plain.example/x"}))
    rig.step()
    assert call.poll() == Result(ok=True, data=DONE)                     # nothing it can not draw


# ---- what the replays gave: the checker's (publish), this console's (load_ghost) -------------------------------------

REPLAY = {"frames": 6170, "final_hash": 576543229}


def test_a_listing_says_what_the_checkers_replay_gave(tmp_path):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    call = _publish(rig)
    rig.service.move("done", ok=True, data=dict(DONE, replay=dict(REPLAY, extra="never passed on")))
    rig.step()
    assert call.poll() == Result(ok=True, data=dict(DONE, replay=REPLAY))
    for n, odd in enumerate(({"frames": 0, "final_hash": 1}, {"frames": "6170", "final_hash": 1},
                             {"frames": True, "final_hash": 1}, {"frames": 6170, "final_hash": -1},
                             {"frames": 6170, "final_hash": 2 ** 32}, {"frames": 6170, "final_hash": None},
                             {"frames": 6170, "final_hash": "1a2b3c4d"}, {"frames": 6170, "final_hash": True},
                             {"frames": 6170}, "6170", None)):
        rig = Rig(tmp_path / str(n))
        rig.best("MDGP", acl("6ps"), 6170)
        call = _publish(rig)
        rig.service.move("done", ok=True, data=dict(DONE, replay=odd))
        rig.step()
        assert call.poll() == Result(ok=True, data=DONE), odd           # nothing it can not show
    rig = Rig(tmp_path / "edge")
    rig.best("MDGP", acl("6ps"), 6170)
    call = _publish(rig)
    rig.service.move("done", ok=True, data=dict(DONE, replay={"frames": 1, "final_hash": 2 ** 32 - 1}))
    rig.step()
    assert call.poll().data["replay"] == {"frames": 1, "final_hash": 2 ** 32 - 1}


def _explorer_rig(tmp_path, **config):
    rig = Rig(tmp_path)
    rig.service.config.update(explorer_tx="https://rabdi.explorer.arkiv.network/tx/{tx}",
                              explorer_entity="https://rabdi.explorer.arkiv.network/entity/{key}")
    rig.service.config.update(config)
    rig.prefetch()
    return rig


def test_a_loaded_ghost_names_its_runs_explorer_link_as_the_service_builds_it(tmp_path):
    rig = _explorer_rig(tmp_path)
    log = acl("2kd")
    run = rig.node.run("ANY-2KD", 6200, log=log, listed=True)
    rig.service.ghosts[run["key"]] = log
    rig.replays.know(log, 6200)
    payload = target_payload(rig.node, run)
    link = "https://rabdi.explorer.arkiv.network/entity/" + run["key"].lower()
    assert _load(rig, payload) == Result(ok=True, data={"ghost_log": _ghost_file(rig, log), "replayed": 6200,
                                                        "explorer": {"run": link}})
    assert _load(rig, payload).data == {"ghost_log": _ghost_file(rig, log), "replayed": 6200, "replay_cached": True,
                                        "explorer": {"run": link}}
    assert _load(rig, dict(payload, target_run=payload["target_run"].upper().replace("0X", "0x"))).data[
        "explorer"] == {"run": link}                                     # the key as the explorer names it


@pytest.mark.parametrize("config", [{}, {"explorer_entity": None},
                                    {"explorer_entity": "https://rabdi.explorer.arkiv.network/entity/"},
                                    {"explorer_entity": "https://elsewhere.example/entity/{key}"},
                                    {"explorer_entity": "http://rabdi.explorer.arkiv.network/entity/{key}"}])
def test_no_run_link_unless_the_template_is_on_the_allowed_explorer(tmp_path, config):
    rig = _explorer_rig(tmp_path, **config) if config else Rig(tmp_path)   # {}: /arkiv/config never read
    log = acl("2kd")
    run = rig.node.run("ANY-2KD", 6200, log=log, listed=True)
    rig.service.ghosts[run["key"]] = log
    rig.replays.know(log, 6200)
    result = _load(rig, target_payload(rig.node, run))
    assert result.ok and "explorer" not in result.data, config
    assert rig.sponsors.entity_link(run["key"]) is None, config        # nor any row's (the board's own links)


# ---- a board run's records: its listing's Hedera message, any row's explorer link -----------------------------------

def test_a_listing_names_its_hedera_message_and_the_cache_keeps_it(tmp_path):
    rig = Rig(tmp_path)
    rig.node.run("BOT-A2", 6236, book=False, listed=True, pay_to="0.0.7700001", hcs="0.0.11332437/41")
    rig.node.run("ANY-6PS", 6414, listed=True, pay_to="0.0.9473064")    # listed before the message was kept: none
    rig.node.run("ANY-K2P", 6500, listed=True, hcs="0.0.11332437")       # not "<topic>/<seq>": left off, still listed
    rig.prefetch()
    rows = rig.sponsors.board("MDGP").rows
    assert [(r.book or r.label, r.listing is not None, r.hcs) for r in rows] == [
        ("BOT-A2", True, "0.0.11332437/41"), ("ANY-6PS", True, None), ("ANY-K2P", True, None)]
    rig.node.down = True
    assert rig.make().board("MDGP").rows == rows                        # the cache keeps it
    path = os.path.join(rig.state_dir, arkiv.CACHE_FILE)
    with open(path, encoding="utf-8") as f:
        cached = json.load(f)
    for row in cached["boards"]["MDGP"]["rows"]:
        del row["hcs"]                                                  # a cache written before it
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cached, f)
    read = rig.make().board("MDGP")
    assert read.stale and [r.hcs for r in read.rows] == [None, None, None] and read.rows[0].listing is not None
    cached["boards"]["MDGP"]["rows"][0]["hcs"] = "0.0.11332437"         # not one the board would have read
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cached, f)
    assert rig.make().board("MDGP") is None


def test_any_rows_explorer_link_is_built_as_the_service_builds_it(tmp_path):
    run = key("ANY-6PS run")
    assert Rig(tmp_path).sponsors.entity_link(run) is None              # /arkiv/config not read yet
    rig = _explorer_rig(tmp_path / "config")
    link = "https://rabdi.explorer.arkiv.network/entity/" + run
    assert rig.sponsors.entity_link(run) == link
    assert rig.sponsors.entity_link(run.upper().replace("0X", "0x")) == link   # the key as the explorer names it
    for odd in (None, "", 7, "0x12", run + "00", "../" + run, run[2:]):
        assert rig.sponsors.entity_link(odd) is None, odd


# ---- the console signs its own records: the sign stage, `written`, the stamp -----------------------------------------

def _signing(rig, log=None, payload=LIST_PAYLOAD, **issued):
    """A publish of LIST_PAYLOAD's run (its log the best on this console, its replay known) up to the sign stage: the
    start is sent, then the service issues (issue(log, **issued)) and the next round signs."""
    log = log if log is not None else acl("6ps")
    rig.best("MDGP", log, 6170)
    rig.replays.know(log, 6170)
    call = _publish(rig, payload)
    rig.service.move("sign", data={"issue": issue(log, **issued)})
    return call, log


def test_the_console_signs_what_was_issued_tells_the_service_and_lists_it_stamped(tmp_path):
    rig = Rig(tmp_path)
    call, log = _signing(rig)
    rig.step()
    (signed,) = rig.signer.calls
    sent = issue(log)
    assert signed == {"key_file": os.path.join(rig.state_dir, "arkiv-key"), "rpc": sent["rpc"],
                      "chain_id": sent["chain_id"], "run": sent["run"], "listing": sent["listing"],
                      "timeout_s": arkiv.SIGN_TIMEOUT_S, "run_key": None, "replaces": None}
    assert os.path.isfile(signed["key_file"])                           # made on this console, never sent anywhere
    assert rig.service.written() == [("/arkiv/publish/pub1/written",
                                      {"tx": DONE["tx"], "run": DONE["run"], "listing": DONE["listing"]})]
    assert call.poll() is None and rig.sponsors.status()["board"] == "busy"
    rig.service.move("done", ok=True, data=DONE)
    rig.step()
    assert call.poll() == Result(ok=True, data=DONE)
    assert call.poll().data["stamp"] == DONE["stamp"] and call.poll().data["stamp_tx"] == DONE["stamp_tx"]
    assert len(rig.signer.calls) == 1 and len(rig.service.written()) == 1
    assert rig.replays.calls == [("MDGP", "MDGP.acl")]                  # its own replay of its own log, once
    body = [b for p, b in rig.service.posts("/arkiv/publish")][0]
    assert "arkiv-key" not in json.dumps(body)                          # the key never leaves the console


def test_every_look_at_the_sign_stage_repeats_the_issue_and_it_is_signed_once(tmp_path):
    """The service keeps one job id per approval: a job this console wrote for that comes back at "sign" (the
    service did not find the records yet, or issued afresh) is told again with the same transaction and keys, never
    signed again, never left to run out its budget."""
    rig = Rig(tmp_path)
    rig.service.stay_at_sign = True                                     # the service has not moved on yet
    call, _ = _signing(rig)
    for _ in range(6):
        rig.step()
    assert len(rig.signer.calls) == 1 and len(rig.service.written()) >= 2
    assert {json.dumps(body, sort_keys=True) for _, body in rig.service.written()} == {
        json.dumps({"tx": DONE["tx"], "run": DONE["run"], "listing": DONE["listing"]}, sort_keys=True)}
    assert call.poll() is None
    rig.service.move("done", ok=True, data=DONE)
    rig.step()
    assert call.poll().ok and len(rig.signer.calls) == 1


@pytest.mark.parametrize("what, issued", [
    ("another log", {"run": {"log_h": sha(b"someone else's run")}}),
    ("another log on the listing", {"listing": {"log_h": sha(b"someone else's run")}}),
    ("another game", {"run": {"game": "SHIP"}}),
    ("another book", {"book": "ANY-9MX"}),
    ("a label", {"run": {"book": None, "label": "BOT-A1"}}),
    ("other frames", {"frames": 6100}),
    ("frames as text", {"run": {"frames": "6170"}}),
    ("another price", {"price": "0.5"}),
    ("a price that is not one", {"price": "ten"}),
    ("a payout account nobody approved", {"pay_to": "0.0.6666666"}),
    ("its ghost in the clear", {"run": {"log": {"$bytes": "QUNMMQ=="}}}),
    ("a run with no game", {"run": {"game": None}}),
])
def test_an_issue_that_is_not_what_this_console_knows_is_never_signed(tmp_path, what, issued):
    rig = Rig(tmp_path)
    call, _ = _signing(rig, **issued)
    rig.step()
    assert call.poll() == Result(ok=False, failure="ls_publish_fail"), what
    assert rig.signer.calls == [] and rig.service.written() == []


def test_a_run_this_consoles_replay_times_otherwise_is_never_signed(tmp_path):
    rig = Rig(tmp_path)
    call, log = _signing(rig)
    rig.replays.know(log, 6171)                                         # the console's own replay disagrees
    rig.step()
    assert call.poll() == Result(ok=False, failure="ls_publish_fail") and rig.signer.calls == []
    rig = Rig(tmp_path / "unfinished")
    call, log = _signing(rig)
    rig.replays.times.clear()                                           # the tool is there and says unfinished
    rig.step()
    assert call.poll() == Result(ok=False, failure="ls_publish_fail") and rig.signer.calls == []


def test_without_a_replay_tool_the_frames_asked_are_checked(tmp_path):
    rig = Rig(tmp_path)
    rig.sponsors._replay = None
    call, _ = _signing(rig)
    rig.step()
    assert len(rig.signer.calls) == 1 and call.poll() is None
    rig = Rig(tmp_path / "other")
    rig.sponsors._replay = None
    call, _ = _signing(rig, frames=6100)
    rig.step()
    assert call.poll().failure == "ls_publish_fail" and rig.signer.calls == []


def test_the_approved_payout_account_is_the_listings(tmp_path):
    rig = Rig(tmp_path)
    call, _ = _signing(rig, payload=dict(LIST_PAYLOAD, pay_to="0.0.5123456"), pay_to="0.0.5123456")
    rig.step()
    assert len(rig.signer.calls) == 1
    rig = Rig(tmp_path / "none")
    call, _ = _signing(rig, payload=dict(LIST_PAYLOAD, pay_to="0.0.5123456"))     # the approval named one: missing
    rig.step()
    assert call.poll().failure == "ls_publish_fail" and rig.signer.calls == []


@pytest.mark.parametrize("kind, failure", [("unfunded", "ls_unfunded"), ("no_node", "ls_publish_fail"),
                                           ("no_key", "ls_publish_fail"), ("rpc", "ls_publish_fail"),
                                           ("rejected", "ls_publish_fail"), ("bad_reply", "ls_publish_fail")])
def test_each_signer_failure_is_a_screen_and_nothing_is_told(tmp_path, kind, failure):
    rig = Rig(tmp_path)
    rig.signer.error = SignError(kind, "detail", tx="0x" + "ab" * 32 if kind == "rejected" else None)
    call, _ = _signing(rig)
    rig.step()
    assert call.poll() == Result(ok=False, failure=failure)
    assert rig.service.written() == [] and rig.sponsors.status()["board"] == "ok"


def test_an_unfunded_wallet_lists_on_the_same_approval_once_funded(tmp_path):
    """ls_unfunded, then Cross (the flow begins publish again with the same payload): the same jti goes to the service,
    which issues again, and this time the funded wallet signs."""
    rig = Rig(tmp_path)
    rig.signer.error = SignError("unfunded", "balance 0")
    call, log = _signing(rig)
    rig.step()
    assert call.poll().failure == "ls_unfunded"
    rig.signer.error = None                                             # the owner ran npm run arkiv:fund
    again = _publish(rig)
    assert [b["jti"] for p, b in rig.service.posts("/arkiv/publish")] == ["3f9c0a1b2c3d4e5f"] * 2
    rig.service.move("sign", data={"issue": issue(log)})
    rig.step()
    rig.service.move("done", ok=True, data=DONE)
    rig.step()
    assert again.poll() == Result(ok=True, data=DONE) and len(rig.signer.calls) == 2


def test_without_node_the_listing_fails_and_the_board_still_reads(tmp_path):
    """Review Focus 4: the real Signer with no Node binary on the console is ls_publish_fail, never a crash, and the
    board reads on."""
    from arca_launcher.handler.arkiv_sign import Signer
    rig = Rig(tmp_path)
    rig.signer = Signer(node=str(tmp_path / "no-node-here"))
    rig.sponsors = rig.make()
    rig.node.run("ANY-K2P", 6000, listed=True)
    call, _ = _signing(rig)
    rig.step()
    assert call.poll() == Result(ok=False, failure="ls_publish_fail") and rig.service.written() == []
    rig.sponsors.board("MDGP")
    rig.step(arkiv.REFRESH_MS)
    assert [r.book for r in rig.sponsors.board("MDGP").rows] == ["ANY-K2P"]
    assert rig.sponsors.status()["board"] == "ok"


def test_a_written_the_service_did_not_hear_is_told_again_and_a_refusal_is_not_listed(tmp_path):
    rig = Rig(tmp_path)
    rig.service.written_error = urllib.error.URLError("blip")
    call, _ = _signing(rig)
    rig.step()
    assert len(rig.signer.calls) == 1 and call.poll() is None
    rig.service.written_error = None
    rig.step()
    assert len(rig.service.written()) == 2 and len(rig.signer.calls) == 1     # told again, never signed again
    rig.service.move("done", ok=True, data=DONE)
    rig.step()
    assert call.poll().ok
    rig = Rig(tmp_path / "refused")
    rig.service.written_error = 400
    call, _ = _signing(rig)
    rig.step()
    assert call.poll() == Result(ok=False, failure="ls_publish_fail")


def test_a_written_answered_not_now_waits_for_the_next_sign_and_is_told_again_then(tmp_path):
    """409 on `written`: the job is running again under its id (Cross after an unheard `written`). Not a failure:
    the console polls on, and tells again only when the job is back at "sign"."""
    rig = Rig(tmp_path)
    rig.service.written_error = 409
    call, log = _signing(rig)
    rig.step()
    assert call.poll() is None and len(rig.service.written()) == 1
    rig.service.move("check")
    for _ in range(4):
        rig.step()
    assert call.poll() is None and len(rig.service.written()) == 1      # not told while it runs
    rig.service.written_error = None
    rig.service.move("sign", data={"issue": issue(log)})                 # it issued afresh: the same records again
    rig.step()
    rig.step()
    assert len(rig.service.written()) == 2 and len(rig.signer.calls) == 1
    rig.service.move("done", ok=True, data=DONE)
    rig.step()
    assert call.poll() == Result(ok=True, data=DONE)


def test_a_failed_done_after_a_not_now_is_told_once_more_then_it_is_a_failure(tmp_path):
    rig = Rig(tmp_path)
    rig.service.written_error = 409
    call, _ = _signing(rig)
    rig.step()
    rig.service.written_error = None
    rig.service.move("done", ok=False, failure="ls_publish_fail")
    rig.step()
    rig.step()
    assert call.poll() is None and len(rig.service.written()) == 2      # its records exist: the service may stamp them
    rig.service.move("done", ok=False, failure="ls_publish_fail")
    rig.step()
    assert call.poll() == Result(ok=False, failure="ls_publish_fail") and len(rig.service.written()) == 2


def test_a_job_the_service_forgot_is_started_again_with_the_same_approval(tmp_path):
    """The service holds a job an hour: a 404 starts it again with the same jti under a new id. What this console's
    wallet wrote stays with the job: the service either finds those records and stamps them (its done has no tx: the
    console's own fills in), or issues again, and then `written` names them, with no second signature."""
    rig = Rig(tmp_path)
    call, log = _signing(rig)
    rig.step()
    del rig.service.jobs["pub1"]                                        # pruned: a new job, a new id
    del rig.service.by_jti["3f9c0a1b2c3d4e5f"]
    rig.step()
    rig.step()
    assert [b["jti"] for p, b in rig.service.posts("/arkiv/publish")] == ["3f9c0a1b2c3d4e5f"] * 2
    rig.service.move("done", ok=True, data=dict(DONE, tx=None))         # found on Arkiv before it was told
    rig.step()
    assert call.poll() == Result(ok=True, data=DONE)                    # the tx this console sent, all the same
    assert len(rig.signer.calls) == 1
    rig = Rig(tmp_path / "issued")
    call, log = _signing(rig)
    rig.step()
    del rig.service.jobs["pub1"]
    del rig.service.by_jti["3f9c0a1b2c3d4e5f"]
    rig.step()
    rig.step()
    rig.service.move("sign", data={"issue": issue(log)})                 # the new job issues again
    rig.step()
    rig.step()
    told = {"tx": DONE["tx"], "run": DONE["run"], "listing": DONE["listing"]}
    assert rig.service.written()[-1] == ("/arkiv/publish/pub2/written", told) and len(rig.signer.calls) == 1


def test_a_done_without_this_consoles_tx_still_lists_with_what_it_knows(tmp_path):
    rig = Rig(tmp_path)
    rig.best("MDGP", acl("6ps"), 6170)
    call = _publish(rig)
    rig.service.move("done", ok=True, data=dict(DONE, tx=None, stamp_tx=None))
    rig.step()
    assert call.poll() == Result(ok=True, data={"run": DONE["run"], "listing": DONE["listing"],
                                                "stamp": DONE["stamp"]})


def _relist_rig(tmp_path, wallet=WALLET):
    """A console whose wallet World knows, with its own stamped run of LIST_PAYLOAD's log and that run's listing on
    the board: (rig, the run, its listing)."""
    world = WorldSponsors("http://bridge.test:8787", FakeClock(), transport=StubBridge(), background=False,
                          wallet=wallet)
    rig = Rig(tmp_path, inner=world)
    run = rig.node.run("ANY-6PS", 6170, log=acl("6ps"), listed=True)
    return rig, run, rig.node.listing_of(run)


def _relisting(rig, run, replaces):
    call, log = _signing(rig, relist=True)
    sent = dict(issue(log, relist=True), run_key=run["key"], replaces=replaces)
    rig.service.move("sign", data={"issue": sent})
    rig.step()
    return call, sent


def test_a_relist_signs_the_listing_only_and_names_the_stamped_run(tmp_path):
    rig, run, old = _relist_rig(tmp_path)
    call, sent = _relisting(rig, run, old["key"])
    (signed,) = rig.signer.calls
    assert signed["run"] is None and signed["run_key"] == run["key"] and signed["replaces"] == old["key"]
    assert signed["listing"] == sent["listing"]
    assert rig.service.written() == [("/arkiv/publish/pub1/written",
                                      {"tx": DONE["tx"], "run": run["key"], "listing": DONE["listing"]})]
    rig, run, old = _relist_rig(tmp_path / "nothing to replace")
    _relisting(rig, run, None)
    assert len(rig.signer.calls) == 1
    rig = Rig(tmp_path / "keyless")
    bad = issue(acl("6ps"), relist=True)
    bad["run_key"] = "0x12"
    call, _ = _signing(rig, relist=True)
    rig.service.move("sign", data={"issue": bad})
    rig.step()
    assert call.poll().failure == "ls_publish_fail" and rig.signer.calls == []


@pytest.mark.parametrize("pending", [True, False])
def test_a_console_whose_wallet_waits_on_a_new_link_lists_nothing(tmp_path, pending):
    """Task 1's review: the binding says wallet_pending (this console's wallet is not the one World linked to the
    book): ls_not_linked before the service is asked, since the checker would never stamp what it writes."""
    from test_handler_world import CONSOLE, ConsoleBridge
    bridge = ConsoleBridge()
    bridge.console = {"tag": "C-7QZP", "book": "ANY-6PS", "state": "bound", "credential": "Orb",
                      "wallet": None if pending else WALLET, "wallet_pending": pending}
    world = WorldSponsors("http://bridge.test:8787", FakeClock(), transport=bridge, background=False, console=CONSOLE,
                          wallet=WALLET)
    world.work()
    rig = Rig(tmp_path, inner=world)
    rig.best("MDGP", acl("6ps"), 6170)
    call = _publish(rig)
    if pending:
        assert call.poll() == Result(ok=False, failure="ls_not_linked") and rig.service.requests == []
    else:
        assert call.poll() is None and rig.service.posts("/arkiv/publish")
    assert rig.sponsors.arkiv_wallet == WALLET


@pytest.mark.parametrize("change", [{"chain_id": "7794095"}, {"rpc": None}, {"listing": None}])
def test_an_issue_with_no_chain_or_no_listing_is_never_signed(tmp_path, change):
    rig = Rig(tmp_path)
    call, log = _signing(rig)
    rig.service.move("sign", data={"issue": dict(issue(log), **change)})
    rig.step()
    assert call.poll() == Result(ok=False, failure="ls_publish_fail") and rig.signer.calls == []


@pytest.mark.parametrize("what", ["a stranger's listing", "a listing of another run", "a listing of another log",
                                  "a listing given away", "not a listing", "a run stamped to another wallet",
                                  "a run with no stamp", "a run of another log", "the wallet not known", "arkiv down"])
def test_a_relist_never_deletes_or_relists_what_is_not_this_wallets(tmp_path, what):
    """Spec Goal 5: a relist deletes `replaces` in the console's own transaction, so before signing the console reads
    it and the run from Arkiv: the run must be stamped as this wallet's run of this log, and `replaces` this wallet's
    listing of that run. The service can never make this wallet delete a record of its choosing."""
    rig, run, old = _relist_rig(tmp_path, wallet=None if what == "the wallet not known" else WALLET)
    replaces = old["key"]
    if what == "a stranger's listing":
        replaces = rig.node.listing_of(rig.node.run("ANY-6PS", 6100, listed=True, creator=STRANGER))["key"]
    elif what == "a listing of another run":
        replaces = rig.node.listing_of(rig.node.run("ANY-6PS", 6300, listed=True))["key"]
    elif what == "a listing of another log":
        for a in old["attributes"]:
            if a["name"] == "log_h":
                a["value"] = sha(b"another log")
    elif what == "a listing given away":
        old["owner"] = STRANGER
    elif what == "not a listing":
        replaces = run["key"]                                            # its own run: never deleted
    elif what == "a run stamped to another wallet":
        for a in rig.node.stamp_of(run)["attributes"]:
            if a["name"] == "console":
                a["value"] = STRANGER
    elif what == "a run with no stamp":
        rig.node.stamps.clear()
    elif what == "a run of another log":
        run = rig.node.run("ANY-6PS", 6180, log=acl("someone else's"))   # this wallet's, stamped, another log
    call, log = _signing(rig, relist=True)
    sent = dict(issue(log, relist=True), run_key=run["key"], replaces=replaces)
    rig.service.move("sign", data={"issue": sent})
    rig.node.down = what == "arkiv down"
    rig.step()
    assert call.poll() == Result(ok=False, failure="ls_publish_fail"), what
    assert rig.signer.calls == []


RABDI_HOST = "rpc.rabdi.db-chain.testnet.arkiv.network"


@pytest.mark.parametrize("change", [{"chain_id": 1}, {"chain_id": 7794096}, {"rpc": "http://" + RABDI_HOST},
                                    {"rpc": "https://evil.example/rpc"}, {"rpc": f"https://{RABDI_HOST}.evil.example"},
                                    {"rpc": "not a url"}])
def test_the_console_signs_only_for_rabdi_on_the_configured_rpc_host(tmp_path, change):
    rig = Rig(tmp_path)
    call, log = _signing(rig)
    rig.service.move("sign", data={"issue": dict(issue(log), **change)})
    rig.step()
    assert call.poll() == Result(ok=False, failure="ls_publish_fail") and rig.signer.calls == []
    rig = Rig(tmp_path / "keyed")
    call, log = _signing(rig)
    keyed = dict(issue(log), rpc=rpc.RABDI_RPC + "/some/path?key=x")     # the same host: taken
    rig.service.move("sign", data={"issue": keyed})
    rig.step()
    assert len(rig.signer.calls) == 1 and rig.signer.calls[0]["rpc"] == keyed["rpc"]


def test_the_signer_never_gets_more_time_than_the_publish_has_left(tmp_path):
    rig = Rig(tmp_path)
    call, _ = _signing(rig)
    rig.clock.ms += TIMEOUT_MS["publish"] - 50000                       # 50 s of the budget left
    rig.step()
    assert rig.signer.calls[0]["timeout_s"] == pytest.approx(50 - arkiv.POLL_MS / 1000)
    rig = Rig(tmp_path / "late")
    call, _ = _signing(rig)
    rig.clock.ms += TIMEOUT_MS["publish"] - arkiv.SIGN_MIN_S * 1000 + 1000     # under 30 s left: not signed
    rig.step()
    assert call.poll() == Result(ok=False, failure="ls_publish_fail") and rig.signer.calls == []
    rig = Rig(tmp_path / "early")
    call, _ = _signing(rig)
    rig.step()
    assert rig.signer.calls[0]["timeout_s"] == arkiv.SIGN_TIMEOUT_S
