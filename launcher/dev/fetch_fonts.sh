#!/bin/bash
# Download Outfit (SIL Open Font License 1.1) from the Google Fonts repository and cut the three
# weights the launcher uses (Regular 400, SemiBold 600, Bold 700) from its variable font with fontTools.
set -euo pipefail
DEST="$(cd "$(dirname "$0")/.." && pwd)/arca_launcher/assets/fonts"
PY=/opt/arca-sandbox/venv/bin/python
SRC=https://raw.githubusercontent.com/google/fonts/main/ofl/outfit
mkdir -p "$DEST"
tmp=$(mktemp -d)
curl -fsSL -o "$tmp/Outfit.ttf" "$SRC/Outfit%5Bwght%5D.ttf"
curl -fsSL -o "$DEST/LICENSE-Outfit.txt" "$SRC/OFL.txt"
"$PY" - "$tmp/Outfit.ttf" "$DEST" <<'EOF'
import os, sys
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
src, dest = sys.argv[1], sys.argv[2]
for name, weight in (("Regular", 400), ("SemiBold", 600), ("Bold", 700)):
    font = instancer.instantiateVariableFont(TTFont(src), {"wght": weight})
    font.save(os.path.join(dest, f"Outfit-{name}.ttf"))
print("fonts:", sorted(os.listdir(dest)))
EOF
rm -rf "$tmp"
