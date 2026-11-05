#include "rules.h"
#include "tuning.h"
#include "rng.h"
#include "ac_rng.h"
#include "scene_office.h"
#include "scene_hall.h"

typedef struct {
    uint8_t on, desk, sitting;
    uint16_t x, y;                          /* quarter pixels */
} Bug;

typedef struct {
    uint16_t x, y;                          /* an attendee's feet in the hall, in quarter pixels */
    uint8_t wp, facing;                     /* the waypoint it walks to, and which way it faces */
    uint8_t pause, gathered;                /* frames left standing at a waypoint; at its pitch spot */
} Crowd;

typedef struct {
    uint8_t scene, paused, carrying, facing, moving, act;
    uint16_t prev;
    uint16_t x, y;                          /* the player's feet in room pixels, in quarter pixels */
    uint8_t dash_left, dash_cool;
    uint8_t energy[DEVS], type_timer[DEVS], drain_timer;
    uint16_t progress, hour_frames, rng;
    uint8_t hour, clock_running, nightfall;
    uint16_t act_frames;
    Bug bug[MAX_BUGS];
    uint8_t next_bug, next_fry, router_fried;
    uint16_t last_commit;
    uint8_t commit_hold, pizza, message, message_timer;
    uint32_t run_frames, hash;
    uint32_t split[3];
    uint8_t room, demoday, walkout, verified, stun, immune, slide, stumble, clear_frames;
    Crowd crowd[HALL_CROWD_N];
} State;

static State s;
static const int16_t hand_x[DEVS] = {HAND0_X, HAND1_X, HAND2_X};
static const int16_t hand_y[DEVS] = {HAND0_Y, HAND1_Y, HAND2_Y};
static const int16_t spawn_x[3] = {BUGSPAWN0_X, BUGSPAWN1_X, BUGSPAWN2_X};
static const int16_t spawn_y[3] = {BUGSPAWN0_Y, BUGSPAWN1_Y, BUGSPAWN2_Y};
static const int16_t perch_x[DEVS] = {BUGDESK0_X, BUGDESK1_X, BUGDESK2_X};
static const int16_t perch_y[DEVS] = {BUGDESK0_Y, BUGDESK1_Y, BUGDESK2_Y};
static const uint8_t start_energy[DEVS] = START_ENERGY;
static const uint16_t bug_schedule[BUG_COUNT][3] = BUG_SCHEDULE;
static const uint16_t router_fries[FRY_COUNT] = ROUTER_FRIES;
static const uint16_t pitch_keys[PITCH_SLIDES] = PITCH_KEYS;

/* This run's act 2 timetable and starting energies: the classic tables for seed 0; any other seed shifts every bug
   spawn by up to BUG_JITTER frames, every router fry by up to FRY_JITTER, the pizza by up to PIZZA_JITTER (each kept
   after the one before it, so the events keep their order) and each dev's starting energy by up to ENERGY_JITTER.
   Set by rules_init / rules_init_seeded; constant for the run (derived from the seed, so not hashed). */
static uint16_t bug_at[BUG_COUNT], fry_at[FRY_COUNT], pizza_at;
static uint8_t energy0[DEVS];

static int32_t jitter(uint32_t *x, int32_t range) {
    *x = ac_rng32(*x);
    return (int32_t)(*x % (uint32_t)(2 * range + 1)) - range;
}

static void set_timetable(uint32_t seed) {
    uint32_t x = seed;
    int32_t prev = 0, v;
    uint8_t i;
    for (i = 0; i < BUG_COUNT; i++) {
        v = bug_schedule[i][0] + (seed ? jitter(&x, BUG_JITTER) : 0);
        if (v <= prev) v = prev + 1;
        bug_at[i] = (uint16_t)v;
        prev = v;
    }
    for (i = 0, prev = 0; i < FRY_COUNT; i++) {
        v = router_fries[i] + (seed ? jitter(&x, FRY_JITTER) : 0);
        if (v <= prev) v = prev + 1;
        fry_at[i] = (uint16_t)v;
        prev = v;
    }
    pizza_at = (uint16_t)(PIZZA_FRAME + (seed ? jitter(&x, PIZZA_JITTER) : 0));
    for (i = 0; i < DEVS; i++) {
        v = start_energy[i] + (seed ? jitter(&x, ENERGY_JITTER) : 0);
        energy0[i] = (uint8_t)(v < 1 ? 1 : v > 255 ? 255 : v);
    }
}
static const int16_t fan_x[HALL_CROWD_N] = {HALL_FAN0_X, HALL_FAN1_X, HALL_FAN2_X, HALL_FAN3_X, HALL_FAN4_X, HALL_FAN5_X};
static const int16_t fan_y[HALL_CROWD_N] = {HALL_FAN0_Y, HALL_FAN1_Y, HALL_FAN2_Y, HALL_FAN3_Y, HALL_FAN4_Y, HALL_FAN5_Y};
#define PITCH_BUTTONS (BTN_A | BTN_B | BTN_UP | BTN_DOWN | BTN_LEFT | BTN_RIGHT)
/* facing 0 is down the screen, then clockwise: 2 right, 4 up, 6 left */
static const int8_t face_dx[8] = {0, 1, 1, 1, 0, -1, -1, -1};
static const int8_t face_dy[8] = {1, 1, 0, -1, -1, -1, 0, 1};

