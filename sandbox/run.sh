#!/bin/bash
# Run any sandbox step with the environment loaded:
#   run.sh 04_games.py        (python steps use the sandbox venv)
#   run.sh 05_build_games.sh
#   run.sh launcher           (the game launcher, see launcher/)
#   run.sh game               (build and play SHIP IT!, see game/README.md)
source "$(dirname "$0")/00_env.sh"
step="$1"; shift
case "$step" in
  launcher) exec bash "$PROJECT/launcher/launch.sh" "$@" ;;
  game) exec bash "$PROJECT/game/play.sh" "$@" ;;
  *.py) exec "$SANDBOX/venv/bin/python" "$PROJECT/sandbox/$step" "$@" ;;
  *)    exec bash "$PROJECT/sandbox/$step" "$@" ;;
esac
