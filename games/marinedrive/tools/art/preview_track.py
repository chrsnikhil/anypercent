"""Layout preview: tests/out/track_layout.png (road/curb/slow/wall at 1/2 scale) and the layout checks."""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import track_geom as G  # noqa: E402

pts, total = G.centre_line()
print("length %.0f px, %d points, min radius %.0f" % (total, len(pts), G.min_radius(pts)))
r = G.radii(pts)
for i in np.argsort(r)[:40:8]:
    print("radius %.0f at %s" % (r[i], pts[i].round()))
for p in G.check(pts, total):
    print("PROBLEM:", p)
S = 2
c = (np.arange(G.MAP // S) * S + S / 2).astype(np.float32)
xx, yy = np.meshgrid(c, c)
idx, dist, side = G.nearest(pts, np.stack([xx.ravel(), yy.ravel()], 1))
cls = G.classify(dist).reshape(G.MAP // S, G.MAP // S)
pal = np.array([(90, 90, 96), (220, 60, 60), (200, 180, 110), (30, 60, 110)], np.uint8)
img = pal[cls]
for i, (x, y) in enumerate(pts):
    if i % 10 == 0:
        img[int(y) // S, int(x) // S] = (255, 255, 0) if i else (0, 255, 0)
for i, (x, y) in enumerate(G.CONTROL):
    img[max(0, y // S - 1):y // S + 2, max(0, x // S - 1):x // S + 2] = (255, 255, 255)
out = os.path.join(os.path.dirname(__file__), "..", "..", "tests", "out")
os.makedirs(out, exist_ok=True)
Image.fromarray(img).save(os.path.join(out, "track_layout.png"))
