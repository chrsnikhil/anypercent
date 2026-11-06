"""Arkiv's board, read straight from the public Rabdi RPC: standard library only (urllib JSON-RPC), no access key, no
proxy, a 3 s timeout. The console's board and its listing check come from here; no backend of ours sits in the read
path, so the board survives the laptop being off. Callers run it on a background thread.

Console-owned records (docs/superpowers/specs/2026-11-06-arkiv-console-owned-design.md): each console's own wallet
creates its run and listing rows (the house's wallet the BOT ones), and our checker writes a separate stamp
(anypercent.stamp) naming each run it replayed and the wallet (`console`) that owns it. A board is read as the service
and the web board read it: the checker's stamps first (pinned to the checker's `$creator`), then the runs and listings
of every wallet those stamps name (Q1 and Q2 pinned to that wallet). join_board is the readers' one rule (the
bridge's board.ts, line for line): a run counts only when a checker stamp names it, the run's creator and its current
owner are both the stamp's `console` (a read-only entity can still be transferred, so every run and listing read
selects its owner; one whose owner is not returned does not count) and the columns the stamp copied agree (game,
season, frames, log_h, book or label, human, the lap splits); a listing counts only when its creator and owner are that
same console, its `run` names a run that counts and its game, season, frames, log_h, book or label and human are the
run's. Anything else is dropped and counted; a stamped run whose listing expired still ranks, as not for sale. Two
stamps of one log count once (the first, which on a board read is the fastest). A look-alike row (any stranger's
wallet, any book name) has no stamp, so it never counts, even from a node that skipped a pin.

The query strings are the same characters the service and the web board send (apps/world-bridge src/arkiv/queries.ts:
q1Stamps, q1Board, q2Listings, q6Run, qStampForRun, q6ListingByKey). Rows are checked here, never trusted: one whose
`arkiv.schema` or creator is not the expected one, or that lacks a column or carries one of the wrong type, is
dropped and counted. An address goes into a query in its EIP-55 form, as the service and the web board write it (the
node refuses a mixed-case address whose checksum is wrong, so it is computed here, never copied); keys go in
lowercase.

A run row may carry its lap times (s1..s4, split_kind "lap"): kept only when they are contiguous from s1, every one
above 0, and add up to the run's frames; otherwise the run is kept without them. A run, a stamp and a listing each name
their runner by exactly one of book (a person's record book) and label (the house's BOT ghost, HOUSE_LABEL); one with
both, neither, or any other label is dropped (the open tier is retired). A run with no record book is never HUMAN:
nobody's World ID stands behind it. A listing's LISTING message on Hedera (hcs, "<topic>/<seq>") is kept only in that
form; any other leaves it off, never the listing. No reader selects a run's log: every ghost is a listed one, its log
encrypted on the row and served by the service against a payment."""
import functools
import json
import re
import time
import urllib.request

from arca_launcher.handler.sponsors import HCS_MSG, HOUSE_LABEL, PAY_TO, RunRow

RABDI_RPC = "https://rpc.rabdi.db-chain.testnet.arkiv.network"   # the public endpoint: no key on the console
RUN_SCHEMA, LISTING_SCHEMA, STAMP_SCHEMA = "anypercent.run", "anypercent.listing", "anypercent.stamp"
PAGE = 100                    # one page: runners beyond the top 100 runs are not shown
TIMEOUT_S = 3.0
MAX_REPLY = 1 << 20           # a page of 100 rows is far below this
TEXT_MAX = 64                 # bytes of any text column (a title, a book, a label)
YIELD_EVERY = 20              # rows decoded between letting the frame loop have the GIL (a Pi decodes slowly)

_GAME = re.compile(r"[A-Z0-9]{4}")
_ADDR = re.compile(r"0x[0-9a-f]{40}")
_KEY = re.compile(r"0x[0-9a-f]{64}")
_HASH = re.compile(r"[0-9a-f]{64}")
_QTY = re.compile(r"0x[0-9a-fA-F]{1,64}")
_DEC = re.compile(r"[0-9]{1,30}(\.[0-9]{1,18})?")
_BYTES = re.compile(r"0x(?:[0-9a-fA-F]{2})*")
_BAD = object()

