/* ZIP's world (see zip_world.h). Classic momentum physics on floor surfaces up to 45 degrees:
   - Ground: a ground speed along the surface; slope gravity (running / rolling up / rolling down factors),
     acceleration, braking and friction from the d-pad; a slip with locked input on 45-degree slopes when slow.
     Movement is sub-stepped (no step longer than SUBSTEP_PX on either axis): each sub-step checks the side sensor
     in the direction of travel (walls) and re-snaps two foot sensors to the surface (height masks), which also
     sets the angle; losing the surface launches the player along it.
   - Air: velocity, gravity, air control, the variable jump cut; sub-stepped with side, head and foot sensors;
     landing projects the velocity onto the surface.
   - Loop: a precomputed path (gen/zip_tiles.c); entering its trigger on the ground moving right locks the player to
     it, progress += ground speed with slope gravity along it. Entering slower than LOOP_MIN_SPEED (or slowing below
     SLIP_SPEED beyond 45 degrees) falls off at the quarter point, pushed back.
   - Things: packets, springs, boosters, bugs, spikes, the checkpoint and the finish (zip_level.h); hits scatter up
     to SCATTER_MAX packets in a fixed fan, or respawn at the checkpoint with none.
   Integers only; angles 0-255 per turn, the kit's ac_sin/ac_cos take angle * 4 and return Q1.14. */
#include "zip_world.h"
#include "ac_fix.h"
#include "ac_hash.h"
#include "tuning.h"
#include "zip_level.h"

#define MAX_ENTS 512

static world_t w;
static uint32_t seed;                          /* world_init's: 0 the classic level, else each bug's patrol phase */
static uint8_t ent_state[MAX_ENTS];            /* packet: 1 taken; bug: 1 squashed; spring: frames of its animation
                                                  left; checkpoint: 1 lit */
static zip_scatter scatter[SCATTER_MAX];
static const zip_level *L;

const world_t *world(void) { return &w; }
uint8_t world_ent_state(int i) { return (i >= 0 && i < MAX_ENTS) ? ent_state[i] : 0; }
const zip_scatter *world_scatter(int i) { return &scatter[i]; }

static int32_t sinq(uint8_t a) { return ac_sin((uint16_t)(a * 4)); }
static int32_t cosq(uint8_t a) { return ac_cos((uint16_t)(a * 4)); }
static int32_t iabs(int32_t v) { return v < 0 ? -v : v; }
static int32_t sgn(int32_t v) { return (v > 0) - (v < 0); }
/* v * a Q1.14 factor; |v| <= MAX_SPEED (2^12), so the product fits 32 bits */
static int32_t muls(int32_t v, int32_t q14) { return (v * q14) >> 14; }

/* ---- the level's surfaces ----------------------------------------------------------------------------------- */

static uint8_t tile_at(int32_t c, int32_t r) {
    if (r < 0 || r >= L->h) return 0;
    if (c < 0 || c >= L->w) return 1;              /* the level's sides are walls */
    return L->tiles[r * L->w + c];
}

/* height of the solid part of pixel column px in tile row r */
static int32_t col_height(int32_t px, int32_t r) {
    return ZIP_TILE_MASK[tile_at(px >> 4, r)][px & 15];
}

int world_solid(int32_t px, int32_t py) {
    int32_t h;
    if (py < 0) return 0;
    h = col_height(px, py >> 4);
    return (py & 15) >= 16 - h;
}

/* The surface in column px near py (the feet): its y and the tile id that holds it; 0 if none within a tile. */
static int surface_near(int32_t px, int32_t py, int32_t *sy, uint8_t *tid) {
    int32_t r = py >> 4, h = col_height(px, r);
    if (h == 0) {
        int32_t h2 = col_height(px, r + 1);
        if (h2 == 0) return 0;
        *sy = (r + 1) * 16 + 16 - h2;
        *tid = tile_at(px >> 4, r + 1);
        return 1;
    }
    if (h == 16) {
        int32_t h2 = col_height(px, r - 1);
        if (h2 > 0) {
            *sy = (r - 1) * 16 + 16 - h2;
            *tid = tile_at(px >> 4, r - 1);
            return 1;
        }
        *sy = r * 16;
        *tid = tile_at(px >> 4, r);
        return 1;
    }
    *sy = r * 16 + 16 - h;
    *tid = tile_at(px >> 4, r);
    return 1;
}

