"""Sound for the briefing film, synthesised from src/timeline.json so every cue lands on its frame.

  python video/briefing/prep/make_audio.py      -> video/briefing/out/briefing_audio.wav (48 kHz stereo, float)

Beds: a low drone that opens up shot by shot, and a 120 BPM pulse under the build (cuts land on downbeats). Cues: keystrokes for every
typed character, data chirps, locks, whooshes, glitches, a clunk and ping for every part that seats, magnetic snaps
for the panel swaps, the flip, the power-on and the final hit. Peaks are normalised to -1 dBFS; nothing is boosted
past that."""
import json
import os

import numpy as np
from scipy.io import wavfile
from scipy.ndimage import minimum_filter1d
from scipy.signal import butter, fftconvolve, sosfilt

HERE = os.path.dirname(os.path.abspath(__file__))
TL = json.load(open(os.path.join(HERE, "..", "src", "timeline.json"), encoding="utf-8"))
SR = 48000
FPS = TL["fps"]
N = int(TL["duration"] / FPS * SR) + SR          # one second of tail
rng = np.random.default_rng(7)


def sec(frame):
    return frame / FPS


def t_(dur):
    return np.arange(int(dur * SR)) / SR


def env(n, a=0.002, r=0.1, shape=4.0):
    """Attack then exponential release, n samples."""
    x = np.arange(n) / SR
    e = np.minimum(1, x / max(a, 1e-4)) * np.exp(-np.maximum(0, x - a) * shape / max(r, 1e-4))
    return e


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], btype="band", fs=SR, output="sos"), x)


def lp(x, f, order=2):
    return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, btype="high", fs=SR, output="sos"), x)


dry = np.zeros((N, 2))
send = np.zeros((N, 2))         # to the reverb


def put(sig, at, gain=1.0, pan=0.0, verb=0.3):
    """Mix a mono signal in at time `at` (s), equal-power pan -1..1."""
    i = int(at * SR)
    if i >= N:
        return
    sig = sig[: N - i] * gain
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    dry[i:i + len(sig), 0] += sig * l
    dry[i:i + len(sig), 1] += sig * r
    send[i:i + len(sig), 0] += sig * l * verb
    send[i:i + len(sig), 1] += sig * r * verb


# ---- cues --------------------------------------------------------------------------------------------------------

def key_click():
    n = int(0.012 * SR)
    s = hp(rng.standard_normal(n), 1800) * env(n, 0.0005, 0.006, 3)
    s += np.sin(2 * np.pi * rng.uniform(2200, 3400) * t_(0.012)) * env(n, 0.0003, 0.004, 3) * 0.4
    return s


def blip(f, d=0.05, shape=3.0):
    tt = t_(d)
    return np.sin(2 * np.pi * f * tt) * env(len(tt), 0.002, d, shape)


def chirps(at, dur, rate=0.035):
    k = at
    while k < at + dur:
        put(blip(rng.choice([1180, 1560, 2080, 2640, 3120]), 0.03), k, 0.16, rng.uniform(-0.5, 0.5), 0.15)
        k += rate * rng.uniform(0.6, 1.4)


def whoosh(dur=0.7, lo=300, hi=4000, up=True):
    """Noise swept through a bank of band-passes (smooth: the bands crossfade, nothing is re-filtered per block)."""
    n = int(dur * SR)
    x = rng.standard_normal(n)
    centres = np.geomspace(lo, min(hi, SR / 2.4), 8)
    bands = [bp(x, c * 0.7, min(c * 1.4, SR / 2 - 200), 2) for c in centres]
    pos = np.linspace(0, 1, n) if up else np.linspace(1, 0, n)
    out = np.zeros(n)
    for k, band in enumerate(bands):
        out += np.exp(-((pos * (len(bands) - 1) - k) ** 2) / (2 * 0.9 ** 2)) * band
    return out * np.sin(np.pi * np.linspace(0, 1, n)) ** 1.5


