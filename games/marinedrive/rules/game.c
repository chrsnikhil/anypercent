/* MARINE DRIVE GP (see game.h). Title: Start. How-to card: Start or A. Countdown: 180 frames, controls locked, Start
   pauses. Race: A throttle, B brake/reverse, d-pad steer, R drift; Start pauses (Start resumes, Select retires).
   The player finishing lap 3 shows FINISH for a moment, then the results; Start there leaves (the ROM resets). */
#include <string.h>

#include "game.h"
#include "ac_buttons.h"
#include "ac_hash.h"
#include "kart.h"
#include "track.h"
#include "tuning.h"

static const char *const TROPHIES[4] = {"Win", "Under 2:15", "Clean lap", "Three drift boosts in one lap"};

/* id, rules version (2: kart contacts step back to the pre-push position; 3: the seed varies the rivals), trophy
   count, trophy names, ghost sample period (frames) */
const ac_game_info GAME_INFO = {"MDGP", 4, 4, TROPHIES, 4};   /* rules 4: the handling */

static struct {
    uint8_t scene, paused_from, finished, placement, events;
    uint16_t countdown, scene_frames;
    uint32_t trophies;
    uint16_t prev;              /* last step's buttons, for presses */
    uint32_t steps, race_frames;
    uint32_t lap_start;         /* race frame the player's current lap began */
    uint32_t lap_frames[LAPS];
    md_race race;
    uint32_t hash;              /* running: folds the previous hash and every field in each step */
} s;

static void set_scene(uint8_t scene) {
    s.scene = scene;
    s.scene_frames = 0;
}

static void rehash(void) {
    ac_hash h;
    int i;
    h.h = s.hash;
    ac_hash_u8(&h, s.scene);
    ac_hash_u8(&h, s.paused_from);
    ac_hash_u8(&h, s.finished);
    ac_hash_u8(&h, s.placement);
    ac_hash_u8(&h, s.events);
    ac_hash_u16(&h, s.countdown);
    ac_hash_u16(&h, s.scene_frames);
    ac_hash_u32(&h, s.trophies);
    ac_hash_u16(&h, s.prev);
    ac_hash_u32(&h, s.steps);
    ac_hash_u32(&h, s.race_frames);
    ac_hash_u32(&h, s.lap_start);
    for (i = 0; i < LAPS; i++) ac_hash_u32(&h, s.lap_frames[i]);
    race_hash(&s.race, &h);
    s.hash = h.h;
}

void game_init(uint32_t seed) {
    ac_hash h;
    int i;
    memset(&s, 0, sizeof s);        /* every field, then the defaults: game_init may run twice in one process */
    s.scene = SC_TITLE; s.paused_from = SC_RACE; s.finished = 0; s.placement = N_KARTS; s.events = 0;
    s.countdown = COUNTDOWN_FRAMES; s.scene_frames = 0; s.trophies = 0; s.prev = 0; s.steps = 0;
    s.race_frames = 0; s.lap_start = 0;
    for (i = 0; i < LAPS; i++) s.lap_frames[i] = 0;
    race_init(&s.race, seed);       /* seed 0: the classic rivals */
    ac_hash_begin(&h);
    ac_hash_u32(&h, seed);
    s.hash = h.h;
    rehash();
}

/* The player's lap bookkeeping and trophies after a race step. */
static void player_laps(uint8_t lap_before) {
    md_kart *p = &s.race.k[0];
    if (p->lap > lap_before && lap_before >= 1 && lap_before <= LAPS) {
        s.lap_frames[lap_before - 1] = s.race_frames - s.lap_start;
        s.lap_start = s.race_frames;
        s.events |= EV_LAP;
        if (p->lap == LAPS) s.events |= EV_FINAL_LAP;
    }
    if (race_player_clean_lap(&s.race)) s.trophies |= TROPHY_CLEAN;
    if (p->lap_boosts >= DRIFT_TROPHY_BOOSTS) s.trophies |= TROPHY_DRIFTS;
}

static void race_frame(uint16_t buttons, uint16_t pressed) {
    uint8_t lap_before = s.race.k[0].lap;
    uint8_t ev;
    (void)pressed;
    s.race_frames++;
    ev = race_step(&s.race, s.scene == SC_RACE ? buttons : 0, s.race_frames);
    s.events |= ev;
    player_laps(lap_before);
    s.placement = s.race.k[0].place;
    if (s.scene == SC_RACE && s.race.k[0].finished) {
        s.finished = 1;
        s.events |= EV_FINISH;
        if (s.placement == 1) s.trophies |= TROPHY_WIN;
        if (s.race.k[0].finish_frame <= FAST_FRAMES) s.trophies |= TROPHY_FAST;
        set_scene(SC_FINISH);
    } else if (s.scene == SC_RACE && s.race_frames >= RACE_LIMIT) {
        set_scene(SC_RESULTS);
    }
}