/* The higher of the two foot sensors' surfaces: 1 and its y and angle, or 0 if neither sees one. */
static int floor_probe(int32_t *sy, uint8_t *ang) {
    int32_t cx = w.x >> 8, feet = (w.y >> 8) + BODY_H, y1 = 0, y2 = 0;
    uint8_t t1 = 0, t2 = 0;
    int a = surface_near(cx - BODY_W, feet, &y1, &t1);
    int b = surface_near(cx + BODY_W, feet, &y2, &t2);
    if (!a && !b) return 0;
    if (a && (!b || y1 < y2 || (y1 == y2 && w.gsp < 0))) { *sy = y1; *ang = ZIP_TILE_ANGLE[t1]; }
    else { *sy = y2; *ang = ZIP_TILE_ANGLE[t2]; }
    return 1;
}

/* Side sensor: if the pixel at (x +- WALL_W, y - dy) is solid, push the player out of the wall; returns 1 on a hit. */
static int wall_check(int dir, int32_t dy) {
    int32_t sx, sy = (w.y >> 8) - dy;
    int k;
    if (!dir) return 0;
    sx = (w.x >> 8) + dir * WALL_W;
    if (!world_solid(sx, sy)) return 0;
    for (k = 0; k < 16 && world_solid(sx, sy); k++) sx -= dir;
    w.x = (int32_t)((sx - dir * WALL_W) << 8) + 128;
    return 1;
}

/* ---- things --------------------------------------------------------------------------------------------------- */

static int first_ent_from(int32_t x) {             /* the first thing with ent.x >= x (binary search) */
    int lo = 0, hi = L->n_ents;
    while (lo < hi) {
        int mid = (lo + hi) / 2;
        if (L->ents[mid].x < x) lo = mid + 1; else hi = mid;
    }
    return lo;
}

/* A seeded run's head start along bug i's triangle wave, Q8.8 pixels (0 for the classic seed 0): a hash of the seed
   and the bug's index, so no per-bug state and the same for the whole run. */
static uint32_t bug_phase(int i) {
    ac_hash h;
    if (!seed) return 0;
    ac_hash_begin(&h);
    ac_hash_u32(&h, seed);
    ac_hash_u32(&h, (uint32_t)i);
    return h.h;
}

/* Where bug i is on its triangle wave: 0 .. 2 * span - 1 (rising: walking right; then falling: walking left). */
static int32_t bug_wave(int i, int32_t span) {
    return (int32_t)((w.frames * (uint32_t)BUG_SPEED + bug_phase(i) % (uint32_t)(2 * span)) % (uint32_t)(2 * span));
}

int world_bug_left(int i) {
    int32_t span = (int32_t)L->ents[i].arg * 16 * 256 * 2;
    return span != 0 && bug_wave(i, span) >= span;
}

int32_t world_bug_x(int i) {
    /* a bug patrols +- arg tiles around its spot, a triangle wave of the world's frames (no per-bug state) */
    const zip_ent *e = &L->ents[i];
    int32_t range = (int32_t)e->arg * 16 * 256, span = range * 2;
    int32_t t;
    if (span == 0) return (int32_t)e->x << 8;
    t = bug_wave(i, span);
    int32_t off = t < span ? t - range : span - (t - span) - range;
    return ((int32_t)e->x << 8) + off;
}

static void set_air(int32_t xv, int32_t yv) {
    w.mode = MODE_AIR;
    w.xv = xv;
    w.yv = yv;
}

