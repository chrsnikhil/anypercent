/* ZIP's run (see game.h): the scenes, the clock, the trophies, the running hash and the arcade interface. The
   world (player, level, things) is zip_world.c. Title: Start or A. How-to: Start or A plays. Play: Start pauses;
   crossing the finish gate stops the clock, the goal plays GOAL_FRAMES, then the results. Pause: Start resumes,
   Select ends the run unfinished. Results: Start (pressed or held) leaves after RESULTS_LOCK frames; the ROM then resets. */
#include "game.h"
#include "ac_buttons.h"
#include "ac_hash.h"
#include "tuning.h"
#include "zip_world.h"

static const char *const TROPHIES[4] = {"Under 1:30", "Never lost packets", "100 packets", "Loop at full speed"};

/* id, rules version, trophy count, trophy names, ghost sample period (frames) */
const ac_game_info GAME_INFO = {"ZIPG", 2, 4, TROPHIES, GHOST_PERIOD};    /* 2: the seed shifts the bugs */

static struct {
    uint8_t scene, finished;
    uint32_t trophies;
    uint16_t prev;              /* last step's buttons, for presses */
    uint32_t steps, run_frames, scene_frames, goal_frames;
    uint32_t score;             /* packets held at the finish gate */
    uint32_t hash;              /* running: folds the previous hash and every field in each step */
} s;

static void rehash(void) {
    ac_hash h;
    h.h = s.hash;
    ac_hash_u8(&h, s.scene);
    ac_hash_u8(&h, s.finished);
    ac_hash_u32(&h, s.trophies);
    ac_hash_u16(&h, s.prev);
    ac_hash_u32(&h, s.steps);
    ac_hash_u32(&h, s.run_frames);
    ac_hash_u32(&h, s.scene_frames);
    ac_hash_u32(&h, s.goal_frames);
    ac_hash_u32(&h, s.score);
    world_hash(&h);
    s.hash = h.h;
}

static void set_scene(uint8_t scene) {
    s.scene = scene;
    s.scene_frames = 0;
}

void game_init(uint32_t seed) {
    ac_hash h;
    s.scene = SC_TITLE; s.finished = 0; s.trophies = 0; s.prev = 0;
    s.steps = 0; s.run_frames = 0; s.scene_frames = 0; s.goal_frames = 0; s.score = 0;
    world_init(seed);
    ac_hash_begin(&h);
    ac_hash_u32(&h, seed);
    s.hash = h.h;
    rehash();
}

/* Trophies are latched as they happen (the finish ones at the gate). */
static void latch_trophies(void) {
    const world_t *w = world();
    if (w->packets >= PACKETS_TROPHY) s.trophies |= TROPHY_100;
    if (w->loop_full) s.trophies |= TROPHY_LOOP;
    if (s.finished && s.goal_frames == 0) {
        if (s.run_frames <= UNDER_FRAMES) s.trophies |= TROPHY_UNDER;
        if (!w->hits) s.trophies |= TROPHY_NO_LOSS;
    }
}

void game_step(uint16_t buttons) {
    uint16_t pressed;
    buttons &= BTN_MASK;
    pressed = (uint16_t)(buttons & ~s.prev);
    s.steps++;
    s.scene_frames++;
    switch (s.scene) {
    case SC_TITLE:
        if (pressed & (BTN_START | BTN_A)) set_scene(SC_HOWTO);
        break;
    case SC_HOWTO:
        if (pressed & (BTN_START | BTN_A)) {
            set_scene(SC_PLAY);
            s.run_frames = 0;
            world_start();
        }
        break;
    case SC_PLAY:
        if (!s.finished && (pressed & BTN_START)) { set_scene(SC_PAUSE); break; }
        if (s.finished) {
            world_step(0, 0, 1);                       /* the goal run-out: no input */
            if (++s.goal_frames >= GOAL_FRAMES) set_scene(SC_RESULTS);
            break;
        }
        s.run_frames++;
        world_step(buttons, pressed, 0);
        if (world()->at_finish) {
            s.finished = 1;
            s.goal_frames = 0;
            s.score = world()->packets;
        }
        latch_trophies();
        break;
    case SC_PAUSE:
        if (pressed & BTN_START) set_scene(SC_PLAY);
        else if (pressed & BTN_SELECT) set_scene(SC_RESULTS);
        break;
    default:                    /* SC_RESULTS */
        if (s.scene_frames > RESULTS_LOCK && (buttons & BTN_START)) set_scene(SC_TITLE);   /* held counts */
        break;
    }
    s.prev = buttons;
    rehash();
}

uint32_t game_hash(void) { return s.hash; }

void game_result(ac_result *out) {
    out->finished = s.finished;
    out->frames = s.steps;
    out->score = s.score;
    out->time_frames = s.run_frames;
    out->trophies = s.trophies;
}

void game_ghost(ac_ghost_pt *out) {
    const world_t *w = world();
    out->x = (int16_t)(w->x >> 8);
    out->y = (int16_t)(w->y >> 8);
    out->angle = w->angle;
    /* 0x80: in play (the ghosts align on play start); low bits: the respawn epoch, so the runtime never
       interpolates across a respawn teleport */
    out->flags = (uint8_t)(((s.scene == SC_PLAY || s.scene == SC_PAUSE) ? AC_GHOST_PLAY : 0) | (w->respawns & 0x7F));
}

uint8_t game_ended(void) { return s.scene == SC_RESULTS; }

uint8_t rules_scene(void) { return s.scene; }
uint32_t rules_run_frames(void) { return s.run_frames; }
uint8_t rules_finished(void) { return s.finished; }
uint32_t rules_trophies(void) { return s.trophies; }
uint8_t rules_n_trophies(void) { return GAME_INFO.n_trophies; }
const char *rules_trophy_name(int i) { return (i >= 0 && i < GAME_INFO.n_trophies) ? TROPHIES[i] : ""; }
uint16_t rules_ghost_period(void) { return GAME_INFO.ghost_period; }
uint32_t rules_scene_frames(void) { return s.scene_frames; }
int32_t rules_px(void) { return world()->x >> 8; }
int32_t rules_py(void) { return world()->y >> 8; }

#ifdef ZIP_TEST_LEVELS
/* snapshots of the whole game for the bot's lookahead (PC library only) */
int world_snapshot_size(void);
void world_save(void *buf);
void world_load(const void *buf);
int game_snapshot_size(void) { return (int)sizeof(s) + world_snapshot_size(); }
void game_save(void *buf) {
    uint8_t *p = (uint8_t *)buf;
    const uint8_t *q = (const uint8_t *)&s;
    unsigned i;
    for (i = 0; i < sizeof(s); i++) p[i] = q[i];
    world_save(p + sizeof(s));
}
void game_load(const void *buf) {
    const uint8_t *p = (const uint8_t *)buf;
    uint8_t *q = (uint8_t *)&s;
    unsigned i;
    for (i = 0; i < sizeof(s); i++) q[i] = p[i];
    world_load(p + sizeof(s));
}
#endif
