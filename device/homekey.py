"""Any% home key: hold the controller's PS button for 2 seconds to get back to the launcher from anything.

  an app (GTA III, the browser)   its service is stopped; the service starts the launcher again as it ends
  a game (RetroArch, mGBA)        RetroArch is asked to QUIT (network command): a normal quit that writes the
                                  save and the game's place for Continue (SIGTERM after 3 s if it hangs);
                                  the launcher was waiting for it and comes straight back
  the launcher itself             it restarts: the way out if it ever freezes or loses the screen
A quick tap of PS sleeps: screen off, a running game paused, CPU slowed; any button wakes it. PS + D-pad up/down
is volume, PS + D-pad left/right brightness (shared with the launcher through /run/anypercent/levels).

A short rumble says it worked. The quit leaves a mark (/run/anypercent/home-quit) so the launcher does not report
it as a crash. Watches every input device with a PS button (BTN_MODE), as pads come and go.

  sudo python3 homekey.py            run (the anypercent-homekey service does this)
  sudo python3 homekey.py --test     print what a hold would do, do nothing"""
import glob
import os
import select
import signal
import struct
import subprocess
import sys
import time

HOLD_S = 2.0
TAP_S = 0.5                                                         # PS up sooner than this: a tap (sleep / wake)
BTN_MODE = 316
EV_KEY = 1
EV_ABS = 3
APP_SERVICES = ("anypercent-gta3.service", "anypercent-browser.service")
LAUNCHER = "anypercent-launcher.service"
RETROARCH_CMD_PORT = 55355                                          # network_cmd_port in the launcher's RetroArch cfg
EMULATORS = ("retroarch", "mgba-qt", "mgba")
RUN_DIR = "/run/anypercent"
RESCAN_S = 2.0
EVENT = struct.Struct("llHHi")


class Hold:
    """A button held down for hold_s seconds, once per press."""

    def __init__(self, hold_s=HOLD_S):
        self.hold_s = hold_s
        self.down_at = None
        self.fired = False

    def key(self, pressed, now):
        """Returns "tap" when PS comes up within TAP_S of going down, used for nothing else (sleep / wake)."""
        if pressed:
            if self.down_at is None:
                self.down_at, self.fired = now, False
            return None
        tap = self.down_at is not None and not self.fired and now - self.down_at < TAP_S
        self.down_at = None
        return "tap" if tap else None

    def hat(self, code, value):
        """A D-pad move (ABS_HAT0X 16 / ABS_HAT0Y 17). With PS held it is a level step and that press no longer
        goes home: ("volume", +1 up / -1 down) or ("brightness", +1 right / -1 left). Without PS: None."""
        if self.down_at is None or value == 0 or code not in (16, 17):
            return None
        self.fired = True
        if code == 17:
            return "volume", 1 if value < 0 else -1
        return "brightness", 1 if value > 0 else -1

    def due(self, now):
        if self.down_at is not None and not self.fired and now - self.down_at >= self.hold_s:
            self.fired = True
            return True
        return False

    def wait(self, now):
        """Seconds until the hold would fire, or None while nothing is held."""
        if self.down_at is None or self.fired:
            return None
        return max(0.0, self.hold_s - (now - self.down_at))


STEP = 10                                                           # percent per D-pad press
VOLUME_CEILING = 96                                                 # the launcher's: 100% is the mixer's 0 dB
MIXER_CONTROLS = ("Master", "PCM", "Headphone", "Digital")
STATE = "/home/anypercent/.local/state/anypercent/state.json"       # the launcher's settings


def load_levels(run_dir=RUN_DIR, state_path=STATE):
    """The current volume and brightness: the last step taken here (run_dir/levels), else the launcher's settings."""
    import json
    for path in (os.path.join(run_dir, "levels"), state_path):
        try:
            with open(path) as f:
                d = json.load(f)
            return {"volume": int(d.get("volume", 80)), "brightness": int(d.get("brightness", 100))}
        except (OSError, ValueError, TypeError):
            continue
    return {"volume": 80, "brightness": 100}


def step(levels, kind, direction):
    lo = 10 if kind == "brightness" else 0                          # never a black screen by accident
    out = dict(levels)
    out[kind] = max(lo, min(100, levels[kind] + direction * STEP))
    return out


