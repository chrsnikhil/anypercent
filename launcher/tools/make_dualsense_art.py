"""Draw the DualSense line art for Settings > Controller: arca_launcher/assets/dualsense.png (white on transparent,
drawn 4x and scaled down for smooth edges) and dualsense.json (where each button sits in the picture, 0..1).

Drawn here rather than taken from Sony's artwork or a product photo: a top-down outline in the launcher's style.

  python launcher/tools/make_dualsense_art.py"""
import json
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "arca_launcher", "assets")
DW, DH = 1000, 640                      # design space
OUT_W = 375                             # final width on the 800 x 480 screen
SS = 4                                  # supersampling
K = OUT_W * SS / DW                     # design -> drawing pixels
LINE = (255, 255, 255, 215)
FAINT = (255, 255, 255, 26)

BODY = [(200, 150), (262, 112), (380, 98), (500, 101), (620, 98), (738, 112), (800, 150), (850, 230), (885, 330),
        (915, 450), (930, 540), (905, 600), (850, 620), (790, 590), (740, 520), (690, 455), (620, 430), (500, 425),
        (380, 430), (310, 455), (260, 520), (210, 590), (150, 620), (95, 600), (70, 540), (85, 450), (115, 330),
        (150, 230)]
L1 = [(198, 146), (226, 96), (310, 68), (398, 66), (410, 86), (300, 104), (236, 136)]
ANCHORS = {
    "touchpad": (500, 160), "l1": (300, 80), "r1": (700, 80), "create": (320, 144), "options": (680, 144),
    "dpad": (240, 260), "lstick": (370, 380), "rstick": (630, 380), "triangle": (760, 205), "circle": (815, 260),
    "cross": (760, 315), "square": (705, 260), "ps": (500, 372),
}


def spline(points, closed=True, steps=14):
    """Catmull-Rom through the points: a smooth outline."""
    pts, out, n = points, [], len(points)
    for i in range(n if closed else n - 1):
        p0, p1, p2, p3 = pts[(i - 1) % n], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    return out


def sc(pts):
    return [(x * K, y * K) for x, y in pts]


def main():
    W, H = round(DW * K), round(DH * K)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lw = round(2.1 * SS)

    def outline(pts, fill=FAINT, width=lw):
        d.polygon(sc(pts), fill=fill)
        d.line(sc(pts) + sc(pts[:1]), fill=LINE, width=width, joint="curve")

    def rrect(x0, y0, x1, y1, r, fill=FAINT, width=lw):
        d.rounded_rectangle([x0 * K, y0 * K, x1 * K, y1 * K], radius=r * K, fill=fill, outline=LINE, width=width)

    def circle(cx, cy, r, fill=FAINT, width=lw):
        d.ellipse([(cx - r) * K, (cy - r) * K, (cx + r) * K, (cy + r) * K], fill=fill, outline=LINE, width=width)

    # shoulder buttons sit behind the body's top edge
    outline(spline(L1))
    outline(spline([(DW - x, y) for x, y in L1]))
    outline(spline(BODY), fill=(255, 255, 255, 18))
    # touchpad with the light bar strips down its sides
    rrect(362, 110, 638, 282, 30)
    for x in (352, 648):
        d.line(sc([(x, 128), (x, 262)]), fill=(255, 255, 255, 120), width=round(1.4 * SS))
    # Create and Options
    rrect(306, 126, 334, 162, 9)
    rrect(666, 126, 694, 162, 9)
    # D-pad
    for x0, y0, x1, y1 in ((222, 198, 258, 244), (222, 276, 258, 322), (170, 242, 216, 278), (264, 242, 310, 278)):
        rrect(x0, y0, x1, y1, 9, fill=(255, 255, 255, 40))
    # face buttons with their marks
    sym = round(1.8 * SS)
    for (cx, cy), mark in zip(((760, 205), (815, 260), (760, 315), (705, 260)), ("triangle", "circle", "cross", "square")):
        circle(cx, cy, 25, fill=(255, 255, 255, 40))
        if mark == "triangle":
            d.polygon(sc([(cx, cy - 11), (cx + 11, cy + 8), (cx - 11, cy + 8)]), outline=LINE, width=sym)
        elif mark == "circle":
            d.ellipse([(cx - 10) * K, (cy - 10) * K, (cx + 10) * K, (cy + 10) * K], outline=LINE, width=sym)
        elif mark == "cross":
            d.line(sc([(cx - 9, cy - 9), (cx + 9, cy + 9)]), fill=LINE, width=sym)
            d.line(sc([(cx - 9, cy + 9), (cx + 9, cy - 9)]), fill=LINE, width=sym)
        else:
            d.rectangle([(cx - 9) * K, (cy - 9) * K, (cx + 9) * K, (cy + 9) * K], outline=LINE, width=sym)
    # sticks
    for cx in (370, 630):
        circle(cx, 380, 50)
        circle(cx, 380, 36, fill=(255, 255, 255, 46))
    # PS button and the mute button under it
    circle(500, 372, 17, fill=(255, 255, 255, 50))
    rrect(484, 404, 516, 420, 8)
    img = img.resize((OUT_W, round(DH * OUT_W / DW)), Image.LANCZOS)
    os.makedirs(ASSETS, exist_ok=True)
    img.save(os.path.join(ASSETS, "dualsense.png"))
    with open(os.path.join(ASSETS, "dualsense.json"), "w", encoding="utf-8") as fh:
        json.dump({k: [round(x / DW, 4), round(y / DH, 4)] for k, (x, y) in ANCHORS.items()}, fh, indent=1)
    print(os.path.join(ASSETS, "dualsense.png"), img.size)


if __name__ == "__main__":
    main()
