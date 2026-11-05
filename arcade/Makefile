# Host builds for the kit's tests. Run from arcade/: make out/libarcade.so
include mk/arcade.mk
CFLAGS := -std=c99 -O1 -Wall -Wextra -Werror $(ARCADE_FLAGS) -Isrc
KIT := $(addprefix src/,$(filter-out ac_replay.c,$(ARCADE_SRC)))

out/libarcade.so: $(wildcard src/*.c src/*.h)
	mkdir -p out
	gcc -shared -fPIC $(CFLAGS) -o $@ $(filter-out src/ac_replay.c,$(wildcard src/*.c))

out/libtoy.so: $(wildcard src/*.c src/*.h) tests/toy_game.c
	mkdir -p out
	gcc -shared -fPIC $(CFLAGS) -o $@ $(wildcard src/*.c) tests/toy_game.c

out/arcade_replay_toy: $(wildcard src/*.c src/*.h) tests/toy_game.c tools/arcade_replay.c
	mkdir -p out
	gcc $(CFLAGS) -o $@ $(wildcard src/*.c) tests/toy_game.c tools/arcade_replay.c

src/ac_tables.c: tools/gen_tables.py
	python3 tools/gen_tables.py > $@

.PHONY: clean
clean:
	rm -rf out