def save_levels(run_dir, levels, now=time.time):
    """For the launcher: it shows the change and keeps it as its own setting (arca_launcher/levels.py)."""
    import json
    os.makedirs(run_dir, exist_ok=True)
    tmp = os.path.join(run_dir, "levels.tmp")
    with open(tmp, "w") as f:
        json.dump({**levels, "changed": now() if callable(now) else now}, f)
    os.replace(tmp, os.path.join(run_dir, "levels"))


def apply_volume(pct, run=None):
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True))
    level = f"{round(pct * VOLUME_CEILING / 100)}%"
    for control in MIXER_CONTROLS:
        r = run(["amixer", "-q", "sset", control, level])
        if r is None or r.returncode == 0:
            return


def apply_brightness(pct, backlight=None):
    d = backlight or next(iter(sorted(glob.glob("/sys/class/backlight/*"))), None)
    if not d:
        return
    try:
        top = int(open(os.path.join(d, "max_brightness")).read())
        with open(os.path.join(d, "brightness"), "w") as f:
            f.write(str(round(top * pct / 100)))
    except (OSError, ValueError):
        pass


def choose(active, pids):
    """What going home means right now: ("stop", app service), ("term", emulator pid), or, already home,
    ("restart", the launcher)."""
    for s in APP_SERVICES:
        if s in active:
            return "stop", s
    if pids:
        return "term", pids[0]
    return "restart", LAUNCHER


def emulator_pids(proc="/proc"):
    out = []
    for d in glob.glob(os.path.join(proc, "[0-9]*")):
        try:
            with open(os.path.join(d, "comm")) as f:
                if f.read().strip() in EMULATORS:
                    out.append(int(os.path.basename(d)))
        except (OSError, ValueError):
            pass
    return out


def active_services():
    r = subprocess.run(["systemctl", "is-active", *APP_SERVICES], capture_output=True, text=True)
    return {s for s, state in zip(APP_SERVICES, r.stdout.split()) if state == "active"}


def stop_service(name):
    subprocess.run(["systemctl", "stop", "--no-block", name], check=False)


def restart_service(name):
    subprocess.run(["systemctl", "restart", "--no-block", name], check=False)


def term(pid):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def _udp_quit(msg):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(msg, ("127.0.0.1", RETROARCH_CMD_PORT))


def _alive(pid):
    return os.path.exists(f"/proc/{pid}")


def quit_emulator(pid, send=_udp_quit, alive=_alive, kill=term, wait=3.0, step=0.1):
    """Ask RetroArch to QUIT over its network command port: a normal quit, so it writes the game's place
    (<rom>.state.auto; on SIGTERM it does not). Still running after `wait` seconds: SIGTERM."""
    try:
        send(b"QUIT")
    except OSError:
        pass
    deadline = time.monotonic() + wait
    while alive(pid):
        if time.monotonic() >= deadline:
            kill(pid)
            return
        time.sleep(step)


def go_home(run_dir=RUN_DIR, active=active_services, pids=emulator_pids, stop=stop_service, term=quit_emulator,
            now=time.time, restart=restart_service):
    action = choose(active(), pids())
    if action[0] == "restart":                                      # nothing to quit: the launcher starts afresh
        restart(action[1])
        return action
    try:
        os.makedirs(run_dir, exist_ok=True)
        with open(os.path.join(run_dir, "home-quit"), "w") as f:
            f.write(f"{now()}\n")
    except OSError:
        pass
    kind, target = action
    (stop if kind == "stop" else term)(target)
    return action


def has_key(capabilities, code):
    """capabilities/key from sysfs: hex words, most significant first, each 64 bits."""
    words = capabilities.split()
    i = code // 64
    if i >= len(words):
        return False
    return bool(int(words[-1 - i], 16) >> (code % 64) & 1)


def pads(sys_root="/sys"):
    out = []
    for cap in glob.glob(os.path.join(sys_root, "class", "input", "event*", "device", "capabilities", "key")):
        try:
            with open(cap) as f:
                if has_key(f.read(), BTN_MODE):
                    out.append("/dev/input/" + cap.split(os.sep)[-4])
        except OSError:
            pass
    return sorted(out)


def rumble(fd):
    """A short double-strength kick: going home."""
    _rumble(fd, 1.0, 250)


