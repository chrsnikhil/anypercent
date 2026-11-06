"""The real numbers behind Act IV: the RUSH HOUR device-check run, its replay verdict, the same log with one byte of
input tampered and its verdict, the seeded run's seed, and the inputs for the frames the film shows.

  (WSL) cd games/zip && /opt/arca-sandbox/venv/bin/python ../../video/briefing/prep/make_proof.py
        -> video/briefing/public/proof.json"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "games", "common", "py"))
import arcade_test as T  # noqa: E402

S = T.S
SB = "/opt/arca-sandbox"
TOOL = os.path.join(SB, "games", "arcade", "RUSH", "arcade_replay")


def replay(path):
    r = subprocess.run([TOOL, path], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else {"error": r.stderr.strip() or "rejected", "code": r.returncode}


log = open(os.path.join(SB, "devicecheck", "RUSH.acl"), "rb").read()
hdr = S.parse_log_header(log)
good = replay(os.path.join(SB, "devicecheck", "RUSH.acl"))
bad = bytearray(log)
i = 32 + (len(log) - 32) // 2                   # one byte in the middle of the input stream
bad[i] ^= 0x01
with tempfile.NamedTemporaryFile(suffix=".acl", delete=False) as f:
    f.write(bad)
tampered = replay(f.name)
os.unlink(f.name)
seeded = S.parse_log_header(open(os.path.join(SB, "devicecheck", "RUSH.seeded.acl"), "rb").read())
with open(os.path.join(REPO, "games", "rushhour", "tests", "routes", "full_run.keys")) as fh:
    keys = [int(line, 16) for line in fh if line.strip()]
out = {
    "game": "RUSH", "rules_version": hdr["rules_version"], "frames": hdr["frames"], "log_bytes": len(log),
    "claimed_hash": "%08X" % hdr["final_hash"], "replay": good, "replay_hash": "%08X" % good["final_hash"],
    "tampered_byte": i, "tampered": tampered,
    "tampered_hash": "%08X" % tampered["final_hash"] if "final_hash" in tampered else None,
    "seeded_seed": "%08X" % seeded["seed"],
    "inputs_window": keys[600:960],              # the buttons for the RUSH frames on screen (public/game/RUSH)
    "log_hex": log.hex(),                        # the whole log, for the hex view of the tamper
}
json.dump(out, open(os.path.join(HERE, "..", "public", "proof.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "inputs_window"}, indent=1))
