"""Draw every launcher screen with the real sandbox library to PNG, for review.
   bash dev/screens.sh  ->  launcher/dev/screens/*.png"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from arca_launcher.actions import Action  # noqa: E402
from arca_launcher.app import Config, Display  # noqa: E402
from arca_launcher.handler.board import build  # noqa: E402
from arca_launcher.handler.flow import Flow  # noqa: E402
from arca_launcher.handler.ledger import Ledger  # noqa: E402
from arca_launcher.handler.mock import MockSponsors  # noqa: E402
from arca_launcher.library import load_library  # noqa: E402
from arca_launcher.model import Nav, Screen  # noqa: E402
from arca_launcher.render.chrome import Status  # noqa: E402

LIB = sys.argv[1] if len(sys.argv) > 1 else "/opt/arca-sandbox/launcher"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screens")
os.makedirs(OUT, exist_ok=True)
display = Display(Config(library_dir=LIB, state_path="/tmp/arca-screens-state.json"))
nav = Nav(load_library(LIB), last_played={"tobu-tobu-girl": 2.0, "shock-lobster": 1.0})
status = Status("9:41 PM", 72)


def shot(name, actions=()):
    for a in actions:
        nav.apply(a)
    for _ in range(40):
        display.views.draw(nav, 16, status)
    pygame.image.save(display.renderer.to_surface(), os.path.join(OUT, name + ".png"))


shot("01-home")
shot("02-home-next", [Action.RIGHT])
shot("03-home-buttons", [Action.LEFT, Action.DOWN, Action.RIGHT])
shot("04-info", [Action.A])
shot("05-info-next-shot", [Action.RIGHT])
nav.apply(Action.B)
nav.apply(Action.UP)
shot("06-library", [Action.RIGHT] * 40 + [Action.A])
shot("07-library-down", [Action.DOWN, Action.DOWN, Action.RIGHT])
nav.apply(Action.B)
shot("08-settings", [Action.R])
shot("09-settings-controls-on", [Action.DOWN, Action.DOWN, Action.A])     # the On-screen controls row, switched on
shot("10-about", [Action.DOWN, Action.A])

# PB the handler (Triangle): a few of its screens, on a mock sponsor whose clock never moves
CTX = {"game": "Marine Drive GP", "target": "RIA", "target_time": "1:41.17", "gap": "3.7 s", "rank": "5th",
       "new_rank": "3rd", "split": "0:01 to 0:02, -0.50 s", "board_case": "ok", "board_rows": build(6070, 6290).rows,
       "best_frames": 6290, "run_frames": 6000, "run_time": "1:40.00", "ghost_look": "the *cyan kart*",
       "wallet": "0xDE40...0000", "runs": "3", "sold": 0, "buyer": "ARJUN"}
for i, state in enumerate(("hub", "board", "target", "buy_pay", "result", "sale", "id_scan", "need_book"), start=11):
    flow = Flow(MockSponsors(lambda: 0), Ledger(book="ANY-7QZ"), "/tmp/arca-screens-handler.json", "marine-drive-gp",
                dict(CTX, **({"gap": "1.2 s"} if state == "result" else {})), lambda: "2026-11-06")
    nav.stack = [Screen.HOME]
    nav.open_handler(flow, state)
    flow.ms_in_state = 60000                                  # its animations done, its words typed out
    shot(f"{i}-handler-{state.replace('_', '-')}")            # id_scan: the real QR, "ANY% MOCK CODE ..."

# Home with the handler on: the PB button and the Triangle hint; attract mode's run-to-beat card
nav.handler_enabled = True
nav.board_times["marine-drive-gp"] = ("RIA", "1:41.27")
nav.stack = [Screen.HOME]
nav.row_index = next((i for i, g in enumerate(nav.row) if g is not None and g.id == "marine-drive-gp"), nav.row_index)
shot("19-home-pb")
nav.stack = [Screen.HOME, Screen.ATTRACT]
games = [g for g in nav.az if g.rom_exists and not g.app] or nav.az     # as attract mode cycles them
display.views.attract.ms = next((k for k, g in enumerate(games) if g.id == "marine-drive-gp"), 0) * 5000 + 2000
shot("20-attract-run-to-beat")
display.close()
print("wrote", OUT)