uint8_t rules_walkable(int16_t px, int16_t py) {
    if (s.room == ROOM_HALL) {
        if (px < 0 || py < 0 || px >= HALL_WALK_W * HALL_WALK_CELL || py >= HALL_WALK_H * HALL_WALK_CELL) return 0;
        if (!s.verified && px - HALL_GATE_X <= GATE_HALF_X && HALL_GATE_X - px <= GATE_HALF_X &&
            py - HALL_GATE_Y <= GATE_HALF_Y && HALL_GATE_Y - py <= GATE_HALF_Y) return 0;     /* the gate is shut */
        return hall_walk_grid[(uint16_t)(py / HALL_WALK_CELL) * HALL_WALK_W + (uint16_t)(px / HALL_WALK_CELL)];
    }
    if (px < 0 || py < 0 || px >= WALK_W * WALK_CELL || py >= WALK_H * WALK_CELL) return 0;
    return walk_grid[(uint16_t)(py / WALK_CELL) * WALK_W + (uint16_t)(px / WALK_CELL)];
}

static uint8_t feet_ok(int16_t px, int16_t py) {
    return rules_walkable((int16_t)(px - FEET_HALF), py) && rules_walkable(px, py) &&
           rules_walkable((int16_t)(px + FEET_HALF), py);
}

static uint8_t near(int16_t tx, int16_t ty) {
    int16_t dx = (int16_t)((int16_t)(s.x >> 2) - tx), dy = (int16_t)((int16_t)(s.y >> 2) - ty);
    if (dx < 0) dx = (int16_t)-dx;
    if (dy < 0) dy = (int16_t)-dy;
    return dx <= REACH_X && dy <= REACH_Y;
}

static uint8_t facing_of_dir(int8_t dx, int8_t dy) {
    uint8_t i;
    for (i = 0; i < 8; i++) if (face_dx[i] == dx && face_dy[i] == dy) return i;
    return 0;
}

static uint8_t facing_of(int8_t dx, int8_t dy) {
    uint8_t i;
    for (i = 0; i < 8; i++) if (face_dx[i] == dx && face_dy[i] == dy) return i;
    return s.facing;
}

static void mix(uint32_t v) {
    s.hash = (s.hash ^ v) * 16777619u;
}

static void say(uint8_t m) {
    s.message = m;
    s.message_timer = MESSAGE_FRAMES;
}

static int8_t dev_in_reach(void) {
    uint8_t i;
    for (i = 0; i < DEVS; i++) if (near(hand_x[i], hand_y[i])) return (int8_t)i;
    return -1;
}

static int8_t bug_in_reach(void) {
    uint8_t i;
    for (i = 0; i < MAX_BUGS; i++) {
        if (!s.bug[i].on) continue;
        if (s.bug[i].sitting ? near(hand_x[s.bug[i].desk], hand_y[s.bug[i].desk])
                             : near((int16_t)(s.bug[i].x >> 2), (int16_t)(s.bug[i].y >> 2))) return (int8_t)i;
    }
    return -1;
}

static uint8_t bug_on_desk(uint8_t d) {
    uint8_t i;
    for (i = 0; i < MAX_BUGS; i++) if (s.bug[i].on && s.bug[i].sitting && s.bug[i].desk == d) return 1;
    return 0;
}

