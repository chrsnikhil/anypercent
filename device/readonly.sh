#!/bin/sh
# Any%: make pulling the power harmless. The system runs from a read-only SD card with every change kept in RAM
# (overlayroot), and only what has to survive a reboot lives on a small ext4 image on the boot partition,
# bind-mounted over its usual place:
#   /opt/anypercent/library                 the game list and its art
#   /opt/anypercent/games                   ROMs and their saves (RetroArch keeps .srm next to the ROM)
#   /opt/anypercent/runs                    verified arcade runs and bests
#   /home/anypercent/.local/state/anypercent  launcher settings (volume, theme, last played)
#   /var/lib/bluetooth                      controller pairings (a pad paired at the venue stays paired)
# Wi-Fi networks and everything else reset on reboot while read-only: add the venue Wi-Fi first, or turn it off.
#
#   sudo sh device/readonly.sh data     one-time: create /data and move the folders above onto it (keeps originals)
#   sudo sh device/readonly.sh on       read-only from the next boot      (then: sudo reboot)
#   sudo sh device/readonly.sh off      writable from the next boot       (then: sudo reboot; needed to deploy)
#   sh device/readonly.sh status
#
# Not raspi-config's overlay option: run non-interactively it also makes the boot partition read-only, and the
# data image lives there.
set -eu

BOOT=/boot/firmware
CMDLINE=$BOOT/cmdline.txt
IMG=$BOOT/anypercent-data.img
DATA=/data
SIZE_MB=256
KEEP="/opt/anypercent/library /opt/anypercent/games /opt/anypercent/runs /home/anypercent/.local/state/anypercent /var/lib/bluetooth"

FLAG="overlayroot=tmpfs:recurse=0"        # recurse=0: leave /data and its bind mounts writable (the default
                                          # puts a RAM layer over every mount, saves included)
overlay_now() { grep -q "overlayroot=" /proc/cmdline; }
overlay_next() { grep -q "overlayroot=" "$CMDLINE"; }
name_of() { echo "$1" | sed 's#^/##; s#/#_#g'; }          # /opt/anypercent/runs -> opt_anypercent_runs

case "${1:-status}" in
data)
    if overlay_now; then echo "read-only right now: run 'off' and reboot first"; exit 1; fi
    dpkg -s overlayroot >/dev/null 2>&1 || apt-get install -y overlayroot      # inert until the cmdline asks for it
    if [ ! -f "$IMG" ]; then
        dd if=/dev/zero of="$IMG" bs=1M count=$SIZE_MB status=none
        mkfs.ext4 -q -F -L anypercent-data "$IMG"
    fi
    mkdir -p "$DATA"
    grep -q " $DATA " /etc/fstab || \
        echo "$IMG $DATA ext4 loop,noatime,nofail,x-systemd.requires-mounts-for=$BOOT 0 0" >> /etc/fstab
    mountpoint -q "$DATA" || mount "$DATA"
    for dir in $KEEP; do
        [ -d "$dir" ] || continue
        store=$DATA/$(name_of "$dir")
        if [ ! -d "$store" ]; then
            mkdir -p "$store"
            cp -a "$dir/." "$store/"
            chown --reference="$dir" "$store"; chmod --reference="$dir" "$store"
        fi
        # a bind mount over the original: if /data ever fails to mount, the last copy underneath still works
        grep -q " $dir none bind" /etc/fstab || \
            echo "$store $dir none bind,nofail,x-systemd.requires-mounts-for=$DATA 0 0" >> /etc/fstab
        mountpoint -q "$dir" || mount "$dir"
    done
    systemctl daemon-reload
    echo "data ready:"; findmnt -rno TARGET,SOURCE | grep -E "^($DATA|/opt/anypercent|/home/anypercent|/var/lib/bluetooth)" || true
    ;;
on)
    mountpoint -q "$DATA" || { echo "no /data: run 'data' first, or saves would be lost on every reboot"; exit 1; }
    dpkg -s overlayroot >/dev/null 2>&1 || { echo "overlayroot is not installed: run 'data' first"; exit 1; }
    sed -i "s/overlayroot=[^ ]* //" "$CMDLINE"
    sed -i "1s/^/$FLAG /" "$CMDLINE"
    sync
    echo "read-only from the next boot: sudo reboot"
    ;;
off)
    sed -i "s/overlayroot=[^ ]* //" "$CMDLINE"
    sync
    echo "writable from the next boot: sudo reboot"
    ;;
status)
    if overlay_now; then echo "now:  read-only (changes outside /data are lost on reboot)"; else echo "now:  writable"; fi
    if overlay_next; then echo "next: read-only"; else echo "next: writable"; fi
    if mountpoint -q "$DATA"; then df -h "$DATA" | tail -1; else echo "/data: not mounted"; fi
    ;;
*)
    echo "usage: $0 data|on|off|status"; exit 2
    ;;
esac
