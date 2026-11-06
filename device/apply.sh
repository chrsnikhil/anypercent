#!/bin/bash
# Any%: put the device files where the system reads them: systemd units, tools, udev rules, the /run/anypercent
# tmpfiles rule, the app scripts, SSH and firewall settings. No packages, no payload (install.sh does those once and
# then runs this), but for the console signer's Node and npm packages, installed only when missing or when its
# package-lock.json changed; device/deploy.py runs this after every sync. Idempotent; a file already in place is left
# alone.
#   sudo bash apply.sh            prints "changed: <unit> ..." for the units whose file changed (deploy restarts them)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
U=anypercent
ROOT=/opt/anypercent
SRC_DEVICE=$ROOT/src/device
CHANGED=()
UDEV=0

put() {   # MODE SRC DEST [OWNER]: install unless DEST is SRC itself or already identical
    local mode=$1 src=$2 dest=$3 owner=${4:-root}
    [ "$(realpath -m "$src")" = "$(realpath -m "$dest")" ] && return 1
    cmp -s "$src" "$dest" 2>/dev/null && return 1
    install -D -m "$mode" -o "$owner" -g "$owner" "$src" "$dest"
}

unit() {  # NAME [SED]: a unit file into /etc/systemd/system, @CORE@ filled in
    local name=$1 tmp
    tmp=$(mktemp)
    sed "s#@CORE@#$CORE#" "$HERE/$name" > "$tmp"
    if put 0644 "$tmp" "/etc/systemd/system/$name"; then CHANGED+=("$name"); fi
    rm -f "$tmp"
}

CORE=$(dpkg -L libretro-mgba 2>/dev/null | grep '/mgba_libretro\.so$' | head -1 || true)
[ -n "$CORE" ] || CORE=/usr/lib/aarch64-linux-gnu/libretro/mgba_libretro.so

# app scripts and their settings (they run from $SRC_DEVICE; a no-op when this already is $SRC_DEVICE)
for f in anypercent-browser anypercent-browser-pad anypercent-gta3 anypercent-haptics homekey.py ssh-switch; do
    put 0755 "$HERE/$f" "$SRC_DEVICE/$f" || true
done
put 0644 "$HERE/labwc/rc.xml" "$SRC_DEVICE/labwc/rc.xml" || true
put 0644 "$HERE/firewall.nft" "$SRC_DEVICE/firewall.nft" || true

watch() {  # FILE UNIT: a service that runs a file in place restarts when the file's checksum moves
    local stamp=/var/lib/anypercent/applied/$(basename "$1").sha256 sum
    sum=$(sha256sum "$1" | cut -d' ' -f1)
    if [ "$(cat "$stamp" 2>/dev/null)" != "$sum" ]; then
        install -D -m 0644 /dev/null "$stamp"
        echo "$sum" > "$stamp"
        CHANGED+=("$2")
    fi
}
watch "$SRC_DEVICE/homekey.py" anypercent-homekey.service
watch "$SRC_DEVICE/firewall.nft" anypercent-firewall.service

# tools
for f in drmgrab.py vkbd.py vtouch.py test_retroarch.sh boot_time.sh bridge_check.py gpio_buttons.py; do
    if put 0755 "$HERE/$f" "$ROOT/tools/$f" "$U" && [ "$f" = gpio_buttons.py ]; then CHANGED+=("anypercent-buttons.service"); fi
done
put 0644 "$HERE/asoundrc" "/home/$U/.asoundrc" "$U" || true
PAD_CFG="DualSense Wireless Controller.cfg"                    # RetroArch's profile for the pad (PS is the home key)
put 0644 "$HERE/retroarch-autoconfig/$PAD_CFG" "/home/$U/.config/retroarch/autoconfig/udev/$PAD_CFG" "$U" || true
put 0644 "$HERE/alsoftrc" "/home/$U/.alsoftrc" "$U" || true

# udev: the DualSense touchpad kept away from the launcher, light bar and uinput access
for r in 70-anypercent-uinput.rules 71-anypercent-dualsense.rules 72-anypercent-lightbar.rules; do
    put 0644 "$HERE/$r" "/etc/udev/rules.d/$r" && UDEV=1 || true
done
if [ "$UDEV" = 1 ]; then
    udevadm control --reload
    udevadm trigger --subsystem-match=input --action=change
    udevadm settle
fi

# /run/anypercent: how the last game or app ended (homekey.py, the app services, the launcher)
put 0644 "$HERE/anypercent-tmpfiles.conf" /etc/tmpfiles.d/anypercent.conf || true
systemd-tmpfiles --create /etc/tmpfiles.d/anypercent.conf

