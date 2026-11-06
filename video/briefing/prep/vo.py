"""The narration for the ETHGlobal submission cut. ETHGlobal's rules: 2 to 4 minutes, no music-with-text instead of
talking, no text-to-speech or AI voice. So a person (Chris) reads the Handler lines; the captions stay as captions.

  python prep/vo.py script            -> src/acts/vo.json (the lines on the submission cut's clock) + VO_SCRIPT.md
  python prep/vo.py prompter          -> out/Any% VO Prompter.mp4 (picture + the line to say + sync beeps; play it
                                         and read along while recording)
  python prep/vo.py mix REC [--track N]
                                      -> out/Any% Submission v7 - ETHGlobal Mumbai.mp4 (the voice laid on the cut,
                                         music ducked under it, -16 LUFS, length and resolution checked)
  python prep/vo.py test              -> runs mix on a synthetic recording (beeps + noise bursts at the cues, no speech)
                                         and checks the alignment

Sync: the prompter opens with three 1 kHz beeps at 0.5, 1.5 and 2.5 s and the film starts at 3.0 s. Record with the
prompter playing out loud (it carries no other sound, so nothing bleeds); the beeps in the recording set the offset.
Needs CUT=sub python post_film.py first (out/film_video_sub.mp4, out/film_audio_sub_orig.wav)."""
import json
import os
import re
import subprocess
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
os.chdir(ROOT)
os.environ["CUT"] = "sub"
sys.path.insert(0, ROOT)
import post_film as P  # noqa: E402

SR = 48000
PRE = 3.0                                                  # countdown before the film, in the prompter
BEEPS = (0.5, 1.5, 2.5)
OUT = "out/Any% Submission v7 - ETHGlobal Mumbai.mp4"
PROMPTER = "out/Any% VO Prompter.mp4"

# (segment in SEG_SUB, frame on that act's own clock, the act's slow factor, the line). Mirrors each act's LINES;
# script() checks every captioned line against its source file. The title line has no caption: it is said over the
# flash-forward and the title, so the first 25 seconds say what this is.
SRC = {0: "ColdOpen", 1: "ProofFlash", 3: "Primer", 4: "Breaks", 6: "MachineSubs", 7: "GameReel", 8: "Proof", 9: "Check", 10: "Coach",
       11: "Proof", 12: "Objectives", 13: "Handler", 15: "ColdOpen"}
