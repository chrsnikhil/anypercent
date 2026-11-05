"""
Build the launcher's game library from the sandbox.

  docs/games/games.json                 titles, authors, genres, licences, sources
  <games>/built/<id>.gb(c)              ROM rebuilt from source (preferred)
  <games>/roms/<id>.gb(c)               the author's published ROM
  <games>/boot/<id>.<built|official>.strip.png   12 frames from the boot test

Writes <out>/library.json and <out>/art/:
  <id>-tile.png    the tile (a native 160 x 144 frame; the launcher crops and scales it)
  <id>-shotN.png   up to three screenshots
  <id>-bg.png      the home background: 200 x 120, blurred and darkened

A lineup file (docs/games/lineup.txt: one game id per line, # comments) keeps only those games. A reskinned game's
own art (games/reskin/<id>/art/<id>-tile.png, -shotN.png, -bg.png, from mGBA frames) is used instead of the
boot-test frames.

  python tools/build_library.py --games-json docs/games/games.json --lineup docs/games/lineup.txt \
      --games /opt/arca-sandbox/games --out /opt/arca-sandbox/launcher
"""
import argparse
import glob
import shutil
import hashlib
import json
import os
import re
import sys

from PIL import Image, ImageChops, ImageEnhance, ImageFilter

FRAME_W, FRAME_H = 160, 144
BG_SIZE = (200, 120)
BG_BLUR = 3
BG_BRIGHTNESS = 0.35
LIVE = 0.01                      # detail below this counts as a blank screen
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PICKS = os.path.join(HERE, "art_picks.json")
DEFAULT_ART_FROM = os.path.join(os.path.dirname(os.path.dirname(HERE)), "games", "reskin")
DEFAULT_CLIPS_FROM = os.path.join(os.path.dirname(os.path.dirname(HERE)), "games", "clips")   # make_clips.py


def read_lineup(path):
    """Game ids, one per line; blank lines and # comments ignored."""
    with open(path, encoding="utf-8") as f:
        return [line.split("#")[0].strip() for line in f if line.split("#")[0].strip()]


def own_art(art_from, gid):
    """A reskinned game's art folder if it has a tile, else None."""
    if not art_from:
        return None
    d = os.path.join(art_from, gid, "art")
    return d if os.path.exists(os.path.join(d, f"{gid}-tile.png")) else None


