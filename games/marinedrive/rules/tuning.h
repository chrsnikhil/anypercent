/* MARINE DRIVE GP's numbers, in one place (tests read them with conftest.tuning()). Integers only.
   Speeds are Q16.16 px per frame on the 1024 x 1024 px track plane; headings are 1024 steps a turn.
   The plan's speeds (top 3.0, curb 2.25, sand 1.375, boosts 4.5) are scaled by 0.8 so three laps of this 5.4 km
   (5424 px) circuit take the spec's 1:45-2:45; accelerations, brakes and drags are the plan's. */
#ifndef TUNING_H
#define TUNING_H

#define COUNTDOWN_FRAMES   180          /* 3-2-1-GO */
#define LAPS               3
#define FINISH_FRAMES      150          /* the FINISH banner before the results card */
#define RACE_LIMIT         36000        /* 10:00: the race ends unfinished (keeps a run log bounded) */
#define FAST_FRAMES        8100         /* "Under 2:15" */
#define DRIFT_TROPHY_BOOSTS 3           /* "Three drift boosts in one lap" */

/* Handling (rules 4, 2026-10-24: arcade, Mario Kart-like): a torque curve, a steering wheel that ramps, steering that
   eases at speed, braking that turns in, grip that gives way in a hard turn at speed, walls that bounce. */
#define ACCEL_LAUNCH       0x00001400   /* the pull from rest ... */
#define ACCEL_TOP_END      0x00000600   /* ... falling in a straight line to this at the surface's top speed */
#define TOP_ROAD           0x00026666   /* 2.4 px/frame (the plan's 3.0 x 0.8: see the ruling) */
#define TOP_CURB           0x0001CCCC
#define TOP_SLOW           0x00011999
#define BRAKE              0x00002000
#define REVERSE_ACCEL      0x00000600
#define REVERSE_MAX        0x00008000
#define COAST_DRAG         0x00000600
#define OVER_TOP_DRAG      0x00001800   /* above the surface's top speed (after a boost, on sand): slows this much */
#define STEER              6            /* heading steps per frame at full steering (the wheel at full lock) */
#define STEER_RAMP         2            /* the wheel turns this much a frame toward where the d-pad holds it */
#define STEER_FULL_SPEED   0x00013333   /* steering reaches STEER at this speed; scales linearly below it */
#define STEER_TAPER_SPEED  0x00020000   /* above this (2.0 px/frame), full lock turns STEER_AT_TOP ... */
#define STEER_AT_TOP       5
#define STEER_AT_BOOST     4            /* ... and above TOP_ROAD (boosting), STEER_AT_BOOST */
#define STEER_BRAKE_BONUS  1            /* braking above STEER_FULL_SPEED with the wheel turned: weight forward */
#define GRIP_Q8            96           /* sideways velocity kept per frame, /256 (the rest is scrubbed) */
#define SLIP_GRIP_Q8       136          /* above STEER_TAPER_SPEED at full lock the tyres give: this much is kept */
#define DRIFT_GRIP_Q8      232          /* while drifting: the kart slides */
#define DRIFT_STEER        9            /* heading steps per frame steering into the drift */
#define DRIFT_STEER_BASE   5            /* steering into the drift with the d-pad released */
#define DRIFT_STEER_OUT    2            /* steering against the drift */
#define DRIFT_MIN_SPEED    0x00013333   /* half of TOP_ROAD: drifting starts and holds above it */
#define DRIFT_CHARGE       45           /* frames of drift for a boost on release (blue sparks) ... */
#define DRIFT_CHARGE_2     90           /* ... and for the bigger one (orange sparks) */
#define DRIFT_BOOST_SPEED  0x00039999
#define DRIFT_BOOST_FRAMES 30
#define DRIFT_BOOST2_FRAMES 50
#define PAD_BOOST_SPEED    0x00039999
#define PAD_BOOST_FRAMES   60
#define KART_RADIUS        6            /* px: walls and kart-kart contacts */
#define WALL_BOUNCE_Q8     96           /* a wall hit: the speed into the wall comes back out at this, /256 ... */
#define WALL_SCRAPE_Q8     192          /* ... and the speed along it is kept at this: head-on hurts, a scrape less */
#define BUMP_SHARE_Q8      64           /* velocity exchanged on a kart-kart contact, /256 */
#define TRACK_SEARCH       4            /* centre points searched either side of a kart's last one per frame */
#define TRACK_CORRIDOR     64           /* px from the centre line: beyond it a kart's point does not follow */

#define AI_SKILL_1_Q8      236          /* rival top speed as a fraction of TOP_ROAD, /256: 0.92, 0.96, 1.00 */
#define AI_SKILL_2_Q8      246
#define AI_SKILL_3_Q8      256
#define AI_REACH           40           /* px: a waypoint within this distance is passed (its speed is the target) */
#define AI_LOOK            5            /* rivals steer at the centre point this many points ahead of theirs ... */
#define AI_LOOK_PER_PX     2            /* ... plus this many per px/frame of speed */
#define AI_LANE_1          (-8)         /* each rival's line, px right of the centre line */
#define AI_LANE_2          8
#define AI_LANE_3          0
/* A seeded race (any seed but 0) varies each rival: its line by up to AI_LANE_JITTER px either way, its pace down by
   up to AI_SKILL_JITTER /256 (never faster than the classic race), and a launch delay of up to AI_LAUNCH_MAX frames. */
#define AI_LANE_JITTER     10
#define AI_SKILL_JITTER    10
#define AI_LAUNCH_MAX      30

#endif
