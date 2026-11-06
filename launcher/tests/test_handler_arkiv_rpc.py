"""Tests for the Arkiv reader (handler/arkiv_rpc.py): the exact query strings the service and the web board send, the
JSON-RPC request, the decoding and validation of raw rows, and the readers' one rule (stamped runs only). A stub stands
in for the node; the last tests use a local HTTP server.

The fixtures (tests/fixtures/arkiv_q*_mdgp.json) are raw replies in the live Rabdi node's shape (key, creator,
expiresAt, attributes [{name, type, value}]): runs and listings a console wallet (WALLET) created. Among the rows: a
look-alike written by another wallet (no stamp names it: never on the board), a row of another schema, an open-tier
TEAM row (retired: a misfit now) and a misfit whose u64 is a bare number. They were read before rows carried their
owner and runs their season: both are added here (owner = creator, season 1), as the node now answers. The checker's
stamps are built here."""
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
WALLET = "0x5b38da6a701c568545dcfcb03fcb875f56beddc4"                  # the console wallet the fixtures' rows are from
CHECKER = "0x8ba1f109551bd432803012645ac136ddd64dba72"                 # the checker: it writes the stamps
STRANGER = "0xab8483f64d9c6d1ecf9b849ae677dd3315835cb2"
WALLET_B = "0x1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b9f3e"


def h(name):
    return hashlib.sha256(name.encode()).hexdigest()


def k(name):
    return "0x" + h("key:" + name)


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


def _as_read_now(reply, runs=False):
    """A fixture page as the node answers a read that selects the owner: each row's owner (its creator: never
    transferred), and a run's season."""
    for e in reply["result"]["data"]:
        e["owner"] = e["creator"]
        if runs and not any(a["name"] == "season" for a in e["attributes"]):
            e["attributes"].append({"name": "season", "type": "i32", "value": 1})
    return reply


Q1_PAGE = _as_read_now(fixture("arkiv_q1_mdgp.json"), runs=True)
Q2_PAGE = _as_read_now(fixture("arkiv_q2_mdgp.json"))


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


def _attrs(entity):
    return {a["name"]: a["value"] for a in entity["attributes"]}


def stamp(run, key=None, console=WALLET, creator=CHECKER, **over):
    """The checker's stamp of a raw run row: its key and the wallet that owns it, and the columns it copies (game,
    season 1, frames, log_h, book or label, human, the lap columns); over replaces any of them."""
    a = _attrs(run)
    values = {"run": ("bytes32", run["key"]), "console": ("str", console), "game": ("str", a["game"]),
              "season": ("i32", 1), "frames": ("u64", a["frames"]), "log_h": ("str", a["log_h"]),
              "human": ("bool", a["human"]), "tool": ("str", "arcade_replay sha256:0123456789ab")}
    for name in ("book", "label", "split_kind"):
        if name in a:
            values[name] = ("str", a[name])
    for name in ("s1", "s2", "s3", "s4"):
        if name in a:
            values[name] = ("u64", a[name])
    for name, value in over.items():
        if value is None:
            values.pop(name, None)
        else:
            values[name] = (values[name][0] if name in values else "u64", value)
    attrs = [{"name": "arkiv.schema", "type": "str", "value": "anypercent.stamp"}]
    attrs += [{"name": name, "type": kind, "value": value} for name, (kind, value) in values.items()]
    return {"key": key or k("stamp:" + run["key"]), "creator": creator, "expiresAt": "0x7a9812", "attributes": attrs}


def run_entity(key, frames, log_h, creator=WALLET, book="ANY-6PS", label=None, laps=None, owner=None):
    attrs = [{"name": "arkiv.schema", "type": "str", "value": "anypercent.run"},
             {"name": "season", "type": "i32", "value": 1},
             {"name": "game", "type": "str", "value": "MDGP"},
             {"name": "title", "type": "str", "value": "MARINE DRIVE GP"},
             {"name": "frames", "type": "u64", "value": hex(frames)},
             {"name": "runner", "type": "str", "value": "0123456789abcdef"},
             {"name": "human", "type": "bool", "value": book is not None},
             {"name": "log_h", "type": "str", "value": log_h}, {"name": "rules", "type": "u64", "value": "0x4"}]
    attrs.append({"name": "book", "type": "str", "value": book} if book else {"name": "label", "type": "str",
                                                                             "value": label})
    if book:
        attrs.append({"name": "credential", "type": "str", "value": "Orb"})
    for i, lap in enumerate(laps or (), start=1):
        attrs.append({"name": f"s{i}", "type": "u64", "value": hex(lap)})
    if laps:
        attrs.append({"name": "split_kind", "type": "str", "value": "lap"})
    return {"key": key, "creator": creator, "owner": owner or creator, "expiresAt": "0x7a9812", "attributes": attrs}


def listing_entity(key, run, creator=WALLET, owner=None, **over):
    a = _attrs(run)
    values = {"run": ("bytes32", run["key"]), "game": ("str", "MDGP"), "season": ("i32", 1),
              "frames": ("u64", a["frames"]), "log_h": ("str", a["log_h"]), "price": ("dec", "0.1"),
              "seller": ("str", "0123456789abcdef"), "human": ("bool", a["human"]), "pay_to": ("str", "0.0.5123456")}
    for name in ("book", "label"):
        if name in a:
            values[name] = ("str", a[name])
    for name, value in over.items():
        values[name] = (values[name][0], value)
    attrs = [{"name": "arkiv.schema", "type": "str", "value": "anypercent.listing"}]
    attrs += [{"name": name, "type": kind, "value": value} for name, (kind, value) in values.items()]
    return {"key": key, "creator": creator, "owner": owner or creator, "expiresAt": "0x46a1d0", "attributes": attrs}


