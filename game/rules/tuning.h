/* Every number to adjust in playtesting (values from the spec). Positions and speeds are in quarter
   pixels. Vertical speeds and reaches are half the horizontal ones: the isometric floor is foreshortened. */
#ifndef TUNING_H
#define TUNING_H

#define DEVS            3
#define WALK_X          6       /* 1.5 px per frame across */
#define WALK_Y          3       /* 0.75 px per frame up and down */
#define DASH_X          14      /* 3.5 px per frame */
#define DASH_Y          7
#define DASH_FRAMES     10
#define DASH_COOLDOWN   60
#define FEET_HALF       3       /* px: the feet are 7 px wide */
#define REACH_X         16      /* px: how close you must be to use something */
#define REACH_Y         8
#define ENERGY_MAX      255
#define START_ENERGY    {200, 140, 90}
#define DRAIN_FRAMES    3
#define TYPE_FRAMES     26
#define PROGRESS_MAX    1000
#define ACT1_GOAL       400
#define FRAMES_PER_HOUR 450
#define DEADLINE_HOURS  36
#define RNG_SEED        0xACE1u

/* Act 2: Midnight bugs (schedules are in frames since Act 2 began) */
#define ACT2_GOAL        800
#define NIGHTFALL_FRAMES 120
#define MAX_BUGS         6
#define BUG_STEP_X       2      /* 0.5 px per frame across */
#define BUG_STEP_Y       1      /* 0.25 px per frame up and down */
#define COMMIT_FRAMES    30
#define COMMIT_MIN       50     /* the shelf offers a commit once the bar is this far past the last one (5%) */
#define COMMIT_NUDGE     60     /* the arrow suggests committing once the bar is this far past the last commit */
#define PIZZA_FRAME      1500
#define MESSAGE_FRAMES   90
#define BUG_COUNT        18
#define BUG_SCHEDULE     { {240, 0, 1}, {540, 1, 0}, {840, 2, 2}, {1140, 0, 1}, {1440, 1, 0}, {1740, 2, 2}, \
                           {2040, 0, 1}, {2340, 1, 0}, {2640, 2, 2}, {2940, 0, 1}, {3240, 1, 0}, {3540, 2, 2}, \
                           {3840, 0, 1}, {4140, 1, 0}, {4440, 2, 2}, {4740, 0, 1}, {5040, 1, 0}, {5340, 2, 2} }
#define FRY_COUNT        6
#define ROUTER_FRIES     {600, 1200, 1800, 2400, 3000, 3600}
/* A seeded run (any seed but 0) shifts each of the above by up to this many frames either way (rules.c) */
#define BUG_JITTER       90
#define FRY_JITTER       120
#define PIZZA_JITTER     180
#define ENERGY_JITTER    24     /* ... and each dev's START_ENERGY by up to this much */

/* Act 3: Demo */
#define GATE_HALF_X      12     /* px around the hall's gate anchor that stay shut until the World scan */
#define GATE_HALF_Y      6
#define CARRY_X          4      /* 1 px per frame across with the laptop */
#define CARRY_Y          2
#define DEMODAY_FRAMES   120
#define WALKOUT_FRAMES   60     /* the room switches halfway, on the black screen */
#define CROWD_STEP       2      /* quarter px per frame along the longer axis, in a straight line to the waypoint */
#define BUMP_X           8      /* px between the player's feet and an attendee's that count as a bump */
#define BUMP_Y           4
#define STUN_FRAMES      30
#define IMMUNE_FRAMES    60     /* after a stun ends */
#define PITCH_SLIDES     5
#define PITCH_STEP       40     /* bar per correct slide: 800 + 5 x 40 = 1000 */
#define PITCH_KEYS       {BTN_A, BTN_RIGHT, BTN_B, BTN_UP, BTN_A}
#define STUMBLE_FRAMES   30
#define SHIPPED_FRAMES   120    /* SHIPPED! alone before the results (and before Start works) */
#define CROWD_PAUSE_MIN  30     /* an attendee stands at each waypoint for MIN + (k*37 + wp*53) % SPAN frames */
#define CROWD_PAUSE_SPAN 91
#define GRADE_S          24     /* ship hour (inclusive) for each grade; later is C, a missed deadline F */
#define GRADE_A          28
#define GRADE_B          32

#endif
