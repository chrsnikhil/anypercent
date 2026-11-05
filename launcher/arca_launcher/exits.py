"""How the last game or app ended, from the marks left in /run/anypercent (a tmpfs: gone at reboot).

  home-quit   written by the PS-button daemon (device/homekey.py) just before it ends a game or app: that ending
              was asked for, so it is no crash
  app-exit    written by an app's service as it stops (GTA III, the browser): "<unit> <result> <code> <status>",
              systemd's SERVICE_RESULT, EXIT_CODE and EXIT_STATUS; anything but "success" is a crash

Each mark is read once and removed."""
import os
from dataclasses import dataclass

RUN_DIR = "/run/anypercent"
HOME_QUIT_MAX_AGE = 60                     # seconds: a mark older than this belongs to some earlier quit


@dataclass(frozen=True)
class AppExit:
    unit: str                              # e.g. "anypercent-gta3.service"
    result: str
    code: str
    status: str

    @property
    def ok(self):
        return self.result == "success"


def _take(path):
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return None
    try:
        os.remove(path)
    except OSError:
        pass
    return text


def home_quit(run_dir, now):
    text = _take(os.path.join(run_dir, "home-quit"))
    try:
        return text is not None and now - float(text.strip()) <= HOME_QUIT_MAX_AGE
    except ValueError:
        return False


def app_exit(run_dir):
    text = _take(os.path.join(run_dir, "app-exit"))
    parts = (text or "").split()
    if len(parts) < 4:
        return None
    unit = parts[0] if parts[0].endswith(".service") else parts[0] + ".service"
    return AppExit(unit, parts[1], parts[2], parts[3])


CRASH_LOG = "crashes.log"                  # beside the launcher's settings (on /data when read-only): survives reboots
CRASH_LOG_KEEP = 20


def log_crash(state_dir, when, title, detail):
    """Add a crash to the log the Device health screen shows; the log keeps the last CRASH_LOG_KEEP."""
    path = os.path.join(state_dir, CRASH_LOG)
    try:
        os.makedirs(state_dir, exist_ok=True)
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = []
        clean = lambda s: str(s).replace("\t", " ").replace("\n", " ")
        lines = (lines + [f"{when}\t{clean(title)}\t{clean(detail or '')}"])[-CRASH_LOG_KEEP:]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass


def crashes(state_dir, n=6):
    """The last n crashes, newest first: [(when, title, detail)]."""
    try:
        with open(os.path.join(state_dir, CRASH_LOG), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        parts = line.split("\t")
        if len(parts) == 3:
            try:
                out.append((float(parts[0]), parts[1], parts[2]))
            except ValueError:
                continue
        if len(out) == n:
            break
    return out
