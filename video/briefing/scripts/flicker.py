"""Sharpness flicker check: per-frame Laplacian variance of a raw act render, flagging frames much softer (or sharper)
than both neighbours, the signature of a post pass that is wrong on alternate frames.

  python scripts/flicker.py cold proof ...      (reads out/<name>_raw.mov)"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 480, 270
for name in sys.argv[1:]:
    src = os.path.join(HERE, "..", "out", f"{name}_raw.mov")
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", f"scale={W}:{H},format=gray", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    sharp = []
    while True:
        b = p.stdout.read(W * H)
        if len(b) < W * H:
            break
        a = np.frombuffer(b, np.uint8).astype(np.float32)[: W * H].reshape(H, W)[20:-20]
        lap = a[1:-1, 1:-1] * 4 - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:]
        sharp.append(float(lap.var()))
    s = np.array(sharp)
    odd = [i for i in range(1, len(s) - 1)
           if s[i] > 5 and (s[i] < 0.6 * min(s[i - 1], s[i + 1]) or s[i] > 1.6 * max(s[i - 1], s[i + 1]))]
    print(f"{name}: {len(s)} frames, {len(odd)} odd ones out", odd[:30])
