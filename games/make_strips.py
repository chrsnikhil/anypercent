"""Launcher tile strips for the arcade games: 12 frames sampled along each game's recorded route, cropped to
the launcher's 160 x 144 frame and written to /opt/arca-sandbox/games/boot/<id>.built.strip.png.
Usage (in the sandbox venv): python games/make_strips.py rushhour rush-hour [dir id ...]"""
import os
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "common", "py"))
import arcade_test as T  # noqa: E402

BOOT = "/opt/arca-sandbox/games/boot"


def route(gdir):
    path = os.path.join(gdir, "tests", "routes", "full_run.keys")
    frames = []
    for line in open(path):
        line = line.split("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) == 2:
            frames += [int(parts[0], 16)] * int(parts[1])
        else:
            frames.append(int(parts[0], 16))
    return frames


def strip(dirname, gid):
    gdir = os.path.join(ROOT, dirname)
    rom = [f for f in os.listdir(gdir) if f.endswith(".gba")][0]
    frames = route(gdir) + [0] * 240
    n = len(frames)
    picks = [30] + [int(n * k / 11) for k in range(1, 11)] + [n - 60]
    tmp = tempfile.mkdtemp()
    shots = [(f, os.path.join(tmp, "s%d.rgba" % f)) for f in picks]
    T.run_rom(os.path.join(gdir, rom), frames, shots=shots)
    out = Image.new("RGB", (160 * 12, 144))
    for i, (_, p) in enumerate(shots):
        im = Image.frombytes("RGBA", (240, 160), open(p, "rb").read()).convert("RGB")
        im = im.crop((30, 0, 210, 160)).resize((160, 144), Image.LANCZOS)
        out.paste(im, (160 * i, 0))
    os.makedirs(BOOT, exist_ok=True)
    dst = os.path.join(BOOT, gid + ".built.strip.png")
    out.save(dst)
    print(dst)


if __name__ == "__main__":
    args = sys.argv[1:]
    for d, g in zip(args[::2], args[1::2]):
        strip(d, g)
