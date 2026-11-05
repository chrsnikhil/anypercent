#!/bin/bash
# Build the ROM (<TARGET>.gba and .elf, TARGET in the Makefile) with Butano.
set -e
cd "$(dirname "$0")/.."
source dev/env.sh
make -j8
