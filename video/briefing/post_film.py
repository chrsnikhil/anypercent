"""The film (STORY.md): every segment, its grade and its sound, in one table, stitched by ffmpeg. Two cuts:

  python post_film.py [all]      the full film, picture, both soundtracks, both films:
                                   out/Any% Film v7 - ETHGlobal Mumbai.mp4                   (MW3 sound, private)
                                   out/Any% Film v7 - ETHGlobal Mumbai (original sound).mp4  (synthesised, public)
  CUT=sub python post_film.py    the ETHGlobal submission cut (under 4:00, no Part I, acts renumbered), original
                                 sound only, voice still to come (prep/mix_vo.py):
                                   out/Any% Submission v7 (no voice yet).mp4
  python post_film.py video | audio | mux     one step (sound changes need only audio + mux, seconds)

Problem acts get the warm MW3 grade, solution acts a cool one, both with an anamorphic streak; the assembly film keeps
its own finish (it is cut from its master). Each segment's sound is cut or padded to exactly its picture, then the whole
mix is loudness-normalised. Needs bash render_acts.sh, the older raws (title_open, dossier, title_end), the assembly
master "out/Any% Briefing - ETHGlobal Mumbai.mp4" (bash post.sh) and the sound (prep/make_mw3_audio.py)."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
CUT = os.environ.get("CUT", "full")
MASTER = {"full": "out/Any% Film v7 - ETHGlobal Mumbai.mp4", "sub": "out/Any% Submission v7 (no voice yet, MW3 sound).mp4"}[CUT]
ORIG = {"full": "out/Any% Film v7 - ETHGlobal Mumbai (original sound).mp4", "sub": "out/Any% Submission v7 (no voice yet).mp4"}[CUT]
ASM = "out/Any% Briefing - ETHGlobal Mumbai.mp4"
PROOF_S, PROOF_CUT = round(2160 * 1.2) / 60, 32.8                # Part IV, and its REJECTED -> seed cut (act f 1640)
BUILT = json.load(open(os.path.join(HERE, "src", "acts", "built.json"), encoding="utf-8"))
OBJ_S = (1510 + sum(round(c["seconds"] * 60) for c in BUILT["clips"])) / 60    # Objectives OBJ_LEN: grows by the field report

# (video, grade, (t0, t1) or None, seconds, sound (mw3 name, original name), gain dB[, transparent overlay])
SEG = [
    ("out/cold_raw.mov", "warm", None, 1200 / 60, ("cold_mw3", "cold_orig"), 0),
    ("out/teaser_raw.mov", "cool", None, 100 / 60, ("teaser_mw3", "teaser_orig"), 0),
    ("out/title_open_raw.mov", "warm", None, 2.5, ("title_open_mw3", "title_open_orig"), 0),
    ("out/primer_raw.mov", "warm", None, 12.0, ("primer_mw3", "primer_orig"), 0),
    ("out/ch1_raw.mov", "warm", None, 50 / 60, ("chapter_mw3", "chapter_orig"), -8),
    ("out/dossier_raw.mov", "warm", None, 50.0, ("dossier_audio_mw3", "dossier_audio"), 0),
    ("out/breaks_raw.mov", "warm", None, round(1340 * 1.25) / 60, ("breaks_mw3", "breaks_orig"), 0),
    ("out/ch3_raw.mov", "cool", None, 50 / 60, ("chapter_mw3", "chapter_orig"), -8),
    (ASM, None, (2.0, 33.5), 31.5, ("briefing_audio_mw3", "briefing_audio"), 0, "out/machine_subs.mov"),   # hero .. section
    ("out/reel_raw.mov", "warm", None, (70 + 5 * 480 + 240) / 60, ("reel_mw3", "reel_orig"), 0),               # the five games
    ("out/proof_raw.mov", "cool", (0, PROOF_CUT), PROOF_CUT, ("proof_mw3", "proof_orig"), 0),                  # .. REJECTED
    ("out/check_raw.mov", "cool", None, 570 / 60, ("check_mw3", "check_orig"), 0),                                # the real checker
    ("out/coach_raw.mov", "cool", None, 630 / 60, ("coach_mw3", "coach_orig"), 0),                                # PB, the coach
    ("out/proof_raw.mov", "cool", (PROOF_CUT, PROOF_S), PROOF_S - PROOF_CUT, ("proof_mw3", "proof_orig"), 0),     # seed ..
    ("out/obj_raw.mov", "cool", None, OBJ_S, ("objectives_mw3", "objectives_orig"), 0),
    ("out/handler_raw.mov", "cool", None, 540 / 60, ("handler_mw3", "handler_orig"), 0),                       # PB on the sponsor steps
    (ASM, None, (33.5, 41.0), 7.5, ("briefing_audio_mw3", "briefing_audio"), 0),     # panel swap .. flip
    ("out/coda_raw.mov", "warm", None, 8.0, ("coda_mw3", "coda_orig"), 0),
    ("out/title_end_raw.mov", "warm", None, 4.0, ("title_end_mw3", "title_end_orig"), 0),
]
# ETHGlobal: 2 to 4 minutes, at most ~20 s of backstory. So no dossier, and the acts renumbered (PART I is How records
# break); the problem is the cold open, the primer and Part I, then the product for the rest.
SEG_SUB = [
    ("out/cold_raw.mov", "warm", None, 1200 / 60, ("cold_mw3", "cold_orig"), 0),
    ("out/flash_raw.mov", "cool", None, 400 / 60, ("flash_mw3", "flash_orig"), 0),           # the mechanism by 0:27
    ("out/title_open_raw.mov", "warm", None, 2.5, ("title_open_mw3", "title_open_orig"), 0),
    ("out/primer_raw.mov", "warm", None, 12.0, ("primer_mw3", "primer_orig"), 0),
    ("out/breaks_sub_raw.mov", "warm", None, 1340 / 60, ("breaks_sub_mw3", "breaks_sub_orig"), 0),             # v3 pace
    ("out/ch2s_raw.mov", "cool", None, 50 / 60, ("chapter_mw3", "chapter_orig"), -8),
    (ASM, None, (2.0, 33.5), 31.5, ("briefing_audio_mw3", "briefing_audio"), 0, "out/machine_subs.mov"),
    ("out/reel_short_raw.mov", "warm", None, (70 + 5 * 240 + 240) / 60, ("reel_short_mw3", "reel_short_orig"), 0),  # 4 s a game
    ("out/proof_sub_raw.mov", "cool", (0, PROOF_CUT), PROOF_CUT, ("proof_mw3", "proof_orig"), 0),
    ("out/check_raw.mov", "cool", None, 570 / 60, ("check_mw3", "check_orig"), 0),
    ("out/coach_raw.mov", "cool", None, 630 / 60, ("coach_mw3", "coach_orig"), 0),
    ("out/proof_sub_raw.mov", "cool", (PROOF_CUT, PROOF_S), PROOF_S - PROOF_CUT, ("proof_mw3", "proof_orig"), 0),
    ("out/obj_sub_raw.mov", "cool", None, OBJ_S, ("objectives_mw3", "objectives_orig"), 0),
    ("out/handler_raw.mov", "cool", None, 540 / 60, ("handler_mw3", "handler_orig"), 0),                       # PB on the sponsor steps
    (ASM, None, (33.5, 41.0), 7.5, ("briefing_audio_mw3", "briefing_audio"), 0),
    ("out/coda_raw.mov", "warm", None, 8.0, ("coda_mw3", "coda_orig"), 0),
    ("out/title_end_raw.mov", "warm", None, 4.0, ("title_end_mw3", "title_end_orig"), 0),
]
CHAPTERS_SUB = ["Cold open", "Flash-forward", "Title", "What a speedrun is", "Part I: How records break", "Part II: The machine", None,
                "The games", "Part III: The proof", "The check", "The coach", "The seed", "Part IV: Mumbai", "PB on the sponsor steps", "The plates", "Coda",
                "End title"]
# FIELD TAPE (src/acts/FieldTape.tsx): real camera footage of the console, if someone has filmed it (public/field/device.mp4,
# rendered to out/field_raw.mov). It goes after the machine, with the clip's own sound; 10 s keeps the cut under 4:00.
FIELD, FIELD_AUDIO = "out/field_raw.mov", "out/field_audio.wav"
FIELD_AT = 7 if os.path.exists(FIELD) else None
if FIELD_AT is not None:
    SEG_SUB.insert(FIELD_AT, (FIELD, "warm", None, 10.0, ("field_audio", "field_audio"), 0))
    CHAPTERS_SUB.insert(FIELD_AT, "Field tape")
    if not os.path.exists(FIELD_AUDIO):                   # the clip's own sound, or silence if it has none
        src = "public/field/device.mp4"
        has = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", src],
                             capture_output=True, text=True).stdout.strip()
        inp = ["-i", src, "-map", "0:a:0"] if has else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        subprocess.run(["ffmpeg", "-v", "error", "-y"] + inp + ["-t", "10", "-ac", "2", "-ar", "48000", "-c:a", "pcm_f32le", FIELD_AUDIO], check=True)
# PB ON THE SPONSOR STEPS (Handler.tsx, mock-drawn screens) fills the room under 4:00 until real footage needs it: once the
# field tape or the field report's clips would take the cut past 4:00, the submission drops it (the director's cut keeps it).
SUB_LIMIT = 240.0
HANDLER_IN_SUB = sum(s[3] for s in SEG_SUB) <= SUB_LIMIT
if not HANDLER_IN_SUB:
    _h = next(i for i, s in enumerate(SEG_SUB) if s[0] == "out/handler_raw.mov")
    del SEG_SUB[_h], CHAPTERS_SUB[_h]
if CUT == "sub" and sum(s[3] for s in SEG_SUB) > SUB_LIMIT:   # the field tape and the clips share ~11 s: say so, loudly
    print(f"WARNING: the submission runs {sum(s[3] for s in SEG_SUB):.1f} s, over 4:00: shorten the field report's clips "
          "(built.json seconds) or drop the field tape", file=sys.stderr)


def streak(i, r, g, b):
    return (f"[s{i}]colorlevels=rimin=0.72:gimin=0.72:bimin=0.72,gblur=sigma=70:sigmaV=0.6,"
            f"colorchannelmixer=rr={r}:gg={g}:bb={b},format=gbrp[k{i}]")


def grade(i, kind, trim=None):
    if kind == "warm":
        look = ("eq=saturation=0.88:contrast=1.06:gamma=1.04,colorbalance=rs=0.03:bs=-0.03:rh=0.02:bh=-0.02,rgbashift=rh=-2:bh=2,"
                "vignette=angle=PI/4.2,noise=alls=7:allf=t")
        glow, sk = (12, 0.16), (0.26, 0.19, 0.13)
    else:
        look = "eq=saturation=0.96:contrast=1.05:gamma=1.04,colorbalance=bs=0.025:rs=-0.01:rh=0.015,rgbashift=rh=-1:bh=1,vignette=angle=PI/4.4,noise=alls=6:allf=t"
        glow, sk = (10, 0.18), (0.15, 0.24, 0.34)
    cut = f"trim={trim[0]}:{trim[1]},setpts=PTS-STARTPTS," if trim else ""   # only with a window: the rest keep their cache
    return (f"[{i}:v]{cut}format=gbrp,split=3[a{i}][b{i}][s{i}];[b{i}]gblur=sigma={glow[0]},format=gbrp[g{i}];{streak(i, *sk)};"
            f"[a{i}][g{i}]blend=all_mode=screen:all_opacity={glow[1]}[h{i}];[h{i}][k{i}]blend=all_mode=screen,{look},"
            f"format=yuv420p,setsar=1,fps=60[v{i}]")


def video_part(i, seg, ov=None):
    """ov: the input index of a transparent overlay (narration) laid over this segment."""
    path, kind, trim, secs = seg[:4]
    if kind is None:
        base = f"[{i}:v]trim={trim[0]}:{trim[1]},setpts=PTS-STARTPTS,format=yuv420p,setsar=1,fps=60"
        if ov is None:
            return base + f"[v{i}]"
        return (base + f"[b{i}];[{ov}:v]setpts=PTS-STARTPTS,format=yuva444p10le[o{i}];"
                f"[b{i}][o{i}]overlay=0:0:format=auto:shortest=1,format=yuv420p,setsar=1,fps=60[v{i}]")
    return grade(i, kind, trim)


def audio_part(j, i, seg):
    """Input j is the sound; cut (for the assembly) or pad it to the segment's picture, exactly."""
    path, kind, trim, secs, names, gain = seg[:6]
    f = []
    if trim:
        f.append(f"atrim={trim[0]}:{trim[1]},asetpts=PTS-STARTPTS,afade=t=in:d=0.05,afade=t=out:st={trim[1] - trim[0] - 0.08:.3f}:d=0.08")
    if gain:
        f.append(f"volume={gain}dB")
    f.append(f"aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{secs:.6f},asetpts=PTS-STARTPTS")
    # hard cuts stay hard, but a sound cut mid-waveform clicks: 3 ms in, 12 ms out at every join
    f.append(f"afade=t=in:d=0.003,afade=t=out:st={secs - 0.012:.6f}:d=0.012")
    return f"[{j}:a]{','.join(f)}[a{i}]"


