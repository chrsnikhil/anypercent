#!/bin/bash
# Build the five arcade games' replay tools on the Pi (arm64, with its own gcc) from ROOT/src and check them: every
# known run log in ROOT/testlogs (per game, the classic seed-0 run and a launcher-seeded one, from
# device/make_testlogs.py) must replay to exactly the x86 tool's JSON. Used by install.sh and update_games.sh.
#   sudo bash replay_tools.sh /opt/anypercent          exits 1 on any MISMATCH
set -euo pipefail
ROOT=${1:?usage: replay_tools.sh ROOT}

build() {  # DIR ID
  make -C "$ROOT/src/$1" -f tools.mk -B replay >/dev/null
  mkdir -p "$ROOT/games/arcade/$2"
  install -m 0755 "$ROOT/src/$1/out/arcade_replay" "$ROOT/games/arcade/$2/arcade_replay"
}
build game SHIP; build games/rushhour RUSH; build games/zip ZIPG; build games/marinedrive MDGP; build games/segfault SEGF
python3 - "$ROOT" <<'EOF'
import json, subprocess, sys
root = sys.argv[1]
bad = 0
for gid in ("SHIP", "RUSH", "ZIPG", "MDGP", "SEGF"):
  for name in (gid, gid + ".seeded"):          # the classic seed-0 run and a launcher-seeded one
    want = json.load(open(f"{root}/testlogs/{name}.x86.json"))
    r = subprocess.run([f"{root}/games/arcade/{gid}/arcade_replay", f"{root}/testlogs/{name}.acl"],
                       capture_output=True, text=True)
    got = json.loads(r.stdout) if r.returncode == 0 else None
    ok = got == want and got["hash_matches"] and got["complete"] and got["claims_match"]
    bad += not ok
    print("%s %s final_hash=%s frames=%s finished=%s" % (name, "OK" if ok else "MISMATCH",
          got and got["final_hash"], got and got["frames"], got and got["finished"]))
sys.exit(1 if bad else 0)
EOF