/* What A does right now (HINT_*), and its dev or bug in *arg. The same order drives the prompt and the press. */
static uint8_t action(int8_t *arg) {
    int8_t k;
    *arg = 0;
    if (s.act == 3) {
        if (s.room == ROOM_OFFICE && s.carrying == ITEM_NONE && near(HAND0_X, HAND0_Y)) return HINT_LAPTOP;
        if (s.room == ROOM_HALL && !s.verified && near(HALL_ORB_X, HALL_ORB_Y)) return HINT_SCAN;
        if (s.room == ROOM_HALL && s.verified && s.slide == 0 && near(HALL_STAGE_X, HALL_STAGE_Y)) return HINT_PITCH;
        return HINT_NONE;
    }
    if (s.act == 2 && (k = bug_in_reach()) >= 0) { *arg = k; return HINT_STOMP; }
    if (s.router_fried && near(ROUTER_X, ROUTER_Y)) return HINT_RESET;
    if (s.pizza == 1 && near(DOOR_X, DOOR_Y)) return HINT_PAY;
    if (s.carrying == ITEM_CHAI && (k = dev_in_reach()) >= 0) { *arg = k; return HINT_GIVE; }
    if (s.carrying == ITEM_NONE && near(COUNTER_X, COUNTER_Y)) return HINT_TAKE;
    if (s.act == 2 && s.progress >= s.last_commit + COMMIT_MIN && near(SHELF_X, SHELF_Y)) return HINT_COMMIT;
    return HINT_NONE;
}

void rules_init_seeded(uint32_t seed) {
    uint8_t *b = (uint8_t *)&s;
    uint16_t i;
    for (i = 0; i < sizeof(s); i++) b[i] = 0;
    set_timetable(seed);
    s.scene = SC_TITLE;
    s.hash = 2166136261u;
}

void rules_init(void) {
    rules_init_seeded(0);
}

uint16_t rules_schedule(int k) {
    if (k < 0) return 0;
    if (k < BUG_COUNT) return bug_at[k];
    k -= BUG_COUNT;
    if (k < FRY_COUNT) return fry_at[k];
    k -= FRY_COUNT;
    if (k == 0) return pizza_at;
    k -= 1;
    return k < DEVS ? energy0[k] : 0;
}

static void start_run(void) {
    uint16_t i, prev = s.prev;
    uint32_t hash = s.hash;
    uint8_t *b = (uint8_t *)&s;
    for (i = 0; i < sizeof(s); i++) b[i] = 0;
    s.prev = prev;                          /* keep the held buttons, or Start held from the title would pause */
    s.hash = hash;
    s.scene = SC_PLAY;
    s.act = 1;
    s.x = (uint16_t)(START_X << 2);
    s.y = (uint16_t)(START_Y << 2);
    for (i = 0; i < DEVS; i++) s.energy[i] = energy0[i];
    s.rng = RNG_SEED;
}

static void move(uint16_t b, uint16_t pressed) {
    int8_t dx = 0, dy = 0;
    uint8_t sx = WALK_X, sy = WALK_Y;
    uint16_t n;
    if (s.carrying == ITEM_LAPTOP) {        /* the demo laptop: slow, and no dashing with it */
        sx = CARRY_X;
        sy = CARRY_Y;
    }
    if (b & BTN_LEFT) dx = -1; else if (b & BTN_RIGHT) dx = 1;
    if (b & BTN_UP) dy = -1; else if (b & BTN_DOWN) dy = 1;
    if (dx || dy) s.facing = facing_of(dx, dy);
    if ((pressed & BTN_B) && !s.dash_left && !s.dash_cool && s.carrying != ITEM_LAPTOP) s.dash_left = DASH_FRAMES;
    if (s.dash_left) {
        sx = DASH_X;
        sy = DASH_Y;
        if (!dx && !dy) {                     /* a dash with no direction goes the way you face */
            dx = face_dx[s.facing];
            dy = face_dy[s.facing];
        }
        if (--s.dash_left == 0) s.dash_cool = DASH_COOLDOWN;
    } else if (s.dash_cool) {
        s.dash_cool--;
    }
    s.moving = (uint8_t)(dx || dy);
    if (dx) {
        n = (uint16_t)(s.x + dx * sx);
        if (feet_ok((int16_t)(n >> 2), (int16_t)(s.y >> 2))) s.x = n;
    }
    if (dy) {
        n = (uint16_t)(s.y + dy * sy);
        if (feet_ok((int16_t)(s.x >> 2), (int16_t)(n >> 2))) s.y = n;
    }
}

static void use(void) {
    int8_t arg;
    uint8_t i;
    switch (action(&arg)) {
    case HINT_STOMP:
        s.bug[arg].on = 0;
        break;
    case HINT_RESET:
        s.router_fried = 0;
        break;
    case HINT_PAY:
        s.pizza = 2;
        for (i = 0; i < DEVS; i++) s.energy[i] = ENERGY_MAX;
        say(MSG_PAID);
        break;
    case HINT_GIVE:
        s.energy[arg] = ENERGY_MAX;
        s.carrying = ITEM_NONE;
        s.clock_running = 1;
        break;
    case HINT_TAKE:
        s.carrying = ITEM_CHAI;
        break;
    case HINT_LAPTOP:
        s.carrying = ITEM_LAPTOP;
        break;
    case HINT_SCAN:
        s.verified = 1;
        say(MSG_VERIFIED);
        break;
    case HINT_PITCH:
        s.slide = 1;
        break;
    default:                                /* HINT_COMMIT is held, not pressed */
        break;
    }
}

