"""One sponsor demo (SPONSOR_DEMOS.md), under 2:00, finished exactly like the film (post_film.py's grades, sound joins,
speaker-friendly lows and two-pass loudness), from its own segment list:

  python scripts/heavy.py python post_sponsor.py arkiv|hedera|chainlink|world [all|video|audio|mux]

The cut is src/sponsors/<name>/cut.json, a list of segments:
  {"video": "out/title_open_raw.mov", "grade": "warm" | "cool" | null, "trim": [t0, t1] | null, "seconds": 2.5,
   "sound": "title_open_orig", "gain": 0, "overlay": null, "chapter": "Title"}
"sound" names out/<sound>.wav, and its trim follows the picture's. Original (synthesised) sound only: the demos are
public. A null grade means the clip is already finished (the assembly master) and is only cut. Graded segments share
the film's cache (out/segcache, named by a hash of everything that makes them).
Writes out/sponsors/Any% x <Sponsor> - ETHGlobal Mumbai.mp4."""
import hashlib
import json
import os
import subprocess
import sys

import post_film as P                                    # its grade/sound helpers; importing it only reads files

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = {"arkiv": "Arkiv", "hedera": "Hedera", "chainlink": "Chainlink", "world": "World"}
LIMIT = 120.0


def load(name):
    cut = json.load(open(os.path.join(HERE, "src", "sponsors", name, "cut.json"), encoding="utf-8"))
    seg = [(c["video"], c.get("grade"), tuple(c["trim"]) if c.get("trim") else None, float(c["seconds"]),
            (c["sound"], c["sound"]), c.get("gain", 0), c.get("overlay")) for c in cut]
    total = sum(s[3] for s in seg)
    if total >= LIMIT:
        sys.exit(f"{name}: the cut runs {total:.2f} s; a sponsor demo must stay under {LIMIT:.0f} s")
    for s in seg:
        for p in (s[0], f"out/{s[4][0]}.wav") + ((s[6],) if s[6] else ()):
            if not os.path.exists(p):
                sys.exit(f"{name}: missing {p}")
    return seg, [c.get("chapter") for c in cut], total


def video(name, seg):
    os.makedirs(P.SEGDIR, exist_ok=True)
    names = []
    for i, s in enumerate(seg):
        ov = s[6]
        graph = P.video_part(0, s, 1 if ov else None)
        key = json.dumps([s[0], os.path.getmtime(s[0]), ov, os.path.getmtime(ov) if ov else 0, s[2], round(s[3], 6), graph, P.X264])
        out = f"{P.SEGDIR}/{hashlib.sha1(key.encode()).hexdigest()[:16]}.mp4"
        names.append(os.path.basename(out))
        if os.path.exists(out):
            continue
        print("segment", i, s[0])
        part = out.replace(".mp4", ".part.mp4")
        P.run(["-i", s[0]] + (["-i", ov] if ov else []) + ["-filter_complex", graph, "-map", "[v0]"] + P.X264
              + ["-t", f"{s[3]:.6f}", "-an", part])
        os.replace(part, out)
    lst = f"{P.SEGDIR}/list_sponsor_{name}.txt"
    open(lst, "w").write("".join(f"file '{n}'\n" for n in names))
    dst = f"out/sponsors/{name}_video.mp4"
    P.run(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", dst + ".part.mp4"])
    os.replace(dst + ".part.mp4", dst)


def audio(name, seg):
    args = []
    for s in seg:
        args += ["-i", f"out/{s[4][0]}.wav"]
    n = len(seg)
    graph = ";".join(P.audio_part(i, i, s) for i, s in enumerate(seg)) + ";" + "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]"
    dst = f"out/sponsors/{name}_audio.wav"
    raw = dst.replace(".wav", ".raw.wav")
    P.run(args + ["-filter_complex", graph, "-map", "[a]", "-c:a", "pcm_f32le", "-ar", "48000", raw])
    P.speaker_friendly(raw)
    target = "I=-16:TP=-1.0:LRA=20"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", raw, "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = json.loads(r.stderr[r.stderr.rindex("{"): r.stderr.rindex("}") + 1])
    af = (f"loudnorm={target}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
          f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")
    P.run(["-i", raw, "-af", af, "-c:a", "pcm_f32le", dst])
    os.remove(raw)


def mux(name, seg, chapters, total):
    t, marks = 0.0, []
    for s, c in zip(seg, chapters):
        if c:
            marks.append((t, c))
        t += s[3]
    meta = [";FFMETADATA1", f"title=Any% x {NAMES[name]} // ETHGlobal Mumbai '26"]
    for i, (a, c) in enumerate(marks):
        b = marks[i + 1][0] if i + 1 < len(marks) else t
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(a * 1000)}", f"END={int(b * 1000)}", f"title={c}"]
    chap = f"out/sponsors/{name}_chapters.txt"
    open(chap, "w").write("\n".join(meta) + "\n")
    out = f"out/sponsors/Any% x {NAMES[name]} - ETHGlobal Mumbai.mp4"
    tmp = out.replace(".mp4", ".part.mp4")
    P.run(["-i", f"out/sponsors/{name}_video.mp4", "-i", f"out/sponsors/{name}_audio.wav", "-i", chap, "-map", "0:v", "-map", "1:a",
           "-map_metadata", "2", "-map_chapters", "2", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest",
           "-movflags", "+faststart", tmp])
    os.replace(tmp, out)
    print(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "compact", out],
                         capture_output=True, text=True).stdout.strip(), out, f"(cut: {total:.2f} s)")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in NAMES:
        sys.exit(__doc__)
    name, step = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "all")
    os.makedirs("out/sponsors", exist_ok=True)
    seg, chapters, total = load(name)
    if step in ("all", "video"):
        video(name, seg)
    if step in ("all", "audio"):
        audio(name, seg)
    if step in ("all", "mux"):
        mux(name, seg, chapters, total)
