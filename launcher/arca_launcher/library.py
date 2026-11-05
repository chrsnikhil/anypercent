"""Load library.json (written by tools/build_library.py) into Game records."""
import json
import os
from dataclasses import dataclass, field

PLATFORM_NAMES = {"GB": "Game Boy", "GBC": "Game Boy Color"}


@dataclass(frozen=True)
class Game:
    id: str
    title: str
    authors: str = ""
    genre: str = ""
    platform: str = "GB"
    code_license: str = ""
    asset_license: str = ""
    source: str = ""
    rom: str | None = None
    rom_origin: str = "missing"      # "built", "author" or "missing"
    tile: str | None = None
    shots: tuple = ()
    bg: str | None = None
    rom_exists: bool = False
    arcade: dict | None = field(default=None, hash=False)   # {"id": "SHIP", "replay": tool}: an arcade-kit game
    app: str | None = None           # not a game: an app the device starts instead (hw.APP_SERVICES), e.g. "browser"
    how_to: dict | None = field(default=None, hash=False)   # {"goal": str, "controls": [[button, action], ...]}
    clip: tuple = ()                 # gameplay frames for attract mode (10 a second), relative to the library

    @property
    def platform_name(self):
        return PLATFORM_NAMES.get(self.platform, self.platform)


class LibraryError(Exception):
    pass


def load_library(library_dir):
    path = os.path.join(library_dir, "library.json")
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)["games"]
    except FileNotFoundError:
        raise LibraryError(f"No game library at {path}") from None
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise LibraryError(f"The game library at {path} is unreadable ({e})") from None
    games, seen = [], set()
    for e in entries if isinstance(entries, list) else []:
        if not isinstance(e, dict) or not e.get("id") or not e.get("title") or e["id"] in seen:
            continue
        seen.add(e["id"])
        rom = e.get("rom") or None
        app = e["app"] if isinstance(e.get("app"), str) and e["app"] else None
        arcade = e.get("arcade")                   # needs a string id: its runs, best and test log are named by it
        arcade = arcade if isinstance(arcade, dict) and isinstance(arcade.get("id"), str) and arcade["id"] else None
        games.append(Game(
            id=e["id"], title=e["title"], authors=e.get("authors") or "", genre=e.get("genre") or "",
            platform=e.get("platform") or "GB", code_license=e.get("code_license") or "",
            asset_license=e.get("asset_license") or "", source=e.get("source") or "",
            rom=rom, rom_origin="app" if app else e.get("rom_origin") or ("author" if rom else "missing"),
            tile=e.get("tile") or None, shots=tuple(e.get("shots") or ()), bg=e.get("bg") or None,
            rom_exists=bool(app) or (bool(rom) and os.path.isfile(rom)),
            arcade=arcade, app=app,
            how_to=e["how_to"] if isinstance(e.get("how_to"), dict) else None,
            clip=tuple(c for c in e.get("clip") or () if isinstance(c, str))))
    return games
