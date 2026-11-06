#!/bin/bash
# The launcher in a window on the laptop (WSLg), with the booth lineup, for building the sponsor integrations.
#   wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/Users/chrsn/Desktop/retro-handheld-ethglobal/launcher/dev/laptop.sh [launcher args]
# The booth library (docs/games/lineup.txt) is built into $SANDBOX/launcher-booth, apart from the full sandbox library,
# and rebuilt when anything it is made from changes. Each arcade game's shipped test log (the handler's board and target
# ghost) comes from $SANDBOX/devicecheck. Keys: arrows, X = Cross, Z = Circle, C = Square, D = Triangle (PB the
# handler), A/S = L1/R1, Enter = Start, Backspace = Select.
# World for real: set ARCA_WORLD_BRIDGE to the World bridge's URL (apps/world-bridge), e.g.
#   wsl -d Ubuntu-24.04 -u root -- env ARCA_WORLD_BRIDGE=http://127.0.0.1:8787 bash .../launcher/dev/laptop.sh
# Unset, every sponsor stays mocked. Arkiv for real as well: also set ARCA_ARKIV_CHECKER to the checker's address (the
# $creator every board read is pinned to); ARCA_ARKIV_RPC and ARCA_ARKIV_SEASON are optional (Rabdi's public RPC, 1):
#   wsl -d Ubuntu-24.04 -u root -- env ARCA_WORLD_BRIDGE=http://127.0.0.1:8787 ARCA_ARKIV_CHECKER=0x... \
#     bash .../launcher/dev/laptop.sh
# Hedera for real on top of both (PB pays over x402 and the listing is recorded on HCS, through the same bridge): also
# set ARCA_HEDERA=1. Without both of the above it stays mocked and the launcher's log says why.
#   wsl -d Ubuntu-24.04 -u root -- env ARCA_WORLD_BRIDGE=http://127.0.0.1:8787 ARCA_ARKIV_CHECKER=0x... ARCA_HEDERA=1 \
#     bash .../launcher/dev/laptop.sh
# With World real this window is one console: its id is $SANDBOX/console-id, beside laptop-state.json and the ledger
# (handler.json). A second window is another console only with a --state in a directory of its own (given after this
# script's, it wins), and is unlinked until the owner runs console:link for its tag (My record book shows it).
set -euo pipefail
source "$(dirname "$0")/../../sandbox/00_env.sh"
HERE="$PROJECT/launcher"
LIB="$SANDBOX/launcher-booth"
PY="$SANDBOX/venv/bin/python"
export PYGAME_HIDE_SUPPORT_PROMPT=1
if [ ! -f "$LIB/library.json" ] || [ -n "$(find "$PROJECT/docs/games/games.json" "$PROJECT/docs/games/lineup.txt" "$HERE/tools" \
      "$PROJECT/games/reskin" "$GAMES/built" "$GAMES/roms" "$GAMES/boot" -newer "$LIB/library.json" -print -quit 2>/dev/null)" ]; then
  say "building the booth library"
  "$PY" "$HERE/tools/build_library.py" --games-json "$PROJECT/docs/games/games.json" --lineup "$PROJECT/docs/games/lineup.txt" \
    --games "$GAMES" --out "$LIB"
fi
WORLD=()
if [ -n "${ARCA_WORLD_BRIDGE:-}" ]; then
  WORLD=(--world-bridge "$ARCA_WORLD_BRIDGE")
fi
ARKIV=()
if [ -n "${ARCA_ARKIV_CHECKER:-}" ]; then
  ARKIV+=(--arkiv-checker "$ARCA_ARKIV_CHECKER")
fi
if [ -n "${ARCA_ARKIV_RPC:-}" ]; then
  ARKIV+=(--arkiv-rpc "$ARCA_ARKIV_RPC")
fi
if [ -n "${ARCA_ARKIV_SEASON:-}" ]; then
  ARKIV+=(--arkiv-season "$ARCA_ARKIV_SEASON")
fi
HEDERA=()
if [ "${ARCA_HEDERA:-}" = "1" ]; then
  HEDERA=(--hedera)
fi
cd "$HERE"
exec "$PY" -m arca_launcher --library "$LIB" --testlogs "$SANDBOX/devicecheck" --state "$SANDBOX/laptop-state.json" --scale 2 \
  "${WORLD[@]}" "${ARKIV[@]}" "${HEDERA[@]}" "$@"
