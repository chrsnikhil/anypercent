/* RUSH HOUR's numbers, in one place (tests read them with conftest.tuning()). Integers only.
   Speeds and accelerations are Q8.8 pixels per frame (0x0100 = one pixel a frame); times are 60 Hz frames. */
#ifndef TUNING_H
#define TUNING_H

#define TILE            16          /* the collision grid, in pixels */
#define PLAYER_W        12          /* the player's hitbox, in pixels */
#define PLAYER_H        14

#define WALK_MAX        0x0180
#define RUN_MAX         0x0300      /* B held */
#define GROUND_ACCEL    0x0028
#define AIR_ACCEL       0x0018
#define FRICTION        0x0030
#define TURN_DECEL      0x0060
#define GRAVITY         0x0040
#define GRAVITY_HOLD    0x0020      /* while A is held and the player is rising from a jump */
#define JUMP_VY         (-0x0520)
#define MAX_FALL        0x0600
#define COYOTE_FRAMES   6
#define BUFFER_FRAMES   6
#define STOMP_HI        (-0x0380)   /* bounce off a bug with A held */
#define STOMP_LO        (-0x0280)
#define HURT_VX         0x0200
#define HURT_VY         (-0x0300)
#define HURT_LOCK       16          /* frames without control after a hit */
#define INVULN_FRAMES   60
#define DROP_FRAMES     8           /* one-way platforms are ignored this long after Down + A */
#define DEATH_FRAMES    45          /* the player lies still this long before the respawn (the clock runs) */
#define MAX_HP          3

#define BUG_SPEED       0x0080
#define BUG_W           14
#define BUG_H           12
#define SQUASH_FRAMES   24          /* a stomped bug stays flat this long (drawn only) */
#define PATROL_SCAN     32          /* a seeded start looks this many tiles each way for the end of a bug's patrol */
#define STOMP_SLACK     8           /* a stomp: last frame the player's feet were at most this far below the bug's top */

#define UNDER_FRAMES    7200        /* "Under 2:00" */
#define TIME_UP_FRAMES  210000      /* 58:20: the run ends unfinished (a run log may hold at most 216000 frames) */

#endif
