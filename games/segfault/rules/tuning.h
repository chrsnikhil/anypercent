/* SEGFAULT's numbers, in one place (tests read them with conftest.tuning()). Integers only.
   Map units: Q16.16, 0x10000 = one grid tile. Angles: 1024 steps a turn, 0 = east (+x), 256 = south (+y). */
#ifndef TUNING_H
#define TUNING_H

#define MAP_W            48
#define MAP_H            48
#define MAX_BUGS         28
#define MAX_DOORS        24

#define MOVE_SPEED       0x00002000   /* forward/back per frame */
#define STRAFE_SPEED     0x00002000
#define TURN_SPEED       10           /* angle steps per frame */
#define PLAYER_RADIUS    0x4000

#define FIRE_COOLDOWN    18           /* frames between shots (hold A to keep firing) */
#define FIRE_RANGE       0x100000     /* 16 tiles */
#define HIT_RADIUS       0x5000       /* a shot hits a bug whose centre is this close to the aim line */
#define BUG_HP           2
#define BUG_RADIUS       0x3000
#define BUG_SPEED        0x00000C00
#define BUG_SIGHT        0x80000      /* chase when in line of sight within 8 tiles */
#define BUG_REACH        0x12000      /* attack when this close (centre to centre, the larger axis distance) */
#define BUG_ATTACK_EVERY 45
#define BUG_FIRST_BITE   20           /* frames from reaching the player to the first bite */
#define BUG_DAMAGE       10
#define BUG_GIVE_UP      180          /* frames without sight before a chasing bug goes idle */
#define BUG_HURT_FRAMES  12           /* a hit bug is stunned this long */
#define BUG_NUDGE_TRIES  4            /* a seeded run tries this many nudges of each bug's spawn (up to 2 cells) */
#define BUG_NUDGE_SAFE   3            /* a nudged bug keeps more than this many cells from the player's start */

#define DOOR_FRAMES      30           /* a door slides open (and shut) over this many frames */
#define DOOR_OPEN_HOLD   180          /* an open door starts closing after this long unless blocked */
#define PUSH_FRAMES      30           /* the secret wall slides away */
#define USE_REACH        0x1A000      /* B reaches a door or panel this far ahead of the player's centre */

#define HEALTH_MAX       100
#define HEALTH_START     100
#define HEALTH_PICKUP    25
#define DEATH_FRAMES     90           /* the "core dumped" screen before the level restarts */
#define MSG_FRAMES       120
#define UNDER_FRAMES     10800        /* "Under 3:00" */

#endif
