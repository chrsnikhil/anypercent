#!/bin/bash
# Mount the device image and step inside it (arm64 via qemu, no Pi needed).
#   pios_enter.sh                 interactive shell inside the Pi OS
#   pios_enter.sh --run 'cmd'     run one command inside and return
# Leave with pios_leave.sh (always, before flashing or copying the image).
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
img="$PIOS/arca-device.img"
root="$PIOS/root"
[ -f "$img" ] || { echo "no image; run 03_pios.sh first"; exit 1; }

if ! mountpoint -q "$root"; then
  loop=$(losetup --find --show --partscan "$img")
  echo "$loop" > "$PIOS/.loop"
  # first mount after growing: fix the filesystem up to the new partition size
  e2fsck -pf "${loop}p2" >/dev/null 2>&1 || true
  resize2fs "${loop}p2" >/dev/null 2>&1 || true
  mkdir -p "$root"
  mount "${loop}p2" "$root"
  mount "${loop}p1" "$root/boot/firmware"
  for d in dev dev/pts proc sys run; do mount --bind "/$d" "$root/$d"; done
  # name resolution inside the chroot
  cp --remove-destination /etc/resolv.conf "$root/etc/resolv.conf"
  # the sandbox (games, scripts) visible inside at /sandbox
  mkdir -p "$root/sandbox"; mount --bind "$SANDBOX" "$root/sandbox"
fi

if [ "${1:-}" = "--run" ]; then
  chroot "$root" /usr/bin/env -i HOME=/root PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin bash -lc "$2"
else
  echo "Inside Raspberry Pi OS (aarch64 via qemu). 'exit' to return; then run pios_leave.sh."
  chroot "$root" /usr/bin/env -i HOME=/root TERM="${TERM:-xterm}" PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin bash -l
fi
