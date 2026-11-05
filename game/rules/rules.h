/* SHIP IT! game rules: plain C, one frame per rules_step(). Shared by the ROM and the PC tests. */
#ifndef RULES_H
#define RULES_H
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define BTN_A      0x001
#define BTN_B      0x002
#define BTN_SELECT 0x004
#define BTN_START  0x008
#define BTN_RIGHT  0x010
#define BTN_LEFT   0x020
#define BTN_UP     0x040
#define BTN_DOWN   0x080
#define BTN_R      0x100
#define BTN_L      0x200

#define SC_TITLE   0
#define SC_PLAY    1
#define SC_CLEAR   2
#define SC_MISSED  3
#define SC_HOWTO   4
#define SC_NIGHTFALL 5
#define SC_DEMODAY 6
#define SC_WALKOUT 7

#define ROOM_OFFICE 0
#define ROOM_HALL   1

#define HINT_NONE  0
#define HINT_TAKE  1
#define HINT_GIVE  2
#define HINT_STOMP 3
#define HINT_RESET 4
#define HINT_PAY   5
#define HINT_COMMIT 6
#define HINT_LAPTOP 7
#define HINT_SCAN   8
#define HINT_PITCH  9

#define MSG_SAVED    1
#define MSG_PAID     2
#define MSG_ROLLBACK 3
#define MSG_VERIFIED 4
#define MSG_STUMBLE  5

#define TARGET_COUNTER 0
#define TARGET_DEV     1       /* dev k is TARGET_DEV + k */
#define TARGET_ROUTER  4
#define TARGET_DOOR    5
#define TARGET_SHELF   6
#define TARGET_BUG     8       /* bug i is TARGET_BUG + i */
#define TARGET_LAPTOP  14
#define TARGET_ORB     15
#define TARGET_STAGE   16

#define ITEM_NONE  0
#define ITEM_CHAI  1
#define ITEM_LAPTOP 2

void rules_init(void);                  /* the classic run: rules_init_seeded(0) */
void rules_init_seeded(uint32_t seed);  /* seed 0: classic; else act 2's timetable and starting energies shift */
void rules_step(uint16_t buttons);
uint16_t rules_schedule(int k);         /* tests: bug spawns, router fries, the pizza, starting energies, in order */

uint8_t  rules_scene(void);
uint8_t  rules_paused(void);
uint8_t  rules_carrying(void);
uint8_t  rules_moving(void);
uint8_t  rules_facing(void);
uint8_t  rules_dash_cool(void);
uint8_t  rules_hour(void);
uint8_t  rules_energy(uint8_t i);
uint16_t rules_px(void);
uint16_t rules_py(void);
uint16_t rules_qx(void);
uint16_t rules_qy(void);
uint16_t rules_progress(void);
uint16_t rules_hour_frames(void);
uint32_t rules_run_frames(void);
uint32_t rules_hash(void);
uint8_t  rules_walkable(int16_t x, int16_t y);
uint8_t  rules_hint(void);          /* what A would do right now */
uint8_t  rules_hint_dev(void);      /* the dev a HINT_GIVE refers to */
uint8_t  rules_target(void);        /* the next objective for the pointers */
uint8_t  rules_clock_running(void); /* 0 until the first chai is handed over */
uint8_t  rules_hint_arg(void);      /* the dev for HINT_GIVE, the bug for HINT_STOMP */
uint8_t  rules_act(void);
uint8_t  rules_nightfall(void);     /* frames left in SC_NIGHTFALL */
uint16_t rules_act_frames(void);
uint8_t  rules_bug_on(uint8_t i);
uint16_t rules_bug_x(uint8_t i);
uint16_t rules_bug_y(uint8_t i);
uint8_t  rules_bug_sitting(uint8_t i);
uint8_t  rules_bug_desk(uint8_t i);
uint8_t  rules_router_fried(void);
uint16_t rules_last_commit(void);
uint8_t  rules_commit_hold(void);
uint8_t  rules_pizza(void);          /* 0 not yet, 1 waiting at the door, 2 paid */
uint8_t  rules_message(void);        /* MSG_* while shown, else 0 */
uint32_t rules_split(uint8_t act);
uint8_t  rules_room(void);
uint8_t  rules_demoday(void);
uint8_t  rules_walkout(void);
uint8_t  rules_verified(void);
uint8_t  rules_stun(void);
uint8_t  rules_immune(void);
uint8_t  rules_slide(void);
uint8_t  rules_stumble(void);
uint16_t rules_pitch_key(void);
uint8_t  rules_crowd_count(void);
uint16_t rules_crowd_x(uint8_t i);
uint16_t rules_crowd_y(uint8_t i);
uint8_t  rules_crowd_facing(uint8_t i);
uint8_t  rules_clear_frames(void);
uint8_t  rules_crowd_paused(uint8_t i);
uint8_t  rules_crowd_gathered(uint8_t i);
uint8_t  rules_crowd_standing(uint8_t i);   /* paused at a waypoint or gathered: not walking */
uint8_t  rules_grade(void);          /* 'S' 'A' 'B' 'C' once shipped, 'F' on a missed deadline, else 0 */

void rules_debug_place(uint16_t x, uint16_t y);
void rules_debug_energy(uint8_t i, uint8_t e);
void rules_debug_progress(uint16_t p);
void rules_debug_clock(uint8_t hour, uint16_t frames);
void rules_debug_act2(uint16_t progress);
void rules_debug_act_frames(uint16_t n);
void rules_debug_act3(uint8_t room);
void rules_debug_verified(uint8_t v);

#ifdef __cplusplus
}
#endif

#endif