static void commit(uint16_t b) {
    int8_t arg;
    if ((b & BTN_A) && action(&arg) == HINT_COMMIT) {
        if (s.commit_hold < COMMIT_FRAMES && ++s.commit_hold == COMMIT_FRAMES) {
            s.last_commit = s.progress;
            say(MSG_SAVED);
        }
    } else if (!(b & BTN_A) || s.commit_hold < COMMIT_FRAMES) {
        s.commit_hold = 0;                  /* a finished commit stays done until A is released */
    }
}

static void spawn_bug(uint8_t from, uint8_t desk) {
    uint8_t i;
    for (i = 0; i < MAX_BUGS; i++) {
        if (s.bug[i].on) continue;
        s.bug[i].on = 1;
        s.bug[i].sitting = 0;
        s.bug[i].desk = desk;
        s.bug[i].x = (uint16_t)(spawn_x[from] << 2);
        s.bug[i].y = (uint16_t)(spawn_y[from] << 2);
        return;
    }                                       /* six already out: this one is skipped */
}

static uint16_t toward(uint16_t v, uint16_t target, uint8_t step) {
    if (v < target) return (uint16_t)(target - v <= step ? target : v + step);
    if (v > target) return (uint16_t)(v - target <= step ? target : v - step);
    return v;
}

static void act_two_events(void) {
    uint8_t i;
    Bug *g;
    s.act_frames++;
    for (i = 0; i < MAX_BUGS; i++) {         /* crawl first, so a bug spawned this frame starts on its spawn point */
        g = &s.bug[i];
        if (!g->on || g->sitting) continue;
        g->x = toward(g->x, (uint16_t)(perch_x[g->desk] << 2), BUG_STEP_X);
        g->y = toward(g->y, (uint16_t)(perch_y[g->desk] << 2), BUG_STEP_Y);
        if (g->x == (uint16_t)(perch_x[g->desk] << 2) && g->y == (uint16_t)(perch_y[g->desk] << 2)) g->sitting = 1;
    }
    if (s.next_bug < BUG_COUNT && s.act_frames == bug_at[s.next_bug]) {
        spawn_bug((uint8_t)bug_schedule[s.next_bug][1], (uint8_t)bug_schedule[s.next_bug][2]);
        s.next_bug++;
    }
    if (s.next_fry < FRY_COUNT && s.act_frames == fry_at[s.next_fry]) {
        s.router_fried = 1;
        s.progress = s.last_commit;
        say(MSG_ROLLBACK);
        s.next_fry++;
    }
    if (s.pizza == 0 && s.act_frames == pizza_at) s.pizza = 1;
}

static void enter_hall(void) {
    uint8_t k;
    s.room = ROOM_HALL;
    s.x = (uint16_t)(HALL_START_X << 2);
    s.y = (uint16_t)(HALL_START_Y << 2);
    s.facing = 2;                           /* facing right, into the hall */
    for (k = 0; k < HALL_CROWD_N; k++) {
        s.crowd[k].x = (uint16_t)(hall_crowd_path[k][0][0] << 2);
        s.crowd[k].y = (uint16_t)(hall_crowd_path[k][0][1] << 2);
        s.crowd[k].wp = 1;
        s.crowd[k].facing = 0;
    }
}

/* d * CROWD_STEP / major, rounded half away from zero */
static int16_t crowd_share(int16_t d, int16_t major) {
    int32_t n = (int32_t)(d < 0 ? -d : d) * CROWD_STEP * 2 + major;
    int16_t q = (int16_t)(n / (2 * (int32_t)major));
    return d < 0 ? (int16_t)-q : q;
}

/* One frame of walking in a straight line: the longer axis moves CROWD_STEP, the other its share of the distance
   still to go (recomputed every frame, so the feet stay on the line between the waypoints). */
static void crowd_move(Crowd *c, uint16_t tx, uint16_t ty) {
    int16_t dx = (int16_t)(tx - c->x), dy = (int16_t)(ty - c->y);
    int16_t ax = dx < 0 ? (int16_t)-dx : dx, ay = dy < 0 ? (int16_t)-dy : dy, major = ax > ay ? ax : ay;
    if (major <= CROWD_STEP) {
        c->x = tx;
        c->y = ty;
        return;
    }
    c->x = (uint16_t)(c->x + crowd_share(dx, major));
    c->y = (uint16_t)(c->y + crowd_share(dy, major));
}