# ---- the query strings: the service's and the web board's, character for character ------------------------------

W55 = "0x5B38Da6a701c568545dCfcB03FcB875f56beddC4"                      # WALLET in its EIP-55 form
C55 = "0x8ba1f109551bD432803012645Ac136ddd64DBA72"                      # CHECKER in its EIP-55 form


def test_the_board_queries_are_the_services():
    """Q1 and Q2 pinned to a console wallet a stamp names, and the stamps pinned to the checker, to the character as
    queries.ts (q1Board, q2Listings, q1Stamps) and the web board write them (addresses in their EIP-55 form)."""
    assert rpc.q1("MDGP", 1, WALLET) == (
        f"arkiv.schema = str('anypercent.run') AND game = str('MDGP') AND season = i32(1) AND $creator = addr("
        f"{W55}) ORDER BY frames:u64 ASC")
    assert rpc.q2("SHIP", 3, WALLET) == (
        f"arkiv.schema = str('anypercent.listing') AND game = str('SHIP') AND season = i32(3) AND $creator = addr("
        f"{W55}) ORDER BY frames:u64 ASC")
    assert rpc.q_stamps("MDGP", 1, CHECKER) == (
        f"arkiv.schema = str('anypercent.stamp') AND game = str('MDGP') AND season = i32(1) AND $creator = addr("
        f"{C55}) ORDER BY frames:u64 ASC")
    template = ("arkiv.schema = str('anypercent.run') AND game = str('${game}') AND season = i32(${season}) AND "
                "$creator = addr(${checker}) ORDER BY frames:u64 ASC")      # queries.ts Q1_TEMPLATE
    assert rpc.q1("ZIPG", 7, WALLET) == template.replace("${game}", "ZIPG").replace("${season}", "7").replace(
        "${checker}", W55)
    stamps = template.replace("anypercent.run", "anypercent.stamp")         # queries.ts Q1_STAMPS_TEMPLATE
    assert rpc.q_stamps("ZIPG", 7, CHECKER) == stamps.replace("${game}", "ZIPG").replace("${season}", "7").replace(
        "${checker}", C55)


def test_the_lookups_by_key_are_the_services():
    key = k("6ps-fast")
    assert rpc.q6(rpc.RUN_SCHEMA, key, WALLET) == (
        f"arkiv.schema = str('anypercent.run') AND $key = key({key}) AND $creator = addr({W55})")          # q6Run
    assert rpc.q_stamp_for_run(key, CHECKER) == (
        f"arkiv.schema = str('anypercent.stamp') AND run = key({key}) AND $creator = addr({C55})")   # qStampForRun
    assert rpc.q6_listing(key) == f"arkiv.schema = str('anypercent.listing') AND $key = key({key})"   # q6ListingByKey


def test_an_address_goes_in_as_eip55_whatever_its_case_and_keys_in_lowercase():
    """The node refuses a mixed-case address whose EIP-55 checksum is wrong, so the form is computed, never copied."""
    for given in (WALLET, W55, WALLET.upper().replace("0X", "0x"), "0x5b38DA6a701c568545dcfcb03fcb875f56beddc4"):
        assert rpc.checker_address(given) == WALLET
        assert f"addr({W55})" in rpc.q1("MDGP", 1, given)
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
def test_a_bad_address_is_refused(bad):
    with pytest.raises(ValueError):
        rpc.checker_address(bad)


@pytest.mark.parametrize("game", ["mdgp", "MDGP') OR (game = str('SHIP", "MDG", "", None])
def test_nothing_but_an_arcade_id_reaches_a_query(game):
    for q in (rpc.q1, rpc.q_stamps):
        with pytest.raises(ValueError):
            q(game, 1, CHECKER)


@pytest.mark.parametrize("season", ["1", 1.0, True, 2 ** 31])
def test_the_season_is_an_i32(season):
    for q in (rpc.q1, rpc.q_stamps):
        with pytest.raises(ValueError):
            q("MDGP", season, CHECKER)


@pytest.mark.parametrize("key", ["0x12", k("x") + "00", "key(0x1) OR *", None])
def test_nothing_but_a_key_reaches_a_lookup(key):
    for q in (lambda key: rpc.q6(rpc.RUN_SCHEMA, key, WALLET), lambda key: rpc.q_stamp_for_run(key, CHECKER),
              rpc.q6_listing):
        with pytest.raises(ValueError):
            q(key)


# ---- the board: the checker's stamps, then each stamped wallet's runs and listings, joined ------------------------

def _fixture_stamps():
    """The checker's stamps of the fixture's own runs (its 6PS runs and K2P, owned by WALLET), fastest first."""
    runs = {e["key"]: e for e in entities(Q1_PAGE)}
    return page(*(stamp(runs[key]) for key in (k("6ps-fast"), k("6ps-slow"), k("k2p"))), block="0x3fe8f")


def _board_rows():
    stub = StubRpc(_fixture_stamps(), Q1_PAGE, Q2_PAGE)
    return rpc.read_board(stub, "MDGP", 1, CHECKER), stub


