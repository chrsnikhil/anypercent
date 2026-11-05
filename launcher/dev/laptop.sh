#!/bin/bash
# The launcher in a window on the laptop (WSLg), with the booth lineup, for building the sponsor integrations.
#   wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/Users/chrsn/Desktop/retro-handheld-ethglobal/launcher/dev/laptop.sh [launcher args]
# The booth library (docs/games/lineup.txt) is built into $SANDBOX/launcher-booth, apart from the full sandbox library,
# and rebuilt when anything it is made from changes. Each arcade game's shipped test log (the handler's board and target
# ghost) comes from $SANDBOX/devicecheck. Keys: arrows, X = Cross, Z = Circle, C = Square, D = Triangle (PB the
# handler), A/S = L1/R1, Enter = Start, Backspace = Select.
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
cd "$HERE"
exec "$PY" -m arca_launcher --library "$LIB" --testlogs "$SANDBOX/devicecheck" --state "$SANDBOX/laptop-state.json" --scale 2 "$@"
