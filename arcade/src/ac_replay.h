/* Headless replay: drive a linked game's game_* interface from a run log. */
#ifndef AC_REPLAY_H
#define AC_REPLAY_H
#include <stdint.h>
#include "ac_game.h"
#include "ac_save.h"
#ifdef __cplusplus
extern "C" {
#endif

/* The longest run a log may claim: one hour at 60 Hz. A longer claim is refused before anything is replayed, so a
   hostile header cannot keep a verifier busy. */
#define AC_MAX_FRAMES 216000u

typedef struct {
    uint32_t frames, final_hash;
    ac_result result;
    int header_ok, hash_matches, complete;
    int claims_match;        /* the header's claimed score and trophies equal the replayed result's */
} ac_replay_out;

/* Replays a log through the linked game. The header must be valid, name the linked game (GAME_INFO.id) and its
   rules version, and claim at most AC_MAX_FRAMES frames, else it returns 0 (header_ok = 0) and replays nothing.
   Replay stops after the header's frame count; complete = that many frames were replayed. */
int ac_replay(const uint8_t *log, uint32_t len, ac_replay_out *out);
/* Replays (the same header checks, up to the header's frames) and samples game_ghost every `period` frames into pts
   (max n); returns the count, raising the period (doubling) until the run fits; *period_out gets the period used, or
   0 when nothing was extracted. */
uint32_t ac_ghost_extract(const uint8_t *log, uint32_t len, uint16_t period, ac_ghost_pt *pts, uint32_t n, uint16_t *period_out);

#ifdef __cplusplus
}
#endif
#endif