# The columns each reader selects (besides arkiv.schema), with their Arkiv types; never `log`/`log_enc`.
RUN_COLUMNS = {"game": "str", "title": "str", "frames": "u64", "runner": "str", "book": "str", "label": "str",
               "human": "bool", "credential": "str", "log_h": "str", "rules": "u64"}
RUN_OPTIONAL = frozenset({"book", "label", "credential"})
# A run's lap times: selected with it, and read leniently (one that does not check out is left off, the run kept).
SPLIT_COLUMNS = {"s1": "u64", "s2": "u64", "s3": "u64", "s4": "u64", "split_kind": "str"}
SPLIT_KIND = "lap"
# Read leniently with a run besides its laps: its season, always compared with its stamp's (none never matches).
RUN_LENIENT = dict(SPLIT_COLUMNS, season="i32")
LISTING_COLUMNS = {"run": "key", "game": "str", "season": "i32", "frames": "u64", "log_h": "str", "price": "dec",
                   "seller": "str", "book": "str", "label": "str", "human": "bool", "pay_to": "str"}
# A listing written before Hedera (or with Hedera off) has no pay_to: it is on the board, but not for sale. It names
# exactly one of book and label.
LISTING_OPTIONAL = frozenset({"pay_to", "book", "label"})
# A listing's LISTING message on Hedera ("<topic>/<seq>"): selected with it and read leniently, since it names a
# record, never who is paid (one in any other form is left off, the listing kept).
LISTING_LENIENT = {"hcs": "str"}
# The checker's stamp of a run: the run it names, the wallet that owns that run (`console`, lowercase), and the
# columns it copied from the run (its lap times read leniently and compared as the run's are read: both the laps that
# check out, or both none).
STAMP_COLUMNS = {"run": "key", "console": "str", "game": "str", "season": "i32", "frames": "u64", "log_h": "str",
                 "book": "str", "label": "str", "human": "bool"}
STAMP_OPTIONAL = frozenset({"book", "label"})
# What a stamp copied from its run and must still say: compared one by one, then the lap columns.
_COPIED = ("game", "frames", "log_h", "book", "label", "human")


class RpcError(Exception):
    """No usable reply: no answer, an HTTP or RPC error, or a reply not in arkiv_query's shape."""


# ---- what may go into a query --------------------------------------------------------------------------------------

_RC = (0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000, 0x000000000000808B,
       0x0000000080000001, 0x8000000080008081, 0x8000000000008009, 0x000000000000008A, 0x0000000000000088,
       0x0000000080008009, 0x000000008000000A, 0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
       0x8000000000008003, 0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
       0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008)
_ROT = ((0, 36, 3, 41, 18), (1, 44, 10, 45, 2), (62, 6, 43, 15, 61), (28, 55, 25, 21, 56), (27, 20, 39, 8, 14))
_LANE = (1 << 64) - 1


def _rol(v, n):
    return ((v << n) | (v >> (64 - n))) & _LANE


