"""SSH to the Any% handheld: key login only, and only to the Pi whose host key is pinned in this repo.

  from anypercent_ssh import connect
  client, host = connect()          # ANYPERCENT_HOST, else anypercent.local, else a scan of the iPhone hotspot

The key is ~/.ssh/anypercent_ed25519 (or ANYPERCENT_KEY); its public half is in the Pi's authorized_keys.
The Pi's host key is device/anypercent_host_key.pub: any other machine answering on the address is refused,
so a look-alike on venue Wi-Fi cannot collect a login. Password login is off on the Pi (sshd_config.d)."""
import base64
import concurrent.futures as cf
import os
import socket

import paramiko

HERE = os.path.dirname(os.path.abspath(__file__))
HOST_KEY_FILE = os.path.join(HERE, "anypercent_host_key.pub")
KEY_FILE = os.environ.get("ANYPERCENT_KEY", os.path.expanduser("~/.ssh/anypercent_ed25519"))
USER = os.environ.get("ANYPERCENT_USER", "anypercent")
HOTSPOT = [f"172.20.10.{i}" for i in range(2, 15)]          # the iPhone Personal Hotspot's DHCP range


def pinned_key():
    kind, data = open(HOST_KEY_FILE, encoding="ascii").read().split()[:2]
    return kind, paramiko.PKey.from_type_string(kind, base64.b64decode(data))


def _answers_ssh(host):
    s = socket.socket()
    s.settimeout(2.5)
    try:
        s.connect((host, 22))
        return host if s.recv(40).startswith(b"SSH") else None
    except OSError:
        return None
    finally:
        s.close()


def find():
    """The Pi's address: ANYPERCENT_HOST, else anypercent.local, else the first SSH server on the hotspot."""
    if os.environ.get("ANYPERCENT_HOST"):
        return os.environ["ANYPERCENT_HOST"]
    try:
        return socket.gethostbyname("anypercent.local")
    except OSError:
        pass
    with cf.ThreadPoolExecutor(len(HOTSPOT)) as ex:
        hits = [h for h in ex.map(_answers_ssh, HOTSPOT) if h]
    return hits[0] if hits else None


def connect(host=None, timeout=30):
    host = host or find()
    if not host:
        raise SystemExit("Any% Pi not found (set ANYPERCENT_HOST, or join the iPhone hotspot)")
    kind, key = pinned_key()
    c = paramiko.SSHClient()
    c.get_host_keys().add(host, kind, key)
    c.set_missing_host_key_policy(paramiko.RejectPolicy())    # a different host key is refused, never learned
    c.connect(host, username=USER, key_filename=KEY_FILE, look_for_keys=False, allow_agent=False,
              timeout=timeout, banner_timeout=timeout)
    return c, host
