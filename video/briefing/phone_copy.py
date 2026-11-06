"""Phone copies of a cut, each under 30 MiB (what a chat app or SendUserFile takes): 720p60, split at the chapter marks
nearest to equal parts of at most ~110 s, two-pass at a fixed bitrate.

  python phone_copy.py SRC NAME     e.g. python phone_copy.py "out/Any% Submission v7 (no voice yet).mp4" "Any% Submission v7"
                                    -> out/<NAME> (part N of M, phone 720p).mp4"""
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
SRC, NAME = sys.argv[1], sys.argv[2]
PART_MAX = 110.0                                     # seconds: 1750k video + 128k audio stays near 26 MiB
VF = "hqdn3d=1.5:1.5:6:6,scale=1280:720:flags=lanczos"
X264 = ["-c:v", "libx264", "-preset", "slow", "-b:v", "1750k", "-maxrate", "2300k", "-bufsize", "3600k", "-r", "60", "-pix_fmt", "yuv420p"]

probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-show_entries", "format=duration", "-of", "json", SRC],
                                  capture_output=True, text=True, check=True).stdout)
dur = float(probe["format"]["duration"])
marks = [float(c["start_time"]) for c in probe.get("chapters", [])][1:]
n = math.ceil(dur / PART_MAX)
cuts = []
for k in range(1, n):                                # the chapter mark nearest each equal split
    want = dur * k / n
    cuts.append(min(marks, key=lambda m: abs(m - want)) if marks else want)
bounds = [0.0] + sorted(set(cuts)) + [dur]
for i in range(len(bounds) - 1):
    a, b = bounds[i], bounds[i + 1]
    out = f"out/{NAME} (part {i + 1} of {len(bounds) - 1}, phone 720p).mp4"
    log = f"out/phone_pass_{i}"
    base = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", SRC, "-vf", VF] + X264
    subprocess.run(base + ["-pass", "1", "-passlogfile", log, "-an", "-f", "mp4", os.devnull], check=True)
    subprocess.run(base + ["-pass", "2", "-passlogfile", log, "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out], check=True)
    for f in os.listdir("out"):
        if f.startswith(f"phone_pass_{i}"):
            os.remove(os.path.join("out", f))
    print(f"{out}: {a:.1f}-{b:.1f} s, {os.path.getsize(out) / 2**20:.1f} MiB")