static void respawn(void) {
    int i;
    int32_t x = L->start_x, y = L->start_y;
    for (i = 0; i < L->n_ents; i++) {
        const zip_ent *e = &L->ents[i];
        if (e->kind == ENT_CHECKPOINT && ent_state[i]) { x = e->x; y = e->y - BODY_H; }
    }
    w.x = x << 8; w.y = y << 8;
    w.xv = w.yv = w.gsp = 0;
    w.mode = MODE_GROUND; w.angle = 0;
    w.rolling = w.ball = w.jumping = w.hurt = 0;
    w.slip_lock = 0;
    w.invuln = INVULN_FRAMES;
    w.packets = 0;
    w.respawns++;
    for (i = 0; i < SCATTER_MAX; i++) scatter[i].age = 0;
}

static void scatter_packets(void) {
    int n = w.packets < SCATTER_MAX ? w.packets : SCATTER_MAX, i, slot = 0;
    for (i = 0; i < n; i++) {
        /* the classic fan: pairs mirrored left/right, 22.5 degrees apart from 101.25 degrees, fast ring then slow ring */
        uint8_t a = (uint8_t)(72 + 16 * ((i / 2) % 8));
        int32_t sp = i < 16 ? SCATTER_FAST : SCATTER_SLOW, xv = muls(sp, cosq(a)), yv = -muls(sp, sinq(a));
        if (i & 1) xv = -xv;
        while (slot < SCATTER_MAX && scatter[slot].age) slot++;
        if (slot >= SCATTER_MAX) break;
        scatter[slot].x = w.x; scatter[slot].y = w.y;
        scatter[slot].xv = (int16_t)xv; scatter[slot].yv = (int16_t)yv;
        scatter[slot].age = 1;
    }
    w.packets = 0;
}

static void hit(int32_t from_x) {
    if (w.invuln || w.mode == MODE_LOOP) return;
    w.hits++;
    if (w.packets == 0) { respawn(); return; }
    scatter_packets();
    set_air((w.x < from_x) ? -HURT_XV : HURT_XV, -HURT_YV);
    w.hurt = 1; w.ball = 0; w.rolling = 0; w.jumping = 0;
    w.invuln = INVULN_FRAMES;
}

static int overlap(int32_t px, int32_t py, int32_t hw, int32_t hh, int32_t ex, int32_t ey, int32_t ew, int32_t eh) {
    return iabs(px - ex) < hw + ew && iabs(py - ey) < hh + eh;
}

static void things(void) {
    int32_t px = w.x >> 8, py = w.y >> 8, feet = py + BODY_H;
    int i = first_ent_from(px - 64);
    for (; i < L->n_ents && L->ents[i].x <= px + 64; i++) {
        const zip_ent *e = &L->ents[i];
        switch (e->kind) {
        case ENT_PACKET:
            if (!ent_state[i] && !w.hurt && overlap(px, py, BODY_W, BODY_H, e->x, e->y, PACKET_R, PACKET_R)) {
                ent_state[i] = 1;
                w.packets++;
            }
            break;
        case ENT_SPRING_Y:
        case ENT_SPRING_R:
            if (w.mode != MODE_LOOP && iabs(px - e->x) < 8 + BODY_W - 2 && feet >= e->y - 10 && feet <= e->y + 2 &&
                (w.mode == MODE_GROUND || w.yv >= 0)) {
                int32_t xv = w.mode == MODE_GROUND ? muls(w.gsp, cosq(w.angle)) : w.xv;
                w.y = (int32_t)(e->y - 10 - BODY_H) << 8;
                set_air(xv, -(e->kind == ENT_SPRING_R ? SPRING_RED : SPRING_YELLOW));
                w.pose = POSE_SPRING; w.ball = 0; w.jumping = 0; w.rolling = 0; w.hurt = 0;
                w.sprung = 1;
                ent_state[i] = SPRING_ANIM;
            }
            break;
        case ENT_BOOSTER:
            if (w.mode == MODE_GROUND && iabs(px - e->x) < 12 && feet >= e->y - 4 && feet <= e->y + 4) {
                w.gsp = BOOST_SPEED;
                w.facing = 0;
            }
            break;
        case ENT_BUG:
            if (!ent_state[i]) {
                int32_t bx = world_bug_x(i) >> 8, by = e->y - 8;
                if (overlap(px, py, BODY_W, BODY_H, bx, by, BUG_R, BUG_R)) {
                    if (w.ball || w.rolling || (w.mode == MODE_AIR && w.yv > 0 && py < by)) {
                        ent_state[i] = 1;
                        if (w.mode == MODE_AIR && w.yv > 0) w.yv = -w.yv;   /* bounce off it */
                    } else {
                        hit(bx);
                    }
                }
            }
            break;
        case ENT_SPIKES:
            if (overlap(px, py, BODY_W, BODY_H, e->x, e->y - 4, 7, 4)) hit(e->x);
            break;
        case ENT_CHECKPOINT:
            if (!ent_state[i] && px >= e->x) {
                int j;
                for (j = 0; j < L->n_ents; j++) if (L->ents[j].kind == ENT_CHECKPOINT) ent_state[j] = 0;
                ent_state[i] = 1;
                w.checkpoint = 1;
            }
            break;
        case ENT_FINISH:
            if (px >= e->x) w.at_finish = 1;
            break;
        default:
            break;
        }
    }
}

