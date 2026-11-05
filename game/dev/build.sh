#!/bin/bash
# Build SHIP IT!: regenerate graphics/ and gen/ from the kept renders, then the ROM (shipit.gba, shipit.elf).
set -e
cd "$(dirname "$0")/.."
source dev/env.sh
make -f tools.mk gen
make -j8
