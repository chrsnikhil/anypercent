// The Mode 7 inner loops, compiled as ARM code in IWRAM (mode7.bn_iwram.cpp): the per-scanline affine registers of
// the ground and the culling/projection of the track's props. See view.cpp for the camera model.
#ifndef MD_MODE7_H
#define MD_MODE7_H

#include "bn_common.h"

namespace md
{
    constexpr int HORIZON = 48;             // the first ground line (the lines above are the skyline)
    constexpr int HAZE = 3;                 // lines under the horizon left to the backdrop (the sea): no shimmer
    constexpr int FOCAL = 128;
    constexpr int CAM_H = 44;
    constexpr int CAM_DIST = 64;
    constexpr int NEAR = 12;                // px: nearer sprites are hidden
    constexpr int FAR = 720;                // px: farther props are hidden
    constexpr int PROP_NEAR = 28;           // px: nearer props are hidden (they would pass through the camera)

    // cam_x, cam_y in 1/256 px; s, c the heading's sine and cosine (Q14). Fills lines HORIZON + HAZE .. 159.
    BN_CODE_IWRAM void ground_lines(int cam_x, int cam_y, int s, int c, int16_t* pa, int16_t* pc, int* dx, int* dy);

    // Projects a plane point (1/256 px): false if behind, too near, too far or off screen. z8: distance, 1/256 px;
    // sx, sy: the screen point where it meets the ground.
    BN_CODE_IWRAM bool project(int cam_x, int cam_y, int s, int c, int px8, int py8, int& sx, int& sy, int& z8);

    // The nearest `max` visible props (track_props.h), nearest first; returns how many. orbs: include the World orbs.
    // The gantry is left out once it is nearer than the player (the camera passes under it).
    BN_CODE_IWRAM int cull_props(int cam_x, int cam_y, int s, int c, bool orbs, int max, int* idx, int* zs, int* sxs,
                                 int* sys);
}

#endif