static void step_scatter(void) {
    int i;
    int32_t px = w.x >> 8, py = w.y >> 8;
    for (i = 0; i < SCATTER_MAX; i++) {
        zip_scatter *p = &scatter[i];
        int32_t sx, sy;
        if (!p->age) continue;
        if (++p->age > SCATTER_LIFE) { p->age = 0; continue; }
        p->yv = (int16_t)(p->yv + SCATTER_GRAVITY);
        if (p->yv > MAX_FALL) p->yv = MAX_FALL;
        p->x += p->xv;
        sx = p->x >> 8;
        if (world_solid(sx + (p->xv > 0 ? 4 : -4), p->y >> 8)) {
            p->x -= p->xv;
            p->xv = (int16_t)(-p->xv / 2);
        }
        p->y += p->yv;
        sy = p->y >> 8;
        if (p->yv > 0 && world_solid(p->x >> 8, sy + 4)) {
            p->y -= p->yv;
            p->yv = (int16_t)(-(p->yv * 3) / 4);
        } else if (p->yv < 0 && world_solid(p->x >> 8, sy - 4)) {
            p->y -= p->yv;
            p->yv = 0;
        }
        if (p->age > SCATTER_WAIT && !w.hurt &&
            overlap(px, py, BODY_W, BODY_H, p->x >> 8, p->y >> 8, PACKET_R, PACKET_R)) {
            p->age = 0;
            w.packets++;
        }
    }
}

/* ---- the player ----------------------------------------------------------------------------------------------- */

static void land(uint8_t ang, int32_t sy) {
    int32_t gsp = muls(w.xv, cosq(ang)) - muls(w.yv, sinq(ang));
    w.mode = MODE_GROUND;
    w.angle = ang;
    w.y = (sy - BODY_H) << 8;
    w.gsp = w.hurt ? 0 : gsp;
    w.xv = w.yv = 0;
    w.ball = 0; w.jumping = 0; w.hurt = 0; w.sprung = 0;
    w.rolling = 0;
}

static void jump(void) {
    uint8_t a = w.angle;
    int32_t xv = muls(w.gsp, cosq(a)) - muls(JUMP_SPEED, sinq(a));
    int32_t yv = -muls(w.gsp, sinq(a)) - muls(JUMP_SPEED, cosq(a));
    set_air(xv, yv);
    w.jumping = 1; w.ball = 1; w.rolling = 0;
}

