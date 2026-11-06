"""Contact sheets of a finished cut, for review: one frame every STEP seconds, timestamped, 24 to a sheet.

  python scripts/review.py "out/Any% Film v5 - ETHGlobal Mumbai.mp4" [STEP]   -> out/review/sheet_NN.jpg"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

src = sys.argv[1]
step = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "review")
os.makedirs(out, exist_ok=True)
for f in os.listdir(out):
    os.remove(os.path.join(out, f))
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                           capture_output=True, text=True).stdout)
with tempfile.TemporaryDirectory() as tmp:
    subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps=1/{step},scale=480:270", os.path.join(tmp, "%04d.png")], check=True)
    frames = sorted(os.listdir(tmp))
    per = 24
    for s in range(0, len(frames), per):
        sheet = Image.new("RGB", (480 * 4, 270 * 6), "black")
        d = ImageDraw.Draw(sheet)
        for i, name in enumerate(frames[s:s + per]):
            x, y = (i % 4) * 480, (i // 4) * 270
            sheet.paste(Image.open(os.path.join(tmp, name)), (x, y))
            t = (s + i) * step
            d.rectangle([x, y, x + 64, y + 18], fill="black")
            d.text((x + 4, y + 3), f"{int(t // 60)}:{t % 60:04.1f}", fill=(255, 220, 0))
        sheet.save(os.path.join(out, f"sheet_{s // per:02d}.jpg"), quality=82)
print(f"{dur:.1f} s -> {len(frames)} frames in {out}")
