#!/bin/bash
# Game Boy toolchains: RGBDS (assembly) and GBDK-2020 (C). Pinned versions,
# official release binaries. Older RGBDS versions are added only if a game
# needs them (see 05_build_games.sh).
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
mkdir -p "$TOOLS"

fetch() {  # url dest-dir [strip]
  local tmp; tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/pkg" "$1"
  mkdir -p "$2"
  case "$1" in
    *.tar.xz) tar -xJf "$tmp/pkg" -C "$2" ${3:+--strip-components=$3} ;;
    *.tar.gz) tar -xzf "$tmp/pkg" -C "$2" ${3:+--strip-components=$3} ;;
  esac
  rm -rf "$tmp"
}

say "RGBDS v1.0.4"
[ -x "$RGBDS_HOME/rgbasm" ] || fetch https://github.com/gbdev/rgbds/releases/download/v1.0.4/rgbds-linux-x86_64.tar.xz "$RGBDS_HOME"
"$RGBDS_HOME/rgbasm" --version

say "GBDK-2020 4.5.0"
[ -x "$GBDK_HOME/bin/lcc" ] || fetch https://github.com/gbdk-2020/gbdk-2020/releases/download/4.5.0/gbdk-linux64.tar.gz "$TOOLS/gbdk" 1
"$GBDK_HOME/bin/lcc" -v 2>&1 | head -1 || true

cat > "$SANDBOX/activate" <<EOF
# source $SANDBOX/activate   -- puts the toolchains and PyBoy on PATH
source $PROJECT/sandbox/00_env.sh
EOF
echo "toolchains OK"
