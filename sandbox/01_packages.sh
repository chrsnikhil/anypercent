#!/bin/bash
# Host packages for the sandbox (run as root in WSL Ubuntu 24.04).
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

say "apt packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  git curl ca-certificates jq xz-utils unzip zip rsync \
  parted e2fsprogs dosfstools fdisk \
  qemu-user-static binfmt-support \
  build-essential cmake pkg-config bison flex libpng-dev \
  python3-venv python3-pip >/dev/null
# RetroArch + the libretro mGBA core are optional here (the device builds its
# own pinned core); install them if the archive has them.
apt-get install -y -qq retroarch libretro-mgba >/dev/null 2>&1 \
  && echo "retroarch + libretro-mgba installed" || echo "retroarch/libretro-mgba not in this archive (fine)"

say "mGBA 0.10.5 (official Ubuntu 24.04 build, same version the device pins)"
if ! command -v mgba-qt >/dev/null; then
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/mgba.tar.xz" https://github.com/mgba-emu/mgba/releases/download/0.10.5/mGBA-0.10.5-ubuntu64-noble.tar.xz
  tar -xJf "$tmp/mgba.tar.xz" -C "$tmp"
  apt-get install -y -qq $(find "$tmp" -name '*.deb' | sort) >/dev/null
  rm -rf "$tmp"
fi
command -v mgba-qt mgba 2>/dev/null || true

say "arm64 binfmt (lets an x86 WSL run the Pi's aarch64 binaries in a chroot)"
if [ ! -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]; then
  update-binfmts --enable qemu-aarch64 2>/dev/null || true
fi
if [ ! -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]; then
  # WSL without systemd: register by hand, with the F (fix binary) flag so the
  # interpreter works inside the chroot without copying it in
  echo ':qemu-aarch64:M::\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\xb7\x00:\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff:/usr/bin/qemu-aarch64-static:F' \
    > /proc/sys/fs/binfmt_misc/register
fi
cat /proc/sys/fs/binfmt_misc/qemu-aarch64 | head -3

say "python venv (PyBoy for headless boot tests)"
mkdir -p "$SANDBOX"
python3 -m venv "$SANDBOX/venv"
"$SANDBOX/venv/bin/pip" install -q --upgrade pip
"$SANDBOX/venv/bin/pip" install -q pyboy "pillow==12.3.*" numpy scipy pypng "pygame-ce==2.5.*" fonttools pytest   # scipy, pypng: game asset tools; pygame-ce, fonttools, pytest: launcher
"$SANDBOX/venv/bin/python" -c "import pyboy; print('pyboy', pyboy.__version__ if hasattr(pyboy,'__version__') else 'ok')"
echo "packages OK"
