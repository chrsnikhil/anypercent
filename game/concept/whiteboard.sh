#!/bin/bash
/opt/arca-sandbox/venv/bin/python - <<'PY'
from PIL import Image, ImageDraw, ImageFont
im=Image.new("RGB",(400,300),(250,250,252)); d=ImageDraw.Draw(im)
fnt=ImageFont.truetype("/mnt/c/Users/chrsn/Desktop/retro-handheld-ethglobal/launcher/arca_launcher/assets/fonts/Outfit-Bold.ttf",46)
d.text((24,14),"SHIP IT",font=fnt,fill=(220,40,60))
blue=(30,80,200); green=(20,150,80)
for (x,y,t) in ((30,120,"World"),(160,120,"Arkiv"),(290,120,"Arc")):
    d.rounded_rectangle((x,y,x+90,y+54),10,outline=blue,width=6)
f2=ImageFont.truetype("/mnt/c/Users/chrsn/Desktop/retro-handheld-ethglobal/launcher/arca_launcher/assets/fonts/Outfit-Bold.ttf",24)
for (x,y,t) in ((30,120,"World"),(160,120,"Arkiv"),(290,120,"Arc")):
    d.text((x+12,y+14),t,font=f2,fill=blue)
d.line((120,147,160,147),fill=blue,width=5); d.line((250,147,290,147),fill=blue,width=5)
for k in range(4): d.line((30,210+k*22,30+[300,220,260,150][k],210+k*22),fill=green,width=6)
d.text((300,20),"36h",font=f2,fill=(40,40,40))
im.save("/mnt/c/Users/chrsn/AppData/Local/Temp/claude/c--Users-chrsn-Desktop-ARCA/f03de88a-2f73-42cb-b30a-3e537b5caf2a/scratchpad/render/whiteboard.png")
PY
