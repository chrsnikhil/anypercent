"""Real gameplay for the film: the shipped ROMs played headless on their recorded routes, frames saved as PNG.

  (WSL) cd games/zip && /opt/arca-sandbox/venv/bin/python ../../video/briefing/prep/capture_gameplay.py survey
        -> video/briefing/out/gameplay_survey/<ID>.jpg   (every 8th frame, a contact sheet, to pick the action)
  (WSL) ... capture_gameplay.py window ID FIRST COUNT
        -> video/briefing/public/game/<ID>/0000.png ...  (every frame of that window, 240 x 160)"""
import os
import sys
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "games", "common", "py"))
import arcade_test as T  # noqa: E402

SB = "/opt/arca-sandbox"
GAMES = {"SHIP": ("game", "ship-it.gba"), "RUSH": ("games/rushhour", "rush-hour.gba"), "ZIPG": ("games/zip", "zip.gba"),
         "MDGP": ("games/marinedrive", "marine-drive-gp.gba"), "SEGF": ("games/segfault", "segfault.gba")}


def route(gid):
    d, _ = GAMES[gid]
    with open(os.path.join(REPO, d, "tests", "routes", "full_run.keys")) as f:
        return [int(line, 16) for line in f if line.strip()]


def shots(gid, frames, out_dir):
    keys = route(gid)
    os.makedirs(out_dir, exist_ok=True)
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(0, len(frames), 16):                 # gba_run takes at most 16 --shot per run
            chunk = frames[i:i + 16]
            pairs = [(fr, os.path.join(tmp, f"{fr}.raw")) for fr in chunk]
            T.run_rom(os.path.join(SB, "games", "built", GAMES[gid][1]), keys[: max(chunk) + 1], shots=pairs, save_in=T.blank_save())
            for fr, p in pairs:
                out.append((fr, Image.frombytes("RGBA", (240, 160), open(p, "rb").read()).convert("RGB")))
    return out


def survey(ids=("RUSH", "MDGP", "SEGF"), stride=8):
    out = os.path.join(HERE, "..", "out", "gameplay_survey")
    os.makedirs(out, exist_ok=True)
    for gid in ids:
        n = len(route(gid))
        imgs = shots(gid, list(range(stride, n, stride)), out)
        cols = 20
        sheet = Image.new("RGB", (cols * 120, ((len(imgs) + cols - 1) // cols) * 80))
        d = ImageDraw.Draw(sheet)
        for i, (fr, im) in enumerate(imgs):
            x, y = (i % cols) * 120, (i // cols) * 80
            sheet.paste(im.resize((120, 80)), (x, y))
            if i % 5 == 0:
                d.text((x + 2, y + 2), str(fr), fill=(255, 255, 0))
        sheet.save(os.path.join(out, f"{gid}.jpg"), quality=80)
        print(gid, n, "frames ->", len(imgs), "shots")


def window(gid, first, count, sub=None):
    """sub: write to public/game/<sub>/<gid>/ instead (the reel), leaving the footage other acts use alone."""
    out = os.path.join(HERE, "..", "public", "game", *( [sub, gid] if sub else [gid] ))
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out) if os.path.isdir(out) else []:
        os.remove(os.path.join(out, f))
    imgs = shots(gid, list(range(first, first + count)), out)
    for i, (fr, im) in enumerate(imgs):
        im.save(os.path.join(out, f"{i:04d}.png"))
    print(gid, "frames", first, "..", first + count - 1, "->", out)


if __name__ == "__main__":
    if sys.argv[1] == "survey":                            # survey [ID,ID] [stride]
        survey(tuple(sys.argv[2].split(",")) if len(sys.argv) > 2 else ("RUSH", "MDGP", "SEGF"), int(sys.argv[3]) if len(sys.argv) > 3 else 8)
    else:                                                 # window ID FIRST COUNT [sub]
        window(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5] if len(sys.argv) > 5 else None)
