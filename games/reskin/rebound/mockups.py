"""Mockups for the full Rebound reskin (worlds, not just characters): real mGBA frames of the current build with the
sky, ground, grass tops and Forest repainted in each direction. Player, coins, enemies and HUD stay (already web3).

  A  "Mainnet"   starry navy sky; the ground is bevelled indigo chain blocks linked at the seams, with an ETH-blue
                 glowing top edge; the Forest is a neon Layer 2 grove (violet night, indigo trunks, cyan canopy)
  B  "Bull run"  light chart-paper sky with a grid; the ground is green candlesticks with wicks and a bright top;
                 the Forest is crypto winter (ice sky, slate trunks, snow)
Plus each direction's game over and end screens, drawn fresh (no faces on tokens).

  python mockups.py ART_DIR OUT.png      (ART_DIR has rebound-shot0..2.png: Plains, Plains, Forest)"""
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = "C:/Windows/Fonts/arialbd.ttf"
W, H = 160, 144

# original colours (from the frames)
SKY = (132, 165, 255)
DIRT = {(181, 82, 0): "light", (140, 66, 0): "mid", (99, 49, 0): "dark"}
GRASS = {(0, 206, 0): "light", (0, 165, 0): "dark"}
FLOWER = (255, 222, 0)
F_BG, F_BARK, F_LEAF, F_SKIN = (41, 74, 0), (123, 57, 0), (82, 156, 0), (198, 140, 99)

SCHEMES = {
    "A  Mainnet": dict(
        sky=(20, 22, 43), star=(192, 203, 246), star2=(98, 126, 234),
        block=(69, 74, 117), bevel_hi=(110, 118, 178), bevel_lo=(36, 38, 72), link=(138, 146, 178),
        top_hi=(192, 203, 246), top=(98, 126, 234), flower=(192, 203, 246),
        f_bg=(30, 18, 52), f_bark=(69, 74, 117), f_leaf=(0, 205, 220), f_skin=(138, 146, 178),
        screen_bg=(20, 22, 43), screen_fg=(192, 203, 246), screen_acc=(98, 126, 234),
        over="REKT", over_sub="the market took your coin", end="MAINNET", end_sub="thanks for playing"),
    "B  Bull run": dict(
        sky=(242, 244, 252), grid=(222, 226, 242), chart=(120, 200, 150),
        candle=(38, 166, 91), candle_hi=(96, 214, 146), candle_lo=(18, 104, 58), wick=(14, 70, 40),
        top_hi=(170, 255, 200), top=(0, 214, 110), flower=(255, 200, 60),
        f_bg=(206, 224, 242), f_bark=(84, 96, 128), f_leaf=(250, 252, 255), f_skin=(150, 190, 230),
        screen_bg=(242, 244, 252), screen_fg=(18, 104, 58), screen_acc=(235, 64, 64),
        over="REKT", over_sub="bear market", end="TO THE MOON", end_sub="thanks for playing"),
}


def paint_plains(img, s, night):
    out = img.copy()
    px = out.load()
    rnd = random.Random(7)
    stars = {(rnd.randrange(W), rnd.randrange(H)) for _ in range(40)}
    for y in range(H):
        for x in range(W):
            c = px[x, y]
            if c == SKY:
                if night:
                    px[x, y] = (s["star"] if (x, y) in stars and (x + y) % 3 else
                                s["star2"] if (x, y) in stars else s["sky"])
                else:
                    on_grid = x % 16 == 0 or y % 16 == 0
                    chart = abs(y - (110 - x * 0.45 - 8 * ((x // 20) % 2))) < 0.8
                    px[x, y] = s["chart"] if chart else s["grid"] if on_grid else s["sky"]
            elif c in DIRT:
                bx, by = x % 16, y % 16
                if night:                                   # chain blocks: bevel, plus a link at each seam
                    if bx == 0 or by == 0:
                        px[x, y] = s["bevel_hi"]
                    elif bx == 15 or by == 15:
                        px[x, y] = s["bevel_lo"]
                    elif by in (7, 8) and (bx < 2 or bx > 13):
                        px[x, y] = s["link"]
                    else:
                        px[x, y] = s["block"]
                else:                                       # candles: body with a wick through the gap
                    col = x % 8
                    if col == 7:
                        px[x, y] = s["wick"] if (y // 4) % 2 else s["sky"] if False else s["candle_lo"]
                    elif col == 0:
                        px[x, y] = s["candle_hi"]
                    else:
                        px[x, y] = s["candle"] if ((x // 8 + y // 12) % 5) else s["candle_lo"]
            elif c in GRASS:
                px[x, y] = s["top_hi"] if GRASS[c] == "light" else s["top"]
            elif c == FLOWER:
                px[x, y] = s["flower"]
    return out


def paint_forest(img, s):
    lut = {F_BG: s["f_bg"], F_BARK: s["f_bark"], F_LEAF: s["f_leaf"], F_SKIN: s["f_skin"]}
    out = img.copy()
    px = out.load()
    for y in range(H):
        for x in range(W):
            if x >= 104 and y >= 128:                     # the HUD box shares these colours: leave it
                continue
            px[x, y] = lut.get(px[x, y], px[x, y])
    return out


def screen(s, title, sub, coin):
    img = Image.new("RGB", (W, H), s["screen_bg"])
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype(FONT, 26 if len(title) < 8 else 18)
    d.text((W // 2 + 1, 52 + 1), title, font=big, fill=s["screen_acc"], anchor="mm")
    d.text((W // 2, 52), title, font=big, fill=s["screen_fg"], anchor="mm")
    d.text((W // 2, 100), sub, font=ImageFont.truetype(FONT, 9), fill=s["screen_fg"], anchor="mm")
    if coin:                                                # a plain USDC coin, no face, cracked for game over
        cx, cy, r = W // 2, 78, 9
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(39, 117, 202), outline=(255, 255, 255))
        d.text((cx, cy), "$", font=ImageFont.truetype(FONT, 11), fill=(255, 255, 255), anchor="mm")
        if coin == "cracked":
            d.line((cx + 2, cy - r, cx - 1, cy - 2, cx + 3, cy + 2, cx, cy + r), fill=s["screen_bg"], width=1)
    return img


def main():
    art, out_path = sys.argv[1], sys.argv[2]
    shots = [Image.open(os.path.join(art, f"rebound-shot{i}.png")).convert("RGB") for i in range(3)]
    S, gap, label = 3, 8, 22
    cols = 5
    sheet = Image.new("RGB", (cols * (W * S + gap) + gap, len(SCHEMES) * (H * S + gap + label) + gap), (24, 24, 32))
    d = ImageDraw.Draw(sheet)
    for r, (name, s) in enumerate(SCHEMES.items()):
        night = name.startswith("A")
        frames = [paint_plains(shots[0], s, night), paint_plains(shots[1], s, night), paint_forest(shots[2], s),
                  screen(s, s["over"], s["over_sub"], "cracked"), screen(s, s["end"], s["end_sub"], "coin")]
        y = gap + r * (H * S + gap + label)
        d.text((gap, y), name, font=ImageFont.truetype(FONT, 16), fill=(236, 239, 255))
        for i, f in enumerate(frames):
            sheet.paste(f.resize((W * S, H * S), Image.NEAREST), (gap + i * (W * S + gap), y + label))
    sheet.save(out_path)
    print("mockups ->", out_path)


if __name__ == "__main__":
    main()
