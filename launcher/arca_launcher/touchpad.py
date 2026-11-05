"""On-screen controls for games: the Any% touch-to-gamepad service.

While a game runs with Settings > On-screen controls on, this process owns the touch panel (EVIOCGRAB, so neither
RetroArch nor the launcher sees a raw touch), follows every finger (multitouch type B, all slots), and turns the
fingers on the drawn gamepad into key presses on a virtual keyboard (uinput) with the keys RetroArch maps to
player 1 (device/retroarch.cfg). RetroArch only draws the gamepad (overlay input and touch off). So two thumbs
work: hold the D-pad with one and mash A/B with the other.

  python -m arca_launcher.touchpad OVERLAY.cfg [--device /dev/input/eventN]

The geometry is the overlay's own hitboxes (gamepad.cfg, made by device/overlay/make_overlay.py): a finger presses
the buttons of every hitbox it is inside (the D-pad's corner cells hold two directions), sliding moves the press
with it, sliding off or lifting releases. A button stays down while any finger is on it. The launcher starts this
right before RetroArch and stops it right after (runner.py); it prints "ready" once the keyboard exists and the
panel is grabbed. On SIGTERM, SIGINT, SIGHUP or the launcher dying it lets go of every key, ungrabs the panel and
removes the keyboard (the kernel would also do the last two if it were killed outright).

Why keys and not a virtual gamepad: RetroArch 1.20's keyboard binds are always player 1 whatever pads are plugged
in (a uinput joypad would take the next free port and needs an autoconfig profile matched by name); the keys are
the same path the virtual keyboard tests already proved on the device; and the run recorder sees the same joypad
bits as from real buttons. The launcher never sees the keyboard: it exists only while the launcher waits for
RetroArch."""
import ctypes
import fcntl
import glob
import os
import resource
import select
import signal
import struct
import subprocess
import sys
import time
from dataclasses import dataclass

W, H = 800, 480                                        # the panel and the overlay's full-screen size
EVENT = struct.Struct("<qqHHi")                        # struct input_event on 64-bit
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT, SYN_DROPPED = 0, 3
ABS_MT_SLOT, ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID = 0x2F, 0x35, 0x36, 0x39

# overlay button -> Linux key code, as device/retroarch.cfg maps the keyboard to player 1
KEYS = {"up": 103, "down": 108, "left": 105, "right": 106,
        "a": 45, "b": 44, "l": 30, "r": 31,                # x, z, a, s
        "start": 28, "select": 14}                         # enter, backspace
ESC = 1                                                # input_exit_emulator: L + R on the overlay quits the game


@dataclass(frozen=True)
class Hitbox:
    buttons: tuple
    x: float                                           # centre and half-size, normalized to the screen
    y: float
    shape: str                                         # "rect" or "radial" (an ellipse)
    rx: float
    ry: float

    def contains(self, nx, ny):
        dx, dy = (nx - self.x) / self.rx, (ny - self.y) / self.ry
        if self.shape == "radial":
            return dx * dx + dy * dy <= 1
        return abs(dx) <= 1 and abs(dy) <= 1


def parse_overlay(text):
    """The hitboxes of a RetroArch overlay .cfg's first overlay (normalized descs: names,x,y,shape,rx,ry)."""
    cfg = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"')
    if "overlay0_descs" not in cfg:
        raise ValueError("no overlay0_descs in the overlay config")
    boxes = []
    for i in range(int(cfg["overlay0_descs"])):
        names, x, y, shape, rx, ry = [s.strip() for s in cfg[f"overlay0_desc{i}"].split(",")[:6]]
        boxes.append(Hitbox(tuple(names.split("|")), float(x), float(y), shape, float(rx), float(ry)))
    return boxes


def load_overlay(path):
    with open(path) as f:
        return parse_overlay(f.read())


class Pad:
    def __init__(self, hitboxes, width=W, height=H):
        self.hitboxes = [b for b in hitboxes if all(n in KEYS for n in b.buttons)]
        self.width, self.height = width, height

    def buttons_at(self, x, y):
        """The buttons pressed by a finger at panel pixel x, y (the pixel's centre, normalized)."""
        nx, ny = (x + 0.5) / self.width, (y + 0.5) / self.height
        return frozenset(n for b in self.hitboxes if b.contains(nx, ny) for n in b.buttons)


