"""After bot.py: replay its turns, find the first meal (the eaten-counter in the HUD's first box changes while it
shows the ETH icon) and save a zoomed strip of the snake's head around that moment.

  python eat_check.py ROM TURNS.json OUT.png"""
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import shoot                                       # noqa: E402
import bot                                         # noqa: E402


def counter(img):
    """The first HUD box when it shows the ETH icon (gold pixels), else None."""
    box = img.crop((8, 136, 30, 144))
    if not any(sum(abs(u - v) for u, v in zip(p, bot.FOOD)) < 24 for p in box.getdata()):
        return None
    return box.crop((9, 0, 22, 8)).tobytes()


def main():
    rom, turns_path, out = sys.argv[1:4]
    bot.ROM = rom
    turns = [tuple(t) for t in json.load(open(turns_path))]
    end = max(t for _, t in turns)

    def changes(frames):
        imgs = bot.run(turns, frames)
        prev, out = None, []
        for f in frames:
            c = counter(imgs[f])
            if c is not None and prev is not None and c != prev:
                out.append(f)
            if c is not None:
                prev = c
        return out, imgs

    def first_change(frames):
        out, imgs = changes(frames)
        return (out[0] if out else None), imgs

    all_meals, coarse_imgs = changes(list(range(420, end, 48)))
    print("meals (to within 48 frames):", all_meals)
    pick = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    if len(all_meals) <= pick:
        print("no meal seen")
        return
    coarse = all_meals[pick]
    frames = list(range(coarse - 96, coarse + 48, 2))               # then frame by frame (well, every other)
    meal, imgs = first_change(frames)
    meal = meal or coarse
    sel = [f for f in frames if meal - 40 <= f <= meal + 40][::3][:15]
    before = imgs[max(f for f in imgs if f <= meal - 20)]          # the ETH the snake was about to eat
    s = bot.find(before, bot.SNAKE)
    food = bot.find(before, bot.FOOD)
    cx, cy = (int(s[0]), int(s[1])) if s else (80, 64)
    if s and food:
        fx, fy = min(food[2], key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
        cx, cy = fx, fy
    box = (max(0, cx - 32), max(0, cy - 24), max(0, cx - 32) + 64, max(0, cy - 24) + 48)
    sheet = Image.new("RGB", (5 * 130, 3 * 98), (40, 40, 40))
    for i, f in enumerate(sel):
        sheet.paste(imgs[f].crop(box).resize((128, 96), Image.NEAREST), ((i % 5) * 130 + 1, (i // 5) * 98 + 1))
    sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(out)
    print("first meal at frame", meal, "->", out)


if __name__ == "__main__":
    main()