def test_the_board_is_the_stamps_then_each_wallets_runs_and_listings_with_no_ghost_bytes():
    (rows, block, dropped), stub = _board_rows()
    (m0, (s0, o0), t0), (m1, (s1, o1), t1), (m2, (s2, o2), t2) = stub.requests
    assert (m0, s0, t0) == ("arkiv_query", rpc.q_stamps("MDGP", 1, CHECKER), rpc.TIMEOUT_S)
    assert (m1, s1, t1) == ("arkiv_query", rpc.q1("MDGP", 1, WALLET), rpc.TIMEOUT_S)        # the wallet a stamp names
    assert (m2, s2, t2) == ("arkiv_query", rpc.q2("MDGP", 1, WALLET), rpc.TIMEOUT_S)
    assert o0["limit"] == o1["limit"] == o2["limit"] == "0x64" and rpc.TIMEOUT_S <= 3
    assert "owner" not in o0["select"] and o1["select"]["owner"] and o2["select"]["owner"]   # a run's owner now
    for options in (o0, o1, o2):
        sel = options["select"]
        assert sel["key"] and sel["creator"] and sel["expiresAt"]          # the creator is checked again here
        assert "log" not in sel["attributes"] and "log_enc" not in sel["attributes"]   # never a ghost
        assert sel["attributes"]["arkiv.schema"] is True
    assert set(o0["select"]["attributes"]) == {"arkiv.schema", "run", "console", "game", "season", "frames", "log_h",
                                               "book", "label", "human", "s1", "s2", "s3", "s4", "split_kind"}
    assert set(o1["select"]["attributes"]) == {"arkiv.schema", "game", "title", "frames", "runner", "book", "label",
                                               "human", "credential", "log_h", "rules", "s1", "s2", "s3", "s4",
                                               "split_kind", "season"}
    assert set(o2["select"]["attributes"]) == {"arkiv.schema", "run", "game", "season", "frames", "log_h", "price",
                                               "seller", "book", "label", "human", "pay_to", "hcs"}


def test_the_fixture_decodes_to_its_stamped_runs():
    (rows, block, dropped), _ = _board_rows()
    assert block == 0x3fe91                                             # the latest of the reads
    assert rows == (
        RunRow(key=k("6ps-fast"), game="MDGP", title="MARINE DRIVE GP", frames=6170, runner="3f9a0c21d4e5b6a7",
               book="ANY-6PS", label=None, human=True, credential="Orb", log_h=h("6ps-fast"), rules=4,
               expires_block=0x7a9812, listing=k("l-6ps"), price="0.1"),
        RunRow(key=k("6ps-slow"), game="MDGP", title="MARINE DRIVE GP", frames=6350, runner="3f9a0c21d4e5b6a7",
               book="ANY-6PS", label=None, human=True, credential="Orb", log_h=h("6ps-slow"), rules=4,
               expires_block=0x7a9812),
        RunRow(key=k("k2p"), game="MDGP", title="MARINE DRIVE GP", frames=6400, runner="71c0ee5d2b9a8f34",
               book="ANY-K2P", label=None, human=True, credential="Orb", log_h=h("k2p"), rules=4,
               expires_block=0x7a9812, listing=k("l-k2p"), price="0.1"),
    )
    # The open-tier TEAM row, the other schema's row and the misfit; and the look-alike's listing (its run has no
    # stamp). The look-alike run itself is simply not on the board: no stamp names it.
    assert dropped == 4


def test_rows_another_wallet_wrote_are_ignored():
    """The look-alike: a well-formed run 10 s faster under the owner's own book, written by a stranger's wallet. No
    stamp names it, so it never reaches the board, even from a node that hands it over."""
    (rows, _, _), _ = _board_rows()
    assert all(row.key != k("lookalike") for row in rows)
    assert min(row.frames for row in rows) == 6170
    lookalike = next(e for e in entities(Q1_PAGE) if e["creator"] == STRANGER)
    assert rpc.decode_runs([lookalike], "MDGP", WALLET) == ([], 1)
    assert rpc.decode_runs([lookalike], "MDGP", STRANGER)[0][0]["key"] == k("lookalike")   # well-formed: only the pin
    forged = stamp(lookalike, console=WALLET)                           # even a stamp naming the owner's wallet
    rows, _, _ = rpc.read_board(StubRpc(page(forged), Q1_PAGE, page()), "MDGP", 1, CHECKER)
    assert rows == ()                                                   # its run is not that wallet's


def test_a_smoke_page_decodes_under_its_own_schema():
    smoke = [e for e in entities(Q1_PAGE) if e["key"] == k("smoke")]
    assert rpc.decode_runs(smoke, "MDGP", WALLET) == ([], 1)
    runs, dropped = rpc.decode_runs(smoke, "MDGP", WALLET, schema="anypercent.smoke.run")
    assert dropped == 0 and runs[0]["frames"] == 6410


# ---- the readers' rule: the five-row mix every reader agrees on (the bridge's arkiv-board.test.ts) ------------------

WALLET_A, STAMPER = WALLET, CHECKER
K1, K2, K3, K4, L1, L2, S1, S3, S4 = (k(n) for n in ("K1", "K2", "K3", "K4", "L1", "L2", "S1", "S3", "S4"))
LAPS = (2087, 1995)


