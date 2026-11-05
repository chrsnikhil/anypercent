"""python -m arca_launcher [--library DIR] [--scale 1|2|3] [--emulator mgba|retroarch] [--fullscreen] [--fps]
[--no-handler] [--testlogs DIR]"""
import argparse
import os
import sys

from . import settings
from .app import App, Config
from .input import parse_joy_map


def build_config(argv=None):
    p = argparse.ArgumentParser(prog="arca_launcher", description="Any% game launcher")
    p.add_argument("--library", default=os.environ.get("ARCA_LIBRARY", "/opt/arca-sandbox/launcher"))
    p.add_argument("--state", default=settings.default_path())
    p.add_argument("--runs", default="/opt/arca-sandbox/runs", help="arcade runs: verified queue and best logs")
    p.add_argument("--emulator", choices=("mgba", "retroarch"), default="mgba")
    p.add_argument("--retroarch-core", default="/usr/lib/x86_64-linux-gnu/libretro/mgba_libretro.so")
    p.add_argument("--retroarch-cfg",
                   default=os.path.join(os.path.expanduser("~"), ".config", "arca-launcher", "retroarch.cfg"))
    p.add_argument("--overlay", default="/opt/anypercent/overlays/gamepad.cfg",
                   help="RetroArch overlay for the On-screen controls setting")
    p.add_argument("--scale", type=int, choices=(1, 2, 3), default=1)
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--fps", action="store_true", help="print frames per second every 5 seconds")
    p.add_argument("--joy-map", type=parse_joy_map, default=None, metavar="a=0,b=1,...",
                   help="gamepad button numbers, e.g. a=0,b=1,l=4,r=5,select=6,start=7 (the default)")
    p.add_argument("--haptics", default=None, metavar="PCM",
                   help="ALSA pcm for game audio that also drives controller rumble (device/asoundrc)")
    p.add_argument("--no-splash", dest="splash", action="store_false", help="skip the start-up splash")
    p.add_argument("--no-coach", dest="coach", action="store_false", help="no PB, the coach")
    p.add_argument("--no-handler", dest="handler", action="store_false", help="no PB the handler (Triangle)")
    p.add_argument("--testlogs", default="/opt/anypercent/testlogs",
                   help="each arcade game's shipped test log, <ID>.acl: the handler's board and target ghost")
    p.add_argument("--coach-voice-key", default=None, metavar="FILE",
                   help="a file holding an Anthropic API key, for PB's optional voice (default: coach-voice.key "
                        "beside the --state file; no file, no voice)")
    a = p.parse_args(argv)
    return Config(library_dir=a.library, state_path=a.state, emulator=a.emulator, retroarch_core=a.retroarch_core,
                  retroarch_cfg=a.retroarch_cfg, scale=a.scale, fullscreen=a.fullscreen, show_fps=a.fps,
                  joy_map=a.joy_map, splash=a.splash, runs_dir=a.runs, overlay=a.overlay,
                  haptics=a.haptics, coach=a.coach, handler=a.handler, handler_warm=a.handler, testlogs_dir=a.testlogs,
                  coach_voice_key=a.coach_voice_key or os.path.join(os.path.dirname(a.state), "coach-voice.key"))


def main(argv=None):
    app = App(build_config(argv))
    try:
        return app.run()
    finally:
        app.close()        # after a crash too: queued background replays are dropped, so the restart is not held up


if __name__ == "__main__":
    sys.exit(main())
