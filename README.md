# Any%

A handheld speedrun console where every run is provable. The games record their inputs, and anyone can replay a run's
log to re-derive its time: the log either replays to the claimed time (VERIFIED) or it doesn't (REJECTED).

## What's here

| Folder | What it is |
|---|---|
| `launcher/` | The console's launcher (Python, pygame): the game library, PB the coach, and PB the handler, who walks a player through each sponsor step. |
| `arcade/` | The arcade kit: deterministic C game rules shared by the console games and the PC replay checker. |
| `games/`, `game/` | The console's own games (Marine Drive GP, Rush Hour, Segfault, Zip, SHIP IT!), their shared code and a template. |
| `apps/world-bridge/` | The console's laptop service: World (the IDKit record book, one per World ID, and listing approvals) and the Arkiv module (the checker that writes the board, the listed-ghost key release, the web board). |
| `arkiv/` | The Arkiv track's notes ([schema](arkiv/schema.md), [how we use Arkiv](arkiv/how-you-use-arkiv.md), [why Arkiv](arkiv/why-arkiv.md), [reach](arkiv/reach.md), [friction](arkiv/friction.md)) and the board's snapshot (`snapshot.json`). |

Only code is in this repository. The art, music, ROM builds and the console's CAD are not.

## Sponsors in the launcher

The handler talks to sponsors through one interface (`launcher/arca_launcher/handler/sponsors.py`).
- **World** has a real adapter (`handler/world.py`), which talks to `apps/world-bridge`.
- **Arkiv** is real: the board is read straight from Arkiv, and listings are written through `apps/world-bridge` (see below).
- **Hedera** still runs on the mock adapter (`handler/mock.py`), so payments are mocked. The console marks it MOCK on screen.

## Arkiv

The board lives on Arkiv's Rabdi testnet (chain id 7794095). Every time on it was replayed by our checker before it was
written, and nothing about a runner goes on Arkiv until they approve the listing in World App ("on the public board").

- **Writer (the checker):** `0x3d3260425Cb52F0c6716212274a883337aFa3f63`. It creates every board row, and every reader
  (the console, the web board) ignores rows from any other wallet.
- **Look-alike demo only (the stranger):** `0x6CD1e043820e450A13B3F536F7a90ED2aDCfbCc1`. It writes a perfect copy of a
  run to show that the board ignores it.
- **Web board:** _owner: the hosted URL goes here_. The page is `apps/world-bridge/public/board.html` (one file, no build);
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

### AI use

_Owner: confirm or rewrite._ This project was built with AI assistance. Claude (Anthropic), through Claude Code, wrote
and reviewed much of the code, tests and documentation, including the Arkiv module, under the team's direction. The
team designed the console and the integrations, made every decision, and tested the result on the hardware.

## License

_Owner: add an OSS `LICENSE` file at the repository root and name it here._

## Running

- **Launcher tests:** `bash launcher/dev/pytest.sh` (in the WSL sandbox described in the scripts).
- **Launcher in a window:** `bash launcher/dev/laptop.sh`. Set `ARCA_WORLD_BRIDGE` to the bridge's URL to use real World.
- **World bridge and the Arkiv module:** see `apps/world-bridge/README.md`.
