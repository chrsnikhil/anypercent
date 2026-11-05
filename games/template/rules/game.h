/* The template game's rules: a dot moved with the d-pad toward a goal square. Plain C99, integers only, one
   module-global state; the ROM and out/librules.so compile this same code. The arcade interface (game_init,
   game_step, game_hash, game_result, game_ghost, GAME_INFO) is in arcade/src/ac_game.h and game_ended() in
   games/common/src/arcade_game_ext.h; below are the extra reads the view and the tests use. */
#ifndef GAME_H
#define GAME_H
#include <stdint.h>
#include "ac_game.h"
#include "arcade_game_ext.h"

enum { SC_TITLE = 0, SC_PLAY = 1, SC_RESULTS = 2 };
enum { TROPHY_REACHED = 1, TROPHY_FAST = 2 };

uint8_t  rules_scene(void);
uint8_t  rules_paused(void);
int16_t  rules_x(void);             /* the dot's top-left, in pixels */
int16_t  rules_y(void);
uint32_t rules_run_frames(void);    /* play frames (not paused) since the title */
uint8_t  rules_finished(void);      /* 1 once the goal was reached */
uint32_t rules_trophies(void);
int16_t  rules_goal_x(void);        /* the goal's top-left: the classic spot for seed 0, else a seeded one */
int16_t  rules_goal_y(void);

#endif
