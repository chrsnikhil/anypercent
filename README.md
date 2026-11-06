# Any%

A handheld speedrun console where every run is provable. The games record their inputs, and anyone can replay a run's
log to re-derive its time: the log either replays to the claimed time (VERIFIED) or it doesn't (REJECTED).

## What's here

| Folder | What it is |
|---|---|
| `launcher/` | The console's launcher (Python, pygame): the game library, PB the coach, and PB the handler, who walks a player through each sponsor step. |
| `arcade/` | The arcade kit: deterministic C game rules shared by the console games and the PC replay checker. |
| `games/`, `game/` | The console's own games (Marine Drive GP, Rush Hour, Segfault, Zip, SHIP IT!), their shared code and a template. |
| `apps/world-bridge/` | The console's laptop service: World (the IDKit record book, one per World ID, and listing approvals), the Arkiv module (the checker that writes the board, the listed-ghost key release, the web board) and the Hedera module (the x402 paywall on listed ghosts, PB's paying agent, the HCS market topic). |
| `arkiv/` | The Arkiv track's notes ([schema](arkiv/schema.md), [how we use Arkiv](arkiv/how-you-use-arkiv.md), [why Arkiv](arkiv/why-arkiv.md), [reach](arkiv/reach.md), [friction](arkiv/friction.md)) and the board's snapshot (`snapshot.json`). |
| `hedera/` | The Hedera track's [transaction list](hedera/transactions.md): every transaction id in the video, with its HashScan link. |

Only code is in this repository. The art, music, ROM builds and the console's CAD are not.

## Sponsors in the launcher

The handler talks to sponsors through one interface (`launcher/arca_launcher/handler/sponsors.py`).
- **World** has a real adapter (`handler/world.py`), which talks to `apps/world-bridge`.
- **Arkiv** is real: the board is read straight from Arkiv, and listings are written through `apps/world-bridge` (see below).
- **Hedera** is real: PB pays over x402 through `apps/world-bridge`, and the console's MOCK pill goes only when World,
  Arkiv and Hedera are all real (see below). Without `--hedera` the launcher keeps the mock adapter (`handler/mock.py`)
  and marks it MOCK on screen.

## Arkiv

The board lives on Arkiv's Rabdi testnet (chain id 7794095). Every time on it was replayed by our checker before it was
written, and nothing about a runner goes on Arkiv until they approve the listing in World App ("on the public board").

- **Writer (the checker):** `0x3d3260425Cb52F0c6716212274a883337aFa3f63`. It creates every board row, and every reader
  (the console, the web board) ignores rows from any other wallet.
- **Look-alike demo only (the stranger):** `0x6CD1e043820e450A13B3F536F7a90ED2aDCfbCc1`. It writes a perfect copy of a
  run to show that the board ignores it.
- **Web board:** _Owner: the hosted URL goes here_. The page is `apps/world-bridge/public/board.html` (one file, no build);
  the World bridge also serves it at `/board`.
- **How it works:** [arkiv/schema.md](arkiv/schema.md) (entities, queries, who can edit, extend or delete, expiry) and
  `apps/world-bridge/README.md` (the service).

### Run the board's query yourself

The listed MARINE DRIVE GP ghost just ahead of 1:44.83 (6290 frames), from any terminal, no key:

```bash
curl -s https://rpc.rabdi.db-chain.testnet.arkiv.network -H 'content-type: application/json' --data @- <<'EOF'
{"jsonrpc":"2.0","id":1,"method":"arkiv_query","params":["arkiv.schema = str('anypercent.listing') AND game = str('MDGP') AND season = i32(1) AND frames < u64(6290) AND $creator = addr(0x3d3260425Cb52F0c6716212274a883337aFa3f63) ORDER BY frames:u64 DESC",{"select":{"key":true,"creator":true,"expiresAt":true,"attributes":true},"limit":"0x1"}]}
EOF
```

Take out `AND $creator = addr(...)` to see what any wallet wrote, look-alikes included. The full board of a game is the
same call with `arkiv.schema = str('anypercent.run') AND game = str('MDGP') AND season = i32(1) AND $creator =
addr(0x3d3260425Cb52F0c6716212274a883337aFa3f63) ORDER BY frames:u64 ASC` and `"limit":"0x64"`.

### Verify an open-tier run yourself

