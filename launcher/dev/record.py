"""Record the real launcher to video from a shot script, for the demo film.

  wsl -d Ubuntu-24.04 -u root -- [env ARCA_WORLD_BRIDGE=URL ARCA_ARKIV_CHECKER=0x... ARCA_HEDERA=1] \\
    /opt/arca-sandbox/venv/bin/python /mnt/c/Users/chrsn/Desktop/retro-handheld-ethglobal/launcher/dev/record.py \\
    SHOT.json [--name NAME] [--out DIR] [--keep-frames] [-- launcher args]

The real App (arca_launcher.app), headless (SDL's dummy video and audio, no pad opened), 800 x 480, driven by the
shot script's steps and recorded at a fixed 30 frames a second to video/final/rec/<name>.mp4 (H.264, yuv420p), with
<name>.json beside it: the marks, the chain links PB opened, the launch the shot ended on, every step's frames.

Sponsors as on the laptop (laptop.sh): the same environment and flags; none given, every sponsor is mocked. Arkiv's
RPC is read through agent_rpc (the same request under a User-Agent of its own: see there), unless --console-rpc.

It acts as the laptop console: once per run its state is copied from /opt/arca-sandbox (laptop-state.json and the
files beside it that make it that console: console-id, handler.json, the sponsors' caches) and its runs folder into
/opt/arca-sandbox/recorder/, and it runs on that copy only, with a run dir of its own. PB's day-start greeting and
book offer are marked done in the copy (the first press would only move PB on), unless the script asks for them.

Time: each frame advances the app by exactly 1/30 s and is never drawn ahead of the wall clock, so animations are
smooth and a network step takes as long in the video as it did for real (the sidecar says how far the frames ever
fell behind). Frames go to PNG files in a WSL folder on worker threads, then the Windows ffmpeg encodes them.

A chain link PB opens (OpenLink) is logged in the sidecar, never opened. A launch (Play, or PB's RaceTarget) draws
its Starting card, holds it and ends the shot: no emulator starts (races come from games/clips/render_race.py).
With any sponsor real, the steps that spend or write on a chain (WRITE_STEPS) end the shot with an error unless the
script sets "real_writes": true. A step that waits (until_*) fails the shot on its timeout, keeping what was
recorded. Only an until_* step waits on a person (a World App scan the owner makes live).

The shot script (JSON) is a list of steps, or {"steps": [...], options}:
  {"press": "triangle"}                      a button: up down left right cross circle square triangle l1 r1
                                             options create (also start, select, themes); "times": N presses,
                                             "every_ms" apart (default 300)
  {"wait_ms": 1500}
  {"until_state": "scout_pick", "timeout_ms": 30000}   PB's flow on screen in that state (handler/states.py)
  {"until_screen": "HANDLER"}                the launcher on that screen (model.Screen)
  {"until_ready": true}                      every real sponsor's start-up reads are in (see waiting_for)
  {"select": "marine-drive-gp"}              Left / Right on Home until that game (id or title) is selected,
                                             "every_ms" apart (default 250)
  {"pick": "BOT-A2"}                         Up / Down on the real board until its cursor is on that runner's row
                                             (a book or a BOT label), "every_ms" apart (default 400)
  {"mark": "scout_card"}                     the next frame's time, into the sidecar
Options: "name", "splash" (false: start on Home), "greet" (false), "warm_up" (default: on with any sponsor real;
run the app until until_ready holds before the first recorded frame; off with the splash), "real_writes" (false),
"launch_hold_ms" (1000)."""
import argparse
import dataclasses
import datetime
import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
LAUNCHER = os.path.dirname(HERE)
REPO = os.path.dirname(LAUNCHER)
sys.path.insert(0, LAUNCHER)

from arca_launcher.actions import Action  # noqa: E402
from arca_launcher.handler.states import STATES  # noqa: E402
from arca_launcher.model import Screen  # noqa: E402