def _mix():
    """K1 a run of WALLET_A that the checker's stamp S1 names with WALLET_A: kept. K2 a run of WALLET_A no stamp
    names: never on the board. K3 a run of WALLET_B whose stamp S3 names WALLET_A: dropped. K4 a run whose stamp S4
    copied other frames: dropped. L1 WALLET_A's listing of K1: kept; L2 a stranger's listing naming K1: dropped."""
    runs = [run_entity(K1, 6170, h("1"), laps=LAPS + (6170 - 4082,)),
            run_entity(K2, 6050, h("2"), laps=LAPS + (6050 - 4082,)),
            run_entity(K3, 6180, h("3"), creator=WALLET_B, laps=LAPS + (6180 - 4082,)),
            run_entity(K4, 6200, h("4"), laps=LAPS + (6200 - 4082,))]
    stamps = [stamp(runs[3], S4, frames=hex(6100)), stamp(runs[0], S1), stamp(runs[2], S3, console=WALLET_A)]
    listings = [listing_entity(L1, runs[0]), listing_entity(L2, runs[0], creator=STRANGER)]
    return stamps, runs, listings


class MixNode:
    """arkiv_query over the mix as a node answers it: the schema, $key, run, game, season and $creator pins honoured
    (ignore_pin: every $creator pin skipped, as a node handing over look-alikes would), fastest first."""

    def __init__(self, ignore_pin=False):
        self.stamps, self.runs, self.listings = _mix()
        self.ignore_pin, self.queries = ignore_pin, []

    def __call__(self, method, params, timeout_s):
        import re
        text, options = params
        self.queries.append(text)
        want = {"schema": r"arkiv\.schema = str\('([^']+)'\)", "creator": r"\$creator = addr\((0x[0-9a-fA-F]{40})\)",
                "key": r"\$key = key\((0x[0-9a-f]{64})\)", "run": r" run = key\((0x[0-9a-f]{64})\)"}
        got = {name: (re.search(pattern, text) or [None, None])[1] for name, pattern in want.items()}
        rows = {"anypercent.stamp": self.stamps, "anypercent.run": self.runs,
                "anypercent.listing": self.listings}[got["schema"]]
        out = [e for e in rows
               if (self.ignore_pin or not got["creator"] or e["creator"] == got["creator"].lower())
               and (not got["key"] or e["key"] == got["key"]) and (not got["run"] or _attrs(e)["run"] == got["run"])]
        out.sort(key=lambda e: int(_attrs(e)["frames"], 16))
        return page(*copy.deepcopy(out[:int(options["limit"], 16)]))


@pytest.mark.parametrize("ignore_pin", [False, True])
def test_the_five_row_mix_keeps_k1_and_its_owners_listing_only(ignore_pin):
    node = MixNode(ignore_pin)
    rows, _, dropped = rpc.read_board(node, "MDGP", 1, CHECKER)
    assert [(r.key, r.listing, r.frames) for r in rows] == [(K1, L1, 6170)]
    assert rows[0].splits == LAPS + (6170 - 4082,) and rows[0].pay_to == "0.0.5123456"
    assert node.queries == [rpc.q_stamps("MDGP", 1, CHECKER), rpc.q1("MDGP", 1, WALLET_A), rpc.q2("MDGP", 1, WALLET_A)]
    # S4 (other frames) and S3 (its run is WALLET_B's) do not count; from a node that skips pins, L2 (a stranger's)
    # comes back too and does not count either. K2 has no stamp: not on the board, not counted.
    assert dropped == (3 if ignore_pin else 2)


def test_why_each_row_of_the_mix_does_not_count():
    stamps, runs, listings = _mix()
    decoded = {}
    for kind, rows, decode in (("stamp", stamps, lambda d: rpc.decode_stamps(d, None, CHECKER)),
                               ("run", runs, lambda d: rpc.decode_runs(d, None, None)),
                               ("listing", listings, lambda d: rpc.decode_listings(d, None, None))):
        got, dropped = decode(rows)
        assert dropped == 0
        decoded.update({row["key"]: row for row in got})
    assert rpc.run_mismatch(decoded[S1], decoded[K1]) is None
    assert rpc.run_mismatch(decoded[S4], decoded[K4]) == "frames"
    assert rpc.run_mismatch(decoded[S3], decoded[K3]) == "created by another wallet than the stamp names"
    assert rpc.listing_mismatch(decoded[S1], decoded[L1]) is None
    assert rpc.listing_mismatch(decoded[S1], decoded[L2]) == "created by another wallet than the run's"
    kept, offers, dropped = rpc.join_board([decoded[s] for s in (S4, S1, S3)], [decoded[r] for r in (K1, K2, K3, K4)],
                                           [decoded[x] for x in (L1, L2)])
    assert [run["key"] for _, run in kept] == [K1] and list(offers) == [K1] and offers[K1]["key"] == L1
    assert dropped == 3


@pytest.mark.parametrize("what, over", [
    ("game", {"game": "SHIP"}), ("season", {"season": 2}), ("log_h", {"log_h": h("9")}), ("book", {"book": "ANY-ZZZ"}),
    ("human", {"human": False}), ("splits", {"s3": hex(2000)}),
])
def test_any_copied_column_that_disagrees_drops_the_run(what, over):
    run = run_entity(K1, 6170, h("1"), laps=LAPS + (6170 - 4082,))
    (st,), _ = rpc.decode_stamps([stamp(run, S1, **over)], None, CHECKER)
    (row,), _ = rpc.decode_runs([run], None, None)
    assert rpc.run_mismatch(st, row) == what


