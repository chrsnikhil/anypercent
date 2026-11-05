#include "ac_replay.h"
#include "ac_log.h"

/* Opens a log for the linked game: a valid header, the game's id and rules version, a claim within AC_MAX_FRAMES. */
static int open_for_game(ac_log_reader *rd, const uint8_t *log, uint32_t len) {
    int i;
    if (!ac_log_open(rd, log, len)) return 0;
    for (i = 0; i < 4; i++) if (log[4 + i] != (uint8_t)GAME_INFO.id[i]) return 0;
    return ac_log_u32(log + 8) == GAME_INFO.rules_version && ac_log_u32(log + 16) <= AC_MAX_FRAMES;
}

int ac_replay(const uint8_t *log, uint32_t len, ac_replay_out *out) {
    ac_log_reader rd;
    uint16_t b;
    uint32_t n = 0, frames;
    if (!open_for_game(&rd, log, len)) { out->header_ok = 0; return 0; }
    frames = ac_log_u32(log + 16);
    game_init(ac_log_u32(log + 12));
    while (n < frames && ac_log_next(&rd, &b)) { game_step(b); n++; }
    out->header_ok = 1;
    out->frames = n;
    out->final_hash = game_hash();
    out->hash_matches = out->final_hash == ac_log_u32(log + 20);
    out->complete = n == frames;
    game_result(&out->result);
    out->claims_match = out->result.score == ac_log_u32(log + 24) && out->result.trophies == ac_log_u32(log + 28);
    return 1;
}

uint32_t ac_ghost_extract(const uint8_t *log, uint32_t len, uint16_t period, ac_ghost_pt *pts, uint32_t n, uint16_t *period_out) {
    ac_log_reader rd;
    uint16_t b;
    uint32_t frames, count, i;
    *period_out = 0;
    if (!open_for_game(&rd, log, len) || period == 0 || n == 0) return 0;
    frames = ac_log_u32(log + 16);
    while (frames && (frames - 1) / period + 1 > n) {
        if (period >= 0x8000u) return 0;          /* would not fit in a u16 period */
        period = (uint16_t)(period * 2);
    }
    game_init(ac_log_u32(log + 12));
    count = 0; i = 0;
    while (i < frames && ac_log_next(&rd, &b)) {
        game_step(b);
        if (i % period == 0 && count < n) game_ghost(&pts[count++]);
        i++;
    }
    *period_out = period;
    return count;
}
