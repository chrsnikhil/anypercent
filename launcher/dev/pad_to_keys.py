"""A DualSense on the laptop, for the launcher in WSL: WSLg windows only get Windows' keyboard and mouse, never its
game controllers. This reads the controller on Windows and types the launcher's keys into whatever window is in front
(the launcher, or a game's mGBA window), so no driver is installed.

  python launcher/dev/pad_to_keys.py          (Windows; Ctrl+C to stop)

Cross = X, Circle = Z, Square = C, Triangle = D (PB), D-pad and left stick = arrows, L1/L2 = A, R1/R2 = S,
Options = Enter, Create = Backspace: the launcher's keyboard map (input.py) and mGBA's own. Buttons are held as long as
they are held, so a game's accelerate works. Scan codes, not virtual keys, so the RDP channel WSLg runs on passes them."""
import ctypes
import os
import sys
import time
from ctypes import wintypes

os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"     # events while the launcher, not us, has the focus
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame  # noqa: E402
from pygame._sdl2 import controller  # noqa: E402

# (scan code, extended) for each launcher key
X, Z, C, D, A, S = (0x2D, False), (0x2C, False), (0x2E, False), (0x20, False), (0x1E, False), (0x1F, False)
ENTER, BACKSPACE = (0x1C, False), (0x0E, False)
UP, DOWN, LEFT, RIGHT = (0x48, True), (0x50, True), (0x4B, True), (0x4D, True)
BUTTONS = {
    pygame.CONTROLLER_BUTTON_A: X, pygame.CONTROLLER_BUTTON_B: Z, pygame.CONTROLLER_BUTTON_X: C,
    pygame.CONTROLLER_BUTTON_Y: D, pygame.CONTROLLER_BUTTON_LEFTSHOULDER: A, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: S,
    pygame.CONTROLLER_BUTTON_START: ENTER, pygame.CONTROLLER_BUTTON_BACK: BACKSPACE,
    pygame.CONTROLLER_BUTTON_DPAD_UP: UP, pygame.CONTROLLER_BUTTON_DPAD_DOWN: DOWN,
    pygame.CONTROLLER_BUTTON_DPAD_LEFT: LEFT, pygame.CONTROLLER_BUTTON_DPAD_RIGHT: RIGHT,
}
ON, OFF = 0.5, 0.35                      # stick and trigger thresholds, with hysteresis so a key never chatters

KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x8


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def send(key, down):
    code, extended = key
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0) | (0 if down else KEYEVENTF_KEYUP)
    inp = INPUT(type=1, ki=KEYBDINPUT(0, code, flags, 0, 0))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


class Keys:
    """Each key is held while any source (a button, the stick, a trigger) holds it; pressed and released once."""

    def __init__(self):
        self.held = {}

    def set(self, source, key, on):
        holders = self.held.setdefault(key, set())
        was = bool(holders)
        holders.add(source) if on else holders.discard(source)
        if bool(holders) != was:
            send(key, bool(holders))

    def release_all(self):
        for key, holders in self.held.items():
            if holders:
                send(key, False)
        self.held.clear()


def main():
    pygame.init()
    controller.init()
    keys, pads, axes = Keys(), {}, {}
    print("pad_to_keys: waiting for a controller (Ctrl+C to stop)", flush=True)
    try:
        while True:
            for e in pygame.event.get():
                if e.type == pygame.CONTROLLERDEVICEADDED:
                    pad = controller.Controller(e.device_index)
                    pads[pad.as_joystick().get_instance_id()] = pad
                    print("connected:", pad.name, flush=True)
                elif e.type == pygame.CONTROLLERDEVICEREMOVED:
                    pads.pop(e.instance_id, None)
                    keys.release_all()
                    print("controller removed", flush=True)
                elif e.type in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP) and e.button in BUTTONS:
                    keys.set(("btn", e.button), BUTTONS[e.button], e.type == pygame.CONTROLLERBUTTONDOWN)
                elif e.type == pygame.CONTROLLERAXISMOTION:
                    v = e.value / 32767
                    if e.axis == pygame.CONTROLLER_AXIS_LEFTX:
                        pairs = ((LEFT, -v), (RIGHT, v))
                    elif e.axis == pygame.CONTROLLER_AXIS_LEFTY:
                        pairs = ((UP, -v), (DOWN, v))
                    elif e.axis == pygame.CONTROLLER_AXIS_TRIGGERLEFT:
                        pairs = ((A, v),)
                    elif e.axis == pygame.CONTROLLER_AXIS_TRIGGERRIGHT:
                        pairs = ((S, v),)
                    else:
                        continue
                    for key, amount in pairs:
                        src = ("axis", e.axis, key)
                        on = amount > (OFF if axes.get(src) else ON)
                        axes[src] = on
                        keys.set(src, key, on)
            time.sleep(0.004)
    except KeyboardInterrupt:
        pass
    finally:
        keys.release_all()                # never leave a key stuck down in the launcher


if __name__ == "__main__":
    if sys.platform != "win32":
        sys.exit("pad_to_keys is for Windows (the launcher in WSL); on the console the DualSense is read directly")
    main()
