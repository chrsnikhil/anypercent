/* RUSH HOUR's scenes, clock, hash and results (see game.h). Title -> how-to (Start or A) -> play (Start or A);
   in play Start pauses; in the pause Start resumes and Select gives up; reaching the venue door finishes the run.
   Results: Start leaves (the ROM then resets). The player and the tile grid are in physics.c, the rest of the
   level's things in entities.c. */
#include "game.h"
#include "ac_buttons.h"
#include "ac_hash.h"
#include "level.h"
#include "rh_state.h"
#include "tuning.h"
#include <string.h>

static const char *const TROPHIES[4] = {"Under 2:00", "All chai", "No damage", "Checkpoint-free"};

/* id, rules version, trophy count, trophy names, ghost sample period (frames) */
const ac_game_info GAME_INFO = {"RUSH", 2, 4, TROPHIES, 4};    /* 2: the seed starts the bugs (entities.c) */

rh_state rh_s;
#define s rh_s

static void rehash(void) {
    ac_hash h;
    int i;
    h.h = s.hash;
    ac_hash_u8(&h, s.scene);
    ac_hash_u8(&h, s.finished);
    ac_hash_u32(&h, s.trophies);
    ac_hash_u16(&h, s.prev);
    ac_hash_u32(&h, s.steps);
    ac_hash_u32(&h, s.run_frames);
    ac_hash_i32(&h, s.x);
    ac_hash_i32(&h, s.y);
    ac_hash_i32(&h, s.vx);
    ac_hash_i32(&h, s.vy);
    ac_hash_i32(&h, s.prev_y);
    ac_hash_u8(&h, s.on_ground);
    ac_hash_u8(&h, s.facing_left);
    ac_hash_u8(&h, s.coyote);
    ac_hash_u8(&h, s.jump_buf);
    ac_hash_u8(&h, s.jumping);
    ac_hash_u8(&h, s.drop);
    ac_hash_u8(&h, s.hurt_lock);
    ac_hash_u8(&h, s.invuln);
    ac_hash_u8(&h, s.dead);
    ac_hash_u8(&h, s.hp);
    ac_hash_u8(&h, s.shield);
    ac_hash_u8(&h, s.damaged);
    ac_hash_u8(&h, s.touched_checkpoint);
    ac_hash_u16(&h, s.chai);
    ac_hash_u16(&h, s.lives_lost);
    ac_hash_i32(&h, s.spawn_tx);
    ac_hash_i32(&h, s.spawn_ty);
    ac_hash_u16(&h, s.n_ents);
    for (i = 0; i < s.n_ents; i++) {
        const rh_ent *e = &s.ents[i];
        ac_hash_u8(&h, e->type);
        ac_hash_u8(&h, e->state);
        ac_hash_u8(&h, (uint8_t)e->dir);
        ac_hash_u8(&h, e->timer);
        ac_hash_i32(&h, e->x);
        ac_hash_i32(&h, e->y);
    }
    s.hash = h.h;
}

static void new_run(void) {
    s.finished = 0; s.trophies = 0; s.run_frames = 0;
    s.hp = MAX_HP; s.shield = 0; s.damaged = 0; s.touched_checkpoint = 0; s.chai = 0; s.lives_lost = 0;
    s.dead = 0; s.invuln = 0; s.hurt_lock = 0;
    rh_ents_load();
    rh_player_spawn();
}

static void use_level(void) {
    int i;
    s.map = LEVEL_TILES; s.map_w = LEVEL_W; s.map_h = LEVEL_H;
    s.spawn_tx = LEVEL_START_TX; s.spawn_ty = LEVEL_START_TY;
    s.chai_total = 0;
    for (i = 0; i < LEVEL_N_ENTS; i++)
        if (LEVEL_ENTS[i].type == E_CHAI) s.chai_total++;
}

void game_init(uint32_t seed) {
    ac_hash h;
    memset(&s, 0, sizeof s);   /* nothing survives from a previous run in this process */
    s.seed = seed;             /* before new_run(): the level's bugs start from it */
    s.scene = SC_TITLE;
    use_level();                /* always the level: a test's map lasts until the next game_init */
    new_run();
    ac_hash_begin(&h);
    ac_hash_u32(&h, seed);
    s.hash = h.h;
    rehash();
}

/* The trophies a run earns when it reaches the door (latched in the state, so hashed). */
static void finish(void) {
    s.finished = 1;
    if (s.run_frames < UNDER_FRAMES) s.trophies |= TROPHY_UNDER;
    if (s.chai >= s.chai_total) s.trophies |= TROPHY_ALL_CHAI;
    if (!s.damaged) s.trophies |= TROPHY_NO_DAMAGE;
    if (!s.touched_checkpoint) s.trophies |= TROPHY_NO_CHECKPOINT;
    s.scene = SC_RESULTS;
}

