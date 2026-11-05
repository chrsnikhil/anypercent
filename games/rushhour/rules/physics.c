/* The player and the tile grid. Positions are Q8.8 pixels; the player's hitbox is PLAYER_W x PLAYER_H with its
   top-left at (x, y). Movement is axis-separated (x, then y) in one-pixel steps, so no speed can carry the hitbox
   through a tile. One-way platforms block only a downward step whose feet enter the tile's top pixel row (so only
   from above), and not while dropping (Down + A). */
#include "ac_buttons.h"
#include "rh_state.h"
#include "tuning.h"
#define s rh_s

int rh_floor_div(int32_t v, int32_t d) { return (int)(v >= 0 ? v / d : -((-v + d - 1) / d)); }

uint8_t rh_tile(int tx, int ty) {
    if (tx < 0 || tx >= s.map_w) return T_SOLID;         /* the level's sides are walls */
    if (ty < 0 || ty >= s.map_h) return T_EMPTY;         /* open above; below is the pit */
    return s.map[ty * s.map_w + tx];
}

static int px_of(int32_t v) { return rh_floor_div(v, 256); }

/* Does a PLAYER_W x PLAYER_H box at pixel (px, py) overlap a solid tile? */
static int box_solid(int px, int py) {
    int tx, ty;
    int tx0 = rh_floor_div(px, TILE), tx1 = rh_floor_div(px + PLAYER_W - 1, TILE);
    int ty0 = rh_floor_div(py, TILE), ty1 = rh_floor_div(py + PLAYER_H - 1, TILE);
    for (ty = ty0; ty <= ty1; ty++)
        for (tx = tx0; tx <= tx1; tx++)
            if (rh_tile(tx, ty) == T_SOLID) return 1;
    return 0;
}

/* With the box at (px, py), are its feet (bottom pixel row) on the top pixel row of a one-way tile? */
static int box_oneway_top(int px, int py) {
    int tx, feet = py + PLAYER_H - 1, ty = rh_floor_div(feet, TILE);
    if (feet - ty * TILE != 0) return 0;
    for (tx = rh_floor_div(px, TILE); tx <= rh_floor_div(px + PLAYER_W - 1, TILE); tx++)
        if (rh_tile(tx, ty) == T_ONEWAY) return 1;
    return 0;
}

static int grounded(void) {
    int px = px_of(s.x), py = px_of(s.y);
    return box_solid(px, py + 1) || (!s.drop && box_oneway_top(px, py + 1));
}

static int on_oneway_only(void) {
    int px = px_of(s.x), py = px_of(s.y);
    return !box_solid(px, py + 1) && box_oneway_top(px, py + 1);
}

static void move_x(int32_t dv) {
    int32_t target = s.x + dv;
    int cur = px_of(s.x), goal = px_of(target), py = px_of(s.y);
    int step = goal > cur ? 1 : -1;
    while (cur != goal) {
        if (box_solid(cur + step, py)) {
            s.x = cur * 256 + (step > 0 ? 255 : 0);
            s.vx = 0;
            return;
        }
        cur += step;
    }
    s.x = target;
}

static void move_y(int32_t dv) {
    int32_t target = s.y + dv;
    int cur = px_of(s.y), goal = px_of(target), px = px_of(s.x);
    int step = goal > cur ? 1 : -1;
    while (cur != goal) {
        int n = cur + step;
        if (box_solid(px, n) || (step > 0 && !s.drop && box_oneway_top(px, n))) {
            s.y = cur * 256 + (step > 0 ? 255 : 0);
            s.vy = 0;
            if (step < 0) s.jumping = 0;             /* head bump */
            return;
        }
        cur = n;
    }
    s.y = target;
}

void rh_player_spawn(void) {
    s.x = (s.spawn_tx * TILE + (TILE - PLAYER_W) / 2) * 256;
    s.y = ((s.spawn_ty + 1) * TILE - PLAYER_H) * 256;
    s.prev_y = s.y;
    s.vx = 0; s.vy = 0;
    s.on_ground = 1; s.coyote = COYOTE_FRAMES; s.jump_buf = 0; s.jumping = 0; s.drop = 0; s.hurt_lock = 0;
}

void rh_player_die(void) {
    if (s.dead) return;
    s.dead = DEATH_FRAMES;
    s.damaged = 1;
    s.lives_lost++;
    s.vx = 0; s.vy = 0; s.shield = 0; s.hurt_lock = 0; s.invuln = 0; s.jumping = 0;
}

