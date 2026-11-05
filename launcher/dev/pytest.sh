#!/bin/bash
# Run the launcher's tests in the sandbox venv, headless.
#   bash dev/pytest.sh [pytest args]
set -e
cd "$(dirname "$0")/.."
export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy PYGAME_HIDE_SUPPORT_PROMPT=1 PYTHONDONTWRITEBYTECODE=1
exec /opt/arca-sandbox/venv/bin/python -m pytest "$@"
