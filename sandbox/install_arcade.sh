#!/bin/bash
# Install an arcade-kit game into the sandbox: its ROM where the launcher finds rebuilt ROMs, and its replay tool
# where games.json's "arcade" entry points the launcher's bridge.
#   bash sandbox/install_arcade.sh GAME_DIR ID ROMNAME      e.g.  bash sandbox/install_arcade.sh game SHIP ship-it.gba
# GAME_DIR must hold exactly one ROM (<target>.gba, the Butano build); its replay tool is (re)built here first
# (make -f tools.mk replay), so the installed tool always matches the game's current rules.
set -e
[ $# -eq 3 ] || { echo "usage: install_arcade.sh GAME_DIR ID ROMNAME" >&2; exit 2; }
GAME_DIR=$1 ID=$2 ROMNAME=$3
GAMES=${ARCA_GAMES:-/opt/arca-sandbox/games}
shopt -s nullglob
roms=("$GAME_DIR"/*.gba)
[ ${#roms[@]} -eq 1 ] || { echo "expected one .gba in $GAME_DIR, found ${#roms[@]}" >&2; exit 1; }
make -C "$GAME_DIR" -f tools.mk replay >&2
[ -x "$GAME_DIR/out/arcade_replay" ] || { echo "missing $GAME_DIR/out/arcade_replay after make -f tools.mk replay" >&2; exit 1; }
mkdir -p "$GAMES/built" "$GAMES/arcade/$ID"
cp "${roms[0]}" "$GAMES/built/$ROMNAME"
cp "$GAME_DIR/out/arcade_replay" "$GAMES/arcade/$ID/arcade_replay"
chmod +x "$GAMES/arcade/$ID/arcade_replay"
echo "installed ${roms[0]} -> $GAMES/built/$ROMNAME, replay -> $GAMES/arcade/$ID/arcade_replay"
