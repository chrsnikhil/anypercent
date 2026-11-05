#!/bin/bash
# Stamp a new arcade game from games/template:
#   bash games/new_game.sh ID4 DIRNAME "ROM TITLE" ROMCODE      e.g.  bash games/new_game.sh RUSH rushhour "RUSH HOUR" RUSH
# ID4: the game id in the save and run logs (4 of A-Z 0-9, unique across games). DIRNAME: games/<DIRNAME>/ and the ROM
# name <DIRNAME>.gba (a-z 0-9 _, no hyphens). ROM TITLE: the cartridge header title and the title screen text (1-12 of
# A-Z 0-9 space ! . -). ROMCODE: the cartridge header code (4 of A-Z 0-9).
# Copies only sources (no build/, out/, ROMs, saves or caches) and refuses an existing target.
set -euo pipefail
usage() { echo "usage: new_game.sh ID4 DIRNAME \"ROM TITLE\" ROMCODE" >&2; exit 2; }
[ $# -eq 4 ] || usage
ID=$1 DIR=$2 TITLE=$3 CODE=$4
GAMES=$(cd "$(dirname "$0")" && pwd)
SRC=$GAMES/template
DST=$GAMES/$DIR

[[ $ID =~ ^[A-Z0-9]{4}$ ]] || { echo "ID4 must be 4 of A-Z 0-9: '$ID'" >&2; exit 2; }
[[ $DIR =~ ^[a-z_][a-z0-9_]*$ ]] || { echo "DIRNAME must be a-z 0-9 _ (no hyphens): '$DIR'" >&2; exit 2; }
[[ $TITLE =~ ^[A-Z0-9\ \!.-]{1,12}$ ]] || { echo "ROM TITLE must be 1-12 of A-Z 0-9 space ! . -: '$TITLE'" >&2; exit 2; }
[[ $CODE =~ ^[A-Z0-9]{4}$ ]] || { echo "ROMCODE must be 4 of A-Z 0-9: '$CODE'" >&2; exit 2; }
case $DIR in template|common|tests|_kenney) echo "DIRNAME '$DIR' is reserved" >&2; exit 2 ;; esac
case $ID in TMPL|SHIP) echo "ID4 '$ID' is taken (template / SHIP IT!)" >&2; exit 2 ;; esac
if grep -ls "const ac_game_info GAME_INFO = {\"$ID\"" "$GAMES"/*/rules/*.c >/dev/null 2>&1; then
    echo "ID4 '$ID' is already used by $(grep -ls "GAME_INFO = {\"$ID\"" "$GAMES"/*/rules/*.c | head -1)" >&2; exit 2
fi
[ ! -e "$DST" ] || { echo "$DST exists: refusing to overwrite it" >&2; exit 1; }

fail() { echo "new_game.sh: $*" >&2; rm -rf "$DST"; exit 1; }
mkdir "$DST"
trap 'rm -rf "$DST"' ERR
(cd "$SRC" && tar -cf - --exclude=./build --exclude=./out --exclude=./tests/out --exclude='*.gba' --exclude='*.elf' \
    --exclude='*.sav' --exclude='__pycache__' --exclude='.pytest_cache' .) | (cd "$DST" && tar -xf -)

sub() {   # sub FILE PATTERN REPLACEMENT: sed on one file; fails if the pattern is not there (the template changed)
    grep -q -- "$2" "$DST/$1" || fail "'$2' not found in $1 (the template changed?)"
    sed -i "s|$2|$3|" "$DST/$1"
}
sub Makefile '^TARGET          :=  template$' "TARGET          :=  $DIR"
sub Makefile '^ROMTITLE        :=  TEMPLATE$' "ROMTITLE        :=  $TITLE"
sub Makefile '^ROMCODE         :=  TMPL$' "ROMCODE         :=  $CODE"
sub rules/game.c 'GAME_INFO = {"TMPL"' "GAME_INFO = {\"$ID\""
sub src/view.cpp 'title = "TEMPLATE"' "title = \"$TITLE\""
sub README.md '^# TEMPLATE$' "# $TITLE"
sub README.md 'game id `TMPL`' "game id \`$ID\`"
trap - ERR
echo "stamped games/$DIR (id $ID, ROM $DIR.gba, title '$TITLE', code $CODE)"
echo "next: cd games/$DIR && bash dev/pytest.sh    (in the sandbox; see games/README.md)"
