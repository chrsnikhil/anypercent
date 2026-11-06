"""
Any% build guide: one self-contained HTML page with the assembly in 3D, step by step, and
every wire routed in 3D from its switch or part to its pin on the Pi's GPIO header.

  python cad2/make_build_guide.py            -> Any% Build Guide.html (repo root)

Geometry: cad2/viewer_cache/asm (prep_viewer_meshes.py). Order and part motion:
cad2/assembly_steps.json. Switch positions are measured from the assembly meshes; the
Pi header, audio jack and Pico-free wiring follow enclosure.scad's placement constants.
"""
import base64
import gzip
import json
import math
import os

import numpy as np
import trimesh

CAD2 = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CAD2)
ASM = os.path.join(CAD2, "stl_assembly")
CACHE = os.path.join(CAD2, "viewer_cache", "asm")
OUT = os.path.join(ROOT, "Any% Build Guide.html")

# ------------------------------------------------------------------ parts
# name: (colour, alpha, label, step it arrives, move dir, distance)
PARTS = {
    "asm_front_shell":       ("#16181b", 0.30, "Front shell", 0, None, 0),
    "asm_inserts":           ("#C9A24A", 1, "M3 heat-set inserts (8)", 1, (0, 0, -1), 25),
    "asm_cap_a":             ("#E4572E", 1, "A button", 2, (0, 0, -1), 30),
    "asm_cap_b":             ("#E4572E", 1, "B button", 2, (0, 0, -1), 30),
    "asm_cap_x":             ("#5F646B", 1, "X button", 2, (0, 0, -1), 30),
    "asm_cap_y":             ("#5F646B", 1, "Y button", 2, (0, 0, -1), 30),
    "asm_cap_pills":         ("#C9CCD1", 1, "START / SELECT", 2, (0, 0, -1), 30),
    "asm_cap_dpad":          ("#26282C", 1, "D-pad", 2, (0, 0, -1), 30),
    "asm_plate_face":        ("#6E747C", 1, "Switch plate, ABXY", 3, (0, 0, -1), 30),
    "asm_plate_dpad":        ("#6E747C", 1, "Switch plate, D-pad", 3, (0, 0, -1), 30),
    "asm_plate_pills":       ("#6E747C", 1, "Switch plate, START/SELECT", 3, (0, 0, -1), 30),
    "asm_switches_plates":   ("#2E3035", 1, "Tactile switches (10)", 3, (0, 0, -1), 30),
    "asm_screws_plates":     ("#B8BCC2", 1, "M3x8 plate screws (6)", 3, (0, 0, -1), 30),
    "asm_screw_pivot":       ("#B8BCC2", 1, "M3x8 D-pad pivot", 4, (0, 0, -1), 30),
    "asm_shoulders":         ("#26282C", 1, "Shoulder paddles", 5, (0, -1, 0), 25),
    "asm_pins":              ("#E8D9A8", 1, "Paddle pins, 1.75 filament", 5, (0, 0, -1), 25),
    "asm_switches_shoulder": ("#2E3035", 1, "Shoulder switches (2)", 5, (0, 0, -1), 25),
    "asm_display":           ("#1A1E25", 1, "Waveshare 5in DSI display", 6, (0, 0, -1), 30),
    "asm_spacers":           ("#7C828A", 1, "Display spacer pucks (4)", 6, (0, 0, -1), 30),
    "asm_speaker":           ("#1B1B1B", 1, "FIT0502 speaker", 7, (0, 0, -1), 30),
    "asm_pi_board":          ("#2F6F3F", 1, "Raspberry Pi 3B+", 8, (0, 0, -1), 30),
    "asm_pi_parts":          ("#A3A8AE", 1, "Pi 3B+ connectors", 8, (0, 0, -1), 30),
    "asm_heatsinks":         ("#4F86C6", 1, "Heatsinks", 8, (0, 0, -1), 30),
    "asm_bay_tray":          ("#5A6068", 1, "Bay tray", 9, (0, 0, -1), 30),
    "asm_rear_frame":        ("#3F444B", 1, "Rear frame", 10, (0, 0, -1), 40),
    "asm_pam":               ("#1E4FAA", 1, "PAM8403 amp", 10, (0, 0, -1), 40),
    "asm_magnets_frame":     ("#A9AEB5", 1, "Frame magnets (6)", 10, (0, 0, -1), 40),
    "asm_screws_frame":      ("#B8BCC2", 1, "M3x8 frame screws (8)", 10, (0, 0, -1), 30),
    "asm_panel_world_body":  ("#F9F9F8", 1, "World panel", 11, (0, 0, -1), 40),
    "asm_panel_world_logo":  ("#181818", 1, "World emblem", 11, (0, 0, -1), 40),
    "asm_magnets_panel":     ("#A9AEB5", 1, "Panel magnets (6)", 11, (0, 0, -1), 40),
    "asm_bank":              ("#D8DADE", 1, "Power bank", 12, (0, -1, 0), 80),
}

