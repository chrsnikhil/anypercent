// The raycaster's shared state (raycaster.cpp sets it up, raycaster.bn_iwram.cpp renders from it).
#ifndef SEGF_RAYCASTER_STATE_H
#define SEGF_RAYCASTER_STATE_H

#include "raycaster.h"

namespace ray::detail
{
    constexpr int map_w = 48;
    constexpr int tex = 64;
    constexpr int proj = 182;            // wall height in pixels at distance 1 (120 columns over a 0.66 plane)
    constexpr int recip_n = 4800;
    constexpr int door_tex = 4;          // texture numbers that slide: the door and the secret wall
    constexpr int push_tex = 10;
    constexpr int locked_tex = 11;
    constexpr int slide_frames = 30;

    extern uint8_t* textures;            // EWRAM copy, [tex][x][y]
    extern int32_t* recip;               // 1 / x, x in Q12 -> Q16 (EWRAM)
    constexpr int lh_shift = 6;          // wall heights by perpendicular distance in Q10 (perp >> 6)
    constexpr int lh_n = 24 << 10;
    extern uint16_t* line_heights;       // proj / distance in pixels, clamped (EWRAM)
    constexpr int32_t step_per_perp = (tex << 16) / proj;   // texels per pixel = perp * tex / proj
    extern uint8_t cells[map_w * map_w];
    extern uint8_t* doors;               // EWRAM
    extern uint8_t* raw;                 // the rules' cells as they are (CELL_*), for the radar (EWRAM)
    constexpr int max_sliding = 24;
    extern uint16_t door_list[max_sliding];        // indices of the sliding cells (doors, the secret wall)
    extern int n_door_list;
    extern int32_t camx[cols];           // -1 .. 1 across the columns, Q16
    extern int32_t zbuf[cols];
    extern uint32_t bg_words[view_h / 4];
    extern camera cam;
    extern billboard* bills[max_billboards];   // far to near
    extern int n_bills;
    extern uint32_t drawn;
}

#endif
