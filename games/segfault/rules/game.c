/* SEGFAULT's rules (see game.h). Title: Start. How-to: A or Start. Play: d-pad up/down moves, left/right turns,
   L/R strafe, A fires (hold for auto-fire), B uses (doors, shelves, the reader, the terminal, the secret wall),
   Start pauses (Resume / Quit). Results: Start leaves (the ROM then resets). */
#include <string.h>

#include "game.h"
#include "ac_buttons.h"
#include "ac_fix.h"
#include "ac_hash.h"
#include "ac_rng.h"
#include "map.h"
#include "tuning.h"

static const char *const TROPHIES[4] = {"All bugs", "No damage", "Under 3:00", "Secret room"};

/* id, rules version (4: the seed nudges the bugs' spawns), trophy count, trophy names, ghost sample period */
const ac_game_info GAME_INFO = {"SEGF", 4, 4, TROPHIES, 4};

#define NCELLS (MAP_W * MAP_H)

/* The GBA's fast IWRAM is 32 KB; the big tables that are not the per-frame state live in its 256 KB EWRAM there
   (a placement only: the code and the results are the same on every target). */
#if defined(__arm__) && !defined(__linux__)
#define SEGF_BIG __attribute__((section(".ewram_bss")))
#else
#define SEGF_BIG
#endif

/* The level source (constant after a load; restarts reload from it). Not state: never hashed. */
static char level_src[NCELLS] SEGF_BIG;
#define FULL_TILE 0x10000
enum { DOOR_SHUT = 0, DOOR_OPENING = 1, DOOR_OPEN = 2, DOOR_CLOSING = 3, DOOR_GONE = 4 };
enum { KIND_DOOR = 0, KIND_PUSH = 1, KIND_LOCKED = 2 };

typedef struct {
    int32_t x, y;
    uint8_t hp, state, sees, biting, bite_cd;
    uint16_t anim, lost;
} bug_t;

typedef struct {
    uint8_t x, y, kind, mode, amount;
    uint16_t timer;
} door_t;

static struct {
    uint32_t seed;              /* game_init's: 0 the classic spawns, else each bug nudged (load_level); not hashed per
                                   step, game_init folds it into the first hash */
    uint8_t start_cx, start_cy; /* the level's '@' cell, found once at init (a nudged bug keeps clear of it) */
    uint16_t start_angle;
    /* scenes */
    uint8_t scene, paused, sel, finished;
    uint32_t trophies;
    uint16_t prev;
    uint32_t steps, run_frames;
    /* the map */
    uint8_t cells[NCELLS];
    uint32_t edits;             /* a running FNV of every cell change, so the hash covers the map */
    uint16_t map_version;       /* +1 on every load and cell change (the view rebuilds its copy then) */
    door_t doors[MAX_DOORS];
    uint8_t n_doors;
    bug_t bugs[MAX_BUGS];
    uint8_t n_bugs, squashed;
    /* the player */
    int32_t px, py, sx, sy;     /* position and the level start */
    uint16_t angle;
    uint8_t health, has_key, took_damage, deaths, secret, fire_armed;
    uint16_t dead_timer, fire_cd, shot_age, hurt_age, walk, msg_timer;
    int8_t last_hit;
    uint8_t msg;
    uint32_t hash;
} s;

/* The bugs' flow field toward the player: a cache derived from the state (the player's cell and which doors are
   passable), rebuilt whenever that changes, so it needs no hashing. */
static uint8_t field[NCELLS] SEGF_BIG;
static uint32_t field_cell = 0xFFFFFFFFu;      /* the player's cell the field was built for */
static uint32_t field_doors;                   /* bit k: sliding cell k was passable then (MAX_DOORS <= 32) */
typedef char door_bits_fit[MAX_DOORS <= 32 ? 1 : -1];

static int32_t iabs(int32_t v) { return v < 0 ? -v : v; }
static int32_t imax(int32_t a, int32_t b) { return a > b ? a : b; }

/* ---- the map -------------------------------------------------------------------------------------------------- */

static int door_index(int x, int y) {
    int i;
    for (i = 0; i < s.n_doors; i++)
        if (s.doors[i].x == x && s.doors[i].y == y && s.doors[i].mode != DOOR_GONE) return i;
    return -1;
}

static int solid(int cx, int cy) {
    uint8_t c;
    if (cx < 0 || cy < 0 || cx >= MAP_W || cy >= MAP_H) return 1;
    c = s.cells[cy * MAP_W + cx];
    if (c == CELL_FLOOR || c == CELL_SECRET) return 0;
    if (c == CELL_DOOR || c == CELL_LOCKED) {
        int d = door_index(cx, cy);
        return d < 0 || s.doors[d].amount != DOOR_FRAMES;
    }
    return 1;
}

