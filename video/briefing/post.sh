#!/bin/bash
# Finish the film: glow, a hint of chromatic fringing, scanlines, vignette, grain; mux the soundtrack; H.264 60 fps.
#   bash post.sh   (after: npx remotion render ... out/briefing_raw.mov, python prep/make_audio.py)
set -euo pipefail
cd "$(dirname "$0")"
ffmpeg -y -hide_banner -loglevel warning -stats \
  -i out/briefing_raw.mov -loop 1 -framerate 60 -i public/scanlines.png -i out/briefing_audio.wav \
  -filter_complex "\
    [0:v]format=gbrp,split[a][b];\
    [b]gblur=sigma=9,format=gbrp[g];\
    [a][g]blend=all_mode=screen:all_opacity=0.32[glow];\
    [glow]rgbashift=rh=-1:bh=1[ca];\
    [1:v]format=gbrp[sl];\
    [ca][sl]blend=all_mode=multiply:shortest=1[scan];\
    [scan]vignette=angle=PI/4.6,noise=alls=5:allf=t,format=yuv420p[v]" \
  -map "[v]" -map 2:a -r 60 -c:v libx264 -preset slow -crf 14 -profile:v high -pix_fmt yuv420p \
  -c:a aac -b:a 320k -ar 48000 -shortest -movflags +faststart \
  "out/Any% Briefing - ETHGlobal Mumbai.mp4"
ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height,r_frame_rate -of compact "out/Any% Briefing - ETHGlobal Mumbai.mp4"
