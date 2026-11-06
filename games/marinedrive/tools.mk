# PC builds of the same rules the ROM runs (the ROM itself is built by Makefile through Butano):
#   make -f tools.mk host     out/librules.so: rules/*.c + the arcade kit (without ac_replay.c), for ctypes tests
#   make -f tools.mk replay   out/arcade_replay: the kit's run-log replayer linked with these rules (the launcher's)
#   make -f tools.mk splits   out/arcade_splits: the same replay, then the player's lap times (tools/arcade_splits.c)
#   make -f tools.mk runner   games/common/out/gba_run, the headless ROM runner shared by every game
PY     ?= /opt/arca-sandbox/venv/bin/python
ARCADE := ../../arcade
COMMON := ../common
include $(ARCADE)/mk/arcade.mk

RULES    := $(wildcard rules/*.c)
DEPS     := $(RULES) $(wildcard rules/*.h $(ARCADE)/src/*.c $(ARCADE)/src/*.h $(COMMON)/src/*.h) tools.mk
KIT      := $(addprefix $(ARCADE)/src/,$(ARCADE_SRC))
CFLAGS   := -std=c99 -O1 -Wall -Wextra -Werror=implicit-function-declaration $(ARCADE_FLAGS) -Irules -I$(ARCADE)/src -I$(COMMON)/src

host: out/librules.so

out/librules.so: $(DEPS)
	mkdir -p out
	gcc -shared -fPIC $(CFLAGS) -o $@ $(RULES) $(filter-out %/ac_replay.c,$(KIT))

replay: out/arcade_replay

out/arcade_replay: $(DEPS) $(ARCADE)/tools/arcade_replay.c
	mkdir -p out
	gcc $(CFLAGS) -o $@ $(RULES) $(KIT) $(ARCADE)/tools/arcade_replay.c

splits: out/arcade_splits

out/arcade_splits: $(DEPS) tools/arcade_splits.c
	mkdir -p out
	gcc $(CFLAGS) -o $@ $(RULES) $(KIT) tools/arcade_splits.c

runner:
	$(PY) -c "import sys; sys.path.insert(0, '$(COMMON)/py'); import arcade_test; print(arcade_test.build_runner())"

clean:
	rm -rf out build *.gba *.elf *.sav tests/out

.PHONY: host replay splits runner clean
