# Any% on Arkiv: schema

Any% is a handheld speedrun console. Its board lives on Arkiv: one row per checked run, one row per listed ghost. This
file is the entities, the fields we query, who owns them, who can edit, extend or delete them, and when they expire.

- **Network:** Arkiv Rabdi testnet, chain id 7794095 (`0x76edaf`), RPC `https://rpc.rabdi.db-chain.testnet.arkiv.network`.
- **SDK:** `@arkiv-network/sdk` 1.0.1 with `viem` 2.57.16 (writes); raw `arkiv_query` JSON-RPC (every read).
- **Writer (the checker):** `0x3d3260425Cb52F0c6716212274a883337aFa3f63`. It creates every row; every reader pins it.
- **Look-alike demo wallet (the stranger):** `0x6CD1e043820e450A13B3F536F7a90ED2aDCfbCc1`. Its rows must never show.
- **Code:** the schemas are `apps/world-bridge/src/arkiv/schema.ts`; the queries `apps/world-bridge/src/arkiv/queries.ts`.

## Entities

Both are SDK named schemas: every row carries an indexed `arkiv.schema` str with the schema's name, and every query
filters on it. No names, faces, raw World ids, device ids or free text go in either.

### `anypercent.run`: one checked run

Written only after the checker replayed the run's log with the game's own replay tool and got the same time.

| Column | Type | Indexed | Value |
|---|---|---|---|
| `game` | str | yes | Arcade id: `SHIP`, `MDGP`, `RUSH`, `SEGF`, `ZIPG` |
| `title` | str | no | The game's title, as World App showed it in the listing approval (`MARINE DRIVE GP`) |
| `season` | i32 | yes | The season (1) |
| `rules` | u64 | yes | The game's rules version, from the log header |
| `frames` | u64 | yes | The replayed finish time in frames at 60 fps. The sort key |
| `log_h` | str | yes | Lowercase hex SHA-256 of the plain log: dedupe, and the buyer's ghost check |
| `runner` | str | yes | The World bridge's runner id: 16 hex of an HMAC, never a World nullifier. Open tier: an HMAC of `open\|<label>` |
| `book` | str, optional | yes | The record book, `ANY-XXX`. Absent on open-tier rows |
| `label` | str, optional | no | An open-tier row's display name: `TEAM`, or `BOT-A2` for the house's BOT ghosts. Never a person's name |
| `human` | bool | yes | True only when the run's record book was opened with a World ID proof at our bridge. False on open-tier rows |
| `credential` | str, optional | no | What World checked when the book was opened (`Orb`). Absent on open-tier rows |
| `tool` | str | no | The replay tool that checked it: `arcade_replay sha256:<first 12 hex of the binary>` |
| `log` | bytes, optional | no | The plain `.acl` log, on open-tier rows only: anyone can replay it |
| `log_enc` | bytes, optional | no | A listed run's log, encrypted: `nonce(12) \|\| AES-256-GCM ciphertext \|\| tag(16)` |
| `s1`, `s2`, `s3`, `s4` | u64, optional | yes | Split k in frames: MARINE DRIVE GP's lap k. Present for k = 1..n, contiguous from `s1`, adding up to `frames`; the rest absent |
| `split_kind` | str, optional | no | `"lap"`. Present exactly when `s1` is |
| `gen` | str, optional | no | BOT rows only: how the log was made, e.g. `ghostgen v2 seed 0 @<commit>` |

- **Flags:** `readonly: true`, `permissionlessExtension: true`.
- **Expiry:** season end + 30 days (`ExpirationTime.atDate(seasonEnd + 30 d, { atLeast: fromDays(1) })`).
- **Creator and owner:** the checker.
- Exactly one of `log` and `log_enc` is present.
- **Who writes the splits:** the checker, from the game's own `arcade_splits` (built from the same tree as
  `arcade_replay`, installed beside it): the same replay, then `rules_lap_frames(1..3)`. It writes them only when they
  are laps that add up to the replayed time and come from the same replay (the same final hash); anything else writes
  the run without splits, and never fails a write. Rows written before splits still fit, with none. A reader treats
  splits that do not check out (not contiguous, another kind, a zero, another sum) as absent and keeps the row.

### `anypercent.listing`: a World-approved offer of one run's ghost

