# Any%

A handheld speedrun console where every run is provable. The games record their inputs, and anyone can replay a run's
log to re-derive its time: the log either replays to the claimed time (VERIFIED) or it doesn't (REJECTED).

## What's here

| Folder | What it is |
|---|---|
| `launcher/` | The console's launcher (Python, pygame): the game library, PB the coach, and PB the handler, who walks a player through each sponsor step. |
| `arcade/` | The arcade kit: deterministic C game rules shared by the console games and the PC replay checker. |
| `games/`, `game/` | The console's own games (Marine Drive GP, Rush Hour, Segfault, Zip, SHIP IT!), their shared code and a template. |
| `apps/world-bridge/` | The World service: the IDKit record book (one human, one record book) and Agent Pass approvals for money actions. |

Only code is in this repository. The art, music, ROM builds and the console's CAD are not.

## Sponsors in the launcher

The handler talks to sponsors through one interface (`launcher/arca_launcher/handler/sponsors.py`).
- **World** has a real adapter (`handler/world.py`), which talks to `apps/world-bridge`.
- **Arkiv** and **Hedera** still run on the mock adapter (`handler/mock.py`). The console marks them MOCK on screen.

## Running

- **Launcher tests:** `bash launcher/dev/pytest.sh` (in the WSL sandbox described in the scripts).
- **Launcher in a window:** `bash launcher/dev/laptop.sh`. Set `ARCA_WORLD_BRIDGE` to the bridge's URL to use real World.
- **World bridge:** see `apps/world-bridge/README.md`.
