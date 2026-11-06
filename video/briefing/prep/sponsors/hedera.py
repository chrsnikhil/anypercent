"""The Hedera sponsor demo (SPONSOR_DEMOS.md): its sound cues, and (run directly) its one asset.

Sound: python scripts/heavy.py python prep/make_mw3_audio.py out/mw3ref sponsor hedera  -> out/sponsor_hedera_orig.wav
  make_mw3_audio.py runs this file with card, ramp, rnd and np handed in, and reads LEN_S, BED_AT, BED_DB and build().
  Every cue comes from src/sponsors/hedera/timing.json, the same numbers Act.tsx draws from, so a retimed shot moves its
  sound with it. When built.json gets HEDERA field-report clips, the act grows at the HashScan slot; so does this, and
  building the sound also sets the act's length in src/sponsors/hedera/cut.json.

Asset: python prep/sponsors/hedera.py  -> public/sponsors/hedera/plate_body.stl + plate_logo.stl
  The printed Hedera swap plate (cad2/stl_extra/arca_panel_hedera_{body,logo}.stl, black body, white logo), moved to
  where the console's rear plates sit (console.json panelDz, as prep/make_meshes.py does for the ETHGlobal plates).
  The film's console.bin only carries the two ETHGlobal plates, so the act adds this one itself."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BRIEF = os.path.abspath(os.path.join(HERE, "..", ".."))
TIMING = json.load(open(os.path.join(BRIEF, "src", "sponsors", "hedera", "timing.json"), encoding="utf-8"))
BUILT = json.load(open(os.path.join(BRIEF, "src", "acts", "built.json"), encoding="utf-8"))

# the field report: real HashScan / console recordings replace the HashScan slot and the act grows by the difference
CLIPS = [c for c in BUILT.get("clips", []) if str(c.get("sponsor", "")).upper() == "HEDERA"]
SLOT = next(s for s in TIMING["shots"] if s["id"] == "hashscan")
CLIP_FR = [round(c["seconds"] * 60) for c in CLIPS]
GROW = (sum(CLIP_FR) - SLOT["len"]) if CLIPS else 0


def shift(f):
    """A base-timeline frame, moved past the HashScan slot when the field report has grown the act."""
    return f + GROW if f >= SLOT["at"] + SLOT["len"] else f


LEN = TIMING["len"] + GROW
LEN_S = LEN / 60
BED_AT = 40.0                       # C add9, the Mumbai bed: this is what gets built at the event
BED_DB = -25


def build(m, sec):
    shots = {s["id"]: s for s in TIMING["shots"]}
    S = lambda sid, off: sec(shift(shots[sid]["at"] + off))

    ramp(m, 0, LEN_S, [(0, -4), (1.0, 0), (LEN_S - 2.0, 0), (LEN_S, -8)])
    m.fx("whoosh", 0.05, -9)                                  # the slate
    m.fx("tick", sec(5), -12)
    m.fx("tick", sec(12), -15)

    for s in TIMING["shots"]:
        if s["id"] == "slate" or (CLIPS and s["id"] == "hashscan"):
            continue
        at = shift(s["at"])
        if s["id"] in ("plate", "end"):                       # the console, in 3D: a deep hit under the cut
            m.fx("big" if s["id"] == "plate" else "hit", sec(at), -5 if s["id"] == "plate" else -7)
            m.fx("whoosh", sec(at) - 0.14, -12)
        else:                                                 # every hard cut: a short glitch, a breath of air before it
            m.fx("whoosh", sec(at) - 0.12, -13)
            m.fx("glitch", sec(at), -11)
        for c in s.get("cards", []):                          # each card spawning: the box, then its content
            card(m, sec, shift(s["at"] + c), -13)
        for c in s.get("chirps", []):
            m.fx("chirp", sec(shift(s["at"] + c)), -11)
        for c in s.get("hits", []):                           # stamps
            m.fx("hit", sec(shift(s["at"] + c)), -4)
            m.fx("chirp", sec(shift(s["at"] + c + 2)), -9)
        for c in s.get("glitch", []):                         # an inner cut or a screen coming up
            m.fx("glitch", sec(shift(s["at"] + c)), -12)
        for a, b, step in s.get("typing", []):                # PB's words typing out on the console
            for k in range(a, b, step):
                m.fx("tick", sec(shift(s["at"] + k)), -23)

    if CLIPS:                                                 # the field report: in on a glitch, a chirp as it settles
        f0 = SLOT["at"]
        for n in CLIP_FR:
            m.fx("glitch", sec(f0), -9)
            m.fx("chirp", sec(f0 + 30), -11)
            card(m, sec, f0 + 30, -13)
            m.fx("tick", sec(f0 + 16) - 0.03, -19)
            f0 += n

    for ln in TIMING["lines"]:                                # a soft comms tick as each subtitle comes in
        if CLIPS and ln.get("slot"):
            continue
        m.fx("tick", sec(shift(ln["at"])) - 0.03, -19)

    m.fx("whoosh", sec(LEN - 30), -11)                        # out, into the end title
    sync_cut()


def sync_cut():
    """Keep cut.json's act segment as long as the act (it grows with the field report), so post_sponsor.py cuts it right."""
    path = os.path.join(BRIEF, "src", "sponsors", "hedera", "cut.json")
    cut = json.load(open(path, encoding="utf-8"))
    for c in cut:
        if c["video"] == "out/sponsor_hedera_raw.mov" and abs(c["seconds"] - LEN / 60) > 1e-4:
            c["seconds"] = round(LEN / 60, 6)
            open(path, "w", encoding="utf-8").write("[\n" + ",\n".join(" " + json.dumps(x) for x in cut) + "\n]\n")
            print(f"cut.json: the act now runs {LEN / 60:.2f} s")


if __name__ == "__main__":
    import trimesh

    ROOT = os.path.abspath(os.path.join(BRIEF, "..", ".."))
    dz = json.load(open(os.path.join(BRIEF, "public", "console.json"), encoding="utf-8"))["panelDz"]
    out = os.path.join(BRIEF, "public", "sponsors", "hedera")
    os.makedirs(out, exist_ok=True)
    for part in ("body", "logo"):
        mesh = trimesh.load(os.path.join(ROOT, "cad2", "stl_extra", f"arca_panel_hedera_{part}.stl"))
        mesh.apply_translation([0, 0, dz])
        mesh.export(os.path.join(out, f"plate_{part}.stl"))     # binary STL
        print(part, len(mesh.faces), "faces, bounds", mesh.bounds.round(2).tolist())
