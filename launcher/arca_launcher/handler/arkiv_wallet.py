"""This console's Arkiv wallet: its private key in <state_dir>/arkiv-key, made once on the device (mode 0600, 32 random
bytes as 64 hex digits, a valid secp256k1 key) and read by nothing but the signer helper (handler/arkiv_sign.py,
launcher/arkiv_signer), which signs the console's run and listing records with it. Like console-id it sits beside
handler.json, so one --state directory is one console and one wallet; copying the folder copies the wallet (the
recorder's copy is the laptop console's). The key is never sent, logged or drawn.

A key file is never replaced once it holds anything: one that is not a key is reported, not thrown away (it may be
the only copy of a funded wallet); the owner fixes or removes it. Only an empty file (a start cut off between creating
the file and writing it) is made again: it holds nothing to lose.

The address is public. It is asked of the signer once and kept in <state_dir>/arkiv-address beside a short
fingerprint of the key it came from, so a new key is never shown with an old wallet's address. It is logged once per
start; a signer that cannot answer (no Node, no key) gives None, never a crash."""
import hashlib
import logging
import os
import re
import secrets

from arca_launcher.handler.arkiv_sign import SignError

log = logging.getLogger(__name__)

FILE = "arkiv-key"
ADDRESS_FILE = "arkiv-address"
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141   # the curve's order: keys are 1..n-1
_KEY = re.compile(r"(?:0[xX])?([0-9a-fA-F]{64})")
_ADDRESS = re.compile(r"0x[0-9a-f]{40}")
_logged = set()                   # addresses logged by this process


def _key_in(path):
    """(state, key): "missing", "empty", "bad" (holds something that is not a key, or cannot be read) or "key" with
    the key as 64 lowercase hex."""
    try:
        with open(path, "rb") as f:
            raw = f.read(256)
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "bad", None
    text = raw.decode("ascii", "replace").strip()
    if not text:
        return "empty", None
    m = _KEY.fullmatch(text)
    if m and 0 < int(m.group(1), 16) < SECP256K1_N:
        return "key", m.group(1).lower()
    return "bad", None


def _new_key():
    while True:
        k = secrets.token_bytes(32)
        if 0 < int.from_bytes(k, "big") < SECP256K1_N:
            return k.hex()


def _owner_only(path):
    """A key file others can read is closed again (a copy that lost its mode); best effort."""
    if os.name != "posix":
        return
    try:
        if os.stat(path).st_mode & 0o077:
            os.chmod(path, 0o600)
    except OSError:
        pass


def key_file(state_dir) -> str:
    """The path of this console's key file in state_dir, the key made there first if it has none. A directory that
    cannot be written still gives the path: the signer then reports no_key, and the console says so."""
    state_dir = state_dir or "."
    path = os.path.join(state_dir, FILE)
    state, _ = _key_in(path)
    if state == "key":
        _owner_only(path)
        return path
    if state == "bad":
        log.warning("arkiv key file holds no key: this console cannot sign until the owner fixes or removes it "
                    "(it is never replaced)")
        return path
    try:
        os.makedirs(state_dir, exist_ok=True)
        if state == "empty":
            os.unlink(path)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(_new_key() + "\n")
            f.flush()
            os.fsync(f.fileno())
        log.info("arkiv wallet made for this console")
    except FileExistsError:                           # another window made it first: that one is this console's
        pass
    except OSError as e:
        log.warning("arkiv key not saved (%s): this console cannot sign", type(e).__name__)
    return path


def _fingerprint(key):
    return hashlib.sha256(("anypercent arkiv-address " + key).encode("ascii")).hexdigest()[:16]


def _cached(path, fingerprint):
    try:
        with open(path, encoding="ascii") as f:
            parts = f.read(200).split()
    except (OSError, ValueError):
        return None
    if len(parts) == 2 and _ADDRESS.fullmatch(parts[0]) and parts[1] == fingerprint:
        return parts[0]
    return None


def _keep(path, found, fingerprint):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="ascii") as f:
            f.write(f"{found} {fingerprint}\n")
        os.replace(tmp, path)
    except OSError as e:
        log.warning("arkiv address not saved (%s): asked again next start", type(e).__name__)


def address(state_dir, signer) -> "str | None":
    """This console's wallet address, lowercase, or None when it has no key or the signer cannot say (no Node, no
    packages). The key is made first if there is none; the address is asked of `signer` (an arkiv_sign.Signer) only
    when arkiv-address does not hold it for this key."""
    state_dir = state_dir or "."
    path = key_file(state_dir)
    state, key = _key_in(path)
    if state != "key":
        return None
    fingerprint = _fingerprint(key)
    del key
    cache = os.path.join(state_dir, ADDRESS_FILE)
    found = _cached(cache, fingerprint)
    if found is None:
        try:
            found = signer.address(path)
        except SignError as e:
            log.warning("arkiv wallet address unknown (%s): %s", e.kind, e.detail)
            return None
        except Exception as e:                        # a signer that breaks its contract never stops the console
            log.warning("arkiv wallet address unknown (%s)", type(e).__name__)
            return None
        found = found.lower() if isinstance(found, str) else ""
        if not _ADDRESS.fullmatch(found):
            log.warning("arkiv wallet address unknown (not an address)")
            return None
        _keep(cache, found, fingerprint)
    if found not in _logged:
        _logged.add(found)
        log.info("arkiv wallet %s", found)
    return found


def short(address) -> "str | None":
    """A wallet address as the console shows it, "0x1a2b…9f3e" (0x, its first 4 hex digits, an ellipsis, its
    last 4), as the bridge's link text names it; None for anything that is not an address."""
    low = address.lower() if isinstance(address, str) else ""
    return low[:6] + "\u2026" + low[-4:] if _ADDRESS.fullmatch(low) else None