@pytest.mark.parametrize("what", ["transferred", "no owner given", "no season"])
def test_a_run_given_away_or_read_without_its_owner_or_season_does_not_count(what):
    """A read-only entity can still be transferred: the run counts only while its owner is the stamp's console too
    (a node that does not say the owner counts as a mismatch), and only with the stamp's season."""
    run = run_entity(K1, 6170, h("1"), owner=WALLET_B if what == "transferred" else None)
    if what == "no owner given":
        del run["owner"]
    elif what == "no season":
        run["attributes"] = [a for a in run["attributes"] if a["name"] != "season"]
    stamps = page(stamp(run, S1))
    rows, _, dropped = rpc.read_board(StubRpc(stamps, page(run), page()), "MDGP", 1, CHECKER)
    assert rows == () and dropped == 1
    assert rpc.read_run(StubRpc(stamps, page(run)), K1, CHECKER) is None


def test_a_listing_given_away_or_whose_run_does_not_count_is_none():
    run = run_entity(K1, 6170, h("1"))
    given = listing_entity(L1, run, owner=WALLET_B)
    rows, _, dropped = rpc.read_board(StubRpc(page(stamp(run, S1)), page(run), page(given)), "MDGP", 1, CHECKER)
    assert [(r.key, r.listing) for r in rows] == [(K1, None)] and dropped == 1
    assert rpc.read_listing(StubRpc(page(given), page(stamp(run, S1))), L1, CHECKER) is None
    mine = listing_entity(L1, run)
    gone = StubRpc(page(mine), page(stamp(run, S1)), page())                # its stamp, but the run is gone
    assert rpc.read_listing(gone, L1, CHECKER) is None and len(gone.requests) == 3
    moved = StubRpc(page(mine), page(stamp(run, S1)), page(run_entity(K1, 6170, h("1"), owner=WALLET_B)))
    assert rpc.read_listing(moved, L1, CHECKER) is None
    assert rpc.read_listing(StubRpc(page(mine), page(stamp(run, S1)), page(run)), L1, CHECKER)["key"] == L1


def test_a_bot_stamp_with_another_label_drops_its_run():
    bot = run_entity(K1, 6236, h("1"), book=None, label="BOT-A2")
    (st,), _ = rpc.decode_stamps([stamp(bot, S1, label="BOT-A3")], None, CHECKER)
    (row,), _ = rpc.decode_runs([bot], None, None)
    assert rpc.run_mismatch(st, row) == "label"
    (st,), _ = rpc.decode_stamps([stamp(bot, S1)], None, CHECKER)
    assert rpc.run_mismatch(st, row) is None


def test_two_stamps_of_one_log_count_once_and_a_stamp_whose_run_is_gone_for_nothing():
    stamps, runs, listings = _mix()
    again = stamp(runs[0], k("S1 again"))
    rows, _, dropped = rpc.read_board(StubRpc(page(stamps[1], again), page(runs[0]), page()), "MDGP", 1, CHECKER)
    assert [r.key for r in rows] == [K1] and dropped == 1
    rows, _, dropped = rpc.read_board(StubRpc(page(stamps[1]), page(), page()), "MDGP", 1, CHECKER)
    assert rows == () and dropped == 1


def test_a_stamp_not_the_checkers_or_naming_no_wallet_is_a_misfit():
    run = run_entity(K1, 6170, h("1"))
    assert rpc.decode_stamps([stamp(run, creator=STRANGER)], None, CHECKER) == ([], 1)
    assert rpc.decode_stamps([stamp(run, console="C-7QZP")], None, CHECKER) == ([], 1)
    assert rpc.decode_stamps([stamp(run, console=W55)], None, CHECKER) == ([], 1)   # the bridge writes it lowercase
    assert rpc.decode_stamps([stamp(run)], None, CHECKER)[1] == 0


def test_a_stamped_run_whose_listing_expired_still_ranks_as_not_for_sale():
    stamps, runs, _ = _mix()
    rows, _, dropped = rpc.read_board(StubRpc(page(stamps[1]), page(runs[0]), page()), "MDGP", 1, CHECKER)
    assert [(r.key, r.listing, r.price, r.pay_to) for r in rows] == [(K1, None, None, None)] and dropped == 0


def test_each_stamped_wallet_is_read_once_in_the_stamps_order():
    a = run_entity(K1, 6170, h("1"))
    b = run_entity(K3, 6180, h("3"), creator=WALLET_B, book="ANY-2KD")
    c = run_entity(K4, 6200, h("4"))
    stub = StubRpc(page(stamp(a), stamp(b, console=WALLET_B), stamp(c)), page(a, c), page(), page(b), page())
    rows, _, _ = rpc.read_board(stub, "MDGP", 1, CHECKER)
    assert [r.key for r in rows] == [K1, K3, K4]
    assert [params[0] for _, params, _ in stub.requests] == [
        rpc.q_stamps("MDGP", 1, CHECKER), rpc.q1("MDGP", 1, WALLET), rpc.q2("MDGP", 1, WALLET),
        rpc.q1("MDGP", 1, WALLET_B), rpc.q2("MDGP", 1, WALLET_B)]


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


def _open_tier(e):
    _no_name(e)
    e["attributes"].append({"name": "label", "type": "str", "value": "TEAM"})


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
    "an open-tier label": _open_tier,
    "a book and a label": lambda e: e["attributes"].append({"name": "label", "type": "str", "value": "BOT-A2"}),
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
    runs, dropped = rpc.decode_runs([good, bad, "not a row"], "MDGP", WALLET)
    assert [r["key"] for r in runs] == [k("6ps-fast")] and dropped == 2, name


