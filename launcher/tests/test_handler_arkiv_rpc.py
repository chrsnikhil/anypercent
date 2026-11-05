"""Tests for the Arkiv reader (handler/arkiv_rpc.py): the spec's exact Q1, Q2 and Q6 strings, the JSON-RPC request,
and the decoding and validation of raw rows. A stub stands in for the node; the last tests use a local HTTP server.

The fixtures (tests/fixtures/arkiv_q*_mdgp.json) are raw replies in the live Rabdi node's shape (key, creator,
expiresAt, attributes [{name, type, value}]). Among the rows: a look-alike written by another wallet (the board must
ignore it), a row of another schema, and a misfit whose u64 is a bare number."""
import copy
import hashlib
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from arca_launcher.handler import arkiv_rpc as rpc
from arca_launcher.handler.sponsors import RunRow

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
CHECKER = "0x5b38da6a701c568545dcfcb03fcb875f56beddc4"
STRANGER = "0xab8483f64d9c6d1ecf9b849ae677dd3315835cb2"


def h(name):
    return hashlib.sha256(name.encode()).hexdigest()


def k(name):
    return "0x" + h("key:" + name)


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


Q1_PAGE, Q2_PAGE = fixture("arkiv_q1_mdgp.json"), fixture("arkiv_q2_mdgp.json")


