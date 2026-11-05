/* The race (see kart.h): kart physics on the track plane, surfaces, walls, kart contacts, checkpoints, laps,
   placement, and the rivals' driving. Integers only.

   A kart's velocity is a vector; each frame it is split into the part along the heading (the throttle, a torque
   curve, and the brakes act on it) and the part across it (scrubbed by grip: most of it normally, less of it when a
   hard turn at speed overwhelms the tyres, little of it while drifting, so the kart slides). Steering goes through a
   wheel that turns STEER_RAMP a frame, and how far full lock turns the kart eases off at speed and tightens when
   braking. The kart moves in two half steps, each followed by a push out of any wall cell its circle overlaps; a
   hit bounces the velocity's part into the wall back out (WALL_BOUNCE) and keeps most of the part along it
   (WALL_SCRAPE). Progress is each kart's nearest centre line point, searched only near the last one, so a kart can
   never skip checkpoints. */
#include "kart.h"
#include "ac_buttons.h"
#include "ac_fix.h"
#include "ac_rng.h"
#include "track.h"
#include "tuning.h"

#define Q14 16384
#define WALL_HIT_MIN 0x00004000     /* a push into a wall faster than this (px/frame, Q16) is a hit */

static const uint16_t SKILL_Q8[N_KARTS] = {0, AI_SKILL_1_Q8, AI_SKILL_2_Q8, AI_SKILL_3_Q8};
static const int8_t AI_LANE[N_KARTS] = {0, AI_LANE_1, AI_LANE_2, AI_LANE_3};
static uint8_t frozen;              /* tests only (rules_debug_freeze): karts whose input is forced to 0 */

/* ---- the track ---------------------------------------------------------------------------------------------- */

static int is_wall_cell(int cx, int cy) {
    if (cx < 0 || cy < 0 || cx >= TRACK_CELLS || cy >= TRACK_CELLS) return 1;
    return md_cells[cy * TRACK_CELLS + cx] == SURF_WALL;
}

uint8_t track_surface(int32_t px, int32_t py) {
    if (px < 0 || py < 0 || px >= TRACK_CELLS * TRACK_CELL || py >= TRACK_CELLS * TRACK_CELL) return SURF_WALL;
    return md_cells[(py / TRACK_CELL) * TRACK_CELLS + px / TRACK_CELL];
}

static int32_t dist2(int32_t px, int32_t py, int i) {
    int32_t dx = px - md_points[i][0], dy = py - md_points[i][1];
    return dx * dx + dy * dy;
}

static uint16_t nearest_point(int32_t px, int32_t py) {
    int i, best = 0;
    int32_t bd = dist2(px, py, 0);
    for (i = 1; i < TRACK_POINTS; i++) {
        int32_t d = dist2(px, py, i);
        if (d < bd) { bd = d; best = i; }
    }
    return (uint16_t)best;
}

uint8_t track_sector_at(int32_t px, int32_t py) {
    return (uint8_t)(nearest_point(px, py) * TRACK_SECTORS / TRACK_POINTS);
}

static int wrap_pt(int i) { return (i % TRACK_POINTS + TRACK_POINTS) % TRACK_POINTS; }

/* The kart's point after a move: the nearest within TRACK_SEARCH points of the last one, if the kart is on its
   corridor. */
static uint16_t track_follow(uint16_t last, int32_t x, int32_t y) {
    int d, best = last;
    int32_t px = x >> 16, py = y >> 16;
    int32_t bd = dist2(px, py, last);
    for (d = -TRACK_SEARCH; d <= TRACK_SEARCH; d++) {
        int i = wrap_pt(last + d);
        int32_t dd = dist2(px, py, i);
        if (dd < bd) { bd = dd; best = i; }
    }
    /* off the corridor (only possible by being put there): the kart keeps its point until it comes back */
    if (bd > TRACK_CORRIDOR * TRACK_CORRIDOR) return last;
    return (uint16_t)best;
}

