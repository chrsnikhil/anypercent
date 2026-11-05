"""Launcher colour themes, one per sponsor panel, picked with the DualSense trick (Create + Options together, in the
launcher only). Every ground is dark so the white text works on all of them; the pad's light bar follows the theme."""
from dataclasses import dataclass

from .render import theme


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    bg: tuple          # screen ground
    panel: tuple       # cards
    accent: tuple      # highlights (the active tab's underline, the picker)
    tint: int          # how strongly the ground washes over a game's blurred art on Home, 0..255
    light: tuple       # DualSense light bar
    logo: str | None = None    # assets/ file, white on transparent (tools/make_sponsor_logos.py)
    label: bool = False        # the logo is a mark only: write the name beside it


THEMES = [
    Theme("anypercent", "Any%", (11, 13, 18), (22, 24, 30), (240, 102, 61), 0, (240, 102, 61)),
    Theme("world", "World", (6, 6, 7), (26, 26, 28), (255, 255, 255), 90, (255, 255, 255), "logo-world.png"),
    Theme("arkiv", "Arkiv", (10, 14, 58), (26, 32, 96), (246, 244, 239), 110, (24, 30, 169), "logo-arkiv.png"),
    Theme("arc", "Arc", (6, 20, 40), (20, 40, 66), (205, 221, 242), 110, (80, 150, 255), "logo-arc.png"),
    Theme("chainlink", "Chainlink", (8, 18, 56), (24, 42, 100), (55, 91, 210), 110, (55, 91, 210), "logo-chainlink.png", True),
    Theme("ethglobal", "ETHGlobal Mumbai", (46, 4, 24), (76, 16, 40), (255, 133, 0), 110, (255, 108, 0), "logo-ethglobal.png", True),
]
BY_ID = {t.id: t for t in THEMES}
DEFAULT = "anypercent"


def get(theme_id):
    return BY_ID.get(theme_id, BY_ID[DEFAULT])


def apply(theme_id):
    """Recolour the launcher: the views read these at draw time."""
    t = get(theme_id)
    theme.BG, theme.PANEL, theme.ACCENT, theme.TINT = t.bg, t.panel, t.accent, t.tint
    theme.CURRENT = t.id
    return t
