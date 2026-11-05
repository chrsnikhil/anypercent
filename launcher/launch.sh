#!/bin/bash
# Start the launcher in the sandbox. Rebuilds the game library first if anything it is made from changed.
#   bash run.sh launcher [--scale 1|2|3] [--emulator mgba|retroarch] [--fps]
set -euo pipefail
source "$(dirname "$0")/../sandbox/00_env.sh"
HERE="$PROJECT/launcher"
LIB="$SANDBOX/launcher"
PY="$SANDBOX/venv/bin/python"
export PYGAME_HIDE_SUPPORT_PROMPT=1
if [ ! -f "$LIB/library.json" ] || [ -n "$(find "$PROJECT/docs/games/games.json" "$HERE/tools" "$GAMES/built" \
      "$GAMES/roms" "$GAMES/boot" -newer "$LIB/library.json" -print -quit 2>/dev/null)" ]; then
  say "building the game library"
  "$PY" "$HERE/tools/build_library.py" --games-json "$PROJECT/docs/games/games.json" --games "$GAMES" --out "$LIB"
fi
cd "$HERE"
exec "$PY" -m arca_launcher --library "$LIB" --scale 2 "$@"
