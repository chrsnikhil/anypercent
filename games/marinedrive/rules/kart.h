/* The race itself: four karts on the track plane (physics, surfaces, walls, kart contacts, checkpoints, laps,
   placement) and the rivals' driving. Plain C99, integers only; game.c owns one md_race in its state. */
#ifndef KART_H
#define KART_H
#include <stdint.h>
#include "ac_hash.h"
#include "game.h"

typedef struct {
    md_kart k[N_KARTS];
    uint16_t pt[N_KARTS];         /* each kart's nearest centre line point (tracked locally, never jumps) */
    uint8_t wp[N_KARTS];          /* rivals: the waypoint they drive to */
    uint8_t stuck[N_KARTS];       /* rivals: frames barely moving */
    uint8_t recover[N_KARTS];     /* rivals: frames left reversing out of a jam */
    uint8_t order[N_KARTS];       /* standings: kart index by place */
    uint8_t finishers;            /* karts that finished */
    uint8_t player_clean_lap;     /* latched: the player completed a lap without a wall hit */
    /* The rivals' driving for this race, set by race_init from the seed (the classic values for seed 0) and
       constant all race (not hashed: game_init folds the seed into the first hash). */
    int8_t lane[N_KARTS];         /* px right of the centre line */
    uint16_t skill[N_KARTS];      /* top and target speed fraction /256 (0: the player) */
    uint8_t launch[N_KARTS];      /* race frames a rival waits at the green light */
} md_race;

void race_init(md_race *r, uint32_t seed);
/* One race frame: the player's buttons (0 while coasting after the finish), the race frame number (1-based).
   Returns the EV_* bits the player raised. */
uint8_t race_step(md_race *r, uint16_t buttons, uint32_t frame);
void race_hash(const md_race *r, ac_hash *h);
uint8_t race_player_clean_lap(const md_race *r);
void race_place(md_race *r, int i, int32_t px, int32_t py, uint16_t heading);
/* Tests only (through game.c's rules_debug_*): */
void race_debug_move(md_race *r, int i, int32_t px, int32_t py);
void race_debug_set(md_race *r, int i, int32_t speed, uint8_t lap, uint8_t cp);
void race_debug_freeze(uint8_t mask);

uint8_t track_surface(int32_t px, int32_t py);      /* SURF_* at a pixel; outside the map: wall */
uint8_t track_sector_at(int32_t px, int32_t py);    /* sector of the nearest centre point (global search) */

#endif
