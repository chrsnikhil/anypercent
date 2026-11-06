"""The console's Arkiv signer, driven from Python: each call runs `node launcher/arkiv_signer/signer.mjs` once, writes
one JSON request line on its stdin and reads one JSON reply line from its stdout (the protocol is in signer.mjs). The
helper signs with Arkiv's own SDK from the console's own wallet; this module never sees the key, only the path of the
key file (handler/arkiv_wallet.py), which it passes as an absolute path.

`address(key_file)` is the wallet's address, lowercase (no network). `write(...)` writes what the bridge issued at
publish stage `sign`: a run and its listing in one transaction (`run` a SpecJSON spec, `run_key` None), or a relist
(`run` None, `run_key` the stamped run, `replaces` the console's own older listing or None). It returns
{"tx", "run", "listing"}, all lowercase 0x hex; a relist's `run` must come back as the run_key.

Everything that goes wrong is one SignError, never a crash; its kind says which:
  no_node    no Node binary, or the helper (its script, its npm packages) is not installed
  no_key     the key file is missing or holds no key
  unfunded   the console's wallet has no tGLM, or not enough for this transaction
  rpc        the node gave no usable answer (down, refused, rate limited, timed out), or the helper ran out of time
  rejected   the helper or the chain refused the request (not SpecJSON, a value that does not fit, a revert, the
             wrong chain, keys that moved)
  bad_reply  the helper answered something that is not the protocol
`detail` is the helper's one short line (no URL, no key), and `tx` the transaction when one went out. Callers run it
on a background thread: a write waits for its transaction, up to timeout_s."""
import json
import logging
import os
import re
import subprocess

log = logging.getLogger(__name__)

SCRIPT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "arkiv_signer",
                                       "signer.mjs"))
KINDS = frozenset({"no_node", "no_key", "unfunded", "rpc", "rejected", "bad_reply"})
HELPER_ERRORS = frozenset({"no_key", "unfunded", "rpc", "rejected"})
ADDRESS_TIMEOUT_S = 30.0          # Node's start (loading viem) takes seconds on a Pi
DETAIL_MAX = 240
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
_NOT_INSTALLED = ("ERR_MODULE_NOT_FOUND", "Cannot find module", "Cannot find package")


class SignError(Exception):
    """The signer did not do what was asked. kind: one of KINDS; detail: one short line; tx: the transaction hash
    when one was sent before it failed, else None."""

    def __init__(self, kind, detail="", tx=None):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind, self.detail, self.tx = kind, detail, tx


def _reply_of(stdout):
    """The last stdout line that is a JSON object, or None."""
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None
    return None


def _hash(value):
    return value.lower() if isinstance(value, str) and _HASH.fullmatch(value) else None


class Signer:
    """The helper as a callable: `node` is the Node binary (a name on PATH or a path), `script` the helper."""

    def __init__(self, node="node", script=SCRIPT):
        self.node, self.script = node, script

    def _call(self, request, timeout_s):
        if not os.path.isfile(self.script):
            raise SignError("no_node", "the signer helper is not installed")
        env = dict(os.environ, NODE_NO_WARNINGS="1")
        try:
            done = subprocess.run([self.node, self.script], input=json.dumps(request) + "\n", capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=timeout_s, env=env)
        except subprocess.TimeoutExpired:
            raise SignError("rpc", f"no answer from the signer in {timeout_s:g} s") from None
        except OSError as e:                              # no such binary, not executable
            raise SignError("no_node", type(e).__name__) from None
        reply = _reply_of(done.stdout)
        if reply is None:
            if any(mark in (done.stderr or "") for mark in _NOT_INSTALLED):
                raise SignError("no_node", "the signer's packages are not installed (npm ci in launcher/arkiv_signer)")
            raise SignError("bad_reply", f"no reply line (exit {done.returncode})")
        if "error" in reply:
            kind, detail = reply.get("error"), str(reply.get("detail", ""))[:DETAIL_MAX]
            if kind not in HELPER_ERRORS:
                raise SignError("bad_reply", f"unknown error {str(kind)[:40]!r}")
            raise SignError(kind, detail, _hash(reply.get("tx")))
        return reply

    def address(self, key_file):
        """The wallet's address in key_file, lowercase. SignError when there is none to give."""
        reply = self._call({"op": "address", "key_file": os.path.abspath(key_file)}, ADDRESS_TIMEOUT_S)
        found = reply.get("address")
        if not (isinstance(found, str) and _ADDRESS.fullmatch(found)):
            raise SignError("bad_reply", "no address in the reply")
        return found.lower()

    def write(self, key_file, rpc, chain_id, run, listing, timeout_s=90, run_key=None, replaces=None):
        """The issued run and listing (or a relist's listing) signed and sent from the wallet in key_file, in one
        transaction: {"tx", "run", "listing"}, lowercase. SignError otherwise."""
        reply = self._call({"op": "write", "key_file": os.path.abspath(key_file), "rpc": rpc, "chain_id": chain_id,
                            "run": run, "listing": listing, "run_key": run_key, "replaces": replaces}, timeout_s)
        out = {name: _hash(reply.get(name)) for name in ("tx", "run", "listing")}
        if None in out.values():
            raise SignError("bad_reply", "the reply lacks the transaction or a key")
        if run_key is not None and out["run"] != str(run_key).lower():
            raise SignError("bad_reply", "the relist came back naming another run")
        return out