static void set_cell(int cx, int cy, uint8_t c) {
    ac_hash h;
    s.cells[cy * MAP_W + cx] = c;
    s.map_version++;
    h.h = s.edits;
    ac_hash_u8(&h, (uint8_t)cx);
    ac_hash_u8(&h, (uint8_t)cy);
    ac_hash_u8(&h, c);
    s.edits = h.h;
}

static int box_blocked(int32_t x, int32_t y, int32_t r) {
    int cx, cy, x0 = (x - r) >> 16, x1 = (x + r - 1) >> 16, y0 = (y - r) >> 16, y1 = (y + r - 1) >> 16;
    for (cy = y0; cy <= y1; cy++)
        for (cx = x0; cx <= x1; cx++)
            if (solid(cx, cy)) return 1;
    return 0;
}

static int box_on_cell(int32_t x, int32_t y, int32_t r, int cx, int cy) {
    return ((x - r) >> 16) <= cx && cx <= ((x + r - 1) >> 16) && ((y - r) >> 16) <= cy && cy <= ((y + r - 1) >> 16);
}

/* Segment p0 -> p1 through the grid, exact in integers: at each step cross whichever cell boundary the line reaches
   first (compare nx / |dx| with ny / |dy| as products). Through a corner point both side cells must be open. */
static int los(int32_t x0, int32_t y0, int32_t x1, int32_t y1) {
    int cx = x0 >> 16, cy = y0 >> 16, ex = x1 >> 16, ey = y1 >> 16, n;
    int32_t dx = x1 - x0, dy = y1 - y0;
    int sx = dx > 0 ? 1 : dx < 0 ? -1 : 0, sy = dy > 0 ? 1 : dy < 0 ? -1 : 0;
    int64_t adx = iabs(dx), ady = iabs(dy);
    int64_t nx = sx > 0 ? (int64_t)((cx + 1) << 16) - x0 : (int64_t)x0 - (cx << 16);
    int64_t ny = sy > 0 ? (int64_t)((cy + 1) << 16) - y0 : (int64_t)y0 - (cy << 16);
    for (n = 0; n < 2 * (MAP_W + MAP_H); n++) {
        int stepx, stepy;
        if (cx == ex && cy == ey) return 1;
        if (sx == 0) { stepx = 0; stepy = 1; }
        else if (sy == 0) { stepx = 1; stepy = 0; }
        else {
            int64_t a = nx * ady, b = ny * adx;
            stepx = a <= b;
            stepy = b <= a;
        }
        if (stepx && stepy) {
            if (solid(cx + sx, cy) || solid(cx, cy + sy)) return 0;
        }
        if (stepx) { cx += sx; nx += FULL_TILE; }
        if (stepy) { cy += sy; ny += FULL_TILE; }
        if (solid(cx, cy)) return 0;
    }
    return 1;
}

/* map.txt characters -> cells (the special ones -- D P L b @ -- are handled in load_level) */
static uint8_t cell_of(char ch) {
    switch (ch) {
    case '#': return CELL_RACK;
    case 'c': return CELL_CABLE;
    case 'o': return CELL_OFFICE;
    case 'w': return CELL_BOARD;
    case 'A': return CELL_SHELF;
    case 'K': return CELL_READER;
    case 'X': return CELL_TERMINAL;
    case 's': return CELL_SECRET;
    default: return CELL_FLOOR;
    }
}

/* Open floor in the level source at (x, y) ('.'; outside the map is not). */
static int src_floor(int x, int y) {
    return x >= 0 && y >= 0 && x < MAP_W && y < MAP_H && level_src[y * MAP_W + x] == '.';
}

/* A seeded run nudges the bug spawning at (x, y): up to BUG_NUDGE_TRIES seeded tries of a cell at most two away on
   open floor (the cell half way there open too, so a nudge never crosses a wall), more than BUG_NUDGE_SAFE cells
   from the player's start and not holding a bug already. Stays put when no try fits. */
static void nudge_spawn(int *x, int *y, uint32_t *r) {
    int t, k;
    for (t = 0; t < BUG_NUDGE_TRIES; t++) {
        int dx, dy, nx, ny, sx, sy, taken = 0;
        *r = ac_rng32(*r);
        dx = (int)(*r % 5u) - 2;
        dy = (int)((*r >> 3) % 5u) - 2;
        nx = *x + dx; ny = *y + dy;
        if ((dx == 0 && dy == 0) || !src_floor(nx, ny)) continue;
        if ((dx / 2 || dy / 2) && !src_floor(*x + dx / 2, *y + dy / 2)) continue;     /* through a wall */
        sx = nx - s.start_cx; sy = ny - s.start_cy;
        if (sx <= BUG_NUDGE_SAFE && sx >= -BUG_NUDGE_SAFE && sy <= BUG_NUDGE_SAFE && sy >= -BUG_NUDGE_SAFE) continue;
        for (k = 0; k < s.n_bugs; k++)
            if ((s.bugs[k].x >> 16) == nx && (s.bugs[k].y >> 16) == ny) taken = 1;
        if (taken) continue;
        *x = nx; *y = ny;
        return;
    }
}

