#!/bin/bash
# Phone copies of the film under 30 MiB each (the SendUserFile limit): 720p60, three parts split at Part III and
# at the end of the games.
#   bash phone_copy.sh [SRC]
set -euo pipefail
cd "$(dirname "$0")"
SRC=${1:-"out/Any% Film v5 - ETHGlobal Mumbai.mp4"}
SPLIT=114.92                                   # the PART III card: 20 + 1.667 + 2.5 + 12 + 0.833 + 50 + 27.917
SPLIT2=192.417                                 # PART IV: + 0.833 + 31.5 + the games 45.167
VF="hqdn3d=1.5:1.5:6:6,scale=1280:720:flags=lanczos"
X264=(-c:v libx264 -preset slow -b:v 1750k -maxrate 2300k -bufsize 3600k -r 60 -pix_fmt yuv420p)   # ~26 MiB a half: margin under 30
part() {  # N START [DURATION]
  local o="out/Any% Film v5 (part $1 of 3, phone 720p).mp4" log="out/phone_pass_$1"
  local t=(); if [ $# -gt 2 ]; then t=(-t "$3"); fi
  ffmpeg -y -hide_banner -loglevel error -ss "$2" "${t[@]}" -i "$SRC" -vf "$VF" "${X264[@]}" -pass 1 -passlogfile "$log" -an -f mp4 NUL
  ffmpeg -y -hide_banner -loglevel error -ss "$2" "${t[@]}" -i "$SRC" -vf "$VF" "${X264[@]}" -pass 2 -passlogfile "$log" \
    -c:a aac -b:a 128k -movflags +faststart "$o"
  rm -f "$log"*
  ls -la "$o" | awk '{print $5}'
}
part 1 0 $SPLIT
part 2 $SPLIT $(python -c "print($SPLIT2 - $SPLIT)")
part 3 $SPLIT2
