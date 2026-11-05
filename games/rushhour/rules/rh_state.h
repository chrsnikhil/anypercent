/* The rules' one module-global state, shared by game.c (scenes, clock, hash, results), physics.c (the player and
   the tile grid) and entities.c (bugs, chai, orb, checkpoints, door). Internal to rules/: the view reads game.h. */
#ifndef RH_STATE_H
#define RH_STATE_H
#include <stdint.h>
#include "world.h"

#define MAX_ENTS 128

typedef struct {
    uint8_t type, state;        /* E_*, ES_* */
    int8_t dir;                 /* bugs: -1 left, 1 right */
    uint8_t timer;              /* a squashed bug's frames left */
    int32_t x, y;               /* the box's top-left, Q8.8 level pixels */
} rh_ent;

typedef struct {
    uint32_t seed;              /* game_init's: 0 the classic level, else where the bugs start (entities.c) */
                                /* (not hashed per step: game_init folds it into the first hash) */
    uint8_t scene, finished;
    uint32_t trophies;
    uint16_t prev;              /* last step's buttons, for presses */
    uint32_t steps, run_frames;

    int32_t x, y, vx, vy;       /* the player's hitbox top-left and velocity, Q8.8 */
    int32_t prev_y;             /* y before this frame's move (stomps) */
    uint8_t on_ground, facing_left, coyote, jump_buf, jumping, drop, hurt_lock, invuln, dead, hp, shield;
    uint8_t damaged, touched_checkpoint;
    uint16_t chai, lives_lost;
    int16_t spawn_tx, spawn_ty; /* the respawn tile: the player's feet stand on its bottom edge */

    uint16_t n_ents;
    rh_ent ents[MAX_ENTS];

    /* A seeded run's bug starts, worked out once by game_init's level load (at boot, where time is free) and only
       copied by the reload at play start (whose frame is already the view's busiest). Constant for the run. */
    uint8_t starts_ready;
    int8_t start_dir[MAX_ENTS];
    int32_t start_x[MAX_ENTS];

    uint32_t hash;              /* running: folds the previous hash and every field in each step */

    /* The map: constant data chosen at init (the level, or a test's), not hashed. */
    const uint8_t *map;
    uint16_t map_w, map_h, chai_total;
} rh_state;

extern rh_state rh_s;

/* physics.c */
uint8_t rh_tile(int tx, int ty);
int     rh_floor_div(int32_t v, int32_t d);
void    rh_player_spawn(void);                          /* at the respawn tile, standing, still */
void    rh_player_step(uint16_t buttons, uint16_t pressed);
void    rh_player_hurt(int32_t from_center_x);          /* Q8.8 x of what hit; shield, hearts, knockback */
void    rh_player_die(void);                            /* fell or lost the last heart: lie still, then respawn */

/* entities.c */
void    rh_ent_place(rh_ent *e, int tx, int ty);        /* its box from its tile (see entities.c) */
void    rh_ents_load(void);                             /* from the level (a test map has none) */
void    rh_ents_step(uint16_t buttons);                 /* bugs move; contacts with the player */

#endif
