"""Sound for the dossier (src/dossier/dossier.json), in the manner of a Modern Warfare III briefing: a low tense bed,
a radio squelch whenever someone starts talking, a digital burst on every pixel cut, UI ticks as cards load, a
counter rattle on the seed search, a thud for every verdict stamp, and a deep hit on the countermeasure.

  python video/briefing/prep/make_dossier_audio.py   -> video/briefing/out/dossier_audio.wav"""
import json
import os

import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve

import make_audio as A                      # the shared synth voices (blip, whoosh, glitch_burst, ...)

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "..", "src", "dossier", "dossier.json"), encoding="utf-8"))
SR, FPS = A.SR, D["fps"]
N = int(D["duration"] / FPS * SR) + SR
rng = np.random.default_rng(11)
dry = np.zeros((N, 2))
send = np.zeros((N, 2))
sec = lambda fr: fr / FPS
case_at = lambda k: D["caseStart"] + k * D["caseLen"]


def put(sig, at, gain=1.0, pan=0.0, verb=0.3):
    i = int(at * SR)
    if i >= N or i < 0:
        return
    sig = sig[: N - i] * gain
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    dry[i:i + len(sig), 0] += sig * l
    dry[i:i + len(sig), 1] += sig * r
    send[i:i + len(sig), 0] += sig * l * verb
    send[i:i + len(sig), 1] += sig * r * verb


def bed():
    tt = np.arange(N) / SR
    x = np.zeros(N)
    for f, a in ((55.0, 1.0), (55.18, 0.5), (82.4, 0.45), (110.2, 0.25), (164.8, 0.08)):
        saw = 2 * ((f * tt + rng.uniform()) % 1) - 1
        x += a * saw
    x = A.lp(x, 320, 2) + 0.2 * A.lp(rng.standard_normal(N), 160)
    swell = 0.55 + 0.45 * np.sin(2 * np.pi * tt / 9.0) ** 2
    keys = [(0, 0.2), (300, 0.6), (D["outro"][0], 0.8), (2900, 1.0), (D["duration"] - 20, 0.0), (D["duration"] + 60, 0.0)]
    lvl = np.interp(tt * FPS, [k for k, _ in keys], [v for _, v in keys])
    return x * swell * lvl


def pulse():
    out = np.zeros(N)
    for k, fr in enumerate(range(330, D["outro"][0], 30)):               # 120 BPM heartbeat under the case files
        th = A.sub_hit(58, 42, 0.4) * (0.5 if k % 2 == 0 else 0.25)
        i = int(sec(fr) * SR)
        out[i:i + len(th)] += th[: N - i]
    return out


def squelch():
    n = int(0.09 * SR)
    x = A.bp(rng.standard_normal(n), 900, 3200) * A.env(n, 0.001, 0.07, 2.5)
    b = A.blip(2350, 0.04, 2) * 0.3
    x[: len(b)] += b
    return x


def ui_tick():
    x = A.blip(rng.choice([1800, 2400, 3000]), 0.025, 3)
    n = int(0.01 * SR)
    x[:n] += A.hp(rng.standard_normal(n), 4000) * A.env(n, 0.0003, 0.006, 3) * 0.4
    return x


def rattle(d):
    out = np.zeros(int(d * SR))
    k = 0
    while k < d:
        c = A.blip(rng.choice([2600, 3100, 3600]), 0.012, 3)
        i = int(k * SR)
        out[i:i + len(c)] += c[: len(out) - i]
        k += 0.028 + 0.02 * k / d
    return out


def stamp():
    x = A.sub_hit(110, 55, 0.35) * 0.9
    n = int(0.05 * SR)
    x[:n] += A.hp(rng.standard_normal(n), 1500) * A.env(n, 0.0005, 0.03, 3) * 0.5
    return x


def main():
    b = bed() * 0.11 + pulse() * 0.35
    dry[:, 0] += b
    dry[:, 1] += np.roll(b, 180)

    cuts = [190] + [case_at(k) + o for k in range(5) for o in (0, 150, 300)] + [D["outro"][0], 2900]
    for c in cuts:
        put(A.glitch_burst(0.11), sec(c) - 0.04, 0.28, rng.uniform(-0.3, 0.3), 0.1)
        put(A.whoosh(0.3, 800, 7000, False), sec(c) - 0.15, 0.18, 0, 0.2)

    lines = list(D["intro_lines"]) + list(D["outro_lines"])
    for k, c in enumerate(D["cases"]):
        for i, t in enumerate(c["lines"]):
            lines.append({"at": case_at(k) + i * 150 + 10, "who": "Any%" if i == 2 else "Handler"})
    for l in lines:
        put(squelch(), sec(l["at"]), 0.22, -0.2 if l["who"] == "Handler" else 0.2, 0.15)

    loads = [196 + k * 7 for k in range(5)] + [case_at(k) + 150 for k in range(5)] + [case_at(k) + 306 for k in range(5)] + [2700]
    for fr in loads:
        put(ui_tick(), sec(fr), 0.16, rng.uniform(-0.5, 0.5), 0.2)
        put(ui_tick(), sec(fr + 7), 0.12, rng.uniform(-0.5, 0.5), 0.2)
    put(rattle(sec(56)), sec(case_at(2) + 164), 0.1, 0.2, 0.15)          # the seed counter rolling up

    for k in range(5):
        put(stamp(), sec(case_at(k) + 318), 0.6, 0, 0.35)
    put(A.sub_hit(70, 30, 3.0), sec(2820), 0.7, 0, 0.5)                   # the countermeasure lands
    put(A.metal(990, 2.5), sec(2820), 0.12, 0, 0.7)
    put(A.riser(1.4, 150, 1100), sec(D["duration"]) - 1.5, 0.25, 0, 0.3)

    ir_n = int(2.6 * SR)
    decay = np.exp(-np.arange(ir_n) / SR * 2.6)
    ir = np.stack([A.lp(rng.standard_normal(ir_n), 5000) * decay, A.lp(rng.standard_normal(ir_n), 5000) * decay], 1) * 0.05
    wet = np.stack([fftconvolve(send[:, c], ir[:, c])[:N] for c in range(2)], 1)
    mix = A.hp(dry + wet, 25)
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    fade = np.ones(N)
    fade[: int(0.3 * SR)] = np.linspace(0, 1, int(0.3 * SR))
    tail = int(sec(D["duration"]) * SR)
    fade[tail:] = np.linspace(1, 0, N - tail)
    mix = A.limit(mix * fade[:, None])
    mix = mix / np.abs(mix).max() * 10 ** (-1 / 20)
    out = os.path.join(HERE, "..", "out", "dossier_audio.wav")
    wavfile.write(out, SR, mix[: tail + int(0.05 * SR)].astype(np.float32))
    print(f"{out}: {tail / SR:.1f} s, rms {20 * np.log10(np.sqrt(np.mean(mix ** 2))):.1f} dBFS")


if __name__ == "__main__":
    main()