void game_step(uint16_t buttons) {
    uint16_t pressed;
    buttons &= BTN_MASK;
    pressed = (uint16_t)(buttons & ~s.prev);
    s.steps++;
    s.events = 0;
    if (s.scene_frames < 0xFFFF) s.scene_frames++;
    switch (s.scene) {
    case SC_TITLE:
        if (pressed & BTN_START) set_scene(SC_HOWTO);
        break;
    case SC_HOWTO:
        if (pressed & (BTN_START | BTN_A)) {
            set_scene(SC_COUNTDOWN);
            s.countdown = COUNTDOWN_FRAMES;
        }
        break;
    case SC_COUNTDOWN:
        if (pressed & BTN_START) { s.paused_from = SC_COUNTDOWN; s.scene = SC_PAUSE; break; }
        s.countdown--;
        if (s.countdown == 0) {
            set_scene(SC_RACE);
            s.events |= EV_GO;
        }
        break;
    case SC_RACE:
        if (pressed & BTN_START) { s.paused_from = SC_RACE; s.scene = SC_PAUSE; break; }
        race_frame(buttons, pressed);
        break;
    case SC_PAUSE:
        if (pressed & BTN_SELECT) { set_scene(SC_RESULTS); break; }
        if (pressed & BTN_START) s.scene = s.paused_from;
        break;
    case SC_FINISH:              /* the race runs on (the player coasts) under the FINISH banner */
        race_frame(0, 0);
        if (s.scene_frames >= FINISH_FRAMES) set_scene(SC_RESULTS);
        break;
    default:                     /* SC_RESULTS */
        if (pressed & BTN_START) set_scene(SC_TITLE);
        break;
    }
    s.prev = buttons;
    rehash();
}

uint32_t game_hash(void) { return s.hash; }

void game_result(ac_result *out) {
    out->finished = s.finished;
    out->frames = s.steps;
    out->score = s.finished ? s.placement : 0;
    out->time_frames = s.finished ? s.race.k[0].finish_frame : s.race_frames;
    out->trophies = s.trophies;
}

void game_ghost(ac_ghost_pt *out) {
    const md_kart *p = &s.race.k[0];
    out->x = (int16_t)(p->x >> 16);
    out->y = (int16_t)(p->y >> 16);
    out->angle = (uint8_t)(p->heading >> 2);
    /* in play from the countdown to the finish banner: the runtime aligns the ghost on the first such step */
    out->flags = (uint8_t)((s.scene >= SC_COUNTDOWN && s.scene <= SC_FINISH) ? AC_GHOST_PLAY : 0);
}

uint8_t game_ended(void) { return s.scene == SC_RESULTS; }

uint8_t rules_scene(void) { return s.scene; }
uint16_t rules_countdown(void) { return s.countdown; }
uint8_t rules_paused_from(void) { return s.paused_from; }
uint32_t rules_race_frames(void) { return s.race_frames; }
uint16_t rules_scene_frames(void) { return s.scene_frames; }
uint8_t rules_finished(void) { return s.finished; }
uint32_t rules_trophies(void) { return s.trophies; }
uint8_t rules_placement(void) { return s.placement; }
void rules_kart(int i, md_kart *out) { *out = s.race.k[i & 3]; }
uint8_t rules_order(int place) { return s.race.order[(place - 1) & 3]; }
uint8_t rules_events(void) { return s.events; }
uint32_t rules_lap_frames(int lap) { return lap >= 1 && lap <= LAPS ? s.lap_frames[lap - 1] : 0; }
uint8_t rules_surface_at(int32_t px, int32_t py) { return track_surface(px, py); }
uint8_t rules_sector_at(int32_t px, int32_t py) { return track_sector_at(px, py); }
int32_t rules_track_len(void) { return TRACK_LEN; }
uint8_t rules_n_waypoints(void) { return TRACK_WAYPOINTS; }
void rules_debug_place(int i, int32_t px, int32_t py, uint16_t heading) {
    race_place(&s.race, i & 3, px, py, heading);
    rehash();
}
void rules_debug_move(int i, int32_t px, int32_t py) { race_debug_move(&s.race, i & 3, px, py); }
void rules_debug_set(int i, int32_t speed, uint8_t lap, uint8_t cp) { race_debug_set(&s.race, i & 3, speed, lap, cp); }
void rules_debug_freeze(uint8_t mask) { race_debug_freeze(mask); }
