"""Draw the Any% on-screen controls: a RetroArch input overlay for the 800x480 panel, GBA layout.

  python3 make_overlay.py [OUT_DIR]        (default: next to this script)

Writes gamepad.png (the art, 800x480, transparent where there is no control) and gamepad.cfg (one full-screen
overlay with normalized hitboxes). RetroArch draws the art at the launcher's input_overlay_opacity (0.45) and
presses a button for every finger inside its hitbox.

Layout: D-pad bottom left (a 3x3 grid of hitboxes: the corners press two directions, the middle nothing), A and B
bottom right (A further right and higher, as on a GBA), L and R in the top corners, Select and Start small at the
bottom centre. A GBA game fills x 40..759, so the controls sit over the 40 px side bars and the edges of the picture;
hitboxes are larger than the drawings so a finger that lands a little off still counts."""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 800, 480
SS = 4                                             # supersampling: draw at 4x, scale down (smooth edges)

DPAD = (80, 372)                                   # centre
DPAD_CELL = 48                                     # hitbox grid pitch; the arms are drawn DPAD_ARM wide
DPAD_ARM, DPAD_REACH = 44, 70                      # arm width, centre to arm end
BUTTON_A = (738, 318)
BUTTON_B = (660, 382)
BUTTON_R, BUTTON_HIT_R = 33, 44                    # drawn radius, hitbox radius
SHOULDER = (118, 42)                               # L / R tab size, drawn in the top corners
SHOULDER_HIT = (132, 58)
SELECT = (352, 460)
START = (448, 460)
PILL = (72, 24)
PILL_HIT = (88, 40)

FILL = (236, 238, 244, 225)
EDGE = (18, 20, 28, 210)
INK = (18, 20, 28, 255)
FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "launcher", "arca_launcher", "assets",
                    "fonts", "Outfit-Bold.ttf")


def hitboxes():
    """[(buttons, cx, cy, shape, rx, ry)] in panel pixels; rx, ry are half sizes (radii for "radial")."""
    x, y, c = DPAD[0], DPAD[1], DPAD_CELL
    half = c / 2
    out = []
    for row, v in ((-1, "up"), (0, None), (1, "down")):
        for col, h in ((-1, "left"), (0, None), (1, "right")):
            names = [n for n in (v, h) if n]
            if names:
                out.append(("|".join(names), x + col * c, y + row * c, "rect", half, half))
    out.append(("a", *BUTTON_A, "radial", BUTTON_HIT_R, BUTTON_HIT_R))
    out.append(("b", *BUTTON_B, "radial", BUTTON_HIT_R, BUTTON_HIT_R))
    sw, sh = SHOULDER_HIT
    out.append(("l", sw / 2, sh / 2, "rect", sw / 2, sh / 2))
    out.append(("r", W - sw / 2, sh / 2, "rect", sw / 2, sh / 2))
    pw, ph = PILL_HIT
    out.append(("select", *SELECT, "rect", pw / 2, min(ph / 2, H - SELECT[1])))
    out.append(("start", *START, "rect", pw / 2, min(ph / 2, H - START[1])))
    return out


def cfg_text():
    lines = ["# Any% on-screen controls (made by make_overlay.py; do not edit by hand)",
             "overlays = 1",
             'overlay0_overlay = "gamepad.png"',
             'overlay0_full_screen = "true"',
             'overlay0_normalized = "true"',
             f"overlay0_descs = {len(hitboxes())}"]
    for i, (names, cx, cy, shape, rx, ry) in enumerate(hitboxes()):
        lines.append(f'overlay0_desc{i} = "{names},{cx / W:.6f},{cy / H:.6f},{shape},{rx / W:.6f},{ry / H:.6f}"')
    return "\n".join(lines) + "\n"


def _font(size):
    try:
        return ImageFont.truetype(FONT, size * SS)
    except OSError:
        return ImageFont.load_default(size * SS)


def _s(*v):
    return [round(n * SS) for n in v]


def _label(d, xy, text, size):
    d.text(_s(*xy), text, font=_font(size), fill=INK, anchor="mm")


def _arrow(d, cx, cy, dx, dy):
    """A small solid triangle pointing (dx, dy) in the middle of a D-pad arm."""
    tip = (cx + dx * 9, cy + dy * 9)
    base = [(cx - dx * 5 + dy * 8, cy - dy * 5 + dx * 8), (cx - dx * 5 - dy * 8, cy - dy * 5 - dx * 8)]
    d.polygon([tuple(_s(*p)) for p in (tip, *base)], fill=INK)


def draw():
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    edge = 2 * SS
    # D-pad: a cross of two rounded bars, an arrow in each arm
    x, y, a, r = DPAD[0], DPAD[1], DPAD_ARM / 2, DPAD_REACH
    for box in ((x - r, y - a, x + r, y + a), (x - a, y - r, x + a, y + r)):
        d.rounded_rectangle(_s(*box), radius=8 * SS, fill=EDGE)
    for box in ((x - r + 2, y - a + 2, x + r - 2, y + a - 2), (x - a + 2, y - r + 2, x + a - 2, y + r - 2)):
        d.rounded_rectangle(_s(*box), radius=6 * SS, fill=FILL)
    d.ellipse(_s(x - 9, y - 9, x + 9, y + 9), outline=EDGE, width=edge)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        _arrow(d, x + dx * (r - 20), y + dy * (r - 20), dx, dy)
    # A and B
    for (bx, by), name in ((BUTTON_A, "A"), (BUTTON_B, "B")):
        d.ellipse(_s(bx - BUTTON_R, by - BUTTON_R, bx + BUTTON_R, by + BUTTON_R), fill=FILL, outline=EDGE, width=edge)
        _label(d, (bx, by + 1), name, 26)
    # L and R: tabs in the top corners, square against the screen edges
    sw, sh = SHOULDER
    for box, name in (((-20, -20, sw, sh), "L"), ((W - sw, -20, W + 20, sh), "R")):   # off-screen corners square
        d.rounded_rectangle(_s(*box), radius=16 * SS, fill=FILL, outline=EDGE, width=edge)
        _label(d, ((max(0, box[0]) + min(W, box[2])) / 2, sh / 2 - 1), name, 22)
    # Select and Start
    pw, ph = PILL
    for (px, py), name in ((SELECT, "SELECT"), (START, "START")):
        d.rounded_rectangle(_s(px - pw / 2, py - ph / 2, px + pw / 2, py + ph / 2), radius=ph / 2 * SS, fill=FILL,
                            outline=EDGE, width=edge)
        _label(d, (px, py + 1), name, 12)
    return img.resize((W, H), Image.LANCZOS)


def write(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    draw().save(os.path.join(out_dir, "gamepad.png"), optimize=True)
    with open(os.path.join(out_dir, "gamepad.cfg"), "w", newline="\n") as f:
        f.write(cfg_text())


if __name__ == "__main__":
    write(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)))