/* Arc position of (x, y) near point pt, in 1/16 px: the point's arc plus the projection on the local direction. */
static int32_t arc16(uint16_t pt, int32_t x, int32_t y) {
    int a = wrap_pt(pt - 1), b = wrap_pt(pt + 1);
    int32_t tx = md_points[b][0] - md_points[a][0], ty = md_points[b][1] - md_points[a][1];
    int32_t len = (int32_t)ac_isqrt((uint32_t)(tx * tx + ty * ty));
    int32_t dx = (x >> 12) - (md_points[pt][0] << 4), dy = (y >> 12) - (md_points[pt][1] << 4);   /* 1/16 px */
    int32_t along = len ? (dx * tx + dy * ty) / len : 0;
    int32_t half = TRACK_POINT_STEP * 8;
    if (along > half) along = half;
    if (along < -half) along = -half;
    return (int32_t)pt * TRACK_POINT_STEP * 16 + along;
}

/* ---- setup ------------------------------------------------------------------------------------------------- */

void race_place(md_race *r, int i, int32_t px, int32_t py, uint16_t heading) {
    md_kart *k = &r->k[i];
    k->x = px << 16; k->y = py << 16; k->vx = 0; k->vy = 0; k->speed = 0;
    k->heading = (uint16_t)(heading & 1023);
    k->drift = DRIFT_NONE; k->drift_charge = 0; k->boost = 0; k->steer = 0;
    k->surface = track_surface(px, py);
    r->pt[i] = nearest_point(px, py);
}

void race_init(md_race *r, uint32_t seed) {
    int i;
    uint32_t x = seed;
    frozen = 0;
    for (i = 0; i < N_KARTS; i++) {                 /* the classic rivals, then the seed's variations */
        r->lane[i] = AI_LANE[i];
        r->skill[i] = SKILL_Q8[i];
        r->launch[i] = 0;
        if (seed && i > 0) {
            x = ac_rng32(x);
            r->lane[i] = (int8_t)(AI_LANE[i] + (int)(x % (2 * AI_LANE_JITTER + 1)) - AI_LANE_JITTER);
            r->skill[i] = (uint16_t)(SKILL_Q8[i] - (x >> 8) % (AI_SKILL_JITTER + 1));
            r->launch[i] = (uint8_t)((x >> 16) % (AI_LAUNCH_MAX + 1));
        }
    }
    for (i = 0; i < N_KARTS; i++) {
        md_kart *k = &r->k[i];
        k->progress = 0; k->finish_frame = 0; k->wall_hits = 0;
        k->lap = 0; k->cp = TRACK_SECTORS - 1; k->finished = 0;
        k->lap_boosts = 0; k->lap_clean = 1;
        race_place(r, i, md_grid[i][0], md_grid[i][1], (uint16_t)md_grid[i][2]);
        k->place = (uint8_t)(i == 0 ? N_KARTS : i);
        r->order[i] = (uint8_t)((i + 1) % N_KARTS);
        r->wp[i] = 0;
        r->stuck[i] = 0;
        r->recover[i] = 0;
    }
    r->finishers = 0;
    r->player_clean_lap = 0;
    for (i = 0; i < N_KARTS; i++) r->k[i].progress = arc16(r->pt[i], r->k[i].x, r->k[i].y) - TRACK_LEN * 16;
}

/* ---- physics ----------------------------------------------------------------------------------------------- */

static int32_t mul_q14(int32_t v, int32_t q14) { return (int32_t)(((int64_t)v * q14) >> 14); }

static int32_t surface_top(uint8_t surface) {
    return surface == SURF_CURB ? TOP_CURB : surface == SURF_SLOW ? TOP_SLOW : TOP_ROAD;
}

/* Pushes the kart's circle out of the wall cells it overlaps; reflects and halves the velocity on a hit.
   Returns 1 on a hit. prev_x/prev_y: where the centre was before this move (fallback if it got inside a cell). */