def game_id(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def find_rom(games_dir, gid):
    for folder, origin in (("built", "built"), ("roms", "author")):
        hits = sorted(glob.glob(os.path.join(games_dir, folder, gid + ".gb*")))
        if hits:
            return hits[0], origin
    return None, "missing"


def load_frames(games_dir, gid, prefer=None):
    """The boot-test frames: from the rebuilt ROM's strip, else the author's (or `prefer` first)."""
    order = ("built", "official") if prefer is None else (prefer, "built", "official")
    for src in order:
        path = os.path.join(games_dir, "boot", f"{gid}.{src}.strip.png")
        if os.path.exists(path):
            strip = Image.open(path).convert("RGB")
            return [strip.crop((i * FRAME_W, 0, (i + 1) * FRAME_W, FRAME_H)) for i in range(strip.width // FRAME_W)]
    return []


def detail(frame):
    """How busy a frame is: the share of pixels that differ from their right-hand neighbour."""
    grey = frame.convert("L")
    w, h = grey.size
    diff = ImageChops.difference(grey.crop((1, 0, w, h)), grey.crop((0, 0, w - 1, h)))
    return (diff.width * diff.height - diff.histogram()[0]) / (w * h)


def spread(items, k):
    """Up to k items, evenly spaced through the list, keeping the first and the last."""
    if len(items) <= k:
        return list(items)
    step = (len(items) - 1) / (k - 1)
    return [items[round(j * step)] for j in range(k)]


def pick_art(frames, override=None):
    """Frame indices for the tile, the screenshots and the background."""
    override = override or {}
    if not frames:
        return None, [], None
    n = len(frames)

    def valid(i):                 # a hand-edited index that is not a frame is ignored, not fatal
        return isinstance(i, int) and not isinstance(i, bool) and 0 <= i < n

    scores = [detail(f) for f in frames]
    tile = override.get("tile")
    if not valid(tile):
        tile = max(range(min(4, n)), key=lambda i: scores[i])
    shots = [i for i in override.get("shots") or [] if valid(i)] or None
    if shots is None:
        seen, shots = set(), []
        for i in range(4, len(frames)):
            h = hashlib.sha1(frames[i].tobytes()).hexdigest()
            if scores[i] > LIVE and h not in seen:
                seen.add(h)
                shots.append(i)
        shots = spread(shots, 3) or [tile]
    bg = override.get("bg")
    if not valid(bg):
        bg = next((i for i in reversed(range(len(frames))) if scores[i] > LIVE), tile)
    return tile, list(shots), bg


def make_bg(frame):
    """The frame cropped to 5:3 around its centre, shrunk, blurred and darkened."""
    w, h = frame.size
    ch = round(w * 3 / 5)
    top = (h - ch) // 2
    img = frame.crop((0, top, w, top + ch)).resize(BG_SIZE, Image.BILINEAR)
    img = img.filter(ImageFilter.GaussianBlur(BG_BLUR))
    return ImageEnhance.Brightness(img).enhance(BG_BRIGHTNESS)


def _save(img, art_dir, name):
    img.save(os.path.join(art_dir, name))
    return "art/" + name


def build(games_json, games_dir, out_dir, picks_path=DEFAULT_PICKS, lineup=None, art_from=None, clips_from=None):
    meta = json.load(open(games_json, encoding="utf-8"))
    entries = meta["games"] if isinstance(meta, dict) else meta
    picks = json.load(open(picks_path, encoding="utf-8")) if picks_path and os.path.exists(picks_path) else {}
    art_dir = os.path.join(out_dir, "art")
    os.makedirs(art_dir, exist_ok=True)
    games = []
    keep = set(lineup) if lineup is not None else None
    for e in entries:
        gid = game_id(e["title"])
        if keep is not None and gid not in keep:
            continue
        rom, origin = find_rom(games_dir, gid)
        pick = picks.get(gid) or {}
        frames = load_frames(games_dir, gid, pick.get("strip"))
        tile_i, shot_is, bg_i = pick_art(frames, pick)
        entry = dict(id=gid, title=e["title"], authors=e.get("authors", ""), genre=e.get("genre", ""),
                     platform=e.get("platform", "GB"), code_license=e.get("code_license", ""),
                     asset_license=e.get("asset_license", ""), source=e.get("source", ""),
                     rom=rom, rom_origin=origin, tile=None, shots=[], bg=None)
        if e.get("arcade"):
            entry["arcade"] = e["arcade"]
        if isinstance(e.get("how_to"), dict):                     # the info page's how-to-play card
            entry["how_to"] = e["how_to"]
        clip = sorted(glob.glob(os.path.join(clips_from, gid, f"{gid}-clip-*.png"))) if clips_from else []
        if clip:                                                   # attract mode's gameplay loop
            for c in clip:
                shutil.copyfile(c, os.path.join(art_dir, os.path.basename(c)))
            entry["clip"] = ["art/" + os.path.basename(c) for c in clip]
        if e.get("app"):                                           # an app (the browser): no ROM, the device starts it
            entry.update(app=e["app"], rom=None, rom_origin="app")
        own = own_art(art_from, gid)
        if own:
            def copy(name):
                shutil.copyfile(os.path.join(own, name), os.path.join(art_dir, name))
                return "art/" + name
            entry["tile"] = copy(f"{gid}-tile.png")
            entry["shots"] = [copy(f"{gid}-shot{n}.png") for n in range(3)
                              if os.path.exists(os.path.join(own, f"{gid}-shot{n}.png"))]
            if os.path.exists(os.path.join(own, f"{gid}-bg.png")):
                entry["bg"] = copy(f"{gid}-bg.png")
        elif frames:
            entry["tile"] = _save(frames[tile_i], art_dir, f"{gid}-tile.png")
            entry["shots"] = [_save(frames[i], art_dir, f"{gid}-shot{n}.png") for n, i in enumerate(shot_is)]
            entry["bg"] = _save(make_bg(frames[bg_i]), art_dir, f"{gid}-bg.png")
        games.append(entry)
    games.sort(key=lambda g: g["title"].casefold())
    tmp = os.path.join(out_dir, "library.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "games": games}, f, indent=1, ensure_ascii=False)
    os.replace(tmp, os.path.join(out_dir, "library.json"))
    return games


def main(argv=None):
    p = argparse.ArgumentParser(description="Build the Any% launcher's game library")
    p.add_argument("--games-json", required=True)
    p.add_argument("--games", required=True, help="the sandbox games folder")
    p.add_argument("--out", required=True)
    p.add_argument("--picks", default=DEFAULT_PICKS)
    p.add_argument("--lineup", help="file of game ids to keep (default: every game)")
    p.add_argument("--art-from", default=DEFAULT_ART_FROM, help="reskinned games' own art: <dir>/<id>/art/")
    p.add_argument("--clips-from", default=DEFAULT_CLIPS_FROM, help="attract-mode clips: <dir>/<id>/<id>-clip-NN.png")
    a = p.parse_args(argv)
    games = build(a.games_json, a.games, a.out, a.picks, read_lineup(a.lineup) if a.lineup else None, a.art_from,
                  a.clips_from)
    playable = sum(1 for g in games if g["rom"])
    print(f"library: {len(games)} games ({playable} with a ROM) -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
