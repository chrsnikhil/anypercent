# SHIP IT! ROM, built by Butano: `bash dev/build.sh` regenerates graphics/ and gen/ first, then runs make.
# Output: shipit.gba and shipit.elf (the tests read symbol addresses from the .elf). Butano resolves every
# folder below relative to this one (../arcade/src is the arcade kit, shared with the other games), so the
# two Butano sprite fonts are vendored in fonts/ and include/ (zlib). USERFLAGS are the kit's determinism flags,
# from arcade/mk/arcade.mk (shared with every arcade game's ROM and host tools).
BUTANO          :=  /opt/arca-sandbox/toolchains/butano
TARGET          :=  shipit
BUILD           :=  build
LIBBUTANO       :=  $(BUTANO)/butano
PYTHON          :=  python
SOURCES         :=  src rules gen stream ../arcade/src
INCLUDES        :=  include rules gen stream ../arcade/src
DATA            :=
GRAPHICS        :=  graphics fonts
AUDIO           :=
AUDIOBACKEND    :=  null
AUDIOTOOL       :=
DMGAUDIO        :=  dmg_audio
DMGAUDIOBACKEND :=  default
ROMTITLE        :=  SHIP IT
ROMCODE         :=  SHIP
# Butano runs this file again from build/, so the kit's path is taken from this file's own directory.
include $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../arcade/mk/arcade.mk
USERFLAGS       :=  $(ARCADE_FLAGS)
USERCXXFLAGS    :=
USERASFLAGS     :=
USERLDFLAGS     :=
USERLIBDIRS     :=
USERLIBS        :=
DEFAULTLIBS     :=
STACKTRACE      :=
USERBUILD       :=
EXTTOOL         :=

ifndef LIBBUTANOABS
	export LIBBUTANOABS := $(realpath $(LIBBUTANO))
endif

include $(LIBBUTANOABS)/butano.mak