static int resolve_walls(md_kart *k, int32_t prev_x, int32_t prev_y) {
    const int32_t R = KART_RADIUS << 16;
    int hit = 0, cx, cy, pass;
    int32_t pcx = k->x >> 16, pcy = k->y >> 16;
    if (is_wall_cell((int)(pcx >> 3), (int)(pcy >> 3))) {         /* the centre entered a wall: step back */
        k->x = prev_x; k->y = prev_y;
        if ((int64_t)k->vx * k->vx + (int64_t)k->vy * k->vy > (int64_t)WALL_HIT_MIN * WALL_HIT_MIN) hit = 1;
        k->vx = -k->vx / 2; k->vy = -k->vy / 2;
        return hit;
    }
    for (pass = 0; pass < 2; pass++) {
        int32_t bx = (k->x >> 16) >> 3, by = (k->y >> 16) >> 3;
        for (cy = (int)by - 1; cy <= (int)by + 1; cy++) {
            for (cx = (int)bx - 1; cx <= (int)bx + 1; cx++) {
                int32_t qx, qy, dx, dy, d;
                int64_t d2;
                int32_t nx, ny, vn;
                if (!is_wall_cell(cx, cy)) continue;
                qx = k->x; qy = k->y;                                 /* the closest point of the cell, Q16 */
                if (qx < (cx << 19)) qx = cx << 19;
                if (qx > ((cx + 1) << 19)) qx = (cx + 1) << 19;
                if (qy < (cy << 19)) qy = cy << 19;
                if (qy > ((cy + 1) << 19)) qy = (cy + 1) << 19;
                dx = k->x - qx; dy = k->y - qy;
                d2 = (int64_t)dx * dx + (int64_t)dy * dy;
                if (d2 >= (int64_t)R * R) continue;
                /* distance in 1/256 px for the unit normal */
                d = (int32_t)ac_isqrt((uint32_t)(d2 >> 16));          /* Q8 */
                if (d == 0) continue;                                  /* on the corner exactly: the next pass */
                nx = (int32_t)(((int64_t)(dx >> 8) << 14) / d);      /* Q14 unit normal, out of the wall */
                ny = (int32_t)(((int64_t)(dy >> 8) << 14) / d);
                {
                    int32_t push = R - (d << 8) + 1;                  /* Q16, one unit past the contact */
                    k->x += mul_q14(push, nx);
                    k->y += mul_q14(push, ny);
                }
                vn = mul_q14(k->vx, nx) + mul_q14(k->vy, ny);          /* < 0: moving into the wall */
                if (vn < 0) {
                    if (-vn > WALL_HIT_MIN) {                        /* along it: scraped; into it: bounced */
                        int32_t tx = k->vx - mul_q14(vn, nx), ty = k->vy - mul_q14(vn, ny);
                        int32_t out = -vn * WALL_BOUNCE_Q8 / 256;
                        k->vx = tx * WALL_SCRAPE_Q8 / 256 + mul_q14(out, nx);
                        k->vy = ty * WALL_SCRAPE_Q8 / 256 + mul_q14(out, ny);
                        hit = 1;
                    } else {                                           /* a graze: slide along the wall */
                        k->vx -= mul_q14(vn, nx);
                        k->vy -= mul_q14(vn, ny);
                    }
                }
            }
        }
    }
    return hit;
}

