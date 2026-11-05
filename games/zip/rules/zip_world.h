/* ZIP's world: the player's momentum physics on the level's surfaces, the loop, springs, boosters, packets, bugs,
   the checkpoint and the finish. One module-global instance, read by game.c, the view and the tests. */
#ifndef ZIP_WORLD_H
#define ZIP_WORLD_H
#include <stdint.h>
#include "ac_hash.h"

enum { MODE_GROUND = 0, MODE_AIR = 1, MODE_LOOP = 2 };
/* pose (for the view): what the player is doing */
enum { POSE_STAND = 0, POSE_RUN = 1, POSE_ROLL = 2, POSE_JUMP = 3, POSE_SPRING = 4, POSE_HURT = 5, POSE_FALL = 6 };

typedef struct {
    int32_t x, y;               /* centre, Q8.8 pixels */
    int32_t xv, yv;             /* air velocity, Q8.8 px/frame */
    int32_t gsp;                /* ground (or loop path) speed */
    uint8_t mode, angle, pose;
    uint8_t rolling, ball;      /* ball: curled (a roll or a jump): hurts bugs */
    uint8_t jumping;            /* in a jump that A's release can cut */
    uint8_t facing;             /* 0 right, 1 left */
    uint8_t slip_lock;          /* input ignored for this many frames */
    uint8_t invuln, hurt;       /* invulnerable frames; hurt: knocked back until landing */
    uint16_t packets, hits, respawns;
    uint8_t loop_full, at_finish, checkpoint;
    uint8_t sprung;             /* launched by a spring, still rising */
    uint8_t loop_quarter_fail;  /* this loop visit falls off at the quarter point */
    int32_t loop_pos;           /* Q8.8 pixels of arc travelled on the loop path */
    int32_t loop_x, loop_y;     /* the loop being run: its entry point (the player's centre there), pixels */
    uint16_t fell_off_loop;     /* times the player fell off a loop */
    uint32_t frames;            /* world steps in play */
} world_t;

typedef struct {                /* a scattered packet */
    int32_t x, y;               /* Q8.8 */
    int16_t xv, yv;
    uint16_t age;               /* 0: free slot; frames since it was scattered */
} zip_scatter;

const world_t *world(void);
void world_init(uint32_t seed);          /* the level's initial state (before play); seed 0: the classic bugs */
void world_start(void);                  /* play begins */
void world_step(uint16_t buttons, uint16_t pressed, int autopilot);
void world_hash(ac_hash *h);
uint8_t world_ent_state(int i);          /* the state of thing i (zip_level.h): taken, squashed, spring frames, lit */
const zip_scatter *world_scatter(int i); /* i < SCATTER_MAX */
int32_t world_bug_x(int i);              /* bug thing i's centre x now, Q8.8 */
int     world_bug_left(int i);           /* 1 while bug thing i walks left (its sprite faces left) */
int world_solid(int32_t px, int32_t py); /* is this level pixel solid */

#endif
