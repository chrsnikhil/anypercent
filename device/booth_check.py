"""Is the Any% handheld ready for the booth? Read-only checks, run from the laptop before the doors open.

  python device/booth_check.py          (ANYPERCENT_HOST picks the address, as for deploy.py)

One SSH session runs a read-only script on the Pi (it changes nothing); the laptop compares what comes back with the
repo and the WSL sandbox, then prints PASS, WARN, FAIL or INFO for each item of docs/TODO-before-hackathon.md and
docs/demo-run-sheet.md that a machine can check. Exits 1 when anything FAILs.

  launcher running, home key, launcher flags (no --no-handler, no leftover --fps), launcher code (the same files
  as launcher/arca_launcher), game ROMs (the same as the sandbox's built ROMs), a board per arcade game (its test
  log replays finished and verified on the Pi), GTA III out, read-only, home SSH rule, power, temperature, disk,
  DualSense paired, fresh console (no record book left from a rehearsal), clock, attract clips (the same as
  games/clips), booth link (attract mode's QR)."""
import glob
import hashlib
import json
import os
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ARCADE_IDS = ("SHIP", "RUSH", "ZIPG", "MDGP", "SEGF")
ROMS = ("ship-it.gba", "rush-hour.gba", "zip.gba", "marine-drive-gp.gba", "segfault.gba")
HOME_RULE = "192.168.1.0/24"
BITS = {0x1: "under-voltage now", 0x2: "frequency capped now", 0x4: "throttled now", 0x8: "soft temperature limit now",
        0x10000: "under-voltage since boot", 0x20000: "frequency capped since boot", 0x40000: "throttled since boot",
        0x80000: "soft temperature limit since boot"}

# Every section prints "@@name" then its answer. Nothing here writes anywhere.
REMOTE = r"""
s() { echo "@@$1"; }
s launcher_active; systemctl is-active anypercent-launcher
s homekey_active; systemctl is-active anypercent-homekey
s execstart; systemctl show -p ExecStart --value anypercent-launcher
s launcher_sha; cd /opt/anypercent/src/launcher && find arca_launcher -name '*.py' -not -path '*/__pycache__/*' \
    -exec sha256sum {} + ; cd /
s rom_sha; sha256sum """ + " ".join("/opt/anypercent/games/built/" + r for r in ROMS) + r""" 2>&1
""" + "".join(f"s replay_{gid}; timeout 60 /opt/anypercent/games/arcade/{gid}/arcade_replay "
              f"/opt/anypercent/testlogs/{gid}.acl 2>&1 | tail -1\n" for gid in ARCADE_IDS) + r"""
L=/opt/anypercent/library/library.json
s library_gta; if [ -r "$L" ]; then grep -c '"gta-iii"' "$L"; else echo ERR; fi
s readonly; timeout 20 sh /opt/anypercent/src/device/readonly.sh status 2>&1
s firewall_home; if r=$(timeout 10 sudo -n nft list ruleset 2>/dev/null); then printf '%s\n' "$r" | grep -c '""" + \
    HOME_RULE + r"""'; else echo ERR; fi
s throttled; timeout 10 vcgencmd get_throttled 2>&1
s temp; timeout 10 vcgencmd measure_temp 2>&1
s disk; timeout 10 df -P / /data 2>/dev/null
s pads; timeout 10 bluetoothctl devices Paired 2>/dev/null || timeout 10 bluetoothctl paired-devices 2>/dev/null
s handler_json; cat "$HOME/.local/state/anypercent/handler.json" 2>/dev/null
s booth_url; head -n 1 "$HOME/.local/state/anypercent/booth-url.txt" 2>/dev/null
s clip_sha; cd /opt/anypercent/library/art 2>/dev/null && sha256sum ./*-clip-*.png 2>/dev/null; cd /
s ntp; timeout 10 timedatectl show -p NTPSynchronized --value 2>&1
"""


def parse(text):
    """The remote script's output -> {section: its answer, stripped}."""
    facts, name, lines = {}, None, []
    for line in text.splitlines():
        if line.startswith("@@"):
            if name is not None:
                facts[name] = "\n".join(lines).strip()
            name, lines = line[2:].strip(), []
        elif name is not None:
            lines.append(line)
    if name is not None:
        facts[name] = "\n".join(lines).strip()
    return facts


def _shas(text):
    """sha256sum output -> {path relative to the launcher, or a ROM's file name: digest}."""
    out = {}
    for line in (text or "").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and len(parts[0]) >= 2 and "No such file" not in line:
            path = parts[1].strip().lstrip("*")
            out[path if path.startswith("arca_launcher/") else os.path.basename(path)] = parts[0]
    return out