/* The attendees walk their loops; one within bump range stuns the player (whoever walked into whom). */
static void crowd_step(void) {
    uint8_t k;
    int16_t dx, dy;
    for (k = 0; k < HALL_CROWD_N; k++) {
        Crowd *c = &s.crowd[k];
        uint16_t tx, ty;
        int8_t fx, fy;
        if (s.slide) {                          /* the pitch: everyone gathers to watch; no bumps while pitching */
            tx = (uint16_t)(fan_x[k] << 2);
            ty = (uint16_t)(fan_y[k] << 2);
            c->pause = 0;
            if (c->x == tx && c->y == ty) {
                c->gathered = 1;
                c->facing = 3;                  /* up and right: toward the stage */
                continue;
            }
            fx = (int8_t)(tx > c->x ? 1 : tx < c->x ? -1 : 0);
            fy = (int8_t)(ty > c->y ? 1 : ty < c->y ? -1 : 0);
            c->facing = facing_of_dir(fx, fy);
            crowd_move(c, tx, ty);
            continue;
        }
        if (c->pause) {                         /* standing at a waypoint, looking out at the room */
            c->pause--;
            c->facing = 0;
        } else {
            tx = (uint16_t)(hall_crowd_path[k][c->wp][0] << 2);
            ty = (uint16_t)(hall_crowd_path[k][c->wp][1] << 2);
            fx = (int8_t)(tx > c->x ? 1 : tx < c->x ? -1 : 0);
            fy = (int8_t)(ty > c->y ? 1 : ty < c->y ? -1 : 0);
            if (fx || fy) c->facing = facing_of_dir(fx, fy);
            crowd_move(c, tx, ty);
            if (c->x == tx && c->y == ty) {
                c->pause = (uint8_t)(CROWD_PAUSE_MIN + (k * 37 + c->wp * 53) % CROWD_PAUSE_SPAN);
                c->facing = 0;                  /* arrived: turn to look out at the room */
                c->wp = (uint8_t)((c->wp + 1) % hall_crowd_len[k]);
            }
        }
        dx = (int16_t)((int16_t)(c->x >> 2) - (int16_t)(s.x >> 2));
        dy = (int16_t)((int16_t)(c->y >> 2) - (int16_t)(s.y >> 2));
        if (!s.stun && !s.immune && dx <= BUMP_X && -dx <= BUMP_X && dy <= BUMP_Y && -dy <= BUMP_Y) {
            s.stun = STUN_FRAMES;
            s.immune = STUN_FRAMES + IMMUNE_FRAMES;
        }
    }
}

/* One slide per new press of its button; any other button (or two at once) is a stumble. */
static void pitch_step(uint16_t pressed) {
    s.moving = 0;
    if (s.stumble) {
        s.stumble--;
        return;
    }
    pressed &= PITCH_BUTTONS;
    if (!pressed) return;
    if (pressed != pitch_keys[s.slide - 1]) {
        s.stumble = STUMBLE_FRAMES;
        say(MSG_STUMBLE);
        return;
    }
    s.progress = (uint16_t)(s.progress + PITCH_STEP > PROGRESS_MAX ? PROGRESS_MAX : s.progress + PITCH_STEP);
    if (++s.slide > PITCH_SLIDES) {
        s.progress = PROGRESS_MAX;
        s.split[2] = s.run_frames - s.split[0] - s.split[1];
        s.scene = SC_CLEAR;
        s.clear_frames = 0;
    }
}

static void begin_act_three(void) {
    uint8_t i;
    s.scene = SC_PLAY;
    s.act = 3;
    s.act_frames = 0;
    s.room = ROOM_OFFICE;
    s.carrying = ITEM_NONE;
    for (i = 0; i < MAX_BUGS; i++) s.bug[i].on = 0;
    s.router_fried = 0;
    s.pizza = 2;
    s.commit_hold = 0;
    s.message = 0;
    s.message_timer = 0;
}

