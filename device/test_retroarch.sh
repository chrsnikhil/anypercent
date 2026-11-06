#!/bin/bash
# Check an arcade game starts in RetroArch full screen exactly as the launcher starts it, and grab a frame.
#   sudo bash test_retroarch.sh [ROM] [SECONDS]      (stops the launcher service while it runs, then restarts it)
set -u
ROM=${1:-/opt/anypercent/games/built/segfault.gba}
WAIT=${2:-15}
CORE=/usr/lib/aarch64-linux-gnu/libretro/mgba_libretro.so
CFG=/home/anypercent/.config/anypercent/retroarch-launch.cfg
DIR=$(cd "$(dirname "$0")" && pwd)
systemctl stop anypercent-launcher
cd /opt/anypercent/src/launcher
CMD=$(sudo -u anypercent /opt/anypercent/venv/bin/python -c "
import shlex
from arca_launcher.runner import Runner
print(shlex.join(Runner('retroarch', '$CORE', '$CFG', fullscreen=True, audio_sync=True).command('$ROM')))")
echo "command: $CMD"
sudo -u anypercent HOME=/home/anypercent bash -c "exec $CMD" > /tmp/retroarch-test.log 2>&1 &
sleep "$WAIT"
pgrep -a retroarch || echo "retroarch is not running"
python3 "$DIR/drmgrab.py" /tmp/retroarch.png
pkill -INT retroarch; sleep 2; pkill -9 retroarch 2>/dev/null
tail -5 /tmp/retroarch-test.log
systemctl start anypercent-launcher
