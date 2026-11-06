#!/bin/bash
# The full cut: title, dossier (the problem), the assembly film (the fix), end title. The title cards and the dossier
# get the MW3 grade; the assembly film keeps its own finish and loses its old end card for the new one.
#   needs: out/title_open_raw.mov, out/dossier_raw.mov, out/title_end_raw.mov (npx remotion render ...),
#          "out/Any% Briefing - ETHGlobal Mumbai.mp4" (bash post.sh), and the *_mw3.wav files (prep/make_mw3_audio.py)
set -euo pipefail
cd "$(dirname "$0")"
END=41.0                                       # the assembly film's own end card starts here; the new one replaces it
FADE_AT=40.92
grade() {  # IN OUT: the MW3 grade (soft bloom, warm desaturation, fringing, vignette, grain) with labels of its own
  echo "[$1]format=gbrp,split[a$2][b$2];[b$2]gblur=sigma=12,format=gbrp[g$2];[a$2][g$2]blend=all_mode=screen:all_opacity=0.16,\
eq=saturation=0.88:contrast=1.06:gamma=0.98,colorbalance=rs=0.03:bs=-0.03:rh=0.02:bh=-0.02,rgbashift=rh=-2:bh=2,\
vignette=angle=PI/4.2,noise=alls=7:allf=t,format=yuv420p,setsar=1,fps=60[v$2]"
}
ffmpeg -y -hide_banner -loglevel warning -stats \
  -i out/title_open_raw.mov -i out/dossier_raw.mov -i "out/Any% Briefing - ETHGlobal Mumbai.mp4" -i out/title_end_raw.mov \
  -i out/title_open_mw3.wav -i out/dossier_audio_mw3.wav -i out/briefing_audio_mw3.wav -i out/title_end_mw3.wav \
  -filter_complex "$(grade 0:v 0);$(grade 1:v 1);\
[2:v]trim=0:${END},setpts=PTS-STARTPTS,format=yuv420p,setsar=1,fps=60[v2];$(grade 3:v 3);\
[6:a]atrim=0:${END},asetpts=PTS-STARTPTS,afade=t=out:st=${FADE_AT}:d=0.08[a6];\
[v0][4:a][v1][5:a][v2][a6][v3][7:a]concat=n=4:v=1:a=1[v][a]" \
  -map "[v]" -map "[a]" -r 60 -c:v libx264 -preset slow -crf 18 -tune grain -maxrate 45M -bufsize 90M -pix_fmt yuv420p \
  -c:a aac -b:a 320k -ar 48000 -movflags +faststart "out/Any% Full Cut - ETHGlobal Mumbai.mp4"
ffprobe -v error -show_entries format=duration,size -of compact "out/Any% Full Cut - ETHGlobal Mumbai.mp4"
