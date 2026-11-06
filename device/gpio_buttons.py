"""The handheld's 12 buttons, wired straight to the Pi's GPIO header, as a keyboard.

Each switch joins one GPIO to ground; the internal pull-up holds the line high and a
press pulls it low. Presses become the same key events the laptop remote sends
(vkbd.py), which the launcher and RetroArch already use:

  D-pad = arrows, A = X, B = Z, L = A, R = S, START = Enter, SELECT = Backspace,
  X = F1 (RetroArch menu), Y = Esc (back to the launcher), L + R together = Esc too

  sudo python3 gpio_buttons.py          run (the anypercent-buttons service does this)
  sudo python3 gpio_buttons.py --test   print each press and release, send no keys

Needs python3-libgpiod (v2 API), installed by install.sh.
"""
import datetime
import fcntl
import glob
import os
import struct
import sys

# button: (BCM GPIO, header pin, Linux key code)
BUTTONS = {
    "UP":     (17, 11, 103), "DOWN":   (27, 13, 108), "LEFT": (22, 15, 105), "RIGHT": (23, 16, 106),
    "A":      (5, 29, 45),   "B":      (6, 31, 44),   "X":    (24, 18, 59),  "Y":     (25, 22, 1),
    "START":  (26, 37, 28),  "SELECT": (16, 36, 14),  "L":    (20, 38, 30),  "R":     (21, 40, 31),
}
ESC = 1
# Every key from Esc to S as well as ours: udev tags ID_INPUT_KEYBOARD only then, and RetroArch's udev
# driver opens only devices with that tag (touchpad.py's keyboard does the same).
KEYBOARD_KEYS = set(range(1, 32)) | {code for _, _, code in BUTTONS.values()}
DEBOUNCE = datetime.timedelta(milliseconds=5)

UI_SET_EVBIT, UI_SET_KEYBIT, UI_DEV_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = 0x40045564, 0x40045565, 0x405C5503, 0x5501, 0x5502
EV_SYN, EV_KEY = 0, 1
EVENT = struct.Struct("<qqHHi")


def keys_for(held):
    """The keys to hold down for these held buttons. L + R also holds Esc (quit to the launcher); it is held
    rather than tapped because RetroArch reads the keyboard once a frame."""
    keys = {BUTTONS[name][2] for name in held}
    if {"L", "R"} <= set(held):
        keys.add(ESC)
    return keys


def gpio_chip(gpiod):
    """The chip that owns the 40-pin header (label pinctrl-bcm2835 on a Pi 3B+)."""
    for path in sorted(glob.glob("/dev/gpiochip*")):
        with gpiod.Chip(path) as chip:
            if "bcm2835" in chip.get_info().label:
                return path
    sys.exit("no bcm2835 GPIO chip found: is this a Raspberry Pi 3?")


def keyboard():
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    for code in sorted(KEYBOARD_KEYS):
        fcntl.ioctl(fd, UI_SET_KEYBIT, code)
    fcntl.ioctl(fd, UI_DEV_SETUP, struct.pack("<HHHH80sI", 0x06, 0x1209, 0x0002, 1, b"anypercent buttons", 0))
    fcntl.ioctl(fd, UI_DEV_CREATE)
    return fd


def send(fd, changes):
    """[(key code, 1 or 0), ...] then one SYN."""
    os.write(fd, b"".join(EVENT.pack(0, 0, EV_KEY, c, v) for c, v in changes) + EVENT.pack(0, 0, EV_SYN, 0, 0))


def main(test):
    import gpiod
    from gpiod.line import Bias, Direction, Edge

    by_gpio = {gpio: name for name, (gpio, _, _) in BUTTONS.items()}
    settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP,
                                  edge_detection=Edge.BOTH, debounce_period=DEBOUNCE)
    fd = None if test else keyboard()
    with gpiod.request_lines(gpio_chip(gpiod), consumer="anypercent-buttons",
                             config={tuple(by_gpio): settings}) as req:
        held = {by_gpio[g] for g in by_gpio if req.get_value(g).value == 0}
        if held:
            print("held at start (check the wiring if nothing is pressed):", ", ".join(sorted(held)), flush=True)
        down = set()
        print("ready" + (" (test mode: press each button)" if test else ""), flush=True)
        try:
            while True:
                if not req.wait_edge_events(datetime.timedelta(seconds=5)):
                    continue
                for ev in req.read_edge_events():
                    name = by_gpio[ev.line_offset]
                    pressed = ev.event_type == ev.Type.FALLING_EDGE          # pulled to ground = pressed
                    (held.add if pressed else held.discard)(name)
                    if test:
                        print(f"{name:6s} {'down' if pressed else 'up'}" + ("   (L + R: quit to launcher)" if {"L", "R"} <= held else ""), flush=True)
                want = keys_for(held)
                changes = [(c, 0) for c in sorted(down - want)] + [(c, 1) for c in sorted(want - down)]
                if changes and fd is not None:
                    send(fd, changes)
                down = want
        except KeyboardInterrupt:
            pass
        finally:
            if fd is not None:
                send(fd, [(c, 0) for c in sorted(down)])
                fcntl.ioctl(fd, UI_DEV_DESTROY)
                os.close(fd)


if __name__ == "__main__":
    main("--test" in sys.argv[1:])
