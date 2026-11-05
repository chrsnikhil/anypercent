"""Volume and brightness set from the controller (PS + D-pad, device/homekey.py), which works in games and apps
too: the home key writes the new levels to /run/anypercent/levels and the launcher takes them up as its own
settings, showing the change if it happens while it is on screen."""
import json
import os


def read(run_dir):
    """{"volume", "brightness", "changed"} from the home key, or None."""
    try:
        with open(os.path.join(run_dir, "levels")) as f:
            d = json.load(f)
        return {"volume": int(d["volume"]), "brightness": int(d["brightness"]), "changed": float(d["changed"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None
