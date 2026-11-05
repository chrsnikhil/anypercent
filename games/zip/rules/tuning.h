/* ZIP's numbers, in one place (tests read them with conftest.tuning()). Integers only.
   Speeds and accelerations are Q8.8 pixels per frame; positions Q8.8 pixels; angles 0-255 per turn in the rules
   (the kit's ac_sin/ac_cos take 1024 steps: angle * 4). A positive angle is a surface rising to the right. */
#ifndef TUNING_H
#define TUNING_H

#define GHOST_PERIOD     2            /* ghost sample period (fast motion) */
#define UNDER_FRAMES     5400         /* "Under 1:30" */
#define PACKETS_TROPHY   100          /* "100 packets": holding this many at once */
#define GOAL_FRAMES      90           /* frames of the goal celebration after the finish gate, before the results */
#define RESULTS_LOCK     30           /* results ignore Start for this many frames */
#define BOT_MIN_FRAMES   2400         /* tests: the bot's route finishes in 0:40 .. 1:30 */
#define BOT_MAX_FRAMES   5400

/* ground */
#define ACCEL            0x000C
#define DECEL            0x0080       /* pressing against the motion */
#define FRICTION         0x000C
#define TOP_SPEED        0x0600       /* the d-pad accelerates up to this */
#define MAX_SPEED        0x1000       /* absolute cap on every speed */
#define SLOPE_RUN        0x0020
#define SLOPE_ROLL_UP    0x0014
#define SLOPE_ROLL_DOWN  0x0050
#define ROLL_FRICTION    0x0006
#define ROLL_DECEL       0x0020       /* pressing against a roll */
#define ROLL_MIN         0x0100       /* Down rolls at this ground speed or more */
#define UNROLL_SPEED     0x0080       /* a roll slower than this stands up */
#define SLIP_SPEED       0x0280       /* the fall-off threshold: slower than this beyond 45 degrees (the loop) falls */
#define SLIP_ANGLE       32           /* 45 degrees: a slope this steep or steeper can slip */
#define SLIP_TRIGGER     0x0080       /* slower than this on a 45-degree slope: slip (input locked, slide down) */
#define SLIP_LOCK        8            /* the lock lasts while the ground is steep, then this many frames */

/* air */
#define AIR_ACCEL        0x0018
#define GRAVITY          0x0038
#define JUMP_SPEED       0x0680       /* along the surface normal */
#define JUMP_CAP         0x0400       /* releasing A while rising faster than this cuts the rise to it */
#define MAX_FALL         0x1000
#define SUBSTEP_PX       4            /* no movement sub-step is longer than this (pixels, each axis) */

/* body (pixels from the centre) */
#define BODY_W           6            /* foot sensors at x +- BODY_W */
#define BODY_H           10           /* feet at y + BODY_H; head at y - BODY_H */
#define WALL_W           7            /* side sensors at x +- WALL_W */
#define WALL_DY          2            /* ground side sensor at y - WALL_DY (12 px above the feet) */
#define SNAP_MAX         14           /* the feet follow a surface up to this far away */

/* things */
#define SPRING_YELLOW    0x0A00
#define SPRING_RED       0x0D00
#define BOOST_SPEED      0x0C00
#define SPRING_ANIM      12           /* frames a fired spring animates */
#define LOOP_MIN_SPEED   0x0700       /* enter a loop at this ground speed or more to go round */
#define LOOP_FULL_SPEED  0x0900       /* "Loop at full speed" */
#define LOOP_GRAV        0x0020       /* slope factor along the loop path */
#define LOOP_PUSH        0x0200       /* falling off a loop pushes back this fast */
#define LOOP_STEP_PX     4            /* the loop path's points are this many pixels of arc apart */

/* packets and hits */
#define PACKET_R         6            /* packet half size for pickups */
#define SCATTER_MAX      32
#define SCATTER_WAIT     64           /* frames before a scattered packet can be picked up */
#define SCATTER_LIFE     240          /* frames before it vanishes */
#define SCATTER_GRAVITY  0x0018
#define SCATTER_FAST     0x0400
#define SCATTER_SLOW     0x0200
#define INVULN_FRAMES    60
#define HURT_XV          0x0200
#define HURT_YV          0x0400
#define BUG_SPEED        0x0080
#define BUG_R            7

#endif