| Column | Type | Indexed | Value |
|---|---|---|---|
| `run` | key | yes | The run row's `$key` |
| `game` | str | yes | Copied from the run |
| `season` | i32 | yes | Copied |
| `frames` | u64 | yes | Copied, so "the listed ghost just ahead of me" is one query |
| `log_h` | str | yes | Copied; a buyer checks it equals the run's |
| `price` | dec | yes | USDC, `0.1` |
| `seller` | str | yes | The seller's runner id |
| `book` | str, optional | yes | The seller's record book. Absent on the house's listings |
| `label` | str, optional | no | The house's BOT label (`BOT-A2`). Exactly one of `book` and `label` is present; a reader drops a listing with both or neither |
| `human` | bool | yes | Copied (always false on a `label` listing) |
| `pay_to` | str, optional | yes | The seller's Hedera account, `0.0.N`, exactly as World App showed it in the approved listing text ("... for 0.10 USDC to 0.0.N on the public board"). Absent: not for sale |
| `hcs` | str, optional | no | `<topic id>/<sequence number>` of the `LISTING` message on the Hedera market topic: the approved text, word for word, at consensus time. Absent when Hedera was off |

- **Flags:** `readonly: true`, `permissionlessExtension: false`. A listing never outlives its week.
- **Expiry:** 7 days (`ExpirationTime.fromDays(7)`), the console's "Ends in 7 days".
- **Creator and owner:** the checker.

The run and its listing are written in one transaction: `predictEntityKeys` gives the run's key before it exists, so
the listing can carry it.

**Who sets `pay_to` and `hcs`.** The owner registers a book's Hedera account once (`npm run hedera:payto`, which checks on
the Hedera mirror node that the account can take USDC). From then on the console's listing text names it, so the seller
sees it in World App when approving. The checker writes `pay_to` only when the approved text names exactly the book's
registered account, and `hcs` when the record step put that text on the Hedera market topic. Both are optional: rows
written before them still fit the schema, and are on the board but not for sale until relisted. A relist whose `pay_to`
differs from the run's live listing writes the new listing and deletes the old one in the same transaction, so a run has
one listing. A buyer's agent pays only the `pay_to` of a listing row the checker created, never an account named
anywhere else (see the root README, Hedera).

## Three tiers: HUMAN, BOT, OPEN

| Tier | Rows | What stands behind them |
|---|---|---|
| HUMAN | `human` true, a `book`, a `credential` | A record book opened with a World ID proof at our bridge (one per World ID). It does not mean a human pressed every button |
| BOT | `human` false, `label` `BOT-<batch letter><n>`, no book | A program: the route bot of MARINE DRIVE GP slowed down on purpose in chosen laps (`games/marinedrive/dev/ghostgen.py`) |
| OPEN | `human` false, any other `label`, no book | The team's own runs (`npm run arkiv:open-run`) |

