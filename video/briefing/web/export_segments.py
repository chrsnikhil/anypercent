"""The browser film's timeline, from the same segment tables post_film.py stitches the MP4s from, so the two cuts can
never drift apart: each segment becomes (composition, props, first frame, frames, grade, overlay).

  python web/export_segments.py   -> web/segments.json  {"full": [...], "sub": [...], "chapters": {...}}"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# the rendered file each segment is cut from -> the composition (and props) that rendered it
COMP = {
    "out/cold_raw.mov": ("ColdOpen", {}),
    "out/teaser_raw.mov": ("ProofTeaser", {}),
    "out/flash_raw.mov": ("ProofFlash", {}),
    "out/title_open_raw.mov": ("TitleOpen", {}),
    "out/primer_raw.mov": ("Primer", {}),
    "out/ch1_raw.mov": ("Chapter", {"part": "PART I", "title": "THE CASE FILES"}),
    "out/ch3_raw.mov": ("Chapter", {"part": "PART III", "title": "THE MACHINE"}),
    "out/ch2s_raw.mov": ("Chapter", {"part": "PART II", "title": "THE MACHINE"}),
    "out/dossier_raw.mov": ("Dossier", {}),
    "out/breaks_raw.mov": ("Breaks", {}),
    "out/breaks_sub_raw.mov": ("Breaks", {"part": "PART I", "slow": 1}),
    "out/Any% Briefing - ETHGlobal Mumbai.mp4": ("Briefing", {}),
    "out/reel_raw.mov": ("GameReel", {}),
    "out/reel_short_raw.mov": ("GameReel", {"shot": 240}),
    "out/proof_raw.mov": ("Proof", {}),
    "out/proof_sub_raw.mov": ("Proof", {"part": "PART III"}),
    "out/check_raw.mov": ("Check", {}),
    "out/coach_raw.mov": ("Coach", {}),
    "out/obj_raw.mov": ("Objectives", {}),
    "out/obj_sub_raw.mov": ("Objectives", {"part": "PART IV"}),
    "out/handler_raw.mov": ("Handler", {}),
    "out/coda_raw.mov": ("Coda", {}),
    "out/title_end_raw.mov": ("TitleEnd", {}),
}
OVERLAY = {"out/machine_subs.mov": "MachineSubs"}


def table(cut):
    code = ("import json, post_film as P; print(json.dumps({'seg': [list(s[:4]) + [s[6] if len(s) > 6 else None] for s in P.SEG], "
            "'chapters': P.CHAPTERS}))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=dict(os.environ, CUT=cut), capture_output=True, text=True, check=True)
    d = json.loads(out.stdout.strip().splitlines()[-1])
    rows = []
    for (path, grade, trim, secs, ov), chap in zip(d["seg"], d["chapters"]):
        if path not in COMP:
            raise SystemExit(f"{cut}: no composition for {path}")
        comp, props = COMP[path]
        rows.append({"comp": comp, "props": props, "from": round(trim[0] * 60) if trim else 0, "frames": round(secs * 60),
                     "grade": grade or "asm", "overlay": OVERLAY.get(ov), "chapter": chap})
    return rows


if __name__ == "__main__":
    data = {cut: table(cut) for cut in ("full", "sub")}
    with open(os.path.join(HERE, "segments.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    for cut, rows in data.items():
        print(cut, len(rows), "segments,", sum(r["frames"] for r in rows), "frames")