def keccak256(data):
    """Keccak-256 as Ethereum uses it (not SHA3-256: the padding differs), which hashlib does not have."""
    rate = 136
    msg = bytearray(data) + b"\x01"
    msg += bytes(-len(msg) % rate)
    msg[-1] |= 0x80
    a = [[0] * 5 for _ in range(5)]
    for off in range(0, len(msg), rate):
        for i in range(rate // 8):
            a[i % 5][i // 5] ^= int.from_bytes(msg[off + 8 * i:off + 8 * i + 8], "little")
        for rc in _RC:
            c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
            d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
            b = [[0] * 5 for _ in range(5)]
            for x in range(5):
                for y in range(5):
                    b[y][(2 * x + 3 * y) % 5] = _rol(a[x][y] ^ d[x], _ROT[x][y])
            a = [[b[x][y] ^ (~b[(x + 1) % 5][y] & b[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
            a[0][0] ^= rc
    return b"".join(a[i % 5][i // 5].to_bytes(8, "little") for i in range(4))


@functools.lru_cache(maxsize=32)
def eip55(address):
    """An address in its EIP-55 mixed-case form (a letter is upper case where its nibble of the hash is 8 or more)."""
    low = checker_address(address)[2:]
    digest = keccak256(low.encode("ascii")).hex()
    return "0x" + "".join(ch.upper() if ch.isalpha() and int(digest[i], 16) >= 8 else ch for i, ch in enumerate(low))


def checker_address(text):
    """An address as the console compares it, all lowercase (a query takes it as eip55()). ValueError unless it is 0x
    and 40 hex digits."""
    s = text.strip().lower() if isinstance(text, str) else ""
    if not _ADDR.fullmatch(s):
        raise ValueError(f"not an address: {text!r}")
    return s


def entity_key(text):
    """An entity key as a query takes it, all lowercase. ValueError unless it is 0x and 64 hex digits."""
    s = text.strip().lower() if isinstance(text, str) else ""
    if not _KEY.fullmatch(s):
        raise ValueError(f"not an entity key: {text!r}")
    return s


def game_id(text):
    """An arcade id (SHIP, MDGP, ...). ValueError for anything else: nothing but an id reaches a query."""
    if not (isinstance(text, str) and _GAME.fullmatch(text)):
        raise ValueError(f"not an arcade id: {text!r}")
    return text


def _season(season):
    if type(season) is not int or not -2 ** 31 <= season < 2 ** 31:
        raise ValueError(f"not an i32 season: {season!r}")
    return season


def q_stamps(game, season, checker):
    """The checker's stamps of the game this season, fastest first: the board before the join (q1Stamps)."""
    return (f"arkiv.schema = str('{STAMP_SCHEMA}') AND game = str('{game_id(game)}') AND season = i32("
            f"{_season(season)}) AND $creator = addr({eip55(checker)}) ORDER BY frames:u64 ASC")


def q1(game, season, owner):
    """The game's runs this season that owner (a wallet a stamp names) created, fastest first (Q1, q1Board)."""
    return (f"arkiv.schema = str('{RUN_SCHEMA}') AND game = str('{game_id(game)}') AND season = i32({_season(season)})"
            f" AND $creator = addr({eip55(owner)}) ORDER BY frames:u64 ASC")


def q2(game, season, owner):
    """The game's live listings this season that owner created, fastest first (Q2, q2Listings)."""
    return (f"arkiv.schema = str('{LISTING_SCHEMA}') AND game = str('{game_id(game)}') AND season = i32("
            f"{_season(season)}) AND $creator = addr({eip55(owner)}) ORDER BY frames:u64 ASC")


def q6(schema, key, owner):
    """One row by its key that owner created (Q6): a run, pinned to the wallet its stamp names (q6Run)."""
    return (f"arkiv.schema = str('{schema}') AND $key = key({entity_key(key)})"
            f" AND $creator = addr({eip55(owner)})")


def q_stamp_for_run(key, checker):
    """The checker's stamp of one run, if any (qStampForRun)."""
    return (f"arkiv.schema = str('{STAMP_SCHEMA}') AND run = key({entity_key(key)})"
            f" AND $creator = addr({eip55(checker)})")


def q6_listing(key):
    """One listing by its key, whoever created it (q6ListingByKey): its creator is then compared with the wallet its
    run's stamp names."""
    return f"arkiv.schema = str('{LISTING_SCHEMA}') AND $key = key({entity_key(key)})"


def _select(columns, owner=False):
    """What a reader asks for: the key, its creator (checked again here) and expiry, its current owner (owner: a run
    or a listing, whose owner must still be the wallet its stamp names), and the named columns."""
    return dict({"key": True, "creator": True, "expiresAt": True}, **({"owner": True} if owner else {}),
                attributes=dict({"arkiv.schema": True}, **{name: True for name in columns}))


# ---- the transport and one query ----------------------------------------------------------------------------------

# Rabdi's RPC sits behind Cloudflare, which refuses Python's default User-Agent (Python-urllib/3.x) with a 403: the
# console names itself instead, on every request.
USER_AGENT = "AnyPercent-Console/1.0 (+https://github.com/chrsnikhil/anypercent)"


def rpc_transport(rpc_url):
    """(method, params, timeout_s) -> the node's JSON reply; raises on anything else (no answer, an HTTP error, a
    reply too large or not JSON). No proxy: an HTTP_PROXY left set on the console is never used."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def send(method, params, timeout_s):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
        request = urllib.request.Request(rpc_url, data=body, method="POST",
                                         headers={"Content-Type": "application/json", "Accept": "application/json",
                                                  "User-Agent": USER_AGENT})
        with opener.open(request, timeout=timeout_s) as reply:
            raw = reply.read(MAX_REPLY + 1)
        if len(raw) > MAX_REPLY:
            raise RpcError("reply too large")
        return json.loads(raw.decode("utf-8"))
    return send


def query(send, text, select, limit=PAGE):
    """One arkiv_query page: (its rows as the node sent them, the block it was read at). RpcError when there is no
    usable reply."""
    try:
        reply = send("arkiv_query", [text, {"select": select, "limit": hex(limit)}], TIMEOUT_S)
    except Exception as e:                      # no answer, an HTTP error status, not JSON
        raise RpcError(type(e).__name__) from e
    result = reply.get("result") if isinstance(reply, dict) else None
    if not isinstance(result, dict):
        error = reply.get("error") if isinstance(reply, dict) else None
        message = error.get("message") if isinstance(error, dict) else None
        raise RpcError(str(message)[:200] if message else "not a JSON-RPC result")
    data, block = result.get("data"), _value("u64", result.get("blockNumber"))
    if not isinstance(data, list) or block is _BAD:
        raise RpcError("not an arkiv_query reply")
    return data, block


# ---- decoding and checking rows -------------------------------------------------------------------------------------

def _value(kind, value):
    """value decoded from kind's JSON encoding (u64 a 0x quantity, i32 a number, bool bare, dec and str strings, key,
    addr and bytes 0x hex); _BAD when it is not in that encoding."""
    if kind in ("str", "dec"):
        if not isinstance(value, str) or (kind == "dec" and not _DEC.fullmatch(value)):
            return _BAD
        return value
    if kind == "bool":
        return value if isinstance(value, bool) else _BAD
    if kind == "i32":
        return value if type(value) is int and -2 ** 31 <= value < 2 ** 31 else _BAD
    if kind in ("u64", "u256"):
        if not (isinstance(value, str) and _QTY.fullmatch(value)):
            return _BAD
        n = int(value, 16)
        return n if kind == "u256" or n < 2 ** 64 else _BAD
    if kind in ("key", "addr"):
        s = value.lower() if isinstance(value, str) else ""
        return s if (_KEY if kind == "key" else _ADDR).fullmatch(s) else _BAD
    if kind == "bytes":
        return bytes.fromhex(value[2:]) if isinstance(value, str) and _BYTES.fullmatch(value) else _BAD
    return _BAD


def _text_ok(text):
    """Text the console may show: one line, not empty, within TEXT_MAX bytes."""
    return (0 < len(text.encode("utf-8")) <= TEXT_MAX and text.strip() == text
            and not any(ord(ch) < 32 or ord(ch) == 127 for ch in text))


def _row(entity, schema, columns, optional, creator, lenient=None):
    """entity's key, creator, current owner (None when the node did not give one), expiry and columns, decoded; None
    when it is not a row of schema that creator created (creator None: any wallet), with every required column present
    in its own type. lenient: more columns, each its value or None when absent or not in its type (never a reason to
    drop the row)."""
    if not isinstance(entity, dict):
        return None
    key, made_by = _value("key", entity.get("key")), _value("addr", entity.get("creator"))
    expires = _value("u64", entity.get("expiresAt"))
    if _BAD in (key, made_by, expires) or (creator is not None and made_by != creator):
        return None
    attrs = entity.get("attributes")
    if not isinstance(attrs, list):
        return None
    got = {}
    for attr in attrs:
        if not isinstance(attr, dict) or not isinstance(attr.get("name"), str) or attr["name"] in got:
            return None
        got[attr["name"]] = (attr.get("type"), attr.get("value"))
    if got.get("arkiv.schema") != ("str", schema):
        return None
    owner = _value("addr", entity.get("owner"))
    out = {"key": key, "creator": made_by, "owner": None if owner is _BAD else owner, "expires": expires}
    for name, kind in columns.items():
        if name not in got:
            if name not in optional:
                return None
            out[name] = None
            continue
        typed, raw = got[name]
        if kind == "key" and typed == "bytes32":
            typed = "key"           # Rabdi labels a key column "bytes32" (the SDK's reader takes it as a key too)
        value = _value(kind, raw) if typed == kind else _BAD
        if value is _BAD or (kind == "str" and not _text_ok(value)):
            return None
        out[name] = value
    if not _HASH.fullmatch(out.get("log_h") or ""):
        return None
    for name, kind in (lenient or {}).items():
        typed, raw = got.get(name, (None, None))
        value = _value(kind, raw) if typed == kind else _BAD
        out[name] = None if value is _BAD or (kind == "str" and not _text_ok(value)) else value
    return out


def _named(row):
    """Exactly one of book and label, and a label only as the house's BOT ghosts are named (the open tier is
    retired)."""
    book, label = row.get("book"), row.get("label")
    return (book is None) != (label is None) and (label is None or HOUSE_LABEL.fullmatch(label) is not None)


def _creator(creator):
    return None if creator is None else checker_address(creator)


def _splits(row):
    """The run's lap times as a tuple, or None when it has none that check out: s1.. contiguous, none 0, of kind
    "lap", adding up to its frames."""
    laps = []
    for name in ("s1", "s2", "s3", "s4"):
        if row.get(name) is None:
            break
        laps.append(row[name])
    rest = [name for name in ("s1", "s2", "s3", "s4")[len(laps):] if row.get(name) is not None]
    if not laps or rest or row.get("split_kind") != SPLIT_KIND or 0 in laps or sum(laps) != row["frames"]:
        return None
    return tuple(laps)


def _yield(i):
    """Every YIELD_EVERY rows, let another thread take the GIL: the board is decoded on the worker, and the frame loop
    must never wait behind a whole page (a slice of 20 rows is well under a millisecond, even on a Pi)."""
    if i and i % YIELD_EVERY == 0:
        time.sleep(0)


def decode_runs(data, game, creator, schema=RUN_SCHEMA):
    """(the valid run rows of data, as dicts in data's order, how many were dropped). game None: any game; creator
    None: any wallet (join_board then compares it with the stamp's console)."""
    creator = _creator(creator)
    rows, dropped = [], 0
    for i, entity in enumerate(data):
        _yield(i)
        row = _row(entity, schema, RUN_COLUMNS, RUN_OPTIONAL, creator, lenient=RUN_LENIENT)
        if row is None or (game is not None and row["game"] != game) or not _named(row):
            dropped += 1
            continue
        row["splits"] = _splits(row)
        rows.append(row)
    return rows, dropped


def decode_listings(data, game, creator, season=None, schema=LISTING_SCHEMA):
    """(the valid listing rows of data, as dicts in data's order, how many were dropped). game, season, creator None:
    any. A pay_to that is not a plain `0.0.N` account makes the row a misfit: PB never pays an account it cannot read.
    An hcs that is not "<topic>/<seq>" is only left off (None)."""
    creator = _creator(creator)
    rows, dropped = [], 0
    for i, entity in enumerate(data):
        _yield(i)
        row = _row(entity, schema, LISTING_COLUMNS, LISTING_OPTIONAL, creator, lenient=LISTING_LENIENT)
        if (row is None or game not in (None, row["game"]) or season not in (None, row["season"]) or not _named(row)
                or (row["pay_to"] is not None and not PAY_TO.fullmatch(row["pay_to"]))):
            dropped += 1
            continue
        if row["hcs"] is not None and not HCS_MSG.fullmatch(row["hcs"]):
            row["hcs"] = None
        rows.append(row)
    return rows, dropped


def decode_stamps(data, game, checker, season=None, schema=STAMP_SCHEMA):
    """(the valid stamps of data the checker created, as dicts in data's order, how many were dropped). game, season
    None: any. A stamp that names no wallet as its `console` (0x and 40 lowercase hex) is a misfit."""
    checker = checker_address(checker)
    rows, dropped = [], 0
    for i, entity in enumerate(data):
        _yield(i)
        row = _row(entity, schema, STAMP_COLUMNS, STAMP_OPTIONAL, checker, lenient=SPLIT_COLUMNS)
        if (row is None or game not in (None, row["game"]) or season not in (None, row["season"]) or not _named(row)
                or not _ADDR.fullmatch(row["console"])):
            dropped += 1
            continue
        row["splits"] = _splits(row)
        rows.append(row)
    return rows, dropped


# ---- the readers' rule ---------------------------------------------------------------------------------------------

def run_mismatch(stamp, run):
    """Why this run does not count under this stamp (a few words), or None when it does: the stamp names it, its
    creator and its current owner are the stamp's console, and every column the stamp copied agrees as written (the
    laps as read: the same laps that check out, or none on both). The bridge's board.ts runMismatch."""
    if run["key"] != stamp["run"]:
        return "another run"
    if run["creator"] != stamp["console"]:
        return "created by another wallet than the stamp names"
    if run.get("owner") != stamp["console"]:
        return "owned by another wallet than the stamp names"
    if run.get("season") != stamp["season"]:
        return "season"
    for name in _COPIED:
        if run[name] != stamp[name]:
            return name
    if run.get("splits") != stamp.get("splits"):
        return "splits"
    return None


def listing_mismatch(stamp, listing):
    """Why this listing does not count for the run this stamp names, or None when it does: it names that run, its
    creator and current owner are the run's owner (the stamp's console), and its game, season, frames, log_h, book or
    label and human are the run's. The bridge's board.ts listingMismatch."""
    if listing["run"] != stamp["run"]:
        return "another run"
    if listing["creator"] != stamp["console"]:
        return "created by another wallet than the run's"
    if listing.get("owner") != stamp["console"]:
        return "owned by another wallet than the run's"
    if listing["season"] != stamp["season"]:
        return "season"
    for name in _COPIED:
        if listing[name] != stamp[name]:
            return name
    return None


def join_board(stamps, runs, listings):
    """The readers' one rule over decoded rows: ([(stamp, run)] that count, in the stamps' order; {run key: its first
    listing that counts}; how many stamps and listings did not count). A run no stamp names is simply not on the board
    (not counted); a stamp whose run is missing or disagrees, a second stamp of one log or one run, and a listing that
    is not its stamped run's owner's are."""
    by_key = {}
    for run in runs:
        by_key.setdefault(run["key"], run)
    kept, logs, named, dropped = [], set(), set(), 0
    for stamp in stamps:
        run = by_key.get(stamp["run"])
        if (stamp["log_h"] in logs or stamp["run"] in named or run is None
                or run_mismatch(stamp, run) is not None):
            dropped += 1
            continue
        logs.add(stamp["log_h"])
        named.add(stamp["run"])
        kept.append((stamp, run))
    stamp_of = {stamp["run"]: stamp for stamp, _ in kept}
    offers = {}
    for listing in listings:
        stamp = stamp_of.get(listing["run"])
        if stamp is None or listing_mismatch(stamp, listing) is not None:
            dropped += 1
            continue
        offers.setdefault(listing["run"], listing)
    return kept, offers, dropped


def run_row(row, listing=None):
    """A decoded run (and the live listing that offers it, if any) as the board's RunRow. A run with no record book
    is never HUMAN, whatever its row says: nobody's World ID stands behind it."""
    human = row["human"] and row["book"] is not None
    return RunRow(key=row["key"], game=row["game"], title=row["title"], frames=row["frames"], runner=row["runner"],
                  book=row["book"], label=row["label"], human=human, credential=row["credential"] if human else None,
                  log_h=row["log_h"], rules=row["rules"], expires_block=row["expires"],
                  listing=listing["key"] if listing else None, price=listing["price"] if listing else None,
                  pay_to=listing["pay_to"] if listing else None,
                  splits=row.get("splits"), hcs=listing.get("hcs") if listing else None)


# ---- the readers ---------------------------------------------------------------------------------------------------

_STAMP_SELECT = dict(STAMP_COLUMNS, **SPLIT_COLUMNS)
_RUN_SELECT = dict(RUN_COLUMNS, **RUN_LENIENT)
_LISTING_SELECT = dict(LISTING_COLUMNS, **LISTING_LENIENT)


def read_board(send, game, season, checker):
    """(rows, block, dropped): the game's stamped runs this season as RunRows, fastest first (the checker's stamps,
    then each stamped wallet's runs and listings, joined by join_board), each with its live listing when one counts;
    the latest block of the reads; how many rows were dropped (misfits, stamps and listings that do not count).
    RpcError when any read fails."""
    checker = checker_address(checker)
    data, block = query(send, q_stamps(game, season, checker), _select(_STAMP_SELECT))
    stamps, dropped = decode_stamps(data, game, checker, season)
    runs, listings = [], []
    for owner in dict.fromkeys(stamp["console"] for stamp in stamps):
        data, at = query(send, q1(game, season, owner), _select(_RUN_SELECT, owner=True))
        got, misfit = decode_runs(data, game, None)
        runs += got
        data, listed_at = query(send, q2(game, season, owner), _select(_LISTING_SELECT, owner=True))
        offers, more = decode_listings(data, game, None, season)
        listings += offers
        dropped += misfit + more
        block = max(block, at, listed_at)
    kept, offers, more = join_board(stamps, runs, listings)
    return tuple(run_row(run, offers.get(run["key"])) for _, run in kept), block, dropped + more


def read_stamp(send, run_key, checker):
    """The checker's live stamp of this run, decoded, or None."""
    checker, run_key = checker_address(checker), entity_key(run_key)
    data, _ = query(send, q_stamp_for_run(run_key, checker), _select(_STAMP_SELECT), limit=1)
    stamps, _ = decode_stamps(data, None, checker)
    return next((stamp for stamp in stamps if stamp["run"] == run_key), None)


def read_run(send, key, checker, stamp=None):
    """The live stamped run with this key, decoded with its stamp's key; None when no checker stamp names it, or the
    run is gone, is another wallet's or disagrees with its stamp. stamp: its stamp, already read."""
    key = entity_key(key)
    stamp = stamp if stamp is not None else read_stamp(send, key, checker)
    if stamp is None:
        return None
    data, _ = query(send, q6(RUN_SCHEMA, key, stamp["console"]), _select(_RUN_SELECT, owner=True), limit=1)
    runs, _ = decode_runs(data, None, stamp["console"])
    run = next((row for row in runs if row["key"] == key), None)
    if run is None or run_mismatch(stamp, run) is not None:
        return None
    return dict(run, stamp=stamp["key"])


def read_listing(send, key, checker):
    """The live listing with this key, decoded, only when it counts: its run is stamped by the checker and counts
    (read_run), and the listing is that run's owner's, with the run's columns. None when it is gone or does not
    count."""
    key = entity_key(key)
    data, _ = query(send, q6_listing(key), _select(_LISTING_SELECT, owner=True), limit=1)
    rows, _ = decode_listings(data, None, None)
    listing = next((row for row in rows if row["key"] == key), None)
    if listing is None:
        return None
    stamp = read_stamp(send, listing["run"], checker)
    if stamp is None or listing_mismatch(stamp, listing) is not None:
        return None
    return listing if read_run(send, listing["run"], checker, stamp=stamp) is not None else None