class StubRpc:
    """arkiv_query in memory: replies[i] answers the i-th request (a dict, or an exception to raise)."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, method, params, timeout_s):
        self.requests.append((method, params, timeout_s))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return copy.deepcopy(reply)


def page(*entities, block="0x3fe90"):
    return {"jsonrpc": "2.0", "id": 1, "result": {"data": list(entities), "blockNumber": block}}


def entities(reply):
    return copy.deepcopy(reply["result"]["data"])


# ---- the query strings: the spec's, character for character -----------------------------------------------------

C55 = "0x5B38Da6a701c568545dCfcB03FcB875f56beddC4"                      # CHECKER in its EIP-55 form


def test_the_board_queries_are_the_specs():
    """Q1 and Q2, to the character as the service and the web board write them (the checker in its EIP-55 form)."""
    assert rpc.q1("MDGP", 1, CHECKER) == (
        "arkiv.schema = str('anypercent.run') AND game = str('MDGP') AND season = i32(1) AND $creator = addr("
        "0x5B38Da6a701c568545dCfcB03FcB875f56beddC4) ORDER BY frames:u64 ASC")
    assert rpc.q2("SHIP", 3, CHECKER) == (
        "arkiv.schema = str('anypercent.listing') AND game = str('SHIP') AND season = i32(3) AND $creator = addr("
        "0x5B38Da6a701c568545dCfcB03FcB875f56beddC4) ORDER BY frames:u64 ASC")
    template = ("arkiv.schema = str('anypercent.run') AND game = str('${game}') AND season = i32(${season}) AND "
                "$creator = addr(${checker}) ORDER BY frames:u64 ASC")      # Part A's Q1_TEMPLATE
    assert rpc.q1("ZIPG", 7, CHECKER) == template.replace("${game}", "ZIPG").replace("${season}", "7").replace(
        "${checker}", C55)


def test_the_lookups_by_key_are_the_specs():
    key = k("6ps-fast")
    assert rpc.q6(rpc.LISTING_SCHEMA, key, CHECKER) == (
        f"arkiv.schema = str('anypercent.listing') AND $key = key({key}) AND $creator = addr({C55})")
    assert rpc.q6(rpc.RUN_SCHEMA, key, CHECKER) == (
        f"arkiv.schema = str('anypercent.run') AND $key = key({key}) AND $creator = addr({C55})")


def test_the_checker_goes_in_as_eip55_whatever_its_case_and_keys_in_lowercase():
    """The node refuses a mixed-case address whose EIP-55 checksum is wrong, so the form is computed, never copied."""
    for given in (CHECKER, C55, CHECKER.upper().replace("0X", "0x"), "0x5b38DA6a701c568545dcfcb03fcb875f56beddc4"):
        assert rpc.checker_address(given) == CHECKER
        assert f"addr({C55})" in rpc.q1("MDGP", 1, given)
    assert rpc.entity_key(k("x").upper().replace("0X", "0x")) == k("x")


def test_keccak_and_eip55_match_the_published_vectors():
    assert rpc.keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert rpc.keccak256(b"abc").hex() == "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"
    for address in ("0x52908400098527886E0F7030069857D2E4169EE7", "0x8617E340B3D01FA5F11F306F4090FD50E238070D",
                    "0xde709f2102306220921060314715629080e2fb77", "0x27b1fdb04752bbc536007a920d24acb045561c26",
                    "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed", "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359",
                    "0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB", "0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb"):
        assert rpc.eip55(address.lower()) == address                     # EIP-55's own test addresses


@pytest.mark.parametrize("bad", ["", "0x123", CHECKER + "0", "5b38da6a701c568545dcfcb03fcb875f56beddc4",
                                 "0x5b38da6a701c568545dcfcb03fcb875f56beddcg", None])
def test_a_bad_checker_is_refused(bad):
    with pytest.raises(ValueError):
        rpc.checker_address(bad)


@pytest.mark.parametrize("game", ["mdgp", "MDGP') OR (game = str('SHIP", "MDG", "", None])
def test_nothing_but_an_arcade_id_reaches_a_query(game):
    with pytest.raises(ValueError):
        rpc.q1(game, 1, CHECKER)


@pytest.mark.parametrize("season", ["1", 1.0, True, 2 ** 31])
def test_the_season_is_an_i32(season):
    with pytest.raises(ValueError):
        rpc.q1("MDGP", season, CHECKER)


@pytest.mark.parametrize("key", ["0x12", k("x") + "00", "key(0x1) OR *", None])
def test_nothing_but_a_key_reaches_a_lookup(key):
    with pytest.raises(ValueError):
        rpc.q6(rpc.RUN_SCHEMA, key, CHECKER)


# ---- the board: Q1 + Q2 -----------------------------------------------------------------------------------------

def _board_rows():
    stub = StubRpc(Q1_PAGE, Q2_PAGE)
    return rpc.read_board(stub, "MDGP", 1, CHECKER), stub


def test_the_board_is_one_page_of_each_with_no_ghost_bytes():
    (rows, block, dropped), stub = _board_rows()
    (m1, (s1, o1), t1), (m2, (s2, o2), t2) = stub.requests
    assert (m1, s1, t1) == ("arkiv_query", rpc.q1("MDGP", 1, CHECKER), rpc.TIMEOUT_S)
    assert (m2, s2, t2) == ("arkiv_query", rpc.q2("MDGP", 1, CHECKER), rpc.TIMEOUT_S)
    assert o1["limit"] == o2["limit"] == "0x64" and rpc.TIMEOUT_S <= 3
    for options in (o1, o2):
        sel = options["select"]
        assert sel["key"] and sel["creator"] and sel["expiresAt"]          # the creator is checked again here
        assert "log" not in sel["attributes"] and "log_enc" not in sel["attributes"]   # never a ghost for a board
        assert sel["attributes"]["arkiv.schema"] is True
    assert set(o1["select"]["attributes"]) == {"arkiv.schema", "game", "title", "frames", "runner", "book", "label",
                                               "human", "credential", "log_h", "rules"}
    assert set(o2["select"]["attributes"]) == {"arkiv.schema", "run", "game", "season", "frames", "log_h", "price",
                                               "seller", "book", "human"}


def test_the_fixture_decodes():
    (rows, block, dropped), _ = _board_rows()
    assert block == 0x3fe91                                             # the later of the two reads
    assert rows == (
        RunRow(key=k("6ps-fast"), game="MDGP", title="MARINE DRIVE GP", frames=6170, runner="3f9a0c21d4e5b6a7",
               book="ANY-6PS", label=None, human=True, credential="Orb", log_h=h("6ps-fast"), rules=4,
               expires_block=0x7a9812, listing=k("l-6ps"), price="0.1"),
        RunRow(key=k("team"), game="MDGP", title="MARINE DRIVE GP", frames=6300, runner="e0b7d1c2a3f45968",
               book=None, label="TEAM", human=False, credential=None, log_h=h("team"), rules=4,
               expires_block=0x7a9812),
        RunRow(key=k("6ps-slow"), game="MDGP", title="MARINE DRIVE GP", frames=6350, runner="3f9a0c21d4e5b6a7",
               book="ANY-6PS", label=None, human=True, credential="Orb", log_h=h("6ps-slow"), rules=4,
               expires_block=0x7a9812),
        RunRow(key=k("k2p"), game="MDGP", title="MARINE DRIVE GP", frames=6400, runner="71c0ee5d2b9a8f34",
               book="ANY-K2P", label=None, human=True, credential="Orb", log_h=h("k2p"), rules=4,
               expires_block=0x7a9812, listing=k("l-k2p"), price="0.1"),
    )
    assert dropped == 4      # the look-alike run and its listing, the other schema's row, the misfit


def test_rows_another_wallet_wrote_are_ignored():
    """The look-alike: a well-formed run 10 s faster under the owner's own book, written by a stranger's wallet. A
    node that skipped the $creator pin would hand it over; the reader still drops it."""
    (rows, _, _), _ = _board_rows()
    assert all(row.key != k("lookalike") for row in rows)
    assert min(row.frames for row in rows) == 6170
    lookalike = next(e for e in entities(Q1_PAGE) if e["creator"] == STRANGER)
    assert rpc.decode_runs([lookalike], "MDGP", CHECKER) == ([], 1)
    assert rpc.decode_runs([lookalike], "MDGP", STRANGER)[0][0]["key"] == k("lookalike")   # well-formed: only the pin


def test_a_smoke_page_decodes_under_its_own_schema():
    smoke = [e for e in entities(Q1_PAGE) if e["key"] == k("smoke")]
    assert rpc.decode_runs(smoke, "MDGP", CHECKER) == ([], 1)
    runs, dropped = rpc.decode_runs(smoke, "MDGP", CHECKER, schema="anypercent.smoke.run")
    assert dropped == 0 and runs[0]["frames"] == 6410


def _good_run():
    return copy.deepcopy(next(e for e in entities(Q1_PAGE) if e["key"] == k("6ps-fast")))


def _attr(entity, name):
    return next(a for a in entity["attributes"] if a["name"] == name)


def _without(name):
    def change(e):
        e["attributes"] = [a for a in e["attributes"] if a["name"] != name]
    return change


def _set(name, **kw):
    def change(e):
        _attr(e, name).update(kw)
    return change


def _no_name(e):
    e["attributes"] = [a for a in e["attributes"] if a["name"] != "book"]


MISFITS = {
    "no frames": _without("frames"),
    "no log_h": _without("log_h"),
    "no human": _without("human"),
    "no schema": _without("arkiv.schema"),
    "frames as a number": _set("frames", value=6170),
    "frames typed i32": _set("frames", type="i32", value=6170),
    "frames past u64": _set("frames", value="0x1" + "0" * 16),
    "human as a string": _set("human", value="true"),
    "human typed str": _set("human", type="str", value="true"),
    "another schema": _set("arkiv.schema", value="anypercent.listing"),
    "another game": _set("game", value="SHIP"),
    "log_h not hex": _set("log_h", value="../../etc/passwd" + "0" * 48),
    "log_h uppercase": _set("log_h", value=h("6ps-fast").upper()),
    "log_h typed bytes32": _set("log_h", type="bytes32"),          # "bytes32" stands for "key" only in key columns
    "credential a number": _set("credential", type="i32", value=1),
    "book with a control character": _set("book", value="ANY-\n6PS"),
    "title too long": _set("title", value="X" * 65),
    "no book and no label": _no_name,
    "a duplicate column": lambda e: e["attributes"].append({"name": "frames", "type": "u64", "value": "0x1"}),
    "attributes not a list": lambda e: e.update(attributes={"frames": "0x1"}),
    "a bad key": lambda e: e.update(key="0x1234"),
    "no creator": lambda e: e.pop("creator"),
    "no expiry": lambda e: e.pop("expiresAt"),
}


@pytest.mark.parametrize("name", sorted(MISFITS))
def test_a_misfit_row_is_dropped_and_counted(name):
    good, bad = _good_run(), _good_run()
    MISFITS[name](bad)
    runs, dropped = rpc.decode_runs([good, bad, "not a row"], "MDGP", CHECKER)
    assert [r["key"] for r in runs] == [k("6ps-fast")] and dropped == 2, name


def test_optional_columns_may_be_absent():
    e = _good_run()
    e["attributes"] = [a for a in e["attributes"] if a["name"] not in ("credential",)]
    (run,), dropped = rpc.decode_runs([e], "MDGP", CHECKER)
    assert dropped == 0 and run["credential"] is None and run["human"] is True


def test_the_creator_compares_in_any_case():
    e = _good_run()
    e["creator"] = "0x5B38Da6a701c568545dCfcB03FcB875f56beddC4"
    assert len(rpc.decode_runs([e], "MDGP", CHECKER)[0]) == 1


def _listings(*changes):
    out = entities(Q2_PAGE)
    for change in changes:
        change(out)
    return page(*out, block="0x3fe91")


@pytest.mark.parametrize("why, change", [
    ("its log differs from the run's", lambda ls: _set("log_h", value=h("other"))(ls[1])),
    ("its time differs from the run's", lambda ls: _set("frames", value=hex(6100))(ls[1])),
    ("its price is not a decimal", lambda ls: _set("price", value="ten")(ls[1])),
    ("another season", lambda ls: _set("season", value=2)(ls[1])),
    ("another wallet wrote it", lambda ls: ls[1].update(creator=STRANGER)),
])
def test_a_listing_counts_only_for_its_own_run(why, change):
    rows, _, _ = rpc.read_board(StubRpc(Q1_PAGE, _listings(change)), "MDGP", 1, CHECKER)
    fast = next(r for r in rows if r.key == k("6ps-fast"))
    assert (fast.listing, fast.price) == (None, None), why
    assert next(r for r in rows if r.key == k("k2p")).listing == k("l-k2p")


@pytest.mark.parametrize("reply", [
    {"jsonrpc": "2.0", "id": 1, "error": {"code": -32001, "message": "expected a comparison operator"}},
    {"jsonrpc": "2.0", "id": 1},
    {"jsonrpc": "2.0", "id": 1, "result": {"data": {}, "blockNumber": "0x1"}},
    {"jsonrpc": "2.0", "id": 1, "result": {"data": [], "blockNumber": 7}},
    {"jsonrpc": "2.0", "id": 1, "result": {"data": []}},
    "not json-rpc",
    ConnectionRefusedError("refused"),
    TimeoutError("timed out"),
])
def test_a_bad_reply_is_an_rpc_error(reply):
    with pytest.raises(rpc.RpcError):
        rpc.read_board(StubRpc(reply, Q2_PAGE), "MDGP", 1, CHECKER)
    with pytest.raises(rpc.RpcError):
        rpc.read_board(StubRpc(Q1_PAGE, reply), "MDGP", 1, CHECKER)


def test_an_empty_board_is_no_rows():
    assert rpc.read_board(StubRpc(page(), page()), "MDGP", 1, CHECKER) == ((), 0x3fe90, 0)


# ---- Q6: one listing, one run -----------------------------------------------------------------------------------

def test_a_listing_by_its_key():
    listing = next(e for e in entities(Q2_PAGE) if e["key"] == k("l-6ps"))
    stub = StubRpc(page(listing))
    got = rpc.read_listing(stub, k("l-6ps"), CHECKER)
    assert got == {"key": k("l-6ps"), "creator": CHECKER, "expires": 0x46a1d0, "run": k("6ps-fast"), "game": "MDGP",
                   "season": 1, "frames": 6170, "log_h": h("6ps-fast"), "price": "0.1", "seller": "3f9a0c21d4e5b6a7",
                   "book": "ANY-6PS", "human": True}
    method, (query, options), _ = stub.requests[0]
    assert query == rpc.q6(rpc.LISTING_SCHEMA, k("l-6ps"), CHECKER) and options["limit"] == "0x1"


def test_a_listing_that_is_gone_or_not_ours_is_none():
    assert rpc.read_listing(StubRpc(page()), k("l-6ps"), CHECKER) is None
    lookalike = next(e for e in entities(Q2_PAGE) if e["creator"] == STRANGER)
    assert rpc.read_listing(StubRpc(page(lookalike)), lookalike["key"], CHECKER) is None
    other = next(e for e in entities(Q2_PAGE) if e["key"] == k("l-k2p"))
    assert rpc.read_listing(StubRpc(page(other)), k("l-6ps"), CHECKER) is None     # a row for another key


def test_a_run_with_its_plain_log():
    run = _good_run()
    run["attributes"].append({"name": "log", "type": "bytes", "value": "0x" + b"ACL1MDGP".hex()})
    stub = StubRpc(page(run))
    got = rpc.read_run(stub, k("6ps-fast"), CHECKER, with_log=True)
    assert got["log"] == b"ACL1MDGP" and got["frames"] == 6170 and got["log_h"] == h("6ps-fast")
    (method, (query, options), _), = stub.requests
    assert query == rpc.q6(rpc.RUN_SCHEMA, k("6ps-fast"), CHECKER)
    assert options["select"]["attributes"]["log"] is True and "log_enc" not in options["select"]["attributes"]
    stub = StubRpc(page(_good_run()))
    assert rpc.read_run(stub, k("6ps-fast"), CHECKER, with_log=True)["log"] is None   # a listed run: no plain log


def test_a_run_lookup_without_the_log_never_asks_for_it():
    stub = StubRpc(page(_good_run()))
    got = rpc.read_run(stub, k("6ps-fast"), CHECKER)
    assert got["key"] == k("6ps-fast") and "log" not in got
    assert "log" not in stub.requests[0][1][1]["select"]["attributes"]


def test_a_run_with_bad_bytes_is_dropped():
    run = _good_run()
    run["attributes"].append({"name": "log", "type": "bytes", "value": "0xabc"})
    assert rpc.read_run(StubRpc(page(run)), k("6ps-fast"), CHECKER, with_log=True) is None


# ---- the transport: JSON-RPC over HTTP, no proxy --------------------------------------------------------------------

class _Node(BaseHTTPRequestHandler):
    bodies = []
    reply = {"jsonrpc": "2.0", "id": 1, "result": {"data": [], "blockNumber": "0x10"}}
    status = 200

    def log_message(self, *args):
        pass

    def do_POST(self):
        type(self).bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        raw = json.dumps(type(self).reply).encode()
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def node(monkeypatch):
    monkeypatch.setattr(_Node, "bodies", [])
    monkeypatch.setattr(_Node, "status", 200)
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")             # a proxy that is not there: never used
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Node)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()
    server.server_close()


def test_the_transport_posts_one_json_rpc_request(node):
    send = rpc.rpc_transport(node)
    rows, block, dropped = rpc.read_board(send, "MDGP", 1, CHECKER)
    assert (rows, block, dropped) == ((), 0x10, 0)
    first = _Node.bodies[0]
    assert first["jsonrpc"] == "2.0" and first["id"] == 1 and first["method"] == "arkiv_query"
    assert first["params"][0] == rpc.q1("MDGP", 1, CHECKER) and first["params"][1]["limit"] == "0x64"


def test_an_http_error_is_an_rpc_error(node):
    _Node.status = 503
    with pytest.raises(rpc.RpcError):
        rpc.read_board(rpc.rpc_transport(node), "MDGP", 1, CHECKER)


def test_nothing_listening_is_an_rpc_error():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(rpc.RpcError):
        rpc.read_board(rpc.rpc_transport(f"http://127.0.0.1:{port}"), "MDGP", 1, CHECKER)