static void play_step(uint16_t b, uint16_t pressed) {
    uint8_t i;
    s.run_frames++;
    s.rng = rng_next(s.rng);
    if (s.act == 2) act_two_events();
    if (s.act == 3 && s.room == ROOM_HALL) crowd_step();
    if (++s.drain_timer >= DRAIN_FRAMES) {   /* drain before actions: a hand-over leaves a full 255 */
        s.drain_timer = 0;
        for (i = 0; i < DEVS; i++) if (s.energy[i]) s.energy[i]--;
    }
    if (s.slide) {
        pitch_step(pressed);
    } else if (s.stun) {
        s.stun--;
        s.moving = 0;
    } else {
        move(b, pressed);
        if (pressed & BTN_A) use();
    }
    if (s.immune) s.immune--;
    commit(b);
    for (i = 0; i < DEVS; i++) {
        if (s.act < 3 && s.energy[i] && !s.router_fried && !bug_on_desk(i) && ++s.type_timer[i] >= TYPE_FRAMES) {
            s.type_timer[i] = 0;
            if (s.progress < PROGRESS_MAX) s.progress++;
        }
    }
    if (s.message_timer && --s.message_timer == 0) s.message = 0;
    if (s.scene != SC_PLAY) return;         /* the pitch shipped this frame: the clock does not tick on it */
    if (s.act == 1 && s.progress >= ACT1_GOAL) {  /* checked before the clock: a clear on the last frame counts */
        s.split[0] = s.run_frames;
        s.scene = SC_NIGHTFALL;
        s.nightfall = NIGHTFALL_FRAMES;
        return;
    }
    if (s.act == 2 && s.progress >= ACT2_GOAL) {
        s.split[1] = s.run_frames - s.split[0];
        s.scene = SC_DEMODAY;
        s.demoday = DEMODAY_FRAMES;
        return;
    }
    if (s.act == 3 && s.room == ROOM_OFFICE && s.carrying == ITEM_LAPTOP && near(DOOR_X, DOOR_Y)) {
        s.scene = SC_WALKOUT;
        s.walkout = WALKOUT_FRAMES;
        return;
    }
    if (s.clock_running && ++s.hour_frames >= FRAMES_PER_HOUR) {
        s.hour_frames = 0;
        if (++s.hour >= DEADLINE_HOURS) s.scene = SC_MISSED;
    }
}

void rules_step(uint16_t b) {
    uint16_t pressed = (uint16_t)(b & ~s.prev);
    uint8_t i;
    s.prev = b;
    if (s.scene == SC_TITLE) {
        if (pressed & BTN_START) s.scene = SC_HOWTO;
    } else if (s.scene == SC_HOWTO) {
        if (pressed & (BTN_A | BTN_START)) start_run();
    } else if (s.scene == SC_PLAY) {
        if (pressed & BTN_START) s.paused ^= 1;
        else if (!s.paused) play_step(b, pressed);
    } else if (s.scene == SC_NIGHTFALL) {
        s.run_frames++;
        if (--s.nightfall == 0) {
            s.scene = SC_PLAY;
            s.act = 2;
            s.act_frames = 0;
            s.last_commit = s.progress;
        }
    } else if (s.scene == SC_DEMODAY) {
        s.run_frames++;
        if (--s.demoday == 0) begin_act_three();
    } else if (s.scene == SC_WALKOUT) {
        s.run_frames++;
        if (--s.walkout == WALKOUT_FRAMES / 2) enter_hall();
        if (s.walkout == 0) s.scene = SC_PLAY;
    } else if (s.scene == SC_CLEAR) {
        if (s.clear_frames < SHIPPED_FRAMES) s.clear_frames++;
        else if (pressed & BTN_START) s.scene = SC_TITLE;
    } else if (pressed & BTN_START) {
        s.scene = SC_TITLE;
    }
    mix((uint32_t)s.scene | ((uint32_t)s.paused << 8) | ((uint32_t)s.carrying << 16) | ((uint32_t)s.facing << 24));
    mix(((uint32_t)s.x << 16) | s.y);
    mix(((uint32_t)s.progress << 16) | s.hour_frames);
    mix((uint32_t)s.energy[0] | ((uint32_t)s.energy[1] << 8) | ((uint32_t)s.energy[2] << 16) | ((uint32_t)s.hour << 24));
    mix((uint32_t)s.type_timer[0] | ((uint32_t)s.type_timer[1] << 8) | ((uint32_t)s.type_timer[2] << 16) |
        ((uint32_t)s.drain_timer << 24));
    mix(((uint32_t)s.rng << 16) | ((uint32_t)s.dash_left << 8) | s.dash_cool);
    mix(((uint32_t)s.prev << 16) | ((uint32_t)s.moving << 8) | s.clock_running);
    mix((uint32_t)s.act | ((uint32_t)s.nightfall << 8) | ((uint32_t)s.act_frames << 16));
    mix((uint32_t)s.next_bug | ((uint32_t)s.next_fry << 8) | ((uint32_t)s.router_fried << 16) | ((uint32_t)s.pizza << 24));
    mix(((uint32_t)s.last_commit << 16) | ((uint32_t)s.commit_hold << 8) | s.message);
    mix(s.message_timer);
    for (i = 0; i < MAX_BUGS; i++) {
        mix((uint32_t)s.bug[i].on | ((uint32_t)s.bug[i].sitting << 8) | ((uint32_t)s.bug[i].desk << 16));
        mix(((uint32_t)s.bug[i].x << 16) | s.bug[i].y);
    }
    mix(s.split[0]);
    mix(s.split[1]);
    mix(s.split[2]);
    mix((uint32_t)s.room | ((uint32_t)s.demoday << 8) | ((uint32_t)s.walkout << 16) | ((uint32_t)s.verified << 24));
    mix((uint32_t)s.stun | ((uint32_t)s.immune << 8) | ((uint32_t)s.slide << 16) | ((uint32_t)s.stumble << 24));
    mix(s.clear_frames);
    for (i = 0; i < HALL_CROWD_N; i++) {
        mix(((uint32_t)s.crowd[i].x << 16) | s.crowd[i].y);
        mix((uint32_t)s.crowd[i].wp | ((uint32_t)s.crowd[i].facing << 8) | ((uint32_t)s.crowd[i].pause << 16) |
            ((uint32_t)s.crowd[i].gathered << 24));
    }
    mix(s.run_frames);
}

