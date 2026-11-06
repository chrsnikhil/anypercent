"""Master the final film's sound: two-pass EBU R128 loudnorm to -16 LUFS integrated, true peak -1 dBTP, linear (the
mix keeps its dynamics; the gain is one number), the picture copied untouched.

  python scripts/heavy.py python prep/final_master.py out/final_demo_raw.mp4 "../final/Any% - ETHGlobal Mumbai.mp4"

The soundtrack (public/final/audio/final_demo.wav) is already pre-mastered to about -16.1 LUFS; this pass only absorbs
what the race clip's game audio adds in scenes 1 and 20, and prints the result."""
import json
import re
import subprocess
import sys

FF = "ffmpeg"
src, dst = sys.argv[1], sys.argv[2]
TARGET = "I=-16:TP=-1.5:LRA=11"


def measure(path, extra=""):
    p = subprocess.run([FF, "-hide_banner", "-nostats", "-i", path, "-af", f"loudnorm={TARGET}{extra}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    return json.loads(re.findall(r"\{[^{}]*\}", p.stderr)[-1])


m = measure(src)
print(f"in:  {m['input_i']} LUFS, true peak {m['input_tp']} dBTP")
af = (f"loudnorm={TARGET}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
      f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")
subprocess.run([FF, "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-af", af,
                "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", dst], check=True)
o = measure(dst)
print(f"out: {o['input_i']} LUFS, true peak {o['input_tp']} dBTP -> {dst}")
