#!/bin/bash
# Copies the Kenney CC0 files ZIP uses from the shared cache (games/_kenney/*.zip, downloaded once from kenney.nl)
# into art/kenney/<pack>/ with each pack's License.txt. Run from the game directory: bash tools/art/fetch_kenney.sh
# (the plan asked for a kenney.nl scraper; the packs are cached, so nothing is downloaded here).
set -euo pipefail
cd "$(dirname "$0")/../.."
CACHE=../_kenney
get() {   # get PACK FILE...
    local pack=$1; shift
    mkdir -p "art/kenney/$pack"
    unzip -o -q -j "$CACHE/$pack.zip" License.txt "$@" -d "art/kenney/$pack"
}
get pixel-platformer Tilemap/tilemap_packed.png Tilemap/tilemap-characters_packed.png
get pixel-platformer-industrial-expansion Tilemap/tilemap_packed.png
echo "art/kenney: $(find art/kenney -type f | wc -l) files"
