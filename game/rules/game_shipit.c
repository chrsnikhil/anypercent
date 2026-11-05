/* SHIP IT! behind the arcade kit's game interface (arcade/src/ac_game.h). game_init's seed shifts act 2's timetable
   and the starting energies (rules_init_seeded; 0 is the classic run); the ROM records the seed it booted with
   (src/runlog.cpp). The ROM steps through game_step too (src/main.cpp), so game_result's frames counts the steps
   since boot there as in a replay. */
#include "ac_game.h"
#include "rules.h"

static const char *const TROPHIES[4] = {"Shipped", "Grade A or better", "Grade S", "Shipped before hour 24"};

const ac_game_info GAME_INFO = {{'S', 'H', 'I', 'P'}, 2, 4, TROPHIES, 4};    /* 2: the seed shifts act 2 */

static uint32_t steps;

void game_init(uint32_t seed) {
    steps = 0;
    rules_init_seeded(seed);
}

void game_step(uint16_t buttons) {
    rules_step(buttons);
    steps++;
}

uint32_t game_hash(void) {
    return rules_hash();
}

void game_result(ac_result *out) {
    uint8_t g = rules_grade();
    uint8_t shipped = g == 'S' || g == 'A' || g == 'B' || g == 'C';
    out->finished = shipped;
    out->frames = steps;
    out->score = 0;
    out->time_frames = rules_run_frames();
    out->trophies = 0;
    if (shipped) {
        out->trophies |= 1u;
        if (g == 'A' || g == 'S') out->trophies |= 2u;
        if (g == 'S') out->trophies |= 4u;
        if (rules_hour() < 24) out->trophies |= 8u;
    }
}

void game_ghost(ac_ghost_pt *out) {
    out->x = (int16_t)rules_px();
    out->y = (int16_t)rules_py();
    out->angle = rules_facing();
    out->flags = (uint8_t)(rules_room() | (rules_scene() == SC_PLAY ? AC_GHOST_PLAY : 0));
}
