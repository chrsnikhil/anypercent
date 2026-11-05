/* The level's vocabulary, shared by the rules, the generated level (level.h / level_data.c, written by
   tools/level/build_level.py from level/level.txt) and the view. */
#ifndef WORLD_H
#define WORLD_H
#include <stdint.h>

/* Collision tiles (16 x 16 px). */
enum { T_EMPTY = 0, T_SOLID = 1, T_ONEWAY = 2, T_SPIKE = 3 };

/* Entities. Positions in the level are tiles; each entity's box is fixed per type (see entities.c). */
enum { E_NONE = 0, E_BUG = 1, E_CHAI = 2, E_ORB = 3, E_CHECK = 4, E_DOOR = 5 };

/* Entity states. */
enum { ES_LIVE = 0, ES_GONE = 1, ES_SQUASHED = 2, ES_ON = 3 };

typedef struct { uint8_t type; uint16_t tx; uint8_t ty; } rh_level_ent;

#endif