static void enter_loop(const zip_ent *e) {
    w.mode = MODE_LOOP;
    w.loop_x = e->x;
    w.loop_y = e->y - BODY_H;
    w.loop_pos = 0;
    w.loop_quarter_fail = w.gsp < LOOP_MIN_SPEED;
    if (w.gsp >= LOOP_FULL_SPEED) w.loop_full = 1;
    w.x = (int32_t)w.loop_x << 8;
    w.y = (int32_t)w.loop_y << 8;
    w.angle = 0;
}

static void check_loop_entry(int32_t x_before) {
    int i;
    int32_t a = x_before >> 8, b = w.x >> 8;
    if (w.gsp <= 0 || w.mode != MODE_GROUND) return;
    for (i = first_ent_from(a); i < L->n_ents && L->ents[i].x <= b; i++) {
        const zip_ent *e = &L->ents[i];
        if (e->kind == ENT_LOOP && a < e->x && iabs((w.y >> 8) + BODY_H - e->y) < 6) {
            enter_loop(e);
            return;
        }
    }
}

static void loop_step(void) {
    int32_t len = (int32_t)(ZIP_LOOP_POINTS - 1) * LOOP_STEP_PX * 256;
    int32_t idx, frac, x0, y0, x1, y1;
    uint8_t a;
    w.loop_pos += w.gsp;
    if (w.loop_pos >= len) {                       /* out of the loop, running on */
        w.mode = MODE_GROUND;
        w.x = ((int32_t)w.loop_x << 8) + (w.loop_pos - len);
        w.y = (int32_t)w.loop_y << 8;
        w.angle = 0;
        return;
    }
    if (w.loop_pos < 0) w.loop_pos = 0;
    idx = w.loop_pos / (LOOP_STEP_PX * 256);
    frac = w.loop_pos % (LOOP_STEP_PX * 256);
    x0 = ZIP_LOOP_PATH[idx][0]; y0 = ZIP_LOOP_PATH[idx][1];
    x1 = ZIP_LOOP_PATH[idx + 1][0]; y1 = ZIP_LOOP_PATH[idx + 1][1];
    w.x = ((int32_t)w.loop_x << 8) + x0 * 256 + (x1 - x0) * frac / LOOP_STEP_PX;
    w.y = ((int32_t)w.loop_y << 8) + y0 * 256 + (y1 - y0) * frac / LOOP_STEP_PX;
    a = ZIP_LOOP_ANGLE[idx];
    w.angle = a;
    w.gsp -= muls(LOOP_GRAV, sinq(a));
    /* falling off: a slow entry at the quarter point (the right side, going straight up), or too slow beyond 45 */
    if ((w.loop_quarter_fail && w.loop_pos >= len / 4) || w.gsp <= 0 ||
        (w.gsp < SLIP_SPEED && a > SLIP_ANGLE && a < 256 - SLIP_ANGLE)) {
        int32_t sp = w.gsp > 0 ? w.gsp : 0;
        set_air(muls(sp, cosq(a)) - LOOP_PUSH, -muls(sp, sinq(a)));
        w.angle = 0;
        w.fell_off_loop++;
    }
}

