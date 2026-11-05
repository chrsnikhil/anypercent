#!/bin/bash
/opt/arca-sandbox/venv/bin/python - <<'PY'
from PIL import Image, ImageDraw, ImageFont
im=Image.new("RGB",(700,200),(126,58,242)); d=ImageDraw.Draw(im)
d.rectangle((0,0,699,199),outline=(255,200,40),width=10)
fnt=ImageFont.truetype("/mnt/c/Users/chrsn/Desktop/retro-handheld-ethglobal/launcher/arca_launcher/assets/fonts/Outfit-Bold.ttf",96)
d.text((350,102),"ETHMUMBAI",font=fnt,fill=(255,255,255),anchor="mm")
im.save("/mnt/c/Users/chrsn/AppData/Local/Temp/claude/c--Users-chrsn-Desktop-ARCA/f03de88a-2f73-42cb-b30a-3e537b5caf2a/scratchpad/render/banner.png")
PY
