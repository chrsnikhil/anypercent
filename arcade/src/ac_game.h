/* The interface every game implements: init/step/hash/result/ghost + a static info block.
   Exactly one game's object is ever linked into a given binary (the kit's own libarcade.so
   excludes ac_replay.c, which is the only kit file that calls into this interface). */
#ifndef AC_GAME_H
#define AC_GAME_H
#include <stdint.h>
#include "ac_save.h"
#ifdef __cplusplus
extern "C" {
#endif

typedef struct { uint8_t finished; uint32_t frames, score, time_frames, trophies; } ac_result;

typedef struct {
    char id[4];              /* e.g. "SHIP" */
    uint32_t rules_version;
    uint8_t n_trophies;
    const char *const *trophy_names;
    uint16_t ghost_period;   /* default sample period in frames */
} ac_game_info;

void     game_init(uint32_t seed);
void     game_step(uint16_t buttons);
uint32_t game_hash(void);
void     game_result(ac_result *out);
void     game_ghost(ac_ghost_pt *out);   /* ac_ghost_pt from ac_save.h */
extern const ac_game_info GAME_INFO;

/* game_ghost() flags bit, reserved: set on every step the player is in play (not on the title, how-to or results).
   A ghost is aligned on it: the recorded run's first in-play sample is shown on this run's first in-play step, so
   time spent on the title does not offset the ghost. It is not a room/lap change (the other 7 bits). The same value
   as games/common/src/arcade_game_ext.h, which defines it too (an identical redefinition). */
#ifndef AC_GHOST_PLAY
#define AC_GHOST_PLAY 0x80
#endif

#ifdef __cplusplus
}
#endif
#endif