static void ground_step(uint16_t buttons, uint16_t pressed) {
    int input = !w.slip_lock && !w.hurt;
    int right = input && (buttons & 0x0010), left = input && (buttons & 0x0020);
    int32_t s = sinq(w.angle), dx, dy, steps, i, x_before = w.x;
    int8_t sa = (int8_t)w.angle;

    if (input && (pressed & 0x0001)) {             /* A: jump */
        jump();
        return;
    }
    if (input && (buttons & 0x0080) && !w.rolling && iabs(w.gsp) >= ROLL_MIN) w.rolling = 1;
    /* slope gravity */
    if (w.rolling) {
        int uphill = sgn(w.gsp) == sgn(s);
        w.gsp -= muls(uphill ? SLOPE_ROLL_UP : SLOPE_ROLL_DOWN, s);
    } else {
        w.gsp -= muls(SLOPE_RUN, s);
    }
    /* the d-pad */
    if (w.rolling) {
        if (right && w.gsp < 0) { w.gsp += ROLL_DECEL; if (w.gsp > 0) w.gsp = 0; }
        if (left && w.gsp > 0) { w.gsp -= ROLL_DECEL; if (w.gsp < 0) w.gsp = 0; }
        if (w.gsp > 0) w.gsp -= w.gsp < ROLL_FRICTION ? w.gsp : ROLL_FRICTION;
        else if (w.gsp < 0) w.gsp += -w.gsp < ROLL_FRICTION ? -w.gsp : ROLL_FRICTION;
        if (iabs(w.gsp) < UNROLL_SPEED) w.rolling = 0;
    } else if (right) {
        w.facing = 0;
        if (w.gsp < 0) { w.gsp += DECEL; if (w.gsp >= 0) w.gsp = DECEL; }
        else if (w.gsp < TOP_SPEED) { w.gsp += ACCEL; if (w.gsp > TOP_SPEED) w.gsp = TOP_SPEED; }
    } else if (left) {
        w.facing = 1;
        if (w.gsp > 0) { w.gsp -= DECEL; if (w.gsp <= 0) w.gsp = -DECEL; }
        else if (w.gsp > -TOP_SPEED) { w.gsp -= ACCEL; if (w.gsp < -TOP_SPEED) w.gsp = -TOP_SPEED; }
    } else {
        if (w.gsp > 0) w.gsp -= w.gsp < FRICTION ? w.gsp : FRICTION;
        else if (w.gsp < 0) w.gsp += -w.gsp < FRICTION ? -w.gsp : FRICTION;
    }
    if (w.gsp > MAX_SPEED) w.gsp = MAX_SPEED;
    if (w.gsp < -MAX_SPEED) w.gsp = -MAX_SPEED;
    /* slip: (nearly) stopped on a 45-degree slope, the input locks and gravity takes the player down; the lock
       holds while the ground is steep and runs out SLIP_LOCK frames after flatter ground */
    {
        int steep = sa >= SLIP_ANGLE || sa <= -SLIP_ANGLE;
        if (w.slip_lock) { if (!steep) w.slip_lock--; }
        else if (steep && iabs(w.gsp) < SLIP_TRIGGER) w.slip_lock = SLIP_LOCK;
    }

    /* move along the surface, sub-stepped */
    dx = muls(w.gsp, cosq(w.angle));
    dy = -muls(w.gsp, s);
    steps = (iabs(dx) > iabs(dy) ? iabs(dx) : iabs(dy)) / (SUBSTEP_PX * 256) + 1;
    for (i = 0; i < steps; i++) {
        int32_t sy;
        uint8_t ang;
        w.x += dx * (i + 1) / steps - dx * i / steps;
        w.y += dy * (i + 1) / steps - dy * i / steps;
        if (wall_check(sgn(w.gsp), WALL_DY)) { w.gsp = 0; }
        if (!floor_probe(&sy, &ang) || sy - ((w.y >> 8) + BODY_H) > SNAP_MAX ||
            sy - ((w.y >> 8) + BODY_H) < -SNAP_MAX) {
            set_air(muls(w.gsp, cosq(w.angle)), -muls(w.gsp, sinq(w.angle)));
            w.ball = w.rolling;                     /* rolling off an edge stays curled */
            w.rolling = 0;
            return;
        }
        w.y = (sy - BODY_H) << 8;
        w.angle = ang;
        if (w.gsp == 0) break;
    }
    check_loop_entry(x_before);
}

