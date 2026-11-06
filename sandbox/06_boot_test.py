"""
Boot every game headless in PyBoy and check it actually runs, and that each ROM
rebuilt here behaves like the author's.

Each ROM plays for about 30 seconds: 12 frames are sampled, and Start and A are
pressed after each one. For every game that rebuilt from source, the built ROM and
the author's ROM get the same inputs, and their frame sequences are compared:

  same as author ROM   every sampled frame is identical
  runs                 the frames differ (e.g. random levels) but it keeps moving
  CHECK                it shows fewer distinct screens than the author's ROM: probably stuck
  FAIL                 the emulator crashed, or the screen stays blank

  games/boot/<id>.<built|official>.strip.png   the 12 sampled frames
  games/boot/contact_sheet.png                  every game at a glance
  games/boot/boot.json, games/BOOT_TEST.md
"""
import concurrent.futures as cf
import glob
import hashlib
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

G = os.path.join(os.environ.get("SANDBOX", "/opt/arca-sandbox"), "games")
OUT = os.path.join(G, "boot")
SAMPLES, EVERY = 12, 150            # 12 frames, one every 2.5 s of game time


def boot(job):
    gid, kind, rom = job
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from pyboy import PyBoy
    res = dict(id=gid, source=kind, rom=rom, ok=False, error="", frames=[])
    try:
        pb = PyBoy(rom, window="null", sound_emulated=False)
        pb.set_emulation_speed(0)
        shots = []
        for _ in range(SAMPLES):
            pb.tick(EVERY, True)
            shots.append(pb.screen.image.copy().convert("RGB"))
            pb.button("start", 8)
            pb.tick(20, False)
            pb.button("a", 8)
        pb.stop(save=False)
        strip = Image.new("RGB", (SAMPLES * 160, 144))
        for i, im in enumerate(shots):
            strip.paste(im, (i * 160, 0))
        path = os.path.join(OUT, f"{gid}.{kind}.strip.png")
        strip.save(path)
        res["frames"] = [hashlib.sha1(im.tobytes()).hexdigest()[:12] for im in shots]
        blank = all(len(im.getcolors(1 << 16) or []) <= 1 for im in shots)
        res.update(ok=not blank, strip=path, distinct=len(set(res["frames"])), error="blank screen" if blank else "")
    except Exception as e:                                                   # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"[:200]
    return res


def verdict(built, official):
    """Compare a rebuilt ROM's run with the author's."""
    if built is None:
        return None
    if not built["ok"]:
        return "FAIL: " + built["error"]
    if official is None or not official["ok"]:
        return "runs"
    if built["frames"] == official["frames"]:
        return "same as author ROM"
    if built["distinct"] + 1 < official["distinct"]:
        return (f"CHECK: {built['distinct']} distinct screens vs {official['distinct']} "
                "for the author ROM; probably stuck")
    return "runs (differs from author ROM)"


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def contact_sheet(rows, path):
    cols, tw, th, pad, lab = 3, 160, 144, 14, 34
    cw, ch = 2 * tw + 8 + 2 * pad, th + lab + 2 * pad
    sheet = Image.new("RGB", (cols * cw, ((len(rows) + cols - 1) // cols) * ch), (24, 26, 32))
    d = ImageDraw.Draw(sheet)
    f1, f2 = font(15), font(12)
    for i, (r, tag, good) in enumerate(rows):
        x, y = (i % cols) * cw + pad, (i // cols) * ch + pad
        colour = (120, 220, 140) if good else (240, 110, 100)
        d.text((x, y), r["id"], fill=(235, 235, 235), font=f1)
        d.text((x, y + 17), tag, fill=colour, font=f2)
        if r.get("strip") and os.path.exists(r["strip"]):
            strip = Image.open(r["strip"]).convert("RGB")
            for j, k in enumerate((1, SAMPLES - 1)):          # an early screen and the last one
                sheet.paste(strip.crop((k * 160, 0, k * 160 + 160, 144)), (x + j * (tw + 8), y + lab))
        else:
            d.rectangle([x, y + lab, x + tw, y + lab + th], outline=colour)
    sheet.save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    ids = sorted(os.listdir(os.path.join(G, "src")))
    todo = [i for i in ids if i in sys.argv[1:]] if sys.argv[1:] else ids
    jobs = []
    for gid in todo:
        for kind, folder in (("built", "built"), ("official", "roms")):
            roms = glob.glob(os.path.join(G, folder, gid + ".gb*"))
            if roms:
                jobs.append((gid, kind, roms[0]))
    with cf.ProcessPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        results = list(ex.map(boot, jobs))
    bj = os.path.join(OUT, "boot.json")
    if sys.argv[1:] and os.path.exists(bj):          # partial run: keep earlier results for other games
        results = [r for r in json.load(open(bj)) if r["id"] not in todo] + results
    json.dump(results, open(bj, "w"), indent=1)
    by = {(r["id"], r["source"]): r for r in results}

    rows, lines, counts = [], [], dict(same=0, runs=0, check=0, fail=0, author=0)
    for gid in ids:
        b, o = by.get((gid, "built")), by.get((gid, "official"))
        v = verdict(b, o)
        if b is not None:
            key = ("same" if v.startswith("same") else "runs" if v.startswith("runs") else
                   "check" if v.startswith("CHECK") else "fail")
            counts[key] += 1
            rows.append((b, "built: " + v.split(";")[0], key in ("same", "runs")))
        elif o is not None:
            counts["author"] += 1
            rows.append((o, "author ROM (not rebuilt): " + ("runs" if o["ok"] else "FAIL"), o["ok"]))
        ocell = "-" if o is None else ("runs" if o["ok"] else "FAIL: " + o["error"])
        lines.append(f"| {gid} | {v or 'not rebuilt'} | {ocell} |")
    contact_sheet(rows, os.path.join(OUT, "contact_sheet.png"))

    with open(os.path.join(G, "BOOT_TEST.md"), "w") as f:
        f.write("# Boot test\n\nEach ROM plays ~30 s in PyBoy (headless) with Start and A pressed; 12 frames are "
                "sampled. Rebuilt ROMs are compared with the author's ROM given the same inputs.\n\n"
                f"Rebuilt from source: {counts['same']} identical to the author ROM, {counts['runs']} run but differ, "
                f"{counts['check']} to check, {counts['fail']} failed. Author ROMs only: {counts['author']}.\n\n"
                "Frames: games/boot/<id>.<built|official>.strip.png. Overview: games/boot/contact_sheet.png\n\n"
                "| Game | Rebuilt ROM | Author ROM |\n|---|---|---|\n" + "\n".join(lines) + "\n")
    for line in lines:
        print(" ", line)
    print(f"\nrebuilt: {counts['same']} identical, {counts['runs']} differ but run, {counts['check']} check, "
          f"{counts['fail']} fail; author-only: {counts['author']}")


if __name__ == "__main__":
    main()