void rh_player_hurt(int32_t from_center_x) {
    int32_t center = s.x + PLAYER_W * 128;
    if (s.invuln || s.dead) return;
    if (s.shield) {
        s.shield = 0;                                 /* the orb takes it: not damage */
    } else {
        s.damaged = 1;
        if (s.hp) s.hp--;
        if (s.hp == 0) { rh_player_die(); return; }
    }
    s.vx = center < from_center_x ? -HURT_VX : HURT_VX;
    s.vy = HURT_VY;
    s.hurt_lock = HURT_LOCK;
    s.invuln = INVULN_FRAMES;
    s.jumping = 0; s.on_ground = 0; s.coyote = 0; s.jump_buf = 0;
}

static int32_t toward(int32_t v, int32_t target, int32_t step) {
    if (v < target) return v + step > target ? target : v + step;
    if (v > target) return v - step < target ? target : v - step;
    return v;
}

/* Spikes hurt in the bottom half of their tile (less 2 px each side). */
static void spikes(void) {
    int tx, ty, px = px_of(s.x), py = px_of(s.y);
    for (ty = rh_floor_div(py, TILE); ty <= rh_floor_div(py + PLAYER_H - 1, TILE); ty++)
        for (tx = rh_floor_div(px, TILE); tx <= rh_floor_div(px + PLAYER_W - 1, TILE); tx++)
            if (rh_tile(tx, ty) == T_SPIKE) {
                int zx = tx * TILE + 2, zy = ty * TILE + TILE / 2;
                if (px < zx + TILE - 4 && zx < px + PLAYER_W && py < zy + TILE / 2 && zy < py + PLAYER_H) {
                    rh_player_hurt((tx * TILE + TILE / 2) * 256);
                    return;
                }
            }
}

void rh_player_step(uint16_t buttons, uint16_t pressed) {
    int dir;
    int32_t max;
    s.prev_y = s.y;
    if (s.dead) {
        if (--s.dead == 0) {
            rh_player_spawn();
            s.hp = MAX_HP;
            s.invuln = INVULN_FRAMES;
        }
        return;
    }
    if (s.invuln) s.invuln--;
    if (s.drop) s.drop--;

    /* run and walk */
    dir = ((buttons & BTN_RIGHT) ? 1 : 0) - ((buttons & BTN_LEFT) ? 1 : 0);
    max = (buttons & BTN_B) ? RUN_MAX : WALK_MAX;
    if (s.hurt_lock) {
        s.hurt_lock--;
    } else if (dir) {
        s.facing_left = (uint8_t)(dir < 0);
        if (s.vx * dir < 0) {
            s.vx += dir * (s.on_ground ? TURN_DECEL : 2 * AIR_ACCEL);
        } else if (s.vx * dir < max) {
            s.vx += dir * (s.on_ground ? GROUND_ACCEL : AIR_ACCEL);
            if (s.vx * dir > max) s.vx = dir * max;
        } else if (s.on_ground) {
            s.vx = toward(s.vx, dir * max, FRICTION);  /* let go of B at a run */
        }
    } else if (s.on_ground) {
        s.vx = toward(s.vx, 0, FRICTION);
    }

    /* jump (buffered, with coyote time) or drop through a one-way platform */
    if (pressed & BTN_A) {
        if ((buttons & BTN_DOWN) && s.on_ground && on_oneway_only()) {
            s.drop = DROP_FRAMES;
            s.on_ground = 0; s.coyote = 0;
        } else {
            s.jump_buf = BUFFER_FRAMES;
        }
    }
    if (s.jump_buf && s.coyote && !s.drop) {
        s.vy = JUMP_VY;
        s.jumping = 1;
        s.jump_buf = 0; s.coyote = 0; s.on_ground = 0;
    }
    if (!(buttons & BTN_A)) s.jumping = 0;
    s.vy += (s.jumping && s.vy < 0) ? GRAVITY_HOLD : GRAVITY;
    if (s.vy > MAX_FALL) s.vy = MAX_FALL;

    move_x(s.vx);
    move_y(s.vy);

    s.on_ground = (uint8_t)grounded();
    if (s.on_ground) {
        if (s.vy > 0) s.vy = 0;
        s.coyote = COYOTE_FRAMES;
    } else if (s.coyote) {
        s.coyote--;
    }
    if (s.jump_buf && !(pressed & BTN_A)) s.jump_buf--;

    if (px_of(s.y) >= s.map_h * TILE) { rh_player_die(); return; }
    spikes();
}
