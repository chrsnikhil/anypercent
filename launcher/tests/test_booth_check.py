"""device/booth_check.py: reading the Pi's answers and judging each booth-day item (the SSH side needs the Pi)."""
import importlib.util
import json
import os

from conftest import LAUNCHER_DIR

REPO = os.path.dirname(LAUNCHER_DIR)
spec = importlib.util.spec_from_file_location("booth_check", os.path.join(REPO, "device", "booth_check.py"))
bc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bc)

FINISHED = {"hash_matches": True, "complete": True, "claims_match": True, "finished": True, "time_frames": 6076}


def pi_output(**over):
    """What the remote script prints on a booth-ready Pi, with sections replaced by over."""
    sections = {
        "launcher_active": "active", "homekey_active": "active",
        "execstart": "/opt/anypercent/venv/bin/python -m arca_launcher --fullscreen",
        "launcher_sha": "aa  arca_launcher/app.py\nbb  arca_launcher/qr.py",
        "rom_sha": "11  /opt/anypercent/games/built/zip.gba\n22  /opt/anypercent/games/built/ship-it.gba",
        "library_gta": "0", "readonly": "now:  read-only (changes outside /data are lost on reboot)\nnext: read-only",
        "firewall_home": "0", "throttled": "throttled=0x0", "temp": "temp=52.1'C",
        "disk": "Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/root 100 40 60 40% /\n"
                "/dev/loop0 100 20 80 20% /data",
        "pads": "Device 00:11:22:33:44:55 DualSense Wireless Controller", "handler_json": "", "ntp": "yes",
        "booth_url": "https://ethglobal.com/showcase/any-percent",
        "clip_sha": "c1  /opt/anypercent/library/art/zip-clip-00.png\nc2  /opt/anypercent/library/art/zip-clip-01.png",
    }
    for gid in bc.ARCADE_IDS:
        sections["replay_" + gid] = json.dumps(FINISHED)
    sections.update(over)
    return "".join(f"@@{k}\n{v}\n" for k, v in sections.items())


LOCAL = {"launcher": {"arca_launcher/app.py": "aa", "arca_launcher/qr.py": "bb"},
         "roms": {"zip.gba": "11", "ship-it.gba": "22"}, "firewall_home": False,
         "clips": {"zip-clip-00.png": "c1", "zip-clip-01.png": "c2", "snake-clip-00.png": "c3"}}


def verdicts(**over):
    return {name: (status, detail) for status, name, detail in bc.verdicts(bc.parse(pi_output(**over)), LOCAL)}


def test_the_pis_answer_splits_into_sections():
    facts = bc.parse("@@a\none\ntwo\n@@b\n\n@@c\nx\n")
    assert facts == {"a": "one\ntwo", "b": "", "c": "x"}


def test_a_booth_ready_pi_passes_everything():
    got = verdicts()
    assert {name for name, (status, _) in got.items() if status != "PASS"} == {"hotspot password"}
    assert got["hotspot password"][0] == "INFO"


def test_stale_code_roms_or_flags_fail():
    assert verdicts(launcher_active="failed")["launcher running"][0] == "FAIL"
    got = verdicts(launcher_sha="aa  arca_launcher/app.py\nzz  arca_launcher/qr.py")
    assert got["launcher code"][0] == "FAIL" and "arca_launcher/qr.py" in got["launcher code"][1]
    assert verdicts(launcher_sha="aa  arca_launcher/app.py")["launcher code"][0] == "FAIL"     # qr.py missing
    assert verdicts(rom_sha="99  /opt/anypercent/games/built/zip.gba\n22  /opt/anypercent/games/built/ship-it.gba")[
        "game ROMs"][0] == "FAIL"
    assert verdicts(execstart="python -m arca_launcher --no-handler")["launcher flags"][0] == "FAIL"
    assert verdicts(execstart="python -m arca_launcher --fps")["launcher flags"][0] == "WARN"   # a leftover drop-in


