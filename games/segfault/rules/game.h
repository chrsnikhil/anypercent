/* SEGFAULT's rules: a grid-map first-person shooter. The night before demo day the server room is overrun with bugs:
   squash them with the debugger blaster, get the keycard at the World orb reader and reboot the build server at the
   Chainlink terminal. Plain C99, integers only, one module-global state; the ROM and out/librules.so compile this
   same code. The arcade interface is in arcade/src/ac_game.h (+ game_ended()); below are the reads the view, the bot
   and the tests use. The raycaster that draws the map is view code; hitscan and line of sight here use their own
   integer grid walk. */
#ifndef GAME_H
#define GAME_H
#include <stdint.h>
#include "ac_game.h"
#include "arcade_game_ext.h"

enum { SC_TITLE = 0, SC_HOWTO = 1, SC_PLAY = 2, SC_RESULTS = 3 };
enum { TROPHY_ALL_BUGS = 1, TROPHY_NO_DAMAGE = 2, TROPHY_UNDER = 4, TROPHY_SECRET = 8 };

/* Map cells. Walkable: CELL_FLOOR, CELL_SECRET, a fully open CELL_DOOR or CELL_LOCKED (a door B opens only with
   the keycard). */
enum {
    CELL_FLOOR = 0, CELL_RACK = 1, CELL_CABLE = 2, CELL_OFFICE = 3, CELL_BOARD = 4, CELL_DOOR = 5,
    CELL_SHELF = 6, CELL_SHELF_EMPTY = 7, CELL_READER = 8, CELL_READER_DONE = 9, CELL_TERMINAL = 10,
    CELL_PUSH = 11, CELL_SECRET = 12, CELL_LOCKED = 13, CELL_KINDS = 14
};
enum { BUG_IDLE = 0, BUG_CHASE = 1, BUG_HURT = 2, BUG_DEAD = 3 };
enum {
    MSG_NONE = 0, MSG_NEED_KEY, MSG_GOT_KEY, MSG_HEALTH, MSG_HEALTH_FULL, MSG_SHELF_EMPTY, MSG_READER_DONE,
    MSG_SECRET, MSG_ALL_BUGS, MSG_REBOOT, MSG_LOCKED
};

uint8_t  rules_scene(void);
uint8_t  rules_paused(void);
uint8_t  rules_pause_sel(void);      /* 0 Resume, 1 Quit */
uint32_t rules_run_frames(void);     /* play frames (not paused) since the how-to card; keeps running over deaths */
uint8_t  rules_finished(void);
uint32_t rules_trophies(void);

int32_t  rules_px(void);             /* the player, Q16.16 map units */
int32_t  rules_py(void);
uint16_t rules_angle(void);          /* 0..1023 */
uint8_t  rules_health(void);
uint8_t  rules_has_key(void);
uint8_t  rules_took_damage(void);
uint8_t  rules_deaths(void);
uint16_t rules_dead_timer(void);     /* > 0 while the "core dumped" screen shows */
uint16_t rules_fire_cooldown(void);
uint16_t rules_shot_age(void);       /* frames since the last shot (capped at 255) */
int8_t   rules_last_hit(void);       /* bug index the last shot hit, -1 if it missed */
uint16_t rules_hurt_age(void);       /* frames since the player was last bitten (capped at 255) */
uint16_t rules_walk(void);           /* distance walked, for the blaster bob (wraps) */
uint8_t  rules_msg(void);
uint16_t rules_msg_timer(void);
uint8_t  rules_secret_found(void);

uint8_t  rules_cell(int x, int y);   /* CELL_* (out of range: CELL_RACK) */
uint8_t  rules_door_amount(int x, int y);   /* 0 shut .. DOOR_FRAMES open, for a door or the sliding secret wall */
uint16_t rules_map_version(void);    /* changes whenever rules_cells() does */
const uint8_t *rules_cells(void);    /* the whole map, MAP_W * MAP_H CELL_* (row-major), for the view to read fast */

uint8_t  rules_bug_count(void);
uint8_t  rules_bugs_left(void);
uint8_t  rules_squashed(void);
int32_t  rules_bug_x(int i);
int32_t  rules_bug_y(int i);
uint8_t  rules_bug_state(int i);
uint8_t  rules_bug_hp(int i);
uint8_t  rules_bug_sees(int i);
uint16_t rules_bug_anim(int i);      /* frames in the current state */
uint8_t  rules_bug_biting(int i);    /* frames left of the bite pose */

/* Line of sight between two map points (walls and doors that are not fully open block), as the bugs and the
   hitscan use it. Exposed for tests. */
uint8_t  rules_los(int32_t x0, int32_t y0, int32_t x1, int32_t y1);

/* Tests only: load a MAP_W x MAP_H level from rows (the level/map.txt legend) and start playing it at once. */
void     rules_test_setup(const char *rows, uint16_t angle);

#endif
