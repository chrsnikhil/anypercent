/* A tiny game for the kit's tests: a dot that moves with the d-pad; finishes after 300 frames of A held
   in total; trophy 0 = ever pressed B. */
#include "ac_game.h"
#include "ac_buttons.h"
#include "ac_hash.h"

static const char *const NAMES[] = {"Pressed B"};
const ac_game_info GAME_INFO = {{'T', 'O', 'Y', '1'}, 3, 1, NAMES, 4};
static struct { int32_t x, y; uint32_t frames, held; uint32_t trophies; ac_hash h; uint32_t seed; } s;

void game_init(uint32_t seed) { s.x = 0; s.y = 0; s.frames = 0; s.held = 0; s.trophies = 0; s.seed = seed; ac_hash_begin(&s.h); ac_hash_u32(&s.h, seed); }
void game_step(uint16_t b) {
    if (s.held >= 300) return;
    s.frames++;
    if (b & BTN_RIGHT) s.x++;
    if (b & BTN_LEFT) s.x--;
    if (b & BTN_DOWN) s.y++;
    if (b & BTN_UP) s.y--;
    if (b & BTN_A) s.held++;
    if (b & BTN_B) s.trophies |= 1;
    ac_hash_i32(&s.h, s.x); ac_hash_i32(&s.h, s.y); ac_hash_u32(&s.h, s.held); ac_hash_u32(&s.h, s.trophies);
}
uint32_t game_hash(void) { return s.h.h; }
void game_result(ac_result *o) { o->finished = s.held >= 300; o->frames = s.frames; o->score = (uint32_t)(s.x < 0 ? -s.x : s.x); o->time_frames = s.frames; o->trophies = s.trophies; }
void game_ghost(ac_ghost_pt *p) { p->x = (int16_t)s.x; p->y = (int16_t)s.y; p->angle = 0; p->flags = 0; }
