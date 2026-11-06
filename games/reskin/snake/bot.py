"""Steer Snake to its food in mGBA (headless), to check how eating looks. Closed loop by replay: each step re-runs
the game from power-on with the turns so far (the emulator is deterministic), looks at the last frame, and adds the
next turn towards the food. Stops when the food has been eaten; saves a zoomed strip of the frames around it.

  python bot.py ROM OUT.png"""
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import shoot                                       # noqa: E402

FOOD = (255, 214, 102)                             # gold: the ETH diamond's left facets
SNAKE = (98, 126, 234)                             # ETH blue
START = [("start", 100)]                         # title -> level 1 (another Start changes level)
STEP = 24                                          # frames between decisions
OPPOSITE = {"left": "right", "right": "left", "up": "down", "down": "up"}


def find(img, colour):
    px = img.load()
    near = lambda c: sum(abs(u - v) for u, v in zip(c, colour)) < 24   # the screen shows 5-bit colour
    pts = [(x, y) for y in range(2, 126) for x in range(2, 158) if near(px[x, y])]   # above the gold HUD bar
    if not pts:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), pts


def run(turns, frames):
    steps = [([k], a, a + 6) for k, a in START] + [([k], a, a + 6) for k, a in turns]
    keys = {"a": 0, "b": 1, "select": 2, "start": 3, "right": 4, "left": 5, "up": 6, "down": 7}
    steps = [([keys[k] for k in ks], a, b) for ks, a, b in steps]
    return shoot.shoot(ROM, steps, frames)


def head(img, heading):
    """The snake pixel furthest along its heading."""
    s = find(img, SNAKE)
    if not s:
        return None
    pts = s[2]
    key = {"right": lambda p: p[0], "left": lambda p: -p[0], "down": lambda p: p[1], "up": lambda p: -p[1]}[heading]
    return max(pts, key=key)


def main():
    global ROM
    ROM, out = sys.argv[1], sys.argv[2]
    turns, heading, t = [("right", 400)], "right", 400
    eaten, target, last_head = None, None, None
    for _ in range(300):
        t += STEP
        img = run(turns, [t])[t]
        food = find(img, FOOD)
        px = img.load()
        gold = lambda p: sum(abs(u - v) for u, v in zip(px[p], FOOD)) < 24
        if target is not None and not any(gold((target[0] + dx, target[1] + dy))
                                          for dx in range(-3, 4) for dy in range(-4, 5)
                                          if 0 <= target[0] + dx < 160 and 0 <= target[1] + dy < 126):
            eaten = t                                               # the ETH we were after is gone
            break
        h = head(img, heading)
        if food is None or h is None:
            continue
        if h == last_head and t < 800:                              # not moving yet (READY?): press the way again
            turns.append((heading, t))
            continue
        last_head = h
        target = min(food[2], key=lambda p: (p[0] - h[0]) ** 2 + (p[1] - h[1]) ** 2)   # the nearest ETH
        dx, dy = target[0] - h[0], target[1] - h[1]
        want = ("right" if dx > 0 else "left") if abs(dx) > abs(dy) else ("down" if dy > 0 else "up")
        if want == OPPOSITE[heading]:                               # can't reverse: turn sideways first
            want = ("down" if dy > 0 else "up") if heading in ("left", "right") else ("right" if dx > 0 else "left")
        if want != heading:
            turns.append((want, t))
            heading = want
    json.dump(turns, open(os.path.splitext(out)[0] + ".turns.json", "w"))
    if eaten is None:
        img.resize((480, 432), Image.NEAREST).save(out)
        print("never ate; last target", target, "frame", t, "turns", turns[-8:])
        return
    frames = list(range(eaten - 48, eaten + 48, 6))
    imgs = run(turns, frames)
    cx, cy = target
    box = (max(0, cx - 24), max(0, cy - 20), max(0, cx - 24) + 48, max(0, cy - 20) + 40)
    sheet = Image.new("RGB", (4 * 98, 4 * 82), (40, 40, 40))
    for i, fr in enumerate(frames[:16]):
        sheet.paste(imgs[fr].crop(box).resize((96, 80), Image.NEAREST), ((i % 4) * 98 + 1, (i // 4) * 82 + 1))
    sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(out)
    print("ate at frame", eaten, "->", out)


if __name__ == "__main__":
    main()