class Touchpad:
    """Multitouch type B events in, key changes out. send(changes) gets [(key code, 1 or 0), ...] once per panel
    report that changes something (releases first). resync() -> (slot, {slot: (tracking id, (x, y))}) reads the
    panel's current state after the kernel dropped events."""

    def __init__(self, pad, send, slot=0, resync=None):
        self.pad = pad
        self.send = send
        self.slot = slot
        self.ids = {}                                  # slot -> tracking id (-1 = no finger)
        self.pos = {}                                  # slot -> [x, y]; kept after a lift (see event)
        self.pressed = set()
        self.dropping = False
        self._resync = resync

    def event(self, etype, code, value):
        if self.dropping:                              # SYN_DROPPED: skip to the next report, then re-read state
            if etype == EV_SYN and code == SYN_REPORT:
                self.dropping = False
                if self._resync is not None:
                    self.load(*self._resync())
                self.update()
            return
        if etype == EV_SYN:
            if code == SYN_REPORT:
                self.update()
            elif code == SYN_DROPPED:
                self.dropping = True
        elif etype == EV_ABS:
            if code == ABS_MT_SLOT:
                self.slot = value
            elif code == ABS_MT_TRACKING_ID:
                self.ids[self.slot] = value
            elif code == ABS_MT_POSITION_X:
                # the input core only sends a slot's position when it changes, so a new finger landing where
                # the last one in that slot lifted sends none: positions are never cleared
                self.pos.setdefault(self.slot, [None, None])[0] = value
            elif code == ABS_MT_POSITION_Y:
                self.pos.setdefault(self.slot, [None, None])[1] = value

    def load(self, slot, slots):
        self.slot = slot
        self.ids = {}
        for s, (tid, (x, y)) in slots.items():
            self.ids[s] = tid
            self.pos[s] = [x, y]

    def fingers(self):
        out = {}
        for s, tid in self.ids.items():
            p = self.pos.get(s)
            if tid >= 0 and p and None not in p:
                out[s] = tuple(p)
        return out

    def update(self):
        want = {KEYS[n] for x, y in self.fingers().values() for n in self.pad.buttons_at(x, y)}
        if {KEYS["l"], KEYS["r"]} <= want:             # held, not tapped: RetroArch polls once a frame
            want.add(ESC)
        self._apply(want)

    def release_all(self):
        self._apply(set())

    def _apply(self, want):
        changes = [(c, 0) for c in sorted(self.pressed - want)] + [(c, 1) for c in sorted(want - self.pressed)]
        if changes:
            self.send(changes)
        self.pressed = want


def decode(data):
    """(kernel time in seconds, type, code, value) for each whole event in data."""
    for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
        sec, usec, etype, code, value = EVENT.unpack_from(data, off)
        yield sec + usec / 1e6, etype, code, value


# --- the process the launcher starts around a game ------------------------------------------------------------

def command(overlay):
    return [sys.executable, "-m", "arca_launcher.touchpad", overlay]


class Service:
    def __init__(self, proc, ready):
        self.proc = proc
        self.ready = ready

    def stop(self, grace=2.0):
        """SIGTERM (the service releases every key, ungrabs, removes its keyboard), SIGKILL after grace."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(grace)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        if self.proc.stdout:
            self.proc.stdout.close()


def start(overlay, cmd=None, timeout=3.0):
    """Start the service and wait (up to timeout) until it says ready. Never raises for a service that fails:
    the game then simply has no touch."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # so -m finds arca_launcher
    proc = subprocess.Popen(cmd or command(overlay), stdout=subprocess.PIPE, cwd=here)
    ready = False
    end = time.monotonic() + timeout
    buf = b""
    while not ready:
        left = end - time.monotonic()
        if left <= 0 or not select.select([proc.stdout], [], [], left)[0]:
            break
        chunk = os.read(proc.stdout.fileno(), 256)
        if not chunk:                                  # exited
            break
        buf += chunk
        ready = b"ready" in buf
    return Service(proc, ready)


# --- the service itself (Linux only) --------------------------------------------------------------------------

EVIOCGNAME = 0x80FF4506
EVIOCGRAB = 0x40044590
EVIOCGABS_MT_SLOT = 0x80184540 + ABS_MT_SLOT            # struct input_absinfo: value, min, max, ...


def EVIOCGMTSLOTS(length):
    return (2 << 30) | (length << 16) | (ord("E") << 8) | 0x0A


UI_SET_EVBIT, UI_SET_KEYBIT, UI_DEV_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = (0x40045564, 0x40045565, 0x405C5503,
                                                                             0x5501, 0x5502)
UI_GET_SYSNAME = (2 << 30) | (64 << 16) | (ord("U") << 8) | 44
BUS_VIRTUAL = 0x06
KEYBOARD_NAME = b"anypercent touch controls"


def find_panel():
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        name = bytearray(256)
        try:
            fcntl.ioctl(fd, EVIOCGNAME, name)
        finally:
            os.close(fd)
        if b"ft5x06" in name or b"ft5406" in name or b"edt-ft5" in name:
            return path
    raise SystemExit("touchpad: no ft5x06 touchscreen under /dev/input")