def test_boards_need_finished_verified_test_logs():
    unfinished = dict(FINISHED, finished=False)
    got = verdicts(replay_SHIP=json.dumps(unfinished))
    assert got["board SHIP"][0] == "WARN" and "no board" in got["board SHIP"][1]
    assert verdicts(replay_ZIPG=json.dumps(dict(FINISHED, hash_matches=False)))["board ZIPG"][0] == "FAIL"
    assert verdicts(replay_MDGP="cannot open /opt/anypercent/testlogs/MDGP.acl")["board MDGP"][0] == "FAIL"
    assert "1:41.27" in verdicts()["board MDGP"][1]


def test_booth_day_reminders_warn():
    assert verdicts(library_gta="1")["GTA III out"][0] == "WARN"
    assert verdicts(readonly="now:  writable\nnext: writable")["read-only"][0] == "WARN"
    assert verdicts(firewall_home="1")["home SSH rule"][0] == "WARN"
    in_repo = {n: s for s, n, _ in bc.verdicts(bc.parse(pi_output()), dict(LOCAL, firewall_home=True))}
    assert in_repo["home SSH rule"] == "WARN"                         # still in device/firewall.nft: the next deploy
    got = verdicts(throttled="throttled=0x50005")
    assert got["power"][0] == "WARN" and "under-voltage" in got["power"][1]
    assert verdicts(temp="temp=81.0'C")["temperature"][0] == "WARN"
    assert verdicts(disk="Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/root 100 95 5 95% /")[
        "disk"][0] == "WARN"
    assert verdicts(pads="")["DualSense paired"][0] == "WARN"
    got = verdicts(handler_json=json.dumps({"book": "ANY-7QZ", "listings": []}))
    assert got["fresh console"][0] == "WARN" and "ANY-7QZ" in got["fresh console"][1]
    assert verdicts(ntp="no")["clock"][0] == "WARN"


def test_the_booth_link_is_reported():
    assert verdicts()["booth link"] == ("PASS", "https://ethglobal.com/showcase/any-percent")
    assert verdicts(booth_url="")["booth link"][0] == "INFO"                    # optional: no QR in attract mode
    assert verdicts(booth_url="not a link")["booth link"][0] == "WARN"


def test_attract_clips_on_the_pi_match_the_repo():
    assert verdicts()["attract clips"][0] == "PASS"                             # snake's are not on the Pi: fine
    got = verdicts(clip_sha="c1  /opt/anypercent/library/art/zip-clip-00.png\n"
                            "zz  /opt/anypercent/library/art/zip-clip-01.png")
    assert got["attract clips"][0] == "WARN" and "zip" in got["attract clips"][1]
    assert verdicts(clip_sha="")["attract clips"][0] == "INFO"


def test_odd_answers_never_crash_the_check():
    for odd in ("123", "null", "[1]", '"x"', json.dumps(dict(FINISHED, time_frames=None))):
        got = verdicts(replay_MDGP=odd, handler_json=odd)
        assert got["board MDGP"][0] in ("FAIL", "WARN"), odd
        assert got["fresh console"][0] in ("PASS", "WARN"), odd


def test_a_check_that_could_not_look_never_passes():
    assert verdicts(firewall_home="ERR")["home SSH rule"][0] == "INFO"          # sudo or nft failed
    assert verdicts(execstart="")["launcher flags"][0] == "FAIL"                # no service to read flags from
    assert verdicts(library_gta="ERR")["GTA III out"][0] == "FAIL"              # no library.json to read
    adapter = "Controller 00:1A:7D:DA:71:13 anypercent [default]"                 # the Pi's own Bluetooth
    assert verdicts(pads=adapter)["DualSense paired"][0] == "WARN"
    assert verdicts(pads=adapter + "\nDevice 00:11:22:33:44:55 DualSense Wireless Controller")[
        "DualSense paired"][0] == "PASS"


def test_the_remote_script_bounds_every_slow_command():
    assert "timeout 10 bluetoothctl" in bc.REMOTE and "timeout 60 /opt/anypercent/games/arcade/" in bc.REMOTE


def test_a_missing_answer_never_crashes_the_check():
    facts = bc.parse("@@launcher_active\nactive\n")                  # everything else missing
    statuses = {name: status for status, name, _ in bc.verdicts(facts, {"launcher": {}, "roms": None,
                                                                          "firewall_home": False})}
    assert statuses["launcher running"] == "PASS" and statuses["game ROMs"] == "INFO"
    assert all(s in ("PASS", "WARN", "FAIL", "INFO") for s in statuses.values())
