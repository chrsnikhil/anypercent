"""The console's signer wrapper (handler/arkiv_sign.py): one `node signer.mjs` per call, one JSON line in and one out.
A fake node (a script printing a canned reply) stands in for the helper; every way the call can go wrong is one
SignError kind, never a crash. Two tests at the end run the real helper when Node and its packages are installed
(offline: an address, and a write to a port nothing listens on)."""
import json
import os
import shutil
import socket
import sys

import pytest

from arca_launcher.handler import arkiv_sign
from arca_launcher.handler.arkiv_sign import SCRIPT, SignError, Signer

TX = "0x" + "ab" * 32
RUN = "0x" + "cd" * 32
LISTING = "0x" + "ef" * 32
RUN_SPEC = {"values": {"game": "MDGP", "frames": 5025, "log_enc": {"$bytes": "AAEC"}},
            "flags": {"readonly": True, "permissionlessExtension": True},
            "expiry": {"kind": "atDate", "date": {"$date": "2027-01-30T00:00:00.000Z"}, "atLeastDays": 1}}
LISTING_SPEC = {"values": {"game": "MDGP", "price": "0.1", "frames": {"$big": "5025"}},
                "flags": {"readonly": True, "permissionlessExtension": False}, "expiry": {"kind": "days", "days": 7}}
HARDHAT_KEY = "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"   # public test key, holds nothing
HARDHAT_ADDRESS = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"


def fake_node(tmp_path, stdout="", stderr="", code=0, sleep=0.0):
    """(node, script): an executable that saves its stdin beside itself and answers with the canned text."""
    node = tmp_path / "fake-node"
    node.write_text(
        f"#!{sys.executable}\n"
        "import sys, time\n"
        f"open({str(tmp_path / 'stdin.txt')!r}, 'w').write(sys.stdin.read())\n"
        f"time.sleep({sleep!r})\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({code!r})\n", encoding="utf-8")
    node.chmod(0o755)
    script = tmp_path / "signer.mjs"
    script.write_text("// stand-in\n", encoding="utf-8")
    return str(node), str(script)


def sent(tmp_path):
    return json.loads((tmp_path / "stdin.txt").read_text(encoding="utf-8"))


def reply(**kw):
    return json.dumps(kw) + "\n"


def signer(tmp_path, **kw):
    node, script = fake_node(tmp_path, **kw)
    return Signer(node=node, script=script)


# ---- write ----------------------------------------------------------------------------------------------------------

def test_a_publish_sends_the_issued_specs_and_returns_the_keys(tmp_path):
    s = signer(tmp_path, stdout=reply(tx=TX.upper().replace("0X", "0x"), run=RUN, listing=LISTING))
    out = s.write("arkiv-key", "https://rpc.example", 7794095, RUN_SPEC, LISTING_SPEC)
    assert out == {"tx": TX, "run": RUN, "listing": LISTING}
    req = sent(tmp_path)
    assert req == {"op": "write", "key_file": os.path.abspath("arkiv-key"), "rpc": "https://rpc.example",
                   "chain_id": 7794095, "run": RUN_SPEC, "listing": LISTING_SPEC, "run_key": None, "replaces": None}


def test_a_relist_sends_the_run_key_and_what_it_replaces_and_must_get_that_run_back(tmp_path):
    old = "0x" + "11" * 32
    s = signer(tmp_path, stdout=reply(tx=TX, run=RUN, listing=LISTING))
    out = s.write("k", "https://rpc.example", 7794095, None, LISTING_SPEC, run_key=RUN, replaces=old)
    assert out == {"tx": TX, "run": RUN, "listing": LISTING}
    req = sent(tmp_path)
    assert req["run"] is None and req["run_key"] == RUN and req["replaces"] == old
    other = signer(tmp_path, stdout=reply(tx=TX, run="0x" + "22" * 32, listing=LISTING))
    with pytest.raises(SignError) as e:
        other.write("k", "https://rpc.example", 7794095, None, LISTING_SPEC, run_key=RUN)
    assert e.value.kind == "bad_reply"


@pytest.mark.parametrize("kind", ["unfunded", "rpc", "rejected", "no_key"])
def test_each_helper_error_is_its_sign_error(tmp_path, kind):
    s = signer(tmp_path, stdout=reply(error=kind, detail="the wallet holds no tGLM"), code=2)
    with pytest.raises(SignError) as e:
        s.write("k", "https://rpc.example", 7794095, RUN_SPEC, LISTING_SPEC)
    assert e.value.kind == kind and e.value.detail == "the wallet holds no tGLM"


def test_an_error_after_the_transaction_went_out_names_it(tmp_path):
    s = signer(tmp_path, stdout=reply(error="rejected", detail="the predicted keys moved", tx=TX), code=2)
    with pytest.raises(SignError) as e:
        s.write("k", "https://rpc.example", 7794095, RUN_SPEC, LISTING_SPEC)
    assert e.value.kind == "rejected" and e.value.tx == TX


def test_an_error_the_protocol_does_not_have_is_a_bad_reply(tmp_path):
    s = signer(tmp_path, stdout=reply(error="on_fire", detail="x"), code=2)
    with pytest.raises(SignError) as e:
        s.write("k", "https://rpc.example", 7794095, RUN_SPEC, LISTING_SPEC)
    assert e.value.kind == "bad_reply"


def test_no_node_binary_is_no_node(tmp_path):
    script = tmp_path / "signer.mjs"
    script.write_text("//\n", encoding="utf-8")
    s = Signer(node=str(tmp_path / "no-such-node"), script=str(script))
    with pytest.raises(SignError) as e:
        s.write("k", "https://rpc.example", 7794095, RUN_SPEC, LISTING_SPEC)
    assert e.value.kind == "no_node"
    with pytest.raises(SignError) as e:
        s.address("k")
    assert e.value.kind == "no_node"


