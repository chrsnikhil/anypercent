#!/bin/bash
/opt/arca-sandbox/venv/bin/python - <<'PY'
from PIL import Image, ImageDraw
import random
random.seed(7)
W,H=512,512
im=Image.new("RGB",(W,H)); d=ImageDraw.Draw(im)
for y in range(H):  # monsoon day sky: soft blue to warm haze
    t=y/H; d.line((0,y,W,y),fill=(int(150+80*t),int(185+45*t),int(225+10*t)))
for layer,(col,hmin,hmax,base) in enumerate([((150,160,185),80,220,330),((105,115,145),60,260,380)]):
    x=0
    while x<W:
        w=random.randint(22,60); h=random.randint(hmin,hmax)
        d.rectangle((x,base-h,x+w,H),fill=col)
        if layer==1:
            for wy in range(base-h+8,base,14):
                for wx in range(x+5,x+w-6,10):
                    if random.random()<0.35: d.rectangle((wx,wy,wx+4,wy+6),fill=(215,205,160))
        x+=w+random.randint(0,6)
d.rectangle((0,400,W,H),fill=(70,110,140))      # the sea
for k in range(6): d.line((0,412+k*16,W,408+k*16),fill=(95,140,165),width=2)
# sea link: pylon and cables
d.rectangle((300,250,310,405),fill=(90,95,120)); d.rectangle((0,395,W,402),fill=(90,95,120))
for k in range(9):
    d.line((305,255,300-30*k-20,396),fill=(200,205,215)); d.line((305,255,310+30*k+20,396),fill=(200,205,215))
im.save("/mnt/c/Users/chrsn/AppData/Local/Temp/claude/c--Users-chrsn-Desktop-ARCA/f03de88a-2f73-42cb-b30a-3e537b5caf2a/scratchpad/render/skyline_day.png")
PY
