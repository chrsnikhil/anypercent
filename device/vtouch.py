"""A virtual touchscreen (uinput, multitouch type B) for driving the launcher's touch controls over SSH,
and a reader for the real panel's touches.

  sudo python3 vtouch.py STEP [STEP ...]
  STEP: tap=X,Y                    finger down and up at panel pixel X,Y (0..799, 0..479)
        swipe=X1,Y1,X2,Y2[,MS]     finger down at X1,Y1, moves to X2,Y2 over MS milliseconds (default 250), up
        down=X,Y  move=X,Y[,MS]  up    the same in pieces, to grab frames while the finger is still down
        wait=SECONDS
        grab=PATH.png              runs drmgrab.py next to this file
        panel                      the touches after this go into the real panel's own event node (ft5x06) instead
                                   of a new virtual touchscreen: every program reading the panel gets them as if a
                                   finger touched it, including one that opened it at start-up and never looks
                                   for new devices (RetroArch). Coordinates are screen pixels as given (the device
                                   tree's inversion is applied by the driver, which these events bypass)
        STEP@N                     any of tap, swipe, down, move, up with @N (N = 0..9) uses finger N (a multitouch
                                   slot of its own), so fingers can be held together: down=128,372 tap@1=738,318
                                   holds finger 0 on one spot while finger 1 taps another. tap=X,Y*N taps N times
        listen                     prints, from now on, every key the on-screen controls service (arca_launcher
                                   touchpad) presses or releases on its virtual keyboard, with the time since the
                                   last touch step (the service must be running, i.e. a game with the setting on)
        watch=SECONDS              prints the real touchscreen's touches (ft5x06) in panel pixels, for checking
                                   by hand that touch and picture line up (touch the corners: top left should
                                   print near 0,0, bottom right near 799,479), with each touch's report rate,
                                   report gaps and how far a held finger wandered
  e.g.  sudo python3 vtouch.py wait=2 tap=250,160 wait=1 grab=/tmp/a.png swipe=600,160,200,160 grab=/tmp/b.png
        sudo python3 vtouch.py panel listen down=128,372 tap@1=738,318*5 up        (hold right, mash A)

The device reports INPUT_PROP_DIRECT, BTN_TOUCH, ABS_X/Y and the ABS_MT_* slot protocol with the panel's own
ranges, so udev tags it ID_INPUT_TOUCHSCREEN and SDL's evdev picks it up on hotplug like the real ft5x06. It
reports panel pixels as they are on screen: it is always "right way round", whatever the real panel's axes do
(the kernel applies the device tree's touchscreen-inverted-x/y to the real one before anyone sees it)."""
import fcntl
import glob
import os
import select
import struct
import subprocess
import sys
import time

W, H = 800, 480
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_ABSBIT, UI_SET_PROPBIT = 0x40045564, 0x40045565, 0x40045567, 0x4004556E
UI_DEV_SETUP, UI_ABS_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = 0x405C5503, 0x401C5504, 0x5501, 0x5502
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
BTN_TOUCH = 0x14A
ABS_X, ABS_Y, ABS_MT_SLOT, ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID = 0, 1, 0x2F, 0x35, 0x36, 0x39
INPUT_PROP_DIRECT = 1
EVENT = struct.Struct("<qqHHi")                  # struct input_event on 64-bit
EVIOCGNAME = 0x80FF4506