def test_optional_columns_may_be_absent():
    e = _good_run()
    e["attributes"] = [a for a in e["attributes"] if a["name"] not in ("credential",)]
    (run,), dropped = rpc.decode_runs([e], "MDGP", WALLET)
    assert dropped == 0 and run["credential"] is None and run["human"] is True


def test_the_creator_compares_in_any_case():
    e = _good_run()
    e["creator"] = W55
    assert len(rpc.decode_runs([e], "MDGP", WALLET)[0]) == 1


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
    ("another book", lambda ls: _set("book", value="ANY-K2P")(ls[1])),
    ("not human as the run is", lambda ls: _set("human", value=False)(ls[1])),
    ("another wallet wrote it", lambda ls: ls[1].update(creator=STRANGER)),
])
def test_a_listing_counts_only_for_its_own_run(why, change):
    rows, _, _ = rpc.read_board(StubRpc(_fixture_stamps(), Q1_PAGE, _listings(change)), "MDGP", 1, CHECKER)
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
    for replies in ((reply,), (_fixture_stamps(), reply), (_fixture_stamps(), Q1_PAGE, reply)):
        with pytest.raises(rpc.RpcError):
            rpc.read_board(StubRpc(*replies, Q1_PAGE, Q2_PAGE), "MDGP", 1, CHECKER)


def test_an_empty_board_is_one_read_and_no_rows():
    stub = StubRpc(page())
    assert rpc.read_board(stub, "MDGP", 1, CHECKER) == ((), 0x3fe90, 0)
    assert len(stub.requests) == 1                                      # no stamp names a wallet: nothing more to read


# ---- one listing, one run: each only when it counts ----------------------------------------------------------------

def _fast_stamp():
    return stamp(next(e for e in entities(Q1_PAGE) if e["key"] == k("6ps-fast")))


def _listed(listing):
    """A listing read as read_listing reads it: the listing, its run's stamp, the run."""
    return StubRpc(page(listing), page(_fast_stamp()), page(_good_run()))


def test_a_listing_by_its_key():
    listing = next(e for e in entities(Q2_PAGE) if e["key"] == k("l-6ps"))
    stub = _listed(listing)
    got = rpc.read_listing(stub, k("l-6ps"), CHECKER)
    assert got == {"key": k("l-6ps"), "creator": WALLET, "owner": WALLET, "expires": 0x46a1d0, "run": k("6ps-fast"),
                   "game": "MDGP", "season": 1, "frames": 6170, "log_h": h("6ps-fast"), "price": "0.1",
                   "seller": "3f9a0c21d4e5b6a7", "book": "ANY-6PS", "label": None, "human": True, "pay_to": None,
                   "hcs": None}
    (_, (q1, o1), _), (_, (q2, o2), _), (_, (q3, o3), _) = stub.requests
    assert q1 == rpc.q6_listing(k("l-6ps")) and o1["limit"] == "0x1"           # whoever created it...
    assert q2 == rpc.q_stamp_for_run(k("6ps-fast"), CHECKER) and o2["limit"] == "0x1"   # ...then its run's stamp
    assert q3 == rpc.q6(rpc.RUN_SCHEMA, k("6ps-fast"), WALLET)                 # ...and the run, which must count
    assert "hcs" in o1["select"]["attributes"] and o1["select"]["owner"] and o3["select"]["owner"]


def _with_pay_to(value, kind="str"):
    listing = next(e for e in entities(Q2_PAGE) if e["key"] == k("l-6ps"))
    listing["attributes"].append({"name": "pay_to", "type": kind, "value": value})
    return listing


def test_a_listing_names_the_account_it_pays_when_it_has_one():
    """pay_to is optional: rows written before Hedera have none (listed, not for sale) and still read."""
    listing = _with_pay_to("0.0.5123456")
    assert rpc.read_listing(_listed(listing), k("l-6ps"), CHECKER)["pay_to"] == "0.0.5123456"
    rows, _, _ = rpc.read_board(StubRpc(_fixture_stamps(), Q1_PAGE, page(listing, block="0x3fe91")), "MDGP", 1,
                                CHECKER)
    assert next(r for r in rows if r.key == k("6ps-fast")).pay_to == "0.0.5123456"
    rows, _, _ = rpc.read_board(StubRpc(_fixture_stamps(), Q1_PAGE, Q2_PAGE), "MDGP", 1, CHECKER)
    assert [(r.listing is not None, r.pay_to) for r in rows if r.book == "ANY-6PS"] == [(True, None), (False, None)]


@pytest.mark.parametrize("value, kind", [("0x5B38Da6a701c568545dCfcB03FcB875f56beddC4", "str"), ("0.0.", "str"),
                                         ("0.0.12345678901", "str"), ("1.2.3", "str"), ("0.0.5 ", "str"),
                                         ("0.0.5123456", "key"), ("0x4e2d40", "u64")])
def test_a_listing_naming_an_account_x402_cannot_pay_is_a_misfit(value, kind):
    assert rpc.decode_listings([_with_pay_to(value, kind)], None, WALLET) == ([], 1)


def _with_hcs(value, kind="str"):
    listing = _with_pay_to("0.0.5123456")
    listing["attributes"].append({"name": "hcs", "type": kind, "value": value})
    return listing