VO = [
    (0, 70, 1, "Every world record is a claim."),
    (0, 330, 1, "Thousands of records, and you have to take each one on trust."),
    (0, 780, 1, "And a claim is only as good as its proof."),
    (1, 8, 1, "Any%: every run is a tiny log anyone can replay."),
    (1, 236, 1, "Change one byte, and the fingerprint breaks."),
    (3, 24, 1, "A speedrun: finish a game as fast as you possibly can."),
    (3, 280, 1, "The fastest time on the board is the world record."),
    (3, 500, 1, "And the only thing standing behind it is a video."),
    (4, 70, 1, "Splice two attempts together, and the video looks like one run."),         # Part I at its v3 pace here
    (4, 450, 1, "Mod the game to change the odds, and the video still looks fair."),
    (4, 830, 1, "Or slow the game down, and play the video back at full speed."),
    (4, 1200, 1, "Video can't tell which. So we stopped trusting video."),
    (6, 20, 1, "This is Any%: a handheld console, built for speedrunning."),
    (6, 240, 1, "Fifty-nine parts, from the shell to the screws."),
    (6, 900, 1, "A five-inch touchscreen, and a Raspberry Pi to run the games."),
    (6, 1150, 1, "Our own games, with fixed rules: same inputs in, same run out."),
    (6, 1420, 1, "The buttons are cosmetic for now: pair a controller, and play."),
    (6, 1690, 1, "And every input, every frame, is written to a log."),
    (7, 86, 1, "Ship It: run the hackathon office."),                                       # GameReelShort: 4 s a game
    (7, 326, 1, "Rush Hour: Mumbai's trains, against the clock."),
    (7, 566, 1, "Zip: a packet racing through the venue."),
    (7, 806, 1, "Marine Drive GP: three laps, three rivals."),
    (7, 1046, 1, "Segfault: bugs in the server room."),
    (7, 1292, 1, "Five games. Any run in any of them can be checked, by anyone."),
    (8, 70, 1.2, "A full run of Rush Hour, logged by the game itself."),
    (8, 280, 1.2, "Every button, every frame, written down as it is played."),
    (8, 515, 1.2, "The whole run, every frame of it, fits in 731 bytes."),
    (8, 760, 1.2, "Hand that log to anyone. They replay it, with the same rules."),
    (8, 1020, 1.2, "The fingerprints match: the run is exactly what those inputs produce."),
    (8, 1220, 1.2, "Now change a single bit of the log. Byte 381."),
    (8, 1440, 1.2, "The fingerprint changes. A modded game fails too; a spliced log desyncs."),
    (9, 26, 1, "The real checker, run on a laptop, with its actual output."),
    (9, 318, 1, "Five games, five run logs. Each one checked in milliseconds."),
    (10, 24, 1, "The same log also coaches you. Meet PB, the launcher's coach."),
    (10, 342, 1, "It replays both runs, and finds where the time went."),
    (11, 1660, 1.2, "A fresh seed every launch, but a rigged console could pick its own."),
    (11, 1900, 1.2, "Not proven yet: who claims it, when, and at what pace. That is Mumbai."),
    (12, 60, 1, "At ETHGlobal Mumbai, we'll add three networks."),
    (12, 210, 1, "World ID: your agent asks, only you approve."),
    (12, 420, 1, "Hedera: HCS seeds and checkpoints, and x402 payments."),
    (12, 640, 1, "And Arkiv: every log, on a board anyone can query."),
    (12, 856, 1, "The goal: your coach agent pays the runner just ahead of you, for their ghost."),
    (13, 54, 1, "PB also walks you through every sponsor step."),
    (13, 300, 1, "Real screens. The calls stay mock until Mumbai."),
    (15, 250, 1, "Don't trust the video. Check the run."),
]
# THE FIELD REPORT (src/acts/built.json, Objectives.tsx): each clip's line between the cards and the loop, which moves
# later by the clips' length; once all three networks are built, the act's first and last lines turn to past tense.
BUILT = json.load(open("src/acts/built.json", encoding="utf-8"))
ALL_DONE = all(BUILT["built"].values())
_t, _clips = 856, []
for _c in BUILT["clips"]:
    _clips.append((12, _t + 16, 1, _c["line"]))
    _t += round(_c["seconds"] * 60)
_loop = (12, _t, 1, ("Your coach agent pays the runner just ahead of you, for their ghost." if ALL_DONE
                     else "The goal: your coach agent pays the runner just ahead of you, for their ghost."))
_sum = (12, _t + 344, 1, ("" if ALL_DONE else "The plan: ") + ("checked" if not ALL_DONE else "Checked")
        + " on the console, published with World ID, listed on Arkiv, paid over Hedera.")
VO = [v for v in VO if not (v[0] == 12 and v[1] == 856)]
VO.insert(next(i for i, v in enumerate(VO) if v[0] > 12), _sum)
VO.insert(next(i for i, v in enumerate(VO) if v[0] == 12 and v[1] == _t + 344), _loop)
for _c in reversed(_clips):
    VO.insert(next(i for i, v in enumerate(VO) if v[0] == 12 and v[1] == _t), _c)
if ALL_DONE:
    VO = [(s, f, k, "At ETHGlobal Mumbai, we added three networks.") if (s, f) == (12, 60) else (s, f, k, x) for s, f, k, x in VO]