def glitch_burst(d=0.16):
    n = int(d * SR)
    x = np.sign(np.sin(2 * np.pi * rng.uniform(180, 900) * t_(d))) * 0.5
    x += np.repeat(rng.standard_normal(n // 64 + 1), 64)[:n]          # bit-crushed noise
    gate = np.repeat(rng.random(n // 900 + 1) > 0.35, 900)[:n]
    return hp(x * gate, 200) * env(n, 0.001, d, 1.5)


def sub_hit(f0=70, f1=32, d=1.6):
    tt = t_(d)
    f = f1 + (f0 - f1) * np.exp(-tt * 6)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * env(len(tt), 0.003, d, 2.6)


def metal(f=2100, d=0.6):
    tt = t_(d)
    s = sum(np.sin(2 * np.pi * f * m * tt) / (k + 1) for k, m in enumerate([1, 1.47, 2.09, 2.76]))
    return s * env(len(tt), 0.001, d, 5)


def clunk(d=0.35):
    tt = t_(d)
    f = 55 + 45 * np.exp(-tt * 30)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(tt), 0.001, 0.18, 4)
    click = hp(rng.standard_normal(len(tt)), 2500) * env(len(tt), 0.0003, 0.008, 3)
    return body * 0.9 + click * 0.35 + metal(rng.uniform(1700, 2600), d) * 0.12


def servo(d):
    tt = t_(d)
    f = 240 + 260 * (tt / d)
    saw = 2 * ((np.cumsum(f) / SR) % 1) - 1
    return lp(saw, 900) * np.sin(np.pi * tt / d) ** 2


def lock_beep():
    return np.concatenate([blip(1320, 0.07, 2), np.zeros(int(0.02 * SR)), blip(1760, 0.11, 2)])


def riser(d, lo=200, hi=1400):
    tt = t_(d)
    f = lo * (hi / lo) ** (tt / d)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.3 + whoosh(d, lo * 2, hi * 4) * 0.7
    return tone * (tt / d) ** 1.5


# ---- beds --------------------------------------------------------------------------------------------------------

def drone():
    tt = np.arange(N) / SR
    x = np.zeros(N)
    for f, a in ((41.2, 1.0), (41.32, 0.35), (61.7, 0.5), (82.4, 0.35), (123.5, 0.12)):
        x += a * np.sin(2 * np.pi * f * tt + rng.uniform(0, 6))
    x += 0.25 * lp(rng.standard_normal(N), 180)
    S = TL["shots"]
    keys = [(0, 0.15), (S["hero"][0], 0.45), (TL["hero"]["explode"], 0.7), (S["build"][0], 0.5), (S["section"][0], 0.62),
            (S["allies"][0], 0.55), (S["end"][0] - 30, 0.65), (S["end"][0], 0.0), (TL["duration"], 0.0)]
    level = np.interp(tt * FPS, [k for k, _ in keys], [v for _, v in keys])
    return x * level


def air():
    x = bp(rng.standard_normal(N), 900, 5000) * 0.018
    return x * (0.75 + 0.25 * np.sin(2 * np.pi * 0.07 * np.arange(N) / SR))


def pulse():
    """120 BPM under the build: a beat is 30 frames, so every step cut (120 frames) lands on a downbeat."""
    out = np.zeros(N)
    a, b = TL["shots"]["build"][0], TL["shots"]["reveal"][0]
    for k, fr in enumerate(range(a, b, 15)):
        i = int(sec(fr) * SR)
        on = k % 2 == 0
        n = int(0.03 * SR)
        tick = hp(rng.standard_normal(n), 7000) * env(n, 0.0005, 0.018 if on else 0.01, 3) * (0.25 if on else 0.12)
        out[i:i + n] += tick[: N - i]
        if k % 4 == 0:
            th = sub_hit(62, 44, 0.32) * 0.4
            out[i:i + len(th)] += th[: N - i]
    return out


def ratchet(d, n_ticks):
    out = np.zeros(max(1, int(d * SR)))
    for j in range(n_ticks):
        i = int(j / n_ticks * len(out))
        c = hp(rng.standard_normal(int(0.006 * SR)), 3500) * env(int(0.006 * SR), 0.0003, 0.004, 3)
        out[i:i + len(c)] += c[: len(out) - i]
    return out


def sizzle(d):
    n = int(d * SR)
    x = hp(rng.standard_normal(n), 3000) * (0.6 + 0.4 * rng.random(n))
    return x * np.sin(np.pi * np.linspace(0, 1, n)) ** 0.6


def magnet_hum(d):
    tt = t_(d)
    return (np.sin(2 * np.pi * 100 * tt) + 0.4 * np.sin(2 * np.pi * 300 * tt)) * (0.5 + 0.5 * np.sin(2 * np.pi * 14 * tt)) * np.sin(np.pi * tt / d)


def slots():
    """The build schedule, computed the same way as src/three/consoleModel.ts."""
    meta = json.load(open(os.path.join(HERE, "..", "public", "console.json"), encoding="utf-8"))["parts"]
    B = TL["build"]
    out = []
    for s, st in enumerate(TL["steps"]):
        for m in st["moves"]:
            parts = [p for f in m["files"] for p in sorted([q for q in meta if q["file"] == f or q["name"] == f], key=lambda q: q["inst"])]
            for i, p in enumerate(parts):
                rigid = bool(m.get("rigid"))
                if rigid and i > 0:
                    continue                      # a rigid group makes one sound
                k = 0 if rigid else i
                base = B["start"] + (s - 1) * B["stepLen"] + m["t0"]
                begin = base + (k * 2 if m["kind"] == "press" else k * m.get("stagger", 0))
                press_at = base + m.get("fly", 0) + k * m.get("stagger", 0)
                land = press_at + m["dur"] if m["kind"] == "press" else begin + m["dur"]
                size = 80.0 if rigid else float(np.linalg.norm(np.array(p["bounds"][1]) - np.array(p["bounds"][0])))
                out.append({"step": s, "kind": m["kind"], "begin": begin, "land": land, "press": press_at, "dur": m["dur"], "size": size, "k": k})
    return out


def limit(x, drive_db=2.0, ceiling=0.89, release=0.09):
    """A look-ahead peak limiter: lifts the body by drive_db while the peaks stay under the ceiling."""
    x = x * 10 ** (drive_db / 20)
    want = np.minimum(1.0, ceiling / np.maximum(np.abs(x).max(axis=1), 1e-9))
    want = minimum_filter1d(want, size=int(0.004 * SR), origin=-int(0.002 * SR))
    g = np.empty_like(want)
    rel = 1.0 / (release * SR)
    cur = 1.0
    for i in range(len(want)):
        w = want[i]
        cur = w if w < cur else cur + (1.0 - cur) * rel
        if cur > w:
            cur = w
        g[i] = cur
    return x * g[:, None]


def main():
    S = TL["shots"]
    bed = drone() * 0.17 + air()
    bed[: int(sec(S["end"][0]) * SR)] += pulse()[: int(sec(S["end"][0]) * SR)] * 0.5
    dry[:, 0] += bed
    dry[:, 1] += bed * 0.97 + np.roll(bed, 240) * 0.03

    # typed text: one click per character
    for e in TL["type"]:
        for c in range(len(e["text"])):
            if e["text"][c] != " ":
                put(key_click(), sec(e["frame"]) + c / e["cps"], 0.2 if e["frame"] < 120 else 0.12, rng.uniform(-0.2, 0.2), 0.05)
    chirps(sec(22), sec(36), 0.025)

    HR = TL["hero"]
    for e in TL["sfx"]:
        at, k = sec(e["frame"]), e["kind"]
        if k == "hum":
            tt = t_(2.5)
            h = sum(np.sin(2 * np.pi * 60 * m * tt) / m for m in (1, 2, 3, 5)) * np.minimum(1, tt / 0.3) * np.exp(-tt * 0.6)
            put(h, at, 0.05, 0, 0)
        elif k == "title":
            put(sub_hit(85, 30, 2.0), at, 0.55, 0, 0.4)
            put(metal(1480, 1.2), at, 0.18, 0, 0.6)
            put(whoosh(0.35, 2000, 9000, False), at, 0.3, 0, 0.3)
        elif k == "glitch":
            put(glitch_burst(), at, 0.35, rng.uniform(-0.3, 0.3), 0.1)
        elif k == "scan":
            put(riser(1.3, 300, 1600), at, 0.22, 0, 0.4)
            put(sub_hit(70, 40, 1.0), at, 0.5, 0, 0.3)
            b0 = S["hero"][0] + 84
            tt = t_(sec(HR["explode"] - 10 - b0))
            band = np.sin(2 * np.pi * np.cumsum(500 + 900 * tt / tt[-1]) / SR) * np.sin(np.pi * tt / tt[-1]) * (0.6 + 0.4 * np.sin(2 * np.pi * 11 * tt))
            put(band, sec(b0), 0.07, -0.2, 0.5)
        elif k == "explode":
            put(whoosh(0.9, 200, 7000), at - 0.05, 0.6, 0, 0.4)
            put(sub_hit(90, 35, 1.4), at, 0.5, 0, 0.4)
            put(glitch_burst(0.06), at, 0.2, 0, 0.1)
            for _ in range(26):
                put(blip(rng.choice([2200, 2900, 3500]), 0.02), at + rng.uniform(0.05, 0.9), 0.07, rng.uniform(-0.8, 0.8), 0.2)
        elif k == "complete":
            for j, f in enumerate((880, 1174, 1568)):
                put(blip(f, 0.16, 2.5), at + j * 0.09, 0.22, (j - 1) * 0.3, 0.5)
        elif k == "section":
            sc = TL["section"]
            put(riser(sec(sc["in"][1] - sc["in"][0]), 200, 1200), at, 0.25, 0, 0.4)
            put(whoosh(0.5, 300, 4000, False), sec(sc["out"][0]), 0.3, 0, 0.3)
        elif k == "card":
            put(whoosh(0.25, 1500, 7000), at - 0.05, 0.25, 0.4, 0.2)
            put(blip(2400, 0.03), at + 0.18, 0.15, 0.4, 0.2)
        elif k == "flip":
            put(whoosh(1.6, 150, 2500), at, 0.6, 0, 0.4)
            put(servo(1.4), at, 0.1, 0, 0.2)
        elif k == "power":
            put(riser(0.6, 200, 1400), at - 0.6, 0.3, 0, 0.3)
            put(blip(1568, 0.5, 1.5), at, 0.2, 0, 0.7)
            put(blip(2093, 0.6, 1.5), at + 0.08, 0.14, 0, 0.7)
        elif k == "impact":
            n = int(1.0 * SR)
            rev = hp(rng.standard_normal(n), 400) * np.linspace(0, 1, n) ** 3
            put(rev, at - 1.0, 0.22, 0, 0.4)
            put(sub_hit(65, 28, 4.0), at, 0.75, 0, 0.45)
            put(metal(980, 3.0), at, 0.13, 0, 0.8)
            put(glitch_burst(0.08), at, 0.25, 0, 0.1)

    # a hit on every cut
    B = TL["build"]
    for s in range(1, B["steps"] + 1):
        at = sec(B["start"] + (s - 1) * B["stepLen"])
        put(sub_hit(95, 50, 0.45), at, 0.42, 0, 0.2)
        put(whoosh(0.28, 700, 9000, False), at - 0.12, 0.28, 0, 0.2)
        put(glitch_burst(0.05), at, 0.14, rng.uniform(-0.4, 0.4), 0.05)

    # every part, by how it goes in
    for sl in slots():
        pan = float(np.clip((sl["k"] % 5 - 2) * 0.18, -0.5, 0.5))
        land = sec(sl["land"])
        if sl["kind"] == "spin":
            t_thread = sec(sl["begin"] + 0.45 * sl["dur"])
            put(ratchet(land - t_thread, 9), t_thread, 0.16, pan, 0.1)
            put(clunk(0.12), land, 0.18, pan, 0.2)
            put(metal(rng.uniform(2700, 3300), 0.25), land, 0.06, pan, 0.3)
        elif sl["kind"] == "press":
            put(sizzle(sec(sl["land"] - sl["press"]) + 0.15), sec(sl["press"]), 0.1, pan, 0.2)
            put(clunk(0.1), land, 0.12, pan, 0.2)
        elif sl["kind"] == "snap":
            d = sec(sl["dur"])
            put(magnet_hum(0.16 * d), sec(sl["begin"]) + 0.62 * d, 0.08, 0, 0.3)
            put(clunk(0.3), sec(sl["begin"]) + 0.84 * d, 0.6, 0, 0.3)
            put(metal(3100, 0.3), sec(sl["begin"]) + 0.84 * d, 0.12, 0, 0.3)
        else:
            if sl["kind"] in ("tilt", "slide"):
                put(servo(sec(sl["dur"])), sec(sl["begin"]), 0.07, pan, 0.2)
            if sl["size"] < 18:
                put(clunk(0.12), land, 0.16, pan, 0.2)
                put(blip(rng.choice([2400, 2800]), 0.025), land, 0.06, pan, 0.2)
            else:
                put(clunk(), land, 0.48, pan, 0.3)

    # panel swaps: lift off, then the magnetic clack
    for sw in TL["swap"]["swaps"]:
        put(whoosh(0.5, 600, 6000), sec(sw), 0.3, 0, 0.3)
        put(magnet_hum(0.35), sec(sw + 16 + 30), 0.07, 0, 0.3)
        put(clunk(0.25), sec(sw + 16 + 50), 0.55, 0, 0.3)
        put(metal(3100, 0.25), sec(sw + 16 + 50), 0.12, 0, 0.3)

    # reverb: stereo exponentially decaying noise
    ir_n = int(2.2 * SR)
    decay = np.exp(-np.arange(ir_n) / SR * 3.2)
    ir = np.stack([lp(rng.standard_normal(ir_n), 6000) * decay, lp(rng.standard_normal(ir_n), 6000) * decay], 1) * 0.05
    wet = np.stack([fftconvolve(send[:, c], ir[:, c])[:N] for c in range(2)], 1)
    mix = hp(dry + wet, 25)
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    # fades: in over the first 0.3 s, out over the tail
    fade = np.ones(N)
    fade[: int(0.3 * SR)] = np.linspace(0, 1, int(0.3 * SR))
    tail = int(sec(TL["duration"]) * SR)
    fade[tail:] = np.linspace(1, 0, N - tail)
    mix *= fade[:, None]
    mix = limit(mix)
    peak = np.abs(mix).max()
    mix = mix / peak * 10 ** (-1 / 20)
    out = os.path.join(HERE, "..", "out", "briefing_audio.wav")
    wavfile.write(out, SR, mix.astype(np.float32))
    rms = np.sqrt(np.mean(mix ** 2))
    print(f"{out}: {len(mix) / SR:.1f} s, peak -1.0 dBFS, rms {20 * np.log10(rms):.1f} dBFS")


if __name__ == "__main__":
    main()
