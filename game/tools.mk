# SHIP IT! tools (the ROM itself is built by Makefile through Butano):
#   make -f tools.mk art      re-render the office in Blender (slow; renders are kept in art/renders)
#   make -f tools.mk gen      renders -> graphics/ and gen/ (limit checks; run by dev/build.sh)
#   make -f tools.mk host     out/librules.so for the tests (rules + arcade kit + game_shipit.c)
#   make -f tools.mk replay   out/arcade_replay, the kit's run-log replayer linked with SHIP IT!
#   make -f tools.mk runner   out/gba_run, the headless test runner
#   make -f tools.mk stream   out/libstream.so for the streamer tests
PY      ?= /opt/arca-sandbox/venv/bin/python
BLENDER ?= blender
MGBA    ?= /opt/arca-sandbox/toolchains/mgba-src
SCENE   := office

art:
	$(PY) tools/render/textures.py --out art/textures
	$(BLENDER) -b --python-exit-code 1 -P tools/render/render.py -- --scene $(SCENE) --out art/renders/$(SCENE)
	$(BLENDER) -b --python-exit-code 1 -P tools/render/render.py -- --scene $(SCENE) --out art/renders/$(SCENE)_night --only room --variant night
	$(BLENDER) -b --python-exit-code 1 -P tools/render/render.py -- --scene $(SCENE) --out art/renders/$(SCENE)_dawn --only room --variant dawn
	$(BLENDER) -b --python-exit-code 1 -P tools/render/render.py -- --scene hall --out art/renders/hall

gen:
	$(PY) tools/art/build_art.py --renders art/renders/$(SCENE) --scene $(SCENE) --graphics graphics --gen gen \
		--night-renders art/renders/$(SCENE)_night --dawn-renders art/renders/$(SCENE)_dawn --hall-renders art/renders/hall

host: out/librules.so

include ../arcade/mk/arcade.mk
DETERMINISM := $(ARCADE_FLAGS)
KIT_SRC     := $(filter-out ../arcade/src/ac_replay.c,$(wildcard ../arcade/src/*.c))

out/librules.so: $(wildcard rules/*.c rules/*.h ../arcade/src/*.c ../arcade/src/*.h) gen/scene_office.c gen/scene_office.h gen/scene_hall.c gen/scene_hall.h
	mkdir -p out
	gcc -shared -fPIC -O1 -Wall -Wextra $(DETERMINISM) -Irules -Igen -I../arcade/src -o $@ rules/rules.c rules/rng.c rules/record.c rules/game_shipit.c gen/scene_office.c gen/scene_hall.c $(KIT_SRC)

replay: out/arcade_replay

out/arcade_replay: $(wildcard rules/*.c rules/*.h ../arcade/src/*.c ../arcade/src/*.h ../arcade/tools/arcade_replay.c) gen/scene_office.c gen/scene_hall.c
	mkdir -p out
	gcc -O1 $(DETERMINISM) -Irules -Igen -I../arcade/src -o $@ rules/*.c gen/scene_office.c gen/scene_hall.c ../arcade/src/*.c ../arcade/tools/arcade_replay.c

runner: out/gba_run

out/gba_run: tools/gba_run/gba_run.c
	mkdir -p out
	gcc -O2 -o $@ $< -I$(MGBA)/include -I$(MGBA)/build/include $(MGBA)/build/libmgba.a -lm -lpthread

stream: out/libstream.so

out/libstream.so: stream/stream.c stream/stream.h
	mkdir -p out
	gcc -shared -fPIC -O1 -Wall -Wextra -Istream -o $@ stream/stream.c

.PHONY: art gen host replay runner stream
