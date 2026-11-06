"""
Games workspace: for every game in docs/games/games.json
  games/src/<id>/        full source (git clone), ready to modify
  games/roms/<id>.gb(c)  the author-published ROM (Homebrew Hub copy)
  games/licenses/<id>/   every LICENSE / COPYING file from the source
  games/CREDITS.md       title, authors, licences, source -- ship this
Run with the sandbox python:  $SANDBOX/venv/bin/python 04_games.py
"""
import json
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request

SANDBOX = os.environ.get("SANDBOX", "/opt/arca-sandbox")
PROJECT = os.environ.get("PROJECT", "/mnt/c/Users/chrsn/Desktop/retro-handheld-ethglobal")
G = os.path.join(SANDBOX, "games")
for d in ("src", "roms", "licenses"):
    os.makedirs(os.path.join(G, d), exist_ok=True)

games = json.load(open(os.path.join(PROJECT, "docs/games/games.json"), encoding="utf-8"))["games"]


def gid(g):
    return re.sub(r"[^a-z0-9]+", "-", g["title"].lower()).strip("-")


rows, problems = [], []
for g in games:
    i = gid(g)
    src = os.path.join(G, "src", i)
    # 1. source
    if not os.path.isdir(os.path.join(src, ".git")):
        r = subprocess.run(["git", "clone", "--quiet", "--depth", "1", g["source"] + ".git", src],
                           capture_output=True, text=True)
        if r.returncode:
            problems.append(f"{g['title']}: clone failed: {r.stderr.strip()[:120]}")
    commit = subprocess.run(["git", "-C", src, "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    # 2. ROM (URL-encode the path part: some names have spaces)
    ext = os.path.splitext(g["rom_file"])[1].lower() or ".gb"
    rom = os.path.join(G, "roms", i + ext)
    if not os.path.exists(rom):
        base, _, path = g["rom_url"].partition("/entries/")
        url = base + "/entries/" + urllib.parse.quote(path)
        try:
            with urllib.request.urlopen(url, timeout=60) as r, open(rom, "wb") as f:
                f.write(r.read())
        except Exception as e:                                   # noqa: BLE001
            problems.append(f"{g['title']}: ROM download failed: {e}")
    size = os.path.getsize(rom) if os.path.exists(rom) else 0
    # 3. licence files
    ldir = os.path.join(G, "licenses", i)
    os.makedirs(ldir, exist_ok=True)
    found = []
    if os.path.isdir(src):
        for f in os.listdir(src):
            if re.match(r"(?i)^(licen[cs]e|copying|unlicense|licence)", f) and os.path.isfile(os.path.join(src, f)):
                shutil.copy(os.path.join(src, f), os.path.join(ldir, f)); found.append(f)
    with open(os.path.join(ldir, "SOURCE.txt"), "w") as f:
        f.write(f"{g['title']}\nAuthors: {g['authors']}\nCode licence: {g['code_license']}\n"
                f"Art/music: {g['asset_license']}\nSource: {g['source']} (commit {commit})\n"
                f"Homebrew Hub: {g['homebrew_hub']}\n")
    rows.append((i, g, commit, size, found))
    print(f"  {i:28s} src@{commit or '-':8s} rom {size:>8d} B  licence files: {', '.join(found) or '(README only)'}")

with open(os.path.join(G, "CREDITS.md"), "w", encoding="utf-8") as f:
    f.write("# Game credits\n\nEvery game on this device is the work of its authors, used under the licence shown. "
            "Source code for each is at the link given.\n\n")
    f.write("| Game | Authors | Code licence | Art / music | Source |\n|---|---|---|---|---|\n")
    for i, g, commit, size, found in rows:
        f.write(f"| {g['title']} | {g['authors']} | {g['code_license']} | {g['asset_license']} | {g['source']} |\n")

print(f"\n{len(rows)} games; {sum(1 for r in rows if r[3])} ROMs downloaded")
if problems:
    print("PROBLEMS:"); [print("  " + p) for p in problems]
