import gc
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

LAUNCHER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(LAUNCHER_DIR, "tests", "out")
sys.path.insert(0, LAUNCHER_DIR)
sys.path.insert(0, os.path.join(LAUNCHER_DIR, "tools"))
os.makedirs(OUT_DIR, exist_ok=True)

import json

import pytest
from PIL import Image, ImageDraw

FRAME = (160, 144)
PALETTE = [(200, 40, 40), (40, 160, 60), (40, 60, 200), (220, 180, 30),
           (160, 40, 160), (30, 170, 170), (240, 120, 30), (90, 90, 90)]
LONG_TITLE = "The Extraordinarily Long Title of a Game That Keeps Going"

FIXTURE_GAMES = [
    {"title": "Alpha Quest", "authors": "Ada", "genre": "Platformer", "platform": "GB",
     "code_license": "MIT", "asset_license": "CC BY 4.0", "source": "https://example.org/alpha"},
    {"title": "Beta Blocks", "authors": "Bo", "genre": "Puzzle", "platform": "GBC",
     "code_license": "GPL-3.0", "asset_license": "same as code", "source": "https://example.org/beta"},
    {"title": "Gamma", "authors": "Gil", "genre": "Shooter", "platform": "GB",
     "code_license": "Zlib", "asset_license": "same as code", "source": "https://example.org/gamma"},
    {"title": LONG_TITLE, "authors": "A Very Long Studio Name Collective and All of Their Friends",
     "genre": "Adventure", "platform": "GB", "code_license": "Zlib",
     "asset_license": "CC BY 4.0 (all images, text, sound, music, and the printed manual too)",
     "source": "https://example.org/a/very/long/path/to/the/repository/of/this/particular/game"},
]


def frame(kind, color=(0, 0, 0)):
    img = Image.new("RGB", FRAME, (255, 255, 255))
    d = ImageDraw.Draw(img)
    if kind == "checker":
        for y in range(0, FRAME[1], 8):
            for x in range(0, FRAME[0], 8):
                if (x // 8 + y // 8) % 2:
                    d.rectangle([x, y, x + 7, y + 7], fill=color)
    elif kind == "stripes":
        for x in range(0, FRAME[0], 4):
            d.rectangle([x, 0, x + 1, FRAME[1] - 1], fill=color)
    return img


def save_strip(path, frames):
    strip = Image.new("RGB", (FRAME[0] * len(frames), FRAME[1]))
    for i, f in enumerate(frames):
        strip.paste(f, (i * FRAME[0], 0))
    strip.save(path)


@pytest.fixture
def sandbox_games(tmp_path):
    games_dir = tmp_path / "games"
    for sub in ("built", "roms", "boot"):
        (games_dir / sub).mkdir(parents=True)
    (games_dir / "built" / "alpha-quest.gb").write_bytes(b"built")
    (games_dir / "roms" / "alpha-quest.gb").write_bytes(b"author")
    (games_dir / "roms" / "beta-blocks.gbc").write_bytes(b"author")
    long_id = "the-extraordinarily-long-title-of-a-game-that-keeps-going"
    (games_dir / "roms" / f"{long_id}.gb").write_bytes(b"author")
    save_strip(games_dir / "boot" / "alpha-quest.built.strip.png",
               [frame("blank"), frame("checker"), frame("blank"), frame("blank")]
               + [frame("stripes", c) for c in PALETTE])
    save_strip(games_dir / "boot" / "beta-blocks.official.strip.png", [frame("stripes", (0, 0, 200))] * 12)
    save_strip(games_dir / "boot" / f"{long_id}.official.strip.png",
               [frame("blank")] * 5 + [frame("checker", (0, 120, 0))] + [frame("blank")] * 6)
    games_json = tmp_path / "games.json"
    games_json.write_text(json.dumps({"games": FIXTURE_GAMES}), encoding="utf-8")
    return str(games_json), str(games_dir)


@pytest.fixture
def library_dir(tmp_path, sandbox_games):
    import build_library
    out = tmp_path / "library"
    build_library.build(sandbox_games[0], sandbox_games[1], str(out), picks_path=None)
    return str(out)


from types import SimpleNamespace


@pytest.fixture
def screen(library_dir):
    import pygame
    from pygame._sdl2.video import Renderer, Window
    from arca_launcher.library import load_library
    from arca_launcher.render.art import Art
    from arca_launcher.render.gfx import Gfx
    pygame.display.init()
    pygame.font.init()
    win = Window("test", size=(800, 480))
    ren = Renderer(win)
    ren.logical_size = (800, 480)
    gfx = Gfx(ren)
    ns = SimpleNamespace(win=win, ren=ren, gfx=gfx, art=Art(gfx, library_dir), games=load_library(library_dir))
    yield ns
    # Free the renderer (and its textures) before its window: a Renderer collected later would destroy a stale
    # SDL renderer pointer, which can be the next test's renderer (its textures then go "invalid" at random).
    ns.__dict__.clear()
    del ren, gfx
    gc.collect()
    win.destroy()
    pygame.display.quit()


def snapshot(ren, name):
    import pygame
    surf = ren.to_surface()
    pygame.image.save(surf, os.path.join(OUT_DIR, name + ".png"))
    return surf


def distinct_colours(surf, step=7):
    return len({tuple(surf.get_at((x, y)))[:3] for x in range(0, surf.get_width(), step)
                for y in range(0, surf.get_height(), step)})