def read_panel_state(fd):
    """(slot, {slot: (tracking id, (x, y))}) as the kernel holds them now."""
    info = bytearray(24)
    fcntl.ioctl(fd, EVIOCGABS_MT_SLOT, info)
    slot, _, top = struct.unpack_from("<3i", info)
    n = top + 1
    cols = {}
    for code in (ABS_MT_TRACKING_ID, ABS_MT_POSITION_X, ABS_MT_POSITION_Y):
        buf = bytearray(struct.pack("<I", code) + bytes(4 * n))
        fcntl.ioctl(fd, EVIOCGMTSLOTS(len(buf)), buf)
        cols[code] = struct.unpack_from(f"<{n}i", buf, 4)
    return slot, {i: (cols[ABS_MT_TRACKING_ID][i], (cols[ABS_MT_POSITION_X][i], cols[ABS_MT_POSITION_Y][i]))
                  for i in range(n)}


class VirtualKeys:
    """A uinput keyboard. It has every key from Esc to S so udev tags it ID_INPUT_KEYBOARD, which is what
    RetroArch's udev driver looks for at start-up."""

    def __init__(self):
        self.fd = os.open("/dev/uinput", os.O_WRONLY)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)          # no EV_REP: no autorepeat
        for code in sorted(set(range(1, 32)) | set(KEYS.values())):
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
        fcntl.ioctl(self.fd, UI_DEV_SETUP, struct.pack("<HHHH80sI", BUS_VIRTUAL, 0x1209, 0x0001, 1, KEYBOARD_NAME, 0))
        fcntl.ioctl(self.fd, UI_DEV_CREATE)

    def send(self, changes):
        os.write(self.fd, b"".join(EVENT.pack(0, 0, EV_KEY, c, v) for c, v in changes) + EVENT.pack(0, 0, EV_SYN, 0, 0))

    def wait_for_udev(self, timeout=2.0):
        """Wait until udev has tagged the keyboard (so a RetroArch starting now opens it). True if it did."""
        name = bytearray(64)
        fcntl.ioctl(self.fd, UI_GET_SYSNAME, name)
        sysname = name.split(b"\0")[0].decode()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for dev in glob.glob(f"/sys/devices/virtual/input/{sysname}/event*/dev"):
                try:
                    with open(dev) as f:
                        num = f.read().strip()
                    with open(f"/run/udev/data/c{num}") as f:
                        if "E:ID_INPUT_KEYBOARD=1" in f.read():
                            return True
                except OSError:
                    pass
            time.sleep(0.02)
        return False

    def close(self):
        fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        os.close(self.fd)


def _die_with_parent():
    try:
        ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM)              # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass
    if os.getppid() == 1:
        raise SystemExit(0)


def _stop(signum, frame):
    raise SystemExit(0)


def serve(overlay, device=None, out=sys.stdout, log=sys.stderr):
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, _stop)
    _die_with_parent()
    pad = Pad(load_overlay(overlay))
    path = device or find_panel()
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    keys = service = None
    grabbed = False
    lat = []                                           # ms from the panel's report to our keys being written
    reports = 0
    t0, cpu0 = time.monotonic(), resource.getrusage(resource.RUSAGE_SELF)
    try:
        keys = VirtualKeys()
        tagged = keys.wait_for_udev()
        fcntl.ioctl(fd, EVIOCGRAB, 1)
        grabbed = True
        slot, slots = read_panel_state(fd)
        service = Touchpad(pad, keys.send, resync=lambda: read_panel_state(fd))
        service.load(slot, slots)
        print("ready", flush=True, file=out)
        if not tagged:
            print("touchpad: udev had not tagged the keyboard yet", file=log, flush=True)
        while True:
            select.select([fd], [], [])
            try:
                data = os.read(fd, EVENT.size * 64)
            except BlockingIOError:
                continue
            if not data:
                break
            for when, etype, code, value in decode(data):
                pressed = service.pressed
                service.event(etype, code, value)
                if etype == EV_SYN and code == SYN_REPORT:
                    reports += 1
                    if service.pressed != pressed:
                        lat.append((time.time() - when) * 1000)
    finally:
        if service is not None:
            try:
                service.release_all()
            except OSError:
                pass
        if grabbed:
            try:
                fcntl.ioctl(fd, EVIOCGRAB, 0)
            except OSError:
                pass
        os.close(fd)
        if keys is not None:
            keys.close()
        cpu = resource.getrusage(resource.RUSAGE_SELF)
        used = cpu.ru_utime + cpu.ru_stime - cpu0.ru_utime - cpu0.ru_stime
        lat.sort()
        timing = (f", report to keys median {lat[len(lat) // 2]:.2f} ms max {lat[-1]:.2f} ms" if lat else "")
        print(f"touchpad: {reports} panel reports, {len(lat)} with key changes{timing}, cpu {used:.2f} s in "
              f"{time.monotonic() - t0:.1f} s", file=log, flush=True)


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="python -m arca_launcher.touchpad", description=__doc__.split("\n\n")[0])
    p.add_argument("overlay", help="RetroArch overlay .cfg whose hitboxes are the controls")
    p.add_argument("--device", help="the touchscreen's event node (default: find the ft5x06)")
    a = p.parse_args(argv)
    serve(a.overlay, a.device)


if __name__ == "__main__":
    main()