uint8_t  rules_scene(void)        { return s.scene; }
uint8_t  rules_paused(void)       { return s.paused; }
uint8_t  rules_carrying(void)     { return s.carrying; }
uint8_t  rules_moving(void)       { return s.moving; }
uint8_t  rules_facing(void)       { return s.facing; }
uint8_t  rules_dash_cool(void)    { return s.dash_cool; }
uint8_t  rules_hour(void)         { return s.hour; }
uint8_t  rules_energy(uint8_t i)  { return i < DEVS ? s.energy[i] : 0; }
uint16_t rules_px(void)           { return (uint16_t)(s.x >> 2); }
uint16_t rules_py(void)           { return (uint16_t)(s.y >> 2); }
uint16_t rules_qx(void)           { return s.x; }
uint16_t rules_qy(void)           { return s.y; }
uint16_t rules_progress(void)     { return s.progress; }
uint16_t rules_hour_frames(void)  { return s.hour_frames; }
uint32_t rules_run_frames(void)   { return s.run_frames; }
uint32_t rules_hash(void)         { return s.hash; }
uint8_t  rules_clock_running(void) { return s.clock_running; }
uint8_t  rules_act(void)          { return s.act; }
uint8_t  rules_nightfall(void)    { return s.nightfall; }
uint16_t rules_act_frames(void)   { return s.act_frames; }
uint8_t  rules_bug_on(uint8_t i)      { return i < MAX_BUGS ? s.bug[i].on : 0; }
uint16_t rules_bug_x(uint8_t i)       { return i < MAX_BUGS ? (uint16_t)(s.bug[i].x >> 2) : 0; }
uint16_t rules_bug_y(uint8_t i)       { return i < MAX_BUGS ? (uint16_t)(s.bug[i].y >> 2) : 0; }
uint8_t  rules_bug_sitting(uint8_t i) { return i < MAX_BUGS ? s.bug[i].sitting : 0; }
uint8_t  rules_bug_desk(uint8_t i)    { return i < MAX_BUGS ? s.bug[i].desk : 0; }
uint8_t  rules_router_fried(void) { return s.router_fried; }
uint16_t rules_last_commit(void)  { return s.last_commit; }
uint8_t  rules_commit_hold(void)  { return s.commit_hold; }
uint8_t  rules_pizza(void)        { return s.pizza; }
uint8_t  rules_message(void)      { return s.message; }
uint32_t rules_split(uint8_t act) { return act >= 1 && act <= 3 ? s.split[act - 1] : 0; }
uint8_t  rules_room(void)         { return s.room; }
uint8_t  rules_demoday(void)      { return s.demoday; }
uint8_t  rules_walkout(void)      { return s.walkout; }
uint8_t  rules_verified(void)     { return s.verified; }
uint8_t  rules_stun(void)         { return s.stun; }
uint8_t  rules_immune(void)       { return s.immune; }
uint8_t  rules_crowd_count(void)  { return s.room == ROOM_HALL ? HALL_CROWD_N : 0; }
uint16_t rules_crowd_x(uint8_t i) { return i < HALL_CROWD_N ? (uint16_t)(s.crowd[i].x >> 2) : 0; }
uint16_t rules_crowd_y(uint8_t i) { return i < HALL_CROWD_N ? (uint16_t)(s.crowd[i].y >> 2) : 0; }
uint8_t  rules_crowd_facing(uint8_t i) { return i < HALL_CROWD_N ? s.crowd[i].facing : 0; }
uint8_t  rules_slide(void)        { return s.slide; }
uint8_t  rules_stumble(void)      { return s.stumble; }
uint16_t rules_pitch_key(void)    { return s.slide >= 1 && s.slide <= PITCH_SLIDES ? pitch_keys[s.slide - 1] : 0; }
uint8_t  rules_clear_frames(void) { return s.clear_frames; }
uint8_t  rules_crowd_paused(uint8_t i)   { return i < HALL_CROWD_N ? (uint8_t)(s.crowd[i].pause > 0) : 0; }
uint8_t  rules_crowd_gathered(uint8_t i) { return i < HALL_CROWD_N ? s.crowd[i].gathered : 0; }
uint8_t  rules_crowd_standing(uint8_t i) { return i < HALL_CROWD_N ? (uint8_t)(s.crowd[i].pause > 0 || s.crowd[i].gathered) : 0; }

