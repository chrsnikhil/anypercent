"""Screenshots of the ROM along the bot route (or idle frames), as PNGs, for looking at the game:
    /opt/arca-sandbox/venv/bin/python dev/shots.py OUT_DIR FRAME [FRAME ...] [--scale N] [--ghost]
Frames count from power-on over tests/routes/full_run.keys followed by idle frames and a Start (results left)."""
import os
import sys
import tempfile

from PIL import Image

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME, "..", "common", "py"))
sys.path.insert(0, os.path.join(GAME, "tests"))
import arcade_test as T  # noqa: E402
from arcade_test import S  # noqa: E402
from conftest import load_keys  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
scale = 1
if "--scale" in sys.argv:
    scale = int(sys.argv[sys.argv.index("--scale") + 1])
    args.remove(str(scale))
out, frames = args[0], [int(a) for a in args[1:]]
os.makedirs(out, exist_ok=True)
keys = load_keys("full_run.keys") + [0] * 120
keys += [0] * max(0, max(frames) - len(keys))
save = T.blank_save()
if "--ghost" in sys.argv:
    lib = T.load_lib(os.path.join(GAME, "out", "librules.so"))
    pts = T.pc_player(lib, keys)
    save = T.save_with(T.game_id(lib), ghost=S.ghost_bytes(T.game_id(lib), 0, 4, [(x - 40, y, 0, 0x80) for x, y in pts[::4]]))
with tempfile.TemporaryDirectory() as tmp:
    shots = [(f, os.path.join(tmp, "%d.rgba" % f)) for f in frames]
    T.run_rom(os.path.join(GAME, "rushhour.gba"), keys[:max(frames)], save_in=save, shots=shots)
    for f, path in shots:
        with open(path, "rb") as fh:
            img = Image.frombytes("RGBA", (240, 160), fh.read()).convert("RGB")
        if scale > 1:
            img = img.resize((240 * scale, 160 * scale), Image.NEAREST)
        img.save(os.path.join(out, "f%05d.png" % f))
        print(os.path.join(out, "f%05d.png" % f))