class VTouch:
    def __init__(self):
        self.tracking = 0
        self.slots = {}                                # slot -> (x, y) of each finger that is down
        self.pos = {}                                  # slot -> last (x, y), down or not
        self.fd = self._create()

    def _create(self):
        fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(fd, UI_SET_KEYBIT, BTN_TOUCH)
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_ABS)
        fcntl.ioctl(fd, UI_SET_PROPBIT, INPUT_PROP_DIRECT)
        for code, hi in ((ABS_X, W - 1), (ABS_Y, H - 1), (ABS_MT_SLOT, 9), (ABS_MT_POSITION_X, W - 1),
                         (ABS_MT_POSITION_Y, H - 1), (ABS_MT_TRACKING_ID, 65535)):
            fcntl.ioctl(fd, UI_SET_ABSBIT, code)
            fcntl.ioctl(fd, UI_ABS_SETUP, struct.pack("<H2x6i", code, 0, 0, hi, 0, 0, 0))
        fcntl.ioctl(fd, UI_DEV_SETUP, struct.pack("<HHHH80sI", 0x18, 0x1234, 0x5679, 1, b"anypercent virtual touch", 0))
        fcntl.ioctl(fd, UI_DEV_CREATE)
        time.sleep(1.5)                                # let udev and the launcher see the new device
        return fd

    def emit(self, etype, code, value):
        os.write(self.fd, EVENT.pack(0, 0, etype, code, value))

    def syn(self):
        self.emit(EV_SYN, 0, 0)

    def down(self, x, y, slot=0):
        self.tracking = (self.tracking + 1) % 65536
        self.emit(EV_ABS, ABS_MT_SLOT, slot)
        self.emit(EV_ABS, ABS_MT_TRACKING_ID, self.tracking)
        first = not self.slots
        self.slots[slot] = None
        self.move(x, y, sync=False, slot=slot)
        if first:
            self.emit(EV_KEY, BTN_TOUCH, 1)
        self.syn()

    def move(self, x, y, sync=True, slot=0):
        x, y = min(W - 1, max(0, round(x))), min(H - 1, max(0, round(y)))
        self.pos[slot] = self.slots[slot] = (x, y)
        self.emit(EV_ABS, ABS_MT_SLOT, slot)
        self.emit(EV_ABS, ABS_MT_POSITION_X, x)
        self.emit(EV_ABS, ABS_MT_POSITION_Y, y)
        if slot == min(self.slots):                    # single-touch emulation follows the oldest slot
            self.emit(EV_ABS, ABS_X, x)
            self.emit(EV_ABS, ABS_Y, y)
        if sync:
            self.syn()

    def up(self, slot=0):
        self.slots.pop(slot, None)
        self.emit(EV_ABS, ABS_MT_SLOT, slot)
        self.emit(EV_ABS, ABS_MT_TRACKING_ID, -1)
        if not self.slots:
            self.emit(EV_KEY, BTN_TOUCH, 0)
        self.syn()

    def tap(self, x, y, times=1, hold=0.08, slot=0):
        for _ in range(times):
            self.down(x, y, slot)
            time.sleep(hold)
            self.up(slot)
            time.sleep(0.3 if times == 1 else 0.12)

    def swipe(self, x1, y1, x2, y2, ms=250, slot=0):
        self.down(x1, y1, slot)
        self.glide(x2, y2, ms, slot)
        self.up(slot)
        time.sleep(0.3)

    def glide(self, x2, y2, ms=250, slot=0):
        """Move a finger that is down from where it is to x2, y2 over ms, one report per 16 ms."""
        x1, y1 = self.pos[slot]
        n = max(1, ms // 16)
        for i in range(1, n + 1):
            time.sleep(ms / 1000 / n)
            self.move(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n, slot=slot)

    def close(self):
        fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        os.close(self.fd)


class PanelTouch(VTouch):
    """Touches written into the real panel's event node (evdev passes written events on to every reader)."""

    def _create(self):
        path, fd = real_touchscreen(os.O_WRONLY)
        print("panel", path, flush=True)
        return fd

    def close(self):
        os.close(self.fd)


def real_touchscreen(mode=os.O_RDONLY | os.O_NONBLOCK):
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, mode)
        except OSError:
            continue
        name = bytearray(256)
        fcntl.ioctl(fd, EVIOCGNAME, name)
        if b"ft5x06" in name or b"ft5406" in name or b"edt-ft5" in name:
            return path, fd
        os.close(fd)
    raise SystemExit("no ft5x06 touchscreen found under /dev/input")


LISTEN_T = [time.monotonic()]                          # when the last touch step ran


