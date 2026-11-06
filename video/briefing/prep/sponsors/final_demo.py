"""The final film's sound (FinalDemo, video/final/SCRIPT.md): the house synth grammar, synthesised only.

  python scripts/heavy.py python prep/make_mw3_audio.py out/mw3ref sponsor final_demo
    -> out/sponsor_final_demo_orig.wav, then copy it to public/final/audio/final_demo.wav

make_mw3_audio.py runs this file with card, ramp, rnd and np handed in and reads LEN_S, BED_AT, BED_DB and build().
The cues are read from the composition itself (src/final/FinalDemo.tsx and scenes.json): every cut, card, stamp,
slate, subtitle and 3D shot gets its sound where the TS draws it, so a retimed shot moves its sound with it.
Beds change with the story: D minor (the problem), F add9 (the fix), C add9 (Mumbai). The reused acts (Primer,
BreaksSub, the assembly film, TitleEnd) bring their own sound, cut on the same frame windows as their pictures. The race
clip's game audio is mixed by Remotion (ducked under subtitles), not here."""
import json
import os
import re

import soundfile as sf
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
BRIEF = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(BRIEF, "out")
SC = json.load(open(os.path.join(BRIEF, "src", "final", "scenes.json"), encoding="utf-8"))
TSX = open(os.path.join(BRIEF, "src", "final", "FinalDemo.tsx"), encoding="utf-8").read()
SR = 48000

STARTS = []
_t = 0
for _s in SC["scenes"]:
    STARTS.append(_t)
    _t += _s["len"]
LEN = _t
LEN_S = LEN / 60
BED_AT = None                     # the beds are laid per section in build()
BED_DB = -26


def block(n):
    """The TSX source of scene n's component."""
    a = TSX.index(f"const S{n}: React.FC")
    nxt = [i for i in (TSX.find("\nconst S", a + 10), TSX.find("\n/* ----", a + 10)) if i > 0]
    return TSX[a: min(nxt) if nxt else len(TSX)]


def at_value(expr):
    expr = expr.strip()
    m = re.fullmatch(r"sec\(([\d.]+)\)", expr)
    if m:
        return float(m.group(1)) * 60
    try:
        return float(expr)
    except ValueError:
        return None


def cues(n):
    """(kind, frame in the scene) for scene n, read from its TSX."""
    b = block(n)
    out = []
    wins = [(m.start(), int(m.group(1))) for m in re.finditer(r"<Win f=\{f\} a=\{(\d+)\} b=\{\d+\}>", b)]
    win_at = lambda pos: max([a for p, a in wins if p < pos], default=0)
    # cuts={[...]}, or the SAFE cut (the final film renders in SAFE mode): pick([...], [SAFE]) / SAFE && ... ? [SAFE] : [...]
    m = re.search(r"cuts=\{(?:pick\(\[[\d, ]*\], \[([\d, ]*)\]\)|SAFE && !isLive\(TAKES\.\w+\) \? \[([\d, ]*)\] : \[[\d, ]*\]|\[([\d, ]+)\])\}", b)
    txt = next((g for g in m.groups() if g is not None), "") if m else ""
    for c in [int(x) for x in txt.split(",") if x.strip()]:
        out.append(("cut", c))
    m = re.search(r"lines\(([\d.]+), (?:pick<[^>]*>\()?\[(.*?)\]\)", b, re.S)
    if m:                                                    # a line may be pick("normal", "safe"): same time either way
        for t in sorted(set(re.findall(r'\[([\d.]+), (?:pick\()?"', m.group(2)))):
            out.append(("line", float(t) * 60))
    for m in re.finditer(r"<Card2 (?:key=\{[^}]*\} )?f=\{(f|t)\} at=\{([^}]+)\}", b):
        v = at_value(m.group(2))
        if v is not None and v >= 0:
            out.append(("card", v + (win_at(m.start()) if m.group(1) == "t" else 0)))
    for m in re.finditer(r"<Stamp f=\{(f|t)\} at=\{(\d+)\}", b):
        out.append(("stamp", int(m.group(2)) + (win_at(m.start()) if m.group(1) == "t" else 0)))
    for m in re.finditer(r"<Slate2 ", b):
        out.append(("slate", win_at(m.start())))
    for m in re.finditer(r"<C3D |<Console3D ", b):
        out.append(("console", win_at(m.start())))
    for m in re.finditer(r"<ModelCode f=\{t\}", b):
        w = win_at(m.start())
        out += [("node", w + k) for k in (4, 22, 30)]
    for m in re.finditer(r"<ArkivFlow f=\{(f|t)\}", b):
        w = win_at(m.start()) if m.group(1) == "t" else 0
        out += [("node", w + k) for k in (4, 12, 20, 28, 36, 46)]
    for m in re.finditer(r"<PayFlow f=\{f\}", b):
        out += [("node", k) for k in (4, 14, 24, 34, 44, 54)]
    for m in re.finditer(r"<HcsPanel f=\{t\}", b):
        w = win_at(m.start())
        out += [("row", w + 6 + 5 * k) for k in range(6)]
    for m in re.finditer(r"<Quote f=\{t\} at=\{(\d+)\}", b):
        out.append(("quote", win_at(m.start()) + int(m.group(1))))
    for m in re.finditer(r"<Pointer f=\{f\} at=\{([^}]+)\}", b):
        out.append(("pointer", at_value(m.group(1))))
    if n == 22:                                              # the close's three cards come from a list
        out += [("card", 18), ("card", 120), ("card", 222), ("url", 360), ("end", 540)]
    return out


