"""Wiring cards for the build guide: one per connection, in the order they are made."""

ROUTE_FACE = "down past the ABXY plate to the bottom edge, then along the bottom to the Pi's corner"
ROUTE_DPAD = "down past the D-pad plate to the bottom edge, then along the whole bottom edge to the Pi's corner"
ROUTE = {
    "A": ROUTE_FACE, "B": ROUTE_FACE, "X": ROUTE_FACE, "Y": ROUTE_FACE,
    "UP": ROUTE_DPAD, "DOWN": ROUTE_DPAD, "LEFT": ROUTE_DPAD, "RIGHT": ROUTE_DPAD,
    "START": "straight down into the bottom bundle, then along it to the Pi's corner",
    "SELECT": "straight down into the bottom bundle, then along it to the Pi's corner",
    "L": "down the right-hand wall (looking into the back) to the bottom edge, then along the bottom to the Pi's corner",
    "R": "down the left-hand wall (looking into the back) to the bottom edge, then to the Pi's corner",
}


def row(pin):
    return "inner row" if pin % 2 else "outer row"


def wiring_items(wl, buttons):
    by = {w["id"]: w for w in wl}
    items = []
    for name in ["UP", "DOWN", "LEFT", "RIGHT", "A", "B", "X", "Y", "START", "SELECT", "L", "R"]:
        gpio, pin, key, _ = buttons[name]
        w = by[f"btn-{name}"]
        step = "step 5" if name in ("L", "R") else "step 3"
        items.append({
            "wire": w["id"], "group": "Buttons", "title": f"{name} button",
            "from": f"{name} switch, one leg (any corner)", "to": f"Header pin {pin} ({row(pin)}), GPIO {gpio}",
            "fromTag": f"{name} switch", "toTag": f"pin {pin}", "pin": pin, "cut": f"{w['cut']} mm",
            "when": f"Switch end in {step}, pin end in step 8", "sends": key,
            "how": [f"Label both ends of a {w['cut']} mm wire \"{name}\".",
                    f"Solder it to one leg of the {name} switch. The ground chain goes on the leg diagonally opposite.",
                    f"Route it {ROUTE[name]}. Tape it into the bundle.",
                    f"In step 8, solder it onto header pin {pin} ({row(pin)}), low down, heatshrink over the joint."],
            "test": f"Meter on beep between this wire and the ground chain: it beeps only while {name} is pressed. "
                    f"After the button service is installed, its --test mode prints \"{name} down\" and \"{name} up\".",
            "diagrams": ["switch", "header"]})
    g = by["gnd"]
    items.append({
        "wire": "gnd", "group": "Buttons", "title": "Button ground chain",
        "from": "Every switch, the leg diagonal to its signal wire", "to": "Header pin 39 (inner row, last pin at the USB end)",
        "fromTag": "ground chain", "toTag": "pin 39", "pin": 39, "cut": f"about {g['cut']} mm in total",
        "when": "Steps 3 and 5, pin end in step 8", "sends": "0 V for all 12 buttons",
        "how": ["On each plate, run short jumpers from ground leg to ground leg: ABXY plate (4 switches), START/SELECT plate (2), D-pad plate (4).",
                "Link the plates with one wire each, and carry it on to both shoulder switches in step 5.",
                "Run the tail with the bundle to the Pi's corner.",
                "In step 8, solder the tail onto pin 39, the last inner-row pin at the USB end."],
        "test": "Meter on beep from the pin 39 wire to any switch's ground leg: it always beeps, without pressing anything.",
        "diagrams": ["switch", "header"]})
    for leg, colr, pad in (("L", "red", "L"), ("GND", "black", "G"), ("R", "white", "R")):
        w = by[f"aud-{leg}"]
        find = {"L": "beeps with the aux plug's tip", "R": "beeps with the aux plug's ring", "GND": "beeps with header pin 6"}[leg]
        items.append({
            "wire": w["id"], "group": "Audio", "title": f"Jack {leg} to amp input {pad}",
            "from": f"Pi 3.5 mm jack, {leg} leg (underside)", "to": f"PAM8403 input {pad}",
            "fromTag": f"jack {leg}", "toTag": f"amp IN {pad}", "pin": None, "cut": f"{w['cut']} mm",
            "when": "Jack end in step 8 (before the Pi goes in), amp end in step 10",
            "sends": {"L": "left audio", "R": "right audio", "GND": "audio ground"}[leg],
            "how": [f"Plug an aux cable into the jack. The {leg} leg is the one that {find}. Mark it, then unplug the cable.",
                    f"Solder a {w['cut']} mm {colr} wire to that leg on the underside of the Pi. Keep it low and tape over it.",
                    "Feed it out past the board edge on the side-wall side, then up to the frame.",
                    f"In step 10, solder it to the PAM8403's input {pad} pad."],
            "test": "In step 10, speaker-test says \"Front Left\" from the left driver and \"Front Right\" from the right. If the sides are swapped, so are L and R.",
            "diagrams": ["audio"]})
    for pin, nm, sign in ((4, "5V", "+"), (14, "GND", "-")):
        w = by[f"amp-{nm}"]
        items.append({
            "wire": w["id"], "group": "Audio", "title": f"Amp power {sign}",
            "from": f"Header pin {pin} ({row(pin)}), {nm}", "to": f"PAM8403 power {sign}",
            "fromTag": f"pin {pin}", "toTag": f"amp {sign}", "pin": pin, "cut": f"{w['cut']} mm", "when": "Step 10",
            "sends": "5 V to the amp" if nm == "5V" else "ground to the amp",
            "how": [f"Solder a {w['cut']} mm {'red' if nm == '5V' else 'black'} wire onto header pin {pin} ({row(pin)}), with heatshrink.",
                    "Route it up to the frame and along to the amp's corner.",
                    f"Solder it to the PAM8403's {'+ (VCC)' if nm == '5V' else '- (GND)'} power pad."],
            "test": "With bench power on, the meter reads about 5 V across the amp's + and - pads.",
            "diagrams": ["audio", "header"]})
    for out, side in (("L+", "left"), ("L-", "left"), ("R+", "right"), ("R-", "right")):
        pol = "+" if out.endswith("+") else "-"
        items.append({
            "wire": f"spk-{out}", "group": "Audio", "title": f"Speaker {out}",
            "from": f"PAM8403 output {out}", "to": f"Speaker {side} driver {pol}",
            "fromTag": f"speaker {side}", "toTag": f"amp {out}", "pin": None, "cut": "the speaker's own lead", "when": "Step 10",
            "sends": f"{side} channel",
            "how": [f"Use the speaker's own lead. Find its {side} driver's {pol} wire.",
                    f"Solder it to the PAM8403's {out} output pad.",
                    "The outputs are bridged: L+ and L- go only to the left driver, R+ and R- only to the right."],
            "test": f"speaker-test's \"Front {side.title()}\" plays from the {side} driver only.",
            "warn": "Never join an output minus (L- or R-) to ground. That shorts the amp.",
            "diagrams": ["audio"]})
    for pin, nm, colr in ((2, "5V", "red"), (6, "GND", "black")):
        items.append({
            "wire": f"pwr-{nm}", "group": "Power", "title": f"Power {nm}",
            "from": f"Power bank lead, {colr} wire", "to": f"Header pin {pin} ({row(pin)}), {nm}",
            "fromTag": "bank lead", "toTag": f"pin {pin}", "pin": pin, "cut": "cable cut 15 cm from the C plug", "when": "Step 10",
            "sends": "5 V from the power bank" if nm == "5V" else "ground from the power bank",
            "how": ["Cut a USB-C cable 15 cm from the plug and strip the red and black wires.",
                    "Plug it into the bank, switch the bank on and measure black to red: it must read +5 V. If it reads -5 V the colours are swapped. Unplug it.",
                    f"Solder the {'+5 V' if nm == '5V' else 'ground'} wire onto pin {pin} ({row(pin)}), with heatshrink.",
                    "Run the lead through the pass-through at the drawer's inner end."],
            "test": "Unplug bench power, plug the lead into the bank and switch it on: the Pi boots.",
            "warn": "5 V on any other pin can destroy the Pi. Pin 2 is on the outer row at the microSD end: check it twice." if nm == "5V" else None,
            "diagrams": ["power", "header"]})
    items.append({
        "wire": None, "group": "Display", "title": "Display ribbon",
        "from": "Display's DSI connector (the ribbon stays attached)", "to": "Pi's DISPLAY connector",
        "fromTag": None, "toTag": None, "pin": None, "cut": "the display's own ribbon", "when": "Step 8, before the Pi goes onto its posts",
        "sends": "video and touch",
        "how": ["Leave the ribbon latched at the display end.",
                "Plug the other end into the Pi's DISPLAY connector, the same way round as when the screen worked on the bench.",
                "Close the latch, then lower the Pi onto its posts."],
        "test": "At the bench test the launcher appears on the screen and touch works.",
        "diagrams": []})
    return items
