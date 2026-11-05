/* MARINE DRIVE GP's rules: a three-lap kart race on a 1024 x 1024 px track plane against three AI rivals. Plain
   C99, integers only, one module-global state; the ROM and out/librules.so compile this same code. The arcade
   interface (game_init, game_step, game_hash, game_result, game_ghost, GAME_INFO) is in arcade/src/ac_game.h and
   game_ended() in games/common/src/arcade_game_ext.h; below are the extra reads the view and the tests use.

   Plane: x right, y down, in Q16.16 pixels of the track map. Headings: 1024 steps, 0 = +x, 256 = +y (ac_sin/ac_cos). */
#ifndef GAME_H
#define GAME_H
#include <stdint.h>
#include "ac_game.h"
#include "arcade_game_ext.h"

enum { SC_TITLE = 0, SC_HOWTO = 1, SC_COUNTDOWN = 2, SC_RACE = 3, SC_PAUSE = 4, SC_FINISH = 5, SC_RESULTS = 6 };
enum { TROPHY_WIN = 1, TROPHY_FAST = 2, TROPHY_CLEAN = 4, TROPHY_DRIFTS = 8 };
enum { SURF_ROAD = 0, SURF_CURB = 1, SURF_SLOW = 2, SURF_WALL = 3, SURF_BOOST = 4 };
enum { DRIFT_NONE = 0, DRIFT_LEFT = 1, DRIFT_RIGHT = 2 };
enum { EV_LAP = 1, EV_BOOST = 2, EV_WALL = 4, EV_DRIFT_BOOST = 8, EV_FINAL_LAP = 16, EV_GO = 32, EV_FINISH = 64 };
#define N_KARTS 4                 /* kart 0 is the player, 1..3 the rivals */

typedef struct {
    int32_t x, y;                 /* centre, Q16.16 px */
    int32_t vx, vy;               /* velocity, Q16.16 px per frame */
    int32_t speed;                /* velocity along the heading, Q16.16 (negative: reversing) */
    int32_t progress;             /* (lap - 1) * track length + arc position along the centre line, 1/16 px */
    uint32_t finish_frame;        /* race frame the kart finished on (0: not yet) */
    uint16_t heading;             /* 0..1023 */
    uint16_t drift_charge;        /* frames of the current drift */
    uint16_t boost;               /* boost frames left */
    uint16_t wall_hits;           /* over the race */
    uint8_t lap;                  /* start/finish line crossings in order: 1 on lap 1, LAPS + 1 when finished */
    uint8_t cp;                   /* the last checkpoint sector reached in order */
    uint8_t surface;              /* SURF_* under the centre */
    uint8_t drift;                /* DRIFT_* */
    uint8_t finished;
    uint8_t place;                /* 1..4 */
    uint8_t lap_boosts;           /* drift boosts this lap */
    uint8_t lap_clean;            /* 1 while this lap has had no wall hit */
    int8_t steer;                 /* the wheel: heading steps a frame at full speed, turning STEER_RAMP a frame */
} md_kart;

uint8_t  rules_scene(void);
uint16_t rules_countdown(void);        /* countdown frames left (SC_COUNTDOWN, or paused from it) */
uint8_t  rules_paused_from(void);      /* SC_PAUSE: the scene it returns to */
uint32_t rules_race_frames(void);      /* frames since GO (not paused); runs on under the FINISH banner (the
                                          player's time is its finish_frame) */
uint16_t rules_scene_frames(void);     /* frames spent in the current scene, saturating (for banners) */
uint8_t  rules_finished(void);         /* 1 once the player completed the last lap */
uint32_t rules_trophies(void);
uint8_t  rules_placement(void);        /* the player's place, 1..4 (final once finished) */
void     rules_kart(int i, md_kart *out);
uint8_t  rules_order(int place);       /* the kart in 1-based place (the standings) */
uint8_t  rules_events(void);           /* EV_* bits raised by the player in the last step, for the view */
uint32_t rules_lap_frames(int lap);    /* the player's lap times (lap 1..LAPS), 0 until done */
uint8_t  rules_surface_at(int32_t px, int32_t py);   /* SURF_* of the map cell holding pixel (px, py) */
uint8_t  rules_sector_at(int32_t px, int32_t py);    /* checkpoint sector nearest pixel (px, py) */
int32_t  rules_track_len(void);        /* centre line length, px */
uint8_t  rules_n_waypoints(void);
/* Tests only (the ROM never calls these): put kart i at pixel (px, py) facing heading, at rest, re-tracked; move it
   without re-tracking; set its speed along its heading, lap and checkpoint; force some karts' input to 0 (bit i). */
void     rules_debug_place(int i, int32_t px, int32_t py, uint16_t heading);
void     rules_debug_move(int i, int32_t px, int32_t py);
void     rules_debug_set(int i, int32_t speed, uint8_t lap, uint8_t cp);
void     rules_debug_freeze(uint8_t mask);

#endif
