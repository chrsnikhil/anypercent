"""A PNG of the whole level as the game draws it (sky, skyline, level map, entity sprites), for eyeballing the
design: /opt/arca-sandbox/venv/bin/python dev/level_preview.py OUT.png [first_col last_col] [--route KEYS]
With --route, the bot route's player path (from out/librules.so) is drawn as a line."""
import os
import sys

from PIL import Image, ImageDraw

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME, "tools", "art"))
sys.path.insert(0, os.path.join(GAME, "tools", "level"))
import build_art  # noqa: E402
import build_level  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
route = sys.argv[sys.argv.index("--route") + 1] if "--route" in sys.argv else None
if route:
    args.remove(route)
out = args[0]
rows, zones = build_level.parse()
c0, c1 = (int(args[1]), int(args[2])) if len(args) > 2 else (0, len(rows[0]) - 1)
W = (c1 - c0 + 1) * 16
img = Image.new("RGBA", (len(rows[0]) * 16, 192), build_art.SKY + (255,))
sky = build_art.skyline_image(512, 256, 200)
for x in range(0, img.width, 512):
    img.alpha_composite(sky.crop((0, 40, 512, 232)), (x, 0))
img.alpha_composite(build_level.render(rows, zones).crop((0, 0, img.width, 192)))
spr = {"E_BUG": build_art.bug_frames()[0], "E_CHAI": build_art.chai_frames()[0], "E_ORB": build_art.orb_frames()[0],
       "E_CHECK": build_art.shelf_frames()[0], "E_DOOR": build_art.door_frame()}
ents, start = build_level.entities(rows)
for kind, tx, ty in ents:
    im = spr[kind]
    x = tx * 16 + (16 - im.width) // 2 if kind != "E_DOOR" else tx * 16
    y = (ty + 1) * 16 - im.height + (4 if kind in ("E_BUG",) else 0)
    if kind in ("E_CHAI", "E_ORB"):
        y = ty * 16
    img.alpha_composite(im, (x, y))
hero = build_art.hero_frames()[0]
img.alpha_composite(hero, (start[0] * 16 - 8, (start[1] + 1) * 16 - 28))
if route:
    import ctypes
    sys.path.insert(0, os.path.join(GAME, "..", "common", "py"))
    import arcade_test as T
    lib = T.load_lib(os.path.join(GAME, "out", "librules.so"))
    with open(route) as f:
        keys = [int(line, 16) for line in f if line.strip()]
    pts = [(x + 6, y + 7) for x, y in T.pc_player(lib, keys)]
    ImageDraw.Draw(img).line(pts, fill=(255, 0, 0, 255), width=1)
img = img.crop((c0 * 16, 0, c0 * 16 + W, 192))
img.convert("RGB").save(out)
print(out, img.size)
