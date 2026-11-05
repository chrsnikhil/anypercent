"""Start a game in an emulator and wait for it to finish.

Sandbox: mGBA, paced by the display (WSLg's audio starves mGBA's default audio sync).
Device: RetroArch with the pinned mGBA core; L + R quits back to the launcher. RetroArch keeps each game's
save next to its ROM (<rom>.srm), where the arcade bridge reads and writes it.

On-screen controls (a launcher setting, off by default): RetroArch draws a translucent gamepad over the game (the
overlay made by device/overlay/make_overlay.py) as a picture only, and the touchpad service (touchpad.py), running
only while RetroArch runs, turns the fingers on it into the keys RetroArch maps to player 1, so the core sees the
same joypad buttons the real buttons press, from any number of fingers at once. The menu stays button-only either
way."""
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass

from . import touchpad as touchpad_service

log = logging.getLogger(__name__)

RETROARCH_CFG = """\
# written by the Any% launcher
input_quit_gamepad_combo = "6"
input_player1_analog_dpad_mode = "1"
quit_press_twice = "false"
config_save_on_exit = "false"
pause_nonactive = "false"
audio_sync = "{audio_sync}"
video_vsync = "true"
savefiles_in_content_dir = "true"
sort_savefiles_enable = "false"
sort_savefiles_by_content_enable = "false"
menu_mouse_enable = "false"
menu_pointer_enable = "false"
libretro_directory = "/usr/lib/aarch64-linux-gnu/libretro"
libretro_info_path = "/usr/share/libretro/info"
core_info_cache_enable = "false"
network_cmd_enable = "true"
network_cmd_port = "55355"
savestates_in_content_dir = "true"
sort_savestates_enable = "false"
sort_savestates_by_content_enable = "false"
savestate_auto_index = "false"
savestate_auto_save = "{auto_save}"
savestate_auto_load = "{auto_load}"
"""
# Save states (2026-10-04): a game keeps its place when it quits (the L + R combo, or the home key's QUIT over the
# network command port) as <rom>.state.auto beside the ROM, and Continue loads it. RetroArch only allows states once
# it can match the core to its .info file, hence the cores and info folders. Arcade games never get states: one
# would let a verified run be rewound.

NO_TOUCH = """input_overlay_enable = "false"
input_touch_enable = "false"
"""

TOUCH_OVERLAY = """input_overlay_enable = "true"
input_overlay = "{overlay}"
input_overlay_opacity = "{opacity}"
input_overlay_scale_landscape = "1.000000"
input_overlay_auto_scale = "false"
input_overlay_enable_autopreferred = "false"
input_overlay_hide_in_menu = "true"
input_overlay_hide_when_gamepad_connected = "false"
input_overlay_show_mouse_cursor = "false"
input_overlay_show_inputs = "0"
input_overlay_pointer_enable = "false"
input_touch_enable = "false"
"""
OVERLAY_OPACITY = 0.45


@dataclass(frozen=True)
class RunResult:
    ok: bool
    code: int | None = None
    error: str | None = None


def mgba_command(rom, exe=None, smooth=False):
    exe = exe or shutil.which("mgba-qt") or shutil.which("mgba") or "mgba-qt"
    cmd = [exe, "-C", "audioSync=0", "-C", "videoSync=1"]
    if smooth:
        cmd += ["-C", "resampleVideo=1"]      # bilinear filter (SHIP IT!'s pre-rendered art)
    return cmd + [rom]


def retroarch_command(rom, core, cfg_path, exe=None, fullscreen=False):
    cmd = [exe or shutil.which("retroarch") or "retroarch", "-L", core, "--appendconfig", cfg_path]
    if fullscreen:
        cmd.append("--fullscreen")
    return cmd + [rom]


def state_path(rom):
    """Where RetroArch keeps a game's place: <rom without extension>.state.auto, beside the ROM."""
    return os.path.splitext(rom)[0] + ".state.auto"


def write_retroarch_cfg(path, audio_sync=False, touch_controls=False, overlay=None, audio_device=None, states=False,
                        resume=False):
    """The per-launch settings. touch_controls needs an overlay file; without one the game stays button-only.
    audio_device: an ALSA pcm to play through (the haptics tee, device/asoundrc: rumble from the game's sound).
    states: the game keeps its place on quit; resume: it starts from that place (both off for arcade runs)."""
    on = lambda b: "true" if b else "false"
    text = RETROARCH_CFG.format(audio_sync=on(audio_sync), auto_save=on(states), auto_load=on(states and resume))
    if audio_device:
        text += f'audio_driver = "alsa"\naudio_device = "{audio_device}"\n'
    if touch_controls and overlay:
        text += TOUCH_OVERLAY.format(overlay=overlay, opacity=f"{OVERLAY_OPACITY:.6f}")
    else:
        text += NO_TOUCH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def run_command(cmd):
    try:
        code = subprocess.run(cmd).returncode
    except OSError as e:
        return RunResult(False, None, f"Cannot start {cmd[0]}: {e.strerror or e}")
    return RunResult(code == 0, code, None if code == 0 else f"{os.path.basename(cmd[0])} exited with code {code}")


class Runner:
    def __init__(self, emulator="mgba", retroarch_core=None, retroarch_cfg=None, fullscreen=False, audio_sync=False,
                 overlay=None, touchpad=None, haptics=None):
        self.emulator = emulator
        self.retroarch_core = retroarch_core
        self.retroarch_cfg = retroarch_cfg
        self.fullscreen = fullscreen
        self.audio_sync = audio_sync
        self.overlay = overlay                 # RetroArch overlay .cfg for on-screen controls
        self.touch_controls = False            # the launcher setting; read at each launch
        self.haptics = haptics                 # ALSA pcm that also drives the pad's rumble, or None
        self.touchpad = touchpad or touchpad_service.start  # overlay -> a running service with stop()

    def command(self, rom, resume=False, states=False):
        if self.emulator == "mgba":
            return mgba_command(rom)
        if self.emulator == "retroarch":
            write_retroarch_cfg(self.retroarch_cfg, self.audio_sync, self.touch_controls, self.overlay, self.haptics,
                                states=states, resume=resume)
            return retroarch_command(rom, self.retroarch_core, self.retroarch_cfg, fullscreen=self.fullscreen)
        raise ValueError(f"unknown emulator {self.emulator!r}")

    def run(self, rom, resume=False, states=False):
        cmd = self.command(rom, resume, states)
        pad = None
        if self.emulator == "retroarch" and self.touch_controls and self.overlay:
            try:
                pad = self.touchpad(self.overlay)
            except Exception:
                log.exception("on-screen controls: the touchpad service did not start")
        try:
            return run_command(cmd)
        finally:
            if pad is not None:
                try:
                    pad.stop()
                except Exception:
                    log.exception("on-screen controls: stopping the touchpad service failed")
