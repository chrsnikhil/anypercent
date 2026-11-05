#!/bin/bash
S=/mnt/c/Users/chrsn/AppData/Local/Temp/claude/c--Users-chrsn-Desktop-ARCA/f03de88a-2f73-42cb-b30a-3e537b5caf2a/scratchpad
blender -b -P $S/bl_scene.py 2>&1 | grep -E '^RENDERED|Error'
/opt/arca-sandbox/venv/bin/python - <<PY
from PIL import Image, ImageDraw, ImageFont
hi=Image.open("$S/render/office_hi.png").convert("RGBA")
bg=Image.new("RGBA",hi.size,(26,28,44,255)); bg.alpha_composite(hi)
lo=bg.resize((240,160),Image.LANCZOS).convert("RGB")
import sys
try:
    q=lo.quantize(255,method=Image.LIBIMAGEQUANT,dither=Image.FLOYDSTEINBERG); print("libimagequant")
except Exception as e:
    q=lo.quantize(255,method=Image.MEDIANCUT,kmeans=4,dither=Image.FLOYDSTEINBERG); print("mediancut+kmeans",e)
tiles=set()
for ty in range(20):
    for tx in range(30):
        tiles.add(q.crop((tx*8,ty*8,tx*8+8,ty*8+8)).tobytes())
print("colours",len(q.getcolors(256)),"unique 8x8 tiles",len(tiles),"of 600; 8bpp VRAM",len(tiles)*64,"bytes")
f=q.convert("RGB")
# GBA is 15-bit colour
f=f.point(lambda v:(v>>3)<<3)
d=ImageDraw.Draw(f)
d.rectangle((0,144,239,159),fill=(20,22,38))
fnt=ImageFont.truetype("/mnt/c/Users/chrsn/Desktop/retro-handheld-ethglobal/launcher/arca_launcher/assets/fonts/Outfit-Bold.ttf",9)
d.fontmode="1"
d.text((5,147),"ACT 1  BUILD",font=fnt,fill=(255,208,90))
d.text((82,147),"HR",font=fnt,fill=(150,160,190)); d.text((98,147),"06:40",font=fnt,fill=(235,235,245))
d.rectangle((140,149,205,154),outline=(120,130,160)); d.rectangle((141,150,141+int(64*0.42),153),fill=(120,220,120))
d.text((210,147),"42%",font=fnt,fill=(235,235,245))
f.save("$S/render/gba_frame.png")
f.resize((960,640),Image.NEAREST).save("$S/render/gba_frame_x4.png")
PY
