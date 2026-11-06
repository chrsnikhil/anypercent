#!/bin/bash
# Set up a Raspberry Pi (3B+, Raspberry Pi OS Lite 64-bit, trixie) as the Any% handheld.
#   sudo bash install.sh /tmp/anypercent-payload.tar.gz
# The payload comes from device/stage.sh (run in the WSL sandbox). Idempotent: safe to run again.
# Never touches /boot/firmware/config.txt (the display lines there are set by hand, see docs/device-setup.md).
set -euo pipefail
PAYLOAD=${1:?usage: install.sh PAYLOAD.tar.gz}
U=anypercent
ROOT=/opt/anypercent
HERE=$(cd "$(dirname "$0")" && pwd)
say() { echo "== $*"; }

say "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  retroarch libretro-mgba \
  python3-venv python3-pip python3-dev build-essential \
  libsdl2-2.0-0 libsdl2-ttf-2.0-0 libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 libfreetype6 \
  fbgrab python3-pil python3-libgpiod \
  chromium labwc wvkbd seatd \n  libglfw3 libopenal1 libmpg123-0t64 libsndfile1 nftables
CORE=$(dpkg -L libretro-mgba | grep '/mgba_libretro\.so$' | head -1)
[ -f "$CORE" ] || { echo "mgba_libretro.so not found" >&2; exit 1; }
say "core: $CORE"

say "payload -> $ROOT"
mkdir -p "$ROOT"
# games/built and games/roms are not wiped: they hold the players' saves (<rom>.srm) next to the ROMs
rm -rf "$ROOT/src" "$ROOT/library" "$ROOT/testlogs" "$ROOT/overlays"
tar -C "$ROOT" -xzf "$PAYLOAD"
# on-screen controls (the launcher's setting): RetroArch reads this overlay when the setting is on
[ -f "$ROOT/overlays/gamepad.cfg" ] && [ -f "$ROOT/overlays/gamepad.png" ] || { echo "overlay missing from the payload" >&2; exit 1; }
chmod -R a+rX "$ROOT/overlays"
mkdir -p "$ROOT/runs" "$ROOT/games/arcade"

say "arm64 replay tools"
bash "$HERE/replay_tools.sh" "$ROOT"

say "python venv"
if [ ! -x "$ROOT/venv/bin/python" ]; then python3 -m venv "$ROOT/venv"; fi
"$ROOT/venv/bin/pip" install -q --upgrade pip
"$ROOT/venv/bin/pip" install -q -r <(grep -v pytest "$ROOT/src/launcher/requirements.txt")

# runs: the bridge's queue/best; built + roms: RetroArch and the bridge write <rom>.srm next to each ROM
chown -R "$U:$U" "$ROOT/runs" "$ROOT/games/built" "$ROOT/games/roms"
usermod -aG video,input,render,audio "$U"

say "RetroArch config (~$U/.config/retroarch/retroarch.cfg)"
H=/home/$U
install -d -o "$U" -g "$U" "$H/.config" "$H/.config/retroarch" "$H/.config/anypercent" "$H/.local" "$H/.local/state" "$H/.local/state/anypercent"
install -m 0644 -o "$U" -g "$U" "$HERE/retroarch.cfg" "$H/.config/retroarch/retroarch.cfg"

say "DualSense: RetroArch profile, touchpad kept away from the launcher, Bluetooth on"
install -d -o "$U" -g "$U" "$H/.config/retroarch/autoconfig/udev"
install -m 0644 -o "$U" -g "$U" "$HERE/retroarch-autoconfig/DualSense Wireless Controller.cfg" "$H/.config/retroarch/autoconfig/udev/"
rfkill unblock bluetooth || true      # pairing the pad itself is one-time: bluetoothctl pair / trust / connect

say "on-screen controls: /dev/uinput for the input group (the touchpad service), uinput loaded at boot"
# the touchpad service (arca_launcher/touchpad.py) reads the panel itself; RetroArch no longer opens it, so the old
# rule that tagged touchscreens as mice (70-anypercent-touch.rules) is removed
rm -f /etc/udev/rules.d/70-anypercent-touch.rules
echo uinput > /etc/modules-load.d/anypercent-uinput.conf
modprobe uinput

say "device files: units, tools, udev rules, app scripts, SSH, firewall (apply.sh, also run by deploy.py)"
install -d -o "$U" -g "$U" "$ROOT/tools"
bash "$HERE/apply.sh"
udevadm trigger --subsystem-match=misc --sysname-match=uinput --action=change
udevadm settle
systemctl disable getty@tty1.service
systemctl enable --now seatd.service
systemctl set-default multi-user.target
# cloud-init did its job on the first boot (user, host name, Wi-Fi); left on it re-runs every boot, about 11 s in
# front of the launcher (23.6 s -> 13.0 s, 2026-10-04). Wi-Fi lives in NetworkManager's own netplan file, not its.
touch /etc/cloud/cloud-init.disabled
say "done: reboot, or  systemctl stop getty@tty1 && systemctl start anypercent-launcher"

# Audio: the headphone jack (card 0) feeds the PAM8403 amp; keep it the default and at 0 dB
# No software boost: an +8 dB limiter stage (2026-10-04) was pulled after smoke was seen while GTA III played;
# do not raise the level past 0 dB until the speaker and amp are checked and rated for it.
printf 'defaults.pcm.card 0\ndefaults.ctl.card 0\n' > /etc/asound.conf
amixer -c 0 sset PCM 0dB >/dev/null 2>&1 && alsactl store || true