static void load_level(void) {
    int i, x = 0, y = 0;                        /* x, y walk with i: no division (Thumb-1 has none, it is slow) */
    uint32_t r = s.seed;                        /* every load nudges the same way: the same seed, the same chain */
    s.n_doors = 0;
    s.n_bugs = 0;
    s.edits = 0;
    s.map_version++;
    for (i = 0; i < NCELLS; i++, x = x + 1 == MAP_W ? 0 : x + 1, y += x == 0) {
        char ch = level_src[i];
        uint8_t c;
        if (ch == '.') { s.cells[i] = CELL_FLOOR; continue; }
        c = cell_of(ch);
        if (ch == 'D' || ch == 'P' || ch == 'L') {
            c = ch == 'D' ? CELL_DOOR : ch == 'L' ? CELL_LOCKED : CELL_PUSH;
            if (s.n_doors < MAX_DOORS) {
                door_t *d = &s.doors[s.n_doors++];
                d->x = (uint8_t)x; d->y = (uint8_t)y; d->kind = ch == 'D' ? KIND_DOOR : ch == 'L' ? KIND_LOCKED : KIND_PUSH;
                d->mode = DOOR_SHUT; d->amount = 0; d->timer = 0;
            } else {
                c = CELL_RACK;
            }
        } else if (ch == 'b') {
            if (s.n_bugs < MAX_BUGS) {
                int bx = x, by = y;
                bug_t *b;
                if (s.seed) nudge_spawn(&bx, &by, &r);
                b = &s.bugs[s.n_bugs++];
                b->x = (bx << 16) + 0x8000; b->y = (by << 16) + 0x8000;
                b->hp = BUG_HP; b->state = BUG_IDLE; b->sees = 0; b->biting = 0; b->bite_cd = BUG_FIRST_BITE;
                b->anim = (uint16_t)(i * 7); b->lost = 0;
            }
        } else if (ch == '@') {
            s.sx = (x << 16) + 0x8000; s.sy = (y << 16) + 0x8000;
        }
        s.cells[i] = c;
    }
    s.squashed = 0;
    s.px = s.sx; s.py = s.sy; s.angle = s.start_angle;
    s.health = HEALTH_START; s.has_key = 0;
    s.dead_timer = 0; s.fire_cd = 0; s.shot_age = 255; s.hurt_age = 255; s.last_hit = -1;
    s.msg = MSG_NONE; s.msg_timer = 0;
    field_cell = 0xFFFFFFFFu;
}

static void say(uint8_t msg) { s.msg = msg; s.msg_timer = MSG_FRAMES; }

/* ---- the player ----------------------------------------------------------------------------------------------- */

static int bug_alive(const bug_t *b) { return b->state != BUG_DEAD; }

/* Moving the player or bug `self` (-1: the player) to (nx, ny) would push into another body: blocked when it
   overlaps one it did not overlap before, or gets closer to one it already overlaps. */
static int bodies_block(int self, int32_t x, int32_t y, int32_t nx, int32_t ny, int32_t r) {
    int i;
    if (self >= 0) {
        int32_t lim = r + PLAYER_RADIUS;
        if (iabs(nx - s.px) < lim && iabs(ny - s.py) < lim) {
            int before = iabs(x - s.px) < lim && iabs(y - s.py) < lim;
            if (!before || imax(iabs(nx - s.px), iabs(ny - s.py)) < imax(iabs(x - s.px), iabs(y - s.py))) return 1;
        }
    }
    for (i = 0; i < s.n_bugs; i++) {
        const bug_t *b = &s.bugs[i];
        int32_t lim = r + BUG_RADIUS;
        if (i == self || !bug_alive(b)) continue;
        if (iabs(nx - b->x) < lim && iabs(ny - b->y) < lim) {
            int before = iabs(x - b->x) < lim && iabs(y - b->y) < lim;
            if (!before || imax(iabs(nx - b->x), iabs(ny - b->y)) < imax(iabs(x - b->x), iabs(y - b->y))) return 1;
        }
    }
    return 0;
}

/* One axis of a move with a box of radius r: stop flush against a wall (the leading cell's edge) or a body. */
static void move_axis(int self, int32_t *x, int32_t *y, int32_t d, int axis, int32_t r) {
    int32_t nx = *x, ny = *y;
    if (d == 0) return;
    if (axis == 0) nx += d; else ny += d;
    if (box_blocked(nx, ny, r)) {
        int32_t v = axis == 0 ? nx : ny;
        if (d > 0) v = (((v + r - 1) >> 16) << 16) - r;
        else v = (((v - r) >> 16) + 1) * FULL_TILE + r;
        if (axis == 0) nx = v; else ny = v;
        if (d > 0 ? (axis == 0 ? nx <= *x : ny <= *y) : (axis == 0 ? nx >= *x : ny >= *y)) return;
        if (box_blocked(nx, ny, r)) return;
    }
    if (bodies_block(self, *x, *y, nx, ny, r)) return;
    *x = nx; *y = ny;
}