if any(BUILT["built"].values()):                         # THE HANDLER (Handler.tsx): its screens stay mock-drawn
    VO = [(s, f, k, "These screens run on mocks. The real calls came just before.") if (s, f) == (13, 300) else (s, f, k, x)
          for s, f, k, x in VO]
if not P.HANDLER_IN_SUB:                                 # the cut dropped it to stay under 4:00: its lines go with it
    VO = [(s - (s > 13), f, k, x) for s, f, k, x in VO if s != 13]
    SRC = {s - (s > 13): v for s, v in SRC.items() if s != 13}
FIELD_LINE = "And this is the real console, running."     # src/acts/FieldTape.tsx, only with real footage
TEMPLATED = {"The whole run, every frame of it, fits in 731 bytes.": ("The whole run, every frame of it, fits in ${",),
             "Now change a single bit of the log. Byte 381.": ("Now change a single bit of the log. Byte ${",)}


def starts():
    t, out = 0.0, []
    for s in P.SEG_SUB:
        out.append(t)
        t += s[3]
    return out, t


def lines():
    """VO with each segment index moved past the field tape, and its line added, when the cut has one."""
    if P.FIELD_AT is None:
        return VO
    out = [(s + (s >= P.FIELD_AT), fr, slow, text) for s, fr, slow, text in VO]
    k = next(i for i, v in enumerate(out) if v[0] > P.FIELD_AT)
    return out[:k] + [(P.FIELD_AT, 24, 1, FIELD_LINE)] + out[k:]


def src_of(seg):
    if P.FIELD_AT is None:
        return SRC[seg]
    return "FieldTape" if seg == P.FIELD_AT else SRC[seg - (seg > P.FIELD_AT)]


def timeline():
    st, total = starts()
    rows = []
    for seg, fr, slow, text in lines():
        trim = P.SEG_SUB[seg][2]
        t = st[seg] + fr * slow / 60 - (trim[0] if trim and P.SEG_SUB[seg][1] is not None else 0)
        rows.append({"t": round(t, 3), "text": text, "caption": src_of(seg) is not None, "words": len(re.findall(r"[\w%'-]+", text))})
    for i, r in enumerate(rows):
        nxt = rows[i + 1]["t"] if i + 1 < len(rows) else total
        r["budget"] = round(nxt - r["t"], 2)
        r["wps"] = round(r["words"] / r["budget"], 2)
    return rows, total


