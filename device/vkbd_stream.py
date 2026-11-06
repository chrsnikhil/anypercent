"""Virtual keyboard fed from stdin, for the laptop remote (device/remote_keys.py).
  sudo python3 vkbd_stream.py      then lines on stdin: "d <keycode>" press, "u <keycode>" release, "q" quit.
Only the keys the launcher and RetroArch use are allowed."""
import fcntl, os, struct, sys, time

ALLOWED = {1, 14, 28, 30, 31, 44, 45, 59, 103, 105, 106, 108}   # esc bksp enter a s z x f1 up left right down
UI_SET_EVBIT, UI_SET_KEYBIT, UI_DEV_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = 0x40045564, 0x40045565, 0x405C5503, 0x5501, 0x5502
EV_SYN, EV_KEY = 0, 1

fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
for c in ALLOWED:
    fcntl.ioctl(fd, UI_SET_KEYBIT, c)
fcntl.ioctl(fd, UI_DEV_SETUP, struct.pack("<HHHH80sI", 0x03, 0x1234, 0x5679, 1, b"anypercent laptop remote", 0))
fcntl.ioctl(fd, UI_DEV_CREATE)
time.sleep(1.0)
print("ready", flush=True)
down = set()
try:
    for line in sys.stdin:
        parts = line.split()
        if not parts or parts[0] == "q":
            break
        if len(parts) != 2 or parts[0] not in ("d", "u"):
            continue
        code = int(parts[1])
        if code not in ALLOWED:
            continue
        val = 1 if parts[0] == "d" else 0
        (down.add if val else down.discard)(code)
        os.write(fd, struct.pack("<qqHHi", 0, 0, EV_KEY, code, val))
        os.write(fd, struct.pack("<qqHHi", 0, 0, EV_SYN, 0, 0))
finally:
    for code in down:                       # never leave a key stuck down
        os.write(fd, struct.pack("<qqHHi", 0, 0, EV_KEY, code, 0))
    os.write(fd, struct.pack("<qqHHi", 0, 0, EV_SYN, 0, 0))
    fcntl.ioctl(fd, UI_DEV_DESTROY)
    os.close(fd)