FPS = 30
SIZE = (800, 480)
SANDBOX = "/opt/arca-sandbox"
SOURCE_STATE = os.path.join(SANDBOX, "laptop-state.json")     # laptop.sh's --state
SOURCE_RUNS = os.path.join(SANDBOX, "runs")                   # the launcher's default --runs, as laptop.sh leaves it
RECORDER = os.path.join(SANDBOX, "recorder")
LIBRARY = os.path.join(SANDBOX, "launcher-booth")             # laptop.sh's booth library
TESTLOGS = os.path.join(SANDBOX, "devicecheck")
OUT = os.path.join(REPO, "video", "final", "rec")
FFMPEG = os.environ.get("ARCA_FFMPEG", "/mnt/c/ProgramData/chocolatey/bin/ffmpeg.exe")
# Beside the settings file, what makes the copy this console and shows what it showed: its id, the ledger, the
# sponsors' last reads, the booth link and the crash log. Never handler-resume.json (a browser hand-off in flight) or
# coach-voice.key (PB's voice is never asked from a recording).
STATE_FILES = ("console-id", "handler.json", "hedera-payto.json", "arkiv-boards.json", "booth-url.txt", "crashes.log")
PRESSES = {"up": Action.UP, "down": Action.DOWN, "left": Action.LEFT, "right": Action.RIGHT,
           "cross": Action.A, "circle": Action.B, "square": Action.X, "triangle": Action.Y,
           "l1": Action.L, "r1": Action.R, "options": Action.START, "create": Action.SELECT,
           "start": Action.START, "select": Action.SELECT, "themes": Action.THEMES}
UNTIL_MS = 30000
PRESS_EVERY_MS = 300
SELECT_EVERY_MS = 250
PICK_EVERY_MS = 400
WARM_UP_MS = 45000
PRE_ROLL = 15                     # frames run before the first recorded one (no splash): Home's art is loaded by then
LAUNCH_HOLD_MS = 1000
RPC_AGENT = "anypercent-recorder/1"   # agent_rpc's User-Agent on Arkiv's RPC
# Sponsor steps that spend testnet money, write on a chain or open a World request: refused while any sponsor is
# real unless the script sets "real_writes". Reads (a board, a run's records, a ghost already paid for) never are.
WRITE_STEPS = ("idkit_scan", "approve_scan", "check_listing", "pay", "record", "publish", "scout")
_STEP_KEYS = {"press": {"times", "every_ms"}, "wait_ms": set(), "until_state": {"timeout_ms"},
              "until_screen": {"timeout_ms"}, "until_ready": {"timeout_ms"}, "select": {"every_ms"},
              "pick": {"every_ms"}, "mark": set()}
_OPTIONS = {"name", "splash", "greet", "warm_up", "real_writes", "launch_hold_ms", "steps"}
log = logging.getLogger("record")


class ScriptError(ValueError):
    """The shot script is not one this recorder plays."""


class ShotFailed(Exception):
    """The shot stopped short: a wait timed out, or a step was refused. What was recorded is kept."""


@dataclasses.dataclass(frozen=True)
class Step:
    kind: str                     # press, wait, until_state, until_screen, until_ready, select, mark
    value: object = None          # the Action, ms, state name, Screen, game, mark name
    times: int = 1
    every_ms: int = 0
    timeout_ms: int = 0
    text: str = ""                # the step as written, for the sidecar and errors


@dataclasses.dataclass(frozen=True)
class Script:
    steps: tuple
    name: str | None = None
    splash: bool = False
    greet: bool = False
    warm_up: bool | None = None   # None: on when any sponsor is real
    real_writes: bool = False
    launch_hold_ms: int = LAUNCH_HOLD_MS


