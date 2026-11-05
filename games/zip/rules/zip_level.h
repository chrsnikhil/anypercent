/* ZIP's level data: a tile grid (ids into the generated tile table: a 16-entry height mask and an angle per id)
   and a list of things sorted by x. gen/level.c holds the real level (tools/level/build_level.py writes it from
   level/level.txt); the PC test library can load a small test level from glyph rows instead (ZIP_TEST_LEVELS). */
#ifndef ZIP_LEVEL_H
#define ZIP_LEVEL_H
#include <stdint.h>

enum {
    ENT_PACKET = 0, ENT_SPRING_Y = 1, ENT_SPRING_R = 2, ENT_BOOSTER = 3, ENT_BUG = 4, ENT_SPIKES = 5,
    ENT_CHECKPOINT = 6, ENT_FINISH = 7, ENT_LOOP = 8
};

/* x, y in pixels: a packet's centre; a loop's bottom centre on the floor; the finish line's x; everything else
   stands on the floor: x its centre, y its bottom. arg: a bug's patrol half-range in tiles. */
typedef struct { int16_t x, y; uint8_t kind, arg; } zip_ent;

typedef struct {
    uint16_t w, h;              /* tiles */
    const uint8_t *tiles;       /* w * h tile ids, row major */
    uint16_t n_ents;
    const zip_ent *ents;        /* sorted by x */
    int16_t start_x, start_y;   /* the player's centre at the start */
} zip_level;

extern const zip_level ZIP_LEVEL;                 /* gen/level.c */
extern const uint8_t ZIP_TILE_MASK[][16];         /* gen/zip_tiles.c: per tile id */
extern const uint8_t ZIP_TILE_ANGLE[];
extern const char ZIP_TILE_GLYPHS[];              /* glyph of each id, id order */
extern const uint8_t ZIP_TILE_COUNT;
extern const int16_t ZIP_LOOP_PATH[][2];          /* gen/zip_tiles.c: the loop's centre path from its entry point */
extern const uint8_t ZIP_LOOP_ANGLE[];
extern const uint16_t ZIP_LOOP_POINTS;            /* points on the path; the last one is the entry point again */

const zip_level *zip_level_current(void);

#ifdef ZIP_TEST_LEVELS
/* PC tests only: load a level from `h` rows of `w` glyphs (tools/level/tiles.py glyphs plus the thing glyphs
   o S R > e x C F P L); returns 0 on success. zip_level_reset() goes back to the real level. */
int zip_test_level(const char *rows, int w, int h);
void zip_level_reset(void);
#endif

#endif
