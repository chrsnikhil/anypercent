#!/bin/bash
# Boot-to-launcher timing.   sudo bash boot_time.sh
#  1. when (seconds after the kernel started) this boot's launcher process started (/proc/PID/stat);
#  2. how long the launcher takes from process start to owning the display: restarts the service and polls every
#     20 ms until the process holds /dev/dri/card0 (the splash is drawn right after).
# Boot-to-launcher = 1 + 2.
P=$(pgrep -u anypercent -f 'python -m arca_launcher' | head -1)
[ -n "$P" ] || { echo "launcher not running"; exit 1; }
systemd-analyze | head -1
awk -v hz="$(getconf CLK_TCK)" '{printf "launcher process started: %.2f s after boot\n", $22 / hz}' /proc/$P/stat
systemctl restart anypercent-launcher
t0=$(date +%s.%N)
for _ in $(seq 1 1000); do
  P=$(pgrep -u anypercent -f 'python -m arca_launcher' | head -1)
  if [ -n "$P" ] && ls -l /proc/$P/fd 2>/dev/null | grep -q /dev/dri/card0; then
    python3 -c "import sys; print('process start -> display open: %.2f s' % (float(sys.argv[2]) - float(sys.argv[1])))" \
      "$t0" "$(date +%s.%N)"
    exit 0
  fi
  sleep 0.02
done
echo "the launcher did not open the display within 20 s"; exit 1