/* One kart's frame: input (BTN_* bits), then the move. Returns EV_* bits. */
static uint8_t kart_step(md_race *r, int i, uint16_t in) {
    md_kart *k = &r->k[i];
    int32_t hx, hy, f, l, top;
    int dir = ((in & BTN_RIGHT) ? 1 : 0) - ((in & BTN_LEFT) ? 1 : 0);
    int steer = 0, sub;
    uint8_t ev = 0, surface_before = k->surface;

    if (k->boost) k->boost--;
    top = surface_top(k->surface);
    if (r->skill[i]) top = (int32_t)(((int64_t)top * r->skill[i]) >> 8);

    /* the part of the velocity along the heading */
    hx = ac_cos(k->heading); hy = ac_sin(k->heading);
    f = mul_q14(k->vx, hx) + mul_q14(k->vy, hy);

    /* drifting: R held while steering above half speed; releasing R after DRIFT_CHARGE frames boosts */
    if (k->drift == DRIFT_NONE) {
        if ((in & BTN_R) && dir != 0 && f >= DRIFT_MIN_SPEED) {
            k->drift = dir > 0 ? DRIFT_RIGHT : DRIFT_LEFT;
            k->drift_charge = 0;
        }
    } else if (!(in & BTN_R)) {
        if (k->drift_charge >= DRIFT_CHARGE) {
            k->boost = k->drift_charge >= DRIFT_CHARGE_2 ? DRIFT_BOOST2_FRAMES : DRIFT_BOOST_FRAMES;
            if (f < DRIFT_BOOST_SPEED) f = DRIFT_BOOST_SPEED;
            if (k->lap_boosts < 255) k->lap_boosts++;
            ev |= EV_BOOST | EV_DRIFT_BOOST;
        }
        k->drift = DRIFT_NONE;
        k->drift_charge = 0;
    } else if (f < DRIFT_MIN_SPEED * 3 / 4) {                         /* slowed down: the drift is lost */
        k->drift = DRIFT_NONE;
        k->drift_charge = 0;
    }
    if (k->drift != DRIFT_NONE && k->drift_charge < 0xFFFF) k->drift_charge++;

    /* throttle, brakes, reverse */
    if (k->boost) top = DRIFT_BOOST_SPEED;
    if (in & BTN_A) {
        if (f < 0) f += BRAKE;
        else if (f < top) {                                            /* the torque curve: strong low, easing off */
            f += ACCEL_LAUNCH - (int32_t)((int64_t)(ACCEL_LAUNCH - ACCEL_TOP_END) * f / top);
            if (f > top) f = top;
        }
    } else if (in & BTN_B) {
        if (f > 0) { f -= BRAKE; if (f < 0) f = 0; }
        else { f -= REVERSE_ACCEL; if (f < -REVERSE_MAX) f = -REVERSE_MAX; }
    } else {
        if (f > COAST_DRAG) f -= COAST_DRAG;
        else if (f < -COAST_DRAG) f += COAST_DRAG;
        else f = 0;
    }
    if (f > top) { f -= OVER_TOP_DRAG; if (f < top) f = top; }
    if (k->boost && f < top) f = top;                                  /* a boost carries the kart */

    /* steering: the wheel turns STEER_RAMP a frame toward where the d-pad holds it (or the drift's own lock);
       out of a drift, full lock turns the kart STEER (scaled down below STEER_FULL_SPEED, eased off above
       STEER_TAPER_SPEED and more above TOP_ROAD), a little more while braking; reversed when reversing */
    {
        int target = dir * STEER, w;
        if (k->drift != DRIFT_NONE) {
            int into = k->drift == DRIFT_RIGHT ? 1 : -1;
            target = into * (dir == into ? DRIFT_STEER : dir == 0 ? DRIFT_STEER_BASE : DRIFT_STEER_OUT);
        }
        w = k->steer;
        if (w < target) { w += STEER_RAMP; if (w > target) w = target; }
        else if (w > target) { w -= STEER_RAMP; if (w < target) w = target; }
        k->steer = (int8_t)w;
        if (k->drift != DRIFT_NONE) steer = w;
        else {
            int32_t sp = f < 0 ? -f : f;
            int cap = sp < STEER_FULL_SPEED ? (int)((int64_t)STEER * sp / STEER_FULL_SPEED)
                    : sp <= STEER_TAPER_SPEED ? STEER : sp <= TOP_ROAD ? STEER_AT_TOP : STEER_AT_BOOST;
            steer = w * cap / STEER;
            if ((in & BTN_B) && f >= STEER_FULL_SPEED && w) steer += w > 0 ? STEER_BRAKE_BONUS : -STEER_BRAKE_BONUS;
            if (f < 0) steer = -steer;
        }
    }
    k->heading = (uint16_t)((k->heading + steer) & 1023);

    /* the velocity against the new heading: keep f, scrub the sideways part (less of it flat out at full lock, so
       a corner taken at top speed runs wide; much less of it in a drift) */
    hx = ac_cos(k->heading); hy = ac_sin(k->heading);
    l = mul_q14(k->vx, -hy) + mul_q14(k->vy, hx);
    {
        int32_t keep = GRIP_Q8, sp = f < 0 ? -f : f;
        if (k->drift != DRIFT_NONE) keep = DRIFT_GRIP_Q8;
        else if (sp > STEER_TAPER_SPEED && (k->steer >= STEER || k->steer <= -STEER)) keep = SLIP_GRIP_Q8;
        l = (int32_t)(((int64_t)l * keep) >> 8);
    }
    k->vx = mul_q14(f, hx) - mul_q14(l, hy);
    k->vy = mul_q14(f, hy) + mul_q14(l, hx);

    /* move in two half steps, out of the walls after each */
    for (sub = 0; sub < 2; sub++) {
        int32_t px = k->x, py = k->y;
        k->x += k->vx / 2;
        k->y += k->vy / 2;
        if (resolve_walls(k, px, py)) {
            if (k->wall_hits < 0xFFFF) k->wall_hits++;
            k->lap_clean = 0;
            if (k->drift != DRIFT_NONE) { k->drift = DRIFT_NONE; k->drift_charge = 0; }
            ev |= EV_WALL;
        }
    }
    k->speed = mul_q14(k->vx, hx) + mul_q14(k->vy, hy);
    k->surface = track_surface(k->x >> 16, k->y >> 16);

    /* boost pads: on entering one */
    if (k->surface == SURF_BOOST && surface_before != SURF_BOOST) {
        k->boost = PAD_BOOST_FRAMES;
        if (k->speed < PAD_BOOST_SPEED) {
            k->vx = mul_q14(PAD_BOOST_SPEED, hx);
            k->vy = mul_q14(PAD_BOOST_SPEED, hy);
            k->speed = PAD_BOOST_SPEED;
        }
        ev |= EV_BOOST;
    }
    return ev;
}

