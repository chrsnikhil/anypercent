#!/bin/bash
# Run the kit's tests in the sandbox venv: bash dev/pytest.sh [pytest args]
set -e
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
exec /opt/arca-sandbox/venv/bin/python -m pytest "$@"