def script():
    rows, total = timeline()
    for (seg, _, _, text), r in zip(lines(), rows):           # every captioned line must be the act's own words
        if src_of(seg) is None:
            continue
        src = open(f"src/acts/{src_of(seg)}.tsx", encoding="utf-8").read() + "".join(c["line"] for c in BUILT["clips"])
        assert all(p in src for p in TEMPLATED.get(text, (text,))), f"not in {src_of(seg)}.tsx: {text}"
    json.dump({"pre": PRE, "beeps": BEEPS, "total": round(total, 3), "lines": rows}, open("src/acts/vo.json", "w", encoding="utf-8"), indent=1)
    fast = [r for r in rows if r["wps"] > 2.8]
    md = ["# Narration script: ETHGlobal submission cut", "",
          f"Read by a person (ETHGlobal bans text-to-speech and AI voices, and music-with-text instead of talking). The cut "
          f"runs {int(total // 60)}:{total % 60:04.1f}; the limit is 4:00.", "",
          "How to record:", "",
          "1. Quiet room, a real microphone (not a phone, not AirPods; the Brio mic is fine), about a hand's width away.",
          f"2. Start recording, then play `{PROMPTER}` out loud (it has no sound but three beeps; they set the sync).",
          "3. Read each line when the prompter turns it amber. Calm, clear, a little slower than feels natural. If a line",
          "   overruns, keep going: the next one waits for its cue, not for you. Fluffed a line? Finish the take anyway.",
          "4. Stop after the end title. Then: `python prep/vo.py mix path/to/recording.wav` (any format ffmpeg reads).",
          "   With OBS multi-track recordings, add `--track N` for the microphone's track.", "",
          "| # | Time | Line | Words | Seconds to the next line |", "|---|---|---|---|---|"]
    for i, r in enumerate(rows):
        m, s = divmod(r["t"], 60)
        note = "" if r["caption"] else " *(no caption: said over the title)*"
        md.append(f"| {i + 1} | {int(m)}:{s:04.1f} | {r['text']}{note} | {r['words']} | {r['budget']} |")
    md += ["", f"Pace: {sum(r['words'] for r in rows)} words in {total:.0f} s. Lines above 2.8 words a second: "
           + (", ".join(str(rows.index(r) + 1) for r in fast) if fast else "none") + "."]
    open("VO_SCRIPT.md", "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(len(rows), "lines,", round(total, 3), "s; fastest", max(r["wps"] for r in rows), "words/s; over 2.8:", [r["text"] for r in fast])


def beep_track(seconds):
    x = np.zeros(int(seconds * SR), np.float32)
    n = int(0.12 * SR)
    b = (0.5 * np.sin(2 * np.pi * 1000 * np.arange(n) / SR) * np.hanning(n)).astype(np.float32)
    for t in BEEPS:
        x[int(t * SR): int(t * SR) + n] += b
    return x


def prompter():
    rows, total = timeline()
    subprocess.run(["npx", "remotion", "render", "src/index.ts", "Prompter", "out/prompter_panel.mov", "--codec=prores",   # remotion.config pins ProRes
                    "--concurrency=4", "--log=error"], check=True, shell=os.name == "nt")
    sf.write("out/prompter_beeps.wav", beep_track(PRE + total + 1), SR)
    P.run(["-i", P.VIDEO, "-i", "out/prompter_panel.mov", "-i", "out/prompter_beeps.wav", "-filter_complex",
           f"[0:v]scale=1280:720,tpad=start_duration={PRE}:color=black,pad=1920:720:320:0[top];[top][1:v]vstack=inputs=2,format=yuv420p[v]",
           "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "160k",
           "-t", f"{PRE + total + 0.5:.3f}", "-movflags", "+faststart", PROMPTER])
    print(PROMPTER)


def load(path, track=None):
    args = ["ffmpeg", "-v", "error", "-i", path] + (["-map", f"0:a:{track}"] if track is not None else []) + \
           ["-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(args, capture_output=True, check=True).stdout, np.float32)


def find_sync(x):
    """Where the first beep starts in the recording: matched filter on the three-beep pattern."""
    from scipy.signal import fftconvolve
    tpl = beep_track(BEEPS[-1] + 0.2)[int((BEEPS[0] - 0.05) * SR):]
    head = x[: int(30 * SR)]
    c = fftconvolve(head, tpl[::-1], mode="valid")
    i = int(np.argmax(np.abs(c)))
    return i / SR + 0.05, float(np.abs(c[i]) / (np.sqrt((head ** 2).sum() * (tpl ** 2).sum()) + 1e-12))


def mix(rec, track=None):
    x = load(rec, track)
    b0, score = find_sync(x)
    film0 = b0 - BEEPS[0] + PRE                              # where the film's frame 0 falls in the recording
    print(f"sync: first beep at {b0:.3f} s (match {score:.2f}); film starts at {film0:.3f} s of the recording")
    if score < 0.05:
        sys.exit("no clear beeps found: was the prompter audible to the microphone? (or pass --track)")
    total = sum(s[3] for s in P.SEG_SUB)
    vo = x[int(film0 * SR):]
    vo = np.concatenate([vo, np.zeros(max(0, int(total * SR) - len(vo)), np.float32)])[: int(total * SR)]
    sf.write("out/vo_aligned.wav", vo, SR)
    film = P.AUDIO[True]
    graph = ("[0:a]highpass=f=80,afftdn=nf=-30,acompressor=threshold=0.08:ratio=3:attack=8:release=200:makeup=2,"
             "aformat=channel_layouts=stereo,asplit=2[vo][key];"
             "[1:a][key]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=450:makeup=1[bed];"
             "[bed][vo]amix=inputs=2:weights=1 1.6:normalize=0[a]")
    raw = "out/vo_mix.raw.wav"
    P.run(["-i", "out/vo_aligned.wav", "-i", film, "-filter_complex", graph, "-map", "[a]", "-c:a", "pcm_f32le", "-ar", "48000", raw])
    target = "I=-16:TP=-1.0:LRA=20"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", raw, "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = json.loads(r.stderr[r.stderr.rindex("{"): r.stderr.rindex("}") + 1])
    af = (f"loudnorm={target}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
          f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")
    P.chapters()
    tmp = OUT.replace(".mp4", ".part.mp4")
    P.run(["-i", P.VIDEO, "-i", raw, "-i", "out/chapters.txt", "-map", "0:v", "-map", "1:a", "-map_metadata", "2", "-map_chapters", "2",
           "-af", af, "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest", "-movflags", "+faststart", tmp])
    os.replace(tmp, OUT)
    os.remove(raw)
    check(OUT)


def check(path):
    """The rules ETHGlobal's upload enforces: 2 to 4 minutes, at least 720p."""
    p = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=height,codec_type", "-of", "json", path],
                                  capture_output=True, text=True, check=True).stdout)
    d = float(p["format"]["duration"])
    h = max(s.get("height", 0) for s in p["streams"])
    ok = 120 <= d < 240 and h >= 720
    print(f"{path}: {d:.2f} s, {h}p -> {'OK for ETHGlobal' if ok else 'FAILS the 2-4 min / 720p rule'}")
    return ok


def test():
    """No speech is synthesised (that would be an AI voice): noise bursts stand in for the lines."""
    rows, total = timeline()
    lead = 1.37                                              # recording started a little before the prompter
    x = np.zeros(int((lead + PRE + total + 1) * SR), np.float32)
    bt = beep_track(PRE) * 0.2                               # heard faintly through the speakers
    x[int(lead * SR): int(lead * SR) + len(bt)] += bt
    rng = np.random.default_rng(1)
    edge = np.hanning(2 * int(0.01 * SR))                    # 10 ms fades, a spoken onset's (a full-length Hann bump
    for r in rows:                                           # crosses the onset level 250 ms late and fails the test)
        i = int((lead + PRE + r["t"]) * SR)
        n = int(min(1.5, r["budget"] - 0.2) * SR)
        w = np.ones(n)
        w[: len(edge) // 2], w[-(len(edge) // 2):] = edge[: len(edge) // 2], edge[len(edge) // 2:]
        x[i: i + n] += (rng.standard_normal(n) * 0.1 * w).astype(np.float32)
    x += (rng.standard_normal(len(x)) * 0.002).astype(np.float32)   # room noise
    sf.write("out/vo_test_recording.wav", x, SR)
    mix("out/vo_test_recording.wav")
    vo = sf.read("out/vo_aligned.wav")[0]
    env = np.convolve(np.abs(vo), np.ones(480) / 480, mode="same")
    errs = []
    for r in rows:
        i = int(r["t"] * SR)
        seg = env[max(0, i - SR // 2): i + SR // 2]
        on = np.argmax(seg > 0.02) + max(0, i - SR // 2)
        errs.append((on - i) / SR * 1000)
    print(f"alignment: {len(errs)} cues, worst error {max(abs(e) for e in errs):.1f} ms")
    assert max(abs(e) for e in errs) < 30, errs


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "script":
        script()
    elif cmd == "prompter":
        prompter()
    elif cmd == "mix":
        tr = int(sys.argv[sys.argv.index("--track") + 1]) if "--track" in sys.argv else None
        mix(sys.argv[2], tr)
    elif cmd == "test":
        test()
