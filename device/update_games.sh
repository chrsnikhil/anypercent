#!/bin/bash
# Update the five arcade games on an installed Any% Pi without a full install.sh (which replaces the library):
# their rules sources (the replay tools are built from them), their ROMs and the known run logs come from a stage.sh
# payload, then replay_tools.sh rebuilds the replay tools and checks them. The library, the launcher (device/deploy.py
# sends that), every other ROM, the players' saves and runs are left as they are.
#   sudo bash /opt/anypercent/src/device/update_games.sh /tmp/anypercent-payload.tar.gz
set -euo pipefail
PAYLOAD=${1:?usage: update_games.sh PAYLOAD.tar.gz}
ROOT=${ANYPERCENT_ROOT:-/opt/anypercent}
HERE=$(cd "$(dirname "$0")" && pwd)
ROMS="ship-it.gba rush-hour.gba zip.gba marine-drive-gp.gba segfault.gba"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

tar -C "$T" -xzf "$PAYLOAD" ./src/arcade ./src/game ./src/games ./testlogs $(printf './games/built/%s ' $ROMS)
for d in arcade game games; do
  rm -rf "$ROOT/src/$d"
  mv "$T/src/$d" "$ROOT/src/$d"
done
rm -rf "$ROOT/testlogs"
mv "$T/testlogs" "$ROOT/testlogs"
for r in $ROMS; do                  # owned like games/built, where RetroArch writes each ROM's .srm
  install -m 0644 "$T/games/built/$r" "$ROOT/games/built/$r"
  chown --reference="$ROOT/games/built" "$ROOT/games/built/$r"
done
echo "== games updated: $ROMS"
bash "$HERE/replay_tools.sh" "$ROOT"
