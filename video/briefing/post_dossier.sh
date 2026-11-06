#!/bin/bash
# Finish the dossier in the manner of a Modern Warfare III briefing: soft bloom, a warm desaturated grade, lens
# fringing, vignette and grain; mux its soundtrack. Then join it to the assembly film for the full cut.
#   bash post_dossier.sh   (after: npx remotion render src/index.ts Dossier out/dossier_raw.mov ...,
#                           python prep/make_dossier_audio.py, and bash post.sh for the assembly film)
set -euo pipefail
cd "$(dirname "$0")"
ffmpeg -y -hide_banner -loglevel warning -stats \
  -i out/dossier_raw.mov -i out/dossier_audio.wav \
  -filter_complex "\
    [0:v]format=gbrp,split[a][b];\
    [b]gblur=sigma=12,format=gbrp[g];\
    [a][g]blend=all_mode=screen:all_opacity=0.16[glow];\
    [glow]eq=saturation=0.88:contrast=1.06:gamma=0.98,colorbalance=rs=0.03:bs=-0.03:rh=0.02:bh=-0.02,\
rgbashift=rh=-2:bh=2,vignette=angle=PI/4.2,noise=alls=7:allf=t,format=yuv420p[v]" \
  -map "[v]" -map 1:a -r 60 -c:v libx264 -preset slow -crf 17 -tune grain -profile:v high -pix_fmt yuv420p \
  -c:a aac -b:a 320k -ar 48000 -shortest -movflags +faststart "out/Any% Dossier.mp4"

# the full cut: the dossier (the problem), then the assembly film (the fix)
ffmpeg -y -hide_banner -loglevel warning -stats \
  -i "out/Any% Dossier.mp4" -i "out/Any% Briefing - ETHGlobal Mumbai.mp4" \
  -filter_complex "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]" \
  -map "[v]" -map "[a]" -r 60 -c:v libx264 -preset slow -crf 19 -tune grain -maxrate 45M -bufsize 90M -pix_fmt yuv420p \
  -c:a aac -b:a 320k -ar 48000 -movflags +faststart "out/Any% Full Cut - ETHGlobal Mumbai.mp4"
for f in "out/Any% Dossier.mp4" "out/Any% Full Cut - ETHGlobal Mumbai.mp4"; do
  ffprobe -v error -show_entries format=duration,size -of compact "$f"
done
