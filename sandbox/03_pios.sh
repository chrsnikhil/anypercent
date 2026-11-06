#!/bin/bash
# Download the REAL device OS -- Raspberry Pi OS Lite 64-bit, latest -- verify
# it against Raspberry Pi's published SHA-256, grow it so packages fit, and
# prove the chroot works. This same .img is what gets flashed to the SD card.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
mkdir -p "$PIOS"
cd "$PIOS"

say "download (Raspberry Pi OS Lite, arm64, latest)"
if ! ls *raspios*.img.xz >/dev/null 2>&1; then
  # the _latest URL redirects to the dated file; keep its real name
  url=$(curl -fsSLI -o /dev/null -w '%{url_effective}' https://downloads.raspberrypi.com/raspios_lite_arm64_latest)
  echo "  $url"
  curl -fsSL -C - -o "$(basename "$url")" "$url"
  curl -fsSL -o "$(basename "$url").sha256" "$url.sha256"
fi
xzimg=$(ls *raspios*.img.xz | head -1)

say "verify SHA-256 against Raspberry Pi's published value"
sha256sum -c "$xzimg.sha256"

say "decompress to the working image"
img="${xzimg%.xz}"
work="arca-device.img"
if [ ! -f "$work" ]; then
  xz -dkT0 "$xzimg"
  mv "$img" "$work"
  say "grow by ${PIOS_GROW_GB} GB so RetroArch, Node and the games fit"
  truncate -s +${PIOS_GROW_GB}G "$work"
  parted -s "$work" resizepart 2 100%
fi
fdisk -l "$work" | sed -n '1,12p'

say "chroot smoke test"
bash "$PROJECT/sandbox/pios_enter.sh" --run 'uname -m; . /etc/os-release; echo "$PRETTY_NAME"; df -h / | tail -1; cat /boot/firmware/config.txt | grep -c . ; echo "config.txt lines above"'
bash "$PROJECT/sandbox/pios_leave.sh"
echo "Pi OS image ready: $PIOS/$work"
