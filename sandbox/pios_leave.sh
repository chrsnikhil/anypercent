#!/bin/bash
# Unmount the device image cleanly (safe to run twice).
source "$(dirname "$0")/00_env.sh"
root="$PIOS/root"
for d in sandbox run sys proc dev/pts dev boot/firmware; do
  mountpoint -q "$root/$d" && umount -l "$root/$d"
done
mountpoint -q "$root" && umount "$root"
if [ -f "$PIOS/.loop" ]; then losetup -d "$(cat "$PIOS/.loop")" 2>/dev/null; rm -f "$PIOS/.loop"; fi
sync
echo "image unmounted: $PIOS/arca-device.img"
