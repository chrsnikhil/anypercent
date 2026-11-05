/* The level's things, in one fixed array (hashed field by field in game.c): bugs walk and turn at walls and
   ledges (a stomp squashes them, side contact hurts), chai cups count, the World orb gives a shield that takes one
   hit, Arkiv shelves set the respawn point, and the venue door finishes the run. Boxes (top-left, size) per type:
   bug 14 x 12 on its tile's floor, chai 10 x 10 and orb 12 x 12 centred in the tile, shelf 12 x 32 standing on the
   tile's floor (two tiles tall), door 32 x 32 with its bottom-left tile at (tx, ty). */
#include "ac_buttons.h"
#include "ac_rng.h"
#include "level.h"
#include "rh_state.h"
#include "tuning.h"
#define s rh_s

static int px_of(int32_t v) { return rh_floor_div(v, 256); }
static int floor_tile(int tx, int ty);

static void box(const rh_ent *e, int *w, int *h) {
    switch (e->type) {
    case E_BUG: *w = BUG_W; *h = BUG_H; break;
    case E_CHAI: *w = 10; *h = 10; break;
    case E_ORB: *w = 12; *h = 12; break;
    case E_CHECK: *w = 12; *h = 32; break;
    default: *w = 32; *h = 32; break;                /* E_DOOR */
    }
}

void rh_ent_place(rh_ent *e, int tx, int ty) {
    int x, y;
    switch (e->type) {
    case E_BUG: x = tx * TILE + 1; y = (ty + 1) * TILE - BUG_H; break;
    case E_CHAI: x = tx * TILE + 3; y = ty * TILE + 3; break;
    case E_ORB: x = tx * TILE + 2; y = ty * TILE + 2; break;
    case E_CHECK: x = tx * TILE + 2; y = (ty - 1) * TILE; break;
    default: x = tx * TILE; y = (ty - 1) * TILE; break;
    }
    e->x = x * 256;
    e->y = y * 256;
}

/* A column a bug can stand in: its body row is not a wall and the row below is floor. */
static int patrol_col(int tx, int ty) { return rh_tile(tx, ty) != T_SOLID && floor_tile(tx, ty + 1); }

/* A seeded start: the bug faces a seeded way at a seeded pixel of its patrol, the run of standable columns around
   its tile (found column by column, so it costs a few tile reads, never a lag frame at play start). */
static void bug_seed_start(rh_ent *e, uint32_t r) {
    int x = px_of(e->x), ty = rh_floor_div(px_of(e->y), TILE);
    int c = rh_floor_div(x + BUG_W / 2, TILE), lo = c, hi = c, span;
    while (lo > c - PATROL_SCAN && patrol_col(lo - 1, ty)) lo--;
    while (hi < c + PATROL_SCAN && patrol_col(hi + 1, ty)) hi++;
    span = (hi + 1) * TILE - BUG_W - lo * TILE;     /* the legal left edges are lo * TILE .. lo * TILE + span */
    e->dir = (r & 1) ? 1 : -1;
    if (span > 0) e->x = (int32_t)(lo * TILE + (int)((r >> 1) % (uint32_t)(span + 1))) * 256;
}

/* Seed 0 is the classic level: every bug walks left from its tile. Any other seed starts each bug facing a seeded
   way somewhere along its patrol, so where the bugs are when the player arrives differs from run to run while the
   level stays the same. */
void rh_ents_load(void) {
    int i;
    uint32_t r = s.seed;
    s.n_ents = 0;
    if (s.map != LEVEL_TILES) return;                /* a test map brings its own */
    for (i = 0; i < LEVEL_N_ENTS && i < MAX_ENTS; i++) {
        rh_ent *e = &s.ents[s.n_ents++];
        e->type = LEVEL_ENTS[i].type;
        e->state = ES_LIVE;
        e->dir = -1;
        e->timer = 0;
        rh_ent_place(e, LEVEL_ENTS[i].tx, LEVEL_ENTS[i].ty);
        if (s.seed && e->type == E_BUG) {
            if (!s.starts_ready) {
                r = ac_rng32(r);
                bug_seed_start(e, r);
                s.start_x[i] = e->x;
                s.start_dir[i] = e->dir;
            }
            e->x = s.start_x[i];
            e->dir = s.start_dir[i];
        }
    }
    s.starts_ready = 1;
}

static int floor_tile(int tx, int ty) {
    uint8_t t = rh_tile(tx, ty);
    return t == T_SOLID || t == T_ONEWAY;
}

/* One bug step: walk; turn (instead of moving) at a wall or where the floor ends. */
static void bug_walk(rh_ent *e) {
    int32_t nx = e->x + e->dir * BUG_SPEED;
    int left = px_of(nx), top = px_of(e->y);
    int lead = e->dir > 0 ? left + BUG_W - 1 : left;
    int col = rh_floor_div(lead, TILE), ty;
    int blocked = 0;
    for (ty = rh_floor_div(top, TILE); ty <= rh_floor_div(top + BUG_H - 1, TILE); ty++)
        if (rh_tile(col, ty) == T_SOLID) blocked = 1;
    if (!floor_tile(col, rh_floor_div(top + BUG_H, TILE))) blocked = 1;
    if (blocked) e->dir = (int8_t)-e->dir;
    else e->x = nx;
}

void rh_ents_step(uint16_t buttons) {
    int i;
    int px = px_of(s.x), py = px_of(s.y), prev_feet = px_of(s.prev_y) + PLAYER_H;
    for (i = 0; i < s.n_ents; i++) {
        rh_ent *e = &s.ents[i];
        int ex, ey, w, h, touch;
        if (e->type == E_BUG) {
            if (e->state == ES_SQUASHED) {
                if (e->timer) e->timer--;
                if (!e->timer) e->state = ES_GONE;
                continue;
            }
            if (e->state != ES_LIVE) continue;
            bug_walk(e);
        } else if (e->state == ES_GONE) {
            continue;
        }
        if (s.dead || s.finished) continue;
        ex = px_of(e->x); ey = px_of(e->y);
        box(e, &w, &h);
        touch = px < ex + w && ex < px + PLAYER_W && py < ey + h && ey < py + PLAYER_H;
        if (!touch) continue;
        switch (e->type) {
        case E_BUG:
            if (s.vy > 0 && prev_feet <= ey + STOMP_SLACK) {
                e->state = ES_SQUASHED;
                e->timer = SQUASH_FRAMES;
                s.vy = (buttons & BTN_A) ? STOMP_HI : STOMP_LO;
                s.jumping = 0; s.on_ground = 0; s.coyote = 0;
            } else {
                rh_player_hurt(e->x + BUG_W * 128);
            }
            break;
        case E_CHAI:
            e->state = ES_GONE;
            s.chai++;
            break;
        case E_ORB:
            e->state = ES_GONE;
            s.shield = 1;
            break;
        case E_CHECK:
            s.touched_checkpoint = 1;
            if (e->state != ES_ON) {
                e->state = ES_ON;
                s.spawn_tx = (int16_t)rh_floor_div(ex, TILE);
                s.spawn_ty = (int16_t)(rh_floor_div(ey, TILE) + 1);
            }
            break;
        case E_DOOR:
            s.finished = 1;
            break;
        default:
            break;
        }
    }
}
