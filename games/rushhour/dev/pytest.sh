#!/bin/bash
# Run the game's tests in the sandbox venv:  bash dev/pytest.sh [pytest args]
set -e
cd "$(dirname "$0")/.."
source dev/env.sh
exec "$SANDBOX/venv/bin/python" -m pytest "$@"