def _time(frames):
    cs = round(frames * 100 / 60)
    return "%d:%02d.%02d" % (cs // 6000, cs // 100 % 60, cs % 100)


def verdicts(facts, local):
    """[(status, item, detail)] for facts (parse()) against local (local_facts())."""
    out = []

    def add(status, item, detail=""):
        out.append((status, item, detail))

    def is_(key, want):
        return facts.get(key, "").strip() == want

    add("PASS" if is_("launcher_active", "active") else "FAIL", "launcher running",
        facts.get("launcher_active", "no answer"))
    add("PASS" if is_("homekey_active", "active") else "WARN", "home key", "PS-hold to leave a game or restart")
    flags = facts.get("execstart", "")
    if "arca_launcher" not in flags:
        add("FAIL", "launcher flags", "no launcher service found")
    elif "--no-handler" in flags:
        add("FAIL", "launcher flags", "--no-handler: PB the handler is off")
    elif "--no-coach" in flags or "--fps" in flags:
        add("WARN", "launcher flags", "a leftover --no-coach or --fps (a drop-in?): " + flags)
    else:
        add("PASS", "launcher flags", "handler and coach on")

    pi, mine = _shas(facts.get("launcher_sha")), local.get("launcher") or {}
    differ = sorted(p for p in set(pi) | set(mine) if pi.get(p) != mine.get(p))
    if not pi:
        add("FAIL", "launcher code", "no answer")
    elif differ:
        add("FAIL", "launcher code", f"{len(differ)} files differ ({', '.join(differ[:4])}): python device/deploy.py")
    else:
        add("PASS", "launcher code", f"{len(pi)} files, the same as the repo")

    roms = local.get("roms")
    if not roms:
        add("INFO", "game ROMs", "not compared (the WSL sandbox's built ROMs were not readable)")
    else:
        pi_roms = _shas(facts.get("rom_sha"))
        stale = sorted(r for r in roms if pi_roms.get(r) != roms[r])
        add("FAIL" if stale else "PASS", "game ROMs",
            f"differ: {', '.join(stale)} (stage.sh, push, update_games.sh)" if stale else "the same as the sandbox")

    for gid in ARCADE_IDS:
        raw = facts.get("replay_" + gid, "")
        try:
            res = json.loads(raw)
        except ValueError:
            res = None
        if not isinstance(res, dict):
            add("FAIL", "board " + gid, "its test log did not replay: " + (raw[:80] or "no answer"))
            continue
        if not (res.get("hash_matches") and res.get("complete") and res.get("claims_match")):
            add("FAIL", "board " + gid, "its test log does not verify")
        elif not res.get("finished") or not isinstance(res.get("time_frames"), int):
            add("WARN", "board " + gid, "the test log never finishes: no board or target ghost (games update)")
        else:
            add("PASS", "board " + gid, "RIA " + _time(res["time_frames"]))

    gta = facts.get("library_gta", "").strip()
    if gta in ("", "ERR"):
        add("FAIL", "GTA III out", "no readable /opt/anypercent/library/library.json")
    else:
        add("PASS" if gta == "0" else "WARN", "GTA III out",
            "not in the library" if gta == "0" else "personal: take it out of docs/games/lineup.txt for the booth")
    ro = facts.get("readonly", "")
    add("PASS" if "now:  read-only" in ro else "WARN", "read-only",
        "frozen" if "now:  read-only" in ro else "writable: readonly.sh on after the last deploy")
    fw = facts.get("firewall_home", "").strip()
    on_pi = fw not in ("", "0", "ERR")
    if fw in ("", "ERR") and not local.get("firewall_home"):
        add("INFO", "home SSH rule", "could not read the Pi's firewall (sudo -n nft)")
    elif on_pi or local.get("firewall_home"):
        where = " and ".join(w for w, x in (("on the Pi", on_pi), ("in device/firewall.nft",
                                                                     local.get("firewall_home"))) if x)
        add("WARN", "home SSH rule", f"{HOME_RULE} still {where}: remove before the venue")
    else:
        add("PASS", "home SSH rule", "gone")

    try:
        bits = int(facts.get("throttled", "").split("=")[1], 16)
    except (IndexError, ValueError):
        bits = None
    if bits is None:
        add("INFO", "power", "no answer from vcgencmd")
    else:
        bad = [text for bit, text in BITS.items() if bits & bit]
        add("WARN" if bad else "PASS", "power", ", ".join(bad) or "no under-voltage or throttling")
    try:
        temp = float(facts.get("temp", "").split("=")[1].split("'")[0])
    except (IndexError, ValueError):
        temp = None
    add("INFO" if temp is None else "WARN" if temp >= 75 else "PASS", "temperature",
        "no answer" if temp is None else f"{temp:.0f} C")
    full = []
    for line in facts.get("disk", "").splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 6 and cols[4].endswith("%") and cols[4][:-1].isdigit() and int(cols[4][:-1]) >= 90:
            full.append(f"{cols[5]} {cols[4]}")
    add("WARN" if full else "PASS", "disk", ", ".join(full) or "room on / and /data")
    pads = [line for line in facts.get("pads", "").splitlines()          # "Controller <MAC> ..." is the Pi's adapter
            if line.startswith("Device ") and ("DualSense" in line or "Wireless Controller" in line)]
    add("PASS" if pads else "WARN", "DualSense paired", f"{len(pads)} paired" if pads else "none paired")
    try:
        state = json.loads(facts.get("handler_json") or "{}")
    except ValueError:
        state = None
    book = state.get("book") if isinstance(state, dict) else None
    add("WARN" if book else "PASS", "fresh console",
        f"record book {book} from a rehearsal: Triangle, Start over (mock), Cross" if book else "no record book yet")
    add("PASS" if is_("ntp", "yes") else "WARN", "clock",
        "synced" if is_("ntp", "yes") else "not synced: PB's day (budget, offers) may be wrong")
    pi_clips, my_clips = _shas(facts.get("clip_sha")), local.get("clips") or {}
    if not pi_clips or not my_clips:
        add("INFO", "attract clips", "none on the Pi" if not pi_clips else "not compared (no games/clips)")
    else:
        stale = sorted({n.split("-clip-")[0] for n in pi_clips if n in my_clips and pi_clips[n] != my_clips[n]})
        add("WARN" if stale else "PASS", "attract clips",
            f"older than games/clips: {', '.join(stale)} (copy them into library/art)" if stale
            else f"{len(pi_clips)} frames, the same as games/clips")
    url = facts.get("booth_url", "").strip()
    if not url:
        add("INFO", "booth link", "none: attract mode shows no QR (booth-url.txt beside state.json)")
    elif url.startswith(("https://", "http://")):
        add("PASS", "booth link", url)
    else:
        add("WARN", "booth link", "booth-url.txt holds no http(s) link: " + url[:60])
    add("INFO", "hotspot password", "owner: a strong iPhone hotspot password (not checkable from here)")
    return out


def local_facts(repo=REPO):
    """What the Pi should hold: the launcher's files and the sandbox's built ROMs, digested; the firewall source."""
    launcher = {}
    base = os.path.join(repo, "launcher")
    for root, dirs, files in os.walk(os.path.join(base, "arca_launcher")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, "rb") as fh:
                    launcher[os.path.relpath(path, base).replace(os.sep, "/")] = hashlib.sha256(fh.read()).hexdigest()
    try:
        out = subprocess.run(["wsl", "-d", "Ubuntu-24.04", "-e", "sha256sum"]
                             + ["/opt/arca-sandbox/games/built/" + r for r in ROMS],
                             capture_output=True, text=True, timeout=60).stdout
        roms = _shas(out) or None
    except (OSError, subprocess.TimeoutExpired):
        roms = None
    with open(os.path.join(repo, "device", "firewall.nft"), encoding="utf-8") as f:
        rule = any(HOME_RULE in line and not line.lstrip().startswith("#") for line in f)
    clips = {}
    for path in glob.glob(os.path.join(repo, "games", "clips", "*", "*-clip-*.png")):
        with open(path, "rb") as fh:
            clips[os.path.basename(path)] = hashlib.sha256(fh.read()).hexdigest()
    return {"launcher": launcher, "roms": roms, "firewall_home": rule, "clips": clips}


def main():
    sys.path.insert(0, HERE)
    import anypercent_ssh
    client, host = anypercent_ssh.connect()
    got = b""
    try:
        _, out, _ = client.exec_command(REMOTE, timeout=240)
        while True:                                # every command is bounded; a stall still keeps what came back
            chunk = out.channel.recv(65536)
            if not chunk:
                break
            got += chunk
    except socket.timeout:
        print("the Pi stopped answering part way: judging what arrived")
    finally:
        client.close()
    facts = parse(got.decode(errors="replace"))
    rows = verdicts(facts, local_facts())
    print(f"Any% booth check, {host}")
    for status, item, detail in rows:
        print(f"  {status:<5} {item:<18} {detail}")
    fails = sum(1 for status, _, _ in rows if status == "FAIL")
    warns = sum(1 for status, _, _ in rows if status == "WARN")
    print(f"{fails} FAIL, {warns} WARN")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