**BOT rows** come only from a house batch its owner approved in World App, as a named batch, with this text:
`Publish BOT batch 8477d8: 6 MARINE DRIVE GP ghosts made by a program, 0.10 USDC each to house 0.0.11333910 on the
public board, never HUMAN` (only `HOUSE_OWNER_BOOK`'s approval counts; one approval, one batch). The checker replays
every log again, requires its lap splits, and writes the whole batch in one transaction: each BOT run (its ghost
encrypted in `log_enc`, its splits, `gen`) with its listing (`label`, `pay_to` = the house account `0.0.11333910`,
`hcs` = the HOUSE message on the Hedera market topic). They are sold through the same x402 paywall as every listed
ghost. The generator is public and deterministic (same commit and seed: byte-identical logs), so anyone can regenerate
a listed BOT ghost and check its `log_h` against the row without buying it. A BOT row can never carry HUMAN, a book or a
credential: the service's row builders take no such fields. `arkiv:open-run` refuses `BOT-` labels.

## Who can do what

| | `anypercent.run` | `anypercent.listing` |
|---|---|---|
| Create | the checker, only after the runner approved the listing in World App (BOT rows: after the house owner approved the batch in World App; open tier: the team's CLI) | the checker, in the same transaction as its run |
| Edit (patch) | nobody, not even the checker (`readonly`) | nobody (`readonly`) |
| Extend | anyone (`permissionlessExtension`), to a later expiry only | only the owner (the checker), which never does |
| Delete | the owner (the checker) | the owner (the checker) |
| Change owner | the owner (the checker); not used in this build | the same |

So a run row cannot be edited, not even by our checker. Our checker could delete one; anyone can keep one alive longer.

## The pin

Anyone can write a row with `arkiv.schema = 'anypercent.run'` and every column right. Nobody can forge `$creator`, the
wallet that created the row. Every reader (the console's board, its listing check, the web board, the profile) adds
`$creator = addr(<the checker>)`, so only rows our checker wrote count. Q8 is the one query without the pin, used by
the web board's "show rows from any wallet" toggle, which strikes those rows out.

Every raw reader also validates each row itself and drops (and counts) a row that lacks a required column, carries one
with the wrong type, has another `arkiv.schema`, or another creator. One wire detail: `arkiv_query` tags a `key`
column (the listing's `run`) `"bytes32"`, so readers take `bytes32` as `key`, as the SDK's own decoder does (see
[friction.md](friction.md), item 12).

## The open tier

Rows with no record book: written by a CLI (`npm run arkiv:open-run`) from the team's own logs (the shipped test runs),
after the same replay check. They carry a `label`, `human: false` and the plain `log`, so anyone can fetch the log and
replay it themselves. They show on the board without the HUMAN badge.

## Queries (`C` = the checker, `S` = the season)

Each is sent as `{"jsonrpc":"2.0","id":1,"method":"arkiv_query","params":["<query>",{"select":{...},"limit":"0x64"}]}`.
A board never selects `log` or `log_enc`; only a single ghost read does.

| # | Query | Used by |
|---|---|---|
| Q1 | `arkiv.schema = str('anypercent.run') AND game = str('MDGP') AND season = i32(S) AND $creator = addr(C) ORDER BY frames:u64 ASC` | The console's board, the web board |
| Q2 | `arkiv.schema = str('anypercent.listing') AND game = str('MDGP') AND season = i32(S) AND $creator = addr(C) ORDER BY frames:u64 ASC` | Which runs are listed, their price and `pay_to` (for sale only with one) |
| Q3 | `arkiv.schema = str('anypercent.listing') AND game = str('MDGP') AND season = i32(S) AND frames < u64(6290) AND $creator = addr(C) ORDER BY frames:u64 DESC` (limit 1) | The listed ghost just ahead of 1:44.83 |
| Q4 | `arkiv.schema = str('anypercent.run') AND book = str('ANY-6PS') AND $creator = addr(C) ORDER BY frames:u64 ASC` | A record book's profile: its runs, times, HUMAN and credential |
| Q5 | `arkiv.schema = str('anypercent.listing') AND book = str('ANY-6PS') AND $creator = addr(C) ORDER BY $expiresAt:u64 ASC` | The profile's listed ghosts, soonest to end first |
| Q6 | `arkiv.schema = str('anypercent.listing') AND $key = key(0x...) AND $creator = addr(C)`, and the same on `anypercent.run` | The console's listing check before a purchase (selects `pay_to`); the x402 paywall and PB's guards (select `pay_to` and `hcs`); an open-tier ghost (select `log`) |
| Q7 | `arkiv.schema = str('anypercent.run') AND log_h = str('<64 hex>') AND $creator = addr(C)` (limit 1) | The checker's dedupe before a write |
| Q8 | Q1 without `$creator` (select `creator`) | The look-alike demo |
| Q9 | `arkiv.schema = str('anypercent.run') AND game = str('MDGP') AND season = i32(S) AND human = true AND $creator = addr(C) ORDER BY frames:u64 ASC` | The web board's "HUMAN only" filter |
| Q10 | `arkiv.schema = str('anypercent.run') AND game = str('MDGP') AND season = i32(S) AND $creator = addr(C) ORDER BY s2:u64 ASC` | The lap leaders: the fastest lap 2 on the board, one indexed split in one query (`s1`, `s3` for the other laps). The web board's "lap leaders" box; rows without splits never lead a lap |

Every board read selects `s1`..`s4` and `split_kind` on runs and `label` on listings. PB's scout reads Q1 and Q2 to
compare YOU's laps with the listed ghosts' laps.

`C` is written in its EIP-55 form, `0x3d3260425Cb52F0c6716212274a883337aFa3f63` (all-lowercase works too).

## When rows go

- Runs stay on the board until 30 days after the season ends, unless someone extends them. An extension sets a new,
  later expiry, at most about 182.5 days from the block it lands in.
- Listings end after 7 days.
- There is no expiry event: a row past its expiry is simply no longer returned by any query.
- Paging: a page is up to 100 rows. The board reads one page per game; runners past the 100 fastest runs are not shown
  in this build.

## What stays off Arkiv

World nullifiers, the bridge's HMAC secret, World ID session ids, the ghost key, the approval id, console ids (and
console tags) and anyone's name. Why each stays off is in [why-arkiv.md](why-arkiv.md).
