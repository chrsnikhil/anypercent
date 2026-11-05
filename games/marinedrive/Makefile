# The ROM, built by Butano: `bash dev/build.sh` -> <TARGET>.gba and <TARGET>.elf (the tests read symbol addresses
# from the .elf). Butano resolves every folder below relative to this one: ../common/src is the common runtime and
# ../../arcade/src the arcade kit, shared by every game. Objects are named by file basename, so no file here may
# share a name with one in those folders. The Butano sprite fonts are vendored in fonts/ and include/ (zlib).
# USERFLAGS are the kit's determinism flags, taken from arcade/mk/arcade.mk (found next to this Makefile, since Butano
# re-reads it from build/); tools.mk builds the same rules for the PC with the same flags.
include $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../../arcade/mk/arcade.mk
BUTANO          :=  /opt/arca-sandbox/toolchains/butano
TARGET          :=  marinedrive
BUILD           :=  build
LIBBUTANO       :=  $(BUTANO)/butano
PYTHON          :=  python
SOURCES         :=  src rules ../common/src ../../arcade/src
INCLUDES        :=  include src rules ../common/src ../../arcade/src
DATA            :=
GRAPHICS        :=  graphics fonts
AUDIO           :=
AUDIOBACKEND    :=  null
AUDIOTOOL       :=
DMGAUDIO        :=  dmg_audio
DMGAUDIOBACKEND :=  default
ROMTITLE        :=  MARINE DRIVE
ROMCODE         :=  MDGP
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
