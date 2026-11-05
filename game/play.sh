#!/bin/bash
# Build SHIP IT! and play it in mGBA (audio sync off: WSLg audio starves it, see sandbox/README.md;
# bilinear filter on: the pre-rendered art is meant to be seen smoothed).
set -e
cd "$(dirname "$0")"
bash dev/build.sh
exec mgba-qt -C audioSync=0 -C videoSync=1 -C resampleVideo=1 "$@" shipit.gba
