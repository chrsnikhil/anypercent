#!/bin/bash
# Build the Any% device payload in the WSL sandbox: sources the Pi needs, ROMs, the game library (paths rewritten
# to /opt/anypercent) and the known run logs used to check the arm64 replay tools.
#   MSYS_NO_PATHCONV=1 wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/.../device/stage.sh
# Output: /opt/arca-sandbox/device-stage/anypercent-payload.tar.gz (copy it to the Pi, then run device/install.sh).
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
SB=/opt/arca-sandbox
OUT=$SB/device-stage
P=$OUT/payload
rm -rf "$OUT"; mkdir -p "$P/src" "$P/games/built" "$P/games/roms" "$P/testlogs"

# launcher (the bridge imports ../../arcade/py relative to launcher/arca_launcher)
mkdir -p "$P/src/launcher"
cp -r "$REPO/launcher/arca_launcher" "$REPO/launcher/requirements.txt" "$P/src/launcher/"
find "$P/src" -name __pycache__ -prune -exec rm -rf {} +

# on-screen controls: the RetroArch overlay (art + hitboxes, made by device/overlay/make_overlay.py)
mkdir -p "$P/overlays"
cp "$REPO/device/overlay/gamepad.png" "$REPO/device/overlay/gamepad.cfg" "$P/overlays/"

# arcade kit + the five games' rules (enough to build arcade_replay on the Pi)
mkdir -p "$P/src/arcade" "$P/src/game" "$P/src/games/common"
cp -r "$REPO/arcade/src" "$REPO/arcade/tools" "$REPO/arcade/mk" "$REPO/arcade/py" "$P/src/arcade/"
cp -r "$REPO/game/rules" "$REPO/game/gen" "$REPO/game/tools.mk" "$P/src/game/"
cp -r "$REPO/games/common/src" "$P/src/games/common/"
for g in rushhour zip marinedrive segfault; do
  mkdir -p "$P/src/games/$g"
  cp -r "$REPO/games/$g/rules" "$REPO/games/$g/tools.mk" "$P/src/games/$g/"
  [ -d "$REPO/games/$g/gen" ] && cp -r "$REPO/games/$g/gen" "$P/src/games/$g/"
done
find "$P/src" \( -name __pycache__ -o -name out \) -prune -exec rm -rf {} +

# ROMs only (no sandbox .sav files: the device starts with blank cartridges)
cp "$SB"/games/built/*.gb "$SB"/games/built/*.gbc "$SB"/games/built/*.gba "$P/games/built/" 2>/dev/null || true
cp -r "$SB"/games/roms/. "$P/games/roms/"

# library: art + library.json with /opt/arca-sandbox -> /opt/anypercent
cp -r "$SB/launcher" "$P/library"
sed -i 's#/opt/arca-sandbox/#/opt/anypercent/#g' "$P/library/library.json"
if grep -q arca-sandbox "$P/library/library.json"; then echo "unrewritten path left in library.json" >&2; exit 1; fi

# known logs + the x86 tool's results (made by device/make_testlogs.py)
cp "$SB"/devicecheck/*.acl "$SB"/devicecheck/*.x86.json "$P/testlogs/"

tar -C "$P" -czf "$OUT/anypercent-payload.tar.gz" .
ls -la "$OUT/anypercent-payload.tar.gz"
