"""The console's screen in THE COACH: the real launcher (launcher/arca_launcher, its own drawing code, headless SDL)
showing home with the booth lineup and PB saying the line make_coach.py got from coach.after_run(), typing out at the
launcher's own speed. One PNG a film frame (60 fps), identical frames shared.

  (WSL) /opt/arca-sandbox/venv/bin/python video/briefing/prep/make_coach_frames.py
        -> video/briefing/public/coach/screen/NNN.jpg + screen.json (film frame -> image)"""
import hashlib
import io
import json
import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "launcher"))
sys.path.insert(0, os.path.join(REPO, "launcher", "tools"))

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

import build_library  # noqa: E402
from arca_launcher.app import Config, Display  # noqa: E402
from arca_launcher.coach import Line  # noqa: E402
from arca_launcher.library import load_library  # noqa: E402
from arca_launcher.model import Nav  # noqa: E402
from arca_launcher.render.chrome import Status  # noqa: E402

OUT = os.path.join(HERE, "..", "public", "coach", "screen")
FRAMES, LEAD = 420, 24                 # film frames drawn; PB's box opens after LEAD (the run just ended)
COACH = json.load(open(os.path.join(HERE, "..", "public", "coach", "coach.json"), encoding="utf-8"))


def lineup():
    """The booth lineup, without the personal GTA III build (never shown)."""
    ids = build_library.read_lineup(os.path.join(REPO, "docs", "games", "lineup.txt"))
    return [g for g in ids if g != "gta-iii"]


def main():
    lib = tempfile.mkdtemp(prefix="coach-lib-")
    build_library.build(os.path.join(REPO, "docs", "games", "games.json"), "/opt/arca-sandbox/games", lib, lineup=lineup())
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))
    display = Display(Config(library_dir=lib, state_path=os.path.join(lib, "state.json")))
    # home lists the most recently played first: Rush Hour (the run just played), then the other four arcade games
    nav = Nav(load_library(lib), last_played={"rush-hour": 9.0, "marine-drive-gp": 8.0, "segfault": 7.0, "zip": 6.0, "ship-it": 5.0})
    status = Status("9:41 PM", 72)
    line = COACH["lines"][0]
    seen, index = {}, []
    for i in range(FRAMES):
        if i == LEAD:
            nav.say([Line(line["mood"], line["text"], line["kind"])])
        if nav.mascot is not None:
            nav.mascot_text, nav.mascot_ms = nav.mascot.text, round((i - LEAD) * 1000 / 60)
        display.views.draw(nav, 1000 / 60, status)
        raw = pygame.image.tobytes(display.renderer.to_surface(), "RGB")
        key = hashlib.sha1(raw).hexdigest()
        if key not in seen:
            seen[key] = len(seen)
            buf = io.BytesIO()
            Image.frombytes("RGB", (800, 480), raw).save(buf, "JPEG", quality=92)
            with open(os.path.join(OUT, "%03d.jpg" % seen[key]), "wb") as f:
                f.write(buf.getvalue())
        index.append(seen[key])
    display.close()
    with open(os.path.join(OUT, "..", "screen.json"), "w") as f:
        json.dump({"lead": LEAD, "frames": index, "images": len(seen), "text": line["text"]}, f)
    print(FRAMES, "frames,", len(seen), "images ->", OUT)


if __name__ == "__main__":
    main()