uint8_t rules_grade(void) {
    if (s.scene == SC_MISSED) return 'F';
    if (s.scene != SC_CLEAR) return 0;
    return s.hour <= GRADE_S ? 'S' : s.hour <= GRADE_A ? 'A' : s.hour <= GRADE_B ? 'B' : 'C';
}

uint8_t rules_hint(void) {
    int8_t arg;
    if (s.scene != SC_PLAY || s.paused) return HINT_NONE;
    return action(&arg);
}

uint8_t rules_hint_arg(void) {
    int8_t arg;
    action(&arg);
    return (uint8_t)arg;
}

uint8_t rules_hint_dev(void) { return rules_hint_arg(); }

uint8_t rules_target(void) {
    uint8_t i, best = 0;
    int8_t bug = -1;
    int16_t d, bestd = 0x7FFF, dx, dy;
    if (s.act == 3) {
        if (s.room == ROOM_OFFICE) return s.carrying == ITEM_LAPTOP ? TARGET_DOOR : TARGET_LAPTOP;
        return s.verified ? TARGET_STAGE : TARGET_ORB;
    }
    if (s.router_fried) return TARGET_ROUTER;
    for (i = 0; i < MAX_BUGS; i++) {
        if (!s.bug[i].on) continue;
        dx = (int16_t)((int16_t)(s.bug[i].x >> 2) - perch_x[s.bug[i].desk]);
        dy = (int16_t)((int16_t)(s.bug[i].y >> 2) - perch_y[s.bug[i].desk]);
        d = (int16_t)(s.bug[i].sitting ? 0 : (dx < 0 ? -dx : dx) + (dy < 0 ? -dy : dy));
        if (d < bestd) { bestd = d; bug = (int8_t)i; }
    }
    if (bug >= 0) return (uint8_t)(TARGET_BUG + bug);
    if (s.pizza == 1) return TARGET_DOOR;
    if (s.carrying != ITEM_NONE) {
        for (i = 1; i < DEVS; i++) if (s.energy[i] < s.energy[best]) best = i;
        return (uint8_t)(TARGET_DEV + best);
    }
    if (s.act == 2 && s.progress >= s.last_commit + COMMIT_NUDGE) return TARGET_SHELF;
    return TARGET_COUNTER;
}

void rules_debug_place(uint16_t x, uint16_t y)     { s.x = (uint16_t)(x << 2); s.y = (uint16_t)(y << 2); }
void rules_debug_energy(uint8_t i, uint8_t e)      { if (i < DEVS) s.energy[i] = e; }
void rules_debug_progress(uint16_t p)              { s.progress = p; }
void rules_debug_clock(uint8_t hour, uint16_t fr)  { s.hour = hour; s.hour_frames = fr; s.clock_running = 1; }

void rules_debug_act2(uint16_t progress) {
    s.scene = SC_PLAY;
    s.act = 2;
    s.act_frames = 0;
    s.progress = progress;
    s.last_commit = progress;
    s.clock_running = 1;
}

void rules_debug_act_frames(uint16_t n) {
    s.act_frames = n;
    s.next_bug = 0;
    while (s.next_bug < BUG_COUNT && bug_at[s.next_bug] <= n) s.next_bug++;
    s.next_fry = 0;
    while (s.next_fry < FRY_COUNT && fry_at[s.next_fry] <= n) s.next_fry++;
}

void rules_debug_act3(uint8_t room) {
    begin_act_three();
    s.progress = ACT2_GOAL;
    s.clock_running = 1;
    if (room == ROOM_HALL) {
        s.carrying = ITEM_LAPTOP;
        enter_hall();
    }
}

void rules_debug_verified(uint8_t v) { s.verified = v; }
