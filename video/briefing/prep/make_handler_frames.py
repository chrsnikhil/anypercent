"""The console's screens in THE HANDLER (src/acts/Handler.tsx): PB walking the sponsor steps, drawn by the real launcher
(launcher/arca_launcher: its handler flow, mock sponsors, views; headless SDL), one sequence per step from the moment
the step opens. The numbers are real: RIA is the shipped test log, "you" the slower run make_handler_run.py played and
replayed (public/handler/run.json). The sponsor calls are the launcher's mocks (its MOCK pill is on screen).

  (WSL) /opt/arca-sandbox/venv/bin/python video/briefing/prep/make_handler_frames.py
        -> video/briefing/public/handler/<step>/NN.jpg + screens.json"""
import io
import json
import os
import shutil
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "launcher"))

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from arca_launcher import coach  # noqa: E402
from arca_launcher.app import Config, Display  # noqa: E402
from arca_launcher.handler.flow import Flow  # noqa: E402
from arca_launcher.handler.ledger import Ledger  # noqa: E402
from arca_launcher.handler.mock import MockSponsors  # noqa: E402
from arca_launcher.handler_glue import GHOST_LOOKS, MOCK_WALLET, HandlerGlue  # noqa: E402
from arca_launcher.library import load_library  # noqa: E402
from arca_launcher.model import Nav, Screen  # noqa: E402
from arca_launcher.render.chrome import Status  # noqa: E402

OUT = os.path.join(HERE, "..", "public", "handler")
LIB = "/opt/arca-sandbox/launcher"
STEPS = ["id_scan", "board", "buy_pay", "ls_scan"]   # World ID (IDKit), Arkiv, Hedera x402, World ID (Agent Pass)
FRAMES, EVERY = 96, 2                                # each step's first 3.2 s, one image every 2 film frames (30 fps)
SIZE = (800, 480)                                    # native: the film shows them large


def context(run):
    you, ria = run["run"]["time_frames"], run["ria"]["time_frames"]
    ctx = {"game": "Marine Drive GP", "arcade": True, "buyer": "", "wallet": MOCK_WALLET, "split": "",
           "ghost_look": GHOST_LOOKS["MDGP"], "runs": "1", "sold": 0, "log_frames": ria, "best_frames": you,
           "run_frames": you, "run_time": coach.fmt_time(you)}
    ctx.update(HandlerGlue._board_ctx(ria, you))      # the launcher's own board around her log and your best
    return ctx


def main():
    with open(os.path.join(OUT, "run.json")) as f:
        run = json.load(f)
    display = Display(Config(library_dir=LIB, state_path="/tmp/handler-film-state.json"))
    games = load_library(LIB)
    nav = Nav(games)
    status = Status("9:41 PM", 72)
    index = {}
    for step in STEPS:
        d = os.path.join(OUT, step)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        ctx = dict(context(run), game_titles={g.id: g.title for g in games})
        flow = Flow(MockSponsors(lambda: 0), Ledger(book="ANY-7QZ"), "/tmp/handler-film.json", "marine-drive-gp", ctx,
                    lambda: "2026-11-07")
        nav.stack = [Screen.HOME]
        nav.open_handler(flow, step)
        n = 0
        for i in range(0, FRAMES, EVERY):
            flow.ms_in_state = round(i * 1000 / 60)
            display.views.draw(nav, 1000 / 60 * EVERY, status)
            raw = pygame.image.tobytes(display.renderer.to_surface(), "RGB")
            img = Image.frombytes("RGB", (800, 480), raw).resize(SIZE, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=88)
            with open(os.path.join(d, "%02d.jpg" % n), "wb") as f:
                f.write(buf.getvalue())
            n += 1
        index[step] = n
    display.close()
    with open(os.path.join(OUT, "screens.json"), "w") as f:
        json.dump({"steps": STEPS, "images": index, "every": EVERY,
                   "you": run["run"]["time_frames"], "ria": run["ria"]["time_frames"]}, f)
    print(index, "->", OUT)


if __name__ == "__main__":
    main()