void game_step(uint16_t buttons) {
    uint16_t pressed;
    buttons &= BTN_MASK;
    pressed = (uint16_t)(buttons & ~s.prev);
    s.steps++;
    switch (s.scene) {
    case SC_TITLE:
        if (pressed & (BTN_START | BTN_A)) s.scene = SC_HOWTO;
        break;
    case SC_HOWTO:
        if (pressed & (BTN_START | BTN_A)) { s.scene = SC_PLAY; new_run(); }
        break;
    case SC_PLAY:
        if (pressed & BTN_START) { s.scene = SC_PAUSE; break; }
        s.run_frames++;
        rh_player_step(buttons, pressed);
        rh_ents_step(buttons);
        if (s.finished) finish();
        else if (s.run_frames >= TIME_UP_FRAMES) s.scene = SC_RESULTS;      /* time up: unfinished */
        break;
    case SC_PAUSE:
        if (pressed & BTN_START) s.scene = SC_PLAY;
        else if (pressed & BTN_SELECT) s.scene = SC_RESULTS;
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
    out->score = s.chai;
    out->time_frames = s.run_frames;
    out->trophies = s.trophies;
}

uint8_t rules_pose(void);

void game_ghost(ac_ghost_pt *out) {
    out->x = (int16_t)rh_floor_div(s.x, 256);
    out->y = (int16_t)rh_floor_div(s.y, 256);
    out->angle = (uint8_t)(s.facing_left | (rules_pose() << 1) | ((s.vx > 0x0200 || s.vx < -0x0200) ? 0x10 : 0));
    /* Low 7 bits: respawns (a teleport: the ghost never slides across one). AC_GHOST_PLAY: in play (the runtime aligns
       ghosts on the first in-play step). */
    out->flags = (uint8_t)((s.lives_lost & 0x7F) | ((s.scene == SC_PLAY || s.scene == SC_PAUSE) ? AC_GHOST_PLAY : 0));
}

uint8_t game_ended(void) { return s.scene == SC_RESULTS; }

/* ---- reads ---- */
uint8_t rules_scene(void) { return s.scene; }
uint32_t rules_steps(void) { return s.steps; }
uint32_t rules_run_frames(void) { return s.run_frames; }
uint8_t rules_finished(void) { return s.finished; }
uint32_t rules_trophies(void) { return s.trophies; }
int16_t rules_px(void) { return (int16_t)rh_floor_div(s.x, 256); }
int16_t rules_py(void) { return (int16_t)rh_floor_div(s.y, 256); }
int32_t rules_vx(void) { return s.vx; }
int32_t rules_vy(void) { return s.vy; }
uint8_t rules_on_ground(void) { return s.on_ground; }
uint8_t rules_facing_left(void) { return s.facing_left; }
uint8_t rules_hp(void) { return s.hp; }
uint8_t rules_shield(void) { return s.shield; }
uint8_t rules_invuln(void) { return s.invuln; }
uint8_t rules_dead(void) { return s.dead; }
uint16_t rules_chai(void) { return s.chai; }
uint16_t rules_chai_total(void) { return s.chai_total; }
uint16_t rules_lives_lost(void) { return s.lives_lost; }
uint8_t rules_damaged(void) { return s.damaged; }
uint8_t rules_touched_checkpoint(void) { return s.touched_checkpoint; }
uint16_t rules_level_w(void) { return s.map_w; }
uint16_t rules_level_h(void) { return s.map_h; }
uint8_t rules_tile(int tx, int ty) { return rh_tile(tx, ty); }

uint8_t rules_pose(void) {
    if (s.dead) return POSE_DEAD;
    if (s.hurt_lock) return POSE_HURT;
    if (!s.on_ground) return s.vy < 0 ? POSE_JUMP : POSE_FALL;
    return s.vx != 0 ? POSE_RUN : POSE_IDLE;
}

uint16_t rules_ent_count(void) { return s.n_ents; }
static const rh_ent *ent(int i) {
    static const rh_ent none = {E_NONE, ES_GONE, 0, 0, 0, 0};
    return (i >= 0 && i < s.n_ents) ? &s.ents[i] : &none;
}
uint8_t rules_ent_type(int i) { return ent(i)->type; }
uint8_t rules_ent_state(int i) { return ent(i)->state; }
int16_t rules_ent_x(int i) { return (int16_t)rh_floor_div(ent(i)->x, 256); }
int16_t rules_ent_y(int i) { return (int16_t)rh_floor_div(ent(i)->y, 256); }
int8_t rules_ent_dir(int i) { return ent(i)->dir; }
uint8_t rules_ent_timer(int i) { return ent(i)->timer; }

/* ---- debug hooks (tests) ---- */
void rules_debug_place(int px, int py) {
    s.x = px * 256; s.y = py * 256; s.prev_y = s.y; s.vx = 0; s.vy = 0;
    s.on_ground = 0; s.coyote = 0; s.jump_buf = 0; s.jumping = 0;     /* the next step finds the ground */
    rehash();
}

void rules_debug_velocity(int32_t vx, int32_t vy) { s.vx = vx; s.vy = vy; rehash(); }

void rules_debug_map(const uint8_t *tiles, int w, int h) {
    if (!tiles) { use_level(); new_run(); rehash(); return; }
    s.map = tiles; s.map_w = (uint16_t)w; s.map_h = (uint16_t)h;
    s.n_ents = 0; s.chai_total = 0;
    rehash();
}

void rules_debug_add_ent(int type, int tx, int ty) {
    int n = s.n_ents;
    if (n >= MAX_ENTS) return;
    s.n_ents++;
    s.ents[n].type = (uint8_t)type;
    s.ents[n].state = ES_LIVE;
    s.ents[n].dir = -1;
    s.ents[n].timer = 0;
    if (type == E_CHAI) s.chai_total++;
    rh_ent_place(&s.ents[n], tx, ty);
    rehash();
}

void rules_debug_set_start(int tx, int ty) { s.spawn_tx = (int16_t)tx; s.spawn_ty = (int16_t)ty; rh_player_spawn(); rehash(); }

void rules_debug_run_frames(uint32_t frames) { s.run_frames = frames; rehash(); }

uint32_t rules_debug_state_size(void) { return (uint32_t)sizeof(rh_s); }