/* Circle-circle contacts: push apart, exchange part of the velocity along the contact normal. */
static void kart_contacts(md_race *r) {
    const int32_t D = (2 * KART_RADIUS) << 16;
    int i, j;
    for (i = 0; i < N_KARTS; i++) {
        for (j = i + 1; j < N_KARTS; j++) {
            md_kart *a = &r->k[i], *b = &r->k[j];
            int32_t dx = b->x - a->x, dy = b->y - a->y, d, nx, ny, push, va, vb, dv, ax0, ay0, bx0, by0;
            int64_t d2 = (int64_t)dx * dx + (int64_t)dy * dy;
            if (d2 >= (int64_t)D * D) continue;
            d = (int32_t)ac_isqrt((uint32_t)(d2 >> 16));              /* Q8 */
            if (d == 0) { nx = Q14; ny = 0; }
            else {
                nx = (int32_t)(((int64_t)(dx >> 8) << 14) / d);
                ny = (int32_t)(((int64_t)(dy >> 8) << 14) / d);
            }
            push = (D - (d << 8)) / 2 + 1;
            ax0 = a->x; ay0 = a->y; bx0 = b->x; by0 = b->y;
            a->x -= mul_q14(push, nx); a->y -= mul_q14(push, ny);
            b->x += mul_q14(push, nx); b->y += mul_q14(push, ny);
            va = mul_q14(a->vx, nx) + mul_q14(a->vy, ny);
            vb = mul_q14(b->vx, nx) + mul_q14(b->vy, ny);
            dv = va - vb;                                              /* > 0: closing */
            if (dv > 0) {
                int32_t share = (int32_t)(((int64_t)dv * BUMP_SHARE_Q8) >> 8);
                a->vx -= mul_q14(share, nx); a->vy -= mul_q14(share, ny);
                b->vx += mul_q14(share, nx); b->vy += mul_q14(share, ny);
            }
            /* a push must not leave a kart in a wall */
            resolve_walls(a, ax0, ay0);
            resolve_walls(b, bx0, by0);
        }
    }
}

/* ---- the rivals -------------------------------------------------------------------------------------------- */

/* to - from, wrapped to -512..511 */
static int angle_diff(uint16_t to, uint16_t from) {
    int d = ((int)to - (int)from) & 1023;
    return d >= 512 ? d - 1024 : d;
}