static void finish(void) {
    s.finished = 1;
    if (s.squashed == s.n_bugs) s.trophies |= TROPHY_ALL_BUGS;
    if (!s.took_damage) s.trophies |= TROPHY_NO_DAMAGE;
    if (s.run_frames < UNDER_FRAMES) s.trophies |= TROPHY_UNDER;
    say(MSG_REBOOT);
    s.scene = SC_RESULTS;
}

static int door_blocked(const door_t *d) {
    int i;
    if (box_on_cell(s.px, s.py, PLAYER_RADIUS, d->x, d->y)) return 1;
    for (i = 0; i < s.n_bugs; i++)
        if (bug_alive(&s.bugs[i]) && box_on_cell(s.bugs[i].x, s.bugs[i].y, BUG_RADIUS, d->x, d->y)) return 1;
    return 0;
}

static void use(void) {
    int32_t c = ac_cos(s.angle), sn = ac_sin(s.angle), dist;
    for (dist = 0x4000; dist <= USE_REACH; dist += 0x2000) {
        int cx = (int)((s.px + (int32_t)(((int64_t)c * dist) >> 14)) >> 16);
        int cy = (int)((s.py + (int32_t)(((int64_t)sn * dist) >> 14)) >> 16);
        uint8_t cell;
        if (cx < 0 || cy < 0 || cx >= MAP_W || cy >= MAP_H) return;
        cell = s.cells[cy * MAP_W + cx];
        if (cell == CELL_FLOOR || cell == CELL_SECRET) continue;
        switch (cell) {
        case CELL_DOOR: case CELL_PUSH: case CELL_LOCKED: {
            int i = door_index(cx, cy);
            door_t *d;
            if (i < 0) return;
            d = &s.doors[i];
            if (d->kind == KIND_LOCKED && !s.has_key) { say(MSG_LOCKED); break; }
            if (d->mode == DOOR_SHUT || d->mode == DOOR_CLOSING) d->mode = DOOR_OPENING;
            else if (d->mode == DOOR_OPEN && d->kind != KIND_PUSH && !door_blocked(d)) d->mode = DOOR_CLOSING;
            break;
        }
        case CELL_SHELF:
            if (s.health < HEALTH_MAX) {
                int h = s.health + HEALTH_PICKUP;
                s.health = (uint8_t)(h > HEALTH_MAX ? HEALTH_MAX : h);
                set_cell(cx, cy, CELL_SHELF_EMPTY);
                say(MSG_HEALTH);
            } else {
                say(MSG_HEALTH_FULL);
            }
            break;
        case CELL_SHELF_EMPTY: say(MSG_SHELF_EMPTY); break;
        case CELL_READER:
            s.has_key = 1;
            set_cell(cx, cy, CELL_READER_DONE);
            say(MSG_GOT_KEY);
            break;
        case CELL_READER_DONE: say(MSG_READER_DONE); break;
        case CELL_TERMINAL:
            if (s.has_key) finish();
            else say(MSG_NEED_KEY);
            break;
        default: break;
        }
        return;
    }
}

static void shoot(void) {
    int32_t c = ac_cos(s.angle), sn = ac_sin(s.angle), best = FIRE_RANGE + 1;
    int i, hit = -1;
    s.fire_cd = FIRE_COOLDOWN;
    s.shot_age = 0;
    for (i = 0; i < s.n_bugs; i++) {
        const bug_t *b = &s.bugs[i];
        int64_t rx = b->x - s.px, ry = b->y - s.py;
        int32_t along = (int32_t)((rx * c + ry * sn) >> 14);
        int64_t cross = (rx * sn - ry * c) >> 14;
        if (!bug_alive(b) || along <= 0 || along >= best) continue;
        if (cross >= HIT_RADIUS || cross <= -HIT_RADIUS) continue;
        if (!los(s.px, s.py, b->x, b->y)) continue;
        best = along;
        hit = i;
    }
    s.last_hit = (int8_t)hit;
    if (hit >= 0) {
        bug_t *b = &s.bugs[hit];
        b->hp--;
        b->anim = 0;
        b->lost = 0;
        if (b->hp == 0) {
            b->state = BUG_DEAD;
            b->biting = 0;
            s.squashed++;
            if (s.squashed == s.n_bugs) {
                s.trophies |= TROPHY_ALL_BUGS;
                say(MSG_ALL_BUGS);
            }
        } else {
            b->state = BUG_HURT;
        }
    }
}

/* ---- doors and bugs ------------------------------------------------------------------------------------------- */

