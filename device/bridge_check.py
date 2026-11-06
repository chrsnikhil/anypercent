"""Check the arcade bridge end to end with the arm64 replay tools: each known log (/opt/anypercent/testlogs) is put
in a RetroArch .srm next to a copy of its ROM, Bridge.after() must verify and queue it, Bridge.before() must write the
profile (with a nonzero seed nonce, boot count 0) and ghost. Works in a temporary directory; touches nothing the launcher uses.
  /opt/anypercent/venv/bin/python /opt/anypercent/tools/bridge_check.py"""
import json, os, shutil, sys, tempfile
sys.path.insert(0, "/opt/anypercent/src/launcher")
from arca_launcher.arcade_bridge import Bridge, S
lib = {g["id"]: g for g in json.load(open("/opt/anypercent/library/library.json"))["games"]}
tmp = tempfile.mkdtemp()
for gid_lib, gid in [("segfault","SEGF"),("rush-hour","RUSH"),("zip","ZIPG"),("marine-drive-gp","MDGP"),("ship-it","SHIP")]:
    g = lib[gid_lib]; rom = os.path.join(tmp, os.path.basename(g["rom"]))
    shutil.copy(g["rom"], rom)
    save = S.blank(); S.fmt(save, gid.encode()); S.put(save, S.RUN, open(f"/opt/anypercent/testlogs/{gid}.acl","rb").read())
    open(os.path.splitext(rom)[0] + ".srm", "wb").write(bytes(save))
    b = Bridge(os.path.join(tmp, "runs"), emulator="retroarch")
    res = b.after(rom, g["arcade"])
    print(gid, g["arcade"]["replay"], "verified+queued" if res else "NOT verified", res and res["final_hash"])
    b.before(rom, g["arcade"])   # writes profile (with a fresh seed nonce) + ghost from best (if any)
    srm = bytearray(open(os.path.splitext(rom)[0] + ".srm", "rb").read()[:S.SIZE])
    nonce, boots = S.parse_profile_seed(S.get(srm, gid.encode(), S.PROFILE)[0])
    print("   seed nonce %08x boots %d: %s" % (nonce, boots, "OK" if nonce and boots == 0 else "PROBLEM"))
print(sorted(os.listdir(os.path.join(tmp, "runs", "queue"))), sorted(os.listdir(os.path.join(tmp, "runs", "best"))))
shutil.rmtree(tmp)