def _rumble(fd, strength, ms):
    """Through the launcher's own force-feedback code. Best effort."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "launcher"))
        from arca_launcher import haptics
        import fcntl
        buf = bytearray(haptics.rumble_effect(-1, strength, strength, ms))
        fcntl.ioctl(fd, haptics.EVIOCSFF, buf)
        effect = haptics.FFEffect.from_buffer(buf).id
        os.write(fd, struct.pack("llHHi", 0, 0, haptics.EV_FF, effect, 1))
    except Exception:
        pass


def _udp(msg):
    try:
        _udp_quit(msg)
    except OSError:
        pass


def set_governor(mode):
    for f in glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor"):
        try:
            with open(f, "w") as g:
                g.write(mode)
        except OSError:
            pass


class Sleeper:
    """A tap of PS: the screen goes off, a running game pauses, the CPU slows down. Any button wakes it all."""

    def __init__(self, set_brightness=None, pause=None, cpu=set_governor, brightness=None, playing=None):
        self.set_brightness = set_brightness or apply_brightness
        self.pause = pause or (lambda: _udp(b"PAUSE_TOGGLE"))
        self.cpu = cpu
        self.brightness = brightness or (lambda: load_levels()["brightness"])
        self.playing = playing or (lambda: bool(emulator_pids()))
        self.asleep, self.paused = False, False

    def toggle(self):
        (self.wake if self.asleep else self.sleep)()

    def sleep(self):
        self.paused = self.playing()
        if self.paused:
            self.pause()
        self.set_brightness(0)
        self.cpu("powersave")
        self.asleep = True

    def wake(self):
        self.cpu("ondemand")
        self.set_brightness(max(10, self.brightness()))
        if self.paused:
            self.pause()                                            # PAUSE_TOGGLE again: the game runs on
        self.asleep = self.paused = False


EVIOCGRAB = 0x40044590


def grab(fd, on):
    """Take the pad for ourselves while PS is held, so a PS + D-pad level step does not also move the game or
    the launcher; let go with PS."""
    try:
        import fcntl
        fcntl.ioctl(fd, EVIOCGRAB, 1 if on else 0)
    except OSError:
        pass


def tick(fd):
    """A very short, light rumble: one level step."""
    _rumble(fd, 0.25, 40)


def main(test=False):
    holds, fds, last_scan = {}, {}, 0.0
    sleeper = Sleeper()
    while True:
        now = time.monotonic()
        if now - last_scan >= RESCAN_S:
            last_scan = now
            for path in pads():
                if path not in fds:
                    try:
                        fds[path] = os.open(path, os.O_RDWR | os.O_NONBLOCK)
                        holds[path] = Hold()
                        print("watching", path, flush=True)
                    except OSError:
                        pass
        waits = [w for w in (h.wait(now) for h in holds.values()) if w is not None]
        timeout = min([RESCAN_S] + waits)
        ready, _, _ = select.select(list(fds.values()), [], [], timeout)
        now = time.monotonic()
        for path, fd in list(fds.items()):
            if fd in ready:
                try:
                    data = os.read(fd, EVENT.size * 64)
                except OSError:                                     # the pad went away
                    os.close(fd)
                    del fds[path], holds[path]
                    continue
                for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
                    _, _, etype, code, value = EVENT.unpack_from(data, off)
                    if sleeper.asleep:                  # asleep: any press wakes, and does nothing else
                        if (etype == EV_KEY and value == 1) or (etype == EV_ABS and code in (16, 17) and value):
                            sleeper.wake()
                            grab(fd, False)
                            print("woke", flush=True)
                            if etype == EV_KEY and code == BTN_MODE:
                                holds[path].key(True, now)
                                holds[path].fired = True    # its release is no tap: it would sleep again
                        continue
                    if etype == EV_KEY and code == BTN_MODE:
                        tap = holds[path].key(value != 0, now)
                        grab(fd, value != 0)            # while PS is held its D-pad steps reach no game
                        if tap == "tap" and not test:
                            sleeper.sleep()
                            grab(fd, True)              # asleep: the waking press must not reach the game
                            print("asleep", flush=True)
                    elif etype == EV_ABS:
                        combo = holds[path].hat(code, value)
                        if combo and not test:
                            kind, direction = combo
                            levels = step(load_levels(), kind, direction)
                            (apply_volume if kind == "volume" else apply_brightness)(levels[kind])
                            save_levels(RUN_DIR, levels)
                            tick(fd)
            if path in holds and holds[path].due(now):
                if test:
                    print("hold: would do", choose(active_services(), emulator_pids()), flush=True)
                else:
                    action = go_home()
                    print("hold:", action, flush=True)
                    if action[0] != "restart":                  # the launcher restart is feedback enough
                        rumble(fd)


if __name__ == "__main__":
    main(test="--test" in sys.argv)