static void air_step(uint16_t buttons) {
    int input = !w.hurt;
    int32_t steps, i, dx, dy;
    if (input && (buttons & 0x0010)) { w.facing = 0; if (w.xv < TOP_SPEED) { w.xv += AIR_ACCEL; if (w.xv > TOP_SPEED) w.xv = TOP_SPEED; } }
    if (input && (buttons & 0x0020)) { w.facing = 1; if (w.xv > -TOP_SPEED) { w.xv -= AIR_ACCEL; if (w.xv < -TOP_SPEED) w.xv = -TOP_SPEED; } }
    if (w.jumping && !(buttons & 0x0001) && w.yv < -JUMP_CAP) w.yv = -JUMP_CAP;
    w.yv += w.hurt ? GRAVITY / 2 + GRAVITY / 4 : GRAVITY;
    if (w.yv > MAX_FALL) w.yv = MAX_FALL;
    if (w.xv > MAX_SPEED) w.xv = MAX_SPEED;
    if (w.xv < -MAX_SPEED) w.xv = -MAX_SPEED;
    dx = w.xv; dy = w.yv;
    steps = (iabs(dx) > iabs(dy) ? iabs(dx) : iabs(dy)) / (SUBSTEP_PX * 256) + 1;
    for (i = 0; i < steps; i++) {
        int32_t sy;
        uint8_t ang;
        w.x += dx * (i + 1) / steps - dx * i / steps;
        if (wall_check(sgn(w.xv), WALL_DY) | wall_check(sgn(w.xv), 0)) { w.xv = 0; dx = 0; }
        w.y += dy * (i + 1) / steps - dy * i / steps;
        if (w.yv < 0) {
            int32_t hy = (w.y >> 8) - BODY_H, cx = w.x >> 8;
            if (world_solid(cx - BODY_W, hy) || world_solid(cx + BODY_W, hy)) {
                w.y = (((hy >> 4) + 1) * 16 + BODY_H) << 8;
                w.yv = 0; dy = 0;
            }
        } else if (floor_probe(&sy, &ang)) {
            int32_t d = sy - ((w.y >> 8) + BODY_H);
            if (d <= 0 && d >= -(SUBSTEP_PX + 8)) {
                land(ang, sy);
                return;
            }
        }
    }
}

static void update_pose(void) {
    if (w.mode == MODE_AIR) {
        if (w.hurt) w.pose = POSE_HURT;
        else if (w.ball) w.pose = POSE_JUMP;
        else if (w.sprung && w.yv < 0) w.pose = POSE_SPRING;
        else w.pose = POSE_FALL;
    } else if (w.rolling) {
        w.pose = POSE_ROLL;
    } else if (iabs(w.gsp) < 0x0020 && w.mode == MODE_GROUND) {
        w.pose = POSE_STAND;
    } else {
        w.pose = POSE_RUN;
    }
    if (w.mode != MODE_AIR && w.gsp) w.facing = w.gsp < 0;
}

/* ---- the interface -------------------------------------------------------------------------------------------- */

void world_init(uint32_t run_seed) {
    world_t z = {0};
    int i;
    seed = run_seed;
    L = zip_level_current();
    w = z;
    for (i = 0; i < MAX_ENTS; i++) ent_state[i] = 0;
    for (i = 0; i < SCATTER_MAX; i++) { zip_scatter e = {0}; scatter[i] = e; }
    w.x = (int32_t)L->start_x << 8;
    w.y = (int32_t)L->start_y << 8;
    w.mode = MODE_GROUND;
}

void world_start(void) {}

void world_step(uint16_t buttons, uint16_t pressed, int autopilot) {
    int i;
    if (autopilot) { buttons = 0; pressed = 0; }      /* past the finish: no input, Zip glides to a stop */
    w.frames++;
    for (i = 0; i < L->n_ents && i < MAX_ENTS; i++) {
        uint8_t k = L->ents[i].kind;
        if ((k == ENT_SPRING_Y || k == ENT_SPRING_R) && ent_state[i]) ent_state[i]--;
    }
    switch (w.mode) {
    case MODE_GROUND: ground_step(buttons, pressed); break;
    case MODE_AIR: air_step(buttons); break;
    default: loop_step(); break;
    }
    if (w.mode == MODE_AIR && w.yv > 0 && w.sprung) w.sprung = 0;
    if (w.invuln) w.invuln--;
    things();
    step_scatter();
    if ((w.y >> 8) > L->h * 16 + 32) {             /* fell out of the level */
        w.hits++;
        respawn();
    }
    update_pose();
}