# ------------------------------------------------------------ Pi geometry
PI_X0, PI_Y0 = 5.91, 34.12          # enclosure.scad pi_x0 / pi_y0 (board bx -> +y, by -> -x)
HEADER_TIP_Z = 15.6 + 1.6 + 8.5     # Pi front face + PCB + pin height


def pin_xyz(n):
    """World position of GPIO header pin n's tip. Pin 1 is nearest the microSD end."""
    bx = 8.33 + ((n - 1) // 2) * 2.54
    by = 4.81 if n % 2 else 2.27
    return (PI_X0 + 56 - by, PI_Y0 + bx, HEADER_TIP_Z)


# button: (BCM GPIO, header pin, key, wire colour in the 3D view)
BUTTONS = {
    "UP":     (17, 11, "Up arrow",   "#F2C94C"), "DOWN":  (27, 13, "Down arrow",  "#E0B43A"),
    "LEFT":   (22, 15, "Left arrow", "#D9A62E"), "RIGHT": (23, 16, "Right arrow", "#C9971F"),
    "A":      (5, 29, "X key",       "#FF7A45"), "B":     (6, 31, "Z key",       "#F2994A"),
    "X":      (24, 18, "F1 (menu)",  "#9B8CFF"), "Y":     (25, 22, "Esc (exit)", "#B7A6FF"),
    "START":  (26, 37, "Enter",      "#56CCF2"), "SELECT": (16, 36, "Backspace", "#2DB5E0"),
    "L":      (20, 38, "A key",      "#6FCF97"), "R":     (21, 40, "S key",      "#3FB77A"),
}
GND_PIN = 39


def switch_positions():
    """Centre of each tactile switch, matched to its button from the cap positions."""
    out = {}
    for fname, zb in (("asm_switches_plates", 12.6), ("asm_switches_shoulder", 11.0)):
        m = trimesh.load(os.path.join(ASM, fname + ".stl"))
        cl = []
        for p in m.split(only_watertight=False):
            c = p.bounds.mean(0)
            for g in cl:
                if np.linalg.norm(g[0][:2] - c[:2]) < 5:
                    g[1].append(p.bounds)
                    break
            else:
                cl.append([c, [p.bounds]])
        for _, bs in cl:
            b = np.array(bs)
            ctr = (b[:, 0].min(0) + b[:, 1].max(0)) / 2
            out[(round(float(ctr[0]), 1), round(float(ctr[1]), 1))] = zb
    caps = {k: trimesh.load(os.path.join(ASM, f"asm_cap_{k.lower()}.stl")).bounds.mean(0)[:2] for k in "ABXY"}
    sw = {}
    for (x, y), zb in out.items():
        if y > 105:
            sw["L" if x > 101 else "R"] = (x, y, zb)
        elif y < 40:
            sw["SELECT" if x > 101 else "START"] = (x, y, zb)
        elif x < 60:
            k = min(caps, key=lambda c: np.hypot(*(caps[c] - (x, y))))
            sw[k] = (x, y, zb)
        else:
            dx, dy = x - 181.5, y - 82.0
            sw[("UP" if dy > 0 else "DOWN") if abs(dy) > abs(dx) else ("LEFT" if dx > 0 else "RIGHT")] = (x, y, zb)
    assert sorted(sw) == sorted(BUTTONS), sorted(sw)
    return sw


def length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def cut_length(pts):
    return int(math.ceil((length(pts) + 50) / 10.0) * 10)      # +50 mm for strip, solder and slack


def wires():
    sw = switch_positions()
    out = []
    order = ["R", "X", "Y", "A", "B", "START", "SELECT", "RIGHT", "DOWN", "UP", "LEFT", "L"]
    for lane, name in enumerate(order):
        x, y, zb = sw[name]
        gpio, pin, _, colour = BUTTONS[name]
        px, py, pz = pin_xyz(pin)
        zr = 13.2 + (lane % 4) * 0.8
        ybus = 30.5 - (lane // 4) * 0.9 - (lane % 4) * 0.3
        xc = 63.0 + (lane % 6) * 0.5
        pts = [(x, y, zb), (x, y, zr)]
        if name == "R":
            pts += [(3.8, y, zr), (3.8, ybus, zr)]
        elif name == "L":
            pts += [(197.0, y, zr), (197.0, ybus, zr)]
        else:
            pts += [(x + (lane % 3) * 0.6, ybus, zr)]
            pts[-2] = (x + (lane % 3) * 0.6, y, zr)
        pts += [(xc, ybus, zr), (xc, ybus, 27.6 + (lane % 4) * 0.6), (xc, py, 27.6 + (lane % 4) * 0.6),
                (px, py, pz + 0.8), (px, py, pz)]
        step = 5 if name in ("L", "R") else 3
        out.append({"id": f"btn-{name}", "label": f"{name} to GPIO {gpio} (pin {pin})", "colour": colour,
                    "step": step, "group": "buttons", "pts": pts, "cut": cut_length(pts)})
    # ground: one wire daisy-chained through every switch, then to pin 39
    g = []
    for name in ["R", "X", "A", "B", "Y"]:
        x, y, zb = sw[name]
        g += [(x + 2.2, y - 2.2, zb + 0.4)]
    g += [(sw["B"][0] + 2.2, 29.0, 14.0)]
    for name in ["START", "SELECT"]:
        x, y, zb = sw[name]
        g += [(x + 2.2, 29.0, 14.0), (x + 2.2, y - 2.2, zb + 0.4), (x + 2.2, 29.0, 14.0)]
    for name in ["DOWN", "RIGHT", "UP", "LEFT"]:
        x, y, zb = sw[name]
        g += [(x + 2.2, y - 2.2, zb + 0.4)]
    x, y, zb = sw["L"]
    g += [(x + 2.2, y - 2.2, zb + 0.4), (198.0, y - 2.2, 14.0), (198.0, 27.0, 14.0),
          (62.6, 27.0, 14.0), (62.6, 27.0, 29.0)]
    px, py, pz = pin_xyz(GND_PIN)
    g += [(62.6, py, 29.0), (px, py, pz + 0.8), (px, py, pz)]
    # the shoulder switch R starts the chain: reach it from X
    out.append({"id": "gnd", "label": "Ground: every switch to GND (pin 39)", "colour": "#1b1d20",
                "step": 3, "group": "buttons", "pts": g, "cut": cut_length(g), "gnd": True})

    # audio: jack legs under the Pi -> PAM8403 input
    jx, jy = PI_X0 + 5.0, PI_Y0 + 53.53
    for i, (nm, col) in enumerate((("L", "#EB5757"), ("GND", "#1b1d20"), ("R", "#F2F2F2"))):
        y0 = jy - 3 + i * 3
        pts = [(jx, y0, 15.2), (3.5 - i * 0.5, y0, 15.2), (3.5 - i * 0.5, y0, 37.6),
               (3.5 - i * 0.5, 37.2 + i * 0.6, 37.6), (186.0 + i * 0.8, 37.2 + i * 0.6, 37.6),
               (186.0 + i * 0.8, 89.0 + i * 1.6, 37.6), (179.0, 89.0 + i * 1.6, 37.2)]
        out.append({"id": f"aud-{nm}", "label": f"Audio {nm}: jack leg to PAM8403 input {nm if nm != 'GND' else 'G'}",
                    "colour": col, "step": 8, "group": "audio", "pts": pts, "cut": cut_length(pts), "gnd": nm == "GND"})
    # amp power from header pin 4 (5 V) and pin 14 (GND)
    for i, (pin, nm, col) in enumerate(((4, "5V", "#EB5757"), (14, "GND", "#1b1d20"))):
        px, py, pz = pin_xyz(pin)
        pts = [(px, py, pz), (px, py, pz + 1.2), (64.4 + i * 0.6, py, 30.0), (64.4 + i * 0.6, 39.0 + i * 0.6, 30.0),
               (64.4 + i * 0.6, 39.0 + i * 0.6, 37.6), (190.0 + i * 0.8, 39.0 + i * 0.6, 37.6),
               (190.0 + i * 0.8, 104.0, 37.6), (185.0 + i * 2, 105.0, 37.2)]
        out.append({"id": f"amp-{nm}", "label": f"Amp power {nm}: header pin {pin} to PAM8403 {'+' if nm == '5V' else '-'}",
                    "colour": col, "step": 10, "group": "audio", "pts": pts, "cut": cut_length(pts), "gnd": nm == "GND"})
    # amp outputs -> speaker (its own lead)
    for i, (nm, col) in enumerate((("L+", "#EB5757"), ("L-", "#6b6f76"), ("R+", "#EB5757"), ("R-", "#6b6f76"))):
        pts = [(95.0 + i * 3, 35.0, 24.0), (95.0 + i * 3, 36.2, 24.0), (95.0 + i * 3, 36.2 + i * 0.2, 36.8),
               (193.5 + i * 0.7, 36.2 + i * 0.2, 36.8), (193.5 + i * 0.7, 98.0, 36.8), (196.0, 98.0 + i * 1.8, 37.2)]
        out.append({"id": f"spk-{nm}", "label": f"Speaker {nm}: PAM8403 output to speaker lead",
                    "colour": col, "step": 10, "group": "audio", "pts": pts, "cut": 0})
    # power: bank Type-C lead (cut cable) -> pin 2 (5 V) and pin 6 (GND)
    for i, (pin, nm, col) in enumerate(((2, "5V", "#EB5757"), (6, "GND", "#1b1d20"))):
        px, py, pz = pin_xyz(pin)
        pts = [(68.5, 64.0 + i * 1.2, 29.0), (65.6 + i * 0.5, 64.0 + i * 1.2, 29.0), (65.6 + i * 0.5, py, 29.0),
               (px, py, pz + 1.2), (px, py, pz)]
        out.append({"id": f"pwr-{nm}", "label": f"Power {nm}: power bank lead to header pin {pin}",
                    "colour": col, "step": 10, "group": "power", "pts": pts, "cut": 0, "gnd": nm == "GND"})
    return out, sw


def mesh_blob(name):
    raw = open(os.path.join(CACHE, name + ".stl"), "rb").read()
    return base64.b64encode(gzip.compress(raw, 9)).decode()


def pins_table():
    used = {2: ("5V in (power bank +)", "pwr"), 4: ("5V out to amp +", "pwr"), 6: ("GND (power bank -)", "gnd"),
            14: ("GND to amp -", "gnd"), GND_PIN: ("GND, all buttons", "gnd")}
    for name, (gpio, pin, key, col) in BUTTONS.items():
        used[pin] = (f"{name} (GPIO {gpio})", "btn")
    std = {1: "3V3", 17: "3V3", 2: "5V", 4: "5V", 6: "GND", 9: "GND", 14: "GND", 20: "GND", 25: "GND",
           30: "GND", 34: "GND", 39: "GND", 27: "ID_SD", 28: "ID_SC"}
    return {"used": used, "std": std}


from build_guide_content import STEPS, HTML   # noqa: E402  (page text and template)
from build_guide_wiring import wiring_items    # noqa: E402


def main():
    wl, sw = wires()
    labels = {name: [x, y, zb + 1.5] for name, (x, y, zb) in sw.items()}
    data = {
        "parts": [{"name": n, "colour": c, "alpha": a, "label": l, "step": s, "dir": d, "dist": dist,
                   "blob": mesh_blob(n)} for n, (c, a, l, s, d, dist) in PARTS.items()],
        "wires": wl,
        "labels": labels,
        "pins": {str(n): [*pin_xyz(n)] for n in range(1, 41)},
        "pintable": pins_table(),
        "buttons": {k: {"gpio": g, "pin": p, "key": key, "colour": c,
                        "cut": next(w["cut"] for w in wl if w["id"] == f"btn-{k}")}
                    for k, (g, p, key, c) in BUTTONS.items()},
        "gndcut": next(w["cut"] for w in wl if w["id"] == "gnd"),
        "audiocut": {w["id"]: w["cut"] for w in wl if w["cut"] and w["group"] == "audio"},
        "steps": STEPS,
        "wiring": wiring_items(wl, BUTTONS),
    }
    html = HTML.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(OUT, f"{os.path.getsize(OUT) / 1048576:.1f} MB")
    for w in wl:
        if w["cut"]:
            print(f"  {w['id']:10s} route {length(w['pts']):5.0f} mm  cut {w['cut']} mm")


if __name__ == "__main__":
    main()