Open-tier rows (the team's own runs, marked OPEN on the board) carry their plain log, so anyone can replay one. Listed
runs carry theirs encrypted until bought, so this works only for rows with a plain `log`.

```bash
RUN=0x...   # an open-tier run's key, from the board's query
curl -s https://rpc.rabdi.db-chain.testnet.arkiv.network -H 'content-type: application/json' --data @- <<EOF > row.json
{"jsonrpc":"2.0","id":1,"method":"arkiv_query","params":["arkiv.schema = str('anypercent.run') AND \$key = key($RUN) AND \$creator = addr(0x3d3260425Cb52F0c6716212274a883337aFa3f63)",{"select":{"key":true,"attributes":true},"limit":"0x1"}]}
EOF
jq -r '.result.data[0].attributes[] | select(.name=="log") | .value' row.json | sed 's/^0x//' | xxd -r -p > run.acl
sha256sum run.acl          # equals the row's log_h
make -C games/marinedrive -f tools.mk replay     # MDGP; SHIP is game/, RUSH games/rushhour, SEGF games/segfault, ZIPG games/zip
games/marinedrive/out/arcade_replay run.acl      # "time_frames" equals the row's frames
```

## Hedera

PB, the coach agent, buys the ghost of the runner just ahead of you over x402 and pays that runner's own Hedera account
directly, in testnet USDC. No human approves the payment: PB's limits are code next to its key. HCS keeps the listing
the seller approved in World App, PB's intent before it pays, and its receipt after. Testnet only.

```
 Console (Pi or WSL)                 Laptop: apps/world-bridge (Node 22)                         Hedera testnet
   record ──────── HTTP ──────────> /hedera/record ── operator key ── LISTING ──────────────────> HCS topic
   pay ─────────── HTTP ──────────> /hedera/buy: PB's agent (guards, agent key)
                                       │ INTENT ───────────────────────────────────────────────> HCS topic
                                       │ GET /x402/ghost/{listing}           -> 402 + requirements
                                       │ GET /x402/ghost/{listing} + payment -> /verify, /settle ──> facilitator ──> HTS transfer
                                       │ 200 + the ghost + the settlement
                                       │ RECEIPT (once the mirror shows the transfer) ─────────> HCS topic
   load_ghost ──── HTTP ──────────> /arkiv/ghost {run, receipt = the payment's transaction id}
 Any x402 client ─────────────────> GET /x402/ghost/{listing}  (the same paywall)
 Mirror node (HTTPS, no key) <───── balances, associations, transactions, topic messages
```

| Party | Who | Holds |
|---|---|---|
| Client (buyer) | PB's agent in the service (`src/hedera/agent.ts`) | the agent key: test USDC, a little HBAR |
| Resource server | `GET /x402/ghost/{listing}` in the same service (`src/hedera/resource.ts`) | the ghost secret |
| Facilitator | https://x402.org/facilitator (Blocky402 as the fallback) | its fee-payer account: it pays the network fee and submits |
| Seller (payTo) | the listed runner's own account | nothing of ours; receives USDC |
| Recorder | the service's operator account | the topic's submit key; pays HCS fees |

### Setup

All of it runs in `apps/world-bridge` (full detail in its README, "Hedera"):

1. **Accounts.** At portal.hedera.com, a testnet account with an ECDSA key: the operator. Put its id and DER private key
   in `apps/world-bridge/.env` as `HEDERA_OPERATOR_ID` and `HEDERA_OPERATOR_KEY` (`.env.example` lists every name).
2. **`npm run hedera:setup`**: creates PB's agent account (ECDSA, no EVM alias, 5 HBAR), associates it with testnet USDC
   `0.0.429274`, creates the market topic with no admin key, and appends the ids and the agent key to `.env`.
3. **Test USDC** for the agent at https://faucet.circle.com (Hedera Testnet, the agent's `0.0.N` id).
4. **`npm run hedera:payto -- --book ANY-6PS --account 0.0.N`**: the seller's account, checked on the mirror node.
5. **`npm run hedera:smoke -- --pay-to 0.0.N`**: balances, the topic's keys, one HCS message, both facilitators, and
   one real x402 payment of 0.01 USDC, each with its HashScan link.
6. **`npm run hedera:agent -- --book ANY-K2Q --game MDGP --frames 6290`**: PB, with no console and no human, finds the
   listed ghost just ahead on Arkiv, pays for it over x402, checks the ghost, and prints the INTENT, the payment and the
   RECEIPT on HashScan.

### The payment flow

1. The console asks the service to buy the ghost the board names (`POST /hedera/buy`).
2. PB's guards run (table below): the listing and its run re-read from Arkiv, the payout account checked on the mirror,
   the caps, then a reservation that counts against them.
3. PB's INTENT goes to the market topic; a node must accept it before anything is signed.
4. PB finds the endpoint (`<service>/x402/ghost/<listing key>`, published by `/hedera/config`) and asks without paying.
5. The paywall answers 402 with one requirement: `exact` on `hedera:testnet`, USDC, `payTo` = the listing's `pay_to`,
   the listed amount, and the facilitator's fee payer.
6. PB checks the 402 against what it read from Arkiv itself: any mismatch, and nothing is signed.
7. PB builds the payment with `@x402/hedera`: a USDC `TransferTransaction` from the agent to `payTo`, its transaction
   id on the facilitator's fee payer, valid 120 s, signed by the agent key only.
8. PB sends it in `PAYMENT-SIGNATURE`.
9. The paywall checks that the payment accepts exactly the requirement it issues now, and asks the facilitator to
   `/verify` it.
10. It decrypts the ghost and checks its hash (a bad log is never sold), then asks the facilitator to `/settle`: the
    facilitator co-signs as fee payer and submits.
11. It records the sale and answers 200 with the ghost and `PAYMENT-RESPONSE`.
12. PB checks the settlement and the ghost's hash; the receipt is the payment's transaction id. Once the mirror node
    shows the transfer, PB posts its RECEIPT to the topic.
13. The console loads the ghost with that transaction id (`/arkiv/ghost`) and the race starts.

The real 402 and settle bodies, from the end-to-end run:

_Owner: paste the real `PAYMENT-REQUIRED` (decoded) and the settle response from the H3 run here, as two JSON blocks._

### On-chain ids (Hedera testnet)

| What | Id | HashScan |
|---|---|---|
| Market topic (no admin key) | _Owner: the topic id (`HEDERA_TOPIC_ID`)_ | `https://hashscan.io/testnet/topic/<id>` |
| PB's agent account | _Owner: the agent id (`HEDERA_AGENT_ID`)_ | `https://hashscan.io/testnet/account/<id>` |
| Facilitator | https://x402.org/facilitator, fee payer `0.0.9185802` | https://hashscan.io/testnet/account/0.0.9185802 |
| Testnet USDC | `0.0.429274` | https://hashscan.io/testnet/token/0.0.429274 |
| A settled payment | _Owner: the transaction id, checked by `npm run hedera:verify`_ | _link_ |
| Its INTENT and RECEIPT | _Owner: sequence numbers_ | _links_ |

Every transaction id shown in the video is in [hedera/transactions.md](hedera/transactions.md).

### No Solidity

Everything is the Hedera JavaScript SDK (`@hiero-ledger/sdk`) and the x402 libraries; `git ls-files '*.sol'` prints
nothing.
- **HTS:** the USDC payment is a `TransferTransaction` built and signed with the SDK (through `@x402/hedera`), and the
  agent's USDC association is a `TokenAssociateTransaction`.
- **HCS:** the market topic (`TopicCreateTransaction`, no admin key), its LISTING, INTENT and RECEIPT messages
  (`TopicMessageSubmitTransaction`, one chunk each), and every read of them through the mirror node's REST API.
- **Accounts:** PB's agent account is an `AccountCreateTransaction` with an ECDSA key and no EVM alias.

### PB's guards (no human approval, still safe)

| Check | Source of truth | If it fails |
|---|---|---|
| The buyer's record book was issued by this service | its store | no purchase (no budget) |
| Not the buyer's own book | the listing | no purchase |
| The listing is live, written by our checker, for the console's seller, at the listed price | Arkiv | no purchase (changed) |
| The run is live, the checker's, with the same log hash and its sealed ghost | Arkiv | no purchase |
| The listing names a payout account that can take USDC | Arkiv, the mirror node | no purchase |
| 0.10 USDC a purchase; 1.00 a day per record book; 5.00 a day across all books; the agent holds enough | config, store, the mirror node | no purchase (budget) |
| Once per (buyer, game, seller, run) | store | the earlier receipt, nothing paid |
| The 402: one `exact` entry, testnet, USDC, at most 300 s | the 402 | nothing signed |
| The 402's `payTo` is the listing's payout account | Arkiv | nothing signed (`REFUSED payTo`) |
| The 402's amount is the listed price | Arkiv | nothing signed |
| The 402's fee payer is the facilitator's own | the facilitator's `/supported` | nothing signed |

`npm run hedera:evil402 -- --listing 0x...` runs PB against a paywall that names another `payTo` and shows the refusal.

### Claims and limits

- PB, your coach agent, buys the ghost of the runner just ahead of you over x402, and pays her own Hedera account
  directly, in testnet USDC. No human approves the payment.
- PB's limits are code next to its key, not a model's judgement: 0.10 USDC a ghost, 1.00 a day per record book, and it
  only pays the account on the checker's Arkiv listing.
- The seller saw her Hedera account in World App when she approved the listing.
- Before paying, PB posts its intent to a Hedera topic; after, a receipt once the mirror node shows the transfer. Nobody,
  including us, can delete or edit that topic's messages.
- Hedera SDK only: HTS moves the USDC, HCS keeps the record. No Solidity.

Limits: testnet USDC only. There is no escrow: the payment goes straight to the seller, and our service holds the ghost's
key. PB's choice is the board's runner just ahead, not a model's. The intent is submitted before the payment is signed;
we do not claim it reached consensus first. World binds the record book, not whose hands played. The laptop service must
be on for a purchase.

## AI use

_Owner: confirm or rewrite._ This project was built with AI assistance. Claude (Anthropic), through Claude Code, wrote
and reviewed much of the code, tests and documentation, including the Arkiv and Hedera modules, under the team's direction. The
team designed the console and the integrations, made every decision, and tested the result on the hardware.

## License

_Owner: add an OSS `LICENSE` file at the repository root and name it here._

## Running

- **Launcher tests:** `bash launcher/dev/pytest.sh` (in the WSL sandbox described in the scripts).
- **Launcher in a window:** `bash launcher/dev/laptop.sh`. Set `ARCA_WORLD_BRIDGE` to the bridge's URL to use real World.
- **World bridge, the Arkiv and Hedera modules:** see `apps/world-bridge/README.md`.