static uint16_t ai_input(md_race *r, int i) {
    md_kart *k = &r->k[i];
    int w = r->wp[i], nw = (w + 1) % TRACK_WAYPOINTS, pw = (w + TRACK_WAYPOINTS - 1) % TRACK_WAYPOINTS;
    int32_t px = k->x >> 16, py = k->y >> 16;
    int32_t tx = md_waypoints[w][0], ty = md_waypoints[w][1];
    int32_t dx = tx - px, dy = ty - py;
    int32_t sx = tx - md_waypoints[pw][0], sy = ty - md_waypoints[pw][1];
    int32_t target;
    uint16_t in = 0, want;
    int diff;
    /* passed the waypoint (near it, or beyond it along the leg that leads to it): aim at the next */
    if (dx * dx + dy * dy < AI_REACH * AI_REACH || (-dx) * sx + (-dy) * sy > 0) {
        r->wp[i] = (uint8_t)nw;
        w = nw; nw = (w + 1) % TRACK_WAYPOINTS;
        tx = md_waypoints[w][0]; ty = md_waypoints[w][1];
        dx = tx - px; dy = ty - py;
    }
    /* stuck against something: reverse with the wheel turned for a moment */
    if (r->recover[i]) {
        r->recover[i]--;
        return (uint16_t)(BTN_B | (r->recover[i] & 32 ? BTN_LEFT : BTN_RIGHT));
    }
    if ((k->speed < 0x4000 && k->speed > -0x4000)) {
        if (r->stuck[i] < 255) r->stuck[i]++;
        if (r->stuck[i] > 45) { r->stuck[i] = 0; r->recover[i] = 40; }
    } else r->stuck[i] = 0;

    /* steer at a point on the centre line ahead (further at speed), shifted into this rival's lane */
    {
        int j = wrap_pt(r->pt[i] + AI_LOOK + AI_LOOK_PER_PX * (k->speed >> 16));
        int a = wrap_pt(j - 1), b = wrap_pt(j + 1);
        int32_t nx = -(md_points[b][1] - md_points[a][1]), ny = md_points[b][0] - md_points[a][0];  /* right */
        int32_t len = (int32_t)ac_isqrt((uint32_t)(nx * nx + ny * ny));
        int32_t ax = (md_points[j][0] << 8) + (len ? r->lane[i] * nx * 256 / len : 0);
        int32_t ay = (md_points[j][1] << 8) + (len ? r->lane[i] * ny * 256 / len : 0);
        want = ac_atan2(ay - (k->y >> 8), ax - (k->x >> 8));
    }
    diff = angle_diff(want, k->heading);
    if (diff > 3) in |= BTN_RIGHT;
    else if (diff < -3) in |= BTN_LEFT;
    target = md_waypoints[w][2];
    if (md_waypoints[nw][2] < target && dx * dx + dy * dy < 90 * 90) target = md_waypoints[nw][2];
    target = (int32_t)(((int64_t)target * r->skill[i]) >> 8);
    if (diff > 160 || diff < -160) target = target < STEER_FULL_SPEED ? target : STEER_FULL_SPEED;
    if (k->speed < target) in |= BTN_A;
    else if (k->speed > target + 0x2000) in |= BTN_B;
    return in;
}

/* ---- laps and placement ------------------------------------------------------------------------------------ */

static void track_progress(md_race *r, int i, uint32_t frame, uint8_t *finished_now) {
    md_kart *k = &r->k[i];
    uint8_t sector;
    int32_t arc;
    r->pt[i] = track_follow(r->pt[i], k->x, k->y);
    sector = (uint8_t)(r->pt[i] * TRACK_SECTORS / TRACK_POINTS);
    if (!k->finished && sector == (k->cp + 1) % TRACK_SECTORS) {
        k->cp = sector;
        if (sector == 0) {                                             /* over the line, every checkpoint in order */
            if (k->lap >= 1 && k->lap_clean && i == 0) r->player_clean_lap = 1;
            k->lap++;
            k->lap_boosts = 0;
            k->lap_clean = 1;
            if (k->lap > LAPS) {
                k->finished = 1;
                k->finish_frame = frame;
                *finished_now |= (uint8_t)(1 << i);
            }
        }
    }
    arc = arc16(r->pt[i], k->x, k->y);
    if (sector > k->cp + TRACK_SECTORS / 2) arc -= TRACK_LEN * 16;    /* backwards over the line */
    k->progress = (int32_t)(k->lap - 1) * TRACK_LEN * 16 + arc;
}

static int ahead(const md_kart *a, int ia, const md_kart *b, int ib) {
    if (a->progress != b->progress) return a->progress > b->progress;
    return ia < ib;
}

