"""A virtual USB keyboard (uinput) for driving the launcher and RetroArch over SSH.

  sudo python3 vkbd.py STEP [STEP ...]
  STEP: a key name (up down left right x z a s enter backspace esc f1) pressed once, optionally *N to repeat it,
        or wait=SECONDS, or grab=PATH.png (runs drmgrab.py next to this file).
  e.g.  sudo python3 vkbd.py wait=2 right*3 grab=/tmp/a.png x wait=12 grab=/tmp/b.png esc wait=5 grab=/tmp/c.png
The device appears like a plugged-in keyboard (SDL's evdev and RetroArch's udev input both pick it up on hotplug)."""
import fcntl
import os
import struct
import subprocess
import sys
import time

KEYS = {"esc": 1, "backspace": 14, "enter": 28, "a": 30, "s": 31, "z": 44, "x": 45, "f1": 59,
        "up": 103, "left": 105, "right": 106, "down": 108}
UI_SET_EVBIT, UI_SET_KEYBIT, UI_DEV_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = 0x40045564, 0x40045565, 0x405C5503, 0x5501, 0x5502
EV_SYN, EV_KEY = 0, 1


def emit(fd, etype, code, value):
    os.write(fd, struct.pack("<qqHHi", 0, 0, etype, code, value))


def press(fd, code):
    emit(fd, EV_KEY, code, 1)
    emit(fd, EV_SYN, 0, 0)
    time.sleep(0.08)
    emit(fd, EV_KEY, code, 0)
    emit(fd, EV_SYN, 0, 0)
    time.sleep(0.25)


def main(steps):
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    for code in KEYS.values():
        fcntl.ioctl(fd, UI_SET_KEYBIT, code)
    fcntl.ioctl(fd, UI_DEV_SETUP, struct.pack("<HHHH80sI", 0x03, 0x1234, 0x5678, 1, b"anypercent virtual keyboard", 0))
    fcntl.ioctl(fd, UI_DEV_CREATE)
    time.sleep(1.5)                                    # let udev and the programs see the new device
    try:
        for step in steps:
            if step.startswith("wait="):
                time.sleep(float(step[5:]))
            elif step.startswith("grab="):
                subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "drmgrab.py"),
                                step[5:]])
            else:
                name, _, n = step.partition("*")
                for _ in range(int(n or 1)):
                    press(fd, KEYS[name])
                print("pressed", step, flush=True)
    finally:
        fcntl.ioctl(fd, UI_DEV_DESTROY)
        os.close(fd)


if __name__ == "__main__":
    main(sys.argv[1:])