def _ms(value, what, allow_zero=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 or (value == 0 and not allow_zero):
        raise ScriptError(f"{what} must be a number of milliseconds")
    return int(value)


def parse_step(raw, i):
    """One step of the script as a Step; i is its number (from 1) for the error."""
    where = f"step {i}"
    if not isinstance(raw, dict):
        raise ScriptError(f"{where}: a step is an object, e.g. {{\"press\": \"cross\"}}")
    kinds = [k for k in raw if k in _STEP_KEYS]
    if len(kinds) != 1:
        raise ScriptError(f"{where}: needs exactly one of {', '.join(_STEP_KEYS)}")
    kind = kinds[0]
    extra = set(raw) - {kind} - _STEP_KEYS[kind]
    if extra:
        raise ScriptError(f"{where}: {kind} does not take {', '.join(sorted(extra))}")
    text = json.dumps(raw, sort_keys=True)
    value = raw[kind]
    timeout = _ms(raw.get("timeout_ms", UNTIL_MS), f"{where}: timeout_ms", allow_zero=False)
    if kind == "press":
        name = value.strip().lower() if isinstance(value, str) else None
        if name not in PRESSES:
            raise ScriptError(f"{where}: press {value!r} is not a button ({', '.join(PRESSES)})")
        times = raw.get("times", 1)
        if isinstance(times, bool) or not isinstance(times, int) or times < 1:
            raise ScriptError(f"{where}: times must be a whole number from 1")
        return Step("press", PRESSES[name], times=times,
                    every_ms=_ms(raw.get("every_ms", PRESS_EVERY_MS), f"{where}: every_ms"), text=text)
    if kind == "wait_ms":
        return Step("wait", _ms(value, f"{where}: wait_ms"), text=text)
    if kind == "until_state":
        if value not in STATES:
            raise ScriptError(f"{where}: {value!r} is not one of PB's states (handler/states.py)")
        return Step("until_state", value, timeout_ms=timeout, text=text)
    if kind == "until_screen":
        screen = next((s for s in Screen if isinstance(value, str) and value.strip().lower() in (s.name.lower(),
                                                                                               s.value)), None)
        if screen is None:
            raise ScriptError(f"{where}: {value!r} is not a screen ({', '.join(s.name for s in Screen)})")
        return Step("until_screen", screen, timeout_ms=timeout, text=text)
    if kind == "until_ready":
        if value is not True:
            raise ScriptError(f"{where}: until_ready takes true")
        return Step("until_ready", True, timeout_ms=timeout, text=text)
    if kind == "select":
        if not (isinstance(value, str) and value.strip()):
            raise ScriptError(f"{where}: select names a game by its id or title")
        return Step("select", value.strip(), every_ms=_ms(raw.get("every_ms", SELECT_EVERY_MS), f"{where}: every_ms"),
                    text=text)
    if kind == "pick":
        if not (isinstance(value, str) and value.strip()):
            raise ScriptError(f"{where}: pick names a board row's runner (a book or a BOT label)")
        return Step("pick", value.strip(), every_ms=_ms(raw.get("every_ms", PICK_EVERY_MS), f"{where}: every_ms"),
                    text=text)
    if not (isinstance(value, str) and value.strip()):
        raise ScriptError(f"{where}: a mark needs a name")
    return Step("mark", value.strip(), text=text)


def parse_script(data):
    """A shot script (a list of steps, or an object with "steps" and options) as a Script. Raises ScriptError."""
    if isinstance(data, list):
        data = {"steps": data}
    if not isinstance(data, dict):
        raise ScriptError("a shot script is a list of steps, or an object with \"steps\"")
    extra = set(data) - _OPTIONS
    if extra:
        raise ScriptError(f"unknown option {', '.join(sorted(extra))} (options: {', '.join(sorted(_OPTIONS))})")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ScriptError("the script has no steps")
    for flag in ("splash", "greet", "real_writes"):
        if not isinstance(data.get(flag, False), bool):
            raise ScriptError(f"{flag} is true or false")
    warm = data.get("warm_up")
    if warm is not None and not isinstance(warm, bool):
        raise ScriptError("warm_up is true or false")
    name = data.get("name")
    if name is not None and not (isinstance(name, str) and name.strip()
                                 and all(c.isalnum() or c in "-_." for c in name)):
        raise ScriptError("name is a file name: letters, digits, - _ .")
    return Script(steps=tuple(parse_step(s, i) for i, s in enumerate(steps, start=1)), name=name,
                  splash=data.get("splash", False), greet=data.get("greet", False), warm_up=warm,
                  real_writes=data.get("real_writes", False),
                  launch_hold_ms=_ms(data.get("launch_hold_ms", LAUNCH_HOLD_MS), "launch_hold_ms"))


def load_script(path):
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except ValueError as e:
            raise ScriptError(f"{path} is not JSON: {e}") from None
    return parse_script(data)


def frames_for(ms, fps=FPS):
    """Whole frames that cover ms (at least one for any wait above zero)."""
    return 0 if ms <= 0 else max(1, round(ms * fps / 1000))


# ---- the console's state, copied ------------------------------------------------------------------------------------

def prepare_state(src_state, src_runs, dest, today, greet=False):
    """A fresh copy of a console's state in dest, made once per run: its settings file (as laptop-state.json), the
    STATE_FILES beside it and its runs folder; whatever an earlier run left there goes first. PB's greeting and book
    offer are marked done for today unless greet. Returns (state path, runs dir, run dir). Nothing is ever written
    beside src_state or in src_runs."""
    src_dir = os.path.dirname(os.path.abspath(src_state))
    dest = os.path.abspath(dest)
    if os.path.realpath(dest) == os.path.realpath(src_dir):
        raise ValueError("the recorder's copy must not be the console's own state directory")
    if not os.path.isfile(src_state):
        raise FileNotFoundError(f"no console state at {src_state}")
    os.makedirs(dest, exist_ok=True)
    state = os.path.join(dest, "laptop-state.json")
    runs, run = os.path.join(dest, "runs"), os.path.join(dest, "run")
    for name in STATE_FILES + ("laptop-state.json", "handler-resume.json"):
        try:
            os.remove(os.path.join(dest, name))
        except FileNotFoundError:
            pass
    for d in (runs, run):
        if os.path.isdir(d):
            shutil.rmtree(d)
    with open(src_state, encoding="utf-8") as f:
        data = json.load(f)
    if not greet and isinstance(data, dict):
        data["coach_greeted"] = data["handler_offered"] = today
    with open(state, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    for name in STATE_FILES:
        if os.path.isfile(os.path.join(src_dir, name)):
            shutil.copy2(os.path.join(src_dir, name), os.path.join(dest, name))
    if not os.path.isfile(os.path.join(dest, "console-id")):
        log.warning("%s has no console-id: the recorder is a new console, not that one", src_dir)
    if os.path.isdir(src_runs):
        shutil.copytree(src_runs, runs)
    else:
        os.makedirs(runs)
    os.makedirs(run)
    return state, runs, run


# ---- the launcher, recording ----------------------------------------------------------------------------------------

def no_pads():
    """The recorder never opens a pad: SDL's joystick and game controller systems are never started."""
    import pygame
    import pygame._sdl2.controller as controller

    def refuse():
        raise RuntimeError("no pads while recording")
    pygame.joystick.init = lambda: None
    pygame.joystick.get_count = lambda: 0
    controller.init = refuse


def agent_rpc(rpc_url, agent=RPC_AGENT):
    """The console's Arkiv RPC transport (arkiv_rpc.rpc_transport: no proxy, its reply cap) with a User-Agent of its
    own. Rabdi's public RPC is behind Cloudflare, which on 6 Nov 2026 answered urllib's default agent
    ("Python-urllib/3.12") with 403 Forbidden on every request, and the same request under any other agent with the
    board: the launcher's own reads failed ("Arkiv not answering") while this one worked."""
    from arca_launcher.handler import arkiv_rpc
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def send(method, params, timeout_s):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
        request = urllib.request.Request(rpc_url, data=body, method="POST",
                                         headers={"Content-Type": "application/json", "Accept": "application/json",
                                                  "User-Agent": agent})
        with opener.open(request, timeout=timeout_s) as reply:
            raw = reply.read(arkiv_rpc.MAX_REPLY + 1)
        if len(raw) > arkiv_rpc.MAX_REPLY:
            raise arkiv_rpc.RpcError("reply too large")
        return json.loads(raw.decode("utf-8"))
    return send


def recording_classes():
    """RecorderHardware and RecordingApp, made on first use: they need pygame and the launcher's App."""
    import pygame
    from arca_launcher.app import App
    from arca_launcher.hw import LINK, Hardware

    class RecorderHardware(Hardware):
        """The laptop's hardware, minus everything that reaches outside the recording: a chain link goes to
        on_link (the sidecar), never to Edge; no mixer, backlight, app or power change."""
        on_link = None

        def open_url(self, url):
            if not (isinstance(url, str) and LINK.fullmatch(url)):
                return None
            if self.on_link is not None:
                self.on_link(url)
            return "window"                        # what the laptop says: "Opened in a window"

        def set_volume(self, pct):
            return False

        def set_brightness(self, pct):
            return False

        def start_app(self, name):
            return False

        def power_off(self):
            return False

    class RecordingApp(App):
        """The launcher as it runs, except that a launch draws its Starting card, keeps it (launch_card) and stops
        there: no emulator, no save written, Home left as it was."""
        launched = None
        launch_card = None

        def frame(self, dt, actions=(), touches=()):
            pygame.event.get()                     # nothing reads the dummy window's events; never let them pile up
            return super().frame(dt, actions, touches)

        def launch(self, game, resume=False, ghost=None):
            race = self.handler.race if self.handler is not None else None
            self.display.views.starting(game)
            self.display.renderer.present()
            self.launch_card = self.capture()
            self.launched = {"game": game.id, "title": game.title, "resume": bool(resume),
                             "race": race is not None, "seller": race[1] if race else None,
                             "ghost": ghost is not None}

        def capture(self):
            """The screen as last presented, as 800 x 480 RGB bytes."""
            return pygame.image.tobytes(self.display.renderer.to_surface(), "RGB")

        def waiting_for(self):
            """What the real sponsors' start-up reads still wait for ([]: nothing). World: the console's binding.
            Arkiv: a fresh read of every arcade game's board, and the explorer /arkiv/config names (a run's records
            link to it). Hedera: the book's payout account."""
            s, out = self.sponsors, []
            if not s.mocked("world") and getattr(s, "console_state", lambda: None)() is None:
                out.append("World's console binding")
            if not s.mocked("board"):
                for gid in dict.fromkeys(g.arcade["id"] for g in self.nav.games if g.arcade):
                    read = s.board(gid, look=False)
                    if read is None or read.stale:
                        out.append(f"the {gid} board")
                if getattr(s, "explorer_origin", None) is None:
                    out.append("Arkiv's explorer (/arkiv/config)")
            book = self.handler.ledger.book if self.handler is not None else None
            if not s.mocked("third") and book and getattr(s, "pay_to", lambda b: None)(book) is None:
                out.append(f"{book}'s {s.names.third} account")
            return out

    return RecorderHardware, RecordingApp


class GuardedSponsors:
    """The app's sponsors, with WRITE_STEPS refused (ShotFailed) while any sponsor is real, unless allowed."""

    def __init__(self, inner, allow):
        self._inner = inner
        self._allow = allow

    def real(self):
        return any(not self._inner.mocked(s) for s in ("world", "board", "third"))

    def begin(self, step, payload):
        if step in WRITE_STEPS and not self._allow and self.real():
            raise ShotFailed(f"PB began {step!r}, a real sponsor write (money, a chain or a World request); "
                             "set \"real_writes\": true in the script to record it")
        return self._inner.begin(step, payload)

    def __getattr__(self, name):
        return getattr(self._inner, name)


# ---- frames to disk, then video -------------------------------------------------------------------------------------

class PngFrames:
    """Frames as PNG files (000000.png ...) in folder, written on worker threads so the frame loop never waits on
    zlib (a full backlog does make it wait: that shows as lag in the sidecar)."""

    def __init__(self, folder, size=SIZE, workers=2, backlog=90):
        from PIL import Image
        self._image = Image
        self.folder, self.size, self.count = folder, size, 0
        if os.path.isdir(folder):
            shutil.rmtree(folder)
        os.makedirs(folder)
        self._q = queue.Queue(maxsize=backlog)
        self._error = None
        self._threads = [threading.Thread(target=self._work, daemon=True) for _ in range(workers)]
        for t in self._threads:
            t.start()

    def path(self, i):
        return os.path.join(self.folder, "%06d.png" % i)

    def put(self, rgb):
        self._q.put((self.count, rgb))
        self.count += 1

    def _work(self):
        while True:
            item = self._q.get()
            if item is None:
                return
            i, rgb = item
            try:
                self._image.frombuffer("RGB", self.size, rgb, "raw", "RGB", 0, 1).save(self.path(i), compress_level=1)
            except Exception as e:                 # kept for close(): a frame that is not on disk spoils the video
                self._error = self._error or e

    def close(self):
        for _ in self._threads:
            self._q.put(None)
        for t in self._threads:
            t.join()
        if self._error is not None:
            raise self._error


def windows_path(path):
    out = subprocess.run(["wslpath", "-w", path], capture_output=True, text=True, check=True).stdout.strip()
    return out or path


def encode(frames, out_mp4, fps=FPS, ffmpeg=FFMPEG):
    """The PNG frames into an H.264 mp4 (yuv420p, BT.709, the frames' own size), through ffmpeg's stdin. A Windows
    ffmpeg.exe (the default: WSL has none) is given the output as a Windows path."""
    target = windows_path(out_mp4) if ffmpeg.lower().endswith(".exe") else out_mp4
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(fps),
           "-c:v", "png", "-i", "-", "-vf", "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd,"
           "format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "12", "-tune", "animation",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
           "-r", str(fps), "-movflags", "+faststart", target]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(frames.count):
            with open(frames.path(i), "rb") as f:
                p.stdin.write(f.read())
        p.stdin.close()
    except BrokenPipeError:
        pass
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed ({p.returncode}) on {out_mp4}")


# ---- the shot -------------------------------------------------------------------------------------------------------

class Recorder:
    """Plays a Script on app (a RecordingApp, or anything with its frame / capture / waiting_for / launched /
    launch_card / nav), handing each frame's RGB bytes to sink.put. clock and sleep are the wall clock's."""

    def __init__(self, app, script, sink, fps=FPS, clock=time.monotonic, sleep=time.sleep):
        self.app, self.script, self.sink, self.fps = app, script, sink, fps
        self.clock, self.sleep = clock, sleep
        self.k = 0                                 # frames recorded
        self.t0 = None
        self.max_lag_ms = 0.0
        self.marks, self.links, self.log = [], [], []
        self.skipped = []
        self.warm_up_s = 0.0

    # time
    def _dt(self, k):
        return round((k + 1) * 1000 / self.fps) - round(k * 1000 / self.fps)

    def _pace(self, t0, k):
        """Wait until frame k's time (never draw ahead of the wall clock); note how late it is when behind."""
        due = t0 + k / self.fps
        now = self.clock()
        if now < due:
            self.sleep(due - now)
        else:
            self.max_lag_ms = max(self.max_lag_ms, (now - due) * 1000)

    def frame(self, actions=()):
        if self.t0 is None:
            self.t0 = self.clock()
        self._pace(self.t0, self.k)
        self.app.frame(self._dt(self.k), list(actions), ())
        if self.app.launched is not None:
            for _ in range(max(1, frames_for(self.script.launch_hold_ms, self.fps))):
                self.sink.put(self.app.launch_card)
                self.k += 1
            return
        self.sink.put(self.app.capture())
        self.k += 1

    @property
    def t(self):
        return round(self.k / self.fps, 3)

    # the steps
    def warm_up(self, timeout_ms=WARM_UP_MS, wait=True, min_frames=PRE_ROLL):
        """Run the app, unrecorded, for min_frames (Home's first frames load its art: never in the video) and, with
        wait, until the real sponsors' start-up reads are in (ShotFailed after timeout_ms)."""
        start, n = self.clock(), 0
        while n < min_frames or (wait and self.app.waiting_for()):
            if n >= frames_for(timeout_ms, self.fps):
                raise ShotFailed(f"warming up: after {timeout_ms / 1000:.0f} s still waiting for "
                                 + ", ".join(self.app.waiting_for()))
            self._pace(start, n)
            self.app.frame(self._dt(n), [], ())
            n += 1
        self.warm_up_s = round(self.clock() - start, 1)
        self.max_lag_ms = 0.0
        if hasattr(self.app, "idle_ms"):
            self.app.idle_ms = 0                   # the shot gets attract mode's whole minute, as a fresh start would

    def run(self):
        steps = self.script.steps
        for i, step in enumerate(steps):
            if self.app.launched is not None:
                self.skipped = [s.text for s in steps[i:]]
                break
            first = self.k
            try:
                self.do(step)
            finally:
                self.log.append({"step": i + 1, "do": step.text, "frames": [first, self.k]})

    def do(self, step):
        if step.kind == "press":
            for j in range(step.times):
                if j:
                    self.wait(step.every_ms)
                if self.app.launched is not None:
                    return
                self.frame([step.value])
        elif step.kind == "wait":
            self.wait(step.value)
        elif step.kind == "mark":
            self.marks.append({"mark": step.value, "frame": self.k, "t": self.t})
        elif step.kind == "select":
            self.select(step)
        elif step.kind == "pick":
            self.pick(step)
        else:
            self.until(step)

    def wait(self, ms):
        for _ in range(frames_for(ms, self.fps)):
            if self.app.launched is not None:
                return
            self.frame()

    def until(self, step):
        if step.kind == "until_state":
            test, what = (lambda: self._state() == step.value), f"PB's {step.value!r} screen"
        elif step.kind == "until_screen":
            test, what = (lambda: self.app.nav.screen is step.value), f"the {step.value.name} screen"
        else:
            test, what = (lambda: not self.app.waiting_for()), "the sponsors' start-up reads"
        give_up = self.k + frames_for(step.timeout_ms, self.fps)
        while not test():
            if self.app.launched is not None:
                return
            if self.k >= give_up:
                now = self._state() or self.app.nav.screen.name
                extra = (("; still waiting for " + ", ".join(self.app.waiting_for()))
                         if step.kind == "until_ready" else "")
                raise ShotFailed(f"{step.text}: {what} did not come in {step.timeout_ms / 1000:.1f} s "
                                 f"(on {now} at {self.t:.1f} s){extra}")
            self.frame()

    def _state(self):
        nav = self.app.nav
        return nav.handler.state.name if nav.screen is Screen.HANDLER and nav.handler is not None else None

    def select(self, step):
        """Left / Right on Home, one press every every_ms, until the named game is the selected tile."""
        nav, want = self.app.nav, step.value.casefold()
        row = [g for g in nav.row]
        target = next((i for i, g in enumerate(row) if g is not None and want in (g.id.casefold(),
                                                                                g.title.casefold())), None)
        if target is None:
            raise ShotFailed(f"{step.text}: no game {step.value!r} on Home")
        for _ in range(len(row) + 1):
            if nav.stack != [Screen.HOME] or nav.home_focus != "tiles":
                raise ShotFailed(f"{step.text}: select works on Home's tiles (on {nav.screen.name})")
            if nav.row_index == target:
                return
            self.frame([Action.RIGHT if nav.row_index < target else Action.LEFT])
            if nav.row_index != target:
                self.wait(step.every_ms)
            if self.app.launched is not None:
                return
        raise ShotFailed(f"{step.text}: the selection never reached {step.value!r}")

    def pick(self, step):
        """Up / Down on the real board, one press every every_ms, until its cursor is on the named runner's row."""
        want = step.value.casefold()
        for _ in range(64):
            flow = self.app.nav.handler
            if self._state() not in ("board", "board_new") or flow.board_cursor is None:
                raise ShotFailed(f"{step.text}: pick works on the real board, which has a cursor "
                                 f"(on {self._state() or self.app.nav.screen.name})")
            target = next((i for i, row in enumerate(flow.board_shown) if (row.name or "").casefold() == want), None)
            if target is None:
                raise ShotFailed(f"{step.text}: no {step.value!r} row on the board")
            if flow.board_cursor == target:
                return
            self.frame([Action.UP if flow.board_cursor > target else Action.DOWN])
            if self.app.launched is not None:
                return
            if flow.board_cursor != target:
                self.wait(step.every_ms)
        raise ShotFailed(f"{step.text}: the cursor never reached {step.value!r}")

    def link(self, url):
        """A chain link PB asked the laptop to open: logged with the chain row it came from."""
        entry = {"url": url, "frame": self.k, "t": self.t}
        flow = self.app.nav.handler
        rows = (flow.ctx.get("chain") or []) if flow is not None else []
        row = next((r for r in rows if r.get("url") == url), None)
        if row is not None:
            entry.update(label=row.get("label"), value=row.get("value"))
        self.links.append(entry)


def sponsors_line(app):
    return {s: ("mock" if app.sponsors.mocked(s) else "real") for s in ("world", "board", "third")}


def main(argv=None):
    p = argparse.ArgumentParser(prog="record.py", description="Record the real launcher from a shot script.")
    p.add_argument("script", help="the shot script (JSON)")
    p.add_argument("--name", help="the shot's name: <out>/<name>.mp4 and .json (default: the script's, else its "
                                  "file's)")
    p.add_argument("--out", default=OUT, help=f"where the video and sidecar go (default {OUT})")
    p.add_argument("--state", default=SOURCE_STATE, help=f"the console state to copy (default {SOURCE_STATE})")
    p.add_argument("--runs", default=SOURCE_RUNS, help=f"that console's runs folder (default {SOURCE_RUNS})")
    p.add_argument("--copy", default=RECORDER, help=f"where the copy lives (default {RECORDER})")
    p.add_argument("--keep-frames", action="store_true", help="keep the PNG frames after encoding")
    p.add_argument("--console-rpc", action="store_true",
                   help="read Arkiv with the launcher's own RPC transport, not agent_rpc's (see agent_rpc)")
    p.epilog = ("After --: launcher flags, as laptop.sh passes them (--world-bridge URL, --arkiv-checker 0x..., "
                "--hedera).")
    argv = list(sys.argv[1:] if argv is None else argv)
    cut = argv.index("--") if "--" in argv else len(argv)
    a, extra = p.parse_args(argv[:cut]), argv[cut + 1:]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", stream=sys.stderr)
    try:
        script = load_script(a.script)
    except (OSError, ScriptError) as e:
        print(f"record: {e}", file=sys.stderr)
        return 2
    name = a.name or script.name or os.path.splitext(os.path.basename(a.script))[0]

    from arca_launcher.__main__ import build_config
    cfg = build_config(["--library", LIBRARY, "--testlogs", TESTLOGS] + extra)
    if not os.path.isfile(os.path.join(cfg.library_dir, "library.json")):
        print(f"record: no library at {cfg.library_dir}: start launcher/dev/laptop.sh once (it builds the booth "
              "library), or pass -- --library DIR", file=sys.stderr)
        return 2
    today = time.strftime("%Y-%m-%d")
    state, runs, run = prepare_state(a.state, a.runs, a.copy, today, greet=script.greet)
    cfg = dataclasses.replace(cfg, state_path=state, runs_dir=runs, run_dir=run, scale=1, fullscreen=False,
                              show_fps=False, splash=script.splash,
                              coach_voice_key=os.path.join(a.copy, "coach-voice.key"))
    rpc_used = None
    if cfg.world_bridge and cfg.arkiv_checker:
        rpc_used = f"{cfg.arkiv_rpc} (the launcher's transport)"
        if not a.console_rpc:
            rpc_used = f"{cfg.arkiv_rpc} (agent_rpc, User-Agent {RPC_AGENT})"
            cfg = dataclasses.replace(cfg, arkiv_rpc=agent_rpc(cfg.arkiv_rpc))
    no_pads()
    RecorderHardware, RecordingApp = recording_classes()
    hw = RecorderHardware(run_dir=run)
    app = RecordingApp(cfg, hw=hw)
    app.sponsors = GuardedSponsors(app.sponsors, script.real_writes)
    frames = PngFrames(os.path.join(a.copy, "frames", name))
    rec = Recorder(app, script, frames)
    hw.on_link = rec.link
    os.makedirs(a.out, exist_ok=True)
    mp4, sidecar = os.path.join(a.out, name + ".mp4"), os.path.join(a.out, name + ".json")
    started, error = datetime.datetime.now().astimezone().isoformat(timespec="seconds"), None
    wall = time.monotonic()
    warm = script.warm_up if script.warm_up is not None else app.sponsors.real()
    try:
        if not script.splash:                      # the splash is the first thing on screen: nothing runs before it
            if warm:
                print(f"record: warming up ({', '.join(app.waiting_for()) or 'nothing to wait for'})", flush=True)
            rec.warm_up(wait=warm)
        print(f"record: {name}: {len(script.steps)} steps", flush=True)
        wall = time.monotonic()
        rec.run()
    except ShotFailed as e:
        error = str(e)
    except KeyboardInterrupt:
        error = "stopped by hand"
    except Exception as e:                         # a launcher crash: keep the frames and say what it was
        log.exception("the launcher failed while recording")
        error = f"{type(e).__name__}: {e}"
    finally:
        real_s = time.monotonic() - wall
        try:
            info = {"sponsors": sponsors_line(app),
                    "console": app.sponsors.console_state() if hasattr(app.sponsors, "console_state") else None,
                    "book": app.handler.ledger.book if app.handler is not None else None}
        except Exception:
            info = {}
        try:
            app.close()
        finally:
            frames.close()
    if frames.count:
        print(f"record: encoding {frames.count} frames to {mp4}", flush=True)
        try:
            encode(frames, mp4)
            if not a.keep_frames:
                shutil.rmtree(frames.folder)
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
            error = (error + "; " if error else "") + f"encoding: {e} (the frames stay in {frames.folder})"
    side = {"shot": name, "script": os.path.abspath(a.script), "video": os.path.basename(mp4) if frames.count else None,
            "recorded_at": started, "fps": FPS, "size": list(SIZE), "frames": frames.count,
            "duration_s": round(frames.count / FPS, 3), "real_s": round(real_s, 2),
            "max_lag_ms": round(rec.max_lag_ms, 1), "warm_up_s": rec.warm_up_s, **info, "arkiv_rpc": rpc_used,
            "state_from": os.path.abspath(a.state), "marks": rec.marks, "links": rec.links, "launch": app.launched,
            "ended": "error" if error else "launch" if app.launched else "script", "error": error,
            "skipped": rec.skipped, "steps": rec.log}
    if app.launched:
        side["launch"] = dict(app.launched, frame=rec.k - max(1, frames_for(script.launch_hold_ms)))
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump(side, f, indent=1)
    print(f"record: {name}: {frames.count} frames ({frames.count / FPS:.1f} s, wall {real_s:.1f} s, "
          f"max lag {rec.max_lag_ms:.0f} ms) -> {sidecar}", flush=True)
    if error:
        print(f"record: FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
