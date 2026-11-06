"""Play a Game Boy (Color) ROM headless in mGBA, the emulator the console runs, with a scripted input, and save a
contact sheet of frames: how a reskin looks in the game, title to gameplay. (PyBoy drew Rebound's levels without
the player or the HUD numbers; mGBA draws them.)

  python shoot.py <rom> <out.png> [--script "start@200,start@500,right@1500:5000"] [--shots 300,600,...]

A script step is buttons@frame (a tap) or buttons@from:to (held), buttons joined by '+'. Runs out/gb_run (SHIP IT!'s
gba_run.c linked against a libmgba with the Game Boy core, toolchains/mgba-src/build-gb), 16 screenshots a pass."""
import argparse
import os
import subprocess
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "out", "gb_run")    # game/tools/gba_run/gba_run.c on a libmgba built with the GB core
KEYS = {"a": 0, "b": 1, "select": 2, "start": 3, "right": 4, "left": 5, "up": 6, "down": 7}


def parse(script):
    steps = []
    for part in filter(None, script.split(",")):
        keys, _, when = part.partition("@")
        a, _, b = when.partition(":")
        steps.append(([KEYS[k] for k in keys.split("+")], int(a), int(b) if b else int(a) + 6))
    return steps


def script_text(steps, frames):
    """gb_run's input: "<keys hex> <count>" lines, one per run of the same keys."""
    lines, prev, count = [], None, 0
    for f in range(1, frames + 1):
        mask = 0
        for bits, a, b in steps:
            if a <= f < b:
                for bit in bits:
                    mask |= 1 << bit
        if mask == prev:
            count += 1
        else:
            if prev is not None:
                lines.append(f"{prev:x} {count}")
            prev, count = mask, 1
    lines.append(f"{prev:x} {count}")
    return "\n".join(lines) + "\n"


def shoot(rom, steps, shots):
    """{frame: PIL image} for the asked frames."""
    frames = max(shots)
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        sc = os.path.join(tmp, "input.txt")
        with open(sc, "w") as f:
            f.write(script_text(steps, frames))
        for i in range(0, len(shots), 16):
            args = [RUNNER, rom, sc]
            for s in shots[i:i + 16]:
                args += ["--shot", str(s), os.path.join(tmp, f"{s}.rgba")]
            subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
            for s in shots[i:i + 16]:
                raw = open(os.path.join(tmp, f"{s}.rgba"), "rb").read()
                w, h = (160, 144) if len(raw) == 160 * 144 * 4 else (256, 224)   # mGBA's GB buffer is SGB-sized
                out[s] = Image.frombytes("RGBA", (w, h), raw).convert("RGB").crop((0, 0, 160, 144))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("rom")
    p.add_argument("out")
    p.add_argument("--script", default="")
    p.add_argument("--shots", default="")
    p.add_argument("--every", type=int, default=150)
    p.add_argument("--frames", type=int, default=3600)
    p.add_argument("--cols", type=int, default=8)
    p.add_argument("--big", default="", help="frames also saved alone at 3x, e.g. 900,2400")
    a = p.parse_args()
    shots = sorted({int(x) for x in a.shots.split(",") if x} or set(range(a.every, a.frames + 1, a.every)))
    big = {int(x) for x in a.big.split(",") if x}
    imgs = shoot(a.rom, parse(a.script), sorted(set(shots) | big))
    for f in big:
        imgs[f].resize((imgs[f].width * 3, imgs[f].height * 3), Image.NEAREST).save(
            os.path.splitext(a.out)[0] + f"-{f}.png")
    cols = min(a.cols, len(shots))
    rows = (len(shots) + cols - 1) // cols
    w, h = imgs[shots[0]].size
    sheet = Image.new("RGB", (cols * (w + 2), rows * (h + 2)), (40, 40, 40))
    for i, f in enumerate(shots):
        sheet.paste(imgs[f], ((i % cols) * (w + 2) + 1, (i // cols) * (h + 2) + 1))
    sheet.save(a.out)
    print(a.out, len(shots), "frames")


if __name__ == "__main__":
    main()
