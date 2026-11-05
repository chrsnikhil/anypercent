/* The level the world runs: gen/level.c's ZIP_LEVEL, or (PC tests only) a test level parsed from glyph rows. */
#include "zip_level.h"
#include "tuning.h"

#ifndef ZIP_TEST_LEVELS

const zip_level *zip_level_current(void) { return &ZIP_LEVEL; }

#else

#define TEST_W 128
#define TEST_H 48
#define TEST_ENTS 512

static uint8_t test_tiles[TEST_W * TEST_H];
static zip_ent test_ents[TEST_ENTS];
static zip_level test_level;
static int use_test;

const zip_level *zip_level_current(void) { return use_test ? &test_level : &ZIP_LEVEL; }

void zip_level_reset(void) { use_test = 0; }

static int tile_id(char ch) {
    int i;
    for (i = 0; i < ZIP_TILE_COUNT; i++) if (ZIP_TILE_GLYPHS[i] == ch) return i;
    return -1;
}

int zip_test_level(const char *rows, int w, int h) {
    int r, c, n = 0, start = 0;
    static const char kinds[] = "oSR>exCFL";
    if (w > TEST_W || h > TEST_H) return 1;
    for (c = 0; c < w; c++) {                      /* column-major, so the things come out sorted by x */
        for (r = 0; r < h; r++) {
            char ch = rows[r * w + c];
            int id = tile_id(ch), k;
            test_tiles[r * w + c] = (uint8_t)(id > 0 ? id : 0);
            if (id >= 0) continue;
            if (ch == 'P') {
                test_level.start_x = (int16_t)(c * 16 + 8);
                test_level.start_y = (int16_t)(r * 16 + 16 - BODY_H);
                start = 1;
                continue;
            }
            for (k = 0; kinds[k] && kinds[k] != ch; k++) {}
            if (!kinds[k] || n >= TEST_ENTS) continue;
            test_ents[n].kind = (uint8_t)k;
            test_ents[n].arg = (uint8_t)(k == ENT_BUG ? 2 : 0);
            test_ents[n].x = (int16_t)(k == ENT_FINISH ? c * 16 : c * 16 + 8);
            test_ents[n].y = (int16_t)(k == ENT_PACKET ? r * 16 + 8 : r * 16 + 16);
            n++;
        }
    }
    test_level.w = (uint16_t)w;
    test_level.h = (uint16_t)h;
    test_level.tiles = test_tiles;
    test_level.n_ents = (uint16_t)n;
    test_level.ents = test_ents;
    use_test = 1;
    return start ? 0 : 2;
}

#endif