static void standings(md_race *r, uint8_t finished_now) {
    int i, j, n = 0;
    uint8_t order[N_KARTS];
    /* karts that finished this frame get the next places: further past the line first, then by index */
    while (finished_now) {
        int best = -1;
        for (i = 0; i < N_KARTS; i++)
            if ((finished_now >> i) & 1)
                if (best < 0 || ahead(&r->k[i], i, &r->k[best], best)) best = i;
        finished_now &= (uint8_t)~(1 << best);
        r->finishers++;
        r->k[best].place = r->finishers;
    }
    for (i = 1; i <= r->finishers; i++)                                /* finished karts, by their fixed place */
        for (j = 0; j < N_KARTS; j++)
            if (r->k[j].finished && r->k[j].place == i) order[n++] = (uint8_t)j;
    for (i = 0; i < N_KARTS; i++) {                                    /* the rest by progress, then index */
        if (r->k[i].finished) continue;
        order[n] = (uint8_t)i;
        for (j = n; j > r->finishers && ahead(&r->k[order[j]], order[j], &r->k[order[j - 1]], order[j - 1]); j--) {
            uint8_t t = order[j]; order[j] = order[j - 1]; order[j - 1] = t;
        }
        n++;
    }
    for (i = 0; i < N_KARTS; i++) {
        r->order[i] = order[i];
        r->k[order[i]].place = (uint8_t)(i + 1);
    }
}

uint8_t race_step(md_race *r, uint16_t buttons, uint32_t frame) {
    uint8_t ev = 0, finished_now = 0;
    int i;
    for (i = 0; i < N_KARTS; i++) {
        uint16_t in = i == 0 ? buttons : (frame > r->launch[i] ? ai_input(r, i) : 0);   /* rivals wait their launch */
        uint8_t e;
        if ((frozen >> i) & 1) in = 0;
        e = kart_step(r, i, in);
        if (i == 0) ev |= e;
    }
    kart_contacts(r);
    for (i = 0; i < N_KARTS; i++) {
        uint8_t lap = r->k[i].lap;
        r->k[i].surface = track_surface(r->k[i].x >> 16, r->k[i].y >> 16);
        track_progress(r, i, frame, &finished_now);
        if (i == 0 && r->k[0].lap != lap) ev |= EV_LAP;
    }
    standings(r, finished_now);
    return ev;
}

/* ---- hashing and test hooks -------------------------------------------------------------------------------- */

static void hash_kart(const md_kart *k, ac_hash *h) {
    ac_hash_i32(h, k->x); ac_hash_i32(h, k->y); ac_hash_i32(h, k->vx); ac_hash_i32(h, k->vy);
    ac_hash_i32(h, k->speed); ac_hash_i32(h, k->progress); ac_hash_u32(h, k->finish_frame);
    ac_hash_u16(h, k->heading); ac_hash_u16(h, k->drift_charge); ac_hash_u16(h, k->boost);
    ac_hash_u16(h, k->wall_hits);
    ac_hash_u8(h, k->lap); ac_hash_u8(h, k->cp); ac_hash_u8(h, k->surface); ac_hash_u8(h, k->drift);
    ac_hash_u8(h, k->finished); ac_hash_u8(h, k->place); ac_hash_u8(h, k->lap_boosts); ac_hash_u8(h, k->lap_clean);
    ac_hash_u8(h, (uint8_t)k->steer);
}

void race_hash(const md_race *r, ac_hash *h) {
    int i;
    for (i = 0; i < N_KARTS; i++) {
        hash_kart(&r->k[i], h);
        ac_hash_u16(h, r->pt[i]);
        ac_hash_u8(h, r->wp[i]);
        ac_hash_u8(h, r->order[i]);
        ac_hash_u8(h, r->stuck[i]);
        ac_hash_u8(h, r->recover[i]);
    }
    ac_hash_u8(h, r->finishers);
    ac_hash_u8(h, r->player_clean_lap);
    ac_hash_u8(h, frozen);
}

uint8_t race_player_clean_lap(const md_race *r) { return r->player_clean_lap; }

void race_debug_move(md_race *r, int i, int32_t px, int32_t py) {
    r->k[i].x = px << 16;
    r->k[i].y = py << 16;
}

void race_debug_set(md_race *r, int i, int32_t speed, uint8_t lap, uint8_t cp) {
    md_kart *k = &r->k[i];
    k->vx = mul_q14(speed, ac_cos(k->heading));
    k->vy = mul_q14(speed, ac_sin(k->heading));
    k->speed = speed;
    k->lap = lap;
    k->cp = cp;
}

void race_debug_freeze(uint8_t mask) { frozen = mask; }