void world_hash(ac_hash *h) {
    int i;
    ac_hash_i32(h, w.x); ac_hash_i32(h, w.y);
    ac_hash_i32(h, w.xv); ac_hash_i32(h, w.yv); ac_hash_i32(h, w.gsp);
    ac_hash_u8(h, w.mode); ac_hash_u8(h, w.angle); ac_hash_u8(h, w.pose);
    ac_hash_u8(h, w.rolling); ac_hash_u8(h, w.ball); ac_hash_u8(h, w.jumping); ac_hash_u8(h, w.facing);
    ac_hash_u8(h, w.slip_lock); ac_hash_u8(h, w.invuln); ac_hash_u8(h, w.hurt); ac_hash_u8(h, w.sprung);
    ac_hash_u16(h, w.packets); ac_hash_u16(h, w.hits); ac_hash_u16(h, w.respawns);
    ac_hash_u8(h, w.loop_full); ac_hash_u8(h, w.at_finish); ac_hash_u8(h, w.checkpoint);
    ac_hash_u8(h, w.loop_quarter_fail); ac_hash_i32(h, w.loop_pos);
    ac_hash_i32(h, w.loop_x); ac_hash_i32(h, w.loop_y); ac_hash_u16(h, w.fell_off_loop);
    ac_hash_u32(h, w.frames);
    for (i = 0; i < L->n_ents && i < MAX_ENTS; i++) ac_hash_u8(h, ent_state[i]);
    for (i = 0; i < SCATTER_MAX; i++) {
        const zip_scatter *p = &scatter[i];
        ac_hash_u16(h, p->age);
        if (!p->age) continue;
        ac_hash_i32(h, p->x); ac_hash_i32(h, p->y);
        ac_hash_i32(h, p->xv); ac_hash_i32(h, p->yv);
    }
}

/* ---- tests: poke the state (PC library only) ------------------------------------------------------------------- */
#ifdef ZIP_TEST_LEVELS
void world_test_set(int32_t x, int32_t y, int32_t gsp, uint8_t mode, uint8_t angle) {
    w.x = x; w.y = y; w.gsp = gsp; w.mode = mode; w.angle = angle;
    w.xv = w.yv = 0;
}
void world_test_air(int32_t xv, int32_t yv) { w.xv = xv; w.yv = yv; w.mode = MODE_AIR; }
void world_test_packets(uint16_t n) { w.packets = n; }
int world_test_scatter_count(void) {
    int i, n = 0;
    for (i = 0; i < SCATTER_MAX; i++) n += scatter[i].age != 0;
    return n;
}
int32_t world_test_scatter_x(int i) { return scatter[i].x; }
int32_t world_test_scatter_y(int i) { return scatter[i].y; }
uint16_t world_test_scatter_age(int i) { return scatter[i].age; }
void world_test_scatter_place(int i, int32_t x, int32_t y, uint16_t age) {
    scatter[i].x = x; scatter[i].y = y; scatter[i].xv = 0; scatter[i].yv = 0; scatter[i].age = age;
}
#endif

#ifdef ZIP_TEST_LEVELS
/* snapshots for the bot's lookahead (PC library only) */
typedef struct { world_t w; uint8_t ent_state[MAX_ENTS]; zip_scatter scatter[SCATTER_MAX]; } world_snap;
int world_snapshot_size(void) { return (int)sizeof(world_snap); }
void world_save(void *buf) {
    world_snap *p = (world_snap *)buf;
    int i;
    p->w = w;
    for (i = 0; i < MAX_ENTS; i++) p->ent_state[i] = ent_state[i];
    for (i = 0; i < SCATTER_MAX; i++) p->scatter[i] = scatter[i];
}
void world_load(const void *buf) {
    const world_snap *p = (const world_snap *)buf;
    int i;
    w = p->w;
    for (i = 0; i < MAX_ENTS; i++) ent_state[i] = p->ent_state[i];
    for (i = 0; i < SCATTER_MAX; i++) scatter[i] = p->scatter[i];
}
#endif