static void update_doors(void) {
    int i;
    for (i = 0; i < s.n_doors; i++) {
        door_t *d = &s.doors[i];
        uint8_t full = d->kind == KIND_PUSH ? PUSH_FRAMES : DOOR_FRAMES;
        switch (d->mode) {
        case DOOR_OPENING:
            d->amount++;
            if (d->amount >= full) {
                d->amount = full;
                d->timer = 0;
                if (d->kind == KIND_PUSH) {
                    d->mode = DOOR_GONE;
                    set_cell(d->x, d->y, CELL_FLOOR);
                } else {
                    d->mode = DOOR_OPEN;
                }
            }
            break;
        case DOOR_OPEN:
            if (d->timer < DOOR_OPEN_HOLD) d->timer++;
            else if (!door_blocked(d)) d->mode = DOOR_CLOSING;
            break;
        case DOOR_CLOSING:
            if (door_blocked(d)) { d->mode = DOOR_OPENING; break; }
            d->amount--;
            if (d->amount == 0) d->mode = DOOR_SHUT;
            break;
        default: break;
        }
    }
}

/* Cell index i is passable for a bug (the BFS works on indices: no x / y division). */
static int open_index(int i) {
    uint8_t c = s.cells[i];
    int k;
    if (c == CELL_FLOOR || c == CELL_SECRET) return 1;
    if (c != CELL_DOOR && c != CELL_LOCKED) return 0;
    for (k = 0; k < s.n_doors; k++)
        if (s.doors[k].y * MAP_W + s.doors[k].x == i) return s.doors[k].amount == DOOR_FRAMES;
    return 0;
}

/* Breadth-first distances from the player's cell, out to FIELD_REACH steps (farther bugs cannot follow it). */
#define FIELD_REACH 40
static void build_field(void) {
    /* the cache key is exact: the player's cell and one passable bit per sliding cell */
    uint32_t cell = (uint32_t)((s.py >> 16) * MAP_W + (s.px >> 16)), doors = 0;
    int i, head = 0, tail = 0;
    static uint16_t queue[NCELLS] SEGF_BIG;
    for (i = 0; i < s.n_doors; i++)
        if (s.doors[i].mode == DOOR_GONE || s.doors[i].amount == DOOR_FRAMES) doors |= 1u << i;
    if (cell == field_cell && doors == field_doors) return;
    field_cell = cell;
    field_doors = doors;
    memset(field, 255, sizeof field);           /* 255: not reached (253: blocked, looked at) */
    i = (s.py >> 16) * MAP_W + (s.px >> 16);
    field[i] = 0;
    queue[tail++] = (uint16_t)i;
    while (head < tail) {                       /* the map's border is walls, so neighbours stay in range */
        int c = queue[head++], k;
        uint8_t d = (uint8_t)(field[c] + 1);
        static const int16_t STEP[4] = {1, -1, MAP_W, -MAP_W};
        if (d > FIELD_REACH) break;
        for (k = 0; k < 4; k++) {
            int n = c + STEP[k];
            if (n < 0 || n >= NCELLS || field[n] != 255) continue;
            if (!open_index(n)) { field[n] = 253; continue; }
            field[n] = d;
            queue[tail++] = (uint16_t)n;
        }
    }
}

static void bite(bug_t *b) {
    int h = s.health - BUG_DAMAGE;
    s.health = (uint8_t)(h < 0 ? 0 : h);
    s.took_damage = 1;
    s.hurt_age = 0;
    b->biting = 15;
    if (s.health == 0) s.dead_timer = DEATH_FRAMES;
}

/* A step of BUG_SPEED toward (dx, dy), the direction rounded to 16 compass points by comparing |dy| / |dx| with
   tan 11.25, 33.75, 56.25 and 78.75 degrees (5, 3/2, 2/3, 1/5): no division, which Thumb-1 code pays dearly for. */
static void heading(int32_t dx, int32_t dy, int32_t *vx, int32_t *vy) {
    static const int16_t C[5] = {BUG_SPEED, BUG_SPEED * 924 / 1000, BUG_SPEED * 707 / 1000, BUG_SPEED * 383 / 1000, 0};
    int64_t ax = dx < 0 ? -(int64_t)dx : dx, ay = dy < 0 ? -(int64_t)dy : dy;
    int k;
    if (ax == 0 && ay == 0) { *vx = 0; *vy = 0; return; }
    if (ay * 5 <= ax) k = 0;
    else if (ay * 3 <= ax * 2) k = 1;
    else if (ay * 2 <= ax * 3) k = 2;
    else if (ay <= ax * 5) k = 3;
    else k = 4;
    *vx = dx < 0 ? -C[k] : C[k];
    *vy = dy < 0 ? -C[4 - k] : C[4 - k];
}

