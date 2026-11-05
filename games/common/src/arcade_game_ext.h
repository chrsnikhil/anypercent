/* The one hook every arcade game adds beyond arcade/src/ac_game.h, for the common runtime
   (games/common/src/arcade_runtime.h). It lives in the game's rules, so the PC library exports it too.

   game_ended() is 1 while a finished or failed run's results are shown, else 0. The runtime closes and saves the
   run log on its rising edge and resets the ROM on its falling edge (the player left the results), so every run's
   log starts at boot. It must rise at most once per boot: the rules should never go from the results back into
   play without a reset. */
#ifndef ARCADE_GAME_EXT_H
#define ARCADE_GAME_EXT_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

uint8_t game_ended(void);

/* game_ghost() flags bit, reserved: set it (flags |= AC_GHOST_PLAY) on every step the player is in play (not on the
   title, how-to or results). The runtime aligns the ghost on it: the recorded run's first in-play sample is shown on
   this run's first in-play step, so time spent on the title does not offset the ghost. It is ignored by the
   "never slide across a flags change" rule; use the other 7 bits for rooms, laps, respawns. A game that never sets
   it gets a ghost indexed by steps since boot. */
#define AC_GHOST_PLAY 0x80

#ifdef __cplusplus
}
#endif
#endif
