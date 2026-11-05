/* The template game (see game.h). Title: Start plays. Play: the d-pad moves the dot; reaching the goal square ends
   the run finished, Select ends it unfinished, Start pauses. Results: Start leaves (the ROM then resets). */
#include "game.h"
#include "ac_buttons.h"
#include "ac_hash.h"
#include "ac_rng.h"
#include "tuning.h"

static const char *const TROPHIES[2] = {"Reached the goal", "Under 5 seconds"};

/* id, rules version (2: the seed moves the goal), trophy count, trophy names, ghost sample period (frames) */
const ac_game_info GAME_INFO = {"TMPL", 2, 2, TROPHIES, 4};

static struct {
    uint8_t scene, paused, finished;
    uint32_t trophies;
    int16_t x, y;
    int16_t goal_x, goal_y;     /* the classic goal for seed 0, else a seeded spot in the goal region */
    uint16_t prev;              /* last step's buttons, for presses */
    uint32_t steps, run_frames;
    uint32_t hash;              /* running: folds the previous hash and every field in each step */
} s;

static int16_t clamp16(int v, int lo, int hi) { return (int16_t)(v < lo ? lo : v > hi ? hi : v); }

static void rehash(void) {
    ac_hash h;
    h.h = s.hash;
    ac_hash_u8(&h, s.scene);
    ac_hash_u8(&h, s.paused);
    ac_hash_u8(&h, s.finished);
    ac_hash_u32(&h, s.trophies);
    ac_hash_i32(&h, s.x);
    ac_hash_i32(&h, s.y);
    ac_hash_u16(&h, s.prev);
    ac_hash_u32(&h, s.steps);
    ac_hash_u32(&h, s.run_frames);
    s.hash = h.h;
}

void game_init(uint32_t seed) {
    ac_hash h;
    s.scene = SC_TITLE; s.paused = 0; s.finished = 0; s.trophies = 0;
    s.x = START_X; s.y = START_Y; s.prev = 0; s.steps = 0; s.run_frames = 0;
    s.goal_x = GOAL_X; s.goal_y = GOAL_Y;
    if (seed) {                 /* a stamped game makes its seed change its own play; the template moves the goal */
        uint32_t r = ac_rng32(seed);
        s.goal_x = (int16_t)(GOAL_MIN_X + (int)(r % (GOAL_MAX_X - GOAL_MIN_X + 1)));
        s.goal_y = (int16_t)(GOAL_MIN_Y + (int)((r >> 16) % (GOAL_MAX_Y - GOAL_MIN_Y + 1)));
        if (s.goal_x == GOAL_X && s.goal_y == GOAL_Y) s.goal_x = GOAL_MIN_X;
    }
    ac_hash_begin(&h);
    ac_hash_u32(&h, seed);
    s.hash = h.h;
    rehash();
}

static int reached(void) {
    return s.x < s.goal_x + GOAL_SIZE && s.goal_x < s.x + DOT_SIZE && s.y < s.goal_y + GOAL_SIZE &&
           s.goal_y < s.y + DOT_SIZE;
}

void game_step(uint16_t buttons) {
    uint16_t pressed;
    buttons &= BTN_MASK;
    pressed = (uint16_t)(buttons & ~s.prev);
    s.steps++;
    switch (s.scene) {
    case SC_TITLE:
        if (pressed & BTN_START) {
            s.scene = SC_PLAY;
            s.x = START_X; s.y = START_Y; s.run_frames = 0;
        }
        break;
    case SC_PLAY:
        if (pressed & BTN_START) s.paused = (uint8_t)!s.paused;
        if (s.paused) break;
        if (pressed & BTN_SELECT) { s.scene = SC_RESULTS; break; }
        {
            int dx = ((buttons & BTN_RIGHT) ? 1 : 0) - ((buttons & BTN_LEFT) ? 1 : 0);
            int dy = ((buttons & BTN_DOWN) ? 1 : 0) - ((buttons & BTN_UP) ? 1 : 0);
            s.x = clamp16(s.x + dx * DOT_SPEED, 0, FIELD_W - DOT_SIZE);
            s.y = clamp16(s.y + dy * DOT_SPEED, FIELD_TOP, FIELD_H - DOT_SIZE);
        }
        s.run_frames++;
        if (reached()) {
            s.finished = 1;
            s.trophies |= TROPHY_REACHED;
            if (s.run_frames <= FAST_FRAMES) s.trophies |= TROPHY_FAST;
            s.scene = SC_RESULTS;
        }
        break;
    default:                    /* SC_RESULTS */
        if (pressed & BTN_START) s.scene = SC_TITLE;
        break;
    }
    s.prev = buttons;
    rehash();
}

uint32_t game_hash(void) { return s.hash; }

void game_result(ac_result *out) {
    out->finished = s.finished;
    out->frames = s.steps;
    out->score = 0;
    out->time_frames = s.run_frames;
    out->trophies = s.trophies;
}

void game_ghost(ac_ghost_pt *out) {
    out->x = s.x;
    out->y = s.y;
    out->angle = 0;
    out->flags = s.scene == SC_PLAY ? AC_GHOST_PLAY : 0;   /* in play: the runtime aligns the ghost on it */
}

uint8_t game_ended(void) { return s.scene == SC_RESULTS; }

uint8_t rules_scene(void) { return s.scene; }
uint8_t rules_paused(void) { return s.paused; }
int16_t rules_x(void) { return s.x; }
int16_t rules_y(void) { return s.y; }
uint32_t rules_run_frames(void) { return s.run_frames; }
uint8_t rules_finished(void) { return s.finished; }
uint32_t rules_trophies(void) { return s.trophies; }
int16_t rules_goal_x(void) { return s.goal_x; }
int16_t rules_goal_y(void) { return s.goal_y; }