static void bug_step(int i) {
    bug_t *b = &s.bugs[i];
    int32_t dx = s.px - b->x, dy = s.py - b->y, cheb = imax(iabs(dx), iabs(dy));
    if (b->anim < 0xFFFF) b->anim++;
    if (b->biting) b->biting--;
    if (((s.run_frames + (uint32_t)i) & 3u) == 0)    /* staggered by play time: idle title time changes nothing */
        b->sees = (uint8_t)(cheb <= BUG_SIGHT && los(b->x, b->y, s.px, s.py));
    switch (b->state) {
    case BUG_HURT:
        if (b->anim >= BUG_HURT_FRAMES) {
            b->state = BUG_CHASE; b->anim = 0; b->lost = 0; b->bite_cd = BUG_FIRST_BITE;
        }
        return;
    case BUG_IDLE:
        if (b->sees) {
            b->state = BUG_CHASE; b->anim = 0; b->lost = 0; b->bite_cd = BUG_FIRST_BITE;
        }
        return;
    case BUG_CHASE: break;
    default: return;
    }
    if (b->sees) b->lost = 0;
    else if (++b->lost >= BUG_GIVE_UP) { b->state = BUG_IDLE; b->anim = 0; b->lost = 0; return; }
    if (b->sees && cheb <= BUG_REACH) {
        if (b->bite_cd) b->bite_cd--;
        if (b->bite_cd == 0 && !s.dead_timer) {
            bite(b);
            b->bite_cd = BUG_ATTACK_EVERY;
        }
        return;
    }
    b->bite_cd = BUG_FIRST_BITE;
    {
        int32_t tx, ty;
        if (b->sees) {
            tx = s.px; ty = s.py;
        } else {
            int cx = b->x >> 16, cy = b->y >> 16, c = cy * MAP_W + cx, k, go = -1;
            static const int8_t DX[4] = {1, -1, 0, 0}, DY[4] = {0, 0, 1, -1};
            build_field();
            if (field[c] >= 253 || field[c] == 0) return;
            for (k = 0; k < 4 && go < 0; k++) {
                int nx = cx + DX[k], ny = cy + DY[k];
                if (nx >= 0 && ny >= 0 && nx < MAP_W && ny < MAP_H && field[ny * MAP_W + nx] == field[c] - 1) go = k;
            }
            if (go < 0) return;
            /* toward the next cell, keeping to the middle of this row or column */
            if (DX[go]) { tx = ((cx + DX[go]) << 16) + 0x8000; ty = (cy << 16) + 0x8000; }
            else { tx = (cx << 16) + 0x8000; ty = ((cy + DY[go]) << 16) + 0x8000; }
        }
        {
            int32_t vx, vy, ox = b->x, oy = b->y;
            heading(tx - b->x, ty - b->y, &vx, &vy);
            move_axis(i, &b->x, &b->y, vx, 0, BUG_RADIUS);
            move_axis(i, &b->x, &b->y, vy, 1, BUG_RADIUS);
            /* caught on a wall corner: slide toward the middle of the cell on the other axis */
            if (vy && b->y == oy && b->x == ox + vx) {
                int32_t mid = ((b->x >> 16) << 16) + 0x8000, d = mid - b->x;
                move_axis(i, &b->x, &b->y, d > BUG_SPEED ? BUG_SPEED : d < -BUG_SPEED ? -BUG_SPEED : d, 0, BUG_RADIUS);
            }
            if (vx && b->x == ox && b->y == oy + vy) {
                int32_t mid = ((b->y >> 16) << 16) + 0x8000, d = mid - b->y;
                move_axis(i, &b->x, &b->y, d > BUG_SPEED ? BUG_SPEED : d < -BUG_SPEED ? -BUG_SPEED : d, 1, BUG_RADIUS);
            }
        }
    }
}

/* ---- the frame ------------------------------------------------------------------------------------------------ */

static void start_run(void) {
    s.scene = SC_PLAY; s.paused = 0; s.sel = 0; s.finished = 0; s.trophies = 0; s.run_frames = 0;
    s.took_damage = 0; s.deaths = 0; s.secret = 0; s.walk = 0;
    load_level();
}