def wav(name, a_frame, b_frame):
    """A window of an act's own sound file (in out/), by the act's 60 fps frames, as 48 kHz stereo."""
    x, sr = sf.read(os.path.join(OUT, name), start=0, dtype="float32", always_2d=True)
    if sr != SR:
        x = resample_poly(x, SR, sr, axis=0).astype("float32")
    seg = x[int(a_frame / 60 * SR): int(b_frame / 60 * SR)].copy()
    n = min(len(seg), int(0.02 * SR))
    if n:
        ramp_in = np.linspace(0, 1, n)[:, None]
        seg[:n] *= ramp_in
        seg[-n:] *= ramp_in[::-1]
    if seg.shape[1] == 1:
        seg = np.repeat(seg, 2, axis=1)
    return seg


def build(m, sec):
    S = lambda n, f: (STARTS[n - 1] + f) / 60

    def pad(key, a, b, db):                                  # a synth bed from a to b (s), with its own fades
        t = type(m)(b - a)
        t.bed(key, b - a, db)
        m.put(t.x[: int((b - a + 0.5) * SR)], a)

    pad(145.0, 0.0, 8.6, -31)                                # the cold open: D minor under the race's engine
    pad(220.0, S(4, 0) - 0.4, S(9, 0) + 0.6, -26)            # the fix: F add9, through World
    pad(40.0, S(9, 0) - 0.4, S(18, 0) + 0.6, -26)            # Arkiv and Hedera: C add9
    pad(40.0, S(18, 0) - 0.2, S(21, 0) + 0.8, -23)           # what you get: the bed lifts
    pad(40.0, S(22, 0) - 0.6, LEN_S, -24)                    # the close

    # the reused acts' own sound, on the same windows as their pictures
    m.put(wav("primer_orig.wav", 0, 720), S(2, 0), -2)
    t = S(3, 0)
    for a, b in ((50, 400), (430, 780), (810, 1160), (1190, 1340)):
        m.put(wav("breaks_sub_orig.wav", a, b), t, -2)
        t += (b - a) / 60
    t = S(21, 0)
    for a, b in ((160, 560), (1020, 1490), (1800, 2010)):
        m.put(wav("briefing_audio.wav", a, b), t, -4)
        t += (b - a) / 60
    m.put(wav("title_end_orig.wav", 120, 240), S(22, 540), -1)

    own = {2, 3, 21}                                         # scenes whose act already carries its cues
    for n in range(1, len(SC["scenes"]) + 1):
        if n in own:
            continue
        for kind, f in cues(n):
            at = S(n, f)
            if kind == "cut" and f > 0:
                m.fx("whoosh", at - 0.12, -14)
                m.fx("glitch", at, -13)
            elif kind == "line":
                m.fx("tick", at - 0.03, -19)
            elif kind == "card":
                card(m, sec, STARTS[n - 1] + f, -14)
            elif kind == "stamp":
                m.fx("hit", at, -7)
                m.fx("glitch", at + 0.02, -12)
            elif kind == "slate":
                m.fx("whoosh", at + 0.02, -10)
                m.fx("hit", at + 0.1, -8)
            elif kind == "console":
                m.fx("whoosh", at - 0.15, -12)
                m.fx("big", at, -9)
            elif kind == "node":
                m.fx("tick", at, -16)
            elif kind == "row":
                m.fx("tick", at, -18)
            elif kind in ("quote", "pointer", "url"):
                m.fx("chirp", at, -11)
            elif kind == "end":
                m.fx("big", at, -6)
        if n > 1:                                            # every scene starts on a hard cut
            m.fx("whoosh", S(n, 0) - 0.12, -13)
            m.fx("glitch", S(n, 0), -12)
    m.fx("hit", S(2, 0), -8)                                 # out of the cold open into the primer
    ramp(m, LEN_S - 1.2, LEN_S, [(LEN_S - 1.2, 0), (LEN_S, -40)])   # out to black by 3:58.0
