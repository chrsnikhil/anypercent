"""Launcher preferences and last-played times, kept in one small JSON file."""
import json
import os
from dataclasses import dataclass, field

MIN_BRIGHTNESS = 10


@dataclass
class Prefs:
    volume: int = 80
    brightness: int = 100
    touch_controls: bool = False          # on-screen controls (a touch gamepad) in games
    theme: str = "anypercent"             # themes.THEMES id, picked with the DualSense trick
    coach_greeted: str = ""               # the day (YYYY-MM-DD) PB last said hello
    handler_offered: str = ""             # the day PB the handler last offered a record book
    last_played: dict = field(default_factory=dict)


def default_path():
    return os.path.join(os.path.expanduser("~"), ".local", "state", "arca-launcher", "state.json")


def _pct(value, default, lo=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(min(100, max(lo, value)))


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return Prefs()
    p = Prefs()
    if not isinstance(data, dict):
        return p
    p.volume = _pct(data.get("volume"), p.volume)
    p.brightness = _pct(data.get("brightness"), p.brightness, lo=MIN_BRIGHTNESS)
    p.touch_controls = data.get("touch_controls") is True
    from .themes import BY_ID
    if data.get("theme") in BY_ID:
        p.theme = data["theme"]
    if isinstance(data.get("coach_greeted"), str):
        p.coach_greeted = data["coach_greeted"]
    if isinstance(data.get("handler_offered"), str):
        p.handler_offered = data["handler_offered"]
    played = data.get("last_played")
    if isinstance(played, dict):
        p.last_played = {k: float(v) for k, v in played.items()
                         if isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool)}
    return p


def save(path, prefs):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"volume": prefs.volume, "brightness": prefs.brightness, "touch_controls": prefs.touch_controls,
                   "theme": prefs.theme, "coach_greeted": prefs.coach_greeted,
                   "handler_offered": prefs.handler_offered, "last_played": prefs.last_played}, f, indent=1)
    os.replace(tmp, path)