def listen():
    """Print the on-screen controls service's key presses (its keyboard, by name) from a background thread."""
    import threading
    names = {103: "up", 108: "down", 105: "left", 106: "right", 45: "A(x)", 44: "B(z)", 30: "L(a)", 31: "R(s)",
             28: "start(enter)", 14: "select(backspace)"}
    fd = None
    for path in sorted(glob.glob("/dev/input/event*")):
        f = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        name = bytearray(256)
        fcntl.ioctl(f, EVIOCGNAME, name)
        if name.startswith(b"anypercent touch controls"):
            fd = f
            print("listening to", path, flush=True)
            break
        os.close(f)
    if fd is None:
        raise SystemExit("no 'anypercent touch controls' keyboard: is a game running with on-screen controls on?")

    def loop():
        while True:
            select.select([fd], [], [])
            try:
                data = os.read(fd, EVENT.size * 64)
            except OSError:
                return
            for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
                _, _, etype, code, value = EVENT.unpack_from(data, off)
                if etype == EV_KEY:
                    print(f"  key {names.get(code, code)} {'down' if value else 'up'} "
                          f"(+{(time.monotonic() - LISTEN_T[0]) * 1000:.0f} ms)", flush=True)
    threading.Thread(target=loop, daemon=True).start()


def watch(seconds):
    """Print each real touch: where it went down and up, and from the kernel's event times how often the panel
    reported it (reports per second, the gap between reports) and how far a held finger wandered (jitter)."""
    path, fd = real_touchscreen()
    print(f"reading {path} for {seconds} s; touch the screen (hold still for a jitter reading)", flush=True)
    end = time.time() + seconds
    x = y = None
    frames = []                                        # (seconds, x, y) of each report (SYN) while down
    down = False
    while time.time() < end:
        if not select.select([fd], [], [], 0.2)[0]:
            continue
        data = os.read(fd, EVENT.size * 64)
        for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
            sec, usec, etype, code, value = EVENT.unpack_from(data, off)
            if etype == EV_ABS and code in (ABS_X, ABS_MT_POSITION_X):
                x = value
            elif etype == EV_ABS and code in (ABS_Y, ABS_MT_POSITION_Y):
                y = value
            elif etype == EV_KEY and code == BTN_TOUCH:
                down = bool(value)
                if down:
                    frames = []
                    print("down", x, y, flush=True)
                else:
                    print("up  ", x, y, summary(frames), flush=True)
            elif etype == EV_SYN and down:
                frames.append((sec + usec / 1e6, x, y))
    os.close(fd)


def summary(frames):
    if len(frames) < 3:
        return f"({len(frames)} reports)"
    gaps = sorted((b[0] - a[0]) * 1000 for a, b in zip(frames, frames[1:]))
    span = frames[-1][0] - frames[0][0]
    x0, y0 = frames[0][1], frames[0][2]
    wander = max(max(abs(f[1] - x0), abs(f[2] - y0)) for f in frames)
    return (f"({len(frames)} reports in {span * 1000:.0f} ms = {(len(frames) - 1) / span:.1f}/s, gap median "
            f"{gaps[len(gaps) // 2]:.1f} ms max {gaps[-1]:.1f} ms, wandered {wander} px)")


def main(steps):
    touch = None
    make = VTouch
    try:
        for step in steps:
            name, _, arg = step.partition("=")
            if name == "panel":
                if touch is not None:
                    touch.close()
                touch, make = None, PanelTouch
            elif name == "wait":
                time.sleep(float(arg))
            elif name == "grab":
                subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "drmgrab.py"),
                                arg])
            elif name == "watch":
                watch(float(arg))
            elif name == "listen":
                listen()
            elif name.split("@")[0] in ("tap", "swipe", "down", "move", "up"):
                if touch is None:
                    touch = make()
                verb, _, finger = name.partition("@")
                arg, _, times = arg.partition("*")
                nums = [int(v) for v in arg.split(",")] if arg else []
                kw = {"slot": int(finger or 0)}
                if times:
                    kw["times"] = int(times)
                LISTEN_T[0] = time.monotonic()
                {"move": touch.glide}.get(verb, getattr(touch, verb))(*nums, **kw)
                print(step, flush=True)
            else:
                raise SystemExit(f"unknown step {step!r}")
    finally:
        if touch is not None:
            touch.close()


if __name__ == "__main__":
    main(sys.argv[1:])
