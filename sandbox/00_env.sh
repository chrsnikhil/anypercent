#!/bin/bash
# ARCA sandbox -- shared settings. Source this, do not run it.
#   source /mnt/c/Users/chrsn/Desktop/retro-handheld-ethglobal/sandbox/00_env.sh
#
# Everything lives on the WSL ext4 disk (fast, supports loop mounts and
# chroot); the scripts themselves live in the project so they are versioned.
# From Windows the sandbox is at  \\wsl.localhost\Ubuntu-24.04\opt\arca-sandbox

export SANDBOX=/opt/arca-sandbox
export PROJECT=/mnt/c/Users/chrsn/Desktop/retro-handheld-ethglobal
export TOOLS=$SANDBOX/toolchains
export PIOS=$SANDBOX/pios                 # Raspberry Pi OS image + mount points
export GAMES=$SANDBOX/games               # sources, ROMs, licences, builds

export RGBDS_HOME=$TOOLS/rgbds
export GBDK_HOME=$TOOLS/gbdk/            # GBDK makefiles expect the trailing slash
export PATH=$RGBDS_HOME:$GBDK_HOME/bin:$TOOLS/bin:$TOOLS/jdk/bin:$SANDBOX/venv/bin:$PATH

# image size headroom added before first boot / chroot, so packages fit
export PIOS_GROW_GB=4

say() { printf '\n== %s\n' "$*"; }