static void play_step(uint16_t buttons, uint16_t pressed) {
    if (s.paused) {
        if (pressed & BTN_START) s.paused = 0;
        else if (pressed & BTN_UP) s.sel = 0;
        else if (pressed & BTN_DOWN) s.sel = 1;
        else if (pressed & BTN_A) {
            if (s.sel == 0) s.paused = 0;
            else s.scene = SC_RESULTS;          /* Quit: the run ends unfinished */
        }
        return;
    }
    if (pressed & BTN_START) { s.paused = 1; s.sel = 0; return; }
    s.run_frames++;
    if (s.shot_age < 255) s.shot_age++;
    if (s.hurt_age < 255) s.hurt_age++;
    if (s.msg_timer && --s.msg_timer == 0) s.msg = MSG_NONE;
    if (s.dead_timer) {
        if (--s.dead_timer == 0) {
            s.deaths++;
            load_level();
        }
        return;
    }
    {
        int fwd = ((buttons & BTN_UP) ? 1 : 0) - ((buttons & BTN_DOWN) ? 1 : 0);
        int str = ((buttons & BTN_R) ? 1 : 0) - ((buttons & BTN_L) ? 1 : 0);
        int32_t c, sn, dx, dy, ox = s.px, oy = s.py;
        if (buttons & BTN_RIGHT) s.angle = (uint16_t)((s.angle + TURN_SPEED) & 1023);
        if (buttons & BTN_LEFT) s.angle = (uint16_t)((s.angle - TURN_SPEED) & 1023);
        c = ac_cos(s.angle); sn = ac_sin(s.angle);
        dx = ((fwd * c * MOVE_SPEED) >> 14) + ((str * -sn * STRAFE_SPEED) >> 14);
        dy = ((fwd * sn * MOVE_SPEED) >> 14) + ((str * c * STRAFE_SPEED) >> 14);
        move_axis(-1, &s.px, &s.py, dx, 0, PLAYER_RADIUS);
        move_axis(-1, &s.px, &s.py, dy, 1, PLAYER_RADIUS);
        s.walk = (uint16_t)(s.walk + ((iabs(s.px - ox) + iabs(s.py - oy)) >> 8));
    }
    if (pressed & BTN_B) use();
    if (s.scene != SC_PLAY) return;             /* the terminal finished the run */
    if (s.fire_cd) s.fire_cd--;
    if (!(buttons & BTN_A)) s.fire_armed = 1;
    if ((buttons & BTN_A) && s.fire_armed && s.fire_cd == 0) shoot();
    update_doors();
    {
        int i;
        for (i = 0; i < s.n_bugs; i++)
            if (bug_alive(&s.bugs[i])) bug_step(i);
    }
    if (!s.secret && s.cells[(s.py >> 16) * MAP_W + (s.px >> 16)] == CELL_SECRET) {
        s.secret = 1;
        s.trophies |= TROPHY_SECRET;
        say(MSG_SECRET);
    }
}

static void rehash(void) {
    ac_hash h;
    int i;
    h.h = s.hash;
    ac_hash_u8(&h, s.scene); ac_hash_u8(&h, s.paused); ac_hash_u8(&h, s.sel); ac_hash_u8(&h, s.finished);
    ac_hash_u32(&h, s.trophies); ac_hash_u16(&h, s.prev); ac_hash_u32(&h, s.steps); ac_hash_u32(&h, s.run_frames);
    ac_hash_u32(&h, s.edits);
    ac_hash_u16(&h, s.map_version);
    ac_hash_i32(&h, s.px); ac_hash_i32(&h, s.py); ac_hash_u16(&h, s.angle);
    ac_hash_u8(&h, s.health); ac_hash_u8(&h, s.has_key); ac_hash_u8(&h, s.took_damage); ac_hash_u8(&h, s.deaths);
    ac_hash_u8(&h, s.secret); ac_hash_u8(&h, s.fire_armed);
    ac_hash_u16(&h, s.dead_timer); ac_hash_u16(&h, s.fire_cd); ac_hash_u16(&h, s.shot_age);
    ac_hash_u16(&h, s.hurt_age); ac_hash_u16(&h, s.walk); ac_hash_u16(&h, s.msg_timer);
    ac_hash_u8(&h, (uint8_t)s.last_hit); ac_hash_u8(&h, s.msg);
    ac_hash_u8(&h, s.n_doors);
    for (i = 0; i < s.n_doors; i++) {
        const door_t *d = &s.doors[i];
        ac_hash_u8(&h, d->mode); ac_hash_u8(&h, d->amount); ac_hash_u16(&h, d->timer);
    }
    ac_hash_u8(&h, s.n_bugs); ac_hash_u8(&h, s.squashed);
    for (i = 0; i < s.n_bugs; i++) {
        const bug_t *b = &s.bugs[i];
        ac_hash_i32(&h, b->x); ac_hash_i32(&h, b->y);
        ac_hash_u8(&h, b->hp); ac_hash_u8(&h, b->state); ac_hash_u8(&h, b->sees); ac_hash_u8(&h, b->biting);
        ac_hash_u8(&h, b->bite_cd); ac_hash_u16(&h, b->anim); ac_hash_u16(&h, b->lost);
    }
    s.hash = h.h;
}

