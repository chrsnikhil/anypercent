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
| `label` | str, optional | no | An open-tier row's display name, such as `TEAM` or `BOT-7`. Never a person's name |
| `human` | bool | yes | True only when the run's record book was opened with a World ID proof at our bridge. False on open-tier rows |
| `credential` | str, optional | no | What World checked when the book was opened (`Orb`). Absent on open-tier rows |
| `tool` | str | no | The replay tool that checked it: `arcade_replay sha256:<first 12 hex of the binary>` |
| `log` | bytes, optional | no | The plain `.acl` log, on open-tier rows only: anyone can replay it |
| `log_enc` | bytes, optional | no | A listed run's log, encrypted: `nonce(12) \|\| AES-256-GCM ciphertext \|\| tag(16)` |

- **Flags:** `readonly: true`, `permissionlessExtension: true`.
- **Expiry:** season end + 30 days (`ExpirationTime.atDate(seasonEnd + 30 d, { atLeast: fromDays(1) })`).
- **Creator and owner:** the checker.
- Exactly one of `log` and `log_enc` is present.

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
| `book` | str | yes | The seller's record book |
| `human` | bool | yes | Copied |

- **Flags:** `readonly: true`, `permissionlessExtension: false`. A listing never outlives its week.
- **Expiry:** 7 days (`ExpirationTime.fromDays(7)`), the console's "Ends in 7 days".
- **Creator and owner:** the checker.

The run and its listing are written in one transaction: `predictEntityKeys` gives the run's key before it exists, so
the listing can carry it.

## Who can do what

| | `anypercent.run` | `anypercent.listing` |
|---|---|---|
| Create | the checker, only after the runner approved the listing in World App (open tier: the team's CLI) | the checker, in the same transaction as its run |
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
| Q2 | `arkiv.schema = str('anypercent.listing') AND game = str('MDGP') AND season = i32(S) AND $creator = addr(C) ORDER BY frames:u64 ASC` | Which runs are listed, and their price |
| Q3 | `arkiv.schema = str('anypercent.listing') AND game = str('MDGP') AND season = i32(S) AND frames < u64(6290) AND $creator = addr(C) ORDER BY frames:u64 DESC` (limit 1) | The listed ghost just ahead of 1:44.83 |
| Q4 | `arkiv.schema = str('anypercent.run') AND book = str('ANY-6PS') AND $creator = addr(C) ORDER BY frames:u64 ASC` | A record book's profile: its runs, times, HUMAN and credential |
| Q5 | `arkiv.schema = str('anypercent.listing') AND book = str('ANY-6PS') AND $creator = addr(C) ORDER BY $expiresAt:u64 ASC` | The profile's listed ghosts, soonest to end first |
| Q6 | `arkiv.schema = str('anypercent.listing') AND $key = key(0x...) AND $creator = addr(C)`, and the same on `anypercent.run` | The console's listing check before a purchase; an open-tier ghost (select `log`) |
| Q7 | `arkiv.schema = str('anypercent.run') AND log_h = str('<64 hex>') AND $creator = addr(C)` (limit 1) | The checker's dedupe before a write |
| Q8 | Q1 without `$creator` (select `creator`) | The look-alike demo |
| Q9 | `arkiv.schema = str('anypercent.run') AND game = str('MDGP') AND season = i32(S) AND human = true AND $creator = addr(C) ORDER BY frames:u64 ASC` | The web board's "HUMAN only" filter |

`C` is written in its EIP-55 form, `0x3d3260425Cb52F0c6716212274a883337aFa3f63` (all-lowercase works too).

## When rows go

- Runs stay on the board until 30 days after the season ends, unless someone extends them. An extension sets a new,
  later expiry, at most about 182.5 days from the block it lands in.
- Listings end after 7 days.
- There is no expiry event: a row past its expiry is simply no longer returned by any query.
- Paging: a page is up to 100 rows. The board reads one page per game; runners past the 100 fastest runs are not shown
  in this build.

## What stays off Arkiv

World nullifiers, the bridge's HMAC secret, World ID session ids, the ghost key, the approval id, console ids and
anyone's name. Why each stays off is in [why-arkiv.md](why-arkiv.md).