SUFFIX = "" if CUT == "full" else "_" + CUT
VIDEO = f"out/film_video{SUFFIX}.mp4"                        # the picture alone, so sound changes never re-encode it
AUDIO = {False: f"out/film_audio{SUFFIX}_mw3.wav", True: f"out/film_audio{SUFFIX}_orig.wav"}
SEGDIR = "out/segcache"           # shared by both cuts: a graded segment is named by a hash of everything that makes it


def run(args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-stats"] + args, check=True)


X264 = ["-r", "60", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-tune", "grain", "-maxrate", "45M", "-bufsize", "90M",
        "-pix_fmt", "yuv420p"]


def video():
    """Each segment is graded and encoded on its own (all of them in one graph runs out of memory) into out/segcache/,
    named by a hash of its input files (and their times), trim, length, grade and encoder settings, so both cuts share
    the segments they have in common and nothing is encoded twice; then the pieces are joined without re-encoding."""
    import hashlib
    os.makedirs(SEGDIR, exist_ok=True)
    names = []
    for i, s in enumerate(SEG):
        ov = s[6] if len(s) > 6 and s[6] else None
        graph = video_part(0, s, 1 if ov else None)
        key = json.dumps([s[0], os.path.getmtime(s[0]), ov, os.path.getmtime(ov) if ov else 0, s[2], round(s[3], 6), graph, X264])
        out = f"{SEGDIR}/{hashlib.sha1(key.encode()).hexdigest()[:16]}.mp4"
        names.append(os.path.basename(out))
        if os.path.exists(out):
            continue
        print("segment", i, s[0])
        args = ["-i", s[0]] + (["-i", ov] if ov else [])
        part = out.replace(".mp4", ".part.mp4")              # a crash never leaves a half segment under a done name
        run(args + ["-filter_complex", graph, "-map", "[v0]"] + X264 + ["-t", f"{s[3]:.6f}", "-an", part])   # never longer than its slot
        os.replace(part, out)
    lst = f"{SEGDIR}/list_{CUT}.txt"
    open(lst, "w").write("".join(f"file '{n}'\n" for n in names))
    tmp = VIDEO.replace(".mp4", ".part.mp4")
    run(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", tmp])
    os.replace(tmp, VIDEO)


def speaker_friendly(path):
    """For the original-sound mix: its synthesised beds put half their energy under 60 Hz, which phones and laptops
    cannot play. Saturate the lows into harmonics they can (psychoacoustic bass), and take some of the sub away."""
    import numpy as np
    import soundfile as sf
    from scipy.signal import butter, sosfilt, sosfiltfilt
    x, sr = sf.read(path, dtype="float64")
    band = lambda y, lo, hi: sosfilt(butter(2, [lo, hi], "band", fs=sr, output="sos"), y, axis=0)
    sub = sosfilt(butter(2, 90, "low", fs=sr, output="sos"), x, axis=0)
    g = 4.0 / (np.abs(sub).max() + 1e-9)
    harm = band(np.tanh(sub * g) / g, 110, 420)
    # zero-phase, so the subtraction cancels (a causal low-pass is ~70 degrees late at 41 Hz and would barely dent it):
    # about -13 dB at 41 Hz, -0.6 dB at 80 Hz
    deep = sosfiltfilt(butter(4, 60, "low", fs=sr, output="sos"), x, axis=0)
    x = x + 1.2 * harm - 0.8 * deep
    sf.write(path, x.astype(np.float32), sr, subtype="FLOAT")


def audio(orig):
    """Both soundtracks: each segment cut or padded to its picture, then a two-pass linear loudnorm (no pumping)."""
    n = len(SEG)
    args = []
    for s in SEG:
        args += ["-i", f"out/{s[4][1 if orig else 0]}.wav"]
    graph = ";".join(audio_part(i, i, s) for i, s in enumerate(SEG)) + ";" + "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]"
    raw = AUDIO[orig].replace(".wav", ".raw.wav")
    run(args + ["-filter_complex", graph, "-map", "[a]", "-c:a", "pcm_f32le", "-ar", "48000", raw])
    if orig:
        speaker_friendly(raw)
    target = "I=-16:TP=-1.0:LRA=20"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", raw, "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = json.loads(r.stderr[r.stderr.rindex("{"): r.stderr.rindex("}") + 1])
    af = (f"loudnorm={target}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
          f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")
    run(["-i", raw, "-af", af, "-c:a", "pcm_f32le", AUDIO[orig]])
    os.remove(raw)
    print(AUDIO[orig], "in", m["input_i"], "LUFS, LRA", m["input_lra"])


CHAPTERS = ["Cold open", "Flash-forward", "Title", "What a speedrun is", "Part I: The case files", None, "Part II: How records break",
            "Part III: The machine", None, "The games", "Part IV: The proof", "The check", "The coach", "The seed", "Part V: Mumbai",
            "PB on the sponsor steps", "The plates", "Coda", "End title"]
if CUT == "sub":
    SEG, CHAPTERS = SEG_SUB, CHAPTERS_SUB


def chapters():
    """Chapter marks for players and YouTube, from the segment table (a PART card belongs to the act it opens)."""
    t, marks = 0.0, []
    for seg, name in zip(SEG, CHAPTERS):
        if name:
            marks.append((t, name))
        t += seg[3]
    lines = [";FFMETADATA1", "title=Any% // ETHGlobal Mumbai '26"]
    for i, (a, n) in enumerate(marks):
        b = marks[i + 1][0] if i + 1 < len(marks) else t
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(a * 1000)}", f"END={int(b * 1000)}", f"title={n}"]
    open("out/chapters.txt", "w").write("\n".join(lines) + "\n")


def mux(orig):
    out = ORIG if orig else MASTER
    src = VIDEO if os.path.exists(VIDEO) else MASTER
    tmp = out.replace(".mp4", ".part.mp4")
    chapters()
    run(["-i", src, "-i", AUDIO[orig], "-i", "out/chapters.txt", "-map", "0:v", "-map", "1:a", "-map_metadata", "2", "-map_chapters", "2",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest", "-movflags", "+faststart", tmp])
    os.replace(tmp, out)
    print(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "compact", out],
                         capture_output=True, text=True).stdout.strip(), out)


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in ("all", "video"):
        video()
        print("expected", round(sum(s[3] for s in SEG), 3), "s")
    if step in ("all", "audio"):
        if CUT == "full":                                 # the submission is public: original sound only
            audio(False)
        audio(True)
    if step == "orig":
        audio(True)
    if step in ("all", "mux"):
        if CUT == "full":
            mux(False)
        mux(True)
    if step == "orig":
        mux(True)