static void begin(uint32_t seed, const char *rows, uint16_t angle) {
    ac_hash h;
    int i;
    memset(&s, 0, sizeof s);                    /* every field, hashed or not: init twice in one process is init once */
    s.seed = seed;
    field_cell = 0xFFFFFFFFu;
    for (i = 0; i < NCELLS; i++) {
        level_src[i] = rows[i];
        if (rows[i] == '@') { s.start_cx = (uint8_t)(i % MAP_W); s.start_cy = (uint8_t)(i / MAP_W); }
    }
    s.start_angle = (uint16_t)(angle & 1023);
    s.scene = SC_TITLE; s.paused = 0; s.sel = 0; s.finished = 0; s.trophies = 0;
    s.prev = 0; s.steps = 0; s.run_frames = 0;
    s.took_damage = 0; s.deaths = 0; s.secret = 0; s.walk = 0;
    load_level();
    ac_hash_begin(&h);
    ac_hash_u32(&h, seed);
    s.hash = h.h;
}

void game_init(uint32_t seed) {
    begin(seed, LEVEL_ROWS, LEVEL_ANGLE);
    rehash();
}

void rules_test_setup(const char *rows, uint16_t angle) {
    begin(0, rows, angle);
    start_run();
    s.fire_armed = 1;                           /* tests start as if A had been released */
    rehash();
}

void game_step(uint16_t buttons) {
    uint16_t pressed;
    buttons &= BTN_MASK;
    pressed = (uint16_t)(buttons & ~s.prev);
    s.steps++;
    switch (s.scene) {
    case SC_TITLE:
        if (pressed & BTN_START) s.scene = SC_HOWTO;
        break;
    case SC_HOWTO:
        if (pressed & (BTN_START | BTN_A)) start_run();
        s.fire_armed = 0;                       /* A held from the card must be released before the first shot */
        break;
    case SC_PLAY:
        play_step(buttons, pressed);
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
    out->score = s.squashed;
    out->time_frames = s.run_frames;
    out->trophies = s.trophies;
}

void game_ghost(ac_ghost_pt *out) {
    out->x = (int16_t)(s.px >> 12);
    out->y = (int16_t)(s.py >> 12);
    out->angle = (uint8_t)(s.angle >> 2);
    out->flags = (uint8_t)((s.scene == SC_PLAY ? AC_GHOST_PLAY : 0) | (s.deaths & 0x7F));
}

uint8_t game_ended(void) { return s.scene == SC_RESULTS; }

/* ---- reads ---------------------------------------------------------------------------------------------------- */

uint8_t rules_scene(void) { return s.scene; }
uint8_t rules_paused(void) { return s.paused; }
uint8_t rules_pause_sel(void) { return s.sel; }
uint32_t rules_run_frames(void) { return s.run_frames; }
uint8_t rules_finished(void) { return s.finished; }
uint32_t rules_trophies(void) { return s.trophies; }
int32_t rules_px(void) { return s.px; }
int32_t rules_py(void) { return s.py; }
uint16_t rules_angle(void) { return s.angle; }
uint8_t rules_health(void) { return s.health; }
uint8_t rules_has_key(void) { return s.has_key; }
uint8_t rules_took_damage(void) { return s.took_damage; }
uint8_t rules_deaths(void) { return s.deaths; }
uint16_t rules_dead_timer(void) { return s.dead_timer; }
uint16_t rules_fire_cooldown(void) { return s.fire_cd; }
uint16_t rules_shot_age(void) { return s.shot_age; }
int8_t rules_last_hit(void) { return s.last_hit; }
uint16_t rules_hurt_age(void) { return s.hurt_age; }
uint16_t rules_walk(void) { return s.walk; }
uint8_t rules_msg(void) { return s.msg; }
uint16_t rules_msg_timer(void) { return s.msg_timer; }
uint8_t rules_secret_found(void) { return s.secret; }

uint8_t rules_cell(int x, int y) {
    if (x < 0 || y < 0 || x >= MAP_W || y >= MAP_H) return CELL_RACK;
    return s.cells[y * MAP_W + x];
}

const uint8_t *rules_cells(void) { return s.cells; }
uint16_t rules_map_version(void) { return s.map_version; }

uint8_t rules_door_amount(int x, int y) {
    int i = door_index(x, y);
    return i < 0 ? 0 : s.doors[i].amount;
}

uint8_t rules_bug_count(void) { return s.n_bugs; }
uint8_t rules_bugs_left(void) { return (uint8_t)(s.n_bugs - s.squashed); }
uint8_t rules_squashed(void) { return s.squashed; }
int32_t rules_bug_x(int i) { return s.bugs[i].x; }
int32_t rules_bug_y(int i) { return s.bugs[i].y; }
uint8_t rules_bug_state(int i) { return s.bugs[i].state; }
uint8_t rules_bug_hp(int i) { return s.bugs[i].hp; }
uint8_t rules_bug_sees(int i) { return s.bugs[i].sees; }
uint16_t rules_bug_anim(int i) { return s.bugs[i].anim; }
uint8_t rules_bug_biting(int i) { return s.bugs[i].biting; }
uint8_t rules_los(int32_t x0, int32_t y0, int32_t x1, int32_t y1) { return (uint8_t)los(x0, y0, x1, y1); }
