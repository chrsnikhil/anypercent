#!/bin/bash
# Draw every launcher screen with the real sandbox library (builds the library first).
set -euo pipefail
source "$(dirname "$0")/../../sandbox/00_env.sh"
export SDL_VIDEODRIVER=dummy PYGAME_HIDE_SUPPORT_PROMPT=1
"$SANDBOX/venv/bin/python" "$PROJECT/launcher/tools/build_library.py" \
  --games-json "$PROJECT/docs/games/games.json" --games "$GAMES" --out "$SANDBOX/launcher"
exec "$SANDBOX/venv/bin/python" "$PROJECT/launcher/dev/screens.py" "$SANDBOX/launcher"
