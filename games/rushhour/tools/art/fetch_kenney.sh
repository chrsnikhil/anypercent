#!/bin/bash
# Puts the Kenney packs RUSH HOUR uses into art/kenney/ (CC0; License.txt kept): from the shared cache
# games/_kenney/*.zip when it is there, else downloaded from kenney.nl. Only the tilemaps and licenses are kept.
set -euo pipefail
cd "$(dirname "$0")/../.."
CACHE=../_kenney
fetch() {   # fetch NAME ZIP URL
    local name=$1 zip=$2 url=$3 dst=art/kenney/$1
    local src=$CACHE/$zip
    if [ ! -f "$src" ]; then
        src=$(mktemp --suffix=.zip)
        curl -fsSL -o "$src" "$url"
    fi
    rm -rf "${dst:?}"
    mkdir -p "$dst"
    unzip -q -o "$src" -d "$dst"
    rm -rf "${dst:?}/Construct 3" "${dst:?}/Tiled" "${dst:?}/Tiles"
    find "$dst" -name '*.url' -delete
    [ -f "$dst/License.txt" ] || { echo "no License.txt in $zip" >&2; exit 1; }
}
fetch pixel-platformer pixel-platformer.zip \
    https://kenney.nl/media/pages/assets/pixel-platformer/33bb4921eb-1696667883/kenney_pixel-platformer.zip
fetch pixel-platformer-industrial pixel-platformer-industrial-expansion.zip \
    https://kenney.nl/media/pages/assets/pixel-platformer-industrial-expansion/7d8a6d7bb4-1677693518/kenney_pixel-platformer-industrial-expansion.zip
echo "Kenney packs in art/kenney/"