def test_a_listing_names_its_hedera_listing_message_and_a_misfit_one_is_left_off():
    """hcs ("<topic>/<seq>": the listing's LISTING message on Hedera) is optional and read leniently: one in any other
    form is left off and the listing kept, since it names a record, never who is paid."""
    listing = _with_hcs("0.0.11332437/41")
    assert rpc.read_listing(_listed(listing), k("l-6ps"), CHECKER)["hcs"] == "0.0.11332437/41"
    rows, _, _ = rpc.read_board(StubRpc(_fixture_stamps(), Q1_PAGE, page(listing, block="0x3fe91")), "MDGP", 1,
                                CHECKER)
    assert next(r for r in rows if r.key == k("6ps-fast")).hcs == "0.0.11332437/41"
    rows, _, _ = rpc.read_board(StubRpc(_fixture_stamps(), Q1_PAGE, Q2_PAGE), "MDGP", 1, CHECKER)
    assert all(r.hcs is None for r in rows)                             # listings written before it: none
    for value, kind in (("0.0.11332437", "str"), ("0.0.1/x", "str"), ("1.2.3/4", "str"), ("0.0.1/41/2", "str"),
                        ("0.0.1/" + "9" * 21, "str"), ("0.0.1/41 ", "str"), ("0x29", "u64")):
        (got,), dropped = rpc.decode_listings([_with_hcs(value, kind)], None, WALLET)
        assert dropped == 0 and got["hcs"] is None and got["pay_to"] == "0.0.5123456", (value, kind)


def test_a_listing_that_is_gone_or_does_not_count_is_none():
    stub = StubRpc(page())
    assert rpc.read_listing(stub, k("l-6ps"), CHECKER) is None and len(stub.requests) == 1
    lookalike = next(e for e in entities(Q2_PAGE) if e["creator"] == STRANGER)       # its run has no stamp
    assert rpc.read_listing(StubRpc(page(lookalike), page()), lookalike["key"], CHECKER) is None
    other = next(e for e in entities(Q2_PAGE) if e["key"] == k("l-k2p"))
    assert rpc.read_listing(StubRpc(page(other)), k("l-6ps"), CHECKER) is None     # a row for another key
    mine = next(e for e in entities(Q2_PAGE) if e["key"] == k("l-6ps"))
    stranger = dict(copy.deepcopy(mine), creator=STRANGER, owner=STRANGER)   # a stranger's copy of a stamped run's
    assert rpc.read_listing(_listed(stranger), k("l-6ps"), CHECKER) is None


def test_a_run_by_its_stamp_then_pinned_to_the_wallet_it_names():
    stub = StubRpc(page(_fast_stamp()), page(_good_run()))
    got = rpc.read_run(stub, k("6ps-fast"), CHECKER)
    assert got["key"] == k("6ps-fast") and got["frames"] == 6170 and got["log_h"] == h("6ps-fast")
    assert (got["owner"], got["stamp"]) == (WALLET, k("stamp:" + k("6ps-fast")))
    (_, (q1, o1), _), (_, (q2, o2), _) = stub.requests
    assert q1 == rpc.q_stamp_for_run(k("6ps-fast"), CHECKER) and q2 == rpc.q6(rpc.RUN_SCHEMA, k("6ps-fast"), WALLET)
    assert o1["limit"] == o2["limit"] == "0x1"
    assert "log" not in o2["select"]["attributes"] and "log_enc" not in o2["select"]["attributes"]
    assert o2["select"]["owner"] and "owner" not in o1["select"]


def test_a_run_no_stamp_names_or_that_disagrees_is_none():
    stub = StubRpc(page())
    assert rpc.read_run(stub, k("6ps-fast"), CHECKER) is None and len(stub.requests) == 1   # no stamp: no run read
    assert rpc.read_run(StubRpc(page(_fast_stamp()), page()), k("6ps-fast"), CHECKER) is None
    slow = stamp(_good_run(), frames=hex(6100))
    assert rpc.read_run(StubRpc(page(slow), page(_good_run())), k("6ps-fast"), CHECKER) is None
    theirs = dict(_good_run(), creator=STRANGER, owner=STRANGER)         # a node that skipped the pin
    assert rpc.read_run(StubRpc(page(_fast_stamp()), page(theirs)), k("6ps-fast"), CHECKER) is None


# ---- the transport: JSON-RPC over HTTP, no proxy --------------------------------------------------------------------

class _Node(BaseHTTPRequestHandler):
    bodies = []
    agents = []
    reply = {"jsonrpc": "2.0", "id": 1, "result": {"data": [], "blockNumber": "0x10"}}
    status = 200

    def log_message(self, *args):
        pass

    def do_POST(self):
        type(self).bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        type(self).agents.append(self.headers.get("User-Agent", ""))
        raw = json.dumps(type(self).reply).encode()
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def node(monkeypatch):
    monkeypatch.setattr(_Node, "bodies", [])
    monkeypatch.setattr(_Node, "agents", [])
    monkeypatch.setattr(_Node, "status", 200)
    monkeypatch.setattr(_Node, "reply", {"jsonrpc": "2.0", "id": 1, "result": {"data": [], "blockNumber": "0x10"}})
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
    assert first["params"][0] == rpc.q_stamps("MDGP", 1, CHECKER) and first["params"][1]["limit"] == "0x64"


