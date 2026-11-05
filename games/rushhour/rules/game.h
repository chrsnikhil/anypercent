/* RUSH HOUR's rules: late for ETHGlobal Mumbai registration, run across the streets, market awnings and train roofs
   to the venue door. Plain C99, integers only, one module-global state; the ROM and out/librules.so compile this
   same code. The arcade interface (game_init, game_step, game_hash, game_result, game_ghost, GAME_INFO) is in
   arcade/src/ac_game.h and game_ended() in games/common/src/arcade_game_ext.h; below are the reads the view and
   the tests use, and the debug hooks the tests use (never called by the ROM). */
#ifndef GAME_H
#define GAME_H
#include <stdint.h>
#include "ac_game.h"
#include "arcade_game_ext.h"
#include "world.h"

enum { SC_TITLE = 0, SC_HOWTO = 1, SC_PLAY = 2, SC_PAUSE = 3, SC_RESULTS = 4 };
enum { TROPHY_UNDER = 1, TROPHY_ALL_CHAI = 2, TROPHY_NO_DAMAGE = 4, TROPHY_NO_CHECKPOINT = 8 };

/* Player pose (game_ghost angle bits 1..3; bit 0 = facing left; bit 4 = running fast, for the run cycle). */
enum { POSE_IDLE = 0, POSE_RUN = 1, POSE_JUMP = 2, POSE_FALL = 3, POSE_HURT = 4, POSE_DEAD = 5 };


uint8_t  rules_scene(void);
uint32_t rules_steps(void);         /* game steps since game_init */
uint32_t rules_run_frames(void);    /* play frames (not paused) since the run began */
uint8_t  rules_finished(void);      /* 1 once the door was reached */
uint32_t rules_trophies(void);

int16_t  rules_px(void);            /* the player's hitbox top-left, in level pixels */
int16_t  rules_py(void);
int32_t  rules_vx(void);            /* Q8.8 px/frame */
int32_t  rules_vy(void);
uint8_t  rules_on_ground(void);
uint8_t  rules_facing_left(void);
uint8_t  rules_pose(void);
uint8_t  rules_hp(void);
uint8_t  rules_shield(void);
uint8_t  rules_invuln(void);        /* invulnerable frames left */
uint8_t  rules_dead(void);          /* death frames left (0: alive) */
uint16_t rules_chai(void);          /* chai cups collected this run */
uint16_t rules_chai_total(void);    /* chai cups in the level */
uint16_t rules_lives_lost(void);    /* respawns this run (also game_ghost's flags) */
uint8_t  rules_damaged(void);       /* 1 once the player lost a heart or died this run */
uint8_t  rules_touched_checkpoint(void);

uint16_t rules_level_w(void);       /* the level, in tiles */
uint16_t rules_level_h(void);
uint8_t  rules_tile(int tx, int ty);    /* T_*; outside the level: T_SOLID left/right, T_EMPTY above/below */

uint16_t rules_ent_count(void);
uint8_t  rules_ent_type(int i);     /* E_* */
uint8_t  rules_ent_state(int i);    /* ES_* */
int16_t  rules_ent_x(int i);        /* the entity's box top-left, in level pixels */
int16_t  rules_ent_y(int i);
int8_t   rules_ent_dir(int i);      /* bugs: -1 / 1 */
uint8_t  rules_ent_timer(int i);    /* a squashed bug's frames left */

/* Debug hooks for the tests (PC only by convention; they are harmless in the ROM). */
void rules_debug_place(int px, int py);                 /* teleport the player (hitbox top-left), stop it */
void rules_debug_velocity(int32_t vx, int32_t vy);
void rules_debug_map(const uint8_t *tiles, int w, int h); /* play on this map (row major, T_*), no entities */
void rules_debug_add_ent(int type, int tx, int ty);
void rules_debug_set_start(int tx, int ty);             /* the start tile (the player's feet stand on its bottom) */
void rules_debug_run_frames(uint32_t frames);           /* set the clock */
uint32_t rules_debug_state_size(void);                  /* sizeof the state (the bot snapshots it) */

#endif
