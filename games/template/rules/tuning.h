/* The template's numbers, in one place (tests read them with conftest.tuning()). Integers only. */
#ifndef TUNING_H
#define TUNING_H

#define FIELD_W      240          /* the play field in pixels: the whole screen below the HUD row */
#define FIELD_TOP    16
#define FIELD_H      160
#define DOT_SIZE     8
#define DOT_SPEED    1            /* pixels per frame on each axis */
#define START_X      16
#define START_Y      76
#define GOAL_X       200
#define GOAL_Y       120
#define GOAL_SIZE    8
#define GOAL_MIN_X   120          /* a seeded run (any seed but 0) puts the goal's top-left in this region */
#define GOAL_MAX_X   224
#define GOAL_MIN_Y   24
#define GOAL_MAX_Y   144
#define FAST_FRAMES  300          /* "Under 5 seconds": reach the goal within this many play frames */

#endif