def test_the_transport_names_the_console_not_python_on_every_read(node):
    """Rabdi's RPC sits behind Cloudflare, which answers Python's default User-Agent (Python-urllib/3.x) with 403. A
    board read is several requests (the stamps, then each stamped wallet's runs and listings): every one names the
    console."""
    _Node.reply = page(_fast_stamp(), block="0x10")
    rpc.read_board(rpc.rpc_transport(node), "MDGP", 1, CHECKER)
    rpc.read_run(rpc.rpc_transport(node), k("6ps-fast"), CHECKER)
    assert len(_Node.agents) == 5 and set(_Node.agents) == {rpc.USER_AGENT}
    assert not rpc.USER_AGENT.lower().startswith("python")


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


# ---- splits on run rows, label listings (the house's BOT ghosts) ----------------------------------------------------

def _with_splits(*laps, kind="lap", frames=None, typed="u64"):
    """The 6ps-fast run (6170 frames) with s1..sN and split_kind, frames set to their sum unless given."""
    run = _good_run()
    for i, lap in enumerate(laps, start=1):
        run["attributes"].append({"name": f"s{i}", "type": typed, "value": hex(lap) if typed == "u64" else lap})
    if kind is not None:
        run["attributes"].append({"name": "split_kind", "type": "str", "value": kind})
    _attr(run, "frames")["value"] = hex(frames if frames is not None else sum(laps))
    return run


def test_a_runs_lap_times_come_with_it():
    (row,), dropped = rpc.decode_runs([_with_splits(2140, 2165, 2109)], "MDGP", WALLET)
    assert dropped == 0 and row["splits"] == (2140, 2165, 2109) and row["frames"] == 6414
    assert rpc.run_row(row).splits == (2140, 2165, 2109)
    (old,), _ = rpc.decode_runs([_good_run()], "MDGP", WALLET)        # a row from before splits: still loads
    assert old["splits"] is None and rpc.run_row(old).splits is None


def test_a_stamp_carries_the_laps_it_copied_and_they_must_be_the_runs():
    run = _with_splits(2140, 2165, 2109)
    (st,), _ = rpc.decode_stamps([stamp(run)], None, CHECKER)
    (row,), _ = rpc.decode_runs([run], None, None)
    assert st["splits"] == (2140, 2165, 2109) and rpc.run_mismatch(st, row) is None
    (bare,), _ = rpc.decode_stamps([stamp(run, s1=None, s2=None, s3=None, split_kind=None)], None, CHECKER)
    assert rpc.run_mismatch(bare, row) == "splits"


def _gapped():
    """s1 and s3 with no s2, frames their sum: not contiguous."""
    run = _with_splits(2140, 2165, 2109, frames=4249)
    _without("s2")(run)
    return run


@pytest.mark.parametrize("why, run", [
    ("they do not add up to its frames", lambda: _with_splits(2140, 2165, 2109, frames=6415)),
    ("a lap of 0", lambda: _with_splits(2140, 0, 4274)),
    ("not contiguous from s1", _gapped),
    ("another kind", lambda: _with_splits(2140, 2165, 2109, kind="section")),
    ("no kind", lambda: _with_splits(2140, 2165, 2109, kind=None)),
    ("a split typed as a string", lambda: _with_splits(2140, 2165, 2109, typed="str")),
])
def test_lap_times_that_do_not_check_out_are_left_off_and_the_run_kept(why, run):
    (row,), dropped = rpc.decode_runs([run()], "MDGP", WALLET)
    assert dropped == 0 and row["splits"] is None, why


def _house_listing(**over):
    """A label listing: the house's BOT-A2, paid to the house account, never human."""
    listing = next(e for e in entities(Q2_PAGE) if e["key"] == k("l-6ps"))
    listing["attributes"] = [a for a in listing["attributes"] if a["name"] != "book"]
    listing["attributes"] += [{"name": "label", "type": "str", "value": "BOT-A2"},
                              {"name": "pay_to", "type": "str", "value": "0.0.7700001"}]
    _attr(listing, "human")["value"] = False
    for name, value in over.items():
        _attr(listing, name)["value"] = value
    return listing


def test_a_label_listing_decodes_and_one_with_both_or_neither_name_or_an_open_tier_label_is_dropped():
    (got,), dropped = rpc.decode_listings([_house_listing()], None, WALLET)
    assert dropped == 0 and (got["label"], got["book"], got["human"], got["pay_to"]) == ("BOT-A2", None, False,
                                                                                         "0.0.7700001")
    both = _house_listing()
    both["attributes"].append({"name": "book", "type": "str", "value": "ANY-6PS"})
    neither = _house_listing()
    neither["attributes"] = [a for a in neither["attributes"] if a["name"] != "label"]
    team = _house_listing(label="TEAM")
    assert rpc.decode_listings([both, neither, team], None, WALLET) == ([], 3)


def test_a_bot_run_is_never_human():
    """A run with no record book has nobody's World ID behind it: never HUMAN, whatever its row says."""
    run = _good_run()
    run["attributes"] = [a for a in run["attributes"] if a["name"] not in ("book", "credential")]
    run["attributes"].append({"name": "label", "type": "str", "value": "BOT-A2"})
    (row,), _ = rpc.decode_runs([run], "MDGP", WALLET)
    out = rpc.run_row(row)
    assert (out.label, out.book, out.human, out.credential) == ("BOT-A2", None, False, None)