def test_no_helper_script_is_no_node(tmp_path):
    node, _ = fake_node(tmp_path, stdout=reply(tx=TX, run=RUN, listing=LISTING))
    with pytest.raises(SignError) as e:
        Signer(node=node, script=str(tmp_path / "missing.mjs")).write("k", "https://r", 1, RUN_SPEC, LISTING_SPEC)
    assert e.value.kind == "no_node"


def test_helper_packages_not_installed_is_no_node(tmp_path):
    s = signer(tmp_path, code=1, stderr="node:internal/errors:497\n  ErrorCaptureStackTrace(err);\n"
                                         "Error [ERR_MODULE_NOT_FOUND]: Cannot find package '@arkiv-network/sdk'\n")
    with pytest.raises(SignError) as e:
        s.write("k", "https://rpc.example", 7794095, RUN_SPEC, LISTING_SPEC)
    assert e.value.kind == "no_node"


@pytest.mark.parametrize("stdout,code", [("", 0), ("", 1), ("garbage\n", 0), ("[1, 2]\n", 0), ("{\"tx\": \n", 0),
                                         ("\"ok\"\n", 0)])
def test_garbage_stdout_is_a_bad_reply(tmp_path, stdout, code):
    s = signer(tmp_path, stdout=stdout, code=code, stderr="Segmentation fault\n")
    with pytest.raises(SignError) as e:
        s.write("k", "https://rpc.example", 7794095, RUN_SPEC, LISTING_SPEC)
    assert e.value.kind == "bad_reply"


@pytest.mark.parametrize("bad", [{"tx": TX, "run": RUN}, {"tx": TX, "listing": LISTING}, {"run": RUN, "listing": LISTING},
                                 {"tx": TX, "run": RUN, "listing": "0x1234"}, {"tx": "nope", "run": RUN, "listing": LISTING},
                                 {"tx": TX, "run": 5, "listing": LISTING}])
def test_a_reply_without_both_keys_and_the_tx_is_a_bad_reply(tmp_path, bad):
    s = signer(tmp_path, stdout=reply(**bad))
    with pytest.raises(SignError) as e:
        s.write("k", "https://rpc.example", 7794095, RUN_SPEC, LISTING_SPEC)
    assert e.value.kind == "bad_reply"


def test_a_helper_that_never_answers_is_rpc_and_is_stopped(tmp_path):
    s = signer(tmp_path, stdout=reply(tx=TX, run=RUN, listing=LISTING), sleep=10)
    with pytest.raises(SignError) as e:
        s.write("k", "https://rpc.example", 7794095, RUN_SPEC, LISTING_SPEC, timeout_s=0.5)
    assert e.value.kind == "rpc"


def test_library_noise_before_the_reply_line_is_ignored(tmp_path):
    s = signer(tmp_path, stdout="a warning\n" + reply(tx=TX, run=RUN, listing=LISTING))
    assert s.write("k", "https://rpc.example", 7794095, RUN_SPEC, LISTING_SPEC)["run"] == RUN


def test_sign_error_kinds_are_the_documented_ones():
    assert arkiv_sign.KINDS == {"no_node", "no_key", "unfunded", "rpc", "rejected", "bad_reply"}
    assert SignError("unfunded").kind == "unfunded" and SignError("rpc", "x").detail == "x"


# ---- address --------------------------------------------------------------------------------------------------------

def test_the_address_comes_back_lowercase(tmp_path):
    s = signer(tmp_path, stdout=reply(address="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"))
    assert s.address("arkiv-key") == HARDHAT_ADDRESS
    assert sent(tmp_path) == {"op": "address", "key_file": os.path.abspath("arkiv-key")}


@pytest.mark.parametrize("bad", [{}, {"address": "0x1234"}, {"address": 7}, {"address": HARDHAT_ADDRESS + "00"}])
def test_an_address_reply_that_is_no_address_is_a_bad_reply(tmp_path, bad):
    with pytest.raises(SignError) as e:
        signer(tmp_path, stdout=reply(**bad)).address("k")
    assert e.value.kind == "bad_reply"


def test_an_address_without_a_key_is_no_key(tmp_path):
    with pytest.raises(SignError) as e:
        signer(tmp_path, stdout=reply(error="no_key", detail="the key file is missing"), code=2).address("k")
    assert e.value.kind == "no_key"


# ---- the real helper (offline) --------------------------------------------------------------------------------------

def _real_helper():
    node = shutil.which("node")
    packages = os.path.join(os.path.dirname(SCRIPT), "node_modules", "@arkiv-network", "sdk")
    if not node or not os.path.isdir(packages):
        pytest.skip("Node or the signer's packages are not installed (npm ci in launcher/arkiv_signer)")
    return Signer(node=node)


def test_the_real_helper_derives_the_address_of_a_known_key(tmp_path):
    s = _real_helper()
    key = tmp_path / "arkiv-key"
    key.write_text(HARDHAT_KEY + "\n", encoding="ascii")
    assert s.address(str(key)) == HARDHAT_ADDRESS


def test_the_real_helper_reports_a_node_nobody_answers_as_rpc(tmp_path):
    s = _real_helper()
    key = tmp_path / "arkiv-key"
    key.write_text(HARDHAT_KEY + "\n", encoding="ascii")
    with socket.socket() as sock:                       # a port taken and let go: nothing listens there
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with pytest.raises(SignError) as e:
        s.write(str(key), f"http://127.0.0.1:{port}/", 7794095, RUN_SPEC, LISTING_SPEC, timeout_s=60)
    assert e.value.kind == "rpc"
    assert HARDHAT_KEY not in e.value.detail and "127.0.0.1" not in e.value.detail
