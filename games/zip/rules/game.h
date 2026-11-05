/* ZIP's rules: a momentum platformer. Plain C99, integers only, one module-global state; the ROM and
   out/librules.so compile this same code. The arcade interface is in arcade/src/ac_game.h and game_ended() in
   games/common/src/arcade_game_ext.h; below are the extra reads the view and the tests use. */
#ifndef GAME_H
#define GAME_H
#include <stdint.h>
#include "ac_game.h"
#include "arcade_game_ext.h"

enum { SC_TITLE = 0, SC_HOWTO = 1, SC_PLAY = 2, SC_PAUSE = 3, SC_RESULTS = 4 };
enum { TROPHY_UNDER = 1, TROPHY_NO_LOSS = 2, TROPHY_100 = 4, TROPHY_LOOP = 8 };

uint8_t  rules_scene(void);
uint32_t rules_run_frames(void);    /* play frames (not paused) since play began, frozen at the finish gate */
uint8_t  rules_finished(void);      /* 1 once the finish gate was crossed */
uint32_t rules_trophies(void);
uint8_t  rules_n_trophies(void);
const char *rules_trophy_name(int i);
uint16_t rules_ghost_period(void);
uint32_t rules_scene_frames(void);  /* frames since the scene changed (for the view's animations) */

int32_t  rules_px(void);            /* the player's centre, whole pixels */
int32_t  rules_py(void);

#endif
