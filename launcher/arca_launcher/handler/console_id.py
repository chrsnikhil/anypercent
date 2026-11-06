"""This console's id: a random id kept in <state_dir>/console-id, made once (mode 0600) and read on every start after.
state_dir is the directory of the --state file, the same one as handler.json, so the ledger and the console id always
go together: two windows with two --state directories are two consoles, while two --state files in one directory share
one ledger and so are one console, by design. Copying the state folder copies the console: the id is a file, not a
hardware key.

The id goes only to the World bridge, which keys and tags it (the console shows that tag, e.g. C-7QZP, never the id).
It is never logged and never drawn."""
import logging
import os
import re
import secrets

log = logging.getLogger(__name__)

FILE = "console-id"
CONSOLE_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")    # what the bridge takes as a console id


def _read(path):
    try:
        with open(path, encoding="ascii") as f:
            text = f.read(256).strip()
    except (OSError, ValueError):
        return None
    return text if CONSOLE_RE.fullmatch(text) else None


def load_or_create(state_dir) -> str:
    """The console's id from state_dir, made there first if it has none (or an unreadable one). A directory that
    cannot be written gives an id for this run only: an unlinked console, never a missing one."""
    state_dir = state_dir or "."
    path = os.path.join(state_dir, FILE)
    found = _read(path)
    if found is not None:
        return found
    made = secrets.token_hex(16)
    try:
        os.makedirs(state_dir, exist_ok=True)
        if os.path.exists(path):                     # there, but not an id: replaced, never trusted
            log.warning("console id file unreadable: this console gets a new id (link it again)")
            os.unlink(path)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(made + "\n")
    except FileExistsError:                          # another window made it first: that one is this console's
        return _read(path) or made
    except OSError as e:
        log.warning("console id not saved (%s): an id for this run only", type(e).__name__)
    return made
