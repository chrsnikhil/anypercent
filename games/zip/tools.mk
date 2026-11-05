# PC builds of the same rules the ROM runs (the ROM itself is built by Makefile through Butano):
#   make -f tools.mk host     out/librules.so: rules/*.c gen/*.c + the kit (without ac_replay.c), for ctypes tests;
#                             built with ZIP_TEST_LEVELS (test levels and state pokes, never in the ROM or replayer)
#   make -f tools.mk replay   out/arcade_replay: the kit's run-log replayer linked with these rules (the launcher's)
#   make -f tools.mk runner   games/common/out/gba_run, the headless ROM runner shared by every game
PY     ?= /opt/arca-sandbox/venv/bin/python
ARCADE := ../../arcade
COMMON := ../common
include $(ARCADE)/mk/arcade.mk

RULES    := $(wildcard rules/*.c gen/*.c)
DEPS     := $(RULES) $(wildcard rules/*.h gen/*.h $(ARCADE)/src/*.c $(ARCADE)/src/*.h $(COMMON)/src/*.h) tools.mk
KIT      := $(addprefix $(ARCADE)/src/,$(ARCADE_SRC))
CFLAGS   := -std=c99 -O1 -Wall -Wextra -Werror=implicit-function-declaration $(ARCADE_FLAGS) -Irules -Igen -I$(ARCADE)/src -I$(COMMON)/src

host: out/librules.so

out/librules.so: $(DEPS)
	mkdir -p out
	gcc -shared -fPIC $(CFLAGS) -DZIP_TEST_LEVELS -o $@ $(RULES) $(filter-out %/ac_replay.c,$(KIT))

replay: out/arcade_replay

out/arcade_replay: $(DEPS) $(ARCADE)/tools/arcade_replay.c
	mkdir -p out
	gcc $(CFLAGS) -o $@ $(RULES) $(KIT) $(ARCADE)/tools/arcade_replay.c

runner:
	$(PY) -c "import sys; sys.path.insert(0, '$(COMMON)/py'); import arcade_test; print(arcade_test.build_runner())"

clean:
	rm -rf out build *.gba *.elf *.sav tests/out

.PHONY: host replay runner clean