# SSH: key login only, once a key is installed
if [ -s "/home/$U/.ssh/authorized_keys" ] && put 0644 "$HERE/sshd-keys-only.conf" /etc/ssh/sshd_config.d/01-anypercent-keys-only.conf; then
    sshd -t && systemctl reload ssh
fi

# The console's Arkiv signer (launcher/arkiv_signer: the launcher runs `node signer.mjs` to sign the console's run and
# listing from its own wallet). Node from apt when there is none, then its npm packages (npm ci --omit=dev) once per
# package-lock.json, kept in $ROOT/signer-modules outside the source tree (deploy.py swaps $ROOT/src whole and never
# sends node_modules) and linked into it, so a deploy that keeps the lockfile needs no network. Any failure here (no
# network) is only a warning: the launcher runs without the signer, its listings say "not listed yet", the board reads.
# Progress goes to stdout ("signer: ..."; deploy.py prints it as it comes). One apply at a time holds the signer's
# lock, and apt waits for dpkg's own lock (another apply, an unattended upgrade) and is tried again, so a rerun after
# a cut-off deploy finishes the install instead of colliding with it.
SIGNER=$ROOT/src/launcher/arkiv_signer
MODULES=$ROOT/signer-modules
APT=(apt-get -y -qq -o DPkg::Lock::Timeout=600)
apt_try() {  # ARGS...: apt-get ARGS, three tries a minute apart
    local n
    for n in 1 2 3; do
        "${APT[@]}" "$@" >/dev/null 2>&1 && return 0
        echo "signer: apt-get $1 did not finish (try $n of 3)"
        [ "$n" = 3 ] || sleep "${APT_RETRY_S:-60}"
    done
    return 1
}
if [ -f "$SIGNER/package-lock.json" ]; then
    exec 9>"${SIGNER_LOCK:-/run/anypercent-signer.lock}"
    flock -w 1500 9 || echo "signer: another apply holds the signer lock; going on" >&2
    if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
        export DEBIAN_FRONTEND=noninteractive
        echo "signer: installing nodejs and npm with apt (first time only: several minutes on a Pi)"
        dpkg --configure -a >/dev/null 2>&1 || true          # an install cut off before this one
        if apt_try install nodejs npm || { apt_try update && apt_try install nodejs npm; }; then
            echo "signer: node $(node -v 2>/dev/null) and npm $(npm -v 2>/dev/null) installed"
        else
            echo "warning: nodejs and npm not installed: this console cannot sign its listings" >&2
        fi
    fi
    LOCK=$(sha256sum "$SIGNER/package-lock.json" | cut -d' ' -f1)
    if command -v npm >/dev/null 2>&1 && [ "$(cat "$MODULES/.lock-sha256" 2>/dev/null)" != "$LOCK" ]; then
        echo "signer: npm ci --omit=dev (the signer's packages, once per package-lock.json)"
        rm -rf "$MODULES.new"
        mkdir -p "$MODULES.new"
        cp "$SIGNER/package.json" "$SIGNER/package-lock.json" "$MODULES.new/"
        if (cd "$MODULES.new" && npm ci --omit=dev --no-audit --no-fund --loglevel=error >/dev/null 2>&1); then
            echo "$LOCK" > "$MODULES.new/.lock-sha256"
            rm -rf "$MODULES"
            mv "$MODULES.new" "$MODULES"
            echo "signer: packages installed"
        else
            rm -rf "$MODULES.new"
            echo "warning: the signer's npm packages did not install: this console cannot sign its listings" >&2
        fi
    fi
    if [ -d "$MODULES/node_modules" ] && { [ ! -e "$SIGNER/node_modules" ] || [ -L "$SIGNER/node_modules" ]; }; then
        ln -sfn "$MODULES/node_modules" "$SIGNER/node_modules"
    fi
    flock -u 9
fi

# units
for u in anypercent-launcher.service anypercent-buttons.service anypercent-browser.service anypercent-gta3.service \
         anypercent-firewall.service anypercent-homekey.service; do
    unit "$u"
done
systemctl daemon-reload
systemctl enable -q anypercent-launcher.service anypercent-buttons.service anypercent-firewall.service \
    anypercent-homekey.service
for u in anypercent-buttons.service anypercent-firewall.service anypercent-homekey.service; do
    systemctl is-active -q "$u" || systemctl start "$u"
done
echo "changed: $(printf '%s\n' "${CHANGED[@]}" | sort -u | tr '\n' ' ')"
