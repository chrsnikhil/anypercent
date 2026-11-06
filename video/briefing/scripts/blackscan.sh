#!/bin/bash
# list runs of near-black frames in each raw act render (limited-range black = 16, so threshold 32)
cd "$(dirname "$0")/.."
for f in "$@"; do
  echo -n "$f: "
  ffmpeg -hide_banner -i out/${f}_raw.mov -vf "scale=320:-1,blackframe=amount=98:threshold=32" -an -f null - 2>&1 | grep -o "] frame:[0-9]* pblack" | grep -o "[0-9]*" | sort -n | uniq | python -c "
import sys
n=[int(x) for x in sys.stdin.read().split()]
runs=[]
for x in n:
    if runs and x==runs[-1][1]+1: runs[-1][1]=x
    else: runs.append([x,x])
print(runs)"
done
